"""
Unit tests for constraint created_by write-once semantics.

No product DB writes. Run:
  python -m unittest tests.test_constraint_created_by -v
"""

from __future__ import annotations

import unittest

from services.constraints_service import (
    _build_constraint_row,
    is_created_by_empty,
    merge_created_by_once,
)


class CreatedByWriteOnceTests(unittest.TestCase):
    def test_t1_first_fixation_sets_created_by(self) -> None:
        payload = {"updated_by": "Ivanov", "check_status": "HOLD"}
        out = merge_created_by_once(
            payload,
            existing_created_by=None,
            recorder_name="Ivanov I.I.",
        )
        self.assertEqual(out.get("created_by"), "Ivanov I.I.")
        self.assertEqual(out.get("updated_by"), "Ivanov")

    def test_t1b_empty_string_existing_sets_created_by(self) -> None:
        out = merge_created_by_once(
            {"updated_by": "Petrov"},
            existing_created_by="  ",
            recorder_name="Petrov P.P.",
        )
        self.assertEqual(out.get("created_by"), "Petrov P.P.")

    def test_t2_second_edit_does_not_overwrite_created_by(self) -> None:
        payload = {"updated_by": "Sidorov"}
        out = merge_created_by_once(
            payload,
            existing_created_by="Ivanov I.I.",
            recorder_name="Sidorov S.S.",
        )
        self.assertNotIn("created_by", out)
        self.assertEqual(out.get("updated_by"), "Sidorov")

    def test_t3_updated_by_still_changes_on_edit(self) -> None:
        first = merge_created_by_once(
            {"updated_by": "A"},
            existing_created_by=None,
            recorder_name="A",
        )
        second = merge_created_by_once(
            {"updated_by": "B"},
            existing_created_by=first.get("created_by"),
            recorder_name="B",
        )
        self.assertEqual(first["created_by"], "A")
        self.assertEqual(first["updated_by"], "A")
        self.assertNotIn("created_by", second)
        self.assertEqual(second["updated_by"], "B")

    def test_blank_recorder_does_not_stamp(self) -> None:
        out = merge_created_by_once(
            {"updated_by": "X"},
            existing_created_by=None,
            recorder_name="  ",
        )
        self.assertNotIn("created_by", out)

    def test_is_created_by_empty(self) -> None:
        self.assertTrue(is_created_by_empty(None))
        self.assertTrue(is_created_by_empty(""))
        self.assertTrue(is_created_by_empty("nan"))
        self.assertFalse(is_created_by_empty("Ivanov"))

    def test_auto_create_omits_created_by(self) -> None:
        row = _build_constraint_row(
            {
                "draft_id": "d1",
                "line_id": "l1",
                "project_code": "P",
                "month_key": "m",
                "boq_code": "B",
                "boq_name": "N",
            },
            {
                "gate_layer": "EXECUTABILITY",
                "responsible_department": "ПТО",
                "check_name": "check",
            },
        )
        self.assertNotIn("created_by", row)


if __name__ == "__main__":
    unittest.main()
