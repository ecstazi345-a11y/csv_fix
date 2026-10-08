"""
RUNTIME-A — Professional Human Review Gate + Reviewed Package runtime.

Pure runtime tests. No Streamlit UI. No new DB/store. No product writes.
"""

from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_PROVISIONAL,
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_NORMATIVE_BENCHMARK,
    BASIS_OBSERVED_PRODUCTIVITY,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    LaborNormEvidence,
    SOURCE_OFFICIAL_NORMATIVE,
    SOURCE_PROJECT_HISTORY,
)
from agents.monthly_plan_constructor.durable_checkpoint import (
    build_constructor_jsonplus_serializer,
)
from agents.monthly_plan_constructor.human_review_contracts import (
    HumanReviewContractError,
    HumanReviewDecision,
    build_human_review_event,
)
from agents.monthly_plan_constructor.hitl_contracts import (
    CODE_HITL_CONTRACT_BLOCKER,
    DECISION_CLARIFY_SCOPE,
    HitlContractError,
    build_resume_command,
)
from agents.monthly_plan_constructor.hitl_resume import (
    build_decision_request_from_lifecycle,
)
from agents.monthly_plan_constructor.langgraph_runtime import (
    build_constructor_langgraph,
    run_constructor_langgraph,
)
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_READY_FOR_HANDOFF,
    STATUS_REVIEWED_PACKAGE_READY,
    STATUS_WAITING_FOR_HUMAN,
    STATUS_WAITING_FOR_HUMAN_CONFIRM,
    STATUS_WAITING_FOR_HUMAN_REVIEW,
    CandidateAssemblyResult,
    create_lifecycle_state,
    run_constructor_lifecycle,
)
from agents.monthly_plan_constructor.mission_scope import (
    CODE_AMBIGUOUS_SCOPE,
)
from agents.monthly_plan_constructor.professional_review_resume import (
    ProfessionalHumanReviewResumeCommand,
    WAIT_KIND_HUMAN_REVIEW,
    apply_professional_human_review,
    build_professional_review_wait_request,
)
from agents.observability.contracts import EventType
from agents.observability.recorder import InMemoryObservabilityRecorder
from security.agent_execution_context import issue_read_only_agent_context

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY = "16160-17"
DISCIPLINE = "Автоматизация"
MISSION_ID = "mission-rta-1"
RUN_ID = "run-rta-1"
CAND_A = "CAND-A"
CAND_B = "CAND-B"
FIXED_AT = datetime(2026, 10, 8, 15, 0, 0, tzinfo=timezone.utc)


def _raw_row() -> dict[str, object]:
    return {
        "project_code": PROJECT,
        "month_key": MONTH,
        "facility": FACILITY,
        "facility_building": FACILITY,
        "discipline": DISCIPLINE,
        "construction_discipline": DISCIPLINE,
        "system": "SYS-1",
        "system_label": "SYS-1",
        "iwp": "IWP-1",
        "boq_code": "BOQ-001",
        "boq_name": "Кабель",
        "unit": "м",
        "remaining_qty": 10.0,
    }


class StubAssembler:
    def __init__(self, *, labor_status: str = LABOR_VALIDATED, two: bool = False) -> None:
        self.labor_status = labor_status
        self.two = two

    def __call__(self, reality_read, scope) -> CandidateAssemblyResult:
        def one(cid: str, boq: str) -> dict[str, object]:
            return {
                "candidate_id": cid,
                "project_code": PROJECT,
                "month_key": MONTH,
                "facility": FACILITY,
                "discipline": DISCIPLINE,
                "system": "SYS-1",
                "iwp": "IWP-1",
                "queue": "",
                "boq_code": boq,
                "boq_name": "Кабель",
                "unit": "м",
                "remaining_qty": 10.0,
                "already_planned_qty": 0.0,
                "available_to_add_qty": 10.0,
                "availability_status": "AVAILABLE",
                "labor_norm_status": self.labor_status,
            }

        items = [one(CAND_A, "BOQ-001")]
        if self.two:
            items.append(one(CAND_B, "BOQ-002"))
        return CandidateAssemblyResult(
            candidates=tuple(items),
            scanned_count=len(items),
        )


