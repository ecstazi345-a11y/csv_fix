"""
Regression checks for Performance Optimization Release 1 (pages 21/23).
No Streamlit UI. Stub streamlit. Read-only against Supabase.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
os.environ.setdefault("PERF_AUDIT", "0")

from services.constraints_loader import fetch_all_constraints  # noqa: E402
from services.supabase_client import supabase  # noqa: E402

VIEW_DASHBOARD_V2 = "monthly_plan_constraints_dashboard_v2"
TABLE_V2 = "monthly_plan_lines_v2"
TABLE_REVIEW_QUEUE = "monthly_plan_review_queue"


def _stub_streamlit() -> ModuleType:
    class _CachedFunc:
        def __init__(self, func: Callable):
            self._func = func
            self._store: Dict[Any, Any] = {}

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            key = (
                id(self._func),
                tuple(id(a) if isinstance(a, pd.DataFrame) else a for a in args),
                tuple(
                    sorted(
                        (k, id(v) if isinstance(v, pd.DataFrame) else v)
                        for k, v in kwargs.items()
                    )
                ),
            )
            if key not in self._store:
                self._store[key] = self._func(*args, **kwargs)
            return self._store[key]

        def clear(self) -> None:
            self._store.clear()

    class _CacheData:
        def __call__(self, func: Callable | None = None, **kwargs: Any):
            if func is not None:
                return _CachedFunc(func)

            def decorator(f: Callable) -> _CachedFunc:
                return _CachedFunc(f)

            return decorator

        def clear(self) -> None:
            pass

    st = ModuleType("streamlit")
    st.cache_data = _CacheData()
    st.set_page_config = lambda **_: None
    st.session_state = {
        "wr2_passport_composition": {},
        "wr2_passport_audit": [],
        "wr2_passport_is_draft": False,
        "wr2_passport_is_formed": False,
        "wr2_deferred_decisions": {},
        "wr2_excluded_decisions": {},
    }
    st.error = print
    st.warning = print
    st.info = print
    return st


def _load_page_module(filename: str, mod_name: str) -> ModuleType:
    if "streamlit" not in sys.modules:
        sys.modules["streamlit"] = _stub_streamlit()
    path = ROOT / "pages" / filename
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def outcome_counts(board: pd.DataFrame) -> Dict[str, int]:
    if board.empty or "outcome" not in board.columns:
        return {}
    return {str(k): int(v) for k, v in board["outcome"].value_counts().to_dict().items()}


def main() -> None:
    checks: list[dict[str, Any]] = []

    mod21 = _load_page_module(
        "21_Admission_Управление_ограничениями_месячного_плана.py",
        "reg_page_21",
    )
    mod23 = _load_page_module(
        "23_Admission_War_Room_ограничений.py",
        "reg_page_23",
    )

    rows = fetch_all_constraints(supabase, VIEW_DASHBOARD_V2)
    constraints_df = mod21.enrich_dataframe(pd.DataFrame(rows))
    v2_df = pd.DataFrame(
        supabase.table(TABLE_V2).select("*").limit(10000).execute().data or []
    )
    queue_df = pd.DataFrame(
        supabase.table(TABLE_REVIEW_QUEUE).select("*").limit(10000).execute().data or []
    )

    # 1-4: read model determinism + outcomes
    board1 = mod23.build_war_room_read_model(constraints_df, v2_df, queue_df)
    board2 = mod23.build_war_room_read_model(constraints_df, v2_df, queue_df)
    checks.append(
        {
            "name": "23 same row count on cold+warm cache",
            "ok": len(board1) == len(board2) and len(board1) > 0,
            "detail": {"rows": len(board1)},
        }
    )
    boq1 = sorted(board1["boq_code"].astype(str).tolist()) if "boq_code" in board1 else []
    boq2 = sorted(board2["boq_code"].astype(str).tolist()) if "boq_code" in board2 else []
    checks.append(
        {
            "name": "23 BOQ codes stable across cache hit",
            "ok": boq1 == boq2,
            "detail": {"boq_count": len(boq1)},
        }
    )
    oc1 = outcome_counts(board1)
    oc2 = outcome_counts(board2)
    checks.append(
        {
            "name": "23 admission outcomes stable",
            "ok": oc1 == oc2,
            "detail": oc1,
        }
    )

    # Registry without re-fetch
    reg = mod23.wr2_build_unified_registry_df(board1, constraints_df)
    checks.append(
        {
            "name": "23 registry rows == board rows",
            "ok": len(reg) == len(board1),
            "detail": {"registry": len(reg), "board": len(board1)},
        }
    )

    # 5-7: composition / include rules / override payload helpers exist & behave
    ok_row = board1[board1["outcome"].astype(str).str.contains("OK|ДОПУЩЕН|ADMITTED", case=False, na=False)]
    if ok_row.empty:
        # fallback: any row with passport_include True
        if "passport_include" in board1.columns:
            ok_row = board1[board1["passport_include"] == True]  # noqa: E712
    sample = board1.iloc[0]
    if not ok_row.empty:
        sample = ok_row.iloc[0]

    # Auto composition sync should not crash
    before_comp = dict(sys.modules["streamlit"].session_state.get("wr2_passport_composition", {}))
    mod23.wr2_sync_auto_admitted_composition(board1.head(min(20, len(board1))))
    after_comp = sys.modules["streamlit"].session_state.get("wr2_passport_composition", {})
    checks.append(
        {
            "name": "23 composition sync runs (session composition retained/updated)",
            "ok": isinstance(after_comp, dict),
            "detail": {
                "before_keys": len(before_comp),
                "after_keys": len(after_comp),
            },
        }
    )

    # Override / include helpers
    for fname in (
        "wr2_build_passport_override_payload",
        "wr2_writer_needs_override_for_row",
        "wr2_row_in_passport_inclusion",
        "passport_includes_outcome",
    ):
        checks.append(
            {
                "name": f"23 helper present: {fname}",
                "ok": hasattr(mod23, fname),
                "detail": {},
            }
        )

    if hasattr(mod23, "wr2_row_in_passport_inclusion"):
        # Should not raise; result is bool
        try:
            inc = bool(mod23.wr2_row_in_passport_inclusion(sample, allow_risk=True))
            inc2 = bool(mod23.wr2_row_in_passport_inclusion(sample, allow_risk=False))
            checks.append(
                {
                    "name": "23 INCLUDE / INCLUDE_RISK helpers callable",
                    "ok": True,
                    "detail": {"allow_risk_true": inc, "allow_risk_false": inc2},
                }
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                {
                    "name": "23 INCLUDE / INCLUDE_RISK helpers callable",
                    "ok": False,
                    "detail": {"error": str(exc)},
                }
            )

    if hasattr(mod23, "wr2_build_passport_override_payload"):
        try:
            payload = mod23.wr2_build_passport_override_payload(
                board1.head(min(5, len(board1))),
                "regression_test",
                allow_risk=True,
            )
            checks.append(
                {
                    "name": "23 passport override payload builds",
                    "ok": isinstance(payload, dict),
                    "detail": {
                        "type": type(payload).__name__,
                        "size": len(payload),
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                {
                    "name": "23 passport override payload builds",
                    "ok": False,
                    "detail": {"error": str(exc)},
                }
            )

    # Project/month isolation: filtered board only contains selected keys
    if not board1.empty and "project_code" in board1.columns and "month_key" in board1.columns:
        project = str(board1.iloc[0]["project_code"])
        month = str(board1.iloc[0]["month_key"])
        filtered = mod23.apply_war_room_plan_filters(
            board1,
            project=project,
            month=month,
            queue="Все",
            title="Все",
            discipline="Все",
            department="Все",
            outcome="Все",
            check_status="Все",
            overdue_only=False,
            search_boq="",
        )
        other_proj = (
            filtered["project_code"].astype(str) != project
        ).any() if not filtered.empty else False
        other_month = (
            filtered["month_key"].astype(str) != month
        ).any() if not filtered.empty else False
        checks.append(
            {
                "name": "23 project/month filter isolation",
                "ok": (not other_proj) and (not other_month) and len(filtered) > 0,
                "detail": {
                    "project": project,
                    "month": month,
                    "filtered_rows": len(filtered),
                },
            }
        )

    # 8: page 21 packages/checks
    packages = mod21.build_package_dataframe(constraints_df)
    checks.append(
        {
            "name": "21 package dataframe built",
            "ok": not packages.empty,
            "detail": {"packages": len(packages), "constraints": len(constraints_df)},
        }
    )
    line_ids = tuple(
        mod21.safe_str(x)
        for x in packages.get("line_id", pd.Series(dtype=str)).tolist()
        if mod21.safe_str(x)
    )
    v2_chunked = mod21.load_v2_plan_lines_for_constraints(line_ids)
    enriched_pkg = mod21.enrich_packages_with_v2_lines(packages, v2_chunked)
    checks.append(
        {
            "name": "21 v2 single-select enrich keeps package count",
            "ok": len(enriched_pkg) == len(packages),
            "detail": {
                "packages": len(packages),
                "v2_rows": len(v2_chunked),
                "enriched": len(enriched_pkg),
            },
        }
    )

    # 9: cache invalidation updates data (clear forces rebuild)
    board_cached = mod23.build_war_room_read_model(constraints_df, v2_df, queue_df)
    mod23.clear_war_room_data_caches()
    # After clear, calling load_* would refetch; read model cache cleared
    board_after_clear = mod23.build_war_room_read_model(constraints_df, v2_df, queue_df)
    checks.append(
        {
            "name": "23 clear_war_room_data_caches rebuilds equal read model",
            "ok": len(board_cached) == len(board_after_clear)
            and outcome_counts(board_cached) == outcome_counts(board_after_clear),
            "detail": {"rows": len(board_after_clear)},
        }
    )

    # Ensure no global clear left in source
    src23 = (ROOT / "pages" / "23_Admission_War_Room_ограничений.py").read_text(
        encoding="utf-8"
    )
    src21 = (
        ROOT / "pages" / "21_Admission_Управление_ограничениями_месячного_плана.py"
    ).read_text(encoding="utf-8")
    checks.append(
        {
            "name": "no st.cache_data.clear() on page 23",
            "ok": "st.cache_data.clear()" not in src23,
            "detail": {},
        }
    )
    checks.append(
        {
            "name": "no st.cache_data.clear() on page 21",
            "ok": "st.cache_data.clear()" not in src21,
            "detail": {},
        }
    )
    checks.append(
        {
            "name": "21 uses clear_admission_constraint_caches after decisions",
            "ok": "clear_admission_constraint_caches()" in src21,
            "detail": {},
        }
    )

    failed = [c for c in checks if not c["ok"]]
    report = {
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "checks": checks,
    }
    out = ROOT / "_tmp_perf_regression_result.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
