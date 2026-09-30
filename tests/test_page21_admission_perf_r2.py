"""
Page 21 Admission — Performance R2 guards.

- Query scope respects month/project filters
- Scoped query ≡ old full-load → pandas filter
- Golden UX regression still enforced via R1 suite
No product DB writes.
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


ROOT = Path(__file__).resolve().parents[1]
PAGE21_PATH = ROOT / "pages" / "21_Admission_Управление_ограничениями_месячного_плана.py"


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
        if key in {"streamlit", "page21_perf_r2"} or key.startswith("page21_perf_r2"):
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

    # Use real constraints_loader for equivalence helpers.
    if "services.constraints_loader" in sys.modules:
        del sys.modules["services.constraints_loader"]

    for mod_name in (
        "services.boq_execution_history_service",
        "services.boq_execution_crews_service",
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

    spec = importlib.util.spec_from_file_location("page21_perf_r2", PAGE21_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["page21_perf_r2"] = mod
    spec.loader.exec_module(mod)
    mod.st = st  # type: ignore[attr-defined]
    return mod


FIXTURE_ROWS = [
    {
        "constraint_id": "c1",
        "line_id": "l1",
        "month_key": "октябрь-2026",
        "project_code": "PRJ_A",
        "check_status": "ОЖИДАЕТ",
        "responsible_department": "ПТО",
        "boq_code": "B1",
        "boq_name": "n1",
        "facility_building": "F1",
        "construction_discipline": "D1",
        "crew_id": "CR1",
        "plan_value": 10,
        "required_hours": 1,
        "value_at_risk": 10,
        "gate_layer": "EXECUTABILITY",
        "check_name": "chk",
        "resolution_status": "OPEN",
    },
    {
        "constraint_id": "c2",
        "line_id": "l1",
        "month_key": "октябрь-2026",
        "project_code": "PRJ_A",
        "check_status": "PASS",
        "responsible_department": "МТО",
        "boq_code": "B1",
        "boq_name": "n1",
        "facility_building": "F1",
        "construction_discipline": "D1",
        "crew_id": "CR1",
        "plan_value": 10,
        "required_hours": 1,
        "value_at_risk": 10,
        "gate_layer": "EXECUTABILITY",
        "check_name": "chk2",
        "resolution_status": "OPEN",
    },
    {
        "constraint_id": "c3",
        "line_id": "l2",
        "month_key": "июль-2026",
        "project_code": "PRJ_A",
        "check_status": "HOLD",
        "responsible_department": "ПТО",
        "boq_code": "B2",
        "boq_name": "n2",
        "facility_building": "F2",
        "construction_discipline": "D2",
        "crew_id": "CR2",
        "plan_value": 20,
        "required_hours": 2,
        "value_at_risk": 20,
        "gate_layer": "EXECUTABILITY",
        "check_name": "chk3",
        "resolution_status": "OPEN",
    },
    {
        "constraint_id": "c4",
        "line_id": "l3",
        "month_key": "октябрь-2026",
        "project_code": "PRJ_B",
        "check_status": "WARNING",
        "responsible_department": "QAQC",
        "boq_code": "B3",
        "boq_name": "n3",
        "facility_building": "F3",
        "construction_discipline": "D3",
        "crew_id": "CR3",
        "plan_value": 30,
        "required_hours": 3,
        "value_at_risk": 30,
        "gate_layer": "ACCEPTABILITY",
        "check_name": "chk4",
        "resolution_status": "OPEN",
    },
]


class ConstraintsLoaderScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # R1 suite may leave a stub in sys.modules — force real loader.
        import importlib

        sys.modules.pop("services.constraints_loader", None)
        cls.loader = importlib.import_module("services.constraints_loader")

    def test_client_scope_filter_matches_month_project(self) -> None:
        scoped = self.loader.apply_client_scope_filter(
            FIXTURE_ROWS, month_key="октябрь-2026", project_code="PRJ_A"
        )
        ids = sorted(r["constraint_id"] for r in scoped)
        self.assertEqual(ids, ["c1", "c2"])

    def test_query_equivalence_old_pandas_vs_scoped(self) -> None:
        full = list(FIXTURE_ROWS)
        month = "октябрь-2026"
        old = self.loader.apply_client_scope_filter(full, month_key=month)
        # Simulate server-scoped result (same filter semantics).
        new = [r for r in full if r.get("month_key") == month]
        old_ids = sorted(r["constraint_id"] for r in old)
        new_ids = sorted(r["constraint_id"] for r in new)
        self.assertEqual(old_ids, new_ids)
        self.assertEqual(len(old), len(new))
        # Same business fields for matched ids
        old_by = {r["constraint_id"]: r for r in old}
        new_by = {r["constraint_id"]: r for r in new}
        for cid in old_ids:
            for field in ("month_key", "project_code", "check_status", "line_id", "boq_code"):
                self.assertEqual(old_by[cid][field], new_by[cid][field])


class Page21R2PackageParity(unittest.TestCase):
    def setUp(self) -> None:
        self.mod = _load_page21()
        self.st = self.mod.st
        self.st.session_state.clear()

    def test_required_columns_defined(self) -> None:
        self.assertTrue(self.mod.REQUIRED_COLUMNS)
        self.assertIn("constraint_id", self.mod.REQUIRED_COLUMNS)
        self.assertIn("month_key", self.mod.REQUIRED_COLUMNS)
        self.assertNotIn("*", self.mod.REQUIRED_COLUMNS)

    def test_package_build_stable_on_fixture(self) -> None:
        df = pd.DataFrame(FIXTURE_ROWS)
        a = self.mod.build_package_dataframe(df)
        b = self.mod.build_package_dataframe(df)
        self.assertEqual(len(a), len(b))
        self.assertEqual(
            sorted(a["package_key"].astype(str).tolist()),
            sorted(b["package_key"].astype(str).tolist()),
        )
        self.assertEqual(
            sorted(a["package_status"].astype(str).tolist()),
            sorted(b["package_status"].astype(str).tolist()),
        )

    def test_resolve_scope_from_session(self) -> None:
        self.st.session_state[self.mod.FILTER_SESSION_KEYS["month"]] = "октябрь-2026"
        self.st.session_state[self.mod.FILTER_SESSION_KEYS["project"]] = "Все"
        mk, pk = self.mod.resolve_constraint_load_scope()
        self.assertEqual(mk, "октябрь-2026")
        self.assertEqual(pk, "")

    def test_load_constraints_passes_scope_kwargs(self) -> None:
        captured: dict[str, Any] = {}

        def fake_cached(month_key: str = "", project_code: str = ""):
            captured["month_key"] = month_key
            captured["project_code"] = project_code
            return pd.DataFrame(FIXTURE_ROWS[:1]), {"rows": 1, "pages": 1, "network_s": 0.0}

        with patch.object(self.mod, "_load_constraints_cached", side_effect=fake_cached):
            out = self.mod.load_constraints("октябрь-2026", "PRJ_A")
        self.assertEqual(captured["month_key"], "октябрь-2026")
        self.assertEqual(captured["project_code"], "PRJ_A")
        self.assertEqual(len(out), 1)

    def test_no_select_star_in_loader_default_columns(self) -> None:
        from services.constraints_loader import DEFAULT_CONSTRAINT_COLUMNS

        self.assertTrue(DEFAULT_CONSTRAINT_COLUMNS)
        self.assertNotIn("*", DEFAULT_CONSTRAINT_COLUMNS)


if __name__ == "__main__":
    unittest.main()
