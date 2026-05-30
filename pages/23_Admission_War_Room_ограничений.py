from datetime import date, datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from services.supabase_client import supabase

st.set_page_config(layout="wide")

TABLE_CONSTRAINTS = "monthly_plan_constraints"
VIEW_DASHBOARD_V2 = "monthly_plan_constraints_dashboard_v2"
VIEW_DASHBOARD_V1 = "monthly_plan_constraints_dashboard_v1"

GATE_LAYER_RU = {
    "EXECUTABILITY": "Исполнимый фронт",
    "ACCEPTABILITY": "Признаваемость",
    "CREW_ECONOMICS": "Экономика звена",
}

CHECK_STATUS_RU = {
    "ОЖИДАЕТ": "Ожидает проверки",
    "PASS": "Пройдено",
    "WARNING": "Риск / требуется уточнение",
    "HOLD": "Удержание / блокировка",
    "FAIL": "Не пройдено",
}

RESOLUTION_RU = {
    "OPEN": "Открыто",
    "IN_PROGRESS": "В работе",
    "RESOLVED": "Закрыто",
    "CANCELLED": "Отменено",
}

CHECK_STATUS_OPTIONS = ["ОЖИДАЕТ", "PASS", "WARNING", "HOLD", "FAIL"]
RESOLUTION_OPTIONS = ["OPEN", "IN_PROGRESS", "RESOLVED", "CANCELLED"]
OPEN_RESOLUTION = {"OPEN", "IN_PROGRESS"}

DEPARTMENT_RU = {
    "Участок": "Линейное управление / Field Construction Management",
    "ПТО": "ПТО / Engineering & Work Packaging",
    "МТО": "МТО / Procurement & Materials",
    "ОТиТБ": "HSE / ОТиПБ",
    "QAQC": "QA/QC",
    "Коммерческий отдел": "Коммерческий контроль / Contract & Commercial",
    "Руководство": "Проектное управление / Project Management",
}

CHECK_STATUS_BG_RU = {
    "Ожидает проверки": "background-color: #f3f4f6;",
    "Пройдено": "background-color: #dcfce7;",
    "Риск / требуется уточнение": "background-color: #fef9c3;",
    "Удержание / блокировка": "background-color: #ffedd5;",
    "Не пройдено": "background-color: #fee2e2;",
}

EMPTY_MSG = (
    "Ограничений пока нет. Сформируйте проверки на странице "
    "**Контур допуска месячного плана**."
)


def safe_str(value: Any) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def safe_num(value: Any) -> float:
    if value is None or pd.isna(value):
        return 0.0
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return 0.0


def safe_date(value: Any) -> Optional[date]:
    if value is None or pd.isna(value) or safe_str(value) == "":
        return None
    try:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        return pd.to_datetime(value).date()
    except Exception:  # noqa: BLE001
        return None


def money_ru(value: Any) -> str:
    try:
        if value is None or pd.isna(value):
            return "0,00 ₽"
        amount = float(value)
        sign = "-" if amount < 0 else ""
        amount = abs(amount)
        whole, frac = f"{amount:.2f}".split(".")
        whole_fmt = f"{int(whole):,}".replace(",", " ")
        return f"{sign}{whole_fmt},{frac} ₽"
    except Exception:  # noqa: BLE001
        return "0,00 ₽"


def display_dash(value: Any) -> str:
    text = safe_str(value)
    return text if text else "—"


def reverse_map(mapping: Dict[str, str]) -> Dict[str, str]:
    return {v: k for k, v in mapping.items()}


def ru_label(tech: str, mapping: Dict[str, str]) -> str:
    if tech == "Все":
        return "Все"
    return mapping.get(tech, tech)


def norm_tech_value(
    value: Any,
    tech_options: List[str],
    mapping: Dict[str, str],
    default: str,
) -> str:
    if value is None or pd.isna(value):
        return default
    raw = str(value).strip()
    if raw in tech_options:
        return raw
    rev = reverse_map(mapping)
    if raw in rev:
        return rev[raw]
    upper = raw.upper()
    if upper in tech_options:
        return upper
    return default


