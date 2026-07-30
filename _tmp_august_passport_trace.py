"""Read-only trace for BOQ codes missing from August 2026 passport. No writes."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_KEY")
client = create_client(url, key)

MONTH = "август-2026"
BOQS = ["1500-04-01-01", "1500-05-02-07"]


def _stub_streamlit() -> ModuleType:
    class _CachedFunc:
        def __init__(self, func: Callable):
            self._func = func

        def __call__(self, *args: Any, **kwargs: Any) -> Any:
            return self._func(*args, **kwargs)

        def clear(self) -> None:
            pass

    class _CacheData:
        def __call__(self, func: Callable | None = None, **kwargs: Any):
            if func is not None:
                return _CachedFunc(func)
            return lambda f: _CachedFunc(f)

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
    return st


def load_mod(filename: str, name: str) -> ModuleType:
    if "streamlit" not in sys.modules:
        sys.modules["streamlit"] = _stub_streamlit()
    path = ROOT / "pages" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def fetch_v2(boq: str) -> List[Dict[str, Any]]:
    r = (
        client.table("monthly_plan_lines_v2")
        .select("*")
        .eq("month_key", MONTH)
        .eq("boq_code", boq)
        .execute()
    )
    return r.data or []


def fetch_constraints(line_id: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for table in (
        "monthly_plan_constraints_dashboard_v2",
        "monthly_plan_constraints",
    ):
        try:
            r = (
                client.table(table)
                .select("*")
                .eq("line_id", line_id)
                .execute()
            )
            rows.extend(r.data or [])
        except Exception:  # noqa: BLE001
            continue
    return rows


def fetch_passports(project_code: str) -> List[Dict[str, Any]]:
    r = (
        client.table("monthly_plan_passports")
        .select("*")
        .eq("project_code", project_code)
        .eq("month_key", MONTH)
        .order("approved_at", desc=True)
        .execute()
    )
    return r.data or []


def fetch_passport_lines(passport_id: str) -> List[Dict[str, Any]]:
    r = (
        client.table("monthly_plan_passport_lines")
        .select("*")
        .eq("passport_id", passport_id)
        .execute()
    )
    return r.data or []


def writer_dry_run(
    mps,
    source_row: Dict[str, Any],
    constraints: List[Dict[str, Any]],
    *,
    has_override: bool,
    in_inclusion_ids: bool,
) -> Dict[str, Any]:
    """Simulate create_monthly_passport loop + War Room inclusion patch."""
    line_id = str(source_row.get("line_id") or "")
    counts = mps._count_constraints(constraints)
    override = mps._read_override_from_queue(source_row)
    if has_override:
        override["management_override"] = True
        override["override_reason"] = override.get("override_reason") or "dry-run"
    admission = mps._resolve_admission_status(counts, override["management_override"])
    # War Room patch (wr2_create_monthly_passport_with_overrides)
    if not in_inclusion_ids:
        admission_wr = "BLOCKED"
    elif has_override and admission in ("BLOCKED", "WAITING_CHECKS"):
        admission_wr = "APPROVED_BY_OVERRIDE"
    else:
        admission_wr = admission

    decision = "SKIP"
    reason = ""
    if admission_wr == "BLOCKED":
        decision, reason = "SKIP", "BLOCKED (or not in inclusion_ids)"
    elif admission_wr == "WAITING_CHECKS":
        decision, reason = "SKIP", "WAITING_CHECKS"
    elif admission_wr == "NO_CHECKS":
        decision, reason = "SKIP", "NO_CHECKS"
    elif admission_wr in mps.INCLUDED_STATUSES:
        decision, reason = "KEEP", admission_wr
    else:
        decision, reason = "SKIP", f"status={admission_wr}"

    return {
        "line_id": line_id,
        "boq_code": source_row.get("boq_code"),
        "counts": counts,
        "admission_plain": admission,
        "admission_with_wr_patches": admission_wr,
        "has_override": has_override,
        "in_inclusion_ids": in_inclusion_ids,
        "writer_decision": decision,
        "writer_reason": reason,
    }


def main() -> None:
    from services import monthly_passport_service as mps
    from services.constraints_loader import fetch_all_constraints
    from services.supabase_client import supabase

    mod23 = load_mod("23_Admission_War_Room_ограничений.py", "trace23")

    report: Dict[str, Any] = {"month": MONTH, "boqs": {}, "passports": []}

    v2_all: List[Dict[str, Any]] = []
    project_codes: set[str] = set()
    for boq in BOQS:
        v2_rows = fetch_v2(boq)
        v2_all.extend(v2_rows)
        for r in v2_rows:
            pc = r.get("project_code")
            if pc:
                project_codes.add(str(pc))
        report["boqs"][boq] = {
            "v2_rows": [
                {
                    k: r.get(k)
                    for k in (
                        "plan_line_id",
                        "boq_code",
                        "boq_name",
                        "project_code",
                        "month_key",
                        "status",
                        "line_origin",
                        "sent_to_constraints_at",
                        "created_at",
                        "updated_at",
                        "planned_at",
                    )
                }
                for r in v2_rows
            ],
            "v2_count": len(v2_rows),
            "duplicate_plan_line_ids": len({r.get("plan_line_id") for r in v2_rows})
            != len(v2_rows),
        }

    if not project_codes:
        # try ilike boq name fragment
        for boq in BOQS:
            r = (
                client.table("monthly_plan_lines_v2")
                .select("plan_line_id,boq_code,project_code,month_key,status")
                .eq("month_key", MONTH)
                .ilike("boq_code", f"%{boq.split('-')[-1]}%")
                .limit(20)
                .execute()
            )
            report["boqs"][boq]["fuzzy_v2_search"] = r.data or []

    project_code = sorted(project_codes)[0] if len(project_codes) == 1 else list(project_codes)

    # Passports
    if isinstance(project_code, list):
        for pc in project_code:
            report["passports"].extend(
                [{"project_code": pc, **p} for p in fetch_passports(pc)]
            )
    else:
        passports = fetch_passports(project_code)
        report["passports"] = passports
        for p in passports:
            pid = p.get("passport_id")
            lines = fetch_passport_lines(str(pid))
            p["_lines"] = [
                {
                    k: ln.get(k)
                    for k in (
                        "passport_line_id",
                        "line_id",
                        "boq_code",
                        "boq_name",
                        "admission_status",
                        "management_override",
                        "override_reason",
                    )
                }
                for ln in lines
            ]
            p["_lines_count_actual"] = len(lines)
            for boq in BOQS:
                p[f"_has_{boq}"] = any(
                    str(ln.get("boq_code")) == boq for ln in lines
                )

    # Build board from DB
    constraints_df = pd.DataFrame(
        fetch_all_constraints(supabase, "monthly_plan_constraints_dashboard_v2")
    )
    if not constraints_df.empty and hasattr(mod23, "enrich_dataframe"):
        constraints_df = mod23.enrich_dataframe(constraints_df)
    v2_df = pd.DataFrame(
        client.table("monthly_plan_lines_v2").select("*").limit(10000).execute().data
        or []
    )
    queue_df = pd.DataFrame(
        client.table("monthly_plan_review_queue")
        .select("*")
        .limit(10000)
        .execute()
        .data
        or []
    )
    full_board = mod23.build_war_room_read_model(constraints_df, v2_df, queue_df)

    for boq in BOQS:
        trace = report["boqs"][boq]
        v2_rows = trace.get("v2_rows") or []
        pids = [str(r.get("plan_line_id")) for r in v2_rows if r.get("plan_line_id")]

        board_hits = []
        if not full_board.empty and "boq_code" in full_board.columns:
            hits = full_board[full_board["boq_code"].astype(str) == boq]
            for _, row in hits.iterrows():
                board_hits.append(
                    {
                        "plan_line_id": str(row.get("plan_line_id")),
                        "project_code": str(row.get("project_code")),
                        "month_key": str(row.get("month_key")),
                        "outcome": str(row.get("outcome")),
                        "classic_outcome": str(row.get("classic_outcome")),
                    }
                )
        trace["full_board_hits"] = board_hits

        aug_filtered = []
        if board_hits and not full_board.empty:
            for h in board_hits:
                sub = full_board[
                    (full_board["plan_line_id"].astype(str) == h["plan_line_id"])
                    & (full_board["month_key"].astype(str) == MONTH)
                ]
                if not sub.empty:
                    aug_filtered.append(h)
        trace["august_month_on_board"] = aug_filtered

        constraints_detail = []
        for pid in pids:
            crows = fetch_constraints(pid)
            group = pd.DataFrame(crows) if crows else pd.DataFrame()
            counts = (
                mod23.count_line_constraint_statuses(group)
                if not group.empty
                else {"hold": 0, "fail": 0, "warning": 0, "waiting": 0}
            )
            outcome = (
                mod23.resolve_war_room_line_outcome(counts, group)
                if not group.empty
                else "n/a"
            )
            constraints_detail.append(
                {
                    "plan_line_id": pid,
                    "constraint_rows": len(crows),
                    "check_statuses": [c.get("check_status") for c in crows],
                    "counts": counts,
                    "resolve_war_room_line_outcome": outcome,
                    "wr2_writer_needs_override": (
                        mod23.wr2_writer_needs_override_for_row(
                            full_board[
                                full_board["plan_line_id"].astype(str) == pid
                            ].iloc[0]
                        )
                        if not full_board.empty
                        and pid
                        and (full_board["plan_line_id"].astype(str) == pid).any()
                        else None
                    ),
                    "wr2_line_is_fully_admitted": (
                        mod23.wr2_line_is_fully_admitted(
                            full_board[
                                full_board["plan_line_id"].astype(str) == pid
                            ].iloc[0]
                        )
                        if not full_board.empty
                        and pid
                        and (full_board["plan_line_id"].astype(str) == pid).any()
                        else None
                    ),
                }
            )
        trace["constraints"] = constraints_detail

        # Source loader
        pc = v2_rows[0].get("project_code") if v2_rows else (
            project_code if isinstance(project_code, str) else None
        )
        if pc:
            src_rows, src_err, src_kind = mps.load_passport_source_rows(
                supabase, str(pc), MONTH
            )
            trace["load_passport_source_rows"] = {
                "project_code": pc,
                "source_kind": src_kind,
                "errors": src_err,
                "total_rows": len(src_rows),
                "boq_in_source": [
                    {
                        "line_id": r.get("line_id"),
                        "boq_code": r.get("boq_code"),
                        "source_kind": r.get("source_kind"),
                    }
                    for r in src_rows
                    if str(r.get("boq_code")) == boq
                ],
            }

            existing = mps._fetch_existing_approved_passport(
                client, str(pc), MONTH, None
            )
            trace["existing_approved_passport_id"] = existing
            trace["create_monthly_passport_would"] = (
                "already_exists (no insert, no line writes)"
                if existing
                else "proceed to source load + writer"
            )

            for pid in pids:
                src = next(
                    (r for r in src_rows if str(r.get("line_id")) == pid),
                    None,
                )
                if not src:
                    trace.setdefault("writer_dry_run", []).append(
                        {
                            "plan_line_id": pid,
                            "writer_decision": "SKIP",
                            "writer_reason": "not in load_passport_source_rows (status/month/project?)",
                        }
                    )
                    continue
                crows = fetch_constraints(pid)
                # hypothetical: user included in draft with manual override
                dr_with = writer_dry_run(
                    mps, src, crows, has_override=True, in_inclusion_ids=True
                )
                dr_without = writer_dry_run(
                    mps, src, crows, has_override=False, in_inclusion_ids=True
                )
                trace.setdefault("writer_dry_run", []).append(
                    {
                        "with_override_and_inclusion": dr_with,
                        "without_override": dr_without,
                    }
                )

        # Override payload dry-run (needs session composition — simulate manual INCLUDE)
        if pids and not full_board.empty:
            pid = pids[0]
            row = full_board[full_board["plan_line_id"].astype(str) == pid]
            if not row.empty:
                row_s = row.iloc[0]
                comp = {
                    pid: {
                        "boq_code": boq,
                        "boq_name": trace["v2_rows"][0].get("boq_name") if trace["v2_rows"] else "",
                        "decision": mod23.WR2_MGMT_INCLUDE,
                        "basis": "Тестовое основание сквозного прогона",
                        "responsible": "Тест",
                    }
                }
                sys.modules["streamlit"].session_state[mod23.WR2_SESSION_COMPOSITION] = comp
                sys.modules["streamlit"].session_state[
                    mod23.wr2_mgmt_session_key(pid)
                ] = mod23.WR2_MGMT_INCLUDE
                scoped = row.copy()
                overrides = mod23.wr2_build_passport_override_payload(
                    scoped, "trace_user", allow_risk=True
                )
                gaps = mod23.wr2_passport_draft_coverage_gaps(
                    scoped, overrides, allow_risk=True
                )
                val_errs = mod23.wr2_collect_passport_override_errors(
                    scoped, allow_risk=True
                )
                trace["override_dry_run_simulated_manual_include"] = {
                    "overrides_keys": list(overrides.keys()),
                    "override_for_pid": overrides.get(pid),
                    "coverage_gaps": gaps,
                    "validation_errors": val_errs,
                    "wr2_writer_needs_override": mod23.wr2_writer_needs_override_for_row(
                        row_s
                    ),
                }

    report["project_codes_seen"] = list(project_codes) if project_codes else project_code
    out = ROOT / "_tmp_august_passport_trace.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
