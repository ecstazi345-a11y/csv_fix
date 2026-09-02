"""
Increment 10.6 — AgentControlRoomQueryPort tests.

Agent-neutral read port over ObservabilityStore. No Constructor imports. No Streamlit.
"""

from __future__ import annotations

import ast
import inspect
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from agents.control_room.dtos import (
    DerivationState,
    HandoffStatus,
    ProfessionalExecutionState,
    ProfessionalExecutionStepKind,
    StageDisplayState,
    ToolExecutionStatus,
    WaitClosedBy,
)
from agents.control_room.errors import (
    CODE_CONTROL_ROOM_QUERY_BLOCKER,
    CODE_CONTROL_ROOM_RUN_NOT_FOUND,
    ControlRoomQueryBlockerError,
    ControlRoomRunNotFoundError,
)
from agents.control_room.query_port import AgentControlRoomQueryPort
from agents.observability.contracts import (
    EventFamily,
    EventStatus,
    EventType,
    InitiatorType,
    OperationalStatus,
    TriggerType,
    build_agent_run,
    build_handoff_observability_context,
    build_human_decision_record_observability_context,
    build_human_decision_request_observability_context,
    build_observability_event,
)
from agents.observability.durable_recorder import StoreObservabilityRecorder
from agents.observability.projection import project_agent_run_event
from agents.observability.recorder import RecordOutcome
from agents.observability.store import (
    InMemoryObservabilityStore,
    ObservabilityStore,
)
from agents.observability.sqlite_store import SqliteObservabilityStore

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROL_ROOM_ROOT = REPO_ROOT / "agents" / "control_room"
FIXED_AT = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
LATER_AT = datetime(2026, 9, 2, 12, 30, 0, tzinfo=timezone.utc)
EVEN_LATER_AT = datetime(2026, 9, 2, 13, 0, 0, tzinfo=timezone.utc)

_FORBIDDEN_IMPORT_PREFIXES = (
    "agents.monthly_plan_constructor",
    "streamlit",
)


def _agent_run_kwargs(**overrides: Any) -> dict[str, Any]:
    payload = {
        "run_id": "run-001",
        "request_id": "req-001",
        "agent_code": "MONTHLY_PLAN_CONSTRUCTOR",
        "agent_version": "0.1",
        "mission_id": "mission-001",
        "project_code": "PRJ_001",
        "month_key": "2026-09",
        "initiator_type": InitiatorType.HUMAN,
        "initiator_id": "operator-local",
        "trigger_type": TriggerType.MANUAL,
        "trigger_reason": "manual-start",
        "operational_status": OperationalStatus.REQUESTED,
        "requested_at": FIXED_AT,
        "updated_at": FIXED_AT,
        "thread_id": "run-001",
        "scope_summary": {"facility": "A"},
        "safe_summary": {"phase": "starting"},
        "safe_counts": {"candidates": 0},
        "projection_version": 0,
    }
    payload.update(overrides)
    return payload


def _build_run(**overrides: Any):
    return build_agent_run(**_agent_run_kwargs(**overrides))


def _event_kwargs(**overrides: Any) -> dict[str, Any]:
    payload = {
        "event_id": "evt-001",
        "run_id": "run-001",
        "agent_code": "MONTHLY_PLAN_CONSTRUCTOR",
        "occurred_at": FIXED_AT,
        "event_type": EventType.RUN_REQUESTED,
        "status": EventStatus.OK,
        "title": "Run requested",
        "detail": {},
    }
    payload.update(overrides)
    return payload


def _hitl_request(**overrides: Any):
    payload = {
        "reason_code": "AMBIGUOUS_SCOPE",
        "allowed_decisions": ("CLARIFY_SCOPE", "ABORT_RUN"),
        "human_readable_reason": "Scope needs clarification",
        "evidence_refs": ("ref-001",),
    }
    payload.update(overrides)
    return build_human_decision_request_observability_context(**payload)


def _hitl_record(**overrides: Any):
    payload = {
        "decision_code": "CLARIFY_SCOPE",
        "actor_id": "operator-local",
        "actor_type": "HUMAN",
    }
    payload.update(overrides)
    return build_human_decision_record_observability_context(**payload)


def _handoff_context(**overrides: Any):
    payload = {
        "handoff_type": "CONSTRUCTOR_TO_ADMISSION",
        "target_role_code": "MONTHLY_PLAN_ADMISSION_AGENT",
    }
    payload.update(overrides)
    return build_handoff_observability_context(**payload)


def _build_event(**overrides: Any):
    allow_legacy_hitl = overrides.pop("allow_legacy_missing_hitl_subcontracts", False)
    allow_legacy_handoff = overrides.pop("allow_legacy_missing_handoff_subcontract", False)
    return build_observability_event(
        **_event_kwargs(**overrides),
        allow_legacy_missing_hitl_subcontracts=allow_legacy_hitl,
        allow_legacy_missing_handoff_subcontract=allow_legacy_handoff,
    )


def _append(store: ObservabilityStore, event_kwargs: dict[str, Any]) -> None:
    event = _build_event(**event_kwargs)
    run = store.get_run(event.run_id)
    change = project_agent_run_event(run, event)
    store.append_event_and_project_run(
        event=event,
        expected_projection_version=run.projection_version,
        projection_change=change,
    )

def _memory_store_factory() -> InMemoryObservabilityStore:
    return InMemoryObservabilityStore()


def _sqlite_store_factory() -> SqliteObservabilityStore:
    handle = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    handle.close()
    return SqliteObservabilityStore(handle.name)


