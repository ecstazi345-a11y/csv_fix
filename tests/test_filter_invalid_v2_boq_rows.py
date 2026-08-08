"""
Unit tests for filter_invalid_v2_boq_rows and COMPLETED visibility (Constructor 10B).

No Streamlit page load. No product DB writes.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

import pandas as pd


PAGE_PATH = (
    Path(__file__).resolve().parents[1]
    / "pages"
    / "10B_Конструктор_месячного_плана.py"
)


def _load_fns(*names: str) -> dict:
    tree = ast.parse(PAGE_PATH.read_text(encoding="utf-8"))
    wanted = set(names)
    body = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    found = {node.name for node in body}
    missing = wanted - found
    if missing:
        raise RuntimeError(f"functions not found: {sorted(missing)}")
    # Constants referenced by status helpers
    const_assigns = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {
                    "V2_SCOPE_STATUS_NOT_REQUIRED",
                    "V2_SCOPE_STATUS_OVERRUN",
                }:
                    const_assigns.append(node)
    module = ast.Module(body=const_assigns + body, type_ignores=[])
    ns: dict = {"pd": pd, "Any": object}
    exec(compile(module, str(PAGE_PATH), "exec"), ns)
    return {name: ns[name] for name in names}


class FilterInvalidV2BoqRowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fns = _load_fns(
            "filter_invalid_v2_boq_rows",
            "_v2_safe_num",
            "_v2_value_per_unit_series",
            "_v2_resolve_available_status",
            "_v2_resolve_scope_status_row",
            "_v2_apply_boq_availability_metrics",
        )
        cls.fn = staticmethod(fns["filter_invalid_v2_boq_rows"])
        cls.resolve_status = staticmethod(fns["_v2_resolve_scope_status_row"])
        cls.apply_metrics = staticmethod(fns["_v2_apply_boq_availability_metrics"])
        # wire nested deps used by resolve/metrics into same ns already done via exec

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
