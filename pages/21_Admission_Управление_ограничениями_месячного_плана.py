import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client

from services.supabase_client import supabase

load_dotenv()

st.set_page_config(layout="wide")

TABLE_CONSTRAINTS = "monthly_plan_constraints"
VIEW_DASHBOARD_V2 = "monthly_plan_constraints_dashboard_v2"

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

SEVERITY_RU = {
    "LOW": "Низкая",
    "MEDIUM": "Средняя",
    "HIGH": "Высокая",
    "CRITICAL": "Критическая",
}

CHECK_STATUS_OPTIONS = ["ОЖИДАЕТ", "PASS", "WARNING", "HOLD", "FAIL"]
RESOLUTION_OPTIONS = ["OPEN", "IN_PROGRESS", "RESOLVED", "CANCELLED"]
SEVERITY_OPTIONS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

DEPARTMENT_RU = {
    "Участок": "Линейное управление / Field Construction Management",
    "ПТО": "ПТО / Engineering & Work Packaging",
    "МТО": "МТО / Procurement & Materials",
    "ОТиТБ": "HSE / ОТиПБ",
    "QAQC": "QA/QC",
    "Коммерческий отдел": "Коммерческий контроль / Contract & Commercial",
    "Руководство": "Проектное управление / Project Management",
}

CATEGORY_BY_DEPARTMENT: Dict[str, List[str]] = {
    "ПТО": [
        "РД не выдана",
        "РД не актуальна / устаревшая ревизия",
        "Нет IWP / пакет работ не сформирован",
        "Нет Work Package / методики выполнения",
        "Не подтверждён объём BOQ",
        "Несоответствие BOQ и РД",
        "Не согласованы изменения",
        "Нет ответа на RFI",
        "Нет исполнительной схемы",
        "Нет As-built основы",
        "Нет акта скрытых работ",
        "Нет привязки к системе / зоне",
        "Несоответствие РД и фактического фронта",
        "Другое",
    ],
    "МТО": [
        "Материал не поставлен",
        "Оборудование не поставлено",
        "Нет сертификатов / паспортов",
        "Не выполнен входной контроль",
        "Материал не тот / пересорт",
        "Нет крепежа / расходников",
        "Нет складского подтверждения",
        "Нет комплектации по системе",
        "Нет логистики до зоны работ",
        "Поставка обещана, но просрочена",
        "Материал зарезервирован под другой фронт",
        "Другое",
    ],
    "Участок": [
        "Фронт физически не открыт",
        "Смежники мешают",
        "Нет доступа в зону",
        "Нет лесов / подмостей / подъёмника",
        "Нет техники / механизации",
        "Зона не подготовлена",
        "Нет людей / звена",
        "Нет мастера / ответственного",
        "Невозможно безопасно выполнить",
        "Не завершены предшествующие работы",
        "Другое",
    ],
    "ОТиТБ": [
        "Нет наряда-допуска",
        "Нет допуска персонала",
        "Нет инструктажа",
        "Нет безопасных условий",
        "Нет ограждений / знаков",
        "Работы повышенной опасности не согласованы",
        "Нет СИЗ / спецусловий",
        "Нет ППР / технологической карты для опасных работ",
        "Нет допуска к высотным работам",
        "Другое",
    ],
    "QAQC": [
        "Нет ИТП / плана контроля",
        "Не определена точка инспекции",
        "Нет возможности предъявить качество",
        "Нет актов скрытых работ",
        "Нет протоколов испытаний",
        "Нет подтверждения ВИК / контроля",
        "Требуется инспекция заказчика",
        "Нет чек-листа контроля",
        "Нет лабораторного / инструментального подтверждения",
        "Другое",
    ],
    "Коммерческий отдел": [
        "Нет основания для предъявления",
        "Нет ДС / изменение не оформлено",
        "Объём не признаётся заказчиком",
        "Работа вне BOQ",
        "Нет подтверждающих документов",
        "Риск отказа в КС",
        "Нет подписанного акта / протокола",
        "Нет коммерческого основания для оплаты",
        "Не подтверждена цена / расценка",
        "Другое",
    ],
    "Руководство": [
        "Недостаточно людей",
        "Перегруз звена",
        "Норма выработки не подтверждена",
        "Высокая себестоимость",
        "Отрицательная маржа",
        "Недостаточно часов до конца месяца",
        "Не подтверждён состав звена",
        "Работа не приоритетна по Critical Value Path",
        "Нет управленческого решения по запуску",
        "Другое",
    ],
}

