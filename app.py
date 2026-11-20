import hashlib
import hmac
import io
import re
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title='Мезонин — общая база', page_icon='📦', layout='centered', initial_sidebar_state='collapsed')
st.markdown('''<style>.block-container{padding-top:1rem;padding-bottom:3rem;max-width:760px}h1{font-size:1.65rem!important}div.stButton>button{min-height:46px;border-radius:12px}@media(max-width:600px){.block-container{padding-left:12px;padding-right:12px}}</style>''',unsafe_allow_html=True)
st.title('📦 Мезонин')
st.caption('Общая база выкладки · Supabase')

try:
    BASE = st.secrets['SUPABASE_URL'].rstrip('/') + '/rest/v1'
    KEY = st.secrets['SUPABASE_KEY']
except KeyError:
    st.error('Добавьте SUPABASE_URL и SUPABASE_KEY в Streamlit Secrets.')
    st.stop()
HEADERS = {'apikey': KEY, 'Authorization': 'Bearer ' + KEY, 'Content-Type': 'application/json'}

class DbError(Exception): pass

def api(method, table, params=None, payload=None, prefer=None):
    headers = dict(HEADERS)
    if prefer: headers['Prefer'] = prefer
    try:
        r = requests.request(method, f'{BASE}/{table}', headers=headers, params=params, json=payload, timeout=35)
        r.raise_for_status()
        return r.json() if r.content else []
    except requests.RequestException as e:
        msg = e.response.text[:450] if e.response is not None else str(e)
        raise DbError(msg) from e

def fetch_all(table, select='*', extra=None):
    result=[]
    for offset in range(0, 100000, 1000):
        p={'select':select,'limit':1000,'offset':offset}
        if extra:p.update(extra)
        chunk=api('GET',table,p)
        result.extend(chunk)
        if len(chunk)<1000:break
    return result

def norm(s): return re.sub(r'\s+',' ',str(s).strip().lower().replace('_',' '))
def clean(v):
    if pd.isna(v):return ''
    s=str(v).strip()
    return s[:-2] if re.fullmatch(r'\d+\.0',s) else s

def find_col(cols,opts):
    for o in opts:
        for c in cols:
            if norm(c)==o:return c
    for o in opts:
        for c in cols:
            if o in norm(c):return c
    return None

ALIASES={
 'name':['наименование','название товара','товар','наименование товара'],
 'code':['код товара','кодтовара','код','sku'],
 'barcode':['штрихкод','штрих код','шк','barcode','ean'],
 'address':['адрес','адрес хранения','адрес товара'],
 'stock':['доступный остаток','остаток','количество','кол-во'],
 'unit':['единица измерения','ед. изм.','ед изм','единица','ед.изм'],
 'group':['группа товара','группа'],
 'subgroup':['подгруппа товара','подгруппа']}

def parse_excel(file):
    df=pd.read_excel(file,dtype=str).fillna('')
    cols={k:find_col(df.columns,v) for k,v in ALIASES.items()}
    if not cols['address'] or not cols['name'] or not cols['code']:
        raise ValueError('Нужны столбцы «Адрес», «Наименование» и «Код товара».')
    rows={}
    for _,r in df.iterrows():
        d={k:clean(r[c]) if c else '' for k,c in cols.items()}
        a=d['address'].split('.')
        if len(a)<5 or not a[2].isdigit() or not a[3].isdigit() or not a[4].isdigit() or not d['code']:
            continue
        try:stock=float(d['stock'].replace(',','.')) if d['stock'] else 0
        except ValueError:stock=0
        item={'product_code':d['code'],'barcode':d['barcode'],'product_name':d['name'],
          'product_group':d['group'],'subgroup':d['subgroup'],'unit':d['unit'],
          'available_stock':stock,'warehouse':a[0],'zone':a[1],
          'aisle':int(a[2]),'module':int(a[3]),'shelf':int(a[4]),'address':d['address']}
        rows[(d['code'],d['address'])]=item
    return list(rows.values())

# Admin access: set ADMIN_PASSWORD in Streamlit Secrets. This protects uploads and reports,
# not individual operator identity. For verified employee attribution add authentication.
admin_password=st.secrets.get('ADMIN_PASSWORD','')
if not admin_password:
    st.error('Для безопасной загрузки Excel добавьте ADMIN_PASSWORD в Streamlit Secrets и перезапустите приложение.')
    st.stop()
with st.sidebar:
    st.subheader('Руководитель')
    attempt=st.text_input('Пароль руководителя',type='password')
    is_admin=hmac.compare_digest(attempt,admin_password) if attempt else False

if is_admin:
    with st.expander('📄 Загрузить Excel в общую базу'):
        st.warning('Загрузка обновляет ассортимент и остатки. Существующие статусы сохраняются. Удалённые из Excel позиции автоматически не удаляются.')
        upload=st.file_uploader('Excel с ассортиментом',type=['xlsx'])
        if upload is not None:
            try:
                records=parse_excel(upload)
                st.write(f'Подготовлено позиций: {len(records)}')
                if st.button('Загрузить / обновить общую базу',type='primary'):
                    if not records: st.warning('Нет корректных адресов.')
                    else:
                        with st.spinner('Загружаем...'):
                            for i in range(0,len(records),200):
                                api('POST','products',{'on_conflict':'product_code,address'},records[i:i+200],
                                    'resolution=merge-duplicates,return=minimal')
                        st.success(f'Загружено или обновлено: {len(records)}')
            except (ValueError,DbError) as e:st.error(str(e))

