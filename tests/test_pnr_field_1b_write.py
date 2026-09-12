"""
FIELD-1B structured write tests. No live Supabase.

Run:
  python -m unittest tests.test_pnr_field_1b_write -v
"""

from __future__ import annotations

import inspect
import unittest
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from services.pnr_service import (
    EVENT_FIELDS,
    PnrServiceError,
    PnrValidationError,
    RPC_CREATE_STRUCTURED_EVENT,
    STRUCTURED_EVENT_FIELDS,
    create_execution_event,
    create_structured_execution_event,
)


SYS_ID = "11111111-1111-4111-8111-111111111111"
OTHER_SYS = "22222222-2222-4222-8222-222222222222"
OBJ_ID = "33333333-3333-4333-8333-333333333333"
OTHER_OBJ = "66666666-6666-4666-8666-666666666666"
OP_ID = "55555555-5555-4555-8555-555555555555"
OTHER_OP = "77777777-7777-4777-8777-777777777777"
SCOPE_ID = "44444444-4444-4444-8444-444444444444"
OTHER_SCOPE = "99999999-9999-4999-8999-999999999999"
PRIOR_ID = "88888888-8888-4888-8888-888888888888"
AWARE = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
FIXED_EVENT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


class _Result:
    def __init__(self, data: object) -> None:
        self.data = data


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
            row.setdefault("created_at", "2026-09-11T12:00:00+00:00")
            return _Result([row])
        rows = list(self._store.get(self._table, []))
        for column, value in self._eq.items():
            rows = [row for row in rows if row.get(column) == value]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result(rows)


class FakeRpc:
    def __init__(self, owner: FakeClient, name: str, params: dict) -> None:
        self._owner = owner
        self._name = name
        self._params = params

    def execute(self) -> _Result:
        if self._owner.rpc_error is not None:
            raise self._owner.rpc_error
        self._owner.rpc_calls.append({"name": self._name, "params": self._params})
        payload = self._params.get("p_payload") or {}
        row = {
            "event_id": payload.get("event_id"),
            "system_id": payload.get("system_id"),
            "object_id": payload.get("object_id"),
            "work_scope_id": payload.get("work_scope_id"),
            "operation_id": payload.get("operation_id"),
            "unmapped_operation_name": payload.get("unmapped_operation_name"),
            "result": {
                ("COMPLETED", "CONFORMS"): "PASS",
                ("COMPLETED", "NOT_EVALUATED"): "PASS",
                ("COMPLETED", "DOES_NOT_CONFORM"): "FAIL",
                ("NOT_COMPLETED", "NOT_EVALUATED"): "FAIL",
                ("PARTIAL", "NOT_EVALUATED"): "PARTIAL",
                ("PARTIAL", "DOES_NOT_CONFORM"): "PARTIAL",
                ("BLOCKED", "NOT_EVALUATED"): "BLOCKED",
            }.get(
                (
                    payload.get("execution_status"),
                    payload.get("evaluation_status"),
                )
            ),
            "occurred_at": payload.get("occurred_at"),
            "people_count": payload.get("people_count"),
            "duration_hours": payload.get("duration_hours"),
            "labor_hours": payload.get("labor_hours"),
            "reason": payload.get("reason"),
            "comment": payload.get("comment"),
            "source": payload.get("source"),
            "created_at": "2026-09-11T12:00:00+00:00",
            "functional_position_id": payload.get("functional_position_id"),
            "execution_status": payload.get("execution_status"),
            "evaluation_status": payload.get("evaluation_status"),
            "observation_text": payload.get("observation_text"),
            "retry_of_event_id": payload.get("retry_of_event_id"),
        }
        return _Result(row)


class FakeClient:
    def __init__(self, store: dict[str, list[dict]] | None = None) -> None:
        self.store = store or {}
        self.inserts: list[dict] = []
        self.rpc_calls: list[dict] = []
        self.rpc_error: Exception | None = None

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self.store, self.inserts, name)

    def rpc(self, name: str, params: dict) -> FakeRpc:
        return FakeRpc(self, name, params)


