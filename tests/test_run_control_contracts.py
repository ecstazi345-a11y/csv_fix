"""
Increment 10.2 — Run Control contract tests.
"""

from __future__ import annotations

import ast
import inspect
import unittest
from dataclasses import fields
from pathlib import Path

from agents.observability.contracts import InitiatorType, TriggerType
from agents.run_control.contracts import (
    CODE_RUN_CONTROL_BLOCKER,
    ManagedRunStartInput,
    RunControlError,
)
from security.agent_execution_context import AgentExecutionContext

REPO = Path(__file__).resolve().parents[1]
RUN_CONTROL_DIR = REPO / "agents" / "run_control"


def _valid_input(**overrides):
    base = dict(
        agent_code="MONTHLY_PLAN_CONSTRUCTOR",
        initiator_type=InitiatorType.HUMAN,
        initiator_id="operator-local",
        trigger_type=TriggerType.MANUAL,
        trigger_reason="manual-start",
        project_code="PRJ_001",
        month_key="2026-09",
        requested_mission_id="mission-001",
        idempotency_key="idem-001",
        scope_request={"facility": "A"},
        metadata={"ui": "control-room"},
    )
    base.update(overrides)
    return ManagedRunStartInput(**base)


class ManagedRunStartInputTests(unittest.TestCase):
    def test_01_rejects_missing_agent_code(self) -> None:
        with self.assertRaises(RunControlError) as ctx:
            _valid_input(agent_code="  ")
        self.assertEqual(ctx.exception.code, CODE_RUN_CONTROL_BLOCKER)

    def test_02_rejects_missing_mission_id(self) -> None:
        with self.assertRaises(RunControlError):
            _valid_input(requested_mission_id="")

    def test_03_rejects_missing_idempotency_key(self) -> None:
        with self.assertRaises(RunControlError):
            _valid_input(idempotency_key="")

    def test_04_orchestrator_requires_orchestration_run_id(self) -> None:
        with self.assertRaises(RunControlError):
            _valid_input(
                initiator_type=InitiatorType.ORCHESTRATOR,
                orchestration_run_id=None,
            )

    def test_05_no_request_id_or_run_id_fields(self) -> None:
        names = {field.name for field in fields(ManagedRunStartInput)}
        self.assertNotIn("request_id", names)
        self.assertNotIn("run_id", names)
        self.assertNotIn("requested_at", names)
        self.assertNotIn("canonical_request_digest", names)

    def test_05b_result_has_no_execution_context_field(self) -> None:
        from agents.run_control.contracts import ManagedRunStartResult

        names = {field.name for field in fields(ManagedRunStartResult)}
        self.assertNotIn("execution_context", names)
        self.assertIn("authorization_id", names)

    def test_06_no_runtime_security_objects(self) -> None:
        sig = inspect.signature(ManagedRunStartInput)
        for forbidden in (
            "context",
            "execution_context",
            "authorization",
            "supabase",
            "dataframe",
        ):
            self.assertNotIn(forbidden, sig.parameters)

    def test_07_valid_input_constructs(self) -> None:
        item = _valid_input()
        self.assertEqual(item.agent_code, "MONTHLY_PLAN_CONSTRUCTOR")
        self.assertIsInstance(item, ManagedRunStartInput)
        self.assertNotIsInstance(item, AgentExecutionContext)


class RunControlArchitectureImportTests(unittest.TestCase):
    def test_08_no_constructor_mission_scope_import(self) -> None:
        forbidden = "agents.monthly_plan_constructor"
        for path in RUN_CONTROL_DIR.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(alias.name.startswith(forbidden), path.name)
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertFalse(node.module.startswith(forbidden), path.name)


if __name__ == "__main__":
    unittest.main()
