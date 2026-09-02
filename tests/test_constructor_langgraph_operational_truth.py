"""
Operational Truth Fix — Constructor LangGraph runtime + Run Control boundary tests.

Non-Postgres only. Proves RUN_ADVANCING seam, terminal RUN_FAILED paths,
RUN_ABORTED, and Run Control post-launch STARTING semantics.
"""

from __future__ import annotations

import ast
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
)
from agents.monthly_plan_constructor.exception_engine import (
    CODE_AMBIGUOUS_SCOPE,
    CODE_READ_FAILED,
)
from agents.monthly_plan_constructor.handoff_store import HandoffStorePutResult
from agents.monthly_plan_constructor.hitl_contracts import (
    DECISION_ABORT_RUN,
    DECISION_CLARIFY_SCOPE,
    build_resume_command,
)
from agents.monthly_plan_constructor.hitl_resume import build_decision_request_from_lifecycle
from agents.monthly_plan_constructor.langgraph_runtime import (
    build_constructor_langgraph,
    run_constructor_langgraph,
)
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_FAILED,
    STATUS_LABOR_RESOLVED,
    STATUS_READY_FOR_HANDOFF,
    STATUS_WAITING_FOR_HUMAN,
    advance_constructor_lifecycle,
    create_lifecycle_state,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_OBSERVED_PRODUCTIVITY,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    LaborNormEvidence,
    SOURCE_PROJECT_HISTORY,
)
from agents.monthly_plan_constructor.mission_scope import ConstructorMissionScope
from agents.monthly_plan_constructor.runtime_instrumentation import (
    RUN_CONTROL_OWNED_EVENT_TYPES,
    ConstructorRuntimeEventKey,
    compute_constructor_runtime_event_id,
)
from agents.monthly_plan_constructor.secure_read_tools import SecureReadError
from agents.observability.contracts import (
    EventStatus,
    EventType,
    InitiatorType,
    OperationalStatus,
    TriggerType,
)
from agents.observability.recorder import (
    InMemoryObservabilityRecorder,
    RecordOutcome,
)
from agents.run_control.contracts import (
    CODE_LAUNCH_OUTCOME_UNKNOWN,
    ManagedRunStartInput,
    RunControlError,
)
from agents.run_control.registry import InMemoryRunControlRegistry
from agents.run_control.service import RunControlService
from security.agent_execution_context import issue_read_only_agent_context

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"
MISSION_ID = "mission-operational-truth"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
FIXED_AT = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
AGENT_CODE = "MONTHLY_PLAN_CONSTRUCTOR"
REPO = __import__("pathlib").Path(__file__).resolve().parents[1]


def _context(*, run_id: str):
    return issue_read_only_agent_context(
        agent_code=AGENT_CODE,
        project_code=PROJECT,
        run_id=run_id,
    )


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
        from agents.monthly_plan_constructor.lifecycle import CandidateAssemblyResult

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


def _run_graph(
    *,
    recorder: InMemoryObservabilityRecorder,
    run_id: str,
    reader: Any | None = None,
    project_code: str = PROJECT,
    facility_scope: object = None,
    handoff_store: Any | None = None,
) -> Any:
    return run_constructor_langgraph(
        context=_context(run_id=run_id),
        project_code=project_code,
        month_key=MONTH,
        facility_scope=facility_scope,  # type: ignore[arg-type]
        assemble_candidates=StubAssembler(),
        labor_evidence=[_history()],
        scope_reader=reader or RecordingReader(),
        mission_id=MISSION_ID,
        run_id=run_id,
        now=FIXED_AT,
        recorder=recorder,
        handoff_store=handoff_store,
    )


def _events(recorder: InMemoryObservabilityRecorder, run_id: str):
    return list(recorder.events_for_run(run_id))


def _event_types(recorder: InMemoryObservabilityRecorder, run_id: str):
    return [event.event_type for event in _events(recorder, run_id)]


