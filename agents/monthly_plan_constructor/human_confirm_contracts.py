"""
Constructor Human Confirm Contract V1 — pure package-level authority gate.

Human Confirm answers only:
  Does an attributed human confirm THIS immutable ReviewedCandidatePackage
  as Constructor's completed professional reviewed result?

It is NOT:
  - Human Review (row-level)
  - Recommendation
  - disposition recalculation
  - monthly commitment
  - Executability acceptance
  - handoff / receiver ACK
  - generic HITL (CLARIFY_SCOPE / ABORT_RUN)

V1: contract-only. No LangGraph wiring. No persistence. No UI. No LLM.
CAPABILITY != AUTHORITY.

HUMAN IDENTITY: TRANSITIONAL.
actor_type=HUMAN is structured attribution, not verified IAM authentication.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Sequence

from agents.monthly_plan_constructor.reviewed_candidate_package import (
    ReviewedCandidatePackage,
)

SCHEMA_VERSION = "1.0"
CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER = "HUMAN_CONFIRM_CONTRACT_BLOCKER"

ACTOR_TYPE_HUMAN = "HUMAN"

_MAX_ID_LEN = 128
_MAX_ACTOR_LEN = 64


class HumanConfirmDecision(str, Enum):
    """Closed package-level confirm action (V1)."""

    CONFIRM = "CONFIRM"


class HumanConfirmContractError(ValueError):
    """Fail-closed Human Confirm contract violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class HumanConfirmEvent:
    """
    Immutable Human Confirm event.

    Caller supplies confirm_event_id and confirmed_at.
    This module never invents UUIDs or wall-clock timestamps.

    Decision confirms the reviewed package identity only.
    It does not mutate the ReviewedCandidatePackage and does not create handoff.
    """

    schema_version: str
    confirm_event_id: str
    reviewed_package_id: str
    source_candidate_package_id: str
    run_id: str
    mission_id: str
    decision: HumanConfirmDecision
    actor_type: str
    actor_id: str
    confirmed_at: datetime


# Explicit non-goals for V1 (documentation markers for audits).
V1_FORBIDDEN_SEMANTIC_FIELDS = frozenset(
    {
        "handoff_ready",
        "handoff_id",
        "approved_month",
        "monthly_commitment",
        "executability_accepted",
        "receiver_ack",
        "authorized",
        "verified_human",
    }
)


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    return text


def _require_text(value: Any, field_name: str, *, max_len: int = _MAX_ID_LEN) -> str:
    text = _optional_text(value)
    if text is None:
        raise HumanConfirmContractError(
            CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
            f"{field_name} is required",
        )
    if len(text) > max_len:
        raise HumanConfirmContractError(
            CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
            f"{field_name} exceeds max length {max_len}",
        )
    return text


