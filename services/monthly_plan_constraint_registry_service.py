"""
Реестр ограничений допуска месячного плана — Python read model + resolve/update RPC.

Источник чтения: monthly_plan_constraints_dashboard_v2
Обогащение (bulk): monthly_plan_lines_v2
Закрытие: RPC resolve_monthly_plan_constraint
Обновление (R2): RPC update_monthly_plan_constraint

Не пишет в passport. Не меняет page 21 / page 23.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime
from typing import Any, Optional

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client

from services.constraint_display import (
    constraint_block_substance,
    safe_text,
)
from services.perf_audit import log_supabase_query, perf_audit_enabled
from services.supabase_client import supabase

load_dotenv()

VIEW_DASHBOARD_V2 = "monthly_plan_constraints_dashboard_v2"
TABLE_PLAN_LINES_V2 = "monthly_plan_lines_v2"
TABLE_EVENTS = "monthly_plan_constraint_events"
RPC_RESOLVE = "resolve_monthly_plan_constraint"
RPC_UPDATE = "update_monthly_plan_constraint"

# R2 update patch: only these keys may be sent to update_monthly_plan_constraint.
# deadline_status is live/computed in SQL and must never be stored.
UPDATE_PATCH_WHITELIST = frozenset(
    {
        "constraint_occurred_at",
        "problem_owner",
        "owner_name",
        "subcontractor_coordinator",
        "constraint_category",
        "constraint_priority",
        "problem_description",
        "problem_impact",
        "required_action",
        "deadline_source",
        "target_resolution_date",
        "next_control_date",
    }
)

UPDATE_DATE_FIELDS = frozenset(
    {
        "constraint_occurred_at",
        "target_resolution_date",
        "next_control_date",
    }
)

UPDATE_ENUM_FIELDS = frozenset(
    {
        "deadline_source",
        "constraint_priority",
    }
)

EMPTY_TEXT_MARKERS = frozenset({"", "—", "-", "–", "−", "‒"})

DEADLINE_STATUS_DISPLAY = {
    "NOT_SET": "Не определён",
    "REQUESTED": "Запрошен",
    "ESTIMATED": "Предварительный",
    "CONFIRMED": "Подтверждён",
    "RESCHEDULED": "Перенесён",
    "OVERDUE": "Просрочен",
    "RESOLVED": "Исполнен",
}

DEADLINE_SOURCE_DISPLAY = {
    "CUSTOMER": "Заказчик",
    "GENERAL_CONTRACTOR": "Генподрядчик",
    "DESIGN_INSTITUTE": "Проектный институт",
    "SUPPLIER": "Поставщик",
    "SUBCONTRACTOR_ESTIMATE": "Оценка субподрядчика",
    "MEETING_PROTOCOL": "Протокол совещания",
    "LETTER": "Письмо",
    "TEQ": "TEQ",
    "OTHER": "Другое",
}

CONSTRAINT_PRIORITY_DISPLAY = {
    "CRITICAL": "Критический",
    "HIGH": "Высокий",
    "NORMAL": "Нормальный",
    "LOW": "Низкий",
}

DEADLINE_STATUS_CODES = frozenset(DEADLINE_STATUS_DISPLAY.keys())
DEADLINE_SOURCE_CODES = frozenset(DEADLINE_SOURCE_DISPLAY.keys())
CONSTRAINT_PRIORITY_CODES = frozenset(CONSTRAINT_PRIORITY_DISPLAY.keys())

DEFAULT_PAGE_SIZE = 1000
LINE_ID_CHUNK = 200

CLOSED_RESOLUTION = frozenset({"RESOLVED", "CANCELLED"})
BLOCKING_CHECK = frozenset({"HOLD", "FAIL"})

DISPLAY_STATUS_BY_CHECK = {
    "HOLD": "Удержание",
    "FAIL": "Не пройдено",
    "WARNING": "Предупреждение",
    "ОЖИДАЕТ": "Ожидает проверки",
    "PASS": "Пройдено",
}

READ_MODEL_COLUMNS = [
    "constraint_id",
    "line_id",
    "project_code",
    "month_key",
    "constraint_created_at",
    "queue",
    "facility_building",
    "construction_discipline",
    "boq_code",
    "boq_name",
    "iwp",
    "work_package",
    "system",
    "unit",
    "planned_qty",
    "plan_value",
    "responsible_department",
    "check_name",
    "check_status",
    "resolution_status",
    "constraint_category",
    "block_reason",
    "root_cause",
    "problem_owner",
    "owner_name",
    "subcontractor_coordinator",
    "required_action",
    "target_resolution_date",
    "actual_resolution_date",
    "constraint_occurred_at",
    "problem_description",
    "problem_impact",
    "deadline_status",
    "deadline_source",
    "next_control_date",
    "constraint_priority",
    "resolution_basis",
    "resolved_at",
    "resolved_by",
    "severity",
    "value_at_risk",
    "comment",
    "evidence_count",
    "effective_promised_date",
    "is_promise_overdue",
    "last_action_at",
    "updated_by",
    "delay_days",
    "days_open",
    "days_open_real",
    "deadline_days_overdue",
    "is_deadline_overdue",
    "is_next_control_overdue",
    "effective_deadline_status",
    "is_open",
    "is_blocking",
    "is_warning",
    "is_resolved",
    "display_status",
    "problem_summary",
    "next_action_summary",
]


def get_write_client() -> Optional[Client]:
    """service_role client for resolve RPC (anon has no EXECUTE)."""
    url = os.getenv("SUPABASE_URL")
    secret_key = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not secret_key:
        return None
    return create_client(url, secret_key)


def _norm_filter(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _safe_date(value: Any) -> Optional[date]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.date()
    except Exception:  # noqa: BLE001
        return None


def _format_iso_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    parsed = _safe_date(text)
    if parsed is not None:
        return parsed.isoformat()
    return text


def derive_construction_queue(facility: Any) -> str:
    text = str(facility or "")
    if "16160-13" in text or "16160-17" in text:
        return "1 очередь"
    if "26160-13" in text or "26160-17" in text:
        return "2 очередь"
    return "Не определено"


def _apply_eq_filters(query: Any, filters: dict[str, Optional[str]]) -> Any:
    for column, value in filters.items():
        if value is not None:
            query = query.eq(column, value)
    return query


def _fetch_paginated(
    client: Client,
    table: str,
    *,
    filters: Optional[dict[str, Optional[str]]] = None,
    select: str = "*",
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[dict[str, Any]]:
    """Bulk paginated read with optional .eq filters. No per-row queries."""
    if page_size < 1:
        raise ValueError("page_size must be >= 1")

    rows: list[dict[str, Any]] = []
    offset = 0
    page_num = 0
    import time as _time

    t_all = _time.perf_counter() if perf_audit_enabled() else 0.0
    while True:
        t_batch = _time.perf_counter()
        query = client.table(table).select(select)
        if filters:
            query = _apply_eq_filters(query, filters)
        response = query.range(offset, offset + page_size - 1).execute()
        batch = list(response.data or [])
        page_num += 1
        if perf_audit_enabled():
            log_supabase_query(
                table,
                _time.perf_counter() - t_batch,
                len(batch),
                pages=page_num,
            )
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    if perf_audit_enabled() and page_num > 1:
        log_supabase_query(table, _time.perf_counter() - t_all, len(rows), pages=page_num)
    return rows


def _fetch_plan_lines_for_ids(
    client: Client,
    line_ids: list[str],
    *,
    project_code: Optional[str] = None,
    month_key: Optional[str] = None,
) -> pd.DataFrame:
    """One bulk enrichment path: filter by project/month when possible, else chunked IN."""
    select_cols = (
        "plan_line_id,planned_qty,unit,system,iwp,facility,discipline,"
        "project_code,month_key"
    )
    unique_ids = [lid for lid in dict.fromkeys(line_ids) if lid]
    if not unique_ids:
        return pd.DataFrame()

    if project_code and month_key:
        rows = _fetch_paginated(
            client,
            TABLE_PLAN_LINES_V2,
            filters={"project_code": project_code, "month_key": month_key},
            select=select_cols,
        )
        df = pd.DataFrame(rows)
        if df.empty or "plan_line_id" not in df.columns:
            return pd.DataFrame()
        wanted = set(unique_ids)
        return df[df["plan_line_id"].astype(str).isin(wanted)].copy()

    rows: list[dict[str, Any]] = []
    import time as _time

    for offset in range(0, len(unique_ids), LINE_ID_CHUNK):
        chunk = unique_ids[offset : offset + LINE_ID_CHUNK]
        t0 = _time.perf_counter()
        response = (
            client.table(TABLE_PLAN_LINES_V2)
            .select(select_cols)
            .in_("plan_line_id", chunk)
            .execute()
        )
        batch = list(response.data or [])
        if perf_audit_enabled():
            log_supabase_query(
                TABLE_PLAN_LINES_V2,
                _time.perf_counter() - t0,
                len(batch),
                pages=offset // LINE_ID_CHUNK + 1,
            )
        rows.extend(batch)
    return pd.DataFrame(rows)


def _norm_check_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().str.upper()


def _norm_resolution_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().str.upper()


def _to_datetime_series(values: Any) -> pd.Series:
    return pd.to_datetime(values, errors="coerce", utc=True)


def _compute_days_open(df: pd.DataFrame) -> pd.Series:
    if "constraint_created_at" in df.columns:
        created_src = df["constraint_created_at"]
    elif "created_at" in df.columns:
        created_src = df["created_at"]
    else:
        return pd.Series(0, index=df.index, dtype=int)

    created = _to_datetime_series(created_src)
    if "resolved_at" in df.columns:
        resolved = _to_datetime_series(df["resolved_at"])
    else:
        resolved = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")

    today_ts = pd.Timestamp(date.today(), tz="UTC")
    end = resolved.fillna(today_ts)
    # Align tz-aware series for subtraction
    created_naive = created.dt.tz_convert("UTC").dt.normalize()
    end_naive = end.dt.tz_convert("UTC").dt.normalize()
    delta = (end_naive - created_naive).dt.days
    return delta.fillna(0).clip(lower=0).astype(int)


def _compute_delay_days(df: pd.DataFrame, is_open: pd.Series) -> pd.Series:
    """Days past target_resolution_date for open constraints; else 0."""
    if "target_resolution_date" not in df.columns:
        return pd.Series(0, index=df.index, dtype=int)
    target = _to_datetime_series(df["target_resolution_date"])
    today = pd.Timestamp(date.today(), tz="UTC").normalize()
    target_norm = target.dt.tz_convert("UTC").dt.normalize()
    overdue = (today - target_norm).dt.days
    overdue = overdue.fillna(0)
    result = overdue.where(is_open & target.notna() & (overdue > 0), 0)
    return result.astype(int)


def _display_status_row(check: str, resolution: str, is_resolved: bool) -> str:
    if is_resolved or resolution == "RESOLVED":
        return "Закрыто"
    if resolution == "CANCELLED":
        return "Отменено"
    return DISPLAY_STATUS_BY_CHECK.get(check, check or "—")


def _problem_summary_row(row: pd.Series) -> str:
    if bool(row.get("is_resolved")):
        return "Ограничение снято"
    try:
        return constraint_block_substance(row) or "—"
    except Exception:  # noqa: BLE001
        for key in ("root_cause", "block_reason", "comment"):
            text = safe_text(row.get(key))
            if text:
                return text
        return "—"


def _next_action_summary_row(row: pd.Series) -> str:
    if bool(row.get("is_resolved")):
        actual = _safe_date(row.get("actual_resolution_date"))
        if actual is not None:
            return f"Закрыто ({actual.isoformat()})"
        return "Закрыто"
    required = safe_text(row.get("required_action"))
    if required:
        return required
    target = _safe_date(row.get("target_resolution_date"))
    if target is not None:
        return f"Снять до {target.isoformat()}"
    owner = safe_text(row.get("problem_owner")) or safe_text(row.get("owner_name"))
    if owner:
        return f"Назначено: {owner}"
    return "Назначить действие и срок"


def _line_risk_value(row: pd.Series) -> float:
    """Prefer value_at_risk, else plan_value — used once per unique plan_line_id."""
    raw = row.get("value_at_risk")
    if raw is not None and not (isinstance(raw, float) and pd.isna(raw)):
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    try:
        pv = row.get("plan_value")
        if pv is None or (isinstance(pv, float) and pd.isna(pv)):
            return 0.0
        return float(pv)
    except (TypeError, ValueError):
        return 0.0


def _unique_nonempty_count(series: Optional[pd.Series]) -> int:
    if series is None:
        return 0
    values = {
        str(v).strip()
        for v in series.dropna().tolist()
        if str(v).strip() and str(v).strip().lower() not in {"nan", "none", "<na>", "—"}
    }
    return len(values)


def build_registry_summary(df: pd.DataFrame) -> dict[str, Any]:
    """
    Managerial KPI summary for the registry page.

    Layer 1 — constraints (by constraint_id / rows).
    Layer 2 — BOQ / plan lines under open constraints (unique plan_line_id).

    Cost at risk = SUM(plan_value|value_at_risk) once per unique line_id among open rows.
    Does not mutate df. No Supabase calls.
    """
    empty: dict[str, Any] = {
        "constraints_total": 0,
        "constraints_open": 0,
        "constraints_hold": 0,
        "constraints_fail": 0,
        "constraints_warning": 0,
        "constraints_overdue": 0,
        "constraints_resolved": 0,
        "boq_under_constraint_count": 0,
        "boq_cost_at_risk": 0.0,
        "unique_facility_count": 0,
        "unique_discipline_count": 0,
        "unique_system_count": 0,
        "unique_iwp_count": 0,
        # legacy aliases used by older page metrics
        "total": 0,
        "open": 0,
        "blocking": 0,
        "warning": 0,
        "overdue": 0,
        "resolved": 0,
        "boq_count": 0,
        "value_at_risk": 0.0,
    }
    if df is None or df.empty:
        return empty

    check = (
        df["check_status"].fillna("").astype(str).str.strip().str.upper()
        if "check_status" in df.columns
        else pd.Series("", index=df.index)
    )
    resolution = (
        df["resolution_status"].fillna("").astype(str).str.strip().str.upper()
        if "resolution_status" in df.columns
        else pd.Series("", index=df.index)
    )
    is_open = (
        df["is_open"].fillna(False).astype(bool)
        if "is_open" in df.columns
        else ~resolution.isin(CLOSED_RESOLUTION)
    )
    is_resolved = (
        df["is_resolved"].fillna(False).astype(bool)
        if "is_resolved" in df.columns
        else resolution.eq("RESOLVED")
    )
    delay = (
        pd.to_numeric(df["delay_days"], errors="coerce").fillna(0)
        if "delay_days" in df.columns
        else pd.Series(0, index=df.index)
    )
    overdue = is_open & (delay > 0)

    hold = int((is_open & check.eq("HOLD")).sum())
    fail = int((is_open & check.eq("FAIL")).sum())
    warning = int((is_open & check.eq("WARNING")).sum())

    # Layer 2: unique plan_line_id among open constraints
    open_df = df.loc[is_open].copy() if is_open.any() else df.iloc[0:0].copy()
    line_col = "line_id" if "line_id" in open_df.columns else None
    if line_col and not open_df.empty:
        open_df["_line_key"] = open_df[line_col].map(
            lambda v: str(v).strip() if v is not None and not (isinstance(v, float) and pd.isna(v)) else ""
        )
        open_with_line = open_df[open_df["_line_key"] != ""]
        unique_lines = open_with_line.drop_duplicates(subset=["_line_key"], keep="first")
        boq_line_count = int(len(unique_lines))
        boq_cost = float(unique_lines.apply(_line_risk_value, axis=1).sum()) if boq_line_count else 0.0
    else:
        boq_line_count = 0
        boq_cost = 0.0

    # Scope dimensions from open constrained lines (fallback: all filtered rows)
    scope_df = open_df if not open_df.empty else df
    unique_facility = _unique_nonempty_count(
        scope_df["facility_building"] if "facility_building" in scope_df.columns else None
    )
    unique_discipline = _unique_nonempty_count(
        scope_df["construction_discipline"]
        if "construction_discipline" in scope_df.columns
        else None
    )
    unique_system = _unique_nonempty_count(
        scope_df["system"] if "system" in scope_df.columns else None
    )
    iwp_series = None
    if "iwp" in scope_df.columns:
        iwp_series = scope_df["iwp"]
    elif "work_package" in scope_df.columns:
        iwp_series = scope_df["work_package"]
    unique_iwp = _unique_nonempty_count(iwp_series)

    summary = {
        "constraints_total": int(len(df)),
        "constraints_open": int(is_open.sum()),
        "constraints_hold": hold,
        "constraints_fail": fail,
        "constraints_warning": warning,
        "constraints_overdue": int(overdue.sum()),
        "constraints_resolved": int(is_resolved.sum()),
        "boq_under_constraint_count": boq_line_count,
        "boq_cost_at_risk": boq_cost,
        "unique_facility_count": unique_facility,
        "unique_discipline_count": unique_discipline,
        "unique_system_count": unique_system,
        "unique_iwp_count": unique_iwp,
        "total": int(len(df)),
        "open": int(is_open.sum()),
        "blocking": hold + fail,
        "warning": warning,
        "overdue": int(overdue.sum()),
        "resolved": int(is_resolved.sum()),
        "boq_count": boq_line_count,
        "value_at_risk": boq_cost,
    }
    return summary


def build_constraint_registry_read_model(
    constraints_df: pd.DataFrame,
    plan_lines_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Vectorized read model: one constraint = one row. No Supabase calls."""
    if constraints_df is None or constraints_df.empty:
        return pd.DataFrame(columns=READ_MODEL_COLUMNS)

    result = constraints_df.copy()

    if plan_lines_df is not None and not plan_lines_df.empty:
        plan = plan_lines_df.copy()
        plan["plan_line_id"] = plan["plan_line_id"].astype(str)
        plan = plan.drop_duplicates(subset=["plan_line_id"], keep="first")
        rename = {
            "planned_qty": "_v2_planned_qty",
            "unit": "_v2_unit",
            "system": "_v2_system",
            "iwp": "_v2_iwp",
        }
        keep = ["plan_line_id"] + [c for c in rename if c in plan.columns]
        plan = plan[keep].rename(columns=rename)
        result["line_id"] = result["line_id"].astype(str)
        result = result.merge(
            plan,
            how="left",
            left_on="line_id",
            right_on="plan_line_id",
        )
        if "plan_line_id" in result.columns:
            result = result.drop(columns=["plan_line_id"])
    else:
        for col in ("_v2_planned_qty", "_v2_unit", "_v2_system", "_v2_iwp"):
            result[col] = pd.NA

    v2_qty = result["_v2_planned_qty"] if "_v2_planned_qty" in result.columns else pd.Series(pd.NA, index=result.index)
    if "planned_qty" in result.columns:
        result["planned_qty"] = result["planned_qty"].where(result["planned_qty"].notna(), v2_qty)
    else:
        result["planned_qty"] = v2_qty

    result["unit"] = result["_v2_unit"] if "_v2_unit" in result.columns else pd.NA
    result["system"] = result["_v2_system"] if "_v2_system" in result.columns else pd.NA
    result["iwp"] = result["_v2_iwp"] if "_v2_iwp" in result.columns else pd.NA
    result["work_package"] = result["iwp"]

    facility = (
        result["facility_building"]
        if "facility_building" in result.columns
        else pd.Series("", index=result.index)
    )
    result["queue"] = facility.map(derive_construction_queue)

    check = _norm_check_series(
        result["check_status"] if "check_status" in result.columns else pd.Series("", index=result.index)
    )
    resolution = _norm_resolution_series(
        result["resolution_status"]
        if "resolution_status" in result.columns
        else pd.Series("", index=result.index)
    )

    result["is_open"] = ~resolution.isin(CLOSED_RESOLUTION)
    result["is_resolved"] = resolution.eq("RESOLVED") | (
        check.eq("PASS") & resolution.eq("RESOLVED")
    )
    result["is_blocking"] = result["is_open"] & check.isin(BLOCKING_CHECK)
    result["is_warning"] = result["is_open"] & check.eq("WARNING")
    result["days_open"] = _compute_days_open(result)
    result["delay_days"] = _compute_delay_days(result, result["is_open"])

    result["display_status"] = [
        _display_status_row(c, r, bool(ir))
        for c, r, ir in zip(check.tolist(), resolution.tolist(), result["is_resolved"].tolist())
    ]

    if "evidence_count" not in result.columns:
        result["evidence_count"] = 0
    else:
        result["evidence_count"] = pd.to_numeric(result["evidence_count"], errors="coerce").fillna(0).astype(int)

    if "is_promise_overdue" not in result.columns:
        result["is_promise_overdue"] = False
    else:
        result["is_promise_overdue"] = result["is_promise_overdue"].fillna(False).astype(bool)

    # R2 deadline / control flags (prefer dashboard_v2 computed columns)
    if "days_open_real" in result.columns:
        result["days_open_real"] = (
            pd.to_numeric(result["days_open_real"], errors="coerce")
            .fillna(result["days_open"])
            .astype(int)
        )
    else:
        result["days_open_real"] = result["days_open"]

    if "deadline_days_overdue" in result.columns:
        result["deadline_days_overdue"] = (
            pd.to_numeric(result["deadline_days_overdue"], errors="coerce")
            .fillna(0)
            .astype(int)
        )
    else:
        result["deadline_days_overdue"] = 0

    for flag_col in ("is_deadline_overdue", "is_next_control_overdue"):
        if flag_col not in result.columns:
            result[flag_col] = False
        else:
            result[flag_col] = result[flag_col].fillna(False).astype(bool)

    if "effective_deadline_status" not in result.columns:
        if "deadline_status" in result.columns:
            result["effective_deadline_status"] = result["deadline_status"]
        else:
            result["effective_deadline_status"] = "NOT_SET"
    result["effective_deadline_status"] = (
        result["effective_deadline_status"]
        .fillna("NOT_SET")
        .astype(str)
        .str.strip()
        .str.upper()
        .replace({"": "NOT_SET"})
    )

    result["problem_summary"] = result.apply(_problem_summary_row, axis=1)
    result["next_action_summary"] = result.apply(_next_action_summary_row, axis=1)

    drop_tmp = [c for c in result.columns if c.startswith("_v2_")]
    if drop_tmp:
        result = result.drop(columns=drop_tmp)

    for col in READ_MODEL_COLUMNS:
        if col not in result.columns:
            result[col] = pd.NA

    return result