class RecordingReader:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, context, mission) -> list[dict[str, object]]:
        self.calls += 1
        return [_raw_row()]


def _ctx(run_id: str = RUN_ID):
    return issue_read_only_agent_context(
        agent_code="MONTHLY_PLAN_CONSTRUCTOR",
        project_code=PROJECT,
        run_id=run_id,
    )


def _validated_evidence(candidate_id: str = CAND_A) -> LaborNormEvidence:
    return LaborNormEvidence(
        evidence_id="ev-project",
        candidate_id=candidate_id,
        source_type=SOURCE_PROJECT_HISTORY,
        labor_hours_per_unit=1.42,
        unit="м",
        source_reference="project-history-run",
        source_version="2026-08",
        planning_use_status=LABOR_VALIDATED,
        basis=BASIS_OBSERVED_PRODUCTIVITY,
        hours_quality=HOURS_VALIDATED_PRODUCTIVE_DIRECT,
        executed_quantity_validated=True,
    )


def _provisional_evidence(candidate_id: str = CAND_A) -> LaborNormEvidence:
    return LaborNormEvidence(
        evidence_id="ev-official",
        candidate_id=candidate_id,
        source_type=SOURCE_OFFICIAL_NORMATIVE,
        labor_hours_per_unit=2.0,
        unit="м",
        source_reference="gesn-table",
        planning_use_status=LABOR_PROVISIONAL,
        basis=BASIS_NORMATIVE_BENCHMARK,
    )


def _run_lifecycle(*, labor_status: str = LABOR_VALIDATED, run_id: str = RUN_ID):
    evidence: tuple[LaborNormEvidence, ...] = ()
    if labor_status == LABOR_VALIDATED:
        evidence = (_validated_evidence(),)
    elif labor_status == LABOR_PROVISIONAL:
        evidence = (_provisional_evidence(),)
    return run_constructor_lifecycle(
        context=_ctx(run_id),
        project_code=PROJECT,
        month_key=MONTH,
        facility_scope=FACILITY,
        discipline_scope=DISCIPLINE,
        assemble_candidates=StubAssembler(labor_status=labor_status),
        labor_evidence=evidence,
        scope_reader=RecordingReader(),
        mission_id=MISSION_ID,
        run_id=run_id,
        now=FIXED_AT,
    )


def _review_event(package, *, decision=HumanReviewDecision.ADD, event_id="rev-1", cand=CAND_A):
    return build_human_review_event(
        review_event_id=event_id,
        run_id=package.run_id,
        mission_id=package.mission_id,
        package_id=package.package_id,
        candidate_id=cand,
        decision=decision,
        actor_id="operator-1",
        reviewed_at=FIXED_AT,
    )


class RuntimeALifecycleTests(unittest.TestCase):
    def test_01_normal_path_reaches_waiting_for_human_review(self) -> None:
        state = _run_lifecycle()
        self.assertEqual(state.status, STATUS_WAITING_FOR_HUMAN_REVIEW)
        self.assertIsNotNone(state.package)
        self.assertIsNotNone(state.exceptions)
        self.assertNotEqual(state.status, STATUS_READY_FOR_HANDOFF)

    def test_02_wait_bound_to_run_mission_package(self) -> None:
        state = _run_lifecycle()
        req = build_professional_review_wait_request(state, created_at=FIXED_AT)
        self.assertEqual(req.wait_kind, WAIT_KIND_HUMAN_REVIEW)
        self.assertEqual(req.run_id, RUN_ID)
        self.assertEqual(req.mission_id, MISSION_ID)
        self.assertEqual(req.package_id, state.package.package_id)
        self.assertEqual(req.candidate_ids, (CAND_A,))


