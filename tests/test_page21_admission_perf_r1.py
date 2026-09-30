"""
Page 21 Admission — golden UX / multi-BOQ selection regression guards.

Protects pre-R1 queue behavior: clickable cards + invisible buttons.
No product DB writes.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
import unittest
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd


PAGE21_PATH = (
    Path(__file__).resolve().parents[1]
    / "pages"
    / "21_Admission_Управление_ограничениями_месячного_плана.py"
)


class _SessionState(dict):
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


def _cache_data_stub(*args: Any, **kwargs: Any) -> Any:
    def decorator(fn: Any) -> Any:
        def clear() -> None:
            clear.called = True  # type: ignore[attr-defined]

        clear.called = False  # type: ignore[attr-defined]
        fn.clear = clear  # type: ignore[attr-defined]
        return fn

    if args and callable(args[0]) and not kwargs:
        return decorator(args[0])
    return decorator


def _install_streamlit_stub() -> ModuleType:
    st = ModuleType("streamlit")
    st.session_state = _SessionState()
    st.set_page_config = lambda **kwargs: None
    st.cache_data = _cache_data_stub
    st.cache_resource = _cache_data_stub
    st.fragment = lambda fn=None, **kwargs: (fn if fn is not None else (lambda f: f))
    st.markdown = lambda *a, **k: None
    st.caption = lambda *a, **k: None
    st.info = lambda *a, **k: None
    st.warning = lambda *a, **k: None
    st.error = lambda *a, **k: None
    st.success = lambda *a, **k: None
    st.button = lambda *a, **k: False
    st.radio = lambda *a, **k: None
    st.text_area = lambda *a, **k: ""
    st.text_input = lambda *a, **k: ""
    st.selectbox = lambda *a, **k: (a[1][0] if len(a) > 1 and a[1] else None)
    st.multiselect = lambda *a, **k: []
    st.date_input = lambda *a, **k: date.today()
    st.number_input = lambda *a, **k: 0.0
    st.columns = lambda n, **k: [MagicMock() for _ in range(n if isinstance(n, int) else 3)]
    st.rerun = lambda *a, **k: None
    st.expander = MagicMock()
    st.form = MagicMock()
    st.form_submit_button = lambda *a, **k: False
    st.dataframe = lambda *a, **k: MagicMock()
    st.spinner = MagicMock()
    st.divider = lambda: None
    st.container = MagicMock()
    st.column_config = MagicMock()
    st.column_config.NumberColumn = lambda *a, **k: None
    st.column_config.TextColumn = lambda *a, **k: None
    st.segmented_control = lambda *a, **k: None
    st.title = lambda *a, **k: None
    st.metric = lambda *a, **k: None
    st.write = lambda *a, **k: None
    st.checkbox = lambda *a, **k: False
    st.json = lambda *a, **k: None
    st.stop = lambda: None
    sys.modules["streamlit"] = st
    return st


def _load_page21() -> ModuleType:
    for key in list(sys.modules):
        if key == "streamlit" or key.startswith("page21_perf_r1"):
            del sys.modules[key]
    st = _install_streamlit_stub()

    fake_dotenv = ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *a, **k: None  # type: ignore[attr-defined]
    sys.modules["dotenv"] = fake_dotenv
    fake_supabase = ModuleType("supabase")
    fake_supabase.Client = object  # type: ignore[attr-defined]
    fake_supabase.create_client = lambda *a, **k: None  # type: ignore[attr-defined]
    sys.modules["supabase"] = fake_supabase
    fake_sb_client = ModuleType("services.supabase_client")
    fake_sb_client.supabase = None  # type: ignore[attr-defined]
    sys.modules["services.supabase_client"] = fake_sb_client

    for mod_name in (
        "services.boq_execution_history_service",
        "services.boq_execution_crews_service",
        "services.constraints_loader",
        "services.perf_audit",
        "services.constraints_service",
        "services.constraint_display",
    ):
        if mod_name not in sys.modules:
            stub = ModuleType(mod_name)
            if mod_name.endswith("history_service"):
                stub.get_boq_execution_history = lambda *a, **k: pd.DataFrame()  # type: ignore
            if mod_name.endswith("crews_service"):
                stub.get_boq_execution_crew_breakdown = lambda *a, **k: pd.DataFrame()  # type: ignore
            if mod_name.endswith("constraints_loader"):
                stub.fetch_all_constraints = lambda *a, **k: []  # type: ignore
                stub.fetch_constraints_scoped = lambda *a, **k: ([], {})  # type: ignore
                stub.fetch_constraint_filter_metadata = lambda *a, **k: {}  # type: ignore
                stub.scope_filters_from_values = lambda *a, **k: (None, None)  # type: ignore
                stub.DEFAULT_CONSTRAINT_COLUMNS = ("constraint_id", "month_key")  # type: ignore
            if mod_name.endswith("perf_audit"):
                stub.start_page = lambda *a, **k: None  # type: ignore
                stub.finish_page = lambda *a, **k: None  # type: ignore
                stub.stage = MagicMock()
                stub.log_supabase_query = lambda *a, **k: None  # type: ignore
                stub.perf_audit_enabled = lambda: False  # type: ignore
            if mod_name.endswith("constraints_service"):
                stub.merge_created_by_once = lambda payload, **k: payload  # type: ignore
            if mod_name.endswith("constraint_display"):
                stub.constraint_block_substance = lambda *a, **k: ""  # type: ignore
                stub.is_generic_block_reason = lambda *a, **k: False  # type: ignore
                stub.is_insufficient_block_description = lambda *a, **k: False  # type: ignore
                stub.registry_specific_block_reason = lambda *a, **k: ""  # type: ignore
            sys.modules[mod_name] = stub

    spec = importlib.util.spec_from_file_location("page21_perf_r1", PAGE21_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["page21_perf_r1"] = mod
    spec.loader.exec_module(mod)
    mod.st = st  # type: ignore[attr-defined]
    return mod


def _sample_workbench() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "constraint_id": "cid-A",
                "boq_code": "B-001",
                "boq_name": "Work A",
                "check_status": "ОЖИДАЕТ",
                "responsible_department": "ПТО",
                "line_id": "line-1",
                "check_name": "PTO check",
            },
            {
                "constraint_id": "cid-B",
                "boq_code": "B-002",
                "boq_name": "Work B",
                "check_status": "ОЖИДАЕТ",
                "responsible_department": "ПТО",
                "line_id": "line-2",
                "check_name": "PTO check",
            },
            {
                "constraint_id": "cid-C",
                "boq_code": "B-003",
                "boq_name": "Work C",
                "check_status": "ОЖИДАЕТ",
                "responsible_department": "ПТО",
                "line_id": "line-3",
                "check_name": "PTO check",
            },
            {
                "constraint_id": "cid-D",
                "boq_code": "B-004",
                "boq_name": "Work D",
                "check_status": "ОЖИДАЕТ",
                "responsible_department": "ПТО",
                "line_id": "line-4",
                "check_name": "PTO check",
            },
            {
                "constraint_id": "cid-E",
                "boq_code": "B-005",
                "boq_name": "Work E",
                "check_status": "ОЖИДАЕТ",
                "responsible_department": "ПТО",
                "line_id": "line-5",
                "check_name": "PTO check",
            },
        ]
    )


class Page21GoldenUxGuards(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_page21()
        self.st = self.mod.st
        self.st.session_state.clear()

    def _queue_fn_ast(self):
        source = PAGE21_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "render_direct_admit_queue_pane":
                return node
        self.fail("render_direct_admit_queue_pane missing")

    def test_queue_uses_clickable_cards_and_buttons_not_selectbox_dataframe(self) -> None:
        fn = self._queue_fn_ast()
        src = ast.get_source_segment(PAGE21_PATH.read_text(encoding="utf-8"), fn) or ""
        self.assertIn("_da_queue_card_html", src)
        self.assertIn("clickable=True", src)
        self.assertIn("st.button", src)
        self.assertNotIn("st.selectbox", src)
        self.assertNotIn("st.dataframe", src)
        self.assertNotIn("st.radio", src)

    def test_no_fragment_on_direct_admit_module(self) -> None:
        source = PAGE21_PATH.read_text(encoding="utf-8")
        self.assertNotIn("@st.fragment", source)
        self.assertNotIn("_render_direct_admission_workbench_fragment", source)

    def test_multi_boq_selection_switches_selected_id(self) -> None:
        wb = _sample_workbench()
        for cid in ("cid-A", "cid-B", "cid-C", "cid-D", "cid-E"):
            self.mod._da_queue_select_item(cid)
            self.assertEqual(
                self.st.session_state[self.mod.DIRECT_ADMIT_SELECTED_CID_KEY], cid
            )
            resolved = self.mod.resolve_direct_admit_selected_cid(wb)
            self.assertEqual(resolved, cid)

    def test_repeated_selection_works(self) -> None:
        wb = _sample_workbench()
        self.mod._da_queue_select_item("cid-A")
        self.mod._da_queue_select_item("cid-C")
        self.mod._da_queue_select_item("cid-A")
        self.assertEqual(self.mod.resolve_direct_admit_selected_cid(wb), "cid-A")

    def test_three_pane_labels_preserved(self) -> None:
        source = PAGE21_PATH.read_text(encoding="utf-8")
        self.assertIn("1. Очередь допуска", source)
        self.assertIn("2. Решение по коду", source)
        self.assertIn("3. Фиксация решения", source)
        self.assertIn("Непосредственный допуск по отделам", source)

    def test_no_new_tab_generators(self) -> None:
        source = PAGE21_PATH.read_text(encoding="utf-8")
        self.assertNotIn('target="_blank"', source)
        self.assertNotIn("st.page_link", source)
        self.assertNotIn("st.switch_page", source)

    def test_save_pass_no_global_clear_keeps_payload(self) -> None:
        row = pd.Series(
            {
                "constraint_id": "cid-save-1",
                "responsible_department": "ПТО",
                "comment": "",
                "created_by": None,
            }
        )
        clear_fn = self.mod.load_constraints.clear
        clear_fn.called = False  # type: ignore[attr-defined]
        with patch.object(self.mod, "update_constraint_record", return_value=None) as upd:
            err = self.mod.save_direct_admission_decision(
                row, "pass", "Officer Test", comment="ok", owner_name="Officer Test"
            )
        self.assertIsNone(err)
        upd.assert_called_once()
        payload = upd.call_args[0][1]
        self.assertEqual(payload["check_status"], "PASS")
        self.assertFalse(clear_fn.called)  # type: ignore[attr-defined]

    def test_package_cache_invisible_perf_helper_present(self) -> None:
        self.assertTrue(callable(self.mod.get_cached_package_dataframe))
        src = inspect.getsource(self.mod.save_direct_admission_decision)
        self.assertIn("register_local_constraint_row_patch", src)


if __name__ == "__main__":
    unittest.main()
