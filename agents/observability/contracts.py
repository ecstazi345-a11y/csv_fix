"""
Increment 10.1A — agent-neutral RunRequest, AgentRun, ObservabilityEvent contracts.

Normative source: docs/agentic_architecture/AGENT_RUN_CONTROL_AND_OBSERVABILITY_V0_1.md

Not Run Control. Not a store. Not instrumentation. Not Constructor business logic.
MODEL IS NOT A SECURITY BOUNDARY. DATA != INSTRUCTION.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional

from security.sanitize import assert_no_secrets_in_payload

OBSERVABILITY_SCHEMA_VERSION = "0.1"
RUN_REQUEST_SCHEMA_VERSION = "run_request.v0.1"
AGENT_RUN_SCHEMA_VERSION = "agent_run.v0.1"
OBSERVABILITY_EVENT_SCHEMA_VERSION = "observability_event.v0.1"
STAGE_DEFINITION_SCHEMA_VERSION = "stage_definition.v0.1"

CODE_OBSERVABILITY_CONTRACT_BLOCKER = "OBSERVABILITY_CONTRACT_BLOCKER"

# Conservative v0.1 payload bounds. Overflow fails closed. No silent truncation.
MAX_ID_LENGTH = 128
MAX_REASON_LENGTH = 500
MAX_TITLE_LENGTH = 200
MAX_DETAIL_KEYS = 32
MAX_NESTING_DEPTH = 2
MAX_STRING_LENGTH = 500
MAX_SERIALIZED_BYTES = 8192
MAX_LIST_LENGTH = 32
MAX_METADATA_KEYS = 16
MAX_SCOPE_KEYS = 32
MAX_SAFE_COUNT_KEYS = 32
MAX_SAFE_SUMMARY_KEYS = 32

_JSON_SEPARATORS = (",", ":")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DICT_TAG = "__obs_dict__"
_LIST_TAG = "__obs_list__"

# Primary secret law: security.sanitize.assert_no_secrets_in_payload.
# Supplemental key denylist is exact normalized names only. No substring scan.
# No URL-as-secret rule. Values are not scanned by a custom credential regex.
_FORBIDDEN_SECRET_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "bearer_token",
        "client_secret",
        "database_url",
        "dsn",
        "passwd",
        "password",
        "refresh_token",
        "secret",
        "service_role",
        "service_role_key",
        "supabase_key",
        "supabase_secret_key",
    }
)


class ObservabilityContractError(ValueError):
    """Fail-closed observability / run-control contract violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class InitiatorType(str, Enum):
    """Legal NEW RUN initiators. RESUME / RETRY are not members."""

    HUMAN = "HUMAN"
    ORCHESTRATOR = "ORCHESTRATOR"


class TriggerType(str, Enum):
    MANUAL = "MANUAL"
    ORCHESTRATION = "ORCHESTRATION"
    SYSTEM_EVENT = "SYSTEM_EVENT"


class OperationalStatus(str, Enum):
    REQUESTED = "REQUESTED"
    AUTHORIZING = "AUTHORIZING"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class EventFamily(str, Enum):
    RUN_CONTROL = "RUN_CONTROL"
    MISSION = "MISSION"
    STAGE = "STAGE"
    TOOL = "TOOL"
    ARTIFACT = "ARTIFACT"
    EXCEPTION = "EXCEPTION"
    HITL = "HITL"
    REALITY = "REALITY"
    RETRY = "RETRY"
    HANDOFF = "HANDOFF"
    SECURITY = "SECURITY"


class EventStatus(str, Enum):
    OK = "OK"
    DENIED = "DENIED"
    FAILED = "FAILED"
    INFO = "INFO"


class EventType(str, Enum):
    RUN_REQUESTED = "RUN_REQUESTED"
    RUN_AUTHORIZATION_STARTED = "RUN_AUTHORIZATION_STARTED"
    RUN_AUTHORIZED = "RUN_AUTHORIZED"
    RUN_DENIED = "RUN_DENIED"
    RUN_STARTED = "RUN_STARTED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAILED = "RUN_FAILED"
    RUN_ABORTED = "RUN_ABORTED"
    MISSION_BOUND = "MISSION_BOUND"
    STAGE_STARTED = "STAGE_STARTED"
    STAGE_COMPLETED = "STAGE_COMPLETED"
    STAGE_FAILED = "STAGE_FAILED"
    TOOL_CALL_STARTED = "TOOL_CALL_STARTED"
    TOOL_CALL_COMPLETED = "TOOL_CALL_COMPLETED"
    TOOL_CALL_DENIED = "TOOL_CALL_DENIED"
    ARTIFACT_CREATED = "ARTIFACT_CREATED"
    EXCEPTION_RAISED = "EXCEPTION_RAISED"
    HUMAN_WAIT_STARTED = "HUMAN_WAIT_STARTED"
    HUMAN_DECISION_RECEIVED = "HUMAN_DECISION_RECEIVED"
    RUN_RESUMED = "RUN_RESUMED"
    REALITY_REFRESH_STARTED = "REALITY_REFRESH_STARTED"
    REALITY_REFRESH_COMPLETED = "REALITY_REFRESH_COMPLETED"
    RETRY_REQUESTED = "RETRY_REQUESTED"
    RETRY_STARTED = "RETRY_STARTED"
    REPLAY_DETECTED = "REPLAY_DETECTED"
    HANDOFF_CREATED = "HANDOFF_CREATED"
    HANDOFF_PERSISTED = "HANDOFF_PERSISTED"
    HANDOFF_PERSIST_FAILED = "HANDOFF_PERSIST_FAILED"
    SECURITY_EVENT = "SECURITY_EVENT"


