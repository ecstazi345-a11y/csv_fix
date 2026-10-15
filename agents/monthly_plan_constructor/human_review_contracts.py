"""
Constructor Human Review Contract V1 — pure professional review decisions.

Human Review = human planning judgment over a Candidate Package.
It is NOT Constructor recommendation, Human Confirm, final inclusion,
monthly commitment, handoff, product write, or Executability authority.

Generic HITL (CLARIFY_SCOPE / ABORT_RUN) is a different runtime object.
Do not overload this contract with mission-scope clarification.

V1 is contract-only: no LangGraph wiring, no persistence, no UI, no LLM.
CAPABILITY != AUTHORITY.

HUMAN IDENTITY: TRANSITIONAL.
actor_type=HUMAN is structured attribution, not verified IAM authentication.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from agents.monthly_plan_constructor.candidate_package import CandidatePackage

SCHEMA_VERSION = "1.0"

CODE_HUMAN_REVIEW_CONTRACT_BLOCKER = "HUMAN_REVIEW_CONTRACT_BLOCKER"

ACTOR_TYPE_HUMAN = "HUMAN"

# Additive V1.2 professional resolution metadata (backwards-compatible).
RESOLUTION_KIND_DEFER_TO_PERIOD = "DEFER_TO_PERIOD"

_MAX_ID_LEN = 128
_MAX_ACTOR_LEN = 64
_MAX_RESOLUTION_LEN = 64
_MAX_PERIOD_LEN = 32


class HumanReviewDecision(str, Enum):
    """Closed professional row-level review actions (V1)."""

    ADD = "ADD"
    REMOVE = "REMOVE"
    REQUIRES_CLARIFICATION = "REQUIRES_CLARIFICATION"


class HumanReviewContractError(ValueError):
    """Fail-closed Human Review contract violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class HumanReviewEvent:
    """
    Immutable Human Review event.

    Caller supplies review_event_id and reviewed_at.
    This module never invents UUIDs or wall-clock timestamps.

    Decision is human judgment / intent only.
    It does not set included/approved/final/handoff_ready/labor_resolved flags.

    Optional quantity / reason fields are V1.1 additions.
    Optional resolution_kind / target_period are V1.2 additions
    (e.g. REMOVE + DEFER_TO_PERIOD + 2026-11).
    Historical events without them remain readable (None).
    """

    schema_version: str
    review_event_id: str
    run_id: str
    mission_id: str
    package_id: str
    candidate_id: str
    decision: HumanReviewDecision
    actor_type: str
    actor_id: str
    reviewed_at: datetime
    constructor_proposed_qty: Optional[float] = None
    human_approved_qty: Optional[float] = None
    reason_text: Optional[str] = None
    resolution_kind: Optional[str] = None
    target_period: Optional[str] = None


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
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            f"{field_name} is required",
        )
    if len(text) > max_len:
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            f"{field_name} exceeds max length {max_len}",
        )
    return text


def _require_aware_utc(value: Any, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            f"{field_name} must be datetime",
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            f"{field_name} must be timezone-aware UTC",
        )
    return value.astimezone(timezone.utc)


def _coerce_decision(value: Any) -> HumanReviewDecision:
    if isinstance(value, HumanReviewDecision):
        return value
    text = _require_text(value, "decision", max_len=64).upper()
    try:
        return HumanReviewDecision(text)
    except ValueError as exc:
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            f"invalid human review decision {text!r}",
        ) from exc


_MAX_REASON_LEN = 2000


def _optional_finite_qty(value: Any, field_name: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            f"{field_name} must be a finite number when provided",
        )
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            f"{field_name} must be a finite number when provided",
        )
    return number


def _optional_reason(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > _MAX_REASON_LEN:
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            f"reason_text exceeds max length {_MAX_REASON_LEN}",
        )
    return text


