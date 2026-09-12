"""Static SQL contract checks for FIELD-1B structured write RPC.

Does not connect to Supabase. Does not execute the RPC.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RPC_SQL = ROOT / "sql" / "pnr_field_1b_structured_event_write.sql"
FIELD_1A = ROOT / "sql" / "pnr_field_1a_structured_event_contract.sql"

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


class PnrField1bSqlContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = RPC_SQL.read_text(encoding="utf-8")
        cls.body = _strip_sql_comments(cls.raw)
        cls.text = _norm(cls.body)

    def test_rpc_file_exists(self) -> None:
        self.assertTrue(RPC_SQL.is_file(), RPC_SQL)

    def test_expected_function_exists(self) -> None:
        self.assertIn(
            "create or replace function public.create_pnr_structured_execution_event( p_payload jsonb )",
            self.text,
        )
        self.assertIn("returns jsonb", self.text)
        self.assertIn("language plpgsql", self.text)

    def test_invoker_not_generic_definer_escalation(self) -> None:
        self.assertIn("security invoker", self.text)
        self.assertIn("set search_path = public", self.text)
        self.assertNotIn("security definer", self.text)

    def test_allowlisted_insert_tables_only(self) -> None:
        tables = re.findall(r"insert\s+into\s+([a-z0-9_.]+)", self.text)
        self.assertEqual(set(tables), ALLOWED_INSERT_TABLES)
        self.assertIn("insert into public.pnr_execution_events", self.text)
        self.assertIn("insert into public.pnr_event_measurements", self.text)
        self.assertIn("insert into public.pnr_event_blocked_details", self.text)
        self.assertIn("insert into public.pnr_event_partial_details", self.text)

    def test_parent_measurements_and_sidecars_present(self) -> None:
        self.assertIn("execution_status", self.text)
        self.assertIn("evaluation_status", self.text)
        self.assertIn("blocked_detail", self.text)
        self.assertIn("partial_detail", self.text)
        self.assertIn("jsonb_array_elements", self.text)

    def test_no_mutating_existing_rows(self) -> None:
        self.assertNotRegex(self.text, r"\bupdate\s+")
        self.assertNotRegex(self.text, r"\bdelete\s+from\b")
        self.assertNotRegex(self.text, r"\btruncate\b")
        self.assertNotRegex(self.text, r"\bupsert\b")
        self.assertNotRegex(self.text, r"\bon\s+conflict\b")

    def test_no_dynamic_sql_or_generic_executor(self) -> None:
        self.assertNotRegex(self.text, r"\bexecute\s+format\b")
        self.assertNotRegex(self.text, r"\bexecute\s+'")
        self.assertNotIn("format(", self.text)
        self.assertNotIn("pg_catalog", self.text)
        self.assertNotIn("dblink", self.text)

    def test_execute_privilege_service_role_only(self) -> None:
        self.assertIn(
            "revoke all on function public.create_pnr_structured_execution_event(jsonb) from public",
            self.text,
        )
        self.assertIn(
            "revoke all on function public.create_pnr_structured_execution_event(jsonb) from anon",
            self.text,
        )
        self.assertIn(
            "revoke all on function public.create_pnr_structured_execution_event(jsonb) from authenticated",
            self.text,
        )
        self.assertIn(
            "grant execute on function public.create_pnr_structured_execution_event(jsonb) to service_role",
            self.text,
        )
        self.assertNotRegex(self.text, r"grant execute[^;]*to authenticated")
        self.assertNotRegex(self.text, r"grant execute[^;]*to anon")
        self.assertNotRegex(self.text, r"grant execute[^;]*to public")

    def test_no_table_grant_broadening(self) -> None:
        self.assertNotRegex(self.text, r"grant\s+[^;]*on table")
        self.assertNotIn("create trigger", self.text)

    def test_no_agent_runtime_or_bhk(self) -> None:
        self.assertNotIn("agent runtime", self.text)
        self.assertNotIn("langgraph", self.text)
        self.assertNotIn("bhk", self.text)
        self.assertNotIn("boq_master_api", self.text)
        self.assertNotIn("monthly_plan", self.text)

    def test_server_side_function_scope(self) -> None:
        self.assertIn("as $$", self.text)
        self.assertIn("$$;", self.text)
        self.assertNotIn("begin;", self.text)

    def test_no_product_row_dml_outside_function(self) -> None:
        outside = _norm(_strip_sql_comments(re.split(r"as\s+\$\$", self.raw, maxsplit=1, flags=re.I)[0]))
        self.assertNotIn("insert into", outside)
        after = self.raw.rsplit("$$;", 1)[-1]
        after_text = _norm(_strip_sql_comments(after))
        self.assertNotIn("insert into", after_text)

    def test_does_not_modify_field_1a_file(self) -> None:
        self.assertTrue(FIELD_1A.is_file())
        self.assertNotEqual(RPC_SQL.resolve(), FIELD_1A.resolve())


if __name__ == "__main__":
    unittest.main()
