"""
Increment 10.3C — Constructor LangGraph tool / artifact instrumentation tests.

Non-Postgres only. Tool scope: load_constructor_scope only.
Artifact scope: ConstructorRealityRead + CandidatePackage only.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Sequence

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
)
from agents.monthly_plan_constructor.exception_engine import (
    CODE_READ_FAILED,
    CODE_SECURITY_DENIED,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_OBSERVED_PRODUCTIVITY,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    LaborNormEvidence,
    SOURCE_PROJECT_HISTORY,
)
from agents.monthly_plan_constructor.langgraph_runtime import (
    build_constructor_langgraph,
    run_constructor_langgraph,
)
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_FAILED,
    STATUS_MISSION_BOUND,
    STATUS_REALITY_LOADED,
    STATUS_READY_FOR_HANDOFF,
    advance_constructor_lifecycle,
    advance_constructor_reality_read_step,
    create_lifecycle_state,
)
from agents.monthly_plan_constructor.mission_scope import (
    ConstructorMissionScope,
    build_constructor_mission_scope,
)
from agents.monthly_plan_constructor.runtime_instrumentation import (
    RUN_CONTROL_OWNED_EVENT_TYPES,
)
from agents.monthly_plan_constructor.secure_read_tools import SecureReadError
from agents.observability.contracts import EventStatus, EventType
from agents.observability.recorder import (
    InMemoryObservabilityRecorder,
    RecordOutcome,
    RecordResult,
)
from security.agent_execution_context import (
    TOOL_LOAD_SCOPE,
    issue_read_only_agent_context,
)

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"
MISSION_ID = "mission-inc-10-3c"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
FIXED_AT = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)
FIXED_RUN_ID = "run-inc-10-3c"
AGENT_CODE = "MONTHLY_PLAN_CONSTRUCTOR"


def _context(project_code: str = PROJECT):
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

    def __call__(self, context, mission: ConstructorMissionScope):
        return list(self.rows)


class StubAssembler:
    def __init__(self, candidates: list[dict[str, object]] | None = None) -> None:
        self.candidates = candidates if candidates is not None else [
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
            }
        ]

    def __call__(self, reality_read, scope: ConstructorMissionScope):
        from agents.monthly_plan_constructor.lifecycle import CandidateAssemblyResult

        return CandidateAssemblyResult(
            candidates=tuple(self.candidates),
            scanned_count=max(1, len(self.candidates)),
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


def _run_graph(
    *,
    recorder: InMemoryObservabilityRecorder | None = None,
    reader: RecordingReader | None = None,
    evidence: Sequence[LaborNormEvidence] = (),
    run_id: str = FIXED_RUN_ID,
):
    return run_constructor_langgraph(
        context=_context(),
        project_code=PROJECT,
        month_key=MONTH,
        assemble_candidates=StubAssembler(),
        labor_evidence=evidence,
        scope_reader=reader or RecordingReader(),
        mission_id=MISSION_ID,
        run_id=run_id,
        now=FIXED_AT,
        recorder=recorder,
    )


def _events(recorder: InMemoryObservabilityRecorder, run_id: str):
    return list(recorder.events_for_run(run_id))


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
        self.assertEqual(baseline.status, with_recorder.status)
        self.assertEqual(baseline.run_id, with_recorder.run_id)
        self.assertEqual(
            [t.to_status for t in baseline.transitions],
            [t.to_status for t in with_recorder.transitions],
        )


class TestRealityReadToolEvents(unittest.TestCase):
    def setUp(self) -> None:
        self.recorder = InMemoryObservabilityRecorder()
        self.state = _run_graph(recorder=self.recorder, evidence=[_history()])

    def test_tool_started_completed(self) -> None:
        tool_events = [
            e
            for e in _events(self.recorder, FIXED_RUN_ID)
            if e.event_type
            in {
                EventType.TOOL_CALL_STARTED,
                EventType.TOOL_CALL_COMPLETED,
                EventType.TOOL_CALL_DENIED,
            }
            and e.tool_name == TOOL_LOAD_SCOPE
        ]
        self.assertEqual(
            [e.event_type for e in tool_events],
            [EventType.TOOL_CALL_STARTED, EventType.TOOL_CALL_COMPLETED],
        )
        self.assertEqual(tool_events[-1].status, EventStatus.OK)

    def test_reality_snapshot_artifact_created(self) -> None:
        artifacts = [
            e
            for e in _events(self.recorder, FIXED_RUN_ID)
            if e.event_type == EventType.ARTIFACT_CREATED
            and e.to_dict().get("detail", {}).get("artifact_type") == "snapshot"
        ]
        self.assertEqual(len(artifacts), 1)
        detail = artifacts[0].to_dict()["detail"]
        self.assertEqual(detail.get("artifact_type"), "snapshot")
        self.assertIn("row_count", detail)
        self.assertNotIn("rows", detail)

    def test_stage_events_still_present(self) -> None:
        stage_events = [
            e
            for e in _events(self.recorder, FIXED_RUN_ID)
            if e.stage_id == "REALITY_READ"
            and e.event_type
            in {
                EventType.STAGE_STARTED,
                EventType.STAGE_COMPLETED,
                EventType.STAGE_FAILED,
            }
        ]
        self.assertEqual(len(stage_events), 2)
        self.assertEqual(stage_events[0].event_type, EventType.STAGE_STARTED)
        self.assertEqual(stage_events[1].event_type, EventType.STAGE_COMPLETED)


class TestToolFailureEvents(unittest.TestCase):
    def test_security_denial_tool_denied(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        state = run_constructor_langgraph(
            context=_context(project_code="PRJ_OTHER"),
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            scope_reader=RecordingReader(),
            mission_id=MISSION_ID,
            run_id="run-security-deny",
            now=FIXED_AT,
            recorder=recorder,
        )
        self.assertEqual(state.status, STATUS_FAILED)
        tool_events = [
            e
            for e in _events(recorder, "run-security-deny")
            if e.tool_name == TOOL_LOAD_SCOPE
        ]
        self.assertEqual(
            [e.event_type for e in tool_events],
            [EventType.TOOL_CALL_STARTED, EventType.TOOL_CALL_DENIED],
        )
        self.assertEqual(tool_events[-1].status, EventStatus.DENIED)
        detail_text = str(tool_events[-1].to_dict()["detail"]).lower()
        self.assertNotIn("supabase", detail_text)
        self.assertNotIn("password", detail_text)

    def test_read_failure_tool_denied_failed(self) -> None:
        def raising_reader(context, mission):
            raise SecureReadError(CODE_READ_FAILED, "read failed")

        recorder = InMemoryObservabilityRecorder()
        state = _run_graph(
            recorder=recorder,
            reader=raising_reader,  # type: ignore[arg-type]
            run_id="run-read-fail",
        )
        self.assertEqual(state.status, STATUS_FAILED)
        tool_events = [
            e
            for e in _events(recorder, "run-read-fail")
            if e.tool_name == TOOL_LOAD_SCOPE
        ]
        self.assertEqual(tool_events[-1].event_type, EventType.TOOL_CALL_DENIED)
        self.assertEqual(tool_events[-1].status, EventStatus.FAILED)
        artifacts = [
            e
            for e in _events(recorder, "run-read-fail")
            if e.event_type == EventType.ARTIFACT_CREATED
        ]
        self.assertEqual(artifacts, [])


class TestCandidatePackageArtifact(unittest.TestCase):
    def test_package_artifact_created_once(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        state = _run_graph(recorder=recorder, evidence=[_history()])
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        package_artifacts = [
            e
            for e in _events(recorder, FIXED_RUN_ID)
            if e.event_type == EventType.ARTIFACT_CREATED
            and e.to_dict().get("detail", {}).get("artifact_type") == "package"
        ]
        self.assertEqual(len(package_artifacts), 1)
        detail = package_artifacts[0].to_dict()["detail"]
        self.assertEqual(detail.get("artifact_type"), "package")
        self.assertIn("candidate_count", detail)
        self.assertNotIn("candidates", detail)

    def test_no_labor_or_exception_artifacts(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        _run_graph(recorder=recorder, evidence=[_history()])
        for event in _events(recorder, FIXED_RUN_ID):
            if event.event_type != EventType.ARTIFACT_CREATED:
                continue
            detail = event.to_dict()["detail"]
            self.assertNotIn("labor", str(detail.get("artifact_type", "")).lower())
            self.assertNotIn("exception", str(detail.get("artifact_type", "")).lower())


class TestBoundaryAndReplay(unittest.TestCase):
    def test_no_run_control_events(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        _run_graph(recorder=recorder, evidence=[_history()])
        recorded = {e.event_type for e in _events(recorder, FIXED_RUN_ID)}
        self.assertTrue(recorded.isdisjoint(RUN_CONTROL_OWNED_EVENT_TYPES))

    def test_no_hitl_or_handoff_event_types(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        _run_graph(recorder=recorder, evidence=[_history()])
        forbidden = {
            EventType.HUMAN_WAIT_STARTED,
            EventType.HUMAN_DECISION_RECEIVED,
            EventType.RUN_RESUMED,
            EventType.REALITY_REFRESH_STARTED,
            EventType.REALITY_REFRESH_COMPLETED,
            EventType.HANDOFF_CREATED,
            EventType.HANDOFF_PERSISTED,
            EventType.RUN_COMPLETED,
        }
        recorded = {e.event_type for e in _events(recorder, FIXED_RUN_ID)}
        self.assertTrue(recorded.isdisjoint(forbidden))

    def test_replay_idempotent(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        _run_graph(recorder=recorder, evidence=[_history()])
        events = _events(recorder, FIXED_RUN_ID)
        first = events[0]
        result = recorder.record_event(first)
        self.assertEqual(result.outcome, RecordOutcome.IDEMPOTENT_REPLAY)


class TestRecorderFailurePolicy(unittest.TestCase):
    def test_recorder_failure_propagates(self) -> None:
        failing = FailingRecorder(fail_on=3)
        with self.assertRaises(RuntimeError):
            run_constructor_langgraph(
                context=_context(),
                project_code=PROJECT,
                month_key=MONTH,
                assemble_candidates=StubAssembler(),
                scope_reader=RecordingReader(),
                mission_id=MISSION_ID,
                run_id="run-recorder-fail",
                now=FIXED_AT,
                recorder=failing,  # type: ignore[arg-type]
            )


class TestLifecycleExtractionEquivalence(unittest.TestCase):
    def _mission_bound_state(self) -> tuple[Any, ConstructorMissionScope]:
        ctx = _context()
        scope = build_constructor_mission_scope(
            project_code=PROJECT,
            month_key=MONTH,
        )
        state = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id="run-lifecycle-extract",
            authorization_id=ctx.authorization_id,
            created_at=FIXED_AT,
        )
        bound = advance_constructor_lifecycle(
            state,
            context=ctx,
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            now=FIXED_AT,
        )
        return ctx, bound

    def test_step_matches_lifecycle_advance_happy_path(self) -> None:
        ctx, bound = self._mission_bound_state()
        via_lifecycle = advance_constructor_lifecycle(
            bound,
            context=ctx,
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            scope_reader=RecordingReader(),
            now=FIXED_AT,
        )
        ctx2, bound2 = self._mission_bound_state()
        via_step = advance_constructor_reality_read_step(
            bound2,
            context=ctx2,
            scope_reader=RecordingReader(),
            at=FIXED_AT,
        )
        self.assertEqual(via_lifecycle.status, via_step.status)
        self.assertEqual(via_lifecycle.status, STATUS_REALITY_LOADED)
        self.assertIsNotNone(via_lifecycle.reality_read)
        self.assertIsNotNone(via_step.reality_read)
        self.assertEqual(
            via_lifecycle.reality_read.row_count,  # type: ignore[union-attr]
            via_step.reality_read.row_count,  # type: ignore[union-attr]
        )

    def test_step_matches_lifecycle_read_failure(self) -> None:
        def raising_reader(context, mission):
            raise SecureReadError(CODE_READ_FAILED, "read failed")

        ctx, bound = self._mission_bound_state()
        via_lifecycle = advance_constructor_lifecycle(
            bound,
            context=ctx,
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            scope_reader=raising_reader,  # type: ignore[arg-type]
            now=FIXED_AT,
        )
        ctx2, bound2 = self._mission_bound_state()
        via_step = advance_constructor_reality_read_step(
            bound2,
            context=ctx2,
            scope_reader=raising_reader,  # type: ignore[arg-type]
            at=FIXED_AT,
        )
        self.assertEqual(via_lifecycle.status, via_step.status)
        self.assertEqual(via_lifecycle.status, STATUS_FAILED)
        self.assertEqual(via_lifecycle.error_code, via_step.error_code)

    def test_step_matches_lifecycle_security_denial(self) -> None:
        ctx = _context(project_code="PRJ_OTHER")
        scope = build_constructor_mission_scope(
            project_code=PROJECT,
            month_key=MONTH,
        )
        state = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id="run-sec-step",
            authorization_id=ctx.authorization_id,
            created_at=FIXED_AT,
        )
        bound = advance_constructor_lifecycle(
            state,
            context=ctx,
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            now=FIXED_AT,
        )
        via_lifecycle = advance_constructor_lifecycle(
            bound,
            context=ctx,
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            scope_reader=RecordingReader(),
            now=FIXED_AT,
        )
        ctx2 = _context(project_code="PRJ_OTHER")
        state2 = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id="run-sec-step-2",
            authorization_id=ctx2.authorization_id,
            created_at=FIXED_AT,
        )
        bound2 = advance_constructor_lifecycle(
            state2,
            context=ctx2,
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            now=FIXED_AT,
        )
        via_step = advance_constructor_reality_read_step(
            bound2,
            context=ctx2,
            scope_reader=RecordingReader(),
            at=FIXED_AT,
        )
        self.assertEqual(via_lifecycle.status, via_step.status)
        self.assertEqual(via_lifecycle.error_code, via_step.error_code)
        self.assertEqual(via_lifecycle.error_code, CODE_SECURITY_DENIED)


if __name__ == "__main__":
    unittest.main()
