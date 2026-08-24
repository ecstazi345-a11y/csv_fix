"""
Increment 4 — Constructor LaborNormResolver capability.

Pure domain tests. No Streamlit, Supabase, LLM, SQL, or product writes.
"""

from __future__ import annotations

import math
import unittest

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_PROVISIONAL,
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
    CandidatePackage,
    build_candidate_package,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_NORMATIVE_BENCHMARK,
    BASIS_OBSERVED_PRODUCTIVITY,
    CODE_REJECTED_HISTORY_WITHOUT_EXECUTED_QUANTITY,
    CODE_REJECTED_INCOMPATIBLE_UNIT,
    CODE_REJECTED_MISSING_PROVENANCE,
    CODE_REJECTED_NEGATIVE_NORM,
    CODE_REJECTED_NON_FINITE_NORM,
    CODE_REJECTED_NONPRODUCTIVE_HOURS,
    CODE_REJECTED_ZERO_NORM,
    HOURS_PAID_NONPRODUCTIVE,
    HOURS_PAID_WITHOUT_EXECUTED_QUANTITY,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    LaborNormEvidence,
    REASON_AMBIGUOUS_LABOR_NORM_EVIDENCE,
    REASON_DUPLICATE_EVIDENCE_DEDUPLICATED,
    REASON_NO_ADMISSIBLE_EVIDENCE,
    SOURCE_COMPANY_HISTORY,
    SOURCE_OFFICIAL_NORMATIVE,
    SOURCE_PROJECT_HISTORY,
    resolve_labor_norms,
)
from agents.monthly_plan_constructor.mission_scope import (
    ConstructorMissionScope,
    build_constructor_mission_scope,
)

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"
MISSION_ID = "mission-increment-4"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
OTHER_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-002"


def _mission(**overrides: object) -> ConstructorMissionScope:
    payload: dict[str, object] = {
        "project_code": PROJECT,
        "month_key": MONTH,
    }
    payload.update(overrides)
    return build_constructor_mission_scope(**payload)  # type: ignore[arg-type]


def _candidate(**overrides: object) -> dict[str, object]:
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


