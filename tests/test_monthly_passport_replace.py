"""
Unit tests for monthly passport replace/rebuild (RPC path).

Does not write to production DB. RPC is mocked.
Run: python -m unittest tests.test_monthly_passport_replace -v
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from services import monthly_passport_service as mps


class ValidatePayloadTests(unittest.TestCase):
    def test_empty_lines_forbidden(self) -> None:
        errs = mps.validate_passport_line_payloads("P", "август-2026", [])
        self.assertTrue(errs)

    def test_duplicate_line_id(self) -> None:
        lines = [
            {"line_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "boq_code": "A", "project_code": "P", "month_key": "август-2026"},
            {"line_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "boq_code": "B", "project_code": "P", "month_key": "август-2026"},
        ]
        errs = mps.validate_passport_line_payloads("P", "август-2026", lines)
        self.assertTrue(any("Дублирующий" in e for e in errs))

    def test_project_month_mismatch(self) -> None:
        lines = [
            {
                "line_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "boq_code": "A",
                "project_code": "OTHER",
                "month_key": "июль-2026",
            }
        ]
        errs = mps.validate_passport_line_payloads("P", "август-2026", lines)
        self.assertGreaterEqual(len(errs), 2)

    def test_ok_payload(self) -> None:
        lines = [
            {
                "line_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "boq_code": "A",
                "project_code": "P",
                "month_key": "август-2026",
            },
            {
                "line_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "boq_code": "B",
                "project_code": "P",
                "month_key": "август-2026",
            },
        ]
        self.assertEqual(mps.validate_passport_line_payloads("P", "август-2026", lines), [])


class CreateMonthlyPassportRpcTests(unittest.TestCase):
    def _source_rows(self, n: int = 2) -> List[Dict[str, Any]]:
        rows = []
        for i in range(n):
            rows.append(
                {
                    "line_id": f"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa{i}",
                    "boq_code": f"BOQ-{i}",
                    "boq_name": f"Name {i}",
                    "project_code": "PRJ_TEST",
                    "month_key": "август-2026",
                    "plan_value": 100.0 * (i + 1),
                    "required_hours": 2.0 * (i + 1),
                    "labor_cost": 50.0 * (i + 1),
                    "management_override": False,
                }
            )
        return rows

    def _mock_write_client(self, rpc_result: Dict[str, Any]) -> MagicMock:
        client = MagicMock()
        rpc = MagicMock()
        rpc.execute.return_value = MagicMock(data=rpc_result)
        client.rpc.return_value = rpc
        return client

    @patch.object(mps, "get_write_client")
    @patch.object(mps, "load_passport_source_rows")
    @patch.object(mps, "_fetch_constraints_for_lines")
    def test_created_via_rpc(
        self,
        mock_constraints: MagicMock,
        mock_source: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        sources = self._source_rows(2)
        mock_source.return_value = (sources, [], "v2")
        mock_constraints.return_value = {
            sources[0]["line_id"]: [{"check_status": "PASS"}],
            sources[1]["line_id"]: [{"check_status": "PASS"}],
        }
        mock_write.return_value = self._mock_write_client(
            {
                "status": "created",
                "passport_id": "pppppppp-pppp-pppp-pppp-pppppppppppp",
                "previous_rows": 0,
                "current_rows": 2,
                "added_count": 2,
                "removed_count": 0,
                "updated_count": 0,
            }
        )

        summary = mps.create_monthly_passport("PRJ_TEST", "август-2026", created_by="tester")
        self.assertEqual(summary["status"], "created")
        self.assertEqual(summary["current_rows"], 2)
        self.assertEqual(summary["created_lines"], 2)
        self.assertEqual(summary["previous_rows"], 0)
        mock_write.return_value.rpc.assert_called_once()
        args, kwargs = mock_write.return_value.rpc.call_args
        self.assertEqual(args[0], "replace_monthly_passport")
        self.assertEqual(args[1]["p_expected_rows"], 2)
        self.assertNotIn("passport_id", args[1]["p_lines"][0])

    @patch.object(mps, "get_write_client")
    @patch.object(mps, "load_passport_source_rows")
    @patch.object(mps, "_fetch_constraints_for_lines")
    def test_rebuilt_via_rpc(
        self,
        mock_constraints: MagicMock,
        mock_source: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        sources = self._source_rows(4)
        mock_source.return_value = (sources, [], "v2")
        mock_constraints.return_value = {
            r["line_id"]: [{"check_status": "PASS"}] for r in sources
        }
        mock_write.return_value = self._mock_write_client(
            {
                "status": "rebuilt",
                "passport_id": "pppppppp-pppp-pppp-pppp-pppppppppppp",
                "previous_rows": 1,
                "current_rows": 4,
                "added_count": 3,
                "removed_count": 0,
                "updated_count": 1,
            }
        )
        summary = mps.create_monthly_passport("PRJ_TEST", "август-2026")
        self.assertEqual(summary["status"], "rebuilt")
        self.assertEqual(summary["passport_id"], "pppppppp-pppp-pppp-pppp-pppppppppppp")
        self.assertEqual(summary["previous_rows"], 1)
        self.assertEqual(summary["current_rows"], 4)

    @patch.object(mps, "get_write_client")
    @patch.object(mps, "load_passport_source_rows")
    @patch.object(mps, "_fetch_constraints_for_lines")
    def test_no_already_exists_early_return(
        self,
        mock_constraints: MagicMock,
        mock_source: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        """Existing passport must still call RPC (rebuilt), not already_exists."""
        sources = self._source_rows(1)
        mock_source.return_value = (sources, [], "v2")
        mock_constraints.return_value = {
            sources[0]["line_id"]: [{"check_status": "PASS"}]
        }
        mock_write.return_value = self._mock_write_client(
            {
                "status": "rebuilt",
                "passport_id": "existing-id",
                "previous_rows": 1,
                "current_rows": 1,
                "added_count": 0,
                "removed_count": 0,
                "updated_count": 1,
            }
        )
        summary = mps.create_monthly_passport("PRJ_TEST", "август-2026")
        self.assertNotEqual(summary["status"], "already_exists")
        self.assertEqual(summary["status"], "rebuilt")
        mock_write.return_value.rpc.assert_called_once()

    @patch.object(mps, "get_write_client")
    @patch.object(mps, "load_passport_source_rows")
    @patch.object(mps, "_fetch_constraints_for_lines")
    def test_validation_error_skips_rpc(
        self,
        mock_constraints: MagicMock,
        mock_source: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        # Force duplicate by patching payload builder path: two sources same line_id
        row = {
            "line_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "boq_code": "A",
            "project_code": "PRJ_TEST",
            "month_key": "август-2026",
            "plan_value": 1,
            "required_hours": 1,
            "labor_cost": 1,
            "management_override": False,
        }
        mock_source.return_value = ([row, dict(row)], [], "v2")
        mock_constraints.return_value = {
            row["line_id"]: [{"check_status": "PASS"}]
        }
        client = self._mock_write_client({"status": "created"})
        mock_write.return_value = client

        summary = mps.create_monthly_passport("PRJ_TEST", "август-2026")
        self.assertEqual(summary["status"], "validation_error")
        client.rpc.assert_not_called()

    @patch.object(mps, "get_write_client")
    @patch.object(mps, "load_passport_source_rows")
    @patch.object(mps, "_fetch_constraints_for_lines")
    def test_waiting_without_override_not_in_payload(
        self,
        mock_constraints: MagicMock,
        mock_source: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        sources = self._source_rows(1)
        mock_source.return_value = (sources, [], "v2")
        mock_constraints.return_value = {
            sources[0]["line_id"]: [{"check_status": "ОЖИДАЕТ"}]
        }
        client = self._mock_write_client({})
        mock_write.return_value = client
        summary = mps.create_monthly_passport("PRJ_TEST", "август-2026")
        self.assertEqual(summary["status"], "no_eligible_lines")
        client.rpc.assert_not_called()

    @patch.object(mps, "get_write_client")
    @patch.object(mps, "load_passport_source_rows")
    @patch.object(mps, "_fetch_constraints_for_lines")
    def test_rpc_failure_preserves_error_status(
        self,
        mock_constraints: MagicMock,
        mock_source: MagicMock,
        mock_write: MagicMock,
    ) -> None:
        sources = self._source_rows(1)
        mock_source.return_value = (sources, [], "v2")
        mock_constraints.return_value = {
            sources[0]["line_id"]: [{"check_status": "PASS"}]
        }
        client = MagicMock()
        client.rpc.return_value.execute.side_effect = RuntimeError("db rolled back")
        mock_write.return_value = client
        summary = mps.create_monthly_passport("PRJ_TEST", "август-2026")
        self.assertEqual(summary["status"], "error")
        self.assertTrue(any("RPC" in e for e in summary["errors"]))


class LinePayloadStripTests(unittest.TestCase):
    def test_strip_passport_id(self) -> None:
        row = mps._build_passport_line(
            passport_id=mps.PLACEHOLDER_PASSPORT_ID,
            source_row={
                "line_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "boq_code": "X",
                "project_code": "P",
                "month_key": "август-2026",
            },
            counts={
                "constraints_total": 1,
                "constraints_pass": 1,
                "constraints_warning": 0,
                "constraints_hold": 0,
                "constraints_fail": 0,
                "constraints_waiting": 0,
            },
            admission_status="APPROVED_TO_EXECUTE",
            override={
                "management_override": False,
                "override_by": None,
                "override_at": None,
                "override_reason": None,
                "override_risk_comment": None,
                "override_basis": None,
            },
        )
        safe = mps._line_payload_for_rpc(row)
        self.assertNotIn("passport_id", safe)
        self.assertEqual(safe["boq_code"], "X")


if __name__ == "__main__":
    unittest.main()
