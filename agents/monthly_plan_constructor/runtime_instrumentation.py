"""
Increment 10.3A — Constructor runtime observability foundation.

Deterministic event identity, stage validation, and safe Recorder emission.
Not LangGraph wiring. Not lifecycle business logic. Not Run Control.

Observability RECORDS execution truth; it does NOT become execution truth.
Caller owns occurred_at semantics for LangGraph wiring in later 10.3 slices.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

from agents.observability.contracts import (
    CONSTRUCTOR_STAGE_CATALOG,
    EventStatus,
    EventType,
    build_observability_event,
)
from agents.observability.recorder import ObservabilityRecorder, RecordResult

CONSTRUCTOR_RUNTIME_EVENT_NAMESPACE = "constructor_runtime_event.v0.1"

CODE_RUNTIME_INSTRUMENTATION_BLOCKER = "RUNTIME_INSTRUMENTATION_BLOCKER"

_JSON_SEPARATORS = (",", ":")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_MAX_NODE_NAME_LEN = 128
_MAX_SEMANTIC_KEY_LEN = 128

_CONSTRUCTOR_STAGE_IDS = frozenset(stage.stage_id for stage in CONSTRUCTOR_STAGE_CATALOG)

RUN_CONTROL_OWNED_EVENT_TYPES = frozenset(
    {
        EventType.RUN_REQUESTED,
        EventType.RUN_AUTHORIZATION_STARTED,
        EventType.RUN_AUTHORIZED,
        EventType.RUN_DENIED,
        EventType.MISSION_BOUND,
        EventType.RUN_STARTED,
    }
)

RUNTIME_OWNED_EVENT_TYPES = frozenset(
    {
        EventType.STAGE_STARTED,
        EventType.STAGE_COMPLETED,
        EventType.STAGE_FAILED,
        EventType.TOOL_CALL_STARTED,
        EventType.TOOL_CALL_COMPLETED,
        EventType.TOOL_CALL_DENIED,
        EventType.ARTIFACT_CREATED,
        EventType.EXCEPTION_RAISED,
        EventType.HUMAN_WAIT_STARTED,
        EventType.HUMAN_DECISION_RECEIVED,
        EventType.RUN_RESUMED,
        EventType.REALITY_REFRESH_STARTED,
        EventType.REALITY_REFRESH_COMPLETED,
        EventType.REPLAY_DETECTED,
        EventType.HANDOFF_CREATED,
        EventType.HANDOFF_PERSISTED,
        EventType.HANDOFF_PERSIST_FAILED,
        EventType.RUN_ADVANCING,
        EventType.RUN_COMPLETED,
        EventType.RUN_FAILED,
        EventType.RUN_ABORTED,
        EventType.SECURITY_EVENT,
    }
)


class ConstructorRuntimeInstrumentationError(ValueError):
    """Fail-closed Constructor runtime instrumentation violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ConstructorRuntimeEventKey:
    """
    Stable semantic coordinates for deterministic Constructor runtime event identity.

    Does not include occurred_at, title, or payload — identity only.
    """

    run_id: str
    event_type: EventType
    stage_id: Optional[str] = None
    node_name: Optional[str] = None
    attempt_n: int = 1
    resume_n: int = 0
    semantic_occurrence_key: str = ""
    artifact_correlation_id: Optional[str] = None

    def __post_init__(self) -> None:
        _require_id(self.run_id, "run_id")
        if not isinstance(self.event_type, EventType):
            raise ConstructorRuntimeInstrumentationError(
                CODE_RUNTIME_INSTRUMENTATION_BLOCKER,
                "event_type must be EventType",
            )
        if self.event_type in RUN_CONTROL_OWNED_EVENT_TYPES:
            raise ConstructorRuntimeInstrumentationError(
                CODE_RUNTIME_INSTRUMENTATION_BLOCKER,
                f"event_type {self.event_type.value} is owned by Run Control",
            )
        if self.stage_id is not None:
            validate_constructor_stage_id(self.stage_id)
        if self.node_name is not None:
            _require_bounded_text(self.node_name, "node_name", max_len=_MAX_NODE_NAME_LEN)
        if not isinstance(self.attempt_n, int) or isinstance(self.attempt_n, bool):
            raise ConstructorRuntimeInstrumentationError(
                CODE_RUNTIME_INSTRUMENTATION_BLOCKER,
                "attempt_n must be int",
            )
        if self.attempt_n < 1:
            raise ConstructorRuntimeInstrumentationError(
                CODE_RUNTIME_INSTRUMENTATION_BLOCKER,
                "attempt_n must be >= 1",
            )
        if not isinstance(self.resume_n, int) or isinstance(self.resume_n, bool):
            raise ConstructorRuntimeInstrumentationError(
                CODE_RUNTIME_INSTRUMENTATION_BLOCKER,
                "resume_n must be int",
            )
        if self.resume_n < 0:
            raise ConstructorRuntimeInstrumentationError(
                CODE_RUNTIME_INSTRUMENTATION_BLOCKER,
                "resume_n must be >= 0",
            )
        if self.semantic_occurrence_key:
            _require_bounded_text(
                self.semantic_occurrence_key,
                "semantic_occurrence_key",
                max_len=_MAX_SEMANTIC_KEY_LEN,
            )
        if self.artifact_correlation_id is not None:
            _require_id(self.artifact_correlation_id, "artifact_correlation_id")


def validate_constructor_stage_id(stage_id: str) -> str:
    """Fail-closed lookup against frozen CONSTRUCTOR_STAGE_CATALOG."""
    text = _require_id(stage_id, "stage_id")
    if text not in _CONSTRUCTOR_STAGE_IDS:
        raise ConstructorRuntimeInstrumentationError(
            CODE_RUNTIME_INSTRUMENTATION_BLOCKER,
            f"unknown constructor stage_id {text!r}",
        )
    return text


