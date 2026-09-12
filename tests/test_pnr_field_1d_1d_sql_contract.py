"""Static SQL contract checks for FIELD-1D.1D event work-scope context.

Does not connect to Supabase. Does not execute the migration or RPC.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql" / "pnr_field_1d_1d_event_scope_context.sql"
MVP = ROOT / "sql" / "pnr_mvp_0_1.sql"

ALLOWED_INSERT_TABLES = frozenset(
    {
        "public.pnr_execution_events",
        "public.pnr_event_measurements",
        "public.pnr_event_blocked_details",
        "public.pnr_event_partial_details",
    }
)


def _strip_sql_comments(sql: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    without_line = re.sub(r"--.*?$", " ", without_block, flags=re.M)
    return without_line


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.lower())


class PnrField1d1dSqlContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = MIGRATION.read_text(encoding="utf-8")
        cls.body = _strip_sql_comments(cls.raw)
        cls.text = _norm(cls.body)
        cls.mvp = _norm(_strip_sql_comments(MVP.read_text(encoding="utf-8")))

    def test_migration_file_exists(self) -> None:
        self.assertTrue(MIGRATION.is_file(), MIGRATION)

    def test_transaction_wrapper(self) -> None:
        self.assertTrue(self.text.strip().startswith("begin;"))
        self.assertTrue(self.text.strip().endswith("commit;"))

    def test_work_scope_id_nullable_no_default(self) -> None:
        self.assertIn(
            "alter table public.pnr_execution_events add column work_scope_id uuid;",
            self.text,
        )
        self.assertNotRegex(
            self.text,
            r"add column work_scope_id uuid\s+not null",
        )
        self.assertNotRegex(
            self.text,
            r"add column work_scope_id uuid\s+default",
        )
        self.assertNotIn("work_scope_id uuid not null", self.text)

    def test_no_historical_event_backfill_or_update(self) -> None:
        self.assertNotRegex(self.text, r"\bupdate\s+")
        self.assertNotRegex(self.text, r"\bdelete\s+from\b")
        self.assertNotRegex(self.text, r"\btruncate\b")
        self.assertNotRegex(self.text, r"\bupsert\b")
        self.assertNotRegex(self.text, r"\bon\s+conflict\b")
        outside_fn = _norm(
            _strip_sql_comments(
                re.split(r"as\s+\$\$", self.raw, maxsplit=1, flags=re.I)[0]
            )
        )
        self.assertNotIn("insert into public.pnr_execution_events", outside_fn)

    def test_simple_work_scope_fk(self) -> None:
        self.assertIn(
            "constraint pnr_execution_events_work_scope_fk "
            "foreign key (work_scope_id) "
            "references public.pnr_work_scopes (work_scope_id) "
            "on delete no action",
            self.text,
        )

    def test_composite_match_simple_fk(self) -> None:
        self.assertIn(
            "constraint pnr_execution_events_work_scope_operation_fk "
            "foreign key (work_scope_id, operation_id) "
            "references public.pnr_work_scope_operations (work_scope_id, operation_id) "
            "match simple on delete no action",
            self.text,
        )
        self.assertNotIn("match full", self.text)

    def test_index_exists(self) -> None:
        self.assertIn(
            "create index idx_pnr_execution_events_work_scope_id "
            "on public.pnr_execution_events (work_scope_id)",
            self.text,
        )

    def test_existing_xor_preserved(self) -> None:
        self.assertIn("pnr_execution_events_operation_xor_chk", self.mvp)
        self.assertNotIn("drop constraint pnr_execution_events_operation_xor_chk", self.text)
        self.assertNotIn("drop constraint pnr_execution_events_status_pair_chk", self.text)
        self.assertNotIn("alter table public.pnr_operations", self.text)

    def test_no_status_pair_scope_check(self) -> None:
        self.assertNotIn("execution_status is not null", self.text)
        self.assertNotIn("pnr_execution_events_work_scope_required_chk", self.text)

    def test_rpc_replaced_same_signature(self) -> None:
        self.assertIn(
            "create or replace function "
            "public.create_pnr_structured_execution_event( p_payload jsonb )",
            self.text,
        )
        self.assertIn("returns jsonb", self.text)
        self.assertIn("language plpgsql", self.text)
        self.assertIn("security invoker", self.text)
        self.assertNotIn("security definer", self.text)

    def test_rpc_requires_work_scope_id(self) -> None:
        self.assertIn("v_work_scope_id := nullif(btrim(p_payload->>'work_scope_id'), '')::uuid", self.text)
        self.assertIn(
            "raise exception 'field-1d.1d work_scope_id is required'",
            self.text,
        )

    def test_rpc_rejects_missing_and_inactive_scope(self) -> None:
        self.assertIn("from public.pnr_work_scopes s", self.text)
        self.assertIn(
            "raise exception 'field-1d.1d work_scope_id does not exist'",
            self.text,
        )
        self.assertIn(
            "raise exception 'field-1d.1d work_scope_id is not an active work scope'",
            self.text,
        )
        self.assertIn("if v_scope_active is not true", self.text)

    def test_rpc_mapped_membership_distinguishes_missing_and_inactive(self) -> None:
        self.assertIn("from public.pnr_work_scope_operations m", self.text)
        self.assertIn("if v_operation_id is not null then", self.text)
        self.assertIn(
            "raise exception "
            "'field-1d.1d (work_scope_id, operation_id) is not a work-scope membership'",
            self.text,
        )
        self.assertIn(
            "raise exception "
            "'field-1d.1d (work_scope_id, operation_id) is not an active work-scope membership'",
            self.text,
        )
        self.assertIn("if v_membership_active is not true", self.text)
        self.assertIn("m.is_active", self.text)

    def test_rpc_unmapped_skips_bridge_when_operation_null(self) -> None:
        fn = self.text.split("create or replace function", 1)[-1]
        membership_block = fn.split("if v_operation_id is not null then", 1)[-1]
        membership_block = membership_block.split("if v_retry_of_event_id is not null then", 1)[0]
        self.assertIn("pnr_work_scope_operations", membership_block)
        before_membership = fn.split("if v_operation_id is not null then", 1)[0]
        self.assertNotIn("pnr_work_scope_operations", before_membership)
        self.assertIn("field-1d.1d work_scope_id is required", before_membership)

    def test_rpc_inserts_and_returns_work_scope_id(self) -> None:
        self.assertIn("insert into public.pnr_execution_events (", self.text)
        insert_block = self.text.split("insert into public.pnr_execution_events (", 1)[-1]
        insert_block = insert_block.split(") values (", 1)[0]
        self.assertIn("work_scope_id", insert_block)
        values = self.text.split("insert into public.pnr_execution_events (", 1)[-1]
        values = values.split(") values (", 1)[-1]
        values = values.split(");", 1)[0]
        self.assertIn("v_work_scope_id", values)
        self.assertIn("'work_scope_id', v_work_scope_id", self.text)

    def test_sidecar_inserts_unchanged(self) -> None:
        tables = re.findall(r"insert\s+into\s+([a-z0-9_.]+)", self.text)
        self.assertEqual(set(tables), ALLOWED_INSERT_TABLES)
        self.assertIn("insert into public.pnr_event_measurements", self.text)
        self.assertIn("insert into public.pnr_event_blocked_details", self.text)
        self.assertIn("insert into public.pnr_event_partial_details", self.text)

    def test_retry_scope_law(self) -> None:
        self.assertIn(
            "raise exception "
            "'field-1d.1d retry work_scope_id must match the prior event'",
            self.text,
        )
        self.assertIn(
            "if v_prior_work_scope_id is not null "
            "and v_prior_work_scope_id is distinct from v_work_scope_id",
            self.text,
        )
        self.assertNotRegex(self.text, r"update\s+public\.pnr_execution_events")

    def test_execute_privilege_service_role_only(self) -> None:
        self.assertIn(
            "revoke all on function "
            "public.create_pnr_structured_execution_event(jsonb) from public",
            self.text,
        )
        self.assertIn(
            "revoke all on function "
            "public.create_pnr_structured_execution_event(jsonb) from anon",
            self.text,
        )
        self.assertIn(
            "revoke all on function "
            "public.create_pnr_structured_execution_event(jsonb) from authenticated",
            self.text,
        )
        self.assertIn(
            "grant execute on function "
            "public.create_pnr_structured_execution_event(jsonb) to service_role",
            self.text,
        )
        self.assertNotRegex(self.text, r"grant execute[^;]*to authenticated")
        self.assertNotRegex(self.text, r"grant execute[^;]*to anon")
        self.assertNotRegex(self.text, r"grant execute[^;]*to public")

    def test_no_table_grant_or_policy_changes(self) -> None:
        self.assertNotRegex(self.text, r"grant\s+[^;]*on table")
        self.assertNotRegex(self.text, r"revoke\s+[^;]*on table")
        self.assertNotIn("create policy", self.text)
        self.assertNotIn("create trigger", self.text)
        self.assertNotIn("enable row level security", self.text)

    def test_no_professional_catalog_seed(self) -> None:
        self.assertNotIn("insert into public.pnr_work_scopes", self.text)
        self.assertNotIn("insert into public.pnr_operations", self.text)
        self.assertNotIn("insert into public.pnr_work_scope_operations", self.text)
        self.assertNotIn("meas-001", self.text)
        self.assertNotIn("п-1.1", self.text)
        self.assertNotIn("п-1.2", self.text)


if __name__ == "__main__":
    unittest.main()
