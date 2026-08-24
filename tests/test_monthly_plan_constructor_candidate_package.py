"""
Increment 2 — Constructor Candidate Package artifact.

Pure domain tests. No Streamlit, Supabase, or product writes.
"""

from __future__ import annotations

import copy
import dataclasses
import uuid
import unittest

import pandas as pd

from agents.monthly_plan_constructor.candidate_package import (
    CODE_DATA_CONTRACT_BLOCKER,
    SCHEMA_VERSION,
    CandidatePackage,
    CandidatePackageError,
    CandidateRecord,
    LABOR_UNRESOLVED,
    build_candidate_package,
)
from agents.monthly_plan_constructor.mission_scope import (
    ConstructorMissionScope,
    build_constructor_mission_scope,
)

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
OTHER_PROJECT = "PRJ_OTHER"
OTHER_MONTH = "август-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"
MISSION_ID = "mission-increment-2"


def _mission(**overrides: object) -> ConstructorMissionScope:
    payload: dict[str, object] = {
        "project_code": PROJECT,
        "month_key": MONTH,
    }
    payload.update(overrides)
    return build_constructor_mission_scope(**payload)  # type: ignore[arg-type]


def _candidate(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "candidate_id": "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001",
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
    *,
    scope: ConstructorMissionScope | None = None,
    scanned_count: int | None = None,
    **kwargs: object,
) -> CandidatePackage:
    items = candidates if candidates is not None else [_candidate()]
    return build_candidate_package(
        scope or _mission(),
        items,
        mission_id=MISSION_ID,
        scanned_count=len(items) if scanned_count is None else scanned_count,
        **kwargs,  # type: ignore[arg-type]
    )


