"""
Isolated unit tests for Registry R2 service layer.

No product writes. RPC calls are mocked.
Run: python -m unittest tests.test_constraint_registry_r2_service -v
"""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd

from services import monthly_plan_constraint_registry_service as svc


class NormalizeUpdatePatchTests(unittest.TestCase):
    def test_t1_patch_normalization(self) -> None:
        patch, err = svc.normalize_update_patch(
            {
                "problem_owner": "  Заказчик  ",
                "owner_name": "—",
                "deadline_status": "confirmed",
                "deadline_source": "teq",
                "constraint_priority": "high",
                "target_resolution_date": date(2026, 8, 20),
                "next_control_date": "",
                "problem_description": "-",
            }
        )
        self.assertIsNone(err)
        assert patch is not None
        self.assertEqual(patch["problem_owner"], "Заказчик")
        self.assertIsNone(patch["owner_name"])
        self.assertEqual(patch["deadline_status"], "CONFIRMED")
        self.assertEqual(patch["deadline_source"], "TEQ")
        self.assertEqual(patch["constraint_priority"], "HIGH")
        self.assertEqual(patch["target_resolution_date"], "2026-08-20")
        self.assertIsNone(patch["next_control_date"])
        self.assertIsNone(patch["problem_description"])

    def test_t2_invalid_key_rejected(self) -> None:
        patch, err = svc.normalize_update_patch(
            {"required_action": "ok", "check_status": "PASS"}
        )
        self.assertIsNone(patch)
        self.assertIsNotNone(err)
        assert err is not None
        self.assertIn("unknown or forbidden patch key", err)


class UpdateConstraintServiceTests(unittest.TestCase):
    def test_t3_update_open_success(self) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = {
            "status": "updated",
            "constraint_id": "bbbbbbbb-bbbb-cccc-dddd-eeeeeeee1001",
            "changed_fields": ["owner_name"],
            "event_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeee0001",
        }
        mock_client.rpc.return_value.execute.return_value = mock_resp

        with patch.object(svc, "get_write_client", return_value=mock_client), patch.object(
            svc, "clear_registry_read_caches", return_value={"registry": True, "events": True}
        ) as clear_mock:
            result = svc.update_constraint(
                "bbbbbbbb-bbbb-cccc-dddd-eeeeeeee1001",
                "R2 Tester",
                "Обновление",
                {"owner_name": "Проектный институт"},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "updated")
        self.assertIsNone(result["error"])
        self.assertEqual(result["data"]["status"], "updated")
        clear_mock.assert_called_once()
        args, kwargs = mock_client.rpc.call_args
        self.assertEqual(args[0], svc.RPC_UPDATE)
        self.assertEqual(args[1]["p_patch"]["owner_name"], "Проектный институт")

    def test_t4_no_changes(self) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = {
            "status": "no_changes",
            "constraint_id": "bbbbbbbb-bbbb-cccc-dddd-eeeeeeee1001",
            "event_id": None,
            "changed_fields": [],
        }
        mock_client.rpc.return_value.execute.return_value = mock_resp

        with patch.object(svc, "get_write_client", return_value=mock_client), patch.object(
            svc, "clear_registry_read_caches", return_value={"registry": True, "events": True}
        ) as clear_mock:
            result = svc.update_constraint(
                "bbbbbbbb-bbbb-cccc-dddd-eeeeeeee1001",
                "R2 Tester",
                "Повтор",
                {"owner_name": "Проектный институт"},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "no_changes")
        clear_mock.assert_called_once()

    def test_t5_controlled_error(self) -> None:
        mock_client = MagicMock()
        mock_client.rpc.return_value.execute.side_effect = Exception(
            "update_monthly_plan_constraint: cannot update resolution_status=RESOLVED (only OPEN/IN_PROGRESS)"
        )

        with patch.object(svc, "get_write_client", return_value=mock_client), patch.object(
            svc, "clear_registry_read_caches"
        ) as clear_mock:
            result = svc.update_constraint(
                "bbbbbbbb-bbbb-cccc-dddd-eeeeeeee1003",
                "R2 Tester",
                "try",
                {"required_action": "x"},
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "error")
        self.assertIn("OPEN/IN_PROGRESS", result["error"] or "")
        clear_mock.assert_not_called()

    def test_t5b_validation_error_no_rpc(self) -> None:
        with patch.object(svc, "get_write_client") as client_mock:
            result = svc.update_constraint(
                "bbbbbbbb-bbbb-cccc-dddd-eeeeeeee1001",
                "R2 Tester",
                "try",
                {"resolution_basis": "letter"},
            )
        self.assertFalse(result["ok"])
        self.assertIn("unknown or forbidden patch key", result["error"] or "")
        client_mock.assert_not_called()


