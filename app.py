import streamlit as st
import pandas as pd
import re
from urllib.parse import quote

st.set_page_config(page_title='Мезонин — выкладка', page_icon='📦', layout='centered', initial_sidebar_state='collapsed')
st.markdown('''<style>
.block-container{padding-top:1rem;padding-bottom:3rem;max-width:760px}h1{font-size:1.65rem!important}div[data-testid="stVerticalBlockBorderWrapper"]{border-radius:16px}div.stButton>button{min-height:48px;border-radius:12px}div[data-testid="stMetric"]{background:#f6f7f9;padding:10px;border-radius:12px}@media(max-width:600px){.block-container{padding-left:12px;padding-right:12px}div[data-testid="stHorizontalBlock"]{gap:7px}}
</style>''', unsafe_allow_html=True)

st.title('📦 Мезонин')
st.caption('Выкладка ассортимента по аллеям и модулям')
with st.expander('📄 Загрузить Excel', expanded='data' not in st.session_state):
    upload=st.file_uploader('Файл Excel с ассортиментом',type=['xlsx','xls'])
    st.caption('Статусы в этой версии сохраняются только в текущей сессии. Для общей работы сотрудников потребуется база данных.')

aliases={
 'name':['наименование','название товара','товар','наименование товара'],
 'code':['код товара','кодтовара','код','sku'],
 'barcode':['штрихкод','штрих код','шк','barcode','ean'],
 'address':['адрес','адрес хранения','адрес товара'],
 'stock':['доступный остаток','остаток','количество','кол-во'],
 'unit':['единица измерения','ед. изм.','ед изм','единица','ед.изм'],
 'group':['группа товара','группа'],
 'subgroup':['подгруппа товара','подгруппа']}
def norm(s):return re.sub(r'\s+',' ',str(s).strip().lower().replace('_',' '))
def find_col(cols, opts):
    for o in opts:
        for c in cols:
            if norm(c)==o:return c
    for o in opts:
        for c in cols:
            if o in norm(c):return c
    return None
def clean(v):
    if pd.isna(v):return ''
    s=str(v).strip()
    return s[:-2] if re.fullmatch(r'\d+\.0',s) else s
def addr_parts(a):
    a=clean(a)
    p=a.split('.')
    return (p[2],p[3],p[4]) if len(p)>=5 else ('','','')

if upload is not None:
    try:
        data=pd.read_excel(upload,dtype=str)
        st.session_state['data']=data
        st.session_state['file_name']=upload.name
    except Exception as e:st.error(f'Не удалось прочитать Excel: {e}')

if 'data' not in st.session_state:
    st.info('Загрузите Excel, чтобы выбрать аллею и модуль и начать выкладку.')
    st.stop()

df=st.session_state['data'].copy().fillna('')
cols={k:find_col(df.columns,v) for k,v in aliases.items()}
if not cols['address'] or not cols['name']:
    st.error('Не найдены обязательные столбцы «Адрес» и «Наименование». Проверьте заголовки Excel.')
    st.write('Найденные столбцы:',', '.join(map(str,df.columns)))
    st.stop()
for key,col in cols.items():df[key]=df[col].map(clean) if col else ''
df[['alley','module','shelf']]=pd.DataFrame(df['address'].map(addr_parts).tolist(),index=df.index)
df=df[(df.alley!='')&(df.module!='')].copy()
if df.empty:st.warning('Нет адресов формата 8031.1.8.5.2');st.stop()

