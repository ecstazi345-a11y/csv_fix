"""
Increment 10.10 — Constructor full managed live-run proof.

Authoritative path:
  RunControlService.start
  → ConstructorManagedRuntimeLauncher
  → LangGraph interrupt (Human Wait)
  → typed CLARIFY_SCOPE resume (Command)
  → Reality Refresh
  → handoff persist
  → RUN_COMPLETED
  → reopen SQLite + Control Room factory Query Port

No production code. No Streamlit. No product Supabase. No event fabrication.
"""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agents.control_room.dtos import DerivationState, HandoffStatus
from agents.control_room.factory import build_agent_control_room_query_port
from agents.monthly_plan_constructor.candidate_package import (
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
)
from agents.monthly_plan_constructor.durable_checkpoint import (
    build_constructor_jsonplus_serializer,
)
from agents.monthly_plan_constructor.handoff_contracts import HANDOFF_TYPE, TARGET_ROLE
from agents.monthly_plan_constructor.handoff_store import HandoffStorePutResult
from agents.monthly_plan_constructor.hitl_contracts import (
    DECISION_CLARIFY_SCOPE,
    build_resume_command,
)
from agents.monthly_plan_constructor.hitl_resume import (
    build_decision_request_from_lifecycle,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_OBSERVED_PRODUCTIVITY,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    SOURCE_PROJECT_HISTORY,
    LaborNormEvidence,
)
from agents.monthly_plan_constructor.langgraph_runtime import (
    CONSTRUCTOR_AGENT_CODE,
    build_constructor_langgraph,
    run_constructor_langgraph,
)
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_READY_FOR_HANDOFF,
    CandidateAssemblyResult,
)
from agents.monthly_plan_constructor.managed_launcher import (
    ConstructorManagedRuntimeLauncher,
)
from agents.monthly_plan_constructor.mission_scope import ConstructorMissionScope
from agents.observability.contracts import (
    EventType,
    InitiatorType,
    OperationalStatus,
    TriggerType,
)
from agents.observability.durable_recorder import StoreObservabilityRecorder
from agents.observability.recorder import (
    RecordOutcome,
    compute_observability_event_fingerprint,
)
from agents.observability.sqlite_store import SqliteObservabilityStore
from agents.observability.store import DEFAULT_LIST_EVENTS_LIMIT
from agents.run_control.contracts import ManagedRunStartInput, ManagedRuntimeLauncher
from agents.run_control.registry import InMemoryRunControlRegistry
from agents.run_control.service import RunControlService
from security.agent_execution_context import issue_read_only_agent_context

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"
MISSION_ID = "mission-10-10-live"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
FIXED_AT = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
WAIT_TIMEOUT_SECONDS = 45.0
POLL_INTERVAL_SECONDS = 0.05


def _raw(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "project_code": PROJECT,
        "month_key": MONTH,
        "facility": FACILITY_TARGET,
        "facility_building": FACILITY_TARGET,
        "discipline": DISCIPLINE_VENT,
        "construction_discipline": DISCIPLINE_VENT,
        "system": "SYS-1",
        "system_label": "SYS-1",
        "iwp": "IWP-1",
        "iwp_id": "IWP-1",
        "boq_code": "BOQ-001",
        "boq_name": "Воздуховод",
        "unit_of_measure": "м2",
    }
    base.update(overrides)
    return base


class StubAssembler:
    def __call__(self, reality_read, scope: ConstructorMissionScope):
        return CandidateAssemblyResult(
            candidates=(
                {
                    "candidate_id": CANDIDATE_ID,
                    "project_code": PROJECT,
                    "month_key": MONTH,
                    "facility": FACILITY_TARGET,
                    "discipline": DISCIPLINE_VENT,
                    "system": "SYS-1",
                    "iwp": "IWP-1",
                    "boq_code": "BOQ-001",
                    "remaining_qty": 10.0,
                    "already_planned_qty": 0.0,
                    "available_to_add_qty": 10.0,
                    "availability_status": "Доступно",
                    "labor_norm_status": LABOR_UNRESOLVED,
                },
            ),
            scanned_count=1,
        )