def _load_constraint_registry_uncached(
    project_code: Optional[str] = None,
    month_key: Optional[str] = None,
    facility_building: Optional[str] = None,
    construction_discipline: Optional[str] = None,
    responsible_department: Optional[str] = None,
    resolution_status: Optional[str] = None,
    check_status: Optional[str] = None,
) -> pd.DataFrame:
    filters = {
        "project_code": _norm_filter(project_code),
        "month_key": _norm_filter(month_key),
        "facility_building": _norm_filter(facility_building),
        "construction_discipline": _norm_filter(construction_discipline),
        "responsible_department": _norm_filter(responsible_department),
        "resolution_status": _norm_filter(resolution_status),
        "check_status": _norm_filter(check_status),
    }

    rows = _fetch_paginated(supabase, VIEW_DASHBOARD_V2, filters=filters)
    constraints_df = pd.DataFrame(rows)
    if constraints_df.empty:
        return pd.DataFrame(columns=READ_MODEL_COLUMNS)

    line_ids = (
        constraints_df["line_id"].dropna().astype(str).str.strip().tolist()
        if "line_id" in constraints_df.columns
        else []
    )
    plan_df = _fetch_plan_lines_for_ids(
        supabase,
        line_ids,
        project_code=filters["project_code"],
        month_key=filters["month_key"],
    )
    return build_constraint_registry_read_model(constraints_df, plan_df)


