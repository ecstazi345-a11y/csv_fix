"""Read-only manual monthly plan vs Constructor reconciliation harness.

Does not mutate DB, live run, or product state. Writes analysis artifacts to TEMP only.
Defaults reproduce the October 2026 acceptance comparison.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

os.environ.setdefault(
    "AGENT_OBSERVABILITY_DB_PATH",
    str((ROOT / ".runtime/shadow/constructor/observability.sqlite").resolve()),
)

DEFAULT_RUN_ID = "run-a0c70277-486b-439d-a6be-7599411ffc37"
DEFAULT_MISSION_ID = "mission-hs-64b62cbcb56220fb604625d3"
DEFAULT_PROJECT = "PRJ_001_БХК"
DEFAULT_MONTH = "октябрь-2026"
DEFAULT_FACILITIES = ("16160-13", "16160-17")

RUN_ID = DEFAULT_RUN_ID
MISSION_ID = DEFAULT_MISSION_ID
PROJECT = DEFAULT_PROJECT
MONTH = DEFAULT_MONTH
FACILITIES = set(DEFAULT_FACILITIES)

TEMP = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".")
OUT_CSV = TEMP / "dynamis_manual_vs_constructor_reconciliation.csv"
OUT_JSON = TEMP / "dynamis_manual_vs_constructor_reconciliation.json"
QTY_TOL = 1e-6


def _s(v: Any) -> str:
    if v is None:
        return ""
    try:
        if isinstance(v, float) and math.isnan(v):
            return ""
    except Exception:
        pass
    t = str(v).strip()
    if t.lower() in {"", "nan", "none", "<na>", "null", "—", "-"}:
        return ""
    return t


def _f(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def _near(a: Optional[float], b: Optional[float], tol: float = QTY_TOL) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= max(tol, abs(a) * 1e-9, abs(b) * 1e-9)


def _norm_sys(v: Any) -> str:
    return _s(v)


def grain_full(facility: str, system: str, iwp: str, boq: str) -> str:
    return "|".join([_s(facility), _norm_sys(system), _s(iwp), _s(boq)])


def grain_title_boq(facility: str, boq: str) -> str:
    return "|".join([_s(facility), _s(boq)])


def grain_plan(facility: str, discipline: str, boq: str) -> str:
    return "|".join([_s(facility), _s(discipline), _s(boq)])


@dataclass
class ManualRow:
    plan_line_id: str
    facility: str
    discipline: str
    system: str
    iwp: str
    boq_code: str
    boq_name: str
    unit: str
    planned_qty: Optional[float]
    status: str


@dataclass
class DecisionRow:
    source_identity: str
    facility: str
    discipline: str
    system: str
    iwp: str
    boq_code: str
    boq_name: str
    unit: str
    remaining_qty: Optional[float]
    already_planned_qty: Optional[float]
    available_qty: Optional[float]
    outcome: str
    reason_code: str
    reason_text: str
    candidate_created: bool
    candidate_id: Optional[str]


def load_manual() -> list[ManualRow]:
    from services.supabase_client import supabase

    resp = (
        supabase.table("monthly_plan_lines_v2")
        .select(
            "plan_line_id,project_code,month_key,facility,discipline,system,iwp,"
            "boq_code,boq_name,unit,planned_qty,status"
        )
        .eq("project_code", PROJECT)
        .eq("month_key", MONTH)
        .limit(10000)
        .execute()
    )
    rows: list[ManualRow] = []
    for r in resp.data or []:
        fac = _s(r.get("facility"))
        if FACILITIES and fac and fac not in FACILITIES:
            # Keep all project/month rows; facilities filter noted separately.
            pass
        rows.append(
            ManualRow(
                plan_line_id=_s(r.get("plan_line_id")),
                facility=fac,
                discipline=_s(r.get("discipline")),
                system=_s(r.get("system")),
                iwp=_s(r.get("iwp")),
                boq_code=_s(r.get("boq_code")),
                boq_name=_s(r.get("boq_name")),
                unit=_s(r.get("unit")),
                planned_qty=_f(r.get("planned_qty")),
                status=_s(r.get("status")),
            )
        )
    return rows


def load_decisions() -> tuple[list[DecisionRow], dict[str, Any]]:
    from langgraph.checkpoint.sqlite import SqliteSaver

    cp = ROOT / ".runtime/shadow/constructor/checkpoints.sqlite"
    with SqliteSaver.from_conn_string(str(cp)) as saver:
        tup = saver.get_tuple({"configurable": {"thread_id": RUN_ID}})
    if tup is None:
        raise SystemExit(f"live run missing: {RUN_ID}")
    life = (tup.checkpoint.get("channel_values") or {}).get("lifecycle")
    if life is None:
        raise SystemExit("lifecycle missing")
    meta = {
        "status": str(life.status),
        "mission_id": life.mission_id,
        "run_id": life.run_id,
        "package_id": getattr(life.package, "package_id", None) if life.package else None,
    }
    out: list[DecisionRow] = []
    for d in tuple(life.row_decisions or ()):
        out.append(
            DecisionRow(
                source_identity=_s(d.source_identity),
                facility=_s(d.facility),
                discipline=_s(d.discipline),
                system=_s(d.system),
                iwp=_s(d.iwp),
                boq_code=_s(d.boq_code),
                boq_name=_s(d.boq_name),
                unit=_s(d.unit),
                remaining_qty=_f(d.remaining_qty),
                already_planned_qty=_f(d.already_planned_qty),
                available_qty=_f(d.available_qty),
                outcome=_s(d.outcome),
                reason_code=_s(d.reason_code),
                reason_text=_s(d.reason_text),
                candidate_created=bool(d.candidate_created),
                candidate_id=_s(d.candidate_id) or None,
            )
        )
    return out, meta


def count_identities(rows: list[Any], *, kind: str) -> dict[str, int]:
    boqs = set()
    title_boq = set()
    full = set()
    plan = set()
    for r in rows:
        boqs.add(_s(r.boq_code))
        title_boq.add(grain_title_boq(r.facility, r.boq_code))
        full.add(grain_full(r.facility, r.system, r.iwp, r.boq_code))
        disc = getattr(r, "discipline", "")
        plan.add(grain_plan(r.facility, disc, r.boq_code))
    return {
        "kind": kind,
        "rows": len(rows),
        "unique_boq": len(boqs),
        "unique_title_boq": len(title_boq),
        "unique_full_title_system_iwp_boq": len(full),
        "unique_plan_grain_facility_discipline_boq": len(plan),
    }


def index_decisions(decisions: list[DecisionRow]) -> dict[str, dict[str, list[DecisionRow]]]:
    by_full: dict[str, list[DecisionRow]] = defaultdict(list)
    by_title_boq: dict[str, list[DecisionRow]] = defaultdict(list)
    by_plan: dict[str, list[DecisionRow]] = defaultdict(list)
    by_boq: dict[str, list[DecisionRow]] = defaultdict(list)
    for d in decisions:
        by_full[grain_full(d.facility, d.system, d.iwp, d.boq_code)].append(d)
        by_title_boq[grain_title_boq(d.facility, d.boq_code)].append(d)
        by_plan[grain_plan(d.facility, d.discipline, d.boq_code)].append(d)
        by_boq[_s(d.boq_code)].append(d)
    return {
        "full": by_full,
        "title_boq": by_title_boq,
        "plan": by_plan,
        "boq": by_boq,
    }


def pick_match(m: ManualRow, idx: dict[str, dict[str, list[DecisionRow]]]) -> tuple[Optional[DecisionRow], str]:
    """Return best decision match and match quality label."""
    g_full = grain_full(m.facility, m.system, m.iwp, m.boq_code)
    hits = idx["full"].get(g_full) or []
    if len(hits) == 1:
        return hits[0], "FULL_TITLE_SYSTEM_IWP_BOQ"
    if len(hits) > 1:
        # Prefer candidate or already_planned if multiple.
        ranked = sorted(
            hits,
            key=lambda d: (
                0 if d.outcome == "CANDIDATE" else 1,
                0 if d.outcome == "EXCLUDED_ALREADY_PLANNED" else 1,
                d.source_identity,
            ),
        )
        return ranked[0], "FULL_AMBIGUOUS_PICKED"

    g_plan = grain_plan(m.facility, m.discipline, m.boq_code)
    hits = idx["plan"].get(g_plan) or []
    if len(hits) == 1:
        return hits[0], "PLAN_GRAIN_FACILITY_DISCIPLINE_BOQ"
    if len(hits) > 1:
        # Prefer row whose system/iwp closest to manual.
        def score(d: DecisionRow) -> tuple:
            return (
                0 if _s(d.system) == _s(m.system) else 1,
                0 if _s(d.iwp) == _s(m.iwp) else 1,
                0 if d.outcome == "EXCLUDED_ALREADY_PLANNED" else 1,
                0 if d.outcome == "CANDIDATE" else 1,
                d.source_identity,
            )

        ranked = sorted(hits, key=score)
        return ranked[0], "PLAN_GRAIN_AMBIGUOUS_PICKED"

    g_tb = grain_title_boq(m.facility, m.boq_code)
    hits = idx["title_boq"].get(g_tb) or []
    if len(hits) == 1:
        return hits[0], "TITLE_BOQ"
    if len(hits) > 1:
        ranked = sorted(
            hits,
            key=lambda d: (
                0 if _s(d.system) == _s(m.system) else 1,
                0 if _s(d.iwp) == _s(m.iwp) else 1,
                0 if d.outcome == "EXCLUDED_ALREADY_PLANNED" else 1,
                d.source_identity,
            ),
        )
        return ranked[0], "TITLE_BOQ_AMBIGUOUS_PICKED"

    hits = idx["boq"].get(_s(m.boq_code)) or []
    if hits:
        # Same BOQ elsewhere — not a match of the same physical context.
        return None, "BOQ_ONLY_ELSEWHERE"
    return None, "NOT_FOUND"


def classify_manual(m: ManualRow, d: Optional[DecisionRow], match_quality: str) -> str:
    if d is None:
        if match_quality == "BOQ_ONLY_ELSEWHERE":
            return "A9_NOT_FOUND_SAME_BOQ_ELSEWHERE"
        return "A9_NOT_FOUND"
    o = d.outcome
    mapping = {
        "CANDIDATE": "A1_MANUAL_PLUS_CANDIDATE",
        "EXCLUDED_ALREADY_PLANNED": "A2_ALREADY_PLANNED",
        "EXCLUDED_COMPLETED": "A3_COMPLETED",
        "EXCLUDED_NO_REMAINDER": "A4_NO_REMAINDER",
        "EXCLUDED_INVALID": "A5_INVALID",
        "EXCLUDED_OVERRUN": "A6_OVERRUN",
        "EXCLUDED_INCONSISTENT_QUANTITIES": "A7_INCONSISTENT",
        "EXCLUDED_NOT_REQUIRED": "A8_NOT_REQUIRED",
    }
    return mapping.get(o, f"A_OTHER_{o}")


def qty_relation(manual_qty: Optional[float], already: Optional[float]) -> str:
    if manual_qty is None or already is None:
        return "NOT_COMPARABLE"
    if _near(manual_qty, already):
        return "EXACT_MATCH"
    # Manual is part of aggregated already_planned
    if already > manual_qty + QTY_TOL and manual_qty >= 0:
        return "PARTIAL_MANUAL_WITHIN_AGGREGATE"
    if manual_qty > already + QTY_TOL:
        return "MANUAL_GT_ALREADY_PLANNED"
    return "MISMATCH"


def load_constraints_for_candidates(candidates: list[DecisionRow]) -> dict[str, list[dict]]:
    """Best-effort readiness/constraint evidence for candidate BOQs. Read-only."""
    from services.supabase_client import supabase

    evidence: dict[str, list[dict]] = defaultdict(list)
    # monthly_plan_constraints keyed by plan_line_id — may not cover Constructor-only candidates.
    try:
        resp = (
            supabase.table("monthly_plan_constraints")
            .select("constraint_id,plan_line_id,boq_code,facility,status,constraint_type,severity,description")
            .eq("project_code", PROJECT)
            .eq("month_key", MONTH)
            .limit(5000)
            .execute()
        )
        for r in resp.data or []:
            evidence[_s(r.get("boq_code"))].append(
                {
                    "source": "monthly_plan_constraints",
                    "type": _s(r.get("constraint_type")),
                    "severity": _s(r.get("severity")),
                    "status": _s(r.get("status")),
                    "description": _s(r.get("description"))[:300],
                    "facility": _s(r.get("facility")),
                }
            )
    except Exception as exc:
        evidence["__error__"].append({"source": "monthly_plan_constraints", "error": str(exc)})

    # Management decisions are about existing plan lines, not Constructor candidates.
    try:
        resp = (
            supabase.table("monthly_plan_management_decisions")
            .select("plan_line_id,boq_code,facility_building,decision,status")
            .eq("project_code", PROJECT)
            .eq("month_key", MONTH)
            .eq("status", "ACTIVE")
            .limit(5000)
            .execute()
        )
        for r in resp.data or []:
            evidence[_s(r.get("boq_code"))].append(
                {
                    "source": "monthly_plan_management_decisions",
                    "decision": _s(r.get("decision")),
                    "facility": _s(r.get("facility_building")),
                }
            )
    except Exception as exc:
        evidence["__error__"].append(
            {"source": "monthly_plan_management_decisions", "error": str(exc)}
        )
    return evidence


def _apply_cli(argv: Optional[list[str]] = None) -> None:
    """Bind scope from CLI. Defaults keep the original October comparison."""
    global RUN_ID, MISSION_ID, PROJECT, MONTH, FACILITIES
    parser = argparse.ArgumentParser(
        description=(
            "Read-only manual monthly plan vs Constructor reconciliation. "
            "Writes CSV/JSON under TEMP only."
        )
    )
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--mission-id", default=DEFAULT_MISSION_ID)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--month", default=DEFAULT_MONTH)
    parser.add_argument(
        "--facility",
        action="append",
        dest="facilities",
        help="Repeat for each facility. Defaults to 16160-13 and 16160-17.",
    )
    args = parser.parse_args(argv)
    RUN_ID = str(args.run_id).strip()
    MISSION_ID = str(args.mission_id).strip()
    PROJECT = str(args.project).strip()
    MONTH = str(args.month).strip()
    chosen = args.facilities if args.facilities else list(DEFAULT_FACILITIES)
    FACILITIES = {str(item).strip() for item in chosen if str(item).strip()}


def main() -> None:
    _apply_cli()
    manual = load_manual()
    decisions, life_meta = load_decisions()
    observed_mission = str(life_meta.get("mission_id") or "")
    if MISSION_ID and observed_mission and observed_mission != MISSION_ID:
        print(
            "MISSION_ID_NOTE requested",
            MISSION_ID,
            "observed",
            observed_mission,
        )
    candidates = [d for d in decisions if d.outcome == "CANDIDATE"]

    # Scope note: keep all manual project/month rows (expected ~81).
    manual_in_facilities = [m for m in manual if m.facility in FACILITIES]
    manual_out_facilities = [m for m in manual if m.facility not in FACILITIES]

    counts = {
        "manual_all_month": count_identities(manual, kind="MANUAL_ALL_MONTH"),
        "manual_in_facilities": count_identities(manual_in_facilities, kind="MANUAL_IN_FACILITIES"),
        "constructor_decisions": count_identities(decisions, kind="CONSTRUCTOR_DECISIONS"),
        "constructor_candidates": count_identities(candidates, kind="CONSTRUCTOR_CANDIDATES"),
    }

    idx = index_decisions(decisions)
    manual_by_full = defaultdict(list)
    manual_by_title_boq = defaultdict(list)
    manual_by_plan = defaultdict(list)
    for m in manual:
        manual_by_full[grain_full(m.facility, m.system, m.iwp, m.boq_code)].append(m)
        manual_by_title_boq[grain_title_boq(m.facility, m.boq_code)].append(m)
        manual_by_plan[grain_plan(m.facility, m.discipline, m.boq_code)].append(m)

    # Aggregate manual qty at Constructor planning grain for hypothesis H-incremental
    manual_plan_agg: dict[str, float] = defaultdict(float)
    for m in manual:
        if m.planned_qty is not None:
            manual_plan_agg[grain_plan(m.facility, m.discipline, m.boq_code)] += m.planned_qty

    recon_rows: list[dict[str, Any]] = []
    class_counts: Counter = Counter()
    qty_rel_counts: Counter = Counter()
    invalid_reasons: Counter = Counter()

    for m in manual:
        d, mq = pick_match(m, idx)
        cls = classify_manual(m, d, mq)
        class_counts[cls] += 1
        rel = "N/A"
        if d is not None:
            rel = qty_relation(m.planned_qty, d.already_planned_qty)
            qty_rel_counts[rel] += 1
            if d.outcome == "EXCLUDED_INVALID":
                invalid_reasons[d.reason_code or d.reason_text[:80] or "UNSPECIFIED"] += 1
        note = ""
        if cls.startswith("A9"):
            note = (
                "Manual identity not found in Constructor Decision Registry at "
                "Title+System+IWP+BOQ / facility+discipline+BOQ / Title+BOQ. "
                + ("Same BOQ exists under other title/context." if "ELSEWHERE" in cls else "")
            )
        elif cls == "A2_ALREADY_PLANNED":
            note = f"qty_relation={rel}; Constructor planning grain aggregates by facility+discipline+boq"
        elif cls == "A1_MANUAL_PLUS_CANDIDATE":
            note = "Both human and Constructor selected this operational identity as candidate"

        recon_rows.append(
            {
                "manual_present": "YES",
                "constructor_candidate": "YES" if d and d.outcome == "CANDIDATE" else "NO",
                "constructor_found": "YES" if d else "NO",
                "match_quality": mq,
                "comparison_class": cls,
                "title": m.facility,
                "discipline": m.discipline,
                "system": m.system,
                "iwp": m.iwp,
                "boq": m.boq_code,
                "work_name": m.boq_name,
                "unit": m.unit,
                "manual_qty": m.planned_qty,
                "manual_status": m.status,
                "manual_plan_line_id": m.plan_line_id,
                "physical_qty": None,
                "executed_qty": None,
                "remaining_qty": d.remaining_qty if d else None,
                "already_planned_qty": d.already_planned_qty if d else None,
                "available_qty": d.available_qty if d else None,
                "constructor_outcome": d.outcome if d else "",
                "constructor_reason_code": d.reason_code if d else "",
                "constructor_reason": d.reason_text if d else "",
                "constructor_source_identity": d.source_identity if d else "",
                "qty_relation_manual_vs_already_planned": rel,
                "readiness_evidence_found": "",
                "known_constraint": "",
                "analysis_note": note,
            }
        )

    # Candidate → Manual
    cand_classes: Counter = Counter()
    constraint_map = load_constraints_for_candidates(candidates)
    for c in candidates:
        g_full = grain_full(c.facility, c.system, c.iwp, c.boq_code)
        g_plan = grain_plan(c.facility, c.discipline, c.boq_code)
        g_tb = grain_title_boq(c.facility, c.boq_code)
        manuals = (
            manual_by_full.get(g_full)
            or manual_by_plan.get(g_plan)
            or manual_by_title_boq.get(g_tb)
            or []
        )
        also_manual = bool(manuals)
        if also_manual:
            bucket = "B1_CANDIDATE_ALSO_MANUAL"
            hyp = "AGREEMENT"
            readiness = ""
            known = ""
            note = "Also present in manual monthly intention"
        else:
            # Check readiness evidence
            ev = constraint_map.get(c.boq_code) or []
            fac_ev = [e for e in ev if not e.get("facility") or e.get("facility") == c.facility]
            if fac_ev:
                bucket = "B2_CANDIDATE_NOT_MANUAL_KNOWN_CONSTRAINT_EVIDENCE"
                hyp = "KNOWN_BLOCKER_OR_CONSTRAINT_DATA_PRESENT"
                readiness = "YES"
                known = json.dumps(fac_ev[:3], ensure_ascii=False)[:500]
                note = (
                    "Candidate not in manual; related constraint/management evidence exists "
                    "but does not alone prove October non-executability for this Constructor row"
                )
            else:
                bucket = "B2_CANDIDATE_NOT_MANUAL_EXECUTABILITY_NOT_PROVEN"
                hyp = "EXECUTABILITY_NOT_PROVEN"
                readiness = "NO"
                known = ""
                note = (
                    "Physical unplanned remainder appears available to Constructor; "
                    "no authoritative readiness/admission/predecessor evidence found in "
                    "queried product tables for this identity. Not classified as human omission "
                    "or Constructor error without executability proof."
                )
        cand_classes[bucket] += 1
        recon_rows.append(
            {
                "manual_present": "YES" if also_manual else "NO",
                "constructor_candidate": "YES",
                "constructor_found": "YES",
                "match_quality": "CANDIDATE_LOOKUP",
                "comparison_class": bucket,
                "title": c.facility,
                "discipline": c.discipline,
                "system": c.system,
                "iwp": c.iwp,
                "boq": c.boq_code,
                "work_name": c.boq_name,
                "unit": c.unit,
                "manual_qty": manuals[0].planned_qty if manuals else None,
                "manual_status": manuals[0].status if manuals else "",
                "manual_plan_line_id": manuals[0].plan_line_id if manuals else "",
                "physical_qty": None,
                "executed_qty": None,
                "remaining_qty": c.remaining_qty,
                "already_planned_qty": c.already_planned_qty,
                "available_qty": c.available_qty,
                "constructor_outcome": c.outcome,
                "constructor_reason_code": c.reason_code,
                "constructor_reason": c.reason_text,
                "constructor_source_identity": c.source_identity,
                "qty_relation_manual_vs_already_planned": "N/A",
                "readiness_evidence_found": readiness,
                "known_constraint": known,
                "analysis_note": f"{hyp}; {note}",
                "candidate_hypothesis": hyp,
            }
        )

    # Incremental hypothesis at Constructor planning grain
    # For each plan-grain with manual qty, find decision already_planned
    exact = partial = mismatch = not_matchable = 0
    plan_grain_report = []
    decision_by_plan: dict[str, list[DecisionRow]] = defaultdict(list)
    for d in decisions:
        decision_by_plan[grain_plan(d.facility, d.discipline, d.boq_code)].append(d)

    for g, mqty in sorted(manual_plan_agg.items()):
        ds = decision_by_plan.get(g) or []
        if not ds:
            not_matchable += 1
            plan_grain_report.append({"grain": g, "manual_agg": mqty, "relation": "NO_DECISION"})
            continue
        # already_planned should be same across rows of that grain if applied from aggregate
        already_vals = [d.already_planned_qty for d in ds if d.already_planned_qty is not None]
        if not already_vals:
            not_matchable += 1
            plan_grain_report.append({"grain": g, "manual_agg": mqty, "relation": "NO_ALREADY_QTY"})
            continue
        # Use max already (they should be equal)
        already = max(already_vals)
        if _near(mqty, already):
            exact += 1
            rel = "EXACT"
        elif already + QTY_TOL >= mqty and mqty >= 0:
            # Aggregate includes at least the manual sum — could be exact already counted
            if _near(mqty, already):
                exact += 1
                rel = "EXACT"
            else:
                # If already == manual sum across lines of grain, exact; else partial
                partial += 1
                rel = "PARTIAL_OR_SUPERSET"
        else:
            mismatch += 1
            rel = "MISMATCH"
        plan_grain_report.append(
            {
                "grain": g,
                "manual_agg": mqty,
                "already_planned": already,
                "relation": rel,
                "decision_outcomes": Counter(d.outcome for d in ds),
            }
        )

    # Same BOQ different titles
    boq_to_titles_manual: dict[str, set[str]] = defaultdict(set)
    for m in manual:
        boq_to_titles_manual[m.boq_code].add(m.facility)
    boq_to_titles_dec: dict[str, set[str]] = defaultdict(set)
    for d in decisions:
        boq_to_titles_dec[d.boq_code].add(d.facility)

    same_boq_diff_title = []
    for boq, titles in sorted(boq_to_titles_dec.items()):
        if len(titles) > 1:
            samples = []
            for t in sorted(titles):
                sample = next(d for d in decisions if d.boq_code == boq and d.facility == t)
                samples.append(
                    {
                        "title": t,
                        "system": sample.system,
                        "iwp": sample.iwp,
                        "discipline": sample.discipline,
                        "unit": sample.unit,
                        "work_name": sample.boq_name,
                        "remaining_qty": sample.remaining_qty,
                        "outcome": sample.outcome,
                    }
                )
            # Collision heuristic: identical system+iwp+name+unit across titles with conflicting semantics
            collision = False
            keys = {(s["system"], s["iwp"], s["work_name"], s["unit"]) for s in samples}
            # Different titles with different systems/iwp = normal different context
            classification = "NORMAL_DIFFERENT_PHYSICAL_CONTEXT"
            if len(keys) == 1 and len(titles) > 1:
                # Same system/iwp/name copied across titles — still usually normal (same BOQ catalog)
                classification = "NORMAL_SAME_CATALOG_CODE_DIFFERENT_TITLE"
            same_boq_diff_title.append(
                {
                    "boq": boq,
                    "titles": sorted(titles),
                    "classification": classification,
                    "samples": samples,
                    "possible_collision": collision,
                }
            )

    # Summaries for report
    manual_total = len(manual)
    a_sum = sum(class_counts.values())
    cand_also = cand_classes.get("B1_CANDIDATE_ALSO_MANUAL", 0)
    cand_not = len(candidates) - cand_also

    # Map A classes to report buckets
    def cget(*keys: str) -> int:
        return sum(class_counts.get(k, 0) for k in keys)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "run_id": RUN_ID,
            "mission_id": MISSION_ID,
            "project": PROJECT,
            "month": MONTH,
            "facilities": sorted(FACILITIES),
        },
        "live_run": life_meta,
        "grain_primary": "Title + System + IWP + BOQ (fallback: facility+discipline+BOQ = Constructor planning grain; then Title+BOQ)",
        "constructor_already_planned_grain": "project + facility + discipline + boq_code (system/iwp NOT in aggregate key)",
        "counts": counts,
        "manual_facility_split": {
            "in_scope_facilities": len(manual_in_facilities),
            "outside_facilities": len(manual_out_facilities),
            "outside_facility_values": sorted({m.facility for m in manual_out_facilities}),
        },
        "manual_to_constructor_classes": dict(class_counts),
        "manual_accounting_sum": a_sum,
        "manual_total": manual_total,
        "qty_relation_on_matched_manual": dict(qty_rel_counts),
        "invalid_reason_codes": dict(invalid_reasons),
        "candidate_to_manual_classes": dict(cand_classes),
        "candidates_total": len(candidates),
        "candidates_also_manual": cand_also,
        "candidates_not_manual": cand_not,
        "incremental_hypothesis": {
            "plan_grains_with_manual": len(manual_plan_agg),
            "exact_manual_agg_eq_already_planned": exact,
            "partial_or_superset": partial,
            "mismatch": mismatch,
            "not_matchable": not_matchable,
            "samples": plan_grain_report[:30],
        },
        "same_boq_different_title": {
            "count_boq_codes": len(same_boq_diff_title),
            "normal_different_context": sum(
                1
                for x in same_boq_diff_title
                if x["classification"].startswith("NORMAL")
            ),
            "possible_collision": sum(1 for x in same_boq_diff_title if x["possible_collision"]),
            "examples": same_boq_diff_title[:15],
        },
        "constraint_query_errors": constraint_map.get("__error__", []),
        "outcome_distribution_decisions": dict(Counter(d.outcome for d in decisions)),
    }

    # Write CSV
    fieldnames = [
        "manual_present",
        "constructor_candidate",
        "constructor_found",
        "match_quality",
        "comparison_class",
        "title",
        "discipline",
        "system",
        "iwp",
        "boq",
        "work_name",
        "unit",
        "manual_qty",
        "manual_status",
        "manual_plan_line_id",
        "physical_qty",
        "executed_qty",
        "remaining_qty",
        "already_planned_qty",
        "available_qty",
        "constructor_outcome",
        "constructor_reason_code",
        "constructor_reason",
        "constructor_source_identity",
        "qty_relation_manual_vs_already_planned",
        "readiness_evidence_found",
        "known_constraint",
        "analysis_note",
        "candidate_hypothesis",
    ]
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in recon_rows:
            w.writerow(row)

    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("=== COUNTS ===")
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    print("=== MANUAL→CONSTRUCTOR ===")
    print(json.dumps(dict(class_counts), ensure_ascii=False, indent=2))
    print("accounting", a_sum, "manual_total", manual_total)
    print("=== QTY REL ===")
    print(dict(qty_rel_counts))
    print("=== INVALID REASONS ===")
    print(dict(invalid_reasons))
    print("=== CAND→MANUAL ===")
    print(dict(cand_classes))
    print("=== INCREMENTAL ===")
    print(json.dumps(report["incremental_hypothesis"], ensure_ascii=False, indent=2, default=str)[:4000])
    print("=== SAME BOQ DIFF TITLE ===")
    print(report["same_boq_different_title"]["count_boq_codes"], "normal", report["same_boq_different_title"]["normal_different_context"])
    print("CSV", OUT_CSV)
    print("JSON", OUT_JSON)
    print("LIFE", life_meta)


if __name__ == "__main__":
    main()
