"""
Increment 1 — Constructor mission scope contract + binder.

Pure DataFrame tests. No Streamlit, Supabase, or product writes.
"""

from __future__ import annotations

import unittest

import pandas as pd

from agents.monthly_plan_constructor.mission_scope import (
    CODE_AMBIGUOUS_SCOPE,
    CODE_DATA_CONTRACT_BLOCKER,
    ConstructorMissionScope,
    MissionScopeError,
    assert_rows_belong_to_mission_scope,
    bind_scope_to_mission,
    build_constructor_mission_scope,
)

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
OTHER_PROJECT = "PRJ_OTHER"
OTHER_MONTH = "август-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "project_code": PROJECT,
        "month_key": MONTH,
        "facility": "Здание А",
        "facility_building": "Здание А",
        "discipline": "ОВ",
        "construction_discipline": "ОВ",
        "system": "SYS-1",
        "system_label": "SYS-1",
        "iwp": "IWP-1",
        "iwp_id": "IWP-1",
        "construction_queue": "Q1",
        "boq_code": "BOQ-001",
    }
    base.update(overrides)
    return base


def _frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _mission(**overrides: object) -> ConstructorMissionScope:
    payload: dict[str, object] = {
        "project_code": PROJECT,
        "month_key": MONTH,
    }
    payload.update(overrides)
    return build_constructor_mission_scope(**payload)  # type: ignore[arg-type]


class MissionContractTests(unittest.TestCase):
    def test_project_and_month_are_mandatory(self) -> None:
        with self.assertRaises(MissionScopeError) as blank_project:
            build_constructor_mission_scope(project_code="", month_key=MONTH)
        self.assertEqual(blank_project.exception.code, CODE_DATA_CONTRACT_BLOCKER)

        with self.assertRaises(MissionScopeError) as all_project:
            build_constructor_mission_scope(project_code="Все", month_key=MONTH)
        self.assertEqual(all_project.exception.code, CODE_DATA_CONTRACT_BLOCKER)

        with self.assertRaises(MissionScopeError) as blank_month:
            build_constructor_mission_scope(project_code=PROJECT, month_key="")
        self.assertEqual(blank_month.exception.code, CODE_DATA_CONTRACT_BLOCKER)

    def test_optional_all_none_empty_do_not_lift_project_month(self) -> None:
        for facility in (None, "", "ALL", [], ["ALL"]):
            scope = _mission(facility_scope=facility)
            self.assertIsNone(scope.facility_scope)
            self.assertEqual(scope.project_code, PROJECT.upper())
            self.assertEqual(scope.month_key_canonical, "2026-09")

    def test_optional_specific_values_are_normalized_not_fuzzy(self) -> None:
        scope = _mission(facility_scope="  facility_target  ", discipline_scope=["Вентиляция"])
        self.assertEqual(scope.facility_scope, ("FACILITY_TARGET",))
        self.assertEqual(scope.discipline_scope, ("ВЕНТИЛЯЦИЯ",))


