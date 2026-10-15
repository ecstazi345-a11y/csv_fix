"""Human Review Command Port V1 — validation, append-only, checkpoint binding."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from agents.human_surface.human_review_command import (
    HumanReviewAction,
    HumanReviewCommand,
    HumanReviewCommandError,
    prepare_human_review_surface,
    submit_human_review_decision,
)
from agents.monthly_plan_constructor.candidate_package import (
    LABOR_VALIDATED,
    PackageExceptionSummary,
    build_candidate_package,
)
from agents.monthly_plan_constructor.exception_engine import (
    SCHEMA_VERSION as EXC_SCHEMA,
    ConstructorExceptionSet,
)
from agents.monthly_plan_constructor.human_review_contracts import (
    HumanReviewDecision,
    build_human_review_event,
    normalize_human_review_events,
    project_effective_human_review_events,
)
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_WAITING_FOR_HUMAN_REVIEW,
    ConstructorLifecycleState,
    LifecycleTransition,
    create_lifecycle_state,
)
from agents.monthly_plan_constructor.mission_scope import build_constructor_mission_scope
from agents.monthly_plan_constructor.professional_review_resume import (
    ProfessionalHumanReviewResumeCommand,
)

FIXED_AT = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)
RUN_ID = "run-hr-cmd-001"
MISSION_ID = "mission-hr-cmd-001"
CAND_A = "cand-a"
CAND_B = "cand-b"
PROJECT = "PRJ_001_БХК"
MONTH = "октябрь-2026"
FACILITY = "16160-13"
DISCIPLINE = "Вентиляция"


def _mission():
    return build_constructor_mission_scope(
        project_code=PROJECT,
        month_key=MONTH,
        facility_scope=FACILITY,
        discipline_scope=DISCIPLINE,
    )


def _candidate(candidate_id: str, *, available: float = 80.0) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "project_code": PROJECT,
        "month_key": MONTH,
        "facility": FACILITY,
        "discipline": DISCIPLINE,
        "system": "SYS-1",
        "iwp": "IWP-1",
        "queue": "",
        "boq_code": f"BOQ-{candidate_id}",
        "boq_name": f"Work {candidate_id}",
        "unit": "м",
        "remaining_qty": 100.0,
        "already_planned_qty": 20.0,
        "available_to_add_qty": available,
        "availability_status": "AVAILABLE",
        "labor_norm_status": LABOR_VALIDATED,
    }


def _package():
    items = [_candidate(CAND_A), _candidate(CAND_B, available=50.0)]
    return build_candidate_package(
        _mission(),
        items,
        mission_id=MISSION_ID,
        scanned_count=len(items),
        run_id=RUN_ID,
        snapshot_id="snap-hr-cmd-1",
        created_at=FIXED_AT.isoformat(),
        exception_summary=PackageExceptionSummary(
            blocking_count=0,
            non_blocking_count=0,
            warning_count=0,
        ),
    )


def _lifecycle() -> ConstructorLifecycleState:
    package = _package()
    state = create_lifecycle_state(
        mission_id=MISSION_ID,
        run_id=RUN_ID,
        authorization_id="auth-hr-1",
        created_at=FIXED_AT,
    )
    exc_set = ConstructorExceptionSet(
        schema_version=EXC_SCHEMA,
        exceptions=(),
        summary=package.exception_summary,
        package_id=package.package_id,
    )
    # Minimal WAITING surface for Command Port tests (no full lifecycle transition path).
    return replace(
        state,
        status=STATUS_WAITING_FOR_HUMAN_REVIEW,
        scope=package.scope,
        package=package,
        exceptions=exc_set,
        transitions=(
            LifecycleTransition(
                from_status="LABOR_RESOLVED",
                to_status=STATUS_WAITING_FOR_HUMAN_REVIEW,
                at=FIXED_AT,
                trigger_code="HUMAN_REVIEW",
                source_capability="LIFECYCLE",
                note="awaiting",
            ),
        ),
        updated_at=FIXED_AT,
        error_code="HUMAN_REVIEW",
        terminal_reason="awaiting professional Human Review",
    )


class _FakeRuntime:
    """Injectable runtime: append-only event merge without LangGraph/lifecycle invariants."""

    def __init__(self, lifecycle: ConstructorLifecycleState) -> None:
        self.lifecycle = lifecycle
        self.checkpoint_id = "ckpt-1"
        self.resume_calls = 0

    def load_lifecycle(self, run_id: str) -> ConstructorLifecycleState:
        if run_id != self.lifecycle.run_id:
            raise HumanReviewCommandError("run not found")
        return self.lifecycle

    def current_checkpoint_id(self, run_id: str) -> str:
        return self.checkpoint_id

    def resume_professional_review(
        self,
        *,
        run_id: str,
        resume_command: ProfessionalHumanReviewResumeCommand,
    ) -> ConstructorLifecycleState:
        self.resume_calls += 1
        if self.lifecycle.package is None:
            raise HumanReviewCommandError("package missing")
        history = normalize_human_review_events(
            tuple(self.lifecycle.human_review_events or ())
            + tuple(resume_command.review_events),
            self.lifecycle.package,
        )
        self.lifecycle = replace(
            self.lifecycle,
            human_review_events=history,
            updated_at=FIXED_AT,
        )
        self.checkpoint_id = f"ckpt-{self.resume_calls + 1}"
        return self.lifecycle


class HumanReviewCommandPortTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = _FakeRuntime(_lifecycle())
        self.package_id = self.runtime.lifecycle.package.package_id

    def _cmd(self, **overrides) -> HumanReviewCommand:
        payload = {
            "run_id": RUN_ID,
            "package_id": self.package_id,
            "candidate_id": CAND_A,
            "action": HumanReviewAction.ACCEPT,
            "expected_checkpoint_id": self.runtime.checkpoint_id,
            "approved_qty": None,
            "reason_text": None,
        }
        payload.update(overrides)
        return HumanReviewCommand(**payload)

    def test_01_add_valid_succeeds(self) -> None:
        result = submit_human_review_decision(self._cmd(), runtime=self.runtime, now=FIXED_AT)
        self.assertEqual(result.decision, HumanReviewDecision.ADD)
        self.assertEqual(self.runtime.resume_calls, 1)

    def test_02_add_stores_proposed_and_approved_qty(self) -> None:
        result = submit_human_review_decision(self._cmd(), runtime=self.runtime, now=FIXED_AT)
        self.assertEqual(result.constructor_proposed_qty, 80.0)
        self.assertEqual(result.human_approved_qty, 80.0)
        event = self.runtime.lifecycle.human_review_events[0]
        self.assertEqual(event.constructor_proposed_qty, 80.0)
        self.assertEqual(event.human_approved_qty, 80.0)

    def test_03_remove_without_reason_fails(self) -> None:
        with self.assertRaises(HumanReviewCommandError):
            submit_human_review_decision(
                self._cmd(action=HumanReviewAction.EXCLUDE, reason_text=None),
                runtime=self.runtime,
                now=FIXED_AT,
            )
        self.assertEqual(self.runtime.resume_calls, 0)

    def test_04_remove_with_reason_succeeds(self) -> None:
        result = submit_human_review_decision(
            self._cmd(action=HumanReviewAction.EXCLUDE, reason_text="не нужно в октябре"),
            runtime=self.runtime,
            now=FIXED_AT,
        )
        self.assertEqual(result.decision, HumanReviewDecision.REMOVE)
        self.assertEqual(result.human_approved_qty, 0.0)
        self.assertEqual(result.reason_text, "не нужно в октябре")

    def test_05_change_qty_within_proposed_succeeds(self) -> None:
        result = submit_human_review_decision(
            self._cmd(
                action=HumanReviewAction.CHANGE_QUANTITY,
                approved_qty=50.0,
                reason_text="до конца месяца только 50",
            ),
            runtime=self.runtime,
            now=FIXED_AT,
        )
        self.assertEqual(result.decision, HumanReviewDecision.ADD)
        self.assertEqual(result.human_approved_qty, 50.0)
        self.assertEqual(result.constructor_proposed_qty, 80.0)

    def test_06_change_qty_above_proposed_fails(self) -> None:
        with self.assertRaises(HumanReviewCommandError):
            submit_human_review_decision(
                self._cmd(
                    action=HumanReviewAction.CHANGE_QUANTITY,
                    approved_qty=90.0,
                    reason_text="too much",
                ),
                runtime=self.runtime,
                now=FIXED_AT,
            )

    def test_07_change_qty_zero_or_negative_fails(self) -> None:
        with self.assertRaises(HumanReviewCommandError):
            submit_human_review_decision(
                self._cmd(
                    action=HumanReviewAction.CHANGE_QUANTITY,
                    approved_qty=0.0,
                    reason_text="zero",
                ),
                runtime=self.runtime,
                now=FIXED_AT,
            )

    def test_08_change_qty_without_reason_fails(self) -> None:
        with self.assertRaises(HumanReviewCommandError):
            submit_human_review_decision(
                self._cmd(action=HumanReviewAction.CHANGE_QUANTITY, approved_qty=50.0),
                runtime=self.runtime,
                now=FIXED_AT,
            )

    def test_09_clarification_without_reason_fails(self) -> None:
        with self.assertRaises(HumanReviewCommandError):
            submit_human_review_decision(
                self._cmd(action=HumanReviewAction.NEEDS_DATA),
                runtime=self.runtime,
                now=FIXED_AT,
            )

    def test_10_clarification_with_reason_succeeds(self) -> None:
        result = submit_human_review_decision(
            self._cmd(action=HumanReviewAction.NEEDS_DATA, reason_text="нужна норма"),
            runtime=self.runtime,
            now=FIXED_AT,
        )
        self.assertEqual(result.decision, HumanReviewDecision.REQUIRES_CLARIFICATION)
        self.assertIsNone(result.human_approved_qty)

    def test_11_unknown_candidate_fails(self) -> None:
        with self.assertRaises(HumanReviewCommandError):
            submit_human_review_decision(
                self._cmd(candidate_id="missing"),
                runtime=self.runtime,
                now=FIXED_AT,
            )

    def test_12_package_mismatch_fails(self) -> None:
        with self.assertRaises(HumanReviewCommandError):
            submit_human_review_decision(
                self._cmd(package_id="other-pkg"),
                runtime=self.runtime,
                now=FIXED_AT,
            )

    def test_13_wrong_state_fails(self) -> None:
        self.runtime.lifecycle = replace(self.runtime.lifecycle, status="RUNNING")
        with self.assertRaises(HumanReviewCommandError):
            submit_human_review_decision(self._cmd(), runtime=self.runtime, now=FIXED_AT)

    def test_14_stale_checkpoint_fails(self) -> None:
        with self.assertRaises(HumanReviewCommandError):
            submit_human_review_decision(
                self._cmd(expected_checkpoint_id="stale"),
                runtime=self.runtime,
                now=FIXED_AT,
            )
        self.assertEqual(self.runtime.resume_calls, 0)

    def test_15_ui_approved_qty_ignored_on_accept(self) -> None:
        result = submit_human_review_decision(
            self._cmd(approved_qty=999.0),
            runtime=self.runtime,
            now=FIXED_AT,
        )
        self.assertEqual(result.human_approved_qty, 80.0)

    def test_16_17_18_append_only_latest_wins(self) -> None:
        submit_human_review_decision(self._cmd(), runtime=self.runtime, now=FIXED_AT)
        first_id = self.runtime.lifecycle.human_review_events[0].review_event_id
        submit_human_review_decision(
            self._cmd(
                action=HumanReviewAction.EXCLUDE,
                reason_text="передумал",
                expected_checkpoint_id=self.runtime.checkpoint_id,
            ),
            runtime=self.runtime,
            now=FIXED_AT,
        )
        events = self.runtime.lifecycle.human_review_events
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].review_event_id, first_id)
        self.assertEqual(events[0].decision, HumanReviewDecision.ADD)
        effective = project_effective_human_review_events(
            events, self.runtime.lifecycle.package
        )
        self.assertEqual(effective[CAND_A].decision, HumanReviewDecision.REMOVE)
        self.assertEqual(effective[CAND_A].reason_text, "передумал")

    def test_19_historical_event_without_qty_fields_readable(self) -> None:
        legacy = build_human_review_event(
            review_event_id="legacy-1",
            run_id=RUN_ID,
            mission_id=MISSION_ID,
            package_id=self.package_id,
            candidate_id=CAND_A,
            decision=HumanReviewDecision.ADD,
            actor_id="operator",
            reviewed_at=FIXED_AT,
        )
        self.assertIsNone(legacy.constructor_proposed_qty)
        self.assertIsNone(legacy.human_approved_qty)
        self.assertIsNone(legacy.reason_text)

    def test_24_review_progress_from_durable_truth(self) -> None:
        submit_human_review_decision(self._cmd(), runtime=self.runtime, now=FIXED_AT)
        surface = prepare_human_review_surface(RUN_ID, runtime=self.runtime)
        self.assertEqual(surface.reviewed_count, 1)
        self.assertEqual(surface.not_reviewed_count, 1)
        self.assertEqual(surface.accepted_count, 1)


class HumanReviewPageWiringTests(unittest.TestCase):
    def test_20_21_page_uses_command_port_no_direct_db(self) -> None:
        page = (
            Path(__file__).resolve().parents[1]
            / "pages"
            / "53_AI_Центр_управления_агентами.py"
        )
        text = page.read_text(encoding="utf-8")
        self.assertIn("submit_human_review_decision", text)
        self.assertIn("prepare_human_review_surface", text)
        self.assertIn("ПОДТВЕРДИТЬ РЕШЕНИЕ", text)
        self.assertIn("HumanReviewCommand", text)
        self.assertNotIn("supabase.table(", text)
        self.assertNotIn("SqliteObservabilityStore(", text)

    def test_22_row_preview_required(self) -> None:
        page = (
            Path(__file__).resolve().parents[1]
            / "pages"
            / "53_AI_Центр_управления_агентами.py"
        )
        text = page.read_text(encoding="utf-8")
        self.assertIn("Предпросмотр решения", text)
        self.assertIn("ПОДТВЕРДИТЬ РЕШЕНИЕ", text)
        # Action buttons only set draft; write happens on confirm.
        self.assertIn("dynamis_hr_draft_", text)

    def test_25_28_protected_ux_unchanged(self) -> None:
        result_view = (
            Path(__file__).resolve().parents[1]
            / "agents"
            / "human_surface"
            / "result_view.py"
        )
        rv = result_view.read_text(encoding="utf-8")
        self.assertIn("План > текущего остатка", rv)
        self.assertIn("module5_filter_options", rv)
        page = (
            Path(__file__).resolve().parents[1]
            / "pages"
            / "53_AI_Центр_управления_агентами.py"
        )
        text = page.read_text(encoding="utf-8")
        self.assertIn("Быстрая команда", text)
        self.assertIn('st.session_state["dynamis_global_text"] = ""', text)


if __name__ == "__main__":
    unittest.main()
