"""
Increment 10.4 — Durable ObservabilityStore + StoreObservabilityRecorder tests.

Non-Postgres. No Supabase. No Control Room. No subprocess 10.5 proof.
"""

from __future__ import annotations

import ast
import inspect
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

from agents.observability.contracts import (
    EventStatus,
    EventType,
    InitiatorType,
    ObservabilityContractError,
    OperationalStatus,
    TriggerType,
    build_agent_run,
    build_human_decision_request_observability_context,
    build_observability_event,
)
from agents.observability.durable_recorder import StoreObservabilityRecorder
from agents.observability.projection import project_agent_run_event
from agents.observability.recorder import (
    InMemoryObservabilityRecorder,
    ObservabilityEventConflictError,
    ObservabilityRecorder,
    RecordOutcome,
    compute_observability_event_fingerprint,
)
from agents.observability.store import (
    CODE_OBSERVABILITY_PROJECTION_VERSION_CONFLICT,
    CODE_OBSERVABILITY_RUN_IDENTITY_CONFLICT,
    CODE_OBSERVABILITY_RUN_NOT_FOUND,
    CODE_OBSERVABILITY_STORE_BLOCKER,
    CreateRunOutcome,
    InMemoryObservabilityStore,
    ObservabilityProjectionVersionConflictError,
    ObservabilityRunIdentityConflictError,
    ObservabilityRunNotFoundError,
    ObservabilityStorageFailureError,
    ObservabilityStore,
    compute_agent_run_identity_digest,
)
from agents.observability.sqlite_store import SqliteObservabilityStore

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXED_AT = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
ALT_AT = datetime(2026, 9, 2, 12, 0, 1, tzinfo=timezone.utc)
LATER_AT = datetime(2026, 9, 2, 12, 0, 2, tzinfo=timezone.utc)
TERMINAL_AT = datetime(2026, 9, 2, 13, 0, 0, tzinfo=timezone.utc)

_NEW_STORE_MODULES = (
    REPO_ROOT / "agents" / "observability" / "store.py",
    REPO_ROOT / "agents" / "observability" / "projection.py",
    REPO_ROOT / "agents" / "observability" / "sqlite_store.py",
    REPO_ROOT / "agents" / "observability" / "durable_recorder.py",
)

_FORBIDDEN_IMPORTS = frozenset(
    {
        "agents.monthly_plan_constructor",
        "streamlit",
        "supabase",
        "langgraph",
    }
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
        "detail": {"phase": "request"},
    }
    payload.update(overrides)
    return payload


def _build_event(**overrides: Any):
    return build_observability_event(**_event_kwargs(**overrides))


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


