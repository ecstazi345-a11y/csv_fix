"""
PNR MVP-0.5 journal page tests. No live Supabase writes.

Run:
  python -m unittest tests.test_page61_pnr_journal -v
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

PAGE_PATH = Path(__file__).resolve().parents[1] / "pages" / "61_ПНР_Журнал.py"

SYS = {
    "system_id": "sys-p1",
    "project_code": "PRJ_001_SLM",
    "system_code": "P1",
    "system_name": "Система вентиляции P1",
}
OBJ = {
    "object_id": "obj-1",
    "system_id": "sys-p1",
    "object_code": "ШСАУ-P1",
    "object_name": "Шкаф системы автоматического управления P1",
    "object_kind": "PANEL",
}
SCOPE = {
    "work_scope_id": "scope-1",
    "scope_code": "AUT_ALGORITHMS",
    "scope_name": "Автоматика / алгоритмы",
    "sequence_no": 1,
}
OP = {
    "operation_id": "op-003",
    "work_scope_id": "scope-1",
    "operation_code": "PNR-AUT-003",
    "operation_name": "Проверка алгоритма",
    "sequence_no": 1,
}

FAIL_EVENT = {
    "event_id": "evt-fail",
    "system_id": "sys-p1",
    "object_id": "obj-1",
    "operation_id": "op-003",
    "unmapped_operation_name": None,
    "result": "FAIL",
    "occurred_at": "2026-09-08T10:00:00+00:00",
    "people_count": 2,
    "duration_hours": 1.5,
    "labor_hours": 3,
    "reason": "Тест MVP — отсутствует сигнал датчика температуры",
    "comment": None,
    "source": "STREAMLIT",
    "created_at": "2026-09-08T10:01:00+00:00",
}
PASS_EVENT = {
    "event_id": "evt-pass",
    "system_id": "sys-p1",
    "object_id": "obj-1",
    "operation_id": "op-003",
    "unmapped_operation_name": None,
    "result": "PASS",
    "occurred_at": "2026-09-08T12:00:00+00:00",
    "people_count": 2,
    "duration_hours": 0.5,
    "labor_hours": 1,
    "reason": None,
    "comment": "Повторная проверка после устранения причины — алгоритм выполнен",
    "source": "STREAMLIT",
    "created_at": "2026-09-08T12:01:00+00:00",
}
UNMAPPED_EVENT = {
    "event_id": "evt-unmapped",
    "system_id": "sys-p1",
    "object_id": "obj-1",
    "operation_id": None,
    "unmapped_operation_name": "Прозвонка нестандартной цепи",
    "result": "BLOCKED",
    "occurred_at": "2026-09-08T09:00:00+00:00",
    "people_count": 1,
    "duration_hours": 1,
    "labor_hours": 1,
    "reason": "Нет схемы",
    "comment": None,
    "source": "STREAMLIT",
    "created_at": "2026-09-08T09:01:00+00:00",
}


class _SessionState(dict):
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


class _Stop(Exception):
    pass


class _Column:
    def __init__(self, st_mod: ModuleType) -> None:
        self._st = st_mod

    def __enter__(self) -> _Column:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._st, name)


def _install_streamlit_stub() -> ModuleType:
    st = ModuleType("streamlit")
    st.session_state = _SessionState()
    st.set_page_config = lambda **kwargs: None
    st.title = lambda *a, **k: None
    st.caption = lambda *a, **k: None
    st.subheader = lambda *a, **k: None
    st.markdown = lambda *a, **k: None
    st.divider = lambda *a, **k: None
    st.info = lambda *a, **k: None
    st.warning = lambda *a, **k: None
    st.error = lambda *a, **k: None
    st.success = lambda *a, **k: None
    st.button = lambda *a, **k: False
    st.radio = lambda label, options, **k: options[k.get("index", 0)]
    st.text_area = lambda *a, **k: ""
    st.text_input = lambda *a, **k: k.get("value") or ""
    st.selectbox = lambda label, options, **k: options[0] if options else None
    st.number_input = lambda *a, **k: k.get("value", 1)
    st.dataframe = lambda *a, **k: None
    st.metric = lambda *a, **k: None
    st.expander = MagicMock()
    st.columns = lambda spec: [_Column(st) for _ in range(spec if isinstance(spec, int) else len(spec))]
    st.stop = lambda: (_ for _ in ()).throw(_Stop())
    sys.modules["streamlit"] = st
    return st


def _load_page() -> ModuleType:
    sys.modules.pop("page61_pnr_journal", None)
    spec = importlib.util.spec_from_file_location("page61_pnr_journal", PAGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["page61_pnr_journal"] = module
    spec.loader.exec_module(module)
    return module


class Page61SourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = PAGE_PATH.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def test_imports_pnr_service_not_supabase(self) -> None:
        self.assertIn("from services.pnr_service import", self.source)
        self.assertIn("list_recent_execution_events", self.source)
        self.assertNotIn("create_client", self.source)
        self.assertNotIn("supabase_client", self.source)
        self.assertNotIn("SUPABASE_SECRET_KEY", self.source)
        self.assertNotIn("SUPABASE_KEY", self.source)
        self.assertNotIn("create_execution_event", self.source)

    def test_no_write_methods(self) -> None:
        self.assertNotIn("create_execution_event", self.source)
        self.assertNotIn(".update(", self.source)
        self.assertNotIn(".upsert(", self.source)
        self.assertNotIn(".delete(", self.source)
        self.assertNotIn("update_execution_event", self.source)
        self.assertNotIn("delete_execution_event", self.source)
        self.assertNotIn("СОХРАНИТЬ ФАКТ", self.source)
        self.assertIn("sys.path.insert", self.source)

    def test_russian_result_mapping_in_source(self) -> None:
        self.assertIn('"PASS": "Выполнено"', self.source)
        self.assertIn('"FAIL": "Не выполнено"', self.source)
        self.assertIn('"PARTIAL": "Выполнено частично"', self.source)
        self.assertIn('"BLOCKED": "Заблокировано"', self.source)


class Page61HelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self._st = _install_streamlit_stub()
        patches = [
            patch("services.pnr_service.list_active_systems", return_value=[SYS]),
            patch("services.pnr_service.list_active_objects", return_value=[OBJ]),
            patch("services.pnr_service.list_active_work_scopes", return_value=[SCOPE]),
            patch("services.pnr_service.list_active_operations", return_value=[OP]),
            patch(
                "services.pnr_service.list_recent_execution_events",
                return_value=[FAIL_EVENT, PASS_EVENT],
            ),
        ]
        self._started = [p.start() for p in patches]
        self.addCleanup(lambda: [p.stop() for p in patches])
        try:
            self.page = _load_page()
        except _Stop:
            self.fail("page stopped during load with catalog fixtures")

    def test_result_labels_map_correctly(self) -> None:
        mapping = self.page.RESULT_CODE_TO_LABEL
        self.assertEqual(mapping["PASS"], "Выполнено")
        self.assertEqual(mapping["FAIL"], "Не выполнено")
        self.assertEqual(mapping["PARTIAL"], "Выполнено частично")
        self.assertEqual(mapping["BLOCKED"], "Заблокировано")

    def test_current_state_derived_from_latest_event(self) -> None:
        summary = self.page.summarize_events([FAIL_EVENT, PASS_EVENT])
        self.assertEqual(summary["current_result"], "PASS")
        self.assertEqual(summary["current_label"], "Выполнено")
        self.assertEqual(summary["latest_event"]["event_id"], "evt-pass")

    def test_attempt_count_correct(self) -> None:
        summary = self.page.summarize_events([FAIL_EVENT, PASS_EVENT])
        self.assertEqual(summary["attempt_count"], 2)

    def test_total_labor_correct(self) -> None:
        summary = self.page.summarize_events([FAIL_EVENT, PASS_EVENT])
        self.assertEqual(summary["total_labor"], Decimal("4"))

    def test_fail_then_pass_history_preserves_both_events(self) -> None:
        ordered = self.page.sort_events_newest_first([FAIL_EVENT, PASS_EVENT])
        self.assertEqual([row["event_id"] for row in ordered], ["evt-pass", "evt-fail"])
        self.assertEqual(ordered[0]["result"], "PASS")
        self.assertEqual(ordered[1]["result"], "FAIL")
        rows = self.page.build_history_rows(
            [FAIL_EVENT, PASS_EVENT],
            system_map={"sys-p1": SYS},
            object_map={"obj-1": OBJ},
            operation_map={"op-003": OP},
        )
        results = [row["Результат"] for row in rows]
        self.assertEqual(results, ["Выполнено", "Не выполнено"])
        self.assertEqual(len(rows), 2)

    def test_moscow_timezone_presentation(self) -> None:
        utc_noon = "2026-09-08T12:00:00+00:00"
        self.assertEqual(self.page.format_moscow_datetime(utc_noon), "08.09.2026 15:00")
        aware = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(self.page.format_moscow_datetime(aware), "08.09.2026 15:00")
        moscow = datetime(2026, 9, 8, 15, 0, tzinfo=ZoneInfo("Europe/Moscow"))
        self.assertEqual(self.page.format_moscow_datetime(moscow), "08.09.2026 15:00")
        self.assertNotIn("UTC", self.page.format_moscow_datetime(utc_noon))
        self.assertNotIn("+00:00", self.page.format_moscow_datetime(utc_noon))

    def test_unmapped_operation_fallback(self) -> None:
        label = self.page.resolve_operation_label(UNMAPPED_EVENT, {"op-003": OP})
        self.assertEqual(label, "Прозвонка нестандартной цепи")
        rows = self.page.build_history_rows(
            [UNMAPPED_EVENT],
            system_map={"sys-p1": SYS},
            object_map={"obj-1": OBJ},
            operation_map={"op-003": OP},
        )
        self.assertEqual(rows[0]["Операция"], "Прозвонка нестандартной цепи")

    def test_empty_event_state_does_not_crash(self) -> None:
        summary = self.page.summarize_events([])
        self.assertEqual(summary["attempt_count"], 0)
        self.assertEqual(summary["total_labor"], Decimal("0"))
        self.assertEqual(summary["current_label"], "Нет фактов")
        self.assertIsNone(summary["latest_event"])
        rows = self.page.build_history_rows(
            [],
            system_map={"sys-p1": SYS},
            object_map={"obj-1": OBJ},
            operation_map={"op-003": OP},
        )
        self.assertEqual(rows, [])


class Page61EmptyLoadTests(unittest.TestCase):
    def test_empty_events_page_load_does_not_stop(self) -> None:
        _install_streamlit_stub()
        patches = [
            patch("services.pnr_service.list_active_systems", return_value=[SYS]),
            patch("services.pnr_service.list_active_objects", return_value=[OBJ]),
            patch("services.pnr_service.list_active_work_scopes", return_value=[SCOPE]),
            patch("services.pnr_service.list_active_operations", return_value=[OP]),
            patch("services.pnr_service.list_recent_execution_events", return_value=[]),
        ]
        started = [p.start() for p in patches]
        try:
            page = _load_page()
        except _Stop:
            self.fail("empty event journal must not crash or stop")
        finally:
            for p in patches:
                p.stop()
        self.assertEqual(page.summarize_events([])["attempt_count"], 0)
        self.assertTrue(started)


if __name__ == "__main__":
    unittest.main()
