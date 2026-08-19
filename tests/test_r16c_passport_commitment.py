"""
R1.6C focused tests: Passport consumes approved monthly commitment.

No product DB writes. RPC and override/admission writes are mocked.
Run: python -m unittest tests.test_r16c_passport_commitment -v
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from types import ModuleType
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pandas as pd

from services import monthly_passport_service as mps
from tests.test_wr2_decision_form_hydrate import (
    PAGE_PATH,
    _install_streamlit_stub,
)


LINE_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
LINE_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
BOQ_SAME = "2041-02-06-01"


def _pass_constraints(*line_ids: str) -> Dict[str, List[Dict[str, Any]]]:
    return {lid: [{"check_status": "PASS"}] for lid in line_ids}


def _source_row(
    line_id: str,
    *,
    boq: str = "BOQ-1",
    planned_qty: float = 397.0,
    plan_value: float = 999.0,
    required_hours: float = 88.0,
    labor_cost: float = 77.0,
) -> Dict[str, Any]:
    return {
        "line_id": line_id,
        "boq_code": boq,
        "boq_name": "Name",
        "project_code": "PRJ_TEST",
        "month_key": "август-2026",
        "planned_qty": planned_qty,
        "unit_price": 1.0,
        "plan_value": plan_value,
        "required_hours": required_hours,
        "labor_cost": labor_cost,
        "management_override": False,
    }


def _commitment(
    line_id: str,
    *,
    boq: str = "BOQ-1",
    qty: Any = 180.0,
    work_value: Any = 11.0,
    hours: Any = 22.0,
    labor: Any = 33.0,
) -> Dict[str, Any]:
    return {
        "plan_line_id": line_id,
        "boq_code": boq,
        "decision": "INCLUDE",
        "decision_status": "ACTIVE",
        "approved_commitment_qty": qty,
        "committed_work_value": work_value,
        "committed_required_hours": hours,
        "committed_labor_cost": labor,
    }


class R16CPassportCommitmentTests(unittest.TestCase):
    def _mock_write_client(self, rpc_result: Dict[str, Any] | None = None) -> MagicMock:
        client = MagicMock()
        rpc = MagicMock()
        rpc.execute.return_value = MagicMock(data=rpc_result or {"status": "created"})
        client.rpc.return_value = rpc
        return client

    def test_1_existing_approved_passport_blocks_before_any_write(self) -> None:
        write_client = self._mock_write_client()
        with patch.object(
            mps,
            "find_active_approved_passport",
            return_value=(
                {"passport_id": "872fded9-444c-4052-af01-6d0eeef35789", "passport_status": "APPROVED"},
                None,
            ),
        ) as mock_find, patch.object(
            mps, "load_passport_source_rows"
        ) as mock_source, patch.object(
            mps, "_fetch_constraints_for_lines"
        ) as mock_constraints, patch.object(
            mps, "fetch_commitment_by_plan_line_id"
        ) as mock_commit, patch.object(
            mps, "get_write_client", return_value=write_client
        ) as mock_write, patch.object(
            mps, "_call_replace_monthly_passport"
        ) as mock_rpc:
            summary = mps.create_monthly_passport("PRJ_001_БХК", "август-2026")

        self.assertEqual(summary["status"], "blocked_approved_exists")
        self.assertIn(mps.MSG_APPROVED_PASSPORT_EXISTS, summary["errors"])
        mock_find.assert_called_once()
        mock_source.assert_not_called()
        mock_constraints.assert_not_called()
        mock_commit.assert_not_called()
        mock_write.assert_not_called()
        mock_rpc.assert_not_called()
        write_client.rpc.assert_not_called()

    def test_2_null_commitment_blocks_without_planned_qty_fallback(self) -> None:
        source = _source_row(LINE_A, planned_qty=397.0)
        write_client = self._mock_write_client()
        with patch.object(
            mps, "find_active_approved_passport", return_value=(None, None)
        ), patch.object(
            mps, "load_passport_source_rows", return_value=([source], [], "v2")
        ), patch.object(
            mps, "_fetch_constraints_for_lines", return_value=_pass_constraints(LINE_A)
        ), patch.object(
            mps,
            "fetch_commitment_by_plan_line_id",
            return_value=({LINE_A: _commitment(LINE_A, qty=None)}, None),
        ), patch.object(
            mps, "get_write_client", return_value=write_client
        ) as mock_write, patch.object(
            mps, "_call_replace_monthly_passport"
        ) as mock_rpc:
            summary = mps.create_monthly_passport("PRJ_TEST", "август-2026")

        self.assertEqual(summary["status"], "blocked_commitment")
        self.assertTrue(any(mps.MSG_COMMITMENT_MISSING in e for e in summary["errors"]))
        self.assertTrue(any(LINE_A in e for e in summary["errors"]))
        self.assertNotIn(397.0, summary.get("errors", []))
        mock_write.assert_not_called()
        mock_rpc.assert_not_called()
        write_client.rpc.assert_not_called()

    def test_2b_zero_commitment_blocks(self) -> None:
        source = _source_row(LINE_A, planned_qty=397.0)
        write_client = self._mock_write_client()
        with patch.object(
            mps, "find_active_approved_passport", return_value=(None, None)
        ), patch.object(
            mps, "load_passport_source_rows", return_value=([source], [], "v2")
        ), patch.object(
            mps, "_fetch_constraints_for_lines", return_value=_pass_constraints(LINE_A)
        ), patch.object(
            mps,
            "fetch_commitment_by_plan_line_id",
            return_value=({LINE_A: _commitment(LINE_A, qty=0)}, None),
        ), patch.object(
            mps, "get_write_client", return_value=write_client
        ) as mock_write:
            summary = mps.create_monthly_passport("PRJ_TEST", "август-2026")

        self.assertEqual(summary["status"], "blocked_commitment")
        self.assertTrue(any(mps.MSG_COMMITMENT_MISSING in e for e in summary["errors"]))
        mock_write.assert_not_called()

    def test_3_commitment_mapping_not_requested_qty(self) -> None:
        source = _source_row(
            LINE_A,
            planned_qty=397.0,
            plan_value=999.0,
            required_hours=88.0,
            labor_cost=77.0,
        )
        write_client = self._mock_write_client(
            {
                "status": "created",
                "passport_id": "new-passport",
                "previous_rows": 0,
                "current_rows": 1,
                "added_count": 1,
                "removed_count": 0,
                "updated_count": 0,
            }
        )
        with patch.object(
            mps, "find_active_approved_passport", return_value=(None, None)
        ), patch.object(
            mps, "load_passport_source_rows", return_value=([source], [], "v2")
        ), patch.object(
            mps, "_fetch_constraints_for_lines", return_value=_pass_constraints(LINE_A)
        ), patch.object(
            mps,
            "fetch_commitment_by_plan_line_id",
            return_value=(
                {
                    LINE_A: _commitment(
                        LINE_A, qty=180.0, work_value=11.0, hours=22.0, labor=33.0
                    )
                },
                None,
            ),
        ), patch.object(mps, "get_write_client", return_value=write_client):
            summary = mps.create_monthly_passport("PRJ_TEST", "август-2026")

        self.assertEqual(summary["status"], "created")
        payload = write_client.rpc.call_args[0][1]["p_lines"][0]
        self.assertEqual(payload["planned_qty"], 180.0)
        self.assertEqual(payload["plan_value"], 11.0)
        self.assertEqual(payload["required_hours"], 22.0)
        self.assertEqual(payload["labor_cost"], 33.0)
        self.assertNotEqual(payload["planned_qty"], 397.0)
        self.assertEqual(payload["line_id"], LINE_A)
        self.assertEqual(payload["boq_code"], "BOQ-1")

    def test_4_incomplete_snapshot_blocks_no_v2_hours_fallback(self) -> None:
        source = _source_row(LINE_A, required_hours=88.0)
        write_client = self._mock_write_client()
        with patch.object(
            mps, "find_active_approved_passport", return_value=(None, None)
        ), patch.object(
            mps, "load_passport_source_rows", return_value=([source], [], "v2")
        ), patch.object(
            mps, "_fetch_constraints_for_lines", return_value=_pass_constraints(LINE_A)
        ), patch.object(
            mps,
            "fetch_commitment_by_plan_line_id",
            return_value=(
                {LINE_A: _commitment(LINE_A, qty=180.0, hours=None)},
                None,
            ),
        ), patch.object(
            mps, "get_write_client", return_value=write_client
        ) as mock_write:
            summary = mps.create_monthly_passport("PRJ_TEST", "август-2026")

        self.assertEqual(summary["status"], "blocked_commitment")
        self.assertTrue(any(mps.MSG_SNAPSHOT_INCOMPLETE in e for e in summary["errors"]))
        mock_write.assert_not_called()

    def test_4b_zero_snapshot_is_allowed(self) -> None:
        source = _source_row(LINE_A)
        write_client = self._mock_write_client(
            {
                "status": "created",
                "passport_id": "new-passport",
                "previous_rows": 0,
                "current_rows": 1,
                "added_count": 1,
                "removed_count": 0,
                "updated_count": 0,
            }
        )
        with patch.object(
            mps, "find_active_approved_passport", return_value=(None, None)
        ), patch.object(
            mps, "load_passport_source_rows", return_value=([source], [], "v2")
        ), patch.object(
            mps, "_fetch_constraints_for_lines", return_value=_pass_constraints(LINE_A)
        ), patch.object(
            mps,
            "fetch_commitment_by_plan_line_id",
            return_value=(
                {LINE_A: _commitment(LINE_A, qty=180.0, work_value=0, hours=0, labor=0)},
                None,
            ),
        ), patch.object(mps, "get_write_client", return_value=write_client):
            summary = mps.create_monthly_passport("PRJ_TEST", "август-2026")

        self.assertEqual(summary["status"], "created")
        payload = write_client.rpc.call_args[0][1]["p_lines"][0]
        self.assertEqual(payload["planned_qty"], 180.0)
        self.assertEqual(payload["plan_value"], 0.0)
        self.assertEqual(payload["required_hours"], 0.0)
        self.assertEqual(payload["labor_cost"], 0.0)

    def test_5_same_boq_maps_commitment_by_plan_line_id(self) -> None:
        sources = [
            _source_row(LINE_A, boq=BOQ_SAME, planned_qty=397.0),
            _source_row(LINE_B, boq=BOQ_SAME, planned_qty=153.0),
        ]
        write_client = self._mock_write_client(
            {
                "status": "created",
                "passport_id": "new-passport",
                "previous_rows": 0,
                "current_rows": 2,
                "added_count": 2,
                "removed_count": 0,
                "updated_count": 0,
            }
        )
        with patch.object(
            mps, "find_active_approved_passport", return_value=(None, None)
        ), patch.object(
            mps, "load_passport_source_rows", return_value=(sources, [], "v2")
        ), patch.object(
            mps,
            "_fetch_constraints_for_lines",
            return_value=_pass_constraints(LINE_A, LINE_B),
        ), patch.object(
            mps,
            "fetch_commitment_by_plan_line_id",
            return_value=(
                {
                    LINE_A: _commitment(
                        LINE_A, boq=BOQ_SAME, qty=180.0, work_value=1, hours=2, labor=3
                    ),
                    LINE_B: _commitment(
                        LINE_B, boq=BOQ_SAME, qty=50.0, work_value=4, hours=5, labor=6
                    ),
                },
                None,
            ),
        ), patch.object(mps, "get_write_client", return_value=write_client):
            summary = mps.create_monthly_passport("PRJ_TEST", "август-2026")

        self.assertEqual(summary["status"], "created")
        lines = write_client.rpc.call_args[0][1]["p_lines"]
        by_id = {row["line_id"]: row for row in lines}
        self.assertEqual(by_id[LINE_A]["planned_qty"], 180.0)
        self.assertEqual(by_id[LINE_A]["plan_value"], 1.0)
        self.assertEqual(by_id[LINE_B]["planned_qty"], 50.0)
        self.assertEqual(by_id[LINE_B]["plan_value"], 4.0)
        self.assertEqual(by_id[LINE_A]["boq_code"], BOQ_SAME)
        self.assertEqual(by_id[LINE_B]["boq_code"], BOQ_SAME)


def _load_page23() -> ModuleType:
    for key in list(sys.modules):
        if (
            key == "streamlit"
            or key.startswith("wr2_page23_r16c")
            or key == "services.monthly_plan_management_decisions"
        ):
            del sys.modules[key]
    st = _install_streamlit_stub()
    spec = importlib.util.spec_from_file_location("wr2_page23_r16c_test", PAGE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wr2_page23_r16c_test"] = mod
    spec.loader.exec_module(mod)
    mod.st = st  # type: ignore[attr-defined]
    return mod


class R16CWr2CreatePreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_page23()
        self.st = self.mod.st
        self.st.session_state.clear()
        self.mod.wr2_init_passport_session()

    def tearDown(self) -> None:
        self.st.session_state.clear()
        for key in list(sys.modules):
            if key == "streamlit" or key.startswith("wr2_page23_r16c"):
                del sys.modules[key]

    def _board(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "plan_line_id": LINE_A,
                    "boq_code": "BOQ-1",
                    "outcome": "OK",
                }
            ]
        )

    def test_1_wr2_create_blocks_approved_before_override_or_create(self) -> None:
        with patch.object(
            self.mod.monthly_passport_service,
            "preflight_new_passport",
            return_value={
                "ok": False,
                "status": "blocked_approved_exists",
                "passport_id": "872fded9-444c-4052-af01-6d0eeef35789",
                "errors": [mps.MSG_APPROVED_PASSPORT_EXISTS],
            },
        ), patch.object(
            self.mod, "wr2_collect_passport_override_errors"
        ) as mock_override_errors, patch.object(
            self.mod, "wr2_build_passport_override_payload"
        ) as mock_override_payload, patch.object(
            self.mod, "create_monthly_passport"
        ) as mock_create:
            summary = self.mod.wr2_create_monthly_passport_with_overrides(
                "PRJ_001_БХК",
                "август-2026",
                "tester",
                self._board(),
            )

        self.assertEqual(summary["status"], "blocked_approved_exists")
        self.assertIn(mps.MSG_APPROVED_PASSPORT_EXISTS, summary["errors"])
        mock_override_errors.assert_not_called()
        mock_override_payload.assert_not_called()
        mock_create.assert_not_called()

    def test_2_wr2_create_blocks_null_commitment_before_writes(self) -> None:
        with patch.object(
            self.mod.monthly_passport_service,
            "preflight_new_passport",
            return_value={
                "ok": False,
                "status": "blocked_commitment",
                "passport_id": None,
                "errors": [f"BOQ-1 / {LINE_A}: {mps.MSG_COMMITMENT_MISSING}"],
            },
        ), patch.object(
            self.mod, "wr2_collect_passport_override_errors"
        ) as mock_override_errors, patch.object(
            self.mod, "wr2_build_passport_override_payload"
        ) as mock_override_payload, patch.object(
            self.mod, "create_monthly_passport"
        ) as mock_create:
            summary = self.mod.wr2_create_monthly_passport_with_overrides(
                "PRJ_TEST",
                "август-2026",
                "tester",
                self._board(),
            )

        self.assertEqual(summary["status"], "blocked_commitment")
        mock_override_errors.assert_not_called()
        mock_override_payload.assert_not_called()
        mock_create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