def _optional_resolution_kind(value: Any) -> Optional[str]:
    text = _optional_text(value)
    if text is None:
        return None
    if len(text) > _MAX_RESOLUTION_LEN:
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            f"resolution_kind exceeds max length {_MAX_RESOLUTION_LEN}",
        )
    return text.upper()


def _optional_target_period(value: Any) -> Optional[str]:
    text = _optional_text(value)
    if text is None:
        return None
    if len(text) > _MAX_PERIOD_LEN:
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            f"target_period exceeds max length {_MAX_PERIOD_LEN}",
        )
    return text


def build_human_review_event(
    *,
    review_event_id: str,
    run_id: str,
    mission_id: str,
    package_id: str,
    candidate_id: str,
    decision: Any,
    actor_id: str,
    reviewed_at: datetime,
    actor_type: str = ACTOR_TYPE_HUMAN,
    schema_version: str = SCHEMA_VERSION,
    constructor_proposed_qty: Any = None,
    human_approved_qty: Any = None,
    reason_text: Any = None,
    resolution_kind: Any = None,
    target_period: Any = None,
) -> HumanReviewEvent:
    """
    Normalize a Human Review event. Pure. No UUID / now() generation.
    """
    actor = _require_text(actor_type, "actor_type", max_len=_MAX_ACTOR_LEN)
    if actor != ACTOR_TYPE_HUMAN:
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            "actor_type must be HUMAN (transitional attribution, not verified IAM)",
        )
    kind = _optional_resolution_kind(resolution_kind)
    period = _optional_target_period(target_period)
    if kind == RESOLUTION_KIND_DEFER_TO_PERIOD and period is None:
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            "target_period is required for DEFER_TO_PERIOD",
        )
    if period is not None and kind is None:
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            "resolution_kind is required when target_period is set",
        )
    return HumanReviewEvent(
        schema_version=_require_text(schema_version, "schema_version", max_len=32),
        review_event_id=_require_text(review_event_id, "review_event_id"),
        run_id=_require_text(run_id, "run_id"),
        mission_id=_require_text(mission_id, "mission_id"),
        package_id=_require_text(package_id, "package_id"),
        candidate_id=_require_text(candidate_id, "candidate_id"),
        decision=_coerce_decision(decision),
        actor_type=actor,
        actor_id=_require_text(actor_id, "actor_id"),
        reviewed_at=_require_aware_utc(reviewed_at, "reviewed_at"),
        constructor_proposed_qty=_optional_finite_qty(
            constructor_proposed_qty, "constructor_proposed_qty"
        ),
        human_approved_qty=_optional_finite_qty(
            human_approved_qty, "human_approved_qty"
        ),
        reason_text=_optional_reason(reason_text),
        resolution_kind=kind,
        target_period=period,
    )


def _candidate_id_index(package: CandidatePackage) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in package.candidates:
        key = str(item.candidate_id)
        counts[key] = counts.get(key, 0) + 1
    ambiguous = sorted(key for key, count in counts.items() if count > 1)
    if ambiguous:
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            f"duplicate candidate_id in package: {ambiguous[0]}",
        )
    return {key: 1 for key in counts}


def validate_human_review_event_against_package(
    event: HumanReviewEvent,
    package: CandidatePackage,
) -> HumanReviewEvent:
    """
    Fail-closed binding of a review event to one Candidate Package.

    Does not mutate package, recommendation fields, or labor status.
    """
    if not isinstance(event, HumanReviewEvent):
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            "event must be HumanReviewEvent",
        )
    if not isinstance(package, CandidatePackage):
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            "package must be CandidatePackage",
        )

    package_run = _optional_text(package.run_id)
    if package_run is None:
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            "package.run_id is required for human review binding",
        )
    if event.run_id != package_run:
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            "run_id mismatch between review event and package",
        )
    if event.mission_id != package.mission_id:
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            "mission_id mismatch between review event and package",
        )
    if event.package_id != package.package_id:
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            "package_id mismatch between review event and package",
        )

    index = _candidate_id_index(package)
    if event.candidate_id not in index:
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            f"candidate_id {event.candidate_id!r} is not in package",
        )
    return event


