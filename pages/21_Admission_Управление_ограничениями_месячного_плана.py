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
TABLE_EVIDENCE = "monthly_plan_constraint_evidence"
VIEW_DASHBOARD_V2 = "monthly_plan_constraints_dashboard_v2"

NO_CONSTRAINT_CATEGORY = "Ограничений нет"

FILTER_SESSION_KEYS = {
    "project": "constraints_filter_project",
    "month": "constraints_filter_month",
    "facility": "constraints_filter_facility",
    "discipline": "constraints_filter_discipline",
    "department": "constraints_filter_department",
    "check_status": "constraints_filter_check_status",
    "resolution_status": "constraints_filter_resolution_status",
    "overdue_only": "constraints_filter_overdue_only",
    "search": "constraints_filter_search",
}

CONSTRAINT_EDIT_SELECT_KEY = "constraints_edit_select"
TABLE_SELECTED_ID_KEY = "constraints_table_selected_id"
TABLE_SELECTION_KEY = "constraints_table_select"
TABLE_HEIGHT_PX = 560

AUTO_SCHEDULE_PREFIX = "[AUTO] Срок перенесён"

RESPONSIBILITY_SIDE_OPTIONS = [
    "Не определено",
    "Наша организация / Субподрядчик",
    "Генподрядчик",
    "Заказчик",
    "Проектировщик",
    "Поставщик / Вендор",
    "Технический надзор",
]

OWNER_ROLE_PRESETS = [
    "Руководитель проекта",
    "Руководитель строительства",
    "Начальник участка",
    "Мастер",
    "Инженер ПТО",
    "Руководитель ПТО",
    "Инженер МТО",
    "Руководитель МТО",
    "Инженер ОТиТБ",
    "Инженер QA/QC",
    "Представитель заказчика",
    "Представитель генподрядчика",
    "Представитель проектировщика",
    "Представитель поставщика / вендора",
    "Коммерческий менеджер",
    "Другое",
    "Не требуется",
]

OWNER_NAME_PRESETS = [
    "Не назначен",
    "Не требуется",
    "Храпов Алексей",
    "Масимов Виктор",
    "Руководитель ПТО",
    "Руководитель МТО",
    "Начальник участка",
    "Представитель заказчика",
    "Представитель генподрядчика",
    "Другое",
]

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
    if NO_CONSTRAINT_CATEGORY not in opts:
        opts.append(NO_CONSTRAINT_CATEGORY)
    if current and current not in opts:
        opts = [current] + opts
    return opts


def init_filter_defaults(options: List[str], session_key: str, default: str = "Все") -> None:
    if session_key not in st.session_state:
        st.session_state[session_key] = default
    elif st.session_state[session_key] not in options:
        st.session_state[session_key] = default if default in options else options[0]


def combined_constraint_reason(row: pd.Series) -> str:
    block = safe_str(row.get("block_reason"))
    root = safe_str(row.get("root_cause"))
    if block and root and block != root:
        return f"{block}\n{root}"
    return block or root


def constraint_occurrence_date(row: pd.Series) -> date:
    for col in ("constraint_created_at", "created_at"):
        if col in row.index:
            parsed = safe_date(row.get(col))
            if parsed:
                return parsed
    return date.today()


def constraint_duration_days(
    occurrence: Optional[date],
    target: Optional[date],
) -> str:
    if occurrence is None:
        return "—"
    end = target if target else date.today()
    return str(max((end - occurrence).days, 0))


def infer_responsibility_side(row: pd.Series) -> str:
    """Fallback из owner_department / responsible_department без записи в БД."""
    raw = safe_str(row.get("owner_department") or row.get("responsible_department"))
    if not raw:
        return "Не определено"
    lowered = raw.lower()
    if any(x in lowered for x in ("заказчик", "customer", "client")):
        return "Заказчик"
    if any(x in lowered for x in ("генподряд", "ген подряд")):
        return "Генподрядчик"
    if any(x in lowered for x in ("проектир", "птo", "пто", "engineering")):
        return "Проектировщик"
    if any(x in lowered for x in ("мто", "постав", "vendor", "вендор")):
        return "Поставщик / Вендор"
    if any(x in lowered for x in ("надзор", "техническ")):
        return "Технический надзор"
    if raw in DEPARTMENT_RU or dept_ui(raw) in DEPARTMENT_RU.values():
        return "Наша организация / Субподрядчик"
    return "Не определено"