class CandidatePackageBuilderTests(unittest.TestCase):
    def test_1_build_valid_package(self) -> None:
        package = _package()
        self.assertIsInstance(package, CandidatePackage)
        self.assertEqual(len(package.candidates), 1)
        self.assertEqual(package.mission_id, MISSION_ID)
        self.assertEqual(package.project_code, PROJECT.upper())
        self.assertEqual(package.month_key, MONTH)

    def test_2_package_project_month_match_mission(self) -> None:
        package = _package()
        self.assertEqual(package.project_code, package.scope.project_code)
        self.assertEqual(package.month_key, package.scope.month_key)
        self.assertEqual(package.candidates[0].project_code, PROJECT)
        self.assertEqual(package.candidates[0].month_key, MONTH)

    def test_3_facility_scope_enforced(self) -> None:
        scope = _mission(facility_scope=FACILITY_TARGET)
        package = _package(scope=scope)
        self.assertEqual(package.candidates[0].facility, FACILITY_TARGET)
        outsider = [_candidate(facility="OTHER_FAC", candidate_id="X|OTHER|BOQ")]
        with self.assertRaises(CandidatePackageError) as raised:
            _package(outsider, scope=scope)
        self.assertEqual(raised.exception.code, CODE_DATA_CONTRACT_BLOCKER)

    def test_4_discipline_scope_enforced(self) -> None:
        scope = _mission(discipline_scope=DISCIPLINE_VENT)
        package = _package(scope=scope)
        self.assertEqual(package.candidates[0].discipline, DISCIPLINE_VENT)
        outsider = [
            _candidate(
                discipline="ОВ",
                candidate_id="X|VENT|OV|BOQ",
            )
        ]
        with self.assertRaises(CandidatePackageError):
            _package(outsider, scope=scope)

    def test_5_candidate_outside_mission_fails_closed(self) -> None:
        with self.assertRaises(CandidatePackageError):
            _package(
                [_candidate(project_code=OTHER_PROJECT, candidate_id="LEAK")],
                scope=_mission(facility_scope=FACILITY_TARGET),
            )

    def test_6_candidate_count_equals_len_candidates(self) -> None:
        items = [
            _candidate(boq_code="BOQ-001", candidate_id="C1"),
            _candidate(boq_code="BOQ-002", candidate_id="C2"),
        ]
        package = _package(items, scanned_count=40)
        self.assertEqual(package.candidate_count, 2)
        self.assertEqual(package.summary.candidate_count, len(package.candidates))

    def test_7_empty_candidate_package_is_valid(self) -> None:
        package = _package([], scanned_count=12, excluded_no_remainder_count=12)
        self.assertEqual(package.candidate_count, 0)
        self.assertEqual(package.candidates, ())
        self.assertEqual(package.summary.scanned_count, 12)

    def test_8_zero_price_does_not_invalidate_physical_candidate(self) -> None:
        item = _candidate()
        self.assertNotIn("unit_price", item)
        package = _package([item])
        self.assertEqual(len(package.candidates), 1)
        self.assertFalse(hasattr(package.candidates[0], "unit_price"))
        self.assertEqual(package.candidates[0].available_to_add_qty, 10.0)

    def test_9_unresolved_labor_norm_does_not_remove_candidate(self) -> None:
        package = _package([_candidate(labor_norm_status=LABOR_UNRESOLVED)])
        self.assertEqual(len(package.candidates), 1)
        self.assertEqual(package.candidates[0].labor_norm_status, LABOR_UNRESOLVED)
        self.assertEqual(package.labor_norm_summary.unresolved, 1)
        self.assertEqual(package.labor_norm_summary.validated, 0)

    def test_10_package_does_not_require_crew(self) -> None:
        package = _package()
        names = {item.name for item in dataclasses.fields(CandidateRecord)}
        self.assertNotIn("crew", names)
        self.assertNotIn("proposed_crew", names)
        self.assertFalse(hasattr(package.candidates[0], "crew"))

    def test_11_package_does_not_require_approved_commitment_qty(self) -> None:
        package = _package()
        names = {item.name for item in dataclasses.fields(CandidateRecord)}
        self.assertNotIn("approved_qty", names)
        self.assertNotIn("approved_commitment_qty", names)
        self.assertNotIn("feasible_qty", names)
        self.assertNotIn("planned_qty", names)
        self.assertEqual(package.candidates[0].available_to_add_qty, 10.0)

    def test_12_input_candidate_collection_not_mutated(self) -> None:
        items = [_candidate()]
        before = copy.deepcopy(items)
        package = _package(items)
        self.assertEqual(items, before)
        items[0]["available_to_add_qty"] = 99.0
        self.assertEqual(package.candidates[0].available_to_add_qty, 10.0)

    def test_13_package_identity_is_uuid_and_frozen(self) -> None:
        first = _package()
        second = _package()
        uuid.UUID(first.package_id)
        uuid.UUID(second.package_id)
        self.assertNotEqual(first.package_id, second.package_id)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            first.package_id = "mutated"  # type: ignore[misc]

    def test_14_schema_version_present(self) -> None:
        package = _package()
        self.assertEqual(package.schema_version, SCHEMA_VERSION)
        self.assertEqual(package.schema_version, "1.0")

    def test_15_provenance_present(self) -> None:
        package = _package(
            snapshot_id="snap-1",
            created_at="2026-09-01T00:00:00Z",
        )
        self.assertEqual(package.provenance.mission_id, MISSION_ID)
        self.assertEqual(package.provenance.snapshot_id, "snap-1")
        self.assertEqual(package.provenance.agent_code, "MONTHLY_PLAN_CONSTRUCTOR")
        self.assertEqual(package.provenance.agent_version, "0.1")
        self.assertEqual(package.provenance.created_at, "2026-09-01T00:00:00Z")
        self.assertEqual(package.created_at, package.provenance.created_at)

    def test_16_no_dataframe_in_public_artifact(self) -> None:
        package = _package()
        self.assertNotIsInstance(package, pd.DataFrame)
        self.assertIsInstance(package.candidates, tuple)
        self.assertNotIsInstance(package.candidates, pd.DataFrame)
        for item in dataclasses.fields(package):
            value = getattr(package, item.name)
            self.assertFalse(isinstance(value, pd.DataFrame), item.name)
        reference = package.as_reference()
        self.assertEqual(reference.package_id, package.package_id)
        self.assertEqual(reference.candidate_count, 1)
        self.assertFalse(hasattr(reference, "candidates"))

    def test_17_mixed_project_rows_fail_closed(self) -> None:
        items = [
            _candidate(candidate_id="OK"),
            _candidate(project_code=OTHER_PROJECT, candidate_id="LEAK"),
        ]
        with self.assertRaises(CandidatePackageError) as raised:
            _package(items)
        self.assertEqual(raised.exception.code, CODE_DATA_CONTRACT_BLOCKER)

    def test_18_mixed_month_rows_fail_closed(self) -> None:
        items = [
            _candidate(candidate_id="OK"),
            _candidate(month_key=OTHER_MONTH, candidate_id="LEAK-MO"),
        ]
        with self.assertRaises(CandidatePackageError):
            _package(items)

    def test_19_optional_all_stays_inside_project_month(self) -> None:
        items = [
            _candidate(
                facility="A",
                discipline="ОВ",
                boq_code="A1",
                candidate_id="C-A",
            ),
            _candidate(
                facility="B",
                discipline=DISCIPLINE_VENT,
                boq_code="B1",
                candidate_id="C-B",
            ),
        ]
        package = _package(items, scope=_mission(facility_scope="ALL"))
        self.assertEqual(package.candidate_count, 2)
        leak = items + [
            _candidate(
                project_code=OTHER_PROJECT,
                facility="A",
                candidate_id="C-LEAK",
            )
        ]
        with self.assertRaises(CandidatePackageError):
            _package(leak, scope=_mission(facility_scope="ALL"))

    def test_20_package_summary_invariant(self) -> None:
        items = [
            _candidate(boq_code="BOQ-001", candidate_id="C1"),
            _candidate(boq_code="BOQ-002", candidate_id="C2"),
        ]
        package = _package(
            items,
            scanned_count=30,
            excluded_completed_count=10,
            excluded_no_remainder_count=8,
            already_planned_count=10,
        )
        self.assertEqual(package.summary.candidate_count, 2)
        self.assertEqual(package.summary.candidate_count, len(package.candidates))
        self.assertEqual(package.summary.scanned_count, 30)
        self.assertEqual(package.summary.excluded_completed_count, 10)
        self.assertEqual(package.summary.excluded_no_remainder_count, 8)
        self.assertEqual(package.summary.already_planned_count, 10)
        with self.assertRaises(CandidatePackageError):
            _package(items, scanned_count=1)


if __name__ == "__main__":
    unittest.main()
