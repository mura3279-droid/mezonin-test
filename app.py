import io
import re
import hmac
import hashlib
from urllib.parse import quote

import pandas as pd
import streamlit as st

st.set_page_config(page_title='Мезонин — выкладка', page_icon='📦', layout='centered')
st.markdown('''<style>.block-container{max-width:780px;padding-top:1rem}div.stButton>button,div.stLinkButton>a{min-height:45px;border-radius:12px}@media(max-width:600px){.block-container{padding-left:12px;padding-right:12px}}</style>''', unsafe_allow_html=True)

ALIASES = {
    'name': ['наименование', 'название товара', 'наименование товара', 'товар'],
    'code': ['код товара', 'кодтовара', 'sku', 'код'],
    'barcode': ['штрихкод', 'штрих код', 'шк', 'barcode', 'ean'],
    'address': ['адрес', 'адрес хранения', 'адрес товара'],
    'stock': ['доступный остаток', 'остаток', 'количество', 'кол-во'],
    'unit': ['единица измерения', 'ед. изм.', 'ед изм', 'единица', 'ед.изм'],
    'group': ['группа товара', 'группа'],
    'subgroup': ['подгруппа товара', 'подгруппа'],
}

def clean(value):
    if pd.isna(value):
        return ''
    value = str(value).strip()
    return value[:-2] if re.fullmatch(r'\d+\.0', value) else value

def norm(value):
    return re.sub(r'\s+', ' ', str(value).strip().lower().replace('_', ' '))

def find_col(columns, options):
    for option in options:
        for col in columns:
            if norm(col) == option:
                return col
    for option in options:
        for col in columns:
            if option in norm(col):
                return col
    return None

def sortkey(value):
    return (0, int(value)) if str(value).isdigit() else (1, str(value))

def prepare(raw):
    raw = raw.fillna('').copy()
    columns = {key: find_col(raw.columns, names) for key, names in ALIASES.items()}
    if not columns['name'] or not columns['address']:
        raise ValueError('Нужны столбцы «Наименование» и «Адрес». Найдены: ' + ', '.join(map(str, raw.columns)))
    df = pd.DataFrame(index=raw.index)
    for key, col in columns.items():
        df[key] = raw[col].map(clean) if col else ''
    parts = df['address'].map(lambda x: x.split('.'))
    df['alley'] = parts.map(lambda p: p[2] if len(p) >= 5 else '')
    df['module'] = parts.map(lambda p: p[3] if len(p) >= 5 else '')
    df['shelf'] = parts.map(lambda p: p[4] if len(p) >= 5 else '')
    df = df[(df['alley'] != '') & (df['module'] != '')].copy()
    if df.empty:
        raise ValueError('В Excel нет адресов формата 8031.1.8.5.2')
    df['item_key'] = df.apply(lambda r: '|'.join([r['address'], r['code'], r['barcode'], r['name']]), axis=1)
    return df.drop_duplicates('item_key').reset_index(drop=True)

def state_of(key):
    return st.session_state.statuses.get(key, {}).get('status', 'none')

def render_item(r):
    key = r['item_key']
    with st.container(border=True):
        st.markdown('**' + r['name'] + '**')
        st.caption(f"Код: {r['code'] or '—'} · ШК: {r['barcode'] or '—'}")
        st.caption({'done':'🟢 Выставлен','missing':'🔴 Не найден','none':'🟡 Не выставлен'}[state_of(key)])
        if r['code']:
            url = 'https://s3-pic.e-magnum.kz/item/' + quote(r['code'], safe='') + '.jpg'
            st.link_button('📷 Открыть фото ↗', url, use_container_width=True)
        a, b, c = st.columns(3)
        a.metric('Аллея', r['alley'])
        b.metric('Модуль', r['module'])
        c.metric('Полка', r['shelf'])
        st.caption('Адрес: ' + r['address'])
        st.write(f"**Остаток:** {r['stock'] or '—'} {r['unit']}")
        if r['group'] or r['subgroup']:
            st.caption(' / '.join(x for x in [r['group'], r['subgroup']] if x))
        a, b = st.columns(2)
        if a.button('✓ Выставлен', key='done_'+key, type='primary', use_container_width=True):
            st.session_state.statuses[key] = {'status':'done', 'reason':''}
            st.rerun()
        if b.button('✕ Не найден', key='missing_'+key, use_container_width=True):
            st.session_state.statuses[key] = {'status':'missing', 'reason':'Нет на паллете'}
            st.rerun()
        if state_of(key) == 'missing':
            reasons = ['Нет на паллете', 'Не найден на складе', 'Другое']
            old = st.session_state.statuses[key].get('reason', reasons[0])
            selected = st.selectbox('Причина', reasons, index=reasons.index(old) if old in reasons else 0, key='reason_'+key)
            st.session_state.statuses[key]['reason'] = selected