STORE_FACTORIES: list[tuple[str, Callable[[], ObservabilityStore]]] = [
    ("memory", _memory_store_factory),
    ("sqlite", _sqlite_store_factory),
]


class _WriteTrackingStore:
    def __init__(self, inner: ObservabilityStore) -> None:
        self._inner = inner
        self.create_run_calls = 0
        self.append_calls = 0

    def create_run(self, run):
        self.create_run_calls += 1
        return self._inner.create_run(run)

    def get_run(self, run_id: str):
        return self._inner.get_run(run_id)

    def append_event_and_project_run(self, **kwargs):
        self.append_calls += 1
        return self._inner.append_event_and_project_run(**kwargs)

    def list_events(self, run_id: str, *, limit: int = 500):
        return self._inner.list_events(run_id, limit=limit)

    def list_runs(self, *, limit: int = 200, agent_code: Optional[str] = None):
        return self._inner.list_runs(limit=limit, agent_code=agent_code)


def _stage_started(event_id: str, *, stage_id: str = "REALITY_READ", resume_n: int = 0, artifact_id: Optional[str] = None, at: datetime = FIXED_AT, **extra: Any):
    payload = {
        "event_id": event_id,
        "event_type": EventType.STAGE_STARTED,
        "family": EventFamily.STAGE,
        "stage_id": stage_id,
        "node_name": "load_reality",
        "resume_n": resume_n,
        "artifact_id": artifact_id,
        "occurred_at": at,
        "title": f"{stage_id} started",
    }
    payload.update(extra)
    return payload


def _stage_completed(event_id: str, *, stage_id: str = "REALITY_READ", resume_n: int = 0, artifact_id: Optional[str] = None, at: datetime = LATER_AT):
    return {
        "event_id": event_id,
        "event_type": EventType.STAGE_COMPLETED,
        "family": EventFamily.STAGE,
        "stage_id": stage_id,
        "node_name": "load_reality",
        "resume_n": resume_n,
        "artifact_id": artifact_id,
        "occurred_at": at,
        "title": f"{stage_id} completed",
    }


def _stage_failed(event_id: str, *, stage_id: str = "REALITY_READ", resume_n: int = 0, artifact_id: Optional[str] = None, at: datetime = LATER_AT):
    return {
        "event_id": event_id,
        "event_type": EventType.STAGE_FAILED,
        "family": EventFamily.STAGE,
        "stage_id": stage_id,
        "node_name": "load_reality",
        "resume_n": resume_n,
        "artifact_id": artifact_id,
        "occurred_at": at,
        "title": f"{stage_id} failed",
        "status": EventStatus.FAILED,
    }