class StoreContractTests(unittest.TestCase):
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

    def test_create_run_get_run_round_trip(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            run = _build_run()
            created = store.create_run(run)
            self.assertEqual(created.outcome, CreateRunOutcome.CREATED)
            loaded = store.get_run(run.run_id)
            self.assertEqual(loaded.run_id, run.run_id)
            self.assertEqual(loaded.projection_version, 0)

        self._for_each_store(exercise)

    def test_idempotent_create_same_identity(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            run = _build_run()
            first = store.create_run(run)
            second = store.create_run(run)
            self.assertEqual(first.outcome, CreateRunOutcome.CREATED)
            self.assertEqual(second.outcome, CreateRunOutcome.IDEMPOTENT_REPLAY)

        self._for_each_store(exercise)

    def test_create_run_identity_conflict(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run())
            with self.assertRaises(ObservabilityRunIdentityConflictError) as ctx:
                store.create_run(_build_run(request_id="req-other"))
            self.assertEqual(ctx.exception.code, CODE_OBSERVABILITY_RUN_IDENTITY_CONFLICT)

        self._for_each_store(exercise)

    def test_atomic_append_and_projection_increment(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run())
            recorder = StoreObservabilityRecorder(store)
            result = recorder.record_event(_build_event(event_id="evt-a"))
            self.assertEqual(result.outcome, RecordOutcome.CREATED)
            run = store.get_run("run-001")
            self.assertEqual(run.operational_status, OperationalStatus.REQUESTED)
            self.assertEqual(run.projection_version, 1)

        self._for_each_store(exercise)

    def test_event_idempotent_replay(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run())
            recorder = StoreObservabilityRecorder(store)
            event = _build_event(event_id="evt-replay")
            first = recorder.record_event(event)
            second = recorder.record_event(event)
            self.assertEqual(first.outcome, RecordOutcome.CREATED)
            self.assertEqual(second.outcome, RecordOutcome.IDEMPOTENT_REPLAY)
            self.assertEqual(store.get_run("run-001").projection_version, 1)

        self._for_each_store(exercise)

    def test_replay_after_later_events_keeps_version(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run())
            recorder = StoreObservabilityRecorder(store)
            event_a = _build_event(event_id="evt-a", event_type=EventType.RUN_REQUESTED)
            event_b = _build_event(
                event_id="evt-b",
                event_type=EventType.RUN_STARTED,
                occurred_at=ALT_AT,
                title="Run started",
            )
            recorder.record_event(event_a)
            recorder.record_event(event_b)
            self.assertEqual(store.get_run("run-001").projection_version, 2)
            replay = store.append_event_and_project_run(
                event=event_a,
                expected_projection_version=0,
                projection_change=project_agent_run_event(_build_run(), event_a),
            )
            self.assertEqual(replay.outcome, RecordOutcome.IDEMPOTENT_REPLAY)
            self.assertEqual(store.get_run("run-001").projection_version, 2)

        self._for_each_store(exercise)

    def test_fingerprint_conflict(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run())
            recorder = StoreObservabilityRecorder(store)
            recorder.record_event(_build_event(event_id="evt-conflict"))
            with self.assertRaises(ObservabilityEventConflictError):
                recorder.record_event(_build_event(event_id="evt-conflict", title="Different"))

        self._for_each_store(exercise)

    def test_projection_version_conflict(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run())
            event = _build_event(event_id="evt-stale")
            change = project_agent_run_event(_build_run(), event)
            with self.assertRaises(ObservabilityProjectionVersionConflictError) as ctx:
                store.append_event_and_project_run(
                    event=event,
                    expected_projection_version=99,
                    projection_change=change,
                )
            self.assertEqual(ctx.exception.code, CODE_OBSERVABILITY_PROJECTION_VERSION_CONFLICT)
            self.assertEqual(store.list_events("run-001"), ())

        self._for_each_store(exercise)

    def test_deterministic_list_events_order_and_timestamp_collision(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run())
            recorder = StoreObservabilityRecorder(store)
            recorder.record_event(
                _build_event(event_id="evt-1", occurred_at=FIXED_AT, title="first")
            )
            recorder.record_event(
                _build_event(
                    event_id="evt-2",
                    event_type=EventType.RUN_STARTED,
                    occurred_at=FIXED_AT,
                    title="second",
                )
            )
            ids = [event.event_id for event in store.list_events("run-001")]
            self.assertEqual(ids, ["evt-1", "evt-2"])

        self._for_each_store(exercise)

    def test_list_bounds(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            from agents.observability.store import ObservabilityStoreError

            store.create_run(_build_run())
            with self.assertRaises(ObservabilityStoreError):
                store.list_events("run-001", limit=0)
            with self.assertRaises(ObservabilityStoreError):
                store.list_runs(limit=0)

        self._for_each_store(exercise)

    def test_unknown_run_event_fail_closed(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            recorder = StoreObservabilityRecorder(store)
            with self.assertRaises(Exception) as ctx:
                recorder.record_event(_build_event())
            self.assertIn(
                ctx.exception.code,
                {CODE_OBSERVABILITY_STORE_BLOCKER, CODE_OBSERVABILITY_RUN_NOT_FOUND},
            )

        self._for_each_store(exercise)


class SqliteDurabilityTests(unittest.TestCase):
    def test_object_reopen_preserves_run_and_events(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as handle:
            path = handle.name
        store_a = SqliteObservabilityStore(path)
        store_a.create_run(_build_run())
        recorder = StoreObservabilityRecorder(store_a)
        recorder.record_event(_build_event(event_id="evt-dur-1"))
        recorder.record_event(
            _build_event(
                event_id="evt-dur-2",
                event_type=EventType.RUN_ADVANCING,
                occurred_at=ALT_AT,
                title="Run advancing",
            )
        )
        store_a.close()

        store_b = SqliteObservabilityStore(path)
        try:
            run = store_b.get_run("run-001")
            self.assertEqual(run.operational_status, OperationalStatus.RUNNING)
            self.assertEqual(run.projection_version, 2)
            events = store_b.list_events("run-001")
            self.assertEqual([event.event_id for event in events], ["evt-dur-1", "evt-dur-2"])
        finally:
            store_b.close()

    def test_projection_failure_does_not_persist_event(self) -> None:
        def exercise(store: ObservabilityStore, _label: str) -> None:
            store.create_run(_build_run())
            event = _build_event(event_id="evt-proj-fail")
            change = project_agent_run_event(_build_run(), event)
            with patch(
                "agents.observability.store.build_agent_run",
                side_effect=ObservabilityContractError(
                    "OBSERVABILITY_CONTRACT_BLOCKER",
                    "simulated projection validation failure",
                ),
            ):
                with self.assertRaises(ObservabilityContractError):
                    store.append_event_and_project_run(
                        event=event,
                        expected_projection_version=0,
                        projection_change=change,
                    )
            self.assertEqual(store.get_run("run-001").projection_version, 0)
            self.assertEqual(store.list_events("run-001"), ())

        for label, factory in STORE_FACTORIES:
            with self.subTest(store=label):
                store = factory()
                try:
                    exercise(store, label)
                finally:
                    close = getattr(store, "close", None)
                    if callable(close):
                        close()


class OperationalTruthProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryObservabilityStore()
        self.store.create_run(_build_run())
        self.recorder = StoreObservabilityRecorder(self.store)

    def _project(self, **event_overrides: Any):
        event = _build_event(**event_overrides)
        self.recorder.record_event(event)
        return self.store.get_run("run-001")

    def test_run_requested_to_requested(self) -> None:
        run = self._project(event_id="ot-req", event_type=EventType.RUN_REQUESTED)
        self.assertEqual(run.operational_status, OperationalStatus.REQUESTED)

    def test_run_authorization_started_to_authorizing(self) -> None:
        run = self._project(
            event_id="ot-auth-start",
            event_type=EventType.RUN_AUTHORIZATION_STARTED,
            title="Auth started",
        )
        self.assertEqual(run.operational_status, OperationalStatus.AUTHORIZING)

    def test_run_started_to_starting(self) -> None:
        run = self._project(
            event_id="ot-started",
            event_type=EventType.RUN_STARTED,
            title="Run started",
        )
        self.assertEqual(run.operational_status, OperationalStatus.STARTING)

    def test_run_advancing_to_running_sets_started_at(self) -> None:
        run = self._project(
            event_id="ot-adv",
            event_type=EventType.RUN_ADVANCING,
            occurred_at=ALT_AT,
            title="Run advancing",
        )
        self.assertEqual(run.operational_status, OperationalStatus.RUNNING)
        self.assertEqual(run.started_at, ALT_AT)

    def test_human_wait_started_to_waiting(self) -> None:
        self._project(
            event_id="ot-adv-first",
            event_type=EventType.RUN_ADVANCING,
            occurred_at=ALT_AT,
            title="Run advancing",
        )
        run = self._project(
            event_id="ot-wait",
            event_type=EventType.HUMAN_WAIT_STARTED,
            occurred_at=LATER_AT,
            title="Human wait",
            interrupt_id="intr-001",
            human_decision_request=build_human_decision_request_observability_context(
                reason_code="AMBIGUOUS_SCOPE",
                allowed_decisions=("CLARIFY_SCOPE", "ABORT_RUN"),
            ),
        )
        self.assertEqual(run.operational_status, OperationalStatus.WAITING_FOR_HUMAN)
        self.assertEqual(run.interrupt_id, "intr-001")

    def test_run_resumed_preserves_started_at(self) -> None:
        self._project(
            event_id="ot-adv2",
            event_type=EventType.RUN_ADVANCING,
            occurred_at=ALT_AT,
            title="Run advancing",
        )
        run = self._project(
            event_id="ot-resume",
            event_type=EventType.RUN_RESUMED,
            occurred_at=LATER_AT,
            title="Run resumed",
            resume_n=1,
        )
        self.assertEqual(run.operational_status, OperationalStatus.RUNNING)
        self.assertEqual(run.started_at, ALT_AT)

    def test_run_failed_terminal(self) -> None:
        self._project(
            event_id="ot-adv3",
            event_type=EventType.RUN_ADVANCING,
            occurred_at=ALT_AT,
            title="Run advancing",
        )
        run = self._project(
            event_id="ot-failed",
            event_type=EventType.RUN_FAILED,
            status=EventStatus.FAILED,
            occurred_at=TERMINAL_AT,
            title="Run failed",
            detail={"error_code": "READ_FAILED"},
        )
        self.assertEqual(run.operational_status, OperationalStatus.FAILED)
        self.assertEqual(run.completed_at, TERMINAL_AT)
        self.assertIsNone(run.error_code)

    def test_run_aborted_terminal(self) -> None:
        self._project(
            event_id="ot-adv4",
            event_type=EventType.RUN_ADVANCING,
            occurred_at=ALT_AT,
            title="Run advancing",
        )
        run = self._project(
            event_id="ot-abort",
            event_type=EventType.RUN_ABORTED,
            status=EventStatus.FAILED,
            occurred_at=TERMINAL_AT,
            title="Run aborted",
            decision_id="dec-abort-1",
        )
        self.assertEqual(run.operational_status, OperationalStatus.ABORTED)
        self.assertEqual(run.completed_at, TERMINAL_AT)
        self.assertEqual(run.decision_id, "dec-abort-1")

    def test_run_completed_terminal(self) -> None:
        self._project(
            event_id="ot-adv5",
            event_type=EventType.RUN_ADVANCING,
            occurred_at=ALT_AT,
            title="Run advancing",
        )
        run = self._project(
            event_id="ot-complete",
            event_type=EventType.RUN_COMPLETED,
            occurred_at=TERMINAL_AT,
            title="Run completed",
            handoff_id="hof-001",
        )
        self.assertEqual(run.operational_status, OperationalStatus.COMPLETED)
        self.assertEqual(run.completed_at, TERMINAL_AT)
        self.assertEqual(run.handoff_id, "hof-001")

    def test_stage_started_does_not_change_operational_status(self) -> None:
        self._project(
            event_id="ot-adv6",
            event_type=EventType.RUN_ADVANCING,
            occurred_at=ALT_AT,
            title="Run advancing",
        )
        run = self._project(
            event_id="ot-stage",
            event_type=EventType.STAGE_STARTED,
            occurred_at=LATER_AT,
            title="Stage started",
            stage_id="REALITY_READ",
        )
        self.assertEqual(run.operational_status, OperationalStatus.RUNNING)

    def test_free_form_detail_does_not_change_operational_status(self) -> None:
        run = self._project(
            event_id="ot-detail",
            event_type=EventType.RUN_REQUESTED,
            detail={"invented_status": "RUNNING"},
        )
        self.assertEqual(run.operational_status, OperationalStatus.REQUESTED)


class DurableRecorderTests(unittest.TestCase):
    def test_recorder_satisfies_protocol(self) -> None:
        store = InMemoryObservabilityStore()
        recorder = StoreObservabilityRecorder(store)
        self.assertIsInstance(recorder, ObservabilityRecorder)

    def test_recorder_unknown_run_fail_closed(self) -> None:
        recorder = StoreObservabilityRecorder(InMemoryObservabilityStore())
        with self.assertRaises(Exception) as ctx:
            recorder.record_event(_build_event())
        self.assertEqual(ctx.exception.code, CODE_OBSERVABILITY_STORE_BLOCKER)


class SafetyAndArchitectureTests(unittest.TestCase):
    def test_unsafe_event_rejected_before_write(self) -> None:
        store = InMemoryObservabilityStore()
        store.create_run(_build_run())
        recorder = StoreObservabilityRecorder(store)
        with self.assertRaises(ObservabilityContractError):
            recorder.record_event(
                _build_event(event_id="evt-unsafe", detail={"password": "secret"})
            )
        self.assertEqual(store.list_events("run-001"), ())

    def test_unsafe_run_rejected_before_create(self) -> None:
        store = InMemoryObservabilityStore()
        with self.assertRaises(ObservabilityContractError):
            store.create_run(_build_run(safe_summary={"api_key": "leak"}))

    def test_no_constructor_imports_in_new_modules(self) -> None:
        for path in _NEW_STORE_MODULES:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(
                            any(alias.name.startswith(prefix) for prefix in _FORBIDDEN_IMPORTS),
                            msg=f"{path.name} imports {alias.name}",
                        )
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertFalse(
                        any(node.module.startswith(prefix) for prefix in _FORBIDDEN_IMPORTS),
                        msg=f"{path.name} imports from {node.module}",
                    )

    def test_inmemory_observability_recorder_unchanged(self) -> None:
        source = inspect.getsource(InMemoryObservabilityRecorder.record_event)
        self.assertIn("IDEMPOTENT_REPLAY", source)
        self.assertIn("_validate_recordable_event", source)

    def test_identity_digest_uses_immutable_fields_only(self) -> None:
        base = _build_run()
        other = _build_run(operational_status=OperationalStatus.RUNNING, projection_version=5)
        self.assertEqual(
            compute_agent_run_identity_digest(base),
            compute_agent_run_identity_digest(other),
        )


if __name__ == "__main__":
    unittest.main()