st.caption('После изменения статуса нажмите «Обновить», чтобы увидеть изменения других сотрудников.')
if st.button('🔄 Обновить данные'):st.rerun()
try:
    products=fetch_all('products')
except DbError as e:
    st.error(f'Ошибка подключения к таблице products: {e}')
    st.stop()
if not products:
    st.info('Общая база пока пустая. Руководитель должен загрузить Excel через боковое меню.')
    st.stop()

df=pd.DataFrame(products).fillna('')
for field in ('aisle','module','shelf'):df[field]=pd.to_numeric(df[field],errors='coerce').fillna(0).astype(int)
alleys=sorted(df['aisle'].unique())
c1,c2=st.columns(2)
with c1:alley=st.selectbox('Аллея',alleys,format_func=lambda a:f'Аллея {a}')
mods=sorted(df.loc[df.aisle==alley,'module'].unique())
with c2:module=st.selectbox('Модуль',mods,format_func=lambda m:f'Модуль {m}')
part=df[(df.aisle==alley)&(df.module==module)].copy()
completed=int((part.status=='displayed').sum());total=len(part)
st.progress(completed/total if total else 0,text=f'Выставлено: {completed} из {total} позиций ({completed/total:.0%})' if total else 'Нет товаров')
if total and completed==total:st.success('✅ Модуль полностью завершён!')
mode=st.segmented_control('Показать',['Все','Не выставлено','Выставлено','Не найдено'],default='Не выставлено')
if mode=='Не выставлено':part=part[part.status!='displayed']
elif mode=='Выставлено':part=part[part.status=='displayed']
elif mode=='Не найдено':part=part[part.status=='not_found']
st.caption(f'Показано позиций: {len(part)}')

# Atomic update via conditional status match prevents silent overwrites by other employees.
def set_status(r,new_status,reason=None):
    old=r['status']
    params={'id':f'eq.{int(r["id"])}','status':f'eq.{old}','select':'id'}
    result=api('PATCH','products',params,{'status':new_status},'return=representation')
    if not result:
        st.warning('Статус уже изменён другим сотрудником. Обновите данные.')
        return
    # History is best-effort with current schema; no verified employee account is available.
    try:api('POST','status_history',payload={'product_id':int(r['id']),'old_status':old,'new_status':new_status,'reason':reason},prefer='return=minimal')
    except DbError:st.warning('Статус сохранён, но запись истории не удалась.')
    st.rerun()

for shelf,g in part.groupby('shelf',sort=True):
    st.subheader(f'Полка {shelf}')
    for _,r in g.iterrows():
        uid=str(r['id'])
        with st.container(border=True):
            left,right=st.columns([1,2.1],vertical_alignment='top')
            with left:
                if r['product_code']:
                    url=f'https://s3-pic.e-magnum.kz/item/{quote(str(r["product_code"]))}.jpg'
                    st.image(url,use_container_width=True)
                    st.link_button('Фото ↗',url,use_container_width=True)
            with right:
                st.markdown(f'**{r["product_name"]}**')
                st.caption(f'Код: {r["product_code"]} · ШК: {r["barcode"] or "—"}')
                st.caption({'displayed':'🟢 Выставлен','not_found':'🔴 Не найден','not_displayed':'🟡 Не выставлен'}.get(r['status'],'🟡 Не выставлен'))
            a,b,c=st.columns(3)
            a.metric('Аллея',r['aisle']);b.metric('Модуль',r['module']);c.metric('Полка',r['shelf'])
            st.write(f'**Остаток:** {r["available_stock"]} {r["unit"]}')
            st.caption(' / '.join(x for x in [r['product_group'],r['subgroup']] if x))
            x,y=st.columns(2)
            if x.button('✓ Выставлен',key=f'd_{uid}',use_container_width=True,type='primary'):
                try:set_status(r,'displayed')
                except DbError as e:st.error(str(e))
            if y.button('✕ Не найден',key=f'm_{uid}',use_container_width=True):
                st.session_state[f'pending_{uid}']=True
            if st.session_state.get(f'pending_{uid}'):
                reason=st.selectbox('Причина',['Нет на паллете','Не найден на складе','Другое'],key=f'reason_{uid}')
                if st.button('Сохранить причину',key=f'save_{uid}'):
                    try:set_status(r,'not_found',reason)
                    except DbError as e:st.error(str(e))
            if r['status']!='not_displayed' and st.button('↩ Сбросить статус',key=f'r_{uid}'):
                try:set_status(r,'not_displayed')
                except DbError as e:st.error(str(e))

if is_admin:
    with st.expander('📊 Общий отчёт по аллеям'):
        report=df.groupby('aisle',as_index=False).agg(
            **{'Всего позиций':('id','count'), 'Выставлено':('status',lambda s:(s=='displayed').sum()),
               'Не найдено':('status',lambda s:(s=='not_found').sum())})
        report=report.rename(columns={'aisle':'Аллея'})
        report['Прогресс, %']=(report['Выставлено']/report['Всего позиций']*100).round(1)
        st.dataframe(report,hide_index=True,use_container_width=True)
        st.download_button('Скачать CSV',report.to_csv(index=False).encode('utf-8-sig'),'mezonin_progress.csv','text/csv')
