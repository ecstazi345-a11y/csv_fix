"""
Monthly Resource Plan service (R1.2).

SoT for future crew capacity: APPROVED rows in monthly_resource_plan_lines.
Crew_Register / monthly_labor_summary = candidates / assignment source only.
Daily Progress = actual consumption (not used here).

No Streamlit imports in pure helpers. DB I/O isolated behind load/upsert functions.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client

from services.monthly_plan_labor_service import to_num
from services.supabase_client import supabase
from utils.month_key import normalize_month_key

load_dotenv()

TABLE = "monthly_resource_plan_lines"
VIEW_CAPACITY = "monthly_resource_capacity_v1"
LABOR_TABLE = "monthly_labor_summary"

STATUS_DRAFT = "DRAFT"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
ALLOWED_STATUSES = frozenset({STATUS_DRAFT, STATUS_APPROVED, STATUS_REJECTED})

HOURS_PER_PERSON_MONTH_DEFAULT = 176.0

LINE_COLUMNS = [
    "resource_plan_line_id",
    "project_code",
    "month_key",
    "crew_code",
    "person_id",
    "person_name",
    "role",
    "effective_from",
    "effective_to",
    "planned_shift_hours",
    "confirmed_available_hours",
    "resource_status",
    "approved_by",
    "approved_at",
    "source_airtable_record_id",
    "comment",
    "created_at",
    "updated_at",
]

CAPACITY_COLUMNS = [
    "project_code",
    "month_key",
    "crew_code",
    "available_labor_hours",
    "available_fte",
    "roster_row_count",
    "approved_people_count",
    "approved_assignment_count",
    "approved_available_hours",
    "fte_gap",
    "resource_plan_status",
]

# Sentinels aligned with SQL unique index COALESCE dates
_DATE_SENTINEL_FROM = "1900-01-01"
_DATE_SENTINEL_TO = "9999-12-31"

_last_error: Optional[str] = None


def get_last_error() -> Optional[str]:
    return _last_error


def _set_error(message: Optional[str]) -> None:
    global _last_error
    _last_error = message


def _safe_str(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def get_supabase_write_client() -> Client | None:
    url = os.getenv("SUPABASE_URL")
    secret_key = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not secret_key:
        return None
    return create_client(url, secret_key)


def empty_plan_df() -> pd.DataFrame:
    return pd.DataFrame(columns=LINE_COLUMNS)


def empty_capacity_df() -> pd.DataFrame:
    return pd.DataFrame(columns=CAPACITY_COLUMNS)


def normalize_resource_status(value: Any) -> str:
    text = _safe_str(value).upper()
    if text in ALLOWED_STATUSES:
        return text
    return STATUS_DRAFT


def person_identity_key(person_id: Any, person_name: Any) -> str:
    """Stable person identity: prefer person_id, else person_name."""
    pid = _safe_str(person_id)
    if pid:
        return pid
    return _safe_str(person_name)


def resource_plan_business_key(
    *,
    project_code: Any,
    month_key: Any,
    crew_code: Any,
    person_id: Any,
    person_name: Any,
    effective_from: Any,
    effective_to: Any,
) -> tuple[str, str, str, str, str, str, str]:
    """
    Deterministic anti-duplicate key matching SQL unique index semantics.
    Different periods → different keys (two periods for one person allowed).
    """
    month = normalize_month_key(month_key) or _safe_str(month_key)
    pid = _safe_str(person_id)  # empty string when null — matches SQL coalesce
    from_d = _safe_str(effective_from) or _DATE_SENTINEL_FROM
    to_d = _safe_str(effective_to) or _DATE_SENTINEL_TO
    return (
        _safe_str(project_code),
        month,
        _safe_str(crew_code),
        pid,
        _safe_str(person_name),
        from_d,
        to_d,
    )


def validate_effective_date_range(
    effective_from: Any,
    effective_to: Any,
) -> None:
    """Raise ValueError if both dates set and to < from."""
    from_s = _safe_str(effective_from)
    to_s = _safe_str(effective_to)
    if not from_s or not to_s:
        return
    if to_s < from_s:
        raise ValueError("effective_to должен быть >= effective_from")


def aggregate_approved_capacity(
    lines_df: pd.DataFrame,
    *,
    hours_per_person_month: float = HOURS_PER_PERSON_MONTH_DEFAULT,
) -> pd.DataFrame:
    """
    Deterministic APPROVED-only capacity rollup.
    Grain: project_code + month_key(YYYY-MM) + crew_code.

    approved_people_count = unique people (person_id or person_name)
    approved_assignment_count = APPROVED period lines
    hours = SUM of all APPROVED period hours
    """
    if lines_df is None or lines_df.empty:
        return empty_capacity_df()

    df = lines_df.copy()
    if "resource_status" not in df.columns:
        return empty_capacity_df()

    df["resource_status"] = df["resource_status"].map(normalize_resource_status)
    approved = df[df["resource_status"] == STATUS_APPROVED].copy()
    if approved.empty:
        return empty_capacity_df()

    approved["project_code"] = approved["project_code"].map(_safe_str)
    approved["crew_code"] = approved["crew_code"].map(_safe_str)
    approved["month_key"] = approved["month_key"].map(
        lambda v: normalize_month_key(v) or _safe_str(v)
    )
    approved["confirmed_available_hours"] = pd.to_numeric(
        approved.get("confirmed_available_hours"), errors="coerce"
    ).fillna(0.0)
    if "person_id" not in approved.columns:
        approved["person_id"] = None
    if "person_name" not in approved.columns:
        approved["person_name"] = ""
    approved["_person_key"] = [
        person_identity_key(pid, name)
        for pid, name in zip(approved["person_id"], approved["person_name"])
    ]

    approved = approved[
        (approved["project_code"] != "")
        & (approved["crew_code"] != "")
        & (approved["month_key"] != "")
        & (approved["_person_key"] != "")
    ]
    if approved.empty:
        return empty_capacity_df()

    rows: list[dict[str, Any]] = []
    for (project_code, month_key, crew_code), group in approved.groupby(
        ["project_code", "month_key", "crew_code"], dropna=False
    ):
        hours = float(group["confirmed_available_hours"].sum())
        people = int(group["_person_key"].nunique())
        assignments = int(len(group))
        fte = (
            hours / hours_per_person_month
            if hours_per_person_month > 0
            else 0.0
        )
        rows.append(
            {
                "project_code": project_code,
                "month_key": month_key,
                "crew_code": crew_code,
                "available_labor_hours": hours,
                "available_fte": fte,
                "roster_row_count": people,
                "approved_people_count": people,
                "approved_assignment_count": assignments,
                "approved_available_hours": hours,
                "fte_gap": 0.0,
                "resource_plan_status": STATUS_APPROVED,
            }
        )
    return pd.DataFrame(rows)[CAPACITY_COLUMNS]


def capacity_df_for_page22(lines_or_capacity_df: pd.DataFrame) -> pd.DataFrame:
    """
    Shape data for monthly_plan_resource_economic_service.

    Accepts either plan lines (with confirmed_available_hours + resource_status)
    or a pre-aggregated capacity frame (with available_labor_hours).
    """
    if lines_or_capacity_df is None or lines_or_capacity_df.empty:
        return empty_capacity_df()
    if "confirmed_available_hours" in lines_or_capacity_df.columns:
        return aggregate_approved_capacity(lines_or_capacity_df)
    if "available_labor_hours" in lines_or_capacity_df.columns:
        out = lines_or_capacity_df.copy()
        for col in CAPACITY_COLUMNS:
            if col not in out.columns:
                out[col] = None
        return out[CAPACITY_COLUMNS]
    return empty_capacity_df()


def build_plan_line_payload(
    *,
    project_code: str,
    month_key: str,
    crew_code: str,
    person_name: str,
    confirmed_available_hours: float,
    resource_status: str = STATUS_DRAFT,
    person_id: str | None = None,
    role: str | None = None,
    effective_from: str | None = None,
    effective_to: str | None = None,
    planned_shift_hours: float | None = None,
    approved_by: str | None = None,
    source_airtable_record_id: str | None = None,
    comment: str | None = None,
    resource_plan_line_id: str | None = None,
) -> dict[str, Any]:
    """Validate and build a writable payload. Raises ValueError on invalid input."""
    project = _safe_str(project_code)
    crew = _safe_str(crew_code)
    person = _safe_str(person_name)
    month = normalize_month_key(month_key)
    status = normalize_resource_status(resource_status)
    hours = to_num(confirmed_available_hours, default=-1.0)

    if not project:
        raise ValueError("project_code обязателен")
    if not month:
        raise ValueError("month_key должен нормализоваться в YYYY-MM")
    if not crew:
        raise ValueError("crew_code обязателен")
    if not person:
        raise ValueError("person_name обязателен")
    if hours < 0:
        raise ValueError("confirmed_available_hours должен быть >= 0")

    validate_effective_date_range(effective_from, effective_to)

    now_iso = datetime.now(timezone.utc).isoformat()
    line_id = _safe_str(resource_plan_line_id) or str(uuid.uuid4())
    approver = _safe_str(approved_by) or "system"

    payload: dict[str, Any] = {
        "resource_plan_line_id": line_id,
        "project_code": project,
        "month_key": month,
        "crew_code": crew,
        "person_id": _safe_str(person_id) or None,
        "person_name": person,
        "role": _safe_str(role) or None,
        "effective_from": _safe_str(effective_from) or None,
        "effective_to": _safe_str(effective_to) or None,
        "planned_shift_hours": (
            to_num(planned_shift_hours) if planned_shift_hours is not None else None
        ),
        "confirmed_available_hours": hours,
        "resource_status": status,
        "source_airtable_record_id": _safe_str(source_airtable_record_id) or None,
        "comment": _safe_str(comment) or None,
        "updated_at": now_iso,
    }

    if status == STATUS_APPROVED:
        # Schema CHECK requires approved_by + approved_at for APPROVED
        payload["approved_by"] = approver
        payload["approved_at"] = now_iso
    elif status == STATUS_DRAFT:
        payload["approved_by"] = None
        payload["approved_at"] = None
    # REJECTED: leave approved_* unset here; update path preserves audit trail
    elif status == STATUS_REJECTED:
        # Do not clear historical approval metadata on reject upsert
        if _safe_str(approved_by):
            payload["approved_by"] = _safe_str(approved_by)
        if payload.get("approved_at") is None and payload.get("approved_by"):
            payload["approved_at"] = now_iso

    return payload


def load_resource_plan(
    *,
    project_code: str | None = None,
    month_key: str | None = None,
    crew_code: str | None = None,
    limit: int = 5000,
) -> pd.DataFrame:
    """Read resource plan lines. Returns empty DF on missing table / error."""
    _set_error(None)
    try:
        query = supabase.table(TABLE).select("*").limit(limit)
        if project_code and _safe_str(project_code) not in {"", "Все"}:
            query = query.eq("project_code", _safe_str(project_code))
        month = normalize_month_key(month_key) if month_key else None
        if month:
            query = query.eq("month_key", month)
        if crew_code and _safe_str(crew_code) not in {"", "Все"}:
            query = query.eq("crew_code", _safe_str(crew_code))
        response = query.execute()
        df = pd.DataFrame(response.data or [])
        if df.empty:
            return empty_plan_df()
        for col in LINE_COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df[LINE_COLUMNS]
    except Exception as exc:  # noqa: BLE001
        _set_error(f"{type(exc).__name__}: {exc}")
        return empty_plan_df()


def load_approved_capacity(
    *,
    project_code: str | None = None,
    month_key: str | None = None,
    crew_code: str | None = None,
    limit: int = 5000,
) -> pd.DataFrame:
    """
    Load APPROVED capacity for Page22.
    Prefer view monthly_resource_capacity_v1; fallback to aggregate from lines.
    """
    _set_error(None)
    month = normalize_month_key(month_key) if month_key else None
    try:
        query = supabase.table(VIEW_CAPACITY).select("*").limit(limit)
        if project_code and _safe_str(project_code) not in {"", "Все"}:
            query = query.eq("project_code", _safe_str(project_code))
        if month:
            query = query.eq("month_key", month)
        if crew_code and _safe_str(crew_code) not in {"", "Все"}:
            query = query.eq("crew_code", _safe_str(crew_code))
        response = query.execute()
        df = pd.DataFrame(response.data or [])
        if not df.empty:
            rows = []
            for _, row in df.iterrows():
                hours = to_num(row.get("approved_available_hours"))
                people = int(to_num(row.get("approved_people_count")))
                assignments = int(
                    to_num(
                        row.get("approved_assignment_count"),
                        default=float(people),
                    )
                )
                rows.append(
                    {
                        "project_code": _safe_str(row.get("project_code")),
                        "month_key": normalize_month_key(row.get("month_key"))
                        or _safe_str(row.get("month_key")),
                        "crew_code": _safe_str(row.get("crew_code")),
                        "available_labor_hours": hours,
                        "available_fte": hours / HOURS_PER_PERSON_MONTH_DEFAULT
                        if HOURS_PER_PERSON_MONTH_DEFAULT > 0
                        else 0.0,
                        "roster_row_count": people,
                        "approved_people_count": people,
                        "approved_assignment_count": assignments,
                        "approved_available_hours": hours,
                        "fte_gap": 0.0,
                        "resource_plan_status": STATUS_APPROVED,
                    }
                )
            return pd.DataFrame(rows)[CAPACITY_COLUMNS]
    except Exception as exc:  # noqa: BLE001
        _set_error(f"view:{type(exc).__name__}: {exc}")

    # Fallback: aggregate from lines table
    lines = load_resource_plan(
        project_code=project_code,
        month_key=month_key,
        crew_code=crew_code,
        limit=limit,
    )
    return aggregate_approved_capacity(lines)


def upsert_resource_plan_line(payload: dict[str, Any]) -> dict[str, Any]:
    """Upsert one resource plan line. Requires SUPABASE_SECRET_KEY."""
    _set_error(None)
    write_client = get_supabase_write_client()
    if write_client is None:
        msg = "SUPABASE_SECRET_KEY не задан — запись resource plan недоступна"
        _set_error(msg)
        return {"ok": False, "error": msg, "row": None}

    try:
        built = build_plan_line_payload(
            project_code=payload.get("project_code", ""),
            month_key=payload.get("month_key", ""),
            crew_code=payload.get("crew_code", ""),
            person_name=payload.get("person_name", ""),
            confirmed_available_hours=to_num(payload.get("confirmed_available_hours")),
            resource_status=payload.get("resource_status", STATUS_DRAFT),
            person_id=payload.get("person_id"),
            role=payload.get("role"),
            effective_from=payload.get("effective_from"),
            effective_to=payload.get("effective_to"),
            planned_shift_hours=payload.get("planned_shift_hours"),
            approved_by=payload.get("approved_by"),
            source_airtable_record_id=payload.get("source_airtable_record_id"),
            comment=payload.get("comment"),
            resource_plan_line_id=payload.get("resource_plan_line_id"),
        )
        if "created_at" not in payload or not payload.get("created_at"):
            built["created_at"] = built["updated_at"]
        resp = (
            write_client.table(TABLE)
            .upsert(built, on_conflict="resource_plan_line_id")
            .execute()
        )
        row = (resp.data or [built])[0] if hasattr(resp, "data") else built
        return {"ok": True, "error": None, "row": row}
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
        _set_error(msg)
        return {"ok": False, "error": msg, "row": None}


def approve_resource_plan_line(
    resource_plan_line_id: str,
    *,
    approved_by: str = "system",
) -> dict[str, Any]:
    _set_error(None)
    write_client = get_supabase_write_client()
    if write_client is None:
        msg = "SUPABASE_SECRET_KEY не задан — approve недоступен"
        _set_error(msg)
        return {"ok": False, "error": msg}
    line_id = _safe_str(resource_plan_line_id)
    if not line_id:
        return {"ok": False, "error": "resource_plan_line_id обязателен"}
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        write_client.table(TABLE).update(
            {
                "resource_status": STATUS_APPROVED,
                "approved_by": _safe_str(approved_by) or "system",
                "approved_at": now_iso,
                "updated_at": now_iso,
            }
        ).eq("resource_plan_line_id", line_id).execute()
        return {"ok": True, "error": None}
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
        _set_error(msg)
        return {"ok": False, "error": msg}


def reject_resource_plan_line(resource_plan_line_id: str) -> dict[str, Any]:
    _set_error(None)
    write_client = get_supabase_write_client()
    if write_client is None:
        msg = "SUPABASE_SECRET_KEY не задан — reject недоступен"
        _set_error(msg)
        return {"ok": False, "error": msg}
    line_id = _safe_str(resource_plan_line_id)
    if not line_id:
        return {"ok": False, "error": "resource_plan_line_id обязателен"}
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        write_client.table(TABLE).update(
            {
                "resource_status": STATUS_REJECTED,
                "updated_at": now_iso,
            }
        ).eq("resource_plan_line_id", line_id).execute()
        return {"ok": True, "error": None}
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
        _set_error(msg)
        return {"ok": False, "error": msg}


def load_candidates_from_labor_summary(
    *,
    project_code: str | None = None,
    month_key: str | None = None,
    crew_code: str | None = None,
    limit: int = 5000,
    fallback_last_known: bool = False,
) -> pd.DataFrame:
    """
    Prefill candidates from monthly_labor_summary.
    Prefill ≠ approval. Never auto-writes APPROVED capacity.

    If fallback_last_known=True and target month has no rows for the crew,
    return people from the latest available roster month for that crew.
    """
    _set_error(None)
    cols = (
        "airtable_record_id,full_name_ru,role,project_code,crew_code,month_key,"
        "direct_hours_month,budget_status,actual_mobilization_date,"
        "planned_demobilization_date,actual_demobilization_date"
    )
    try:
        query = supabase.table(LABOR_TABLE).select(cols).limit(limit)
        if project_code and _safe_str(project_code) not in {"", "Все"}:
            query = query.eq("project_code", _safe_str(project_code))
        if crew_code and _safe_str(crew_code) not in {"", "Все"}:
            query = query.eq("crew_code", _safe_str(crew_code))
        response = query.execute()
        df = pd.DataFrame(response.data or [])
        if df.empty:
            return pd.DataFrame()

        if crew_code and _safe_str(crew_code) not in {"", "Все"} and "crew_code" in df.columns:
            df = df[df["crew_code"].astype(str).str.strip() == _safe_str(crew_code)].copy()

        target_month = normalize_month_key(month_key) if month_key else None
        if target_month and "month_key" in df.columns:
            exact = df[
                df["month_key"].map(lambda v: normalize_month_key(v) == target_month)
            ].copy()
            if not exact.empty:
                return exact.reset_index(drop=True)
            if not fallback_last_known:
                return exact.reset_index(drop=True)
            # Last known roster month for this crew (reference only)
            df = df.copy()
            df["_month_canon"] = df["month_key"].map(normalize_month_key)
            df = df[df["_month_canon"].notna()]
            if df.empty:
                return pd.DataFrame()
            latest = str(sorted(df["_month_canon"].unique())[-1])
            out = df[df["_month_canon"] == latest].drop(columns=["_month_canon"])
            return out.reset_index(drop=True)

        return df.reset_index(drop=True)
    except Exception as exc:  # noqa: BLE001
        _set_error(f"{type(exc).__name__}: {exc}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# R1.3 Workbench helpers (pure; no Streamlit; no auto calendar-hour calc)
# ---------------------------------------------------------------------------

STATUS_RU = {
    STATUS_DRAFT: "Черновик",
    STATUS_APPROVED: "Утверждён",
    STATUS_REJECTED: "Отклонён",
}

# Workbench coverage labels (UI). Canonical codes remain for Page22.
WB_STATUS_MISSING = "MISSING"
WB_STATUS_DEFICIT = "DEFICIT"
WB_STATUS_READY = "READY"
WB_STATUS_RU = {
    WB_STATUS_MISSING: "Ресурсный план не сформирован",
    WB_STATUS_DEFICIT: "Дефицит ресурса",
    WB_STATUS_READY: "Ресурс обеспечен",
}

DELETE_AVAILABLE = False  # R1.3: no product delete; use REJECT for DRAFT errors
BATCH_WRITE_AVAILABLE = True  # R1.4.2: batch DRAFT create for current-month selection
BATCH_APPROVE_AVAILABLE = False  # R1.4.2: no batch APPROVE

# Same constant as Page10B Конструктор месячного плана (v2_compute_plan_add_preview).
PRODUCTIVE_HOURS_PER_PERSON_SHIFT = 8.0

ROSTER_MODE_CURRENT_MONTH = "current_month"
ROSTER_MODE_FALLBACK = "fallback_last_known"
ROSTER_MODE_EMPTY = "empty"

PLAN_UI_NOT_ADDED = "not_added"
PLAN_UI_DRAFT = "draft"
PLAN_UI_APPROVED = "approved"
PLAN_UI_REJECTED = "rejected"
PLAN_UI_STATUS_RU = {
    PLAN_UI_NOT_ADDED: "Не добавлен",
    PLAN_UI_DRAFT: "Черновик сформирован",
    PLAN_UI_APPROVED: "Утверждён",
    PLAN_UI_REJECTED: "Отклонён",
}

BATCH_SKIP_ALREADY_DRAFT = "already_draft"
BATCH_SKIP_ALREADY_APPROVED = "already_approved"
BATCH_SKIP_REJECTED = "rejected"
BATCH_SKIP_VALIDATION = "validation"
BATCH_SKIP_FALLBACK = "fallback_not_allowed"
BATCH_SKIP_EMPTY = "empty_selection"


def resource_status_label_ru(status: Any) -> str:
    return STATUS_RU.get(normalize_resource_status(status), _safe_str(status))


def is_resource_line_editable(resource_status: Any) -> bool:
    """R1.3 policy: only DRAFT is editable; APPROVED/REJECTED are read-only."""
    return normalize_resource_status(resource_status) == STATUS_DRAFT


def summarize_crew_demand_from_labor_lines(
    labor_lines_df: pd.DataFrame,
    *,
    project_code: str,
    month_key: str,
    crew_code: str,
) -> dict[str, Any]:
    """
    Required hours / BOQ / plan value for one crew scope.
    Reuses monthly_plan_labor_lines_v1 via Page22 column normalization (crew → crew_code).
    Does not invent norms.
    """
    empty = {
        "required_hours": 0.0,
        "boq_count": 0,
        "plan_value": 0.0,
        "line_count": 0,
        "matched": False,
    }
    if labor_lines_df is None or labor_lines_df.empty:
        return empty

    project = _safe_str(project_code)
    crew = _safe_str(crew_code)
    month = normalize_month_key(month_key)
    if not project or not crew or not month:
        return empty

    scoped = _filter_crew_labor_scope(
        labor_lines_df,
        project_code=project,
        month_key=month,
        crew_code=crew,
    )
    if scoped.empty:
        return empty

    required = float(pd.to_numeric(scoped["labor_hours"], errors="coerce").fillna(0).sum())
    plan_value = (
        float(pd.to_numeric(scoped["plan_value"], errors="coerce").fillna(0).sum())
        if "plan_value" in scoped.columns
        else 0.0
    )
    boq_count = (
        int(scoped["boq_code"].astype(str).str.strip().replace("", pd.NA).nunique(dropna=True))
        if "boq_code" in scoped.columns
        else int(len(scoped))
    )
    return {
        "required_hours": required,
        "boq_count": boq_count,
        "plan_value": plan_value,
        "line_count": int(len(scoped)),
        "matched": True,
    }


def _filter_crew_labor_scope(
    labor_lines_df: pd.DataFrame,
    *,
    project_code: str,
    month_key: str,
    crew_code: str,
) -> pd.DataFrame:
    """Scoped labor lines for one project/month/crew (normalized columns)."""
    from services.monthly_plan_resource_economic_service import normalize_labor_lines_df

    project = _safe_str(project_code)
    crew = _safe_str(crew_code)
    month = normalize_month_key(month_key)
    if not project or not crew or not month:
        return pd.DataFrame()

    df = normalize_labor_lines_df(labor_lines_df)
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["_project"] = df["project_code"].map(_safe_str)
    df["_crew"] = df["crew_code"].map(_safe_str)
    df["_month"] = df["month_key"].map(normalize_month_key)
    scoped = df[
        (df["_project"] == project) & (df["_crew"] == crew) & (df["_month"] == month)
    ].copy()
    return scoped.drop(columns=["_project", "_crew", "_month"], errors="ignore")


def compute_line_duration_shifts(
    required_hours: float,
    crew_size: Any,
) -> float | None:
    """
    Reuses Page10B v2_compute_plan_add_preview duration algorithm:
    duration_shifts = required_hours / (crew_size × PRODUCTIVE_HOURS_PER_PERSON_SHIFT).
    """
    hours = max(float(required_hours or 0.0), 0.0)
    if hours <= 0:
        return None
    size = max(int(to_num(crew_size, default=1.0)), 1)
    capacity = size * PRODUCTIVE_HOURS_PER_PERSON_SHIFT
    if capacity <= 0:
        return None
    return hours / capacity


def format_duration_shifts_display(duration_shifts: float | None) -> str:
    if duration_shifts is None or duration_shifts <= 0:
        return "—"
    text = f"{duration_shifts:.1f}".rstrip("0").rstrip(".")
    return f"{text} смены"


def build_crew_workload_lines(
    labor_lines_df: pd.DataFrame,
    *,
    project_code: str,
    month_key: str,
    crew_code: str,
) -> pd.DataFrame:
    """
    BOQ-level production workload for one crew scope.
    Source: monthly_plan_labor_lines_v1 via normalize_labor_lines_df().
    """
    scoped = _filter_crew_labor_scope(
        labor_lines_df,
        project_code=project_code,
        month_key=month_key,
        crew_code=crew_code,
    )
    if scoped.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for rec in scoped.to_dict(orient="records"):
        required = float(to_num(rec.get("labor_hours")))
        crew_size = rec.get("crew_size")
        duration = compute_line_duration_shifts(required, crew_size)
        rows.append(
            {
                "boq_code": _safe_str(rec.get("boq_code")),
                "boq_name": _safe_str(rec.get("boq_name")),
                "planned_qty": to_num(rec.get("planned_qty")),
                "unit": _safe_str(rec.get("unit")),
                "required_hours": required,
                "crew_size": max(int(to_num(crew_size, default=1.0)), 1),
                "duration_shifts": duration,
                "duration_display": format_duration_shifts_display(duration),
                "plan_value": to_num(rec.get("plan_value")),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["boq_code", "boq_name"], kind="stable").reset_index(drop=True)


def resolve_crew_roster_from_labor_summary(
    *,
    project_code: str | None = None,
    month_key: str | None = None,
    crew_code: str | None = None,
    limit: int = 5000,
    fallback_last_known: bool = True,
) -> dict[str, Any]:
    """
    Current-month roster from monthly_labor_summary, or last-known fallback.
    Returns mode metadata for Page22B proposal vs candidate UX.
    """
    empty: dict[str, Any] = {
        "mode": ROSTER_MODE_EMPTY,
        "target_month": normalize_month_key(month_key) if month_key else None,
        "source_month": None,
        "rows": pd.DataFrame(),
        "proposed_hours_total": 0.0,
    }
    rows = load_candidates_from_labor_summary(
        project_code=project_code,
        month_key=month_key,
        crew_code=crew_code,
        limit=limit,
        fallback_last_known=fallback_last_known,
    )
    if rows.empty:
        return empty

    target_month = normalize_month_key(month_key) if month_key else None
    source_months = sorted(
        {
            m
            for m in (normalize_month_key(v) for v in rows.get("month_key", pd.Series(dtype=str)))
            if m
        }
    )
    source_month = source_months[-1] if source_months else None
    if target_month and source_month == target_month:
        mode = ROSTER_MODE_CURRENT_MONTH
    elif fallback_last_known and source_month:
        mode = ROSTER_MODE_FALLBACK
    else:
        mode = ROSTER_MODE_EMPTY if rows.empty else ROSTER_MODE_FALLBACK

    hours = float(
        pd.to_numeric(rows.get("direct_hours_month"), errors="coerce").fillna(0).sum()
    )
    return {
        "mode": mode,
        "target_month": target_month,
        "source_month": source_month,
        "rows": rows.reset_index(drop=True),
        "proposed_hours_total": hours if mode == ROSTER_MODE_CURRENT_MONTH else 0.0,
    }


def summarize_proposed_vs_demand(
    *,
    required_hours: float,
    proposed_hours: float,
) -> dict[str, Any]:
    """Diagnostic comparison: crew demand vs proposed current-month hours (not approved)."""
    required = max(float(required_hours or 0.0), 0.0)
    proposed = max(float(proposed_hours or 0.0), 0.0)
    gap = proposed - required if required > 0 or proposed > 0 else None
    coverage = (proposed / required) if required > 0 else None
    return {
        "required_hours": required,
        "proposed_hours": proposed,
        "hours_gap": gap,
        "coverage": coverage,
        "coverage_pct": (coverage * 100.0) if coverage is not None else None,
    }


def summarize_selected_roster_preview(
    rows: pd.DataFrame,
    *,
    selected_indices: list[int] | tuple[int, ...] | None,
    required_hours: float,
    roster_mode: str,
) -> dict[str, Any]:
    """
    Non-writing preview of a multi-person selection vs crew demand.

    Current-month: selected_hours = SUM(direct_hours_month of selected rows).
    Fallback: historical hours never become proposed current-month capacity.
    Does not write, approve, or count as monthly_resource_capacity_v1.
    """
    indices = [int(i) for i in (selected_indices or [])]
    selected_people = 0
    selected_hours = 0.0

    if rows is not None and not rows.empty and indices:
        scoped = rows.reset_index(drop=True)
        valid = [i for i in indices if 0 <= i < len(scoped)]
        if valid:
            picked = scoped.iloc[valid]
            selected_people = int(len(picked))
            if (
                roster_mode == ROSTER_MODE_CURRENT_MONTH
                and "direct_hours_month" in picked.columns
            ):
                selected_hours = float(
                    pd.to_numeric(picked["direct_hours_month"], errors="coerce")
                    .fillna(0)
                    .sum()
                )

    diag = summarize_proposed_vs_demand(
        required_hours=required_hours,
        proposed_hours=selected_hours,
    )
    return {
        "selected_people": selected_people,
        "selected_hours": selected_hours,
        "required_hours": diag["required_hours"],
        "hours_gap": diag["hours_gap"],
        "coverage": diag["coverage"],
        "coverage_pct": diag["coverage_pct"],
        "is_approved_capacity": False,
        "writes": False,
        "roster_mode": roster_mode,
    }


def build_roster_prefill_payload(
    row: dict[str, Any] | pd.Series,
    *,
    roster_mode: str,
) -> dict[str, Any]:
    """
    Prefill draft form from monthly_labor_summary row.
    Current month → proposed hours + availability dates.
    Fallback → name/role only; no historical hours or period dates.
    """
    if isinstance(row, pd.Series):
        row = row.to_dict()

    person = _safe_str(row.get("full_name_ru"))
    role = _safe_str(row.get("role"))
    source_id = _safe_str(row.get("airtable_record_id"))
    month_label = _safe_str(row.get("month_key"))

    if roster_mode == ROSTER_MODE_CURRENT_MONTH:
        proposed = to_num(row.get("direct_hours_month"))
        effective_from = _safe_str(row.get("actual_mobilization_date")) or None
        effective_to = (
            _safe_str(row.get("actual_demobilization_date"))
            or _safe_str(row.get("planned_demobilization_date"))
            or None
        )
        return {
            "person_name": person,
            "role": role,
            "effective_from": effective_from,
            "effective_to": effective_to,
            "proposed_hours": proposed,
            "source_airtable_record_id": source_id or None,
            "comment": (
                f"Предложение из кадрового плана ({month_label}); "
                "подтвердите часы перед утверждением"
            ),
            "is_current_month": True,
        }

    return {
        "person_name": person,
        "role": role,
        "effective_from": None,
        "effective_to": None,
        "proposed_hours": None,
        "source_airtable_record_id": source_id or None,
        "comment": (
            f"Кандидат из последнего известного состава ({month_label}); "
            "confirmed hours задать отдельно"
        ),
        "is_current_month": False,
    }


def current_month_assignment_dates(row: dict[str, Any] | pd.Series) -> tuple[str | None, str | None]:
    """R1.4 date priority: mobilization → actual demob, else planned demob. No invented dates."""
    if isinstance(row, pd.Series):
        row = row.to_dict()
    effective_from = _safe_str(row.get("actual_mobilization_date")) or None
    effective_to = (
        _safe_str(row.get("actual_demobilization_date"))
        or _safe_str(row.get("planned_demobilization_date"))
        or None
    )
    return effective_from, effective_to


def _scope_resource_plan_df(
    existing_df: pd.DataFrame,
    *,
    project_code: str,
    month_key: str,
    crew_code: str,
) -> pd.DataFrame:
    if existing_df is None or existing_df.empty:
        return empty_plan_df()
    project = _safe_str(project_code)
    crew = _safe_str(crew_code)
    month = normalize_month_key(month_key)
    df = existing_df.copy()
    df["_project"] = df["project_code"].map(_safe_str)
    df["_crew"] = df["crew_code"].map(_safe_str)
    df["_month"] = df["month_key"].map(lambda v: normalize_month_key(v) or _safe_str(v))
    scoped = df[
        (df["_project"] == project) & (df["_crew"] == crew) & (df["_month"] == month)
    ]
    return scoped.drop(columns=["_project", "_crew", "_month"], errors="ignore")


def find_matching_resource_plan_row(
    existing_df: pd.DataFrame,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Existing row for the same assignment: prefer source_airtable_record_id in scope,
    else SQL business key (person + period).
    """
    scoped = _scope_resource_plan_df(
        existing_df,
        project_code=payload.get("project_code", ""),
        month_key=payload.get("month_key", ""),
        crew_code=payload.get("crew_code", ""),
    )
    if scoped.empty:
        return None

    source = _safe_str(payload.get("source_airtable_record_id"))
    if source and "source_airtable_record_id" in scoped.columns:
        hit = scoped[scoped["source_airtable_record_id"].map(_safe_str) == source]
        if not hit.empty:
            return hit.iloc[0].to_dict()

    wanted = resource_plan_business_key(
        project_code=payload.get("project_code"),
        month_key=payload.get("month_key"),
        crew_code=payload.get("crew_code"),
        person_id=payload.get("person_id"),
        person_name=payload.get("person_name"),
        effective_from=payload.get("effective_from"),
        effective_to=payload.get("effective_to"),
    )
    for rec in scoped.to_dict(orient="records"):
        got = resource_plan_business_key(
            project_code=rec.get("project_code"),
            month_key=rec.get("month_key"),
            crew_code=rec.get("crew_code"),
            person_id=rec.get("person_id"),
            person_name=rec.get("person_name"),
            effective_from=rec.get("effective_from"),
            effective_to=rec.get("effective_to"),
        )
        if got == wanted:
            return rec
    return None