def _catalog_store() -> dict[str, list[dict]]:
    return {
        "pnr_objects": [
            {
                "object_id": OBJ_ID,
                "system_id": SYS_ID,
                "object_code": "ШСАУ-P1",
                "object_name": "Шкаф P1",
                "object_kind": "PANEL",
                "is_active": True,
            },
            {
                "object_id": OTHER_OBJ,
                "system_id": OTHER_SYS,
                "object_code": "OTHER",
                "object_name": "Other",
                "object_kind": "PANEL",
                "is_active": True,
            },
        ],
        "pnr_execution_events": [
            {
                "event_id": PRIOR_ID,
                "system_id": SYS_ID,
                "object_id": OBJ_ID,
                "operation_id": OP_ID,
                "unmapped_operation_name": None,
                "result": "FAIL",
                "execution_status": None,
                "evaluation_status": None,
            }
        ],
    }


def _measurement(**overrides: object) -> dict:
    row = {
        "parameter_name": "Температура",
        "value": 21.5,
        "unit": "°C",
        "recorded_at": AWARE,
    }
    row.update(overrides)
    return row


def _blocked(**overrides: object) -> dict:
    row = {
        "constraint_category": "EQUIPMENT",
        "constraint_description": "Нет питания шкафа",
        "other_work_available": False,
    }
    row.update(overrides)
    return row


def _partial(**overrides: object) -> dict:
    row = {
        "completed_text": "Проверена цепь питания",
        "remaining_text": "Осталась проверка алгоритма",
    }
    row.update(overrides)
    return row


def _kwargs(**overrides: object) -> dict:
    payload = {
        "system_id": SYS_ID,
        "object_id": OBJ_ID,
        "work_scope_id": SCOPE_ID,
        "execution_status": "COMPLETED",
        "evaluation_status": "CONFORMS",
        "occurred_at": AWARE,
        "operation_id": OP_ID,
        "people_count": 2,
        "duration_hours": 4,
    }
    payload.update(overrides)
    return payload