def _require_aware_utc(value: Any, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise HumanConfirmContractError(
            CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
            f"{field_name} must be datetime",
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise HumanConfirmContractError(
            CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
            f"{field_name} must be timezone-aware UTC",
        )
    return value.astimezone(timezone.utc)


def _coerce_decision(value: Any) -> HumanConfirmDecision:
    if isinstance(value, HumanConfirmDecision):
        return value
    text = _require_text(value, "decision", max_len=64).upper()
    try:
        return HumanConfirmDecision(text)
    except ValueError as exc:
        raise HumanConfirmContractError(
            CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
            f"invalid human confirm decision {text!r}",
        ) from exc


def build_human_confirm_event(
    *,
    confirm_event_id: str,
    reviewed_package_id: str,
    source_candidate_package_id: str,
    run_id: str,
    mission_id: str,
    decision: Any,
    actor_id: str,
    confirmed_at: datetime,
    actor_type: str = ACTOR_TYPE_HUMAN,
    schema_version: str = SCHEMA_VERSION,
) -> HumanConfirmEvent:
    """
    Normalize a Human Confirm event. Pure. No UUID / now() generation.
    """
    actor = _require_text(actor_type, "actor_type", max_len=_MAX_ACTOR_LEN)
    if actor != ACTOR_TYPE_HUMAN:
        raise HumanConfirmContractError(
            CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
            "actor_type must be HUMAN (transitional attribution, not verified IAM)",
        )
    return HumanConfirmEvent(
        schema_version=_require_text(schema_version, "schema_version", max_len=32),
        confirm_event_id=_require_text(confirm_event_id, "confirm_event_id"),
        reviewed_package_id=_require_text(
            reviewed_package_id, "reviewed_package_id"
        ),
        source_candidate_package_id=_require_text(
            source_candidate_package_id, "source_candidate_package_id"
        ),
        run_id=_require_text(run_id, "run_id"),
        mission_id=_require_text(mission_id, "mission_id"),
        decision=_coerce_decision(decision),
        actor_type=actor,
        actor_id=_require_text(actor_id, "actor_id"),
        confirmed_at=_require_aware_utc(confirmed_at, "confirmed_at"),
    )


def assert_reviewed_package_confirmable(
    package: ReviewedCandidatePackage,
) -> ReviewedCandidatePackage:
    """
    Eligibility gate: unresolved_count must be zero.

    Does not recalculate labor, dispositions, exceptions, or recommendations.
    """
    if not isinstance(package, ReviewedCandidatePackage):
        raise HumanConfirmContractError(
            CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
            "package must be ReviewedCandidatePackage",
        )
    if int(package.unresolved_count) > 0:
        raise HumanConfirmContractError(
            CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
            "ReviewedCandidatePackage with unresolved_count > 0 is not confirmable",
        )
    return package


def validate_human_confirm_event_against_package(
    event: HumanConfirmEvent,
    package: ReviewedCandidatePackage,
) -> HumanConfirmEvent:
    """
    Fail-closed binding of a confirm event to one Reviewed Candidate Package.

    Does not mutate the package.
    """
    if not isinstance(event, HumanConfirmEvent):
        raise HumanConfirmContractError(
            CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
            "event must be HumanConfirmEvent",
        )
    assert_reviewed_package_confirmable(package)

    if event.reviewed_package_id != package.reviewed_package_id:
        raise HumanConfirmContractError(
            CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
            "reviewed_package_id mismatch between confirm event and package",
        )
    if event.source_candidate_package_id != package.source_candidate_package_id:
        raise HumanConfirmContractError(
            CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
            "source_candidate_package_id mismatch between confirm event and package",
        )
    if event.run_id != package.run_id:
        raise HumanConfirmContractError(
            CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
            "run_id mismatch between confirm event and package",
        )
    if event.mission_id != package.mission_id:
        raise HumanConfirmContractError(
            CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
            "mission_id mismatch between confirm event and package",
        )
    if event.decision != HumanConfirmDecision.CONFIRM:
        raise HumanConfirmContractError(
            CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
            f"unsupported human confirm decision {event.decision!r}",
        )
    return event


def _event_payload_fingerprint(event: HumanConfirmEvent) -> tuple[Any, ...]:
    """Stable comparable payload for idempotent replay (excludes object identity)."""
    return (
        event.schema_version,
        event.confirm_event_id,
        event.reviewed_package_id,
        event.source_candidate_package_id,
        event.run_id,
        event.mission_id,
        event.decision.value,
        event.actor_type,
        event.actor_id,
        event.confirmed_at.isoformat(),
    )


def normalize_human_confirm_events(
    events: Sequence[HumanConfirmEvent],
    package: ReviewedCandidatePackage,
) -> tuple[HumanConfirmEvent, ...]:
    """
    Validate an ordered confirm event sequence against one reviewed package.

    V1 law:
      - 0 events → empty (NOT CONFIRMED)
      - identical replay same confirm_event_id + payload → keep first
      - same confirm_event_id + different payload → FAIL CLOSED
      - multiple distinct confirm_event_ids for one package → FAIL CLOSED
    INPUT ORDER IS AUTHORITATIVE. No wall-clock sorting. No latest-wins.
    """
    if events is None or isinstance(events, (str, bytes)):
        raise HumanConfirmContractError(
            CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
            "events must be a sequence of HumanConfirmEvent",
        )

    assert_reviewed_package_confirmable(package)

    accepted: list[HumanConfirmEvent] = []
    by_id: dict[str, HumanConfirmEvent] = {}
    for raw in events:
        if not isinstance(raw, HumanConfirmEvent):
            raise HumanConfirmContractError(
                CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
                "events must contain HumanConfirmEvent only",
            )
        event = validate_human_confirm_event_against_package(raw, package)
        prior = by_id.get(event.confirm_event_id)
        if prior is not None:
            if _event_payload_fingerprint(prior) != _event_payload_fingerprint(event):
                raise HumanConfirmContractError(
                    CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
                    f"conflicting replay for confirm_event_id {event.confirm_event_id!r}",
                )
            continue
        if accepted and event.confirm_event_id != accepted[0].confirm_event_id:
            raise HumanConfirmContractError(
                CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
                "V1 allows only one distinct confirm_event_id per reviewed package",
            )
        by_id[event.confirm_event_id] = event
        accepted.append(event)
    return tuple(accepted)


def project_effective_human_confirm(
    events: Sequence[HumanConfirmEvent],
    package: ReviewedCandidatePackage,
) -> Optional[HumanConfirmEvent]:
    """
    Effective Confirm for one reviewed package, or None if not confirmed.

    V1: at most one distinct confirm event (after idempotent replay collapse).
    """
    normalized = normalize_human_confirm_events(events, package)
    if not normalized:
        return None
    return normalized[0]


def human_confirm_event_as_dict(event: HumanConfirmEvent) -> dict[str, Any]:
    """JSON-friendly snapshot for tests/audit fixtures. Not a persistence API."""
    payload = asdict(event)
    payload["decision"] = event.decision.value
    payload["confirmed_at"] = event.confirmed_at.isoformat()
    return payload


def assert_no_handoff_or_commitment_semantics(event: HumanConfirmEvent) -> None:
    """Guard: HumanConfirmEvent must not smuggle handoff/commitment authority fields."""
    names = {f.name for f in fields(event)}
    leak = sorted(names & V1_FORBIDDEN_SEMANTIC_FIELDS)
    if leak:
        raise HumanConfirmContractError(
            CODE_HUMAN_CONFIRM_CONTRACT_BLOCKER,
            f"forbidden handoff/commitment fields on HumanConfirmEvent: {leak}",
        )
