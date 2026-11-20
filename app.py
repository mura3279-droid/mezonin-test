import io
import re
import hashlib
from urllib.parse import quote

import pandas as pd
import streamlit as st

st.set_page_config(page_title='Мезонин — выкладка', page_icon='📦', layout='centered', initial_sidebar_state='collapsed')
st.markdown('''<style>.block-container{padding-top:1rem;padding-bottom:3rem;max-width:780px}div.stButton>button,div.stLinkButton>a{min-height:46px;border-radius:12px}div[data-testid="stMetric"]{background:#f6f7f9;padding:10px;border-radius:12px}@media(max-width:600px){.block-container{padding-left:12px;padding-right:12px}}</style>''', unsafe_allow_html=True)

ALIASES = {
    'name':['наименование','название товара','наименование товара','товар'],
    'code':['код товара','кодтовара','sku','код'],
    'barcode':['штрихкод','штрих код','шк','barcode','ean'],
    'address':['адрес','адрес хранения','адрес товара'],
    'stock':['доступный остаток','остаток','количество','кол-во'],
    'unit':['единица измерения','ед. изм.','ед изм','единица','ед.изм'],
    'group':['группа товара','группа'],
    'subgroup':['подгруппа товара','подгруппа'],
}

def norm(v):
    return re.sub(r'\s+', ' ', str(v).strip().lower().replace('_',' '))

def find_col(columns, names):
    for n in names:
        for c in columns:
            if norm(c)==n: return c
    for n in names:
        for c in columns:
            if n in norm(c): return c
    return None

def clean(v):
    if pd.isna(v): return ''
    s=str(v).strip()
    return s[:-2] if re.fullmatch(r'\d+\.0',s) else s

def parts(address):
    p=clean(address).split('.')
    return (p[2],p[3],p[4]) if len(p)>=5 else ('','','')

def sortkey(v):
    s=str(v)
    return (0,int(s)) if s.isdigit() else (1,s)

def load_excel(file):
    raw=file.getvalue()
    fingerprint=hashlib.sha256(raw).hexdigest()
    if st.session_state.get('file_hash')==fingerprint: return
    table=pd.read_excel(io.BytesIO(raw), dtype=str).fillna('')
    cols={k:find_col(table.columns, opts) for k,opts in ALIASES.items()}
    if not cols['name'] or not cols['address']:
        raise ValueError('Нужны столбцы «Наименование» и «Адрес». Найдены: '+', '.join(map(str,table.columns)))
    for key,col in cols.items():
        table[key]=table[col].map(clean) if col else ''
    table[['alley','module','shelf']]=pd.DataFrame(table['address'].map(parts).tolist(),index=table.index)
    table=table[(table['alley']!='')&(table['module']!='')].copy()
    if table.empty: raise ValueError('Нет адресов вида 8031.1.8.5.2')
    table['item_key']=table[['address','code','barcode','name']].agg('|'.join,axis=1)
    table=table.drop_duplicates('item_key').reset_index(drop=True)
    st.session_state['catalog']=table
    st.session_state['file_hash']=fingerprint
    st.session_state['file_name']=file.name
    st.session_state['statuses']={}
    st.session_state['reasons']={}

def state(key): return st.session_state['statuses'].get(key,'none')

def set_state(key, value):
    st.session_state['statuses'][key]=value
    if value!='missing': st.session_state['reasons'].pop(key,None)