class StageDisplayState(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


EVENT_FAMILY_BY_TYPE: Mapping[EventType, EventFamily] = {
    EventType.RUN_REQUESTED: EventFamily.RUN_CONTROL,
    EventType.RUN_AUTHORIZATION_STARTED: EventFamily.RUN_CONTROL,
    EventType.RUN_AUTHORIZED: EventFamily.RUN_CONTROL,
    EventType.RUN_DENIED: EventFamily.RUN_CONTROL,
    EventType.RUN_STARTED: EventFamily.RUN_CONTROL,
    EventType.RUN_COMPLETED: EventFamily.RUN_CONTROL,
    EventType.RUN_FAILED: EventFamily.RUN_CONTROL,
    EventType.RUN_ABORTED: EventFamily.RUN_CONTROL,
    EventType.MISSION_BOUND: EventFamily.MISSION,
    EventType.STAGE_STARTED: EventFamily.STAGE,
    EventType.STAGE_COMPLETED: EventFamily.STAGE,
    EventType.STAGE_FAILED: EventFamily.STAGE,
    EventType.TOOL_CALL_STARTED: EventFamily.TOOL,
    EventType.TOOL_CALL_COMPLETED: EventFamily.TOOL,
    EventType.TOOL_CALL_DENIED: EventFamily.TOOL,
    EventType.ARTIFACT_CREATED: EventFamily.ARTIFACT,
    EventType.EXCEPTION_RAISED: EventFamily.EXCEPTION,
    EventType.HUMAN_WAIT_STARTED: EventFamily.HITL,
    EventType.HUMAN_DECISION_RECEIVED: EventFamily.HITL,
    EventType.RUN_RESUMED: EventFamily.HITL,
    EventType.REALITY_REFRESH_STARTED: EventFamily.REALITY,
    EventType.REALITY_REFRESH_COMPLETED: EventFamily.REALITY,
    EventType.RETRY_REQUESTED: EventFamily.RETRY,
    EventType.RETRY_STARTED: EventFamily.RETRY,
    EventType.REPLAY_DETECTED: EventFamily.RETRY,
    EventType.HANDOFF_CREATED: EventFamily.HANDOFF,
    EventType.HANDOFF_PERSISTED: EventFamily.HANDOFF,
    EventType.HANDOFF_PERSIST_FAILED: EventFamily.HANDOFF,
    EventType.SECURITY_EVENT: EventFamily.SECURITY,
}

EVENT_TYPES: tuple[EventType, ...] = tuple(EventType)

TERMINAL_OPERATIONAL_STATUSES: frozenset[OperationalStatus] = frozenset(
    {
        OperationalStatus.COMPLETED,
        OperationalStatus.FAILED,
        OperationalStatus.ABORTED,
        OperationalStatus.AUTHORIZATION_DENIED,
    }
)

_KNOWN_SCHEMA_VERSIONS = frozenset(
    {
        RUN_REQUEST_SCHEMA_VERSION,
        AGENT_RUN_SCHEMA_VERSION,
        OBSERVABILITY_EVENT_SCHEMA_VERSION,
        STAGE_DEFINITION_SCHEMA_VERSION,
    }
)


def _fail(message: str) -> None:
    raise ObservabilityContractError(CODE_OBSERVABILITY_CONTRACT_BLOCKER, message)


def _require_aware_utc(value: Any, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        _fail(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        _fail(f"{field_name} must be timezone-aware UTC")
    return value.astimezone(timezone.utc)


def _store_utc(instance: Any, field_name: str, value: Any) -> None:
    """Canonical UTC writeback for frozen public constructors. Not a general mutator.

    10.1A does not compare timestamp order. Run Control owns that in 10.2.
    """
    object.__setattr__(instance, field_name, _require_aware_utc(value, field_name))


def _store_optional_utc(instance: Any, field_name: str, value: Any) -> None:
    if value is None:
        return
    _store_utc(instance, field_name, value)


def _normalize_payload_key(key: str) -> str:
    return key.strip().lower().replace("-", "_").replace(" ", "_")


def _is_forbidden_secret_key(key: str) -> bool:
    return _normalize_payload_key(key) in _FORBIDDEN_SECRET_KEYS


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        text = str(value).strip()
    else:
        text = value.strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    return text


def _require_text(value: Any, field_name: str, *, max_len: int = MAX_ID_LENGTH) -> str:
    text = _optional_text(value)
    if text is None:
        _fail(f"{field_name} is required")
    if len(text) > max_len:
        _fail(f"{field_name} exceeds max length {max_len}")
    return text


def _require_id(value: Any, field_name: str) -> str:
    text = _require_text(value, field_name, max_len=MAX_ID_LENGTH)
    if not _ID_RE.match(text):
        _fail(f"{field_name} has invalid format")
    return text


def _optional_id(value: Any, field_name: str) -> Optional[str]:
    text = _optional_text(value)
    if text is None:
        return None
    return _require_id(text, field_name)


def _require_enum(value: Any, enum_cls: type[Enum], field_name: str) -> Any:
    if isinstance(value, enum_cls):
        return value
    text = _optional_text(value)
    if text is None:
        _fail(f"{field_name} is required")
    try:
        return enum_cls(text)
    except ValueError:
        _fail(f"{field_name} is not a valid {enum_cls.__name__}")


def _require_int(value: Any, field_name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{field_name} must be int")
    if value < minimum:
        _fail(f"{field_name} must be >= {minimum}")
    return value


def _require_schema(value: Any, expected: str) -> str:
    text = _require_text(value, "schema_version", max_len=64)
    if text != expected:
        _fail(f"unknown schema_version {text!r}; expected {expected}")
    if text not in _KNOWN_SCHEMA_VERSIONS:
        _fail(f"unknown schema_version {text!r}")
    return text


def _canonical_jsonable(value: Any, *, depth: int = 0) -> Any:
    if depth > MAX_NESTING_DEPTH + 4:
        _fail("canonical value exceeds nesting depth")
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("canonical value rejects NaN/Infinity")
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return _require_aware_utc(value, "datetime").isoformat()
    if isinstance(value, dict):
        return {str(key): _canonical_jsonable(item, depth=depth + 1) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_jsonable(item, depth=depth + 1) for item in value]
    _fail(f"unsupported canonical type {type(value).__name__}")
    return None


def _dumps_canonical(value: Any) -> str:
    return json.dumps(
        _canonical_jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=_JSON_SEPARATORS,
        allow_nan=False,
    )


def _freeze_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("NaN/Infinity is not allowed")
        return value
    if isinstance(value, dict):
        items = []
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            if not isinstance(key, str):
                _fail("mapping keys must be str")
            items.append((key, _freeze_jsonable(item)))
        return (_DICT_TAG, tuple(items))
    if isinstance(value, (list, tuple)):
        return (_LIST_TAG, tuple(_freeze_jsonable(item) for item in value))
    _fail(f"unsupported payload type {type(value).__name__}")
    return None


def _unfreeze_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, tuple) and len(value) == 2 and value[0] == _DICT_TAG:
        return {key: _unfreeze_jsonable(item) for key, item in value[1]}
    if isinstance(value, tuple) and len(value) == 2 and value[0] == _LIST_TAG:
        return [_unfreeze_jsonable(item) for item in value[1]]
    _fail(f"cannot unfreeze type {type(value).__name__}")
    return None


def _assert_allowed_jsonable(
    value: Any,
    *,
    depth: int,
    field_name: str,
    max_keys: int,
) -> None:
    if depth > MAX_NESTING_DEPTH:
        _fail(f"{field_name} exceeds max nesting depth {MAX_NESTING_DEPTH}")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail(f"{field_name} rejects NaN/Infinity")
        return
    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH:
            _fail(f"{field_name} exceeds max string length {MAX_STRING_LENGTH}")
        return
    if isinstance(value, bytes):
        _fail(f"{field_name} rejects bytes")
    if isinstance(value, set):
        _fail(f"{field_name} rejects set")
    if callable(value):
        _fail(f"{field_name} rejects callable")
    type_name = type(value).__name__
    if type_name in {"DataFrame", "Series"}:
        _fail(f"{field_name} rejects {type_name}")
    if isinstance(value, dict):
        if len(value) > max_keys:
            _fail(f"{field_name} exceeds max keys {max_keys}")
        for key, item in value.items():
            if not isinstance(key, str):
                _fail(f"{field_name} keys must be str")
            if not key.strip():
                _fail(f"{field_name} keys must be non-empty")
            if _is_forbidden_secret_key(key):
                _fail(f"{field_name} contains forbidden key")
            _assert_allowed_jsonable(
                item,
                depth=depth + 1,
                field_name=field_name,
                max_keys=max_keys,
            )
        return
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_LIST_LENGTH:
            _fail(f"{field_name} exceeds max list length {MAX_LIST_LENGTH}")
        for item in value:
            _assert_allowed_jsonable(
                item,
                depth=depth + 1,
                field_name=field_name,
                max_keys=max_keys,
            )
        return
    _fail(f"{field_name} rejects unsupported type {type_name}")


def _validate_bounded_mapping(
    value: Any,
    field_name: str,
    *,
    max_keys: int,
    required: bool,
) -> tuple[tuple[str, Any], ...]:
    if value is None:
        if required:
            _fail(f"{field_name} is required")
        return ()
    if not isinstance(value, Mapping):
        _fail(f"{field_name} must be a mapping")
    as_dict = dict(value)
    _assert_allowed_jsonable(as_dict, depth=0, field_name=field_name, max_keys=max_keys)
    encoded = _dumps_canonical(as_dict)
    if len(encoded.encode("utf-8")) > MAX_SERIALIZED_BYTES:
        _fail(f"{field_name} exceeds max serialized bytes {MAX_SERIALIZED_BYTES}")
    try:
        assert_no_secrets_in_payload(as_dict)
    except AssertionError:
        _fail(f"{field_name} failed secret scan")
    frozen = _freeze_jsonable(as_dict)
    if not (isinstance(frozen, tuple) and len(frozen) == 2 and frozen[0] == _DICT_TAG):
        _fail(f"{field_name} freeze failed")
    return frozen


def compute_run_request_digest(
    *,
    agent_code: Any,
    initiator_type: Any,
    initiator_id: Any,
    project_code: Any,
    month_key: Any,
    scope_request: Any,
    requested_mission_id: Any,
    orchestration_run_id: Any,
    predecessor_run_id: Any,
    trigger_type: Any,
) -> str:
    """
    SHA-256 of canonical JSON over the accepted idempotency scope.

    Excludes requested_at, metadata, presentation labels, and idempotency_key.
    """
    initiator = _require_enum(initiator_type, InitiatorType, "initiator_type")
    trigger = _require_enum(trigger_type, TriggerType, "trigger_type")
    scope = dict(scope_request or {})
    if not isinstance(scope, dict):
        _fail("scope_request must be a mapping")
    _assert_allowed_jsonable(scope, depth=0, field_name="scope_request", max_keys=MAX_SCOPE_KEYS)
    payload = {
        "agent_code": _require_text(agent_code, "agent_code", max_len=MAX_ID_LENGTH),
        "initiator_id": _require_text(initiator_id, "initiator_id", max_len=MAX_ID_LENGTH),
        "initiator_type": initiator.value,
        "month_key": _require_text(month_key, "month_key", max_len=MAX_ID_LENGTH),
        "orchestration_run_id": _optional_id(orchestration_run_id, "orchestration_run_id"),
        "predecessor_run_id": _optional_id(predecessor_run_id, "predecessor_run_id"),
        "project_code": _require_text(project_code, "project_code", max_len=MAX_ID_LENGTH),
        "requested_mission_id": _require_id(requested_mission_id, "requested_mission_id"),
        "scope_request": _canonical_jsonable(scope),
        "trigger_type": trigger.value,
    }
    encoded = _dumps_canonical(payload).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class StageDefinition:
    """Agent-neutral professional stage. Colors and HTML belong to presentation."""

    schema_version: str
    stage_id: str
    sequence: int
    code: str
    display_name: str

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, STAGE_DEFINITION_SCHEMA_VERSION)
        _require_id(self.stage_id, "stage_id")
        _require_id(self.code, "code")
        _require_text(self.display_name, "display_name", max_len=MAX_TITLE_LENGTH)
        _require_int(self.sequence, "sequence", minimum=1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "stage_id": self.stage_id,
            "sequence": self.sequence,
            "code": self.code,
            "display_name": self.display_name,
        }


CONSTRUCTOR_STAGE_CATALOG: tuple[StageDefinition, ...] = (
    StageDefinition(
        schema_version=STAGE_DEFINITION_SCHEMA_VERSION,
        stage_id="AUTHORIZATION",
        sequence=1,
        code="AUTHORIZATION",
        display_name="Authorization",
    ),
    StageDefinition(
        schema_version=STAGE_DEFINITION_SCHEMA_VERSION,
        stage_id="MISSION_BINDING",
        sequence=2,
        code="MISSION_BINDING",
        display_name="Mission binding",
    ),
    StageDefinition(
        schema_version=STAGE_DEFINITION_SCHEMA_VERSION,
        stage_id="REALITY_READ",
        sequence=3,
        code="REALITY_READ",
        display_name="Reality read",
    ),
    StageDefinition(
        schema_version=STAGE_DEFINITION_SCHEMA_VERSION,
        stage_id="CANDIDATE_ASSEMBLY",
        sequence=4,
        code="CANDIDATE_ASSEMBLY",
        display_name="Candidate assembly",
    ),
    StageDefinition(
        schema_version=STAGE_DEFINITION_SCHEMA_VERSION,
        stage_id="LABOR_NORM_RESOLUTION",
        sequence=5,
        code="LABOR_NORM_RESOLUTION",
        display_name="Labor norm resolution",
    ),
    StageDefinition(
        schema_version=STAGE_DEFINITION_SCHEMA_VERSION,
        stage_id="EXCEPTION_ANALYSIS",
        sequence=6,
        code="EXCEPTION_ANALYSIS",
        display_name="Exception analysis",
    ),
    StageDefinition(
        schema_version=STAGE_DEFINITION_SCHEMA_VERSION,
        stage_id="HUMAN_GATE",
        sequence=7,
        code="HUMAN_GATE",
        display_name="Human gate",
    ),
    StageDefinition(
        schema_version=STAGE_DEFINITION_SCHEMA_VERSION,
        stage_id="REALITY_REVALIDATION",
        sequence=8,
        code="REALITY_REVALIDATION",
        display_name="Reality revalidation",
    ),
    StageDefinition(
        schema_version=STAGE_DEFINITION_SCHEMA_VERSION,
        stage_id="HANDOFF_PREPARATION",
        sequence=9,
        code="HANDOFF_PREPARATION",
        display_name="Handoff preparation",
    ),
    StageDefinition(
        schema_version=STAGE_DEFINITION_SCHEMA_VERSION,
        stage_id="HANDOFF_PERSISTENCE",
        sequence=10,
        code="HANDOFF_PERSISTENCE",
        display_name="Handoff persistence",
    ),
    StageDefinition(
        schema_version=STAGE_DEFINITION_SCHEMA_VERSION,
        stage_id="RUN_COMPLETION",
        sequence=11,
        code="RUN_COMPLETION",
        display_name="Run completion",
    ),
)


@dataclass(frozen=True)
class RunRequest:
    """Ask to start a new professional managed execution. Does not grant authorization."""

    schema_version: str
    request_id: str
    requested_at: datetime
    agent_code: str
    requested_agent_version: Optional[str]
    initiator_type: InitiatorType
    initiator_id: str
    trigger_type: TriggerType
    trigger_reason: str
    project_code: str
    month_key: str
    scope_request: tuple[Any, ...]
    orchestration_run_id: Optional[str]
    predecessor_run_id: Optional[str]
    requested_mission_id: str
    idempotency_key: str
    metadata: tuple[Any, ...]
    canonical_request_digest: str

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, RUN_REQUEST_SCHEMA_VERSION)
        _require_id(self.request_id, "request_id")
        _store_utc(self, "requested_at", self.requested_at)
        _require_text(self.agent_code, "agent_code", max_len=MAX_ID_LENGTH)
        if self.requested_agent_version is not None:
            _require_text(self.requested_agent_version, "requested_agent_version", max_len=MAX_ID_LENGTH)
        if not isinstance(self.initiator_type, InitiatorType):
            _fail("initiator_type must be InitiatorType")
        if self.initiator_type not in {InitiatorType.HUMAN, InitiatorType.ORCHESTRATOR}:
            _fail("initiator_type must be HUMAN or ORCHESTRATOR")
        _require_text(self.initiator_id, "initiator_id", max_len=MAX_ID_LENGTH)
        if not isinstance(self.trigger_type, TriggerType):
            _fail("trigger_type must be TriggerType")
        _require_text(self.trigger_reason, "trigger_reason", max_len=MAX_REASON_LENGTH)
        _require_text(self.project_code, "project_code", max_len=MAX_ID_LENGTH)
        _require_text(self.month_key, "month_key", max_len=MAX_ID_LENGTH)
        _require_id(self.requested_mission_id, "requested_mission_id")
        _require_id(self.idempotency_key, "idempotency_key")
        if self.initiator_type is InitiatorType.ORCHESTRATOR:
            if self.orchestration_run_id is None:
                _fail("orchestration_run_id is required for ORCHESTRATOR")
            _require_id(self.orchestration_run_id, "orchestration_run_id")
        elif self.orchestration_run_id is not None:
            _require_id(self.orchestration_run_id, "orchestration_run_id")
        if self.predecessor_run_id is not None:
            _require_id(self.predecessor_run_id, "predecessor_run_id")
        expected = compute_run_request_digest(
            agent_code=self.agent_code,
            initiator_type=self.initiator_type,
            initiator_id=self.initiator_id,
            project_code=self.project_code,
            month_key=self.month_key,
            scope_request=_unfreeze_jsonable(self.scope_request),
            requested_mission_id=self.requested_mission_id,
            orchestration_run_id=self.orchestration_run_id,
            predecessor_run_id=self.predecessor_run_id,
            trigger_type=self.trigger_type,
        )
        if self.canonical_request_digest != expected:
            _fail("canonical_request_digest does not match semantic fields")
        try:
            assert_no_secrets_in_payload(self.to_dict())
        except AssertionError:
            _fail("RunRequest failed secret scan")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "requested_at": self.requested_at.astimezone(timezone.utc).isoformat(),
            "agent_code": self.agent_code,
            "requested_agent_version": self.requested_agent_version,
            "initiator_type": self.initiator_type.value,
            "initiator_id": self.initiator_id,
            "trigger_type": self.trigger_type.value,
            "trigger_reason": self.trigger_reason,
            "project_code": self.project_code,
            "month_key": self.month_key,
            "scope_request": _unfreeze_jsonable(self.scope_request),
            "orchestration_run_id": self.orchestration_run_id,
            "predecessor_run_id": self.predecessor_run_id,
            "requested_mission_id": self.requested_mission_id,
            "idempotency_key": self.idempotency_key,
            "metadata": _unfreeze_jsonable(self.metadata),
            "canonical_request_digest": self.canonical_request_digest,
        }