def resolve_assignment_plan_ui_status(
    existing_df: pd.DataFrame,
    assignment_row: dict[str, Any] | pd.Series,
    *,
    project_code: str,
    month_key: str,
    crew_code: str,
) -> dict[str, str]:
    """UI-only status of a current-month assignment vs existing resource-plan rows."""
    if isinstance(assignment_row, pd.Series):
        assignment_row = assignment_row.to_dict()
    scoped = _scope_resource_plan_df(
        existing_df,
        project_code=project_code,
        month_key=month_key,
        crew_code=crew_code,
    )
    if scoped.empty:
        return {"code": PLAN_UI_NOT_ADDED, "label_ru": PLAN_UI_STATUS_RU[PLAN_UI_NOT_ADDED]}

    source = _safe_str(assignment_row.get("airtable_record_id"))
    person = _safe_str(assignment_row.get("full_name_ru"))
    matches = scoped
    if source and "source_airtable_record_id" in scoped.columns:
        by_source = scoped[scoped["source_airtable_record_id"].map(_safe_str) == source]
        if not by_source.empty:
            matches = by_source
        else:
            matches = scoped[scoped["person_name"].map(_safe_str) == person]
    else:
        matches = scoped[scoped["person_name"].map(_safe_str) == person]
    if matches.empty:
        return {"code": PLAN_UI_NOT_ADDED, "label_ru": PLAN_UI_STATUS_RU[PLAN_UI_NOT_ADDED]}

    statuses = {
        normalize_resource_status(v) for v in matches["resource_status"].tolist()
    }
    if STATUS_APPROVED in statuses:
        code = PLAN_UI_APPROVED
    elif STATUS_DRAFT in statuses:
        code = PLAN_UI_DRAFT
    elif STATUS_REJECTED in statuses:
        code = PLAN_UI_REJECTED
    else:
        code = PLAN_UI_NOT_ADDED
    return {"code": code, "label_ru": PLAN_UI_STATUS_RU[code]}


