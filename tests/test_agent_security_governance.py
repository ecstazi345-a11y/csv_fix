"""
Execution OS — Agent Security & Confidentiality governance tests.

Extensible: any agents/<name>/ package with runtime + specification
must ship security.md + security_manifest.json and satisfy EOS-SEC rules.
"""

from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_ROOT = REPO_ROOT / "agents"
SECURITY_ROOT = REPO_ROOT / "security"

REQUIRED_GLOBAL_DOCS = (
    "README.md",
    "agent_security_baseline.md",
    "trust_and_instruction_policy.md",
    "tool_and_permission_policy.md",
    "data_confidentiality_policy.md",
    "security_release_gate.md",
)

REQUIRED_MANIFEST_FIELDS = (
    "agent_code",
    "agent_name",
    "security_tier",
    "llm_enabled",
    "read_access",
    "write_access",
    "allowed_tools",
    "allowed_write_tools",
    "human_gate_required_for",
    "data_classes_allowed",
    "data_classes_forbidden",
    "untrusted_input_sources",
    "secrets_allowed_in_context",
    "external_network_access",
    "arbitrary_sql_allowed",
    "arbitrary_shell_allowed",
    "arbitrary_code_execution_allowed",
    "fail_closed",
    "trace_redaction_required",
    "kill_switch_required",
    "security_policy_version",
)

LLM_PROVIDER_MARKERS = (
    "openai",
    "anthropic",
    "yandexgpt",
    "gigachat",
    "langchain",
    "llama_index",
)

FORBIDDEN_TOOL_PATTERNS = (
    "execute_sql",
    "run_sql",
    "arbitrary_sql",
    "run_shell",
    "subprocess",
    "os.system",
    "execute_python",
    "eval(",
    "exec(",
    "arbitrary_http",
    "call_any_api",
)


def discover_agent_packages() -> list[Path]:
    """Agent packages that have both runtime module and specification/."""
    if not AGENTS_ROOT.is_dir():
        return []
    found: list[Path] = []
    for child in sorted(AGENTS_ROOT.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if child.name == "__pycache__":
            continue
        has_runtime = (child / "runtime.py").is_file()
        has_spec = (child / "specification").is_dir()
        if has_runtime and has_spec:
            found.append(child)
    return found


def load_manifest(agent_dir: Path) -> dict[str, Any]:
    path = agent_dir / "specification" / "security_manifest.json"
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise AssertionError(f"{path}: manifest must be a JSON object")
    return data


def _iter_py_files(agent_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in agent_dir.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        files.append(path)
    return files


def _source_blob(agent_dir: Path) -> str:
    parts: list[str] = []
    for path in _iter_py_files(agent_dir):
        parts.append(path.read_text(encoding="utf-8", errors="replace").lower())
    return "\n".join(parts)


def _imported_modules(agent_dir: Path) -> set[str]:
    names: set[str] = set()
    for path in _iter_py_files(agent_dir):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.name.split(".")[0].lower())
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0].lower())
    return names


class GlobalSecurityBaselineTests(unittest.TestCase):
    def test_global_security_docs_exist(self) -> None:
        self.assertTrue(SECURITY_ROOT.is_dir(), "security/ directory missing")
        for name in REQUIRED_GLOBAL_DOCS:
            path = SECURITY_ROOT / name
            self.assertTrue(path.is_file(), f"missing global security doc: {name}")
            self.assertGreater(path.stat().st_size, 50, f"{name} looks empty")

    def test_policy_version_declared_in_baseline(self) -> None:
        text = (SECURITY_ROOT / "agent_security_baseline.md").read_text(encoding="utf-8")
        self.assertIn("EOS-SEC-1.0", text)
        self.assertIn("MODEL IS NOT A SECURITY BOUNDARY", text)


