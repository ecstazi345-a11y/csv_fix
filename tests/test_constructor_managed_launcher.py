"""
Constructor Managed Runtime Launcher — integration tests.

Local managed runtime backend v0.1 (background thread).
"""

from __future__ import annotations

import ast
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from agents.monthly_plan_constructor.candidate_package import LABOR_UNRESOLVED, LABOR_VALIDATED
from agents.monthly_plan_constructor.handoff_store import HandoffStorePutResult
from agents.monthly_plan_constructor.langgraph_runtime import CONSTRUCTOR_AGENT_CODE
from agents.monthly_plan_constructor.lifecycle import CandidateAssemblyResult
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_OBSERVED_PRODUCTIVITY,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    SOURCE_PROJECT_HISTORY,
    LaborNormEvidence,
)
from agents.monthly_plan_constructor.managed_launcher import (
    ConstructorManagedRuntimeLauncher,
    ManagedLauncherError,
)
from agents.monthly_plan_constructor.mission_scope import ConstructorMissionScope
from agents.observability.contracts import (
    EventType,
    InitiatorType,
    OperationalStatus,
    TriggerType,
)
from agents.observability.durable_recorder import StoreObservabilityRecorder
from agents.observability.sqlite_store import SqliteObservabilityStore
from agents.observability.store import DEFAULT_LIST_EVENTS_LIMIT, ObservabilityStorageFailureError
from agents.run_control.contracts import (
    CODE_CONTROL_PLANE_FAILURE,
    CODE_LAUNCH_OUTCOME_UNKNOWN,
    ManagedRunStartInput,
    ManagedRuntimeLauncher,
    RunControlError,
)
from agents.run_control.registry import InMemoryRunControlRegistry
from agents.run_control.service import RunControlService
from security.agent_execution_context import issue_read_only_agent_context

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"
MISSION_ID = "mission-managed-launcher"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
FIXED_AT = datetime(2026, 9, 2, 15, 0, 0, tzinfo=timezone.utc)
REPO = Path(__file__).resolve().parents[1]
WAIT_TIMEOUT_SECONDS = 30.0


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


class RecordingReader:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows if rows is not None else [_raw()]
        self.calls = 0

    def __call__(self, context, mission: ConstructorMissionScope):
        self.calls += 1
        return list(self.rows)


def _history() -> LaborNormEvidence:
    return LaborNormEvidence(
        evidence_id="ev-project",
        candidate_id=CANDIDATE_ID,
        source_type=SOURCE_PROJECT_HISTORY,
        labor_hours_per_unit=1.42,
        unit="м2",
        source_reference="project-history-run",
        source_version="2026-08",
        planning_use_status=LABOR_VALIDATED,
        basis=BASIS_OBSERVED_PRODUCTIVITY,
        hours_quality=HOURS_VALIDATED_PRODUCTIVE_DIRECT,
        executed_quantity_validated=True,
    )


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


class GatedAssembler:
    def __init__(
        self,
        inner: StubAssembler,
        entered: threading.Event,
        release: threading.Event,
    ) -> None:
        self._inner = inner
        self._entered = entered
        self._release = release

    def __call__(self, reality_read, scope: ConstructorMissionScope):
        self._entered.set()
        if not self._release.wait(timeout=WAIT_TIMEOUT_SECONDS):
            raise TimeoutError("assembler gate release timed out")
        return self._inner(reality_read, scope)


def _start_input(**overrides: Any) -> ManagedRunStartInput:
    payload = dict(
        agent_code=CONSTRUCTOR_AGENT_CODE,
        initiator_type=InitiatorType.HUMAN,
        initiator_id="operator-local",
        trigger_type=TriggerType.MANUAL,
        trigger_reason="managed-launcher-proof",
        project_code=PROJECT,
        month_key=MONTH,
        requested_mission_id=MISSION_ID,
        idempotency_key="idem-managed-launcher",
        scope_request={
            "facility": FACILITY_TARGET,
            "discipline": DISCIPLINE_VENT,
        },
    )
    payload.update(overrides)
    return ManagedRunStartInput(**payload)


def _wait_for(predicate, *, timeout: float = WAIT_TIMEOUT_SECONDS) -> None:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if predicate():
            return
        time.sleep(0.01)
    raise TimeoutError("condition not met within timeout")


class ConstructorManagedLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "observability.sqlite"
        self.store = SqliteObservabilityStore(self.db_path)
        self.recorder = StoreObservabilityRecorder(self.store)
        self.registry = InMemoryRunControlRegistry()
        self.service = RunControlService(
            registry=self.registry,
            recorder=self.recorder,
            durable_store=self.store,
        )
        self.assembler_entered = threading.Event()
        self.release_assembler = threading.Event()
        self.launcher = ConstructorManagedRuntimeLauncher(
            observability_db_path=self.db_path,
            assemble_candidates=GatedAssembler(
                StubAssembler(),
                self.assembler_entered,
                self.release_assembler,
            ),
            scope_reader=RecordingReader(),
            labor_evidence=[_history()],
            handoff_store_factory=InMemoryHandoffStore,
        )
        self.captured_authorization_id: str | None = None

    def tearDown(self) -> None:
        self.release_assembler.set()
        if self.launcher._last_thread is not None:
            self.launcher._last_thread.join(timeout=WAIT_TIMEOUT_SECONDS)
        self.store.close()
        self._tmpdir.cleanup()

    def _start(self, **overrides: Any):
        with patch(
            "agents.run_control.service.issue_read_only_agent_context",
            side_effect=self._issue_context,
        ):
            return self.service.start(
                _start_input(**overrides),
                launcher=self.launcher,
                requested_at=FIXED_AT,
            )

    def _issue_context(self, **kwargs):
        context = issue_read_only_agent_context(**kwargs)
        self.captured_authorization_id = context.authorization_id
        return context

    def _read_store(self) -> SqliteObservabilityStore:
        return SqliteObservabilityStore(self.db_path)

    def test_launcher_satisfies_protocol(self) -> None:
        self.assertIsInstance(self.launcher, ManagedRuntimeLauncher)

    def test_end_to_end_managed_launch_decoupling_and_running_truth(self) -> None:
        result = self._start(idempotency_key="idem-e2e-1")
        self.assertEqual(result.agent_run.operational_status, OperationalStatus.STARTING)

        _wait_for(self.assembler_entered.is_set)
        self.assertFalse(self.release_assembler.is_set())

        reader_store = self._read_store()
        try:
            running_run = reader_store.get_run(result.agent_run.run_id)
            self.assertEqual(running_run.operational_status, OperationalStatus.RUNNING)
            event_types = [
                event.event_type
                for event in reader_store.list_events(
                    result.agent_run.run_id,
                    limit=DEFAULT_LIST_EVENTS_LIMIT,
                )
            ]
            self.assertIn(EventType.RUN_ADVANCING, event_types)
            self.assertEqual(event_types.count(EventType.RUN_ADVANCING), 1)
        finally:
            reader_store.close()

        self.release_assembler.set()
        if self.launcher._last_thread is not None:
            self.launcher._last_thread.join(timeout=WAIT_TIMEOUT_SECONDS)

        final_store = self._read_store()
        try:
            final_run = final_store.get_run(result.agent_run.run_id)
            self.assertEqual(final_run.operational_status, OperationalStatus.COMPLETED)
            self.assertIsNotNone(final_run.completed_at)
            self.assertEqual(final_run.authorization_id, self.captured_authorization_id)
        finally:
            final_store.close()

    def test_scheduling_failure_propagates(self) -> None:
        with patch(
            "agents.monthly_plan_constructor.managed_launcher.threading.Thread.start",
            side_effect=RuntimeError("thread-start-fail"),
        ):
            with self.assertRaises(RunControlError) as ctx:
                self._start(idempotency_key="idem-sched-fail")
        self.assertEqual(ctx.exception.code, CODE_LAUNCH_OUTCOME_UNKNOWN)

    def test_worker_failure_before_run_advancing_does_not_invent_terminal_ops_status(self) -> None:
        with patch(
            "agents.monthly_plan_constructor.managed_launcher.run_constructor_langgraph",
            side_effect=RuntimeError("worker exploded before bind_mission"),
        ):
            result = self._start(idempotency_key="idem-worker-fail-early")
            if self.launcher._last_thread is not None:
                self.launcher._last_thread.join(timeout=WAIT_TIMEOUT_SECONDS)

        reader = self._read_store()
        try:
            run = reader.get_run(result.agent_run.run_id)
            self.assertEqual(run.operational_status, OperationalStatus.STARTING)
            types = [
                event.event_type
                for event in reader.list_events(result.agent_run.run_id, limit=DEFAULT_LIST_EVENTS_LIMIT)
            ]
            self.assertNotIn(EventType.RUN_FAILED, types)
            self.assertNotIn(EventType.RUN_ADVANCING, types)
        finally:
            reader.close()

    def test_launch_envelope_rejects_run_id_mismatch(self) -> None:
        context = issue_read_only_agent_context(
            agent_code=CONSTRUCTOR_AGENT_CODE,
            project_code=PROJECT,
            run_id="run-a",
        )
        with self.assertRaises(ManagedLauncherError):
            self.launcher.launch(
                run_request=type(
                    "Req",
                    (),
                    {
                        "agent_code": CONSTRUCTOR_AGENT_CODE,
                        "project_code": PROJECT,
                        "requested_mission_id": MISSION_ID,
                        "month_key": MONTH,
                        "scope_request": (),
                        "orchestration_run_id": None,
                    },
                )(),
                agent_run=type(
                    "Run",
                    (),
                    {
                        "agent_code": CONSTRUCTOR_AGENT_CODE,
                        "run_id": "run-b",
                        "project_code": PROJECT,
                        "mission_id": MISSION_ID,
                        "authorization_id": context.authorization_id,
                    },
                )(),
                context=context,
            )

    def test_no_streamlit_import(self) -> None:
        path = REPO / "agents" / "monthly_plan_constructor" / "managed_launcher.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn("streamlit", alias.name)
            if isinstance(node, ast.ImportFrom) and node.module:
                self.assertNotIn("streamlit", node.module)
                self.assertNotIn("pages", node.module)


class FailingBootstrapStore(SqliteObservabilityStore):
    def create_run(self, run):  # type: ignore[no-untyped-def]
        raise ObservabilityStorageFailureError("bootstrap failed")


class RunControlBootstrapIntegrationTests(unittest.TestCase):
    def test_bootstrap_failure_prevents_launch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "obs.sqlite"
            store = FailingBootstrapStore(db_path)
            recorder = StoreObservabilityRecorder(store)
            service = RunControlService(
                registry=InMemoryRunControlRegistry(),
                recorder=recorder,
                durable_store=store,
            )

            class _Launcher:
                calls = 0

                def launch(self, **kwargs) -> None:
                    _Launcher.calls += 1

            try:
                with patch(
                    "agents.run_control.service.issue_read_only_agent_context",
                    side_effect=issue_read_only_agent_context,
                ):
                    with self.assertRaises(RunControlError) as ctx:
                        service.start(
                            _start_input(idempotency_key="idem-bootstrap-fail"),
                            launcher=_Launcher(),
                            requested_at=FIXED_AT,
                        )
                self.assertEqual(ctx.exception.code, CODE_CONTROL_PLANE_FAILURE)
                self.assertEqual(_Launcher.calls, 0)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