def build_draft_payload_from_current_month_assignment(
    row: dict[str, Any] | pd.Series,
    *,
    project_code: str,
    month_key: str,
    crew_code: str,
) -> dict[str, Any]:
    """
    Map one current-month MLS assignment to a DRAFT resource-plan payload.
    Raises ValueError if required fields cannot be determined safely.
    Does not approve. Does not invent dates or hours.
    """
    if isinstance(row, pd.Series):
        row = row.to_dict()

    person = _safe_str(row.get("full_name_ru"))
    if not person:
        raise ValueError("нет ФИО")

    raw_hours = row.get("direct_hours_month")
    if raw_hours is None or (isinstance(raw_hours, float) and pd.isna(raw_hours)):
        raise ValueError("нет Direct_Hours_Month")
    hours = to_num(raw_hours, default=-1.0)
    if hours < 0:
        raise ValueError("Direct_Hours_Month должен быть >= 0")

    effective_from, effective_to = current_month_assignment_dates(row)
    if not effective_from or not effective_to:
        raise ValueError("нет безопасных дат available (effective_from / effective_to)")

    month_label = _safe_str(row.get("month_key"))
    person_id = _safe_str(row.get("person_id")) or None
    return build_plan_line_payload(
        project_code=project_code,
        month_key=month_key,
        crew_code=crew_code,
        person_name=person,
        confirmed_available_hours=hours,
        resource_status=STATUS_DRAFT,
        person_id=person_id,
        role=_safe_str(row.get("role")) or None,
        effective_from=effective_from,
        effective_to=effective_to,
        planned_shift_hours=None,
        source_airtable_record_id=_safe_str(row.get("airtable_record_id")) or None,
        comment=(
            f"Черновик из кадрового плана ({month_label}); "
            "не является утверждённой мощностью"
        ),
    )