ADMISSION_INFO = (
    "Страница объединяет три контура допуска:\n"
    "1) **Исполнимый фронт** — можно ли физически выполнить работу.\n"
    "2) **Признаваемость** — можно ли довести работу до инспекции, признания, "
    "предъявления и закрытия объёма.\n"
    "3) **Экономика звена** — можно ли выполнить без убытка."
)

BOQ_MULTI_CONSTRAINT_INFO = (
    "Один BOQ-код может иметь несколько ограничений в разных контурах: исполнимый фронт, "
    "признаваемость, экономика звена. У одного подразделения также может быть несколько "
    "проверок по одной BOQ-строке (например, ПТО — и по РД/IWP, и по признаваемости "
    "исполнительной документации)."
)

TABLE_COLUMNS = [
    "project_code",
    "month_key",
    "boq_code",
    "boq_name",
    "responsible_department",
    "gate_layer",
    "check_name",
    "check_status",
    "severity",
    "resolution_status",
    "owner_name",
    "target_resolution_date",
    "days_overdue",
    "value_at_risk_display",
    "updated_by",
    "comment",
]

TABLE_COLUMNS_RU = {
    "project_code": "Проект",
    "month_key": "Месяц",
    "boq_code": "BOQ-код",
    "boq_name": "Наименование работы",
    "responsible_department": "Отдел",
    "gate_layer": "Контур допуска",
    "check_name": "Проверка",
    "check_status": "Статус проверки",
    "severity": "Критичность",
    "resolution_status": "Статус устранения",
    "owner_name": "Владелец",
    "target_resolution_date": "Срок закрытия",
    "days_overdue": "Просрочка, дней",
    "value_at_risk_display": "Стоимость под риском",
    "updated_by": "Кто обновил",
    "comment": "Комментарий",
}

CHECK_STATUS_BG_RU = {
    "Ожидает проверки": "background-color: #f3f4f6;",
    "Пройдено": "background-color: #dcfce7;",
    "Риск / требуется уточнение": "background-color: #fef9c3;",
    "Удержание / блокировка": "background-color: #ffedd5;",
    "Не пройдено": "background-color: #fee2e2;",
}


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
    """Единый денежный формат: 2 304 000,00 ₽"""
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


def format_datetime_ru(value: Any) -> str:
    if value is None or pd.isna(value) or safe_str(value) == "":
        return "—"
    try:
        return pd.to_datetime(value).strftime("%d.%m.%Y %H:%M")
    except Exception:  # noqa: BLE001
        return "—"


def get_write_client() -> Optional[Client]:
    url = os.getenv("SUPABASE_URL")
    secret_key = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not secret_key:
        return None
    return create_client(url, secret_key)


def reverse_map(mapping: Dict[str, str]) -> Dict[str, str]:
    return {v: k for k, v in mapping.items()}


def dept_ui(db_value: Any) -> str:
    return DEPARTMENT_RU.get(safe_str(db_value), safe_str(db_value))


def dept_db(ui_value: str) -> str:
    return reverse_map(DEPARTMENT_RU).get(ui_value.strip(), ui_value.strip())


def plan_line_key(row: pd.Series) -> str:
    line_id = safe_str(row.get("line_id"))
    if line_id:
        return f"line:{line_id}"
    parts = [
        safe_str(row.get("project_code")),
        safe_str(row.get("month_key")),
        safe_str(row.get("facility_building")),
        safe_str(row.get("construction_discipline")),
        safe_str(row.get("boq_code")),
        safe_str(row.get("crew_id")),
    ]
    return "composite:" + "|".join(parts)


