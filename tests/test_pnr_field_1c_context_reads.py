"""
FIELD-1C context read helpers. SELECT-only. No live Supabase writes.

Run:
  python -m unittest tests.test_pnr_field_1c_context_reads -v
"""

from __future__ import annotations

import inspect
import unittest

from services.pnr_service import (
    PnrValidationError,
    get_work_type_by_code,
    list_active_projects,
    list_active_titles,
    list_active_work_types,
    list_context_disciplines,
    list_system_work_contexts,
    resolve_object_functional_position_id,
)

PRJ_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"
OTHER_PRJ = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2"
TTL_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1"
OTHER_TTL = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2"
PNR_ID = "cccccccc-cccc-4ccc-8ccc-ccccccccccc1"
SMR_ID = "cccccccc-cccc-4ccc-8ccc-ccccccccccc2"
VENT_ID = "dddddddd-dddd-4ddd-8ddd-ddddddddddd1"
EOM_ID = "dddddddd-dddd-4ddd-8ddd-ddddddddddd2"
SYS_P1 = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee1"
SYS_OTHER = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee2"
OBJ_MAPPED = "ffffffff-ffff-4fff-8fff-fffffffffff1"
OBJ_UNMAPPED = "ffffffff-ffff-4fff-8fff-fffffffffff2"
FP_ID = "99999999-9999-4999-8999-999999999999"


class _Result:
    def __init__(self, data: list[dict] | None) -> None:
        self.data = data or []


class FakeQuery:
    def __init__(self, store: dict[str, list[dict]], writes: list, table: str) -> None:
        self._store = store
        self._writes = writes
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

    def update(self, payload: dict) -> FakeQuery:
        self._op = "update"
        self._payload = dict(payload)
        return self

    def delete(self) -> FakeQuery:
        self._op = "delete"
        return self

    def execute(self) -> _Result:
        if self._op != "select":
            self._writes.append({"op": self._op, "table": self._table, "payload": self._payload})
            raise AssertionError(f"unexpected write {self._op} on {self._table}")
        rows = list(self._store.get(self._table, []))
        for column, value in self._eq.items():
            rows = [row for row in rows if row.get(column) == value]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result(rows)


class FakeClient:
    def __init__(self, store: dict[str, list[dict]] | None = None) -> None:
        self.store = store or {}
        self.writes: list[dict] = []
        self.rpc_calls: list[dict] = []

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self.store, self.writes, name)

    def rpc(self, name: str, params: dict | None = None):
        self.rpc_calls.append({"name": name, "params": params or {}})
        raise AssertionError(f"unexpected rpc {name}")


def _store() -> dict[str, list[dict]]:
    return {
        "eos_projects": [
            {
                "project_id": PRJ_ID,
                "project_code": "PRJ_001_SLM",
                "project_name": "Салмановское месторождение",
                "is_active": True,
            },
            {
                "project_id": OTHER_PRJ,
                "project_code": "PRJ_OTHER",
                "project_name": "Другой проект",
                "is_active": False,
            },
        ],
        "eos_titles": [
            {
                "title_id": TTL_ID,
                "project_id": PRJ_ID,
                "title_code": "УКПГ2-011",
                "title_name": "УКПГ2-011",
                "is_active": True,
            },
            {
                "title_id": OTHER_TTL,
                "project_id": OTHER_PRJ,
                "title_code": "OTHER",
                "title_name": "Чужой титул",
                "is_active": True,
            },
        ],
        "eos_work_types": [
            {
                "work_type_id": PNR_ID,
                "work_type_code": "PNR",
                "work_type_name": "ПНР",
                "is_active": True,
            },
            {
                "work_type_id": SMR_ID,
                "work_type_code": "SMR",
                "work_type_name": "СМР",
                "is_active": True,
            },
            {
                "work_type_id": "inactive-wt",
                "work_type_code": "OLD",
                "work_type_name": "Архив",
                "is_active": False,
            },
        ],
        "eos_disciplines": [
            {
                "discipline_id": VENT_ID,
                "discipline_code": "VENTILATION",
                "discipline_name": "Вентиляция",
                "is_active": True,
            },
            {
                "discipline_id": EOM_ID,
                "discipline_code": "EOM",
                "discipline_name": "ЭОМ",
                "is_active": True,
            },
        ],
        "eos_system_work_contexts": [
            {
                "system_work_context_id": "ctx-vent-pnr",
                "title_id": TTL_ID,
                "discipline_id": VENT_ID,
                "work_type_id": PNR_ID,
                "system_id": SYS_P1,
                "context_system_code": "П-1",
                "is_active": True,
            },
            {
                "system_work_context_id": "ctx-eom-pnr",
                "title_id": TTL_ID,
                "discipline_id": EOM_ID,
                "work_type_id": PNR_ID,
                "system_id": SYS_OTHER,
                "context_system_code": "ЭОМ-1",
                "is_active": True,
            },
            {
                "system_work_context_id": "ctx-vent-smr",
                "title_id": TTL_ID,
                "discipline_id": VENT_ID,
                "work_type_id": SMR_ID,
                "system_id": SYS_P1,
                "context_system_code": "П-1",
                "is_active": True,
            },
            {
                "system_work_context_id": "ctx-inactive",
                "title_id": TTL_ID,
                "discipline_id": VENT_ID,
                "work_type_id": PNR_ID,
                "system_id": SYS_OTHER,
                "context_system_code": "HIDDEN",
                "is_active": False,
            },
        ],
        "pnr_object_position_map": [
            {
                "object_id": OBJ_MAPPED,
                "position_id": FP_ID,
                "system_id": SYS_P1,
                "mapping_type": "LEGACY_EQUIVALENT",
            }
        ],
    }