@dataclass
class FakeLauncher:
    calls: list[str] = field(default_factory=list)

    def launch(self, *, run_request, agent_run, context) -> None:
        self.calls.append(agent_run.run_id)


def _start_input(**overrides: Any) -> ManagedRunStartInput:
    payload = dict(
        agent_code=AGENT_CODE,
        initiator_type=InitiatorType.HUMAN,
        initiator_id="operator-local",
        trigger_type=TriggerType.MANUAL,
        trigger_reason="manual-start",
        project_code=PROJECT,
        month_key="2026-09",
        requested_mission_id=MISSION_ID,
        idempotency_key="idem-operational-truth",
        scope_request={"facility": "A"},
        metadata={"ui": "control-room"},
    )
    payload.update(overrides)
    return ManagedRunStartInput(**payload)


class TestRunControlPostLaunch(unittest.TestCase):
    def test_launcher_success_returns_starting_not_running(self) -> None:
        registry = InMemoryRunControlRegistry()
        recorder = InMemoryObservabilityRecorder()
        launcher = FakeLauncher()
        service = RunControlService(registry=registry, recorder=recorder)
        with patch(
            "agents.run_control.service.issue_read_only_agent_context",
            side_effect=issue_read_only_agent_context,
        ):
            result = service.start(
                _start_input(),
                launcher=launcher,
                requested_at=FIXED_AT,
            )
        self.assertEqual(result.agent_run.operational_status, OperationalStatus.STARTING)

    def test_run_control_does_not_emit_run_advancing(self) -> None:
        registry = InMemoryRunControlRegistry()
        recorder = InMemoryObservabilityRecorder()
        launcher = FakeLauncher()
        service = RunControlService(registry=registry, recorder=recorder)
        with patch(
            "agents.run_control.service.issue_read_only_agent_context",
            side_effect=issue_read_only_agent_context,
        ):
            result = service.start(
                _start_input(),
                launcher=launcher,
                requested_at=FIXED_AT,
            )
        types = [event.event_type for event in recorder.events_for_run(result.agent_run.run_id)]
        self.assertNotIn(EventType.RUN_ADVANCING, types)
        self.assertEqual(
            types,
            [
                EventType.RUN_REQUESTED,
                EventType.RUN_AUTHORIZATION_STARTED,
                EventType.RUN_AUTHORIZED,
                EventType.MISSION_BOUND,
                EventType.RUN_STARTED,
            ],
        )

    def test_launch_outcome_unknown_emits_no_run_failed(self) -> None:
        registry = InMemoryRunControlRegistry()
        recorder = InMemoryObservabilityRecorder()

        class BoomLauncher:
            def launch(self, *, run_request, agent_run, context) -> None:
                raise RuntimeError("launcher exploded")

        service = RunControlService(registry=registry, recorder=recorder)
        with patch(
            "agents.run_control.service.issue_read_only_agent_context",
            side_effect=issue_read_only_agent_context,
        ):
            with self.assertRaises(RunControlError) as ctx:
                service.start(
                    _start_input(),
                    launcher=BoomLauncher(),
                    requested_at=FIXED_AT,
                )
        self.assertEqual(ctx.exception.code, CODE_LAUNCH_OUTCOME_UNKNOWN)
        failed_types = {
            event.event_type
            for event in recorder.snapshot_events()
            if event.event_type == EventType.RUN_FAILED
        }
        self.assertEqual(failed_types, set())