class PnrField1bWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeClient(_catalog_store())

    def _create(self, **overrides: object) -> dict:
        return create_structured_execution_event(client=self.client, **_kwargs(**overrides))

    def _payload(self) -> dict:
        self.assertEqual(len(self.client.rpc_calls), 1)
        call = self.client.rpc_calls[0]
        self.assertEqual(call["name"], RPC_CREATE_STRUCTURED_EVENT)
        return call["params"]["p_payload"]

    def test_completed_conforms_projects_pass(self) -> None:
        row = self._create()
        self.assertEqual(row["result"], "PASS")
        self.assertNotIn("result", self._payload())
        self.assertEqual(self._payload()["execution_status"], "COMPLETED")
        self.assertEqual(self._payload()["evaluation_status"], "CONFORMS")
        self.assertEqual(len(self.client.rpc_calls), 1)
        self.assertEqual(self.client.inserts, [])

    def test_completed_not_evaluated_projects_pass(self) -> None:
        row = self._create(evaluation_status="NOT_EVALUATED")
        self.assertEqual(row["result"], "PASS")
        self.assertEqual(self._payload()["evaluation_status"], "NOT_EVALUATED")

    def test_completed_does_not_conform_projects_fail(self) -> None:
        row = self._create(evaluation_status="DOES_NOT_CONFORM")
        self.assertEqual(row["result"], "FAIL")

    def test_not_completed_not_evaluated_projects_fail(self) -> None:
        row = self._create(
            execution_status="NOT_COMPLETED",
            evaluation_status="NOT_EVALUATED",
        )
        self.assertEqual(row["result"], "FAIL")

    def test_partial_not_evaluated_projects_partial(self) -> None:
        row = self._create(
            execution_status="PARTIAL",
            evaluation_status="NOT_EVALUATED",
            partial_detail=_partial(),
        )
        self.assertEqual(row["result"], "PARTIAL")

    def test_partial_does_not_conform_projects_partial(self) -> None:
        row = self._create(
            execution_status="PARTIAL",
            evaluation_status="DOES_NOT_CONFORM",
            partial_detail=_partial(),
        )
        self.assertEqual(row["result"], "PARTIAL")

    def test_blocked_not_evaluated_projects_blocked(self) -> None:
        row = self._create(
            execution_status="BLOCKED",
            evaluation_status="NOT_EVALUATED",
            blocked_detail=_blocked(),
        )
        self.assertEqual(row["result"], "BLOCKED")

    def test_invalid_status_pair_no_rpc(self) -> None:
        with self.assertRaises(PnrValidationError):
            self._create(execution_status="BLOCKED", evaluation_status="CONFORMS")
        self.assertEqual(self.client.rpc_calls, [])
        self.assertEqual(self.client.inserts, [])

    def test_blocked_with_detail_one_rpc(self) -> None:
        self._create(
            execution_status="BLOCKED",
            evaluation_status="NOT_EVALUATED",
            blocked_detail=_blocked(),
        )
        payload = self._payload()
        self.assertEqual(payload["blocked_detail"]["constraint_category"], "EQUIPMENT")
        self.assertIsNone(payload["partial_detail"])
        self.assertEqual(len(self.client.rpc_calls), 1)

    def test_blocked_without_detail_no_rpc(self) -> None:
        with self.assertRaises(PnrValidationError):
            self._create(
                execution_status="BLOCKED",
                evaluation_status="NOT_EVALUATED",
            )
        self.assertEqual(self.client.rpc_calls, [])

    def test_non_blocked_with_blocked_detail_no_rpc(self) -> None:
        with self.assertRaises(PnrValidationError):
            self._create(blocked_detail=_blocked())
        self.assertEqual(self.client.rpc_calls, [])

    def test_partial_with_detail_one_rpc(self) -> None:
        self._create(
            execution_status="PARTIAL",
            evaluation_status="NOT_EVALUATED",
            partial_detail=_partial(),
        )
        payload = self._payload()
        self.assertEqual(payload["partial_detail"]["completed_text"], "Проверена цепь питания")
        self.assertIsNone(payload["blocked_detail"])

    def test_partial_without_detail_no_rpc(self) -> None:
        with self.assertRaises(PnrValidationError):
            self._create(
                execution_status="PARTIAL",
                evaluation_status="NOT_EVALUATED",
            )
        self.assertEqual(self.client.rpc_calls, [])

    def test_non_partial_with_partial_detail_no_rpc(self) -> None:
        with self.assertRaises(PnrValidationError):
            self._create(partial_detail=_partial())
        self.assertEqual(self.client.rpc_calls, [])

    def test_zero_measurements(self) -> None:
        self._create()
        self.assertEqual(self._payload()["measurements"], [])

    def test_one_measurement(self) -> None:
        self._create(measurements=[_measurement()])
        self.assertEqual(len(self._payload()["measurements"]), 1)
        self.assertEqual(self._payload()["measurements"][0]["parameter_name"], "Температура")

    def test_multiple_measurements(self) -> None:
        self._create(
            measurements=[
                _measurement(),
                _measurement(parameter_name="Давление", value=1.2, unit="бар"),
            ]
        )
        self.assertEqual(len(self._payload()["measurements"]), 2)

    def test_invalid_measurement_no_rpc(self) -> None:
        with self.assertRaises(PnrValidationError):
            self._create(measurements=[_measurement(parameter_name="  ")])
        with self.assertRaises(PnrValidationError):
            self._create(measurements=[_measurement(recorded_at=datetime(2026, 9, 11, 12, 0))])
        with self.assertRaises(PnrValidationError):
            self._create(measurements=[_measurement(value=True)])
        self.assertEqual(self.client.rpc_calls, [])

    def test_object_system_mismatch_no_rpc(self) -> None:
        with self.assertRaises(PnrValidationError):
            self._create(system_id=OTHER_SYS)
        self.assertEqual(self.client.rpc_calls, [])

    def test_operation_xor(self) -> None:
        with self.assertRaises(PnrValidationError):
            self._create(unmapped_operation_name="extra")
        with self.assertRaises(PnrValidationError):
            self._create(operation_id=None, unmapped_operation_name="  ")
        self.assertEqual(self.client.rpc_calls, [])
        self._create(operation_id=None, unmapped_operation_name="Прозвонка")
        self.assertIsNone(self._payload()["operation_id"])
        self.assertEqual(self._payload()["unmapped_operation_name"], "Прозвонка")

    def test_labor_recomputed(self) -> None:
        self._create(labor_hours=99)
        self.assertEqual(self._payload()["labor_hours"], 8)
        self.assertEqual(self._payload()["people_count"], 2)
        self.assertEqual(self._payload()["duration_hours"], 4)

    def test_invalid_people_duration_labor_no_rpc(self) -> None:
        with self.assertRaises(PnrValidationError):
            self._create(people_count=0)
        with self.assertRaises(PnrValidationError):
            self._create(people_count=True)
        with self.assertRaises(PnrValidationError):
            self._create(duration_hours=-0.5)
        with self.assertRaises(PnrValidationError):
            self._create(people_count=None, duration_hours=None, labor_hours=-1)
        self.assertEqual(self.client.rpc_calls, [])

    def test_retry_self_reference_no_rpc(self) -> None:
        with patch(
            "services.pnr_service.uuid.uuid4",
            return_value=uuid.UUID(FIXED_EVENT_ID),
        ):
            with self.assertRaises(PnrValidationError):
                self._create(retry_of_event_id=FIXED_EVENT_ID)
        self.assertEqual(self.client.rpc_calls, [])

    def test_retry_wrong_system_no_rpc(self) -> None:
        self.client.store["pnr_execution_events"][0]["system_id"] = OTHER_SYS
        with self.assertRaises(PnrValidationError):
            self._create(retry_of_event_id=PRIOR_ID)
        self.assertEqual(self.client.rpc_calls, [])

    def test_retry_wrong_object_no_rpc(self) -> None:
        self.client.store["pnr_execution_events"][0]["object_id"] = OTHER_OBJ
        with self.assertRaises(PnrValidationError):
            self._create(retry_of_event_id=PRIOR_ID)
        self.assertEqual(self.client.rpc_calls, [])

    def test_retry_different_operation_no_rpc(self) -> None:
        with self.assertRaises(PnrValidationError):
            self._create(retry_of_event_id=PRIOR_ID, operation_id=OTHER_OP)
        self.assertEqual(self.client.rpc_calls, [])

    def test_valid_retry_calls_rpc(self) -> None:
        row = self._create(retry_of_event_id=PRIOR_ID)
        self.assertEqual(self._payload()["retry_of_event_id"], PRIOR_ID)
        self.assertEqual(row["retry_of_event_id"], PRIOR_ID)
        self.assertEqual(len(self.client.rpc_calls), 1)

    def test_rpc_failure_is_service_error(self) -> None:
        self.client.rpc_error = RuntimeError("transport")
        with self.assertRaises(PnrServiceError) as ctx:
            self._create()
        self.assertNotIn("transport", str(ctx.exception))
        self.assertNotIn("eyJ", str(ctx.exception))
        self.assertEqual(self.client.inserts, [])

    def test_no_local_partial_success(self) -> None:
        self._create(
            execution_status="BLOCKED",
            evaluation_status="NOT_EVALUATED",
            blocked_detail=_blocked(),
            measurements=[_measurement()],
        )
        self.assertEqual(self.client.inserts, [])
        self.assertEqual(len(self.client.rpc_calls), 1)
        source = inspect.getsource(create_structured_execution_event)
        self.assertIn(".rpc(", source)
        self.assertNotIn(".insert(", source)
        self.assertNotIn(".update(", source)
        self.assertNotIn(".delete(", source)
        self.assertNotIn(".upsert(", source)

    def test_legacy_create_execution_event_unchanged(self) -> None:
        create_execution_event(
            client=self.client,
            system_id=SYS_ID,
            object_id=OBJ_ID,
            result="FAIL",
            occurred_at=AWARE,
            operation_id=OP_ID,
            people_count=2,
            duration_hours=4,
        )
        self.assertEqual(self.client.rpc_calls, [])
        self.assertEqual(len(self.client.inserts), 1)
        self.assertEqual(self.client.inserts[0]["result"], "FAIL")
        self.assertNotIn("execution_status", self.client.inserts[0])
        self.assertNotIn("work_scope_id", self.client.inserts[0])
        source = inspect.getsource(create_execution_event)
        self.assertIn(".insert(", source)
        self.assertNotIn(".rpc(", source)

    def test_work_scope_id_required(self) -> None:
        with self.assertRaises(PnrValidationError):
            self._create(work_scope_id=None)
        with self.assertRaises(PnrValidationError):
            self._create(work_scope_id="  ")
        missing = _kwargs()
        del missing["work_scope_id"]
        with self.assertRaises(TypeError):
            create_structured_execution_event(client=self.client, **missing)
        self.assertEqual(self.client.rpc_calls, [])

    def test_payload_includes_work_scope_id(self) -> None:
        row = self._create()
        self.assertEqual(self._payload()["work_scope_id"], SCOPE_ID)
        self.assertEqual(row["work_scope_id"], SCOPE_ID)
        self.assertIn("work_scope_id", STRUCTURED_EVENT_FIELDS)
        self.assertNotIn("work_scope_id", EVENT_FIELDS)

    def test_unmapped_operation_still_sends_work_scope_id(self) -> None:
        self._create(operation_id=None, unmapped_operation_name="Прозвонка")
        payload = self._payload()
        self.assertEqual(payload["work_scope_id"], SCOPE_ID)
        self.assertIsNone(payload["operation_id"])
        self.assertEqual(payload["unmapped_operation_name"], "Прозвонка")

    def test_no_python_bridge_query(self) -> None:
        source = inspect.getsource(create_structured_execution_event)
        self.assertNotIn("pnr_work_scope_operations", source)
        self.assertNotIn("work_scope_operations", source)
        self.assertNotIn("TABLE_WORK_SCOPE_OPERATIONS", source)
        self.assertNotIn('table("pnr_work_scope_operations")', source)
        self.assertNotIn("table('pnr_work_scope_operations')", source)

    def test_retry_scope_mismatch_no_rpc(self) -> None:
        self.client.store["pnr_execution_events"][0]["work_scope_id"] = SCOPE_ID
        with self.assertRaises(PnrValidationError):
            self._create(retry_of_event_id=PRIOR_ID, work_scope_id=OTHER_SCOPE)
        self.assertEqual(self.client.rpc_calls, [])

    def test_retry_scope_match_calls_rpc(self) -> None:
        self.client.store["pnr_execution_events"][0]["work_scope_id"] = SCOPE_ID
        self._create(retry_of_event_id=PRIOR_ID, work_scope_id=SCOPE_ID)
        self.assertEqual(self._payload()["work_scope_id"], SCOPE_ID)
        self.assertEqual(len(self.client.rpc_calls), 1)

    def test_retry_historical_null_scope_allowed(self) -> None:
        self.assertIsNone(
            self.client.store["pnr_execution_events"][0].get("work_scope_id")
        )
        self._create(retry_of_event_id=PRIOR_ID)
        self.assertEqual(self._payload()["work_scope_id"], SCOPE_ID)
        self.assertEqual(self._payload()["retry_of_event_id"], PRIOR_ID)


if __name__ == "__main__":
    unittest.main()
