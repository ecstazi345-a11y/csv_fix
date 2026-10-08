"""
RUNTIME-B — Professional Human Confirm Gate + Constructor completion.

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
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
)
from agents.monthly_plan_constructor.durable_checkpoint import (
    build_constructor_jsonplus_serializer,
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
from agents.monthly_plan_constructor.human_confirm_contracts import (
    HumanConfirmContractError,
    HumanConfirmDecision,
    build_human_confirm_event,
)
from agents.monthly_plan_constructor.human_review_contracts import (
    HumanReviewDecision,
    build_human_review_event,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_OBSERVED_PRODUCTIVITY,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    LaborNormEvidence,
    SOURCE_PROJECT_HISTORY,
)
from agents.monthly_plan_constructor.langgraph_runtime import (
    build_constructor_langgraph,
)
from agents.monthly_plan_constructor.lifecycle import (
    COMPLETION_STATUSES,
    STATUS_PROFESSIONAL_WORK_COMPLETED,
    STATUS_READY_FOR_HANDOFF,
    STATUS_REVIEWED_PACKAGE_READY,
    STATUS_WAITING_FOR_HUMAN,
    STATUS_WAITING_FOR_HUMAN_CONFIRM,
    STATUS_WAITING_FOR_HUMAN_REVIEW,
    CandidateAssemblyResult,
    LifecycleError,
    create_lifecycle_state,
    run_constructor_lifecycle,
)
from agents.monthly_plan_constructor.mission_scope import CODE_AMBIGUOUS_SCOPE
from agents.monthly_plan_constructor.professional_confirm_resume import (
    ProfessionalHumanConfirmResumeCommand,
    WAIT_KIND_HUMAN_CONFIRM,
    apply_professional_human_confirm,
    build_professional_confirm_wait_request,
    enter_waiting_for_human_confirm,
)
from agents.monthly_plan_constructor.professional_review_resume import (
    ProfessionalHumanReviewResumeCommand,
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
MISSION_ID = "mission-rtb-1"
RUN_ID = "run-rtb-1"
CAND_A = "CAND-A"
FIXED_AT = datetime(2026, 10, 8, 16, 0, 0, tzinfo=timezone.utc)


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
    def __init__(self, *, labor_status: str = LABOR_VALIDATED) -> None:
        self.labor_status = labor_status

    def __call__(self, reality_read, scope) -> CandidateAssemblyResult:
        return CandidateAssemblyResult(
            candidates=(
                {
                    "candidate_id": CAND_A,
                    "project_code": PROJECT,
                    "month_key": MONTH,
                    "facility": FACILITY,
                    "discipline": DISCIPLINE,
                    "system": "SYS-1",
                    "iwp": "IWP-1",
                    "queue": "",
                    "boq_code": "BOQ-001",
                    "boq_name": "Кабель",
                    "unit": "м",
                    "remaining_qty": 10.0,
                    "already_planned_qty": 0.0,
                    "available_to_add_qty": 10.0,
                    "availability_status": "AVAILABLE",
                    "labor_norm_status": self.labor_status,
                },
            ),
            scanned_count=1,
        )


class RecordingReader:
    def __call__(self, context, mission) -> list[dict[str, object]]:
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


def _run_to_review_wait(*, run_id: str = RUN_ID):
    return run_constructor_lifecycle(
        context=_ctx(run_id),
        project_code=PROJECT,
        month_key=MONTH,
        facility_scope=FACILITY,
        discipline_scope=DISCIPLINE,
        assemble_candidates=StubAssembler(),
        labor_evidence=(_validated_evidence(),),
        scope_reader=RecordingReader(),
        mission_id=MISSION_ID,
        run_id=run_id,
        now=FIXED_AT,
    )


def _to_reviewed_ready(state):
    wait = build_professional_review_wait_request(state, created_at=FIXED_AT)
    event = build_human_review_event(
        review_event_id="rev-rtb-1",
        run_id=state.run_id,
        mission_id=MISSION_ID,
        package_id=state.package.package_id,
        candidate_id=CAND_A,
        decision=HumanReviewDecision.ADD,
        actor_id="operator-1",
        reviewed_at=FIXED_AT,
    )
    return apply_professional_human_review(
        state,
        ProfessionalHumanReviewResumeCommand(
            schema_version="1.0",
            interrupt_id=wait.interrupt_id,
            run_id=state.run_id,
            review_events=(event,),
            answered_at=FIXED_AT,
        ),
        wait_request=wait,
        now=FIXED_AT,
    )


def _confirm_event(reviewed, *, event_id="cfm-1", **overrides):
    payload = dict(
        confirm_event_id=event_id,
        reviewed_package_id=reviewed.reviewed_package_id,
        source_candidate_package_id=reviewed.source_candidate_package_id,
        run_id=reviewed.run_id,
        mission_id=reviewed.mission_id,
        decision=HumanConfirmDecision.CONFIRM,
        actor_id="operator-1",
        confirmed_at=FIXED_AT,
    )
    payload.update(overrides)
    return build_human_confirm_event(**payload)


class RuntimeBLifecycleTests(unittest.TestCase):
    def test_01_reviewed_ready_reaches_confirm_wait(self) -> None:
        ready = _to_reviewed_ready(_run_to_review_wait())
        self.assertEqual(ready.status, STATUS_REVIEWED_PACKAGE_READY)
        waiting = enter_waiting_for_human_confirm(ready, now=FIXED_AT)
        self.assertEqual(waiting.status, STATUS_WAITING_FOR_HUMAN_CONFIRM)
        self.assertNotIn(STATUS_REVIEWED_PACKAGE_READY, COMPLETION_STATUSES)
        self.assertNotIn(STATUS_WAITING_FOR_HUMAN_CONFIRM, COMPLETION_STATUSES)

    def test_02_confirm_wait_binds_exact_identities(self) -> None:
        ready = _to_reviewed_ready(_run_to_review_wait(run_id="run-rtb-bind"))
        waiting = enter_waiting_for_human_confirm(ready, now=FIXED_AT)
        req = build_professional_confirm_wait_request(waiting, created_at=FIXED_AT)
        self.assertEqual(req.wait_kind, WAIT_KIND_HUMAN_CONFIRM)
        self.assertEqual(req.run_id, "run-rtb-bind")
        self.assertEqual(req.mission_id, MISSION_ID)
        self.assertEqual(req.reviewed_package_id, ready.reviewed_package.reviewed_package_id)
        self.assertEqual(
            req.source_candidate_package_id,
            ready.reviewed_package.source_candidate_package_id,
        )


class RuntimeBConfirmAuthorityTests(unittest.TestCase):
    def test_03_04_valid_confirm_reuses_contract(self) -> None:
        ready = _to_reviewed_ready(_run_to_review_wait(run_id="run-rtb-ok"))
        waiting = enter_waiting_for_human_confirm(ready, now=FIXED_AT)
        req = build_professional_confirm_wait_request(waiting, created_at=FIXED_AT)
        before_pkg = copy.deepcopy(waiting.reviewed_package)
        before_history = tuple(waiting.human_review_events)
        final = apply_professional_human_confirm(
            waiting,
            ProfessionalHumanConfirmResumeCommand(
                schema_version="1.0",
                interrupt_id=req.interrupt_id,
                run_id="run-rtb-ok",
                confirm_events=(_confirm_event(waiting.reviewed_package),),
                answered_at=FIXED_AT,
            ),
            wait_request=req,
            now=FIXED_AT,
        )
        self.assertEqual(final.status, STATUS_PROFESSIONAL_WORK_COMPLETED)
        self.assertIn(final.status, COMPLETION_STATUSES)
        self.assertEqual(final.reviewed_package, before_pkg)
        self.assertEqual(final.human_review_events, before_history)
        self.assertEqual(len(final.human_confirm_events), 1)

    def test_05_08_stale_binding_fail_closed(self) -> None:
        ready = _to_reviewed_ready(_run_to_review_wait(run_id="run-rtb-stale"))
        waiting = enter_waiting_for_human_confirm(ready, now=FIXED_AT)
        req = build_professional_confirm_wait_request(waiting, created_at=FIXED_AT)
        reviewed = waiting.reviewed_package
        cases = (
            {"reviewed_package_id": "other-reviewed"},
            {"source_candidate_package_id": "other-source"},
            {"run_id": "other-run"},
            {"mission_id": "other-mission"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(HumanConfirmContractError):
                    apply_professional_human_confirm(
                        waiting,
                        ProfessionalHumanConfirmResumeCommand(
                            schema_version="1.0",
                            interrupt_id=req.interrupt_id,
                            run_id="run-rtb-stale",
                            confirm_events=(
                                _confirm_event(reviewed, event_id="stale-x", **overrides),
                            ),
                            answered_at=FIXED_AT,
                        ),
                        wait_request=req,
                        now=FIXED_AT,
                    )

    def test_09_unresolved_cannot_confirm(self) -> None:
        state = run_constructor_lifecycle(
            context=_ctx("run-rtb-unres"),
            project_code=PROJECT,
            month_key=MONTH,
            facility_scope=FACILITY,
            discipline_scope=DISCIPLINE,
            assemble_candidates=StubAssembler(labor_status=LABOR_UNRESOLVED),
            labor_evidence=(),
            scope_reader=RecordingReader(),
            mission_id=MISSION_ID,
            run_id="run-rtb-unres",
            now=FIXED_AT,
        )
        wait = build_professional_review_wait_request(state, created_at=FIXED_AT)
        mid = apply_professional_human_review(
            state,
            ProfessionalHumanReviewResumeCommand(
                schema_version="1.0",
                interrupt_id=wait.interrupt_id,
                run_id="run-rtb-unres",
                review_events=(
                    build_human_review_event(
                        review_event_id="rev-unres",
                        run_id="run-rtb-unres",
                        mission_id=MISSION_ID,
                        package_id=state.package.package_id,
                        candidate_id=CAND_A,
                        decision=HumanReviewDecision.ADD,
                        actor_id="operator-1",
                        reviewed_at=FIXED_AT,
                    ),
                ),
                answered_at=FIXED_AT,
            ),
            wait_request=wait,
            now=FIXED_AT,
        )
        self.assertEqual(mid.status, STATUS_WAITING_FOR_HUMAN_REVIEW)
        self.assertGreater(mid.reviewed_package.unresolved_count, 0)
        with self.assertRaises(LifecycleError):
            enter_waiting_for_human_confirm(mid, now=FIXED_AT)

    def test_10_12_replay_conflict_second_confirm(self) -> None:
        ready = _to_reviewed_ready(_run_to_review_wait(run_id="run-rtb-replay"))
        waiting = enter_waiting_for_human_confirm(ready, now=FIXED_AT)
        req = build_professional_confirm_wait_request(waiting, created_at=FIXED_AT)
        first = _confirm_event(waiting.reviewed_package, event_id="cfm-same")
        # identical batch: idempotent
        once = apply_professional_human_confirm(
            waiting,
            ProfessionalHumanConfirmResumeCommand(
                schema_version="1.0",
                interrupt_id=req.interrupt_id,
                run_id="run-rtb-replay",
                confirm_events=(first, first),
                answered_at=FIXED_AT,
            ),
            wait_request=req,
            now=FIXED_AT,
        )
        self.assertEqual(once.status, STATUS_PROFESSIONAL_WORK_COMPLETED)
        self.assertEqual(len(once.human_confirm_events), 1)

        # conflicting same id (different actor) while still waiting — rebuild wait state
        waiting2 = enter_waiting_for_human_confirm(ready, now=FIXED_AT)
        req2 = build_professional_confirm_wait_request(waiting2, created_at=FIXED_AT)
        conflict = _confirm_event(
            waiting2.reviewed_package, event_id="cfm-same", actor_id="other-op"
        )
        with self.assertRaises(HumanConfirmContractError) as raised:
            apply_professional_human_confirm(
                waiting2,
                ProfessionalHumanConfirmResumeCommand(
                    schema_version="1.0",
                    interrupt_id=req2.interrupt_id,
                    run_id="run-rtb-replay",
                    confirm_events=(first, conflict),
                    answered_at=FIXED_AT,
                ),
                wait_request=req2,
                now=FIXED_AT,
            )
        self.assertIn("conflicting", str(raised.exception).lower())

        # second distinct confirm_event_id
        second = _confirm_event(waiting2.reviewed_package, event_id="cfm-other")
        with self.assertRaises(HumanConfirmContractError) as raised2:
            apply_professional_human_confirm(
                waiting2,
                ProfessionalHumanConfirmResumeCommand(
                    schema_version="1.0",
                    interrupt_id=req2.interrupt_id,
                    run_id="run-rtb-replay",
                    confirm_events=(first, second),
                    answered_at=FIXED_AT,
                ),
                wait_request=req2,
                now=FIXED_AT,
            )
        self.assertIn("only one distinct", str(raised2.exception).lower())


class RuntimeBGraphTests(unittest.TestCase):
    def _build_app(self, *, run_id=RUN_ID, facility_scope=FACILITY, recorder=None, handoff_store=None):
        ctx = _ctx(run_id)
        checkpointer = InMemorySaver(serde=build_constructor_jsonplus_serializer())
        app = build_constructor_langgraph(
            context=ctx,
            project_code=PROJECT,
            month_key=MONTH,
            facility_scope=facility_scope,
            discipline_scope=DISCIPLINE,
            assemble_candidates=StubAssembler(),
            labor_evidence=(_validated_evidence(),),
            scope_reader=RecordingReader(),
            now=FIXED_AT,
            checkpointer=checkpointer,
            recorder=recorder,
            handoff_store=handoff_store,
        )
        return app, ctx, checkpointer

    def _to_confirm_interrupt(self, app, ctx, run_id):
        initial = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id=run_id,
            authorization_id=ctx.authorization_id,
            created_at=FIXED_AT,
        )
        config = {"configurable": {"thread_id": run_id}}
        out1 = app.invoke({"lifecycle": initial}, config)
        self.assertEqual(out1["lifecycle"].status, STATUS_WAITING_FOR_HUMAN_REVIEW)
        wait_rev = out1["__interrupt__"][0].value
        pkg = out1["lifecycle"].package
        ckpt1 = app.get_state(config).config["configurable"]["checkpoint_id"]
        out2 = app.invoke(
            Command(
                resume=ProfessionalHumanReviewResumeCommand(
                    schema_version="1.0",
                    interrupt_id=wait_rev.interrupt_id,
                    run_id=run_id,
                    review_events=(
                        build_human_review_event(
                            review_event_id="rev-graph-1",
                            run_id=run_id,
                            mission_id=MISSION_ID,
                            package_id=pkg.package_id,
                            candidate_id=CAND_A,
                            decision=HumanReviewDecision.ADD,
                            actor_id="operator-1",
                            reviewed_at=FIXED_AT,
                        ),
                    ),
                    answered_at=FIXED_AT,
                    expected_checkpoint_id=ckpt1,
                )
            ),
            config,
        )
        self.assertEqual(out2["lifecycle"].status, STATUS_WAITING_FOR_HUMAN_CONFIRM)
        self.assertIn("__interrupt__", out2)
        self.assertEqual(out2["__interrupt__"][0].value.wait_kind, WAIT_KIND_HUMAN_CONFIRM)
        return out2, config

    def test_13_16_cross_domain_payload_separation(self) -> None:
        # A: generic into confirm wait
        run_a = "run-rtb-cross-a"
        app_a, ctx_a, _ = self._build_app(run_id=run_a)
        out_a, config_a = self._to_confirm_interrupt(app_a, ctx_a, run_a)
        wait_a = out_a["__interrupt__"][0].value
        ckpt_a = app_a.get_state(config_a).config["configurable"]["checkpoint_id"]
        generic = build_resume_command(
            decision_id="dec-cross-a",
            interrupt_id=wait_a.interrupt_id,
            run_id=run_a,
            mission_id=MISSION_ID,
            decision=DECISION_CLARIFY_SCOPE,
            actor_id="human-1",
            parameters={"facility_scope": [FACILITY]},
            expected_checkpoint_id=ckpt_a,
            submitted_at=FIXED_AT,
        )
        with self.assertRaises(HitlContractError) as ra:
            app_a.invoke(Command(resume=generic), config_a)
        self.assertEqual(ra.exception.code, CODE_HITL_CONTRACT_BLOCKER)

        # B: HumanReview into confirm wait
        review_payload = ProfessionalHumanReviewResumeCommand(
            schema_version="1.0",
            interrupt_id=wait_a.interrupt_id,
            run_id=run_a,
            review_events=(
                build_human_review_event(
                    review_event_id="bad-into-confirm",
                    run_id=run_a,
                    mission_id=MISSION_ID,
                    package_id=out_a["lifecycle"].package.package_id,
                    candidate_id=CAND_A,
                    decision=HumanReviewDecision.ADD,
                    actor_id="operator-1",
                    reviewed_at=FIXED_AT,
                ),
            ),
            answered_at=FIXED_AT,
            expected_checkpoint_id=ckpt_a,
        )
        with self.assertRaises(HitlContractError):
            app_a.invoke(Command(resume=review_payload), config_a)

        # C: Confirm into Review wait
        run_c = "run-rtb-cross-c"
        app_c, ctx_c, _ = self._build_app(run_id=run_c)
        initial = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id=run_c,
            authorization_id=ctx_c.authorization_id,
            created_at=FIXED_AT,
        )
        config_c = {"configurable": {"thread_id": run_c}}
        out_c = app_c.invoke({"lifecycle": initial}, config_c)
        self.assertEqual(out_c["lifecycle"].status, STATUS_WAITING_FOR_HUMAN_REVIEW)
        wait_c = out_c["__interrupt__"][0].value
        ckpt_c = app_c.get_state(config_c).config["configurable"]["checkpoint_id"]
        fake_confirm = ProfessionalHumanConfirmResumeCommand(
            schema_version="1.0",
            interrupt_id=wait_c.interrupt_id,
            run_id=run_c,
            confirm_events=(
                build_human_confirm_event(
                    confirm_event_id="into-review",
                    reviewed_package_id="pkg-x",
                    source_candidate_package_id="src-x",
                    run_id=run_c,
                    mission_id=MISSION_ID,
                    decision=HumanConfirmDecision.CONFIRM,
                    actor_id="operator-1",
                    confirmed_at=FIXED_AT,
                ),
            ),
            answered_at=FIXED_AT,
            expected_checkpoint_id=ckpt_c,
        )
        with self.assertRaises(HitlContractError):
            app_c.invoke(Command(resume=fake_confirm), config_c)

        # D: Confirm into generic scope wait
        run_d = "run-rtb-cross-d"
        app_d, ctx_d, _ = self._build_app(
            run_id=run_d, facility_scope=["ALL", FACILITY]
        )
        initial_d = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id=run_d,
            authorization_id=ctx_d.authorization_id,
            created_at=FIXED_AT,
        )
        config_d = {"configurable": {"thread_id": run_d}}
        out_d = app_d.invoke({"lifecycle": initial_d}, config_d)
        self.assertEqual(out_d["lifecycle"].status, STATUS_WAITING_FOR_HUMAN)
        self.assertEqual(out_d["__interrupt__"][0].value.reason_code, CODE_AMBIGUOUS_SCOPE)
        req_d = build_decision_request_from_lifecycle(out_d["lifecycle"])
        ckpt_d = app_d.get_state(config_d).config["configurable"]["checkpoint_id"]
        with self.assertRaises(HitlContractError):
            app_d.invoke(
                Command(
                    resume=ProfessionalHumanConfirmResumeCommand(
                        schema_version="1.0",
                        interrupt_id=req_d.interrupt_id,
                        run_id=run_d,
                        confirm_events=(
                            build_human_confirm_event(
                                confirm_event_id="into-scope",
                                reviewed_package_id="pkg-y",
                                source_candidate_package_id="src-y",
                                run_id=run_d,
                                mission_id=MISSION_ID,
                                decision=HumanConfirmDecision.CONFIRM,
                                actor_id="operator-1",
                                confirmed_at=FIXED_AT,
                            ),
                        ),
                        answered_at=FIXED_AT,
                        expected_checkpoint_id=ckpt_d,
                    )
                ),
                config_d,
            )

    def test_17_20_stale_confirm_after_restored_wait_fail_closed(self) -> None:
        """Stale binding after confirm-wait checkpoint restore → FAIL CLOSED."""
        run_id = "run-rtb-ckpt-stale"
        app, ctx, _ = self._build_app(run_id=run_id)
        out_wait, config = self._to_confirm_interrupt(app, ctx, run_id)
        restored_wait = app.get_state(config).values["lifecycle"]
        self.assertEqual(restored_wait.status, STATUS_WAITING_FOR_HUMAN_CONFIRM)
        wait_req = out_wait["__interrupt__"][0].value
        self.assertEqual(
            wait_req.reviewed_package_id,
            restored_wait.reviewed_package.reviewed_package_id,
        )
        stale = _confirm_event(
            restored_wait.reviewed_package,
            event_id="stale-after-restore",
            reviewed_package_id="wrong-reviewed",
        )
        ckpt = app.get_state(config).config["configurable"]["checkpoint_id"]
        with self.assertRaises(HumanConfirmContractError):
            app.invoke(
                Command(
                    resume=ProfessionalHumanConfirmResumeCommand(
                        schema_version="1.0",
                        interrupt_id=wait_req.interrupt_id,
                        run_id=run_id,
                        confirm_events=(stale,),
                        answered_at=FIXED_AT,
                        expected_checkpoint_id=ckpt,
                    )
                ),
                config,
            )
        still = app.get_state(config).values["lifecycle"]
        self.assertEqual(still.status, STATUS_WAITING_FOR_HUMAN_CONFIRM)

    def test_17_22_confirm_wait_and_completed_checkpoint(self) -> None:
        run_id = "run-rtb-ckpt"
        recorder = InMemoryObservabilityRecorder()
        handoff_calls: list[object] = []

        class TrackingHandoffStore:
            def get(self, handoff_id: str):
                return None

            def put_if_absent(self, handoff):
                handoff_calls.append(handoff)
                raise AssertionError("professional path must not persist handoff")

        app, ctx, _ = self._build_app(
            run_id=run_id, recorder=recorder, handoff_store=TrackingHandoffStore()
        )
        out_wait, config = self._to_confirm_interrupt(app, ctx, run_id)
        restored_wait = app.get_state(config).values["lifecycle"]
        self.assertEqual(restored_wait.status, STATUS_WAITING_FOR_HUMAN_CONFIRM)
        self.assertEqual(
            restored_wait.reviewed_package.reviewed_package_id,
            out_wait["lifecycle"].reviewed_package.reviewed_package_id,
        )
        wait_req = out_wait["__interrupt__"][0].value
        self.assertEqual(
            wait_req.reviewed_package_id,
            restored_wait.reviewed_package.reviewed_package_id,
        )

        # valid confirm after restore (fresh thread — no prior failed resume)
        ckpt = app.get_state(config).config["configurable"]["checkpoint_id"]
        valid = _confirm_event(restored_wait.reviewed_package, event_id="cfm-restore")
        out_done = app.invoke(
            Command(
                resume=ProfessionalHumanConfirmResumeCommand(
                    schema_version="1.0",
                    interrupt_id=wait_req.interrupt_id,
                    run_id=run_id,
                    confirm_events=(valid,),
                    answered_at=FIXED_AT,
                    expected_checkpoint_id=ckpt,
                )
            ),
            config,
        )
        done = out_done["lifecycle"]
        self.assertEqual(done.status, STATUS_PROFESSIONAL_WORK_COMPLETED)
        restored_done = app.get_state(config).values["lifecycle"]
        self.assertEqual(restored_done.status, STATUS_PROFESSIONAL_WORK_COMPLETED)
        self.assertEqual(
            restored_done.human_confirm_events[0].confirm_event_id,
            "cfm-restore",
        )
        self.assertEqual(
            restored_done.reviewed_package.reviewed_package_id,
            done.reviewed_package.reviewed_package_id,
        )
        self.assertEqual(
            list(restored_done.human_review_events),
            list(done.human_review_events),
        )
        serde = build_constructor_jsonplus_serializer()
        tag, payload = serde.dumps_typed(done)
        loaded = serde.loads_typed((tag, payload))
        self.assertEqual(loaded.status, STATUS_PROFESSIONAL_WORK_COMPLETED)
        self.assertEqual(loaded.human_confirm_events[0].confirm_event_id, "cfm-restore")

        types = {e.event_type for e in recorder.events_for_run(run_id)}
        completed = [
            e
            for e in recorder.events_for_run(run_id)
            if e.event_type == EventType.RUN_COMPLETED
        ]
        self.assertEqual(len(completed), 1)
        self.assertIsNone(completed[0].handoff_id)
        self.assertEqual(
            completed[0].to_dict()["detail"].get("completion_source"),
            "HUMAN_CONFIRM",
        )
        self.assertEqual(completed[0].stage_id, "RUN_COMPLETION")
        self.assertNotIn(EventType.HANDOFF_PERSISTED, types)
        self.assertEqual(handoff_calls, [])
        self.assertNotEqual(done.status, STATUS_READY_FOR_HANDOFF)

    def test_31_legacy_handoff_path_still_works(self) -> None:
        """Legacy READY_FOR_HANDOFF → persist still reachable via fixture status."""
        from agents.monthly_plan_constructor.handoff_contracts import (
            DEFAULT_SECURITY_POLICY_VERSION,
            build_constructor_handoff,
        )
        from agents.monthly_plan_constructor.handoff_store import (
            STATUS_CREATED,
            HandoffStorePutResult,
            persist_constructor_handoff,
        )

        class MemStore:
            def __init__(self) -> None:
                self.items = {}

            def get(self, handoff_id: str):
                return self.items.get(handoff_id)

            def put_if_absent(self, handoff):
                existing = self.items.get(handoff.handoff_id)
                if existing is None:
                    self.items[handoff.handoff_id] = handoff
                    return HandoffStorePutResult(created=True, stored_handoff=handoff)
                return HandoffStorePutResult(created=False, stored_handoff=existing)

        ready = _to_reviewed_ready(_run_to_review_wait(run_id="run-rtb-legacy"))
        # Force legacy completion status for handoff builder (compatibility fixture).
        from dataclasses import replace

        legacy = replace(ready, status=STATUS_READY_FOR_HANDOFF)
        artifact = build_constructor_handoff(
            legacy,
            security_policy_version=DEFAULT_SECURITY_POLICY_VERSION,
            created_at=FIXED_AT,
        )
        store = MemStore()
        result = persist_constructor_handoff(store=store, handoff=artifact)
        self.assertEqual(result.status, STATUS_CREATED)
        self.assertEqual(len(store.items), 1)

    def test_34_35_no_streamlit_no_auto_confirm(self) -> None:
        for path in (
            "agents/monthly_plan_constructor/professional_confirm_resume.py",
            "agents/monthly_plan_constructor/langgraph_runtime.py",
        ):
            source = Path(path).read_text(encoding="utf-8")
            self.assertNotIn("import streamlit", source)
            self.assertNotIn("from streamlit", source)
        # Without resume, graph stops at confirm wait — never auto-completes.
        run_id = "run-rtb-no-auto"
        app, ctx, _ = self._build_app(run_id=run_id)
        out, _ = self._to_confirm_interrupt(app, ctx, run_id)
        self.assertEqual(out["lifecycle"].status, STATUS_WAITING_FOR_HUMAN_CONFIRM)
        self.assertNotEqual(
            out["lifecycle"].status, STATUS_PROFESSIONAL_WORK_COMPLETED
        )


if __name__ == "__main__":
    unittest.main()
