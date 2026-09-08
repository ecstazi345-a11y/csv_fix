"""
PNR MVP-0.4 page tests. No live Supabase writes.

Run:
  python -m unittest tests.test_page60_pnr_fact_form -v
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import unittest
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

PAGE_PATH = (
    Path(__file__).resolve().parents[1] / "pages" / "60_ПНР_Фиксация_факта.py"
)

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


def _install_streamlit_stub() -> ModuleType:
    st = ModuleType("streamlit")
    st.session_state = _SessionState()
    st.set_page_config = lambda **kwargs: None
    st.title = lambda *a, **k: None
    st.caption = lambda *a, **k: None
    st.markdown = lambda *a, **k: None
    st.info = lambda *a, **k: None
    st.warning = lambda *a, **k: None
    st.error = lambda *a, **k: None
    st.success = lambda *a, **k: None
    st.button = lambda *a, **k: False
    st.radio = lambda label, options, **k: options[k.get("index", 0)]
    st.text_area = lambda *a, **k: ""
    st.text_input = lambda *a, **k: k.get("value") or ""
    st.selectbox = lambda label, options, **k: options[0] if options else None
    st.date_input = lambda *a, **k: date(2026, 9, 8)
    st.time_input = lambda *a, **k: time(12, 0)
    st.number_input = lambda *a, **k: k.get("value", 1)
    st.expander = MagicMock()
    st.stop = lambda: (_ for _ in ()).throw(_Stop())
    sys.modules["streamlit"] = st
    return st


def _load_page() -> ModuleType:
    spec = importlib.util.spec_from_file_location("page60_pnr_fact", PAGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["page60_pnr_fact"] = module
    spec.loader.exec_module(module)
    return module


class Page60SourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = PAGE_PATH.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def test_imports_pnr_service_not_supabase(self) -> None:
        self.assertIn("from services.pnr_service import", self.source)
        self.assertIn("create_execution_event", self.source)
        self.assertNotIn("create_client", self.source)
        self.assertNotIn("supabase_client", self.source)
        self.assertNotIn("SUPABASE_SECRET_KEY", self.source)
        self.assertNotIn("SUPABASE_KEY", self.source)

    def test_no_update_delete_upsert(self) -> None:
        self.assertNotIn(".update(", self.source)
        self.assertNotIn(".upsert(", self.source)
        self.assertNotIn(".delete(", self.source)
        self.assertNotIn("update_execution_event", self.source)
        self.assertNotIn("delete_execution_event", self.source)

    def test_submit_is_only_write_path(self) -> None:
        self.assertEqual(self.source.count("create_execution_event("), 1)
        self.assertIn("СОХРАНИТЬ ФАКТ", self.source)
        self.assertNotIn("list_recent_execution_events", self.source)

    def test_russian_result_mapping_in_source(self) -> None:
        self.assertIn('"Выполнено": "PASS"', self.source)
        self.assertIn('"Не выполнено": "FAIL"', self.source)
        self.assertIn('"Выполнено частично": "PARTIAL"', self.source)
        self.assertIn('"Заблокировано": "BLOCKED"', self.source)


class Page60HelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self._st = _install_streamlit_stub()
        patches = [
            patch("services.pnr_service.list_active_systems", return_value=[SYS]),
            patch("services.pnr_service.list_active_objects", return_value=[OBJ]),
            patch("services.pnr_service.list_active_work_scopes", return_value=[SCOPE]),
            patch("services.pnr_service.list_active_operations", return_value=[OP]),
            patch("services.pnr_service.create_execution_event"),
        ]
        self._started = [p.start() for p in patches]
        self.addCleanup(lambda: [p.stop() for p in patches])
        try:
            self.page = _load_page()
        except _Stop:
            self.fail("page stopped during load with catalog fixtures")

    def test_result_labels_map_correctly(self) -> None:
        mapping = self.page.RESULT_LABEL_TO_CODE
        self.assertEqual(mapping["Выполнено"], "PASS")
        self.assertEqual(mapping["Не выполнено"], "FAIL")
        self.assertEqual(mapping["Выполнено частично"], "PARTIAL")
        self.assertEqual(mapping["Заблокировано"], "BLOCKED")

    def test_labor_preview_calculation(self) -> None:
        self.assertEqual(self.page.compute_labor_preview(2, 4), Decimal("8"))
        self.assertEqual(self.page.compute_labor_preview(2, 1.5), Decimal("3.0"))

    def test_catalog_mode_reaches_operation_id(self) -> None:
        occurred = datetime(2026, 9, 8, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))
        kwargs = self.page.build_create_kwargs(
            system_id="sys-p1",
            object_id="obj-1",
            operation_mode=self.page.MODE_CATALOG,
            operation_id="op-003",
            unmapped_operation_name="ignored",
            result_code="FAIL",
            occurred_at=occurred,
            people_count=2,
            duration_hours=Decimal("4"),
            reason="Нет сигнала",
            comment=None,
        )
        self.assertEqual(kwargs["operation_id"], "op-003")
        self.assertIsNone(kwargs["unmapped_operation_name"])
        self.assertEqual(kwargs["source"], "STREAMLIT")
        self.assertEqual(kwargs["labor_hours"], Decimal("8"))
        self.assertTrue(kwargs["occurred_at"].tzinfo is not None)

    def test_unmapped_mode_reaches_unmapped_name(self) -> None:
        occurred = datetime(2026, 9, 8, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))
        kwargs = self.page.build_create_kwargs(
            system_id="sys-p1",
            object_id="obj-1",
            operation_mode=self.page.MODE_UNMAPPED,
            operation_id="op-003",
            unmapped_operation_name="  Прозвонка нестандартной цепи  ",
            result_code="BLOCKED",
            occurred_at=occurred,
            people_count=2,
            duration_hours=Decimal("4"),
            reason="Нет сигнала",
            comment=None,
        )
        self.assertIsNone(kwargs["operation_id"])
        self.assertEqual(kwargs["unmapped_operation_name"], "Прозвонка нестандартной цепи")

    def test_create_execution_event_not_called_without_submit(self) -> None:
        self._started[-1].assert_not_called()


if __name__ == "__main__":
    unittest.main()