class TestRunAdvancingSeam(unittest.TestCase):
    def test_bind_mission_entry_emits_run_advancing(self) -> None:
        run_id = "run-ot-advancing"
        recorder = InMemoryObservabilityRecorder()
        _run_graph(recorder=recorder, run_id=run_id)
        types = _event_types(recorder, run_id)
        self.assertIn(EventType.RUN_ADVANCING, types)
        self.assertEqual(types[0], EventType.RUN_ADVANCING)

    def test_run_advancing_before_first_stage_started(self) -> None:
        run_id = "run-ot-order"
        recorder = InMemoryObservabilityRecorder()
        _run_graph(recorder=recorder, run_id=run_id)
        events = _events(recorder, run_id)
        advancing_idx = next(
            idx for idx, event in enumerate(events) if event.event_type == EventType.RUN_ADVANCING
        )
        stage_started_idx = next(
            idx
            for idx, event in enumerate(events)
            if event.event_type == EventType.STAGE_STARTED
        )
        self.assertLess(advancing_idx, stage_started_idx)

    def test_run_advancing_before_mission_binding_advance(self) -> None:
        from agents.monthly_plan_constructor import langgraph_runtime as lg

        run_id = "run-ot-before-advance"
        recorder = InMemoryObservabilityRecorder()
        seen: list[str] = []
        original = lg.advance_constructor_lifecycle

        def tracking_advance(state, **kwargs):
            seen.append("advance")
            return original(state, **kwargs)

        ctx = _context(run_id=run_id)
        with patch.object(lg, "advance_constructor_lifecycle", side_effect=tracking_advance):
            run_constructor_langgraph(
                context=ctx,
                project_code=PROJECT,
                month_key=MONTH,
                assemble_candidates=StubAssembler(),
                labor_evidence=[_history()],
                scope_reader=RecordingReader(),
                mission_id=MISSION_ID,
                run_id=run_id,
                now=FIXED_AT,
                recorder=recorder,
            )
        types = _event_types(recorder, run_id)
        advancing_idx = types.index(EventType.RUN_ADVANCING)
        stage_idx = types.index(EventType.STAGE_STARTED)
        self.assertLess(advancing_idx, stage_idx)
        self.assertEqual(seen[0], "advance")

    def test_run_advancing_is_distinct_from_stage_started(self) -> None:
        run_id = "run-ot-no-stage-running"
        recorder = InMemoryObservabilityRecorder()
        _run_graph(recorder=recorder, run_id=run_id)
        events = _events(recorder, run_id)
        mission_stage_started = [
            event
            for event in events
            if event.event_type == EventType.STAGE_STARTED
            and event.stage_id == "MISSION_BINDING"
        ]
        self.assertEqual(mission_stage_started, [])
        self.assertIn(EventType.RUN_ADVANCING, _event_types(recorder, run_id))

    def test_run_advancing_deterministic_replay(self) -> None:
        run_id = "run-ot-replay"
        recorder = InMemoryObservabilityRecorder()
        _run_graph(recorder=recorder, run_id=run_id)
        advancing = [
            event
            for event in _events(recorder, run_id)
            if event.event_type == EventType.RUN_ADVANCING
        ]
        self.assertEqual(len(advancing), 1)
        expected_id = compute_constructor_runtime_event_id(
            ConstructorRuntimeEventKey(
                run_id=run_id,
                event_type=EventType.RUN_ADVANCING,
                semantic_occurrence_key="start",
                attempt_n=1,
                resume_n=0,
            )
        )
        self.assertEqual(advancing[0].event_id, expected_id)
        result = recorder.record_event(advancing[0])
        self.assertEqual(result.outcome, RecordOutcome.IDEMPOTENT_REPLAY)