def norm_check_status_key(value: Any) -> str:
    return norm_tech_value(value, CHECK_STATUS_OPTIONS, CHECK_STATUS_RU, "ОЖИДАЕТ")


def dept_ui(db_value: Any) -> str:
    return DEPARTMENT_RU.get(safe_str(db_value), safe_str(db_value))


def row_risk_value(row: pd.Series) -> float:
    if "value_at_risk" in row.index and not pd.isna(row.get("value_at_risk")):
        return safe_num(row.get("value_at_risk"))
    return safe_num(row.get("plan_value"))


def reason_text(row: pd.Series) -> str:
    for col in ("block_reason", "root_cause", "constraint_category", "comment"):
        text = safe_str(row.get(col))
        if text:
            return text
    return "—"


def unique_risk_sum(df_part: pd.DataFrame) -> float:
    if df_part.empty:
        return 0.0
    key_cols: List[str] = []
    if "line_id" in df_part.columns:
        key_cols = ["line_id"]
    else:
        key_cols = [
            "project_code",
            "month_key",
            "facility_building",
            "construction_discipline",
            "boq_code",
            "crew_id",
        ]
        key_cols = [c for c in key_cols if c in df_part.columns]
    risk_col = "_risk_val"
    if key_cols:
        return float(df_part.drop_duplicates(subset=key_cols)[risk_col].sum())
    return float(df_part[risk_col].sum())


def owner_label(value: Any) -> str:
    text = safe_str(value)
    return text if text else "Не назначен"


def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()
    created_col = (
        "constraint_created_at"
        if "constraint_created_at" in result.columns
        else "created_at"
    )

    if "days_overdue" not in result.columns or "is_overdue" not in result.columns:
        overdue_days: List[int] = []
        overdue_flags: List[bool] = []
        for _, row in result.iterrows():
            status = safe_str(row.get("resolution_status")).upper()
            target = safe_date(row.get("target_resolution_date"))
            if status in {"RESOLVED", "CANCELLED"} or target is None or target >= date.today():
                overdue_days.append(0)
                overdue_flags.append(False)
            else:
                overdue_days.append((date.today() - target).days)
                overdue_flags.append(True)
        if "days_overdue" not in result.columns:
            result["days_overdue"] = overdue_days
        if "is_overdue" not in result.columns:
            result["is_overdue"] = overdue_flags

    result["_risk_val"] = result.apply(row_risk_value, axis=1)
    return result


@st.cache_data(ttl=300)
def load_constraints() -> pd.DataFrame:
    for table in (VIEW_DASHBOARD_V2, VIEW_DASHBOARD_V1, TABLE_CONSTRAINTS):
        try:
            response = supabase.table(table).select("*").limit(10000).execute()
            df = enrich_dataframe(pd.DataFrame(response.data or []))
            if not df.empty:
                return df
        except Exception:  # noqa: BLE001
            continue
    return pd.DataFrame()


def filter_options(df: pd.DataFrame, col: str) -> List[str]:
    if df.empty or col not in df.columns:
        return ["Все"]
    vals = df[col].dropna().astype(str).str.strip()
    vals = vals[vals != ""].unique().tolist()
    return ["Все"] + sorted(vals)


def filter_options_ru(df: pd.DataFrame, col: str, mapping: Dict[str, str]) -> List[str]:
    if df.empty or col not in df.columns:
        return ["Все"]
    vals = df[col].dropna().astype(str).str.strip()
    vals = vals[vals != ""].unique().tolist()
    return ["Все"] + sorted(vals, key=lambda v: ru_label(v, mapping))


