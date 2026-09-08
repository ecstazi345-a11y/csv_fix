"""
PNR MVP-0.3 unit tests. No live Supabase. No event writes to production.

Run:
  python -m unittest tests.test_pnr_service -v
"""

from __future__ import annotations

import inspect
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from services.pnr_service import (
    PnrConfigError,
    PnrValidationError,
    create_execution_event,
    get_pnr_client,
    list_active_objects,
    list_active_operations,
    list_active_systems,
    list_active_work_scopes,
    list_recent_execution_events,
)


SYS_ID = "11111111-1111-4111-8111-111111111111"
OTHER_SYS = "22222222-2222-4222-8222-222222222222"
OBJ_ID = "33333333-3333-4333-8333-333333333333"
SCOPE_ID = "44444444-4444-4444-8444-444444444444"
OP_ID = "55555555-5555-4555-8555-555555555555"
AWARE = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


class _Result:
    def __init__(self, data: list[dict] | None) -> None:
        self.data = data or []


class FakeQuery:
    def __init__(self, store: dict[str, list[dict]], inserts: list, table: str) -> None:
        self._store = store
        self._inserts = inserts
        self._table = table
        self._op = "select"
        self._eq: dict[str, object] = {}
        self._payload: dict | None = None
        self._limit: int | None = None

    def select(self, *_args: object, **_kwargs: object) -> FakeQuery:
        self._op = "select"
        return self

    def eq(self, column: str, value: object) -> FakeQuery:
        self._eq[column] = value
        return self

    def order(self, *_args: object, **_kwargs: object) -> FakeQuery:
        return self

    def limit(self, n: int) -> FakeQuery:
        self._limit = n
        return self

    def insert(self, payload: dict) -> FakeQuery:
        self._op = "insert"
        self._payload = dict(payload)
        return self

    def execute(self) -> _Result:
        if self._op == "insert":
            assert self._payload is not None
            self._inserts.append(self._payload)
            row = dict(self._payload)
            row.setdefault("event_id", f"evt-{len(self._inserts)}")
            row.setdefault("created_at", "2026-09-08T12:00:00+00:00")
            return _Result([row])
        rows = list(self._store.get(self._table, []))
        for column, value in self._eq.items():
            rows = [row for row in rows if row.get(column) == value]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result(rows)


class FakeClient:
    def __init__(self, store: dict[str, list[dict]] | None = None) -> None:
        self.store = store or {}
        self.inserts: list[dict] = []

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self.store, self.inserts, name)


def _catalog_store() -> dict[str, list[dict]]:
    return {
        "eos_systems": [
            {
                "system_id": SYS_ID,
                "project_code": "PRJ_001_SLM",
                "system_code": "P1",
                "system_name": "Система вентиляции P1",
                "is_active": True,
            },
            {
                "system_id": OTHER_SYS,
                "project_code": "PRJ_OTHER",
                "system_code": "P2",
                "system_name": "Other",
                "is_active": True,
            },
            {
                "system_id": "inactive-sys",
                "project_code": "PRJ_001_SLM",
                "system_code": "X",
                "system_name": "Off",
                "is_active": False,
            },
        ],
        "pnr_objects": [
            {
                "object_id": OBJ_ID,
                "system_id": SYS_ID,
                "object_code": "ШСАУ-P1",
                "object_name": "Шкаф системы автоматического управления P1",
                "object_kind": "PANEL",
                "is_active": True,
            },
            {
                "object_id": "obj-p2",
                "system_id": OTHER_SYS,
                "object_code": "OTHER",
                "object_name": "Other panel",
                "object_kind": "PANEL",
                "is_active": True,
            },
        ],
        "pnr_work_scopes": [
            {
                "work_scope_id": SCOPE_ID,
                "scope_code": "AUT_ALGORITHMS",
                "scope_name": "Автоматика / алгоритмы",
                "sequence_no": 1,
                "is_active": True,
            }
        ],
        "pnr_operations": [
            {
                "operation_id": OP_ID,
                "work_scope_id": SCOPE_ID,
                "operation_code": "PNR-AUT-003",
                "operation_name": "Проверка алгоритма",
                "sequence_no": 1,
                "is_active": True,
            },
            {
                "operation_id": "op-other-scope",
                "work_scope_id": "other-scope",
                "operation_code": "PNR-XX-001",
                "operation_name": "Other",
                "sequence_no": 1,
                "is_active": True,
            },
        ],
        "pnr_execution_events": [],
    }