@st.cache_data(ttl=300, show_spinner=False)
def load_constraint_registry(
    project_code: Optional[str] = None,
    month_key: Optional[str] = None,
    facility_building: Optional[str] = None,
    construction_discipline: Optional[str] = None,
    responsible_department: Optional[str] = None,
    resolution_status: Optional[str] = None,
    check_status: Optional[str] = None,
) -> pd.DataFrame:
    """
    Полный реестр ограничений с серверными eq-фильтрами и read model.

    Кэш: ttl=300. Инвалидация: clear_constraint_registry_caches().
    """
    return _load_constraint_registry_uncached(
        project_code=project_code,
        month_key=month_key,
        facility_building=facility_building,
        construction_discipline=construction_discipline,
        responsible_department=responsible_department,
        resolution_status=resolution_status,
        check_status=check_status,
    )


def _try_clear_loaded_page_helper(path_substr: str, func_name: str) -> bool:
    """
    Clear page 21/23 caches only if the page module is already loaded.

    Does not import pages (they call st.set_page_config at import time).
    """
    needle = path_substr.replace("\\", "/")
    for mod in list(sys.modules.values()):
        path = getattr(mod, "__file__", None) or ""
        if needle not in path.replace("\\", "/"):
            continue
        fn = getattr(mod, func_name, None)
        if not callable(fn):
            continue
        try:
            fn()
            return True
        except Exception:  # noqa: BLE001
            return False
    return False