def apply_filters(
    df: pd.DataFrame,
    project: str,
    month: str,
    facility: str,
    discipline: str,
    gate_layer: str,
    department: str,
    check_status: str,
    resolution_status: str,
    overdue_only: bool,
) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()
    if project != "Все" and "project_code" in result.columns:
        result = result[result["project_code"].astype(str) == project]
    if month != "Все" and "month_key" in result.columns:
        result = result[result["month_key"].astype(str) == month]
    if facility != "Все" and "facility_building" in result.columns:
        result = result[result["facility_building"].astype(str) == facility]
    if discipline != "Все" and "construction_discipline" in result.columns:
        result = result[result["construction_discipline"].astype(str) == discipline]
    if gate_layer != "Все" and "gate_layer" in result.columns:
        result = result[result["gate_layer"].astype(str) == gate_layer]
    if department != "Все" and "responsible_department" in result.columns:
        result = result[result["responsible_department"].astype(str) == department]
    if check_status != "Все" and "check_status" in result.columns:
        result = result[result["check_status"].astype(str) == check_status]
    if resolution_status != "Все" and "resolution_status" in result.columns:
        result = result[result["resolution_status"].astype(str) == resolution_status]
    if overdue_only and "is_overdue" in result.columns:
        result = result[result["is_overdue"].astype(bool)]
    return result


def style_status_table(df_in: pd.DataFrame, status_col: str):
    styler = df_in.style
    if status_col in df_in.columns:
        fn = lambda v: CHECK_STATUS_BG_RU.get(str(v), "")  # noqa: E731
        if hasattr(styler, "map"):
            styler = styler.map(fn, subset=pd.IndexSlice[:, [status_col]])
        else:
            styler = styler.applymap(fn, subset=pd.IndexSlice[:, [status_col]])
    return styler


def translate_check_status(series: pd.Series) -> pd.Series:
    return series.apply(
        lambda v: CHECK_STATUS_RU.get(norm_check_status_key(v), safe_str(v))
    )


def translate_resolution(series: pd.Series) -> pd.Series:
    return series.apply(
        lambda v: RESOLUTION_RU.get(
            norm_tech_value(v, RESOLUTION_OPTIONS, RESOLUTION_RU, safe_str(v)),
            safe_str(v),
        )
    )


def render_kpis(df: pd.DataFrame) -> None:
    total = len(df)
    open_cnt = (
        len(df[df["resolution_status"].astype(str).isin(OPEN_RESOLUTION)])
        if "resolution_status" in df.columns
        else 0
    )
    hold_cnt = (
        len(df[df["check_status"].astype(str) == "HOLD"]) if "check_status" in df.columns else 0
    )
    fail_cnt = (
        len(df[df["check_status"].astype(str) == "FAIL"]) if "check_status" in df.columns else 0
    )
    overdue_cnt = int(df["is_overdue"].astype(bool).sum()) if "is_overdue" in df.columns else 0
    risk_sum = unique_risk_sum(df)
    overdue_series = (
        df.loc[df["days_overdue"].astype(float) > 0, "days_overdue"].astype(float)
        if "days_overdue" in df.columns
        else pd.Series(dtype=float)
    )
    avg_overdue = float(overdue_series.mean()) if not overdue_series.empty else 0.0
    if "owner_name" in df.columns:
        owners = df["owner_name"].apply(lambda v: safe_str(v)).replace("", pd.NA).dropna().unique()
        owner_cnt = len(owners)
    else:
        owner_cnt = 0

    c1, c2, c3, c4 = st.columns(4)
    c5, c6, c7, c8 = st.columns(4)
    c1.metric("Всего ограничений", total)
    c2.metric("Открыто", open_cnt)
    c3.metric("HOLD", hold_cnt)
    c4.metric("FAIL", fail_cnt)
    c5.metric("Просрочено", overdue_cnt)
    c6.metric("Стоимость под риском", money_ru(risk_sum))
    c7.metric("Средняя просрочка, дней", f"{avg_overdue:.1f}")
    c8.metric("Владельцев ограничений", owner_cnt)


def render_department_summary(df: pd.DataFrame) -> None:
    st.markdown("### Сводка по отделам")
    if df.empty or "responsible_department" not in df.columns:
        st.caption("Нет данных.")
        return

    tmp = df.copy()
    tmp["_hold"] = tmp["check_status"].astype(str) == "HOLD" if "check_status" in tmp.columns else False
    tmp["_fail"] = tmp["check_status"].astype(str) == "FAIL" if "check_status" in tmp.columns else False
    tmp["_overdue"] = tmp["is_overdue"].astype(bool) if "is_overdue" in tmp.columns else False

    rows: List[Dict[str, Any]] = []
    for dept, part in tmp.groupby("responsible_department", dropna=False):
        rows.append(
            {
                "Отдел": dept_ui(dept),
                "Всего": len(part),
                "HOLD": int(part["_hold"].sum()),
                "FAIL": int(part["_fail"].sum()),
                "Просрочено": int(part["_overdue"].sum()),
                "Стоимость под риском": money_ru(unique_risk_sum(part)),
            }
        )
    show = pd.DataFrame(rows)
    st.dataframe(show, use_container_width=True, hide_index=True)