def sortkey(s):return (0,int(s)) if str(s).isdigit() else (1,str(s))
alleys=sorted(df.alley.unique(),key=sortkey)
c1,c2=st.columns(2)
with c1:alley=st.selectbox('Аллея',alleys,format_func=lambda x:f'Аллея {x}')
mods=sorted(df.loc[df.alley==alley,'module'].unique(),key=sortkey)
with c2:module=st.selectbox('Модуль',mods,format_func=lambda x:f'Модуль {x}')
part=df[(df.alley==alley)&(df.module==module)].copy()
# Each address+barcode+code is a distinct placement, including products with two addresses.
part['item_key']=part.apply(lambda r:'|'.join([r['address'],r['code'],r['barcode'],r['name']]),axis=1)
part=part.drop_duplicates('item_key')
if 'statuses' not in st.session_state:st.session_state.statuses={}
statuses=st.session_state.statuses
completed=sum(statuses.get(k)=='done' for k in part.item_key)
total=len(part)
st.progress(completed/total if total else 0,text=f'Выставлено: {completed} из {total} SKU ({completed/total:.0%})' if total else 'Нет товаров')
if total and completed==total:st.success('✅ Модуль полностью завершён!')
filter_mode=st.segmented_control('Показать', ['Все','Не выставлено','Выставлено','Не найдено'],default='Не выставлено')
show=part.copy()
if filter_mode=='Не выставлено':show=show[show.item_key.map(lambda k:statuses.get(k)!='done')]
elif filter_mode=='Выставлено':show=show[show.item_key.map(lambda k:statuses.get(k)=='done')]
elif filter_mode=='Не найдено':show=show[show.item_key.map(lambda k:statuses.get(k)=='missing')]
st.caption(f'Показано позиций: {len(show)}')
for shelf,shelf_df in show.groupby('shelf',sort=False):
    st.subheader(f'Полка {shelf}')
    for _,r in shelf_df.iterrows():
        key=r.item_key
        with st.container(border=True):
            piccol,infocol=st.columns([1,2.1],vertical_alignment='top')
            with piccol:
                if r['code']:
                    url=f"https://s3-pic.e-magnum.kz/item/{quote(r['code'])}.jpg"
                    st.image(url,use_container_width=True)
                    st.link_button('Фото ↗',url,use_container_width=True)
                else:st.caption('Нет кода для фото')
            with infocol:
                st.markdown(f"**{r['name']}**")
                st.caption(f"Код: {r['code'] or '—'}  ·  ШК: {r['barcode'] or '—'}")
                state=statuses.get(key,'none')
                st.caption({'done':'🟢 Выставлен','missing':'🔴 Не найден','none':'🟡 Не выставлен'}[state])
            a,b,c=st.columns(3)
            a.metric('Аллея',r['alley']);b.metric('Модуль',r['module']);c.metric('Полка',r['shelf'])
            st.write(f"**Остаток:** {r['stock'] or '—'} {r['unit']}")
            if r['group'] or r['subgroup']:st.caption(' / '.join(x for x in [r['group'],r['subgroup']] if x))
            x,y=st.columns(2)
            if x.button('✓ Выставлен',key=f'd_{key}',use_container_width=True,type='primary'):
                statuses[key]='done';st.rerun()
            if y.button('✕ Не найден',key=f'm_{key}',use_container_width=True):
                statuses[key]='missing';st.rerun()
            if statuses.get(key) in ('done','missing'):
                if st.button('↩ Сбросить статус',key=f'r_{key}'):
                    statuses.pop(key,None);st.rerun()
            if statuses.get(key)=='missing':
                reasons=['Нет на паллете','Не найден на складе','Другое']
                st.selectbox('Причина',reasons,key=f'reason_{key}')

with st.expander('📊 Прогресс по аллеям (на этом устройстве)'):
    stats=[]
    for a,g in df.groupby('alley'):
        keys=g.apply(lambda r:'|'.join([r['address'],r['code'],r['barcode'],r['name']]),axis=1).unique()
        stats.append({'Аллея':a,'Всего SKU':len(keys),'Выставлено':sum(statuses.get(k)=='done' for k in keys),'Не найдено':sum(statuses.get(k)=='missing' for k in keys)})
    st.dataframe(pd.DataFrame(stats).sort_values('Аллея'),hide_index=True,use_container_width=True)
    st.download_button('Скачать отчёт CSV',pd.DataFrame(stats).to_csv(index=False).encode('utf-8-sig'),'progress.csv','text/csv')