class Field1CContextReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeClient(_store())

    def test_helpers_are_select_only(self) -> None:
        names = [
            list_active_projects,
            list_active_titles,
            list_active_work_types,
            get_work_type_by_code,
            list_context_disciplines,
            list_system_work_contexts,
            resolve_object_functional_position_id,
        ]
        for fn in names:
            source = inspect.getsource(fn)
            with self.subTest(fn=fn.__name__):
                self.assertIn(".select(", source)
                self.assertNotIn(".insert(", source)
                self.assertNotIn(".update(", source)
                self.assertNotIn(".delete(", source)
                self.assertNotIn(".upsert(", source)
                self.assertNotIn(".rpc(", source)

    def test_active_projects_and_titles(self) -> None:
        projects = list_active_projects(client=self.client)
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["project_code"], "PRJ_001_SLM")
        titles = list_active_titles(project_id=PRJ_ID, client=self.client)
        self.assertEqual([row["title_code"] for row in titles], ["УКПГ2-011"])
        foreign = list_active_titles(project_id=OTHER_PRJ, client=self.client)
        self.assertEqual([row["title_id"] for row in foreign], [OTHER_TTL])
        self.assertEqual(self.client.writes, [])
        self.assertEqual(self.client.rpc_calls, [])

    def test_pnr_work_type_resolution(self) -> None:
        types_ = list_active_work_types(client=self.client)
        self.assertEqual({row["work_type_code"] for row in types_}, {"PNR", "SMR"})
        pnr = get_work_type_by_code(work_type_code="PNR", client=self.client)
        assert pnr is not None
        self.assertEqual(pnr["work_type_id"], PNR_ID)
        self.assertEqual(pnr["work_type_name"], "ПНР")
        self.assertIsNone(get_work_type_by_code(work_type_code="OLD", client=self.client))
        self.assertEqual(self.client.writes, [])

    def test_disciplines_come_from_work_contexts(self) -> None:
        rows = list_context_disciplines(
            title_id=TTL_ID, work_type_id=PNR_ID, client=self.client
        )
        self.assertEqual(
            {row["discipline_id"] for row in rows}, {VENT_ID, EOM_ID}
        )
        smr_only = list_context_disciplines(
            title_id=TTL_ID, work_type_id=SMR_ID, client=self.client
        )
        self.assertEqual([row["discipline_id"] for row in smr_only], [VENT_ID])
        empty = list_context_disciplines(
            title_id=OTHER_TTL, work_type_id=PNR_ID, client=self.client
        )
        self.assertEqual(empty, [])
        self.assertEqual(self.client.writes, [])

    def test_system_contexts_filtered_by_selected_contour(self) -> None:
        vent = list_system_work_contexts(
            title_id=TTL_ID,
            work_type_id=PNR_ID,
            discipline_id=VENT_ID,
            client=self.client,
        )
        self.assertEqual(len(vent), 1)
        self.assertEqual(vent[0]["system_id"], SYS_P1)
        self.assertEqual(vent[0]["context_system_code"], "П-1")
        eom = list_system_work_contexts(
            title_id=TTL_ID,
            work_type_id=PNR_ID,
            discipline_id=EOM_ID,
            client=self.client,
        )
        self.assertEqual([row["system_id"] for row in eom], [SYS_OTHER])
        self.assertNotIn(SYS_OTHER, [row["system_id"] for row in vent])
        self.assertEqual(self.client.writes, [])
        self.assertEqual(self.client.rpc_calls, [])

    def test_object_functional_position_zero_or_one(self) -> None:
        mapped = resolve_object_functional_position_id(
            object_id=OBJ_MAPPED, client=self.client
        )
        self.assertEqual(mapped, FP_ID)
        missing = resolve_object_functional_position_id(
            object_id=OBJ_UNMAPPED, client=self.client
        )
        self.assertIsNone(missing)
        self.assertEqual(self.client.writes, [])

    def test_ambiguous_mapping_is_not_guessed(self) -> None:
        self.client.store["pnr_object_position_map"] = [
            {
                "object_id": OBJ_MAPPED,
                "position_id": FP_ID,
                "system_id": SYS_P1,
                "mapping_type": "LEGACY_EQUIVALENT",
            },
            {
                "object_id": OBJ_MAPPED,
                "position_id": "other-fp",
                "system_id": SYS_P1,
                "mapping_type": "LEGACY_EQUIVALENT",
            },
        ]
        with self.assertRaises(PnrValidationError):
            resolve_object_functional_position_id(
                object_id=OBJ_MAPPED, client=self.client
            )


if __name__ == "__main__":
    unittest.main()
