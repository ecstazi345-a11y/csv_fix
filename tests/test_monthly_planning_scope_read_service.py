"""
MPO-002B tests — BOQ reality READ adapter (no live writes).

Run:
  C:\\csv_fix\\.venv\\Scripts\\python.exe -m unittest tests.test_monthly_planning_scope_read_service -v
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from services.monthly_planning_boq_service import _v2_resolve_scope_status_row
from services.monthly_planning_scope_read_service import (
    load_monthly_boq_reality,
    normalize_scope_raw_df,
    prepare_boq_reality_df,
)


def _view_row(**overrides: object) -> dict:
    row = {
        "project_code": "PRJ_001",
        "facility_building": "T1",
        "construction_discipline": "ELEC",
        "boq_code": "9000-00-16-007",
        "boq_name": "Physical work",
        "total_project_qty": 5.0,
        "executed_qty_all_time": 1.0,
        "unit_price": 10.0,
        "total_project_value": 50.0,
        "planning_remaining_qty": 4.0,
        "manual_executed_before_system": 0.0,
    }
    row.update(overrides)
    return row


class BoqRealityAdapterTests(unittest.TestCase):
    def test_normalize_maps_view_aliases(self) -> None:
        raw = pd.DataFrame([_view_row()])
        out = normalize_scope_raw_df(raw)
        self.assertEqual(out.iloc[0]["facility"], "T1")
        self.assertEqual(out.iloc[0]["discipline"], "ELEC")
        self.assertEqual(out.iloc[0]["boq_code"], "9000-00-16-007")
        self.assertEqual(float(out.iloc[0]["total_qty"]), 5.0)
        self.assertEqual(float(out.iloc[0]["executed_qty"]), 1.0)
        self.assertEqual(float(out.iloc[0]["not_required_qty"]), 0.0)

    def test_zero_price_physical_is_retained(self) -> None:
        raw = pd.DataFrame(
            [
                _view_row(
                    unit_price=0.0,
                    total_project_value=0.0,
                    total_project_qty=5.0,
                    executed_qty_all_time=0.0,
                    planning_remaining_qty=5.0,
                )
            ]
        )
        reality, meta = prepare_boq_reality_df(raw)
        self.assertEqual(len(reality), 1)
        self.assertFalse(meta["manual_not_required_adjustments_applied"])
        self.assertEqual(meta["scope_time_basis"], "all_time")
        row = reality.iloc[0]
        self.assertGreater(float(row["total_qty"]), 0.0)
        self.assertLessEqual(float(row["unit_price"]), 0.0)

    def test_completed_uses_frozen_status(self) -> None:
        raw = pd.DataFrame(
            [
                _view_row(
                    total_project_qty=10.0,
                    executed_qty_all_time=10.0,
                    planning_remaining_qty=0.0,
                    unit_price=2.0,
                    total_project_value=20.0,
                )
            ]
        )
        reality, _meta = prepare_boq_reality_df(raw)
        row = reality.iloc[0]
        self.assertEqual(_v2_resolve_scope_status_row(row), "Выполнено")
        self.assertEqual(float(row["remaining_qty"]), 0.0)
        self.assertEqual(float(row["available_to_add_qty"]), 0.0)
        self.assertGreaterEqual(float(row["executed_total_qty"]), float(row["total_qty"]))

    def test_blank_project_is_not_filled(self) -> None:
        raw = pd.DataFrame([_view_row(project_code="")])
        out = normalize_scope_raw_df(raw)
        self.assertEqual(out.iloc[0]["project_code"], "")

    def test_bare_bhk_project_is_blanked_not_remapped(self) -> None:
        raw = pd.DataFrame([_view_row(project_code="БХК")])
        out = normalize_scope_raw_df(raw)
        self.assertEqual(out.iloc[0]["project_code"], "")

    def test_header_row_without_physical_qty_is_dropped(self) -> None:
        raw = pd.DataFrame(
            [
                _view_row(
                    boq_code="HEADER",
                    total_project_qty=0.0,
                    executed_qty_all_time=0.0,
                    planning_remaining_qty=0.0,
                    unit_price=0.0,
                    total_project_value=0.0,
                )
            ]
        )
        reality, meta = prepare_boq_reality_df(raw)
        self.assertTrue(reality.empty)
        self.assertEqual(meta["excluded_invalid"], 1)

    def test_load_failure_returns_empty_and_error_meta(self) -> None:
        with patch(
            "services.monthly_planning_scope_read_service._fetch_scope_view",
            side_effect=RuntimeError("view down"),
        ):
            df, meta = load_monthly_boq_reality(project_code="PRJ_001")
        self.assertTrue(df.empty)
        self.assertIsNotNone(meta["error"])
        self.assertFalse(meta["manual_not_required_adjustments_applied"])
        self.assertEqual(meta["scope_time_basis"], "all_time")

    def test_no_forbidden_imports(self) -> None:
        import services.monthly_planning_scope_read_service as mod

        with open(mod.__file__, encoding="utf-8") as handle:
            src = handle.read()
        self.assertNotIn("import streamlit", src)
        self.assertNotIn("from streamlit", src)
        self.assertNotIn("from pages", src)
        self.assertNotIn("import pages", src)
        self.assertNotIn("ai_router", src.lower())
        self.assertNotIn("import openai", src)
        self.assertNotIn("langchain", src.lower())
        self.assertNotIn("langgraph", src.lower())


if __name__ == "__main__":
    unittest.main()
