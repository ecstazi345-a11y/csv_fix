"""
Increment 8 — HITL resume deterministic helper tests.

No Streamlit, Supabase, Postgres connection, LLM, or product writes.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Sequence

from agents.monthly_plan_constructor.candidate_package import LABOR_UNRESOLVED
from agents.monthly_plan_constructor.exception_engine import CODE_AMBIGUOUS_SCOPE
from agents.monthly_plan_constructor.hitl_contracts import (
    CODE_RUN_ABORTED_BY_HUMAN,
    DECISION_ABORT_RUN,
    DECISION_CLARIFY_SCOPE,
    HitlContractError,
    build_resume_command,
)
from agents.monthly_plan_constructor.hitl_resume import (
    apply_constructor_resume_command,
    build_decision_request_from_lifecycle,
    revalidate_constructor_resume_reality,
    stale_artifacts_cleared,
)
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_APPLYING_HUMAN_DECISION,
    STATUS_FAILED,
    STATUS_READY_FOR_HANDOFF,
    STATUS_REALITY_LOADED,
    STATUS_REVALIDATING_REALITY,
    STATUS_WAITING_FOR_HUMAN,
    CandidateAssemblyResult,
    LifecycleError,
    advance_constructor_lifecycle,
    create_lifecycle_state,
    run_constructor_lifecycle,
)
from agents.monthly_plan_constructor.mission_scope import ConstructorMissionScope
from agents.monthly_plan_constructor.secure_read_tools import (
    ConstructorRealityRead,
    SecureReadError,
)
from security.agent_execution_context import (
    AgentExecutionContext,
    issue_read_only_agent_context,
)

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"
MISSION_ID = "mission-increment-8-resume"
RUN_ID = "run-increment-8-resume"
FIXED_AT = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"


def _context(run_id: str = RUN_ID, project_code: str = PROJECT) -> AgentExecutionContext:
    return issue_read_only_agent_context(
        agent_code="MONTHLY_PLAN_CONSTRUCTOR",
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


class RecordingReader:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows if rows is not None else [_raw()]
        self.calls = 0
        self.last_mission: ConstructorMissionScope | None = None

    def __call__(
        self,
        context: AgentExecutionContext,
        mission: ConstructorMissionScope,
    ) -> list[dict[str, object]]:
        self.calls += 1
        self.last_mission = mission
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
        "queue": "Q1",
        "boq_code": "BOQ-001",
        "boq_name": "Воздуховод",
        "unit": "м2",
        "remaining_qty": 10.0,
        "already_planned_qty": 0.0,
        "available_to_add_qty": 10.0,
        "availability_status": "Доступно",
        "labor_norm_status": LABOR_UNRESOLVED,
    }
    base.update(overrides)
    return base


class StubAssembler:
    def __init__(self, candidates: list[dict[str, object]] | None = None) -> None:
        self.candidates = candidates if candidates is not None else [_candidate_dict()]
        self.calls = 0

    def __call__(
        self,
        reality_read: ConstructorRealityRead,
        scope: ConstructorMissionScope,
    ) -> CandidateAssemblyResult:
        self.calls += 1
        return CandidateAssemblyResult(
            candidates=tuple(self.candidates),
            scanned_count=max(1, len(self.candidates)),
        )


def _wait_state() -> object:
    return run_constructor_lifecycle(
        context=_context(),
        project_code=PROJECT,
        month_key=MONTH,
        facility_scope=["ALL", FACILITY_TARGET],
        assemble_candidates=StubAssembler(),
        scope_reader=RecordingReader(),
        mission_id=MISSION_ID,
        run_id=RUN_ID,
        now=FIXED_AT,
    )


def _cmd(**overrides: object):
    wait = _wait_state()
    req = build_decision_request_from_lifecycle(wait)  # type: ignore[arg-type]
    payload: dict[str, object] = {
        "decision_id": "dec-1",
        "interrupt_id": req.interrupt_id,
        "run_id": RUN_ID,
        "mission_id": MISSION_ID,
        "decision": DECISION_CLARIFY_SCOPE,
        "actor_id": "human-1",
        "parameters": {"facility_scope": [FACILITY_TARGET]},
        "submitted_at": FIXED_AT,
    }
    payload.update(overrides)
    return build_resume_command(**payload)  # type: ignore[arg-type]


class TestApplyResume(unittest.TestCase):
    def test_requires_wait(self) -> None:
        state = create_lifecycle_state(
            mission_id=MISSION_ID, run_id=RUN_ID, created_at=FIXED_AT
        )
        with self.assertRaises(LifecycleError):
            apply_constructor_resume_command(
                state,
                _cmd(),
                context=_context(),
                project_code=PROJECT,
                month_key=MONTH,
                now=FIXED_AT,
            )

    def test_run_id_mismatch(self) -> None:
        wait = _wait_state()
        cmd = _cmd(run_id="run-other")
        with self.assertRaises(HitlContractError):
            apply_constructor_resume_command(
                wait,  # type: ignore[arg-type]
                cmd,
                context=_context(),
                project_code=PROJECT,
                month_key=MONTH,
                now=FIXED_AT,
            )

    def test_mission_id_mismatch(self) -> None:
        wait = _wait_state()
        cmd = _cmd(mission_id="mission-other")
        with self.assertRaises(HitlContractError):
            apply_constructor_resume_command(
                wait,  # type: ignore[arg-type]
                cmd,
                context=_context(),
                project_code=PROJECT,
                month_key=MONTH,
                now=FIXED_AT,
            )

    def test_interrupt_id_mismatch(self) -> None:
        wait = _wait_state()
        cmd = _cmd(interrupt_id="eos-int-deadbeefdeadbeefdeadbeefdeadbe")
        with self.assertRaises(HitlContractError):
            apply_constructor_resume_command(
                wait,  # type: ignore[arg-type]
                cmd,
                context=_context(),
                project_code=PROJECT,
                month_key=MONTH,
                now=FIXED_AT,
            )

    def test_checkpoint_mismatch(self) -> None:
        wait = _wait_state()
        cmd = _cmd(expected_checkpoint_id="ckpt-expected")
        with self.assertRaises(HitlContractError):
            apply_constructor_resume_command(
                wait,  # type: ignore[arg-type]
                cmd,
                context=_context(),
                project_code=PROJECT,
                month_key=MONTH,
                checkpoint_id="ckpt-other",
                now=FIXED_AT,
            )

    def test_checkpoint_missing_when_expected(self) -> None:
        wait = _wait_state()
        cmd = _cmd(expected_checkpoint_id="ckpt-expected")
        with self.assertRaises(HitlContractError):
            apply_constructor_resume_command(
                wait,  # type: ignore[arg-type]
                cmd,
                context=_context(),
                project_code=PROJECT,
                month_key=MONTH,
                now=FIXED_AT,
            )

    def test_auth_project_mismatch(self) -> None:
        wait = _wait_state()
        with self.assertRaises(LifecycleError):
            apply_constructor_resume_command(
                wait,  # type: ignore[arg-type]
                _cmd(),
                context=_context(project_code="PRJ_OTHER"),
                project_code=PROJECT,
                month_key=MONTH,
                now=FIXED_AT,
            )

    def test_clarify_scope_reaches_revalidating(self) -> None:
        wait = _wait_state()
        prior_len = len(wait.transitions)  # type: ignore[union-attr]
        out = apply_constructor_resume_command(
            wait,  # type: ignore[arg-type]
            _cmd(),
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            now=FIXED_AT,
        )
        self.assertEqual(out.status, STATUS_REVALIDATING_REALITY)
        self.assertTrue(stale_artifacts_cleared(out))
        self.assertIsNotNone(out.scope)
        self.assertEqual(out.scope.facility_scope, (FACILITY_TARGET.upper(),))  # type: ignore[union-attr]
        self.assertGreater(len(out.transitions), prior_len)
        self.assertTrue(
            any(t.to_status == STATUS_APPLYING_HUMAN_DECISION for t in out.transitions)
        )

    def test_scope_widening_rejected(self) -> None:
        # First clarify to a narrow scope, then attempt widen via a synthetic WAIT
        # that already has narrow scope (simulate late WAIT with bound scope).
        wait = _wait_state()
        narrowed = apply_constructor_resume_command(
            wait,  # type: ignore[arg-type]
            _cmd(),
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            now=FIXED_AT,
        )
        # Force a second WAIT with narrow scope already present.
        from agents.monthly_plan_constructor.lifecycle import _append_transition
        from agents.monthly_plan_constructor.exception_engine import (
            build_exception_set,
            exception_from_failure,
        )

        mapped = exception_from_failure(
            CODE_AMBIGUOUS_SCOPE,
            source_capability="MISSION_SCOPE",
            reason="re-ambiguous",
            observed_at=FIXED_AT,
        )
        waiting2 = _append_transition(
            narrowed,
            to_status=STATUS_WAITING_FOR_HUMAN,
            at=FIXED_AT,
            trigger_code=CODE_AMBIGUOUS_SCOPE,
            source_capability="MISSION_SCOPE",
            note="second wait",
            exceptions=build_exception_set([mapped]),
            error_code=CODE_AMBIGUOUS_SCOPE,
            terminal_reason="re-ambiguous",
            reality_read=None,
            package=None,
            labor_resolutions=None,
        )
        req = build_decision_request_from_lifecycle(waiting2)
        cmd = build_resume_command(
            decision_id="dec-2",
            interrupt_id=req.interrupt_id,
            run_id=RUN_ID,
            mission_id=MISSION_ID,
            decision=DECISION_CLARIFY_SCOPE,
            actor_id="human-1",
            parameters={"facility_scope": None},  # widen to ALL
            submitted_at=FIXED_AT,
        )
        with self.assertRaises(HitlContractError):
            apply_constructor_resume_command(
                waiting2,
                cmd,
                context=_context(),
                project_code=PROJECT,
                month_key=MONTH,
                now=FIXED_AT,
            )

    def test_project_code_change_rejected(self) -> None:
        wait = _wait_state()
        cmd = _cmd(parameters={"facility_scope": [FACILITY_TARGET], "project_code": "OTHER"})
        with self.assertRaises(HitlContractError):
            apply_constructor_resume_command(
                wait,  # type: ignore[arg-type]
                cmd,
                context=_context(),
                project_code=PROJECT,
                month_key=MONTH,
                now=FIXED_AT,
            )

    def test_month_key_change_rejected(self) -> None:
        wait = _wait_state()
        cmd = _cmd(
            parameters={
                "facility_scope": [FACILITY_TARGET],
                "month_key": "октябрь-2026",
            }
        )
        with self.assertRaises(HitlContractError):
            apply_constructor_resume_command(
                wait,  # type: ignore[arg-type]
                cmd,
                context=_context(),
                project_code=PROJECT,
                month_key=MONTH,
                now=FIXED_AT,
            )

    def test_abort_run(self) -> None:
        wait = _wait_state()
        cmd = _cmd(decision=DECISION_ABORT_RUN, parameters={}, comment="stop")
        out = apply_constructor_resume_command(
            wait,  # type: ignore[arg-type]
            cmd,
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            now=FIXED_AT,
        )
        self.assertEqual(out.status, STATUS_FAILED)
        self.assertEqual(out.error_code, CODE_RUN_ABORTED_BY_HUMAN)
        self.assertTrue(stale_artifacts_cleared(out))

    def test_normal_advance_still_refuses_wait(self) -> None:
        wait = _wait_state()
        with self.assertRaises(LifecycleError):
            advance_constructor_lifecycle(
                wait,  # type: ignore[arg-type]
                context=_context(),
                project_code=PROJECT,
                month_key=MONTH,
                assemble_candidates=StubAssembler(),
                scope_reader=RecordingReader(),
                now=FIXED_AT,
            )


class TestRevalidate(unittest.TestCase):
    def test_fresh_secure_read(self) -> None:
        wait = _wait_state()
        revalidating = apply_constructor_resume_command(
            wait,  # type: ignore[arg-type]
            _cmd(),
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            now=FIXED_AT,
        )
        reader = RecordingReader()
        out = revalidate_constructor_resume_reality(
            revalidating,
            context=_context(),
            scope_reader=reader,
            now=FIXED_AT,
        )
        self.assertEqual(out.status, STATUS_REALITY_LOADED)
        self.assertEqual(reader.calls, 1)
        self.assertIsNotNone(out.reality_read)
        self.assertIsNone(out.package)
        self.assertIsNone(out.labor_resolutions)

    def test_secure_read_failure_fail_closed(self) -> None:
        wait = _wait_state()
        revalidating = apply_constructor_resume_command(
            wait,  # type: ignore[arg-type]
            _cmd(),
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            now=FIXED_AT,
        )

        def raising_reader(context, mission):
            raise SecureReadError("READ_FAILED", "boom")

        out = revalidate_constructor_resume_reality(
            revalidating,
            context=_context(),
            scope_reader=raising_reader,  # type: ignore[arg-type]
            now=FIXED_AT,
        )
        self.assertEqual(out.status, STATUS_FAILED)

    def test_stale_artifacts_never_reused(self) -> None:
        wait = _wait_state()
        revalidating = apply_constructor_resume_command(
            wait,  # type: ignore[arg-type]
            _cmd(),
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            now=FIXED_AT,
        )
        self.assertTrue(stale_artifacts_cleared(revalidating))
        # Inject stale package illegally then revalidate must refuse.
        from dataclasses import replace

        poisoned = replace(revalidating, package=object())  # type: ignore[arg-type]
        with self.assertRaises(LifecycleError):
            revalidate_constructor_resume_reality(
                poisoned,  # type: ignore[arg-type]
                context=_context(),
                scope_reader=RecordingReader(),
                now=FIXED_AT,
            )

    def test_continue_pipeline_after_revalidate(self) -> None:
        wait = _wait_state()
        revalidating = apply_constructor_resume_command(
            wait,  # type: ignore[arg-type]
            _cmd(),
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            now=FIXED_AT,
        )
        reality = revalidate_constructor_resume_reality(
            revalidating,
            context=_context(),
            scope_reader=RecordingReader(),
            now=FIXED_AT,
        )
        assembler = StubAssembler()
        state = reality
        while state.status not in {
            STATUS_READY_FOR_HANDOFF,
            STATUS_FAILED,
            STATUS_WAITING_FOR_HUMAN,
        }:
            state = advance_constructor_lifecycle(
                state,
                context=_context(),
                project_code=PROJECT,
                month_key=MONTH,
                assemble_candidates=assembler,
                labor_evidence=(),
                scope_reader=RecordingReader(),
                now=FIXED_AT,
            )
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        self.assertGreaterEqual(assembler.calls, 1)


if __name__ == "__main__":
    unittest.main()
