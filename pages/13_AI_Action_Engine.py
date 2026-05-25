# ============================================================
# ИИ — Очередь управленческих решений (War Room)
# Источник: public.plan_corrective_actions_view (Supabase)
# ============================================================

import html as html_lib
import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client

from services.supabase_client import supabase

load_dotenv()


def esc(value) -> str:
    if value is None:
        return ""
    return html_lib.escape(str(value))


TABLE_VIEW = "plan_corrective_actions_view"
TABLE_ACTIONS = "plan_corrective_actions"

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

SEVERITY_RU = {
    "CRITICAL": "Критично",
    "HIGH": "Высокий риск",
    "MEDIUM": "Средний риск",
    "LOW": "Низкий риск",
}

ACTION_STATUS_RU = {
    "PENDING": "Ожидает решения",
    "APPROVED": "Одобрено",
    "REJECTED": "Отклонено",
    "APPLIED": "Применено",
    "ROLLED_BACK": "Откат",
}

ACTION_TYPE_RU = {
    "SCOPE_ADD": "Добавить денежный фронт",
    "SCOPE_REMOVE": "Убрать лишний объём",
    "SCOPE_SWAP": "Заменить фронт",
    "ECONOMIC_BLOCK": "Проверить / заблокировать убыточный фронт",
    "PRODUCTIVITY_SCENARIO_CHANGE": "Изменить сценарий производительности",
    "PLAN_REBALANCE": "Перебалансировать месяц",
    "COMPLETE_TO_CLOSE": "Доделать до закрытия",
    "LOSS_ACCEPTED_TO_UNLOCK_CASH": "Принять убыток ради открытия денег",
    "CREW_REDUCE": "Сократить звено",
    "CREW_REALLOCATE": "Перераспределить людей",
}

SEVERITY_ALERT = {
    "CRITICAL": ("🔴", "КРИТИЧНО"),
    "HIGH": ("🟠", "РИСК"),
    "MEDIUM": ("🟡", "ВНИМАНИЕ"),
    "LOW": ("🟢", "НОРМА"),
}

ALERT_CSS_CLASS = {
    "CRITICAL": "war-alert-critical",
    "HIGH": "war-alert-high",
    "MEDIUM": "war-alert-medium",
    "LOW": "war-alert-low",
}

st.set_page_config(layout="wide")

st.title("ИИ — Очередь управленческих решений")
st.caption(
    "War Room / Command Center — за 5 секунд: что плохо, сколько денег, что делать, нужно ли решение."
)

