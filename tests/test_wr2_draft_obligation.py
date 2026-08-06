"""
Page 23 draft obligation baskets — T1–T8 (no product DB).

Run: .\\.venv\\Scripts\\python.exe -m unittest tests.test_wr2_draft_obligation -v
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List
from unittest.mock import patch

import pandas as pd

from tests.test_wr2_decision_form_hydrate import (
    PAGE_PATH,
    TEST_PID,
    _SessionState,
    _cache_data_stub,
    _install_streamlit_stub,
)


PID_DEFER = "TEST-draft-defer-001"
PID_EXCLUDE = "TEST-draft-exclude-001"
PID_RISK = "TEST-draft-risk-001"
PID_INCLUDE = "TEST-draft-include-001"
PID_FILTERED = "TEST-draft-filtered-out-001"


def _load_page() -> ModuleType:
    for key in list(sys.modules):
        if (
            key == "streamlit"
            or key.startswith("wr2_page23_draft_test")
            or key == "services.monthly_plan_management_decisions"
        ):
            del sys.modules[key]
    st = _install_streamlit_stub()
    spec = importlib.util.spec_from_file_location("wr2_page23_draft_test", PAGE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wr2_page23_draft_test"] = mod
    spec.loader.exec_module(mod)
    mod.st = st  # type: ignore[attr-defined]
    return mod


def _board_row(
    pid: str,
    *,
    plan_value: float = 100.0,
    labor: float = 10.0,
    workers: float = 2.0,
    outcome: str = "BLOCKED",
) -> Dict[str, Any]:
    return {
        "plan_line_id": pid,
        "project_code": "TEST_MGMT",
        "month_key": "тест-2026",
        "boq_code": f"BOQ-{pid[-3:]}",
        "boq_name": f"Name {pid}",
        "outcome": outcome,
        "plan_value_num": plan_value,
        "planned_direct_hours": labor,
        "planned_workers": workers,
        "title_display": "T1",
        "discipline": "CIVIL",
        "blocking_departments": "ПТО",
    }


def _month_board(mod: ModuleType, rows: List[Dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows)


class Wr2DraftObligationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_page()
        self.st = self.mod.st
        self.st.session_state.clear()
        self.mod.wr2_init_passport_session()

    def tearDown(self) -> None:
        self.st.session_state.clear()
        for key in list(sys.modules):
            if key == "streamlit" or key.startswith("wr2_page23_draft_test"):
                del sys.modules[key]

    def _row(self, pid: str) -> pd.Series:
        return pd.Series(_board_row(pid))

    def test_t1_defer_to_include_moves_basket(self) -> None:
        """T1 DEFER → INCLUDE: row leaves deferred, enters composition."""
        pid = PID_DEFER
        self.st.session_state[self.mod.WR2_SESSION_DEFERRED] = {
            pid: {
                "decision": self.mod.WR2_MGMT_POSTPONE,
                "basis": "DEFER_BASIS",
                "responsible": "R",
                "review_deadline": "",
                "comment": "",
            }
        }
        with patch.object(
            self.mod,
            "apply_management_decision",
            return_value={"ok": True, "decision_id": "id"},
        ), patch.object(
            self.mod,
            "load_management_decisions",
            return_value=[],
        ):
            errors = self.mod.wr2_apply_management_decision(
                self._row(pid),
                self.mod.WR2_MGMT_INCLUDE,
                basis="NEW_BASIS",
                responsible="R",
                review_deadline="",
                comment="",
            )
        self.assertEqual(errors, [])
        self.assertNotIn(pid, self.st.session_state[self.mod.WR2_SESSION_DEFERRED])
        self.assertIn(pid, self.st.session_state[self.mod.WR2_SESSION_COMPOSITION])
        draft = self.mod.wr2_build_draft_summary_and_tables(
            _month_board(self.mod, [_board_row(pid)]),
            composition=self.st.session_state[self.mod.WR2_SESSION_COMPOSITION],
            deferred=self.st.session_state[self.mod.WR2_SESSION_DEFERRED],
            excluded=self.st.session_state.get(self.mod.WR2_SESSION_EXCLUDED, {}),
        )
        self.assertEqual(draft["summary"]["deferred"]["count"], 0)
        self.assertEqual(draft["summary"]["obligation"]["count"], 1)

    def test_t2_exclude_to_include_risk_moves_basket(self) -> None:
        """T2 EXCLUDE → INCLUDE_RISK: excluded cleared, composition risk."""
        pid = PID_EXCLUDE
        self.st.session_state[self.mod.WR2_SESSION_EXCLUDED] = {
            pid: {
                "decision": self.mod.WR2_MGMT_EXCLUDE,
                "basis": "EX_BASIS",
                "responsible": "R",
                "review_deadline": "",
                "comment": "",
            }
        }
        with patch.object(
            self.mod,
            "apply_management_decision",
            return_value={"ok": True, "decision_id": "id"},
        ), patch.object(
            self.mod,
            "load_management_decisions",
            return_value=[],
        ):
            errors = self.mod.wr2_apply_management_decision(
                self._row(pid),
                self.mod.WR2_MGMT_INCLUDE_RISK,
                basis="RISK_BASIS",
                responsible="R",
                review_deadline="",
                comment="",
                risk_description="D",
                risk_impact="I",
                risk_mitigation_owner="O",
                risk_mitigation_deadline="01.01.2027",
                risk_acceptance_basis="A",
                risk_manager_comment="C",
            )
        self.assertEqual(errors, [])
        self.assertNotIn(pid, self.st.session_state[self.mod.WR2_SESSION_EXCLUDED])
        comp = self.st.session_state[self.mod.WR2_SESSION_COMPOSITION][pid]
        self.assertEqual(comp["decision"], self.mod.WR2_MGMT_INCLUDE_RISK)
        draft = self.mod.wr2_build_draft_summary_and_tables(
            _month_board(self.mod, [_board_row(pid)]),
            composition=self.st.session_state[self.mod.WR2_SESSION_COMPOSITION],
            deferred={},
            excluded={},
        )
        self.assertEqual(draft["summary"]["excluded"]["count"], 0)
        self.assertEqual(draft["summary"]["risk"]["count"], 1)

    def test_t3_empty_review_deadline_apply_passes(self) -> None:
        """T3 review_deadline empty: Apply validation passes."""
        pid = PID_INCLUDE
        with patch.object(
            self.mod,
            "apply_management_decision",
            return_value={"ok": True, "decision_id": "id"},
        ) as mock_apply, patch.object(
            self.mod,
            "load_management_decisions",
            return_value=[],
        ):
            errors = self.mod.wr2_apply_management_decision(
                self._row(pid),
                self.mod.WR2_MGMT_INCLUDE,
                basis="BASIS",
                responsible="R",
                review_deadline="",
                comment="NOTE",
            )
        self.assertEqual(errors, [])
        payload = mock_apply.call_args.kwargs["payload"]
        self.assertEqual(payload["review_deadline"], "")

    def test_t4_empty_comment_apply_passes(self) -> None:
        """T4 decision_comment empty: Apply validation passes."""
        pid = PID_INCLUDE
        with patch.object(
            self.mod,
            "apply_management_decision",
            return_value={"ok": True, "decision_id": "id"},
        ) as mock_apply, patch.object(
            self.mod,
            "load_management_decisions",
            return_value=[],
        ):
            errors = self.mod.wr2_apply_management_decision(
                self._row(pid),
                self.mod.WR2_MGMT_POSTPONE,
                basis="BASIS",
                responsible="R",
                review_deadline="01.01.2027",
                comment="",
            )
        self.assertEqual(errors, [])
        payload = mock_apply.call_args.kwargs["payload"]
        self.assertEqual(payload["decision_comment"], "")

    def test_t5_include_risk_cost_not_double_counted_in_readiness(self) -> None:
        """T5 INCLUDE_RISK: passport scope value counted once, not obligation+risk."""
        pid = PID_RISK
        comp = {
            pid: {
                "decision": self.mod.WR2_MGMT_INCLUDE_RISK,
                "basis": "B",
                "responsible": "R",
                "comment": "",
                "review_deadline": "",
                "risk_description": "D",
                "risk_impact": "I",
                "risk_mitigation_owner": "O",
                "risk_mitigation_deadline": "01.01.2027",
                "risk_acceptance_basis": "A",
                "risk_manager_comment": "C",
            }
        }
        self.st.session_state[self.mod.WR2_SESSION_COMPOSITION] = comp
        self.mod.wr2_sync_decision_type_change(pid, self.mod.WR2_MGMT_INCLUDE_RISK)
        board = _month_board(self.mod, [_board_row(pid, plan_value=250.0)])
        draft = self.mod.wr2_build_draft_summary_and_tables(
            board,
            composition=self.st.session_state[self.mod.WR2_SESSION_COMPOSITION],
            deferred={},
            excluded={},
        )
        self.assertEqual(draft["summary"]["obligation"]["cost"], 250.0)
        self.assertEqual(draft["summary"]["risk"]["cost"], 250.0)
        readiness = self.mod.wr2_compute_readiness("TEST_MGMT", "тест-2026", board)
        self.assertEqual(readiness["metrics"]["value_passport"], 250.0)
        naive_double = (
            draft["summary"]["obligation"]["cost"] + draft["summary"]["risk"]["cost"]
        )
        self.assertNotEqual(
            readiness["metrics"]["value_passport"],
            naive_double,
            "Passport value must not equal naive sum of both basket KPIs",
        )

    def test_t6_reload_restores_four_baskets(self) -> None:
        """T6 rehydrate restores obligation, risk, deferred, excluded."""
        from services.monthly_plan_management_decisions import (
            DECISION_DEFER,
            DECISION_EXCLUDE,
            DECISION_INCLUDE,
            DECISION_INCLUDE_RISK,
        )

        rows = [
            {
                "plan_line_id": PID_INCLUDE,
                "decision": DECISION_INCLUDE,
                "boq_code": "A",
                "boq_name": "A",
                "decision_basis": "b",
                "responsible_person": "r",
                "decision_comment": "",
                "review_deadline": "",
            },
            {
                "plan_line_id": PID_RISK,
                "decision": DECISION_INCLUDE_RISK,
                "boq_code": "B",
                "boq_name": "B",
                "decision_basis": "b",
                "responsible_person": "r",
                "risk_description": "d",
                "risk_impact": "i",
                "risk_mitigation_owner": "o",
                "risk_mitigation_deadline": "d",
                "risk_acceptance_basis": "a",
                "risk_manager_comment": "c",
            },
            {
                "plan_line_id": PID_DEFER,
                "decision": DECISION_DEFER,
                "boq_code": "C",
                "boq_name": "C",
                "decision_basis": "b",
                "responsible_person": "r",
            },
            {
                "plan_line_id": PID_EXCLUDE,
                "decision": DECISION_EXCLUDE,
                "boq_code": "D",
                "boq_name": "D",
                "decision_basis": "b",
                "responsible_person": "r",
            },
        ]
        self.mod.wr2_apply_rehydrate_from_rows(rows)
        comp = self.st.session_state[self.mod.WR2_SESSION_COMPOSITION]
        deferred = self.st.session_state[self.mod.WR2_SESSION_DEFERRED]
        excluded = self.st.session_state[self.mod.WR2_SESSION_EXCLUDED]
        self.assertIn(PID_INCLUDE, comp)
        self.assertIn(PID_RISK, comp)
        self.assertIn(PID_DEFER, deferred)
        self.assertIn(PID_EXCLUDE, excluded)
        board = _month_board(
            self.mod,
            [
                _board_row(PID_INCLUDE),
                _board_row(PID_RISK),
                _board_row(PID_DEFER),
                _board_row(PID_EXCLUDE),
            ],
        )
        draft = self.mod.wr2_build_draft_summary_and_tables(
            board, composition=comp, deferred=deferred, excluded=excluded
        )
        self.assertEqual(draft["summary"]["obligation"]["count"], 2)
        self.assertEqual(draft["summary"]["risk"]["count"], 1)
        self.assertEqual(draft["summary"]["deferred"]["count"], 1)
        self.assertEqual(draft["summary"]["excluded"]["count"], 1)

    def test_t7_filters_do_not_clear_composition(self) -> None:
        """T7 filtered board subset does not wipe session baskets or month board."""
        full_rows = [
            _board_row(PID_INCLUDE, outcome="OK"),
            _board_row(PID_FILTERED, outcome="OK"),
        ]
        full_board = pd.DataFrame(full_rows)
        month_board = self.mod.wr2_slice_month_board(
            full_board, "TEST_MGMT", "тест-2026"
        )
        self.st.session_state[self.mod.WR2_SESSION_MONTH_BOARD] = month_board
        self.st.session_state[self.mod.WR2_SESSION_COMPOSITION] = {
            PID_INCLUDE: {"decision": self.mod.WR2_MGMT_INCLUDE, "basis": "b"},
            PID_FILTERED: {"decision": self.mod.WR2_MGMT_INCLUDE, "basis": "b"},
        }
        self.st.session_state[self.mod.WR2_SESSION_MGMT_REHYDRATED_COUNT] = 2
        filtered = full_board[full_board["plan_line_id"] == PID_INCLUDE].copy()
        self.assertEqual(len(filtered), 1)
        self.assertEqual(
            len(self.st.session_state[self.mod.WR2_SESSION_COMPOSITION]), 2
        )
        self.assertEqual(len(self.mod.wr2_month_board_from_session()), 2)
        draft = self.mod.wr2_build_draft_summary_and_tables(
            self.mod.wr2_month_board_from_session(),
            composition=self.st.session_state[self.mod.WR2_SESSION_COMPOSITION],
            deferred={},
            excluded={},
        )
        self.assertEqual(draft["summary"]["obligation"]["count"], 2)

    def test_t8_passport_uses_full_month_board_not_filter(self) -> None:
        """T8 readiness full_scope includes composition outside filtered view."""
        full_rows = [
            _board_row(PID_INCLUDE),
            _board_row(PID_FILTERED),
        ]
        full_board = pd.DataFrame(full_rows)
        month_board = self.mod.wr2_slice_month_board(
            full_board, "TEST_MGMT", "тест-2026"
        )
        for pid in (PID_INCLUDE, PID_FILTERED):
            self.st.session_state.setdefault(self.mod.WR2_SESSION_COMPOSITION, {})[
                pid
            ] = {
                "decision": self.mod.WR2_MGMT_INCLUDE,
                "basis": "b",
                "responsible": "r",
            }
        filtered = full_board[full_board["plan_line_id"] == PID_INCLUDE].copy()
        readiness_filtered = self.mod.wr2_compute_readiness(
            "TEST_MGMT", "тест-2026", filtered
        )
        readiness_full = self.mod.wr2_compute_readiness(
            "TEST_MGMT", "тест-2026", month_board
        )
        self.assertEqual(len(readiness_filtered["full_scope"]), 1)
        self.assertEqual(len(readiness_full["full_scope"]), 2)


if __name__ == "__main__":
    unittest.main()
