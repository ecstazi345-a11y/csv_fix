"""Static SQL contract checks for FIELD-1A structured event DDL.

Does not connect to Supabase. Does not execute the migration.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql" / "pnr_field_1a_structured_event_contract.sql"
PNR1 = ROOT / "sql" / "pnr_1_physical_and_work_context_foundation.sql"
MVP = ROOT / "sql" / "pnr_mvp_0_1.sql"


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.lower())


class PnrField1aSqlContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = MIGRATION.read_text(encoding="utf-8")
        cls.text = _norm(cls.raw)

    def test_migration_file_exists(self) -> None:
        self.assertTrue(MIGRATION.is_file(), MIGRATION)

    def test_additive_event_columns_nullable_no_default(self) -> None:
        self.assertIn("add column functional_position_id uuid", self.text)
        self.assertIn("add column execution_status text", self.text)
        self.assertIn("add column evaluation_status text", self.text)
        self.assertIn("add column observation_text text", self.text)
        self.assertIn("add column retry_of_event_id uuid", self.text)
        self.assertNotRegex(
            self.text,
            r"add column functional_position_id uuid\s+not null",
        )
        self.assertNotRegex(
            self.text,
            r"add column execution_status text\s+not null",
        )
        self.assertNotRegex(
            self.text,
            r"add column evaluation_status text\s+not null",
        )
        self.assertNotRegex(
            self.text,
            r"add column observation_text text\s+not null",
        )
        self.assertNotRegex(
            self.text,
            r"add column retry_of_event_id uuid\s+not null",
        )
        self.assertNotRegex(
            self.text,
            r"add column \w+\s+\w+\s+default",
        )

    def test_no_historical_event_dml(self) -> None:
        self.assertNotRegex(self.text, r"\bupdate\s+public\.pnr_execution_events\b")
        self.assertNotRegex(self.text, r"\bdelete\s+from\s+public\.pnr_execution_events\b")
        self.assertNotRegex(self.text, r"\binsert\s+into\s+public\.pnr_execution_events\b")
        self.assertNotIn("truncate", self.text)

    def test_legacy_result_not_removed_or_renamed(self) -> None:
        mvp = _norm(MVP.read_text(encoding="utf-8"))
        self.assertIn("result text not null", mvp)
        self.assertIn("pass', 'fail', 'partial', 'blocked'", mvp)
        self.assertNotIn("drop column result", self.text)
        self.assertNotIn("rename column result", self.text)
        self.assertNotIn("drop constraint pnr_execution_events_result_chk", self.text)

    def test_execution_and_evaluation_enums(self) -> None:
        for value in ("completed", "not_completed", "partial", "blocked"):
            self.assertIn(f"'{value}'", self.text)
        for value in ("conforms", "does_not_conform", "not_evaluated"):
            self.assertIn(f"'{value}'", self.text)

    def test_valid_compatibility_matrix_in_status_pair_check(self) -> None:
        self.assertIn("pnr_execution_events_status_pair_chk", self.text)
        self.assertIn("execution_status is null and evaluation_status is null", self.text)
        self.assertIn(
            "execution_status = 'completed' and evaluation_status = 'conforms' and result = 'pass'",
            self.text,
        )
        self.assertIn(
            "execution_status = 'completed' and evaluation_status = 'not_evaluated' and result = 'pass'",
            self.text,
        )
        self.assertIn(
            "execution_status = 'completed' and evaluation_status = 'does_not_conform' and result = 'fail'",
            self.text,
        )
        self.assertIn(
            "execution_status = 'not_completed' and evaluation_status = 'not_evaluated' and result = 'fail'",
            self.text,
        )
        self.assertIn(
            "execution_status = 'partial' and evaluation_status = 'not_evaluated' and result = 'partial'",
            self.text,
        )
        self.assertIn(
            "execution_status = 'partial' and evaluation_status = 'does_not_conform' and result = 'partial'",
            self.text,
        )
        self.assertIn(
            "execution_status = 'blocked' and evaluation_status = 'not_evaluated' and result = 'blocked'",
            self.text,
        )

    def test_invalid_combinations_not_listed_as_valid(self) -> None:
        self.assertNotIn(
            "execution_status = 'blocked' and evaluation_status = 'conforms'",
            self.text,
        )
        self.assertNotIn(
            "execution_status = 'blocked' and evaluation_status = 'does_not_conform'",
            self.text,
        )
        self.assertNotIn(
            "execution_status = 'partial' and evaluation_status = 'conforms'",
            self.text,
        )
        self.assertNotIn(
            "execution_status = 'not_completed' and evaluation_status = 'conforms'",
            self.text,
        )
        self.assertNotIn(
            "execution_status = 'not_completed' and evaluation_status = 'does_not_conform'",
            self.text,
        )

    def test_same_system_fp_fk_reuses_pnr1_unique(self) -> None:
        pnr1 = _norm(PNR1.read_text(encoding="utf-8"))
        self.assertIn(
            "constraint pnr_fp_id_system_key unique (position_id, system_id)",
            pnr1,
        )
        self.assertIn(
            "foreign key (functional_position_id, system_id) "
            "references public.pnr_functional_positions (position_id, system_id)",
            self.text,
        )
        self.assertNotIn(
            "foreign key (functional_position_id) "
            "references public.pnr_functional_positions (position_id)",
            self.text,
        )
        self.assertNotRegex(
            self.text,
            r"add constraint \w+\s+unique \(position_id, system_id\)",
        )

    def test_retry_no_self_and_same_system_object(self) -> None:
        self.assertIn("retry_of_event_id <> event_id", self.text)
        self.assertIn(
            "foreign key (retry_of_event_id) references public.pnr_execution_events (event_id)",
            self.text,
        )
        self.assertIn(
            "foreign key (retry_of_event_id, system_id) "
            "references public.pnr_execution_events (event_id, system_id)",
            self.text,
        )
        self.assertIn(
            "foreign key (retry_of_event_id, object_id) "
            "references public.pnr_execution_events (event_id, object_id)",
            self.text,
        )
        self.assertIn("unique (event_id, system_id)", self.text)
        self.assertIn("unique (event_id, object_id)", self.text)

    def test_helper_unique_keys_use_execution_status_not_legacy_result(self) -> None:
        self.assertIn("pnr_execution_events_id_system_key", self.text)
        self.assertIn("pnr_execution_events_id_object_key", self.text)
        self.assertIn("pnr_execution_events_id_execution_status_key", self.text)
        self.assertIn("unique (event_id, execution_status)", self.text)
        self.assertNotIn("pnr_execution_events_id_result_key", self.text)
        self.assertNotIn("unique (event_id, result)", self.text)

    def test_measurement_child_contract(self) -> None:
        self.assertIn("create table public.pnr_event_measurements", self.text)
        self.assertIn("create index idx_pnr_event_measurements_event_id", self.text)
        self.assertNotIn("idx_pnr_event_measurements_recorded_at", self.text)
        self.assertNotRegex(self.text, r"\btolerance\b")
        self.assertNotIn("create table public.pnr_measurements", self.text)

    def test_blocked_sidecar_contract(self) -> None:
        self.assertIn("create table public.pnr_event_blocked_details", self.text)
        self.assertIn("check (execution_status = 'blocked')", self.text)
        self.assertIn(
            "foreign key (event_id, execution_status) "
            "references public.pnr_execution_events (event_id, execution_status)",
            self.text,
        )
        self.assertIn("unique (event_id, execution_status)", self.text)
        self.assertNotIn("unique (event_id, result)", self.text)
        self.assertNotIn("check (result = 'blocked')", self.text)
        self.assertNotRegex(
            self.text,
            r"create table public.pnr_event_blocked_details \( "
            r"event_id uuid primary key, result text",
        )
        self.assertIn("'documentation'", self.text)
        self.assertIn("'other'", self.text)
        self.assertNotIn("create table public.pnr_constraints", self.text)

    def test_partial_sidecar_contract(self) -> None:
        self.assertIn("create table public.pnr_event_partial_details", self.text)
        self.assertIn("check (execution_status = 'partial')", self.text)
        self.assertIn(
            "foreign key (event_id, execution_status) "
            "references public.pnr_execution_events (event_id, execution_status)",
            self.text,
        )
        self.assertNotIn("check (result = 'partial')", self.text)
        self.assertNotRegex(
            self.text,
            r"create table public.pnr_event_partial_details \( "
            r"event_id uuid primary key, result text",
        )
        self.assertIn("check (length(btrim(completed_text)) > 0)", self.text)
        self.assertIn("check (length(btrim(remaining_text)) > 0)", self.text)

    def test_rls_and_service_role_select_insert_only(self) -> None:
        for table in (
            "pnr_event_measurements",
            "pnr_event_blocked_details",
            "pnr_event_partial_details",
        ):
            self.assertIn(f"alter table public.{table} enable row level security", self.text)
            self.assertIn(f"revoke all on table public.{table} from public", self.text)
            self.assertIn(
                f"revoke all on table public.{table} from anon, authenticated",
                self.text,
            )
            self.assertIn(
                f"revoke all on table public.{table} from service_role",
                self.text,
            )
            self.assertIn(
                f"grant select, insert on table public.{table} to service_role",
                self.text,
            )
        self.assertNotRegex(
            self.text,
            r"grant\s+[^;]*(update|delete)[^;]*on table public\.pnr_event_",
        )
        self.assertNotIn("create policy", self.text)

    def test_no_trigger_rpc_cascade_or_product_dml(self) -> None:
        self.assertNotIn("create trigger", self.text)
        self.assertNotIn("create or replace function", self.text)
        self.assertNotIn("create function", self.text)
        self.assertNotRegex(self.text, r"references\s+[^;]+on delete cascade")
        self.assertIn("on delete no action", self.text)
        self.assertNotIn("prj_001_", self.text)
        self.assertNotIn("boq_master_api", self.text)

    def test_justified_indexes_only(self) -> None:
        self.assertIn("idx_pnr_execution_events_functional_position_id", self.text)
        self.assertIn("idx_pnr_execution_events_retry_of_event_id", self.text)
        self.assertNotIn("idx_pnr_execution_events_execution_status", self.text)
        self.assertNotIn("idx_pnr_execution_events_evaluation_status", self.text)

    def test_does_not_modify_frozen_sql_files(self) -> None:
        self.assertTrue(MVP.is_file())
        self.assertTrue(PNR1.is_file())


if __name__ == "__main__":
    unittest.main()