def kpi_risk_sum(df: pd.DataFrame) -> float:
    """Сумма plan_value/value_at_risk один раз на строку плана (не × число отделов)."""
    if df.empty:
        return 0.0
    tmp = df.copy()
    tmp["_plan_line_key"] = tmp.apply(plan_line_key, axis=1)
    tmp["_risk_val"] = tmp.apply(row_risk_value, axis=1)
    deduped = tmp.drop_duplicates(subset=["_plan_line_key"], keep="first")
    return float(deduped["_risk_val"].sum())


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


def ru_selectbox(
    label: str,
    tech_options: List[str],
    mapping: Dict[str, str],
    current_tech: str,
    key: Optional[str] = None,
) -> str:
    labels = [mapping.get(t, t) for t in tech_options]
    current_tech = norm_tech_value(current_tech, tech_options, mapping, tech_options[0])
    current_label = mapping.get(current_tech, current_tech)
    index = labels.index(current_label) if current_label in labels else 0
    selected_label = st.selectbox(label, labels, index=index, key=key)
    rev = reverse_map(mapping)
    return rev.get(selected_label, tech_options[labels.index(selected_label)])


def filter_options_ru(
    df: pd.DataFrame,
    col: str,
    mapping: Dict[str, str],
) -> List[str]:
    """Технические значения для фильтра; отображение — через format_func."""
    if df.empty or col not in df.columns:
        return ["Все"]
    vals = df[col].dropna().astype(str).str.strip()
    vals = vals[vals != ""].unique().tolist()
    return ["Все"] + sorted(vals, key=lambda v: ru_label(v, mapping))


def category_options_for_department(department: str, current: str) -> List[str]:
    dept = safe_str(department)
    opts = list(CATEGORY_BY_DEPARTMENT.get(dept, ["Другое"]))
    if current and current not in opts:
        opts = [current] + opts
    return opts


def style_check_status_bg(val: Any) -> str:
    return CHECK_STATUS_BG_RU.get(str(val), "")


def style_overdue_bg(val: Any) -> str:
    try:
        if int(float(val)) > 0:
            return "background-color: #fee2e2;"
    except Exception:  # noqa: BLE001
        pass
    return ""


def style_severity_text(val: Any) -> str:
    text = str(val)
    if text in ("Критическая", "CRITICAL"):
        return "color: #b91c1c; font-weight: 700;"
    if text in ("Высокая", "HIGH"):
        return "color: #c2410c; font-weight: 600;"
    return ""


def filter_options(df: pd.DataFrame, col: str) -> List[str]:
    if df.empty or col not in df.columns:
        return ["Все"]
    vals = df[col].dropna().astype(str).str.strip()
    vals = vals[vals != ""].unique().tolist()
    return ["Все"] + sorted(vals)


def row_risk_value(row: pd.Series) -> float:
    if "value_at_risk" in row.index and not pd.isna(row.get("value_at_risk")):
        return safe_num(row.get("value_at_risk"))
    return safe_num(row.get("plan_value"))


def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    result = df.copy()
    created_col = (
        "constraint_created_at"
        if "constraint_created_at" in result.columns
        else "created_at"
    )

    if "days_open" not in result.columns:
        days_open: List[int] = []
        for _, row in result.iterrows():
            start = safe_date(row.get(created_col)) if created_col in result.columns else None
            resolved = safe_date(row.get("resolved_at")) if "resolved_at" in result.columns else None
            end = date.today() if resolved is None else resolved
            if start is None:
                days_open.append(0)
            else:
                days_open.append(max((end - start).days, 0))
        result["days_open"] = days_open

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

    result["value_at_risk_display"] = result.apply(row_risk_value, axis=1)
    return result


@st.cache_data(ttl=300)
def load_constraints() -> pd.DataFrame:
    try:
        response = (
            supabase.table(VIEW_DASHBOARD_V2).select("*").limit(10000).execute()
        )
        return enrich_dataframe(pd.DataFrame(response.data or []))
    except Exception:  # noqa: BLE001
        try:
            response = (
                supabase.table(TABLE_CONSTRAINTS).select("*").limit(10000).execute()
            )
            return enrich_dataframe(pd.DataFrame(response.data or []))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Не удалось загрузить ограничения: {exc}")
            return pd.DataFrame()