def build_run_request(
    *,
    request_id: Any,
    requested_at: datetime,
    agent_code: Any,
    initiator_type: Any,
    initiator_id: Any,
    trigger_type: Any,
    trigger_reason: Any,
    project_code: Any,
    month_key: Any,
    requested_mission_id: Any,
    idempotency_key: Any,
    scope_request: Optional[Mapping[str, Any]] = None,
    requested_agent_version: Any = None,
    orchestration_run_id: Any = None,
    predecessor_run_id: Any = None,
    metadata: Optional[Mapping[str, Any]] = None,
    schema_version: str = RUN_REQUEST_SCHEMA_VERSION,
) -> RunRequest:
    initiator = _require_enum(initiator_type, InitiatorType, "initiator_type")
    trigger = _require_enum(trigger_type, TriggerType, "trigger_type")
    scope = _validate_bounded_mapping(
        scope_request if scope_request is not None else {},
        "scope_request",
        max_keys=MAX_SCOPE_KEYS,
        required=True,
    )
    meta = _validate_bounded_mapping(
        metadata if metadata is not None else {},
        "metadata",
        max_keys=MAX_METADATA_KEYS,
        required=True,
    )
    digest = compute_run_request_digest(
        agent_code=agent_code,
        initiator_type=initiator,
        initiator_id=initiator_id,
        project_code=project_code,
        month_key=month_key,
        scope_request=_unfreeze_jsonable(scope),
        requested_mission_id=requested_mission_id,
        orchestration_run_id=orchestration_run_id,
        predecessor_run_id=predecessor_run_id,
        trigger_type=trigger,
    )
    version = requested_agent_version
    if version is not None:
        version = _require_text(version, "requested_agent_version", max_len=MAX_ID_LENGTH)
    return RunRequest(
        schema_version=schema_version,
        request_id=_require_id(request_id, "request_id"),
        requested_at=_require_aware_utc(requested_at, "requested_at"),
        agent_code=_require_text(agent_code, "agent_code", max_len=MAX_ID_LENGTH),
        requested_agent_version=version,
        initiator_type=initiator,
        initiator_id=_require_text(initiator_id, "initiator_id", max_len=MAX_ID_LENGTH),
        trigger_type=trigger,
        trigger_reason=_require_text(trigger_reason, "trigger_reason", max_len=MAX_REASON_LENGTH),
        project_code=_require_text(project_code, "project_code", max_len=MAX_ID_LENGTH),
        month_key=_require_text(month_key, "month_key", max_len=MAX_ID_LENGTH),
        scope_request=scope,
        orchestration_run_id=_optional_id(orchestration_run_id, "orchestration_run_id"),
        predecessor_run_id=_optional_id(predecessor_run_id, "predecessor_run_id"),
        requested_mission_id=_require_id(requested_mission_id, "requested_mission_id"),
        idempotency_key=_require_id(idempotency_key, "idempotency_key"),
        metadata=meta,
        canonical_request_digest=digest,
    )


