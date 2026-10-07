"""
Constructor Recommendation Layer V1 — pure mapper tests.

No Supabase. No product writes. No LLM.
"""

from __future__ import annotations

import unittest

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_NOT_AVAILABLE,
    LABOR_PROVISIONAL,
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
    CandidateRecord,
    build_candidate_package,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    LaborNormEvidence,
    resolve_labor_norms,
)
from agents.monthly_plan_constructor.mission_scope import (
    build_constructor_mission_scope,
)
from agents.monthly_plan_constructor.recommendation import (
    CODE_RECOMMENDATION_CONTRACT_BLOCKER,
    HUMAN_REVIEW_REQUIRED,
    REASON_AVAILABLE_TO_ADD,
    REASON_LABOR_NORM_UNRESOLVED,
    REASON_LABOR_NOT_AVAILABLE,
    REASON_LABOR_PROVISIONAL,
    REASON_LABOR_VALIDATED,
    RECOMMEND_ADD,
    RECOMMEND_REMOVE,
    RecommendationError,
    apply_recommendation,
    recommend_for_candidate,
)

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY = "16160-17"
DISCIPLINE = "Автоматизация"


def _mission():
    return build_constructor_mission_scope(project_code=PROJECT, month_key=MONTH)


def _record(**overrides: object) -> CandidateRecord:
    base = dict(
        candidate_id="C1",
        project_code=PROJECT,
        month_key=MONTH,
        facility=FACILITY,
        discipline=DISCIPLINE,
        system="SYS-1",
        iwp="IWP-1",
        queue="",
        boq_code="BOQ-001",
        boq_name="Кабель",
        unit="м",
        remaining_qty=90.0,
        already_planned_qty=0.0,
        available_to_add_qty=90.0,
        availability_status="AVAILABLE",
        labor_norm_status=LABOR_UNRESOLVED,
        labor_norm_resolution_ref=None,
        source_snapshot_id="snap-1",
        recommendation=None,
        recommendation_reason_codes=(),
    )
    base.update(overrides)
    return CandidateRecord(**base)  # type: ignore[arg-type]


class RecommendationMapperTests(unittest.TestCase):
    def test_validated_recommend_add(self) -> None:
        result = recommend_for_candidate(
            _record(labor_norm_status=LABOR_VALIDATED, available_to_add_qty=60.0)
        )
        self.assertEqual(result.recommendation, RECOMMEND_ADD)
        self.assertEqual(
            result.recommendation_reason_codes,
            (REASON_AVAILABLE_TO_ADD, REASON_LABOR_VALIDATED),
        )

    def test_provisional_recommend_add(self) -> None:
        result = recommend_for_candidate(
            _record(labor_norm_status=LABOR_PROVISIONAL, available_to_add_qty=40.0)
        )
        self.assertEqual(result.recommendation, RECOMMEND_ADD)
        self.assertEqual(
            result.recommendation_reason_codes,
            (REASON_AVAILABLE_TO_ADD, REASON_LABOR_PROVISIONAL),
        )

    def test_unresolved_human_review_required(self) -> None:
        result = recommend_for_candidate(
            _record(labor_norm_status=LABOR_UNRESOLVED, available_to_add_qty=90.0)
        )
        self.assertEqual(result.recommendation, HUMAN_REVIEW_REQUIRED)
        self.assertEqual(
            result.recommendation_reason_codes,
            (REASON_LABOR_NORM_UNRESOLVED,),
        )

    def test_not_available_human_review_required(self) -> None:
        result = recommend_for_candidate(
            _record(labor_norm_status=LABOR_NOT_AVAILABLE, available_to_add_qty=90.0)
        )
        self.assertEqual(result.recommendation, HUMAN_REVIEW_REQUIRED)
        self.assertEqual(
            result.recommendation_reason_codes,
            (REASON_LABOR_NOT_AVAILABLE,),
        )

    def test_reason_codes_deterministic_and_stable(self) -> None:
        candidate = _record(labor_norm_status=LABOR_VALIDATED)
        first = recommend_for_candidate(candidate)
        second = recommend_for_candidate(candidate)
        self.assertEqual(first, second)
        self.assertEqual(
            apply_recommendation(candidate).recommendation_reason_codes,
            first.recommendation_reason_codes,
        )

    def test_unknown_labor_status_fails_closed(self) -> None:
        with self.assertRaises(RecommendationError) as raised:
            recommend_for_candidate(_record(labor_norm_status="INVENTED_STATUS"))
        self.assertEqual(raised.exception.code, CODE_RECOMMENDATION_CONTRACT_BLOCKER)

    def test_validated_zero_available_fails_closed(self) -> None:
        with self.assertRaises(RecommendationError) as raised:
            recommend_for_candidate(
                _record(labor_norm_status=LABOR_VALIDATED, available_to_add_qty=0.0)
            )
        self.assertEqual(raised.exception.code, CODE_RECOMMENDATION_CONTRACT_BLOCKER)

    def test_mapper_does_not_recompute_quantity(self) -> None:
        candidate = _record(
            labor_norm_status=LABOR_VALIDATED,
            remaining_qty=77.0,
            already_planned_qty=12.0,
            available_to_add_qty=65.0,
        )
        applied = apply_recommendation(candidate)
        self.assertEqual(applied.remaining_qty, 77.0)
        self.assertEqual(applied.already_planned_qty, 12.0)
        self.assertEqual(applied.available_to_add_qty, 65.0)
        self.assertEqual(applied.system, "SYS-1")
        self.assertEqual(applied.iwp, "IWP-1")
        self.assertEqual(applied.labor_norm_status, LABOR_VALIDATED)

    def test_v1_never_returns_recommend_remove(self) -> None:
        for status in (
            LABOR_VALIDATED,
            LABOR_PROVISIONAL,
            LABOR_UNRESOLVED,
            LABOR_NOT_AVAILABLE,
        ):
            result = recommend_for_candidate(
                _record(labor_norm_status=status, available_to_add_qty=10.0)
            )
            self.assertNotEqual(result.recommendation, RECOMMEND_REMOVE)

    def test_apply_recommendation_immutable_rebuild(self) -> None:
        original = _record(labor_norm_status=LABOR_PROVISIONAL)
        applied = apply_recommendation(original)
        self.assertIsNone(original.recommendation)
        self.assertEqual(original.recommendation_reason_codes, ())
        self.assertEqual(applied.recommendation, RECOMMEND_ADD)
        self.assertIsNot(applied, original)