class ClarifyingReader:
    """Deterministic secure read double. Counts fresh reads after resume."""

    def __init__(self) -> None:
        self.calls = 0
        self.rows = [_raw()]

    def __call__(self, context, mission: ConstructorMissionScope):
        self.calls += 1
        return list(self.rows)


def _history() -> LaborNormEvidence:
    return LaborNormEvidence(
        evidence_id="ev-project-10-10",
        candidate_id=CANDIDATE_ID,
        source_type=SOURCE_PROJECT_HISTORY,
        labor_hours_per_unit=1.42,
        unit="м2",
        source_reference="project-history-run",
        source_version="2026-09",
        planning_use_status=LABOR_VALIDATED,
        basis=BASIS_OBSERVED_PRODUCTIVITY,
        hours_quality=HOURS_VALIDATED_PRODUCTIVE_DIRECT,
        executed_quantity_validated=True,
    )


class InMemoryHandoffStore:
    def __init__(self) -> None:
        self._records: dict[str, Any] = {}
        self.put_calls = 0

    def get(self, handoff_id: str):
        return self._records.get(handoff_id)

    def put_if_absent(self, handoff):
        self.put_calls += 1
        existing = self._records.get(handoff.handoff_id)
        if existing is None:
            self._records[handoff.handoff_id] = handoff
            return HandoffStorePutResult(created=True, stored_handoff=handoff)
        return HandoffStorePutResult(created=False, stored_handoff=existing)


class FakeHitlStore:
    def __init__(self) -> None:
        self.open_calls = 0
        self.answer_calls = 0

    def upsert_open_request(self, request) -> None:
        self.open_calls += 1

    def record_answer(self, *, interrupt_id: str, command) -> None:
        self.answer_calls += 1


def _poll_until(
    predicate,
    *,
    timeout: float = WAIT_TIMEOUT_SECONDS,
    interval: float = POLL_INTERVAL_SECONDS,
    label: str = "condition",
) -> None:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        if predicate():
            return
        time.sleep(interval)
    raise TimeoutError(f"timed out waiting for {label}")


def _open_store(db_path: Path) -> SqliteObservabilityStore:
    return SqliteObservabilityStore(db_path)


def _event_types_for(db_path: Path, run_id: str) -> list[EventType]:
    store = _open_store(db_path)
    try:
        return [
            event.event_type
            for event in store.list_events(run_id, limit=DEFAULT_LIST_EVENTS_LIMIT)
        ]
    finally:
        store.close()


def _events_for(db_path: Path, run_id: str):
    store = _open_store(db_path)
    try:
        return list(store.list_events(run_id, limit=DEFAULT_LIST_EVENTS_LIMIT))
    finally:
        store.close()


def _first_index(types: list[EventType], event_type: EventType) -> int:
    try:
        return types.index(event_type)
    except ValueError as exc:
        raise AssertionError(f"missing required event {event_type.value}") from exc


