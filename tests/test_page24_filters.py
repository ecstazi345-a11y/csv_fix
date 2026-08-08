"""
Unit tests for Page 24 apply_filters (registry filters only).

No product DB writes. No dataframe renderer checks.
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
        if key == "streamlit" or key.startswith("page24_filters_test"):
            del sys.modules[key]
    st = _install_streamlit_stub()

    class _Stop(Exception):
        pass

    st.stop = lambda: (_ for _ in ()).throw(_Stop())
    with patch(
        "services.monthly_plan_constraint_registry_service.load_constraint_registry",
        return_value=pd.DataFrame(),
    ):
        spec = importlib.util.spec_from_file_location("page24_filters_test", PAGE_PATH)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules["page24_filters_test"] = mod
        try:
            spec.loader.exec_module(mod)
        except _Stop:
            pass
    return mod


def _base_kwargs(**overrides: Any) -> dict[str, Any]:
    base = {
        "project": "Все",
        "month": "Все",
        "facility": "Все",
        "discipline": "Все",
        "department": "Все",
        "check_status": "Все",
        "resolution_status": "Все",
        "open_mode": "Все",
        "search": "",
    }
    base.update(overrides)
    return base


class Page24FiltersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load_page()

    def _sample(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "project_code": "P1",
                    "month_key": "август-2026",
                    "facility_building": "16160-13",
                    "construction_discipline": "СМР",
                    "responsible_department": "ПТО",
                    "queue": "1 очередь",
                    "check_status": "HOLD",
                    "resolution_status": "OPEN",
                    "problem_owner": "Owner A",
                    "owner_name": "Exec A",
                    "subcontractor_coordinator": "Coord A",
                    "constraint_priority": "HIGH",
                    "effective_deadline_status": "ON_TRACK",
                    "is_deadline_overdue": False,
                    "is_next_control_overdue": False,
                    "boq_code": "BOQ-1",
                    "boq_name": "Work one",
                },
                {
                    "project_code": "P1",
                    "month_key": "август-2026",
                    "facility_building": "26160-17",
                    "construction_discipline": "СМР",
                    "responsible_department": "ПТО",
                    "queue": "2 очередь",
                    "check_status": "FAIL",
                    "resolution_status": "IN_PROGRESS",
                    "problem_owner": "Owner B",
                    "owner_name": "Exec B",
                    "subcontractor_coordinator": "",
                    "constraint_priority": "LOW",
                    "effective_deadline_status": "OVERDUE",
                    "is_deadline_overdue": True,
                    "is_next_control_overdue": False,
                    "boq_code": "BOQ-2",
                    "boq_name": "Work two",
                },
                {
                    "project_code": "P1",
                    "month_key": "август-2026",
                    "facility_building": "16160-13",
                    "construction_discipline": "СМР",
                    "responsible_department": "ПТО",
                    "queue": "1 очередь",
                    "check_status": "PASS",
                    "resolution_status": "RESOLVED",
                    "problem_owner": "Owner A",
                    "owner_name": "Exec A",
                    "subcontractor_coordinator": "Coord A",
                    "constraint_priority": "HIGH",
                    "effective_deadline_status": "CLOSED",
                    "is_deadline_overdue": False,
                    "is_next_control_overdue": False,
                    "boq_code": "BOQ-3",
                    "boq_name": "Work three",
                },
                {
                    "project_code": "P1",
                    "month_key": "август-2026",
                    "facility_building": "16160-13",
                    "construction_discipline": "СМР",
                    "responsible_department": "ПТО",
                    "queue": "1 очередь",
                    "check_status": "HOLD",
                    "resolution_status": "CANCELLED",
                    "problem_owner": "Owner A",
                    "owner_name": "Exec A",
                    "subcontractor_coordinator": "Coord A",
                    "constraint_priority": "HIGH",
                    "effective_deadline_status": "CLOSED",
                    "is_deadline_overdue": False,
                    "is_next_control_overdue": False,
                    "boq_code": "BOQ-4",
                    "boq_name": "Work four",
                },
            ]
        )

    def test_resolution_open_filters(self) -> None:
        out = self.mod.apply_filters(
            self._sample(), **_base_kwargs(resolution_status="OPEN")
        )
        self.assertEqual(list(out["boq_code"]), ["BOQ-1"])

    def test_resolution_resolved_filters(self) -> None:
        out = self.mod.apply_filters(
            self._sample(), **_base_kwargs(resolution_status="RESOLVED")
        )
        self.assertEqual(list(out["boq_code"]), ["BOQ-3"])

    def test_open_mode_only_open(self) -> None:
        out = self.mod.apply_filters(
            self._sample(), **_base_kwargs(open_mode=self.mod.OPEN_ONLY)
        )
        self.assertEqual(set(out["boq_code"]), {"BOQ-1", "BOQ-2"})

    def test_open_mode_all_keeps_closed(self) -> None:
        out = self.mod.apply_filters(
            self._sample(), **_base_kwargs(open_mode=self.mod.MODE_ALL)
        )
        self.assertEqual(len(out), 4)

    def test_resolution_stacks_with_open_mode(self) -> None:
        out = self.mod.apply_filters(
            self._sample(),
            **_base_kwargs(
                open_mode=self.mod.OPEN_ONLY,
                resolution_status="IN_PROGRESS",
            ),
        )
        self.assertEqual(list(out["boq_code"]), ["BOQ-2"])

    def test_problem_owner_filter(self) -> None:
        out = self.mod.apply_filters(
            self._sample(), **_base_kwargs(problem_owner="Owner B")
        )
        self.assertEqual(list(out["boq_code"]), ["BOQ-2"])

    def test_executor_filter(self) -> None:
        out = self.mod.apply_filters(
            self._sample(), **_base_kwargs(owner_name="Exec A")
        )
        self.assertEqual(set(out["boq_code"]), {"BOQ-1", "BOQ-3", "BOQ-4"})

    def test_coordinator_filter(self) -> None:
        out = self.mod.apply_filters(
            self._sample(), **_base_kwargs(subcontractor_coordinator="Coord A")
        )
        self.assertEqual(set(out["boq_code"]), {"BOQ-1", "BOQ-3", "BOQ-4"})

    def test_queue_filter(self) -> None:
        out = self.mod.apply_filters(
            self._sample(), **_base_kwargs(queue="2 очередь")
        )
        self.assertEqual(list(out["boq_code"]), ["BOQ-2"])

    def test_owner_options_from_scope_exclude_empty(self) -> None:
        scoped = self._sample()
        owners = [self.mod.ALL] + self.mod.unique_sorted(scoped["problem_owner"])
        self.assertIn("Owner A", owners)
        self.assertIn("Owner B", owners)
        self.assertNotIn("", owners)
        coordinators = [self.mod.ALL] + self.mod.unique_sorted(
            scoped["subcontractor_coordinator"]
        )
        self.assertEqual(coordinators, [self.mod.ALL, "Coord A"])


if __name__ == "__main__":
    unittest.main()
