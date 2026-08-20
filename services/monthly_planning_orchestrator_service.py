"""
MPO-003A — Monthly Planning Orchestrator v0.1

READ-ONLY deterministic runtime over PlanningSnapshot.
No Streamlit, no writes, no LLM, no agent framework.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Optional

from services.monthly_planning_snapshot_service import load_planning_snapshot

STATE_GATHER = "GATHER"
STATE_ANALYZE = "ANALYZE"
STATE_VALIDATE = "VALIDATE"
STATE_HUMAN_DECISION = "HUMAN_DECISION"
STATE_FAILED = "FAILED"

VAL_PASS = "PASS"
VAL_PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
VAL_BLOCKED = "BLOCKED"

REC_NOT_READY = "NOT_READY_DATA_GAPS"
REC_MIXED = "MIXED_CONDITION"
REC_ADMISSION_BLOCKED = "ADMISSION_BLOCKED"
REC_RESOURCE_DEFICIT = "RESOURCE_DEFICIT"
REC_READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
REC_READY = "READY_FOR_HUMAN_DECISION"

ACTION_REVIEW_PLAN = "REVIEW_PLAN"
ACTION_REVIEW_ADMISSION = "REVIEW_ADMISSION"
ACTION_REVIEW_RESOURCE = "REVIEW_RESOURCE_PLAN"
ACTION_FIX_DQ = "FIX_DATA_QUALITY"
ACTION_WAIT_NOT_REQUIRED = "WAIT_NOT_REQUIRED_LAYER"

SEV_INFO = "INFO"
SEV_WARNING = "WARNING"
SEV_BLOCKER = "BLOCKER"

CODE_CAPACITY_MISSING = "CAPACITY_DATA_MISSING"
CODE_RESOURCE_DEFICIT = "RESOURCE_DEFICIT"
CODE_ADMISSION_BLOCKED = "ADMISSION_BLOCKED"
CODE_BOQ_AMBIGUOUS = "scope_remaining_not_joined"
CODE_NOT_REQUIRED_GAP = "not_required_adjustments_not_applied"
CODE_SCOPE_READ_FAILED = "scope_read_failed"
CODE_NO_PLAN_LINES = "no_plan_lines"
CODE_INVALID_MONTH = "month_normalization_issue"
CODE_BLANK_PROJECT = "blank_project_code"
CODE_COMPLETED_STILL_REQUESTED = "completed_boq_still_requested"
CODE_ADMISSION_UNAVAILABLE = "admission_status_unavailable"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none"} else text


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _finding(
    code: str,
    severity: str,
    *,
    count: int = 0,
    plan_line_ids: Optional[list[str]] = None,
    evidence: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "count": int(count),
        "plan_line_ids": list(plan_line_ids or []),
        "evidence": evidence or {},
    }


def _ids_with(lines: list[dict[str, Any]], predicate) -> list[str]:
    out: list[str] = []
    for row in lines:
        if predicate(row):
            pid = _safe_str(row.get("plan_line_id"))
            if pid:
                out.append(pid)
    return out


def _missing_has(row: dict[str, Any], code: str) -> bool:
    return code in _as_list(row.get("missing_data"))


def _make_trace_event(
    stage: str,
    *,
    started_at: str,
    finished_at: str,
    duration_ms: float,
    status: str,
    tool: Optional[str],
    summary: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "status": status,
        "tool": tool,
        "summary": summary or {},
        "error": error,
    }


def _dq_has(issues: list[Any], code: str) -> bool:
    for item in issues:
        if isinstance(item, dict) and item.get("code") == code:
            return True
        if item == code:
            return True
    return False


def _build_gather_result(snapshot: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {
            "ok": False,
            "snapshot_present": False,
            "sources": {
                "labor": "UNKNOWN",
                "approved_capacity": "UNKNOWN",
                "admission": "UNKNOWN",
                "boq_reality": "UNKNOWN",
            },
            "source_trace": None,
            "error": {"code": "SNAPSHOT_MISSING", "message": "PlanningSnapshot was not produced"},
        }

    summary = _as_dict(snapshot.get("summary"))
    lines = _as_list(snapshot.get("plan_lines"))
    dq = _as_dict(snapshot.get("data_quality"))
    issues = _as_list(dq.get("issues"))
    trace = _as_dict(snapshot.get("source_trace"))
    line_count = int(summary.get("plan_line_count") or len(lines) or 0)
    required = summary.get("required_hours_total")
    approved = summary.get("approved_available_hours_total")
    missing_crew = int(summary.get("capacity_data_missing_crew_count") or 0)

    labor = "OK" if line_count > 0 else "EMPTY"

    if approved is None and (required or 0) > 0:
        capacity = "MISSING"
    elif approved is not None:
        capacity = "OK"
    else:
        capacity = "UNKNOWN"

    unavailable = sum(1 for row in lines if _missing_has(row, CODE_ADMISSION_UNAVAILABLE))
    if unavailable and unavailable >= line_count and line_count > 0:
        admission = "EMPTY"
    elif unavailable:
        admission = "PARTIAL"
    elif line_count > 0:
        admission = "OK"
    else:
        admission = "UNKNOWN"

    if trace.get("scope_read_error") or _dq_has(issues, CODE_SCOPE_READ_FAILED):
        boq = "FAILED"
    elif any(_missing_has(row, CODE_BOQ_AMBIGUOUS) for row in lines):
        boq = "PARTIAL"
    elif any(row.get("remaining_qty") is not None for row in lines):
        boq = "OK"
    else:
        boq = "UNKNOWN"

    return {
        "ok": True,
        "snapshot_present": True,
        "sources": {
            "labor": labor,
            "approved_capacity": capacity,
            "admission": admission,
            "boq_reality": boq,
        },
        "source_trace": trace,
        "error": None,
    }


def _analyze_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    summary_in = _as_dict(snapshot.get("summary"))
    lines = _as_list(snapshot.get("plan_lines"))
    dq = _as_dict(snapshot.get("data_quality"))
    issues = _as_list(dq.get("issues"))
    trace = _as_dict(snapshot.get("source_trace"))

    plan_line_count = int(summary_in.get("plan_line_count") or len(lines) or 0)
    required = summary_in.get("required_hours_total")
    approved = summary_in.get("approved_available_hours_total")
    coverage = summary_in.get("resource_coverage")
    gap = summary_in.get("resource_gap_hours")
    blocking = int(summary_in.get("blocking_line_count") or 0)
    missing_crew = int(summary_in.get("capacity_data_missing_crew_count") or 0)

    feas: dict[str, int] = {}
    admission_counts: dict[str, int] = {}
    missing_codes: dict[str, int] = {}
    for row in lines:
        fs = _safe_str(row.get("feasibility_status")) or "UNKNOWN"
        feas[fs] = feas.get(fs, 0) + 1
        adm = _safe_str(row.get("admission_status")) or "UNAVAILABLE"
        admission_counts[adm] = admission_counts.get(adm, 0) + 1
        for code in _as_list(row.get("missing_data")):
            key = _safe_str(code)
            if key:
                missing_codes[key] = missing_codes.get(key, 0) + 1

    summary = {
        "plan_line_count": plan_line_count,
        "required_hours_total": required,
        "approved_available_hours_total": approved,
        "resource_coverage": coverage,
        "resource_gap_hours": gap,
        "blocking_line_count": blocking,
        "capacity_data_missing_crew_count": missing_crew,
        "feasibility_status_counts": feas,
        "admission_status_counts": admission_counts,
        "missing_data_counts": missing_codes,
        "data_quality_issue_count": len(issues),
    }

    findings: list[dict[str, Any]] = []

    if plan_line_count == 0:
        findings.append(_finding(CODE_NO_PLAN_LINES, SEV_BLOCKER, count=0, evidence={"plan_line_count": 0}))

    capacity_missing_ids = _ids_with(
        lines, lambda r: _safe_str(r.get("feasibility_status")) == CODE_CAPACITY_MISSING
    )
    all_demand_missing = (
        (required or 0) > 0
        and approved is None
        and (
            missing_crew > 0
            or (plan_line_count > 0 and len(capacity_missing_ids) == plan_line_count)
        )
    )
    if all_demand_missing:
        findings.append(
            _finding(
                CODE_CAPACITY_MISSING,
                SEV_BLOCKER,
                count=len(capacity_missing_ids) or missing_crew,
                plan_line_ids=capacity_missing_ids,
                evidence={
                    "approved_available_hours_total": None,
                    "required_hours_total": required,
                    "treated_as_zero": False,
                },
            )
        )
    elif missing_crew > 0 and approved is not None:
        findings.append(
            _finding(
                CODE_CAPACITY_MISSING,
                SEV_WARNING,
                count=missing_crew,
                plan_line_ids=capacity_missing_ids,
                evidence={"capacity_data_missing_crew_count": missing_crew},
            )
        )

    confirmed_deficit = (
        approved is not None
        and (required or 0) > 0
        and coverage is not None
        and float(coverage) < 1.0
    )
    if confirmed_deficit:
        deficit_ids = _ids_with(
            lines,
            lambda r: _safe_str(r.get("feasibility_status"))
            in {"RESOURCE_DEFICIT", "PARTIALLY_FEASIBLE"},
        )
        findings.append(
            _finding(
                CODE_RESOURCE_DEFICIT,
                SEV_WARNING,
                count=len(deficit_ids),
                plan_line_ids=deficit_ids,
                evidence={
                    "required_hours_total": required,
                    "approved_available_hours_total": approved,
                    "resource_coverage": coverage,
                    "resource_gap_hours": gap,
                },
            )
        )

    if blocking > 0:
        blocked_ids = _ids_with(lines, lambda r: _safe_str(r.get("admission_status")) == "BLOCKED")
        findings.append(
            _finding(
                CODE_ADMISSION_BLOCKED,
                SEV_WARNING,
                count=blocking,
                plan_line_ids=blocked_ids,
                evidence={"blocking_line_count": blocking},
            )
        )

    amb_ids = _ids_with(lines, lambda r: _missing_has(r, CODE_BOQ_AMBIGUOUS))
    if amb_ids:
        findings.append(
            _finding(CODE_BOQ_AMBIGUOUS, SEV_WARNING, count=len(amb_ids), plan_line_ids=amb_ids)
        )

    nr_ids = _ids_with(lines, lambda r: _missing_has(r, CODE_NOT_REQUIRED_GAP))
    if nr_ids:
        findings.append(
            _finding(CODE_NOT_REQUIRED_GAP, SEV_WARNING, count=len(nr_ids), plan_line_ids=nr_ids)
        )

    if trace.get("scope_read_error") or _dq_has(issues, CODE_SCOPE_READ_FAILED):
        findings.append(
            _finding(
                CODE_SCOPE_READ_FAILED,
                SEV_WARNING,
                count=1,
                evidence={"scope_read_error": trace.get("scope_read_error")},
            )
        )

    completed_ids = _ids_with(
        lines,
        lambda r: r.get("completed") is True and float(r.get("requested_qty") or 0) > 0,
    )
    if completed_ids:
        findings.append(
            _finding(
                CODE_COMPLETED_STILL_REQUESTED,
                SEV_WARNING,
                count=len(completed_ids),
                plan_line_ids=completed_ids,
            )
        )

    unavail_ids = _ids_with(lines, lambda r: _missing_has(r, CODE_ADMISSION_UNAVAILABLE))
    if unavail_ids and len(unavail_ids) < plan_line_count:
        findings.append(
            _finding(
                CODE_ADMISSION_UNAVAILABLE,
                SEV_WARNING,
                count=len(unavail_ids),
                plan_line_ids=unavail_ids,
            )
        )

    return {"summary": summary, "findings": findings}


def _has_finding(findings: list[dict[str, Any]], code: str) -> bool:
    return any(f.get("code") == code for f in findings)


def _validate_analysis(
    snapshot: dict[str, Any],
    analysis: dict[str, Any],
    *,
    project_code: str,
    month_key_canonical: Optional[str],
) -> dict[str, Any]:
    summary = _as_dict(analysis.get("summary"))
    findings = _as_list(analysis.get("findings"))
    plan_line_count = int(summary.get("plan_line_count") or 0)
    required = summary.get("required_hours_total") or 0
    approved = summary.get("approved_available_hours_total")

    blockers = [f for f in findings if f.get("severity") == SEV_BLOCKER]
    warnings = [f for f in findings if f.get("severity") == SEV_WARNING]

    blocked = False
    reasons: list[str] = []
    if not _safe_str(project_code):
        blocked = True
        reasons.append(CODE_BLANK_PROJECT)
    if not month_key_canonical:
        blocked = True
        reasons.append(CODE_INVALID_MONTH)
    if plan_line_count == 0:
        blocked = True
        reasons.append(CODE_NO_PLAN_LINES)
    if required > 0 and approved is None and _has_finding(findings, CODE_CAPACITY_MISSING):
        blocked = True
        reasons.append(CODE_CAPACITY_MISSING)

    if blocked:
        status = VAL_BLOCKED
    elif warnings:
        status = VAL_PASS_WITH_WARNINGS
    else:
        status = VAL_PASS

    return {
        "status": status,
        "reasons": reasons,
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
    }


def _recommendation_code(
    validation: dict[str, Any],
    analysis: dict[str, Any],
) -> str:
    findings = _as_list(analysis.get("findings"))
    if validation.get("status") == VAL_BLOCKED:
        return REC_NOT_READY
    admission = _has_finding(findings, CODE_ADMISSION_BLOCKED)
    deficit = _has_finding(findings, CODE_RESOURCE_DEFICIT)
    if admission and deficit:
        return REC_MIXED
    if admission:
        return REC_ADMISSION_BLOCKED
    if deficit:
        return REC_RESOURCE_DEFICIT
    if validation.get("status") == VAL_PASS_WITH_WARNINGS:
        return REC_READY_WITH_WARNINGS
    return REC_READY


def _suggested_next_action(rec: str, findings: list[dict[str, Any]]) -> str:
    if rec == REC_NOT_READY:
        return ACTION_FIX_DQ
    if rec == REC_MIXED:
        return ACTION_REVIEW_PLAN
    if rec == REC_ADMISSION_BLOCKED:
        return ACTION_REVIEW_ADMISSION
    if rec == REC_RESOURCE_DEFICIT:
        return ACTION_REVIEW_RESOURCE
    if rec == REC_READY_WITH_WARNINGS:
        codes = {f.get("code") for f in findings}
        if CODE_NOT_REQUIRED_GAP in codes and codes <= {
            CODE_NOT_REQUIRED_GAP,
            CODE_BOQ_AMBIGUOUS,
        }:
            if codes == {CODE_NOT_REQUIRED_GAP}:
                return ACTION_WAIT_NOT_REQUIRED
        return ACTION_REVIEW_PLAN
    return ACTION_REVIEW_PLAN


def _build_human_decision_payload(
    analysis: dict[str, Any],
    validation: dict[str, Any],
    gather: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    findings = _as_list(analysis.get("findings"))
    rec = _recommendation_code(validation, analysis)
    blockers = [f for f in findings if f.get("severity") == SEV_BLOCKER]
    warnings = [f for f in findings if f.get("severity") == SEV_WARNING]
    affected: list[str] = []
    seen: set[str] = set()
    for item in findings:
        for pid in _as_list(item.get("plan_line_ids")):
            text = _safe_str(pid)
            if text and text not in seen:
                seen.add(text)
                affected.append(text)
    return {
        "pending": True,
        "writes_allowed": False,
        "decision_action": None,
        "recommendation_code": rec,
        "validation_status": validation.get("status"),
        "findings": findings,
        "blockers": blockers,
        "warnings": warnings,
        "affected_plan_line_ids": affected,
        "suggested_next_action": _suggested_next_action(rec, findings),
        "evidence": {
            "gather_sources": gather.get("sources"),
            "source_trace": _as_dict(snapshot.get("source_trace")),
        },
    }


def _canonical_from_snapshot(snapshot: dict[str, Any], month_key: str) -> Optional[str]:
    scope = _as_dict(snapshot.get("run_scope"))
    canonical = scope.get("month_key_canonical")
    if canonical:
        return _safe_str(canonical) or None
    return None


def build_orchestrator_run(
    snapshot: Optional[dict[str, Any]],
    *,
    project_code: str,
    month_key: str,
    filters: Optional[dict[str, Any]] = None,
    run_id: Optional[str] = None,
    started_at: Optional[str] = None,
) -> dict[str, Any]:
    """Pure deterministic run builder. Domain result ignores generated clocks unless injected."""
    started = started_at or _utcnow_iso()
    rid = run_id or str(uuid.uuid4())
    filt = dict(filters or {})
    t0 = perf_counter()

    if not isinstance(snapshot, dict):
        finished = _utcnow_iso() if started_at is None else started
        gather = _build_gather_result(None)
        trace = [
            _make_trace_event(
                STATE_GATHER,
                started_at=started,
                finished_at=finished,
                duration_ms=0.0,
                status="ERROR",
                tool="load_planning_snapshot",
                error="PlanningSnapshot missing",
            )
        ]
        return {
            "run_id": rid,
            "started_at": started,
            "finished_at": finished,
            "project_code": _safe_str(project_code),
            "month_key_input": month_key,
            "month_key_canonical": None,
            "filters": filt,
            "state": STATE_FAILED,
            "snapshot": None,
            "gather": gather,
            "analysis": None,
            "validation": None,
            "human_decision": None,
            "trace": trace,
            "error": {"code": "SNAPSHOT_MISSING", "message": "PlanningSnapshot missing"},
        }

    gather = _build_gather_result(snapshot)
    t1 = perf_counter()
    gather_ms = (t1 - t0) * 1000.0
    if started_at is not None:
        gather_ms = 0.0
        gather_finished = started
    else:
        gather_finished = _utcnow_iso()

    analysis = _analyze_snapshot(snapshot)
    t2 = perf_counter()
    analyze_ms = 0.0 if started_at is not None else (t2 - t1) * 1000.0
    analyze_finished = started if started_at is not None else _utcnow_iso()

    canonical = _canonical_from_snapshot(snapshot, month_key)
    validation = _validate_analysis(
        snapshot,
        analysis,
        project_code=_safe_str(project_code) or _safe_str(_as_dict(snapshot.get("run_scope")).get("project_code")),
        month_key_canonical=canonical,
    )
    t3 = perf_counter()
    validate_ms = 0.0 if started_at is not None else (t3 - t2) * 1000.0
    validate_finished = started if started_at is not None else _utcnow_iso()

    human = _build_human_decision_payload(analysis, validation, gather, snapshot)
    finished = started if started_at is not None else _utcnow_iso()

    trace = [
        _make_trace_event(
            STATE_GATHER,
            started_at=started,
            finished_at=gather_finished,
            duration_ms=gather_ms,
            status="OK",
            tool="load_planning_snapshot",
            summary={"snapshot_present": True, "sources": gather.get("sources")},
        ),
        _make_trace_event(
            STATE_ANALYZE,
            started_at=gather_finished,
            finished_at=analyze_finished,
            duration_ms=analyze_ms,
            status="OK",
            tool="analyze_snapshot",
            summary={"finding_count": len(_as_list(analysis.get("findings")))},
        ),
        _make_trace_event(
            STATE_VALIDATE,
            started_at=analyze_finished,
            finished_at=validate_finished,
            duration_ms=validate_ms,
            status="OK",
            tool="validate_run",
            summary={"status": validation.get("status")},
        ),
    ]

    return {
        "run_id": rid,
        "started_at": started,
        "finished_at": finished,
        "project_code": _safe_str(project_code),
        "month_key_input": month_key,
        "month_key_canonical": canonical,
        "filters": filt,
        "state": STATE_HUMAN_DECISION,
        "snapshot": snapshot,
        "gather": gather,
        "analysis": analysis,
        "validation": validation,
        "human_decision": human,
        "trace": trace,
        "error": None,
    }


def run_monthly_planning_orchestrator(
    project_code: str,
    month_key: str,
    *,
    filters: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Live READ wrapper. Calls load_planning_snapshot once. No writes."""
    started = _utcnow_iso()
    rid = str(uuid.uuid4())
    filt = dict(filters or {})
    t0 = perf_counter()
    try:
        snapshot = load_planning_snapshot(
            project_code=project_code,
            month_key=month_key,
            plan_line_id=filt.get("plan_line_id"),
            construction_discipline=filt.get("construction_discipline"),
            facility_building=filt.get("facility_building"),
            crew_code=filt.get("crew_code"),
        )
    except Exception as exc:  # noqa: BLE001
        finished = _utcnow_iso()
        duration_ms = (perf_counter() - t0) * 1000.0
        return {
            "run_id": rid,
            "started_at": started,
            "finished_at": finished,
            "project_code": _safe_str(project_code),
            "month_key_input": month_key,
            "month_key_canonical": None,
            "filters": filt,
            "state": STATE_FAILED,
            "snapshot": None,
            "gather": {
                "ok": False,
                "snapshot_present": False,
                "sources": {
                    "labor": "UNKNOWN",
                    "approved_capacity": "UNKNOWN",
                    "admission": "UNKNOWN",
                    "boq_reality": "UNKNOWN",
                },
                "source_trace": None,
                "error": {"code": type(exc).__name__, "message": str(exc)},
            },
            "analysis": None,
            "validation": None,
            "human_decision": None,
            "trace": [
                _make_trace_event(
                    STATE_GATHER,
                    started_at=started,
                    finished_at=finished,
                    duration_ms=duration_ms,
                    status="ERROR",
                    tool="load_planning_snapshot",
                    error=f"{type(exc).__name__}: {exc}",
                )
            ],
            "error": {"code": type(exc).__name__, "message": str(exc)},
        }

    return build_orchestrator_run(
        snapshot,
        project_code=project_code,
        month_key=month_key,
        filters=filt,
        run_id=rid,
        started_at=started,
    )