st.markdown(
    """
    <style>
    .war-card { background: #fafafa; border: 1px solid #e4e4e7; border-radius: 8px;
        padding: 0.5rem 0.65rem 0.55rem 0.65rem; margin-bottom: 0.55rem; }
    .war-alert { font-size: 0.92rem; font-weight: 600; line-height: 1.35;
        padding: 0.42rem 0.6rem; margin-bottom: 0.45rem; border-radius: 4px; color: #18181b; }
    .war-alert-critical { background: #fef2f2; border-left: 4px solid #b91c1c; }
    .war-alert-high { background: #fff7ed; border-left: 4px solid #c2410c; }
    .war-alert-medium { background: #fefce8; border-left: 4px solid #a16207; }
    .war-alert-low { background: #f0fdf4; border-left: 4px solid #15803d; }
    .war-meta { font-size: 0.76rem; color: #71717A; line-height: 1.35; margin: 0.1rem 0 0.25rem 0; }
    .war-label { font-size: 0.8rem; font-weight: 600; color: #52525b; margin: 0.3rem 0 0.12rem 0; }
    .war-text { font-size: 0.86rem; color: #27272a; line-height: 1.42; margin: 0 0 0.3rem 0; }
    .war-do-box {
        background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #d97706;
        padding: 0.5rem 0.7rem; margin: 0.15rem 0 0.4rem 0;
        font-size: 0.92rem; font-weight: 600; color: #1c1917; line-height: 1.42;
    }
    .war-complete-box {
        background: #fff1f2; border: 1px solid #fecdd3; border-left: 4px solid #e11d48;
        padding: 0.5rem 0.65rem; margin: 0.35rem 0 0.35rem 0;
        font-size: 0.84rem; color: #881337; line-height: 1.42;
    }
    .war-decision-label { font-size: 0.8rem; font-weight: 600; color: #3f3f46;
        margin: 0.35rem 0 0.2rem 0; }
    div[data-testid="stMetric"] { padding-top: 0.1rem; padding-bottom: 0.1rem; }
    div[data-testid="stMetricLabel"] { font-size: 0.76rem !important; }
    div[data-testid="stMetricValue"] { font-size: 1.02rem !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_supabase_write_client() -> Client | None:
    """Запись в plan_corrective_actions — нужен service key (RLS блокирует publishable key)."""
    url = os.getenv("SUPABASE_URL")
    secret = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not secret:
        return None
    return create_client(url, secret)


@st.cache_data(ttl=300)
def load_actions(limit: int = 5000) -> pd.DataFrame:
    response = supabase.table(TABLE_VIEW).select("*").limit(limit).execute()
    return pd.DataFrame(response.data or [])


def money(value) -> str:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        return f"{float(value):,.0f} ₽".replace(",", " ")
    except (TypeError, ValueError):
        return "—"


def safe_text(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def map_label(value: str, mapping: dict[str, str]) -> str:
    return mapping.get(str(value).strip(), str(value))


def raw_filter_values(df: pd.DataFrame, col: str) -> list[str]:
    if df.empty or col not in df.columns:
        return []
    vals = df[col].dropna().astype(str).str.strip()
    return sorted(vals[vals != ""].unique().tolist())


def filter_selectbox(
    label: str,
    df: pd.DataFrame,
    col: str,
    mapping: dict[str, str] | None,
    key: str,
) -> str:
    raw_vals = raw_filter_values(df, col)
    options: list[tuple[str, str]] = [("Все", "Все")]
    for raw in raw_vals:
        display = map_label(raw, mapping) if mapping else raw
        options.append((display, raw))

    labels = [item[0] for item in options]
    label_to_value = {item[0]: item[1] for item in options}
    selected = st.selectbox(label, labels, key=key)
    return label_to_value[selected]


def plain_filter_selectbox(label: str, df: pd.DataFrame, col: str, key: str) -> str:
    opts = ["Все"] + raw_filter_values(df, col)
    return st.selectbox(label, opts, key=key)


def apply_filters(
    df: pd.DataFrame,
    project: str,
    month: str,
    crew: str,
    severity: str,
    action_type: str,
    action_status: str,
) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if project != "Все" and "project_code" in out.columns:
        out = out[out["project_code"].astype(str) == project]
    if month != "Все" and "month_key" in out.columns:
        out = out[out["month_key"].astype(str) == month]
    if crew != "Все" and "crew_code" in out.columns:
        out = out[out["crew_code"].astype(str) == crew]
    if severity != "Все" and "severity" in out.columns:
        out = out[out["severity"].astype(str) == severity]
    if action_type != "Все" and "action_type" in out.columns:
        out = out[out["action_type"].astype(str) == action_type]
    if action_status != "Все" and "action_status" in out.columns:
        out = out[out["action_status"].astype(str) == action_status]
    return out


def sort_actions(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["_severity_ord"] = out["severity"].map(SEVERITY_ORDER).fillna(99)
    sort_cols = ["_severity_ord"]
    if "action_priority_sort" in out.columns:
        sort_cols.append("action_priority_sort")
    if "month_key" in out.columns:
        sort_cols.append("month_key")
    if "crew_code" in out.columns:
        sort_cols.append("crew_code")
    out = out.sort_values(
        [c for c in sort_cols if c in out.columns],
        ascending=[True] * len(sort_cols),
    )
    return out.drop(columns=["_severity_ord"], errors="ignore")


def action_type_label(row: pd.Series) -> str:
    raw = safe_text(row.get("action_type"))
    if raw:
        return ACTION_TYPE_RU.get(raw, safe_text(row.get("action_type_ru")) or raw)
    return safe_text(row.get("action_type_ru")) or "—"


def short_action_label(row: pd.Series) -> str:
    text = action_type_label(row)
    if len(text) > 42:
        return text[:39] + "…"
    return text


def money_compact(value) -> str:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        num = float(value)
        formatted = f"{abs(num):,.0f}".replace(",", " ")
        sign = "−" if num < 0 else ""
        return f"{sign}{formatted} ₽"
    except (TypeError, ValueError):
        return "—"


def hours_reserve_fmt(value) -> str:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return "—"
        num = float(value)
        formatted = f"{abs(num):,.0f}".replace(",", " ")
        if num > 0:
            return f"+{formatted} ч"
        if num < 0:
            return f"−{formatted} ч"
        return "0 ч"
    except (TypeError, ValueError):
        return "—"


def alert_bar_line(row: pd.Series) -> str:
    level = str(row.get("severity") or "").upper()
    emoji, label = SEVERITY_ALERT.get(level, ("⚪", "СТАТУС"))
    crew = row.get("crew_code") or "—"
    action = short_action_label(row)
    effect = money_compact(row.get("current_margin"))
    return f"{emoji} {label} | {crew} | {action} | {effect}"


def render_alert_bar(row: pd.Series) -> None:
    level = str(row.get("severity") or "").upper()
    css_class = ALERT_CSS_CLASS.get(level, "war-alert-medium")
    line = esc(alert_bar_line(row))
    st.markdown(
        f'<div class="war-alert {css_class}">{line}</div>',
        unsafe_allow_html=True,
    )


def is_truthy(value) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "да"}


def needs_completion_block(row: pd.Series) -> bool:
    action_type = str(row.get("action_type") or "").upper()
    return is_truthy(row.get("is_completion_required")) or action_type == "COMPLETE_TO_CLOSE"


def bool_label(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    return "Да" if is_truthy(value) else "Нет"


def update_status(action_id: str, payload: dict):
    write_client = get_supabase_write_client()
    if write_client is None:
        raise RuntimeError(
            "SUPABASE_SECRET_KEY не задан в .env — запись в plan_corrective_actions недоступна."
        )
    return (
        write_client.table(TABLE_ACTIONS)
        .update(payload)
        .eq("action_id", action_id)
        .execute()
    )


def approve_action(action_id: str):
    return update_status(
        action_id,
        {
            "action_status": "APPROVED",
            "approved_by": "streamlit_user",
            "approved_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def reject_action(action_id: str):
    return update_status(
        action_id,
        {
            "action_status": "REJECTED",
            "rejected_reason": "Отклонено через интерфейс",
        },
    )


def render_decision_controls(row: pd.Series) -> None:
    action_id = safe_text(row.get("action_id"))
    status_raw = safe_text(row.get("action_status")) or ""

    if status_raw == "APPROVED":
        st.success("Решение уже принято: Одобрено")
        return
    if status_raw == "REJECTED":
        st.warning("Решение уже принято: Отклонено")
        return

    if not action_id:
        st.caption("Нет идентификатора решения — обновление недоступно.")
        return

    st.caption(f"action_id: {action_id}")

    if get_supabase_write_client() is None:
        st.error(
            "В .env нет SUPABASE_SECRET_KEY — статус решения не сохранится. "
            "Добавьте service key (как для sync-скриптов)."
        )
        return

    _, foot_btn1, foot_btn2 = st.columns([4, 1, 1])
    with foot_btn1:
        if st.button("Одобрить", key=f"approve_{action_id}"):
            try:
                response = approve_action(action_id)
                st.write("DEBUG update response:", response)
                load_actions.clear()
                st.success("Решение одобрено")
                st.rerun()
            except Exception as e:
                st.error("Не удалось обновить статус решения")
                st.exception(e)
    with foot_btn2:
        if st.button("Отклонить", key=f"reject_{action_id}"):
            try:
                response = reject_action(action_id)
                st.write("DEBUG update response:", response)
                load_actions.clear()
                st.warning("Решение отклонено")
                st.rerun()
            except Exception as e:
                st.error("Не удалось обновить статус решения")
                st.exception(e)


def problem_codes(row: pd.Series) -> str | None:
    parts = []
    for col in ("affected_boq_code", "recommended_boq_code"):
        text = safe_text(row.get(col))
        if text:
            parts.append(text)
    if not parts:
        return None
    return ", ".join(dict.fromkeys(parts))


def render_card(row: pd.Series) -> None:
    st.markdown('<div class="war-card">', unsafe_allow_html=True)
    render_alert_bar(row)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Финансовый результат плана", money_compact(row.get("current_margin")))
    m2.metric("Объём покрытия к добавлению", money_compact(row.get("recommended_ev_add")))
    m3.metric("Результат после решения", money_compact(row.get("expected_margin")))
    m4.metric("Резерв / дефицит часов", hours_reserve_fmt(row.get("capacity_delta_hours")))

    st.markdown('<p class="war-label">Что произошло?</p>', unsafe_allow_html=True)
    summary = safe_text(row.get("executive_summary"))
    if summary:
        st.markdown(f'<p class="war-text">{esc(summary)}</p>', unsafe_allow_html=True)
    else:
        st.markdown('<p class="war-meta">Нет данных</p>', unsafe_allow_html=True)

    st.markdown('<p class="war-label">Что делать?</p>', unsafe_allow_html=True)
    action = safe_text(row.get("management_action"))
    if action:
        st.markdown(f'<div class="war-do-box">{esc(action)}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<p class="war-meta">Нет данных</p>', unsafe_allow_html=True)

    if needs_completion_block(row):
        complete_html = (
            "<div class='war-complete-box'>"
            "<strong>⚠ Проверить завершение системы</strong><br>"
            "Убыточный фронт нельзя автоматически убрать — возможно, его нужно доделать "
            "для сдачи, КС или открытия денег.<br>"
            f"Причина: {esc(safe_text(row.get('completion_reason')) or '—')} · "
            f"Приёмка: {bool_label(row.get('unlocks_acceptance'))} · "
            f"Деньги: {bool_label(row.get('unlocks_cash'))} · "
            f"Эффект: {money_compact(row.get('net_cash_effect'))}"
            "</div>"
        )
        st.markdown(complete_html, unsafe_allow_html=True)

    detail = safe_text(row.get("detailed_explanation"))
    if detail:
        with st.expander("Подробное объяснение", expanded=False):
            st.text(detail)

    st.markdown('<p class="war-decision-label">Управленческое решение</p>', unsafe_allow_html=True)
    meta_parts = []
    if safe_text(row.get("month_key")):
        meta_parts.append(f"Месяц: {esc(row['month_key'])}")
    if safe_text(row.get("project_code")):
        meta_parts.append(f"Проект: {esc(row['project_code'])}")
    status_raw = safe_text(row.get("action_status"))
    if status_raw:
        meta_parts.append(esc(map_label(status_raw, ACTION_STATUS_RU)))
    decision = safe_text(row.get("action_decision_label"))
    if decision:
        meta_parts.append(esc(decision))
    codes = problem_codes(row)
    if codes:
        meta_parts.append(f"Коды: {esc(codes)}")
    if meta_parts:
        st.markdown(
            f'<p class="war-meta">{" · ".join(meta_parts)}</p>',
            unsafe_allow_html=True,
        )

    render_decision_controls(row)

    st.markdown("</div>", unsafe_allow_html=True)


def kpi_negative_margin_sum(df: pd.DataFrame) -> float:
    if df.empty or "current_margin" not in df.columns:
        return 0.0
    margins = pd.to_numeric(df["current_margin"], errors="coerce")
    negative = margins[margins < 0]
    return float(negative.sum()) if not negative.empty else 0.0


def kpi_sum(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


try:
    data = load_actions()
except Exception as e:
    st.error(f"Не удалось загрузить очередь решений: {e}")
    st.stop()

if data.empty:
    st.info("Нет данных в очереди управленческих решений.")
    st.stop()

# --- фильтры ---
f1, f2, f3 = st.columns(3)
f4, f5, f6 = st.columns(3)

with f1:
    project_sel = plain_filter_selectbox("Проект", data, "project_code", "filter_project")
with f2:
    month_sel = plain_filter_selectbox("Месяц", data, "month_key", "filter_month")
with f3:
    crew_sel = plain_filter_selectbox("Звено", data, "crew_code", "filter_crew")
with f4:
    severity_sel = filter_selectbox(
        "Уровень риска", data, "severity", SEVERITY_RU, "filter_severity"
    )
with f5:
    action_type_sel = filter_selectbox(
        "Тип действия", data, "action_type", ACTION_TYPE_RU, "filter_action_type"
    )
with f6:
    action_status_sel = filter_selectbox(
        "Статус решения", data, "action_status", ACTION_STATUS_RU, "filter_action_status"
    )

filtered = apply_filters(
    data,
    project_sel,
    month_sel,
    crew_sel,
    severity_sel,
    action_type_sel,
    action_status_sel,
)
filtered = sort_actions(filtered)

# --- KPI ---
st.markdown("---")
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Всего решений", len(filtered))

critical_cnt = 0
pending_cnt = 0
if not filtered.empty:
    if "severity" in filtered.columns:
        critical_cnt = int((filtered["severity"].astype(str) == "CRITICAL").sum())
    if "action_status" in filtered.columns:
        pending_cnt = int((filtered["action_status"].astype(str) == "PENDING").sum())

k2.metric("Критические", critical_cnt)
k3.metric("Ожидают решения", pending_cnt)
k4.metric("Суммарный убыток", money(kpi_negative_margin_sum(filtered)))
k5.metric("Объём покрытия к добавлению", money(kpi_sum(filtered, "recommended_ev_add")))
k6.metric("Улучшение результата", money(kpi_sum(filtered, "margin_delta")))

st.markdown("---")

if filtered.empty:
    st.info("Нет решений по выбранным фильтрам.")
    st.stop()

for _, row in filtered.iterrows():
    render_card(row)

with st.expander("Показать исходные данные", expanded=False):
    st.dataframe(filtered, use_container_width=True, hide_index=True)