def _event_kwargs(**overrides: object) -> dict:
    payload = {
        "system_id": SYS_ID,
        "object_id": OBJ_ID,
        "operation_id": OP_ID,
        "result": "FAIL",
        "occurred_at": AWARE,
        "people_count": 2,
        "duration_hours": 4,
        "reason": "Нет сигнала датчика температуры",
    }
    payload.update(overrides)
    return payload


class PnrServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeClient(_catalog_store())

    def test_missing_secret_fails_closed(self) -> None:
        with patch.dict(
            os.environ,
            {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SECRET_KEY": ""},
            clear=False,
        ):
            with self.assertRaises(PnrConfigError) as ctx:
                get_pnr_client()
        self.assertNotIn("eyJ", str(ctx.exception))
        self.assertNotIn("secret", str(ctx.exception).lower().split("supabase_secret_key")[0])

    def test_active_systems_read(self) -> None:
        rows = list_active_systems(client=self.client)
        codes = {row["system_code"] for row in rows}
        self.assertIn("P1", codes)
        self.assertNotIn("X", codes)
        slm = list_active_systems(project_code="PRJ_001_SLM", client=self.client)
        self.assertEqual(len(slm), 1)
        self.assertEqual(slm[0]["system_name"], "Система вентиляции P1")

    def test_objects_filtered_by_system(self) -> None:
        rows = list_active_objects(system_id=SYS_ID, client=self.client)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["object_code"], "ШСАУ-P1")
        other = list_active_objects(system_id=OTHER_SYS, client=self.client)
        self.assertEqual(len(other), 1)
        self.assertEqual(other[0]["object_code"], "OTHER")

    def test_operations_filtered_by_work_scope(self) -> None:
        scopes = list_active_work_scopes(client=self.client)
        self.assertEqual(scopes[0]["scope_code"], "AUT_ALGORITHMS")
        ops = list_active_operations(work_scope_id=SCOPE_ID, client=self.client)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["operation_code"], "PNR-AUT-003")
        empty = list_active_operations(work_scope_id="missing", client=self.client)
        self.assertEqual(empty, [])

    def test_valid_catalog_operation_insert_payload(self) -> None:
        row = create_execution_event(client=self.client, **_event_kwargs())
        self.assertEqual(len(self.client.inserts), 1)
        payload = self.client.inserts[0]
        self.assertEqual(payload["operation_id"], OP_ID)
        self.assertIsNone(payload["unmapped_operation_name"])
        self.assertEqual(payload["result"], "FAIL")
        self.assertEqual(payload["source"], "STREAMLIT")
        self.assertEqual(row["result"], "FAIL")

    def test_valid_unmapped_operation_insert_payload(self) -> None:
        create_execution_event(
            client=self.client,
            **_event_kwargs(
                operation_id=None,
                unmapped_operation_name="Прозвонка нестандартной цепи",
            ),
        )
        payload = self.client.inserts[0]
        self.assertIsNone(payload["operation_id"])
        self.assertEqual(payload["unmapped_operation_name"], "Прозвонка нестандартной цепи")

    def test_both_operation_paths_rejected(self) -> None:
        with self.assertRaises(PnrValidationError):
            create_execution_event(
                client=self.client,
                **_event_kwargs(unmapped_operation_name="extra"),
            )
        self.assertEqual(self.client.inserts, [])

    def test_neither_operation_path_rejected(self) -> None:
        with self.assertRaises(PnrValidationError):
            create_execution_event(
                client=self.client,
                **_event_kwargs(operation_id=None, unmapped_operation_name="  "),
            )
        self.assertEqual(self.client.inserts, [])

    def test_invalid_result_rejected(self) -> None:
        with self.assertRaises(PnrValidationError):
            create_execution_event(client=self.client, **_event_kwargs(result="DONE"))
        self.assertEqual(self.client.inserts, [])

    def test_people_count_non_positive_rejected(self) -> None:
        with self.assertRaises(PnrValidationError):
            create_execution_event(client=self.client, **_event_kwargs(people_count=0))
        with self.assertRaises(PnrValidationError):
            create_execution_event(client=self.client, **_event_kwargs(people_count=-1))
        self.assertEqual(self.client.inserts, [])

    def test_negative_duration_rejected(self) -> None:
        with self.assertRaises(PnrValidationError):
            create_execution_event(client=self.client, **_event_kwargs(duration_hours=-0.5))
        self.assertEqual(self.client.inserts, [])

    def test_negative_labor_rejected_when_not_computed(self) -> None:
        with self.assertRaises(PnrValidationError):
            create_execution_event(
                client=self.client,
                **_event_kwargs(
                    people_count=None,
                    duration_hours=None,
                    labor_hours=-1,
                ),
            )
        self.assertEqual(self.client.inserts, [])

    def test_people_times_duration_computes_labor_hours(self) -> None:
        create_execution_event(client=self.client, **_event_kwargs())
        self.assertEqual(self.client.inserts[0]["labor_hours"], 8)
        self.assertEqual(self.client.inserts[0]["people_count"], 2)
        self.assertEqual(self.client.inserts[0]["duration_hours"], 4)

    def test_conflicting_caller_labor_hours_not_trusted(self) -> None:
        create_execution_event(client=self.client, **_event_kwargs(labor_hours=99))
        self.assertEqual(self.client.inserts[0]["labor_hours"], 8)

    def test_system_object_mismatch_rejected(self) -> None:
        with self.assertRaises(PnrValidationError):
            create_execution_event(
                client=self.client,
                **_event_kwargs(system_id=OTHER_SYS),
            )
        self.assertEqual(self.client.inserts, [])

    def test_timezone_naive_occurred_at_rejected(self) -> None:
        naive = datetime(2026, 9, 8, 12, 0)
        with self.assertRaises(PnrValidationError):
            create_execution_event(client=self.client, **_event_kwargs(occurred_at=naive))
        with self.assertRaises(PnrValidationError):
            create_execution_event(
                client=self.client,
                **_event_kwargs(occurred_at="2026-09-08T12:00:00"),
            )
        create_execution_event(
            client=self.client,
            **_event_kwargs(occurred_at=datetime(2026, 9, 8, 15, 0, tzinfo=ZoneInfo("Europe/Moscow"))),
        )
        self.assertEqual(len(self.client.inserts), 1)

    def test_fail_then_pass_two_inserts(self) -> None:
        create_execution_event(client=self.client, **_event_kwargs(result="FAIL"))
        create_execution_event(client=self.client, **_event_kwargs(result="PASS", reason=None))
        self.assertEqual(len(self.client.inserts), 2)
        self.assertEqual(self.client.inserts[0]["result"], "FAIL")
        self.assertEqual(self.client.inserts[1]["result"], "PASS")
        self.assertNotEqual(self.client.inserts[0], self.client.inserts[1])

    def test_no_update_delete_upsert_event_methods(self) -> None:
        import services.pnr_service as mod

        names = {name.lower() for name in dir(mod) if not name.startswith("_")}
        for forbidden in (
            "update_event",
            "delete_event",
            "upsert_event",
            "update_execution_event",
            "delete_execution_event",
            "upsert_execution_event",
        ):
            self.assertNotIn(forbidden, names)
        source = inspect.getsource(create_execution_event)
        self.assertNotIn(".update(", source)
        self.assertNotIn(".upsert(", source)
        self.assertNotIn(".delete(", source)
        self.assertIn(".insert(", source)

    def test_recent_events_read_shape(self) -> None:
        self.client.store["pnr_execution_events"] = [
            {
                "event_id": "e1",
                "system_id": SYS_ID,
                "object_id": OBJ_ID,
                "operation_id": OP_ID,
                "unmapped_operation_name": None,
                "result": "FAIL",
                "occurred_at": "2026-09-08T12:00:00+00:00",
                "people_count": 2,
                "duration_hours": 4,
                "labor_hours": 8,
                "reason": "sensor",
                "comment": None,
                "source": "STREAMLIT",
                "created_at": "2026-09-08T12:01:00+00:00",
            }
        ]
        rows = list_recent_execution_events(client=self.client, limit=50)
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0].keys()), {
            "event_id",
            "system_id",
            "object_id",
            "operation_id",
            "unmapped_operation_name",
            "result",
            "occurred_at",
            "people_count",
            "duration_hours",
            "labor_hours",
            "reason",
            "comment",
            "source",
            "created_at",
        })


if __name__ == "__main__":
    unittest.main()
