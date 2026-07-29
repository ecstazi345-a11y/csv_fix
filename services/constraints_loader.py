"""Paginated load for monthly_plan_constraints (PostgREST max ~1000 rows per request)."""

from __future__ import annotations

from typing import Any

from supabase import Client

DEFAULT_PAGE_SIZE = 1000


def fetch_all_constraints(
    client: Client,
    table: str,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[dict[str, Any]]:
    """Load all rows from a constraints table/view via .range() pagination."""
    if page_size < 1:
        raise ValueError("page_size must be >= 1")

    rows: list[dict[str, Any]] = []
    offset = 0
    page_num = 0
    import time as _time
    from services.perf_audit import log_supabase_query, perf_audit_enabled

    t_all = _time.perf_counter() if perf_audit_enabled() else 0.0
    while True:
        t_batch = _time.perf_counter()
        response = (
            client.table(table)
            .select("*")
            .range(offset, offset + page_size - 1)
            .execute()
        )
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