def apply_filters(
    df: pd.DataFrame,
    project: str,
    month: str,
    facility: str,
    discipline: str,
    department: str,
    check_status: str,
    resolution_status: str,
    overdue_only: bool,
    search: str,
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
    if department != "Все" and "responsible_department" in result.columns:
        result = result[result["responsible_department"].astype(str) == department]
    if check_status != "Все" and "check_status" in result.columns:
        result = result[result["check_status"].astype(str) == check_status]
    if resolution_status != "Все" and "resolution_status" in result.columns:
        result = result[result["resolution_status"].astype(str) == resolution_status]
    if overdue_only and "is_overdue" in result.columns:
        result = result[result["is_overdue"].astype(bool)]
    if search.strip():
        q = search.strip().lower()
        mask = pd.Series(False, index=result.index)
        for col in ("boq_code", "boq_name", "owner_name"):
            if col in result.columns:
                mask = mask | result[col].astype(str).str.lower().str.contains(q, na=False)
        result = result[mask]
    return result


def constraint_label(row: pd.Series) -> str:
    status_key = norm_check_status_key(row.get("check_status"))
    status_ui = CHECK_STATUS_RU.get(status_key, status_key)
    gate_ui = GATE_LAYER_RU.get(safe_str(row.get("gate_layer")), safe_str(row.get("gate_layer")))
    return (
        f"{dept_ui(row.get('responsible_department'))} | "
        f"{safe_str(row.get('boq_code'))} | "
        f"{safe_str(row.get('check_name'))} | "
        f"{gate_ui} | "
        f"{status_ui}"
    )


def update_constraint_record(
    constraint_id: str,
    payload: Dict[str, Any],
) -> Optional[str]:
    client = get_write_client()
    if client is None:
        return "SUPABASE_SECRET_KEY не задан в .env — сохранение недоступно."
    try:
        client.table(TABLE_CONSTRAINTS).update(payload).eq(
            "constraint_id", constraint_id
        ).execute()
        return None
    except Exception as exc:  # noqa: BLE001
        return str(exc)


def _apply_cell_style(styler, func, column: str):
    if column not in styler.data.columns:
        return styler
    if hasattr(styler, "map"):
        return styler.map(func, subset=pd.IndexSlice[:, [column]])
    return styler.applymap(func, subset=pd.IndexSlice[:, [column]])


def style_table(df_in: pd.DataFrame):
    styler = df_in.style
    styler = _apply_cell_style(styler, style_check_status_bg, TABLE_COLUMNS_RU["check_status"])
    styler = _apply_cell_style(styler, style_overdue_bg, TABLE_COLUMNS_RU["days_overdue"])
    severity_col = TABLE_COLUMNS_RU.get("severity", "Критичность")
    styler = _apply_cell_style(styler, style_severity_text, severity_col)
    return styler


def render_kpis(df: pd.DataFrame) -> None:
    total = len(df)
    wait_cnt = len(df[df["check_status"].astype(str) == "ОЖИДАЕТ"]) if "check_status" in df.columns else 0
    pass_cnt = len(df[df["check_status"].astype(str) == "PASS"]) if "check_status" in df.columns else 0
    warn_cnt = len(df[df["check_status"].astype(str) == "WARNING"]) if "check_status" in df.columns else 0
    hold_cnt = len(df[df["check_status"].astype(str) == "HOLD"]) if "check_status" in df.columns else 0
    fail_cnt = len(df[df["check_status"].astype(str) == "FAIL"]) if "check_status" in df.columns else 0
    overdue_cnt = int(df["is_overdue"].astype(bool).sum()) if "is_overdue" in df.columns else 0
    risk_sum = kpi_risk_sum(df)

    c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)
    c1.metric("Всего ограничений", total)
    c2.metric("Ожидает проверки", wait_cnt)
    c3.metric("Пройдено", pass_cnt)
    c4.metric("Риск", warn_cnt)
    c5.metric("Удержание", hold_cnt)
    c6.metric("Не пройдено", fail_cnt)
    c7.metric("Просрочено", overdue_cnt)
    c8.metric("Стоимость под риском", money_ru(risk_sum))


