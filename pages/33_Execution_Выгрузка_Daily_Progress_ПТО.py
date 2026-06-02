import re
import streamlit as st
import pandas as pd

from services.supabase_client import supabase

st.set_page_config(layout="wide")

st.title("Выгрузка Daily Progress для ПТО")
st.caption(
    "Страница предназначена для быстрой выгрузки Daily Progress в контур ПТО для проверки объёмов, "
    "КС-6а и исполнительной документации."
)

EXPORT_COLUMNS = [
    "Work_Date",
    "Month_Key",
    "Facility_Building",
    "Construction_Discipline",
    "Foreman",
    "Crew_ID",
    "boq_name_clean",
    "IWP_ID_clean",
    "system_label_clean",
    "Unit_of_Measure",
    "Quantity_Today",
    "Unit_Rate",
    "EV_DAY_VALUE",
    "validation_status_clean",
]

EXPORT_FIELD_MAP = {
    "Work_Date": ["work_date", "Work_Date", "date", "work_day"],
    "Month_Key": ["month_key", "Month_Key", "month"],
    "Facility_Building": ["facility_building", "Facility_Building", "title", "Title"],
    "Construction_Discipline": ["construction_discipline", "Construction_Discipline", "discipline", "Discipline"],
    "Foreman": ["foreman", "Foreman"],
    "Crew_ID": ["crew_id", "Crew_ID", "crew"],
    "boq_name_clean": ["boq_name_clean", "boq_name", "BOQ_Name", "boq_code_name"],
    "IWP_ID_clean": ["iwp_id_clean", "iwp_id", "IWP_ID", "IWP_ID_clean"],
    "system_label_clean": ["system_label_clean", "system_label", "System_Label"],
    "Unit_of_Measure": ["unit_of_measure", "Unit_of_Measure", "unit", "uom"],
    "Quantity_Today": ["quantity_today", "Quantity_Today", "qty_today"],
    "Unit_Rate": ["unit_rate", "Unit_Rate"],
    "EV_DAY_VALUE": ["ev_day_value", "EV_DAY_VALUE", "ev_value"],
    "validation_status_clean": ["validation_status_clean", "validation_status", "Validation_Status"],
}


@st.cache_data(ttl=300)
def load_daily_progress_active(limit: int = 5000) -> pd.DataFrame:
    resp = supabase.table("daily_progress_active").select("*").limit(limit).execute()
    return pd.DataFrame(resp.data or [])


def option_values(df: pd.DataFrame, column: str) -> list[str]:
    if df.empty or column not in df.columns:
        return ["Все"]
    vals = df[column].dropna().astype(str).str.strip()
    vals = vals[vals != ""].unique().tolist()
    return ["Все"] + sorted(vals)


def apply_filter(df: pd.DataFrame, column: str, value: str) -> pd.DataFrame:
    if value == "Все" or column not in df.columns:
        return df
    return df[df[column].astype(str).str.strip() == value]


