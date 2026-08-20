"""
EOS-SEC-1.1 SEC-STEP-1/2 — AgentExecutionContext + trusted read executor tests.
"""

from __future__ import annotations

import ast
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from security.agent_execution_context import (
    MPCA_ALLOWED_TOOLS,
    TOOL_LOAD_ADJUSTMENTS,
    TOOL_LOAD_SCOPE,
    AgentExecutionContext,
    ContextIssueError,
    issue_read_only_agent_context,
)
from security.sanitize import redact_sensitive_text
from security.trusted_read_executor import (
    CREDENTIAL_TRANSITIONAL_PRIVILEGED_READ,
    EVENT_READ_SUCCESS,
    EVENT_TOOL_DENIED,
    ToolPermissionError,
    execute_constructor_adjustments_read,
    execute_constructor_scope_read,
    validate_context_for_tool,
)


REPO = Path(__file__).resolve().parents[1]
AGENT_DIR = REPO / "agents" / "monthly_plan_constructor"


class ExecutionContextIssuerTests(unittest.TestCase):
    def test_01_unknown_agent_denied(self) -> None:
        with self.assertRaises(ContextIssueError) as ctx:
            issue_read_only_agent_context(
                agent_code="UNKNOWN_AGENT_XYZ",
                project_code="PRJ_001_БХК",
            )
        self.assertEqual(ctx.exception.code, "UNKNOWN_AGENT")

    def test_02_empty_project_denied(self) -> None:
        with self.assertRaises(ContextIssueError) as ctx:
            issue_read_only_agent_context(
                agent_code="MONTHLY_PLAN_CONSTRUCTOR",
                project_code="  ",
            )
        self.assertEqual(ctx.exception.code, "BLANK_PROJECT")

    def test_03_allowed_tools_not_caller_supplied(self) -> None:
        # Issuer signature has no allowed_tools parameter.
        import inspect

        sig = inspect.signature(issue_read_only_agent_context)
        self.assertNotIn("allowed_tools", sig.parameters)
        ctx = issue_read_only_agent_context(
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            project_code="PRJ_001_БХК",
        )
        self.assertEqual(ctx.allowed_tools, MPCA_ALLOWED_TOOLS)

    def test_04_write_allowed_false(self) -> None:
        ctx = issue_read_only_agent_context(
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            project_code="PRJ_001_БХК",
        )
        self.assertIs(ctx.write_allowed, False)

    def test_05_expired_context_denied(self) -> None:
        ctx = issue_read_only_agent_context(
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            project_code="PRJ_001_БХК",
            ttl_seconds=60,
        )
        expired = AgentExecutionContext(
            actor_id=ctx.actor_id,
            actor_type=ctx.actor_type,
            agent_code=ctx.agent_code,
            agent_version=ctx.agent_version,
            run_id=ctx.run_id,
            project_code=ctx.project_code,
            allowed_tools=ctx.allowed_tools,
            permission_tier=ctx.permission_tier,
            authorization_id=ctx.authorization_id,
            issued_at=ctx.issued_at,
            expires_at=(
                datetime.now(timezone.utc) - timedelta(seconds=5)
            ).isoformat(),
            security_policy_version=ctx.security_policy_version,
            write_allowed=False,
        )
        with self.assertRaises(ToolPermissionError) as err:
            validate_context_for_tool(expired, TOOL_LOAD_SCOPE)
        self.assertEqual(err.exception.code, "CONTEXT_EXPIRED")

    def test_06_unlisted_tool_denied(self) -> None:
        ctx = issue_read_only_agent_context(
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            project_code="PRJ_001_БХК",
        )
        with self.assertRaises(ToolPermissionError) as err:
            validate_context_for_tool(ctx, "execute_sql")
        self.assertEqual(err.exception.code, "TOOL_NOT_ALLOWED")
        self.assertEqual(err.exception.event["security_event"], EVENT_TOOL_DENIED)

    def test_07_project_mismatch_concept(self) -> None:
        """Executor uses context.project_code only — no alternate project arg."""
        import inspect
        from security import trusted_read_executor as ex

        for name in (
            "execute_constructor_scope_read",
            "execute_constructor_adjustments_read",
        ):
            sig = inspect.signature(getattr(ex, name))
            self.assertNotIn("project_code", sig.parameters)

    def test_12_no_credential_in_context(self) -> None:
        ctx = issue_read_only_agent_context(
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            project_code="PRJ_001_БХК",
        )
        blob = json.dumps(ctx.to_safe_dict(), ensure_ascii=False)
        for banned in ("SUPABASE_", "apikey", "Bearer", "password"):
            self.assertNotIn(banned.lower(), blob.lower())

    def test_20_malformed_context_none(self) -> None:
        with self.assertRaises(ToolPermissionError) as err:
            validate_context_for_tool(None, TOOL_LOAD_SCOPE)
        self.assertEqual(err.exception.code, "CONTEXT_MISSING")


