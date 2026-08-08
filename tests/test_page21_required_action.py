"""
Unit tests: Page 21 «Что необходимо сделать» → required_action.

No product DB writes. Run:
  python -m unittest tests.test_page21_required_action -v
"""

from __future__ import annotations

import importlib.util
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
PAGE24_PATH = (
    Path(__file__).resolve().parents[1]
    / "pages"
    / "24_Реестр_ограничений_допуска_месячного_плана.py"
)

TEST_ACTION = "TEST_REQUIRED_ACTION"
TEST_ACTION_2 = "TEST_REQUIRED_ACTION_UPDATED"


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
        fn.clear = lambda: None  # type: ignore[attr-defined]
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
    st.selectbox = lambda *a, **k: None
    st.multiselect = lambda *a, **k: []
    st.date_input = lambda *a, **k: date.today()
    st.number_input = lambda *a, **k: 0.0
    st.columns = lambda n, **k: [MagicMock() for _ in range(n if isinstance(n, int) else 3)]
    st.rerun = lambda: None
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
    st.title = lambda *a, **k: None
    st.metric = lambda *a, **k: None
    st.write = lambda *a, **k: None
    st.text = lambda *a, **k: None
    st.checkbox = lambda *a, **k: False
    st.stop = lambda: None
    st.toast = lambda *a, **k: None
    st.sidebar = MagicMock()
    st.empty = MagicMock()
    st.progress = MagicMock()
    st.status = MagicMock()
    st.tabs = lambda *a, **k: [MagicMock(), MagicMock()]
    sys.modules["streamlit"] = st
    return st