class BinderHardBoundaryTests(unittest.TestCase):
    def test_1_project_month_only_keeps_requested_slice(self) -> None:
        df = _frame(
            [
                _row(boq_code="IN"),
                _row(project_code=OTHER_PROJECT, boq_code="OTHER-PRJ"),
                _row(month_key=OTHER_MONTH, boq_code="OTHER-MO"),
                _row(boq_code="IN-2", facility="Другой объект", discipline="Вентиляция"),
            ]
        )
        scoped = bind_scope_to_mission(df, _mission())
        self.assertEqual(sorted(scoped["boq_code"].tolist()), ["IN", "IN-2"])
        self.assertTrue((scoped["project_code"] == PROJECT).all())
        self.assertTrue((scoped["month_key"] == MONTH).all())

    def test_2_facility_scope(self) -> None:
        df = _frame(
            [
                _row(facility="A", facility_building="A", boq_code="A1"),
                _row(facility="B", facility_building="B", boq_code="B1"),
            ]
        )
        scoped = bind_scope_to_mission(df, _mission(facility_scope="A"))
        self.assertEqual(scoped["boq_code"].tolist(), ["A1"])

    def test_3_discipline_scope(self) -> None:
        df = _frame(
            [
                _row(discipline="ОВ", construction_discipline="ОВ", boq_code="OV"),
                _row(
                    discipline=DISCIPLINE_VENT,
                    construction_discipline=DISCIPLINE_VENT,
                    boq_code="VENT",
                ),
            ]
        )
        scoped = bind_scope_to_mission(df, _mission(discipline_scope=DISCIPLINE_VENT))
        self.assertEqual(scoped["boq_code"].tolist(), ["VENT"])

    def test_4_facility_and_discipline_intersection(self) -> None:
        df = _frame(
            [
                _row(
                    facility=FACILITY_TARGET,
                    facility_building=FACILITY_TARGET,
                    discipline=DISCIPLINE_VENT,
                    construction_discipline=DISCIPLINE_VENT,
                    boq_code="HIT",
                ),
                _row(
                    facility=FACILITY_TARGET,
                    facility_building=FACILITY_TARGET,
                    discipline="ОВ",
                    construction_discipline="ОВ",
                    boq_code="FAC-ONLY",
                ),
                _row(
                    facility="OTHER",
                    facility_building="OTHER",
                    discipline=DISCIPLINE_VENT,
                    construction_discipline=DISCIPLINE_VENT,
                    boq_code="DISC-ONLY",
                ),
            ]
        )
        scoped = bind_scope_to_mission(
            df,
            _mission(facility_scope=FACILITY_TARGET, discipline_scope=DISCIPLINE_VENT),
        )
        self.assertEqual(scoped["boq_code"].tolist(), ["HIT"])

    def test_5_system_scope(self) -> None:
        df = _frame(
            [
                _row(system="SYS-1", system_label="SYS-1", boq_code="S1"),
                _row(system="SYS-2", system_label="SYS-2", boq_code="S2"),
            ]
        )
        scoped = bind_scope_to_mission(df, _mission(system_scope="SYS-2"))
        self.assertEqual(scoped["boq_code"].tolist(), ["S2"])

    def test_6_iwp_scope(self) -> None:
        df = _frame(
            [
                _row(iwp="IWP-1", iwp_id="IWP-1", boq_code="I1"),
                _row(iwp="IWP-9", iwp_id="IWP-9", boq_code="I9"),
            ]
        )
        scoped = bind_scope_to_mission(df, _mission(iwp_scope="IWP-9"))
        self.assertEqual(scoped["boq_code"].tolist(), ["I9"])

    def test_7_queue_scope(self) -> None:
        df = _frame(
            [
                _row(construction_queue="Q1", boq_code="Q1"),
                _row(construction_queue="Q2", boq_code="Q2"),
            ]
        )
        scoped = bind_scope_to_mission(df, _mission(queue_scope="Q2"))
        self.assertEqual(scoped["boq_code"].tolist(), ["Q2"])

    def test_8_unknown_facility_does_not_expand(self) -> None:
        df = _frame(
            [
                _row(facility="A", facility_building="A", boq_code="A1"),
                _row(facility="B", facility_building="B", boq_code="B1"),
            ]
        )
        scoped = bind_scope_to_mission(df, _mission(facility_scope="UNKNOWN_FACILITY"))
        self.assertEqual(len(scoped), 0)
        self.assertNotEqual(len(scoped), len(df))

    def test_9_requested_queue_column_absent_fail_closed(self) -> None:
        df = _frame([_row()]).drop(columns=["construction_queue"])
        with self.assertRaises(MissionScopeError) as raised:
            bind_scope_to_mission(df, _mission(queue_scope="Q1"))
        self.assertEqual(raised.exception.code, CODE_AMBIGUOUS_SCOPE)

    def test_9b_requested_facility_column_absent_fail_closed(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "project_code": PROJECT,
                    "month_key": MONTH,
                    "boq_code": "X",
                }
            ]
        )
        with self.assertRaises(MissionScopeError) as raised:
            bind_scope_to_mission(df, _mission(facility_scope="A"))
        self.assertEqual(raised.exception.code, CODE_AMBIGUOUS_SCOPE)

    def test_10_wrong_project_never_passes(self) -> None:
        df = _frame(
            [
                _row(project_code=OTHER_PROJECT, boq_code="LEAK"),
                _row(boq_code="OK"),
            ]
        )
        scoped = bind_scope_to_mission(df, _mission())
        self.assertEqual(scoped["boq_code"].tolist(), ["OK"])
        self.assertFalse((scoped["project_code"] == OTHER_PROJECT).any())

    def test_11_wrong_month_never_passes(self) -> None:
        df = _frame(
            [
                _row(month_key=OTHER_MONTH, boq_code="LEAK"),
                _row(month_key="2026-09", boq_code="CANONICAL-HIT"),
            ]
        )
        scoped = bind_scope_to_mission(df, _mission())
        self.assertEqual(scoped["boq_code"].tolist(), ["CANONICAL-HIT"])
        self.assertFalse((scoped["month_key"] == OTHER_MONTH).any())

    def test_12_all_facility_still_bound_by_project_and_month(self) -> None:
        df = _frame(
            [
                _row(facility="A", facility_building="A", boq_code="IN-A"),
                _row(facility="B", facility_building="B", boq_code="IN-B"),
                _row(project_code=OTHER_PROJECT, boq_code="OTHER-PRJ"),
                _row(month_key=OTHER_MONTH, boq_code="OTHER-MO"),
            ]
        )
        scoped = bind_scope_to_mission(df, _mission(facility_scope="ALL"))
        self.assertEqual(sorted(scoped["boq_code"].tolist()), ["IN-A", "IN-B"])
        self.assertTrue((scoped["project_code"] == PROJECT).all())
        self.assertTrue((scoped["month_key"] == MONTH).all())

    def test_13_input_dataframe_is_not_mutated(self) -> None:
        df = _frame([_row(boq_code="A"), _row(project_code=OTHER_PROJECT, boq_code="B")])
        before = df.copy(deep=True)
        scoped = bind_scope_to_mission(df, _mission())
        pd.testing.assert_frame_equal(df, before)
        scoped.loc[0, "project_code"] = "HACKED"
        pd.testing.assert_frame_equal(df, before)

    def test_14_post_bind_invariant_rejects_out_of_scope_row(self) -> None:
        leaking = _frame(
            [
                _row(boq_code="OK"),
                _row(project_code=OTHER_PROJECT, boq_code="LEAK"),
            ]
        )
        with self.assertRaises(MissionScopeError) as raised:
            assert_rows_belong_to_mission_scope(leaking, _mission())
        self.assertEqual(raised.exception.code, CODE_DATA_CONTRACT_BLOCKER)

        scoped = bind_scope_to_mission(leaking, _mission())
        assert_rows_belong_to_mission_scope(scoped, _mission())
        self.assertEqual(scoped["boq_code"].tolist(), ["OK"])

    def test_missing_project_or_month_columns_fail_closed(self) -> None:
        df = pd.DataFrame([{"facility": "A", "boq_code": "X"}])
        with self.assertRaises(MissionScopeError) as raised:
            bind_scope_to_mission(df, _mission())
        self.assertEqual(raised.exception.code, CODE_DATA_CONTRACT_BLOCKER)


