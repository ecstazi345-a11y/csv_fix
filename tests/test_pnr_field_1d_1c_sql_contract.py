"""Static SQL contract checks for FIELD-1D.1C work-scope operation bridge.

Does not connect to Supabase. Does not execute the migration.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql" / "pnr_field_1d_1c_work_scope_operation_bridge.sql"
TABLE = "public.pnr_work_scope_operations"


def _strip_sql_comments(sql: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    without_line = re.sub(r"--.*?$", " ", without_block, flags=re.M)
    return without_line


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.lower())


class PnrField1d1cSqlContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = MIGRATION.read_text(encoding="utf-8")
        cls.body = _strip_sql_comments(cls.raw)
        cls.text = _norm(cls.body)

    def test_migration_file_exists(self) -> None:
        self.assertTrue(MIGRATION.is_file(), MIGRATION)

    def test_table_created(self) -> None:
        self.assertIn("create table public.pnr_work_scope_operations", self.text)

    def test_work_scope_fk_not_null(self) -> None:
        self.assertIn("work_scope_id uuid not null", self.text)
        self.assertIn(
            "foreign key (work_scope_id) references public.pnr_work_scopes (work_scope_id)",
            self.text,
        )

    def test_operation_fk_not_null(self) -> None:
        self.assertIn("operation_id uuid not null", self.text)
        self.assertIn(
            "foreign key (operation_id) references public.pnr_operations (operation_id)",
            self.text,
        )

    def test_composite_primary_key(self) -> None:
        self.assertIn("primary key (work_scope_id, operation_id)", self.text)
        self.assertNotIn("primary key (work_scope_operation_id", self.text)
        self.assertNotIn("work_scope_operation_id uuid", self.text)

    def test_sequence_no_nullable(self) -> None:
        self.assertIn("sequence_no integer,", self.text)
        self.assertNotRegex(self.text, r"sequence_no integer not null")
        self.assertNotRegex(
            self.text,
            r"unique \(work_scope_id, sequence_no\)",
        )
        self.assertNotRegex(self.text, r"unique \(sequence_no\)")

    def test_is_active_default_true(self) -> None:
        self.assertIn("is_active boolean not null default true", self.text)

    def test_timestamps_exist(self) -> None:
        self.assertIn("created_at timestamptz not null default now()", self.text)
        self.assertIn("updated_at timestamptz not null default now()", self.text)

    def test_rls_enabled_zero_policies(self) -> None:
        self.assertIn(
            "alter table public.pnr_work_scope_operations enable row level security",
            self.text,
        )
        self.assertNotIn("create policy", self.text)
        self.assertNotIn("create policy", self.raw.lower())

    def test_public_anon_authenticated_revoked(self) -> None:
        self.assertIn(
            "revoke all on table public.pnr_work_scope_operations from public",
            self.text,
        )
        self.assertIn(
            "revoke all on table public.pnr_work_scope_operations from anon, authenticated",
            self.text,
        )
        self.assertNotRegex(self.text, r"grant\s+[^;]*on table public\.pnr_work_scope_operations to public")
        self.assertNotRegex(self.text, r"grant\s+[^;]*on table public\.pnr_work_scope_operations to anon")
        self.assertNotRegex(
            self.text,
            r"grant\s+[^;]*on table public\.pnr_work_scope_operations to authenticated",
        )

    def test_service_role_select_only(self) -> None:
        self.assertIn(
            "revoke all on table public.pnr_work_scope_operations from service_role",
            self.text,
        )
        self.assertIn(
            "grant select on table public.pnr_work_scope_operations to service_role",
            self.text,
        )
        self.assertNotIn(
            "grant select, insert on table public.pnr_work_scope_operations",
            self.text,
        )
        self.assertNotRegex(
            self.text,
            r"grant\s+[^;]*(insert|update|delete)[^;]*on table public\.pnr_work_scope_operations",
        )

    def test_backfill_from_existing_operations(self) -> None:
        self.assertIn("insert into public.pnr_work_scope_operations", self.text)
        self.assertIn("from public.pnr_operations o", self.text)
        self.assertIn("o.work_scope_id", self.text)
        self.assertIn("o.operation_id", self.text)
        self.assertIn("o.sequence_no", self.text)
        self.assertIn("o.is_active", self.text)
        self.assertIn("where o.work_scope_id is not null", self.text)
        self.assertIn("not exists", self.text)

    def test_backfill_does_not_hardcode_legacy_operation_uuid(self) -> None:
        self.assertNotRegex(
            self.body,
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        )
        insert_block = self.body.lower().split("insert into public.pnr_work_scope_operations", 1)[-1]
        self.assertNotIn("pnr-aut-003", insert_block)
        self.assertNotIn("aut_algorithms", insert_block)

    def test_does_not_mutate_operations_or_events(self) -> None:
        self.assertNotRegex(self.text, r"\bupdate\s+public\.pnr_operations\b")
        self.assertNotRegex(self.text, r"\bupdate\s+public\.pnr_execution_events\b")
        self.assertNotRegex(self.text, r"\bdelete\s+from\s+public\.pnr_operations\b")
        self.assertNotRegex(self.text, r"\bdelete\s+from\s+public\.pnr_execution_events\b")
        self.assertNotRegex(self.text, r"\binsert\s+into\s+public\.pnr_execution_events\b")
        self.assertNotIn("truncate", self.text)

    def test_does_not_alter_operations_work_scope_id(self) -> None:
        self.assertNotIn("alter table public.pnr_operations", self.text)
        self.assertNotIn("drop column work_scope_id", self.text)
        self.assertNotIn("alter column work_scope_id", self.text)
        self.assertNotIn("pnr_operations.work_scope_id drop not null", self.text)

    def test_no_event_work_scope_id_column(self) -> None:
        self.assertNotIn("add column work_scope_id", self.text)
        self.assertNotIn("alter table public.pnr_execution_events", self.text)

    def test_no_professional_p1_seed(self) -> None:
        self.assertNotIn("insert into public.pnr_work_scopes", self.text)
        self.assertNotIn("insert into public.pnr_operations", self.text)
        self.assertNotIn("insert into public.pnr_objects", self.text)
        self.assertNotIn("insert into public.pnr_functional_positions", self.text)
        self.assertNotIn("meas-001", self.text)
        self.assertNotIn("pnr-id-001", self.text)
        self.assertNotIn("insp-001", self.text)
        self.assertNotIn("предпусковая", self.text)
        self.assertNotIn("795-u-030", self.text)
        self.assertNotIn("п-1.1", self.text)
        self.assertNotIn("п-1.2", self.text)

    def test_no_object_applicability_or_event_context(self) -> None:
        create = self.text.split("comment on table")[0]
        self.assertNotIn("object_id", create)
        self.assertNotIn("system_id", create)
        self.assertNotIn("functional_position_id", create)
        self.assertNotIn("source_type", create)
        self.assertNotIn("source_reference", create)

    def test_no_triggers_functions_or_runtime(self) -> None:
        self.assertNotIn("create trigger", self.text)
        self.assertNotIn("create or replace function", self.text)
        self.assertNotIn("create function", self.text)
        self.assertNotIn("create policy", self.text)
        self.assertNotIn("langgraph", self.text)
        self.assertNotIn("boq_master_api", self.text)


if __name__ == "__main__":
    unittest.main()