def owner_role_options(current: str) -> List[str]:
    opts = list(OWNER_ROLE_PRESETS)
    if current and current not in opts:
        opts = [current] + opts
    return opts


def owner_name_options(current: str) -> List[str]:
    opts = list(OWNER_NAME_PRESETS)
    if current and current not in opts:
        opts = [current] + opts
    return opts


def constraint_human_label(row: pd.Series) -> str:
    status_key = norm_check_status_key(row.get("check_status"))
    status_ui = CHECK_STATUS_RU.get(status_key, status_key)
    dept = dept_ui(row.get("responsible_department"))
    boq = safe_str(row.get("boq_code")) or "—"
    name = safe_str(row.get("boq_name")) or "—"
    check = safe_str(row.get("check_name")) or "—"
    return f"{boq} | {name} | {dept} | {check} | {status_ui}"


def resolution_is_closed(resolution_status: str) -> bool:
    key = norm_tech_value(resolution_status, RESOLUTION_OPTIONS, RESOLUTION_RU, "OPEN")
    return key in ("RESOLVED", "CANCELLED")


def overdue_days_for_card(target: Optional[date], resolution_status: str) -> int:
    if resolution_is_closed(resolution_status):
        return 0
    if target is None:
        return 0
    return max((date.today() - target).days, 0)


def count_schedule_reschedules(comment: str) -> int:
    if not comment:
        return 0
    return sum(1 for line in comment.splitlines() if line.strip().startswith(AUTO_SCHEDULE_PREFIX))