def create_draft_resource_plan_from_selection(
    roster_rows: pd.DataFrame,
    *,
    selected_indices: list[int] | tuple[int, ...] | None,
    project_code: str,
    month_key: str,
    crew_code: str,
    roster_mode: str,
    existing_plan_df: pd.DataFrame | None = None,
    write_fn=None,
) -> dict[str, Any]:
    """
    Create one DRAFT resource-plan row per selected current-month assignment.
    No APPROVE. Duplicate-safe. Partial success without rollback.
    Inject write_fn in tests; default is upsert_resource_plan_line.
    """
    empty = {
        "created_count": 0,
        "skipped_count": 0,
        "error_count": 0,
        "created": [],
        "skipped": [],
        "errors": [],
        "created_hours": 0.0,
        "auto_approve": False,
        "writes": False,
    }
    if roster_mode != ROSTER_MODE_CURRENT_MONTH:
        empty["error_count"] = 1
        empty["errors"] = [
            {
                "person_name": "",
                "reason": BATCH_SKIP_FALLBACK,
                "message": (
                    "Массовое создание DRAFT доступно только для состава текущего месяца. "
                    "Исторические часы fallback не переносятся."
                ),
            }
        ]
        return empty

    indices = [int(i) for i in (selected_indices or [])]
    if roster_rows is None or roster_rows.empty or not indices:
        empty["error_count"] = 1
        empty["errors"] = [
            {
                "person_name": "",
                "reason": BATCH_SKIP_EMPTY,
                "message": "Не выбран ни один человек.",
            }
        ]
        return empty

    scoped = roster_rows.reset_index(drop=True)
    existing = existing_plan_df if existing_plan_df is not None else empty_plan_df()
    writer = write_fn or upsert_resource_plan_line
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    working = existing.copy() if not existing.empty else empty_plan_df()

    for idx in indices:
        if idx < 0 or idx >= len(scoped):
            errors.append(
                {
                    "person_name": "",
                    "reason": BATCH_SKIP_VALIDATION,
                    "message": f"Некорректный индекс выбора: {idx}",
                }
            )
            continue
        row = scoped.iloc[idx]
        person = _safe_str(row.get("full_name_ru"))
        try:
            payload = build_draft_payload_from_current_month_assignment(
                row,
                project_code=project_code,
                month_key=month_key,
                crew_code=crew_code,
            )
        except ValueError as exc:
            errors.append(
                {
                    "person_name": person,
                    "reason": BATCH_SKIP_VALIDATION,
                    "message": str(exc),
                }
            )
            continue

        match = find_matching_resource_plan_row(working, payload)
        if match is not None:
            status = normalize_resource_status(match.get("resource_status"))
            if status == STATUS_DRAFT:
                skipped.append(
                    {
                        "person_name": person,
                        "reason": BATCH_SKIP_ALREADY_DRAFT,
                        "message": "Уже добавлен как черновик",
                        "hours": to_num(match.get("confirmed_available_hours")),
                    }
                )
            elif status == STATUS_APPROVED:
                skipped.append(
                    {
                        "person_name": person,
                        "reason": BATCH_SKIP_ALREADY_APPROVED,
                        "message": "Уже утверждён",
                        "hours": to_num(match.get("confirmed_available_hours")),
                    }
                )
            else:
                skipped.append(
                    {
                        "person_name": person,
                        "reason": BATCH_SKIP_REJECTED,
                        "message": (
                            "Отклонён — повторное создание не выполняется автоматически"
                        ),
                        "hours": to_num(match.get("confirmed_available_hours")),
                    }
                )
            continue

        result = writer(payload)
        if result and result.get("ok"):
            row_out = result.get("row") or payload
            created.append(
                {
                    "person_name": person,
                    "hours": to_num(payload.get("confirmed_available_hours")),
                    "resource_status": STATUS_DRAFT,
                    "row": row_out,
                }
            )
            working = pd.concat(
                [working, pd.DataFrame([payload])],
                ignore_index=True,
            )
        else:
            errors.append(
                {
                    "person_name": person,
                    "reason": "write",
                    "message": (result or {}).get("error") or "Ошибка записи",
                }
            )

    created_hours = float(sum(item["hours"] for item in created))
    return {
        "created_count": len(created),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "created_hours": created_hours,
        "auto_approve": False,
        "writes": len(created) > 0,
    }