class RecommendationPackageIntegrationTests(unittest.TestCase):
    def test_package_build_leaves_recommendation_unset(self) -> None:
        package = build_candidate_package(
            _mission(),
            [
                {
                    "candidate_id": "C1",
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
                    "remaining_qty": 90.0,
                    "already_planned_qty": 0.0,
                    "available_to_add_qty": 90.0,
                    "availability_status": "AVAILABLE",
                    "labor_norm_status": LABOR_UNRESOLVED,
                }
            ],
            mission_id="mission-rec-1",
            scanned_count=1,
        )
        self.assertIsNone(package.candidates[0].recommendation)
        self.assertEqual(package.candidates[0].recommendation_reason_codes, ())

    def test_resolve_labor_applies_recommendation_and_keeps_unresolved(self) -> None:
        package = build_candidate_package(
            _mission(),
            [
                {
                    "candidate_id": "C-UNRES",
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
                    "remaining_qty": 90.0,
                    "already_planned_qty": 0.0,
                    "available_to_add_qty": 90.0,
                    "availability_status": "AVAILABLE",
                    "labor_norm_status": LABOR_UNRESOLVED,
                }
            ],
            mission_id="mission-rec-2",
            scanned_count=1,
            snapshot_id="snap-rec",
        )
        resolved = resolve_labor_norms(package, evidence=())
        self.assertEqual(len(resolved.resolved_package.candidates), 1)
        candidate = resolved.resolved_package.candidates[0]
        self.assertEqual(candidate.labor_norm_status, LABOR_UNRESOLVED)
        self.assertEqual(candidate.recommendation, HUMAN_REVIEW_REQUIRED)
        self.assertEqual(
            candidate.recommendation_reason_codes,
            (REASON_LABOR_NORM_UNRESOLVED,),
        )
        self.assertEqual(candidate.available_to_add_qty, 90.0)
        self.assertEqual(candidate.source_snapshot_id, "snap-rec")

    def test_resolve_labor_validated_gets_recommend_add(self) -> None:
        package = build_candidate_package(
            _mission(),
            [
                {
                    "candidate_id": "C-VAL",
                    "project_code": PROJECT,
                    "month_key": MONTH,
                    "facility": FACILITY,
                    "discipline": DISCIPLINE,
                    "system": "SYS-1",
                    "iwp": "IWP-1",
                    "queue": "",
                    "boq_code": "BOQ-002",
                    "boq_name": "Кабель",
                    "unit": "м",
                    "remaining_qty": 50.0,
                    "already_planned_qty": 0.0,
                    "available_to_add_qty": 50.0,
                    "availability_status": "AVAILABLE",
                    "labor_norm_status": LABOR_UNRESOLVED,
                }
            ],
            mission_id="mission-rec-3",
            scanned_count=1,
        )
        evidence = LaborNormEvidence(
            evidence_id="ev-1",
            candidate_id="C-VAL",
            source_type="OFFICIAL_NORMATIVE",
            labor_hours_per_unit=1.5,
            unit="м",
            source_reference="norm-table-1",
            planning_use_status=LABOR_VALIDATED,
            basis="NORMATIVE_BENCHMARK",
        )
        resolved = resolve_labor_norms(package, evidence=(evidence,))
        candidate = resolved.resolved_package.candidates[0]
        self.assertEqual(candidate.labor_norm_status, LABOR_VALIDATED)
        self.assertEqual(candidate.recommendation, RECOMMEND_ADD)
        self.assertEqual(
            candidate.recommendation_reason_codes,
            (REASON_AVAILABLE_TO_ADD, REASON_LABOR_VALIDATED),
        )
        self.assertIsNotNone(candidate.labor_norm_resolution_ref)


if __name__ == "__main__":
    unittest.main()