def render_edit_card(row: pd.Series) -> None:
    st.markdown("### Карточка ограничения")
    st.caption(BOQ_MULTI_CONSTRAINT_INFO)
    info1, info2, info3 = st.columns(3)
    info1.markdown(f"**BOQ-код:** {safe_str(row.get('boq_code'))}")
    info1.markdown(f"**Наименование:** {safe_str(row.get('boq_name'))}")
    info1.markdown(f"**Плановая стоимость:** {money_ru(row.get('plan_value'))}")
    info2.markdown(
        f"**Контур допуска:** {GATE_LAYER_RU.get(safe_str(row.get('gate_layer')), safe_str(row.get('gate_layer')))}"
    )
    info2.markdown(f"**Отдел:** {dept_ui(row.get('responsible_department'))}")
    info2.markdown(f"**Проверка:** {safe_str(row.get('check_name'))}")
    info3.markdown(
        f"**Текущий статус:** "
        f"{CHECK_STATUS_RU.get(norm_check_status_key(row.get('check_status')), safe_str(row.get('check_status')))}"
    )
    created = safe_date(row.get("constraint_created_at")) or safe_date(row.get("created_at"))
    info3.markdown(f"**Дата возникновения:** {created.isoformat() if created else '—'}")
    info3.markdown(f"**Дней открыто:** {int(safe_num(row.get('days_open')))}")

    info4, info5, info6 = st.columns(3)
    target = safe_date(row.get("target_resolution_date"))
    info4.markdown(f"**Срок закрытия:** {target.isoformat() if target else '—'}")
    info4.markdown(f"**Просрочка:** {int(safe_num(row.get('days_overdue')))} дн.")
    if "evidence_count" in row.index and not pd.isna(row.get("evidence_count")):
        info5.markdown(f"**Доказательств:** {int(safe_num(row.get('evidence_count')))}")
    promised = safe_date(row.get("effective_promised_date"))
    if promised:
        info5.markdown(f"**Дата обещания:** {promised.isoformat()}")
    if "days_since_promise" in row.index and safe_num(row.get("days_since_promise")) > 0:
        info6.markdown(f"**Просрочка обещания:** {int(safe_num(row.get('days_since_promise')))} дн.")

    st.markdown("**Аудит последнего изменения**")
    audit1, audit2, audit3 = st.columns(3)
    audit1.markdown(f"**Кто обновил:** {display_dash(row.get('updated_by'))}")
    audit2.markdown(f"**Роль обновившего:** {display_dash(row.get('updated_role'))}")
    audit3.markdown(
        f"**Дата последнего действия:** {format_datetime_ru(row.get('last_action_at'))}"
    )

    st.markdown("---")
    constraint_id = safe_str(row.get("constraint_id"))
    if not constraint_id:
        st.error("У записи нет constraint_id — сохранение недоступно.")
        return

    current_check = norm_check_status_key(row.get("check_status"))
    current_resolution = norm_tech_value(
        row.get("resolution_status"), RESOLUTION_OPTIONS, RESOLUTION_RU, "OPEN"
    )
    current_severity = norm_tech_value(
        row.get("severity"), SEVERITY_OPTIONS, SEVERITY_RU, "MEDIUM"
    )
    dept = safe_str(row.get("responsible_department"))
    current_category = safe_str(row.get("constraint_category")) or "Другое"
    category_opts = category_options_for_department(dept, current_category)
    if current_category not in category_opts:
        current_category = "Другое"

    e1, e2 = st.columns(2)
    new_check_status = ru_selectbox(
        "Статус проверки",
        CHECK_STATUS_OPTIONS,
        CHECK_STATUS_RU,
        current_check,
        key=f"check_status_{constraint_id}",
    )
    new_resolution_status = ru_selectbox(
        "Статус устранения",
        RESOLUTION_OPTIONS,
        RESOLUTION_RU,
        current_resolution,
        key=f"resolution_{constraint_id}",
    )

    e3, e4, e5 = st.columns(3)
    owner_name = e3.text_input("Владелец", value=safe_str(row.get("owner_name")))
    owner_role = e4.text_input("Роль владельца", value=safe_str(row.get("owner_role")))
    owner_dept_raw = safe_str(row.get("owner_department") or row.get("responsible_department"))
    owner_department = e5.text_input(
        "Подразделение владельца",
        value=dept_ui(owner_dept_raw) if owner_dept_raw in DEPARTMENT_RU else owner_dept_raw,
    )

    e6, e7 = st.columns(2)
    target_default = target or date.today()
    new_target_date = e6.date_input("Срок закрытия (target_resolution_date)", value=target_default)
    new_severity = ru_selectbox(
        "Критичность",
        SEVERITY_OPTIONS,
        SEVERITY_RU,
        current_severity,
        key=f"severity_{constraint_id}",
    )

    st.caption(
        "Выберите тип ограничения. Это нужно для совещания и анализа bottleneck по отделам."
    )
    category_labels = category_opts
    category_index = (
        category_labels.index(current_category)
        if current_category in category_labels
        else category_labels.index("Другое")
    )
    new_category = st.selectbox(
        "Тип ограничения",
        category_labels,
        index=category_index,
        key=f"category_{constraint_id}",
    )
    root_cause = st.text_area("Корневая причина", value=safe_str(row.get("root_cause")))
    block_reason_default = safe_str(row.get("block_reason"))
    block_reason = st.text_area(
        "Причина блокировки",
        value=block_reason_default,
        key=f"block_reason_{constraint_id}",
    )
    comment = st.text_area("Комментарий", value=safe_str(row.get("comment")))

    default_risk = row_risk_value(row)
    st.markdown(f"**Текущая стоимость под риском:** {money_ru(default_risk)}")
    new_value_at_risk = st.number_input(
        "Стоимость под риском для сохранения, ₽",
        min_value=0.0,
        value=float(default_risk),
        step=1000.0,
        format="%.2f",
        help="Введите число без пробелов. Отображение суммы выше форматируется автоматически.",
        key=f"value_at_risk_{constraint_id}",
    )
    st.caption(f"Будет сохранено как: {money_ru(new_value_at_risk)}")

    u1, u2 = st.columns(2)
    updated_by = u1.text_input("Кто обновляет", value="Пользователь Streamlit")
    updated_role = u2.text_input("Роль / должность обновляющего", value="")

    if st.button("Сохранить изменение", type="primary", key=f"save_{constraint_id}"):
        now_iso = datetime.now(timezone.utc).isoformat()
        final_block_reason = block_reason.strip()
        if new_category != "Другое" and not final_block_reason:
            final_block_reason = new_category
        payload: Dict[str, Any] = {
            "check_status": new_check_status,
            "resolution_status": new_resolution_status,
            "owner_name": owner_name or None,
            "owner_role": owner_role or None,
            "owner_department": dept_db(owner_department) if owner_department else None,
            "target_resolution_date": new_target_date.isoformat(),
            "severity": new_severity,
            "constraint_category": new_category,
            "root_cause": root_cause or None,
            "block_reason": final_block_reason or None,
            "comment": comment or None,
            "value_at_risk": new_value_at_risk,
            "updated_by": updated_by or None,
            "updated_role": updated_role or None,
            "last_action_at": now_iso,
            "updated_at": now_iso,
        }
        if comment.strip() or final_block_reason:
            payload["last_comment_at"] = now_iso
        if new_resolution_status == "RESOLVED":
            payload["resolved_at"] = now_iso
            payload["resolved_by"] = updated_by or None

        err = update_constraint_record(constraint_id, payload)
        if err:
            st.error(err)
        else:
            st.success("Ограничение обновлено")
            st.cache_data.clear()
            st.rerun()