def render_top10(df: pd.DataFrame) -> None:
    st.markdown("### ТОП-10 ограничений по стоимости под риском")
    if df.empty:
        st.caption("Нет данных.")
        return

    top = df.sort_values("_risk_val", ascending=False).head(10).copy()
    top["Статус"] = translate_check_status(top["check_status"]) if "check_status" in top.columns else "—"
    top["Срок закрытия"] = top["target_resolution_date"].apply(
        lambda v: safe_date(v).isoformat() if safe_date(v) else "—"
    ) if "target_resolution_date" in top.columns else "—"
    top["Просрочка"] = top["days_overdue"].apply(lambda v: int(safe_num(v))) if "days_overdue" in top.columns else 0
    top["Причина"] = top.apply(reason_text, axis=1)

    table = pd.DataFrame(
        {
            "BOQ-код": top["boq_code"].apply(display_dash) if "boq_code" in top.columns else "—",
            "Наименование": top["boq_name"].apply(display_dash) if "boq_name" in top.columns else "—",
            "Отдел": top["responsible_department"].apply(dept_ui),
            "Проверка": top["check_name"].apply(display_dash) if "check_name" in top.columns else "—",
            "Статус": top["Статус"],
            "Владелец": top["owner_name"].apply(display_dash) if "owner_name" in top.columns else "—",
            "Срок закрытия": top["Срок закрытия"],
            "Просрочка": top["Просрочка"],
            "Стоимость под риском": top["_risk_val"].apply(money_ru),
            "Причина": top["Причина"],
        }
    )
    st.dataframe(style_status_table(table, "Статус"), use_container_width=True, hide_index=True)


def render_overdue(df: pd.DataFrame) -> None:
    st.markdown("### Просроченные ограничения")
    if df.empty:
        st.caption("Нет данных.")
        return

    overdue = df[df["days_overdue"].astype(float) > 0].copy() if "days_overdue" in df.columns else pd.DataFrame()
    if overdue.empty:
        st.caption("Просроченных ограничений нет.")
        return

    overdue = overdue.sort_values("days_overdue", ascending=False)
    overdue["Статус"] = translate_check_status(overdue["check_status"]) if "check_status" in overdue.columns else "—"
    overdue["Причина"] = overdue.apply(reason_text, axis=1)

    table = pd.DataFrame(
        {
            "BOQ-код": overdue["boq_code"].apply(display_dash) if "boq_code" in overdue.columns else "—",
            "Отдел": overdue["responsible_department"].apply(dept_ui),
            "Проверка": overdue["check_name"].apply(display_dash) if "check_name" in overdue.columns else "—",
            "Владелец": overdue["owner_name"].apply(display_dash) if "owner_name" in overdue.columns else "—",
            "Срок закрытия": overdue["target_resolution_date"].apply(
                lambda v: safe_date(v).isoformat() if safe_date(v) else "—"
            ) if "target_resolution_date" in overdue.columns else "—",
            "Просрочка, дней": overdue["days_overdue"].apply(lambda v: int(safe_num(v))),
            "Статус": overdue["Статус"],
            "Причина": overdue["Причина"],
        }
    )
    st.dataframe(style_status_table(table, "Статус"), use_container_width=True, hide_index=True)