class Mpca003RegressionTests(unittest.TestCase):
    def test_scoped_mission_does_not_scan_whole_project(self) -> None:
        target_n = 17
        total_n = 447
        rows: list[dict[str, object]] = []
        for i in range(target_n):
            rows.append(
                _row(
                    facility=FACILITY_TARGET,
                    facility_building=FACILITY_TARGET,
                    discipline=DISCIPLINE_VENT,
                    construction_discipline=DISCIPLINE_VENT,
                    boq_code=f"T{i:03d}",
                )
            )
        fillers = total_n - target_n
        facilities = ("Здание А", "Здание Б", FACILITY_TARGET)
        disciplines = ("ОВ", "ЭОМ", DISCIPLINE_VENT)
        for i in range(fillers):
            facility = facilities[i % 3]
            discipline = disciplines[(i // 3) % 3]
            if facility == FACILITY_TARGET and discipline == DISCIPLINE_VENT:
                facility = "Здание А"
            rows.append(
                _row(
                    facility=facility,
                    facility_building=facility,
                    discipline=discipline,
                    construction_discipline=discipline,
                    boq_code=f"F{i:03d}",
                )
            )
        df = _frame(rows)
        self.assertEqual(len(df), 447)

        scoped = bind_scope_to_mission(
            df,
            _mission(facility_scope=FACILITY_TARGET, discipline_scope=DISCIPLINE_VENT),
        )
        self.assertEqual(len(scoped), 17)
        self.assertNotEqual(len(scoped), 447)
        self.assertTrue((scoped["facility"] == FACILITY_TARGET).all())
        self.assertTrue((scoped["discipline"] == DISCIPLINE_VENT).all())
        self.assertTrue((scoped["project_code"] == PROJECT).all())
        self.assertTrue((scoped["month_key"] == MONTH).all())


if __name__ == "__main__":
    unittest.main()