class EventParseAndCacheTests(unittest.TestCase):
    def test_t6_updated_event_parse(self) -> None:
        parsed = svc.parse_constraint_event_payload(
            {
                "source_page": "PAGE_24_CONSTRAINT_REGISTRY",
                "changed_fields": ["owner_name", "deadline_status"],
                "old_values": {"owner_name": "A"},
                "new_values": {"owner_name": "B", "deadline_status": "CONFIRMED"},
            }
        )
        self.assertEqual(parsed["source_page"], "PAGE_24_CONSTRAINT_REGISTRY")
        self.assertEqual(parsed["changed_fields"], ["owner_name", "deadline_status"])
        self.assertEqual(parsed["old_values"]["owner_name"], "A")
        self.assertEqual(parsed["new_values"]["owner_name"], "B")
        self.assertIn("changed_fields", parsed["raw"])

    def test_t7_cache_clear_registry_events_only(self) -> None:
        with patch.object(svc.load_constraint_registry, "clear") as reg_clear, patch.object(
            svc.load_constraint_events, "clear"
        ) as ev_clear, patch.object(svc, "_try_clear_loaded_page_helper") as page_helper:
            cleared = svc.clear_registry_read_caches()
        self.assertTrue(cleared["registry"])
        self.assertTrue(cleared["events"])
        reg_clear.assert_called_once()
        ev_clear.assert_called_once()
        page_helper.assert_not_called()


class ResolveStillWorksTests(unittest.TestCase):
    def test_t8_resolve_service_not_broken(self) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = {
            "status": "resolved",
            "constraint_id": "bbbbbbbb-bbbb-cccc-dddd-eeeeeeee1005",
            "new_check_status": "PASS",
            "new_resolution_status": "RESOLVED",
        }
        mock_client.rpc.return_value.execute.return_value = mock_resp

        with patch.object(svc, "get_write_client", return_value=mock_client), patch.object(
            svc, "clear_constraint_registry_caches", return_value={}
        ):
            result = svc.resolve_constraint(
                "bbbbbbbb-bbbb-cccc-dddd-eeeeeeee1005",
                date(2026, 8, 6),
                "Снято",
                "Closer",
                {"resolution_basis": "Письмо"},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["status"], "resolved")
        args, _kwargs = mock_client.rpc.call_args
        self.assertEqual(args[0], svc.RPC_RESOLVE)


class DisplayAndReadModelTests(unittest.TestCase):
    def test_display_labels(self) -> None:
        self.assertEqual(svc.display_deadline_status("OVERDUE"), "Просрочен")
        self.assertEqual(svc.display_deadline_source("CUSTOMER"), "Заказчик")
        self.assertEqual(svc.display_constraint_priority("CRITICAL"), "Критический")

    def test_read_model_includes_r2_fields(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "constraint_id": "c1",
                    "line_id": "l1",
                    "project_code": "TEST_REG_R2",
                    "month_key": "test-r2-2026",
                    "facility_building": "16160-13",
                    "check_status": "HOLD",
                    "resolution_status": "OPEN",
                    "constraint_created_at": "2026-07-01",
                    "constraint_occurred_at": "2026-06-15",
                    "deadline_status": "CONFIRMED",
                    "deadline_source": "TEQ",
                    "constraint_priority": "HIGH",
                    "days_open_real": 40,
                    "deadline_days_overdue": 5,
                    "is_deadline_overdue": True,
                    "is_next_control_overdue": False,
                    "effective_deadline_status": "OVERDUE",
                    "plan_value": 1000,
                }
            ]
        )
        out = svc.build_constraint_registry_read_model(df)
        for col in (
            "constraint_occurred_at",
            "deadline_status",
            "days_open_real",
            "deadline_days_overdue",
            "is_deadline_overdue",
            "effective_deadline_status",
            "constraint_priority",
            "resolution_basis",
        ):
            self.assertIn(col, out.columns)
        self.assertEqual(int(out.iloc[0]["days_open_real"]), 40)
        self.assertEqual(out.iloc[0]["effective_deadline_status"], "OVERDUE")


if __name__ == "__main__":
    unittest.main()
