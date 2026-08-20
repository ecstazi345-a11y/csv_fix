"""
MPCA-001 — validators for Constructor Agent runs.
"""

from __future__ import annotations

from typing import Any

from utils.month_key import normalize_month_key


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none"} else text


def validate_run_inputs(project_code: str, stored_month_key: str) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if not _safe_text(project_code):
        errors.append({"code": "BLANK_PROJECT", "message": "project_code пуст"})
    canonical = normalize_month_key(stored_month_key)
    if canonical is None:
        errors.append(
            {
                "code": "INVALID_MONTH",
                "message": f"month_key невалиден: {stored_month_key!r}",
            }
        )
    return errors


def validate_proposal(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    """Structural / sanity checks on pure proposal output."""
    errors: list[dict[str, Any]] = []
    if not isinstance(proposal, dict):
        return [{"code": "INVALID_PROPOSAL", "message": "proposal is not a dict"}]

    for cand in proposal.get("candidates") or []:
        if not isinstance(cand, dict):
            errors.append({"code": "INVALID_CANDIDATE", "message": "candidate not dict"})
            continue
        if _safe_text(cand.get("availability_status")) == "Выполнено":
            errors.append(
                {
                    "code": "CANDIDATE_COMPLETED",
                    "message": f"candidate {cand.get('boq_code')} marked completed",
                }
            )
        avail = cand.get("available_to_add_qty")
        try:
            avail_f = float(avail)
        except (TypeError, ValueError):
            errors.append(
                {
                    "code": "INVALID_AVAILABLE",
                    "message": f"bad available_to_add_qty for {cand.get('boq_code')}",
                }
            )
            continue
        if avail_f <= 0:
            errors.append(
                {
                    "code": "CANDIDATE_NON_POSITIVE_AVAILABLE",
                    "message": f"candidate {cand.get('boq_code')} available <= 0",
                }
            )
        if cand.get("proposed_crew") is not None:
            errors.append(
                {
                    "code": "INVENTED_CREW",
                    "message": f"candidate {cand.get('boq_code')} has invented crew",
                }
            )
        if cand.get("proposed_plan_qty") is not None:
            errors.append(
                {
                    "code": "INVENTED_PLANNED_QTY",
                    "message": f"candidate {cand.get('boq_code')} has invented planned_qty",
                }
            )
        rem = cand.get("remaining_qty")
        try:
            rem_f = float(rem)
            if avail_f > rem_f + 1e-9:
                errors.append(
                    {
                        "code": "AVAILABLE_EXCEEDS_REMAINING",
                        "message": f"candidate {cand.get('boq_code')} available > remaining",
                    }
                )
        except (TypeError, ValueError):
            pass

        for field in ("facility", "discipline", "boq_code", "project_code"):
            if not _safe_text(cand.get(field)):
                errors.append(
                    {
                        "code": "SCOPE_KEY_INCOMPLETE",
                        "message": f"candidate missing {field}",
                    }
                )

    for issue in proposal.get("human_issues") or []:
        if (
            isinstance(issue, dict)
            and str(issue.get("severity") or "").upper() == "BLOCKER"
            and str(issue.get("code") or "")
            in {
                "CONFLICTING_PLAN_LINES",
                "INCONSISTENT_QUANTITIES",
                "CANDIDATE_EXCEEDS_AVAILABLE",
            }
        ):
            # Blockers are allowed in proposal; runtime maps to NEEDS_HUMAN.
            # Validator only flags if they were silently dropped — not the case.
            pass

    return errors


def validate_trace(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    required = {
        "START",
        "LOAD_SCOPE",
        "LOAD_ADJUSTMENTS",
        "LOAD_EXISTING_PLAN",
        "NORMALIZE",
        "CALCULATE_AVAILABILITY",
        "APPLY_EXISTING_PLAN",
        "CLASSIFY",
        "BUILD_CANDIDATES",
        "DETECT_HUMAN_ISSUES",
        "VALIDATE",
        "PREPARE_HANDOFF",
        "FINISH",
    }
    present = {str(e.get("step_code") or "") for e in trace}
    missing = sorted(required - present)
    if missing:
        errors.append(
            {
                "code": "TRACE_MISSING_STEPS",
                "message": f"missing steps: {missing}",
            }
        )
    for event in trace:
        try:
            dur = float(event.get("duration_ms"))
            if dur < 0:
                errors.append(
                    {
                        "code": "NEGATIVE_DURATION",
                        "message": f"step {event.get('step_code')} duration_ms < 0",
                    }
                )
        except (TypeError, ValueError):
            errors.append(
                {
                    "code": "BAD_DURATION",
                    "message": f"step {event.get('step_code')} bad duration_ms",
                }
            )
    return errors