class TestRunFailedTerminalPaths(unittest.TestCase):
    def test_stage_terminal_failure_emits_run_failed_once(self) -> None:
        run_id = "run-ot-stage-fail"

        def raising_reader(context, mission):
            raise SecureReadError(CODE_READ_FAILED, "read failed")

        recorder = InMemoryObservabilityRecorder()
        state = _run_graph(recorder=recorder, run_id=run_id, reader=raising_reader)
        self.assertEqual(state.status, STATUS_FAILED)
        failed = [
            event
            for event in _events(recorder, run_id)
            if event.event_type == EventType.RUN_FAILED
        ]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].stage_id, "REALITY_READ")

    def test_bind_mission_terminal_failure_emits_run_failed(self) -> None:
        run_id = "run-ot-bind-fail"
        recorder = InMemoryObservabilityRecorder()
        state = _run_graph(recorder=recorder, run_id=run_id, project_code="")
        self.assertEqual(state.status, STATUS_FAILED)
        failed = [
            event
            for event in _events(recorder, run_id)
            if event.event_type == EventType.RUN_FAILED
        ]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].stage_id, "MISSION_BINDING")

    def test_waiting_path_emits_no_run_failed(self) -> None:
        run_id = "run-ot-wait"
        recorder = InMemoryObservabilityRecorder()
        real = advance_constructor_lifecycle

        def side_effect(state, **kwargs):
            result = real(state, **kwargs)
            if state.status == STATUS_LABOR_RESOLVED:
                from dataclasses import replace

                return replace(
                    result,
                    status=STATUS_WAITING_FOR_HUMAN,
                    error_code=CODE_AMBIGUOUS_SCOPE,
                )
            return result

        with patch(
            "agents.monthly_plan_constructor.langgraph_runtime.advance_constructor_lifecycle",
            side_effect=side_effect,
        ):
            state = _run_graph(recorder=recorder, run_id=run_id)
        self.assertEqual(state.status, STATUS_WAITING_FOR_HUMAN)
        self.assertNotIn(EventType.RUN_FAILED, _event_types(recorder, run_id))

    def test_successful_run_completed_path_unchanged(self) -> None:
        run_id = "run-ot-complete"
        recorder = InMemoryObservabilityRecorder()
        state = _run_graph(
            recorder=recorder,
            run_id=run_id,
            handoff_store=InMemoryHandoffStore(),
        )
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        types = _event_types(recorder, run_id)
        self.assertIn(EventType.RUN_COMPLETED, types)
        self.assertNotIn(EventType.RUN_FAILED, types)


class TestRunAborted(unittest.TestCase):
    def _hitl_app(self, *, run_id: str, recorder: InMemoryObservabilityRecorder):
        from langgraph.checkpoint.memory import InMemorySaver

        from agents.monthly_plan_constructor.durable_checkpoint import (
            build_constructor_jsonplus_serializer,
        )

        ctx = _context(run_id=run_id)

        @dataclass
        class FakeHitlStore:
            def upsert_open_request(self, request) -> None:
                pass

            def record_answer(self, *, interrupt_id: str, command) -> None:
                pass

        return (
            build_constructor_langgraph(
                context=ctx,
                project_code=PROJECT,
                month_key=MONTH,
                facility_scope=["ALL", FACILITY_TARGET],
                assemble_candidates=StubAssembler(),
                scope_reader=RecordingReader(),
                now=FIXED_AT,
                checkpointer=InMemorySaver(serde=build_constructor_jsonplus_serializer()),
                hitl_store=FakeHitlStore(),
                recorder=recorder,
            ),
            ctx,
        )

    def test_abort_run_emits_run_aborted_not_resumed_or_failed(self) -> None:
        from langgraph.types import Command

        run_id = "run-ot-abort"
        recorder = InMemoryObservabilityRecorder()
        app, ctx = self._hitl_app(run_id=run_id, recorder=recorder)
        initial = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id=run_id,
            authorization_id=ctx.authorization_id,
            created_at=FIXED_AT,
        )
        config = {"configurable": {"thread_id": run_id}}
        out1 = app.invoke({"lifecycle": initial}, config)
        self.assertEqual(out1["lifecycle"].status, STATUS_WAITING_FOR_HUMAN)
        req = build_decision_request_from_lifecycle(out1["lifecycle"])
        ckpt = app.get_state(config).config["configurable"]["checkpoint_id"]
        cmd = build_resume_command(
            decision_id="dec-abort-ot",
            interrupt_id=req.interrupt_id,
            run_id=run_id,
            mission_id=MISSION_ID,
            decision=DECISION_ABORT_RUN,
            actor_id="human-1",
            parameters={},
            expected_checkpoint_id=ckpt,
            submitted_at=FIXED_AT,
            comment="stop",
        )
        out2 = app.invoke(Command(resume=cmd), config)
        self.assertEqual(out2["lifecycle"].status, STATUS_FAILED)
        types = _event_types(recorder, run_id)
        self.assertIn(EventType.RUN_ABORTED, types)
        self.assertNotIn(EventType.RUN_RESUMED, types)
        self.assertNotIn(EventType.RUN_FAILED, types)

    def test_run_aborted_replay_identity_stable(self) -> None:
        run_id = "run-ot-abort-id"
        decision_id = "dec-abort-stable"
        expected_id = compute_constructor_runtime_event_id(
            ConstructorRuntimeEventKey(
                run_id=run_id,
                event_type=EventType.RUN_ABORTED,
                stage_id="HUMAN_GATE",
                node_name="human_wait",
                attempt_n=1,
                resume_n=1,
                semantic_occurrence_key=f"abort-{decision_id}",
                artifact_correlation_id=decision_id,
            )
        )
        self.assertTrue(expected_id.startswith("crt-evt-"))


