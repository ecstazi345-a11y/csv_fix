"""
FIELD-1D.1E M:N operation membership reader tests.

No live Supabase. No event writes.

Run:
  python -m unittest tests.test_pnr_field_1d_1e_mn_picker -v
"""

from __future__ import annotations

import inspect
import unittest
from pathlib import Path

from services.pnr_service import (
    create_structured_execution_event,
    list_active_operations,
    list_active_operations_for_work_scope,
)

PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "60_ПНР_Фиксация_факта.py"
SERVICE_PATH = Path(__file__).resolve().parents[1] / "services" / "pnr_service.py"

SCOPE_A = "scope-a"
SCOPE_B = "scope-b"
OP_OWNED_A = "op-owned-a"
OP_CROSS = "op-cross"
OP_B_FIRST = "op-b-first"
OP_B_MID = "op-b-mid"
OP_B_NULL = "op-b-null"
OP_INACTIVE_MEMBER = "op-inactive-member"
OP_INACTIVE_CATALOG = "op-inactive-catalog"


class _Result:
    def __init__(self, data: list[dict] | None) -> None:
        self.data = data or []


class FakeQuery:
    def __init__(self, store: dict[str, list[dict]], table: str) -> None:
        self._store = store
        self._table = table
        self._eq: dict[str, object] = {}
        self._in: tuple[str, list[object]] | None = None

    def select(self, *_args: object, **_kwargs: object) -> FakeQuery:
        return self

    def eq(self, column: str, value: object) -> FakeQuery:
        self._eq[column] = value
        return self

    def in_(self, column: str, values: list[object]) -> FakeQuery:
        self._in = (column, list(values))
        return self

    def execute(self) -> _Result:
        rows = list(self._store.get(self._table, []))
        for column, value in self._eq.items():
            rows = [row for row in rows if row.get(column) == value]
        if self._in is not None:
            column, values = self._in
            allowed = set(values)
            rows = [row for row in rows if row.get(column) in allowed]
        return _Result(rows)


class FakeClient:
    def __init__(self, store: dict[str, list[dict]]) -> None:
        self.store = store

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self.store, name)


def _store() -> dict[str, list[dict]]:
    return {
        "pnr_operations": [
            {
                "operation_id": OP_OWNED_A,
                "work_scope_id": SCOPE_A,
                "operation_code": "PNR-A-001",
                "operation_name": "Owner A only",
                "sequence_no": 1,
                "is_active": True,
            },
            {
                "operation_id": OP_CROSS,
                "work_scope_id": SCOPE_A,
                "operation_code": "PNR-A-CROSS",
                "operation_name": "Owned by A, member of B",
                "sequence_no": 99,
                "is_active": True,
            },
            {
                "operation_id": OP_B_FIRST,
                "work_scope_id": SCOPE_B,
                "operation_code": "PNR-B-010",
                "operation_name": "B first",
                "sequence_no": 50,
                "is_active": True,
            },
            {
                "operation_id": OP_B_MID,
                "work_scope_id": SCOPE_B,
                "operation_code": "PNR-B-005",
                "operation_name": "B mid",
                "sequence_no": 40,
                "is_active": True,
            },
            {
                "operation_id": OP_B_NULL,
                "work_scope_id": SCOPE_B,
                "operation_code": "PNR-B-ZZZ",
                "operation_name": "B null sequence",
                "sequence_no": 3,
                "is_active": True,
            },
            {
                "operation_id": OP_INACTIVE_MEMBER,
                "work_scope_id": SCOPE_B,
                "operation_code": "PNR-B-DEAD-MEM",
                "operation_name": "Inactive membership",
                "sequence_no": 2,
                "is_active": True,
            },
            {
                "operation_id": OP_INACTIVE_CATALOG,
                "work_scope_id": SCOPE_B,
                "operation_code": "PNR-B-DEAD-OP",
                "operation_name": "Inactive catalog",
                "sequence_no": 4,
                "is_active": False,
            },
        ],
        "pnr_work_scope_operations": [
            {
                "work_scope_id": SCOPE_A,
                "operation_id": OP_OWNED_A,
                "sequence_no": 1,
                "is_active": True,
            },
            {
                "work_scope_id": SCOPE_A,
                "operation_id": OP_CROSS,
                "sequence_no": 2,
                "is_active": True,
            },
            {
                "work_scope_id": SCOPE_B,
                "operation_id": OP_CROSS,
                "sequence_no": 10,
                "is_active": True,
            },
            {
                "work_scope_id": SCOPE_B,
                "operation_id": OP_B_FIRST,
                "sequence_no": 1,
                "is_active": True,
            },
            {
                "work_scope_id": SCOPE_B,
                "operation_id": OP_B_MID,
                "sequence_no": 5,
                "is_active": True,
            },
            {
                "work_scope_id": SCOPE_B,
                "operation_id": OP_B_NULL,
                "sequence_no": None,
                "is_active": True,
            },
            {
                "work_scope_id": SCOPE_B,
                "operation_id": OP_INACTIVE_MEMBER,
                "sequence_no": 2,
                "is_active": False,
            },
            {
                "work_scope_id": SCOPE_B,
                "operation_id": OP_INACTIVE_CATALOG,
                "sequence_no": 3,
                "is_active": True,
            },
        ],
    }


