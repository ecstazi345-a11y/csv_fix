"""
Cold server-side performance benchmark (no Streamlit UI).
Run:  $env:PERF_AUDIT='1'; python _tmp_perf_benchmark.py

Measures Supabase + pandas CPU time. Network is included in Supabase timings.
Does NOT measure Streamlit widget render time.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from functools import wraps
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Tuple

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
os.environ.setdefault("PERF_AUDIT", "1")

from services.constraints_loader import fetch_all_constraints  # noqa: E402
from services.perf_audit import perf_audit_enabled  # noqa: E402
from services.supabase_client import supabase  # noqa: E402

VIEW_DASHBOARD_V2 = "monthly_plan_constraints_dashboard_v2"
TABLE_CONSTRAINTS = "monthly_plan_constraints"
TABLE_V2 = "monthly_plan_lines_v2"
TABLE_REVIEW_QUEUE = "monthly_plan_review_queue"


def _stub_streamlit() -> ModuleType:
    """Minimal streamlit stub with working cache_data for cold/warm comparison."""

    class _CachedFunc:
        def __init__(self, func: Callable):
            self._func = func
            self._store: Dict[Any, Any] = {}

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            key = (
                id(self._func),
                tuple(id(a) if isinstance(a, pd.DataFrame) else a for a in args),
                tuple(sorted((k, id(v) if isinstance(v, pd.DataFrame) else v) for k, v in kwargs.items())),
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
    st.session_state = {}
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


def timed(label: str, fn: Callable[[], Any]) -> Tuple[Any, float]:
    t0 = time.perf_counter()
    out = fn()
    dt = time.perf_counter() - t0
    print(f"[BENCH] [{dt:.2f}s] {label}", flush=True)
    return out, dt


def bench_supabase() -> Dict[str, Any]:
    summary: Dict[str, Any] = {"calls": [], "by_table": {}}

    def record(table: str, seconds: float, rows: int, pages: int = 1) -> None:
        summary["calls"].append(
            {"table": table, "seconds": round(seconds, 3), "rows": rows, "pages": pages}
        )
        bucket = summary["by_table"].setdefault(
            table, {"seconds": 0.0, "rows": 0, "requests": 0}
        )
        bucket["seconds"] += seconds
        bucket["rows"] += rows
        bucket["requests"] += pages

    rows_v2_view, dt = timed(
        "fetch_all_constraints (dashboard_v2)",
        lambda: fetch_all_constraints(supabase, VIEW_DASHBOARD_V2),
    )
    record(VIEW_DASHBOARD_V2, dt, len(rows_v2_view), max(1, (len(rows_v2_view) + 999) // 1000))

    v2_rows, dt = timed(
        f"load {TABLE_V2} limit 10000",
        lambda: supabase.table(TABLE_V2).select("*").limit(10000).execute().data or [],
    )
    record(TABLE_V2, dt, len(v2_rows))

    rq_rows, dt = timed(
        f"load {TABLE_REVIEW_QUEUE} limit 10000",
        lambda: supabase.table(TABLE_REVIEW_QUEUE).select("*").limit(10000).execute().data
        or [],
    )
    record(TABLE_REVIEW_QUEUE, dt, len(rq_rows))

    return summary


def bench_pandas(mod21: ModuleType, mod23: ModuleType, constraints_df: pd.DataFrame) -> Dict[str, float]:
    times: Dict[str, float] = {}

    _, times["21 enrich_dataframe"] = timed(
        "21 enrich_dataframe",
        lambda: mod21.enrich_dataframe(constraints_df.copy()),
    )
    enriched = mod21.enrich_dataframe(constraints_df)

    _, times["21 build_package_dataframe"] = timed(
        "21 build_package_dataframe",
        lambda: mod21.build_package_dataframe(enriched),
    )
    packages = mod21.build_package_dataframe(enriched)
    line_ids = tuple(
        mod21.safe_str(x)
        for x in packages.get("line_id", pd.Series(dtype=str)).tolist()
        if mod21.safe_str(x)
    )

    # Clear v2 cache so we measure one cold fetch (combined select).
    if hasattr(mod21.load_v2_plan_lines_for_constraints, "clear"):
        mod21.load_v2_plan_lines_for_constraints.clear()

    _, times["21 load_v2_plan_lines_for_constraints"] = timed(
        "21 load_v2_plan_lines_for_constraints",
        lambda: mod21.load_v2_plan_lines_for_constraints(line_ids),
    )
    v2_chunked = mod21.load_v2_plan_lines_for_constraints(line_ids)

    _, times["21 enrich_packages_with_v2_lines"] = timed(
        "21 enrich_packages_with_v2_lines",
        lambda: mod21.enrich_packages_with_v2_lines(packages, v2_chunked),
    )

    v2_full = pd.DataFrame(
        supabase.table(TABLE_V2).select("*").limit(10000).execute().data or []
    )
    queue_df = pd.DataFrame(
        supabase.table(TABLE_REVIEW_QUEUE).select("*").limit(10000).execute().data or []
    )

    if hasattr(mod23.build_war_room_read_model, "clear"):
        mod23.build_war_room_read_model.clear()

    board, times["23 build_war_room_read_model (cold)"] = timed(
        "23 build_war_room_read_model (cold)",
        lambda: mod23.build_war_room_read_model(enriched, v2_full, queue_df),
    )
    _, times["23 build_war_room_read_model (warm/cache)"] = timed(
        "23 build_war_room_read_model (warm/cache)",
        lambda: mod23.build_war_room_read_model(enriched, v2_full, queue_df),
    )

    _, times["23 wr2_build_unified_registry_df"] = timed(
        "23 wr2_build_unified_registry_df (no re-fetch)",
        lambda: mod23.wr2_build_unified_registry_df(board, enriched),
    )

    return times


def main() -> None:
    print(f"[BENCH] perf_audit_enabled={perf_audit_enabled()}", flush=True)
    before_path = ROOT / "_tmp_perf_benchmark_result.json"
    before = None
    if before_path.exists():
        try:
            before = json.loads(before_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            before = None

    supa = bench_supabase()

    rows = fetch_all_constraints(supabase, VIEW_DASHBOARD_V2)
    constraints_df = pd.DataFrame(rows)
    print(f"[BENCH] constraints rows={len(constraints_df)}", flush=True)

    mod21 = _load_page_module(
        "21_Admission_Управление_ограничениями_месячного_плана.py",
        "bench_page_21",
    )
    mod23 = _load_page_module(
        "23_Admission_War_Room_ограничений.py",
        "bench_page_23",
    )
    pandas_times = bench_pandas(mod21, mod23, constraints_df)

    total_supa = sum(c["seconds"] for c in supa["calls"])
    # Cold page estimate: network + cold read model + registry (no duplicate constraints)
    cold_cpu = (
        pandas_times.get("21 enrich_dataframe", 0)
        + pandas_times.get("23 build_war_room_read_model (cold)", 0)
        + pandas_times.get("23 wr2_build_unified_registry_df", 0)
    )
    warm_cpu = (
        pandas_times.get("23 build_war_room_read_model (warm/cache)", 0)
        + pandas_times.get("23 wr2_build_unified_registry_df", 0)
    )
    grand_cold = total_supa + cold_cpu

    report = {
        "supabase_by_table": {
            k: {kk: round(vv, 3) if isinstance(vv, float) else vv for kk, vv in v.items()}
            for k, v in supa["by_table"].items()
        },
        "supabase_total_seconds": round(total_supa, 3),
        "pandas_seconds": {k: round(v, 3) for k, v in pandas_times.items()},
        "pandas_total_seconds_cold_war_room_path": round(cold_cpu, 3),
        "pandas_total_seconds_warm_war_room_path": round(warm_cpu, 3),
        "estimated_cold_server_seconds": round(grand_cold, 3),
        "estimated_warm_rerun_server_seconds": round(warm_cpu, 3),
        "notes": [
            "Streamlit widget render not measured",
            "21 v2 loader uses 1 select/chunk (fallback to multi if column missing)",
            "wr2_build_unified_registry_df no longer re-fetches constraints",
            "build_war_room_read_model cached via @st.cache_data (stub caches by id)",
        ],
        "before_snapshot": {
            "estimated_cold_server_seconds": (before or {}).get("estimated_cold_server_seconds"),
            "pandas_seconds": (before or {}).get("pandas_seconds"),
            "supabase_total_seconds": (before or {}).get("supabase_total_seconds"),
        }
        if before
        else None,
    }
    out_path = ROOT / "_tmp_perf_benchmark_result.json"
    # Keep previous as before file once
    archive = ROOT / "_tmp_perf_benchmark_result_before.json"
    if before and not archive.exists():
        archive.write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding="utf-8")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[BENCH] wrote {out_path}", flush=True)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
