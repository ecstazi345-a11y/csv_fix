"""
Constructor RUNTIME-B — professional Human Confirm wait / resume helpers.

Reuses interrupt_id / wait_ordinal / checkpoint-binding patterns from
professional Human Review (RUNTIME-A) and generic HITL.
Does NOT overload AMBIGUOUS_SCOPE / HUMAN_REVIEW / CLARIFY_SCOPE / ABORT_RUN.

Confirm authority remains human_confirm_contracts.py.
Does NOT create handoff. Does NOT emit fake ownership transfer.

No Streamlit. No new DB/store. No LLM. No product writes.
CAPABILITY != AUTHORITY.
HUMAN IDENTITY: TRANSITIONAL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Sequence

from agents.monthly_plan_constructor.hitl_contracts import (
    CODE_HITL_CONTRACT_BLOCKER,
    HitlContractError,
    compute_eos_interrupt_id,
)
from agents.monthly_plan_constructor.human_confirm_contracts import (
    HumanConfirmContractError,
    HumanConfirmEvent,
    normalize_human_confirm_events,
    project_effective_human_confirm,
)
from agents.monthly_plan_constructor.lifecycle import (
    CODE_LIFECYCLE_CONTRACT_BLOCKER,
    STATUS_APPLYING_HUMAN_CONFIRM,
    STATUS_FAILED,
    STATUS_PROFESSIONAL_WORK_COMPLETED,
    STATUS_REVIEWED_PACKAGE_READY,
    STATUS_WAITING_FOR_HUMAN_CONFIRM,
    ConstructorLifecycleState,
    LifecycleError,
    _append_transition,
    _require_aware_utc,
)

SCHEMA_VERSION = "1.0"
WAIT_KIND_HUMAN_CONFIRM = "HUMAN_CONFIRM"
REASON_HUMAN_CONFIRM = "HUMAN_CONFIRM"
SOURCE_PROFESSIONAL_CONFIRM = "PROFESSIONAL_CONFIRM"


@dataclass(frozen=True)
class ProfessionalHumanConfirmWaitRequest:
    """Interrupt payload for professional Human Confirm (not Review / not scope HITL)."""

    schema_version: str
    wait_kind: str
    interrupt_id: str
    run_id: str
    mission_id: str
    reviewed_package_id: str
    source_candidate_package_id: str
    wait_ordinal: int
    created_at: datetime


@dataclass(frozen=True)
class ProfessionalHumanConfirmResumeCommand:
    """
    Structured resume payload carrying immutable HumanConfirmEvent(s).

    Caller supplies answered_at. No datetime.now() / UUID generation here.
    """

    schema_version: str
    interrupt_id: str
    run_id: str
    confirm_events: tuple[HumanConfirmEvent, ...]
    answered_at: datetime
    expected_checkpoint_id: Optional[str] = None


def count_human_confirm_wait_ordinal(transitions: Sequence[Any]) -> int:
    """Count transitions into WAITING_FOR_HUMAN_CONFIRM (1-based)."""
    count = 0
    for item in transitions:
        to_status = getattr(item, "to_status", None)
        if to_status == STATUS_WAITING_FOR_HUMAN_CONFIRM:
            count += 1
    return count


def enter_waiting_for_human_confirm(
    state: ConstructorLifecycleState,
    *,
    now: Optional[datetime] = None,
) -> ConstructorLifecycleState:
    """REVIEWED_PACKAGE_READY → WAITING_FOR_HUMAN_CONFIRM (graph enter path)."""
    if state.status != STATUS_REVIEWED_PACKAGE_READY:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "enter human confirm wait requires REVIEWED_PACKAGE_READY",
        )
    if state.reviewed_package is None:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "reviewed_package required to enter Human Confirm wait",
        )
    if int(state.reviewed_package.unresolved_count) > 0:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "unresolved ReviewedCandidatePackage cannot enter Human Confirm",
        )
    stamp = _require_aware_utc(now or state.updated_at, "now")
    return _append_transition(
        state,
        to_status=STATUS_WAITING_FOR_HUMAN_CONFIRM,
        at=stamp,
        source_capability=SOURCE_PROFESSIONAL_CONFIRM,
        note="awaiting professional Human Confirm",
        trigger_code=REASON_HUMAN_CONFIRM,
        error_code=REASON_HUMAN_CONFIRM,
        terminal_reason="awaiting professional Human Confirm",
    )


def build_professional_confirm_wait_request(
    state: ConstructorLifecycleState,
    *,
    created_at: Optional[datetime] = None,
) -> ProfessionalHumanConfirmWaitRequest:
    """Deterministic wait request from WAITING_FOR_HUMAN_CONFIRM lifecycle state."""
    if state.status != STATUS_WAITING_FOR_HUMAN_CONFIRM:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "professional confirm wait requires WAITING_FOR_HUMAN_CONFIRM",
        )
    if state.reviewed_package is None:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "reviewed_package required for professional Human Confirm wait",
        )
    stamp = _require_aware_utc(created_at or state.updated_at, "created_at")
    wait_ordinal = count_human_confirm_wait_ordinal(state.transitions)
    if wait_ordinal < 1:
        wait_ordinal = 1
    interrupt_id = compute_eos_interrupt_id(
        run_id=state.run_id,
        wait_ordinal=wait_ordinal,
        reason_code=REASON_HUMAN_CONFIRM,
    )
    reviewed = state.reviewed_package
    return ProfessionalHumanConfirmWaitRequest(
        schema_version=SCHEMA_VERSION,
        wait_kind=WAIT_KIND_HUMAN_CONFIRM,
        interrupt_id=interrupt_id,
        run_id=state.run_id,
        mission_id=state.mission_id,
        reviewed_package_id=reviewed.reviewed_package_id,
        source_candidate_package_id=reviewed.source_candidate_package_id,
        wait_ordinal=wait_ordinal,
        created_at=stamp,
    )


def coerce_professional_confirm_resume_command(
    payload: Any,
) -> ProfessionalHumanConfirmResumeCommand:
    """Accept typed command or JSON-ish mapping. Fail closed on free-text / unknown."""
    if isinstance(payload, ProfessionalHumanConfirmResumeCommand):
        return payload
    if not isinstance(payload, dict):
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "professional confirm resume payload must be ProfessionalHumanConfirmResumeCommand or mapping",
        )
    events_raw = payload.get("confirm_events")
    if events_raw is None:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "confirm_events required",
        )
    events: list[HumanConfirmEvent] = []
    for item in events_raw:
        if not isinstance(item, HumanConfirmEvent):
            raise HitlContractError(
                CODE_HITL_CONTRACT_BLOCKER,
                "confirm_events must contain HumanConfirmEvent only",
            )
        events.append(item)
    answered = payload.get("answered_at")
    if not isinstance(answered, datetime):
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "answered_at must be datetime",
        )
    expected = payload.get("expected_checkpoint_id")
    return ProfessionalHumanConfirmResumeCommand(
        schema_version=str(payload.get("schema_version") or SCHEMA_VERSION),
        interrupt_id=str(payload.get("interrupt_id") or "").strip(),
        run_id=str(payload.get("run_id") or "").strip(),
        confirm_events=tuple(events),
        answered_at=answered,
        expected_checkpoint_id=(
            None if expected is None else str(expected).strip() or None
        ),
    )


def apply_professional_human_confirm(
    state: ConstructorLifecycleState,
    command: ProfessionalHumanConfirmResumeCommand,
    *,
    wait_request: ProfessionalHumanConfirmWaitRequest,
    now: Optional[datetime] = None,
) -> ConstructorLifecycleState:
    """
    Apply structured Human Confirm resume against current ReviewedCandidatePackage.

    Does not mutate ReviewedCandidatePackage or Human Review history.
    Does not create handoff.
    """
    if state.status != STATUS_WAITING_FOR_HUMAN_CONFIRM:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "professional confirm resume requires WAITING_FOR_HUMAN_CONFIRM",
        )
    if state.reviewed_package is None:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "reviewed_package required for professional Human Confirm resume",
        )

    stamp = _require_aware_utc(now or command.answered_at, "now")
    if command.run_id != state.run_id:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "run_id mismatch on professional confirm resume",
        )
    if command.interrupt_id != wait_request.interrupt_id:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "interrupt_id mismatch on professional confirm resume",
        )
    reviewed = state.reviewed_package
    if wait_request.reviewed_package_id != reviewed.reviewed_package_id:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "reviewed_package_id mismatch on professional confirm wait binding",
        )
    if wait_request.source_candidate_package_id != reviewed.source_candidate_package_id:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "source_candidate_package_id mismatch on professional confirm wait binding",
        )
    if wait_request.mission_id != state.mission_id:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "mission_id mismatch on professional confirm wait binding",
        )

    state = _append_transition(
        state,
        to_status=STATUS_APPLYING_HUMAN_CONFIRM,
        at=stamp,
        source_capability=SOURCE_PROFESSIONAL_CONFIRM,
        note="applying professional Human Confirm",
        trigger_code=REASON_HUMAN_CONFIRM,
    )

    prior_events = tuple(state.human_confirm_events or ())
    try:
        incoming = normalize_human_confirm_events(command.confirm_events, reviewed)
        history = normalize_human_confirm_events(prior_events + incoming, reviewed)
    except HumanConfirmContractError:
        raise

    effective = project_effective_human_confirm(history, reviewed)
    if effective is None:
        return _append_transition(
            state,
            to_status=STATUS_FAILED,
            at=stamp,
            source_capability=SOURCE_PROFESSIONAL_CONFIRM,
            note="Human Confirm produced no effective confirm",
            trigger_code=CODE_LIFECYCLE_CONTRACT_BLOCKER,
            error_code=CODE_LIFECYCLE_CONTRACT_BLOCKER,
            terminal_reason="empty Human Confirm result",
            human_confirm_events=history,
        )

    return _append_transition(
        state,
        to_status=STATUS_PROFESSIONAL_WORK_COMPLETED,
        at=stamp,
        source_capability=SOURCE_PROFESSIONAL_CONFIRM,
        note="Constructor professional work completed via Human Confirm",
        human_confirm_events=history,
        error_code=None,
        terminal_reason=None,
    )