class ConstructorFullManagedLiveRunProof(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmpdir.name) / "observability_10_10.sqlite"
        self.control_store = SqliteObservabilityStore(self.db_path)
        self._query_port = None
        self.control_recorder = StoreObservabilityRecorder(self.control_store)
        self.registry = InMemoryRunControlRegistry()
        self.service = RunControlService(
            registry=self.registry,
            recorder=self.control_recorder,
            durable_store=self.control_store,
        )

        self.reader = ClarifyingReader()
        self.handoff_store = InMemoryHandoffStore()
        self.hitl_store = FakeHitlStore()
        self.checkpointer = InMemorySaver(
            serde=build_constructor_jsonplus_serializer()
        )
        self.captured_context = None

        self.launcher = ConstructorManagedRuntimeLauncher(
            observability_db_path=self.db_path,
            assemble_candidates=StubAssembler(),
            scope_reader=self.reader,
            labor_evidence=[_history()],
            handoff_store_factory=lambda: self.handoff_store,
            checkpointer_factory=lambda: self.checkpointer,
            hitl_store_factory=lambda: self.hitl_store,
        )
        # Deterministic clock so HUMAN_WAIT_STARTED replay on resume
        # matches the worker emit (same event_id + payload fingerprint).
        def _run_with_fixed_clock(*args: Any, **kwargs: Any) -> Any:
            kwargs.setdefault("now", FIXED_AT)
            return run_constructor_langgraph(*args, **kwargs)

        self._clock_patch = patch(
            "agents.monthly_plan_constructor.managed_launcher.run_constructor_langgraph",
            side_effect=_run_with_fixed_clock,
        )
        self._clock_patch.start()

    def tearDown(self) -> None:
        if self.launcher._last_thread is not None:
            self.launcher._last_thread.join(timeout=WAIT_TIMEOUT_SECONDS)
        self._clock_patch.stop()
        if self._query_port is not None:
            store = getattr(self._query_port, "_store", None)
            close = getattr(store, "close", None)
            if callable(close):
                close()
            self._query_port = None
        try:
            self.control_store.close()
        except Exception:
            pass
        self._tmpdir.cleanup()

    def _issue_context(self, **kwargs):
        self.captured_context = issue_read_only_agent_context(**kwargs)
        return self.captured_context

    def _start(self) -> Any:
        start_input = ManagedRunStartInput(
            agent_code=CONSTRUCTOR_AGENT_CODE,
            initiator_type=InitiatorType.HUMAN,
            initiator_id="operator-10-10",
            trigger_type=TriggerType.MANUAL,
            trigger_reason="increment-10-10-full-live-proof",
            project_code=PROJECT,
            month_key=MONTH,
            requested_mission_id=MISSION_ID,
            idempotency_key="idem-10-10-full-live",
            scope_request={
                "facility": ["ALL", FACILITY_TARGET],
                "discipline": DISCIPLINE_VENT,
            },
        )
        with patch(
            "agents.run_control.service.issue_read_only_agent_context",
            side_effect=self._issue_context,
        ):
            return self.service.start(
                start_input,
                launcher=self.launcher,
                requested_at=FIXED_AT,
            )

    def _poll_operational_status(
        self,
        run_id: str,
        expected: OperationalStatus,
        *,
        label: str,
    ):
        holder: dict[str, Any] = {"run": None}

        def ready() -> bool:
            store = _open_store(self.db_path)
            try:
                run = store.get_run(run_id)
                holder["run"] = run
                return run.operational_status is expected
            finally:
                store.close()

        try:
            _poll_until(ready, label=label)
        except TimeoutError as exc:
            run = holder["run"]
            status = None if run is None else run.operational_status
            types = _event_types_for(self.db_path, run_id)
            raise TimeoutError(
                f"{exc}; last_status={status}; event_types={[t.value for t in types]}"
            ) from exc
        return holder["run"]

    def _resume_after_wait(self, *, run_id: str) -> Any:
        assert self.captured_context is not None
        resume_store = _open_store(self.db_path)
        try:
            resume_recorder = StoreObservabilityRecorder(resume_store)
            app = build_constructor_langgraph(
                context=self.captured_context,
                project_code=PROJECT,
                month_key=MONTH,
                facility_scope=["ALL", FACILITY_TARGET],
                discipline_scope=DISCIPLINE_VENT,
                assemble_candidates=StubAssembler(),
                labor_evidence=[_history()],
                scope_reader=self.reader,
                now=FIXED_AT,
                checkpointer=self.checkpointer,
                hitl_store=self.hitl_store,
                handoff_store=self.handoff_store,
                recorder=resume_recorder,
            )
            config = {"configurable": {"thread_id": run_id}}
            snap = app.get_state(config)
            lifecycle = snap.values["lifecycle"]
            self.assertEqual(lifecycle.status, "WAITING_FOR_HUMAN")
            req = build_decision_request_from_lifecycle(lifecycle)
            checkpoint_id = snap.config["configurable"]["checkpoint_id"]
            cmd = build_resume_command(
                decision_id="dec-10-10-clarify",
                interrupt_id=req.interrupt_id,
                run_id=run_id,
                mission_id=MISSION_ID,
                decision=DECISION_CLARIFY_SCOPE,
                actor_id="operator-10-10",
                parameters={"facility_scope": [FACILITY_TARGET]},
                expected_checkpoint_id=checkpoint_id,
                submitted_at=FIXED_AT,
            )
            out = app.invoke(Command(resume=cmd), config)
            return out, req, cmd
        finally:
            resume_store.close()

    def test_constructor_full_managed_live_run_end_to_end(self) -> None:
        self.assertIsInstance(self.launcher, ManagedRuntimeLauncher)

        # --- 1. Managed start ---
        result = self._start()
        run_id = result.agent_run.run_id
        self.assertEqual(result.agent_run.operational_status, OperationalStatus.STARTING)
        self.assertEqual(result.agent_run.agent_code, CONSTRUCTOR_AGENT_CODE)
        self.assertEqual(result.agent_run.mission_id, MISSION_ID)
        self.assertIsNotNone(self.captured_context)
        self.assertEqual(self.captured_context.run_id, run_id)
        authorization_id = result.agent_run.authorization_id

        # --- 2. Runtime advancing ---
        _poll_until(
            lambda: EventType.RUN_ADVANCING in _event_types_for(self.db_path, run_id),
            label="RUN_ADVANCING",
        )

        # --- 3. Real Human Wait ---
        waiting_run = self._poll_operational_status(
            run_id,
            OperationalStatus.WAITING_FOR_HUMAN,
            label="WAITING_FOR_HUMAN",
        )
        self.assertEqual(waiting_run.mission_id, MISSION_ID)
        self.assertEqual(waiting_run.agent_code, CONSTRUCTOR_AGENT_CODE)
        if authorization_id is not None:
            self.assertEqual(waiting_run.authorization_id, authorization_id)

        wait_events = [
            e
            for e in _events_for(self.db_path, run_id)
            if e.event_type is EventType.HUMAN_WAIT_STARTED
        ]
        self.assertEqual(len(wait_events), 1)
        wait_event = wait_events[0]
        self.assertIsNotNone(wait_event.interrupt_id)
        self.assertIsNotNone(wait_event.human_decision_request)
        self.assertTrue(wait_event.human_decision_request.reason_code)
        self.assertIn(
            DECISION_CLARIFY_SCOPE,
            wait_event.human_decision_request.allowed_decisions,
        )
        interrupt_id = wait_event.interrupt_id
        wait_ordinal = wait_event.resume_n

        # Worker finished first invoke at interrupt; join before resume.
        if self.launcher._last_thread is not None:
            self.launcher._last_thread.join(timeout=WAIT_TIMEOUT_SECONDS)
            self.assertFalse(self.launcher._last_thread.is_alive())

        reads_before_resume = self.reader.calls

        # --- 4. Controlled resume with CLARIFY_SCOPE ---
        out, req, cmd = self._resume_after_wait(run_id=run_id)
        self.assertEqual(req.interrupt_id, interrupt_id)
        self.assertEqual(cmd.decision, DECISION_CLARIFY_SCOPE)
        self.assertEqual(cmd.decision_id, "dec-10-10-clarify")
        lifecycle = out["lifecycle"]
        self.assertEqual(lifecycle.status, STATUS_READY_FOR_HANDOFF)

        # --- 5. Completion ---
        completed_run = self._poll_operational_status(
            run_id,
            OperationalStatus.COMPLETED,
            label="COMPLETED",
        )
        self.assertIsNotNone(completed_run.completed_at)
        self.assertIsNotNone(completed_run.handoff_id)

        # Ensure launcher worker after resume path is done (resume ran in this thread).
        if self.launcher._last_thread is not None:
            self.launcher._last_thread.join(timeout=WAIT_TIMEOUT_SECONDS)

        types = _event_types_for(self.db_path, run_id)
        events = _events_for(self.db_path, run_id)

        # --- 6. Critical event presence ---
        for required in (
            EventType.RUN_ADVANCING,
            EventType.HUMAN_WAIT_STARTED,
            EventType.HUMAN_DECISION_RECEIVED,
            EventType.RUN_RESUMED,
            EventType.REALITY_REFRESH_STARTED,
            EventType.REALITY_REFRESH_COMPLETED,
            EventType.HANDOFF_CREATED,
            EventType.HANDOFF_PERSISTED,
            EventType.RUN_COMPLETED,
        ):
            self.assertIn(required, types, msg=required.value)

        self.assertTrue(
            any(t in types for t in (EventType.TOOL_CALL_STARTED, EventType.TOOL_CALL_COMPLETED)),
            msg="secure tool events missing",
        )
        self.assertIn(EventType.ARTIFACT_CREATED, types)
        self.assertTrue(
            any(t in types for t in (EventType.STAGE_STARTED, EventType.STAGE_COMPLETED)),
            msg="professional stage events missing",
        )

        # --- 7. Critical order ---
        i_wait = _first_index(types, EventType.HUMAN_WAIT_STARTED)
        i_decision = _first_index(types, EventType.HUMAN_DECISION_RECEIVED)
        i_resumed = _first_index(types, EventType.RUN_RESUMED)
        i_refresh_start = _first_index(types, EventType.REALITY_REFRESH_STARTED)
        i_refresh_done = _first_index(types, EventType.REALITY_REFRESH_COMPLETED)
        i_handoff_created = _first_index(types, EventType.HANDOFF_CREATED)
        i_handoff_persisted = _first_index(types, EventType.HANDOFF_PERSISTED)
        i_completed = _first_index(types, EventType.RUN_COMPLETED)
        self.assertLess(i_wait, i_decision)
        self.assertLess(i_decision, i_resumed)
        self.assertLess(i_resumed, i_refresh_start)
        self.assertLess(i_refresh_start, i_refresh_done)
        self.assertLess(i_handoff_created, i_handoff_persisted)
        self.assertLess(i_handoff_persisted, i_completed)

        # --- 8. Decision / refresh / handoff structured truth ---
        decision_events = [
            e for e in events if e.event_type is EventType.HUMAN_DECISION_RECEIVED
        ]
        self.assertEqual(len(decision_events), 1)
        decision_event = decision_events[0]
        self.assertEqual(decision_event.interrupt_id, interrupt_id)
        self.assertEqual(decision_event.decision_id, "dec-10-10-clarify")
        self.assertIsNotNone(decision_event.human_decision_record)
        self.assertEqual(
            decision_event.human_decision_record.decision_code,
            DECISION_CLARIFY_SCOPE,
        )
        self.assertEqual(decision_event.human_decision_record.actor_id, "operator-10-10")

        self.assertGreater(
            self.reader.calls,
            reads_before_resume,
            msg="fresh secure read after CLARIFY_SCOPE not proven",
        )
        self.assertGreaterEqual(self.hitl_store.answer_calls, 1)
        self.assertGreaterEqual(self.handoff_store.put_calls, 1)
        self.assertEqual(len(self.handoff_store._records), 1)

        created = [e for e in events if e.event_type is EventType.HANDOFF_CREATED]
        self.assertEqual(len(created), 1)
        handoff_created = created[0]
        self.assertIsNotNone(handoff_created.handoff_id)
        self.assertIsNotNone(handoff_created.handoff_observability)
        self.assertEqual(handoff_created.handoff_observability.handoff_type, HANDOFF_TYPE)
        self.assertEqual(
            handoff_created.handoff_observability.target_role_code,
            TARGET_ROLE,
        )
        self.assertEqual(handoff_created.artifact_type, "package")
        self.assertIsNotNone(handoff_created.artifact_id)
        handoff_id = handoff_created.handoff_id
        self.assertIn(handoff_id, self.handoff_store._records)

        # --- 9. Close original objects; reopen via Control Room factory ---
        self.control_store.close()

        port = build_agent_control_room_query_port(override_path=self.db_path)
        self._query_port = port
        detail = port.get_run(run_id)
        self.assertEqual(completed_run.handoff_id, handoff_id)
        self.assertEqual(detail.run_id, run_id)
        self.assertEqual(detail.agent_code, CONSTRUCTOR_AGENT_CODE)
        self.assertEqual(detail.mission_id, MISSION_ID)
        self.assertEqual(detail.operational_status, OperationalStatus.COMPLETED.value)
        self.assertEqual(detail.handoff_id, handoff_id)

        snapshot = port.get_run_snapshot(run_id)
        self.assertEqual(snapshot.run.run_id, run_id)
        self.assertEqual(snapshot.run.operational_status, OperationalStatus.COMPLETED.value)
        self.assertTrue(snapshot.events_complete)

        # Professional execution path
        path = snapshot.professional_execution_path
        self.assertIsNotNone(path)
        self.assertGreaterEqual(len(path.steps), 1)
        self.assertNotEqual(path.derivation_state, DerivationState.INCONSISTENT)

        # Human Decision history (surface retains closed episode)
        surface = snapshot.human_decision_surface
        self.assertFalse(surface.wait.waiting_for_human)
        self.assertEqual(surface.wait.interrupt_id, interrupt_id)
        self.assertIsNotNone(surface.request)
        self.assertIn(DECISION_CLARIFY_SCOPE, surface.request.allowed_decisions)
        self.assertIsNotNone(surface.decision)
        self.assertEqual(surface.decision.decision_code, DECISION_CLARIFY_SCOPE)
        self.assertEqual(surface.decision.decision_id, "dec-10-10-clarify")
        self.assertFalse(surface.authority_modeled)

        # Reality refresh on read model
        consequence = surface.consequence
        self.assertIsNotNone(consequence)
        self.assertIsNotNone(consequence.reality_refresh_started_at)
        self.assertIsNotNone(consequence.reality_refresh_completed_at)

        # Handoff view
        handoff_view = snapshot.handoff
        self.assertEqual(handoff_view.handoff_id, handoff_id)
        self.assertEqual(handoff_view.status, HandoffStatus.PERSISTED)
        self.assertEqual(handoff_view.handoff_type, HANDOFF_TYPE)
        self.assertEqual(handoff_view.target_role_code, TARGET_ROLE)
        self.assertEqual(handoff_view.artifact_type, "package")
        self.assertEqual(handoff_view.artifact_id, handoff_created.artifact_id)
        self.assertEqual(handoff_view.derivation_state, DerivationState.OK)

        # Digital Organization
        org = snapshot.digital_organization
        self.assertEqual(org.source_agent_code, CONSTRUCTOR_AGENT_CODE)
        self.assertEqual(org.source_run_id, run_id)
        self.assertEqual(org.source_operational_status, OperationalStatus.COMPLETED.value)
        self.assertIsNotNone(org.source_completed_at)
        self.assertIsNotNone(org.handoff)
        self.assertEqual(org.handoff.status, HandoffStatus.PERSISTED)
        self.assertEqual(org.handoff.target_role_code, TARGET_ROLE)
        self.assertEqual(org.handoff.artifact_type, "package")
        self.assertNotIn("receiver_observed", org.__dict__)
        self.assertNotIn("target_run_id", org.__dict__)
        self.assertNotIn("ownership_transferred", org.__dict__)
        self.assertNotIn("orchestration_completed", org.__dict__)
        self.assertNotIn("receiver_accepted", org.handoff.__dict__)

        # Source completion ≠ orchestration / ownership claims
        self.assertNotIn("orchestration_completed", snapshot.run.__dict__)
        self.assertNotIn("ownership_transferred", snapshot.run.__dict__)

        # EOS-SEC / leak sanity on reopened snapshot surface
        org_dump = str(org)
        handoff_dump = str(handoff_view)
        for banned in (
            "SUPABASE",
            "service_role",
            "Bearer ",
            "candidate_ids",
            "AgentExecutionContext",
            "checkpoint_blob",
        ):
            self.assertNotIn(banned, org_dump)
            self.assertNotIn(banned, handoff_dump)

        # Identity chain preserved
        self.assertEqual(wait_ordinal, wait_event.resume_n)
        self.assertEqual(decision_event.resume_n, wait_event.resume_n)
        self.assertIsNone(getattr(org, "target_run_id", None))


