"""
R1.6A+B focused tests: monthly commitment qty gate.

No product DB writes. Page23 apply/cancel are mocked at the RPC boundary.
Run: .\\.venv\\Scripts\\python.exe -m unittest tests.test_r16_commitment_gate -v
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from types import ModuleType
from typing import Any, Dict
from unittest.mock import patch

import pandas as pd

from services.monthly_plan_management_decisions import (
    COMMITMENT_PAYLOAD_KEYS,
    MSG_COMMITMENT_FEASIBLE_MISSING,
    MSG_COMMITMENT_OVER_FEASIBLE,
    build_commitment_snapshots,
    merge_commitment_payload,
    optional_float,
    validate_approved_commitment_qty,
)
from services.monthly_plan_resource_economic_service import (
    theoretical_feasible_qty_by_plan_line,
)
from tests.test_page22_resource_economic_gate import _capacity, _line
from tests.test_wr2_decision_form_hydrate import (
    PAGE_PATH,
    _install_streamlit_stub,
)


PID = "11111111-1111-1111-1111-111111111111"
PID_NULL = "22222222-2222-2222-2222-222222222222"


def _load_page() -> ModuleType:
    for key in list(sys.modules):
        if (
            key == "streamlit"
            or key.startswith("wr2_page23_r16_test")
            or key == "services.monthly_plan_management_decisions"
        ):
            del sys.modules[key]
    st = _install_streamlit_stub()
    spec = importlib.util.spec_from_file_location("wr2_page23_r16_test", PAGE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wr2_page23_r16_test"] = mod
    spec.loader.exec_module(mod)
    mod.st = st  # type: ignore[attr-defined]
    return mod


def _board_row(**extra: Any) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "plan_line_id": PID,
        "project_code": "TEST_MGMT",
        "month_key": "тест-2026",
        "boq_code": "2041-02-06-01",
        "boq_name": "Test BOQ",
        "outcome": "OK",
        "unit": "м",
        "unit_of_measure": "м",
        "planned_qty": 397.0,
        "unit_price": 1000.0,
        "plan_value_num": 397000.0,
        "plan_value": 397000.0,
        "labor_hours": 80.0,
        "labor_rate_per_hour": 3000.0,
        "crew": "АСИ-10",
        "crew_code": "АСИ-10",
        "blocking_departments": "",
    }
    row.update(extra)
    return row


class R16CommitmentHelpersTests(unittest.TestCase):
    def test_t1_old_payload_omits_qty_keys(self) -> None:
        payload = {
            "decision_basis": "BASIS",
            "responsible_person": "R",
            "decision_comment": "",
            "review_deadline": "",
        }
        merged = merge_commitment_payload(payload, None)
        for key in COMMITMENT_PAYLOAD_KEYS:
            self.assertNotIn(key, merged)

    def test_t4_validation_rejects_over_feasible_and_missing(self) -> None:
        self.assertEqual(
            validate_approved_commitment_qty(200, 145),
            MSG_COMMITMENT_OVER_FEASIBLE,
        )
        self.assertEqual(
            validate_approved_commitment_qty(10, None),
            MSG_COMMITMENT_FEASIBLE_MISSING,
        )
        self.assertIsNone(validate_approved_commitment_qty(None, 145))
        self.assertIsNone(validate_approved_commitment_qty(0, 145))
        self.assertIsNone(validate_approved_commitment_qty(130, 145))

    def test_t5_snapshot_does_not_replace_requested(self) -> None:
        planned_qty = 568.0
        row = pd.Series({"planned_qty": planned_qty})
        snapshots = build_commitment_snapshots(
            requested_qty=row.get("planned_qty"),
            feasible_qty=145,
            approved_commitment_qty=130,
            unit_price=10,
            labor_hours=700,
            labor_rate_per_hour=3000,
        )
        assert snapshots is not None
        self.assertEqual(row.get("planned_qty"), planned_qty)
        self.assertEqual(snapshots["requested_qty_snapshot"], planned_qty)
        self.assertEqual(snapshots["approved_commitment_qty"], 130)
        self.assertNotEqual(snapshots["approved_commitment_qty"], planned_qty)

    def test_t6_scale_work_value_hours_labor_cost(self) -> None:
        snapshots = build_commitment_snapshots(
            requested_qty=568,
            feasible_qty=145,
            approved_commitment_qty=130,
            unit_price=2500,
            plan_value=568 * 2500,
            labor_hours=700,
            labor_rate_per_hour=3000,
        )
        assert snapshots is not None
        self.assertAlmostEqual(snapshots["committed_work_value"] or 0, 130 * 2500)
        self.assertAlmostEqual(snapshots["committed_required_hours"] or 0, 700 * 130 / 568)
        self.assertAlmostEqual(
            snapshots["committed_labor_cost"] or 0,
            (700 * 130 / 568) * 3000,
        )

    def test_t6_no_divide_when_requested_qty_zero(self) -> None:
        snapshots = build_commitment_snapshots(
            requested_qty=0,
            feasible_qty=0,
            approved_commitment_qty=10,
            unit_price=None,
            plan_value=100,
            labor_hours=50,
            labor_rate_per_hour=3000,
        )
        assert snapshots is not None
        self.assertIsNone(snapshots["committed_work_value"])
        self.assertIsNone(snapshots["committed_required_hours"])
        self.assertIsNone(snapshots["committed_labor_cost"])

    def test_feasible_helper_reuses_line_model(self) -> None:
        lines = pd.DataFrame([_line("L1", "E-01", 568, 700)])
        capacity = pd.DataFrame([_capacity("E-01", 330)])
        mapping = theoretical_feasible_qty_by_plan_line(lines, capacity)
        self.assertIn("L1", mapping)
        self.assertAlmostEqual(mapping["L1"] or 0, 568 * (330 / 700), places=2)


class R16Page23CommitmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_page()
        self.st = self.mod.st
        self.st.session_state.clear()
        self.mod.wr2_init_passport_session()
        self.st.session_state[self.mod.WR2_SESSION_MGMT_SCOPE] = "TEST_MGMT|тест-2026"
        self.st.session_state["passport_created_by"] = "Tester"

    def tearDown(self) -> None:
        self.st.session_state.clear()
        for key in list(sys.modules):
            if key == "streamlit" or key.startswith("wr2_page23_r16_test"):
                del sys.modules[key]

    def test_t1_old_apply_without_qty_still_works(self) -> None:
        row = pd.Series(_board_row())
        with patch.object(
            self.mod,
            "apply_management_decision",
            return_value={"ok": True, "data": {"status": "inserted"}},
        ) as mock_apply, patch.object(
            self.mod,
            "load_management_decisions",
            return_value=[],
        ), patch.object(
            self.mod,
            "wr2_current_feasible_qty",
            return_value=240.0,
        ) as mock_feasible:
            errors = self.mod.wr2_apply_management_decision(
                row,
                self.mod.WR2_MGMT_INCLUDE,
                basis="BASIS",
                responsible="R",
                review_deadline="",
                comment="",
            )
        self.assertEqual(errors, [])
        mock_feasible.assert_not_called()
        payload = mock_apply.call_args.kwargs["payload"]
        for key in COMMITMENT_PAYLOAD_KEYS:
            self.assertNotIn(key, payload)
        record = self.st.session_state[self.mod.WR2_SESSION_COMPOSITION][PID]
        self.assertIsNone(optional_float(record.get("approved_commitment_qty")))

    def test_t2_null_commitment_rehydrate(self) -> None:
        rows = [
            {
                "plan_line_id": PID,
                "decision": "INCLUDE",
                "decision_status": "ACTIVE",
                "boq_code": "2041-02-06-01",
                "boq_name": "Test BOQ",
                "admission_outcome_at_decision": "OK",
                "management_override": False,
                "decision_basis": "B",
                "responsible_person": "R",
                "review_deadline": "",
                "decision_comment": "",
                "approved_commitment_qty": None,
                "requested_qty_snapshot": None,
                "feasible_qty_snapshot": None,
                "committed_work_value": None,
                "committed_required_hours": None,
                "committed_labor_cost": None,
                "decided_at": "2026-08-01T00:00:00+00:00",
                "decided_by": "R",
            }
        ]
        n = self.mod.wr2_apply_rehydrate_from_rows(rows)
        self.assertEqual(n, 1)
        record = self.st.session_state[self.mod.WR2_SESSION_COMPOSITION][PID]
        self.assertEqual(record["decision"], self.mod.WR2_MGMT_INCLUDE)
        self.assertIsNone(record["approved_commitment_qty"])
        self.assertEqual(
            self.mod.wr2_commitment_status_label(record),
            "ОБЪЁМ НЕ ПРИНЯТ",
        )

    def test_t3_commitment_le_feasible_saves(self) -> None:
        row = pd.Series(_board_row())
        with patch.object(
            self.mod,
            "apply_management_decision",
            return_value={"ok": True, "data": {"status": "updated"}},
        ) as mock_apply, patch.object(
            self.mod,
            "load_management_decisions",
            return_value=[],
        ), patch.object(
            self.mod,
            "wr2_current_feasible_qty",
            return_value=240.0,
        ):
            errors = self.mod.wr2_apply_management_decision(
                row,
                self.mod.WR2_MGMT_INCLUDE,
                basis="BASIS",
                responsible="R",
                review_deadline="",
                comment="",
                commitment_qty=220,
            )
        self.assertEqual(errors, [])
        payload = mock_apply.call_args.kwargs["payload"]
        self.assertEqual(payload["approved_commitment_qty"], 220)
        self.assertEqual(payload["requested_qty_snapshot"], 397.0)
        self.assertEqual(payload["feasible_qty_snapshot"], 240.0)
        self.assertAlmostEqual(payload["committed_work_value"], 220 * 1000)
        self.assertAlmostEqual(payload["committed_required_hours"], 80 * 220 / 397)
        self.assertAlmostEqual(
            payload["committed_labor_cost"],
            (80 * 220 / 397) * 3000,
        )
        record = self.st.session_state[self.mod.WR2_SESSION_COMPOSITION][PID]
        self.assertEqual(record["approved_commitment_qty"], 220)
        self.assertEqual(self.mod.wr2_commitment_status_label(record), "ОБЪЁМ УТВЕРЖДЁН")

    def test_t4_commitment_gt_feasible_rejected(self) -> None:
        row = pd.Series(_board_row())
        with patch.object(
            self.mod,
            "apply_management_decision",
            return_value={"ok": True, "data": {"status": "updated"}},
        ) as mock_apply, patch.object(
            self.mod,
            "wr2_current_feasible_qty",
            return_value=240.0,
        ):
            errors = self.mod.wr2_apply_management_decision(
                row,
                self.mod.WR2_MGMT_INCLUDE,
                basis="BASIS",
                responsible="R",
                review_deadline="",
                comment="",
                commitment_qty=241,
            )
        self.assertEqual(errors, [MSG_COMMITMENT_OVER_FEASIBLE])
        mock_apply.assert_not_called()
        self.assertNotIn(PID, self.st.session_state[self.mod.WR2_SESSION_COMPOSITION])

    def test_t7_cancel_semantics_still_clear_session(self) -> None:
        self.st.session_state[self.mod.WR2_SESSION_COMPOSITION] = {
            PID: {
                "decision": self.mod.WR2_MGMT_INCLUDE,
                "boq_code": "2041-02-06-01",
                "approved_commitment_qty": 220,
            }
        }
        with patch.object(
            self.mod,
            "cancel_management_decision",
            return_value={"ok": True, "data": {"status": "cancelled"}},
        ) as mock_cancel, patch.object(
            self.mod,
            "load_management_decisions",
            return_value=[],
        ):
            errors = self.mod.wr2_remove_from_passport(PID, "2041-02-06-01", "OK")
        self.assertEqual(errors, [])
        mock_cancel.assert_called_once()
        self.assertNotIn(PID, self.st.session_state[self.mod.WR2_SESSION_COMPOSITION])

    def test_t8_draft_summary_distinguishes_null_and_approved(self) -> None:
        board = pd.DataFrame(
            [
                _board_row(),
                _board_row(
                    plan_line_id=PID_NULL,
                    boq_code="2041-02-06-03",
                    planned_qty=249.0,
                ),
            ]
        )
        lookup = {str(r["plan_line_id"]): r for _, r in board.iterrows()}
        records = {
            PID: {
                "decision": self.mod.WR2_MGMT_INCLUDE,
                "boq_code": "2041-02-06-01",
                "boq_name": "A",
                "approved_commitment_qty": 220,
                "requested_qty_snapshot": 397,
                "feasible_qty_snapshot": 240,
                "committed_work_value": 220000,
                "committed_required_hours": 44.332,
                "committed_labor_cost": 132997,
            },
            PID_NULL: {
                "decision": self.mod.WR2_MGMT_INCLUDE_RISK,
                "boq_code": "2041-02-06-03",
                "boq_name": "B",
                "approved_commitment_qty": None,
                "requested_qty_snapshot": None,
                "feasible_qty_snapshot": None,
                "committed_work_value": None,
                "committed_required_hours": None,
                "committed_labor_cost": None,
            },
        }
        with patch.object(self.mod, "wr2_current_feasible_qty", return_value=180.0):
            kpis = self.mod.wr2_compute_commitment_kpis(records, lookup)
            table = self.mod.wr2_build_obligation_qty_table(records, lookup)
        self.assertEqual(kpis["draft_count"], 2)
        self.assertEqual(kpis["with_qty"], 1)
        self.assertEqual(kpis["without_qty"], 1)
        statuses = set(table["Статус объёма"].tolist())
        self.assertEqual(statuses, {"ОБЪЁМ УТВЕРЖДЁН", "ОБЪЁМ НЕ ПРИНЯТ"})
        remainder = table.set_index("BOQ-код")["Остаток"]
        self.assertEqual(remainder.loc["2041-02-06-03"], "Решение по объёму не принято")

    def test_draft_only_excludes_passported_ids(self) -> None:
        """TEST 1–3: 37 INCLUDE minus 19 passport line_ids = 18 draft; no cancel."""
        composition = {
            f"pid-{i:02d}": {
                "decision": (
                    self.mod.WR2_MGMT_INCLUDE_RISK
                    if i >= 17
                    else self.mod.WR2_MGMT_INCLUDE
                ),
                "boq_code": f"BOQ-{i:02d}",
                "boq_name": f"Name {i}",
                "approved_commitment_qty": None,
            }
            for i in range(37)
        }
        passport_ids = {f"pid-{i:02d}" for i in range(19)}
        original = dict(composition)
        draft = self.mod.wr2_filter_draft_only_records(composition, passport_ids)
        self.assertEqual(len(composition), 37)
        self.assertEqual(composition, original)
        self.assertEqual(len(draft), 18)
        for pid in passport_ids:
            self.assertNotIn(pid, draft)
        board_rows = [_board_row(plan_line_id=pid, boq_code=item["boq_code"]) for pid, item in composition.items()]
        month_board = pd.DataFrame(board_rows)
        with patch.object(self.mod, "wr2_current_feasible_qty", return_value=None), patch.object(
            self.mod, "cancel_management_decision"
        ) as mock_cancel:
            built = self.mod.wr2_build_draft_summary_and_tables(
                month_board,
                composition=composition,
                deferred={},
                excluded={},
                passport_line_ids=passport_ids,
            )
        mock_cancel.assert_not_called()
        table = built["tables"]["obligation"]
        self.assertEqual(len(table), 18)
        self.assertEqual(built["summary"]["obligation"]["count"], 18)
        shown = set(table["_plan_line_id"].astype(str))
        self.assertTrue(shown.isdisjoint(passport_ids))
        self.assertEqual(len(composition), 37)

    def test_obligation_table_keeps_pre_r16_and_adds_r16(self) -> None:
        """TEST 4–6: old columns restored, R1.6 additive, NULL = ОБЪЁМ НЕ ПРИНЯТ."""
        row = _board_row()
        board = pd.DataFrame([row])
        lookup = {PID: board.iloc[0]}
        records = {
            PID: {
                "decision": self.mod.WR2_MGMT_INCLUDE,
                "boq_code": "2041-02-06-01",
                "boq_name": "A",
                "responsible": "R",
                "review_deadline": "",
                "comment": "",
                "approved_commitment_qty": None,
            }
        }
        with patch.object(self.mod, "wr2_current_feasible_qty", return_value=None):
            table = self.mod.wr2_build_obligation_qty_table(records, lookup)
        for col in self.mod.WR2_PRE_R16_OBLIGATION_COLUMNS:
            self.assertIn(col, table.columns)
        for col in self.mod.WR2_R16_OBLIGATION_COLUMNS:
            self.assertIn(col, table.columns)
        self.assertEqual(table.iloc[0]["Статус объёма"], "ОБЪЁМ НЕ ПРИНЯТ")


if __name__ == "__main__":
    unittest.main()