def parse_schedule_history(comment: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    if not comment:
        return items
    for line in comment.splitlines():
        text = line.strip()
        if not text.startswith(AUTO_SCHEDULE_PREFIX):
            continue
        body = text[len(AUTO_SCHEDULE_PREFIX) :].strip().lstrip(":").strip()
        note = ""
        if "не выдержан" in body.lower():
            note = "не выдержан"
        arrow = "→"
        if arrow in body:
            left, right = body.split(arrow, 1)
            old_part = left.strip().split(",")[0].strip()
            new_part = right.split(",")[0].strip()
            items.append({"old": old_part, "new": new_part, "note": note})
    return items


def is_owner_optional(check_status: str, category: str) -> bool:
    if norm_check_status_key(check_status) == "PASS":
        return True
    return category == NO_CONSTRAINT_CATEGORY


def resolve_selected_constraint_id(df: pd.DataFrame, label_keys: List[str]) -> str:
    """Приоритет: выделение в таблице → ручной dropdown → последний выбор → первая строка."""
    selection_state = st.session_state.get(TABLE_SELECTION_KEY, {})
    selected_rows = selection_state.get("selection", {}).get("rows", [])
    if selected_rows:
        row_idx = int(selected_rows[0])
        if 0 <= row_idx < len(df):
            picked = safe_str(df.iloc[row_idx].get("constraint_id"))
            if picked in label_keys:
                st.session_state[TABLE_SELECTED_ID_KEY] = picked
                return picked

    manual = st.session_state.get(CONSTRAINT_EDIT_SELECT_KEY)
    if manual and manual in label_keys:
        return str(manual)

    stored = st.session_state.get(TABLE_SELECTED_ID_KEY)
    if stored and stored in label_keys:
        return str(stored)

    return label_keys[0]


def apply_no_constraint_form_preset(constraint_id: str) -> None:
    st.session_state[f"form_preset_{constraint_id}"] = {
        "check_status": "PASS",
        "resolution_status": "RESOLVED",
        "owner_name": "Не требуется",
        "owner_role": "Не требуется",
        "value_at_risk": 0.0,
        "category": NO_CONSTRAINT_CATEGORY,
    }
    for widget_key in (
        f"check_status_{constraint_id}",
        f"resolution_{constraint_id}",
        f"severity_{constraint_id}",
        f"owner_name_sel_{constraint_id}",
        f"owner_role_sel_{constraint_id}",
        f"owner_name_custom_{constraint_id}",
        f"owner_role_custom_{constraint_id}",
        f"value_at_risk_{constraint_id}",
        f"category_{constraint_id}",
    ):
        st.session_state.pop(widget_key, None)


def resolve_owner_name(choice: str, custom: str) -> str:
    if choice == "Другое":
        return custom.strip()
    if choice == "Не назначен":
        return ""
    return choice


def append_schedule_change_comment(
    existing_comment: str,
    old_target: Optional[date],
    new_target: date,
    saver_name: str,
) -> str:
    old_s = old_target.isoformat() if old_target else "—"
    new_s = new_target.isoformat()
    not_met = ""
    if old_target and old_target < date.today() and new_target > old_target:
        not_met = " (старый срок не выдержан)"
    line = (
        f"{AUTO_SCHEDULE_PREFIX}: {old_s} → {new_s}{not_met}, "
        f"дата изменения: {date.today().isoformat()}, кем: {saver_name}"
    )
    base = (existing_comment or "").strip()
    return f"{base}\n{line}".strip() if base else line


def audit_last_updated_at(row: pd.Series) -> Any:
    for col in ("updated_at", "last_action_at", "last_updated_at"):
        if col in row.index and not pd.isna(row.get(col)):
            return row.get(col)
    return None


def audit_last_updated_by(row: pd.Series) -> str:
    for col in ("updated_by", "last_updated_by"):
        if col in row.index:
            text = safe_str(row.get(col))
            if text:
                return text
    return ""


@st.cache_data(ttl=120)
def load_constraint_evidence(constraint_id: str) -> pd.DataFrame:
    if not constraint_id:
        return pd.DataFrame()
    try:
        resp = (
            supabase.table(TABLE_EVIDENCE)
            .select("*")
            .eq("constraint_id", constraint_id)
            .order("uploaded_at", desc=True)
            .limit(100)
            .execute()
        )
        return pd.DataFrame(resp.data or [])
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def insert_evidence_metadata(
    constraint_id: str,
    file_name: str,
    uploaded_by: str,
    description: str = "",
) -> tuple[Optional[str], Optional[str]]:
    """
    Сохраняет метаданные в monthly_plan_constraint_evidence (без файла в Storage).
  Возвращает (error, evidence_id).
    """
    client = get_write_client()
    if client is None:
        return "SUPABASE_SECRET_KEY не задан в .env — сохранение доказательства недоступно.", None
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    evidence_type = "OTHER"
    if ext in ("png", "jpg", "jpeg"):
        evidence_type = "PHOTO"
    payload: Dict[str, Any] = {
        "constraint_id": constraint_id,
        "file_name": file_name,
        "uploaded_by": uploaded_by or None,
        "description": description or None,
        "evidence_type": evidence_type,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        resp = client.table(TABLE_EVIDENCE).insert(payload).execute()
        rows = resp.data or []
        evidence_id = str(rows[0].get("evidence_id") or "") if rows else ""
        return None, evidence_id or None
    except Exception as exc:  # noqa: BLE001
        return str(exc), None


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


def render_kpi_top_bar(df: pd.DataFrame) -> None:
    """Компактная сводка без замены детальных KPI."""
    total = len(df)
    open_cnt = 0
    if "resolution_status" in df.columns:
        open_cnt = len(
            df[df["resolution_status"].astype(str).isin(["OPEN", "IN_PROGRESS"])]
        )
    overdue_cnt = int(df["is_overdue"].astype(bool).sum()) if "is_overdue" in df.columns else 0
    hold_cnt = len(df[df["check_status"].astype(str) == "HOLD"]) if "check_status" in df.columns else 0
    fail_cnt = len(df[df["check_status"].astype(str) == "FAIL"]) if "check_status" in df.columns else 0
    risk_sum = kpi_risk_sum(df)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Всего ограничений", total)
    c2.metric("Открыто", open_cnt)
    c3.metric("Просрочено", overdue_cnt)
    c4.metric("HOLD / FAIL", hold_cnt + fail_cnt)
    c5.metric("Стоимость под риском", money_ru(risk_sum))


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
    info3.markdown(f"**Дней открыто:** {int(safe_num(row.get('days_open')))}")

    info4, info5, info6 = st.columns(3)
    target = safe_date(row.get("target_resolution_date"))
    info4.markdown(f"**Просрочка по сроку:** {int(safe_num(row.get('days_overdue')))} дн.")
    if "evidence_count" in row.index and not pd.isna(row.get("evidence_count")):
        info5.markdown(f"**Доказательств:** {int(safe_num(row.get('evidence_count')))}")
    promised = safe_date(row.get("effective_promised_date"))
    if promised:
        info5.markdown(f"**Дата обещания:** {promised.isoformat()}")
    if "days_since_promise" in row.index and safe_num(row.get("days_since_promise")) > 0:
        info6.markdown(f"**Просрочка обещания:** {int(safe_num(row.get('days_since_promise')))} дн.")

    st.markdown("---")
    constraint_id = safe_str(row.get("constraint_id"))
    if not constraint_id:
        st.error("У записи нет constraint_id — сохранение недоступно.")
        return

    preset_key = f"form_preset_{constraint_id}"
    preset = st.session_state.pop(preset_key, None) or {}

    current_check = norm_check_status_key(preset.get("check_status") or row.get("check_status"))
    current_resolution = norm_tech_value(
        preset.get("resolution_status") or row.get("resolution_status"),
        RESOLUTION_OPTIONS,
        RESOLUTION_RU,
        "OPEN",
    )
    current_severity = norm_tech_value(
        row.get("severity"), SEVERITY_OPTIONS, SEVERITY_RU, "MEDIUM"
    )
    dept = safe_str(row.get("responsible_department"))
    current_category = safe_str(preset.get("category") or row.get("constraint_category")) or "Другое"
    category_opts = category_options_for_department(dept, current_category)
    if current_category not in category_opts:
        current_category = "Другое"

    preset_owner = safe_str(preset.get("owner_name"))
    preset_role = safe_str(preset.get("owner_role"))
    preset_risk = preset.get("value_at_risk")

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

    st.markdown("**Владелец и сторона ответственности**")
    owner_dept_raw = safe_str(row.get("owner_department") or row.get("responsible_department"))
    resp_side_key = f"resp_side_{constraint_id}"
    if resp_side_key not in st.session_state:
        st.session_state[resp_side_key] = infer_responsibility_side(row)

    o1, o2, o3 = st.columns(3)
    side_index = (
        RESPONSIBILITY_SIDE_OPTIONS.index(st.session_state[resp_side_key])
        if st.session_state[resp_side_key] in RESPONSIBILITY_SIDE_OPTIONS
        else 0
    )
    o1.selectbox(
        "Сторона ответственности",
        RESPONSIBILITY_SIDE_OPTIONS,
        index=side_index,
        key=resp_side_key,
    )

    current_owner_name = preset_owner or safe_str(row.get("owner_name"))
    name_opts = owner_name_options(current_owner_name)
    name_index = name_opts.index(current_owner_name) if current_owner_name in name_opts else 0
    owner_name_choice = o2.selectbox(
        "Владелец ограничения",
        name_opts,
        index=name_index,
        key=f"owner_name_sel_{constraint_id}",
    )
    owner_name_custom_default = (
        current_owner_name
        if current_owner_name and current_owner_name not in OWNER_NAME_PRESETS
        else ""
    )
    if owner_name_choice == "Другое":
        owner_name = st.text_input(
            "Укажите владельца",
            value=owner_name_custom_default,
            key=f"owner_name_custom_{constraint_id}",
        )
    else:
        owner_name = resolve_owner_name(owner_name_choice, "")

    current_owner_role = preset_role or safe_str(row.get("owner_role"))
    role_opts = owner_role_options(current_owner_role)
    role_index = role_opts.index(current_owner_role) if current_owner_role in role_opts else 0
    owner_role_choice = o3.selectbox(
        "Роль владельца",
        role_opts,
        index=role_index,
        key=f"owner_role_sel_{constraint_id}",
    )
    if owner_role_choice == "Другое":
        owner_role = st.text_input(
            "Укажите роль владельца",
            value=current_owner_role if current_owner_role not in OWNER_ROLE_PRESETS else "",
            key=f"owner_role_custom_{constraint_id}",
        )
    else:
        owner_role = owner_role_choice

    owner_department = (
        dept_ui(owner_dept_raw) if owner_dept_raw in DEPARTMENT_RU else owner_dept_raw
    )

    st.markdown("**Контроль сроков**")
    d1, d2, d3, d4 = st.columns(4)
    new_occurrence_date = d1.date_input(
        "Дата возникновения ограничения",
        value=constraint_occurrence_date(row),
        key=f"occurrence_{constraint_id}",
    )
    target_default = target or date.today()
    new_target_date = d2.date_input(
        "Текущая требуемая дата устранения",
        value=target_default,
        key=f"target_{constraint_id}",
    )
    overdue_display = overdue_days_for_card(safe_date(new_target_date), new_resolution_status)
    d3.number_input(
        "Просрочка, дней",
        value=int(overdue_display),
        disabled=True,
        key=f"overdue_{constraint_id}",
    )
    record_comment = safe_str(row.get("comment"))
    d4.number_input(
        "Количество переносов срока",
        value=count_schedule_reschedules(record_comment),
        disabled=True,
        key=f"reschedule_cnt_{constraint_id}",
    )

    history_items = parse_schedule_history(record_comment)
    if history_items:
        st.caption("История сроков / переносов")
        for item in history_items:
            suffix = f" — {item['note']}" if item.get("note") else ""
            st.text(f"{item.get('old', '—')} → {item.get('new', '—')}{suffix}")

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
    if new_category == NO_CONSTRAINT_CATEGORY:
        if st.button(
            "Заполнить форму рекомендуемыми значениями (PASS / без ограничений)",
            key=f"preset_pass_{constraint_id}",
        ):
            apply_no_constraint_form_preset(constraint_id)
            st.rerun()

    if is_owner_optional(new_check_status, new_category):
        st.caption(
            "Для PASS / «Ограничений нет» владелец ограничения и роль не обязательны."
        )

    reason_combined = st.text_area(
        "Причина ограничения",
        value=combined_constraint_reason(row),
        key=f"reason_{constraint_id}",
        help="Сохраняется в поля «Причина блокировки» и «Корневая причина» в базе.",
    )
    comment = st.text_area("Комментарий", value=safe_str(row.get("comment")))

    default_risk = float(preset_risk) if preset_risk is not None else row_risk_value(row)
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

    st.markdown("**Аудит последнего изменения (только просмотр)**")
    audit1, audit2 = st.columns(2)
    audit1.text_input(
        "Последнее обновление (last_updated_at)",
        value=format_datetime_ru(audit_last_updated_at(row)),
        disabled=True,
    )
    audit2.text_input(
        "Кто обновил (last_updated_by)",
        value=audit_last_updated_by(row) or "—",
        disabled=True,
    )

    saver_name = st.text_input(
        "Кто сохраняет сейчас",
        value=st.session_state.get("constraints_saver_name", "Пользователь Streamlit"),
        key=f"saver_{constraint_id}",
    )
    st.session_state["constraints_saver_name"] = saver_name

    st.markdown("**Доказательства действий**")
    st.info(
        "Постоянное сохранение файлов будет подключено через Supabase Storage / "
        f"{TABLE_EVIDENCE}."
    )

    if st.button("Сохранить изменение", type="primary", key=f"save_{constraint_id}"):
        now_iso = datetime.now(timezone.utc).isoformat()
        reason_text = reason_combined.strip()
        final_block_reason = reason_text
        if new_category != "Другое" and new_category != NO_CONSTRAINT_CATEGORY and not final_block_reason:
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
            "root_cause": reason_text or None,
            "block_reason": final_block_reason or None,
            "comment": None,
            "value_at_risk": new_value_at_risk,
            "updated_by": saver_name or None,
            "last_action_at": now_iso,
            "updated_at": now_iso,
        }
        if "constraint_created_at" in row.index:
            occurrence_iso = datetime.combine(
                new_occurrence_date, datetime.min.time(), tzinfo=timezone.utc
            ).isoformat()
            payload["constraint_created_at"] = occurrence_iso

        final_comment = comment.strip()
        old_target = safe_date(row.get("target_resolution_date"))
        if old_target != new_target_date:
            final_comment = append_schedule_change_comment(
                final_comment, old_target, new_target_date, saver_name
            )
        payload["comment"] = final_comment or None

        if final_comment or final_block_reason:
            payload["last_comment_at"] = now_iso
        if new_resolution_status == "RESOLVED":
            payload["resolved_at"] = now_iso
            payload["resolved_by"] = saver_name or None

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
    project_opts = filter_options(base_df, "project_code")
    month_opts = filter_options(base_df, "month_key")
    facility_opts = filter_options(base_df, "facility_building")
    discipline_opts = filter_options(base_df, "construction_discipline")
    department_opts = filter_options(base_df, "responsible_department")
    check_opts = filter_options_ru(base_df, "check_status", CHECK_STATUS_RU)
    resolution_opts = filter_options_ru(base_df, "resolution_status", RESOLUTION_RU)

    init_filter_defaults(project_opts, FILTER_SESSION_KEYS["project"])
    init_filter_defaults(month_opts, FILTER_SESSION_KEYS["month"])
    init_filter_defaults(facility_opts, FILTER_SESSION_KEYS["facility"])
    init_filter_defaults(discipline_opts, FILTER_SESSION_KEYS["discipline"])
    init_filter_defaults(department_opts, FILTER_SESSION_KEYS["department"])
    init_filter_defaults(check_opts, FILTER_SESSION_KEYS["check_status"])
    init_filter_defaults(resolution_opts, FILTER_SESSION_KEYS["resolution_status"])
    if FILTER_SESSION_KEYS["overdue_only"] not in st.session_state:
        st.session_state[FILTER_SESSION_KEYS["overdue_only"]] = False
    if FILTER_SESSION_KEYS["search"] not in st.session_state:
        st.session_state[FILTER_SESSION_KEYS["search"]] = ""

    project_sel = f1.selectbox("Проект", project_opts, key=FILTER_SESSION_KEYS["project"])
    month_sel = f2.selectbox("Месяц", month_opts, key=FILTER_SESSION_KEYS["month"])
    facility_sel = f3.selectbox("Здание / объект", facility_opts, key=FILTER_SESSION_KEYS["facility"])
    discipline_sel = f4.selectbox(
        "Дисциплина", discipline_opts, key=FILTER_SESSION_KEYS["discipline"]
    )
    department_sel = f5.selectbox(
        "Отдел",
        department_opts,
        format_func=lambda v: dept_ui(v) if v != "Все" else "Все",
        key=FILTER_SESSION_KEYS["department"],
    )
    check_status_sel = f6.selectbox(
        "Статус проверки",
        check_opts,
        format_func=lambda v: ru_label(v, CHECK_STATUS_RU),
        key=FILTER_SESSION_KEYS["check_status"],
    )
    resolution_sel = f7.selectbox(
        "Статус устранения",
        resolution_opts,
        format_func=lambda v: ru_label(v, RESOLUTION_RU),
        key=FILTER_SESSION_KEYS["resolution_status"],
    )
    overdue_only = f8.checkbox(
        "Только просроченные", key=FILTER_SESSION_KEYS["overdue_only"]
    )
    search_q = st.text_input(
        "Поиск по BOQ-коду / наименованию / владельцу",
        key=FILTER_SESSION_KEYS["search"],
    )

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

    st.markdown("### Сводка")
    render_kpi_top_bar(df)
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
    st.caption("Выберите строку в таблице — карточка ниже откроется автоматически.")
    st.dataframe(
        style_table(table_view),
        use_container_width=True,
        hide_index=True,
        height=TABLE_HEIGHT_PX,
        on_select="rerun",
        selection_mode="single-row",
        key=TABLE_SELECTION_KEY,
    )

    labels: Dict[str, str] = {}
    for _, row in df.iterrows():
        cid = safe_str(row.get("constraint_id"))
        if cid:
            labels[cid] = constraint_human_label(row)
    if not labels:
        st.warning("Нет записей с constraint_id для редактирования.")
        return

    label_keys = list(labels.keys())

    with st.expander("Ручной выбор ограничения", expanded=False):
        st.caption(
            "Используется, если в таблице нет выделенной строки. "
            "При выделении строки в таблице приоритет у таблицы."
        )
        fallback_id = st.session_state.get(TABLE_SELECTED_ID_KEY) or label_keys[0]
        manual_index = label_keys.index(fallback_id) if fallback_id in label_keys else 0
        st.selectbox(
            "Ограничение (fallback)",
            options=label_keys,
            index=manual_index,
            format_func=lambda cid: labels.get(cid, cid),
            key=CONSTRAINT_EDIT_SELECT_KEY,
        )

    selected_id = resolve_selected_constraint_id(df, label_keys)
    selected_row = df[df["constraint_id"].astype(str) == selected_id].iloc[0]

    st.markdown("---")
    st.markdown(f"**Выбрано:** {constraint_human_label(selected_row)}")
    render_edit_card(selected_row)


if __name__ == "__main__":
    main()
