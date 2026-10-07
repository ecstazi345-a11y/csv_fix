"""
Constructor Human Review Contract V1 — pure contract tests.

No runtime wiring. No persistence. No UI. No LLM. No product writes.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from copy import deepcopy

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
    build_candidate_package,
)
from agents.monthly_plan_constructor.human_review_contracts import (
    ACTOR_TYPE_HUMAN,
    CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
    HumanReviewContractError,
    HumanReviewDecision,
    assert_no_final_inclusion_semantics,
    build_human_review_event,
    human_review_event_as_dict,
    normalize_human_review_events,
    project_effective_human_review_decisions,
    validate_human_review_event_against_package,
)
from agents.monthly_plan_constructor.mission_scope import (
    build_constructor_mission_scope,
)
from agents.monthly_plan_constructor.recommendation import (
    HUMAN_REVIEW_REQUIRED,
    REASON_AVAILABLE_TO_ADD,
    REASON_LABOR_VALIDATED,
    RECOMMEND_ADD,
)

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY = "16160-17"
DISCIPLINE = "Автоматизация"
MISSION_ID = "mission-hr-1"
RUN_ID = "run-hr-1"
CAND_A = "CAND-A"
CAND_B = "CAND-B"
STAMP = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)


def _mission():
    return build_constructor_mission_scope(project_code=PROJECT, month_key=MONTH)


def _candidate(
    candidate_id: str = CAND_A,
    *,
    labor_norm_status: str = LABOR_UNRESOLVED,
    recommendation: str | None = None,
    recommendation_reason_codes: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "project_code": PROJECT,
        "month_key": MONTH,
        "facility": FACILITY,
        "discipline": DISCIPLINE,
        "system": "SYS-1",
        "iwp": "IWP-1",
        "queue": "",
        "boq_code": "BOQ-001" if candidate_id == CAND_A else "BOQ-002",
        "boq_name": "Кабель",
        "unit": "м",
        "remaining_qty": 90.0,
        "already_planned_qty": 0.0,
        "available_to_add_qty": 90.0,
        "availability_status": "AVAILABLE",
        "labor_norm_status": labor_norm_status,
        "recommendation": recommendation,
        "recommendation_reason_codes": list(recommendation_reason_codes),
    }


def _package(*, candidates: list[dict[str, object]] | None = None):
    items = candidates if candidates is not None else [_candidate()]
    return build_candidate_package(
        _mission(),
        items,
        mission_id=MISSION_ID,
        scanned_count=len(items),
        run_id=RUN_ID,
        snapshot_id="snap-hr-1",
    )


def _event(
    *,
    review_event_id: str = "evt-1",
    candidate_id: str = CAND_A,
    decision: object = HumanReviewDecision.ADD,
    run_id: str = RUN_ID,
    mission_id: str = MISSION_ID,
    package_id: str | None = None,
    actor_id: str = "operator-1",
    reviewed_at: datetime = STAMP,
    package=None,
):
    pkg = package or _package()
    return build_human_review_event(
        review_event_id=review_event_id,
        run_id=run_id,
        mission_id=mission_id,
        package_id=package_id or pkg.package_id,
        candidate_id=candidate_id,
        decision=decision,
        actor_id=actor_id,
        reviewed_at=reviewed_at,
    )


class HumanReviewContractTests(unittest.TestCase):
    def test_01_add_accepted_for_known_candidate(self) -> None:
        package = _package()
        event = _event(package=package, decision=HumanReviewDecision.ADD)
        validated = validate_human_review_event_against_package(event, package)
        self.assertEqual(validated.decision, HumanReviewDecision.ADD)
        self.assertEqual(validated.candidate_id, CAND_A)

    def test_02_remove_accepted(self) -> None:
        package = _package()
        event = _event(package=package, decision=HumanReviewDecision.REMOVE)
        self.assertEqual(
            validate_human_review_event_against_package(event, package).decision,
            HumanReviewDecision.REMOVE,
        )

    def test_03_requires_clarification_accepted(self) -> None:
        package = _package()
        event = _event(
            package=package,
            decision=HumanReviewDecision.REQUIRES_CLARIFICATION,
        )
        self.assertEqual(
            validate_human_review_event_against_package(event, package).decision,
            HumanReviewDecision.REQUIRES_CLARIFICATION,
        )

    def test_04_recommend_add_plus_human_remove_allowed(self) -> None:
        package = _package(
            candidates=[
                _candidate(
                    recommendation=RECOMMEND_ADD,
                    recommendation_reason_codes=(
                        REASON_AVAILABLE_TO_ADD,
                        REASON_LABOR_VALIDATED,
                    ),
                    labor_norm_status=LABOR_VALIDATED,
                )
            ]
        )
        before = package.candidates[0]
        event = _event(package=package, decision=HumanReviewDecision.REMOVE)
        validate_human_review_event_against_package(event, package)
        after = package.candidates[0]
        self.assertEqual(before.recommendation, RECOMMEND_ADD)
        self.assertEqual(after.recommendation, RECOMMEND_ADD)
        self.assertEqual(after.recommendation_reason_codes, before.recommendation_reason_codes)

    def test_05_human_review_required_plus_human_add_intent_allowed(self) -> None:
        package = _package(
            candidates=[
                _candidate(
                    recommendation=HUMAN_REVIEW_REQUIRED,
                    labor_norm_status=LABOR_UNRESOLVED,
                )
            ]
        )
        event = _event(package=package, decision=HumanReviewDecision.ADD)
        validate_human_review_event_against_package(event, package)
        self.assertEqual(package.candidates[0].recommendation, HUMAN_REVIEW_REQUIRED)
        self.assertEqual(package.candidates[0].labor_norm_status, LABOR_UNRESOLVED)

    def test_06_unresolved_plus_add_does_not_mutate_labor(self) -> None:
        package = _package(
            candidates=[_candidate(labor_norm_status=LABOR_UNRESOLVED)]
        )
        event = _event(package=package, decision=HumanReviewDecision.ADD)
        validate_human_review_event_against_package(event, package)
        self.assertEqual(package.candidates[0].labor_norm_status, LABOR_UNRESOLVED)

    def test_07_unresolved_plus_add_is_intent_only_no_final_flags(self) -> None:
        package = _package()
        event = _event(package=package, decision=HumanReviewDecision.ADD)
        assert_no_final_inclusion_semantics(event)
        payload = human_review_event_as_dict(event)
        for forbidden in (
            "included",
            "approved",
            "final",
            "handoff_ready",
            "labor_resolved",
            "authority_granted",
        ):
            self.assertNotIn(forbidden, payload)

    def test_08_candidate_recommendation_unchanged(self) -> None:
        package = _package(
            candidates=[
                _candidate(
                    recommendation=RECOMMEND_ADD,
                    recommendation_reason_codes=(REASON_AVAILABLE_TO_ADD,),
                    labor_norm_status=LABOR_VALIDATED,
                )
            ]
        )
        snapshot = deepcopy(
            {
                "recommendation": package.candidates[0].recommendation,
                "reasons": package.candidates[0].recommendation_reason_codes,
            }
        )
        normalize_human_review_events(
            (_event(package=package, decision=HumanReviewDecision.REQUIRES_CLARIFICATION),),
            package,
        )
        self.assertEqual(package.candidates[0].recommendation, snapshot["recommendation"])
        self.assertEqual(package.candidates[0].recommendation_reason_codes, snapshot["reasons"])

    def test_09_unknown_candidate_fail_closed(self) -> None:
        package = _package()
        event = _event(package=package, candidate_id="UNKNOWN")
        with self.assertRaises(HumanReviewContractError) as raised:
            validate_human_review_event_against_package(event, package)
        self.assertEqual(raised.exception.code, CODE_HUMAN_REVIEW_CONTRACT_BLOCKER)

    def test_10_wrong_package_id_fail_closed(self) -> None:
        package = _package()
        event = _event(package=package, package_id="other-package")
        with self.assertRaises(HumanReviewContractError) as raised:
            validate_human_review_event_against_package(event, package)
        self.assertEqual(raised.exception.code, CODE_HUMAN_REVIEW_CONTRACT_BLOCKER)

    def test_11_wrong_run_id_fail_closed(self) -> None:
        package = _package()
        event = _event(package=package, run_id="other-run")
        with self.assertRaises(HumanReviewContractError) as raised:
            validate_human_review_event_against_package(event, package)
        self.assertEqual(raised.exception.code, CODE_HUMAN_REVIEW_CONTRACT_BLOCKER)

    def test_12_wrong_mission_id_fail_closed(self) -> None:
        package = _package()
        event = _event(package=package, mission_id="other-mission")
        with self.assertRaises(HumanReviewContractError) as raised:
            validate_human_review_event_against_package(event, package)
        self.assertEqual(raised.exception.code, CODE_HUMAN_REVIEW_CONTRACT_BLOCKER)

    def test_13_blank_actor_id_fail_closed(self) -> None:
        package = _package()
        with self.assertRaises(HumanReviewContractError) as raised:
            build_human_review_event(
                review_event_id="evt-blank-actor",
                run_id=RUN_ID,
                mission_id=MISSION_ID,
                package_id=package.package_id,
                candidate_id=CAND_A,
                decision=HumanReviewDecision.ADD,
                actor_id="  ",
                reviewed_at=STAMP,
            )
        self.assertEqual(raised.exception.code, CODE_HUMAN_REVIEW_CONTRACT_BLOCKER)

    def test_14_blank_review_event_id_fail_closed(self) -> None:
        package = _package()
        with self.assertRaises(HumanReviewContractError) as raised:
            build_human_review_event(
                review_event_id="",
                run_id=RUN_ID,
                mission_id=MISSION_ID,
                package_id=package.package_id,
                candidate_id=CAND_A,
                decision=HumanReviewDecision.ADD,
                actor_id="operator-1",
                reviewed_at=STAMP,
            )
        self.assertEqual(raised.exception.code, CODE_HUMAN_REVIEW_CONTRACT_BLOCKER)

    def test_15_row_index_is_not_identity(self) -> None:
        package = _package(
            candidates=[_candidate(CAND_A), _candidate(CAND_B)]
        )
        # Binding by candidate_id of second row, not by index 1.
        event = _event(
            package=package,
            candidate_id=CAND_B,
            decision=HumanReviewDecision.REMOVE,
        )
        validated = validate_human_review_event_against_package(event, package)
        self.assertEqual(validated.candidate_id, CAND_B)
        self.assertNotEqual(validated.candidate_id, "1")

    def test_16_add_then_remove_latest_effective_remove(self) -> None:
        package = _package()
        events = (
            _event(
                package=package,
                review_event_id="evt-a1",
                decision=HumanReviewDecision.ADD,
            ),
            _event(
                package=package,
                review_event_id="evt-a2",
                decision=HumanReviewDecision.REMOVE,
                reviewed_at=datetime(2026, 10, 7, 13, 0, 0, tzinfo=timezone.utc),
            ),
        )
        effective = project_effective_human_review_decisions(events, package)
        self.assertEqual(effective[CAND_A], HumanReviewDecision.REMOVE)
        self.assertEqual(len(normalize_human_review_events(events, package)), 2)

    def test_17_remove_then_add_latest_effective_add(self) -> None:
        package = _package()
        events = (
            _event(
                package=package,
                review_event_id="evt-b1",
                decision=HumanReviewDecision.REMOVE,
            ),
            _event(
                package=package,
                review_event_id="evt-b2",
                decision=HumanReviewDecision.ADD,
            ),
        )
        effective = project_effective_human_review_decisions(events, package)
        self.assertEqual(effective[CAND_A], HumanReviewDecision.ADD)

    def test_18_previous_review_event_immutable(self) -> None:
        package = _package()
        first = _event(
            package=package,
            review_event_id="evt-imm-1",
            decision=HumanReviewDecision.ADD,
        )
        second = _event(
            package=package,
            review_event_id="evt-imm-2",
            decision=HumanReviewDecision.REMOVE,
        )
        normalized = normalize_human_review_events((first, second), package)
        self.assertEqual(normalized[0].decision, HumanReviewDecision.ADD)
        self.assertEqual(normalized[1].decision, HumanReviewDecision.REMOVE)
        self.assertEqual(first.decision, HumanReviewDecision.ADD)

    def test_19_identical_event_replay_idempotent(self) -> None:
        package = _package()
        event = _event(package=package, review_event_id="evt-idem")
        normalized = normalize_human_review_events((event, event), package)
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0].review_event_id, "evt-idem")

    def test_20_conflicting_event_replay_fail_closed(self) -> None:
        package = _package()
        first = _event(
            package=package,
            review_event_id="evt-conflict",
            decision=HumanReviewDecision.ADD,
        )
        conflict = _event(
            package=package,
            review_event_id="evt-conflict",
            decision=HumanReviewDecision.REMOVE,
        )
        with self.assertRaises(HumanReviewContractError) as raised:
            normalize_human_review_events((first, conflict), package)
        self.assertEqual(raised.exception.code, CODE_HUMAN_REVIEW_CONTRACT_BLOCKER)

    def test_21_unreviewed_candidate_gets_no_fake_decision(self) -> None:
        package = _package(
            candidates=[_candidate(CAND_A), _candidate(CAND_B)]
        )
        events = (
            _event(
                package=package,
                review_event_id="evt-only-a",
                candidate_id=CAND_A,
                decision=HumanReviewDecision.ADD,
            ),
        )
        effective = project_effective_human_review_decisions(events, package)
        self.assertEqual(effective[CAND_A], HumanReviewDecision.ADD)
        self.assertNotIn(CAND_B, effective)

    def test_22_same_ordered_inputs_same_effective_map(self) -> None:
        package = _package(
            candidates=[_candidate(CAND_A), _candidate(CAND_B)]
        )
        events = (
            _event(
                package=package,
                review_event_id="e1",
                candidate_id=CAND_A,
                decision=HumanReviewDecision.ADD,
            ),
            _event(
                package=package,
                review_event_id="e2",
                candidate_id=CAND_B,
                decision=HumanReviewDecision.REQUIRES_CLARIFICATION,
            ),
            _event(
                package=package,
                review_event_id="e3",
                candidate_id=CAND_A,
                decision=HumanReviewDecision.REMOVE,
            ),
        )
        first = project_effective_human_review_decisions(events, package)
        second = project_effective_human_review_decisions(events, package)
        self.assertEqual(first, second)
        self.assertEqual(first[CAND_A], HumanReviewDecision.REMOVE)
        self.assertEqual(first[CAND_B], HumanReviewDecision.REQUIRES_CLARIFICATION)

    def test_input_order_not_reviewed_at_sort(self) -> None:
        """Later event in sequence wins even if reviewed_at is earlier."""
        package = _package()
        later_stamp = datetime(2026, 10, 7, 18, 0, 0, tzinfo=timezone.utc)
        earlier_stamp = datetime(2026, 10, 7, 10, 0, 0, tzinfo=timezone.utc)
        events = (
            _event(
                package=package,
                review_event_id="late-clock-first",
                decision=HumanReviewDecision.ADD,
                reviewed_at=later_stamp,
            ),
            _event(
                package=package,
                review_event_id="early-clock-second",
                decision=HumanReviewDecision.REMOVE,
                reviewed_at=earlier_stamp,
            ),
        )
        effective = project_effective_human_review_decisions(events, package)
        self.assertEqual(effective[CAND_A], HumanReviewDecision.REMOVE)

    def test_actor_type_is_transitional_human_only(self) -> None:
        package = _package()
        with self.assertRaises(HumanReviewContractError):
            build_human_review_event(
                review_event_id="evt-app",
                run_id=RUN_ID,
                mission_id=MISSION_ID,
                package_id=package.package_id,
                candidate_id=CAND_A,
                decision=HumanReviewDecision.ADD,
                actor_id="operator-1",
                reviewed_at=STAMP,
                actor_type="LOCAL_APPLICATION",
            )
        event = _event(package=package)
        self.assertEqual(event.actor_type, ACTOR_TYPE_HUMAN)

    def test_invalid_decision_fail_closed(self) -> None:
        package = _package()
        with self.assertRaises(HumanReviewContractError):
            build_human_review_event(
                review_event_id="evt-bad",
                run_id=RUN_ID,
                mission_id=MISSION_ID,
                package_id=package.package_id,
                candidate_id=CAND_A,
                decision="CLARIFY_SCOPE",
                actor_id="operator-1",
                reviewed_at=STAMP,
            )


if __name__ == "__main__":
    unittest.main()