class AgentLayerIsolationTests(unittest.TestCase):
    def test_08_09_agent_no_credential_or_client(self) -> None:
        banned_env = (
            "SUPABASE_SECRET_KEY",
            "SUPABASE_KEY",
            "SUPABASE_ANON_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
        )
        for rel in (
            "domain.py",
            "skills.py",
            "tools.py",
            "validators.py",
            "contracts.py",
            "runtime.py",
        ):
            src = (AGENT_DIR / rel).read_text(encoding="utf-8")
            for name in banned_env:
                self.assertNotIn(name, src)
            self.assertNotIn("os.getenv", src)
            self.assertNotIn("create_client", src)
            self.assertNotIn("from services.supabase_client", src)

    def test_18_no_write_methods_in_tools(self) -> None:
        src = (AGENT_DIR / "tools.py").read_text(encoding="utf-8").lower()
        for pat in ("insert(", "update(", "delete(", "upsert(", ".rpc("):
            self.assertNotIn(pat, src)


class ExecutorPolicyTests(unittest.TestCase):
    def test_10_column_allowlists_fixed(self) -> None:
        from services.monthly_plan_constructor_read_service import (
            ADJUSTMENT_SELECT_COLUMNS,
            PLAN_LINE_SELECT_COLUMNS,
            SCOPE_SELECT_COLUMNS,
        )

        manifest = json.loads(
            (
                AGENT_DIR / "specification" / "security_manifest.json"
            ).read_text(encoding="utf-8")
        )
        fields = manifest["read_fields_by_source"]
        self.assertEqual(list(SCOPE_SELECT_COLUMNS), fields["monthly_scope_picker_view"])
        self.assertEqual(
            list(ADJUSTMENT_SELECT_COLUMNS),
            fields["monthly_scope_manual_adjustments"],
        )
        self.assertEqual(
            list(PLAN_LINE_SELECT_COLUMNS),
            fields["monthly_plan_lines_v2"],
        )

    def test_11_adjustments_policy_explicit(self) -> None:
        manifest = json.loads(
            (
                AGENT_DIR / "specification" / "security_manifest.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest["credential_policy"]["load_constructor_adjustments"],
            "TRANSITIONAL_PRIVILEGED_READ",
        )
        self.assertIn(
            "monthly_scope_manual_adjustments",
            manifest["transitional_privileged_read_sources"],
        )
        # No silent fallback wording as the only path
        self.assertEqual(
            CREDENTIAL_TRANSITIONAL_PRIVILEGED_READ,
            "TRANSITIONAL_PRIVILEGED_READ",
        )

    def test_14_redaction(self) -> None:
        import os

        sentinel = "UNITTEST_FAKE_SECRET_VALUE_ABC_777"
        old = os.environ.get("SUPABASE_KEY")
        os.environ["SUPABASE_KEY"] = sentinel
        try:
            cleaned = redact_sensitive_text(
                f"Authorization: Bearer {sentinel} boom"
            )
            self.assertNotIn(sentinel, cleaned)
            self.assertIn("REDACTED", cleaned)
        finally:
            if old is None:
                os.environ.pop("SUPABASE_KEY", None)
            else:
                os.environ["SUPABASE_KEY"] = old

    def test_19_manifest_matches_registry(self) -> None:
        manifest = json.loads(
            (
                AGENT_DIR / "specification" / "security_manifest.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(set(manifest["allowed_tools"]), set(MPCA_ALLOWED_TOOLS))
        self.assertIs(manifest["execution_context_required"], True)
        self.assertIs(manifest["trusted_executor_required"], True)
        self.assertIs(manifest["project_scope_enforced"], True)
        self.assertIs(manifest["credential_exposed_to_agent"], False)
        self.assertEqual(manifest["security_policy_version"], "EOS-SEC-1.1")


class ExecutorLiveOptionalTests(unittest.TestCase):
    """Uses inject-free paths only when network available — unit-safe mocks via patching adapters."""

    def test_15_16_audit_events_with_mocked_adapter(self) -> None:
        import pandas as pd
        from unittest.mock import patch

        ctx = issue_read_only_agent_context(
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            project_code="PRJ_001_БХК",
        )
        fake_df = pd.DataFrame([{"project_code": "PRJ_001_БХК", "boq_code": "X"}])
        with patch(
            "services.monthly_plan_constructor_read_service.load_constructor_scope",
            return_value=(
                fake_df,
                {
                    "source": "monthly_scope_picker_view",
                    "error": None,
                    "row_count": 1,
                    "credential_env": "SUPABASE_KEY",
                    "select_columns": ["project_code"],
                },
            ),
        ):
            _df, meta = execute_constructor_scope_read(ctx)
        self.assertEqual(meta["audit_event"]["security_event"], EVENT_READ_SUCCESS)
        self.assertEqual(meta["credential_policy_code"], "PUBLISHABLE_READ")
        self.assertEqual(meta["project_code"], "PRJ_001_БХК")
        self.assertNotIn("SUPABASE_SECRET_KEY", json.dumps(meta["audit_event"]))

        with self.assertRaises(ToolPermissionError) as err:
            validate_context_for_tool(ctx, "delete_everything")
        self.assertEqual(err.exception.event["security_event"], EVENT_TOOL_DENIED)

    def test_13_audit_has_no_secret_values(self) -> None:
        import os
        import pandas as pd
        from unittest.mock import patch

        sentinel = "UNITTEST_AUDIT_SECRET_ZZZ_888"
        old = os.environ.get("SUPABASE_SECRET_KEY")
        os.environ["SUPABASE_SECRET_KEY"] = sentinel
        try:
            ctx = issue_read_only_agent_context(
                agent_code="MONTHLY_PLAN_CONSTRUCTOR",
                project_code="PRJ_001_БХК",
            )
            with patch(
                "services.monthly_plan_constructor_read_service.load_constructor_adjustments",
                return_value=(
                    pd.DataFrame(),
                    {
                        "source": "monthly_scope_manual_adjustments",
                        "error": None,
                        "row_count": 0,
                        "credential_env": "SUPABASE_SECRET_KEY",
                        "select_columns": [],
                    },
                ),
            ):
                _df, meta = execute_constructor_adjustments_read(ctx)
            blob = json.dumps(meta["audit_event"], ensure_ascii=False)
            self.assertNotIn(sentinel, blob)
            self.assertEqual(
                meta["credential_policy_code"],
                CREDENTIAL_TRANSITIONAL_PRIVILEGED_READ,
            )
        finally:
            if old is None:
                os.environ.pop("SUPABASE_SECRET_KEY", None)
            else:
                os.environ["SUPABASE_SECRET_KEY"] = old


if __name__ == "__main__":
    unittest.main()
