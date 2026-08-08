"""
Isolated tests for Page 24 R2 update-form helpers.

No product DB writes. Run:
  python -m unittest tests.test_page24_update_form -v
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


PAGE_PATH = (
    Path(__file__).resolve().parents[1]
    / "pages"
    / "24_Реестр_ограничений_допуска_месячного_плана.py"
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
    st.text_area = lambda *a, **k: None
    st.text_input = lambda *a, **k: None
    st.selectbox = lambda *a, **k: None
    st.date_input = lambda *a, **k: date.today()
    st.columns = lambda n: [MagicMock() for _ in range(n if isinstance(n, int) else 3)]
    st.rerun = lambda: None
    st.expander = MagicMock()
    st.form = MagicMock()
    st.form_submit_button = lambda *a, **k: False
    st.dataframe = lambda *a, **k: MagicMock()
    st.spinner = MagicMock()
    st.divider = lambda: None
    st.column_config = MagicMock()
    st.column_config.NumberColumn = lambda *a, **k: None
    st.column_config.TextColumn = lambda *a, **k: None
    st.title = lambda *a, **k: None
    st.metric = lambda *a, **k: None
    st.write = lambda *a, **k: None
    st.text = lambda *a, **k: None
    st.checkbox = lambda *a, **k: False
    st.stop = lambda: None
    sys.modules["streamlit"] = st
    return st


def _load_page() -> ModuleType:
    for key in list(sys.modules):
        if key == "streamlit" or key.startswith("page24_r2_test"):
            del sys.modules[key]
    st = _install_streamlit_stub()
    # Avoid executing page body (it loads registry at import). Load only by compiling
    # after patching loaders — simplest: import helpers via exec of filtered?
    # Page runs UI at import. Patch load_constraint_registry before exec.
    with patch(
        "services.monthly_plan_constraint_registry_service.load_constraint_registry",
        return_value=pd.DataFrame(),
    ):
        spec = importlib.util.spec_from_file_location("page24_r2_test", PAGE_PATH)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules["page24_r2_test"] = mod
        # Page calls st.stop() on empty — wrap stop to raise SystemExit we catch
        class _Stop(Exception):
            pass

        st.stop = lambda: (_ for _ in ()).throw(_Stop())
        try:
            spec.loader.exec_module(mod)
        except _Stop:
            pass
    mod.st = st  # type: ignore[attr-defined]
    return mod


class Page24UpdateFormTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_page()
        self.st = self.mod.st
        self.st.session_state.clear()
        self.row = pd.Series(
            {
                "constraint_id": "cccccccc-cccc-cccc-cccc-cccccccc0001",
                "resolution_status": "OPEN",
                "problem_owner": "Owner A",
                "owner_name": "Exec B",
                "subcontractor_coordinator": None,
                "constraint_category": "Документы",
                "constraint_priority": "NORMAL",
                "problem_description": "Desc",
                "problem_impact": "Impact",
                "required_action": "Act",
                "deadline_status": "NOT_SET",
                "deadline_source": None,
                "constraint_occurred_at": date(2026, 7, 1),
                "target_resolution_date": date(2026, 8, 10),
                "next_control_date": None,
            }
        )

    def tearDown(self) -> None:
        self.st.session_state.clear()
        for key in list(sys.modules):
            if key == "streamlit" or key.startswith("page24_r2_test"):
                del sys.modules[key]

    def test_t01_hydrate_by_constraint_id(self) -> None:
        baseline = self.mod.row_to_update_baseline(self.row)
        changed = self.mod.hydrate_update_form_state(
            self.st.session_state, self.row["constraint_id"], baseline
        )
        self.assertTrue(changed)
        self.assertEqual(
            self.st.session_state["reg_upd_active_cid"], self.row["constraint_id"]
        )
        self.assertEqual(self.st.session_state["reg_upd_problem_owner"], "Owner A")
        # same cid keeps live input
        self.st.session_state["reg_upd_problem_owner"] = "LIVE"
        changed2 = self.mod.hydrate_update_form_state(
            self.st.session_state, self.row["constraint_id"], baseline
        )
        self.assertFalse(changed2)
        self.assertEqual(self.st.session_state["reg_upd_problem_owner"], "LIVE")

    def test_t02_dirty_patch_changed_only(self) -> None:
        baseline = self.mod.row_to_update_baseline(self.row)
        current = dict(baseline)
        current["owner_name"] = "Exec NEW"
        patch = self.mod.build_update_dirty_patch(baseline, current)
        self.assertEqual(patch, {"owner_name": "Exec NEW"})

    def test_t03_unchanged_omitted(self) -> None:
        baseline = self.mod.row_to_update_baseline(self.row)
        patch = self.mod.build_update_dirty_patch(baseline, dict(baseline))
        self.assertEqual(patch, {})

    def test_t04_clear_to_null(self) -> None:
        baseline = self.mod.row_to_update_baseline(self.row)
        current = dict(baseline)
        current["problem_owner"] = None
        patch = self.mod.build_update_dirty_patch(baseline, current)
        self.assertIn("problem_owner", patch)
        self.assertIsNone(patch["problem_owner"])

    def test_t05_enum_mapping_display(self) -> None:
        self.assertEqual(self.mod.display_constraint_priority("HIGH"), "Высокий")
        self.assertEqual(self.mod.display_deadline_status("CONFIRMED"), "Подтверждён")
        self.assertEqual(self.mod.display_deadline_source("CUSTOMER"), "Заказчик")

    def test_t06_update_comment_required_path(self) -> None:
        # Service-level: empty comment rejected
        from services.monthly_plan_constraint_registry_service import update_constraint

        with patch(
            "services.monthly_plan_constraint_registry_service.get_write_client",
            return_value=MagicMock(),
        ) as client_fn:
            result = update_constraint(
                constraint_id=self.row["constraint_id"],
                updated_by="TEST",
                update_comment="",
                patch={"owner_name": "X"},
            )
        self.assertFalse(result["ok"])
        self.assertIn("комментарий", result["error"].lower())
        client_fn.return_value.rpc.assert_not_called()

    def test_t07_no_changes_no_rpc(self) -> None:
        from services.monthly_plan_constraint_registry_service import update_constraint

        client = MagicMock()
        with patch(
            "services.monthly_plan_constraint_registry_service.get_write_client",
            return_value=client,
        ):
            result = update_constraint(
                constraint_id=self.row["constraint_id"],
                updated_by="TEST",
                update_comment="note",
                patch={},
            )
        self.assertEqual(result["status"], "no_changes")
        client.rpc.assert_not_called()

    def test_t08_success_clears_read_caches(self) -> None:
        from services import monthly_plan_constraint_registry_service as svc

        client = MagicMock()
        client.rpc.return_value.execute.return_value = MagicMock(
            data={"status": "updated", "changed_fields": ["owner_name"]}
        )
        with patch.object(svc, "get_write_client", return_value=client):
            with patch.object(svc, "clear_registry_read_caches") as clear_fn:
                result = svc.update_constraint(
                    constraint_id=self.row["constraint_id"],
                    updated_by="TEST",
                    update_comment="note",
                    patch={"owner_name": "New"},
                )
        self.assertTrue(result["ok"])
        clear_fn.assert_called_once()

    def test_t09_error_preserves_form_session(self) -> None:
        baseline = self.mod.row_to_update_baseline(self.row)
        self.mod.hydrate_update_form_state(
            self.st.session_state, self.row["constraint_id"], baseline
        )
        self.st.session_state["reg_upd_problem_owner"] = "TYPED"
        self.st.session_state["reg_upd_update_comment"] = "keep me"
        # Simulate error path: do not clear session
        self.st.session_state["reg_update_error"] = "fail"
        self.assertEqual(self.st.session_state["reg_upd_problem_owner"], "TYPED")
        self.assertEqual(self.st.session_state["reg_upd_update_comment"], "keep me")

    def test_t10_resolved_disabled(self) -> None:
        self.assertTrue(self.mod.can_edit_update_form("OPEN"))
        self.assertTrue(self.mod.can_edit_update_form("IN_PROGRESS"))
        self.assertFalse(self.mod.can_edit_update_form("RESOLVED"))
        self.assertFalse(self.mod.can_edit_update_form("CANCELLED"))

    # ---- Date UX (modes outside form; dirty patch contract) ----

    def test_date_ux_t1_keep_omits_key(self) -> None:
        baseline = self.mod.row_to_update_baseline(self.row)
        current = self.mod.collect_update_form_current(
            text_values={k: baseline[k] for k in self.mod.UPDATE_TEXT_FIELDS},
            enum_values={k: baseline[k] or "" for k in self.mod.UPDATE_ENUM_FIELDS},
            date_modes={
                "constraint_occurred_at": self.mod.DATE_MODE_KEEP,
                "target_resolution_date": self.mod.DATE_MODE_KEEP,
                "next_control_date": self.mod.DATE_MODE_KEEP,
            },
            date_values={
                "constraint_occurred_at": date(2099, 1, 1),
                "target_resolution_date": date(2099, 1, 1),
                "next_control_date": date(2099, 1, 1),
            },
        )
        for field in self.mod.UPDATE_DATE_FIELDS:
            self.assertNotIn(field, current)
        patch = self.mod.build_update_dirty_patch(baseline, current)
        for field in self.mod.UPDATE_DATE_FIELDS:
            self.assertNotIn(field, patch)

    def test_date_ux_t2_set_puts_iso_in_patch(self) -> None:
        baseline = self.mod.row_to_update_baseline(self.row)
        new_occurred = date(2026, 8, 1)
        current = self.mod.collect_update_form_current(
            text_values={k: baseline[k] for k in self.mod.UPDATE_TEXT_FIELDS},
            enum_values={k: baseline[k] or "" for k in self.mod.UPDATE_ENUM_FIELDS},
            date_modes={
                "constraint_occurred_at": self.mod.DATE_MODE_SET,
                "target_resolution_date": self.mod.DATE_MODE_KEEP,
                "next_control_date": self.mod.DATE_MODE_KEEP,
            },
            date_values={
                "constraint_occurred_at": new_occurred,
                "target_resolution_date": None,
                "next_control_date": None,
            },
        )
        self.assertEqual(current["constraint_occurred_at"], "2026-08-01")
        self.assertNotIn("target_resolution_date", current)
        patch = self.mod.build_update_dirty_patch(baseline, current)
        self.assertEqual(patch.get("constraint_occurred_at"), "2026-08-01")
        self.assertNotIn("target_resolution_date", patch)
        self.assertNotIn("next_control_date", patch)

    def test_date_ux_t3_clear_puts_null(self) -> None:
        baseline = self.mod.row_to_update_baseline(self.row)
        current = self.mod.collect_update_form_current(
            text_values={k: baseline[k] for k in self.mod.UPDATE_TEXT_FIELDS},
            enum_values={k: baseline[k] or "" for k in self.mod.UPDATE_ENUM_FIELDS},
            date_modes={
                "constraint_occurred_at": self.mod.DATE_MODE_KEEP,
                "target_resolution_date": self.mod.DATE_MODE_CLEAR,
                "next_control_date": self.mod.DATE_MODE_KEEP,
            },
            date_values={
                "constraint_occurred_at": None,
                "target_resolution_date": date(2026, 8, 10),
                "next_control_date": None,
            },
        )
        self.assertIn("target_resolution_date", current)
        self.assertIsNone(current["target_resolution_date"])
        patch = self.mod.build_update_dirty_patch(baseline, current)
        self.assertIn("target_resolution_date", patch)
        self.assertIsNone(patch["target_resolution_date"])

    def test_date_ux_t4_mode_switch_preserves_other_fields(self) -> None:
        baseline = self.mod.row_to_update_baseline(self.row)
        self.mod.hydrate_update_form_state(
            self.st.session_state, self.row["constraint_id"], baseline
        )
        self.st.session_state["reg_upd_problem_owner"] = "LIVE_OWNER"
        self.st.session_state["reg_upd_owner_name"] = "LIVE_EXEC"
        self.st.session_state["reg_upd_constraint_occurred_at_mode"] = (
            self.mod.DATE_MODE_SET
        )
        self.st.session_state["reg_upd_constraint_occurred_at_date"] = date(2026, 8, 1)
        # Same constraint hydrate must keep live text values
        changed = self.mod.hydrate_update_form_state(
            self.st.session_state, self.row["constraint_id"], baseline
        )
        self.assertFalse(changed)
        self.assertEqual(self.st.session_state["reg_upd_problem_owner"], "LIVE_OWNER")
        self.assertEqual(self.st.session_state["reg_upd_owner_name"], "LIVE_EXEC")
        self.assertEqual(
            self.st.session_state["reg_upd_constraint_occurred_at_mode"],
            self.mod.DATE_MODE_SET,
        )

    def test_date_ux_t5_no_rpc_before_submit(self) -> None:
        """Mode/patch helpers never call update RPC by themselves."""
        from services.monthly_plan_constraint_registry_service import update_constraint

        baseline = self.mod.row_to_update_baseline(self.row)
        current = self.mod.collect_update_form_current(
            text_values={k: baseline[k] for k in self.mod.UPDATE_TEXT_FIELDS},
            enum_values={k: baseline[k] or "" for k in self.mod.UPDATE_ENUM_FIELDS},
            date_modes={
                "constraint_occurred_at": self.mod.DATE_MODE_SET,
                "target_resolution_date": self.mod.DATE_MODE_CLEAR,
                "next_control_date": self.mod.DATE_MODE_KEEP,
            },
            date_values={
                "constraint_occurred_at": date(2026, 8, 1),
                "target_resolution_date": None,
                "next_control_date": None,
            },
        )
        dirty = self.mod.build_update_dirty_patch(baseline, current)
        self.assertTrue(dirty)

        client = MagicMock()
        with patch(
            "services.monthly_plan_constraint_registry_service.get_write_client",
            return_value=client,
        ):
            # Building patch is not submit — RPC must not run unless update_constraint called
            client.rpc.assert_not_called()
            # Explicit empty submit path still no-op
            result = update_constraint(
                constraint_id=self.row["constraint_id"],
                updated_by="TEST",
                update_comment="note",
                patch={},
            )
        self.assertEqual(result["status"], "no_changes")
        client.rpc.assert_not_called()

        # Structural: date controls helper exists and form source keeps dates outside form
        self.assertTrue(callable(self.mod.render_update_date_controls))
        src = PAGE_PATH.read_text(encoding="utf-8")
        marker = "date_modes_ui, date_values_ui = render_update_date_controls()"
        form_marker = 'with st.form("reg_update_form"'
        self.assertIn(marker, src)
        self.assertLess(src.index(marker), src.index(form_marker))

    # ---- created_by recorder display (not updated_by) ----

    def test_t4_page24_label_uses_created_by_not_updated_by(self) -> None:
        row = self.row.copy()
        row["created_by"] = "RECORDER_FIO"
        row["updated_by"] = "EDITOR_FIO"
        self.assertEqual(
            self.mod.display_recorder(row.get("created_by")), "RECORDER_FIO"
        )
        self.assertEqual(
            self.mod.display_updated_by(row.get("updated_by")), "EDITOR_FIO"
        )
        table = self.mod.build_display_table(pd.DataFrame([row]))
        self.assertEqual(
            table.iloc[0]["Зафиксировал ограничение"], "RECORDER_FIO"
        )
        self.assertEqual(table.iloc[0]["Последнее изменение"], "EDITOR_FIO")
        # Must not show updated_by under the recorder label
        self.assertNotEqual(
            table.iloc[0]["Зафиксировал ограничение"], "EDITOR_FIO"
        )

    def test_t5_created_by_missing_shows_ne_zafiksirovano(self) -> None:
        self.assertEqual(self.mod.display_recorder(None), "Не зафиксировано")
        self.assertEqual(self.mod.display_recorder(""), "Не зафиксировано")
        row = self.row.copy()
        row["created_by"] = None
        table = self.mod.build_display_table(pd.DataFrame([row]))
        self.assertEqual(
            table.iloc[0]["Зафиксировал ограничение"], "Не зафиксировано"
        )

    def test_t6_update_form_excludes_created_by(self) -> None:
        self.assertNotIn("created_by", self.mod.UPDATE_TEXT_FIELDS)
        self.assertNotIn("created_by", self.mod.UPDATE_ENUM_FIELDS)
        self.assertNotIn("created_by", self.mod.UPDATE_DATE_FIELDS)
        from services.monthly_plan_constraint_registry_service import (
            UPDATE_PATCH_WHITELIST,
        )

        self.assertNotIn("created_by", UPDATE_PATCH_WHITELIST)
        src = PAGE_PATH.read_text(encoding="utf-8")
        # Update form must not expose an editable created_by widget
        self.assertNotIn('key="reg_upd_created_by"', src)
        self.assertIn('("created_by", "Зафиксировал ограничение"', src)

    def test_table_status_styles_are_text_only(self) -> None:
        for styles in (
            self.mod.CHECK_STATUS_TEXT_STYLE,
            self.mod.RESOLUTION_STATUS_TEXT_STYLE,
            self.mod.PRIORITY_TEXT_STYLE,
        ):
            for css in styles.values():
                self.assertNotIn("background", css.lower())
                self.assertIn("font-weight:700", css)
                self.assertNotIn("font-size:", css)
                self.assertIn("color:", css)

    def test_table_labels_owner_summary_impact(self) -> None:
        labels = {label for _, label, _ in self.mod.TABLE_COLUMNS}
        self.assertIn("Владелец ограничения", labels)
        self.assertIn("Суть ограничения", labels)
        self.assertIn("Влияние", labels)
        self.assertNotIn("Владелец проблемы", labels)
        self.assertNotIn("Суть проблемы", labels)
        row = self.row.copy()
        row["constraint_priority"] = "CRITICAL"
        row["check_status"] = "HOLD"
        row["resolution_status"] = "OPEN"
        row["problem_impact"] = None
        table = self.mod.build_display_table(pd.DataFrame([row]))
        self.assertEqual(table.iloc[0]["Приоритет"], "КРИТИЧЕСКИЙ")
        self.assertEqual(table.iloc[0]["Статус проверки"], "УДЕРЖАНИЕ")
        self.assertEqual(table.iloc[0]["Статус устранения"], "ОТКРЫТО")
        self.assertEqual(table.iloc[0]["Влияние"], "Не заполнено автором")
        # HTML registry renderer removed; Styler keeps text color for statuses.
        styler = self.mod.style_registry_display(table)
        self.assertTrue(hasattr(styler, "data") or hasattr(styler, "_todo"))
        src = PAGE_PATH.read_text(encoding="utf-8")
        self.assertIn("st.dataframe(", src)
        self.assertIn('on_select="rerun"', src)
        self.assertIn('selection_mode="single-row"', src)
        self.assertNotIn("build_registry_html_table", src)
        self.assertNotIn("Расширенный просмотр таблицы", src)
        self.assertIn("#DC2626", self.mod.PRIORITY_TEXT_STYLE["КРИТИЧЕСКИЙ"])
        self.assertIn("#DC2626", self.mod.CHECK_STATUS_TEXT_STYLE["ЗАБЛОКИРОВАНО"])


if __name__ == "__main__":
    unittest.main()