def clear_constraint_registry_caches() -> dict[str, bool]:
    """
    Clear registry cache. Also clears page 21/23 caches when those modules
    are already loaded in the process. Does not touch passport caches.
    """
    cleared = {"registry": False, "events": False, "page_21": False, "page_23": False}
    try:
        load_constraint_registry.clear()
        cleared["registry"] = True
    except Exception:  # noqa: BLE001
        pass

    try:
        load_constraint_events.clear()
        cleared["events"] = True
    except Exception:  # noqa: BLE001
        pass

    cleared["page_21"] = _try_clear_loaded_page_helper(
        "21_Admission_Управление_ограничениями_месячного_плана.py",
        "clear_admission_constraint_caches",
    )
    cleared["page_23"] = _try_clear_loaded_page_helper(
        "23_Admission_War_Room_ограничений.py",
        "clear_war_room_data_caches",
    )
    return cleared


def clear_registry_read_caches() -> dict[str, bool]:
    """
    R2: clear only registry + events read caches.

    Does NOT touch page 21 / page 23 / passport caches.
    """
    cleared = {"registry": False, "events": False}
    try:
        load_constraint_registry.clear()
        cleared["registry"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        load_constraint_events.clear()
        cleared["events"] = True
    except Exception:  # noqa: BLE001
        pass
    return cleared


def display_deadline_status(value: Any) -> str:
    code = safe_text(value).upper()
    if not code:
        return "—"
    return DEADLINE_STATUS_DISPLAY.get(code, code)


def display_deadline_source(value: Any) -> str:
    code = safe_text(value).upper()
    if not code:
        return "—"
    return DEADLINE_SOURCE_DISPLAY.get(code, code)


def display_constraint_priority(value: Any) -> str:
    code = safe_text(value).upper()
    if not code:
        return "—"
    return CONSTRAINT_PRIORITY_DISPLAY.get(code, code)


def _is_empty_marker(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    text = str(value).strip()
    return text in EMPTY_TEXT_MARKERS or text.lower() in {"nan", "none", "<na>"}


def _normalize_patch_date(value: Any) -> Optional[str]:
    if _is_empty_marker(value):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Некорректная дата: {text}")
    try:
        return parsed.date().isoformat()
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Некорректная дата: {text}") from exc


def _normalize_patch_enum(field: str, value: Any) -> Optional[str]:
    if _is_empty_marker(value):
        return None
    code = str(value).strip().upper()
    allowed = {
        "deadline_source": DEADLINE_SOURCE_CODES,
        "constraint_priority": CONSTRAINT_PRIORITY_CODES,
    }.get(field)
    if allowed is not None and code not in allowed:
        raise ValueError(f"Недопустимое значение {field}: {code}")
    return code


def _normalize_patch_text(value: Any) -> Optional[str]:
    if _is_empty_marker(value):
        return None
    text = str(value).strip()
    return text or None


def normalize_update_patch(patch: Any) -> dict[str, Any]:
    """
    Normalize R2 update patch for RPC.

    - Unknown keys → ValueError (controlled)
    - "" / "—" / "-" / "–" → None (explicit clear)
    - dates → ISO YYYY-MM-DD or None
    - enums → uppercase technical code or None
    - Missing keys stay omitted (dirty patch responsibility of caller)
    """
    if patch is None:
        return {}
    if not isinstance(patch, dict):
        raise ValueError("p_patch должен быть объектом (jsonb object)")

    out: dict[str, Any] = {}
    for raw_key, raw_value in patch.items():
        key = str(raw_key).strip()
        if key not in UPDATE_PATCH_WHITELIST:
            raise ValueError(f"Недопустимое поле обновления: {key}")
        if key in UPDATE_DATE_FIELDS:
            out[key] = _normalize_patch_date(raw_value)
        elif key in UPDATE_ENUM_FIELDS:
            out[key] = _normalize_patch_enum(key, raw_value)
        else:
            out[key] = _normalize_patch_text(raw_value)
    return out


def parse_constraint_event_payload(payload: Any) -> dict[str, Any]:
    """
    Parse monthly_plan_constraint_events.event_payload for UPDATED (and others).

    Returns normalized dict with:
      changed_fields, old_values, new_values, source_page, comment
    """
    empty = {
        "changed_fields": [],
        "old_values": {},
        "new_values": {},
        "source_page": None,
        "comment": None,
    }
    data = payload
    if data is None or (isinstance(data, float) and pd.isna(data)):
        return empty
    if isinstance(data, str):
        text = data.strip()
        if not text:
            return empty
        try:
            data = json.loads(text)
        except Exception:  # noqa: BLE001
            return {**empty, "comment": text}
    if not isinstance(data, dict):
        return empty

    changed = data.get("changed_fields")
    if changed is None:
        changed = []
    if isinstance(changed, str):
        changed = [changed]
    if not isinstance(changed, list):
        changed = list(changed) if changed else []

    old_values = data.get("old_values")
    new_values = data.get("new_values")
    if not isinstance(old_values, dict):
        old_values = {}
    if not isinstance(new_values, dict):
        new_values = {}

    return {
        "changed_fields": [str(x) for x in changed],
        "old_values": old_values,
        "new_values": new_values,
        "source_page": _normalize_patch_text(data.get("source_page")),
        "comment": _normalize_patch_text(data.get("comment") or data.get("update_comment")),
    }


def normalize_update_error(exc: BaseException) -> str:
    """Normalize update RPC errors for UI."""
    raw = str(exc).strip() or exc.__class__.__name__
    lowered = raw.lower()

    if "not found" in lowered:
        match = re.search(r"constraint_id\s+([0-9a-f-]{36})", raw, flags=re.I)
        if match:
            return f"Ограничение не найдено: {match.group(1)}"
        return "Ограничение не найдено"

    if "p_constraint_id is required" in lowered:
        return "Не указан constraint_id"
    if "p_updated_by is required" in lowered:
        return "Не указан автор обновления (updated_by)"
    if "p_update_comment is required" in lowered:
        return "Не указан комментарий обновления"
    if "no_changes" in lowered or "no changes" in lowered:
        return "Нет изменений для сохранения"
    if "permission denied" in lowered or "not authorized" in lowered:
        return "Недостаточно прав для обновления ограничения (нужен service_role / authenticated)"
    if "jwt" in lowered or "api key" in lowered:
        return f"Ошибка авторизации Supabase: {raw}"
    if "недопустимое поле" in lowered or "недопустимое значение" in lowered:
        return raw
    if "update_monthly_plan_constraint:" in raw:
        return raw.split("update_monthly_plan_constraint:", 1)[-1].strip() or raw
    return raw


def update_constraint(
    constraint_id: Any,
    updated_by: Any,
    update_comment: Any,
    patch: Any,
) -> dict[str, Any]:
    """
    Call RPC update_monthly_plan_constraint (OPEN / IN_PROGRESS only on DB side).

    Returns: {"ok": bool, "status": str | None, "data": dict | None, "error": str | None}

    Empty patch after normalization → status=no_changes, RPC not called.
    Success → clear_registry_read_caches() only (not page 23 / passport).
    """
    cid = _norm_filter(constraint_id)
    actor = safe_text(updated_by)
    comment = safe_text(update_comment)

    if not cid:
        return {
            "ok": False,
            "status": "error",
            "data": None,
            "error": "Не указан constraint_id",
        }
    if not actor:
        return {
            "ok": False,
            "status": "error",
            "data": None,
            "error": "Не указан автор обновления (updated_by)",
        }
    if not comment:
        return {
            "ok": False,
            "status": "error",
            "data": None,
            "error": "Не указан комментарий обновления",
        }

    try:
        normalized = normalize_update_patch(patch)
    except ValueError as exc:
        return {
            "ok": False,
            "status": "error",
            "data": None,
            "error": str(exc),
        }

    if not normalized:
        return {
            "ok": True,
            "status": "no_changes",
            "data": None,
            "error": None,
        }

    payload: dict[str, Any] = {
        "p_constraint_id": cid,
        "p_updated_by": actor,
        "p_update_comment": comment,
        "p_patch": normalized,
    }

    client = get_write_client()
    if client is None:
        return {
            "ok": False,
            "status": "error",
            "data": None,
            "error": "Нет SUPABASE_SECRET_KEY — update RPC недоступен с anon-ключом",
        }

    try:
        response = client.rpc(RPC_UPDATE, payload).execute()
        data = response.data
        if isinstance(data, list) and len(data) == 1:
            data = data[0]
        if not isinstance(data, dict):
            data = {"raw": data}
        status = safe_text(data.get("status")) or "updated"
        clear_registry_read_caches()
        return {"ok": True, "status": status, "data": data, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": "error",
            "data": None,
            "error": normalize_update_error(exc),
        }


@st.cache_data(ttl=60, show_spinner=False)
def load_constraint_events(constraint_id: Optional[str] = None) -> pd.DataFrame:
    """
    Read-only audit trail for one constraint_id from monthly_plan_constraint_events.
    """
    cid = _norm_filter(constraint_id)
    if not cid:
        return pd.DataFrame()

    select_cols = (
        "event_id,constraint_id,line_id,project_code,month_key,event_type,"
        "old_check_status,new_check_status,old_resolution_status,new_resolution_status,"
        "event_comment,event_payload,performed_by,performed_at"
    )
    clients: list[Client] = [supabase]
    write_client = get_write_client()
    if write_client is not None:
        clients.append(write_client)

    last_error: Optional[BaseException] = None
    for client in clients:
        try:
            import time as _time

            t0 = _time.perf_counter()
            response = (
                client.table(TABLE_EVENTS)
                .select(select_cols)
                .eq("constraint_id", cid)
                .order("performed_at", desc=True)
                .limit(500)
                .execute()
            )
            rows = list(response.data or [])
            if perf_audit_enabled():
                log_supabase_query(TABLE_EVENTS, _time.perf_counter() - t0, len(rows))
            return pd.DataFrame(rows)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    if last_error is not None:
        raise last_error
    return pd.DataFrame()


def normalize_resolve_error(exc: BaseException) -> str:
    """Normalize PostgREST/RPC errors for UI without hiding the controlled message."""
    raw = str(exc).strip() or exc.__class__.__name__
    lowered = raw.lower()

    if "not found" in lowered:
        match = re.search(r"constraint_id\s+([0-9a-f-]{36})", raw, flags=re.I)
        if match:
            return f"Ограничение не найдено: {match.group(1)}"
        return "Ограничение не найдено"

    if "p_constraint_id is required" in lowered:
        return "Не указан constraint_id"
    if "p_actual_resolution_date is required" in lowered:
        return "Не указана фактическая дата снятия"
    if "p_closed_by is required" in lowered:
        return "Не указан закрывающий (closed_by)"
    if "p_resolution_comment is required" in lowered:
        return "Не указан комментарий закрытия"
    if "permission denied" in lowered or "not authorized" in lowered:
        return "Недостаточно прав для закрытия ограничения (нужен service_role / authenticated)"
    if "jwt" in lowered or "api key" in lowered:
        return f"Ошибка авторизации Supabase: {raw}"

    # Keep controlled DB text visible for diagnostics.
    if "resolve_monthly_plan_constraint:" in raw:
        return raw.split("resolve_monthly_plan_constraint:", 1)[-1].strip() or raw
    return raw


def resolve_constraint(
    constraint_id: Any,
    actual_resolution_date: Any,
    resolution_comment: Any,
    closed_by: Any,
    evidence_payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Call RPC resolve_monthly_plan_constraint.

    Returns: {"ok": bool, "data": dict | None, "error": str | None}
    Does not resolve real rows from smoke tests — caller must pass real id intentionally.
    """
    cid = _norm_filter(constraint_id)
    comment = safe_text(resolution_comment)
    actor = safe_text(closed_by)

    if not cid:
        return {"ok": False, "data": None, "error": "Не указан constraint_id"}
    if actual_resolution_date is None or (
        isinstance(actual_resolution_date, float) and pd.isna(actual_resolution_date)
    ):
        return {"ok": False, "data": None, "error": "Не указана фактическая дата снятия"}
    if not comment:
        return {"ok": False, "data": None, "error": "Не указан комментарий закрытия"}
    if not actor:
        return {"ok": False, "data": None, "error": "Не указан закрывающий (closed_by)"}

    try:
        date_iso = _format_iso_date(actual_resolution_date)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "data": None, "error": f"Некорректная дата: {exc}"}

    payload: dict[str, Any] = {
        "p_constraint_id": cid,
        "p_actual_resolution_date": date_iso,
        "p_resolution_comment": comment,
        "p_closed_by": actor,
        "p_evidence_payload": evidence_payload if evidence_payload is not None else {},
    }

    client = get_write_client()
    if client is None:
        return {
            "ok": False,
            "data": None,
            "error": "Нет SUPABASE_SECRET_KEY — resolve RPC недоступен с anon-ключом",
        }

    try:
        response = client.rpc(RPC_RESOLVE, payload).execute()
        data = response.data
        if isinstance(data, list) and len(data) == 1:
            data = data[0]
        if not isinstance(data, dict):
            data = {"raw": data}
        clear_constraint_registry_caches()
        return {"ok": True, "data": data, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "data": None, "error": normalize_resolve_error(exc)}
