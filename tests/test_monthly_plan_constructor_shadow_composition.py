"""
Increment 11B — Shadow Runtime Composition Root tests.

Injected factories and temporary observability paths only.
No live Supabase. No product writes. No September mission run.
"""

from __future__ import annotations

import ast
import os
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from langgraph.checkpoint.memory import InMemorySaver

from agents.monthly_plan_constructor.durable_checkpoint import (
    build_constructor_jsonplus_serializer,
)
from agents.monthly_plan_constructor.handoff_store import HandoffStorePutResult
from agents.monthly_plan_constructor.langgraph_runtime import CONSTRUCTOR_AGENT_CODE
from agents.monthly_plan_constructor.real_data_assembler import RealDataShadowAdapter
from agents.monthly_plan_constructor.shadow_composition import (
    CODE_COMPOSITION_ALREADY_STARTED,
    CODE_SHADOW_COMPOSITION_BLOCKER,
    ConstructorShadowComposition,
    ShadowCompositionError,
    build_constructor_shadow_composition,
)
from agents.observability.contracts import InitiatorType, TriggerType
from agents.run_control.contracts import ManagedRunStartInput, StartOutcome
from agents.run_control.registry import InMemoryRunControlRegistry
from security.agent_execution_context import issue_read_only_agent_context

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
MISSION_ID = "mission-11b-composition"
FIXED_AT = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)
REPO = Path(__file__).resolve().parents[1]
COMPOSITION_PATH = (
    REPO / "agents" / "monthly_plan_constructor" / "shadow_composition.py"
)
PLAN_LINE_TOKENS = (
    "load_constructor_month_plan_lines",
    "execute_constructor_plan_lines_read",
    "monthly_plan_lines_v2",
)
FORBIDDEN_TOKENS = PLAN_LINE_TOKENS + (
    "default_executor_scope_reader",
    "issue_read_only_agent_context",
    "AGENT_OBSERVABILITY_DB_PATH",
    "create_client",
    ".runtime",
)


class FakeHitlStore:
    def upsert_open_request(self, request) -> None:
        return None

    def record_answer(self, *, interrupt_id: str, command) -> None:
        return None


class InMemoryHandoffStore:
    def __init__(self) -> None:
        self._records: dict[str, Any] = {}

    def get(self, handoff_id: str):
        return self._records.get(handoff_id)

    def put_if_absent(self, handoff):
        existing = self._records.get(handoff.handoff_id)
        if existing is None:
            self._records[handoff.handoff_id] = handoff
            return HandoffStorePutResult(created=True, stored_handoff=handoff)
        return HandoffStorePutResult(created=False, stored_handoff=existing)


def _checkpointer_factory() -> InMemorySaver:
    return InMemorySaver(serde=build_constructor_jsonplus_serializer())


def _start_input(**overrides: Any) -> ManagedRunStartInput:
    payload = dict(
        agent_code=CONSTRUCTOR_AGENT_CODE,
        initiator_type=InitiatorType.HUMAN,
        initiator_id="operator-11b",
        trigger_type=TriggerType.MANUAL,
        trigger_reason="increment-11b-composition-proof",
        project_code=PROJECT,
        month_key=MONTH,
        requested_mission_id=MISSION_ID,
        idempotency_key="idem-11b-composition",
        scope_request={"facility": "16160-17", "discipline": "Автоматизация"},
    )
    payload.update(overrides)
    return ManagedRunStartInput(**payload)


class ShadowCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmpdir.name) / "observability_11b.sqlite"
        self._compositions: list[ConstructorShadowComposition] = []

    def tearDown(self) -> None:
        for composition in self._compositions:
            store = composition.service._durable_store
            close = getattr(store, "close", None)
            if callable(close):
                close()
        self._tmpdir.cleanup()

    def _build(self, **overrides: Any) -> ConstructorShadowComposition:
        payload = dict(
            observability_db_path=self.db_path,
            checkpointer_factory=_checkpointer_factory,
            hitl_store_factory=FakeHitlStore,
            handoff_store_factory=InMemoryHandoffStore,
        )
        payload.update(overrides)
        composition = build_constructor_shadow_composition(**payload)
        self._compositions.append(composition)
        return composition

    def test_a_factory_does_not_start_run(self) -> None:
        thread_calls = {"n": 0}
        original_thread = threading.Thread

        def _counting_thread(*args: Any, **kwargs: Any):
            thread_calls["n"] += 1
            return original_thread(*args, **kwargs)

        with patch(
            "agents.monthly_plan_constructor.managed_launcher.threading.Thread",
            side_effect=_counting_thread,
        ), patch(
            "agents.monthly_plan_constructor.managed_launcher.run_constructor_langgraph",
        ) as mocked_run, patch(
            "agents.monthly_plan_constructor.real_data_assembler.execute_constructor_scope_read",
        ) as mocked_scope, patch(
            "agents.monthly_plan_constructor.real_data_assembler.execute_constructor_adjustments_read",
        ) as mocked_adj:
            composition = self._build()
        self.assertIsInstance(composition, ConstructorShadowComposition)
        self.assertIsNone(composition.launcher._last_thread)
        self.assertEqual(thread_calls["n"], 0)
        mocked_run.assert_not_called()
        mocked_scope.assert_not_called()
        mocked_adj.assert_not_called()

    def test_b_same_adapter_reader_and_assembler(self) -> None:
        composition = self._build()
        launcher = composition.launcher
        self.assertIs(launcher._assemble_candidates, composition.adapter)
        self.assertIsInstance(composition.adapter, RealDataShadowAdapter)
        self.assertIs(launcher._scope_reader.__self__, composition.adapter)
        self.assertEqual(
            launcher._scope_reader.__func__,
            RealDataShadowAdapter.scope_reader,
        )

    def test_c_two_compositions_isolated(self) -> None:
        first = self._build()
        second_path = Path(self._tmpdir.name) / "observability_11b_b.sqlite"
        second = self._build(observability_db_path=second_path)
        self.assertIsNot(first.adapter, second.adapter)
        self.assertIsNot(first.launcher, second.launcher)
        self.assertIs(first.launcher._assemble_candidates, first.adapter)
        self.assertIs(second.launcher._assemble_candidates, second.adapter)
        self.assertIsNone(first.adapter._snapshot)
        self.assertIsNone(second.adapter._snapshot)

    def test_d_run_control_owns_read_only_context(self) -> None:
        source = COMPOSITION_PATH.read_text(encoding="utf-8")
        self.assertNotIn("issue_read_only_agent_context", source)
        self.assertNotIn("security.agent_execution_context", source)
        composition = self._build()
        captured: dict[str, Any] = {}

        def _capture_issue(**kwargs: Any):
            context = issue_read_only_agent_context(**kwargs)
            captured["context"] = context
            return context

        with patch.object(composition.launcher, "launch"), patch(
            "agents.run_control.service.issue_read_only_agent_context",
            side_effect=_capture_issue,
        ):
            result = composition.start(_start_input(), requested_at=FIXED_AT)
        self.assertEqual(result.outcome, StartOutcome.AUTHORIZED)
        context = captured["context"]
        self.assertIs(context.write_allowed, False)
        self.assertEqual(context.permission_tier, "TIER_0_READ_ONLY_DETERMINISTIC")
        self.assertIsNone(composition.launcher._last_thread)

    def test_e_no_product_writers(self) -> None:
        source = COMPOSITION_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        called: set[str] = set()
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called.add(node.func.id.lower())
                elif isinstance(node.func, ast.Attribute):
                    called.add(node.func.attr.lower())
        for token in ("insert", "update", "upsert", "delete", "create_client", "mkdir"):
            self.assertNotIn(token, called)
        self.assertNotIn("streamlit", source.lower())
        self.assertNotIn("supabase", imported)
        self.assertNotIn("pages", imported)
        lowered = source.lower()
        self.assertNotIn("create_client", lowered)
        self.assertNotIn(".runtime", lowered)

    def test_f_no_human_benchmark_read(self) -> None:
        source = COMPOSITION_PATH.read_text(encoding="utf-8")
        for token in FORBIDDEN_TOKENS:
            self.assertNotIn(token, source)

    def test_g_explicit_observability_path_required(self) -> None:
        for invalid in (None, "", "   ", 123):
            with self.assertRaises(ShadowCompositionError) as raised:
                build_constructor_shadow_composition(
                    observability_db_path=invalid,  # type: ignore[arg-type]
                    checkpointer_factory=_checkpointer_factory,
                    hitl_store_factory=FakeHitlStore,
                    handoff_store_factory=InMemoryHandoffStore,
                )
            self.assertEqual(raised.exception.code, CODE_SHADOW_COMPOSITION_BLOCKER)
        decoy = Path(self._tmpdir.name) / "control_room.sqlite"
        decoy.write_text("", encoding="utf-8")
        with patch.dict(os.environ, {"AGENT_OBSERVABILITY_DB_PATH": str(decoy)}):
            with self.assertRaises(ShadowCompositionError) as raised:
                build_constructor_shadow_composition(
                    observability_db_path="   ",
                    checkpointer_factory=_checkpointer_factory,
                    hitl_store_factory=FakeHitlStore,
                    handoff_store_factory=InMemoryHandoffStore,
                )
        self.assertEqual(raised.exception.code, CODE_SHADOW_COMPOSITION_BLOCKER)
        with self.assertRaises(ShadowCompositionError) as raised:
            build_constructor_shadow_composition(
                observability_db_path=Path(self._tmpdir.name),
                checkpointer_factory=_checkpointer_factory,
                hitl_store_factory=FakeHitlStore,
                handoff_store_factory=InMemoryHandoffStore,
            )
        self.assertEqual(raised.exception.code, CODE_SHADOW_COMPOSITION_BLOCKER)

    def test_h_explicit_store_factories_required(self) -> None:
        base = dict(
            observability_db_path=self.db_path,
            checkpointer_factory=_checkpointer_factory,
            hitl_store_factory=FakeHitlStore,
            handoff_store_factory=InMemoryHandoffStore,
        )
        for kwargs in (
            {"checkpointer_factory": None},
            {"hitl_store_factory": None},
            {"handoff_store_factory": None},
            {"checkpointer_factory": "not-callable"},
        ):
            payload = dict(base)
            payload.update(kwargs)
            with self.assertRaises(ShadowCompositionError) as raised:
                build_constructor_shadow_composition(**payload)  # type: ignore[arg-type]
            self.assertEqual(raised.exception.code, CODE_SHADOW_COMPOSITION_BLOCKER)

    def test_i_start_is_one_shot(self) -> None:
        composition = self._build()
        with patch.object(composition.launcher, "launch") as mocked_launch:
            first = composition.start(_start_input(), requested_at=FIXED_AT)
            self.assertEqual(first.outcome, StartOutcome.AUTHORIZED)
            mocked_launch.assert_called_once()
            with self.assertRaises(ShadowCompositionError) as raised:
                composition.start(
                    _start_input(idempotency_key="idem-11b-second"),
                    requested_at=FIXED_AT,
                )
        self.assertEqual(raised.exception.code, CODE_COMPOSITION_ALREADY_STARTED)
        self.assertEqual(mocked_launch.call_count, 1)
        self.assertIsNone(composition.launcher._last_thread)

    def test_j_launcher_receives_wired_dependencies(self) -> None:
        labor = ()
        registry = InMemoryRunControlRegistry()
        composition = self._build(
            labor_evidence=labor,
            registry=registry,
        )
        launcher = composition.launcher
        self.assertEqual(launcher._observability_db_path, str(self.db_path))
        self.assertEqual(composition.observability_db_path, str(self.db_path))
        self.assertIs(launcher._assemble_candidates, composition.adapter)
        self.assertIs(launcher._scope_reader.__self__, composition.adapter)
        self.assertEqual(launcher._labor_evidence, labor)
        self.assertIs(launcher._checkpointer_factory, _checkpointer_factory)
        self.assertIs(launcher._hitl_store_factory, FakeHitlStore)
        self.assertIs(launcher._handoff_store_factory, InMemoryHandoffStore)
        self.assertIs(composition.service._registry, registry)

    def test_k_no_global_state(self) -> None:
        source = COMPOSITION_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        assigned: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and not target.id.isupper():
                        assigned.append(target.id)
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if not node.target.id.isupper() and node.value is not None:
                    assigned.append(node.target.id)
        self.assertEqual(assigned, [])
        first = self._build()
        second_path = Path(self._tmpdir.name) / "observability_11b_k.sqlite"
        second = self._build(observability_db_path=second_path)
        self.assertIsNot(first.adapter, second.adapter)
        self.assertIsNone(getattr(first.adapter, "_snapshot"))
        import agents.monthly_plan_constructor.shadow_composition as module

        self.assertFalse(hasattr(module, "_ADAPTER"))
        self.assertFalse(hasattr(module, "ADAPTER"))
        self.assertFalse(hasattr(module, "_COMPOSITION"))


if __name__ == "__main__":
    unittest.main()
