"""Streamlit-free READ adapter for PSAA — daily_progress_active only.

No writes. Credentials stay in infrastructure layer.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from security.sanitize import redact_sensitive_text, sanitize_read_error
from services.supabase_client import supabase

TABLE = "daily_progress_active"

SELECT_COLUMNS: tuple[str, ...] = (
    "airtable_record_id",
    "project_code",
    "work_date",
    "shift_type",
    "crew_id",
    "crew_size",
    "foreman",
    "facility_building",
    "construction_discipline",
    "boq",
    "boq_name",
    "unit_of_measure",
    "quantity_today",
    "direct_work_hours",
    "productive_work_hours",
    "idle_hours",
    "idle_reason",
    "operation_type",
    "operation_quantity",
    "operation_main_parameter",
    "operation_location",
    "operation_comment",
    "comment_foreman",
    "system_label",
    "iwp_id",
)


def load_shift_daily_progress_rows(
    *,
    project_code: str,
    crew_id: str,
    work_date: str,
    shift_type: Optional[str] = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    project = str(project_code or "").strip()
    crew = str(crew_id or "").strip()
    day = str(work_date or "").strip()
    if not project or not crew or not day:
        return pd.DataFrame(), {
            "error": "project_code, crew_id and work_date are required",
            "error_code": "INVALID_FILTER",
            "live_data_proof": "NOT_ATTEMPTED",
            "row_count": 0,
        }

    cols = ",".join(SELECT_COLUMNS)
    try:
        q = (
            supabase.table(TABLE)
            .select(cols)
            .eq("project_code", project)
            .eq("crew_id", crew)
            .eq("work_date", day)
        )
        st = str(shift_type or "").strip()
        if st:
            q = q.eq("shift_type", st)
        # Soft-deleted rows: exclude if column present in response
        data = q.limit(5000).execute().data or []
        df = pd.DataFrame(data)
        if not df.empty and "is_deleted" in df.columns:
            df = df[df["is_deleted"] != True].copy()  # noqa: E712
        return df, {
            "error": None,
            "row_count": int(len(df)),
            "source": TABLE,
            "live_data_proof": "OK",
            "filters": {
                "project_code": project,
                "crew_id": crew,
                "work_date": day,
                "shift_type": st or None,
            },
            "credential_env": "SUPABASE_KEY",
        }
    except Exception as exc:  # noqa: BLE001
        return pd.DataFrame(), {
            "error": sanitize_read_error(exc),
            "error_code": "READ_FAILED",
            "row_count": 0,
            "source": TABLE,
            "live_data_proof": "FAILED",
            "safe_message": redact_sensitive_text(str(exc)),
        }
