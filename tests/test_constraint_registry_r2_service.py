"""
Unit tests for R2 constraint registry update service.

No product DB writes. Run:
  python -m unittest tests.test_constraint_registry_r2_service -v
"""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from services import monthly_plan_constraint_registry_service as svc


class ConstraintRegistryR2ServiceTests(unittest.TestCase):
    def test_t01_patch_normalization_empty_markers_to_none(self) -> None:
        patch_in = {
            "problem_owner": "—",
            "owner_name": "-",
            "required_action": "–",
            "problem_description": "",
        }
        out = svc.normalize_update_patch(patch_in)
        self.assertEqual(out["problem_owner"], None)
        self.assertEqual(out["owner_name"], None)
        self.assertEqual(out["required_action"], None)
        self.assertEqual(out["problem_description"], None)

    def test_t02_unknown_key_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            svc.normalize_update_patch({"resolution_basis": "x"})
        self.assertIn("Недопустимое поле", str(ctx.exception))

    def test_t03_enum_uppercase(self) -> None:
        out = svc.normalize_update_patch(
            {
                "deadline_source": "customer",
                "constraint_priority": "high",
            }
        )
        self.assertEqual(out["deadline_source"], "CUSTOMER")
        self.assertEqual(out["constraint_priority"], "HIGH")

    def test_deadline_status_rejected_from_normalize_patch(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            svc.normalize_update_patch({"deadline_status": "RESOLVED"})
        self.assertIn("Недопустимое поле", str(ctx.exception))
        self.assertNotIn("deadline_status", svc.UPDATE_PATCH_WHITELIST)

    def test_t04_dates_normalize_iso(self) -> None:
        out = svc.normalize_update_patch(
            {
                "constraint_occurred_at": date(2026, 8, 1),
                "target_resolution_date": "2026-08-15",
                "next_control_date": "—",
            }
        )
        self.assertEqual(out["constraint_occurred_at"], "2026-08-01")
        self.assertEqual(out["target_resolution_date"], "2026-08-15")
        self.assertIsNone(out["next_control_date"])

    def test_t05_null_clear_keeps_key(self) -> None:
        out = svc.normalize_update_patch({"owner_name": None})
        self.assertIn("owner_name", out)
        self.assertIsNone(out["owner_name"])

    def test_t06_update_success_mocked_clears_read_caches(self) -> None:
        client = MagicMock()
        client.rpc.return_value.execute.return_value = MagicMock(
            data={"status": "updated", "constraint_id": "cid-1"}
        )
        with patch.object(svc, "get_write_client", return_value=client):
            with patch.object(svc, "clear_registry_read_caches") as clear_fn:
                with patch.object(svc, "clear_constraint_registry_caches") as full_clear:
                    result = svc.update_constraint(
                        constraint_id="cccccccc-cccc-cccc-cccc-cccccccc0001",
                        updated_by="TEST",
                        update_comment="upd",
                        patch={"problem_owner": "Owner A"},
                    )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "updated")
        self.assertIsNone(result["error"])
        clear_fn.assert_called_once()
        full_clear.assert_not_called()
        args = client.rpc.call_args
        self.assertEqual(args.args[0], "update_monthly_plan_constraint")
        self.assertEqual(args.args[1]["p_patch"]["problem_owner"], "Owner A")

    def test_t07_no_changes_skips_rpc(self) -> None:
        client = MagicMock()
        with patch.object(svc, "get_write_client", return_value=client):
            result = svc.update_constraint(
                constraint_id="cccccccc-cccc-cccc-cccc-cccccccc0001",
                updated_by="TEST",
                update_comment="upd",
                patch={},
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "no_changes")
        client.rpc.assert_not_called()

    def test_t08_controlled_error_fake_not_found(self) -> None:
        client = MagicMock()
        client.rpc.return_value.execute.side_effect = Exception(
            "update_monthly_plan_constraint: constraint_id "
            "cccccccc-cccc-cccc-cccc-cccccccc9999 not found"
        )
        with patch.object(svc, "get_write_client", return_value=client):
            result = svc.update_constraint(
                constraint_id="cccccccc-cccc-cccc-cccc-cccccccc9999",
                updated_by="TEST",
                update_comment="upd",
                patch={"problem_owner": "X"},
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "error")
        self.assertIn("не найдено", result["error"].lower())

    def test_t09_event_payload_parse(self) -> None:
        parsed = svc.parse_constraint_event_payload(
            {
                "changed_fields": ["owner_name", "deadline_status"],
                "old_values": {"owner_name": "A"},
                "new_values": {"owner_name": "B", "deadline_status": "CONFIRMED"},
                "source_page": "24",
                "comment": "note",
            }
        )
        self.assertEqual(parsed["changed_fields"], ["owner_name", "deadline_status"])
        self.assertEqual(parsed["old_values"]["owner_name"], "A")
        self.assertEqual(parsed["new_values"]["deadline_status"], "CONFIRMED")
        self.assertEqual(parsed["source_page"], "24")
        self.assertEqual(parsed["comment"], "note")

    def test_t10_clear_registry_read_caches_only(self) -> None:
        with patch.object(svc.load_constraint_registry, "clear") as reg_clear:
            with patch.object(svc.load_constraint_events, "clear") as ev_clear:
                with patch.object(svc, "_try_clear_loaded_page_helper") as page_helper:
                    out = svc.clear_registry_read_caches()
        self.assertTrue(out["registry"])
        self.assertTrue(out["events"])
        reg_clear.assert_called_once()
        ev_clear.assert_called_once()
        page_helper.assert_not_called()

    def test_t11_resolve_service_still_works(self) -> None:
        client = MagicMock()
        client.rpc.return_value.execute.return_value = MagicMock(
            data={"status": "resolved"}
        )
        with patch.object(svc, "get_write_client", return_value=client):
            with patch.object(svc, "clear_constraint_registry_caches") as clear_fn:
                result = svc.resolve_constraint(
                    constraint_id="cccccccc-cccc-cccc-cccc-cccccccc0001",
                    actual_resolution_date=date(2026, 8, 1),
                    resolution_comment="done",
                    closed_by="TEST",
                )
        self.assertTrue(result["ok"])
        clear_fn.assert_called_once()
        self.assertEqual(client.rpc.call_args.args[0], "resolve_monthly_plan_constraint")


if __name__ == "__main__":
    unittest.main()
