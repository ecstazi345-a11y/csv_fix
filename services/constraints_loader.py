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
    while True:
        response = (
            client.table(table)
            .select("*")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = list(response.data or [])
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows
