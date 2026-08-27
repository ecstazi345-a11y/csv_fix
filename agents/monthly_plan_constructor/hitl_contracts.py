"""
Constructor Runtime v0.1 Increment 8 — HITL contracts.

Immutable structured Human Decision Request / Resume Command.
Not a second agent. No Streamlit. No DB. No LLM. No free-text executable logic.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Protocol, Sequence

SCHEMA_VERSION = "1.0"

SOURCE_HITL = "HITL"

STATUS_HITL_OPEN = "OPEN"
STATUS_HITL_ANSWERED = "ANSWERED"
STATUS_HITL_CANCELLED = "CANCELLED"

DECISION_CLARIFY_SCOPE = "CLARIFY_SCOPE"
DECISION_ABORT_RUN = "ABORT_RUN"

ALLOWED_DECISIONS = frozenset(
    {
        DECISION_CLARIFY_SCOPE,
        DECISION_ABORT_RUN,
    }
)

# Primary WAIT path for Increment 8.
RESUMABLE_REASON_CODES = frozenset(
    {
        "AMBIGUOUS_SCOPE",
    }
)

# Resume must never override these as business success.
NON_OVERRIDABLE_FAILURE_CODES = frozenset(
    {
        "SECURITY_DENIED",
        "DATA_CONTRACT_BLOCKER",
    }
)

ACTOR_TYPE_HUMAN = "HUMAN"
ACTOR_TYPE_LOCAL_APPLICATION = "LOCAL_APPLICATION"

CODE_HITL_CONTRACT_BLOCKER = "HITL_CONTRACT_BLOCKER"
CODE_RUN_ABORTED_BY_HUMAN = "RUN_ABORTED_BY_HUMAN"

_MAX_COMMENT_LEN = 500
_MAX_REASON_LEN = 500
_MAX_ID_LEN = 128
_MAX_EVIDENCE_REFS = 32
_MAX_EVIDENCE_REF_LEN = 128
_MAX_PARAM_KEYS = 16
_MAX_SCOPE_VALUES = 64

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class HitlContractError(ValueError):
    """Fail-closed HITL contract violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _require_aware_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            f"{field_name} must be datetime",
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            f"{field_name} must be timezone-aware UTC",
        )
    return value.astimezone(timezone.utc)


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
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            f"{field_name} is required",
        )
    if len(text) > max_len:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            f"{field_name} exceeds max length {max_len}",
        )
    return text


def _require_id(value: Any, field_name: str) -> str:
    text = _require_text(value, field_name, max_len=_MAX_ID_LEN)
    if not _ID_RE.match(text):
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            f"{field_name} has invalid format",
        )
    return text


def _bounded_comment(value: Any, field_name: str = "comment") -> Optional[str]:
    text = _optional_text(value)
    if text is None:
        return None
    if len(text) > _MAX_COMMENT_LEN:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            f"{field_name} exceeds max length {_MAX_COMMENT_LEN}",
        )
    return text


def _normalize_string_tuple(
    value: Any,
    field_name: str,
    *,
    max_items: int,
    max_item_len: int,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items: Sequence[Any] = (value,)
    elif isinstance(value, (list, tuple)):
        items = value
    else:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            f"{field_name} must be str, list, tuple, or None",
        )
    if len(items) > max_items:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            f"{field_name} exceeds max items {max_items}",
        )
    out: list[str] = []
    for item in items:
        text = _require_text(item, field_name, max_len=max_item_len)
        out.append(text)
    return tuple(out)


def compute_eos_interrupt_id(
    *,
    run_id: str,
    wait_ordinal: int,
    reason_code: str,
) -> str:
    """
    Deterministic Execution OS interrupt identity.

    Same pending WAIT (same run_id + wait_ordinal + reason) → same id.
    Later distinct re-WAIT (higher wait_ordinal) → different id.
    """
    run = _require_id(run_id, "run_id")
    reason = _require_text(reason_code, "reason_code", max_len=64).upper()
    if not isinstance(wait_ordinal, int) or wait_ordinal < 1:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "wait_ordinal must be int >= 1",
        )
    digest = hashlib.sha256(
        f"{run}|{wait_ordinal}|{reason}".encode("utf-8")
    ).hexdigest()[:32]
    return f"eos-int-{digest}"


def count_wait_ordinal(transitions: Sequence[Any]) -> int:
    """Count transitions into WAITING_FOR_HUMAN (1-based ordinal for current/next WAIT)."""
    count = 0
    for item in transitions:
        to_status = getattr(item, "to_status", None)
        if to_status == "WAITING_FOR_HUMAN":
            count += 1
    return count