def main() -> None:
    st.title("Управление ограничениями месячного плана")
    st.caption(
        "Рабочая страница для отделов: проверка ограничений, статус, владелец, "
        "срок закрытия и комментарий."
    )
    st.info(ADMISSION_INFO)

    base_df = load_constraints()
    if base_df.empty:
        st.info(
            "Ограничений пока нет. Сначала сформируйте проверки по отделам на странице 15."
        )
        return

    st.markdown("### Фильтры")
    f1, f2, f3, f4 = st.columns(4)
    f5, f6, f7, f8 = st.columns(4)
    project_sel = f1.selectbox("Проект", filter_options(base_df, "project_code"))
    month_sel = f2.selectbox("Месяц", filter_options(base_df, "month_key"))
    facility_sel = f3.selectbox("Здание / объект", filter_options(base_df, "facility_building"))
    discipline_sel = f4.selectbox("Дисциплина", filter_options(base_df, "construction_discipline"))
    department_sel = f5.selectbox(
        "Отдел",
        filter_options(base_df, "responsible_department"),
        format_func=lambda v: dept_ui(v) if v != "Все" else "Все",
    )
    check_status_sel = f6.selectbox(
        "Статус проверки",
        filter_options_ru(base_df, "check_status", CHECK_STATUS_RU),
        format_func=lambda v: ru_label(v, CHECK_STATUS_RU),
    )
    resolution_sel = f7.selectbox(
        "Статус устранения",
        filter_options_ru(base_df, "resolution_status", RESOLUTION_RU),
        format_func=lambda v: ru_label(v, RESOLUTION_RU),
    )
    overdue_only = f8.checkbox("Только просроченные")
    search_q = st.text_input("Поиск по BOQ-коду / наименованию / владельцу")

    df = apply_filters(
        base_df,
        project_sel,
        month_sel,
        facility_sel,
        discipline_sel,
        department_sel,
        check_status_sel,
        resolution_sel,
        overdue_only,
        search_q,
    )

    st.markdown("### KPI")
    render_kpis(df)

    st.markdown("### Ограничения")
    if df.empty:
        st.caption("По выбранным фильтрам ограничений нет.")
        return

    display_df = df.copy()
    if "responsible_department" in display_df.columns:
        display_df["responsible_department"] = display_df["responsible_department"].apply(dept_ui)
    if "gate_layer" in display_df.columns:
        display_df["gate_layer"] = display_df["gate_layer"].apply(
            lambda v: GATE_LAYER_RU.get(safe_str(v), safe_str(v))
        )
    if "check_status" in display_df.columns:
        display_df["check_status"] = display_df["check_status"].apply(
            lambda v: CHECK_STATUS_RU.get(norm_check_status_key(v), safe_str(v))
        )
    if "severity" in display_df.columns:
        display_df["severity"] = display_df["severity"].apply(
            lambda v: SEVERITY_RU.get(
                norm_tech_value(v, SEVERITY_OPTIONS, SEVERITY_RU, "MEDIUM"),
                safe_str(v),
            )
        )
    if "updated_by" in display_df.columns:
        display_df["updated_by"] = display_df["updated_by"].apply(display_dash)
    if "resolution_status" in display_df.columns:
        display_df["resolution_status"] = display_df["resolution_status"].apply(
            lambda v: RESOLUTION_RU.get(
                norm_tech_value(v, RESOLUTION_OPTIONS, RESOLUTION_RU, safe_str(v)),
                safe_str(v),
            )
        )
    if "value_at_risk_display" in display_df.columns:
        display_df["value_at_risk_display"] = display_df["value_at_risk_display"].apply(money_ru)
    if "target_resolution_date" in display_df.columns:
        display_df["target_resolution_date"] = display_df["target_resolution_date"].apply(
            lambda v: safe_date(v).isoformat() if safe_date(v) else ""
        )

    show_cols = [c for c in TABLE_COLUMNS if c in display_df.columns]
    table_view = display_df[show_cols].rename(columns=TABLE_COLUMNS_RU)
    st.dataframe(
        style_table(table_view),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("---")
    labels: Dict[str, str] = {}
    for _, row in df.iterrows():
        cid = safe_str(row.get("constraint_id"))
        if cid:
            labels[cid] = constraint_label(row)
    if not labels:
        st.warning("Нет записей с constraint_id для редактирования.")
        return

    selected_id = st.selectbox(
        "Выберите ограничение для редактирования",
        options=list(labels.keys()),
        format_func=lambda cid: labels.get(cid, cid),
    )
    selected_row = df[df["constraint_id"].astype(str) == selected_id].iloc[0]
    render_edit_card(selected_row)


if __name__ == "__main__":
    main()
