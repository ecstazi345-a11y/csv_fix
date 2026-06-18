"""
Независимая форма ввода смены (MVP).
Изолирована от dashboard (папка form_app/, без pages/*).

Запуск из корня проекта:
    streamlit run form_app/daily_progress_form_app.py --server.port 8502
"""

from __future__ import annotations

import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

_FORM_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _FORM_DIR.parent
for p in (_FORM_DIR, _PROJECT_ROOT):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from form_supabase import get_form_supabase

supabase = get_form_supabase()

SUBMISSIONS_TABLE = "daily_progress_form_submissions"
DEFAULT_PROJECTS = ["PRJ_001_БХК"]

SHIFT_OPTIONS = ["Дневная", "Ночная", "Выходной"]

OPERATION_TYPES = [
    "Разметка",
    "Подготовка",
    "Монтаж",
    "Fit-up",
    "Сварка",
    "Контроль",
    "Исполнительная фиксация",
    "Другое",
]

MOBILE_CSS = """
<style>
    .block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 720px; }
    div[data-testid="stButton"] > button {
        width: 100%; min-height: 3rem; font-size: 1.1rem; font-weight: 600;
    }
    .stSelectbox label, .stTextInput label, .stNumberInput label,
    .stDateInput label, .stTextArea label { font-size: 1rem; }
    h1 { font-size: 1.6rem !important; }
    h2, h3 { font-size: 1.15rem !important; }
    [data-testid="stSidebar"] { display: none; }
    [data-testid="collapsedControl"] { display: none; }
</style>
"""


@st.cache_data(ttl=300, show_spinner=False)
def load_table(name: str, columns: str = "*", limit: int = 5000) -> pd.DataFrame:
    try:
        response = supabase.table(name).select(columns).limit(limit).execute()
        return pd.DataFrame(response.data or [])
    except Exception:
        return pd.DataFrame()


def distinct_values(df: pd.DataFrame, col: str) -> list[str]:
    if df.empty or col not in df.columns:
        return []
    vals = df[col].dropna().astype(str).str.strip()
    vals = vals[vals != ""].unique().tolist()
    return sorted(vals)


def project_options() -> list[str]:
    passport = load_table("monthly_passport_plan", "project_code")
    codes = distinct_values(passport, "project_code")
    if not codes:
        return DEFAULT_PROJECTS.copy()
    for p in DEFAULT_PROJECTS:
        if p not in codes:
            codes.insert(0, p)
    return codes


def crew_options() -> tuple[list[str], dict[str, str]]:
    labor = load_table("monthly_labor_summary", "crew_code,full_name_ru")
    codes = distinct_values(labor, "crew_code")
    name_map: dict[str, str] = {}
    if not labor.empty and "crew_code" in labor.columns:
        for _, row in labor.drop_duplicates("crew_code").iterrows():
            code = str(row.get("crew_code", "")).strip()
            if code:
                name_map[code] = str(row.get("full_name_ru") or "").strip()
    return codes, name_map


def boq_options() -> pd.DataFrame:
    df = load_table("boq_master_api", "boq_code,name,description,unit_of_measure")
    if df.empty:
        return df
    df = df.dropna(subset=["boq_code"]).drop_duplicates(subset=["boq_code"])
    df["boq_code"] = df["boq_code"].astype(str).str.strip()
    label_name = df["name"] if "name" in df.columns else df.get("description", "")
    if isinstance(label_name, pd.Series):
        df["_label"] = df["boq_code"] + " — " + label_name.fillna("").astype(str)
    else:
        df["_label"] = df["boq_code"]
    return df.sort_values("boq_code")


def passport_for_project(project_code: str) -> pd.DataFrame:
    df = load_table("monthly_passport_plan", "project_code,iwp_id_export,system_label")
    if df.empty or "project_code" not in df.columns:
        return df
    return df[df["project_code"].astype(str) == project_code]


def insert_submission(payload: dict) -> None:
    supabase.table(SUBMISSIONS_TABLE).insert(payload).execute()


