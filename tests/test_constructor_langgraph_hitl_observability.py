"""
Increment 10.3D — Constructor LangGraph HITL / resume / reality refresh observability.

Non-Postgres only. Durable HITL via InMemorySaver.
"""

from __future__ import annotations

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
    CODE_SECURITY_DENIED,
)
from agents.monthly_plan_constructor.hitl_contracts import (
    DECISION_ABORT_RUN,
    DECISION_CLARIFY_SCOPE,
    build_resume_command,
    compute_eos_interrupt_id,
    count_wait_ordinal,
)
from agents.monthly_plan_constructor.hitl_resume import (
    build_decision_request_from_lifecycle,
    stale_artifacts_cleared,
)
from agents.monthly_plan_constructor.langgraph_runtime import build_constructor_langgraph
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_FAILED,
    STATUS_LABOR_RESOLVED,
    STATUS_READY_FOR_HANDOFF,
    STATUS_REVALIDATING_REALITY,
    STATUS_WAITING_FOR_HUMAN,
    advance_constructor_lifecycle,
    create_lifecycle_state,
)
from agents.monthly_plan_constructor.mission_scope import ConstructorMissionScope
from agents.monthly_plan_constructor.runtime_instrumentation import (
    RUN_CONTROL_OWNED_EVENT_TYPES,
    ConstructorRuntimeEventKey,
    compute_constructor_runtime_event_id,
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
MISSION_ID = "mission-inc-10-3d"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
FIXED_AT = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)
AGENT_CODE = "MONTHLY_PLAN_CONSTRUCTOR"

STAGE_EVENT_TYPES = frozenset(
    {
        EventType.STAGE_STARTED,
        EventType.STAGE_COMPLETED,
        EventType.STAGE_FAILED,
    }
)

HITL_EVENT_TYPES = frozenset(
    {
        EventType.HUMAN_WAIT_STARTED,
        EventType.HUMAN_DECISION_RECEIVED,
        EventType.RUN_RESUMED,
    }
)

REFRESH_EVENT_TYPES = frozenset(
    {
        EventType.REALITY_REFRESH_STARTED,
        EventType.REALITY_REFRESH_COMPLETED,
    }
)

HANDOFF_EVENT_TYPES = frozenset(
    {
        EventType.HANDOFF_CREATED,
        EventType.HANDOFF_PERSISTED,
        EventType.HANDOFF_PERSIST_FAILED,
        EventType.RUN_COMPLETED,
    }
)


