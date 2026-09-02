"""
Increment 10.2 — agent-neutral Run Control contracts.

Not observability store. Not AgentRun projection store. Not Constructor logic.
NON-DURABLE · PROCESS-LOCAL · CONTRACT / DEVELOPMENT IMPLEMENTATION ONLY.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from agents.observability.contracts import InitiatorType, TriggerType
from agents.observability.contracts import (
    AgentRun,
    RunRequest,
)
from security.agent_execution_context import AgentExecutionContext

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_SAFE_MESSAGE_LEN = 512

CODE_RUN_CONTROL_BLOCKER = "RUN_CONTROL_BLOCKER"
CODE_IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
CODE_IDEMPOTENCY_IN_PROGRESS = "IDEMPOTENCY_IN_PROGRESS"
CODE_SYSTEM_EVENT_DIRECT_START_FORBIDDEN = "SYSTEM_EVENT_DIRECT_START_FORBIDDEN"
CODE_CONTROL_PLANE_FAILURE = "CONTROL_PLANE_FAILURE"
CODE_LAUNCH_OUTCOME_UNKNOWN = "LAUNCH_OUTCOME_UNKNOWN"


class RunControlError(ValueError):
    """Fail-closed Run Control violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class StartOutcome(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"


class ReservationKind(str, Enum):
    NEW = "NEW"
    IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"
    TERMINAL_FAILURE_REPLAY = "TERMINAL_FAILURE_REPLAY"
    CONFLICT = "CONFLICT"


class ReservationState(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    RESULT_AVAILABLE = "RESULT_AVAILABLE"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"


class TerminalFailureKind(str, Enum):
    CONTROL_PLANE_FAILURE = "CONTROL_PLANE_FAILURE"
    LAUNCH_OUTCOME_UNKNOWN = "LAUNCH_OUTCOME_UNKNOWN"


@dataclass(frozen=True)
class ReservationDecision:
    kind: ReservationKind
    request_id: str
    run_id: str


@dataclass(frozen=True)
class TerminalFailureRecord:
    """Immutable safe process-local control failure. NOT durable observability."""

    failure_kind: TerminalFailureKind
    error_code: str
    request_id: str
    run_id: str
    failed_event_type: str | None = None
    safe_message: str | None = None

    def __post_init__(self) -> None:
        if self.safe_message is not None and len(self.safe_message) > _MAX_SAFE_MESSAGE_LEN:
            object.__setattr__(
                self,
                "safe_message",
                self.safe_message[:_MAX_SAFE_MESSAGE_LEN],
            )


@dataclass(frozen=True)
class ManagedRunStartInput:
    """
    Agent-neutral managed start parameters.

    Does NOT carry request_id, run_id, authorization, or runtime objects.
    RunRequest remains the canonical validated request artifact (built by service).
    """

    agent_code: str
    initiator_type: InitiatorType
    initiator_id: str
    trigger_type: TriggerType
    trigger_reason: str
    project_code: str
    month_key: str
    requested_mission_id: str
    idempotency_key: str
    scope_request: Mapping[str, Any] | None = None
    requested_agent_version: str | None = None
    orchestration_run_id: str | None = None
    predecessor_run_id: str | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        _require_text(self.agent_code, "agent_code")
        if not isinstance(self.initiator_type, InitiatorType):
            raise RunControlError(
                CODE_RUN_CONTROL_BLOCKER,
                "initiator_type must be InitiatorType",
            )
        _require_text(self.initiator_id, "initiator_id")
        if not isinstance(self.trigger_type, TriggerType):
            raise RunControlError(
                CODE_RUN_CONTROL_BLOCKER,
                "trigger_type must be TriggerType",
            )
        _require_text(self.trigger_reason, "trigger_reason")
        _require_text(self.project_code, "project_code")
        _require_text(self.month_key, "month_key")
        _require_id(self.requested_mission_id, "requested_mission_id")
        _require_id(self.idempotency_key, "idempotency_key")
        if self.initiator_type is InitiatorType.ORCHESTRATOR and not self.orchestration_run_id:
            raise RunControlError(
                CODE_RUN_CONTROL_BLOCKER,
                "orchestration_run_id is required for ORCHESTRATOR initiator",
            )
        if self.requested_agent_version is not None:
            _require_text(self.requested_agent_version, "requested_agent_version")
        if self.orchestration_run_id is not None:
            _require_id(self.orchestration_run_id, "orchestration_run_id")
        if self.predecessor_run_id is not None:
            _require_id(self.predecessor_run_id, "predecessor_run_id")


@dataclass(frozen=True)
class ManagedRunStartResult:
    """Immutable process-local control outcome. NOT durable projection."""

    outcome: StartOutcome
    run_request: RunRequest
    agent_run: AgentRun
    authorization_id: str | None = None


def _require_text(value: Any, field_name: str) -> str:
    if value is None:
        raise RunControlError(CODE_RUN_CONTROL_BLOCKER, f"{field_name} is required")
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        raise RunControlError(CODE_RUN_CONTROL_BLOCKER, f"{field_name} is required")
    return text


def _require_id(value: Any, field_name: str) -> str:
    text = _require_text(value, field_name)
    if not _ID_RE.match(text):
        raise RunControlError(CODE_RUN_CONTROL_BLOCKER, f"{field_name} has invalid format")
    return text


@runtime_checkable
class RunControlRegistry(Protocol):
    """
    PROCESS-LOCAL idempotency / start coordination only.

    NOT AgentRun projection store. NOT observability store. NOT durable.
    Restart loses state. Durable truth is Increment 10.4.
    """

    def decide_reservation(
        self,
        *,
        idempotency_key: str,
        canonical_request_digest: str,
        candidate_request_id: str,
        candidate_run_id: str,
    ) -> ReservationDecision:
        ...

    def get_cached_result(
        self,
        *,
        idempotency_key: str,
        canonical_request_digest: str,
    ) -> ManagedRunStartResult | None:
        ...

    def get_terminal_failure(
        self,
        *,
        idempotency_key: str,
        canonical_request_digest: str,
    ) -> TerminalFailureRecord | None:
        ...

    def store_result(
        self,
        *,
        idempotency_key: str,
        canonical_request_digest: str,
        result: ManagedRunStartResult,
    ) -> None:
        ...

    def store_terminal_failure(
        self,
        *,
        idempotency_key: str,
        canonical_request_digest: str,
        failure: TerminalFailureRecord,
    ) -> None:
        ...

    def reservation_state(
        self,
        *,
        idempotency_key: str,
    ) -> ReservationState | None:
        ...


@runtime_checkable
class ManagedRuntimeLauncher(Protocol):
    """
    Accept/schedule authorized runtime execution in a decoupled execution context.

    Successful return means launch acceptance only — not graph completion,
    professional result completion, or RUNNING confirmation.
    """

    def launch(
        self,
        *,
        run_request: RunRequest,
        agent_run: AgentRun,
        context: AgentExecutionContext,
    ) -> None:
        ...