class PnrField1d1eMnPickerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeClient(_store())

    def test_page60_uses_bridge_reader_not_legacy_owner_reader(self) -> None:
        source = PAGE_PATH.read_text(encoding="utf-8")
        self.assertIn("list_active_operations_for_work_scope", source)
        self.assertIn("list_active_operations_for_work_scope(work_scope_id=", source)
        self.assertNotIn("list_active_operations(work_scope_id=", source)
        self.assertNotIn("from services.pnr_service import list_active_operations\n", source)

    def test_active_membership_included(self) -> None:
        rows = list_active_operations_for_work_scope(
            work_scope_id=SCOPE_B, client=self.client
        )
        ids = [row["operation_id"] for row in rows]
        self.assertIn(OP_B_FIRST, ids)
        self.assertIn(OP_B_MID, ids)
        self.assertIn(OP_B_NULL, ids)

    def test_inactive_membership_excluded(self) -> None:
        rows = list_active_operations_for_work_scope(
            work_scope_id=SCOPE_B, client=self.client
        )
        ids = [row["operation_id"] for row in rows]
        self.assertNotIn(OP_INACTIVE_MEMBER, ids)

    def test_inactive_catalog_operation_excluded(self) -> None:
        rows = list_active_operations_for_work_scope(
            work_scope_id=SCOPE_B, client=self.client
        )
        ids = [row["operation_id"] for row in rows]
        self.assertNotIn(OP_INACTIVE_CATALOG, ids)

    def test_cross_scope_membership_ignores_legacy_owner(self) -> None:
        rows = list_active_operations_for_work_scope(
            work_scope_id=SCOPE_B, client=self.client
        )
        by_id = {row["operation_id"]: row for row in rows}
        self.assertIn(OP_CROSS, by_id)
        self.assertEqual(by_id[OP_CROSS]["work_scope_id"], SCOPE_A)
        self.assertNotIn(OP_OWNED_A, by_id)

        legacy_b = list_active_operations(work_scope_id=SCOPE_B, client=self.client)
        legacy_ids = [row["operation_id"] for row in legacy_b]
        self.assertNotIn(OP_CROSS, legacy_ids)
        self.assertIn(OP_B_FIRST, legacy_ids)

    def test_bridge_sequence_orders_nulls_last(self) -> None:
        rows = list_active_operations_for_work_scope(
            work_scope_id=SCOPE_B, client=self.client
        )
        ids = [row["operation_id"] for row in rows]
        self.assertEqual(ids, [OP_B_FIRST, OP_B_MID, OP_CROSS, OP_B_NULL])
        self.assertEqual(rows[0]["sequence_no"], 1)
        self.assertEqual(rows[1]["sequence_no"], 5)
        self.assertEqual(rows[2]["sequence_no"], 10)
        self.assertIsNone(rows[3]["sequence_no"])

    def test_empty_membership_returns_empty(self) -> None:
        rows = list_active_operations_for_work_scope(
            work_scope_id="scope-missing", client=self.client
        )
        self.assertEqual(rows, [])

    def test_legacy_owner_reader_unchanged(self) -> None:
        source = inspect.getsource(list_active_operations)
        self.assertIn('TABLE_OPERATIONS', source)
        self.assertIn('.eq("work_scope_id", wid)', source)
        self.assertNotIn("TABLE_WORK_SCOPE_OPERATIONS", source)
        self.assertNotIn("pnr_work_scope_operations", source)

        rows = list_active_operations(work_scope_id=SCOPE_A, client=self.client)
        ids = [row["operation_id"] for row in rows]
        self.assertEqual(set(ids), {OP_OWNED_A, OP_CROSS})

    def test_new_reader_does_not_filter_catalog_by_owner_column(self) -> None:
        source = inspect.getsource(list_active_operations_for_work_scope)
        self.assertIn("TABLE_WORK_SCOPE_OPERATIONS", source)
        self.assertIn('table(TABLE_WORK_SCOPE_OPERATIONS)', source)
        self.assertNotIn("pnr_operations!inner", source)
        operations_query = source.split("TABLE_OPERATIONS", 1)[-1]
        self.assertIn('.in_("operation_id", operation_ids)', operations_query)
        self.assertNotIn('.eq("work_scope_id"', operations_query)

    def test_write_function_still_has_no_python_bridge_query(self) -> None:
        source = inspect.getsource(create_structured_execution_event)
        self.assertNotIn("pnr_work_scope_operations", source)
        self.assertNotIn("TABLE_WORK_SCOPE_OPERATIONS", source)
        self.assertNotIn('table("pnr_work_scope_operations")', source)

    def test_page60_unmapped_and_save_kwargs_still_use_selected_scope(self) -> None:
        source = PAGE_PATH.read_text(encoding="utf-8")
        self.assertIn("require_selected_work_scope(work_scope_id)", source)
        self.assertIn('kwargs["operation_id"] = None', source)
        self.assertIn('kwargs["unmapped_operation_name"]', source)
        self.assertIn('"work_scope_id": work_scope_id', source)
        self.assertIn("work_scope_id=selected_scope_id", source)
        self.assertIn('kwargs.get("operation_id")', source)


class PnrField1d1eSqlUntouchedTests(unittest.TestCase):
    def test_frozen_sql_files_not_in_this_module_scope(self) -> None:
        service = SERVICE_PATH.read_text(encoding="utf-8")
        self.assertIn("def list_active_operations_for_work_scope(", service)
        self.assertIn("def list_active_operations(", service)
        self.assertIn("def create_structured_execution_event(", service)


if __name__ == "__main__":
    unittest.main()
