"""
Increment 10.3A — Constructor runtime instrumentation foundation tests.

No LangGraph wiring. No Run Control changes. No durable store.
"""

from __future__ import annotations

import ast
import inspect
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from agents.monthly_plan_constructor.runtime_instrumentation import (
    CODE_RUNTIME_INSTRUMENTATION_BLOCKER,
    CONSTRUCTOR_RUNTIME_EVENT_NAMESPACE,
    RUN_CONTROL_OWNED_EVENT_TYPES,
    RUNTIME_OWNED_EVENT_TYPES,
    ConstructorRuntimeEventKey,
    ConstructorRuntimeInstrumentation,
    ConstructorRuntimeInstrumentationError,
    compute_constructor_runtime_event_id,
    is_constructor_stage_id,
    validate_constructor_stage_id,
)
from agents.observability.contracts import (
    CONSTRUCTOR_STAGE_CATALOG,
    EventStatus,
    EventType,
    ObservabilityContractError,
)
from agents.observability.recorder import (
    InMemoryObservabilityRecorder,
    ObservabilityEventConflictError,
    RecordOutcome,
    RecordResult,
)
from security.agent_execution_context import issue_read_only_agent_context

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "agents" / "monthly_plan_constructor" / "runtime_instrumentation.py"

FIXED_AT = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
ALT_AT = datetime(2026, 8, 31, 13, 0, 0, tzinfo=timezone.utc)
AGENT_CODE = "MONTHLY_PLAN_CONSTRUCTOR"
RUN_ID = "run-001"


def _stage_key(**overrides: Any) -> ConstructorRuntimeEventKey:
    payload = dict(
        run_id=RUN_ID,
        event_type=EventType.STAGE_STARTED,
        stage_id="REALITY_READ",
        node_name="load_reality",
        attempt_n=1,
        resume_n=0,
        semantic_occurrence_key="initial",
    )
    payload.update(overrides)
    return ConstructorRuntimeEventKey(**payload)


@dataclass
class CapturingRecorder:
  """Test double using only the ObservabilityRecorder write Protocol."""

  events: list[Any] = field(default_factory=list)
  fail: bool = False

  def record_event(self, event: Any) -> RecordResult:
    if self.fail:
      raise RuntimeError("recorder-down")
    backend = InMemoryObservabilityRecorder()
    for prior in self.events:
      backend.record_event(prior)
    result = backend.record_event(event)
    if result.outcome is RecordOutcome.CREATED:
      self.events.append(event)
    return result


class ConstructorRuntimeEventIdTests(unittest.TestCase):
    def test_01_same_semantic_key_same_event_id(self) -> None:
        key = _stage_key()
        self.assertEqual(
            compute_constructor_runtime_event_id(key),
            compute_constructor_runtime_event_id(_stage_key()),
        )

    def test_02_different_run_id(self) -> None:
        a = compute_constructor_runtime_event_id(_stage_key())
        b = compute_constructor_runtime_event_id(_stage_key(run_id="run-002"))
        self.assertNotEqual(a, b)

    def test_03_different_event_type(self) -> None:
        a = compute_constructor_runtime_event_id(_stage_key())
        b = compute_constructor_runtime_event_id(
            _stage_key(event_type=EventType.STAGE_COMPLETED)
        )
        self.assertNotEqual(a, b)

    def test_04_different_stage_id(self) -> None:
        a = compute_constructor_runtime_event_id(_stage_key())
        b = compute_constructor_runtime_event_id(_stage_key(stage_id="CANDIDATE_ASSEMBLY"))
        self.assertNotEqual(a, b)

    def test_05_different_node_name(self) -> None:
        a = compute_constructor_runtime_event_id(_stage_key())
        b = compute_constructor_runtime_event_id(_stage_key(node_name="build_package"))
        self.assertNotEqual(a, b)

    def test_06_different_attempt_n(self) -> None:
        a = compute_constructor_runtime_event_id(_stage_key())
        b = compute_constructor_runtime_event_id(_stage_key(attempt_n=2))
        self.assertNotEqual(a, b)

    def test_07_different_resume_n(self) -> None:
        a = compute_constructor_runtime_event_id(_stage_key())
        b = compute_constructor_runtime_event_id(_stage_key(resume_n=1))
        self.assertNotEqual(a, b)

    def test_08_different_semantic_occurrence_key(self) -> None:
        a = compute_constructor_runtime_event_id(_stage_key())
        b = compute_constructor_runtime_event_id(
            _stage_key(semantic_occurrence_key="resume-1")
        )
        self.assertNotEqual(a, b)

    def test_09_timestamp_does_not_affect_event_id(self) -> None:
        key = _stage_key()
        self.assertEqual(
            compute_constructor_runtime_event_id(key),
            compute_constructor_runtime_event_id(key),
        )
        source = inspect.getsource(compute_constructor_runtime_event_id)
        self.assertNotIn("datetime", source)
        self.assertNotIn("uuid", source)