def _context(*, run_id: str, project_code: str = PROJECT):
    return issue_read_only_agent_context(
        agent_code=AGENT_CODE,
        project_code=project_code,
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


class FailingRefreshReader:
    def __init__(
        self,
        *,
        fail_code: str = CODE_READ_FAILED,
        fail_from_call: int = 1,
    ) -> None:
        self.calls = 0
        self.fail_code = fail_code
        self.fail_from_call = fail_from_call
        self.rows = [_raw()]

    def __call__(self, context, mission: ConstructorMissionScope):
        self.calls += 1
        if self.calls >= self.fail_from_call:
            raise SecureReadError(self.fail_code, "refresh read failed")
        return list(self.rows)


@dataclass
class FakeHitlStore:
    open_calls: int = 0
    answer_calls: int = 0
    open_ids: list[str] = field(default_factory=list)

    def upsert_open_request(self, request) -> None:
        self.open_calls += 1
        if request.interrupt_id not in self.open_ids:
            self.open_ids.append(request.interrupt_id)

    def record_answer(self, *, interrupt_id: str, command) -> None:
        self.answer_calls += 1


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


def _hitl_app(
    *,
    run_id: str,
    recorder: InMemoryObservabilityRecorder | None = None,
    reader: Any | None = None,
    store: FakeHitlStore | None = None,
):
    from langgraph.checkpoint.memory import InMemorySaver

    from agents.monthly_plan_constructor.durable_checkpoint import (
        build_constructor_jsonplus_serializer,
    )

    ctx = _context(run_id=run_id)
    return (
        build_constructor_langgraph(
            context=ctx,
            project_code=PROJECT,
            month_key=MONTH,
            facility_scope=["ALL", FACILITY_TARGET],
            assemble_candidates=StubAssembler(),
            scope_reader=reader or RecordingReader(),
            now=FIXED_AT,
            checkpointer=InMemorySaver(serde=build_constructor_jsonplus_serializer()),
            hitl_store=store or FakeHitlStore(),
            recorder=recorder,
        ),
        ctx,
    )


def _wait_interrupt(app, *, run_id: str, mission_id: str = MISSION_ID):
    from langgraph.types import Command

    initial = create_lifecycle_state(
        mission_id=mission_id,
        run_id=run_id,
        authorization_id=_context(run_id=run_id).authorization_id,
        created_at=FIXED_AT,
    )
    config = {"configurable": {"thread_id": run_id}}
    out1 = app.invoke({"lifecycle": initial}, config)
    self_status = out1["lifecycle"].status
    assert self_status == STATUS_WAITING_FOR_HUMAN
    req = build_decision_request_from_lifecycle(out1["lifecycle"])
    snap = app.get_state(config)
    checkpoint_id = snap.config["configurable"]["checkpoint_id"]
    return out1, req, config, checkpoint_id


def _resume(
    app,
    *,
    config: dict[str, Any],
    req,
    checkpoint_id: str,
    run_id: str,
    decision_id: str,
    decision: str = DECISION_CLARIFY_SCOPE,
    comment: str | None = None,
):
    from langgraph.types import Command

    cmd = build_resume_command(
        decision_id=decision_id,
        interrupt_id=req.interrupt_id,
        run_id=run_id,
        mission_id=MISSION_ID,
        decision=decision,
        actor_id="human-1",
        parameters={"facility_scope": [FACILITY_TARGET]},
        expected_checkpoint_id=checkpoint_id,
        submitted_at=FIXED_AT,
        comment=comment,
    )
    return app.invoke(Command(resume=cmd), config)


def _events(recorder: InMemoryObservabilityRecorder, run_id: str):
    return list(recorder.events_for_run(run_id))


def _event_types(recorder: InMemoryObservabilityRecorder, run_id: str):
    return {event.event_type for event in _events(recorder, run_id)}


class TestRecorderNoneParity(unittest.TestCase):
    def test_recorder_none_preserves_hitl_lifecycle(self) -> None:
        run_id = "run-10-3d-none"
        app, _ = _hitl_app(run_id=run_id, recorder=None)
        out1, req, config, ckpt = _wait_interrupt(app, run_id=run_id)
        out2 = _resume(
            app,
            config=config,
            req=req,
            checkpoint_id=ckpt,
            run_id=run_id,
            decision_id="dec-none-1",
        )
        baseline = out2["lifecycle"]
        recorder = InMemoryObservabilityRecorder()
        app2, _ = _hitl_app(run_id=run_id + "-r", recorder=recorder)
        out1b, reqb, configb, ckptb = _wait_interrupt(app2, run_id=run_id + "-r")
        out2b = _resume(
            app2,
            config=configb,
            req=reqb,
            checkpoint_id=ckptb,
            run_id=run_id + "-r",
            decision_id="dec-none-1b",
        )
        recorded = out2b["lifecycle"]
        self.assertEqual(baseline.status, recorded.status)
        self.assertEqual(
            [t.to_status for t in baseline.transitions[-5:]],
            [t.to_status for t in recorded.transitions[-5:]],
        )


class TestHumanWaitEvents(unittest.TestCase):
    def test_human_wait_started_on_interrupt(self) -> None:
        run_id = "run-10-3d-wait"
        recorder = InMemoryObservabilityRecorder()
        app, _ = _hitl_app(run_id=run_id, recorder=recorder)
        _wait_interrupt(app, run_id=run_id)
        waits = [
            e
            for e in _events(recorder, run_id)
            if e.event_type == EventType.HUMAN_WAIT_STARTED
        ]
        self.assertEqual(len(waits), 1)
        self.assertEqual(waits[0].stage_id, "HUMAN_GATE")
        self.assertEqual(waits[0].node_name, "human_wait")
        self.assertIsNotNone(waits[0].interrupt_id)
        self.assertIsNotNone(waits[0].human_decision_request)
        self.assertIsNone(waits[0].human_decision_record)
        self.assertTrue(waits[0].human_decision_request.reason_code)
        self.assertGreaterEqual(len(waits[0].human_decision_request.allowed_decisions), 1)

    def test_wait_replay_is_idempotent(self) -> None:
        run_id = "run-10-3d-wait-replay"
        recorder = InMemoryObservabilityRecorder()
        app, _ = _hitl_app(run_id=run_id, recorder=recorder)
        out1, req, config, ckpt = _wait_interrupt(app, run_id=run_id)
        waits = [
            e
            for e in _events(recorder, run_id)
            if e.event_type == EventType.HUMAN_WAIT_STARTED
        ]
        self.assertEqual(len(waits), 1)
        before = len(_events(recorder, run_id))
        replay = recorder.record_event(waits[0])
        self.assertEqual(replay.outcome, RecordOutcome.IDEMPOTENT_REPLAY)
        self.assertEqual(len(_events(recorder, run_id)), before)
        out2 = _resume(
            app,
            config=config,
            req=req,
            checkpoint_id=ckpt,
            run_id=run_id,
            decision_id="dec-wait-replay",
        )
        self.assertEqual(out2["lifecycle"].status, STATUS_READY_FOR_HANDOFF)

    def test_multiple_real_waits_get_distinct_wait_identity(self) -> None:
        from agents.monthly_plan_constructor.lifecycle import (
            SOURCE_LIFECYCLE,
            _append_transition,
        )

        run_id = "run-10-3d-multi-wait"
        recorder = InMemoryObservabilityRecorder()
        real = advance_constructor_lifecycle

        def side_effect(state, **kwargs: Any):
            if (
                state.status == STATUS_LABOR_RESOLVED
                and count_wait_ordinal(state.transitions) >= 1
            ):
                return _append_transition(
                    state,
                    to_status=STATUS_WAITING_FOR_HUMAN,
                    at=state.updated_at,
                    trigger_code=CODE_AMBIGUOUS_SCOPE,
                    source_capability=SOURCE_LIFECYCLE,
                    note="second human gate for multi-wait identity test",
                    error_code=CODE_AMBIGUOUS_SCOPE,
                    terminal_reason=CODE_AMBIGUOUS_SCOPE,
                )
            return real(state, **kwargs)

        with patch(
            "agents.monthly_plan_constructor.langgraph_runtime.advance_constructor_lifecycle",
            side_effect=side_effect,
        ):
            app, _ = _hitl_app(run_id=run_id, recorder=recorder)
            _, req1, config, ckpt1 = _wait_interrupt(app, run_id=run_id)

        first_waits = [
            e
            for e in _events(recorder, run_id)
            if e.event_type == EventType.HUMAN_WAIT_STARTED
        ]
        self.assertEqual(len(first_waits), 1)
        first = first_waits[0]
        self.assertEqual(first.to_dict()["detail"]["wait_ordinal"], "1")
        interrupt_id_1 = compute_eos_interrupt_id(
            run_id=run_id,
            wait_ordinal=1,
            reason_code=CODE_AMBIGUOUS_SCOPE,
        )
        self.assertEqual(first.interrupt_id, interrupt_id_1)
        key1 = ConstructorRuntimeEventKey(
            run_id=run_id,
            event_type=EventType.HUMAN_WAIT_STARTED,
            stage_id="HUMAN_GATE",
            node_name="human_wait",
            attempt_n=1,
            resume_n=1,
            semantic_occurrence_key="wait-1",
            artifact_correlation_id=None,
        )
        self.assertEqual(first.event_id, compute_constructor_runtime_event_id(key1))

        with patch(
            "agents.monthly_plan_constructor.langgraph_runtime.advance_constructor_lifecycle",
            side_effect=side_effect,
        ):
            out2 = _resume(
                app,
                config=config,
                req=req1,
                checkpoint_id=ckpt1,
                run_id=run_id,
                decision_id="dec-multi-1",
            )

        self.assertEqual(out2["lifecycle"].status, STATUS_WAITING_FOR_HUMAN)
        self.assertEqual(count_wait_ordinal(out2["lifecycle"].transitions), 2)
        self.assertIn(EventType.RUN_RESUMED, _event_types(recorder, run_id))
        self.assertIn(EventType.REALITY_REFRESH_COMPLETED, _event_types(recorder, run_id))

        wait_events = [
            e
            for e in _events(recorder, run_id)
            if e.event_type == EventType.HUMAN_WAIT_STARTED
        ]
        self.assertEqual(len(wait_events), 2)
        self.assertEqual(
            [e.to_dict()["detail"]["wait_ordinal"] for e in wait_events],
            ["1", "2"],
        )

        interrupt_id_2 = compute_eos_interrupt_id(
            run_id=run_id,
            wait_ordinal=2,
            reason_code=CODE_AMBIGUOUS_SCOPE,
        )
        self.assertEqual(wait_events[1].interrupt_id, interrupt_id_2)
        self.assertNotEqual(wait_events[0].interrupt_id, wait_events[1].interrupt_id)

        key2 = ConstructorRuntimeEventKey(
            run_id=run_id,
            event_type=EventType.HUMAN_WAIT_STARTED,
            stage_id="HUMAN_GATE",
            node_name="human_wait",
            attempt_n=1,
            resume_n=2,
            semantic_occurrence_key="wait-2",
            artifact_correlation_id=None,
        )
        self.assertEqual(
            wait_events[1].event_id,
            compute_constructor_runtime_event_id(key2),
        )
        self.assertNotEqual(wait_events[0].event_id, wait_events[1].event_id)
    def test_decision_received_and_run_resumed(self) -> None:
        run_id = "run-10-3d-decision"
        recorder = InMemoryObservabilityRecorder()
        app, _ = _hitl_app(run_id=run_id, recorder=recorder)
        _, req, config, ckpt = _wait_interrupt(app, run_id=run_id)
        _resume(
            app,
            config=config,
            req=req,
            checkpoint_id=ckpt,
            run_id=run_id,
            decision_id="dec-clarify-1",
        )
        types = [e.event_type for e in _events(recorder, run_id)]
        self.assertIn(EventType.HUMAN_DECISION_RECEIVED, types)
        self.assertIn(EventType.RUN_RESUMED, types)
        decision_idx = types.index(EventType.HUMAN_DECISION_RECEIVED)
        resumed_idx = types.index(EventType.RUN_RESUMED)
        self.assertLess(decision_idx, resumed_idx)
        decisions = [
            e
            for e in _events(recorder, run_id)
            if e.event_type == EventType.HUMAN_DECISION_RECEIVED
        ]
        self.assertEqual(decisions[0].decision_id, "dec-clarify-1")
        self.assertIsNotNone(decisions[0].human_decision_record)
        self.assertIsNone(decisions[0].human_decision_request)
        self.assertEqual(decisions[0].human_decision_record.decision_code, DECISION_CLARIFY_SCOPE)

    def test_invalid_resume_emits_no_decision(self) -> None:
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.types import Command

        from agents.monthly_plan_constructor import langgraph_runtime as lg_runtime
        from agents.monthly_plan_constructor.durable_checkpoint import (
            build_constructor_jsonplus_serializer,
        )
        from agents.monthly_plan_constructor.hitl_contracts import HitlContractError

        run_id = "run-10-3d-invalid"
        wrong_thread = "wrong-thread"
        recorder = InMemoryObservabilityRecorder()
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
        config = {"configurable": {"thread_id": wrong_thread}}
        out1 = app.invoke({"lifecycle": initial}, config)
        req = build_decision_request_from_lifecycle(out1["lifecycle"])
        snap = app.get_state(config)
        ckpt = snap.config["configurable"]["checkpoint_id"]
        cmd = build_resume_command(
            decision_id="dec-invalid",
            interrupt_id=req.interrupt_id,
            run_id=run_id,
            mission_id=MISSION_ID,
            decision=DECISION_CLARIFY_SCOPE,
            actor_id="human-1",
            parameters={"facility_scope": [FACILITY_TARGET]},
            expected_checkpoint_id=ckpt,
            submitted_at=FIXED_AT,
        )
        with patch.object(
            lg_runtime,
            "apply_constructor_resume_command",
            wraps=lg_runtime.apply_constructor_resume_command,
        ) as apply_mock:
            with self.assertRaises(HitlContractError):
                app.invoke(Command(resume=cmd), config)
            apply_mock.assert_not_called()
        decisions = [
            e
            for e in _events(recorder, run_id)
            if e.event_type == EventType.HUMAN_DECISION_RECEIVED
        ]
        self.assertEqual(decisions, [])

    def test_abort_run_no_resume_or_refresh(self) -> None:
        run_id = "run-10-3d-abort"
        recorder = InMemoryObservabilityRecorder()
        app, _ = _hitl_app(run_id=run_id, recorder=recorder)
        _, req, config, ckpt = _wait_interrupt(app, run_id=run_id)
        out2 = _resume(
            app,
            config=config,
            req=req,
            checkpoint_id=ckpt,
            run_id=run_id,
            decision_id="dec-abort-1",
            decision=DECISION_ABORT_RUN,
            comment="stop please",
        )
        self.assertEqual(out2["lifecycle"].status, STATUS_FAILED)
        types = _event_types(recorder, run_id)
        self.assertIn(EventType.HUMAN_DECISION_RECEIVED, types)
        self.assertIn(EventType.RUN_ABORTED, types)
        self.assertNotIn(EventType.RUN_RESUMED, types)
        self.assertNotIn(EventType.RUN_FAILED, types)
        self.assertTrue(types.isdisjoint(REFRESH_EVENT_TYPES))
        refresh_tools = [
            e
            for e in _events(recorder, run_id)
            if e.stage_id == "REALITY_REVALIDATION"
            and e.event_type
            in {
                EventType.TOOL_CALL_STARTED,
                EventType.TOOL_CALL_COMPLETED,
                EventType.TOOL_CALL_DENIED,
            }
        ]
        self.assertEqual(refresh_tools, [])


class TestRealityRefreshEvents(unittest.TestCase):
    def test_refresh_success_chronology(self) -> None:
        run_id = "run-10-3d-refresh-ok"
        recorder = InMemoryObservabilityRecorder()
        reader = RecordingReader()
        app, _ = _hitl_app(run_id=run_id, recorder=recorder, reader=reader)
        _, req, config, ckpt = _wait_interrupt(app, run_id=run_id)
        out2 = _resume(
            app,
            config=config,
            req=req,
            checkpoint_id=ckpt,
            run_id=run_id,
            decision_id="dec-refresh-ok",
        )
        self.assertEqual(out2["lifecycle"].status, STATUS_READY_FOR_HANDOFF)
        self.assertGreaterEqual(reader.calls, 1)
        self.assertIsNotNone(out2["lifecycle"].reality_read)
        refresh = [
            e
            for e in _events(recorder, run_id)
            if e.stage_id == "REALITY_REVALIDATION"
        ]
        refresh_types = [e.event_type for e in refresh]
        self.assertIn(EventType.REALITY_REFRESH_STARTED, refresh_types)
        self.assertIn(EventType.REALITY_REFRESH_COMPLETED, refresh_types)
        completed = [
            e
            for e in refresh
            if e.event_type == EventType.REALITY_REFRESH_COMPLETED
        ]
        self.assertEqual(completed[0].status, EventStatus.OK)
        tool_events = [
            e
            for e in refresh
            if e.tool_name == TOOL_LOAD_SCOPE
            and e.event_type
            in {
                EventType.TOOL_CALL_STARTED,
                EventType.TOOL_CALL_COMPLETED,
                EventType.TOOL_CALL_DENIED,
            }
        ]
        self.assertEqual(
            [e.event_type for e in tool_events],
            [EventType.TOOL_CALL_STARTED, EventType.TOOL_CALL_COMPLETED],
        )
        artifacts = [
            e
            for e in _events(recorder, run_id)
            if e.event_type == EventType.ARTIFACT_CREATED
            and e.stage_id == "REALITY_REVALIDATION"
        ]
        self.assertEqual(len(artifacts), 1)

    def test_refresh_read_failure(self) -> None:
        run_id = "run-10-3d-refresh-fail"
        recorder = InMemoryObservabilityRecorder()
        reader = FailingRefreshReader()
        app, _ = _hitl_app(run_id=run_id, recorder=recorder, reader=reader)
        _, req, config, ckpt = _wait_interrupt(app, run_id=run_id)
        out2 = _resume(
            app,
            config=config,
            req=req,
            checkpoint_id=ckpt,
            run_id=run_id,
            decision_id="dec-refresh-fail",
        )
        self.assertEqual(out2["lifecycle"].status, STATUS_FAILED)
        completed = [
            e
            for e in _events(recorder, run_id)
            if e.event_type == EventType.REALITY_REFRESH_COMPLETED
        ]
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0].status, EventStatus.FAILED)
        denied = [
            e
            for e in _events(recorder, run_id)
            if e.event_type == EventType.TOOL_CALL_DENIED
            and e.stage_id == "REALITY_REVALIDATION"
        ]
        self.assertEqual(len(denied), 1)
        self.assertEqual(denied[0].status, EventStatus.FAILED)

    def test_refresh_security_denial(self) -> None:
        run_id = "run-10-3d-refresh-sec"
        recorder = InMemoryObservabilityRecorder()
        reader = FailingRefreshReader(fail_code=CODE_SECURITY_DENIED)
        app, _ = _hitl_app(run_id=run_id, recorder=recorder, reader=reader)
        _, req, config, ckpt = _wait_interrupt(app, run_id=run_id)
        _resume(
            app,
            config=config,
            req=req,
            checkpoint_id=ckpt,
            run_id=run_id,
            decision_id="dec-refresh-sec",
        )
        denied = [
            e
            for e in _events(recorder, run_id)
            if e.event_type == EventType.TOOL_CALL_DENIED
            and e.stage_id == "REALITY_REVALIDATION"
        ]
        self.assertEqual(len(denied), 1)
        self.assertEqual(denied[0].status, EventStatus.DENIED)

    def test_stale_artifacts_cleared_before_refresh(self) -> None:
        from agents.monthly_plan_constructor.hitl_resume import (
            apply_constructor_resume_command as apply_resume,
        )

        run_id = "run-10-3d-stale"
        recorder = InMemoryObservabilityRecorder()
        app, _ = _hitl_app(run_id=run_id, recorder=recorder)
        _, req, config, ckpt = _wait_interrupt(app, run_id=run_id)
        applied: list[Any] = []

        def capture_apply(state, command, **kwargs):
            result = apply_resume(state, command, **kwargs)
            applied.append(result)
            return result

        with patch(
            "agents.monthly_plan_constructor.langgraph_runtime.apply_constructor_resume_command",
            side_effect=capture_apply,
        ):
            _resume(
                app,
                config=config,
                req=req,
                checkpoint_id=ckpt,
                run_id=run_id,
                decision_id="dec-stale",
            )
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0].status, STATUS_REVALIDATING_REALITY)
        self.assertTrue(stale_artifacts_cleared(applied[0]))