class QueryPortArchitectureTests(unittest.TestCase):
    def test_no_constructor_or_streamlit_imports(self) -> None:
        for path in CONTROL_ROOM_ROOT.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self._assert_allowed_import(alias.name)
                if isinstance(node, ast.ImportFrom) and node.module:
                    self._assert_allowed_import(node.module)

    def _assert_allowed_import(self, module_name: str) -> None:
        for forbidden in _FORBIDDEN_IMPORT_PREFIXES:
            if module_name == forbidden or module_name.startswith(f"{forbidden}."):
                self.fail(f"forbidden import: {module_name}")

    def test_no_write_surface(self) -> None:
        public = {
            name
            for name, value in inspect.getmembers(AgentControlRoomQueryPort, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        self.assertEqual(public, {"get_run", "get_run_snapshot", "list_runs"})

    def test_write_methods_not_called(self) -> None:
        store = _WriteTrackingStore(_memory_store_factory())
        store.create_run(_build_run())
        port = AgentControlRoomQueryPort(store)
        port.list_runs()
        port.get_run("run-001")
        port.get_run_snapshot("run-001")
        self.assertEqual(store.create_run_calls, 1)
        self.assertEqual(store.append_calls, 0)


class QueryPortContractTests(unittest.TestCase):
    def _for_each_store(self, test_fn: Callable[[ObservabilityStore, str], None]) -> None:
        for label, factory in STORE_FACTORIES:
            with self.subTest(store=label):
                store = factory()
                try:
                    test_fn(store, label)
                finally:
                    close = getattr(store, "close", None)
                    if callable(close):
                        close()

    def test_get_run_not_found(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            port = AgentControlRoomQueryPort(store)
            with self.assertRaises(ControlRoomRunNotFoundError) as ctx:
                port.get_run("missing-run")
            self.assertEqual(ctx.exception.code, CODE_CONTROL_ROOM_RUN_NOT_FOUND)

        self._for_each_store(exercise)

    def test_get_run_safe_detail(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(
                _build_run(
                    operational_status=OperationalStatus.RUNNING,
                    started_at=FIXED_AT,
                    safe_summary={"phase": "running"},
                    safe_counts={"candidates": 3},
                )
            )
            detail = AgentControlRoomQueryPort(store).get_run("run-001")
            self.assertEqual(detail.run_id, "run-001")
            self.assertEqual(detail.projection_version, 0)
            self.assertEqual(dict(detail.safe_summary), {"phase": "running"})
            self.assertNotIn("scope_summary", detail.__dict__)
            self.assertNotIn("authorization_id", detail.__dict__)

        self._for_each_store(exercise)

    def test_list_runs_filters_and_ordering(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run(run_id="run-old", thread_id="run-old", request_id="req-old", updated_at=FIXED_AT, project_code="PRJ_A", month_key="2026-08", operational_status=OperationalStatus.REQUESTED))
            store.create_run(_build_run(run_id="run-new", thread_id="run-new", request_id="req-new", updated_at=EVEN_LATER_AT, project_code="PRJ_B", month_key="2026-09", operational_status=OperationalStatus.RUNNING))
            port = AgentControlRoomQueryPort(store)
            all_runs = port.list_runs()
            self.assertTrue(all_runs.runs_complete)
            self.assertEqual(all_runs.source_count, 2)
            self.assertEqual([item.run_id for item in all_runs.items], ["run-new", "run-old"])

            filtered = port.list_runs(project_code="PRJ_B", month_key="2026-09", operational_status=OperationalStatus.RUNNING)
            self.assertEqual(len(filtered.items), 1)
            self.assertEqual(filtered.items[0].run_id, "run-new")

            by_agent = port.list_runs(agent_code="MONTHLY_PLAN_CONSTRUCTOR")
            self.assertEqual(len(by_agent.items), 2)

        self._for_each_store(exercise)

    def test_runs_complete_false_when_store_window_full(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            for index in range(200):
                run_id = f"run-{index:03d}"
                store.create_run(
                    _build_run(
                        run_id=run_id,
                        thread_id=run_id,
                        request_id=f"req-{index:03d}",
                        updated_at=FIXED_AT + timedelta(minutes=index),
                    )
                )
            view = AgentControlRoomQueryPort(store).list_runs(limit=50)
            self.assertFalse(view.runs_complete)
            self.assertEqual(view.source_count, 200)
            self.assertEqual(len(view.items), 50)

        self._for_each_store(exercise)

    def test_snapshot_fields_and_flags(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run(operational_status=OperationalStatus.RUNNING, started_at=FIXED_AT))
            _append(store, _stage_started("stage-start"))
            _append(store, _stage_completed("stage-done"))
            snapshot = AgentControlRoomQueryPort(store).get_run_snapshot("run-001")
            self.assertEqual(snapshot.run.projection_version, snapshot.run.projection_version)
            self.assertTrue(snapshot.events_complete)
            self.assertIsNotNone(snapshot.read_at)
            self.assertEqual(len(snapshot.timeline_events), 2)
            self.assertFalse(hasattr(snapshot, "recent_events"))
            dumped = json.dumps(snapshot.run.__dict__, default=str)
            self.assertNotIn("ObservabilityStore", dumped)

        self._for_each_store(exercise)

    def test_events_complete_false_at_limit(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run())
            for index in range(3):
                _append(
                    store,
                    {
                        "event_id": f"evt-{index}",
                        "event_type": EventType.RUN_REQUESTED if index == 0 else EventType.RUN_ADVANCING,
                        "family": EventFamily.RUN_CONTROL,
                        "title": f"event {index}",
                        "occurred_at": FIXED_AT + timedelta(seconds=index),
                    },
                )
            snapshot = AgentControlRoomQueryPort(store).get_run_snapshot("run-001", event_limit=2)
            self.assertFalse(snapshot.events_complete)
            self.assertEqual(len(snapshot.timeline_events), 2)
            self.assertEqual(snapshot.stage.derivation_state, DerivationState.INCOMPLETE)

        self._for_each_store(exercise)

    def test_raw_detail_never_exposed(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run())
            misleading_detail = {
                "status": "COMPLETED",
                "stage_state": "FAILED",
                "target_role": "SECRET_AGENT",
                "error_code": "FAKE_ERROR",
                "source_agent": "SHOULD_NOT_LEAK",
                "candidate_count": "999",
                "decision_type": "ABORT",
            }
            _append(
                store,
                _stage_started(
                    "stage-start",
                    detail=misleading_detail,
                ),
            )
            _append(store, _stage_completed("stage-done"))
            snapshot = AgentControlRoomQueryPort(store).get_run_snapshot("run-001")
            payload = json.dumps(
                {
                    "timeline": [event.__dict__ for event in snapshot.timeline_events],
                    "stage": snapshot.stage.__dict__,
                    "handoff": snapshot.handoff.__dict__,
                    "human_wait": snapshot.human_wait.__dict__,
                },
                default=str,
            ).lower()
            for token in ("secret_agent", "fake_error", "should_not_leak", "detail", "abort"):
                self.assertNotIn(token, payload)
            self.assertEqual(snapshot.stage.occurrences[0].display_state, StageDisplayState.COMPLETED)

        self._for_each_store(exercise)


class StageDerivationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _memory_store_factory()
        self.port = AgentControlRoomQueryPort(self.store)
        self.store.create_run(_build_run(operational_status=OperationalStatus.RUNNING, started_at=FIXED_AT))

    def _snapshot(self):
        return self.port.get_run_snapshot("run-001")

    def test_stage_running_then_completed(self) -> None:
        _append(self.store, _stage_started("s1"))
        mid = self._snapshot()
        self.assertEqual(mid.stage.occurrences[0].display_state, StageDisplayState.RUNNING)
        self.assertEqual(mid.stage.current_stage.stage_id, "REALITY_READ")
        _append(self.store, _stage_completed("s1-done"))
        done = self._snapshot()
        self.assertEqual(done.stage.occurrences[0].display_state, StageDisplayState.COMPLETED)
        self.assertIsNone(done.stage.current_stage)

    def test_stage_failed(self) -> None:
        _append(self.store, _stage_started("s1"))
        _append(self.store, _stage_failed("s1-fail"))
        snapshot = self._snapshot()
        self.assertEqual(snapshot.stage.occurrences[0].display_state, StageDisplayState.FAILED)

    def test_multiple_occurrences_by_resume_n(self) -> None:
        _append(self.store, _stage_started("s1", stage_id="CANDIDATE_ASSEMBLY", resume_n=0))
        _append(self.store, _stage_completed("s1-done", stage_id="CANDIDATE_ASSEMBLY", resume_n=0))
        _append(self.store, _stage_started("s2", stage_id="CANDIDATE_ASSEMBLY", resume_n=1))
        snapshot = self._snapshot()
        self.assertEqual(len(snapshot.stage.occurrences), 2)
        self.assertEqual(snapshot.stage.occurrences[1].display_state, StageDisplayState.RUNNING)

    def test_replay_does_not_duplicate_occurrence(self) -> None:
        event = _build_event(**_stage_started("s1"))
        run = self.store.get_run("run-001")
        change = project_agent_run_event(run, event)
        first = self.store.append_event_and_project_run(
            event=event,
            expected_projection_version=run.projection_version,
            projection_change=change,
        )
        replay = self.store.append_event_and_project_run(
            event=event,
            expected_projection_version=self.store.get_run("run-001").projection_version,
            projection_change=change,
        )
        self.assertEqual(first.outcome, RecordOutcome.CREATED)
        self.assertEqual(replay.outcome, RecordOutcome.IDEMPOTENT_REPLAY)
        snapshot = self._snapshot()
        self.assertEqual(len(snapshot.stage.occurrences), 1)

    def test_contradictory_duplicate_start_is_inconsistent(self) -> None:
        _append(self.store, _stage_started("s1"))
        _append(self.store, _stage_started("s1-dup"))
        snapshot = self._snapshot()
        self.assertEqual(snapshot.stage.derivation_state, DerivationState.INCONSISTENT)


class HitlDerivationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _memory_store_factory()
        self.port = AgentControlRoomQueryPort(self.store)

    def test_waiting_view(self) -> None:
        self.store.create_run(
            _build_run(
                operational_status=OperationalStatus.WAITING_FOR_HUMAN,
                interrupt_id="intr-001",
            )
        )
        _append(
            self.store,
            {
                "event_id": "wait-1",
                "event_type": EventType.HUMAN_WAIT_STARTED,
                "family": EventFamily.HITL,
                "stage_id": "HUMAN_GATE",
                "node_name": "human_wait",
                "resume_n": 1,
                "interrupt_id": "intr-001",
                "title": "Human wait started",
                "human_decision_request": _hitl_request(),
            },
        )
        snapshot = self.port.get_run_snapshot("run-001")
        view = snapshot.human_wait
        self.assertTrue(view.waiting_for_human)
        self.assertEqual(view.interrupt_id, "intr-001")
        self.assertEqual(view.wait_ordinal, 1)
        surface = snapshot.human_decision_surface
        self.assertFalse(surface.authority_modeled)
        self.assertIsNotNone(surface.request)
        self.assertEqual(surface.request.reason_code, "AMBIGUOUS_SCOPE")
        self.assertEqual(surface.request.derivation_state, DerivationState.OK)

    def test_legacy_wait_without_request_is_incomplete(self) -> None:
        self.store.create_run(
            _build_run(
                operational_status=OperationalStatus.WAITING_FOR_HUMAN,
                interrupt_id="intr-001",
            )
        )
        _append(
            self.store,
            {
                "event_id": "wait-legacy",
                "event_type": EventType.HUMAN_WAIT_STARTED,
                "family": EventFamily.HITL,
                "stage_id": "HUMAN_GATE",
                "node_name": "human_wait",
                "resume_n": 1,
                "interrupt_id": "intr-001",
                "title": "Human wait started",
                "detail": {
                    "reason_code": "FAKE_REASON",
                    "allowed_decisions": ["FAKE"],
                },
                "allow_legacy_missing_hitl_subcontracts": True,
            },
        )
        surface = self.port.get_run_snapshot("run-001").human_decision_surface
        self.assertIsNotNone(surface.request)
        self.assertEqual(surface.request.derivation_state, DerivationState.INCOMPLETE)
        self.assertEqual(surface.request.reason_code, "")
        self.assertEqual(surface.request.allowed_decisions, ())

    def test_run_resumed_closes_wait(self) -> None:
        self.store.create_run(_build_run(operational_status=OperationalStatus.RUNNING, resume_n=1))
        _append(
            self.store,
            {
                "event_id": "wait-1",
                "event_type": EventType.HUMAN_WAIT_STARTED,
                "family": EventFamily.HITL,
                "stage_id": "HUMAN_GATE",
                "node_name": "human_wait",
                "resume_n": 1,
                "interrupt_id": "intr-001",
                "title": "Human wait started",
                "human_decision_request": _hitl_request(),
            },
        )
        _append(
            self.store,
            {
                "event_id": "dec-1",
                "event_type": EventType.HUMAN_DECISION_RECEIVED,
                "family": EventFamily.HITL,
                "stage_id": "HUMAN_GATE",
                "node_name": "human_wait",
                "resume_n": 1,
                "interrupt_id": "intr-001",
                "decision_id": "dec-001",
                "title": "Human decision received",
                "human_decision_record": _hitl_record(),
            },
        )
        _append(
            self.store,
            {
                "event_id": "res-1",
                "event_type": EventType.RUN_RESUMED,
                "family": EventFamily.HITL,
                "stage_id": "HUMAN_GATE",
                "node_name": "human_wait",
                "resume_n": 1,
                "decision_id": "dec-001",
                "title": "Run resumed",
            },
        )
        view = self.port.get_run_snapshot("run-001").human_wait
        self.assertFalse(view.waiting_for_human)
        self.assertEqual(view.wait_closed_by, WaitClosedBy.RESUMED)
        self.assertEqual(view.decision_id, "dec-001")
        surface = self.port.get_run_snapshot("run-001").human_decision_surface
        self.assertIsNotNone(surface.decision)
        self.assertEqual(surface.decision.decision_code, "CLARIFY_SCOPE")
        self.assertEqual(surface.consequence.closed_by, WaitClosedBy.RESUMED)

    def test_run_aborted_closes_wait(self) -> None:
        self.store.create_run(
            _build_run(
                operational_status=OperationalStatus.WAITING_FOR_HUMAN,
                interrupt_id="intr-001",
            )
        )
        _append(
            self.store,
            {
                "event_id": "wait-1",
                "event_type": EventType.HUMAN_WAIT_STARTED,
                "family": EventFamily.HITL,
                "stage_id": "HUMAN_GATE",
                "node_name": "human_wait",
                "resume_n": 1,
                "interrupt_id": "intr-001",
                "title": "Human wait started",
                "allow_legacy_missing_hitl_subcontracts": True,
            },
        )
        _append(
            self.store,
            {
                "event_id": "abort-1",
                "event_type": EventType.RUN_ABORTED,
                "family": EventFamily.RUN_CONTROL,
                "stage_id": "HUMAN_GATE",
                "node_name": "human_wait",
                "resume_n": 1,
                "decision_id": "dec-abort",
                "title": "Run aborted",
                "status": EventStatus.FAILED,
                "occurred_at": EVEN_LATER_AT,
                "allow_legacy_missing_hitl_subcontracts": True,
            },
        )
        view = self.port.get_run_snapshot("run-001").human_wait
        self.assertEqual(view.wait_closed_by, WaitClosedBy.ABORTED)


class HumanDecisionSurfaceTests(unittest.TestCase):
    def _for_each_store(self, test_fn: Callable[[ObservabilityStore, str], None]) -> None:
        for label, factory in STORE_FACTORIES:
            with self.subTest(store=label):
                store = factory()
                try:
                    test_fn(store, label)
                finally:
                    close = getattr(store, "close", None)
                    if callable(close):
                        close()

    def test_multi_wait_isolation(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run(operational_status=OperationalStatus.RUNNING, resume_n=2))
            port = AgentControlRoomQueryPort(store)
            _append(
                store,
                {
                    "event_id": "wait-1",
                    "event_type": EventType.HUMAN_WAIT_STARTED,
                    "family": EventFamily.HITL,
                    "stage_id": "HUMAN_GATE",
                    "resume_n": 1,
                    "interrupt_id": "intr-a",
                    "title": "Wait 1",
                    "human_decision_request": _hitl_request(reason_code="REASON_A"),
                },
            )
            _append(
                store,
                {
                    "event_id": "dec-1",
                    "event_type": EventType.HUMAN_DECISION_RECEIVED,
                    "family": EventFamily.HITL,
                    "stage_id": "HUMAN_GATE",
                    "resume_n": 1,
                    "interrupt_id": "intr-a",
                    "decision_id": "dec-a",
                    "title": "Decision 1",
                    "human_decision_record": _hitl_record(decision_code="CLARIFY_SCOPE"),
                },
            )
            _append(
                store,
                {
                    "event_id": "res-1",
                    "event_type": EventType.RUN_RESUMED,
                    "family": EventFamily.HITL,
                    "stage_id": "HUMAN_GATE",
                    "resume_n": 1,
                    "decision_id": "dec-a",
                    "title": "Resume 1",
                },
            )
            _append(
                store,
                {
                    "event_id": "wait-2",
                    "event_type": EventType.HUMAN_WAIT_STARTED,
                    "family": EventFamily.HITL,
                    "stage_id": "HUMAN_GATE",
                    "resume_n": 2,
                    "interrupt_id": "intr-b",
                    "title": "Wait 2",
                    "occurred_at": EVEN_LATER_AT,
                    "human_decision_request": _hitl_request(reason_code="REASON_B"),
                },
            )
            snapshot = port.get_run_snapshot("run-001")
            surface = snapshot.human_decision_surface
            self.assertEqual(surface.wait.wait_ordinal, 2)
            self.assertEqual(surface.request.reason_code, "REASON_B")
            self.assertIsNone(surface.decision)

        self._for_each_store(exercise)

    def test_detail_ban_on_human_decision_surface(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(
                _build_run(
                    operational_status=OperationalStatus.WAITING_FOR_HUMAN,
                    interrupt_id="intr-001",
                )
            )
            _append(
                store,
                {
                    "event_id": "wait-fake",
                    "event_type": EventType.HUMAN_WAIT_STARTED,
                    "family": EventFamily.HITL,
                    "stage_id": "HUMAN_GATE",
                    "resume_n": 1,
                    "interrupt_id": "intr-001",
                    "title": "Wait",
                    "detail": {
                        "reason_code": "FAKE_REASON",
                        "decision_type": "FAKE_DECISION",
                        "actor_id": "fake",
                        "allowed_decisions": ["FAKE"],
                        "evidence_refs": ["fake"],
                    },
                    "allow_legacy_missing_hitl_subcontracts": True,
                },
            )
            surface = AgentControlRoomQueryPort(store).get_run_snapshot("run-001").human_decision_surface
            self.assertEqual(surface.request.reason_code, "")
            self.assertNotIn("FAKE", surface.request.allowed_decisions)

        self._for_each_store(exercise)


class HandoffDerivationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _memory_store_factory()
        self.port = AgentControlRoomQueryPort(self.store)
        self.store.create_run(_build_run(operational_status=OperationalStatus.RUNNING, started_at=FIXED_AT))

    def test_handoff_created_and_persisted(self) -> None:
        _append(
            self.store,
            {
                "event_id": "ho-create",
                "event_type": EventType.HANDOFF_CREATED,
                "family": EventFamily.HANDOFF,
                "stage_id": "HANDOFF_PREPARATION",
                "node_name": "persist_handoff",
                "handoff_id": "handoff-001",
                "artifact_type": "package",
                "artifact_id": "pkg-001",
                "title": "Handoff created",
                "handoff_observability": _handoff_context(),
                "detail": {
                    "source_agent": "SHOULD_NOT_DERIVE",
                    "target_role": "SHOULD_NOT_DERIVE",
                    "candidate_count": "999",
                },
            },
        )
        _append(
            self.store,
            {
                "event_id": "ho-persist",
                "event_type": EventType.HANDOFF_PERSISTED,
                "family": EventFamily.HANDOFF,
                "stage_id": "HANDOFF_PERSISTENCE",
                "node_name": "persist_handoff",
                "handoff_id": "handoff-001",
                "title": "Handoff persisted",
            },
        )
        view = self.port.get_run_snapshot("run-001").handoff
        self.assertEqual(view.handoff_id, "handoff-001")
        self.assertEqual(view.status, HandoffStatus.PERSISTED)
        self.assertIsNotNone(view.created_at)
        self.assertIsNotNone(view.persisted_at)
        self.assertIsNone(view.failed_at)
        self.assertEqual(view.handoff_type, "CONSTRUCTOR_TO_ADMISSION")
        self.assertEqual(view.target_role_code, "MONTHLY_PLAN_ADMISSION_AGENT")
        self.assertEqual(view.artifact_type, "package")
        self.assertEqual(view.artifact_id, "pkg-001")
        self.assertEqual(view.derivation_state, DerivationState.OK)
        self.assertNotIn("source_agent", view.__dict__)
        self.assertNotIn("target_role", view.__dict__)

    def test_handoff_persist_failed(self) -> None:
        _append(
            self.store,
            {
                "event_id": "ho-create",
                "event_type": EventType.HANDOFF_CREATED,
                "family": EventFamily.HANDOFF,
                "stage_id": "HANDOFF_PREPARATION",
                "node_name": "persist_handoff",
                "handoff_id": "handoff-001",
                "artifact_type": "package",
                "artifact_id": "pkg-001",
                "title": "Handoff created",
                "handoff_observability": _handoff_context(),
            },
        )
        _append(
            self.store,
            {
                "event_id": "ho-fail",
                "event_type": EventType.HANDOFF_PERSIST_FAILED,
                "family": EventFamily.HANDOFF,
                "stage_id": "HANDOFF_PERSISTENCE",
                "node_name": "persist_handoff",
                "handoff_id": "handoff-001",
                "title": "Handoff persist failed",
                "status": EventStatus.FAILED,
                "occurred_at": LATER_AT,
            },
        )
        view = self.port.get_run_snapshot("run-001").handoff
        self.assertEqual(view.status, HandoffStatus.PERSIST_FAILED)
        self.assertEqual(view.failed_at, LATER_AT)
        self.assertIsNone(view.persisted_at)

    def test_legacy_handoff_incomplete_professional_semantics(self) -> None:
        _append(
            self.store,
            {
                "event_id": "ho-create-legacy",
                "event_type": EventType.HANDOFF_CREATED,
                "family": EventFamily.HANDOFF,
                "stage_id": "HANDOFF_PREPARATION",
                "node_name": "persist_handoff",
                "handoff_id": "handoff-legacy",
                "title": "Handoff created",
                "detail": {
                    "handoff_type": "FAKE_TYPE",
                    "target_role": "FAKE_ROLE",
                    "source_agent": "FAKE_AGENT",
                },
                "allow_legacy_missing_handoff_subcontract": True,
            },
        )
        view = self.port.get_run_snapshot("run-001").handoff
        self.assertEqual(view.handoff_id, "handoff-legacy")
        self.assertEqual(view.status, HandoffStatus.CREATED)
        self.assertIsNone(view.handoff_type)
        self.assertIsNone(view.target_role_code)
        self.assertEqual(view.derivation_state, DerivationState.INCOMPLETE)
        self.assertNotIn("source_agent", view.__dict__)
        self.assertNotIn("receiver_observed", view.__dict__)
        self.assertNotIn("target_run_id", view.__dict__)


class ProfessionalExecutionPathTests(unittest.TestCase):
    def _for_each_store(self, test_fn: Callable[[ObservabilityStore, str], None]) -> None:
        for label, factory in STORE_FACTORIES:
            with self.subTest(store=label):
                store = factory()
                try:
                    test_fn(store, label)
                finally:
                    close = getattr(store, "close", None)
                    if callable(close):
                        close()

    def test_stage_steps_in_event_order(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run(operational_status=OperationalStatus.RUNNING, started_at=FIXED_AT))
            _append(store, _stage_started("s1", stage_id="AUTHORIZATION"))
            _append(store, _stage_completed("s1-done", stage_id="AUTHORIZATION"))
            _append(store, _stage_started("s2", stage_id="REALITY_READ"))
            path = AgentControlRoomQueryPort(store).get_run_snapshot("run-001").professional_execution_path
            self.assertEqual(len(path.steps), 2)
            self.assertEqual(path.steps[0].step_kind, ProfessionalExecutionStepKind.STAGE)
            self.assertEqual(path.steps[0].stage_id, "AUTHORIZATION")
            self.assertEqual(path.steps[0].professional_state, ProfessionalExecutionState.COMPLETED)
            self.assertEqual(path.steps[1].stage_id, "REALITY_READ")
            self.assertEqual(path.steps[1].professional_state, ProfessionalExecutionState.RUNNING)

        self._for_each_store(exercise)

    def test_tools_correlated_to_stage(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run(operational_status=OperationalStatus.RUNNING, started_at=FIXED_AT))
            _append(store, _stage_started("s1", stage_id="REALITY_READ"))
            _append(
                store,
                {
                    "event_id": "tool-start",
                    "event_type": EventType.TOOL_CALL_STARTED,
                    "family": EventFamily.TOOL,
                    "stage_id": "REALITY_READ",
                    "node_name": "load_reality",
                    "tool_name": "load_constructor_scope",
                    "title": "Tool started",
                },
            )
            _append(
                store,
                {
                    "event_id": "tool-done",
                    "event_type": EventType.TOOL_CALL_COMPLETED,
                    "family": EventFamily.TOOL,
                    "stage_id": "REALITY_READ",
                    "node_name": "load_reality",
                    "tool_name": "load_constructor_scope",
                    "title": "Tool completed",
                    "occurred_at": LATER_AT,
                },
            )
            _append(store, _stage_completed("s1-done", stage_id="REALITY_READ"))
            step = AgentControlRoomQueryPort(store).get_run_snapshot("run-001").professional_execution_path.steps[0]
            self.assertEqual(len(step.tools), 1)
            self.assertEqual(step.tools[0].tool_name, "load_constructor_scope")
            self.assertEqual(step.tools[0].status, ToolExecutionStatus.COMPLETED)

        self._for_each_store(exercise)

    def test_artifacts_correlated_to_stage(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run(operational_status=OperationalStatus.RUNNING, started_at=FIXED_AT))
            _append(store, _stage_started("s1", stage_id="CANDIDATE_ASSEMBLY"))
            _append(
                store,
                {
                    "event_id": "art-1",
                    "event_type": EventType.ARTIFACT_CREATED,
                    "family": EventFamily.ARTIFACT,
                    "stage_id": "CANDIDATE_ASSEMBLY",
                    "node_name": "assemble",
                    "artifact_type": "package",
                    "artifact_id": "pkg-001",
                    "title": "Package created",
                },
            )
            _append(store, _stage_completed("s1-done", stage_id="CANDIDATE_ASSEMBLY"))
            step = AgentControlRoomQueryPort(store).get_run_snapshot("run-001").professional_execution_path.steps[0]
            self.assertEqual(len(step.artifacts), 1)
            self.assertEqual(step.artifacts[0].artifact_type, "package")
            self.assertEqual(step.artifacts[0].artifact_id, "pkg-001")

        self._for_each_store(exercise)

    def test_human_gate_step_inserted(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(
                _build_run(
                    operational_status=OperationalStatus.WAITING_FOR_HUMAN,
                    interrupt_id="intr-001",
                )
            )
            _append(
                store,
                {
                    "event_id": "wait-1",
                    "event_type": EventType.HUMAN_WAIT_STARTED,
                    "family": EventFamily.HITL,
                    "stage_id": "HUMAN_GATE",
                    "resume_n": 1,
                    "interrupt_id": "intr-001",
                    "title": "Wait",
                    "human_decision_request": _hitl_request(),
                },
            )
            path = AgentControlRoomQueryPort(store).get_run_snapshot("run-001").professional_execution_path
            hitl_steps = [s for s in path.steps if s.step_kind is ProfessionalExecutionStepKind.HUMAN_DECISION]
            self.assertEqual(len(hitl_steps), 1)
            self.assertEqual(hitl_steps[0].stage_id, "HUMAN_GATE")
            self.assertIsNotNone(hitl_steps[0].human_decision)
            self.assertEqual(hitl_steps[0].human_decision.request.reason_code, "AMBIGUOUS_SCOPE")

        self._for_each_store(exercise)

    def test_reality_refresh_step_inserted(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run(operational_status=OperationalStatus.RUNNING, resume_n=1))
            _append(
                store,
                {
                    "event_id": "rr-start",
                    "event_type": EventType.REALITY_REFRESH_STARTED,
                    "family": EventFamily.REALITY,
                    "stage_id": "REALITY_REVALIDATION",
                    "resume_n": 1,
                    "title": "Refresh started",
                },
            )
            _append(
                store,
                {
                    "event_id": "rr-done",
                    "event_type": EventType.REALITY_REFRESH_COMPLETED,
                    "family": EventFamily.REALITY,
                    "stage_id": "REALITY_REVALIDATION",
                    "resume_n": 1,
                    "title": "Refresh done",
                    "occurred_at": LATER_AT,
                },
            )
            path = AgentControlRoomQueryPort(store).get_run_snapshot("run-001").professional_execution_path
            refresh_steps = [s for s in path.steps if s.step_kind is ProfessionalExecutionStepKind.REALITY_REFRESH]
            self.assertEqual(len(refresh_steps), 1)
            self.assertEqual(refresh_steps[0].professional_state, ProfessionalExecutionState.COMPLETED)
            self.assertIsNotNone(refresh_steps[0].reality_refresh.completed_at)

        self._for_each_store(exercise)

    def test_multi_wait_separated_in_path(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run(operational_status=OperationalStatus.WAITING_FOR_HUMAN, resume_n=2))
            _append(
                store,
                {
                    "event_id": "wait-1",
                    "event_type": EventType.HUMAN_WAIT_STARTED,
                    "family": EventFamily.HITL,
                    "stage_id": "HUMAN_GATE",
                    "resume_n": 1,
                    "interrupt_id": "intr-a",
                    "human_decision_request": _hitl_request(reason_code="REASON_A"),
                },
            )
            _append(
                store,
                {
                    "event_id": "dec-1",
                    "event_type": EventType.HUMAN_DECISION_RECEIVED,
                    "family": EventFamily.HITL,
                    "stage_id": "HUMAN_GATE",
                    "resume_n": 1,
                    "interrupt_id": "intr-a",
                    "decision_id": "dec-a",
                    "human_decision_record": _hitl_record(decision_code="CLARIFY_SCOPE"),
                },
            )
            _append(
                store,
                {
                    "event_id": "res-1",
                    "event_type": EventType.RUN_RESUMED,
                    "family": EventFamily.HITL,
                    "stage_id": "HUMAN_GATE",
                    "resume_n": 1,
                    "decision_id": "dec-a",
                },
            )
            _append(
                store,
                {
                    "event_id": "rr-start",
                    "event_type": EventType.REALITY_REFRESH_STARTED,
                    "family": EventFamily.REALITY,
                    "stage_id": "REALITY_REVALIDATION",
                    "resume_n": 1,
                },
            )
            _append(
                store,
                {
                    "event_id": "rr-done",
                    "event_type": EventType.REALITY_REFRESH_COMPLETED,
                    "family": EventFamily.REALITY,
                    "stage_id": "REALITY_REVALIDATION",
                    "resume_n": 1,
                    "occurred_at": LATER_AT,
                },
            )
            _append(store, _stage_started("work", stage_id="CANDIDATE_ASSEMBLY", resume_n=1))
            _append(
                store,
                {
                    "event_id": "wait-2",
                    "event_type": EventType.HUMAN_WAIT_STARTED,
                    "family": EventFamily.HITL,
                    "stage_id": "HUMAN_GATE",
                    "resume_n": 2,
                    "interrupt_id": "intr-b",
                    "occurred_at": EVEN_LATER_AT,
                    "human_decision_request": _hitl_request(reason_code="REASON_B"),
                },
            )
            path = AgentControlRoomQueryPort(store).get_run_snapshot("run-001").professional_execution_path
            hitl_steps = [s for s in path.steps if s.step_kind is ProfessionalExecutionStepKind.HUMAN_DECISION]
            self.assertEqual(len(hitl_steps), 2)
            self.assertEqual(hitl_steps[0].human_decision.request.reason_code, "REASON_A")
            self.assertEqual(hitl_steps[0].human_decision.decision.decision_code, "CLARIFY_SCOPE")
            self.assertEqual(hitl_steps[1].human_decision.request.reason_code, "REASON_B")
            self.assertIsNone(hitl_steps[1].human_decision.decision)
            self.assertIsNotNone(hitl_steps[0].human_decision.consequence.reality_refresh_completed_at)

        self._for_each_store(exercise)

    def test_incomplete_history_flag(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run())
            for index in range(3):
                _append(
                    store,
                    {
                        "event_id": f"evt-{index}",
                        "event_type": EventType.RUN_REQUESTED if index == 0 else EventType.RUN_ADVANCING,
                        "family": EventFamily.RUN_CONTROL,
                        "title": f"event {index}",
                        "occurred_at": FIXED_AT + timedelta(seconds=index),
                    },
                )
            path = AgentControlRoomQueryPort(store).get_run_snapshot("run-001", event_limit=2).professional_execution_path
            self.assertFalse(path.history_complete)
            self.assertEqual(path.derivation_state, DerivationState.INCOMPLETE)

        self._for_each_store(exercise)

    def test_no_detail_fallback_on_path(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(
                _build_run(
                    operational_status=OperationalStatus.WAITING_FOR_HUMAN,
                    interrupt_id="intr-001",
                )
            )
            _append(
                store,
                {
                    "event_id": "wait-fake",
                    "event_type": EventType.HUMAN_WAIT_STARTED,
                    "family": EventFamily.HITL,
                    "stage_id": "HUMAN_GATE",
                    "resume_n": 1,
                    "interrupt_id": "intr-001",
                    "detail": {
                        "reason_code": "FAKE_REASON",
                        "allowed_decisions": ["FAKE"],
                    },
                    "allow_legacy_missing_hitl_subcontracts": True,
                },
            )
            step = AgentControlRoomQueryPort(store).get_run_snapshot("run-001").professional_execution_path.steps[0]
            self.assertEqual(step.human_decision.request.reason_code, "")
            self.assertNotIn("FAKE", step.human_decision.request.allowed_decisions)

        self._for_each_store(exercise)


class QueryPortValidationTests(unittest.TestCase):
    def test_invalid_limits(self) -> None:
        port = AgentControlRoomQueryPort(_memory_store_factory())
        with self.assertRaises(ControlRoomQueryBlockerError) as ctx:
            port.list_runs(limit=0)
        self.assertEqual(ctx.exception.code, CODE_CONTROL_ROOM_QUERY_BLOCKER)
        with self.assertRaises(ControlRoomQueryBlockerError):
            port.get_run_snapshot("run-001", event_limit=501)


if __name__ == "__main__":
    unittest.main()