def _event_payload_fingerprint(event: HumanReviewEvent) -> tuple[Any, ...]:
    """Stable comparable payload for idempotent replay (excludes object identity)."""
    return (
        event.schema_version,
        event.review_event_id,
        event.run_id,
        event.mission_id,
        event.package_id,
        event.candidate_id,
        event.decision.value,
        event.actor_type,
        event.actor_id,
        event.reviewed_at.isoformat(),
        event.constructor_proposed_qty,
        event.human_approved_qty,
        event.reason_text,
        event.resolution_kind,
        event.target_period,
    )


def normalize_human_review_events(
    events: Sequence[HumanReviewEvent],
    package: CandidatePackage,
) -> tuple[HumanReviewEvent, ...]:
    """
    Validate an ordered event sequence against one package.

    INPUT ORDER IS AUTHORITATIVE.
    Same review_event_id + identical payload → idempotent (keep first).
    Same review_event_id + different payload → FAIL CLOSED.
    """
    if events is None or isinstance(events, (str, bytes)):
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            "events must be a sequence of HumanReviewEvent",
        )

    accepted: list[HumanReviewEvent] = []
    by_id: dict[str, HumanReviewEvent] = {}
    for raw in events:
        if not isinstance(raw, HumanReviewEvent):
            raise HumanReviewContractError(
                CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
                "events must contain HumanReviewEvent only",
            )
        event = validate_human_review_event_against_package(raw, package)
        prior = by_id.get(event.review_event_id)
        if prior is not None:
            if _event_payload_fingerprint(prior) != _event_payload_fingerprint(event):
                raise HumanReviewContractError(
                    CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
                    f"conflicting replay for review_event_id {event.review_event_id!r}",
                )
            continue
        by_id[event.review_event_id] = event
        accepted.append(event)
    return tuple(accepted)


def project_effective_human_review_decisions(
    events: Sequence[HumanReviewEvent],
    package: CandidatePackage,
) -> Mapping[str, HumanReviewDecision]:
    """
    Latest effective decision per candidate_id.

    INPUT ORDER IS AUTHORITATIVE EVENT ORDER.
    Do not sort by reviewed_at.
    Candidates without review events are omitted (NOT REVIEWED — no fake decision).
    """
    return {
        candidate_id: event.decision
        for candidate_id, event in project_effective_human_review_events(
            events, package
        ).items()
    }


def project_effective_human_review_events(
    events: Sequence[HumanReviewEvent],
    package: CandidatePackage,
) -> Mapping[str, HumanReviewEvent]:
    """Latest HumanReviewEvent per candidate_id (append-only history; order wins)."""
    normalized = normalize_human_review_events(events, package)
    effective: dict[str, HumanReviewEvent] = {}
    for event in normalized:
        effective[event.candidate_id] = event
    return dict(effective)


def human_review_event_as_dict(event: HumanReviewEvent) -> dict[str, Any]:
    """JSON-friendly snapshot for tests/audit fixtures. Not a persistence API."""
    payload = asdict(event)
    payload["decision"] = event.decision.value
    payload["reviewed_at"] = event.reviewed_at.isoformat()
    return payload


# Explicit non-goals for V1 (documentation markers for audits).
V1_FORBIDDEN_SEMANTIC_FIELDS = frozenset(
    {
        "included",
        "approved",
        "final",
        "handoff_ready",
        "labor_resolved",
        "authority_granted",
    }
)


def assert_no_final_inclusion_semantics(event: HumanReviewEvent) -> None:
    """Guard: HumanReviewEvent must not smuggle final-inclusion authority fields."""
    names = {f.name for f in fields(event)}
    leak = sorted(names & V1_FORBIDDEN_SEMANTIC_FIELDS)
    if leak:
        raise HumanReviewContractError(
            CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
            f"forbidden final-inclusion fields on HumanReviewEvent: {leak}",
        )