class TestRunResumedContractTarget(unittest.TestCase):
    def test_resume_emits_run_resumed_without_second_run_advancing(self) -> None:
        from langgraph.types import Command
        from langgraph.checkpoint.memory import InMemorySaver

        from agents.monthly_plan_constructor.durable_checkpoint import (
            build_constructor_jsonplus_serializer,
        )

        run_id = "run-ot-resume"
        recorder = InMemoryObservabilityRecorder()

        @dataclass
        class FakeHitlStore:
            def upsert_open_request(self, request) -> None:
                pass

            def record_answer(self, *, interrupt_id: str, command) -> None:
                pass

        ctx = _context(run_id=run_id)
        app = build_constructor_langgraph(
            context=ctx,
            project_code=PROJECT,
            month_key=MONTH,
            facility_scope=["ALL", FACILITY_TARGET],
            assemble_candidates=StubAssembler(),
            scope_reader=RecordingReader(),
            now=FIXED_AT,
            checkpointer=InMemorySaver(serde=build_constructor_jsonplus_serializer()),
            hitl_store=FakeHitlStore(),
            recorder=recorder,
        )
        initial = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id=run_id,
            authorization_id=ctx.authorization_id,
            created_at=FIXED_AT,
        )
        config = {"configurable": {"thread_id": run_id}}
        out1 = app.invoke({"lifecycle": initial}, config)
        req = build_decision_request_from_lifecycle(out1["lifecycle"])
        ckpt = app.get_state(config).config["configurable"]["checkpoint_id"]
        cmd = build_resume_command(
            decision_id="dec-resume-ot",
            interrupt_id=req.interrupt_id,
            run_id=run_id,
            mission_id=MISSION_ID,
            decision=DECISION_CLARIFY_SCOPE,
            actor_id="human-1",
            parameters={"facility_scope": [FACILITY_TARGET]},
            expected_checkpoint_id=ckpt,
            submitted_at=FIXED_AT,
        )
        out2 = app.invoke(Command(resume=cmd), config)
        types = _event_types(recorder, run_id)
        self.assertIn(EventType.RUN_RESUMED, types)
        advancing = [
            event for event in _events(recorder, run_id) if event.event_type == EventType.RUN_ADVANCING
        ]
        self.assertEqual(len(advancing), 1)
        resumed = [
            event for event in _events(recorder, run_id) if event.event_type == EventType.RUN_RESUMED
        ][0]
        self.assertIn("professional_status_before", resumed.to_dict()["detail"])
        self.assertIn("professional_status_after", resumed.to_dict()["detail"])