def render_owners(df: pd.DataFrame) -> None:
    st.markdown("### Владельцы ограничений")
    if df.empty:
        st.caption("Нет данных.")
        return

    tmp = df.copy()
    tmp["_owner"] = (
        tmp["owner_name"].apply(owner_label) if "owner_name" in tmp.columns else "Не назначен"
    )
    tmp["_overdue"] = tmp["is_overdue"].astype(bool) if "is_overdue" in tmp.columns else False

    rows: List[Dict[str, Any]] = []
    for owner, part in tmp.groupby("_owner", dropna=False):
        risk_num = unique_risk_sum(part)
        rows.append(
            {
                "Владелец": owner,
                "Ограничений": len(part),
                "Просрочено": int(part["_overdue"].sum()),
                "_risk_num": risk_num,
                "Стоимость под риском": money_ru(risk_num),
                "Макс. просрочка, дн.": int(part["days_overdue"].max()) if "days_overdue" in part.columns else 0,
            }
        )
    agg = (
        pd.DataFrame(rows)
        .sort_values("_risk_num", ascending=False)
        .drop(columns=["_risk_num"])
    )
    agg["Макс. просрочка, дн."] = agg["Макс. просрочка, дн."].apply(lambda v: int(safe_num(v)))
    st.dataframe(agg, use_container_width=True, hide_index=True)


def render_gate_layers(df: pd.DataFrame) -> None:
    st.markdown("### Контуры допуска")
    st.caption(
        "Стоимость по контурам считается внутри каждого контура; "
        "одна строка плана может входить в несколько контуров."
    )
    if df.empty or "gate_layer" not in df.columns:
        st.caption("Нет данных.")
        return

    rows: List[Dict[str, Any]] = []
    for gate, part in df.groupby("gate_layer", dropna=False):
        rows.append(
            {
                "Контур допуска": GATE_LAYER_RU.get(safe_str(gate), safe_str(gate)),
                "Количество": len(part),
                "Стоимость под риском": money_ru(unique_risk_sum(part)),
            }
        )
    show = pd.DataFrame(rows)
    st.dataframe(show, use_container_width=True, hide_index=True)


def main() -> None:
    st.title("War Room ограничений")
    st.caption(
        "Совещание по блокировкам месячного плана: ТОП по стоимости, просрочки, "
        "владельцы и контуры допуска."
    )

    base_df = load_constraints()
    if base_df.empty:
        st.info(EMPTY_MSG)
        return

    st.markdown("### Фильтры")
    f1, f2, f3, f4 = st.columns(4)
    f5, f6, f7, f8, f9 = st.columns(5)

    project_sel = f1.selectbox("Проект", filter_options(base_df, "project_code"))
    month_sel = f2.selectbox("Месяц", filter_options(base_df, "month_key"))
    facility_sel = f3.selectbox("Здание / объект", filter_options(base_df, "facility_building"))
    discipline_sel = f4.selectbox("Дисциплина", filter_options(base_df, "construction_discipline"))
    gate_sel = f5.selectbox(
        "Контур допуска",
        filter_options_ru(base_df, "gate_layer", GATE_LAYER_RU),
        format_func=lambda v: ru_label(v, GATE_LAYER_RU),
    )
    department_sel = f6.selectbox(
        "Отдел",
        filter_options(base_df, "responsible_department"),
        format_func=lambda v: dept_ui(v) if v != "Все" else "Все",
    )
    check_status_sel = f7.selectbox(
        "Статус проверки",
        filter_options_ru(base_df, "check_status", CHECK_STATUS_RU),
        format_func=lambda v: ru_label(v, CHECK_STATUS_RU),
    )
    resolution_sel = f8.selectbox(
        "Статус устранения",
        filter_options_ru(base_df, "resolution_status", RESOLUTION_RU),
        format_func=lambda v: ru_label(v, RESOLUTION_RU),
    )
    overdue_only = f9.checkbox("Только просроченные")

    df = apply_filters(
        base_df,
        project_sel,
        month_sel,
        facility_sel,
        discipline_sel,
        gate_sel,
        department_sel,
        check_status_sel,
        resolution_sel,
        overdue_only,
    )

    if df.empty:
        st.info("По выбранным фильтрам ограничений нет.")
        return

    st.markdown("### KPI")
    render_kpis(df)

    st.markdown("---")
    render_department_summary(df)
    st.markdown("---")
    render_top10(df)
    st.markdown("---")
    render_overdue(df)
    st.markdown("---")
    render_owners(df)
    st.markdown("---")
    render_gate_layers(df)


if __name__ == "__main__":
    main()