class ProductionDefaultClockReplayGuard(unittest.TestCase):
    """
    10.10A release guard — production-default clock/replay invariant.

    CLOCK_OWNER: FIRST_OCCURRENCE
    REPLAY_SEMANTICS: SAME_IMMUTABLE_FACT
    Production default now=None reuses checkpointed lifecycle.updated_at
    when replaying HUMAN_WAIT_STARTED (same immutable wait fact).
    """

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self._tmpdir.name) / "observability_10_10a_guard.sqlite"
        self.control_store = SqliteObservabilityStore(self.db_path)
        self.service = RunControlService(
            registry=InMemoryRunControlRegistry(),
            recorder=StoreObservabilityRecorder(self.control_store),
            durable_store=self.control_store,
        )
        self.reader = ClarifyingReader()
        self.handoff_store = InMemoryHandoffStore()
        self.hitl_store = FakeHitlStore()
        self.checkpointer = InMemorySaver(
            serde=build_constructor_jsonplus_serializer()
        )
        self.captured_context = None
        # No FIXED_AT / no clock patch — production launcher defaults.
        self.launcher = ConstructorManagedRuntimeLauncher(
            observability_db_path=self.db_path,
            assemble_candidates=StubAssembler(),
            scope_reader=self.reader,
            labor_evidence=[_history()],
            handoff_store_factory=lambda: self.handoff_store,
            checkpointer_factory=lambda: self.checkpointer,
            hitl_store_factory=lambda: self.hitl_store,
        )

    def tearDown(self) -> None:
        if self.launcher._last_thread is not None:
            self.launcher._last_thread.join(timeout=WAIT_TIMEOUT_SECONDS)
        try:
            self.control_store.close()
        except Exception:
            pass
        self._tmpdir.cleanup()

    def _issue_context(self, **kwargs):
        self.captured_context = issue_read_only_agent_context(**kwargs)
        return self.captured_context

    def test_production_default_real_clock_resume_replays_wait_idempotently(self) -> None:
        start_input = ManagedRunStartInput(
            agent_code=CONSTRUCTOR_AGENT_CODE,
            initiator_type=InitiatorType.HUMAN,
            initiator_id="operator-10-10a-guard",
            trigger_type=TriggerType.MANUAL,
            trigger_reason="increment-10-10a-clock-replay-guard",
            project_code=PROJECT,
            month_key=MONTH,
            requested_mission_id="mission-10-10a-clock-guard",
            idempotency_key="idem-10-10a-clock-replay-guard",
            scope_request={
                "facility": ["ALL", FACILITY_TARGET],
                "discipline": DISCIPLINE_VENT,
            },
        )
        with patch(
            "agents.run_control.service.issue_read_only_agent_context",
            side_effect=self._issue_context,
        ):
            result = self.service.start(start_input, launcher=self.launcher)

        run_id = result.agent_run.run_id
        self.assertIsNotNone(self.captured_context)

        def waiting() -> bool:
            store = _open_store(self.db_path)
            try:
                run = store.get_run(run_id)
                return run.operational_status is OperationalStatus.WAITING_FOR_HUMAN
            finally:
                store.close()

        _poll_until(waiting, label="WAITING_FOR_HUMAN")
        if self.launcher._last_thread is not None:
            self.launcher._last_thread.join(timeout=WAIT_TIMEOUT_SECONDS)
            self.assertFalse(self.launcher._last_thread.is_alive())

        wait_events = [
            e
            for e in _events_for(self.db_path, run_id)
            if e.event_type is EventType.HUMAN_WAIT_STARTED
        ]
        self.assertEqual(len(wait_events), 1)
        original = wait_events[0]
        original_fp = compute_observability_event_fingerprint(original)

        replayed: dict[str, Any] = {}
        resume_store = _open_store(self.db_path)
        try:
            resume_recorder = StoreObservabilityRecorder(resume_store)
            real_record = resume_recorder.record_event

            def capturing_record(event):
                result_rec = real_record(event)
                if event.event_type is EventType.HUMAN_WAIT_STARTED:
                    replayed["event"] = event
                    replayed["outcome"] = result_rec.outcome
                    replayed["fingerprint"] = compute_observability_event_fingerprint(
                        event
                    )
                return result_rec

            resume_recorder.record_event = capturing_record  # type: ignore[method-assign]

            # Production-default rebuild: omit now= entirely.
            app = build_constructor_langgraph(
                context=self.captured_context,
                project_code=PROJECT,
                month_key=MONTH,
                facility_scope=["ALL", FACILITY_TARGET],
                discipline_scope=DISCIPLINE_VENT,
                assemble_candidates=StubAssembler(),
                labor_evidence=[_history()],
                scope_reader=self.reader,
                checkpointer=self.checkpointer,
                hitl_store=self.hitl_store,
                handoff_store=self.handoff_store,
                recorder=resume_recorder,
            )
            config = {"configurable": {"thread_id": run_id}}
            snap = app.get_state(config)
            lifecycle = snap.values["lifecycle"]
            self.assertEqual(lifecycle.status, "WAITING_FOR_HUMAN")
            req = build_decision_request_from_lifecycle(lifecycle)
            checkpoint_id = snap.config["configurable"]["checkpoint_id"]
            cmd = build_resume_command(
                decision_id="dec-10-10a-clock-guard",
                interrupt_id=req.interrupt_id,
                run_id=run_id,
                mission_id="mission-10-10a-clock-guard",
                decision=DECISION_CLARIFY_SCOPE,
                actor_id="operator-10-10a-guard",
                parameters={"facility_scope": [FACILITY_TARGET]},
                expected_checkpoint_id=checkpoint_id,
                submitted_at=datetime.now(timezone.utc),
            )
            out = app.invoke(Command(resume=cmd), config)
            self.assertEqual(out["lifecycle"].status, STATUS_READY_FOR_HANDOFF)
        finally:
            resume_store.close()

        self.assertIn("event", replayed)
        replay_event = replayed["event"]
        self.assertEqual(replay_event.event_id, original.event_id)
        self.assertEqual(replay_event.occurred_at, original.occurred_at)
        self.assertEqual(replayed["fingerprint"], original_fp)
        self.assertEqual(replayed["outcome"], RecordOutcome.IDEMPOTENT_REPLAY)

        after = [
            e
            for e in _events_for(self.db_path, run_id)
            if e.event_type is EventType.HUMAN_WAIT_STARTED
        ]
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0].event_id, original.event_id)
        self.assertEqual(after[0].occurred_at, original.occurred_at)


if __name__ == "__main__":
    unittest.main()