def allowed_decisions_for_reason(reason_code: Optional[str]) -> tuple[str, ...]:
    code = (_optional_text(reason_code) or "").upper()
    if code in NON_OVERRIDABLE_FAILURE_CODES:
        return ()
    if code in RESUMABLE_REASON_CODES:
        return (DECISION_CLARIFY_SCOPE, DECISION_ABORT_RUN)
    return ()


@dataclass(frozen=True)
class ScopeSummary:
    """Bounded redacted scope view for HITL payloads — not full business truth."""

    project_code: Optional[str]
    month_key: Optional[str]
    facility_scope: Optional[tuple[str, ...]]
    discipline_scope: Optional[tuple[str, ...]]
    system_scope: Optional[tuple[str, ...]]
    iwp_scope: Optional[tuple[str, ...]]
    queue_scope: Optional[tuple[str, ...]]


@dataclass(frozen=True)
class ConstructorHumanDecisionRequest:
    schema_version: str
    interrupt_id: str
    run_id: str
    mission_id: str
    project_code: Optional[str]
    reason_code: str
    route: str
    severity: str
    human_readable_reason: str
    required_decision_type: str
    allowed_decisions: tuple[str, ...]
    current_scope_summary: ScopeSummary
    evidence_refs: tuple[str, ...]
    created_at: datetime
    status: str
    source_capability: str
    authorization_id_ref: Optional[str]
    wait_ordinal: int


@dataclass(frozen=True)
class ConstructorResumeCommand:
    schema_version: str
    decision_id: str
    interrupt_id: str
    run_id: str
    mission_id: str
    expected_checkpoint_id: Optional[str]
    actor_type: str
    actor_id: str
    decision: str
    parameters: Mapping[str, Any]
    comment: Optional[str]
    submitted_at: datetime
    idempotency_key: Optional[str]


def build_scope_summary(scope: Any) -> ScopeSummary:
    if scope is None:
        return ScopeSummary(
            project_code=None,
            month_key=None,
            facility_scope=None,
            discipline_scope=None,
            system_scope=None,
            iwp_scope=None,
            queue_scope=None,
        )
    return ScopeSummary(
        project_code=_optional_text(getattr(scope, "project_code", None)),
        month_key=_optional_text(getattr(scope, "month_key", None)),
        facility_scope=getattr(scope, "facility_scope", None),
        discipline_scope=getattr(scope, "discipline_scope", None),
        system_scope=getattr(scope, "system_scope", None),
        iwp_scope=getattr(scope, "iwp_scope", None),
        queue_scope=getattr(scope, "queue_scope", None),
    )


def build_human_decision_request(
    *,
    run_id: str,
    mission_id: str,
    reason_code: str,
    route: str,
    severity: str,
    human_readable_reason: str,
    wait_ordinal: int,
    current_scope_summary: ScopeSummary,
    evidence_refs: Sequence[str] = (),
    authorization_id_ref: Optional[str] = None,
    project_code: Optional[str] = None,
    created_at: Optional[datetime] = None,
    status: str = STATUS_HITL_OPEN,
    source_capability: str = SOURCE_HITL,
    interrupt_id: Optional[str] = None,
) -> ConstructorHumanDecisionRequest:
    stamp = _require_aware_utc(created_at or datetime.now(timezone.utc), "created_at")
    reason = _require_text(reason_code, "reason_code", max_len=64).upper()
    allowed = allowed_decisions_for_reason(reason)
    if not allowed:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            f"reason_code {reason} is not resumable via HITL",
        )
    eos_id = interrupt_id or compute_eos_interrupt_id(
        run_id=run_id,
        wait_ordinal=wait_ordinal,
        reason_code=reason,
    )
    refs = _normalize_string_tuple(
        evidence_refs,
        "evidence_refs",
        max_items=_MAX_EVIDENCE_REFS,
        max_item_len=_MAX_EVIDENCE_REF_LEN,
    )
    readable = _require_text(
        human_readable_reason,
        "human_readable_reason",
        max_len=_MAX_REASON_LEN,
    )
    return ConstructorHumanDecisionRequest(
        schema_version=SCHEMA_VERSION,
        interrupt_id=_require_id(eos_id, "interrupt_id"),
        run_id=_require_id(run_id, "run_id"),
        mission_id=_require_id(mission_id, "mission_id"),
        project_code=_optional_text(project_code),
        reason_code=reason,
        route=_require_text(route, "route", max_len=64),
        severity=_require_text(severity, "severity", max_len=64),
        human_readable_reason=readable,
        required_decision_type=allowed[0],
        allowed_decisions=allowed,
        current_scope_summary=current_scope_summary,
        evidence_refs=refs,
        created_at=stamp,
        status=_require_text(status, "status", max_len=32),
        source_capability=_require_text(source_capability, "source_capability", max_len=64),
        authorization_id_ref=_optional_text(authorization_id_ref),
        wait_ordinal=wait_ordinal,
    )