class RuntimeAGraphTests(unittest.TestCase):
    def _build_app(
        self,
        *,
        assembler=None,
        reader=None,
        run_id=RUN_ID,
        labor_evidence=None,
        handoff_store=None,
        recorder=None,
        facility_scope=FACILITY,
    ):
        ctx = _ctx(run_id)
        checkpointer = InMemorySaver(serde=build_constructor_jsonplus_serializer())
        app = build_constructor_langgraph(
            context=ctx,
            project_code=PROJECT,
            month_key=MONTH,
            facility_scope=facility_scope,
            discipline_scope=DISCIPLINE,
            assemble_candidates=assembler or StubAssembler(),
            labor_evidence=labor_evidence
            if labor_evidence is not None
            else (_validated_evidence(),),
            scope_reader=reader or RecordingReader(),
            now=FIXED_AT,
            checkpointer=checkpointer,
            handoff_store=handoff_store,
            recorder=recorder,
        )
        return app, ctx, checkpointer

    def test_03_generic_ambiguous_scope_hitl_still_works(self) -> None:
        """AMBIGUOUS_SCOPE wait still uses generic HITL path, not professional review."""
        from agents.monthly_plan_constructor.hitl_contracts import (
            DECISION_CLARIFY_SCOPE,
            build_resume_command,
        )
        from agents.monthly_plan_constructor.hitl_resume import (
            build_decision_request_from_lifecycle,
        )

        run_id = "run-rta-ambiguous"
        ctx = _ctx(run_id)
        reader = RecordingReader()
        app = build_constructor_langgraph(
            context=ctx,
            project_code=PROJECT,
            month_key=MONTH,
            facility_scope=["ALL", FACILITY],
            assemble_candidates=StubAssembler(),
            labor_evidence=(_validated_evidence(),),
            scope_reader=reader,
            now=FIXED_AT,
            checkpointer=InMemorySaver(serde=build_constructor_jsonplus_serializer()),
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
        interrupt_value = out1["__interrupt__"][0].value
        self.assertEqual(interrupt_value.reason_code, CODE_AMBIGUOUS_SCOPE)

        req = build_decision_request_from_lifecycle(out1["lifecycle"])
        snap = app.get_state(config)
        checkpoint_id = snap.config["configurable"]["checkpoint_id"]
        cmd = build_resume_command(
            decision_id="dec-rta-1",
            interrupt_id=req.interrupt_id,
            run_id=run_id,
            mission_id=MISSION_ID,
            decision=DECISION_CLARIFY_SCOPE,
            actor_id="human-1",
            parameters={"facility_scope": [FACILITY]},
            expected_checkpoint_id=checkpoint_id,
            submitted_at=FIXED_AT,
        )
        out2 = app.invoke(Command(resume=cmd), config)
        # After clarify + labor, professional review wait is next (not READY_FOR_HANDOFF).
        self.assertEqual(out2["lifecycle"].status, STATUS_WAITING_FOR_HUMAN_REVIEW)
        self.assertEqual(out2["__interrupt__"][0].value.wait_kind, WAIT_KIND_HUMAN_REVIEW)

    def test_04_15_valid_add_reaches_reviewed_ready_no_completed(self) -> None:
        app, ctx, _ = self._build_app()
        initial = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id=RUN_ID,
            authorization_id=ctx.authorization_id,
            created_at=FIXED_AT,
        )
        config = {"configurable": {"thread_id": RUN_ID}}
        out1 = app.invoke({"lifecycle": initial}, config)
        self.assertEqual(out1["lifecycle"].status, STATUS_WAITING_FOR_HUMAN_REVIEW)
        wait_req = out1["__interrupt__"][0].value
        package = out1["lifecycle"].package
        event = _review_event(package, decision=HumanReviewDecision.ADD)
        snap = app.get_state(config)
        checkpoint_id = snap.config["configurable"]["checkpoint_id"]
        cmd = ProfessionalHumanReviewResumeCommand(
            schema_version="1.0",
            interrupt_id=wait_req.interrupt_id,
            run_id=RUN_ID,
            review_events=(event,),
            answered_at=FIXED_AT,
            expected_checkpoint_id=checkpoint_id,
        )
        out2 = app.invoke(Command(resume=cmd), config)
        lifecycle = out2["lifecycle"]
        # RUNTIME-B: resolved review continues into Human Confirm wait.
        self.assertEqual(lifecycle.status, STATUS_WAITING_FOR_HUMAN_CONFIRM)
        self.assertIsNotNone(lifecycle.reviewed_package)
        self.assertEqual(lifecycle.reviewed_package.unresolved_count, 0)
        self.assertEqual(lifecycle.reviewed_package.included_count, 1)
        self.assertNotEqual(lifecycle.status, STATUS_READY_FOR_HANDOFF)
        self.assertIn("__interrupt__", out2)

    def test_05_stale_package_review_fail_closed(self) -> None:
        app, ctx, _ = self._build_app()
        initial = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id=RUN_ID,
            authorization_id=ctx.authorization_id,
            created_at=FIXED_AT,
        )
        config = {"configurable": {"thread_id": RUN_ID}}
        out1 = app.invoke({"lifecycle": initial}, config)
        wait_req = out1["__interrupt__"][0].value
        package = out1["lifecycle"].package
        stale = build_human_review_event(
            review_event_id="stale-1",
            run_id=RUN_ID,
            mission_id=MISSION_ID,
            package_id="other-package-id",
            candidate_id=CAND_A,
            decision=HumanReviewDecision.ADD,
            actor_id="operator-1",
            reviewed_at=FIXED_AT,
        )
        snap = app.get_state(config)
        cmd = ProfessionalHumanReviewResumeCommand(
            schema_version="1.0",
            interrupt_id=wait_req.interrupt_id,
            run_id=RUN_ID,
            review_events=(stale,),
            answered_at=FIXED_AT,
            expected_checkpoint_id=snap.config["configurable"]["checkpoint_id"],
        )
        with self.assertRaises(HumanReviewContractError):
            app.invoke(Command(resume=cmd), config)

    def test_06_unknown_candidate_fail_closed(self) -> None:
        state = _run_lifecycle(run_id="run-unknown")
        wait_req = build_professional_review_wait_request(state, created_at=FIXED_AT)
        bad = build_human_review_event(
            review_event_id="bad-cand",
            run_id="run-unknown",
            mission_id=MISSION_ID,
            package_id=state.package.package_id,
            candidate_id="UNKNOWN",
            decision=HumanReviewDecision.ADD,
            actor_id="operator-1",
            reviewed_at=FIXED_AT,
        )
        cmd = ProfessionalHumanReviewResumeCommand(
            schema_version="1.0",
            interrupt_id=wait_req.interrupt_id,
            run_id="run-unknown",
            review_events=(bad,),
            answered_at=FIXED_AT,
        )
        with self.assertRaises(HumanReviewContractError):
            apply_professional_human_review(state, cmd, wait_request=wait_req, now=FIXED_AT)

    def test_07_recommendation_not_mutated(self) -> None:
        state = _run_lifecycle(run_id="run-rec")
        before = copy.deepcopy(state.package.candidates[0])
        wait_req = build_professional_review_wait_request(state, created_at=FIXED_AT)
        event = _review_event(state.package)
        cmd = ProfessionalHumanReviewResumeCommand(
            schema_version="1.0",
            interrupt_id=wait_req.interrupt_id,
            run_id="run-rec",
            review_events=(event,),
            answered_at=FIXED_AT,
        )
        after = apply_professional_human_review(
            state, cmd, wait_request=wait_req, now=FIXED_AT
        )
        self.assertEqual(after.package.candidates[0].recommendation, before.recommendation)
        self.assertEqual(
            after.package.candidates[0].recommendation_reason_codes,
            before.recommendation_reason_codes,
        )
        self.assertEqual(
            after.package.candidates[0].labor_norm_status, before.labor_norm_status
        )

    def test_08_10_11_12_unresolved_loop_new_package_id(self) -> None:
        state = _run_lifecycle(labor_status=LABOR_UNRESOLVED, run_id="run-loop")
        wait1 = build_professional_review_wait_request(state, created_at=FIXED_AT)
        add1 = _review_event(state.package, event_id="rev-add-1")
        mid = apply_professional_human_review(
            state,
            ProfessionalHumanReviewResumeCommand(
                schema_version="1.0",
                interrupt_id=wait1.interrupt_id,
                run_id="run-loop",
                review_events=(add1,),
                answered_at=FIXED_AT,
            ),
            wait_request=wait1,
            now=FIXED_AT,
        )
        self.assertEqual(mid.status, STATUS_WAITING_FOR_HUMAN_REVIEW)
        self.assertIsNotNone(mid.reviewed_package)
        self.assertGreater(mid.reviewed_package.unresolved_count, 0)
        old_package = mid.reviewed_package
        old_id = old_package.reviewed_package_id
        history_before = mid.human_review_events

        wait2 = build_professional_review_wait_request(mid, created_at=FIXED_AT)
        self.assertNotEqual(wait2.interrupt_id, wait1.interrupt_id)
        remove = _review_event(
            mid.package,
            decision=HumanReviewDecision.REMOVE,
            event_id="rev-remove-2",
        )
        final = apply_professional_human_review(
            mid,
            ProfessionalHumanReviewResumeCommand(
                schema_version="1.0",
                interrupt_id=wait2.interrupt_id,
                run_id="run-loop",
                review_events=(remove,),
                answered_at=FIXED_AT,
            ),
            wait_request=wait2,
            now=FIXED_AT,
        )
        self.assertEqual(final.status, STATUS_REVIEWED_PACKAGE_READY)
        self.assertNotEqual(final.reviewed_package.reviewed_package_id, old_id)
        self.assertEqual(old_package.reviewed_package_id, old_id)  # immutable
        self.assertEqual(len(final.human_review_events), len(history_before) + 1)

    def test_13_14_resolved_ready_not_handoff(self) -> None:
        state = _run_lifecycle(labor_status=LABOR_PROVISIONAL, run_id="run-ready")
        wait_req = build_professional_review_wait_request(state, created_at=FIXED_AT)
        final = apply_professional_human_review(
            state,
            ProfessionalHumanReviewResumeCommand(
                schema_version="1.0",
                interrupt_id=wait_req.interrupt_id,
                run_id="run-ready",
                review_events=(_review_event(state.package),),
                answered_at=FIXED_AT,
            ),
            wait_request=wait_req,
            now=FIXED_AT,
        )
        self.assertEqual(final.status, STATUS_REVIEWED_PACKAGE_READY)
        self.assertNotEqual(final.status, STATUS_READY_FOR_HANDOFF)

    def test_16_17_no_handoff_store_and_checkpoint_roundtrip(self) -> None:
        app, ctx, checkpointer = self._build_app(run_id="run-ckpt")
        initial = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id="run-ckpt",
            authorization_id=ctx.authorization_id,
            created_at=FIXED_AT,
        )
        config = {"configurable": {"thread_id": "run-ckpt"}}
        out1 = app.invoke({"lifecycle": initial}, config)
        self.assertEqual(out1["lifecycle"].status, STATUS_WAITING_FOR_HUMAN_REVIEW)
        # Restore from checkpoint
        snap = app.get_state(config)
        restored = snap.values["lifecycle"]
        self.assertEqual(restored.status, STATUS_WAITING_FOR_HUMAN_REVIEW)
        self.assertEqual(restored.package.package_id, out1["lifecycle"].package.package_id)
        self.assertIsNotNone(restored.exceptions)
        wait_req = build_professional_review_wait_request(restored, created_at=FIXED_AT)
        self.assertEqual(wait_req.package_id, restored.package.package_id)

    def test_19_identical_replay_idempotent(self) -> None:
        state = _run_lifecycle(run_id="run-replay")
        wait_req = build_professional_review_wait_request(state, created_at=FIXED_AT)
        event = _review_event(state.package, event_id="same-evt")
        cmd = ProfessionalHumanReviewResumeCommand(
            schema_version="1.0",
            interrupt_id=wait_req.interrupt_id,
            run_id="run-replay",
            review_events=(event, event),
            answered_at=FIXED_AT,
        )
        final = apply_professional_human_review(
            state, cmd, wait_request=wait_req, now=FIXED_AT
        )
        self.assertEqual(final.status, STATUS_REVIEWED_PACKAGE_READY)
        self.assertEqual(len(final.human_review_events), 1)

    def test_gap_a_reviewed_package_ready_checkpoint_restore(self) -> None:
        """TEST_PROVEN (not LIVE_PROVEN): REVIEWED_PACKAGE_READY survives checkpoint."""
        run_id = "run-rta-ready-ckpt"
        recorder = InMemoryObservabilityRecorder()
        handoff_calls: list[object] = []

        class TrackingHandoffStore:
            def get(self, handoff_id: str):
                return None

            def put_if_absent(self, handoff):
                handoff_calls.append(handoff)
                raise AssertionError("professional path must not persist handoff")

        app, ctx, _ = self._build_app(
            run_id=run_id,
            handoff_store=TrackingHandoffStore(),
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
        self.assertEqual(out1["lifecycle"].status, STATUS_WAITING_FOR_HUMAN_REVIEW)
        wait_req = out1["__interrupt__"][0].value
        before = out1["lifecycle"]
        event = _review_event(before.package, event_id="rev-ready-ckpt")
        snap = app.get_state(config)
        out2 = app.invoke(
            Command(
                resume=ProfessionalHumanReviewResumeCommand(
                    schema_version="1.0",
                    interrupt_id=wait_req.interrupt_id,
                    run_id=run_id,
                    review_events=(event,),
                    answered_at=FIXED_AT,
                    expected_checkpoint_id=snap.config["configurable"]["checkpoint_id"],
                )
            ),
            config,
        )
        ready = out2["lifecycle"]
        # After resolved review, RUNTIME-B parks at Confirm wait with reviewed package.
        self.assertEqual(ready.status, STATUS_WAITING_FOR_HUMAN_CONFIRM)
        self.assertIsNotNone(ready.reviewed_package)
        self.assertEqual(len(ready.human_review_events), 1)

        # Checkpoint restore (InMemorySaver get_state) — TEST_PROVEN, not live crash.
        restored = app.get_state(config).values["lifecycle"]
        self.assertEqual(restored.status, STATUS_WAITING_FOR_HUMAN_CONFIRM)
        self.assertEqual(restored.run_id, run_id)
        self.assertEqual(restored.mission_id, MISSION_ID)
        self.assertEqual(restored.package.package_id, ready.package.package_id)
        self.assertEqual(
            [e.review_event_id for e in restored.human_review_events],
            [e.review_event_id for e in ready.human_review_events],
        )
        self.assertEqual(
            [e.decision for e in restored.human_review_events],
            [e.decision for e in ready.human_review_events],
        )
        self.assertEqual(
            restored.reviewed_package.reviewed_package_id,
            ready.reviewed_package.reviewed_package_id,
        )
        self.assertEqual(
            restored.reviewed_package.source_candidate_package_id,
            ready.package.package_id,
        )
        self.assertEqual(
            restored.reviewed_package.included_count,
            ready.reviewed_package.included_count,
        )
        self.assertEqual(
            restored.reviewed_package.excluded_count,
            ready.reviewed_package.excluded_count,
        )
        self.assertEqual(
            restored.reviewed_package.unresolved_count,
            ready.reviewed_package.unresolved_count,
        )
        self.assertEqual(
            [r.disposition for r in restored.reviewed_package.reviewed_records],
            [r.disposition for r in ready.reviewed_package.reviewed_records],
        )
        self.assertIsNotNone(restored.exceptions)
        self.assertEqual(
            [e.exception_code for e in restored.exceptions.exceptions],
            [e.exception_code for e in ready.exceptions.exceptions],
        )
        self.assertEqual(handoff_calls, [])
        self.assertNotIn(
            EventType.RUN_COMPLETED,
            {ev.event_type for ev in recorder.events_for_run(run_id)},
        )
        self.assertNotEqual(restored.status, STATUS_READY_FOR_HANDOFF)

        # Serializer round-trip of the same professional state.
        serde = build_constructor_jsonplus_serializer()
        tag, payload = serde.dumps_typed(ready)
        loaded = serde.loads_typed((tag, payload))
        self.assertEqual(loaded.status, STATUS_WAITING_FOR_HUMAN_CONFIRM)
        self.assertEqual(
            loaded.reviewed_package.reviewed_package_id,
            ready.reviewed_package.reviewed_package_id,
        )
        self.assertEqual(len(loaded.human_review_events), 1)
        self.assertEqual(
            loaded.human_review_events[0].review_event_id,
            ready.human_review_events[0].review_event_id,
        )

    def test_gap_b_conflicting_review_event_fail_closed_via_contract(self) -> None:
        """Same review_event_id + different payload fails via human_review_contracts."""
        state = _run_lifecycle(labor_status=LABOR_UNRESOLVED, run_id="run-conflict")
        wait1 = build_professional_review_wait_request(state, created_at=FIXED_AT)
        first = _review_event(
            state.package,
            decision=HumanReviewDecision.ADD,
            event_id="evt-conflict-x",
        )
        mid = apply_professional_human_review(
            state,
            ProfessionalHumanReviewResumeCommand(
                schema_version="1.0",
                interrupt_id=wait1.interrupt_id,
                run_id="run-conflict",
                review_events=(first,),
                answered_at=FIXED_AT,
            ),
            wait_request=wait1,
            now=FIXED_AT,
        )
        self.assertEqual(mid.status, STATUS_WAITING_FOR_HUMAN_REVIEW)
        self.assertEqual(len(mid.human_review_events), 1)
        self.assertEqual(mid.human_review_events[0].decision, HumanReviewDecision.ADD)

        wait2 = build_professional_review_wait_request(mid, created_at=FIXED_AT)
        conflicting = _review_event(
            mid.package,
            decision=HumanReviewDecision.REMOVE,
            event_id="evt-conflict-x",
        )
        with self.assertRaises(HumanReviewContractError) as raised:
            apply_professional_human_review(
                mid,
                ProfessionalHumanReviewResumeCommand(
                    schema_version="1.0",
                    interrupt_id=wait2.interrupt_id,
                    run_id="run-conflict",
                    review_events=(conflicting,),
                    answered_at=FIXED_AT,
                ),
                wait_request=wait2,
                now=FIXED_AT,
            )
        self.assertIn("conflicting replay", str(raised.exception).lower())

        # Identical payload replay remains idempotent on the same integration path.
        identical = _review_event(
            mid.package,
            decision=HumanReviewDecision.ADD,
            event_id="evt-conflict-x",
        )
        again = apply_professional_human_review(
            mid,
            ProfessionalHumanReviewResumeCommand(
                schema_version="1.0",
                interrupt_id=wait2.interrupt_id,
                run_id="run-conflict",
                review_events=(identical,),
                answered_at=FIXED_AT,
            ),
            wait_request=wait2,
            now=FIXED_AT,
        )
        self.assertEqual(len(again.human_review_events), 1)
        self.assertEqual(again.human_review_events[0].decision, HumanReviewDecision.ADD)

    def test_gap_b_graph_conflicting_review_fail_closed(self) -> None:
        """Graph resume path also fail-closes conflicting same event id."""
        run_id = "run-conflict-graph"
        app, ctx, _ = self._build_app(
            run_id=run_id,
            assembler=StubAssembler(labor_status=LABOR_UNRESOLVED),
            labor_evidence=(),
        )
        initial = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id=run_id,
            authorization_id=ctx.authorization_id,
            created_at=FIXED_AT,
        )
        config = {"configurable": {"thread_id": run_id}}
        out1 = app.invoke({"lifecycle": initial}, config)
        wait1 = out1["__interrupt__"][0].value
        pkg = out1["lifecycle"].package
        first = _review_event(pkg, decision=HumanReviewDecision.ADD, event_id="graph-x")
        ckpt1 = app.get_state(config).config["configurable"]["checkpoint_id"]
        out2 = app.invoke(
            Command(
                resume=ProfessionalHumanReviewResumeCommand(
                    schema_version="1.0",
                    interrupt_id=wait1.interrupt_id,
                    run_id=run_id,
                    review_events=(first,),
                    answered_at=FIXED_AT,
                    expected_checkpoint_id=ckpt1,
                )
            ),
            config,
        )
        self.assertEqual(out2["lifecycle"].status, STATUS_WAITING_FOR_HUMAN_REVIEW)
        wait2 = out2["__interrupt__"][0].value
        conflict = _review_event(
            out2["lifecycle"].package,
            decision=HumanReviewDecision.REMOVE,
            event_id="graph-x",
        )
        ckpt2 = app.get_state(config).config["configurable"]["checkpoint_id"]
        with self.assertRaises(HumanReviewContractError):
            app.invoke(
                Command(
                    resume=ProfessionalHumanReviewResumeCommand(
                        schema_version="1.0",
                        interrupt_id=wait2.interrupt_id,
                        run_id=run_id,
                        review_events=(conflict,),
                        answered_at=FIXED_AT,
                        expected_checkpoint_id=ckpt2,
                    )
                ),
                config,
            )

    def test_gap_c_generic_payload_into_professional_wait_fail_closed(self) -> None:
        """CLARIFY_SCOPE must not resume WAITING_FOR_HUMAN_REVIEW."""
        run_id = "run-cross-generic-into-review"
        app, ctx, _ = self._build_app(run_id=run_id)
        initial = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id=run_id,
            authorization_id=ctx.authorization_id,
            created_at=FIXED_AT,
        )
        config = {"configurable": {"thread_id": run_id}}
        out1 = app.invoke({"lifecycle": initial}, config)
        self.assertEqual(out1["lifecycle"].status, STATUS_WAITING_FOR_HUMAN_REVIEW)
        wait_req = out1["__interrupt__"][0].value
        ckpt = app.get_state(config).config["configurable"]["checkpoint_id"]
        generic = build_resume_command(
            decision_id="dec-cross-1",
            interrupt_id=wait_req.interrupt_id,
            run_id=run_id,
            mission_id=MISSION_ID,
            decision=DECISION_CLARIFY_SCOPE,
            actor_id="human-1",
            parameters={"facility_scope": [FACILITY]},
            expected_checkpoint_id=ckpt,
            submitted_at=FIXED_AT,
        )
        with self.assertRaises(HitlContractError) as raised:
            app.invoke(Command(resume=generic), config)
        self.assertEqual(raised.exception.code, CODE_HITL_CONTRACT_BLOCKER)
        held = app.get_state(config).values["lifecycle"]
        self.assertEqual(held.status, STATUS_WAITING_FOR_HUMAN_REVIEW)
        self.assertEqual(len(held.human_review_events), 0)

    def test_gap_c_professional_payload_into_generic_wait_fail_closed(self) -> None:
        """HumanReviewEvent payload must not resume AMBIGUOUS_SCOPE wait."""
        run_id = "run-cross-review-into-generic"
        app, ctx, _ = self._build_app(
            run_id=run_id,
            facility_scope=["ALL", FACILITY],
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
        interrupt_value = out1["__interrupt__"][0].value
        self.assertEqual(interrupt_value.reason_code, CODE_AMBIGUOUS_SCOPE)
        req = build_decision_request_from_lifecycle(out1["lifecycle"])
        ckpt = app.get_state(config).config["configurable"]["checkpoint_id"]
        # Build a professional review payload bound to the *generic* interrupt id
        # (worst-case shared infrastructure misuse). Still must fail closed.
        fake_package_id = "pkg-not-present"
        professional = ProfessionalHumanReviewResumeCommand(
            schema_version="1.0",
            interrupt_id=req.interrupt_id,
            run_id=run_id,
            review_events=(
                build_human_review_event(
                    review_event_id="cross-domain-1",
                    run_id=run_id,
                    mission_id=MISSION_ID,
                    package_id=fake_package_id,
                    candidate_id=CAND_A,
                    decision=HumanReviewDecision.ADD,
                    actor_id="operator-1",
                    reviewed_at=FIXED_AT,
                ),
            ),
            answered_at=FIXED_AT,
            expected_checkpoint_id=ckpt,
        )
        with self.assertRaises(HitlContractError) as raised:
            app.invoke(Command(resume=professional), config)
        self.assertEqual(raised.exception.code, CODE_HITL_CONTRACT_BLOCKER)
        held = app.get_state(config).values["lifecycle"]
        self.assertEqual(held.status, STATUS_WAITING_FOR_HUMAN)
        self.assertEqual(held.error_code, CODE_AMBIGUOUS_SCOPE)

    def test_21_22_no_streamlit_product_write(self) -> None:
        for path in (
            "agents/monthly_plan_constructor/professional_review_resume.py",
            "agents/monthly_plan_constructor/langgraph_runtime.py",
        ):
            source = Path(path).read_text(encoding="utf-8")
            self.assertNotIn("import streamlit", source)
            self.assertNotIn("from streamlit", source)
            self.assertNotIn("supabase", source.lower())


if __name__ == "__main__":
    unittest.main()