class ConstructorStageValidationTests(unittest.TestCase):
    def test_10_every_catalog_stage_validates(self) -> None:
        for stage in CONSTRUCTOR_STAGE_CATALOG:
            self.assertEqual(validate_constructor_stage_id(stage.stage_id), stage.stage_id)
            self.assertTrue(is_constructor_stage_id(stage.stage_id))

    def test_11_unknown_stage_fails_closed(self) -> None:
        with self.assertRaises(ConstructorRuntimeInstrumentationError) as ctx:
            validate_constructor_stage_id("NOT_A_REAL_STAGE")
        self.assertEqual(ctx.exception.code, CODE_RUNTIME_INSTRUMENTATION_BLOCKER)

    def test_12_no_duplicated_local_catalog(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("CONSTRUCTOR_STAGE_CATALOG", source)
        self.assertNotIn("StageDefinition(", source)


class EventOwnershipTests(unittest.TestCase):
    def _assert_run_control_blocked(self, event_type: EventType) -> None:
        with self.assertRaises(ConstructorRuntimeInstrumentationError) as ctx:
            ConstructorRuntimeEventKey(run_id=RUN_ID, event_type=event_type)
        self.assertEqual(ctx.exception.code, CODE_RUNTIME_INSTRUMENTATION_BLOCKER)
        self.assertIn("Run Control", str(ctx.exception))

    def test_13_run_requested_rejected(self) -> None:
        self._assert_run_control_blocked(EventType.RUN_REQUESTED)

    def test_14_run_authorization_started_rejected(self) -> None:
        self._assert_run_control_blocked(EventType.RUN_AUTHORIZATION_STARTED)

    def test_15_run_authorized_rejected(self) -> None:
        self._assert_run_control_blocked(EventType.RUN_AUTHORIZED)

    def test_16_run_denied_rejected(self) -> None:
        self._assert_run_control_blocked(EventType.RUN_DENIED)

    def test_17_mission_bound_rejected(self) -> None:
        self._assert_run_control_blocked(EventType.MISSION_BOUND)

    def test_18_run_started_rejected(self) -> None:
        self._assert_run_control_blocked(EventType.RUN_STARTED)

    def test_19_runtime_owned_stage_started_accepted(self) -> None:
        key = _stage_key()
        self.assertEqual(key.event_type, EventType.STAGE_STARTED)
        self.assertIn(EventType.STAGE_STARTED, RUNTIME_OWNED_EVENT_TYPES)
        self.assertNotIn(EventType.STAGE_STARTED, RUN_CONTROL_OWNED_EVENT_TYPES)


class RecorderEmitterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.recorder = CapturingRecorder()
        self.emitter = ConstructorRuntimeInstrumentation(recorder=self.recorder)

    def test_20_uses_injected_recorder(self) -> None:
        result = self.emitter.emit(
            key=_stage_key(),
            occurred_at=FIXED_AT,
            agent_code=AGENT_CODE,
            title="Reality read started",
        )
        self.assertIsInstance(result, RecordResult)
        self.assertEqual(len(self.recorder.events), 1)

    def test_21_no_inmemory_import_in_production_module(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        import_froms = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertNotIn("InMemoryObservabilityRecorder", source)
        self.assertNotIn("InMemoryObservabilityRecorder", imports)
        self.assertNotIn("InMemoryObservabilityRecorder", import_froms)

    def test_22_created_outcome(self) -> None:
        result = self.emitter.emit(
            key=_stage_key(),
            occurred_at=FIXED_AT,
            agent_code=AGENT_CODE,
            title="Reality read started",
        )
        self.assertEqual(result.outcome, RecordOutcome.CREATED)

    def test_23_same_event_idempotent_replay(self) -> None:
        key = _stage_key()
        first = self.emitter.emit(
            key=key,
            occurred_at=FIXED_AT,
            agent_code=AGENT_CODE,
            title="Reality read started",
            detail={"candidate_count": 3},
        )
        second = self.emitter.emit(
            key=key,
            occurred_at=FIXED_AT,
            agent_code=AGENT_CODE,
            title="Reality read started",
            detail={"candidate_count": 3},
        )
        self.assertEqual(first.outcome, RecordOutcome.CREATED)
        self.assertEqual(second.outcome, RecordOutcome.IDEMPOTENT_REPLAY)

    def test_24_same_event_id_changed_payload_conflict(self) -> None:
        backend = InMemoryObservabilityRecorder()
        emitter = ConstructorRuntimeInstrumentation(recorder=backend)
        key = _stage_key()
        emitter.emit(
            key=key,
            occurred_at=FIXED_AT,
            agent_code=AGENT_CODE,
            title="Reality read started",
            detail={"candidate_count": 3},
        )
        with self.assertRaises(ObservabilityEventConflictError):
            emitter.emit(
                key=key,
                occurred_at=ALT_AT,
                agent_code=AGENT_CODE,
                title="Reality read started",
                detail={"candidate_count": 4},
            )

    def test_25_recorder_exception_propagates(self) -> None:
        failing = CapturingRecorder(fail=True)
        emitter = ConstructorRuntimeInstrumentation(recorder=failing)
        with self.assertRaises(RuntimeError) as ctx:
            emitter.emit(
                key=_stage_key(),
                occurred_at=FIXED_AT,
                agent_code=AGENT_CODE,
                title="Reality read started",
            )
        self.assertIn("recorder-down", str(ctx.exception))


class PayloadSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.emitter = ConstructorRuntimeInstrumentation(
            recorder=InMemoryObservabilityRecorder()
        )

    def test_26_secret_like_detail_rejected(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            self.emitter.emit(
                key=_stage_key(),
                occurred_at=FIXED_AT,
                agent_code=AGENT_CODE,
                title="Reality read started",
                detail={"supabase_secret_key": "leak"},
            )

    def test_27_dataframe_rejected(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            self.emitter.emit(
                key=_stage_key(),
                occurred_at=FIXED_AT,
                agent_code=AGENT_CODE,
                title="Reality read started",
                detail={"rows": pd.DataFrame({"a": [1]})},
            )

    def test_28_oversized_list_rejected(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            self.emitter.emit(
                key=_stage_key(),
                occurred_at=FIXED_AT,
                agent_code=AGENT_CODE,
                title="Reality read started",
                detail={"items": list(range(33))},
            )

    def test_29_oversized_string_rejected(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            self.emitter.emit(
                key=_stage_key(),
                occurred_at=FIXED_AT,
                agent_code=AGENT_CODE,
                title="Reality read started",
                detail={"note": "x" * 501},
            )

    def test_30_no_agent_execution_context_stored(self) -> None:
        context = issue_read_only_agent_context(
            agent_code=AGENT_CODE,
            project_code="PRJ_001",
            run_id=RUN_ID,
        )
        with self.assertRaises((ObservabilityContractError, TypeError, ValueError)):
            self.emitter.emit(
                key=_stage_key(),
                occurred_at=FIXED_AT,
                agent_code=AGENT_CODE,
                title="Reality read started",
                detail={"context": context},
            )


class ArchitectureGuardTests(unittest.TestCase):
    def test_31_no_langgraph_import(self) -> None:
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        names = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertFalse(any("langgraph" in (m or "").lower() for m in modules))
        self.assertFalse(any("langgraph" in (n or "").lower() for n in names))

    def test_32_no_run_control_production_import(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("agents.run_control", source)

    def test_33_no_lifecycle_mutation(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("advance_constructor_lifecycle", source)
        self.assertNotIn("ConstructorLifecycleState", source)

    def test_34_no_supabase(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8").lower()
        self.assertNotIn("supabase", source)

    def test_35_no_streamlit(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8").lower()
        self.assertNotIn("streamlit", source)

    def test_36_no_global_recorder(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("_GLOBAL_RECORDER", source)
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and "recorder" in target.id.lower():
                        if target.id.isupper():
                            self.fail(f"global recorder-like constant found: {target.id}")

    def test_37_no_clock_or_uuid_for_identity(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        identity_source = inspect.getsource(compute_constructor_runtime_event_id)
        self.assertNotIn("uuid", identity_source)
        self.assertNotIn("datetime.now", identity_source)
        self.assertNotIn("utc_now", identity_source)
        self.assertIn(CONSTRUCTOR_RUNTIME_EVENT_NAMESPACE, source)


if __name__ == "__main__":
    unittest.main()
