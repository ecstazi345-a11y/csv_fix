"""Optional probe: does production Supabase already have PSAA history table?

Does NOT apply migrations. Does NOT write. Honest durability status only.
"""

from __future__ import annotations

from typing import Any


def probe_psaa_history_table() -> dict[str, Any]:
    """Return durability environment status for Supabase/PostgreSQL."""
    try:
        from services.supabase_client import supabase
    except Exception as exc:  # noqa: BLE001
        return {
            "postgres_durability_proof": "ENVIRONMENT_BLOCKED",
            "reason": f"supabase client unavailable: {type(exc).__name__}",
            "table": "psaa_shift_audit_history",
            "migration_applied": False,
        }
    try:
        # Selecting zero rows: success => table exists; failure => missing/blocked
        supabase.table("psaa_shift_audit_history").select("audit_id").limit(1).execute()
        return {
            "postgres_durability_proof": "TABLE_PRESENT_READ_OK",
            "table": "psaa_shift_audit_history",
            "migration_applied": True,
            "note": "Table reachable. Production writes still require explicit approval.",
        }
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        return {
            "postgres_durability_proof": "ENVIRONMENT_BLOCKED",
            "reason": msg[:240],
            "table": "psaa_shift_audit_history",
            "migration_applied": False,
            "migration_file": "sql/psaa_shift_audit_history_v1.sql",
            "note": "Migration not applied to this environment (expected for PSAA-02).",
        }