def summarize_crew_resource_commitment(
    *,
    required_hours: float,
    approved_available_hours: float,
    approved_people_count: int,
    has_approved_plan: bool,
) -> dict[str, Any]:
    """
    Workbench coverage summary.

    Missing = no approved plan (not the same as zero confirmed hours).
    Primary metric = direct hours; headcount is secondary.
    """
    required = max(float(required_hours or 0.0), 0.0)
    approved = max(float(approved_available_hours or 0.0), 0.0)
    people = max(int(approved_people_count or 0), 0)

    if not has_approved_plan:
        status = WB_STATUS_MISSING
        coverage = None
        gap = None
    else:
        gap = approved - required
        coverage = (approved / required) if required > 0 else None
        if required > 0 and approved >= required:
            status = WB_STATUS_READY
        else:
            status = WB_STATUS_DEFICIT

    return {
        "required_hours": required,
        "approved_available_hours": approved,
        "approved_people_count": people,
        "has_approved_plan": bool(has_approved_plan),
        "hours_gap": gap,
        "coverage": coverage,
        "coverage_pct": (coverage * 100.0) if coverage is not None else None,
        "status_code": status,
        "status_ru": WB_STATUS_RU[status],
    }


def preview_capacity_after_hours_delta(
    *,
    required_hours: float,
    current_approved_hours: float,
    current_approved_people: int,
    has_approved_plan: bool,
    add_hours: float,
    add_new_person: bool = True,
) -> dict[str, Any]:
    """
    Non-writing preview: what coverage would be after approving add_hours.
    Does not touch DB.
    """
    add = max(float(add_hours or 0.0), 0.0)
    current = max(float(current_approved_hours or 0.0), 0.0)
    people = max(int(current_approved_people or 0), 0)
    projected_hours = current + add
    projected_people = people + (1 if add_new_person and add > 0 else 0)
    projected_has_plan = bool(has_approved_plan) or add > 0 or projected_hours > 0
    # If adding hours to approve, preview assumes a plan will exist
    if add > 0:
        projected_has_plan = True
    summary = summarize_crew_resource_commitment(
        required_hours=required_hours,
        approved_available_hours=projected_hours,
        approved_people_count=projected_people,
        has_approved_plan=projected_has_plan,
    )
    return {
        "current_approved_hours": current,
        "add_hours": add,
        "projected_approved_hours": projected_hours,
        "projected_people": projected_people,
        **summary,
        "writes": False,
    }