@dataclass(frozen=True)
class AgentRun:
    """Operational envelope of one professional invocation. Not a lifecycle engine."""

    schema_version: str
    run_id: str
    request_id: str
    agent_code: str
    agent_version: str
    mission_id: str
    orchestration_run_id: Optional[str]
    project_code: str
    month_key: str
    scope_summary: tuple[Any, ...]
    initiator_type: InitiatorType
    initiator_id: str
    trigger_type: TriggerType
    trigger_reason: str
    authorization_id: Optional[str]
    authorized_by: Optional[str]
    security_policy_version: Optional[str]
    operational_status: OperationalStatus
    lifecycle_status: Optional[str]
    current_stage_id: Optional[str]
    current_node: Optional[str]
    attempt_n: int
    resume_n: int
    requested_at: datetime
    started_at: Optional[datetime]
    updated_at: datetime
    completed_at: Optional[datetime]
    thread_id: str
    checkpoint_id: Optional[str]
    snapshot_id: Optional[str]
    package_id: Optional[str]
    interrupt_id: Optional[str]
    decision_id: Optional[str]
    handoff_id: Optional[str]
    safe_summary: tuple[Any, ...]
    safe_counts: tuple[Any, ...]
    error_code: Optional[str]
    safe_error_summary: Optional[str]
    projection_version: int

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, AGENT_RUN_SCHEMA_VERSION)
        _require_id(self.run_id, "run_id")
        _require_id(self.request_id, "request_id")
        _require_text(self.agent_code, "agent_code", max_len=MAX_ID_LENGTH)
        _require_text(self.agent_version, "agent_version", max_len=MAX_ID_LENGTH)
        _require_id(self.mission_id, "mission_id")
        if self.orchestration_run_id is not None:
            _require_id(self.orchestration_run_id, "orchestration_run_id")
        _require_text(self.project_code, "project_code", max_len=MAX_ID_LENGTH)
        _require_text(self.month_key, "month_key", max_len=MAX_ID_LENGTH)
        if not isinstance(self.initiator_type, InitiatorType):
            _fail("initiator_type must be InitiatorType")
        _require_text(self.initiator_id, "initiator_id", max_len=MAX_ID_LENGTH)
        if not isinstance(self.trigger_type, TriggerType):
            _fail("trigger_type must be TriggerType")
        _require_text(self.trigger_reason, "trigger_reason", max_len=MAX_REASON_LENGTH)
        if self.authorization_id is not None:
            _require_id(self.authorization_id, "authorization_id")
        if self.authorized_by is not None:
            _require_id(self.authorized_by, "authorized_by")
        if self.security_policy_version is not None:
            _require_text(self.security_policy_version, "security_policy_version", max_len=MAX_ID_LENGTH)
        if not isinstance(self.operational_status, OperationalStatus):
            _fail("operational_status must be OperationalStatus")
        if self.lifecycle_status is not None:
            _require_text(self.lifecycle_status, "lifecycle_status", max_len=MAX_ID_LENGTH)
        if self.current_stage_id is not None:
            _require_id(self.current_stage_id, "current_stage_id")
        if self.current_node is not None:
            _require_text(self.current_node, "current_node", max_len=MAX_ID_LENGTH)
        _require_int(self.attempt_n, "attempt_n", minimum=1)
        _require_int(self.resume_n, "resume_n", minimum=0)
        _require_int(self.projection_version, "projection_version", minimum=0)
        _store_utc(self, "requested_at", self.requested_at)
        _store_utc(self, "updated_at", self.updated_at)
        _store_optional_utc(self, "started_at", self.started_at)
        if self.thread_id != self.run_id:
            _fail("thread_id must equal run_id")
        _require_id(self.thread_id, "thread_id")
        for name in (
            "checkpoint_id",
            "snapshot_id",
            "package_id",
            "interrupt_id",
            "decision_id",
            "handoff_id",
        ):
            raw = getattr(self, name)
            if raw is not None:
                _require_id(raw, name)
        if self.error_code is not None:
            _require_text(self.error_code, "error_code", max_len=MAX_ID_LENGTH)
        if self.safe_error_summary is not None:
            _require_text(self.safe_error_summary, "safe_error_summary", max_len=MAX_REASON_LENGTH)
        terminal = self.operational_status in TERMINAL_OPERATIONAL_STATUSES
        if terminal:
            if self.completed_at is None:
                _fail("completed_at is required for terminal operational_status")
            _store_utc(self, "completed_at", self.completed_at)
        elif self.completed_at is not None:
            _fail("completed_at is only valid for terminal operational_status")
        try:
            assert_no_secrets_in_payload(self.to_dict())
        except AssertionError:
            _fail("AgentRun failed secret scan")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "request_id": self.request_id,
            "agent_code": self.agent_code,
            "agent_version": self.agent_version,
            "mission_id": self.mission_id,
            "orchestration_run_id": self.orchestration_run_id,
            "project_code": self.project_code,
            "month_key": self.month_key,
            "scope_summary": _unfreeze_jsonable(self.scope_summary),
            "initiator_type": self.initiator_type.value,
            "initiator_id": self.initiator_id,
            "trigger_type": self.trigger_type.value,
            "trigger_reason": self.trigger_reason,
            "authorization_id": self.authorization_id,
            "authorized_by": self.authorized_by,
            "security_policy_version": self.security_policy_version,
            "operational_status": self.operational_status.value,
            "lifecycle_status": self.lifecycle_status,
            "current_stage_id": self.current_stage_id,
            "current_node": self.current_node,
            "attempt_n": self.attempt_n,
            "resume_n": self.resume_n,
            "requested_at": self.requested_at.astimezone(timezone.utc).isoformat(),
            "started_at": None
            if self.started_at is None
            else self.started_at.astimezone(timezone.utc).isoformat(),
            "updated_at": self.updated_at.astimezone(timezone.utc).isoformat(),
            "completed_at": None
            if self.completed_at is None
            else self.completed_at.astimezone(timezone.utc).isoformat(),
            "thread_id": self.thread_id,
            "checkpoint_id": self.checkpoint_id,
            "snapshot_id": self.snapshot_id,
            "package_id": self.package_id,
            "interrupt_id": self.interrupt_id,
            "decision_id": self.decision_id,
            "handoff_id": self.handoff_id,
            "safe_summary": _unfreeze_jsonable(self.safe_summary),
            "safe_counts": _unfreeze_jsonable(self.safe_counts),
            "error_code": self.error_code,
            "safe_error_summary": self.safe_error_summary,
            "projection_version": self.projection_version,
        }


def build_agent_run(
    *,
    run_id: Any,
    request_id: Any,
    agent_code: Any,
    agent_version: Any,
    mission_id: Any,
    project_code: Any,
    month_key: Any,
    initiator_type: Any,
    initiator_id: Any,
    trigger_type: Any,
    trigger_reason: Any,
    operational_status: Any,
    requested_at: datetime,
    updated_at: datetime,
    thread_id: Any,
    attempt_n: int = 1,
    resume_n: int = 0,
    projection_version: int = 0,
    orchestration_run_id: Any = None,
    scope_summary: Optional[Mapping[str, Any]] = None,
    authorization_id: Any = None,
    authorized_by: Any = None,
    security_policy_version: Any = None,
    lifecycle_status: Any = None,
    current_stage_id: Any = None,
    current_node: Any = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
    checkpoint_id: Any = None,
    snapshot_id: Any = None,
    package_id: Any = None,
    interrupt_id: Any = None,
    decision_id: Any = None,
    handoff_id: Any = None,
    safe_summary: Optional[Mapping[str, Any]] = None,
    safe_counts: Optional[Mapping[str, Any]] = None,
    error_code: Any = None,
    safe_error_summary: Any = None,
    schema_version: str = AGENT_RUN_SCHEMA_VERSION,
) -> AgentRun:
    return AgentRun(
        schema_version=schema_version,
        run_id=_require_id(run_id, "run_id"),
        request_id=_require_id(request_id, "request_id"),
        agent_code=_require_text(agent_code, "agent_code", max_len=MAX_ID_LENGTH),
        agent_version=_require_text(agent_version, "agent_version", max_len=MAX_ID_LENGTH),
        mission_id=_require_id(mission_id, "mission_id"),
        orchestration_run_id=_optional_id(orchestration_run_id, "orchestration_run_id"),
        project_code=_require_text(project_code, "project_code", max_len=MAX_ID_LENGTH),
        month_key=_require_text(month_key, "month_key", max_len=MAX_ID_LENGTH),
        scope_summary=_validate_bounded_mapping(
            scope_summary if scope_summary is not None else {},
            "scope_summary",
            max_keys=MAX_SCOPE_KEYS,
            required=True,
        ),
        initiator_type=_require_enum(initiator_type, InitiatorType, "initiator_type"),
        initiator_id=_require_text(initiator_id, "initiator_id", max_len=MAX_ID_LENGTH),
        trigger_type=_require_enum(trigger_type, TriggerType, "trigger_type"),
        trigger_reason=_require_text(trigger_reason, "trigger_reason", max_len=MAX_REASON_LENGTH),
        authorization_id=_optional_id(authorization_id, "authorization_id"),
        authorized_by=_optional_id(authorized_by, "authorized_by"),
        security_policy_version=(
            None
            if security_policy_version is None
            else _require_text(
                security_policy_version, "security_policy_version", max_len=MAX_ID_LENGTH
            )
        ),
        operational_status=_require_enum(
            operational_status, OperationalStatus, "operational_status"
        ),
        lifecycle_status=(
            None
            if lifecycle_status is None
            else _require_text(lifecycle_status, "lifecycle_status", max_len=MAX_ID_LENGTH)
        ),
        current_stage_id=_optional_id(current_stage_id, "current_stage_id"),
        current_node=(
            None
            if current_node is None
            else _require_text(current_node, "current_node", max_len=MAX_ID_LENGTH)
        ),
        attempt_n=_require_int(attempt_n, "attempt_n", minimum=1),
        resume_n=_require_int(resume_n, "resume_n", minimum=0),
        requested_at=_require_aware_utc(requested_at, "requested_at"),
        started_at=None if started_at is None else _require_aware_utc(started_at, "started_at"),
        updated_at=_require_aware_utc(updated_at, "updated_at"),
        completed_at=(
            None if completed_at is None else _require_aware_utc(completed_at, "completed_at")
        ),
        thread_id=_require_id(thread_id, "thread_id"),
        checkpoint_id=_optional_id(checkpoint_id, "checkpoint_id"),
        snapshot_id=_optional_id(snapshot_id, "snapshot_id"),
        package_id=_optional_id(package_id, "package_id"),
        interrupt_id=_optional_id(interrupt_id, "interrupt_id"),
        decision_id=_optional_id(decision_id, "decision_id"),
        handoff_id=_optional_id(handoff_id, "handoff_id"),
        safe_summary=_validate_bounded_mapping(
            safe_summary if safe_summary is not None else {},
            "safe_summary",
            max_keys=MAX_SAFE_SUMMARY_KEYS,
            required=True,
        ),
        safe_counts=_validate_bounded_mapping(
            safe_counts if safe_counts is not None else {},
            "safe_counts",
            max_keys=MAX_SAFE_COUNT_KEYS,
            required=True,
        ),
        error_code=(
            None if error_code is None else _require_text(error_code, "error_code", max_len=MAX_ID_LENGTH)
        ),
        safe_error_summary=(
            None
            if safe_error_summary is None
            else _require_text(safe_error_summary, "safe_error_summary", max_len=MAX_REASON_LENGTH)
        ),
        projection_version=_require_int(projection_version, "projection_version", minimum=0),
    )


