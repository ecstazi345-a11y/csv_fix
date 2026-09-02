"""
Increment 10.3B — Constructor LangGraph core stage instrumentation tests.

Non-Postgres only. No Run Control duplication. No HITL/handoff stage events.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Sequence
from unittest.mock import patch

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_PROVISIONAL,
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
)
from agents.monthly_plan_constructor.exception_engine import (
    CODE_AMBIGUOUS_SCOPE,
    CODE_READ_FAILED,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_NORMATIVE_BENCHMARK,
    BASIS_OBSERVED_PRODUCTIVITY,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    LaborNormEvidence,
    SOURCE_OFFICIAL_NORMATIVE,
    SOURCE_PROJECT_HISTORY,
)
from agents.monthly_plan_constructor.langgraph_runtime import (
    build_constructor_langgraph,
    run_constructor_langgraph,
)
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_FAILED,
    STATUS_LABOR_RESOLVED,
    STATUS_MISSION_BOUND,
    STATUS_READY_FOR_HANDOFF,
    STATUS_REALITY_LOADED,
    STATUS_WAITING_FOR_HUMAN,
    CandidateAssemblyResult,
    ConstructorLifecycleState,
    LifecycleError,
    LifecycleTransition,
    advance_constructor_lifecycle,
    create_lifecycle_state,
)
from agents.monthly_plan_constructor.mission_scope import ConstructorMissionScope
from agents.monthly_plan_constructor.runtime_instrumentation import (
    RUN_CONTROL_OWNED_EVENT_TYPES,
    ConstructorRuntimeEventKey,
    compute_constructor_runtime_event_id,
)
from agents.monthly_plan_constructor.secure_read_tools import (
    ConstructorRealityRead,
    SecureReadError,
)
from agents.observability.contracts import EventType
from agents.observability.recorder import (
    InMemoryObservabilityRecorder,
    RecordOutcome,
    RecordResult,
)
from security.agent_execution_context import (
    AgentExecutionContext,
    issue_read_only_agent_context,
)

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"
MISSION_ID = "mission-inc-10-3b"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
FIXED_AT = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)
FIXED_RUN_ID = "run-inc-10-3b"
AGENT_CODE = "MONTHLY_PLAN_CONSTRUCTOR"

CORE_STAGES = (
    "REALITY_READ",
    "CANDIDATE_ASSEMBLY",
    "LABOR_NORM_RESOLUTION",
    "EXCEPTION_ANALYSIS",
)


def _context(project_code: str = PROJECT) -> AgentExecutionContext:
    return issue_read_only_agent_context(
        agent_code=AGENT_CODE,
        project_code=project_code,
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


class RecordingReader:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows if rows is not None else [_raw()]
        self.calls = 0

    def __call__(
        self,
        context: AgentExecutionContext,
        mission: ConstructorMissionScope,
    ) -> list[dict[str, object]]:
        self.calls += 1
        return list(self.rows)


def _candidate_dict(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
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
    }
    base.update(overrides)
    return base


class StubAssembler:
    def __init__(
        self,
        candidates: list[dict[str, object]] | None = None,
        *,
        scanned_count: int | None = None,
    ) -> None:
        self.candidates = candidates if candidates is not None else [_candidate_dict()]
        self.scanned_count = (
            scanned_count if scanned_count is not None else max(1, len(self.candidates))
        )

    def __call__(
        self,
        reality_read: ConstructorRealityRead,
        scope: ConstructorMissionScope,
    ) -> CandidateAssemblyResult:
        return CandidateAssemblyResult(
            candidates=tuple(self.candidates),
            scanned_count=self.scanned_count,
        )


def _history(**overrides: object) -> LaborNormEvidence:
    payload: dict[str, object] = {
        "evidence_id": "ev-project",
        "candidate_id": CANDIDATE_ID,
        "source_type": SOURCE_PROJECT_HISTORY,
        "labor_hours_per_unit": 1.42,
        "unit": "м2",
        "source_reference": "project-history-run",
        "source_version": "2026-08",
        "planning_use_status": LABOR_VALIDATED,
        "basis": BASIS_OBSERVED_PRODUCTIVITY,
        "hours_quality": HOURS_VALIDATED_PRODUCTIVE_DIRECT,
        "executed_quantity_validated": True,
    }
    payload.update(overrides)
    return LaborNormEvidence(**payload)  # type: ignore[arg-type]


def _normative(**overrides: object) -> LaborNormEvidence:
    payload: dict[str, object] = {
        "evidence_id": "ev-official",
        "candidate_id": CANDIDATE_ID,
        "source_type": SOURCE_OFFICIAL_NORMATIVE,
        "labor_hours_per_unit": 2.0,
        "unit": "м2",
        "source_reference": "gesn-table",
        "planning_use_status": LABOR_PROVISIONAL,
        "basis": BASIS_NORMATIVE_BENCHMARK,
    }
    payload.update(overrides)
    return LaborNormEvidence(**payload)  # type: ignore[arg-type]


def _run_graph(
    *,
    recorder: InMemoryObservabilityRecorder | None = None,
    assembler: StubAssembler | None = None,
    reader: RecordingReader | None = None,
    evidence: Sequence[LaborNormEvidence] = (),
    facility_scope: object = None,
    run_id: str = FIXED_RUN_ID,
) -> ConstructorLifecycleState:
    return run_constructor_langgraph(
        context=_context(),
        project_code=PROJECT,
        month_key=MONTH,
        facility_scope=facility_scope,  # type: ignore[arg-type]
        assemble_candidates=assembler or StubAssembler(),
        labor_evidence=evidence,
        scope_reader=reader or RecordingReader(),
        mission_id=MISSION_ID,
        run_id=run_id,
        now=FIXED_AT,
        recorder=recorder,
    )


def _semantic_parity(
    left: ConstructorLifecycleState,
    right: ConstructorLifecycleState,
) -> None:
    assert left.status == right.status
    assert left.error_code == right.error_code
    assert left.mission_id == right.mission_id
    assert left.run_id == right.run_id
    assert [t.to_status for t in left.transitions] == [
        t.to_status for t in right.transitions
    ]


STAGE_EVENT_TYPES = frozenset(
    {
        EventType.STAGE_STARTED,
        EventType.STAGE_COMPLETED,
        EventType.STAGE_FAILED,
    }
)


def _stage_events(recorder: InMemoryObservabilityRecorder, run_id: str):
    return [
        event
        for event in recorder.events_for_run(run_id)
        if event.stage_id in CORE_STAGES and event.event_type in STAGE_EVENT_TYPES
    ]


@dataclass
class FailingRecorder:
    fail_on: int = 1
    calls: int = 0
    events: list[Any] = field(default_factory=list)

    def record_event(self, event: Any) -> RecordResult:
        self.calls += 1
        if self.calls >= self.fail_on:
            raise RuntimeError("recorder-down")
        backend = InMemoryObservabilityRecorder()
        for prior in self.events:
            backend.record_event(prior)
        result = backend.record_event(event)
        self.events.append(event)
        return result


class TestRecorderNoneParity(unittest.TestCase):
    def test_recorder_none_preserves_lifecycle(self) -> None:
        baseline = _run_graph(recorder=None, evidence=[_history()])
        with_recorder = _run_graph(
            recorder=InMemoryObservabilityRecorder(),
            evidence=[_history()],
        )
        _semantic_parity(baseline, with_recorder)


class TestHappyPathStageEvents(unittest.TestCase):
    def setUp(self) -> None:
        self.recorder = InMemoryObservabilityRecorder()
        self.state = _run_graph(recorder=self.recorder, evidence=[_history()])

    def test_ready_for_handoff(self) -> None:
        self.assertEqual(self.state.status, STATUS_READY_FOR_HANDOFF)

    def test_four_stages_emit_started_completed_pairs(self) -> None:
        events = _stage_events(self.recorder, FIXED_RUN_ID)
        by_stage: dict[str, list[str]] = {stage: [] for stage in CORE_STAGES}
        for event in events:
            by_stage[event.stage_id].append(event.event_type.value)
        for stage in CORE_STAGES:
            self.assertEqual(
                by_stage[stage],
                [EventType.STAGE_STARTED.value, EventType.STAGE_COMPLETED.value],
                stage,
            )

    def test_event_order_matches_node_order(self) -> None:
        events = _stage_events(self.recorder, FIXED_RUN_ID)
        stage_order = [event.stage_id for event in events]
        expected = []
        for stage in CORE_STAGES:
            expected.extend([stage, stage])
        self.assertEqual(stage_order, expected)

    def test_node_names_match_langgraph_nodes(self) -> None:
        events = _stage_events(self.recorder, FIXED_RUN_ID)
        node_names = {event.node_name for event in events}
        self.assertEqual(
            node_names,
            {
                "load_reality",
                "build_package",
                "resolve_labor",
                "evaluate_exceptions",
            },
        )


class TestControlPlaneBoundary(unittest.TestCase):
    def test_run_control_events_absent(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        _run_graph(recorder=recorder, evidence=[_history()])
        recorded_types = {event.event_type for event in recorder.events_for_run(FIXED_RUN_ID)}
        self.assertTrue(recorded_types.isdisjoint(RUN_CONTROL_OWNED_EVENT_TYPES))

    def test_no_authorization_mission_binding_stages(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        _run_graph(recorder=recorder, evidence=[_history()])
        stage_ids = {
            event.stage_id
            for event in recorder.events_for_run(FIXED_RUN_ID)
            if event.stage_id is not None
        }
        self.assertNotIn("AUTHORIZATION", stage_ids)
        self.assertNotIn("MISSION_BINDING", stage_ids)


class TestFailureSemantics(unittest.TestCase):
    def test_secure_read_failed_emits_stage_failed(self) -> None:
        def raising_reader(context, mission):
            raise SecureReadError(CODE_READ_FAILED, "read failed")

        recorder = InMemoryObservabilityRecorder()
        state = _run_graph(
            recorder=recorder,
            reader=raising_reader,  # type: ignore[arg-type]
        )
        self.assertEqual(state.status, STATUS_FAILED)
        reality_events = _stage_events(recorder, FIXED_RUN_ID)
        reality_events = [
            event for event in reality_events if event.stage_id == "REALITY_READ"
        ]
        self.assertEqual(
            [event.event_type for event in reality_events],
            [EventType.STAGE_STARTED, EventType.STAGE_FAILED],
        )
        completed = [
            event
            for event in reality_events
            if event.event_type == EventType.STAGE_COMPLETED
        ]
        self.assertEqual(completed, [])


class TestWaitingForHumanSemantics(unittest.TestCase):
    def test_evaluate_exceptions_wait_emits_stage_completed_not_failed(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        real = advance_constructor_lifecycle

        def side_effect(state: ConstructorLifecycleState, **kwargs: Any) -> ConstructorLifecycleState:
            result = real(state, **kwargs)
            if state.status == STATUS_LABOR_RESOLVED:
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
            state = _run_graph(recorder=recorder, evidence=[_history()])
        self.assertEqual(state.status, STATUS_WAITING_FOR_HUMAN)
        exc_events = [
            event
            for event in _stage_events(recorder, FIXED_RUN_ID)
            if event.stage_id == "EXCEPTION_ANALYSIS"
        ]
        self.assertEqual(
            [event.event_type for event in exc_events],
            [EventType.STAGE_STARTED, EventType.STAGE_COMPLETED],
        )
        terminal = exc_events[-1].to_dict()["detail"]
        self.assertEqual(
            terminal.get("professional_status_after"),
            STATUS_WAITING_FOR_HUMAN,
        )


class TestPayloadSecurity(unittest.TestCase):
    def test_no_raw_rows_or_secrets_in_detail(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        _run_graph(recorder=recorder, evidence=[_history()])
        for event in recorder.events_for_run(FIXED_RUN_ID):
            detail = event.to_dict()["detail"]
            for value in detail.values():
                self.assertIsInstance(value, str)
            detail_text = str(detail).lower()
            for forbidden in ("supabase", "password", "secret", "dataframe"):
                self.assertNotIn(forbidden, detail_text)


class TestRecorderFailurePolicy(unittest.TestCase):
    def test_recorder_failure_on_started_propagates_without_advance(self) -> None:
        failing = FailingRecorder(fail_on=1)
        ctx = _context()
        with self.assertRaises(RuntimeError) as ctx_exc:
            run_constructor_langgraph(
                context=ctx,
                project_code=PROJECT,
                month_key=MONTH,
                assemble_candidates=StubAssembler(),
                scope_reader=RecordingReader(),
                mission_id=MISSION_ID,
                run_id="run-recorder-fail-start",
                now=FIXED_AT,
                recorder=failing,  # type: ignore[arg-type]
            )
        self.assertIn("recorder-down", str(ctx_exc.exception))
        self.assertEqual(failing.calls, 1)


class TestReentryOccurrenceIdentity(unittest.TestCase):
    def test_derive_resume_n_after_second_reality_loaded(self) -> None:
        from agents.monthly_plan_constructor.langgraph_runtime import (
            _count_reality_loaded_transitions,
            _derive_resume_n,
        )

        transitions = (
            LifecycleTransition(STATUS_MISSION_BOUND, STATUS_REALITY_LOADED, FIXED_AT),
            LifecycleTransition(
                "REVALIDATING_REALITY",
                STATUS_REALITY_LOADED,
                FIXED_AT,
            ),
        )
        lifecycle = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id="run-resume-n",
            created_at=FIXED_AT,
        )
        lifecycle = replace(
            lifecycle,
            transitions=transitions,
            status=STATUS_REALITY_LOADED,
        )
        self.assertEqual(_count_reality_loaded_transitions(transitions), 2)
        self.assertEqual(_derive_resume_n(lifecycle), 1)

    def test_distinct_event_ids_for_different_resume_n(self) -> None:
        key0 = ConstructorRuntimeEventKey(
            run_id=FIXED_RUN_ID,
            event_type=EventType.STAGE_STARTED,
            stage_id="CANDIDATE_ASSEMBLY",
            node_name="build_package",
            attempt_n=1,
            resume_n=0,
            semantic_occurrence_key="snapshot-read-1",
            artifact_correlation_id="read-1",
        )
        key1 = replace(key0, resume_n=1)
        self.assertNotEqual(
            compute_constructor_runtime_event_id(key0),
            compute_constructor_runtime_event_id(key1),
        )

    def test_hitl_resume_from_bind_wait_records_core_stages_once(self) -> None:
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.types import Command

        from agents.monthly_plan_constructor.durable_checkpoint import (
            build_constructor_jsonplus_serializer,
        )
        from agents.monthly_plan_constructor.hitl_contracts import (
            DECISION_CLARIFY_SCOPE,
            build_resume_command,
        )
        from agents.monthly_plan_constructor.hitl_resume import (
            build_decision_request_from_lifecycle,
        )

        run_id = "run-inc-10-3b-hitl-resume"
        recorder = InMemoryObservabilityRecorder()
        ctx = issue_read_only_agent_context(
            agent_code=AGENT_CODE,
            project_code=PROJECT,
            run_id=run_id,
        )
        app = build_constructor_langgraph(
            context=ctx,
            project_code=PROJECT,
            month_key=MONTH,
            facility_scope=["ALL", FACILITY_TARGET],
            assemble_candidates=StubAssembler(),
            scope_reader=RecordingReader(),
            now=FIXED_AT,
            checkpointer=InMemorySaver(serde=build_constructor_jsonplus_serializer()),
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
        self.assertEqual(out1["lifecycle"].status, STATUS_WAITING_FOR_HUMAN)
        self.assertEqual(
            [
                event.stage_id
                for event in recorder.events_for_run(run_id)
                if event.stage_id in CORE_STAGES
            ],
            [],
        )

        req = build_decision_request_from_lifecycle(out1["lifecycle"])
        snap = app.get_state(config)
        checkpoint_id = snap.config["configurable"]["checkpoint_id"]
        cmd = build_resume_command(
            decision_id="dec-10-3b-1",
            interrupt_id=req.interrupt_id,
            run_id=run_id,
            mission_id=MISSION_ID,
            decision=DECISION_CLARIFY_SCOPE,
            actor_id="human-1",
            parameters={"facility_scope": [FACILITY_TARGET]},
            expected_checkpoint_id=checkpoint_id,
            submitted_at=FIXED_AT,
        )
        out2 = app.invoke(Command(resume=cmd), config)
        self.assertEqual(out2["lifecycle"].status, STATUS_READY_FOR_HANDOFF)
        assembly_started = [
            event
            for event in recorder.events_for_run(run_id)
            if event.stage_id == "CANDIDATE_ASSEMBLY"
            and event.event_type == EventType.STAGE_STARTED
        ]
        self.assertEqual(len(assembly_started), 1)
        self.assertEqual(assembly_started[0].resume_n, 0)


class TestCheckpointReplayIdempotency(unittest.TestCase):
    def test_duplicate_stage_emit_is_idempotent_replay(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        _run_graph(recorder=recorder, evidence=[_history()])
        events = _stage_events(recorder, FIXED_RUN_ID)
        self.assertGreaterEqual(len(events), 2)
        first = events[0]
        before_count = len(recorder.events_for_run(FIXED_RUN_ID))
        result = recorder.record_event(first)
        self.assertEqual(result.outcome, RecordOutcome.IDEMPOTENT_REPLAY)
        self.assertEqual(len(recorder.events_for_run(FIXED_RUN_ID)), before_count)


class TestLifecycleErrorNoFalseTerminal(unittest.TestCase):
    def test_missing_lifecycle_raises_without_stage_events(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        ctx = _context()
        app = build_constructor_langgraph(
            context=ctx,
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            scope_reader=RecordingReader(),
            now=FIXED_AT,
            recorder=recorder,
        )
        with self.assertRaises(LifecycleError):
            app.invoke({})  # type: ignore[arg-type]
        self.assertEqual(recorder.events_for_run(FIXED_RUN_ID), ())


if __name__ == "__main__":
    unittest.main()
