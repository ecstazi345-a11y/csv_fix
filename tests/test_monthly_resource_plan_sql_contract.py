"""Static SQL contract checks for Monthly Resource Plan security (R1.2.1)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "sql" / "monthly_resource_plan_r1.sql"
HOTFIX = ROOT / "sql" / "monthly_resource_plan_r1_security_hotfix.sql"
VERIFY = ROOT / "sql" / "monthly_resource_plan_r1_security_verify.sql"


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.lower())


class MonthlyResourcePlanSqlSecurityContractTests(unittest.TestCase):
    def test_migration_and_hotfix_files_exist(self) -> None:
        self.assertTrue(MIGRATION.is_file(), MIGRATION)
        self.assertTrue(HOTFIX.is_file(), HOTFIX)
        self.assertTrue(VERIFY.is_file(), VERIFY)

    def test_migration_explicit_revoke_anon_authenticated(self) -> None:
        text = _norm(MIGRATION.read_text(encoding="utf-8"))
        self.assertIn(
            "revoke all on table public.monthly_resource_plan_lines from anon, authenticated",
            text,
        )
        self.assertIn(
            "revoke all on table public.monthly_resource_capacity_v1 from anon, authenticated",
            text,
        )

    def test_migration_select_only_for_anon_authenticated_on_table(self) -> None:
        text = _norm(MIGRATION.read_text(encoding="utf-8"))
        self.assertIn(
            "grant select on table public.monthly_resource_plan_lines "
            "to anon, authenticated, service_role",
            text,
        )
        # Must not grant write to anon/authenticated
        self.assertNotRegex(
            text,
            r"grant\s+(insert|update|delete|[a-z,\s]*insert)[^;]*"
            r"on table public\.monthly_resource_plan_lines[^;]*\banon\b",
        )

    def test_migration_service_role_write_on_table(self) -> None:
        text = _norm(MIGRATION.read_text(encoding="utf-8"))
        self.assertIn(
            "grant select, insert, update, delete on table "
            "public.monthly_resource_plan_lines to service_role",
            text,
        )

    def test_migration_view_select_only(self) -> None:
        text = _norm(MIGRATION.read_text(encoding="utf-8"))
        self.assertIn(
            "grant select on table public.monthly_resource_capacity_v1 "
            "to anon, authenticated, service_role",
            text,
        )
        self.assertIn(
            "revoke insert, update, delete on table "
            "public.monthly_resource_capacity_v1 from anon, authenticated, "
            "service_role, public",
            text,
        )

    def test_hotfix_only_mrp_objects_and_exact_probe_delete(self) -> None:
        raw = HOTFIX.read_text(encoding="utf-8")
        text = _norm(raw)
        self.assertIn("monthly_resource_plan_lines", text)
        self.assertIn("monthly_resource_capacity_v1", text)
        self.assertIn(
            "revoke all on table public.monthly_resource_plan_lines from anon, authenticated",
            text,
        )
        self.assertIn(
            "grant select, insert, update, delete on table "
            "public.monthly_resource_plan_lines to service_role",
            text,
        )
        self.assertIn("fff1e853-ccc5-485b-8e61-cff5d28ea424", raw.lower())
        self.assertIn("project_code = '__nowrite__'", text)
        self.assertIn("month_key = '2099-01'", text)
        self.assertIn("crew_code = 'x'", text)
        self.assertIn("person_name = 'x'", text)
        self.assertIn("resource_status = 'draft'", text)
        self.assertIn("confirmed_available_hours = 0", text)
        self.assertNotIn("truncate", text)
        self.assertNotRegex(text, r"delete\s+from\s+public\.monthly_resource_plan_lines\s*;")

    def test_hotfix_does_not_touch_unrelated_product_tables(self) -> None:
        text = _norm(HOTFIX.read_text(encoding="utf-8"))
        forbidden = [
            "monthly_plan_lines_v2",
            "monthly_plan_capacity_v1",
            "monthly_labor_summary",
            "daily_progress",
            "crew_register",
        ]
        for name in forbidden:
            self.assertNotIn(name, text)

    def test_verify_is_readonly_and_covers_catalog(self) -> None:
        raw = VERIFY.read_text(encoding="utf-8")
        text = _norm(raw)
        # Forbid DML statements; privilege names in SELECTs are allowed.
        self.assertNotRegex(text, r"\b(insert into|update\s+\w|delete\s+from|truncate\s+)\b")
        self.assertIn("information_schema.role_table_grants", text)
        self.assertIn("pg_constraint", text)
        self.assertIn("pg_index", text)
        self.assertIn("idx_mrp_lines_business_key", text)
        self.assertIn("idx_mrp_lines_scope", text)
        self.assertIn("__nowrite__", text.lower())
        self.assertIn("monthly_resource_capacity_v1", text)


if __name__ == "__main__":
    unittest.main()