class TestDataMinimizationAndBoundaries(unittest.TestCase):
    def test_no_sensitive_decision_payload_in_events(self) -> None:
        run_id = "run-10-3d-sec-data"
        recorder = InMemoryObservabilityRecorder()
        app, _ = _hitl_app(run_id=run_id, recorder=recorder)
        _, req, config, ckpt = _wait_interrupt(app, run_id=run_id)
        _resume(
            app,
            config=config,
            req=req,
            checkpoint_id=ckpt,
            run_id=run_id,
            decision_id="dec-sec-data",
            comment="secret human comment must not appear",
        )
        for event in _events(recorder, run_id):
            if event.event_type not in HITL_EVENT_TYPES | REFRESH_EVENT_TYPES:
                continue
            detail = event.to_dict()["detail"]
            detail_text = str(detail).lower()
            for forbidden in (
                "comment",
                "parameters",
                "scope_summary",
                "human_readable",
                "terminal_reason",
                "password",
                "secret",
                "dataframe",
                "rows",
            ):
                self.assertNotIn(forbidden, detail_text)

    def test_no_run_control_or_handoff_events(self) -> None:
        run_id = "run-10-3d-boundary"
        recorder = InMemoryObservabilityRecorder()
        app, _ = _hitl_app(run_id=run_id, recorder=recorder)
        _, req, config, ckpt = _wait_interrupt(app, run_id=run_id)
        _resume(
            app,
            config=config,
            req=req,
            checkpoint_id=ckpt,
            run_id=run_id,
            decision_id="dec-boundary",
        )
        types = _event_types(recorder, run_id)
        self.assertTrue(types.isdisjoint(RUN_CONTROL_OWNED_EVENT_TYPES))
        self.assertTrue(types.isdisjoint(HANDOFF_EVENT_TYPES))

    def test_stage_completed_on_wait_without_duplicate_stages(self) -> None:
        from dataclasses import replace

        from agents.monthly_plan_constructor.lifecycle import (
            ConstructorLifecycleState,
            STATUS_LABOR_RESOLVED,
            advance_constructor_lifecycle,
        )
        from agents.monthly_plan_constructor.labor_norm_resolver import (
            BASIS_OBSERVED_PRODUCTIVITY,
            HOURS_VALIDATED_PRODUCTIVE_DIRECT,
            LaborNormEvidence,
            SOURCE_PROJECT_HISTORY,
        )

        run_id = "run-10-3d-stage-wait"
        recorder = InMemoryObservabilityRecorder()
        real = advance_constructor_lifecycle
        evidence = LaborNormEvidence(
            evidence_id="ev-1",
            candidate_id=CANDIDATE_ID,
            source_type=SOURCE_PROJECT_HISTORY,
            labor_hours_per_unit=1.42,
            unit="м2",
            source_reference="ref",
            source_version="2026-08",
            planning_use_status=LABOR_VALIDATED,
            basis=BASIS_OBSERVED_PRODUCTIVITY,
            hours_quality=HOURS_VALIDATED_PRODUCTIVE_DIRECT,
            executed_quantity_validated=True,
        )

        def side_effect(state: ConstructorLifecycleState, **kwargs: Any):
            result = real(state, **kwargs)
            if state.status == STATUS_LABOR_RESOLVED:
                return replace(
                    result,
                    status=STATUS_WAITING_FOR_HUMAN,
                    error_code=CODE_AMBIGUOUS_SCOPE,
                )
            return result

        ctx = _context(run_id=run_id)
        with patch(
            "agents.monthly_plan_constructor.langgraph_runtime.advance_constructor_lifecycle",
            side_effect=side_effect,
        ):
            from langgraph.checkpoint.memory import InMemorySaver

            from agents.monthly_plan_constructor.durable_checkpoint import (
                build_constructor_jsonplus_serializer,
            )

            app = build_constructor_langgraph(
                context=ctx,
                project_code=PROJECT,
                month_key=MONTH,
                assemble_candidates=StubAssembler(),
                labor_evidence=(evidence,),
                scope_reader=RecordingReader(),
                now=FIXED_AT,
                checkpointer=InMemorySaver(
                    serde=build_constructor_jsonplus_serializer()
                ),
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
            app.invoke({"lifecycle": initial}, config)
        exc_stages = [
            e
            for e in _events(recorder, run_id)
            if e.stage_id == "EXCEPTION_ANALYSIS"
            and e.event_type in STAGE_EVENT_TYPES
        ]
        self.assertEqual(
            [e.event_type for e in exc_stages],
            [EventType.STAGE_STARTED, EventType.STAGE_COMPLETED],
        )


class TestRecorderFailurePolicy(unittest.TestCase):
    def test_failure_before_interrupt(self) -> None:
        run_id = "run-10-3d-rec-int"
        failing = FailingRecorder(fail_on=1)
        app, ctx = _hitl_app(run_id=run_id, recorder=failing)  # type: ignore[arg-type]
        initial = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id=run_id,
            authorization_id=ctx.authorization_id,
            created_at=FIXED_AT,
        )
        config = {"configurable": {"thread_id": run_id}}
        with self.assertRaises(RuntimeError):
            app.invoke({"lifecycle": initial}, config)

    def test_failure_before_apply(self) -> None:
        from agents.monthly_plan_constructor import langgraph_runtime as lg_runtime

        run_id = "run-10-3d-rec-apply"
        recorder = InMemoryObservabilityRecorder()
        app, _ = _hitl_app(run_id=run_id, recorder=recorder)
        _, req, config, ckpt = _wait_interrupt(app, run_id=run_id)
        original = lg_runtime.ConstructorRuntimeInstrumentation.emit

        def patched_emit(self, **kwargs):
            if kwargs["key"].event_type == EventType.HUMAN_DECISION_RECEIVED:
                raise RuntimeError("recorder-down")
            return original(self, **kwargs)

        with patch.object(lg_runtime.ConstructorRuntimeInstrumentation, "emit", patched_emit):
            with patch.object(
                lg_runtime,
                "apply_constructor_resume_command",
                wraps=lg_runtime.apply_constructor_resume_command,
            ) as apply_mock:
                with self.assertRaises(RuntimeError):
                    _resume(
                        app,
                        config=config,
                        req=req,
                        checkpoint_id=ckpt,
                        run_id=run_id,
                        decision_id="dec-rec-apply",
                    )
                apply_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