def safe_num(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series(dtype="float64")
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def money(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def qty(value: float) -> str:
    return f"{value:,.3f}".replace(",", " ").replace(".", ",")


def to_excel_date(value) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%d.%m.%Y")


def sanitize_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-zА-Яа-я_\-]+", "_", str(value or "").strip())
    cleaned = cleaned.strip("_")
    return cleaned or "all"


def resolve_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for cand in candidates:
        if cand in df.columns:
            return cand
    return None


def non_empty_count(df: pd.DataFrame, column: str | None) -> int:
    if not column or column not in df.columns:
        return 0
    vals = df[column].dropna().astype(str).str.strip()
    return int((vals != "").sum())

def build_export_df(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
    mapped: dict[str, str] = {}
    missing: list[str] = []
    export_df = pd.DataFrame(index=df.index)
    for target_col in EXPORT_COLUMNS:
        source_col = resolve_column(df, EXPORT_FIELD_MAP.get(target_col, [target_col]))
        if source_col:
            mapped[target_col] = source_col
            export_df[target_col] = df[source_col]
        else:
            missing.append(target_col)
    if "Work_Date" in export_df.columns:
        export_df["Work_Date"] = export_df["Work_Date"].apply(to_excel_date)
    return export_df, mapped, missing


df_raw = load_daily_progress_active()

project_col = resolve_column(df_raw, ["project_code"])
month_col = resolve_column(df_raw, ["Month_Key", "month_key", "Month", "month"])
facility_col = resolve_column(df_raw, ["Facility_Building", "facility_building", "title", "Title"])
discipline_col = resolve_column(
    df_raw,
    ["Construction_Discipline", "construction_discipline", "discipline", "Discipline"],
)

with st.expander("Диагностика загрузки данных", expanded=False):
    st.write("source table/view = daily_progress_active")
    st.write(f"Количество строк первого запроса: {len(df_raw)}")
    st.write("Колонки, пришедшие из Supabase:")
    st.write(list(df_raw.columns))
    st.write("Первые 3 строки raw preview:")
    st.dataframe(df_raw.head(3), use_container_width=True, hide_index=True)
    st.write("Ожидаемые колонки (найдено/не найдено):")
    st.write(f"- project_code: {'найдено' if project_col else 'не найдено'}")
    st.write(f"- Month_Key: {'найдено' if month_col else 'не найдено'}")
    st.write(f"- Facility_Building: {'найдено' if facility_col else 'не найдено'}")
    st.write(f"- Construction_Discipline: {'найдено' if discipline_col else 'не найдено'}")

if df_raw.empty:
    st.error("daily_progress_active вернула 0 строк. Проверьте Supabase/RLS/источник.")
    st.stop()

f1, f2, f3, f4 = st.columns(4)
with f1:
    if project_col:
        project = st.selectbox("Проект", option_values(df_raw, project_col))
    else:
        project = "Все"
        st.warning("Колонка project_code не найдена в daily_progress_active")

df_project = apply_filter(df_raw, project_col or "", project)

with f2:
    if month_col:
        month = st.selectbox("Месяц", option_values(df_project, month_col))
    else:
        month = "Все"
        st.warning("Колонка Month_Key не найдена в daily_progress_active")

df_month = apply_filter(df_project, month_col or "", month)

with f3:
    if facility_col:
        facility = st.selectbox("Титул / объект", option_values(df_month, facility_col))
    else:
        facility = "Все"
        st.warning("Колонка Facility_Building не найдена в daily_progress_active")

df_facility = apply_filter(df_month, facility_col or "", facility)

with f4:
    if discipline_col:
        discipline = st.selectbox(
            "Дисциплина",
            option_values(df_facility, discipline_col),
        )
    else:
        discipline = "Все"
        st.warning("Колонка Construction_Discipline не найдена в daily_progress_active")

df_filtered = apply_filter(df_facility, discipline_col or "", discipline).copy()

if len(df_raw) > 0:
    empty_filters: list[str] = []
    for label, col in [
        ("project_code", project_col),
        ("Month_Key", month_col),
        ("Facility_Building", facility_col),
        ("Construction_Discipline", discipline_col),
    ]:
        if col and option_values(df_raw, col) == ["Все"]:
            empty_filters.append(f"{label} (непустых значений: {non_empty_count(df_raw, col)})")
    if empty_filters:
        st.warning(
            "Данные есть, но значения для фильтров пустые/NaN: " + "; ".join(empty_filters)
        )

df_export, found_export_map, missing_export_columns = build_export_df(df_filtered)
for col in missing_export_columns:
    st.warning(f"Колонка {col} не найдена в daily_progress_active и исключена из выгрузки.")
st.caption("Экспортные поля найдены:")
for target_col in EXPORT_COLUMNS:
    source_col = found_export_map.get(target_col)
    if source_col:
        st.caption(f"{target_col} → {source_col}")
    else:
        st.caption(f"{target_col} → не найдено")

rows_count = len(df_export)
foreman_count = (
    df_export["Foreman"].astype(str).str.strip().replace("", pd.NA).dropna().nunique()
    if "Foreman" in df_export.columns
    else 0
)
crew_count = (
    df_export["Crew_ID"].astype(str).str.strip().replace("", pd.NA).dropna().nunique()
    if "Crew_ID" in df_export.columns
    else 0
)
qty_total = safe_num(df_export["Quantity_Today"] if "Quantity_Today" in df_export.columns else None).sum()
ev_total = safe_num(df_export["EV_DAY_VALUE"] if "EV_DAY_VALUE" in df_export.columns else None).sum()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Количество строк", rows_count)
k2.metric("Количество мастеров", int(foreman_count))
k3.metric("Количество звеньев", int(crew_count))
k4.metric("Общий объём Quantity_Today", qty(float(qty_total)))
k5.metric("Общая стоимость EV_DAY_VALUE", money(float(ev_total)))

if df_export.empty:
    st.info("По выбранным фильтрам данные не найдены.")
    st.stop()

st.dataframe(
    df_export,
    use_container_width=True,
    hide_index=True,
    height=560,
    column_order=[col for col in EXPORT_COLUMNS if col in df_export.columns],
)

file_project = sanitize_filename_part(project if project != "Все" else "all")
file_month = sanitize_filename_part(month if month != "Все" else "all")
filename = f"daily_progress_pto_{file_project}_{file_month}.csv"

csv_text = df_export.to_csv(index=False, sep=";")
csv_bytes = csv_text.encode("utf-8-sig")

st.download_button(
    "Скачать CSV для Excel",
    data=csv_bytes,
    file_name=filename,
    mime="text/csv",
    use_container_width=False,
)

st.markdown("### Как правильно открыть файл")
st.markdown(
    """
1. Не открывайте CSV двойным кликом.
2. Откройте Excel.
3. Данные → Из текста/CSV.
4. Кодировка UTF-8.
5. Разделитель ; (точка с запятой).
6. Для кодов и обозначений использовать тип "Текст".
"""
)
