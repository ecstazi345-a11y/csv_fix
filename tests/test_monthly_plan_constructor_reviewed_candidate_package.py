"""
Constructor Reviewed Candidate Package V1 — pure deterministic tests.

No runtime wiring. No persistence. No UI. No LLM. No product writes.
"""

from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_NOT_AVAILABLE,
    LABOR_PROVISIONAL,
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
    PackageExceptionSummary,
    build_candidate_package,
)
from agents.monthly_plan_constructor.exception_engine import (
    CODE_DATA_CONTRACT_BLOCKER,
    CODE_LABOR_NORM_UNRESOLVED,
    CODE_SECURITY_DENIED,
    ROUTE_CONTINUE,
    ROUTE_FAIL_RUN,
    SEVERITY_BLOCKING,
    SEVERITY_NON_BLOCKING,
    SOURCE_CANDIDATE_PACKAGE,
    SOURCE_LABOR_NORM,
    SOURCE_SECURE_READ,
    ConstructorException,
    build_constructor_exception,
)
from agents.monthly_plan_constructor.human_review_contracts import (
    HumanReviewContractError,
    HumanReviewDecision,
    build_human_review_event,
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
from agents.monthly_plan_constructor.reviewed_candidate_package import (
    REASON_HUMAN_ADD,
    REASON_HUMAN_REMOVE,
    REASON_LABOR_NOT_AVAILABLE,
    REASON_LABOR_NORM_UNRESOLVED,
    REASON_LABOR_PROVISIONAL,
    REASON_LABOR_VALIDATED as RP_LABOR_VALIDATED,
    REASON_NO_HUMAN_REVIEW,
    REASON_REQUIRES_CLARIFICATION,
    ReviewedCandidatePackage,
    ReviewedDisposition,
    ReviewedPackageError,
    build_reviewed_candidate_package,
)

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY = "16160-17"
DISCIPLINE = "Автоматизация"
MISSION_ID = "mission-rp-1"
RUN_ID = "run-rp-1"
CAND_A = "CAND-A"
CAND_B = "CAND-B"
STAMP = datetime(2026, 10, 7, 15, 0, 0, tzinfo=timezone.utc)
CREATED = datetime(2026, 10, 7, 16, 0, 0, tzinfo=timezone.utc)


def _mission():
    return build_constructor_mission_scope(project_code=PROJECT, month_key=MONTH)


def _candidate(
    candidate_id: str = CAND_A,
    *,
    labor_norm_status: str = LABOR_VALIDATED,
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


def _package(
    *,
    candidates: list[dict[str, object]] | None = None,
    exception_summary: PackageExceptionSummary | None = None,
):
    items = candidates if candidates is not None else [_candidate()]
    return build_candidate_package(
        _mission(),
        items,
        mission_id=MISSION_ID,
        scanned_count=len(items),
        run_id=RUN_ID,
        snapshot_id="snap-rp-1",
        exception_summary=exception_summary,
    )


def _event(
    package,
    *,
    review_event_id: str = "evt-1",
    candidate_id: str = CAND_A,
    decision: object = HumanReviewDecision.ADD,
    actor_id: str = "operator-1",
    reviewed_at: datetime = STAMP,
):
    return build_human_review_event(
        review_event_id=review_event_id,
        run_id=RUN_ID,
        mission_id=MISSION_ID,
        package_id=package.package_id,
        candidate_id=candidate_id,
        decision=decision,
        actor_id=actor_id,
        reviewed_at=reviewed_at,
    )


def _exc(
    *,
    exception_code: str,
    severity: str,
    route: str,
    candidate_id: str | None = None,
    package_id: str | None = None,
    exception_id: str = "exc-1",
    source_capability: str = SOURCE_CANDIDATE_PACKAGE,
    reason: str = "test",
) -> ConstructorException:
    return build_constructor_exception(
        exception_code=exception_code,
        reason=reason,
        source_capability=source_capability,
        severity=severity,
        route=route,
        observed_at=STAMP,
        package_id=package_id,
        candidate_id=candidate_id,
        exception_id=exception_id,
    )


class ReviewedCandidatePackageDispositionTests(unittest.TestCase):
    def test_01_add_validated_no_blocker_included(self) -> None:
        package = _package(candidates=[_candidate(labor_norm_status=LABOR_VALIDATED)])
        reviewed = build_reviewed_candidate_package(
            package, [_event(package)], (), created_at=CREATED
        )
        rec = reviewed.reviewed_records[0]
        self.assertEqual(rec.disposition, ReviewedDisposition.INCLUDED)
        self.assertEqual(
            rec.disposition_reason_codes,
            (REASON_HUMAN_ADD, RP_LABOR_VALIDATED),
        )
        self.assertEqual(reviewed.included_count, 1)

    def test_02_add_provisional_no_blocker_included(self) -> None:
        package = _package(
            candidates=[_candidate(labor_norm_status=LABOR_PROVISIONAL)]
        )
        reviewed = build_reviewed_candidate_package(
            package, [_event(package)], (), created_at=CREATED
        )
        rec = reviewed.reviewed_records[0]
        self.assertEqual(rec.disposition, ReviewedDisposition.INCLUDED)
        self.assertEqual(
            rec.disposition_reason_codes,
            (REASON_HUMAN_ADD, REASON_LABOR_PROVISIONAL),
        )

    def test_03_add_unresolved_labor(self) -> None:
        package = _package(
            candidates=[_candidate(labor_norm_status=LABOR_UNRESOLVED)]
        )
        reviewed = build_reviewed_candidate_package(
            package, [_event(package)], (), created_at=CREATED
        )
        rec = reviewed.reviewed_records[0]
        self.assertEqual(rec.disposition, ReviewedDisposition.UNRESOLVED)
        self.assertEqual(
            rec.disposition_reason_codes, (REASON_LABOR_NORM_UNRESOLVED,)
        )

    def test_04_add_not_available(self) -> None:
        package = _package(
            candidates=[_candidate(labor_norm_status=LABOR_NOT_AVAILABLE)]
        )
        reviewed = build_reviewed_candidate_package(
            package, [_event(package)], (), created_at=CREATED
        )
        rec = reviewed.reviewed_records[0]
        self.assertEqual(rec.disposition, ReviewedDisposition.UNRESOLVED)
        self.assertEqual(
            rec.disposition_reason_codes, (REASON_LABOR_NOT_AVAILABLE,)
        )

    def test_05_human_remove_excluded(self) -> None:
        package = _package()
        reviewed = build_reviewed_candidate_package(
            package,
            [_event(package, decision=HumanReviewDecision.REMOVE)],
            (),
            created_at=CREATED,
        )
        rec = reviewed.reviewed_records[0]
        self.assertEqual(rec.disposition, ReviewedDisposition.EXCLUDED)
        self.assertEqual(rec.disposition_reason_codes, (REASON_HUMAN_REMOVE,))

    def test_06_requires_clarification_unresolved(self) -> None:
        package = _package()
        reviewed = build_reviewed_candidate_package(
            package,
            [
                _event(
                    package,
                    decision=HumanReviewDecision.REQUIRES_CLARIFICATION,
                )
            ],
            (),
            created_at=CREATED,
        )
        rec = reviewed.reviewed_records[0]
        self.assertEqual(rec.disposition, ReviewedDisposition.UNRESOLVED)
        self.assertEqual(
            rec.disposition_reason_codes, (REASON_REQUIRES_CLARIFICATION,)
        )

    def test_07_no_human_review_unresolved(self) -> None:
        package = _package()
        reviewed = build_reviewed_candidate_package(
            package, (), (), created_at=CREATED
        )
        rec = reviewed.reviewed_records[0]
        self.assertEqual(rec.disposition, ReviewedDisposition.UNRESOLVED)
        self.assertEqual(rec.disposition_reason_codes, (REASON_NO_HUMAN_REVIEW,))
        self.assertIsNone(rec.human_review_decision)
        self.assertIsNone(rec.effective_review_event)

    def test_08_recommend_add_plus_human_remove_excluded(self) -> None:
        package = _package(
            candidates=[
                _candidate(
                    labor_norm_status=LABOR_VALIDATED,
                    recommendation=RECOMMEND_ADD,
                    recommendation_reason_codes=(
                        REASON_AVAILABLE_TO_ADD,
                        REASON_LABOR_VALIDATED,
                    ),
                )
            ]
        )
        reviewed = build_reviewed_candidate_package(
            package,
            [_event(package, decision=HumanReviewDecision.REMOVE)],
            (),
            created_at=CREATED,
        )
        self.assertEqual(
            reviewed.reviewed_records[0].disposition, ReviewedDisposition.EXCLUDED
        )
        self.assertEqual(package.candidates[0].recommendation, RECOMMEND_ADD)

    def test_09_human_review_required_plus_add_validated_included(self) -> None:
        package = _package(
            candidates=[
                _candidate(
                    labor_norm_status=LABOR_VALIDATED,
                    recommendation=HUMAN_REVIEW_REQUIRED,
                )
            ]
        )
        reviewed = build_reviewed_candidate_package(
            package, [_event(package)], (), created_at=CREATED
        )
        self.assertEqual(
            reviewed.reviewed_records[0].disposition, ReviewedDisposition.INCLUDED
        )
        self.assertEqual(
            package.candidates[0].recommendation, HUMAN_REVIEW_REQUIRED
        )

    def test_10_candidate_blocking_plus_add_unresolved(self) -> None:
        package = _package(
            candidates=[_candidate(labor_norm_status=LABOR_VALIDATED)],
            exception_summary=PackageExceptionSummary(
                blocking_count=1, non_blocking_count=0, warning_count=0
            ),
        )
        blocker = _exc(
            exception_code=CODE_DATA_CONTRACT_BLOCKER,
            severity=SEVERITY_BLOCKING,
            route=ROUTE_FAIL_RUN,
            candidate_id=CAND_A,
            package_id=package.package_id,
            exception_id="blk-cand",
        )
        reviewed = build_reviewed_candidate_package(
            package, [_event(package)], [blocker], created_at=CREATED
        )
        rec = reviewed.reviewed_records[0]
        self.assertEqual(rec.disposition, ReviewedDisposition.UNRESOLVED)
        self.assertIn(CODE_DATA_CONTRACT_BLOCKER, rec.disposition_reason_codes)
        self.assertEqual(
            rec.blocking_exception_codes, (CODE_DATA_CONTRACT_BLOCKER,)
        )

    def test_11_candidate_non_blocking_plus_add_included(self) -> None:
        package = _package(
            candidates=[_candidate(labor_norm_status=LABOR_VALIDATED)],
            exception_summary=PackageExceptionSummary(
                blocking_count=0, non_blocking_count=1, warning_count=0
            ),
        )
        note = _exc(
            exception_code=CODE_LABOR_NORM_UNRESOLVED,
            severity=SEVERITY_NON_BLOCKING,
            route=ROUTE_CONTINUE,
            candidate_id=CAND_A,
            package_id=package.package_id,
            exception_id="nb-1",
            source_capability=SOURCE_LABOR_NORM,
            reason="advisory unresolved note",
        )
        reviewed = build_reviewed_candidate_package(
            package, [_event(package)], [note], created_at=CREATED
        )
        self.assertEqual(
            reviewed.reviewed_records[0].disposition, ReviewedDisposition.INCLUDED
        )

    def test_12_package_global_blocking_prevents_include(self) -> None:
        package = _package(
            candidates=[
                _candidate(CAND_A, labor_norm_status=LABOR_VALIDATED),
                _candidate(CAND_B, labor_norm_status=LABOR_PROVISIONAL),
            ],
            exception_summary=PackageExceptionSummary(
                blocking_count=1, non_blocking_count=0, warning_count=0
            ),
        )
        blocker = _exc(
            exception_code=CODE_SECURITY_DENIED,
            severity=SEVERITY_BLOCKING,
            route=ROUTE_FAIL_RUN,
            candidate_id=None,
            package_id=package.package_id,
            exception_id="pkg-blk",
            source_capability=SOURCE_SECURE_READ,
            reason="denied",
        )
        events = [
            _event(package, review_event_id="e-a", candidate_id=CAND_A),
            _event(package, review_event_id="e-b", candidate_id=CAND_B),
        ]
        reviewed = build_reviewed_candidate_package(
            package, events, [blocker], created_at=CREATED
        )
        self.assertEqual(reviewed.included_count, 0)
        self.assertEqual(reviewed.unresolved_count, 2)
        for rec in reviewed.reviewed_records:
            self.assertEqual(rec.disposition, ReviewedDisposition.UNRESOLVED)
            self.assertIn(CODE_SECURITY_DENIED, rec.disposition_reason_codes)

    def test_13_remove_excluded_even_with_package_blocker(self) -> None:
        package = _package(
            exception_summary=PackageExceptionSummary(
                blocking_count=1, non_blocking_count=0, warning_count=0
            ),
        )
        blocker = _exc(
            exception_code=CODE_SECURITY_DENIED,
            severity=SEVERITY_BLOCKING,
            route=ROUTE_FAIL_RUN,
            package_id=package.package_id,
            exception_id="pkg-blk-2",
            source_capability=SOURCE_SECURE_READ,
        )
        reviewed = build_reviewed_candidate_package(
            package,
            [_event(package, decision=HumanReviewDecision.REMOVE)],
            [blocker],
            created_at=CREATED,
        )
        self.assertEqual(
            reviewed.reviewed_records[0].disposition, ReviewedDisposition.EXCLUDED
        )

    def test_gap_candidate_blocker_does_not_block_sibling(self) -> None:
        package = _package(
            candidates=[
                _candidate(CAND_A, labor_norm_status=LABOR_VALIDATED),
                _candidate(CAND_B, labor_norm_status=LABOR_PROVISIONAL),
            ],
            exception_summary=PackageExceptionSummary(
                blocking_count=1, non_blocking_count=0, warning_count=0
            ),
        )
        blocker_a = _exc(
            exception_code=CODE_DATA_CONTRACT_BLOCKER,
            severity=SEVERITY_BLOCKING,
            route=ROUTE_FAIL_RUN,
            candidate_id=CAND_A,
            package_id=package.package_id,
            exception_id="blk-only-a",
        )
        events = [
            _event(package, review_event_id="e-a", candidate_id=CAND_A),
            _event(package, review_event_id="e-b", candidate_id=CAND_B),
        ]
        reviewed = build_reviewed_candidate_package(
            package, events, [blocker_a], created_at=CREATED
        )
        by_id = {r.candidate_id: r for r in reviewed.reviewed_records}
        self.assertEqual(by_id[CAND_A].disposition, ReviewedDisposition.UNRESOLVED)
        self.assertIn(CODE_DATA_CONTRACT_BLOCKER, by_id[CAND_A].disposition_reason_codes)
        self.assertEqual(by_id[CAND_B].disposition, ReviewedDisposition.INCLUDED)
        self.assertEqual(reviewed.included_count, 1)
        self.assertEqual(reviewed.unresolved_count, 1)


class ReviewedCandidatePackageFailClosedTests(unittest.TestCase):
    def test_14_exception_summary_mismatch_fail_closed(self) -> None:
        package = _package()  # summary all zeros
        blocker = _exc(
            exception_code=CODE_DATA_CONTRACT_BLOCKER,
            severity=SEVERITY_BLOCKING,
            route=ROUTE_FAIL_RUN,
            package_id=package.package_id,
        )
        with self.assertRaises(ReviewedPackageError) as raised:
            build_reviewed_candidate_package(
                package, [_event(package)], [blocker], created_at=CREATED
            )
        self.assertEqual(
            raised.exception.code, "REVIEWED_PACKAGE_CONTRACT_BLOCKER"
        )
        self.assertIn("exception_summary mismatch", str(raised.exception))

    def test_15_orphan_candidate_exception_fail_closed(self) -> None:
        package = _package(
            exception_summary=PackageExceptionSummary(
                blocking_count=1, non_blocking_count=0, warning_count=0
            ),
        )
        orphan = _exc(
            exception_code=CODE_DATA_CONTRACT_BLOCKER,
            severity=SEVERITY_BLOCKING,
            route=ROUTE_FAIL_RUN,
            candidate_id="UNKNOWN-CAND",
            package_id=package.package_id,
        )
        with self.assertRaises(ReviewedPackageError) as raised:
            build_reviewed_candidate_package(
                package, [_event(package)], [orphan], created_at=CREATED
            )
        self.assertIn("orphan exception", str(raised.exception))

    def test_16_stale_human_review_package_binding_fail_closed(self) -> None:
        package = _package()
        stale = build_human_review_event(
            review_event_id="evt-stale",
            run_id=RUN_ID,
            mission_id=MISSION_ID,
            package_id="other-package-id",
            candidate_id=CAND_A,
            decision=HumanReviewDecision.ADD,
            actor_id="operator-1",
            reviewed_at=STAMP,
        )
        with self.assertRaises(HumanReviewContractError):
            build_reviewed_candidate_package(
                package, [stale], (), created_at=CREATED
            )

    def test_gap_missing_source_run_id_fail_closed(self) -> None:
        package = build_candidate_package(
            _mission(),
            [_candidate(labor_norm_status=LABOR_VALIDATED)],
            mission_id=MISSION_ID,
            scanned_count=1,
            run_id=None,
            snapshot_id="snap-rp-1",
        )
        self.assertIsNone(package.run_id)
        event = build_human_review_event(
            review_event_id="evt-no-pkg-run",
            run_id=RUN_ID,
            mission_id=MISSION_ID,
            package_id=package.package_id,
            candidate_id=CAND_A,
            decision=HumanReviewDecision.ADD,
            actor_id="operator-1",
            reviewed_at=STAMP,
        )
        with self.assertRaises(ReviewedPackageError) as raised:
            build_reviewed_candidate_package(
                package, [event], (), created_at=CREATED
            )
        self.assertEqual(
            raised.exception.code, "REVIEWED_PACKAGE_CONTRACT_BLOCKER"
        )
        self.assertIn("run_id", str(raised.exception))


class ReviewedCandidatePackageImmutabilityTests(unittest.TestCase):
    def test_17_21_source_artifacts_unchanged(self) -> None:
        package = _package(
            candidates=[
                _candidate(
                    labor_norm_status=LABOR_VALIDATED,
                    recommendation=RECOMMEND_ADD,
                    recommendation_reason_codes=(REASON_AVAILABLE_TO_ADD,),
                )
            ],
            exception_summary=PackageExceptionSummary(
                blocking_count=0, non_blocking_count=1, warning_count=0
            ),
        )
        event = _event(package)
        note = _exc(
            exception_code=CODE_LABOR_NORM_UNRESOLVED,
            severity=SEVERITY_NON_BLOCKING,
            route=ROUTE_CONTINUE,
            candidate_id=CAND_A,
            package_id=package.package_id,
            source_capability=SOURCE_LABOR_NORM,
        )
        cand_before = copy.deepcopy(package.candidates[0])
        event_before = copy.deepcopy(event)
        note_before = copy.deepcopy(note)
        rec_before = package.candidates[0].recommendation
        labor_before = package.candidates[0].labor_norm_status

        reviewed = build_reviewed_candidate_package(
            package, [event], [note], created_at=CREATED
        )
        self.assertIs(reviewed.reviewed_records[0].source_candidate, package.candidates[0])
        self.assertEqual(package.candidates[0], cand_before)
        self.assertEqual(package.candidates[0].recommendation, rec_before)
        self.assertEqual(package.candidates[0].labor_norm_status, labor_before)
        self.assertEqual(event, event_before)
        self.assertEqual(note, note_before)
        self.assertEqual(reviewed.reviewed_records[0].source_candidate.recommendation, RECOMMEND_ADD)
        self.assertEqual(
            reviewed.reviewed_records[0].source_candidate.labor_norm_status,
            LABOR_VALIDATED,
        )


class ReviewedCandidatePackageIdentityTests(unittest.TestCase):
    def test_22_24_same_inputs_same_dispositions_and_ids(self) -> None:
        package = _package()
        events = [_event(package)]
        a = build_reviewed_candidate_package(
            package, events, (), created_at=CREATED
        )
        b = build_reviewed_candidate_package(
            package, events, (), created_at=CREATED
        )
        self.assertEqual(
            [r.disposition for r in a.reviewed_records],
            [r.disposition for r in b.reviewed_records],
        )
        self.assertEqual(a.review_projection_fingerprint, b.review_projection_fingerprint)
        self.assertEqual(a.reviewed_package_id, b.reviewed_package_id)

    def test_25_26_new_effective_review_changes_fingerprint_and_id(self) -> None:
        package = _package()
        first = build_reviewed_candidate_package(
            package,
            [_event(package, decision=HumanReviewDecision.ADD)],
            (),
            created_at=CREATED,
        )
        second = build_reviewed_candidate_package(
            package,
            [
                _event(package, decision=HumanReviewDecision.ADD),
                _event(
                    package,
                    review_event_id="evt-2",
                    decision=HumanReviewDecision.REMOVE,
                ),
            ],
            (),
            created_at=CREATED,
        )
        self.assertNotEqual(
            first.review_projection_fingerprint, second.review_projection_fingerprint
        )
        self.assertNotEqual(first.reviewed_package_id, second.reviewed_package_id)
        self.assertEqual(
            second.reviewed_records[0].disposition, ReviewedDisposition.EXCLUDED
        )

    def test_27_changed_blocking_exception_changes_package_id(self) -> None:
        package = _package(
            exception_summary=PackageExceptionSummary(
                blocking_count=1, non_blocking_count=0, warning_count=0
            ),
        )
        a = _exc(
            exception_code=CODE_DATA_CONTRACT_BLOCKER,
            severity=SEVERITY_BLOCKING,
            route=ROUTE_FAIL_RUN,
            package_id=package.package_id,
            exception_id="blk-a",
        )
        b = _exc(
            exception_code=CODE_SECURITY_DENIED,
            severity=SEVERITY_BLOCKING,
            route=ROUTE_FAIL_RUN,
            package_id=package.package_id,
            exception_id="blk-b",
            source_capability=SOURCE_SECURE_READ,
        )
        ra = build_reviewed_candidate_package(
            package, [_event(package)], [a], created_at=CREATED
        )
        rb = build_reviewed_candidate_package(
            package, [_event(package)], [b], created_at=CREATED
        )
        self.assertNotEqual(ra.reviewed_package_id, rb.reviewed_package_id)
        self.assertNotEqual(ra.exception_fingerprint, rb.exception_fingerprint)

    def test_28_old_reviewed_package_immutable(self) -> None:
        package = _package()
        old = build_reviewed_candidate_package(
            package, [_event(package)], (), created_at=CREATED
        )
        old_id = old.reviewed_package_id
        old_disp = old.reviewed_records[0].disposition
        _ = build_reviewed_candidate_package(
            package,
            [_event(package, decision=HumanReviewDecision.REMOVE)],
            (),
            created_at=CREATED,
        )
        self.assertEqual(old.reviewed_package_id, old_id)
        self.assertEqual(old.reviewed_records[0].disposition, old_disp)

    def test_identical_idempotent_replay_same_package_id(self) -> None:
        package = _package()
        event = _event(package)
        a = build_reviewed_candidate_package(
            package, [event], (), created_at=CREATED
        )
        b = build_reviewed_candidate_package(
            package, [event, event], (), created_at=CREATED
        )
        self.assertEqual(a.reviewed_package_id, b.reviewed_package_id)
        self.assertEqual(a.review_projection_fingerprint, b.review_projection_fingerprint)

    def test_gap_created_at_does_not_change_package_id(self) -> None:
        package = _package()
        events = [_event(package)]
        created_a = datetime(2026, 10, 7, 16, 0, 0, tzinfo=timezone.utc)
        created_b = datetime(2026, 10, 8, 9, 30, 0, tzinfo=timezone.utc)
        a = build_reviewed_candidate_package(
            package, events, (), created_at=created_a
        )
        b = build_reviewed_candidate_package(
            package, events, (), created_at=created_b
        )
        self.assertNotEqual(a.created_at, b.created_at)
        self.assertEqual(
            a.review_projection_fingerprint, b.review_projection_fingerprint
        )
        self.assertEqual(a.reviewed_package_id, b.reviewed_package_id)

    def test_gap_exception_order_stability(self) -> None:
        package = _package(
            candidates=[
                _candidate(CAND_A, labor_norm_status=LABOR_VALIDATED),
                _candidate(CAND_B, labor_norm_status=LABOR_VALIDATED),
            ],
            exception_summary=PackageExceptionSummary(
                blocking_count=0, non_blocking_count=2, warning_count=0
            ),
        )
        e1 = _exc(
            exception_code=CODE_LABOR_NORM_UNRESOLVED,
            severity=SEVERITY_NON_BLOCKING,
            route=ROUTE_CONTINUE,
            candidate_id=CAND_A,
            package_id=package.package_id,
            exception_id="exc-e1",
            source_capability=SOURCE_LABOR_NORM,
            reason="note-a",
        )
        e2 = _exc(
            exception_code=CODE_LABOR_NORM_UNRESOLVED,
            severity=SEVERITY_NON_BLOCKING,
            route=ROUTE_CONTINUE,
            candidate_id=CAND_B,
            package_id=package.package_id,
            exception_id="exc-e2",
            source_capability=SOURCE_LABOR_NORM,
            reason="note-b",
        )
        events = [
            _event(package, review_event_id="e-a", candidate_id=CAND_A),
            _event(package, review_event_id="e-b", candidate_id=CAND_B),
        ]
        a = build_reviewed_candidate_package(
            package, events, [e1, e2], created_at=CREATED
        )
        b = build_reviewed_candidate_package(
            package, events, [e2, e1], created_at=CREATED
        )
        self.assertEqual(
            [r.disposition for r in a.reviewed_records],
            [r.disposition for r in b.reviewed_records],
        )
        self.assertEqual(a.exception_fingerprint, b.exception_fingerprint)
        self.assertEqual(a.reviewed_package_id, b.reviewed_package_id)

    def test_gap_new_same_decision_review_event_changes_identity(self) -> None:
        package = _package()
        event_1 = _event(
            package,
            review_event_id="review-1",
            decision=HumanReviewDecision.ADD,
        )
        event_2 = _event(
            package,
            review_event_id="review-2",
            decision=HumanReviewDecision.ADD,
        )
        a = build_reviewed_candidate_package(
            package, [event_1], (), created_at=CREATED
        )
        b = build_reviewed_candidate_package(
            package, [event_2], (), created_at=CREATED
        )
        self.assertEqual(
            a.reviewed_records[0].disposition, ReviewedDisposition.INCLUDED
        )
        self.assertEqual(
            b.reviewed_records[0].disposition, ReviewedDisposition.INCLUDED
        )
        self.assertNotEqual(
            a.review_projection_fingerprint, b.review_projection_fingerprint
        )
        self.assertNotEqual(a.reviewed_package_id, b.reviewed_package_id)

        replay = build_reviewed_candidate_package(
            package, [event_1, event_1], (), created_at=CREATED
        )
        self.assertEqual(
            a.review_projection_fingerprint, replay.review_projection_fingerprint
        )
        self.assertEqual(a.reviewed_package_id, replay.reviewed_package_id)


class ReviewedCandidatePackageSemanticsTests(unittest.TestCase):
    def test_29_no_review_does_not_synthesize_decision(self) -> None:
        package = _package(
            candidates=[
                _candidate(CAND_A),
                _candidate(CAND_B, labor_norm_status=LABOR_PROVISIONAL),
            ]
        )
        reviewed = build_reviewed_candidate_package(
            package,
            [_event(package, candidate_id=CAND_A)],
            (),
            created_at=CREATED,
        )
        by_id = {r.candidate_id: r for r in reviewed.reviewed_records}
        self.assertEqual(by_id[CAND_A].disposition, ReviewedDisposition.INCLUDED)
        self.assertIsNone(by_id[CAND_B].human_review_decision)
        self.assertEqual(by_id[CAND_B].disposition, ReviewedDisposition.UNRESOLVED)
        self.assertEqual(
            by_id[CAND_B].disposition_reason_codes, (REASON_NO_HUMAN_REVIEW,)
        )

    def test_30_31_no_confirm_or_handoff_semantics(self) -> None:
        from dataclasses import fields

        names = {f.name for f in fields(ReviewedCandidatePackage)}
        forbidden = {
            "confirmed",
            "approved",
            "authorized",
            "ready_for_handoff",
            "monthly_commitment",
            "handoff_ready",
            "accepted",
            "executable",
            "committed",
        }
        self.assertFalse(names & forbidden)

    def test_32_counts_match_records(self) -> None:
        package = _package(
            candidates=[
                _candidate(CAND_A, labor_norm_status=LABOR_VALIDATED),
                _candidate(CAND_B, labor_norm_status=LABOR_VALIDATED),
            ]
        )
        events = [
            _event(package, review_event_id="e1", candidate_id=CAND_A),
            _event(
                package,
                review_event_id="e2",
                candidate_id=CAND_B,
                decision=HumanReviewDecision.REMOVE,
            ),
        ]
        reviewed = build_reviewed_candidate_package(
            package, events, (), created_at=CREATED
        )
        self.assertEqual(reviewed.included_count, 1)
        self.assertEqual(reviewed.excluded_count, 1)
        self.assertEqual(reviewed.unresolved_count, 0)
        self.assertEqual(
            reviewed.included_count
            + reviewed.excluded_count
            + reviewed.unresolved_count,
            len(reviewed.reviewed_records),
        )

    def test_preserves_source_candidate_order(self) -> None:
        package = _package(
            candidates=[
                _candidate(CAND_B, labor_norm_status=LABOR_VALIDATED),
                _candidate(CAND_A, labor_norm_status=LABOR_VALIDATED),
            ]
        )
        events = [
            _event(package, review_event_id="e-a", candidate_id=CAND_A),
            _event(
                package,
                review_event_id="e-b",
                candidate_id=CAND_B,
                decision=HumanReviewDecision.REMOVE,
            ),
        ]
        reviewed = build_reviewed_candidate_package(
            package, events, (), created_at=CREATED
        )
        self.assertEqual(
            [r.candidate_id for r in reviewed.reviewed_records],
            [CAND_B, CAND_A],
        )

    def test_module_isolation(self) -> None:
        source = Path(
            "agents/monthly_plan_constructor/reviewed_candidate_package.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "import streamlit",
            "from streamlit",
            "import langgraph",
            "from langgraph",
            "supabase",
            "subprocess",
            "uuid.uuid4",
            "sqlite3",
            "hitl_resume",
            "handoff_contracts",
            "langgraph_runtime",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
