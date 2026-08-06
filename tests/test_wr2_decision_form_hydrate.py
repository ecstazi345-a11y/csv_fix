"""
Isolated tests for Page 23 decision-form hydrate / apply priority.

No product DB writes. Uses TEST_MGMT session state only.
Run: .\\.venv\\Scripts\\python.exe -m unittest tests.test_wr2_decision_form_hydrate -v
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


TEST_PID = "TEST_MGMT-plan-line-0001"
PAGE_PATH = (
    Path(__file__).resolve().parents[1]
    / "pages"
    / "23_Admission_War_Room_ограничений.py"
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
    st.radio = lambda *a, **k: None
    st.text_area = lambda *a, **k: None
    st.text_input = lambda *a, **k: None
    st.columns = lambda n: [MagicMock() for _ in range(n)]
    st.rerun = lambda: None
    st.expander = MagicMock()
    sys.modules["streamlit"] = st
    return st


def _load_page() -> ModuleType:
    # Fresh streamlit stub + page module each load.
    for key in list(sys.modules):
        if (
            key == "streamlit"
            or key.startswith("wr2_page23_test")
            or key == "services.monthly_plan_management_decisions"
        ):
            del sys.modules[key]
    st = _install_streamlit_stub()
    spec = importlib.util.spec_from_file_location("wr2_page23_test", PAGE_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wr2_page23_test"] = mod
    spec.loader.exec_module(mod)
    mod.st = st  # type: ignore[attr-defined]
    return mod


class Wr2DecisionFormHydrateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_page()
        self.st = self.mod.st
        self.st.session_state.clear()
        self.mod.wr2_init_passport_session()
        self.pid = TEST_PID
        self.row = pd.Series(
            {
                "plan_line_id": self.pid,
                "project_code": "TEST_MGMT",
                "month_key": "тест-2026",
                "boq_code": "TEST-BOQ-001",
                "boq_name": "Test BOQ",
                "outcome": "BLOCKED",
                "blocking_departments": "ПТО",
                "reason": "test",
                "critical_department": "ПТО",
                "plan_value_num": 1.0,
                "labor_hours": 1.0,
            }
        )

    def tearDown(self) -> None:
        self.st.session_state.clear()
        for key in list(sys.modules):
            if key == "streamlit" or key.startswith("wr2_page23_test"):
                del sys.modules[key]

    def _seed_deferred(self, **extra: Any) -> Dict[str, Any]:
        record = {
            "decision": self.mod.WR2_MGMT_POSTPONE,
            "basis": "OLD_DEFER_BASIS",
            "responsible": "OLD_RESP",
            "review_deadline": "01.01.2026",
            "comment": "OLD_DEFER_COMMENT",
            "risk_description": "",
            "risk_impact": "",
            "risk_mitigation_owner": "",
            "risk_mitigation_deadline": "",
            "risk_acceptance_basis": "",
            "risk_manager_comment": "",
            "override": False,
        }
        record.update(extra)
        self.st.session_state[self.mod.WR2_SESSION_DEFERRED] = {self.pid: record}
        return record

    def _seed_excluded(self, **extra: Any) -> Dict[str, Any]:
        record = {
            "decision": self.mod.WR2_MGMT_EXCLUDE,
            "basis": "OLD_EXCLUDE_BASIS",
            "responsible": "OLD_RESP",
            "review_deadline": "01.01.2026",
            "comment": "OLD_EXCLUDE_COMMENT",
            "override": False,
        }
        record.update(extra)
        self.st.session_state[self.mod.WR2_SESSION_EXCLUDED] = {self.pid: record}
        return record

    def _seed_include_risk(self, **extra: Any) -> Dict[str, Any]:
        record = {
            "decision": self.mod.WR2_MGMT_INCLUDE_RISK,
            "basis": "RISK_BASIS",
            "responsible": "RISK_RESP",
            "review_deadline": "10.10.2026",
            "comment": "RISK_COMMENT_COMMON",
            "risk_description": "DURABLE_RISK_DESCRIPTION",
            "risk_impact": "DURABLE_RISK_IMPACT",
            "risk_mitigation_owner": "DURABLE_RISK_RESPONSIBLE",
            "risk_mitigation_deadline": "20.10.2026",
            "risk_acceptance_basis": "DURABLE_RISK_ACCEPTANCE",
            "risk_manager_comment": "DURABLE_RISK_COMMENT",
            "override": True,
        }
        record.update(extra)
        self.st.session_state[self.mod.WR2_SESSION_COMPOSITION] = {self.pid: record}
        return record

    def test_t1_defer_to_include_risk_no_basis_leak(self) -> None:
        """T1 DEFER → INCLUDE_RISK: basis/comment do not fill risk_*; live risk kept."""
        self._seed_deferred()
        # Initial hydrate as DEFER
        self.mod.wr2_sync_decision_type_change(self.pid, self.mod.WR2_MGMT_POSTPONE)
        # Simulate live risk typing after type change
        self.mod.wr2_sync_decision_type_change(
            self.pid, self.mod.WR2_MGMT_INCLUDE_RISK
        )
        risk_desc_key = self.mod.wr2_risk_reason_text_key(self.pid)
        risk_comment_key = self.mod.wr2_risk_comment_key(self.pid)
        self.assertEqual(self.st.session_state.get(risk_desc_key, ""), "")
        self.assertEqual(self.st.session_state.get(risk_comment_key, ""), "")
        self.assertNotEqual(
            self.st.session_state.get(risk_desc_key, ""),
            "OLD_DEFER_BASIS",
        )
        # Live risk input must win
        self.st.session_state[risk_desc_key] = "LIVE_RISK_DESCRIPTION"
        self.st.session_state[self.mod.wr2_risk_impact_key(self.pid)] = "LIVE_IMPACT"
        self.st.session_state[self.mod.wr2_risk_responsible_key(self.pid)] = "LIVE_OWNER"
        self.st.session_state[self.mod.wr2_risk_deadline_key(self.pid)] = "15.08.2026"
        self.st.session_state[
            self.mod.wr2_risk_acceptance_basis_key(self.pid)
        ] = "LIVE_ACCEPT"
        self.st.session_state[risk_comment_key] = "LIVE_RISK_COMMENT"

        payload = self.mod.wr2_build_mgmt_rpc_payload(
            self.row,
            decision=self.mod.WR2_MGMT_INCLUDE_RISK,
            basis=self.mod.wr2_get_decision_basis(self.pid),
            responsible="LIVE_OWNER",
            review_deadline="15.08.2026",
            comment=self.mod.wr2_get_decision_comment(self.pid),
            risk_description=self.mod.wr2_get_risk_reason_text(self.pid),
            risk_impact=self.mod.wr2_get_risk_impact(self.pid),
            risk_mitigation_owner=self.mod.wr2_get_risk_responsible(self.pid),
            risk_mitigation_deadline=self.mod.wr2_get_risk_deadline(self.pid),
            risk_acceptance_basis=self.mod.wr2_get_risk_acceptance_basis(self.pid),
            risk_manager_comment=self.mod.wr2_get_risk_comment(self.pid),
            override=True,
        )
        self.assertEqual(payload["risk_description"], "LIVE_RISK_DESCRIPTION")
        self.assertEqual(payload["risk_manager_comment"], "LIVE_RISK_COMMENT")
        self.assertNotEqual(payload["risk_description"], "OLD_DEFER_BASIS")
        self.assertNotEqual(payload["risk_manager_comment"], "OLD_DEFER_COMMENT")
        self.assertTrue(payload["management_override"])

    def test_t2_exclude_to_include_clears_baskets_no_risk(self) -> None:
        """T2 EXCLUDE → INCLUDE: excluded cleared, composition added, no risk payload."""
        self._seed_excluded()
        self.mod.wr2_sync_decision_type_change(self.pid, self.mod.WR2_MGMT_EXCLUDE)
        self.mod.wr2_sync_decision_type_change(self.pid, self.mod.WR2_MGMT_INCLUDE)

        # Stale risk widgets must not affect INCLUDE payload
        self.st.session_state[
            self.mod.wr2_risk_reason_text_key(self.pid)
        ] = "STALE_RISK"
        payload = self.mod.wr2_build_mgmt_rpc_payload(
            self.row,
            decision=self.mod.WR2_MGMT_INCLUDE,
            basis="NEW_INCLUDE_BASIS",
            responsible="R",
            review_deadline="01.02.2026",
            comment="NEW_INCLUDE_COMMENT",
            risk_description="STALE_RISK",
            risk_impact="STALE",
            risk_mitigation_owner="STALE",
            risk_mitigation_deadline="STALE",
            risk_acceptance_basis="STALE",
            risk_manager_comment="STALE",
            override=False,
        )
        self.assertEqual(payload["risk_description"], "")
        self.assertEqual(payload["risk_manager_comment"], "")

        with patch.object(
            self.mod,
            "apply_management_decision",
            return_value={"ok": True, "decision_id": "test-id"},
        ), patch.object(
            self.mod,
            "load_management_decisions",
            return_value=[{"plan_line_id": self.pid}],
        ):
            errors = self.mod.wr2_apply_management_decision(
                self.row,
                self.mod.WR2_MGMT_INCLUDE,
                basis="NEW_INCLUDE_BASIS",
                responsible="R",
                review_deadline="01.02.2026",
                comment="NEW_INCLUDE_COMMENT",
                risk_description="STALE_RISK",
                risk_impact="STALE",
                risk_mitigation_owner="STALE",
                risk_mitigation_deadline="STALE",
                risk_acceptance_basis="STALE",
                risk_manager_comment="STALE",
            )
        self.assertEqual(errors, [])
        self.assertNotIn(self.pid, self.st.session_state[self.mod.WR2_SESSION_EXCLUDED])
        self.assertIn(self.pid, self.st.session_state[self.mod.WR2_SESSION_COMPOSITION])
        self.assertEqual(
            self.st.session_state[self.mod.WR2_SESSION_COMPOSITION][self.pid][
                "decision"
            ],
            self.mod.WR2_MGMT_INCLUDE,
        )
        self.assertEqual(
            self.st.session_state[self.mod.WR2_SESSION_COMPOSITION][self.pid][
                "risk_description"
            ],
            "",
        )

    def test_t3_include_risk_to_defer_strips_risk_payload(self) -> None:
        """T3 INCLUDE_RISK → DEFER: risk fields not sent in DEFER payload."""
        self._seed_include_risk()
        self.mod.wr2_sync_decision_type_change(
            self.pid, self.mod.WR2_MGMT_INCLUDE_RISK
        )
        # Leave risk widgets populated, then switch type
        self.mod.wr2_sync_decision_type_change(self.pid, self.mod.WR2_MGMT_POSTPONE)
        self.assertEqual(
            self.st.session_state.get(self.mod.wr2_risk_reason_text_key(self.pid), ""),
            "",
        )
        payload = self.mod.wr2_build_mgmt_rpc_payload(
            self.row,
            decision=self.mod.WR2_MGMT_POSTPONE,
            basis="DEFER_BASIS",
            responsible="R",
            review_deadline="01.03.2026",
            comment="DEFER_COMMENT",
            risk_description="SHOULD_NOT_SEND",
            risk_impact="SHOULD_NOT_SEND",
            risk_mitigation_owner="SHOULD_NOT_SEND",
            risk_mitigation_deadline="SHOULD_NOT_SEND",
            risk_acceptance_basis="SHOULD_NOT_SEND",
            risk_manager_comment="SHOULD_NOT_SEND",
            override=False,
        )
        self.assertEqual(payload["risk_description"], "")
        self.assertEqual(payload["risk_impact"], "")
        self.assertEqual(payload["risk_manager_comment"], "")

    def test_t4_include_risk_rehydrate_durable(self) -> None:
        """T4 INCLUDE_RISK → INCLUDE_RISK: durable risk fields hydrate."""
        self._seed_include_risk()
        self.mod.wr2_sync_decision_type_change(
            self.pid, self.mod.WR2_MGMT_INCLUDE_RISK
        )
        self.assertEqual(
            self.st.session_state[self.mod.wr2_risk_reason_text_key(self.pid)],
            "DURABLE_RISK_DESCRIPTION",
        )
        self.assertEqual(
            self.st.session_state[self.mod.wr2_risk_impact_key(self.pid)],
            "DURABLE_RISK_IMPACT",
        )
        self.assertEqual(
            self.st.session_state[self.mod.wr2_risk_comment_key(self.pid)],
            "DURABLE_RISK_COMMENT",
        )
        # Switch away and back to same durable type restores risk
        self.mod.wr2_sync_decision_type_change(self.pid, self.mod.WR2_MGMT_POSTPONE)
        self.mod.wr2_sync_decision_type_change(
            self.pid, self.mod.WR2_MGMT_INCLUDE_RISK
        )
        self.assertEqual(
            self.st.session_state[self.mod.wr2_risk_reason_text_key(self.pid)],
            "DURABLE_RISK_DESCRIPTION",
        )

    def test_t5_live_widget_overrides_old_record(self) -> None:
        """T5 live widget input overrides durable/session record on Apply getters."""
        self._seed_deferred()
        self.mod.wr2_sync_decision_type_change(self.pid, self.mod.WR2_MGMT_POSTPONE)
        basis_key = self.mod.wr2_decision_basis_key(self.pid)
        self.st.session_state[basis_key] = "LIVE_BASIS_OVERRIDE"
        self.assertEqual(self.mod.wr2_get_decision_basis(self.pid), "LIVE_BASIS_OVERRIDE")
        # Absent widget key falls back to record
        del self.st.session_state[basis_key]
        self.assertEqual(self.mod.wr2_get_decision_basis(self.pid), "OLD_DEFER_BASIS")

    def test_t6_rerun_without_radio_change_keeps_form(self) -> None:
        """T6 rerun without radio change does not clear form."""
        self._seed_deferred()
        self.mod.wr2_sync_decision_type_change(self.pid, self.mod.WR2_MGMT_POSTPONE)
        basis_key = self.mod.wr2_decision_basis_key(self.pid)
        comment_key = self.mod.wr2_decision_comment_key(self.pid)
        self.st.session_state[basis_key] = "USER_TYPED_BASIS"
        self.st.session_state[comment_key] = "USER_TYPED_COMMENT"
        # Simulate Streamlit rerun with same radio
        self.mod.wr2_sync_decision_type_change(self.pid, self.mod.WR2_MGMT_POSTPONE)
        self.mod.wr2_sync_decision_type_change(self.pid, self.mod.WR2_MGMT_POSTPONE)
        self.assertEqual(self.st.session_state[basis_key], "USER_TYPED_BASIS")
        self.assertEqual(self.st.session_state[comment_key], "USER_TYPED_COMMENT")

    def test_dash_placeholder_not_hydrated(self) -> None:
        self._seed_deferred(basis="—", comment="-")
        self.mod.wr2_hydrate_decision_widgets(
            self.pid,
            live_decision=self.mod.WR2_MGMT_POSTPONE,
            force=True,
        )
        self.assertEqual(
            self.st.session_state.get(self.mod.wr2_decision_basis_key(self.pid), ""),
            "",
        )
        self.assertEqual(
            self.st.session_state.get(self.mod.wr2_decision_comment_key(self.pid), ""),
            "",
        )

    def test_apply_button_labels(self) -> None:
        self.assertEqual(
            self.mod.wr2_apply_button_label(self.row, self.mod.WR2_MGMT_POSTPONE),
            "Применить управленческое решение",
        )
        self._seed_deferred()
        self.assertEqual(
            self.mod.wr2_apply_button_label(self.row, self.mod.WR2_MGMT_POSTPONE),
            "Обновить решение",
        )
        self.assertEqual(
            self.mod.wr2_apply_button_label(
                self.row, self.mod.WR2_MGMT_INCLUDE_RISK
            ),
            "Пересмотреть решение",
        )


if __name__ == "__main__":
    unittest.main()