@dataclass(frozen=True)
class ObservabilityEvent:
    """Immutable append-only observability fact. Not a professional decision."""

    schema_version: str
    event_id: str
    run_id: str
    agent_code: str
    occurred_at: datetime
    family: EventFamily
    event_type: EventType
    status: EventStatus
    title: str
    stage_id: Optional[str]
    span_id: Optional[str]
    request_id: Optional[str]
    mission_id: Optional[str]
    orchestration_run_id: Optional[str]
    authorization_id: Optional[str]
    checkpoint_id: Optional[str]
    interrupt_id: Optional[str]
    decision_id: Optional[str]
    artifact_type: Optional[str]
    artifact_id: Optional[str]
    handoff_id: Optional[str]
    tool_name: Optional[str]
    node_name: Optional[str]
    attempt_n: int
    resume_n: int
    detail: tuple[Any, ...]

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, OBSERVABILITY_EVENT_SCHEMA_VERSION)
        _require_id(self.event_id, "event_id")
        _require_id(self.run_id, "run_id")
        _require_id(self.agent_code, "agent_code")
        _store_utc(self, "occurred_at", self.occurred_at)
        if not isinstance(self.family, EventFamily):
            _fail("family must be EventFamily")
        if not isinstance(self.event_type, EventType):
            _fail("event_type must be EventType")
        expected_family = EVENT_FAMILY_BY_TYPE.get(self.event_type)
        if expected_family is None or expected_family is not self.family:
            _fail("event_type does not belong to family")
        if not isinstance(self.status, EventStatus):
            _fail("status must be EventStatus")
        _require_text(self.title, "title", max_len=MAX_TITLE_LENGTH)
        for name in (
            "stage_id",
            "span_id",
            "request_id",
            "mission_id",
            "orchestration_run_id",
            "authorization_id",
            "checkpoint_id",
            "interrupt_id",
            "decision_id",
            "artifact_type",
            "artifact_id",
            "handoff_id",
            "tool_name",
            "node_name",
        ):
            raw = getattr(self, name)
            if raw is not None:
                if name in {"tool_name", "node_name", "artifact_type"}:
                    _require_text(raw, name, max_len=MAX_ID_LENGTH)
                else:
                    _require_id(raw, name)
        artifact_type = self.artifact_type
        artifact_id = self.artifact_id
        if (artifact_type is None) != (artifact_id is None):
            _fail("artifact_type and artifact_id must both exist or both be absent")
        _require_int(self.attempt_n, "attempt_n", minimum=1)
        _require_int(self.resume_n, "resume_n", minimum=0)
        try:
            assert_no_secrets_in_payload(self.to_dict())
        except AssertionError:
            _fail("ObservabilityEvent failed secret scan")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "run_id": self.run_id,
            "agent_code": self.agent_code,
            "occurred_at": self.occurred_at.astimezone(timezone.utc).isoformat(),
            "family": self.family.value,
            "event_type": self.event_type.value,
            "status": self.status.value,
            "title": self.title,
            "stage_id": self.stage_id,
            "span_id": self.span_id,
            "request_id": self.request_id,
            "mission_id": self.mission_id,
            "orchestration_run_id": self.orchestration_run_id,
            "authorization_id": self.authorization_id,
            "checkpoint_id": self.checkpoint_id,
            "interrupt_id": self.interrupt_id,
            "decision_id": self.decision_id,
            "artifact_type": self.artifact_type,
            "artifact_id": self.artifact_id,
            "handoff_id": self.handoff_id,
            "tool_name": self.tool_name,
            "node_name": self.node_name,
            "attempt_n": self.attempt_n,
            "resume_n": self.resume_n,
            "detail": _unfreeze_jsonable(self.detail),
        }


