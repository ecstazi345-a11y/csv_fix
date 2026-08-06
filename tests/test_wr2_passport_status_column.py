"""
Page 23 display-only passport status column — T1–T6 (no product DB).

Run: .\\.venv\\Scripts\\python.exe -m unittest tests.test_wr2_passport_status_column -v
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pandas as pd

from tests.test_wr2_decision_form_hydrate import (
    PAGE_PATH,
    _cache_data_stub,
    _install_streamlit_stub,
    _SessionState,
)


def _load_page() -> ModuleType:
    for key in list(sys.modules):
        if (
            key == "streamlit"
            or key.startswith("wr2_page23_passport_status")
            or key == "services.monthly_plan_management_decisions"
        ):
            del sys.modules[key]
    st = _install_streamlit_stub()
    st.column_config = MagicMock()
    st.column_config.TextColumn = lambda *a, **k: MagicMock(help=k.get("help"))
    spec = importlib.util.spec_from_file_location(
        "wr2_page23_passport_status_test", PAGE_PATH
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wr2_page23_passport_status_test"] = mod
    spec.loader.exec_module(mod)
    mod.st = st  # type: ignore[attr-defined]
    return mod


class Wr2PassportStatusColumnTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_page()
        self.st = self.mod.st
        self.st.session_state.clear()
        self.mod.wr2_init_passport_session()

    def tearDown(self) -> None:
        self.st.session_state.clear()
        for key in list(sys.modules):
            if key == "streamlit" or key.startswith("wr2_page23_passport_status"):
                del sys.modules[key]

    def _index(
        self,
        *,
        by_line: Dict[str, str] | None = None,
        has_passport: bool = True,
        passport_id: str = "pass-1",
        load_calls: int = 1,
    ) -> Dict[str, Any]:
        idx = self.mod.wr2_empty_passport_status_index()
        idx["has_passport"] = has_passport
        idx["passport_id"] = passport_id if has_passport else None
        idx["by_line_id"] = dict(by_line or {})
        idx["lines_loaded"] = len(idx["by_line_id"])
        idx["load_calls"] = load_calls
        return idx

    def _row(self, pid: str, boq: str = "BOQ-1") -> pd.Series:
        return pd.Series(
            {
                "plan_line_id": pid,
                "boq_code": boq,
                "boq_name": "Test",
                "outcome": "BLOCKED",
                "project_code": "TEST_MGMT",
                "month_key": "тест-2026",
            }
        )

    def test_t1_legacy_passport_override_no_decision(self) -> None:
        """T1: no decision + passport override → Pending / Включён с риском, no conflict."""
        pid = "line-legacy-1"
        idx = self._index(
            by_line={pid: self.mod.WR2_PASSPORT_STATUS_IN_RISK},
            has_passport=True,
        )
        self.mod.wr2_store_passport_status_index(idx)
        row = self._row(pid)
        final = self.mod.wr2_final_decision_label_for_row(row)
        passport = self.mod.wr2_passport_status_for_row(row, idx)
        conflict = self.mod.wr2_passport_decision_conflict(
            final, passport, has_active_passport=True
        )
        self.assertEqual(final, self.mod.WR2_FINAL_DECISION_PENDING)
        self.assertEqual(passport, self.mod.WR2_PASSPORT_STATUS_IN_RISK)
        self.assertFalse(conflict)

    def test_t2_include_without_passport_line_conflict(self) -> None:
        """T2: INCLUDE + not in passport + active passport → conflict."""
        pid = "line-include-1"
        idx = self._index(by_line={}, has_passport=True)
        self.st.session_state[self.mod.WR2_SESSION_COMPOSITION] = {
            pid: {"decision": self.mod.WR2_MGMT_INCLUDE}
        }
        row = self._row(pid)
        final = self.mod.wr2_final_decision_label_for_row(row)
        passport = self.mod.wr2_passport_status_for_row(row, idx)
        conflict = self.mod.wr2_passport_decision_conflict(
            final, passport, has_active_passport=True
        )
        self.assertEqual(final, self.mod.WR2_FINAL_DECISION_IN_OBLIGATION)
        self.assertEqual(passport, self.mod.WR2_PASSPORT_STATUS_NOT_IN)
        self.assertTrue(conflict)

    def test_t3_exclude_with_passport_line_conflict(self) -> None:
        """T3: EXCLUDE + in passport → conflict."""
        pid = "line-exclude-1"
        idx = self._index(by_line={pid: self.mod.WR2_PASSPORT_STATUS_IN})
        self.st.session_state[self.mod.WR2_SESSION_EXCLUDED] = {
            pid: {"decision": self.mod.WR2_MGMT_EXCLUDE}
        }
        row = self._row(pid)
        final = self.mod.wr2_final_decision_label_for_row(row)
        passport = self.mod.wr2_passport_status_for_row(row, idx)
        conflict = self.mod.wr2_passport_decision_conflict(
            final, passport, has_active_passport=True
        )
        self.assertEqual(final, self.mod.WR2_FINAL_DECISION_EXCLUDED)
        self.assertEqual(passport, self.mod.WR2_PASSPORT_STATUS_IN)
        self.assertTrue(conflict)

    def test_t4_include_risk_with_override_no_conflict(self) -> None:
        """T4: INCLUDE_RISK + passport override → no conflict."""
        pid = "line-risk-1"
        idx = self._index(by_line={pid: self.mod.WR2_PASSPORT_STATUS_IN_RISK})
        self.st.session_state[self.mod.WR2_SESSION_COMPOSITION] = {
            pid: {"decision": self.mod.WR2_MGMT_INCLUDE_RISK}
        }
        row = self._row(pid)
        final = self.mod.wr2_final_decision_label_for_row(row)
        passport = self.mod.wr2_passport_status_for_row(row, idx)
        conflict = self.mod.wr2_passport_decision_conflict(
            final, passport, has_active_passport=True
        )
        self.assertEqual(final, self.mod.WR2_FINAL_DECISION_IN_OBLIGATION_RISK)
        self.assertEqual(passport, self.mod.WR2_PASSPORT_STATUS_IN_RISK)
        self.assertFalse(conflict)

    def test_t5_no_decision_no_passport(self) -> None:
        """T5: empty baskets + empty passport → Pending / Не включён."""
        pid = "line-empty-1"
        idx = self._index(by_line={}, has_passport=False)
        row = self._row(pid)
        final = self.mod.wr2_final_decision_label_for_row(row)
        passport = self.mod.wr2_passport_status_for_row(row, idx)
        conflict = self.mod.wr2_passport_decision_conflict(
            final, passport, has_active_passport=False
        )
        self.assertEqual(final, self.mod.WR2_FINAL_DECISION_PENDING)
        self.assertEqual(passport, self.mod.WR2_PASSPORT_STATUS_NOT_IN)
        self.assertFalse(conflict)

    def test_t6_bulk_load_no_n_plus_one(self) -> None:
        """T6: one bulk load builds index; N row lookups do not call Supabase again."""
        header = {
            "passport_id": "pass-bulk",
            "passport_status": "APPROVED",
            "updated_at": "2026-08-05T14:00:00+00:00",
        }
        lines = [
            {
                "line_id": "l1",
                "boq_code": "A",
                "admission_status": "APPROVED_BY_OVERRIDE",
                "management_override": True,
            },
            {
                "line_id": "l2",
                "boq_code": "B",
                "admission_status": "READY",
                "management_override": False,
            },
        ]
        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[header]
        )
        # Second chain for lines: .eq(passport_id).limit.execute
        lines_builder = MagicMock()
        lines_builder.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=lines
        )
        headers_builder = MagicMock()
        headers_builder.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[header]
        )

        def table_side_effect(name: str):
            t = MagicMock()
            if name == "monthly_plan_passports":
                t.select.return_value = headers_builder
            else:
                t.select.return_value = lines_builder
            return t

        mock_sb.table.side_effect = table_side_effect
        with patch.object(self.mod, "supabase", mock_sb):
            idx = self.mod.wr2_load_passport_status_index("TEST_MGMT", "тест-2026")
            self.assertEqual(idx["load_calls"], 1)
            self.assertEqual(idx["lines_loaded"], 2)
            self.assertEqual(
                idx["by_line_id"]["l1"], self.mod.WR2_PASSPORT_STATUS_IN_RISK
            )
            self.assertEqual(idx["by_line_id"]["l2"], self.mod.WR2_PASSPORT_STATUS_IN)
            # Lookups are pure dict — no further table() calls after load
            calls_after_load = mock_sb.table.call_count
            for pid in ("l1", "l2", "missing"):
                self.mod.wr2_passport_status_for_row(self._row(pid), idx)
            self.assertEqual(mock_sb.table.call_count, calls_after_load)

    def test_passport_line_label_override_rules(self) -> None:
        self.assertEqual(
            self.mod.wr2_passport_line_status_label(
                {"management_override": True, "admission_status": "READY"}
            ),
            self.mod.WR2_PASSPORT_STATUS_IN_RISK,
        )
        self.assertEqual(
            self.mod.wr2_passport_line_status_label(
                {
                    "management_override": False,
                    "admission_status": "APPROVED_BY_OVERRIDE",
                }
            ),
            self.mod.WR2_PASSPORT_STATUS_IN_RISK,
        )
        self.assertEqual(
            self.mod.wr2_passport_line_status_label(
                {"management_override": False, "admission_status": "READY"}
            ),
            self.mod.WR2_PASSPORT_STATUS_IN,
        )


if __name__ == "__main__":
    unittest.main()