class AgentSecurityGovernanceTests(unittest.TestCase):
    def test_at_least_one_agent_package(self) -> None:
        packages = discover_agent_packages()
        self.assertGreaterEqual(len(packages), 1, "expected MPCA agent package")

    def test_each_agent_has_security_artifacts(self) -> None:
        for agent_dir in discover_agent_packages():
            with self.subTest(agent=agent_dir.name):
                sec_md = agent_dir / "specification" / "security.md"
                sec_json = agent_dir / "specification" / "security_manifest.json"
                self.assertTrue(sec_md.is_file(), f"{agent_dir.name}: missing security.md")
                self.assertTrue(
                    sec_json.is_file(),
                    f"{agent_dir.name}: missing security_manifest.json",
                )

    def test_manifest_required_fields_and_consistency(self) -> None:
        for agent_dir in discover_agent_packages():
            with self.subTest(agent=agent_dir.name):
                manifest = load_manifest(agent_dir)
                for field in REQUIRED_MANIFEST_FIELDS:
                    self.assertIn(field, manifest, f"missing field {field}")

                self.assertTrue(
                    str(manifest.get("security_policy_version") or "").strip(),
                    "security_policy_version empty",
                )
                self.assertIs(manifest.get("fail_closed"), True, "fail_closed must be true")

                write_access = bool(manifest.get("write_access"))
                write_tools = manifest.get("allowed_write_tools")
                self.assertIsInstance(write_tools, list)
                if not write_access:
                    self.assertEqual(
                        write_tools,
                        [],
                        "write_access=false requires empty allowed_write_tools",
                    )

                self.assertIs(manifest.get("secrets_allowed_in_context"), False)
                self.assertIs(manifest.get("arbitrary_sql_allowed"), False)
                self.assertIs(manifest.get("arbitrary_shell_allowed"), False)
                self.assertIs(manifest.get("arbitrary_code_execution_allowed"), False)
                self.assertIs(manifest.get("trace_redaction_required"), True)

                allowed = manifest.get("allowed_tools")
                self.assertIsInstance(allowed, list)
                self.assertGreater(len(allowed), 0, "allowed_tools must be non-empty")

                if write_access:
                    self.assertIs(
                        manifest.get("kill_switch_required"),
                        True,
                        "write_access=true requires kill_switch_required=true",
                    )

    def test_llm_disabled_means_no_provider_imports(self) -> None:
        for agent_dir in discover_agent_packages():
            with self.subTest(agent=agent_dir.name):
                manifest = load_manifest(agent_dir)
                if manifest.get("llm_enabled") is not False:
                    continue
                imported = _imported_modules(agent_dir)
                blob = _source_blob(agent_dir)
                for marker in LLM_PROVIDER_MARKERS:
                    self.assertNotIn(
                        marker,
                        imported,
                        f"{agent_dir.name}: unexpected LLM import {marker}",
                    )
                    # Allow mention only inside comments/strings of security docs — not .py
                    # Soft check: import roots already covered; block common client constructors.
                    self.assertNotIn(f"import {marker}", blob)
                    self.assertNotIn(f"from {marker}", blob)

    def test_no_universal_sql_or_shell_in_tool_surface(self) -> None:
        for agent_dir in discover_agent_packages():
            with self.subTest(agent=agent_dir.name):
                manifest = load_manifest(agent_dir)
                tools_py = agent_dir / "tools.py"
                self.assertTrue(tools_py.is_file(), f"{agent_dir.name}: tools.py required")
                tools_src = tools_py.read_text(encoding="utf-8").lower()
                runtime_src = (agent_dir / "runtime.py").read_text(encoding="utf-8").lower()
                combined = tools_src + "\n" + runtime_src
                if not manifest.get("arbitrary_sql_allowed"):
                    for pat in ("execute_sql", "run_sql", "arbitrary_sql"):
                        self.assertNotIn(pat, combined)
                if not manifest.get("arbitrary_shell_allowed"):
                    for pat in ("run_shell", "subprocess", "os.system"):
                        self.assertNotIn(pat, combined)
                if not manifest.get("arbitrary_code_execution_allowed"):
                    for pat in ("execute_python", "eval(", "exec("):
                        self.assertNotIn(pat, combined)

    def test_mpca_tier0_profile(self) -> None:
        """Concrete expectations for current Constructor agent."""
        agent_dir = AGENTS_ROOT / "monthly_plan_constructor"
        self.assertTrue(agent_dir.is_dir())
        manifest = load_manifest(agent_dir)
        self.assertEqual(manifest["agent_code"], "MONTHLY_PLAN_CONSTRUCTOR")
        self.assertEqual(
            manifest["security_tier"],
            "TIER_0_READ_ONLY_DETERMINISTIC",
        )
        self.assertIs(manifest["llm_enabled"], False)
        self.assertIs(manifest["write_access"], False)
        self.assertEqual(manifest["allowed_write_tools"], [])
        self.assertEqual(
            set(manifest["allowed_tools"]),
            {
                "load_constructor_scope",
                "load_constructor_adjustments",
                "load_constructor_month_plan_lines",
            },
        )
        self.assertEqual(manifest["security_policy_version"], "EOS-SEC-1.1")
        self.assertIs(manifest.get("execution_context_required"), True)
        self.assertIs(manifest.get("credential_exposed_to_agent"), False)

    def test_security_md_mentions_model_not_boundary_or_tier(self) -> None:
        for agent_dir in discover_agent_packages():
            with self.subTest(agent=agent_dir.name):
                text = (agent_dir / "specification" / "security.md").read_text(
                    encoding="utf-8"
                )
                self.assertTrue(
                    "TIER_0" in text
                    or "TIER_1" in text
                    or "TIER_2" in text
                    or "security tier" in text.lower(),
                    "security.md should declare tier",
                )