def render_item(r):
    key=r['item_key']
    with st.container(border=True):
        st.markdown('**'+str(r['name']).replace('*','')+'**')
        st.caption(f"Код: {r['code'] or '—'} · ШК: {r['barcode'] or '—'}")
        st.write({'done':'🟢 Выставлен','missing':'🔴 Не найден','none':'🟡 Не выставлен'}[state(key)])
        if r['code']:
            url='https://s3-pic.e-magnum.kz/item/'+quote(r['code'],safe='')+'.jpg'
            st.link_button('📷 Открыть фото ↗',url,use_container_width=True)
        a,b,c=st.columns(3)
        a.metric('Аллея',r['alley']); b.metric('Модуль',r['module']); c.metric('Полка',r['shelf'])
        st.caption('Адрес: '+r['address'])
        st.write(f"**Остаток:** {r['stock'] or '—'} {r['unit']}")
        if r['group'] or r['subgroup']:
            st.caption(' / '.join(x for x in (r['group'],r['subgroup']) if x))
        x,y=st.columns(2)
        if x.button('✓ Выставлен',key='done_'+key,use_container_width=True,type='primary'):
            set_state(key,'done');st.rerun()
        if y.button('✕ Не найден',key='missing_'+key,use_container_width=True):
            set_state(key,'missing');st.rerun()
        if state(key)=='missing':
            reasons=['Нет на паллете','Не найден на складе','Другое']
            previous=st.session_state['reasons'].get(key,reasons[0])
            chosen=st.selectbox('Причина',reasons,index=reasons.index(previous) if previous in reasons else 0,key='reason_widget_'+key)
            st.session_state['reasons'][key]=chosen
        if state(key)!='none' and st.button('↩ Сбросить статус',key='reset_'+key):
            st.session_state['statuses'].pop(key,None)
            st.session_state['reasons'].pop(key,None)
            st.rerun()

st.title('📦 Мезонин')
st.caption('Выкладка ассортимента · Excel')
mode=st.radio('Режим', ['👷 Сотрудник','👨‍💼 Руководитель'],horizontal=True)
if 'statuses' not in st.session_state: st.session_state['statuses']={}
if 'reasons' not in st.session_state: st.session_state['reasons']={}

if mode=='👨‍💼 Руководитель':
    password=st.secrets.get('ADMIN_PASSWORD','')
    if not password:
        st.error('Для кабинета руководителя настройте ADMIN_PASSWORD в Streamlit Secrets.')
        st.stop()
    if not st.session_state.get('admin_authenticated',False):
        with st.form('admin_login'):
            entered=st.text_input('Пароль руководителя',type='password')
            submit=st.form_submit_button('Войти',use_container_width=True)
        if submit:
            if entered==password:
                st.session_state['admin_authenticated']=True
                st.rerun()
            else: st.error('Неверный пароль')
        st.stop()
    if st.button('Выйти из кабинета'):
        st.session_state['admin_authenticated']=False
        st.rerun()

with st.expander('📄 Загрузить Excel',expanded='catalog' not in st.session_state):
    uploaded=st.file_uploader('Ассортимент Excel',type=['xlsx','xls'])
    if uploaded is not None:
        try:
            load_excel(uploaded)
            st.success('Excel загружен: '+st.session_state['file_name'])
        except Exception as exc: st.error(f'Ошибка Excel: {exc}')
    st.caption('Файл и статусы хранятся в текущей сессии. Другие телефоны не видят эти изменения.')

if 'catalog' not in st.session_state:
    st.info('Загрузите Excel с ассортиментом для начала работы.')
    st.stop()

