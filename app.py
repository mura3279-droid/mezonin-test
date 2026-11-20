
import streamlit as st
import pandas as pd
import re
import hashlib
from urllib.parse import quote

st.set_page_config(
    page_title="Мезонин — выкладка",
    page_icon="📦",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
.block-container {
    padding-top: 1rem;
    padding-bottom: 3rem;
    max-width: 760px;
}
h1 {font-size: 1.65rem!important;}
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 16px;
}
div.stButton>button {
    min-height: 48px;
    border-radius: 12px;
}
div[data-testid="stMetric"] {
    background: #f6f7f9;
    padding: 10px;
    border-radius: 12px;
}
@media(max-width:600px) {
    .block-container {
        padding-left: 12px;
        padding-right: 12px;
    }
    div[data-testid="stHorizontalBlock"] {
        gap: 7px;
    }
}
</style>
""", unsafe_allow_html=True)

st.title("📦 Мезонин")
st.caption("Выкладка ассортимента по аллеям и модулям")

with st.expander(
    "📄 Загрузить Excel",
    expanded="data" not in st.session_state
):
    upload = st.file_uploader(
        "Файл Excel с ассортиментом",
        type=["xlsx", "xls"]
    )
    st.caption(
        "Статусы сохраняются только в текущей сессии. "
        "Для общей работы сотрудников нужна база данных."
    )

aliases = {
    "name": [
        "наименование", "название товара",
        "товар", "наименование товара"
    ],
    "code": ["код товара", "кодтовара", "код", "sku"],
    "barcode": [
        "штрихкод", "штрих код", "шк", "barcode", "ean"
    ],
    "address": ["адрес", "адрес хранения", "адрес товара"],
    "stock": [
        "доступный остаток", "остаток",
        "количество", "кол-во"
    ],
    "unit": [
        "единица измерения", "ед. изм.",
        "ед изм", "единица", "ед.изм"
    ],
    "group": ["группа товара", "группа"],
    "subgroup": ["подгруппа товара", "подгруппа"]
}

def norm(s):
    return re.sub(
        r"\s+", " ",
        str(s).strip().lower().replace("_", " ")
    )

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

def clean(value):
    if pd.isna(value):
        return ""
    s = str(value).strip()
    return s[:-2] if re.fullmatch(r"\d+\.0", s) else s

def addr_parts(address):
    p = clean(address).split(".")
    return (p[2], p[3], p[4]) if len(p) >= 5 else ("", "", "")

def sortkey(s):
    return (0, int(s)) if str(s).isdigit() else (1, str(s))

def item_key(row):
    return "|".join([
        row["address"], row["code"],
        row["barcode"], row["name"]
    ])

if upload is not None:
    try:
        file_bytes = upload.getvalue()
        file_hash = hashlib.sha256(file_bytes).hexdigest()

        if st.session_state.get("file_hash") != file_hash:
            st.session_state["data"] = pd.read_excel(
                upload, dtype=str
            )
            st.session_state["file_name"] = upload.name
            st.session_state["file_hash"] = file_hash
            st.session_state["statuses"] = {}

    except Exception as e:
        st.error(f"Не удалось прочитать Excel: {e}")

if "data" not in st.session_state:
    st.info("Загрузите Excel, чтобы начать работу.")
    st.stop()

df = st.session_state["data"].copy().fillna("")
cols = {
    k: find_col(df.columns, v)
    for k, v in aliases.items()
}

if not cols["address"] or not cols["name"]:
    st.error(
        "Не найдены столбцы «Адрес» и «Наименование»."
    )
    st.write("Столбцы Excel:", ", ".join(map(str, df.columns)))
    st.stop()

for key, col in cols.items():
    df[key] = df[col].map(clean) if col else ""

df[["alley", "module", "shelf"]] = pd.DataFrame(
    df["address"].map(addr_parts).tolist(),
    index=df.index
)

df = df[
    (df["alley"] != "") &
    (df["module"] != "")
].copy()

if df.empty:
    st.warning("Нет адресов формата 8031.1.8.5.2")
    st.stop()

df["item_key"] = df.apply(item_key, axis=1)
df = df.drop_duplicates("item_key")

if "statuses" not in st.session_state:
    st.session_state["statuses"] = {}

statuses = st.session_state["statuses"]

# ==========================================
# ПОИСК И СКАНИРОВАНИЕ
# ==========================================

st.subheader("🔎 Поиск товара")

search = st.text_input(
    "Поиск по штрихкоду",
    placeholder="Введите или вставьте ШК",
    key="barcode_search"
)

try:
    from streamlit_barcode_scanner import st_barcode_scanner
    scanner_available = True
except ImportError:
    scanner_available = False

if scanner_available:
    with st.expander("📷 Сканировать ШК"):
        st.caption(
            "Разрешите браузеру доступ к камере. "
            "Наведите её на штрихкод товара."
        )
        scanned = st_barcode_scanner(
            key="barcode_camera"
        )

        if scanned:
            if isinstance(scanned, dict):
                scanned_code = str(
                    scanned.get("barcode")
                    or scanned.get("text")
                    or scanned.get("value")
                    or ""
                ).strip()
            else:
                scanned_code = str(scanned).strip()

            if scanned_code:
                st.session_state["scanned_barcode"] = scanned_code
                st.success(f"Считан ШК: {scanned_code}")
else:
    st.warning(
        "Сканер не установлен. "
        "Добавьте streamlit-barcode-scanner "
        "в requirements.txt."
    )

if st.session_state.get("scanned_barcode"):
    if st.button("Очистить результат сканирования"):
        st.session_state.pop("scanned_barcode", None)
        st.rerun()

query = search.strip() or st.session_state.get(
    "scanned_barcode", ""
)

def render_item(r):
    key = r["item_key"]
    state = statuses.get(key, "none")

    with st.container(border=True):
        st.markdown(f"**{r['name']}**")
        st.caption(
            f"Код: {r['code'] or '—'}  ·  "
            f"ШК: {r['barcode'] or '—'}"
        )

        st.caption({
            "done": "🟢 Выставлен",
            "missing": "🔴 Не найден",
            "none": "🟡 Не выставлен"
        }[state])

        # Только ссылка на фото, без st.image
        if r["code"]:
            photo_url = (
                "https://s3-pic.e-magnum.kz/item/"
                + quote(r["code"], safe="")
                + ".jpg"
            )
            st.link_button(
                "📷 Открыть фото ↗",
                photo_url,
                use_container_width=True
            )

        a, b, c = st.columns(3)
        a.metric("Аллея", r["alley"])
        b.metric("Модуль", r["module"])
        c.metric("Полка", r["shelf"])

        st.caption(f"Адрес: {r['address']}")

        st.write(
            f"**Остаток:** {r['stock'] or '—'} "
            f"{r['unit']}"
        )

        if r["group"] or r["subgroup"]:
            st.caption(
                " / ".join(
                    x for x in [
                        r["group"], r["subgroup"]
                    ] if x
                )
            )

        x, y = st.columns(2)

        if x.button(
            "✓ Выставлен",
            key=f"d_{key}",
            use_container_width=True,
            type="primary"
        ):
            statuses[key] = "done"
            st.rerun()

        if y.button(
            "✕ Не найден",
            key=f"m_{key}",
            use_container_width=True
        ):
            statuses[key] = "missing"
            st.rerun()

        if statuses.get(key) in ("done", "missing"):
            if st.button(
                "↩ Сбросить статус",
                key=f"r_{key}"
            ):
                statuses.pop(key, None)
                st.session_state.pop(f"reason_{key}", None)
                st.rerun()

        if statuses.get(key) == "missing":
            st.selectbox(
                "Причина",
                [
                    "Нет на паллете",
                    "Не найден на складе",
                    "Другое"
                ],
                key=f"reason_{key}"
            )

if query:
    matches = df[
        df["barcode"].str.strip() == query
    ].copy()

    st.divider()

    if matches.empty:
        st.warning(f"ШК {query} не найден в Excel.")
    else:
        st.success(
            f"Найдено адресов: {len(matches)}"
        )

        for _, row in matches.iterrows():
            render_item(row)

    st.stop()

# ==========================================
# АЛЛЕИ И МОДУЛИ
# ==========================================

st.divider()
st.subheader("📍 Выбор аллеи и модуля")

alleys = sorted(df["alley"].unique(), key=sortkey)

c1, c2 = st.columns(2)

with c1:
    alley = st.selectbox(
        "Аллея",
        alleys,
        format_func=lambda x: f"Аллея {x}"
    )

mods = sorted(
    df.loc[df["alley"] == alley, "module"].unique(),
    key=sortkey
)

with c2:
    module = st.selectbox(
        "Модуль",
        mods,
        format_func=lambda x: f"Модуль {x}"
    )

part = df[
    (df["alley"] == alley) &
    (df["module"] == module)
].copy()

completed = sum(
    statuses.get(k) == "done"
    for k in part["item_key"]
)

total = len(part)

st.progress(
    completed / total if total else 0,
    text=(
        f"Выставлено: {completed} из {total} "
        f"SKU ({completed / total:.0%})"
        if total else "Нет товаров"
    )
)

if total and completed == total:
    st.success("✅ Модуль полностью завершён!")

filter_mode = st.segmented_control(
    "Показать",
    [
        "Все",
        "Не выставлено",
        "Выставлено",
        "Не найдено"
    ],
    default="Не выставлено"
)

show = part.copy()

if filter_mode == "Не выставлено":
    show = show[
        show["item_key"].map(
            lambda k: statuses.get(k) not in (
                "done", "missing"
            )
        )
    ]

elif filter_mode == "Выставлено":
    show = show[
        show["item_key"].map(
            lambda k: statuses.get(k) == "done"
        )
    ]

elif filter_mode == "Не найдено":
    show = show[
        show["item_key"].map(
            lambda k: statuses.get(k) == "missing"
        )
    ]

st.caption(f"Показано позиций: {len(show)}")

for shelf, shelf_df in show.groupby(
    "shelf", sort=False
):
    st.subheader(f"Полка {shelf}")

    for _, row in shelf_df.iterrows():
        render_item(row)

# ==========================================
# ОТЧЁТ
# ==========================================

with st.expander("📊 Прогресс по аллеям"):
    stats = []

    for a, group in df.groupby("alley"):
        keys = group["item_key"].unique()

        stats.append({
            "Аллея": a,
            "Всего SKU": len(keys),
            "Выставлено": sum(
                statuses.get(k) == "done"
                for k in keys
            ),
            "Не найдено": sum(
                statuses.get(k) == "missing"
                for k in keys
            )
        })

    report = pd.DataFrame(stats)
    report = report.sort_values(
        "Аллея", key=lambda s: s.map(sortkey)
    )

    st.dataframe(
        report,
        hide_index=True,
        use_container_width=True
    )

    st.download_button(
        "Скачать отчёт CSV",
        report.to_csv(index=False).encode("utf-8-sig"),
        "progress.csv",
        "text/csv"
    )