def _load_page21() -> ModuleType:
    for key in list(sys.modules):
        if key == "streamlit" or key.startswith("page21_ra_test"):
            del sys.modules[key]
    st = _install_streamlit_stub()
    # Avoid supabase/dotenv side effects where possible
    fake_dotenv = ModuleType("dotenv")
    fake_dotenv.load_dotenv = lambda *a, **k: None  # type: ignore[attr-defined]
    sys.modules["dotenv"] = fake_dotenv
    fake_supabase = ModuleType("supabase")
    fake_supabase.Client = object  # type: ignore[attr-defined]
    fake_supabase.create_client = lambda *a, **k: None  # type: ignore[attr-defined]
    sys.modules["supabase"] = fake_supabase

    fake_sb_client = ModuleType("services.supabase_client")
    fake_sb_client.supabase = None  # type: ignore[attr-defined]
    fake_sb_client.get_write_client = lambda: None  # type: ignore[attr-defined]
    sys.modules["services.supabase_client"] = fake_sb_client

    # Lightweight stubs for heavy optional imports pulled by Page 21
    for mod_name in (
        "services.boq_execution_history_service",
        "services.boq_execution_crews_service",
        "services.constraints_loader",
        "services.perf_audit",
    ):
        if mod_name not in sys.modules:
            stub = ModuleType(mod_name)
            if mod_name.endswith("history_service"):
                stub.get_boq_execution_history = lambda *a, **k: pd.DataFrame()  # type: ignore
            if mod_name.endswith("crews_service"):
                stub.get_boq_execution_crew_breakdown = lambda *a, **k: pd.DataFrame()  # type: ignore
            if mod_name.endswith("constraints_loader"):
                stub.fetch_all_constraints = lambda *a, **k: []  # type: ignore
            if mod_name.endswith("perf_audit"):
                stub.start_page = lambda *a, **k: None  # type: ignore
                stub.finish_page = lambda *a, **k: None  # type: ignore
                stub.stage = MagicMock()
            sys.modules[mod_name] = stub

    spec = importlib.util.spec_from_file_location("page21_ra_test", PAGE21_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["page21_ra_test"] = mod
    # __name__ != __main__ → main() does not run
    spec.loader.exec_module(mod)
    mod.st = st  # type: ignore[attr-defined]
    return mod


def _load_page24() -> ModuleType:
    for key in list(sys.modules):
        if key.startswith("page24_ra_test"):
            del sys.modules[key]
    if "streamlit" not in sys.modules:
        _install_streamlit_stub()
    st = sys.modules["streamlit"]

    # Ensure real registry service is importable (Page21 stubs may have shadowed paths).
    import services.monthly_plan_constraint_registry_service as _reg  # noqa: F401

    with patch.object(
        _reg,
        "load_constraint_registry",
        return_value=pd.DataFrame(),
    ):
        spec = importlib.util.spec_from_file_location("page24_ra_test", PAGE24_PATH)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules["page24_ra_test"] = mod

        class _Stop(Exception):
            pass

        st.stop = lambda: (_ for _ in ()).throw(_Stop())
        try:
            spec.loader.exec_module(mod)
        except _Stop:
            pass
    mod.st = st  # type: ignore[attr-defined]
    return mod


class Page21RequiredActionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_page21()
        self.st = self.mod.st
        self.st.session_state.clear()
        self.cid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeee0001"
        self.prefix = f"da_gov_{self.mod._da_stable_key_fragment(self.cid)}"
        self.row = pd.Series(
            {
                "constraint_id": self.cid,
                "responsible_department": "ПТО",
                "check_status": "ОЖИДАЕТ",
                "resolution_status": "OPEN",
                "comment": "",
                "created_by": None,
                "target_resolution_date": date(2026, 8, 15),
                "required_action": None,
            }
        )
        self.captured: list[dict[str, Any]] = []

        def _fake_update(constraint_id: str, payload: dict[str, Any]) -> None:
            self.captured.append({"constraint_id": constraint_id, "payload": dict(payload)})
            return None

        self._update_patch = patch.object(
            self.mod, "update_constraint_record", side_effect=_fake_update
        )
        self._update_patch.start()
        self.st.session_state["constraints_saver_name"] = "Tester T.T."

    def tearDown(self) -> None:
        self._update_patch.stop()
        self.st.session_state.clear()
        for key in list(sys.modules):
            if key in {"streamlit", "dotenv", "supabase"} or key.startswith(
                ("page21_ra_test", "page24_ra_test")
            ):
                del sys.modules[key]

    def _set_mvp_action(self, text: str) -> None:
        self.st.session_state[f"{self.prefix}_mvp_action"] = text
        self.mod._stamp_mvp_required_action(self.prefix, text)

    def test_source_widget_key(self) -> None:
        src = PAGE21_PATH.read_text(encoding="utf-8")
        self.assertIn('"Что необходимо сделать"', src)
        self.assertIn("_mvp_action", src)
        self.assertIn("required_action", src)

    def test_t1_hold_block_writes_required_action(self) -> None:
        self._set_mvp_action(TEST_ACTION)
        err = self.mod.save_direct_admission_decision(
            self.row,
            "block",
            "Officer O.O.",
            description="Описание ограничения для фиксации",
            block_reason="Конкретная причина блокировки теста",
            required_action=self.mod.resolve_required_action_for_write(prefix=self.prefix),
            target_date=date(2026, 8, 20),
            severity="MEDIUM",
        )
        self.assertIsNone(err)
        self.assertEqual(len(self.captured), 1)
        payload = self.captured[0]["payload"]
        self.assertEqual(payload.get("check_status"), "HOLD")
        self.assertEqual(payload.get("required_action"), TEST_ACTION)

    def test_t2_fail_block_path_writes_required_action(self) -> None:
        # Product fixation «Заблокировать» maps to HOLD (not separate FAIL action).
        # Covered as block path with required_action — same save function.
        self._set_mvp_action(TEST_ACTION)
        err = self.mod.save_direct_admission_decision(
            self.row,
            "block",
            "Officer O.O.",
            description="Описание для FAIL/BLOCK ветки",
            block_reason="Причина блокировки FAIL/BLOCK",
            required_action=TEST_ACTION,
            target_date=date(2026, 8, 20),
        )
        self.assertIsNone(err)
        self.assertEqual(self.captured[0]["payload"].get("required_action"), TEST_ACTION)
        self.assertEqual(self.captured[0]["payload"].get("check_status"), "HOLD")

    def test_t3_warning_clarify_writes_required_action(self) -> None:
        self._set_mvp_action(TEST_ACTION)
        err = self.mod.save_direct_admission_decision(
            self.row,
            "clarify",
            "Officer O.O.",
            description="Нужно уточнение по документации",
            required_action=self.mod.resolve_required_action_for_write(prefix=self.prefix),
            target_date=date(2026, 8, 20),
        )
        self.assertIsNone(err)
        payload = self.captured[0]["payload"]
        self.assertEqual(payload.get("check_status"), "WARNING")
        self.assertEqual(payload.get("required_action"), TEST_ACTION)

    def test_t4_repeated_save_updates_required_action(self) -> None:
        self._set_mvp_action(TEST_ACTION)
        self.mod.save_direct_admission_decision(
            self.row,
            "block",
            "Officer O.O.",
            description="Описание 1",
            block_reason="Причина 1 достаточно конкретная",
            required_action=TEST_ACTION,
            target_date=date(2026, 8, 20),
        )
        self._set_mvp_action(TEST_ACTION_2)
        row2 = self.row.copy()
        row2["required_action"] = TEST_ACTION
        row2["created_by"] = "Tester T.T."
        self.mod.save_direct_admission_decision(
            row2,
            "block",
            "Officer O.O.",
            description="Описание 2",
            block_reason="Причина 2 достаточно конкретная",
            required_action=TEST_ACTION_2,
            target_date=date(2026, 8, 21),
        )
        self.assertEqual(len(self.captured), 2)
        self.assertEqual(self.captured[0]["payload"]["required_action"], TEST_ACTION)
        self.assertEqual(self.captured[1]["payload"]["required_action"], TEST_ACTION_2)

    def test_t5_empty_unrelated_save_preserves_old_value(self) -> None:
        # Empty mvp_action / empty required_action → omit key from payload
        self.st.session_state.pop(f"{self.prefix}_mvp_action", None)
        self.st.session_state.pop(f"{self.prefix}_required_action_committed", None)
        payload: dict[str, Any] = {"check_status": "HOLD", "updated_by": "X"}
        out = self.mod.apply_required_action_to_payload(
            payload,
            "",
            prefix=self.prefix,
        )
        self.assertNotIn("required_action", out)

        # pass path must not write required_action
        self.captured.clear()
        err = self.mod.save_direct_admission_decision(
            self.row,
            "pass",
            "Officer O.O.",
            comment="ok",
            owner_name="Officer O.O.",
        )
        self.assertIsNone(err)
        self.assertNotIn("required_action", self.captured[0]["payload"])

    def test_t6_page24_display_reads_required_action(self) -> None:
        src = PAGE24_PATH.read_text(encoding="utf-8")
        binding = [
            ln
            for ln in src.splitlines()
            if "Требуемое действие" in ln
            and "required_action" in ln
            and "display_author_empty" in ln
        ]
        self.assertTrue(binding)
        self.assertIn('row.get("required_action")', binding[0])
        self.assertNotIn("block_reason", binding[0])
        self.assertNotIn("root_cause", binding[0])
        self.assertNotIn("problem_description", binding[0])
        self.assertIn('key="reg_upd_required_action"', src)
        self.assertIn('("required_action", "Требуемое действие"', src)

    def test_resolve_prefers_candidate_then_session(self) -> None:
        self._set_mvp_action("FROM_SESSION")
        self.assertEqual(
            self.mod.resolve_required_action_for_write("FROM_ARG", prefix=self.prefix),
            "FROM_ARG",
        )
        self.assertEqual(
            self.mod.resolve_required_action_for_write("", prefix=self.prefix),
            "FROM_SESSION",
        )


if __name__ == "__main__":
    unittest.main()