def update_draft_resource_plan_line(
    resource_plan_line_id: str,
    *,
    person_name: str | None = None,
    role: str | None = None,
    effective_from: str | None = None,
    effective_to: str | None = None,
    confirmed_available_hours: float | None = None,
    comment: str | None = None,
    existing_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Edit DRAFT only. Scope (project/month/crew) is preserved from existing row.
    APPROVED/REJECTED → rejected (read-only policy).
    """
    line_id = _safe_str(resource_plan_line_id)
    if not line_id:
        return {"ok": False, "error": "resource_plan_line_id обязателен", "row": None}

    row = existing_row
    if row is None:
        try:
            resp = (
                supabase.table(TABLE)
                .select("*")
                .eq("resource_plan_line_id", line_id)
                .limit(1)
                .execute()
            )
            row = (resp.data or [None])[0]
        except Exception as exc:  # noqa: BLE001
            msg = f"{type(exc).__name__}: {exc}"
            _set_error(msg)
            return {"ok": False, "error": msg, "row": None}

    if not row:
        return {"ok": False, "error": "Строка не найдена", "row": None}

    if not is_resource_line_editable(row.get("resource_status")):
        return {
            "ok": False,
            "error": "Редактирование разрешено только для статуса Черновик (DRAFT)",
            "row": None,
        }

    hours = (
        to_num(confirmed_available_hours)
        if confirmed_available_hours is not None
        else to_num(row.get("confirmed_available_hours"))
    )
    payload = {
        "resource_plan_line_id": line_id,
        "project_code": row.get("project_code"),
        "month_key": row.get("month_key"),
        "crew_code": row.get("crew_code"),
        "person_id": row.get("person_id"),
        "person_name": person_name if person_name is not None else row.get("person_name"),
        "role": role if role is not None else row.get("role"),
        "effective_from": effective_from if effective_from is not None else row.get("effective_from"),
        "effective_to": effective_to if effective_to is not None else row.get("effective_to"),
        "confirmed_available_hours": hours,
        "resource_status": STATUS_DRAFT,
        "source_airtable_record_id": row.get("source_airtable_record_id"),
        "comment": comment if comment is not None else row.get("comment"),
        "created_at": row.get("created_at"),
    }
    return upsert_resource_plan_line(payload)
