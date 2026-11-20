    if st.button('Выйти из кабинета'):
        st.session_state['admin_authenticated']=False
        st.rerun()

with st.expander('📄 Загрузить Excel',expanded=not db and 'data' not in st.session_state):
    upload=st.file_uploader('Ассортимент Excel',type=['xlsx','xls'])
    if upload is not None:
        if db and mode!='👨‍💼 Руководитель':
            st.warning('Загружать общий ассортимент может только руководитель.')
        else:
            try:
                load_catalog(upload,db)
                st.success('Ассортимент загружен')
            except Exception as e:st.error(f'Ошибка Excel или базы: {e}')

try:
    df=get_catalog(db)
    statuses=get_statuses(db)
except Exception as e:
    st.error(f'Не удалось получить данные: {e}')
    st.stop()
if df.empty:
    st.info('Ассортимент ещё не загружен. Руководитель должен загрузить Excel.')
    st.stop()
for col in list(ALIASES)+['alley','module','shelf','item_key']:
    if col not in df:df[col]=''
    df[col]=df[col].fillna('').astype(str)

if mode=='👨‍💼 Руководитель':
    st.subheader('📊 Общий прогресс')
    total=len(df)
    done=sum(status_of(statuses,k)=='done' for k in df.item_key)
    missing=sum(status_of(statuses,k)=='missing' for k in df.item_key)
    a,b,c,d=st.columns(4)
    a.metric('Всего SKU',total);b.metric('Выставлено',done)
    c.metric('Не найдено',missing);d.metric('Прогресс',f'{done/total:.1%}' if total else '0%')
    st.progress(done/total if total else 0)
    stats=[]
    for (alley,module),group in df.groupby(['alley','module']):
        keys=group.item_key.tolist()
        finished=sum(status_of(statuses,k)=='done' for k in keys)
        absent=sum(status_of(statuses,k)=='missing' for k in keys)
        stats.append({'Аллея':alley,'Модуль':module,'Всего SKU':len(keys),'Выставлено':finished,'Не найдено':absent,'Осталось':len(keys)-finished-absent,'Выполнение %':round(finished/len(keys)*100,1)})
    report=pd.DataFrame(stats)
    report=report.sort_values(['Аллея','Модуль'],key=lambda s:s.map(sortkey))
    st.subheader('Прогресс по аллеям')
    alleys=report.groupby('Аллея',as_index=False)[['Всего SKU','Выставлено','Не найдено','Осталось']].sum()
    alleys['Выполнение %']=(alleys['Выставлено']/alleys['Всего SKU']*100).round(1)
    st.dataframe(alleys,hide_index=True,use_container_width=True)
    st.subheader('Прогресс по модулям')
    st.dataframe(report,hide_index=True,use_container_width=True)
    st.subheader('🔴 Проблемные товары')
    problem=df[df.item_key.map(lambda k:status_of(statuses,k)=='missing')].copy()
    if len(problem):
        problem['Причина']=problem.item_key.map(lambda k:statuses.get(k,{}).get('reason','') if isinstance(statuses.get(k),dict) else '')
        st.dataframe(problem[['name','code','barcode','address','Причина']].rename(columns={'name':'Наименование','code':'Код','barcode':'ШК','address':'Адрес'}),hide_index=True,use_container_width=True)
    else:st.success('Проблемных товаров пока нет')
    output=io.BytesIO()
    with pd.ExcelWriter(output,engine='openpyxl') as writer:
        alleys.to_excel(writer,sheet_name='Аллеи',index=False)
        report.to_excel(writer,sheet_name='Модули',index=False)
        problem.to_excel(writer,sheet_name='Не найдено',index=False)
    st.download_button('⬇️ Скачать отчёт Excel',output.getvalue(),file_name='mezzanine_report.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
    if st.button('🔄 Обновить данные',use_container_width=True):st.rerun()
    st.stop()

st.subheader('🔎 Поиск по ШК')
search=st.text_input('Штрихкод',placeholder='Введите или вставьте ШК')
with st.expander('📷 Сканировать камерой'):
    try:
        from streamlit_barcode_scanner import st_barcode_scanner
        result=st_barcode_scanner(key='scanner')
        if result:
            if isinstance(result,dict):
                code=str(result.get('barcode') or result.get('text') or result.get('value') or '').strip()
            else:code=str(result).strip()
            if code:st.session_state['scanned_code']=code
    except ImportError:
        st.warning('Компонент сканера не установлен. Можно ввести ШК вручную.')
if st.session_state.get('scanned_code'):
    st.caption('Последний скан: '+st.session_state['scanned_code'])
    if st.button('Очистить скан'):
        st.session_state.pop('scanned_code',None)
        st.rerun()
query=search.strip() or st.session_state.get('scanned_code','')
if query:
    found=df[df.barcode==query]
    if found.empty:st.warning('Товар с таким ШК не найден')
    else:
        st.success(f'Найдено адресов: {len(found)}')
        for _,r in found.iterrows():render_item(r,db,statuses)
    st.stop()

alleys=sorted(df.alley.unique(),key=sortkey)
a,b=st.columns(2)
with a:alley=st.selectbox('Аллея',alleys,format_func=lambda x:'Аллея '+x)
modules=sorted(df[df.alley==alley].module.unique(),key=sortkey)
with b:module=st.selectbox('Модуль',modules,format_func=lambda x:'Модуль '+x)
part=df[(df.alley==alley)&(df.module==module)]
done=sum(status_of(statuses,k)=='done' for k in part.item_key)
st.progress(done/len(part) if len(part) else 0,text=f'Выставлено: {done} из {len(part)}')
if len(part) and done==len(part):st.success('✅ Модуль завершён')
filter_mode=st.radio('Показать',['Не выставлено','Все','Выставлено','Не найдено'],horizontal=True)
if filter_mode=='Не выставлено':part=part[part.item_key.map(lambda k:status_of(statuses,k)=='none')]
elif filter_mode=='Выставлено':part=part[part.item_key.map(lambda k:status_of(statuses,k)=='done')]
elif filter_mode=='Не найдено':part=part[part.item_key.map(lambda k:status_of(statuses,k)=='missing')]
st.caption(f'Показано: {len(part)}')
for shelf,group in sorted(part.groupby('shelf'),key=lambda x:sortkey(x[0])):
    st.subheader('Полка '+shelf)
    for _,r in group.iterrows():render_item(r,db,statuses)
