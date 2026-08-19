"""
Page 12 person-month fund / required capacity KPI — focused tests.

No product DB writes.
Run: python -m unittest tests.test_page12_person_month_kpi -v
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pandas as pd


PAGE_PATH = (
    Path(__file__).resolve().parents[1]
    / "pages"
    / "12_Planning_Паспорт_месяца.py"
)


class _SessionState(dict):
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


def _cache_data_stub(*args: Any, **kwargs: Any) -> Any:
    def decorator(fn: Any) -> Any:
        fn.clear = lambda: None  # type: ignore[attr-defined]
        return fn

    if args and callable(args[0]) and not kwargs:
        return decorator(args[0])
    return decorator


def _install_streamlit_stub() -> ModuleType:
    st = ModuleType("streamlit")
    st.session_state = _SessionState()
    st.set_page_config = lambda **kwargs: None
    st.cache_data = _cache_data_stub
    st.cache_resource = _cache_data_stub
    st.markdown = lambda *a, **k: None
    st.caption = lambda *a, **k: None
    st.info = lambda *a, **k: None
    st.warning = lambda *a, **k: None
    st.error = lambda *a, **k: None
    st.success = lambda *a, **k: None
    st.button = lambda *a, **k: False
    st.title = lambda *a, **k: None
    st.dataframe = lambda *a, **k: None
    st.columns = lambda n: [MagicMock() for _ in range(n if not isinstance(n, list) else len(n))]
    st.rerun = lambda: None
    st.expander = MagicMock()
    sys.modules["streamlit"] = st
    return st


def _load_page() -> ModuleType:
    for key in list(sys.modules):
        if key == "streamlit" or key.startswith("page12_person_month"):
            del sys.modules[key]
    _install_streamlit_stub()
    spec = importlib.util.spec_from_file_location("page12_person_month_kpi_test", PAGE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["page12_person_month_kpi_test"] = mod
    spec.loader.exec_module(mod)
    return mod


class Page12PersonMonthKpiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_page()

    def test_1_fund_from_full_worker(self) -> None:
        fund = self.mod.derive_person_month_fund_hours(
            [{"lab_hours_month": 216, "lab_fte_month": 1.0}]
        )
        self.assertIsNotNone(fund)
        self.assertAlmostEqual(fund or 0.0, 216.0, places=6)

    def test_2_partial_worker_is_not_fund_152(self) -> None:
        candidate = self.mod.candidate_full_month_hours(152, 0.704)
        self.assertIsNotNone(candidate)
        self.assertAlmostEqual(candidate or 0.0, 152 / 0.704, places=6)
        self.assertGreater(candidate or 0.0, 200.0)
        self.assertNotAlmostEqual(candidate or 0.0, 152.0, places=1)

        fund = self.mod.derive_person_month_fund_hours(
            [
                {"lab_hours_month": 216, "lab_fte_month": 1.0},
                {"lab_hours_month": 152, "lab_fte_month": 0.704},
            ]
        )
        self.assertIsNotNone(fund)
        self.assertAlmostEqual(fund or 0.0, 216.0, delta=1.0)
        self.assertNotAlmostEqual(fund or 0.0, 152.0, places=1)

    def test_3_required_person_months_1000_over_216(self) -> None:
        value = self.mod.required_person_months(1000, 216)
        self.assertIsNotNone(value)
        self.assertAlmostEqual(value or 0.0, 1000 / 216, places=6)
        self.assertEqual(self.mod.kpi_person_months_display(value), "4,63 чел.-мес.")

    def test_4_crew_size_ignored_for_person_months(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "boq_code": "A",
                    "plan_value_num": 1.0,
                    "required_hours_num": 1000.0,
                    "labor_cost_num": 1.0,
                    "planned_qty_num": 1.0,
                    "is_risk": False,
                    "admission_status": "APPROVED_TO_EXECUTE",
                    "crew_label": "АСИ-10",
                    "crew_size": 35,
                }
            ]
        )
        summary = self.mod.compute_passport_summary(df)
        self.assertEqual(summary["total_hours"], 1000.0)
        person_months = self.mod.required_person_months(summary["total_hours"], 216)
        self.assertAlmostEqual(person_months or 0.0, 1000 / 216, places=6)
        self.assertNotEqual(round(person_months or 0.0), 35)
        self.assertNotEqual(self.mod.kpi_person_months_display(person_months), "35 чел.")

    def test_5_missing_fund_no_fallback(self) -> None:
        self.assertIsNone(self.mod.derive_person_month_fund_hours([]))
        self.assertIsNone(self.mod.derive_person_month_fund_hours(pd.DataFrame()))
        self.assertIsNone(self.mod.required_person_months(1000, None))
        self.assertIsNone(self.mod.required_person_months(1000, 0))
        self.assertEqual(self.mod.kpi_fund_hours_display(None), "—")
        self.assertEqual(self.mod.kpi_person_months_display(None), "—")
        self.assertIsNone(self.mod.person_month_formula_caption(1000, None, None))

    def test_month_normalization_matches_english_mls_key(self) -> None:
        labor = pd.DataFrame(
            [
                {
                    "project_code": "PRJ_001_БХК",
                    "month_key": "August-2026",
                    "lab_hours_month": 216,
                    "lab_fte_month": 1.0,
                }
            ]
        )
        scoped = self.mod.filter_labor_rows_for_person_month_fund(
            labor, project="PRJ_001_БХК", month="август-2026"
        )
        self.assertEqual(len(scoped), 1)
        all_month = self.mod.filter_labor_rows_for_person_month_fund(
            labor, project="PRJ_001_БХК", month="Все"
        )
        self.assertTrue(all_month.empty)


if __name__ == "__main__":
    unittest.main()
