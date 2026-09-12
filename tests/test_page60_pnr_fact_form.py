"""
FIELD-1C page 60 tests. No live Supabase writes.

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
from unittest.mock import patch
from zoneinfo import ZoneInfo

PAGE_PATH = (
    Path(__file__).resolve().parents[1] / "pages" / "60_ПНР_Фиксация_факта.py"
)

PROJECT = {
    "project_id": "prj-1",
    "project_code": "PRJ_001_SLM",
    "project_name": "Салмановское месторождение",
}
TITLE = {
    "title_id": "ttl-1",
    "project_id": "prj-1",
    "title_code": "УКПГ2-011",
    "title_name": "УКПГ2-011",
}
WORK_TYPE = {
    "work_type_id": "wt-pnr",
    "work_type_code": "PNR",
    "work_type_name": "ПНР",
}
DISC = {
    "discipline_id": "disc-1",
    "discipline_code": "VENTILATION",
    "discipline_name": "Вентиляция",
}
CTX = {
    "system_work_context_id": "ctx-1",
    "title_id": "ttl-1",
    "discipline_id": "disc-1",
    "work_type_id": "wt-pnr",
    "system_id": "sys-p1",
    "context_system_code": "П-1",
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


class _Column:
    def button(self, *args: Any, **kwargs: Any) -> bool:
        return False


class _Expander:
    def __enter__(self) -> _Expander:
        return self

    def __exit__(self, *args: Any) -> bool:
        return False


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
    st.selectbox = lambda label, options, **k: (
        options[k.get("index", 0)] if options else None
    )
    st.date_input = lambda *a, **k: date(2026, 9, 8)
    st.time_input = lambda *a, **k: time(12, 0)
    st.number_input = lambda *a, **k: k.get("value", 1)
    st.columns = lambda *a, **k: [_Column(), _Column()]
    st.rerun = lambda: None
    st.expander = lambda *a, **k: _Expander()
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


def _imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
    return names


class Page60SourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = PAGE_PATH.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)
        self.imported = _imported_names(self.tree)

    def test_imports_structured_write_not_legacy(self) -> None:
        self.assertIn("create_structured_execution_event", self.imported)
        self.assertNotIn("create_execution_event", self.imported)
        self.assertIn("create_structured_execution_event", self.source)
        self.assertNotIn("create_execution_event", self.source)

    def test_no_direct_client_rpc_or_sql_writes(self) -> None:
        self.assertNotIn("create_client", self.source)
        self.assertNotIn("supabase_client", self.source)
        self.assertNotIn("SUPABASE_SECRET_KEY", self.source)
        self.assertNotIn("SUPABASE_KEY", self.source)
        self.assertNotIn(".rpc(", self.source)
        self.assertNotIn(".update(", self.source)
        self.assertNotIn(".upsert(", self.source)
        self.assertNotIn(".delete(", self.source)
        self.assertNotRegex(self.source, r"(?<!path)\.insert\(")

    def test_system_source_is_work_context_not_physical_list(self) -> None:
        self.assertIn("list_system_work_contexts", self.imported)
        self.assertNotIn("list_active_systems", self.imported)
        self.assertNotIn("list_active_systems", self.source)

    def test_context_cascade_and_explicit_selectors(self) -> None:
        self.assertIn('"Проект"', self.source)
        self.assertIn('"Титул"', self.source)
        self.assertIn('"Дисциплина"', self.source)
        self.assertIn('"Система"', self.source)
        self.assertIn('"Физический объект"', self.source)
        self.assertIn("Вид работ: ПНР", self.source)
        self.assertIn("list_context_disciplines", self.source)
        self.assertNotIn("Вентиляция", self.source)
        self.assertNotIn("list_active_objects(discipline", self.source)

    def test_no_hidden_default_p1_identity(self) -> None:
        self.assertNotIn('index=0, key="pnr_system', self.source)
        self.assertNotIn('"П-1"', self.source)
        self.assertNotIn("'П-1'", self.source)
        self.assertIn("list_system_work_contexts(", self.source)

    def test_result_ux_is_russian_fact_questions(self) -> None:
        self.assertIn('"Работа выполнена?"', self.source)
        self.assertIn('"Выполнена"', self.source)
        self.assertIn('"Выполнена частично"', self.source)
        self.assertIn('"Работа заблокирована"', self.source)
        self.assertIn('"Не выполнена"', self.source)
        self.assertIn('"Полученный результат соответствует требованию?"', self.source)
        self.assertNotIn('"Результат"', self.source)
        self.assertNotIn(": \"PASS\"", self.source)
        self.assertNotIn(": \"FAIL\"", self.source)

    def test_save_control_and_no_history_edit(self) -> None:
        self.assertIn('"Сохранить факт"', self.source)
        self.assertNotIn("list_recent_execution_events", self.source)
        self.assertNotIn("update_execution_event", self.source)
        self.assertNotIn("delete_execution_event", self.source)
        self.assertNotIn("Редактировать", self.source)
        self.assertNotIn("Удалить", self.source)

    def test_no_caller_legacy_result_in_kwargs_builder(self) -> None:
        self.assertNotIn('"result":', self.source)
        self.assertNotIn('"labor_hours":', self.source)

    def test_persists_selected_work_scope_without_m2m_reads(self) -> None:
        self.assertIn("require_selected_work_scope", self.source)
        self.assertIn("Выберите раздел работ.", self.source)
        self.assertIn("work_scope_id=selected_scope_id", self.source)
        self.assertIn('kwargs.get("work_scope_id")', self.source)
        self.assertIn("list_active_operations(work_scope_id=", self.source)
        self.assertNotIn("pnr_work_scope_operations", self.source)


class Page60HelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self._st = _install_streamlit_stub()
        patches = [
            patch("services.pnr_service.list_active_projects", return_value=[PROJECT]),
            patch("services.pnr_service.list_active_titles", return_value=[TITLE]),
            patch("services.pnr_service.get_work_type_by_code", return_value=WORK_TYPE),
            patch("services.pnr_service.list_context_disciplines", return_value=[DISC]),
            patch("services.pnr_service.list_system_work_contexts", return_value=[CTX]),
            patch("services.pnr_service.list_active_objects", return_value=[OBJ]),
            patch(
                "services.pnr_service.resolve_object_functional_position_id",
                return_value="fp-1",
            ),
            patch("services.pnr_service.list_active_work_scopes", return_value=[SCOPE]),
            patch("services.pnr_service.list_active_operations", return_value=[OP]),
            patch("services.pnr_service.create_structured_execution_event"),
        ]
        self._started = [p.start() for p in patches]
        self.addCleanup(lambda: [p.stop() for p in patches])
        try:
            self.page = _load_page()
        except _Stop:
            self.fail("page stopped during load with catalog fixtures")

    def test_all_six_result_mappings(self) -> None:
        cases = [
            ("Выполнена", "Соответствует", "COMPLETED", "CONFORMS"),
            ("Выполнена", "Не соответствует", "COMPLETED", "DOES_NOT_CONFORM"),
            ("Выполнена", "Пока не оценивалось", "COMPLETED", "NOT_EVALUATED"),
            ("Выполнена частично", None, "PARTIAL", "NOT_EVALUATED"),
            ("Работа заблокирована", None, "BLOCKED", "NOT_EVALUATED"),
            ("Не выполнена", None, "NOT_COMPLETED", "NOT_EVALUATED"),
        ]
        for done, evaluation, execution, expected_eval in cases:
            with self.subTest(done=done, evaluation=evaluation):
                got_exec, got_eval = self.page.map_execution_evaluation(done, evaluation)
                self.assertEqual(got_exec, execution)
                self.assertEqual(got_eval, expected_eval)

    def test_not_completed_is_not_blocked(self) -> None:
        execution, evaluation = self.page.map_execution_evaluation("Не выполнена", None)
        self.assertEqual(execution, "NOT_COMPLETED")
        self.assertNotEqual(execution, "BLOCKED")
        self.assertEqual(evaluation, "NOT_EVALUATED")

    def test_nonconforming_observation_and_partial_detail(self) -> None:
        kwargs = self._kwargs(
            execution_status="COMPLETED",
            evaluation_status="DOES_NOT_CONFORM",
            observation_text="Нет сигнала",
        )
        self.assertEqual(kwargs["observation_text"], "Нет сигнала")
        partial = self.page.build_partial_detail("Проверен шкаф", "Осталась прозвонка")
        self.assertEqual(partial["completed_text"], "Проверен шкаф")
        self.assertEqual(partial["remaining_text"], "Осталась прозвонка")
        with self.assertRaises(ValueError):
            self.page.build_partial_detail(" ", "осталось")
        with self.assertRaises(ValueError):
            self.page.build_partial_detail("сделано", "")

    def test_blocked_category_and_other_requires_description(self) -> None:
        detail = self.page.build_blocked_detail(
            "Материалы",
            "Нет кабеля",
            "Да",
        )
        self.assertEqual(detail["constraint_category"], "MATERIALS")
        self.assertEqual(detail["constraint_description"], "Нет кабеля")
        self.assertIs(detail["other_work_available"], True)
        self.assertEqual(self.page.map_other_work_available("Нет"), False)
        self.assertIsNone(self.page.map_other_work_available("Не могу определить"))
        with self.assertRaises(ValueError):
            self.page.build_blocked_detail("Другое", "  ", "Нет")
        other = self.page.build_blocked_detail("Другое", "Нет доступа к ключу", "Нет")
        self.assertEqual(other["constraint_category"], "OTHER")
        self.assertEqual(other["other_work_available"], False)

    def test_labor_preview_not_trusted_as_write_field(self) -> None:
        self.assertEqual(self.page.compute_labor_preview(2, 4), Decimal("8"))
        self.assertEqual(self.page.compute_labor_preview(2, 1.5), Decimal("3.0"))
        kwargs = self._kwargs()
        self.assertNotIn("labor_hours", kwargs)
        self.assertEqual(kwargs["people_count"], 2)
        self.assertEqual(kwargs["duration_hours"], Decimal("4"))

    def test_zero_and_structured_measurements(self) -> None:
        occurred = datetime(2026, 9, 8, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))
        self.assertEqual(self.page.measurements_from_rows([], occurred), [])
        rows = [
            {
                "parameter_name": "Температура",
                "measurement_point": "Вытяжка",
                "value": 21.5,
                "unit": "°C",
                "instrument_text": "Термометр",
            }
        ]
        prepared = self.page.measurements_from_rows(rows, occurred)
        self.assertEqual(len(prepared), 1)
        self.assertEqual(prepared[0]["parameter_name"], "Температура")
        self.assertEqual(prepared[0]["measurement_point"], "Вытяжка")
        self.assertEqual(prepared[0]["unit"], "°C")
        self.assertEqual(prepared[0]["instrument_text"], "Термометр")
        self.assertTrue(prepared[0]["recorded_at"].tzinfo is not None)
        naive = datetime(2026, 9, 8, 12, 0)
        with self.assertRaises(ValueError):
            self.page.measurements_from_rows(rows, naive)

    def test_structured_kwargs_have_no_legacy_result(self) -> None:
        kwargs = self._kwargs()
        self.assertNotIn("result", kwargs)
        self.assertEqual(kwargs["execution_status"], "COMPLETED")
        self.assertEqual(kwargs["evaluation_status"], "CONFORMS")
        self.assertEqual(kwargs["operation_id"], "op-003")
        self.assertIsNone(kwargs["unmapped_operation_name"])
        self.assertEqual(kwargs["functional_position_id"], "fp-1")
        self.assertEqual(kwargs["source"], "STREAMLIT")
        self.assertEqual(kwargs["measurements"], [])

    def test_selected_work_scope_reaches_kwargs(self) -> None:
        kwargs = self._kwargs()
        self.assertEqual(kwargs["work_scope_id"], "scope-1")
        unmapped = self._kwargs(
            operation_mode=self.page.MODE_UNMAPPED,
            unmapped_operation_name="Прозвонка нестандартной цепи",
        )
        self.assertEqual(unmapped["work_scope_id"], "scope-1")
        self.assertIsNone(unmapped["operation_id"])

    def test_fingerprint_includes_work_scope_id(self) -> None:
        kwargs = self._kwargs()
        fingerprint = self.page.submit_fingerprint(kwargs)
        self.assertIn("scope-1", fingerprint)
        other = dict(kwargs)
        other["work_scope_id"] = "scope-2"
        self.assertNotEqual(fingerprint, self.page.submit_fingerprint(other))

    def test_save_refuses_missing_work_scope(self) -> None:
        self.assertEqual(
            self.page.require_selected_work_scope("scope-1"),
            "scope-1",
        )
        with self.assertRaises(ValueError) as ctx:
            self.page.require_selected_work_scope(None)
        self.assertIn("раздел работ", str(ctx.exception).lower())
        with self.assertRaises(ValueError):
            self.page.require_selected_work_scope("  ")
        self.assertIn("require_selected_work_scope(work_scope_id)", PAGE_PATH.read_text(encoding="utf-8"))

    def test_operation_picker_stays_on_legacy_owner_path(self) -> None:
        source = PAGE_PATH.read_text(encoding="utf-8")
        self.assertIn("list_active_operations(work_scope_id=", source)
        self.assertNotIn("pnr_work_scope_operations", source)
        self.assertNotIn("list_work_scope_operations", source)

    def test_unmapped_mode_reaches_unmapped_name(self) -> None:
        kwargs = self._kwargs(
            operation_mode=self.page.MODE_UNMAPPED,
            unmapped_operation_name="  Прозвонка нестандартной цепи  ",
        )
        self.assertIsNone(kwargs["operation_id"])
        self.assertEqual(kwargs["unmapped_operation_name"], "Прозвонка нестандартной цепи")

    def test_review_contains_russian_context_and_labor(self) -> None:
        lines = self.page.build_review_lines(
            project_name="Салмановское месторождение",
            title_name="УКПГ2-011",
            discipline_name="Вентиляция",
            system_label="П-1",
            object_label="Шкаф",
            scope_label="Автоматика / алгоритмы",
            work_label="Проверка алгоритма",
            done_label="Выполнена",
            evaluation_label="Соответствует",
            observation_text=None,
            partial_detail=None,
            blocked_detail_label=None,
            blocked_description=None,
            other_work_label=None,
            measurements=[],
            people_count=2,
            duration_hours=Decimal("4"),
            labor_preview=Decimal("8"),
        )
        text = "\n".join(lines)
        self.assertIn("Проект:", text)
        self.assertIn("Титул:", text)
        self.assertIn("Вид работ: ПНР", text)
        self.assertIn("Дисциплина:", text)
        self.assertIn("Система:", text)
        self.assertIn("Физический объект:", text)
        self.assertIn("Что произошло: Выполнена", text)
        self.assertIn("Оценка: Соответствует", text)
        self.assertIn("Количество специалистов: 2", text)
        self.assertIn("Трудозатраты: 8 чел·ч", text)
        self.assertNotIn("COMPLETED", text)
        self.assertNotIn("CONFORMS", text)

    def test_create_structured_event_not_called_without_submit(self) -> None:
        self._started[-1].assert_not_called()

    def _kwargs(self, **overrides: Any) -> dict[str, Any]:
        occurred = datetime(2026, 9, 8, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))
        payload = dict(
            system_id="sys-p1",
            object_id="obj-1",
            work_scope_id="scope-1",
            functional_position_id="fp-1",
            operation_mode=self.page.MODE_CATALOG,
            operation_id="op-003",
            unmapped_operation_name="ignored",
            execution_status="COMPLETED",
            evaluation_status="CONFORMS",
            occurred_at=occurred,
            people_count=2,
            duration_hours=Decimal("4"),
            observation_text=None,
            measurements=[],
            blocked_detail=None,
            partial_detail=None,
        )
        payload.update(overrides)
        return self.page.build_structured_kwargs(**payload)


if __name__ == "__main__":
    unittest.main()
