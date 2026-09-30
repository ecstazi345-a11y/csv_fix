"""Paginated / scoped load for monthly_plan_constraints (PostgREST max ~1000 rows/request)."""

from __future__ import annotations

import time
from typing import Any, Mapping, Optional, Sequence

from supabase import Client

from services.perf_audit import log_supabase_query, perf_audit_enabled

DEFAULT_PAGE_SIZE = 1000

# Columns Page 21 actually reads. Keep in sync with admission REQUIRED_COLUMNS.
DEFAULT_CONSTRAINT_COLUMNS: tuple[str, ...] = (
    "constraint_id",
    "line_id",
    "project_code",
    "month_key",
    "facility_building",
    "construction_discipline",
    "boq_code",
    "boq_name",
    "crew_id",
    "gate_layer",
    "responsible_department",
    "check_name",
    "check_status",
    "block_reason",
    "owner_name",
    "owner_department",
    "owner_role",
    "target_resolution_date",
    "resolution_status",
    "resolved_at",
    "resolved_by",
    "comment",
    "plan_value",
    "required_hours",
    "value_at_risk",
    "severity",
    "constraint_category",
    "root_cause",
    "created_at",
    "constraint_created_at",
    "updated_at",
    "updated_by",
    "last_action_at",
    "last_comment_at",
    "created_by",
    "days_open",
    "days_overdue",
    "is_overdue",
    "required_action",
    "effective_promised_date",
    "evidence_count",
    "days_since_promise",
)

METADATA_COLUMNS: tuple[str, ...] = (
    "month_key",
    "project_code",
    "responsible_department",
    "check_status",
    "construction_discipline",
    "facility_building",
)


def _perf_log(
    table: str,
    seconds: float,
    rows: int,
    *,
    pages: int = 1,
    columns: int | None = None,
    label: str | None = None,
) -> None:
    name = label or table
    if columns is not None:
        name = f"{name} cols={columns}"
    log_supabase_query(name, seconds, rows, pages=pages)


def fetch_all_constraints(
    client: Client,
    table: str,
    page_size: int = DEFAULT_PAGE_SIZE,
    columns: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Load all rows from a constraints table/view via .range() pagination."""
    rows, _stats = fetch_constraints_scoped(
        client,
        table,
        page_size=page_size,
        columns=columns,
    )
    return rows


def fetch_constraints_scoped(
    client: Client,
    table: str,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
    columns: Sequence[str] | None = None,
    month_key: str | None = None,
    project_code: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Paginated constraints read with optional server-side scope filters.

    Does NOT filter by department/check_status — package completeness requires
    all department checks for lines in the month/project scope.
    """
    if page_size < 1:
        raise ValueError("page_size must be >= 1")

    select_cols = ",".join(columns) if columns else "*"
    col_count = len(columns) if columns else None
    rows: list[dict[str, Any]] = []
    offset = 0
    page_num = 0
    network_s = 0.0
    decode_s = 0.0
    t_all = time.perf_counter()

    while True:
        query = client.table(table).select(select_cols)
        if month_key:
            query = query.eq("month_key", month_key)
        if project_code:
            query = query.eq("project_code", project_code)
        t_batch = time.perf_counter()
        response = query.range(offset, offset + page_size - 1).execute()
        batch_s = time.perf_counter() - t_batch
        network_s += batch_s
        t_dec = time.perf_counter()
        batch = list(response.data or [])
        decode_s += time.perf_counter() - t_dec
        page_num += 1
        if perf_audit_enabled():
            _perf_log(table, batch_s, len(batch), pages=page_num, columns=col_count)
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    total_s = time.perf_counter() - t_all
    if perf_audit_enabled() and page_num > 1:
        _perf_log(table, total_s, len(rows), pages=page_num, columns=col_count)

    stats = {
        "rows": len(rows),
        "pages": page_num,
        "network_s": network_s,
        "decode_s": decode_s,
        "total_s": total_s,
        "columns": col_count if col_count is not None else -1,
        "month_key": month_key or "",
        "project_code": project_code or "",
        "select": select_cols if columns else "*",
    }
    return rows, stats


def fetch_constraint_filter_metadata(
    client: Client,
    table: str,
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Light paginated read for distinct filter-option values (all months/projects)."""
    rows, stats = fetch_constraints_scoped(
        client,
        table,
        page_size=page_size,
        columns=METADATA_COLUMNS,
    )
    months: set[str] = set()
    projects: set[str] = set()
    departments: set[str] = set()
    check_statuses: set[str] = set()
    disciplines: set[str] = set()
    facilities: set[str] = set()
    for row in rows:
        mk = str(row.get("month_key") or "").strip()
        if mk:
            months.add(mk)
        pk = str(row.get("project_code") or "").strip()
        if pk:
            projects.add(pk)
        dept = str(row.get("responsible_department") or "").strip()
        if dept:
            departments.add(dept)
        st = str(row.get("check_status") or "").strip()
        if st:
            check_statuses.add(st)
        disc = str(row.get("construction_discipline") or "").strip()
        if disc:
            disciplines.add(disc)
        fac = str(row.get("facility_building") or "").strip()
        if fac:
            facilities.add(fac)
    return {
        "months": sorted(months),
        "projects": sorted(projects),
        "departments": sorted(departments),
        "check_statuses": sorted(check_statuses),
        "disciplines": sorted(disciplines),
        "facilities": sorted(facilities),
        "_stats": stats,
    }


def scope_filters_from_values(
    month: Any = None,
    project: Any = None,
) -> tuple[Optional[str], Optional[str]]:
    """Normalize UI filter values to server-side eq filters (None = no filter)."""

    def _norm(value: Any) -> Optional[str]:
        text = str(value or "").strip()
        if not text or text == "Все":
            return None
        return text

    return _norm(month), _norm(project)


def apply_client_scope_filter(
    rows: Sequence[Mapping[str, Any]],
    *,
    month_key: str | None = None,
    project_code: str | None = None,
) -> list[dict[str, Any]]:
    """Pandas-equivalent filter used by equivalence tests (old path)."""
    out: list[dict[str, Any]] = []
    for row in rows:
        if month_key and str(row.get("month_key") or "") != month_key:
            continue
        if project_code and str(row.get("project_code") or "") != project_code:
            continue
        out.append(dict(row))
    return out