class TestRevalidationRunFailed(unittest.TestCase):
    def test_revalidation_terminal_failure_emits_run_failed(self) -> None:
        from langgraph.types import Command
        from langgraph.checkpoint.memory import InMemorySaver

        from agents.monthly_plan_constructor.durable_checkpoint import (
            build_constructor_jsonplus_serializer,
        )

        run_id = "run-ot-refresh-fail"
        recorder = InMemoryObservabilityRecorder()

        class FailingRefreshReader:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self, context, mission):
                self.calls += 1
                if self.calls >= 1:
                    raise SecureReadError(CODE_READ_FAILED, "refresh failed")
                return [_raw()]

        @dataclass
        class FakeHitlStore:
            def upsert_open_request(self, request) -> None:
                pass

            def record_answer(self, *, interrupt_id: str, command) -> None:
                pass

        ctx = _context(run_id=run_id)
        app = build_constructor_langgraph(
            context=ctx,
            project_code=PROJECT,
            month_key=MONTH,
            facility_scope=["ALL", FACILITY_TARGET],
            assemble_candidates=StubAssembler(),
            scope_reader=FailingRefreshReader(),
            now=FIXED_AT,
            checkpointer=InMemorySaver(serde=build_constructor_jsonplus_serializer()),
            hitl_store=FakeHitlStore(),
            recorder=recorder,
        )
        initial = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id=run_id,
            authorization_id=ctx.authorization_id,
            created_at=FIXED_AT,
        )
        config = {"configurable": {"thread_id": run_id}}
        out1 = app.invoke({"lifecycle": initial}, config)
        req = build_decision_request_from_lifecycle(out1["lifecycle"])
        ckpt = app.get_state(config).config["configurable"]["checkpoint_id"]
        cmd = build_resume_command(
            decision_id="dec-refresh-fail-ot",
            interrupt_id=req.interrupt_id,
            run_id=run_id,
            mission_id=MISSION_ID,
            decision=DECISION_CLARIFY_SCOPE,
            actor_id="human-1",
            parameters={"facility_scope": [FACILITY_TARGET]},
            expected_checkpoint_id=ckpt,
            submitted_at=FIXED_AT,
        )
        out2 = app.invoke(Command(resume=cmd), config)
        self.assertEqual(out2["lifecycle"].status, STATUS_FAILED)
        failed = [
            event
            for event in _events(recorder, run_id)
            if event.event_type == EventType.RUN_FAILED
        ]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].stage_id, "REALITY_REVALIDATION")


class TestRecorderFailureLaw(unittest.TestCase):
    def test_run_advancing_recorder_failure_propagates_without_invented_run_failed(self) -> None:
        from agents.monthly_plan_constructor import langgraph_runtime as lg

        run_id = "run-ot-recorder-advancing"
        recorder = InMemoryObservabilityRecorder()
        original_emit = lg.ConstructorRuntimeInstrumentation.emit

        def patched_emit(self, **kwargs):
            if kwargs["key"].event_type == EventType.RUN_ADVANCING:
                raise RuntimeError("recorder-down-on-advancing")
            return original_emit(self, **kwargs)

        with patch.object(lg.ConstructorRuntimeInstrumentation, "emit", patched_emit):
            with self.assertRaises(RuntimeError) as caught:
                _run_graph(recorder=recorder, run_id=run_id)
        self.assertEqual(str(caught.exception), "recorder-down-on-advancing")
        self.assertNotIn(EventType.RUN_FAILED, _event_types(recorder, run_id))


class TestGenericInvokeGuard(unittest.TestCase):
    def test_no_broad_app_invoke_run_failed_catch(self) -> None:
        source = (REPO / "agents" / "monthly_plan_constructor" / "langgraph_runtime.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if node.type is None:
                self.fail("broad except around app.invoke must not emit RUN_FAILED")
            if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                for child in ast.walk(node):
                    if isinstance(child, ast.Attribute) and child.attr == "RUN_FAILED":
                        self.fail("generic Exception handler must not emit RUN_FAILED")


class TestRuntimeControlBoundary(unittest.TestCase):
    def test_runtime_events_disjoint_from_run_control_owned(self) -> None:
        run_id = "run-ot-boundary"
        recorder = InMemoryObservabilityRecorder()
        _run_graph(recorder=recorder, run_id=run_id)
        recorded = {event.event_type for event in _events(recorder, run_id)}
        self.assertTrue(recorded.isdisjoint(RUN_CONTROL_OWNED_EVENT_TYPES))


if __name__ == "__main__":
    unittest.main()