def _normalize_parameters(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "parameters must be a mapping",
        )
    if len(value) > _MAX_PARAM_KEYS:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            f"parameters exceed max keys {_MAX_PARAM_KEYS}",
        )
    out: dict[str, Any] = {}
    for key, item in value.items():
        key_text = _require_text(key, "parameters.key", max_len=64)
        if key_text in {"project_code", "month_key", "month_key_canonical"}:
            # Presence is validated later against immutable baseline; store as text only.
            out[key_text] = _require_text(item, key_text, max_len=128)
            continue
        if key_text.endswith("_scope") or key_text in {
            "facility_scope",
            "discipline_scope",
            "system_scope",
            "iwp_scope",
            "queue_scope",
        }:
            if item is None:
                out[key_text] = None
            else:
                out[key_text] = list(
                    _normalize_string_tuple(
                        item,
                        key_text,
                        max_items=_MAX_SCOPE_VALUES,
                        max_item_len=128,
                    )
                )
            continue
        # Reject unknown parameter keys fail closed.
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            f"unexpected resume parameter {key_text}",
        )
    return out


def build_resume_command(
    *,
    decision_id: str,
    interrupt_id: str,
    run_id: str,
    mission_id: str,
    decision: str,
    actor_id: str,
    actor_type: str = ACTOR_TYPE_HUMAN,
    parameters: Optional[Mapping[str, Any]] = None,
    comment: Optional[str] = None,
    expected_checkpoint_id: Optional[str] = None,
    submitted_at: Optional[datetime] = None,
    idempotency_key: Optional[str] = None,
) -> ConstructorResumeCommand:
    stamp = _require_aware_utc(
        submitted_at or datetime.now(timezone.utc),
        "submitted_at",
    )
    decision_text = _require_text(decision, "decision", max_len=64).upper()
    if decision_text not in ALLOWED_DECISIONS:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            f"decision {decision_text} is not allowed",
        )
    return ConstructorResumeCommand(
        schema_version=SCHEMA_VERSION,
        decision_id=_require_id(decision_id, "decision_id"),
        interrupt_id=_require_id(interrupt_id, "interrupt_id"),
        run_id=_require_id(run_id, "run_id"),
        mission_id=_require_id(mission_id, "mission_id"),
        expected_checkpoint_id=(
            _require_id(expected_checkpoint_id, "expected_checkpoint_id")
            if _optional_text(expected_checkpoint_id) is not None
            else None
        ),
        actor_type=_require_text(actor_type, "actor_type", max_len=64),
        actor_id=_require_id(actor_id, "actor_id"),
        decision=decision_text,
        parameters=_normalize_parameters(parameters),
        comment=_bounded_comment(comment),
        submitted_at=stamp,
        idempotency_key=(
            _require_id(idempotency_key, "idempotency_key")
            if _optional_text(idempotency_key) is not None
            else None
        ),
    )


def coerce_resume_command(payload: Any) -> ConstructorResumeCommand:
    """Accept ConstructorResumeCommand or a bounded mapping from Command(resume=...)."""
    if isinstance(payload, ConstructorResumeCommand):
        # Re-validate through builder for fail-closed bounds.
        return build_resume_command(
            decision_id=payload.decision_id,
            interrupt_id=payload.interrupt_id,
            run_id=payload.run_id,
            mission_id=payload.mission_id,
            decision=payload.decision,
            actor_id=payload.actor_id,
            actor_type=payload.actor_type,
            parameters=dict(payload.parameters),
            comment=payload.comment,
            expected_checkpoint_id=payload.expected_checkpoint_id,
            submitted_at=payload.submitted_at,
            idempotency_key=payload.idempotency_key,
        )
    if not isinstance(payload, Mapping):
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "resume payload must be ConstructorResumeCommand or mapping",
        )
    return build_resume_command(
        decision_id=payload.get("decision_id"),
        interrupt_id=payload.get("interrupt_id"),
        run_id=payload.get("run_id"),
        mission_id=payload.get("mission_id"),
        decision=payload.get("decision"),
        actor_id=payload.get("actor_id"),
        actor_type=payload.get("actor_type", ACTOR_TYPE_HUMAN),
        parameters=payload.get("parameters"),
        comment=payload.get("comment"),
        expected_checkpoint_id=payload.get("expected_checkpoint_id"),
        submitted_at=payload.get("submitted_at"),
        idempotency_key=payload.get("idempotency_key"),
    )


class ConstructorHitlStore(Protocol):
    """Minimal future HITL/audit persistence port. No SQL. No generic writes."""

    def upsert_open_request(
        self,
        request: ConstructorHumanDecisionRequest,
    ) -> None:
        """Idempotent create-if-absent / no-op for same interrupt_id."""
        ...

    def record_answer(
        self,
        *,
        interrupt_id: str,
        command: ConstructorResumeCommand,
    ) -> None:
        ...
