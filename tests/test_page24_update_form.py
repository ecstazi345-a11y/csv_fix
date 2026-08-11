"""
Unit tests for Page 24 update-form pure helpers.

No Streamlit runtime, no product writes.
Run: python -m unittest tests.test_page24_update_form -v
"""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

import pages as pages_pkg  # noqa: F401
# Import module by file path helpers — page sets streamlit config on import.
# Load helpers via importlib from the page module carefully.


def _load_page24():
    import importlib.util
    from pathlib import Path

    path = Path(r"c:\csv_fix\pages\24_Реестр_ограничений_допуска_месячного_плана.py")
    spec = importlib.util.spec_from_file_location("page24_registry", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Avoid streamlit page config side effects crashing tests: stub set_page_config
    import streamlit as st

    original = st.set_page_config
    st.set_page_config = lambda *a, **k: None
    try:
        spec.loader.exec_module(mod)
    finally:
        st.set_page_config = original
    return mod


PAGE = _load_page24()


class Page24UpdateFormTests(unittest.TestCase):
    def test_t1_form_hydrate_baseline_by_constraint(self) -> None:
        row = pd.Series(
            {
                "problem_owner": "Заказчик",
                "owner_name": "ПИ",
                "subcontractor_coordinator": None,
                "constraint_category": "МТР",
                "constraint_priority": "high",
                "problem_description": "—",
                "problem_impact": "",
                "required_action": "Выдать TEQ",
                "deadline_status": "confirmed",
                "deadline_source": "teq",
                "constraint_occurred_at": "2026-06-15",
                "target_resolution_date": None,
                "next_control_date": "2026-08-01",
                "actual_resolution_date": None,
            }
        )
        baseline = PAGE.extract_update_baseline(row)
        self.assertEqual(baseline["problem_owner"], "Заказчик")
        self.assertIsNone(baseline["subcontractor_coordinator"])
        self.assertIsNone(baseline["problem_description"])
        self.assertEqual(baseline["constraint_priority"], "HIGH")
        self.assertEqual(baseline["deadline_status"], "CONFIRMED")
        self.assertEqual(baseline["deadline_source"], "TEQ")
        self.assertEqual(baseline["constraint_occurred_at"], date(2026, 6, 15))
        self.assertIsNone(baseline["target_resolution_date"])

    def test_t2_dirty_patch_unchanged_omitted(self) -> None:
        baseline = {
            "problem_owner": "Заказчик",
            "owner_name": "ПИ",
            "subcontractor_coordinator": None,
            "constraint_category": "МТР",
            "problem_description": None,
            "problem_impact": None,
            "required_action": "A",
            "constraint_priority": "NORMAL",
            "deadline_status": "NOT_SET",
            "deadline_source": None,
            "constraint_occurred_at": date(2026, 6, 15),
            "target_resolution_date": None,
            "next_control_date": None,
        }
        patch = PAGE.build_dirty_patch(
            baseline,
            text_values={
                "problem_owner": "Заказчик",
                "owner_name": "ПИ",
                "subcontractor_coordinator": "",
                "constraint_category": "МТР",
                "problem_description": "",
                "problem_impact": "",
                "required_action": "A",
            },
            enum_values={
                "constraint_priority": "NORMAL",
                "deadline_status": "NOT_SET",
                "deadline_source": "",
            },
            date_modes={
                "constraint_occurred_at": PAGE.DATE_MODE_KEEP,
                "target_resolution_date": PAGE.DATE_MODE_KEEP,
                "next_control_date": PAGE.DATE_MODE_KEEP,
            },
            date_values={
                "constraint_occurred_at": None,
                "target_resolution_date": None,
                "next_control_date": None,
            },
        )
        self.assertEqual(patch, {})

    def test_t3_clear_value_to_null(self) -> None:
        baseline = {
            "problem_owner": "Заказчик",
            "owner_name": "ПИ",
            "subcontractor_coordinator": "Иван",
            "constraint_category": "МТР",
            "problem_description": "desc",
            "problem_impact": None,
            "required_action": "A",
            "constraint_priority": "NORMAL",
            "deadline_status": "CONFIRMED",
            "deadline_source": "TEQ",
            "constraint_occurred_at": date(2026, 6, 15),
            "target_resolution_date": date(2026, 8, 1),
            "next_control_date": None,
        }
        patch = PAGE.build_dirty_patch(
            baseline,
            text_values={
                "problem_owner": "Заказчик",
                "owner_name": "ПИ",
                "subcontractor_coordinator": "—",
                "constraint_category": "МТР",
                "problem_description": "desc",
                "problem_impact": "",
                "required_action": "A",
            },
            enum_values={
                "constraint_priority": "NORMAL",
                "deadline_status": "CONFIRMED",
                "deadline_source": "TEQ",
            },
            date_modes={
                "constraint_occurred_at": PAGE.DATE_MODE_KEEP,
                "target_resolution_date": PAGE.DATE_MODE_CLEAR,
                "next_control_date": PAGE.DATE_MODE_KEEP,
            },
            date_values={
                "constraint_occurred_at": None,
                "target_resolution_date": None,
                "next_control_date": None,
            },
        )
        self.assertEqual(patch.get("subcontractor_coordinator"), None)
        self.assertIn("subcontractor_coordinator", patch)
        self.assertEqual(patch.get("target_resolution_date"), None)
        self.assertIn("target_resolution_date", patch)

    def test_t4_technical_enum_mapping(self) -> None:
        baseline = PAGE.extract_update_baseline(
            {
                "constraint_priority": "normal",
                "deadline_status": "requested",
                "deadline_source": "customer",
            }
        )
        self.assertEqual(baseline["constraint_priority"], "NORMAL")
        self.assertEqual(baseline["deadline_status"], "REQUESTED")
        self.assertEqual(baseline["deadline_source"], "CUSTOMER")
        self.assertEqual(PAGE.display_deadline_status("OVERDUE"), "Просрочен")
        self.assertEqual(PAGE.display_deadline_source("TEQ"), "TEQ")

    def test_t5_update_comment_required(self) -> None:
        err = PAGE.validate_update_submission(
            updated_by="Tester",
            update_comment="—",
            patch={"owner_name": "X"},
            baseline={"actual_resolution_date": None, "constraint_occurred_at": None},
        )
        self.assertIsNotNone(err)
        err2 = PAGE.validate_update_submission(
            updated_by="",
            update_comment="ok",
            patch={"owner_name": "X"},
            baseline={"actual_resolution_date": None, "constraint_occurred_at": None},
        )
        self.assertIsNotNone(err2)

    def test_t6_no_changes_no_rpc(self) -> None:
        baseline = PAGE.extract_update_baseline(
            {
                "problem_owner": "A",
                "owner_name": "B",
                "constraint_priority": "NORMAL",
                "deadline_status": "NOT_SET",
            }
        )
        patch = PAGE.build_dirty_patch(
            baseline,
            text_values={
                "problem_owner": "A",
                "owner_name": "B",
                "subcontractor_coordinator": "",
                "constraint_category": "",
                "problem_description": "",
                "problem_impact": "",
                "required_action": "",
            },
            enum_values={
                "constraint_priority": "NORMAL",
                "deadline_status": "NOT_SET",
                "deadline_source": "",
            },
            date_modes={k: PAGE.DATE_MODE_KEEP for k in PAGE.UPDATE_DATE_FIELDS},
            date_values={k: None for k in PAGE.UPDATE_DATE_FIELDS},
        )
        self.assertEqual(patch, {})

    def test_t7_success_clears_caches(self) -> None:
        from services import monthly_plan_constraint_registry_service as svc

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = {"status": "updated", "changed_fields": ["owner_name"]}
        mock_client.rpc.return_value.execute.return_value = mock_resp
        with patch.object(svc, "get_write_client", return_value=mock_client), patch.object(
            svc, "clear_registry_read_caches", return_value={"registry": True, "events": True}
        ) as clear_mock:
            result = svc.update_constraint(
                "bbbbbbbb-bbbb-cccc-dddd-eeeeeeee2001",
                "Tester",
                "comment",
                {"owner_name": "X"},
            )
        self.assertTrue(result["ok"])
        clear_mock.assert_called_once()

    def test_t8_error_preserves_form_contract(self) -> None:
        # Validation error path does not call RPC; form session keys remain caller-owned.
        err = PAGE.validate_update_submission(
            updated_by="Tester",
            update_comment="ok",
            patch={"constraint_occurred_at": "2026-08-10"},
            baseline={
                "actual_resolution_date": date(2026, 8, 1),
                "constraint_occurred_at": date(2026, 6, 1),
            },
        )
        self.assertIsNotNone(err)
        self.assertIn("возникновения", err.lower())

    def test_t9_updated_event_formatting(self) -> None:
        lines = PAGE.format_updated_event_lines(
            {
                "changed_fields": ["owner_name", "deadline_status"],
                "old_values": {"owner_name": "A", "deadline_status": "NOT_SET"},
                "new_values": {"owner_name": "B", "deadline_status": "CONFIRMED"},
            }
        )
        self.assertTrue(any("Исполнитель" in x and "A → B" in x for x in lines))
        self.assertTrue(any("Статус срока" in x for x in lines))

    def test_t10_resolved_form_disabled(self) -> None:
        self.assertFalse(PAGE.can_edit_constraint("RESOLVED"))
        self.assertFalse(PAGE.can_edit_constraint("CANCELLED"))
        self.assertTrue(PAGE.can_edit_constraint("OPEN"))
        self.assertTrue(PAGE.can_edit_constraint("IN_PROGRESS"))


if __name__ == "__main__":
    unittest.main()
