"""
Unit tests for filter_invalid_v2_boq_rows and COMPLETED visibility (Constructor 10B).

Imports the shared deterministic core from monthly_planning_boq_service (MPO-001A).
No Streamlit page load. No product DB writes.
"""

from __future__ import annotations

import unittest

import pandas as pd

from services.monthly_planning_boq_service import (
    _v2_apply_boq_availability_metrics,
    _v2_resolve_scope_status_row,
    filter_invalid_v2_boq_rows,
)


class FilterInvalidV2BoqRowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fn = staticmethod(filter_invalid_v2_boq_rows)
        cls.resolve_status = staticmethod(_v2_resolve_scope_status_row)
        cls.apply_metrics = staticmethod(_v2_apply_boq_availability_metrics)

    def _row(self, **kwargs) -> pd.DataFrame:
        base = {
            "boq_code": "X",
            "unit_price": 0.0,
            "total_value": 0.0,
            "remaining_qty": 0.0,
            "total_qty": 0.0,
        }
        base.update(kwargs)
        return pd.DataFrame([base])

    def test_t1_unit_price_keep(self) -> None:
        kept, excluded = self.fn(self._row(unit_price=10.0))
        self.assertEqual(len(kept), 1)
        self.assertEqual(excluded, 0)

    def test_t2_total_value_keep(self) -> None:
        kept, excluded = self.fn(self._row(total_value=100.0))
        self.assertEqual(len(kept), 1)
        self.assertEqual(excluded, 0)

    def test_t3_remaining_keep_when_price_value_zero(self) -> None:
        kept, excluded = self.fn(self._row(remaining_qty=2.0))
        self.assertEqual(len(kept), 1)
        self.assertEqual(excluded, 0)

    def test_t4_all_zero_drop(self) -> None:
        kept, excluded = self.fn(self._row())
        self.assertEqual(len(kept), 0)
        self.assertEqual(excluded, 1)

    def test_t5_007_survives(self) -> None:
        df = self._row(
            boq_code="9000-00-16-007",
            unit_price=0.0,
            total_value=0.0,
            remaining_qty=2.0,
            total_qty=2.0,
        )
        kept, excluded = self.fn(df)
        self.assertEqual(list(kept["boq_code"]), ["9000-00-16-007"])
        self.assertEqual(excluded, 0)

    def test_t6_008_survives(self) -> None:
        df = self._row(
            boq_code="9000-00-16-008",
            unit_price=0.0,
            total_value=0.0,
            remaining_qty=5.0,
            total_qty=5.0,
        )
        kept, excluded = self.fn(df)
        self.assertEqual(list(kept["boq_code"]), ["9000-00-16-008"])
        self.assertEqual(excluded, 0)

    def test_total_qty_keep_when_remaining_zero(self) -> None:
        kept, excluded = self.fn(
            self._row(total_qty=2.0, remaining_qty=0.0, unit_price=0.0, total_value=0.0)
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(excluded, 0)

    def test_planning_remaining_qty_alias(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "boq_code": "9000-00-16-007",
                    "unit_price": 0.0,
                    "total_value": 0.0,
                    "planning_remaining_qty": 2.0,
                }
            ]
        )
        kept, excluded = self.fn(df)
        self.assertEqual(len(kept), 1)
        self.assertEqual(excluded, 0)

    def test_total_project_qty_alias(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "boq_code": "9000-00-16-005",
                    "unit_price": 0.0,
                    "total_value": 0.0,
                    "total_project_qty": 2.0,
                }
            ]
        )
        kept, excluded = self.fn(df)
        self.assertEqual(len(kept), 1)
        self.assertEqual(excluded, 0)

    def _pipeline_status(self, **kwargs) -> tuple[pd.Series, str]:
        base = {
            "boq_code": "X",
            "total_qty": 0.0,
            "executed_qty": 0.0,
            "unit_price": 0.0,
            "total_value": 0.0,
            "already_planned_qty": 0.0,
            "not_required_qty": 0.0,
            "manual_executed_before_system": 0.0,
        }
        base.update(kwargs)
        df = pd.DataFrame([base])
        kept, _ = self.fn(df)
        self.assertEqual(len(kept), 1, msg="row must survive filter")
        met = self.apply_metrics(kept)
        status = self.resolve_status(met.iloc[0])
        return met.iloc[0], status

    def test_005_visible_completed_no_add(self) -> None:
        row, status = self._pipeline_status(
            boq_code="9000-00-16-005",
            total_qty=2.0,
            executed_qty=2.0,
            remaining_qty=0.0,
        )
        self.assertEqual(status, "Выполнено")
        self.assertEqual(_v2_safe_remaining(row), 0.0)
        self.assertEqual(float(row["available_to_add_qty"]), 0.0)

    def test_006_visible_completed_no_add(self) -> None:
        row, status = self._pipeline_status(
            boq_code="9000-00-16-006",
            total_qty=4.0,
            executed_qty=19.5,
            remaining_qty=0.0,
        )
        self.assertEqual(status, "Выполнено")
        self.assertEqual(_v2_safe_remaining(row), 0.0)
        self.assertEqual(float(row["available_to_add_qty"]), 0.0)

    def test_007_preserved_available(self) -> None:
        row, status = self._pipeline_status(
            boq_code="9000-00-16-007",
            total_qty=2.0,
            executed_qty=0.0,
            remaining_qty=2.0,
        )
        # metrics recompute remaining from total-executed
        self.assertGreater(float(row["remaining_qty"]), 0.0)
        self.assertEqual(status, "Доступно")
        self.assertGreater(float(row["available_to_add_qty"]), 0.0)

    def test_008_preserved_available(self) -> None:
        row, status = self._pipeline_status(
            boq_code="9000-00-16-008",
            total_qty=5.0,
            executed_qty=0.0,
            remaining_qty=5.0,
        )
        self.assertGreater(float(row["remaining_qty"]), 0.0)
        self.assertEqual(status, "Доступно")
        self.assertGreater(float(row["available_to_add_qty"]), 0.0)


def _v2_safe_remaining(row: pd.Series) -> float:
    return float(pd.to_numeric(row.get("remaining_qty"), errors="coerce") or 0.0)


if __name__ == "__main__":
    unittest.main()