class MpcaReadServiceHardeningTests(unittest.TestCase):
    """EOS-SEC-1.0 hardening checks specific to Constructor read surface."""

    def test_a_no_select_star(self) -> None:
        from services import monthly_plan_constructor_read_service as rs

        src = Path(rs.__file__).read_text(encoding="utf-8")
        self.assertNotIn('.select("*")', src)
        self.assertNotIn(".select('*')", src)
        self.assertNotIn('select("*")', src)

    def test_b_allowed_sources_fixed(self) -> None:
        from services.monthly_plan_constructor_read_service import (
            ADJUSTMENTS_TABLE,
            ALLOWED_READ_SOURCES,
            PLAN_LINES_TABLE,
            SCOPE_VIEW,
        )

        self.assertEqual(
            ALLOWED_READ_SOURCES,
            frozenset({SCOPE_VIEW, ADJUSTMENTS_TABLE, PLAN_LINES_TABLE}),
        )
        manifest = load_manifest(AGENTS_ROOT / "monthly_plan_constructor")
        self.assertEqual(set(manifest["read_sources"]), set(ALLOWED_READ_SOURCES))

    def test_c_no_arbitrary_table_parameter(self) -> None:
        from services import monthly_plan_constructor_read_service as rs
        import inspect

        for name in (
            "load_constructor_scope",
            "load_constructor_adjustments",
            "load_constructor_month_plan_lines",
        ):
            sig = inspect.signature(getattr(rs, name))
            self.assertNotIn("table", sig.parameters)
            self.assertNotIn("table_name", sig.parameters)
            self.assertNotIn("sql", sig.parameters)

    def test_d_no_arbitrary_sql(self) -> None:
        from services import monthly_plan_constructor_read_service as rs

        src = Path(rs.__file__).read_text(encoding="utf-8").lower()
        for pat in ("execute_sql", "rpc(", ".rpc(", "raw_sql"):
            self.assertNotIn(pat, src)

    def test_e_credential_not_in_run_contract(self) -> None:
        from agents.monthly_plan_constructor.runtime import (
            run_monthly_plan_constructor_agent,
        )
        import pandas as pd

        def load_scope(_code: str):
            return pd.DataFrame(
                [
                    {
                        "project_code": "PRJ_001_БХК",
                        "facility_building": "F1",
                        "construction_discipline": "ОВ",
                        "boq_code": "BOQ-1",
                        "boq_name": "Test",
                        "unit_of_measure": "м",
                        "total_project_qty": 10.0,
                        "executed_qty_all_time": 0.0,
                        "manual_executed_before_system": 0.0,
                        "manual_verified_remaining_qty": float("nan"),
                        "planning_remaining_qty": 10.0,
                        "unit_price": 1.0,
                        "total_project_value": 10.0,
                        "system_label": "S",
                        "iwp_id": "I",
                    }
                ]
            ), {"source": "test", "error": None, "row_count": 1}

        def load_adj(_code: str):
            return pd.DataFrame(), {"source": "test", "error": None, "row_count": 0}

        def load_plans(_c: str, _m: str):
            return pd.DataFrame(), {"source": "test", "error": None, "row_count": 0}

        run = run_monthly_plan_constructor_agent(
            "PRJ_001_БХК",
            "август-2026",
            load_scope_fn=load_scope,
            load_adjustments_fn=load_adj,
            load_plan_lines_fn=load_plans,
        )
        blob = json.dumps(run, ensure_ascii=False)
        self.assertNotIn('"apikey"', blob.lower())
        self.assertNotIn("authorization: bearer", blob.lower())
        self.assertNotIn('"authorization"', blob.lower())
        # Ensure known env values are absent when set
        from services.monthly_plan_constructor_read_service import (
            assert_no_secrets_in_payload,
        )

        assert_no_secrets_in_payload(run)

    def test_f_trace_redacts_known_test_secret(self) -> None:
        import os
        from services.monthly_plan_constructor_read_service import redact_sensitive_text

        sentinel = "UNITTEST_FAKE_SECRET_VALUE_XYZ_999"
        old = os.environ.get("SUPABASE_KEY")
        os.environ["SUPABASE_KEY"] = sentinel
        try:
            raw = f"boom Authorization: Bearer {sentinel} apikey={sentinel}"
            cleaned = redact_sensitive_text(raw)
            self.assertNotIn(sentinel, cleaned)
            self.assertIn("REDACTED", cleaned)
        finally:
            if old is None:
                os.environ.pop("SUPABASE_KEY", None)
            else:
                os.environ["SUPABASE_KEY"] = old

    def test_g_h_write_access_remains_false(self) -> None:
        manifest = load_manifest(AGENTS_ROOT / "monthly_plan_constructor")
        self.assertIs(manifest["write_access"], False)
        self.assertEqual(manifest["allowed_write_tools"], [])

    def test_i_agent_layer_does_not_read_env_secrets(self) -> None:
        banned = (
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
        ):
            src = (AGENTS_ROOT / "monthly_plan_constructor" / rel).read_text(
                encoding="utf-8"
            )
            for name in banned:
                self.assertNotIn(
                    name,
                    src,
                    f"{rel} must not reference {name}",
                )
            self.assertNotIn("os.getenv", src)
            self.assertNotIn("os.environ", src)

    def test_column_allowlists_match_manifest(self) -> None:
        from services.monthly_plan_constructor_read_service import (
            ADJUSTMENT_SELECT_COLUMNS,
            PLAN_LINE_SELECT_COLUMNS,
            SCOPE_SELECT_COLUMNS,
        )

        manifest = load_manifest(AGENTS_ROOT / "monthly_plan_constructor")
        fields = manifest["read_fields_by_source"]
        self.assertEqual(
            list(SCOPE_SELECT_COLUMNS),
            fields["monthly_scope_picker_view"],
        )
        self.assertEqual(
            list(ADJUSTMENT_SELECT_COLUMNS),
            fields["monthly_scope_manual_adjustments"],
        )
        self.assertEqual(
            list(PLAN_LINE_SELECT_COLUMNS),
            fields["monthly_plan_lines_v2"],
        )

    def test_sanitize_strips_url_and_bearer(self) -> None:
        from services.monthly_plan_constructor_read_service import sanitize_read_error

        class Boom(Exception):
            pass

        err = Boom("fail https://xyz.supabase.co/rest/v1/x Authorization: Bearer abc.def")
        text = sanitize_read_error(err)
        self.assertNotIn("https://", text)
        self.assertNotIn("abc.def", text)
        self.assertIn("Boom", text)


if __name__ == "__main__":
    unittest.main()