df=st.session_state['catalog']
if mode=='👨‍💼 Руководитель':
    st.subheader('📊 Общий прогресс')
    total=len(df)
    done=sum(state(k)=='done' for k in df['item_key'])
    missing=sum(state(k)=='missing' for k in df['item_key'])
    a,b,c,d=st.columns(4)
    a.metric('Всего',total);b.metric('Выставлено',done);c.metric('Не найдено',missing);d.metric('Прогресс',f'{done/total:.1%}' if total else '0%')
    st.progress(done/total if total else 0)
    stats=[]
    for (alley,module),group in df.groupby(['alley','module']):
        keys=group['item_key'].tolist()
        finished=sum(state(k)=='done' for k in keys)
        absent=sum(state(k)=='missing' for k in keys)
        stats.append({'Аллея':alley,'Модуль':module,'Всего SKU':len(keys),'Выставлено':finished,'Не найдено':absent,'Осталось':len(keys)-finished-absent,'Выполнение %':round(100*finished/len(keys),1)})
    report=pd.DataFrame(stats).sort_values(['Аллея','Модуль'],key=lambda s:s.map(sortkey))
    alleys=report.groupby('Аллея',as_index=False)[['Всего SKU','Выставлено','Не найдено','Осталось']].sum()
    alleys['Выполнение %']=(100*alleys['Выставлено']/alleys['Всего SKU']).round(1)
    alleys=alleys.sort_values('Аллея',key=lambda s:s.map(sortkey))
    st.subheader('Прогресс по аллеям')
    st.dataframe(alleys,hide_index=True,use_container_width=True)
    st.subheader('Прогресс по модулям')
    st.dataframe(report,hide_index=True,use_container_width=True)
    st.subheader('🔴 Проблемные товары')
    problem=df[df['item_key'].map(lambda k:state(k)=='missing')].copy()
    problem['Причина']=problem['item_key'].map(lambda k:st.session_state['reasons'].get(k,''))
    problem=problem[['name','code','barcode','address','Причина']].rename(columns={'name':'Наименование','code':'Код','barcode':'ШК','address':'Адрес'})
    st.dataframe(problem,hide_index=True,use_container_width=True)
    output=io.BytesIO()
    with pd.ExcelWriter(output,engine='openpyxl') as writer:
        alleys.to_excel(writer,sheet_name='Аллеи',index=False)
        report.to_excel(writer,sheet_name='Модули',index=False)
        problem.to_excel(writer,sheet_name='Не найдено',index=False)
    st.download_button('⬇️ Скачать отчёт Excel',output.getvalue(),file_name='mezzanine_report.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
    st.info('Этот отчёт содержит только отметки из текущей сессии, не всех сотрудников.')
    st.stop()

st.subheader('🔎 Поиск по ШК')
search=st.text_input('Штрихкод',placeholder='Введите или вставьте ШК')
with st.expander('📷 Сканировать камерой'):
    shot=st.camera_input('Сфотографируйте штрихкод крупно и чётко')
    if shot is not None:
        photo_hash=hashlib.sha256(shot.getvalue()).hexdigest()
        if photo_hash!=st.session_state.get('last_scan_hash'):
            try:
                import zxingcpp
                from PIL import Image, ImageOps
                picture=ImageOps.exif_transpose(Image.open(io.BytesIO(shot.getvalue()))).convert('RGB')
                result=zxingcpp.read_barcode(picture)
                if result and result.text:
                    st.session_state['scanned_code']=result.text.strip()
                    st.session_state['last_scan_hash']=photo_hash
                else:
                    st.warning('Штрихкод не распознан. Попробуйте ближе или введите ШК вручную.')
            except Exception as exc:
                st.error(f'Ошибка распознавания: {exc}')
if st.session_state.get('scanned_code'):
    st.caption('Последний скан: '+st.session_state['scanned_code'])
    if st.button('Очистить скан'):
        st.session_state.pop('scanned_code',None)
        st.session_state.pop('last_scan_hash',None)
        st.rerun()
query=search.strip() or st.session_state.get('scanned_code','')
if query:
    found=df[df['barcode'].str.strip()==query]
    if found.empty: st.warning('Товар с таким ШК не найден')
    else:
        st.success(f'Найдено адресов: {len(found)}')
        for _,r in found.iterrows():render_item(r)
    st.stop()

alleys=sorted(df['alley'].unique(),key=sortkey)
a,b=st.columns(2)
with a: alley=st.selectbox('Аллея',alleys,format_func=lambda x:'Аллея '+x)
modules=sorted(df.loc[df['alley']==alley,'module'].unique(),key=sortkey)
with b: module=st.selectbox('Модуль',modules,format_func=lambda x:'Модуль '+x)
part=df[(df['alley']==alley)&(df['module']==module)].copy()
done=sum(state(k)=='done' for k in part['item_key'])
st.progress(done/len(part) if len(part) else 0,text=f'Выставлено: {done} из {len(part)}')
if len(part) and done==len(part): st.success('✅ Модуль завершён')
filter_mode=st.radio('Показать',['Не выставлено','Все','Выставлено','Не найдено'],horizontal=True)
if filter_mode=='Не выставлено': part=part[part['item_key'].map(lambda k:state(k)=='none')]
elif filter_mode=='Выставлено': part=part[part['item_key'].map(lambda k:state(k)=='done')]
elif filter_mode=='Не найдено': part=part[part['item_key'].map(lambda k:state(k)=='missing')]
st.caption(f'Показано: {len(part)}')
for shelf,group in sorted(part.groupby('shelf'),key=lambda pair:sortkey(pair[0])):
    st.subheader('Полка '+shelf)
    for _,r in group.iterrows():render_item(r)