def main() -> None:
    st.set_page_config(
        page_title="Смена — ввод",
        page_icon="📋",
        layout="centered",
        initial_sidebar_state="collapsed",
    )
    st.markdown(MOBILE_CSS, unsafe_allow_html=True)

    st.title("Ввод смены")
    st.caption("Независимая форма → Supabase · контур Python Form (MVP)")

    projects = project_options()
    crews, crew_names = crew_options()

    # --- Блок 1 ---
    st.header("1. Основная информация")

    project_code = st.selectbox("Проект", projects, index=0)
    work_date = st.date_input("Дата смены", value=date.today())
    shift_type = st.selectbox("Тип смены", SHIFT_OPTIONS)
    is_day_off = shift_type == "Выходной"

    submitted_by = st.text_input("Кто отправляет (ФИО / таб. №)", placeholder="Иванов И.И.")

    # --- Блок 2 ---
    st.header("2. Звено")

    if not crews:
        st.warning("Список звеньев пуст. Запустите синк Crew_Register.")
        crew_code = st.text_input("Код звена (вручную)")
        crew_name = ""
    else:
        crew_code = st.selectbox("Звено (crew_code)", crews)
        crew_name = crew_names.get(crew_code, "")

    boq_code = boq_name = unit_of_measure = None
    iwp_id = system_label = None
    quantity_today = direct_work_hours = idle_hours = None
    idle_reason = None
    operation_type = operation_quantity = operation_unit = None

    if not is_day_off:
        boq_df = boq_options()

        st.header("3. Работа")

        if boq_df.empty:
            st.warning("Справочник BOQ пуст. Запустите boq_sync.")
            boq_code = st.text_input("BoQ код")
            boq_name = st.text_input("Наименование BOQ")
            unit_of_measure = st.text_input("Ед. изм.")
        else:
            labels = boq_df["_label"].tolist()
            selected_label = st.selectbox("BOQ", labels)
            row = boq_df[boq_df["_label"] == selected_label].iloc[0]
            boq_code = str(row["boq_code"])
            boq_name = str(row.get("name") or row.get("description") or "").strip() or None
            uom = row.get("unit_of_measure")
            unit_of_measure = None if pd.isna(uom) else (str(uom).strip() or None)
            if boq_name:
                st.caption(f"Наименование: {boq_name} · Ед.: {unit_of_measure or '—'}")

        passport = passport_for_project(project_code)
        iwp_list = distinct_values(passport, "iwp_id_export")
        sys_list = distinct_values(passport, "system_label")

        if iwp_list:
            iwp_id = st.selectbox("IWP", iwp_list)
        else:
            iwp_id = st.text_input("IWP (вручную)")

        if sys_list:
            system_label = st.selectbox("System", sys_list)
        else:
            system_label = st.text_input("System (вручную)")

        c1, c2 = st.columns(2)
        with c1:
            quantity_today = st.number_input("Объём за смену", min_value=0.0, step=0.1, format="%.2f")
        with c2:
            direct_work_hours = st.number_input("Direct часы", min_value=0.0, step=0.5, format="%.1f")

        c3, c4 = st.columns(2)
        with c3:
            idle_hours = st.number_input("Простой (часы)", min_value=0.0, step=0.5, format="%.1f")
        with c4:
            idle_reason = st.text_input("Причина простоя")

        st.header("4. Операции")
        operation_type = st.selectbox("Тип операции", [""] + OPERATION_TYPES, index=0)
        if operation_type == "":
            operation_type = None
        oc1, oc2 = st.columns(2)
        with oc1:
            operation_quantity = st.number_input(
                "Количество операции", min_value=0.0, step=0.1, format="%.2f"
            )
        with oc2:
            operation_unit = st.text_input("Единица операции")

    st.header("5. Комментарий")
    comment_foreman = st.text_area("Комментарий мастера", height=100)

    day_off_confirmed = True
    if is_day_off:
        day_off_confirmed = st.checkbox("Подтверждаю: смена — выходной, работы не выполнялись")

    st.divider()

    if st.button("Отправить смену", type="primary"):
        errors: list[str] = []
        if not project_code:
            errors.append("Укажите проект.")
        if not crew_code:
            errors.append("Укажите звено.")
        if is_day_off and not day_off_confirmed:
            errors.append("Подтвердите выходной день.")
        if not is_day_off:
            if not boq_code:
                errors.append("Укажите BOQ.")
            if quantity_today is None or quantity_today <= 0:
                errors.append("Укажите объём за смену (> 0).")
            if direct_work_hours is None or direct_work_hours <= 0:
                errors.append("Укажите Direct часы (> 0).")
            if idle_hours and idle_hours > 0 and not (idle_reason or "").strip():
                errors.append("Укажите причину простоя.")

        if errors:
            for msg in errors:
                st.error(msg)
            return

        payload = {
            "submission_id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "project_code": project_code,
            "work_date": work_date.isoformat(),
            "shift_type": shift_type,
            "crew_code": str(crew_code).strip(),
            "crew_name": crew_name or None,
            "is_day_off": is_day_off,
            "boq_code": boq_code if not is_day_off else None,
            "boq_name": boq_name if not is_day_off else None,
            "iwp_id": (iwp_id or None) if not is_day_off else None,
            "system_label": (system_label or None) if not is_day_off else None,
            "unit_of_measure": unit_of_measure if not is_day_off else None,
            "quantity_today": float(quantity_today) if not is_day_off and quantity_today else None,
            "direct_work_hours": float(direct_work_hours)
            if not is_day_off and direct_work_hours
            else None,
            "idle_hours": float(idle_hours) if not is_day_off and idle_hours else None,
            "idle_reason": (idle_reason or None) if not is_day_off else None,
            "operation_type": operation_type if not is_day_off else None,
            "operation_quantity": float(operation_quantity)
            if not is_day_off and operation_quantity
            else None,
            "operation_unit": (operation_unit or None) if not is_day_off else None,
            "comment_foreman": (comment_foreman or None) if comment_foreman else None,
            "submitted_by": (submitted_by or None) if submitted_by else None,
            "data_source": "python_form",
        }

        try:
            insert_submission(payload)
            st.success("Смена успешно отправлена")
            st.balloons()
        except Exception as exc:
            st.error(
                "Не удалось сохранить. Выполните SQL: "
                "sql/daily_progress_form_submissions.sql в Supabase SQL Editor."
            )
            st.caption(str(exc))


if __name__ == "__main__":
    main()
