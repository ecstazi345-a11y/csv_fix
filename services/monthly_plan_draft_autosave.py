"""Session status + Supabase finalize/clear helpers for 10B draft autosave."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st
from supabase import Client

V2_DRAFT_AUTOSAVE_AT_KEY = "v2_draft_autosave_at"
V2_DRAFT_AUTOSAVE_ERROR_KEY = "v2_draft_autosave_error"
V2_DRAFT_AUTOSAVE_ROW_COUNT_KEY = "v2_draft_autosave_row_count"
V2_DRAFT_AUTOSAVE_NOT_NEEDED_KEY = "v2_draft_autosave_not_needed"
V2_DRAFT_STATUS_CONVERTED = "CONVERTED"

TABLE_DRAFTS = "monthly_plan_drafts"
TABLE_DRAFT_LINES = "monthly_plan_draft_lines"


def record_autosave_success(row_count: int) -> None:
    st.session_state[V2_DRAFT_AUTOSAVE_AT_KEY] = datetime.now(timezone.utc).isoformat()
    st.session_state.pop(V2_DRAFT_AUTOSAVE_ERROR_KEY, None)
    st.session_state.pop(V2_DRAFT_AUTOSAVE_NOT_NEEDED_KEY, None)
    st.session_state[V2_DRAFT_AUTOSAVE_ROW_COUNT_KEY] = int(row_count)


def record_autosave_error(message: str) -> None:
    st.session_state[V2_DRAFT_AUTOSAVE_ERROR_KEY] = str(message or "").strip()[:500]
    st.session_state.pop(V2_DRAFT_AUTOSAVE_NOT_NEEDED_KEY, None)


def record_autosave_not_needed() -> None:
    st.session_state[V2_DRAFT_AUTOSAVE_NOT_NEEDED_KEY] = True
    st.session_state.pop(V2_DRAFT_AUTOSAVE_AT_KEY, None)
    st.session_state.pop(V2_DRAFT_AUTOSAVE_ERROR_KEY, None)
    st.session_state.pop(V2_DRAFT_AUTOSAVE_ROW_COUNT_KEY, None)


def clear_autosave_status() -> None:
    st.session_state.pop(V2_DRAFT_AUTOSAVE_AT_KEY, None)
    st.session_state.pop(V2_DRAFT_AUTOSAVE_ERROR_KEY, None)
    st.session_state.pop(V2_DRAFT_AUTOSAVE_ROW_COUNT_KEY, None)
    st.session_state.pop(V2_DRAFT_AUTOSAVE_NOT_NEEDED_KEY, None)


def get_autosave_status() -> dict[str, Any]:
    return {
        "saved_at": st.session_state.get(V2_DRAFT_AUTOSAVE_AT_KEY),
        "error": st.session_state.get(V2_DRAFT_AUTOSAVE_ERROR_KEY),
        "row_count": st.session_state.get(V2_DRAFT_AUTOSAVE_ROW_COUNT_KEY),
        "not_needed": bool(st.session_state.get(V2_DRAFT_AUTOSAVE_NOT_NEEDED_KEY)),
    }


def mark_draft_converted(write_client: Client, draft_id: str) -> None:
    draft_id = str(draft_id or "").strip()
    if not draft_id:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    write_client.table(TABLE_DRAFT_LINES).delete().eq("draft_id", draft_id).execute()
    write_client.table(TABLE_DRAFTS).update(
        {
            "draft_status": V2_DRAFT_STATUS_CONVERTED,
            "rows_count": 0,
            "updated_at": now_iso,
        }
    ).eq("draft_id", draft_id).execute()


def delete_draft_from_supabase(write_client: Client, draft_id: str) -> None:
    draft_id = str(draft_id or "").strip()
    if not draft_id:
        return
    write_client.table(TABLE_DRAFT_LINES).delete().eq("draft_id", draft_id).execute()
    write_client.table(TABLE_DRAFTS).delete().eq("draft_id", draft_id).execute()