def build_observability_event(
    *,
    event_id: Any,
    run_id: Any,
    agent_code: Any,
    occurred_at: datetime,
    event_type: Any,
    status: Any,
    title: Any,
    family: Any = None,
    stage_id: Any = None,
    span_id: Any = None,
    request_id: Any = None,
    mission_id: Any = None,
    orchestration_run_id: Any = None,
    authorization_id: Any = None,
    checkpoint_id: Any = None,
    interrupt_id: Any = None,
    decision_id: Any = None,
    artifact_type: Any = None,
    artifact_id: Any = None,
    handoff_id: Any = None,
    tool_name: Any = None,
    node_name: Any = None,
    attempt_n: int = 1,
    resume_n: int = 0,
    detail: Optional[Mapping[str, Any]] = None,
    schema_version: str = OBSERVABILITY_EVENT_SCHEMA_VERSION,
) -> ObservabilityEvent:
    parsed_type = _require_enum(event_type, EventType, "event_type")
    expected_family = EVENT_FAMILY_BY_TYPE[parsed_type]
    parsed_family = (
        expected_family
        if family is None
        else _require_enum(family, EventFamily, "family")
    )
    frozen_detail = _validate_bounded_mapping(
        detail if detail is not None else {},
        "detail",
        max_keys=MAX_DETAIL_KEYS,
        required=True,
    )
    return ObservabilityEvent(
        schema_version=schema_version,
        event_id=_require_id(event_id, "event_id"),
        run_id=_require_id(run_id, "run_id"),
        agent_code=_require_id(agent_code, "agent_code"),
        occurred_at=_require_aware_utc(occurred_at, "occurred_at"),
        family=parsed_family,
        event_type=parsed_type,
        status=_require_enum(status, EventStatus, "status"),
        title=_require_text(title, "title", max_len=MAX_TITLE_LENGTH),
        stage_id=_optional_id(stage_id, "stage_id"),
        span_id=_optional_id(span_id, "span_id"),
        request_id=_optional_id(request_id, "request_id"),
        mission_id=_optional_id(mission_id, "mission_id"),
        orchestration_run_id=_optional_id(orchestration_run_id, "orchestration_run_id"),
        authorization_id=_optional_id(authorization_id, "authorization_id"),
        checkpoint_id=_optional_id(checkpoint_id, "checkpoint_id"),
        interrupt_id=_optional_id(interrupt_id, "interrupt_id"),
        decision_id=_optional_id(decision_id, "decision_id"),
        artifact_type=(
            None
            if artifact_type is None
            else _require_text(artifact_type, "artifact_type", max_len=MAX_ID_LENGTH)
        ),
        artifact_id=_optional_id(artifact_id, "artifact_id"),
        handoff_id=_optional_id(handoff_id, "handoff_id"),
        tool_name=(
            None if tool_name is None else _require_text(tool_name, "tool_name", max_len=MAX_ID_LENGTH)
        ),
        node_name=(
            None if node_name is None else _require_text(node_name, "node_name", max_len=MAX_ID_LENGTH)
        ),
        attempt_n=_require_int(attempt_n, "attempt_n", minimum=1),
        resume_n=_require_int(resume_n, "resume_n", minimum=0),
        detail=frozen_detail,
    )