def is_constructor_stage_id(stage_id: str) -> bool:
    text = str(stage_id or "").strip()
    return text in _CONSTRUCTOR_STAGE_IDS


def compute_constructor_runtime_event_id(key: ConstructorRuntimeEventKey) -> str:
    """
    Pure deterministic event_id for ObservabilityEvent.

    Independent of occurred_at and payload. Same semantic coordinates → same id.
    """
    if not isinstance(key, ConstructorRuntimeEventKey):
        raise ConstructorRuntimeInstrumentationError(
            CODE_RUNTIME_INSTRUMENTATION_BLOCKER,
            "ConstructorRuntimeEventKey is required",
        )
    identity = {
        "artifact_correlation_id": key.artifact_correlation_id,
        "attempt_n": key.attempt_n,
        "event_type": key.event_type.value,
        "node_name": key.node_name,
        "resume_n": key.resume_n,
        "run_id": key.run_id,
        "schema": CONSTRUCTOR_RUNTIME_EVENT_NAMESPACE,
        "semantic_occurrence_key": key.semantic_occurrence_key or "",
        "stage_id": key.stage_id,
    }
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=_JSON_SEPARATORS,
        allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return f"crt-evt-{digest}"


class ConstructorRuntimeInstrumentation:
    """
    Thin Constructor-specific observability emitter.

    No mutable stage/span/runtime state. Recorder owns event-id idempotency.
    """

    def __init__(self, *, recorder: ObservabilityRecorder) -> None:
        if recorder is None:
            raise ConstructorRuntimeInstrumentationError(
                CODE_RUNTIME_INSTRUMENTATION_BLOCKER,
                "ObservabilityRecorder is required",
            )
        self._recorder = recorder

    def emit(
        self,
        *,
        key: ConstructorRuntimeEventKey,
        occurred_at: datetime,
        agent_code: str,
        title: str,
        status: EventStatus = EventStatus.OK,
        request_id: Optional[str] = None,
        mission_id: Optional[str] = None,
        authorization_id: Optional[str] = None,
        orchestration_run_id: Optional[str] = None,
        checkpoint_id: Optional[str] = None,
        interrupt_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        handoff_id: Optional[str] = None,
        artifact_type: Optional[str] = None,
        artifact_id: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        package_id: Optional[str] = None,
        span_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        detail: Optional[Mapping[str, Any]] = None,
    ) -> RecordResult:
        """
        Build a canonical ObservabilityEvent and record it.

        Caller owns occurred_at semantics. Payload conflicts on the same
        deterministic event_id propagate fail-closed from the recorder.
        """
        if not isinstance(key, ConstructorRuntimeEventKey):
            raise ConstructorRuntimeInstrumentationError(
                CODE_RUNTIME_INSTRUMENTATION_BLOCKER,
                "ConstructorRuntimeEventKey is required",
            )
        event_id = compute_constructor_runtime_event_id(key)
        resolved_artifact_type, resolved_artifact_id = _resolve_artifact_fields(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            snapshot_id=snapshot_id,
            package_id=package_id,
        )
        event = build_observability_event(
            event_id=event_id,
            run_id=key.run_id,
            agent_code=agent_code,
            occurred_at=occurred_at,
            event_type=key.event_type,
            status=status,
            title=title,
            stage_id=key.stage_id,
            node_name=key.node_name,
            request_id=request_id,
            mission_id=mission_id,
            authorization_id=authorization_id,
            orchestration_run_id=orchestration_run_id,
            checkpoint_id=checkpoint_id,
            interrupt_id=interrupt_id,
            decision_id=decision_id,
            handoff_id=handoff_id,
            artifact_type=resolved_artifact_type,
            artifact_id=resolved_artifact_id,
            span_id=span_id,
            tool_name=tool_name,
            attempt_n=key.attempt_n,
            resume_n=key.resume_n,
            detail=dict(detail or {}),
        )
        return self._recorder.record_event(event)


def _resolve_artifact_fields(
    *,
    artifact_type: Optional[str],
    artifact_id: Optional[str],
    snapshot_id: Optional[str],
    package_id: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    if artifact_type is not None or artifact_id is not None:
        if (artifact_type is None) != (artifact_id is None):
            raise ConstructorRuntimeInstrumentationError(
                CODE_RUNTIME_INSTRUMENTATION_BLOCKER,
                "artifact_type and artifact_id must both be set or both absent",
            )
        return artifact_type, artifact_id
    if snapshot_id is not None:
        return "snapshot", _require_id(snapshot_id, "snapshot_id")
    if package_id is not None:
        return "package", _require_id(package_id, "package_id")
    return None, None


def _require_id(value: Any, field_name: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise ConstructorRuntimeInstrumentationError(
            CODE_RUNTIME_INSTRUMENTATION_BLOCKER,
            f"{field_name} is required",
        )
    if not _ID_RE.match(text):
        raise ConstructorRuntimeInstrumentationError(
            CODE_RUNTIME_INSTRUMENTATION_BLOCKER,
            f"{field_name} has invalid format",
        )
    return text


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    return text


def _require_bounded_text(value: Any, field_name: str, *, max_len: int) -> str:
    text = _optional_text(value)
    if text is None:
        raise ConstructorRuntimeInstrumentationError(
            CODE_RUNTIME_INSTRUMENTATION_BLOCKER,
            f"{field_name} is required",
        )
    if len(text) > max_len:
        raise ConstructorRuntimeInstrumentationError(
            CODE_RUNTIME_INSTRUMENTATION_BLOCKER,
            f"{field_name} exceeds max length {max_len}",
        )
    return text