def _package(
    candidates: list[dict[str, object]] | None = None,
    **kwargs: object,
) -> CandidatePackage:
    items = candidates if candidates is not None else [_candidate()]
    return build_candidate_package(
        _mission(),
        items,
        mission_id=MISSION_ID,
        scanned_count=len(items) if kwargs.get("scanned_count") is None else kwargs.pop("scanned_count"),  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


def _history(**overrides: object) -> LaborNormEvidence:
    payload: dict[str, object] = {
        "evidence_id": "ev-project",
        "candidate_id": CANDIDATE_ID,
        "source_type": SOURCE_PROJECT_HISTORY,
        "labor_hours_per_unit": 1.42,
        "unit": "м2",
        "source_reference": "project-history-run-6840m2",
        "source_version": "2026-08",
        "planning_use_status": LABOR_VALIDATED,
        "basis": BASIS_OBSERVED_PRODUCTIVITY,
        "hours_quality": HOURS_VALIDATED_PRODUCTIVE_DIRECT,
        "executed_quantity_validated": True,
    }
    payload.update(overrides)
    return LaborNormEvidence(**payload)  # type: ignore[arg-type]


def _company(**overrides: object) -> LaborNormEvidence:
    return _history(
        evidence_id="ev-company",
        source_type=SOURCE_COMPANY_HISTORY,
        labor_hours_per_unit=1.60,
        source_reference="company-history-p50",
        **overrides,
    )


def _official(**overrides: object) -> LaborNormEvidence:
    payload: dict[str, object] = {
        "evidence_id": "ev-official",
        "candidate_id": CANDIDATE_ID,
        "source_type": SOURCE_OFFICIAL_NORMATIVE,
        "labor_hours_per_unit": 2.10,
        "unit": "м2",
        "source_reference": "GESN-08-01-001/edition-2024",
        "source_version": "2024",
        "planning_use_status": LABOR_PROVISIONAL,
        "basis": BASIS_NORMATIVE_BENCHMARK,
        "hours_quality": "NOT_APPLICABLE",
        "executed_quantity_validated": False,
    }
    payload.update(overrides)
    return LaborNormEvidence(**payload)  # type: ignore[arg-type]


class LaborNormResolverTests(unittest.TestCase):
    def test_01_project_history_beats_company_history(self) -> None:
        result = resolve_labor_norms(_package(), [_history(), _company()])
        resolution = result.resolutions[0]
        self.assertEqual(resolution.source_type, SOURCE_PROJECT_HISTORY)
        self.assertEqual(resolution.labor_hours_per_unit, 1.42)
        self.assertEqual(resolution.status, LABOR_VALIDATED)

    def test_02_company_history_beats_official_when_project_absent(self) -> None:
        result = resolve_labor_norms(_package(), [_company(), _official()])
        resolution = result.resolutions[0]
        self.assertEqual(resolution.source_type, SOURCE_COMPANY_HISTORY)
        self.assertEqual(resolution.labor_hours_per_unit, 1.60)

    def test_03_invalid_higher_priority_falls_through(self) -> None:
        bad_project = _history(hours_quality=HOURS_PAID_NONPRODUCTIVE)
        result = resolve_labor_norms(_package(), [bad_project, _company()])
        resolution = result.resolutions[0]
        self.assertEqual(resolution.source_type, SOURCE_COMPANY_HISTORY)
        self.assertIn(CODE_REJECTED_NONPRODUCTIVE_HOURS, resolution.rejection_codes)

    def test_04_validated_evidence_produces_validated(self) -> None:
        result = resolve_labor_norms(_package(), [_history()])
        self.assertEqual(result.resolutions[0].status, LABOR_VALIDATED)
        self.assertEqual(result.resolved_package.candidates[0].labor_norm_status, LABOR_VALIDATED)

    def test_05_provisional_evidence_remains_provisional(self) -> None:
        result = resolve_labor_norms(_package(), [_official()])
        self.assertEqual(result.resolutions[0].status, LABOR_PROVISIONAL)
        self.assertEqual(
            result.resolved_package.candidates[0].labor_norm_status,
            LABOR_PROVISIONAL,
        )

    def test_06_no_evidence_produces_unresolved(self) -> None:
        result = resolve_labor_norms(_package(), [])
        self.assertEqual(result.resolutions[0].status, LABOR_UNRESOLVED)
        self.assertEqual(result.resolutions[0].resolution_reason, REASON_NO_ADMISSIBLE_EVIDENCE)

    def test_07_unresolved_candidate_remains_represented(self) -> None:
        result = resolve_labor_norms(_package(), [])
        self.assertEqual(len(result.resolved_package.candidates), 1)
        self.assertEqual(result.resolved_package.candidates[0].candidate_id, CANDIDATE_ID)
        self.assertEqual(result.resolved_package.candidates[0].labor_norm_status, LABOR_UNRESOLVED)

    def test_08_candidate_count_preserved(self) -> None:
        items = [
            _candidate(candidate_id=CANDIDATE_ID, boq_code="BOQ-001"),
            _candidate(candidate_id=OTHER_ID, boq_code="BOQ-002"),
        ]
        package = _package(items)
        result = resolve_labor_norms(
            package,
            [_history(), _official(candidate_id=OTHER_ID, evidence_id="ev-other")],
        )
        self.assertEqual(len(result.resolutions), 2)
        self.assertEqual(result.resolved_package.candidate_count, 2)
        self.assertEqual(len(result.resolved_package.candidates), len(package.candidates))

    def test_09_zero_or_missing_price_does_not_remove_candidate(self) -> None:
        item = _candidate()
        self.assertNotIn("unit_price", item)
        package = _package([item])
        result = resolve_labor_norms(package, [])
        self.assertEqual(result.resolved_package.candidate_count, 1)
        self.assertFalse(hasattr(result.resolved_package.candidates[0], "unit_price"))

    def test_10_zero_norm_rejected(self) -> None:
        result = resolve_labor_norms(_package(), [_history(labor_hours_per_unit=0)])
        self.assertEqual(result.resolutions[0].status, LABOR_UNRESOLVED)
        self.assertIn(CODE_REJECTED_ZERO_NORM, result.resolutions[0].rejection_codes)

    def test_11_negative_norm_rejected(self) -> None:
        result = resolve_labor_norms(_package(), [_history(labor_hours_per_unit=-1.2)])
        self.assertEqual(result.resolutions[0].status, LABOR_UNRESOLVED)
        self.assertIn(CODE_REJECTED_NEGATIVE_NORM, result.resolutions[0].rejection_codes)

    def test_12_nan_and_inf_rejected(self) -> None:
        nan_result = resolve_labor_norms(_package(), [_history(labor_hours_per_unit=math.nan)])
        inf_result = resolve_labor_norms(_package(), [_history(labor_hours_per_unit=math.inf)])
        self.assertIn(CODE_REJECTED_NON_FINITE_NORM, nan_result.resolutions[0].rejection_codes)
        self.assertIn(CODE_REJECTED_NON_FINITE_NORM, inf_result.resolutions[0].rejection_codes)
        self.assertEqual(nan_result.resolutions[0].status, LABOR_UNRESOLVED)

    def test_13_incompatible_uom_rejected(self) -> None:
        result = resolve_labor_norms(_package(), [_history(unit="м")])
        self.assertEqual(result.resolutions[0].status, LABOR_UNRESOLVED)
        self.assertIn(CODE_REJECTED_INCOMPATIBLE_UNIT, result.resolutions[0].rejection_codes)

    def test_14_no_implicit_unit_conversion(self) -> None:
        result = resolve_labor_norms(_package(), [_history(unit="кг")])
        self.assertEqual(result.resolutions[0].status, LABOR_UNRESOLVED)
        self.assertIn(CODE_REJECTED_INCOMPATIBLE_UNIT, result.resolutions[0].rejection_codes)

    def test_15_missing_provenance_cannot_become_validated_or_provisional(self) -> None:
        result = resolve_labor_norms(_package(), [_history(source_reference="")])
        self.assertEqual(result.resolutions[0].status, LABOR_UNRESOLVED)
        self.assertIn(CODE_REJECTED_MISSING_PROVENANCE, result.resolutions[0].rejection_codes)

    def test_16_conflicting_same_priority_fails_closed(self) -> None:
        first = _history(evidence_id="ev-a", labor_hours_per_unit=1.42)
        second = _history(evidence_id="ev-b", labor_hours_per_unit=1.90)
        result = resolve_labor_norms(_package(), [first, second])
        resolution = result.resolutions[0]
        self.assertEqual(resolution.status, LABOR_UNRESOLVED)
        self.assertEqual(resolution.resolution_reason, REASON_AMBIGUOUS_LABOR_NORM_EVIDENCE)
        self.assertEqual(result.resolved_package.candidate_count, 1)
        self.assertIn("ev-a", resolution.ambiguity_evidence_ids)
        self.assertIn("ev-b", resolution.ambiguity_evidence_ids)

    def test_17_identical_duplicate_evidence_is_deterministic(self) -> None:
        first = _history(evidence_id="ev-dup-b", labor_hours_per_unit=1.42)
        second = _history(evidence_id="ev-dup-a", labor_hours_per_unit=1.42)
        result_ab = resolve_labor_norms(_package(), [first, second])
        result_ba = resolve_labor_norms(_package(), [second, first])
        self.assertEqual(result_ab.resolutions[0].status, LABOR_VALIDATED)
        self.assertEqual(result_ab.resolutions[0].labor_hours_per_unit, 1.42)
        self.assertEqual(result_ab.resolutions[0].resolution_reason, REASON_DUPLICATE_EVIDENCE_DEDUPLICATED)
        self.assertEqual(
            result_ab.resolutions[0].selected_evidence_id,
            result_ba.resolutions[0].selected_evidence_id,
        )
        self.assertEqual(result_ab.resolutions[0].selected_evidence_id, "ev-dup-a")

    def test_18_original_candidate_package_unchanged(self) -> None:
        package = _package()
        original_status = package.candidates[0].labor_norm_status
        original_ref = package.candidates[0].labor_norm_resolution_ref
        original_summary = package.labor_norm_summary
        result = resolve_labor_norms(package, [_history()])
        self.assertIsNot(result.resolved_package, package)
        self.assertEqual(package.candidates[0].labor_norm_status, original_status)
        self.assertEqual(package.candidates[0].labor_norm_resolution_ref, original_ref)
        self.assertEqual(package.labor_norm_summary, original_summary)
        self.assertEqual(package.package_id, result.package_id)
        self.assertEqual(result.resolved_package.candidates[0].labor_norm_status, LABOR_VALIDATED)

    def test_19_official_normative_is_not_observed_productivity(self) -> None:
        result = resolve_labor_norms(_package(), [_official()])
        resolution = result.resolutions[0]
        self.assertEqual(resolution.source_type, SOURCE_OFFICIAL_NORMATIVE)
        self.assertEqual(resolution.basis, BASIS_NORMATIVE_BENCHMARK)
        self.assertIsNone(resolution.observed_productivity)
        self.assertEqual(resolution.normative_benchmark, 2.10)
        self.assertIsNone(resolution.planning_norm)

    def test_20_historical_source_keeps_historical_semantics(self) -> None:
        result = resolve_labor_norms(_package(), [_history()])
        resolution = result.resolutions[0]
        self.assertEqual(resolution.source_type, SOURCE_PROJECT_HISTORY)
        self.assertEqual(resolution.basis, BASIS_OBSERVED_PRODUCTIVITY)
        self.assertEqual(resolution.observed_productivity, 1.42)
        self.assertIsNone(resolution.normative_benchmark)
        self.assertIn("PROJECT_HISTORY:", str(resolution.provenance))

    def test_21_paid_nonproductive_hours_cannot_become_planning_norm(self) -> None:
        paid = _history(hours_quality=HOURS_PAID_NONPRODUCTIVE)
        result = resolve_labor_norms(_package(), [paid])
        self.assertEqual(result.resolutions[0].status, LABOR_UNRESOLVED)
        self.assertIn(CODE_REJECTED_NONPRODUCTIVE_HOURS, result.resolutions[0].rejection_codes)

    def test_22_history_without_executed_quantity_is_inadmissible(self) -> None:
        incomplete = _history(executed_quantity_validated=False)
        result = resolve_labor_norms(_package(), [incomplete])
        self.assertEqual(result.resolutions[0].status, LABOR_UNRESOLVED)
        self.assertIn(
            CODE_REJECTED_HISTORY_WITHOUT_EXECUTED_QUANTITY,
            result.resolutions[0].rejection_codes,
        )

    def test_23_resolution_links_to_correct_candidate_identity(self) -> None:
        items = [
            _candidate(candidate_id=CANDIDATE_ID, boq_code="BOQ-001"),
            _candidate(candidate_id=OTHER_ID, boq_code="BOQ-002"),
        ]
        evidence = [
            _history(labor_hours_per_unit=1.42),
            _history(
                evidence_id="ev-other",
                candidate_id=OTHER_ID,
                labor_hours_per_unit=3.33,
                source_reference="other-history",
            ),
        ]
        result = resolve_labor_norms(_package(items), evidence)
        by_id = {item.candidate_id: item for item in result.resolutions}
        self.assertEqual(by_id[CANDIDATE_ID].labor_hours_per_unit, 1.42)
        self.assertEqual(by_id[OTHER_ID].labor_hours_per_unit, 3.33)
        self.assertEqual(by_id[CANDIDATE_ID].candidate_id, CANDIDATE_ID)
        self.assertNotEqual(by_id[CANDIDATE_ID].selected_evidence_id, by_id[OTHER_ID].selected_evidence_id)

    def test_24_package_id_and_provenance_preserved(self) -> None:
        package = _package()
        result = resolve_labor_norms(package, [_history()])
        self.assertEqual(result.package_id, package.package_id)
        self.assertEqual(result.resolved_package.package_id, package.package_id)
        self.assertEqual(result.resolved_package.provenance, package.provenance)
        self.assertEqual(result.resolved_package.mission_id, package.mission_id)
        self.assertEqual(
            result.resolved_package.candidates[0].labor_norm_resolution_ref,
            result.resolutions[0].resolution_id,
        )

    def test_25_validated_outranks_provisional_at_same_priority(self) -> None:
        provisional = _history(
            evidence_id="ev-prov",
            planning_use_status=LABOR_PROVISIONAL,
            labor_hours_per_unit=1.90,
        )
        validated = _history(
            evidence_id="ev-val",
            planning_use_status=LABOR_VALIDATED,
            labor_hours_per_unit=1.42,
        )
        result = resolve_labor_norms(_package(), [provisional, validated])
        self.assertEqual(result.resolutions[0].status, LABOR_VALIDATED)
        self.assertEqual(result.resolutions[0].labor_hours_per_unit, 1.42)

    def test_26_boq_code_alone_does_not_map_another_candidate(self) -> None:
        items = [
            _candidate(candidate_id=CANDIDATE_ID, boq_code="BOQ-001"),
            _candidate(candidate_id=OTHER_ID, boq_code="BOQ-001"),
        ]
        result = resolve_labor_norms(_package(items), [_history()])
        by_id = {item.candidate_id: item for item in result.resolutions}
        self.assertEqual(by_id[CANDIDATE_ID].status, LABOR_VALIDATED)
        self.assertEqual(by_id[OTHER_ID].status, LABOR_UNRESOLVED)


if __name__ == "__main__":
    unittest.main()
