"""
Constructor RUNTIME-A — professional Human Review wait / resume helpers.

Reuses interrupt_id / wait_ordinal / checkpoint-binding patterns from generic HITL.
Does NOT overload CLARIFY_SCOPE / ABORT_RUN.

Professional validation authority remains human_review_contracts.py.
Reviewed disposition authority remains reviewed_candidate_package.py.

No Streamlit. No new DB/store. No LLM. No product writes.
CAPABILITY != AUTHORITY.
HUMAN IDENTITY: TRANSITIONAL.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from agents.monthly_plan_constructor.hitl_contracts import (
    CODE_HITL_CONTRACT_BLOCKER,
    HitlContractError,
    compute_eos_interrupt_id,
)
from agents.monthly_plan_constructor.human_review_contracts import (
    HumanReviewContractError,
    HumanReviewEvent,
    normalize_human_review_events,
)
from agents.monthly_plan_constructor.lifecycle import (
    CODE_LIFECYCLE_CONTRACT_BLOCKER,
    STATUS_APPLYING_HUMAN_REVIEW,
    STATUS_FAILED,
    STATUS_REVIEWED_PACKAGE_READY,
    STATUS_WAITING_FOR_HUMAN_REVIEW,
    ConstructorLifecycleState,
    LifecycleError,
    _append_transition,
    _require_aware_utc,
)
from agents.monthly_plan_constructor.reviewed_candidate_package import (
    ReviewedCandidatePackage,
    ReviewedPackageError,
    build_reviewed_candidate_package,
)

SCHEMA_VERSION = "1.0"
WAIT_KIND_HUMAN_REVIEW = "HUMAN_REVIEW"
REASON_HUMAN_REVIEW = "HUMAN_REVIEW"
SOURCE_PROFESSIONAL_REVIEW = "PROFESSIONAL_REVIEW"


@dataclass(frozen=True)
class ProfessionalHumanReviewWaitRequest:
    """Interrupt payload for professional Human Review (not generic scope HITL)."""

    schema_version: str
    wait_kind: str
    interrupt_id: str
    run_id: str
    mission_id: str
    package_id: str
    wait_ordinal: int
    candidate_ids: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True)
class ProfessionalHumanReviewResumeCommand:
    """
    Structured resume payload carrying immutable HumanReviewEvent(s).

    Caller supplies answered_at. No datetime.now() / UUID generation here.
    """

    schema_version: str
    interrupt_id: str
    run_id: str
    review_events: tuple[HumanReviewEvent, ...]
    answered_at: datetime
    expected_checkpoint_id: Optional[str] = None


def count_human_review_wait_ordinal(transitions: Sequence[Any]) -> int:
    """Count transitions into WAITING_FOR_HUMAN_REVIEW (1-based)."""
    count = 0
    for item in transitions:
        to_status = getattr(item, "to_status", None)
        if to_status == STATUS_WAITING_FOR_HUMAN_REVIEW:
            count += 1
    return count


def build_professional_review_wait_request(
    state: ConstructorLifecycleState,
    *,
    created_at: Optional[datetime] = None,
) -> ProfessionalHumanReviewWaitRequest:
    """Deterministic wait request from WAITING_FOR_HUMAN_REVIEW lifecycle state."""
    if state.status != STATUS_WAITING_FOR_HUMAN_REVIEW:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "professional review wait requires WAITING_FOR_HUMAN_REVIEW",
        )
    if state.package is None:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "package required for professional Human Review wait",
        )
    stamp = _require_aware_utc(created_at or state.updated_at, "created_at")
    wait_ordinal = count_human_review_wait_ordinal(state.transitions)
    if wait_ordinal < 1:
        wait_ordinal = 1
    interrupt_id = compute_eos_interrupt_id(
        run_id=state.run_id,
        wait_ordinal=wait_ordinal,
        reason_code=REASON_HUMAN_REVIEW,
    )
    return ProfessionalHumanReviewWaitRequest(
        schema_version=SCHEMA_VERSION,
        wait_kind=WAIT_KIND_HUMAN_REVIEW,
        interrupt_id=interrupt_id,
        run_id=state.run_id,
        mission_id=state.mission_id,
        package_id=state.package.package_id,
        wait_ordinal=wait_ordinal,
        candidate_ids=tuple(c.candidate_id for c in state.package.candidates),
        created_at=stamp,
    )


def coerce_professional_review_resume_command(
    payload: Any,
) -> ProfessionalHumanReviewResumeCommand:
    """Accept typed command or JSON-ish mapping. Fail closed on free-text / unknown."""
    if isinstance(payload, ProfessionalHumanReviewResumeCommand):
        return payload
    if not isinstance(payload, dict):
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "professional review resume payload must be ProfessionalHumanReviewResumeCommand or mapping",
        )
    events_raw = payload.get("review_events")
    if events_raw is None:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "review_events required",
        )
    events: list[HumanReviewEvent] = []
    for item in events_raw:
        if not isinstance(item, HumanReviewEvent):
            raise HitlContractError(
                CODE_HITL_CONTRACT_BLOCKER,
                "review_events must contain HumanReviewEvent only",
            )
        events.append(item)
    answered = payload.get("answered_at")
    if not isinstance(answered, datetime):
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "answered_at must be datetime",
        )
    expected = payload.get("expected_checkpoint_id")
    return ProfessionalHumanReviewResumeCommand(
        schema_version=str(payload.get("schema_version") or SCHEMA_VERSION),
        interrupt_id=str(payload.get("interrupt_id") or "").strip(),
        run_id=str(payload.get("run_id") or "").strip(),
        review_events=tuple(events),
        answered_at=answered,
        expected_checkpoint_id=(
            None if expected is None else str(expected).strip() or None
        ),
    )


def apply_professional_human_review(
    state: ConstructorLifecycleState,
    command: ProfessionalHumanReviewResumeCommand,
    *,
    wait_request: ProfessionalHumanReviewWaitRequest,
    now: Optional[datetime] = None,
) -> ConstructorLifecycleState:
    """
    Apply structured Human Review resume against current Candidate Package.

    Appends immutable review events, rebuilds ReviewedCandidatePackage,
    then either re-enters WAITING_FOR_HUMAN_REVIEW or reaches REVIEWED_PACKAGE_READY.
    """
    if state.status != STATUS_WAITING_FOR_HUMAN_REVIEW:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "professional review resume requires WAITING_FOR_HUMAN_REVIEW",
        )
    if state.package is None:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "package required for professional Human Review resume",
        )
    if state.exceptions is None:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "exceptions required for professional Human Review resume",
        )

    stamp = _require_aware_utc(now or command.answered_at, "now")
    if command.run_id != state.run_id:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "run_id mismatch on professional review resume",
        )
    if command.interrupt_id != wait_request.interrupt_id:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "interrupt_id mismatch on professional review resume",
        )
    if wait_request.package_id != state.package.package_id:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "package_id mismatch on professional review wait binding",
        )

    # Intermediate resume-only status (mirrors generic HITL APPLYING pattern).
    state = _append_transition(
        state,
        to_status=STATUS_APPLYING_HUMAN_REVIEW,
        at=stamp,
        source_capability=SOURCE_PROFESSIONAL_REVIEW,
        note="applying professional Human Review",
        trigger_code=REASON_HUMAN_REVIEW,
    )

    prior_events = tuple(state.human_review_events or ())
    # Normalize ONLY the newly submitted batch against package first (stale/unknown fail).
    try:
        incoming = normalize_human_review_events(command.review_events, state.package)
    except HumanReviewContractError:
        raise

    # Append-only merge: full history then normalize for idempotent replay across waits.
    combined = prior_events + incoming
    try:
        history = normalize_human_review_events(combined, state.package)
    except HumanReviewContractError:
        raise

    exception_items = tuple(state.exceptions.exceptions)
    package_for_builder = replace(
        state.package,
        exception_summary=state.exceptions.summary,
    )
    try:
        reviewed = build_reviewed_candidate_package(
            package_for_builder,
            history,
            exception_items,
            created_at=stamp,
        )
    except ReviewedPackageError as exc:
        return _append_transition(
            state,
            to_status=STATUS_FAILED,
            at=stamp,
            source_capability=SOURCE_PROFESSIONAL_REVIEW,
            note="reviewed package build failed",
            trigger_code=getattr(exc, "code", CODE_LIFECYCLE_CONTRACT_BLOCKER),
            error_code=getattr(exc, "code", CODE_LIFECYCLE_CONTRACT_BLOCKER),
            terminal_reason=str(exc),
            human_review_events=history,
        )

    if reviewed.unresolved_count > 0:
        return _append_transition(
            state,
            to_status=STATUS_WAITING_FOR_HUMAN_REVIEW,
            at=stamp,
            source_capability=SOURCE_PROFESSIONAL_REVIEW,
            note="reviewed package unresolved; awaiting further Human Review",
            trigger_code=REASON_HUMAN_REVIEW,
            human_review_events=history,
            reviewed_package=reviewed,
            package=package_for_builder,
            error_code=REASON_HUMAN_REVIEW,
            terminal_reason="unresolved reviewed package",
        )

    return _append_transition(
        state,
        to_status=STATUS_REVIEWED_PACKAGE_READY,
        at=stamp,
        source_capability=SOURCE_PROFESSIONAL_REVIEW,
        note="reviewed package ready for future Human Confirm",
        human_review_events=history,
        reviewed_package=reviewed,
        package=package_for_builder,
        error_code=None,
        terminal_reason=None,
    )
