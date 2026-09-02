"""
Increment 10.4 — agent-neutral ObservabilityStore port + in-memory test double.

Not Run Control. Not Constructor-specific. Not product Supabase.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable

from agents.observability.contracts import (
    CODE_OBSERVABILITY_CONTRACT_BLOCKER,
    AgentRun,
    ObservabilityContractError,
    ObservabilityEvent,
    build_agent_run,
)
from agents.observability.projection import (
    AgentRunProjectionChange,
    apply_agent_run_projection_change,
)
from agents.observability.recorder import (
    ObservabilityEventConflictError,
    RecordOutcome,
    compute_observability_event_fingerprint,
)
from security.sanitize import assert_no_secrets_in_payload

_JSON_SEPARATORS = (",", ":")

CODE_OBSERVABILITY_STORE_BLOCKER = "OBSERVABILITY_STORE_BLOCKER"
CODE_OBSERVABILITY_RUN_NOT_FOUND = "OBSERVABILITY_RUN_NOT_FOUND"
CODE_OBSERVABILITY_RUN_IDENTITY_CONFLICT = "OBSERVABILITY_RUN_IDENTITY_CONFLICT"
CODE_OBSERVABILITY_PROJECTION_VERSION_CONFLICT = "OBSERVABILITY_PROJECTION_VERSION_CONFLICT"
CODE_OBSERVABILITY_STORAGE_FAILURE = "OBSERVABILITY_STORAGE_FAILURE"

DEFAULT_LIST_EVENTS_LIMIT = 500
DEFAULT_LIST_RUNS_LIMIT = 200
MAX_LIST_EVENTS_LIMIT = 500
MAX_LIST_RUNS_LIMIT = 200


class ObservabilityStoreError(ValueError):
    """Agent-neutral durable observability store failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ObservabilityRunNotFoundError(ObservabilityStoreError):
    def __init__(self, message: str = "run not found") -> None:
        super().__init__(CODE_OBSERVABILITY_RUN_NOT_FOUND, message)


class ObservabilityRunIdentityConflictError(ObservabilityStoreError):
    def __init__(self, message: str = "run identity conflict") -> None:
        super().__init__(CODE_OBSERVABILITY_RUN_IDENTITY_CONFLICT, message)


class ObservabilityProjectionVersionConflictError(ObservabilityStoreError):
    def __init__(self, message: str = "projection version conflict") -> None:
        super().__init__(CODE_OBSERVABILITY_PROJECTION_VERSION_CONFLICT, message)


class ObservabilityStorageFailureError(ObservabilityStoreError):
    def __init__(self, message: str = "storage failure") -> None:
        super().__init__(CODE_OBSERVABILITY_STORAGE_FAILURE, message)


class CreateRunOutcome(str, Enum):
    CREATED = "CREATED"
    IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"


@dataclass(frozen=True)
class CreateRunResult:
    outcome: CreateRunOutcome
    run_id: str
    projection_version: int


@dataclass(frozen=True)
class AppendEventResult:
    outcome: RecordOutcome
    event_id: str
    run_id: str
    projection_version: int


@runtime_checkable
class ObservabilityStore(Protocol):
    """Agent-neutral durable observability store."""

    def create_run(self, run: AgentRun) -> CreateRunResult:
        ...

    def get_run(self, run_id: str) -> AgentRun:
        ...

    def append_event_and_project_run(
        self,
        *,
        event: ObservabilityEvent,
        expected_projection_version: int,
        projection_change: AgentRunProjectionChange,
    ) -> AppendEventResult:
        ...

    def list_events(
        self,
        run_id: str,
        *,
        limit: int = DEFAULT_LIST_EVENTS_LIMIT,
    ) -> tuple[ObservabilityEvent, ...]:
        ...

    def list_runs(
        self,
        *,
        limit: int = DEFAULT_LIST_RUNS_LIMIT,
        agent_code: Optional[str] = None,
    ) -> tuple[AgentRun, ...]:
        ...


_IMMUTABLE_RUN_IDENTITY_FIELDS = (
    "schema_version",
    "run_id",
    "request_id",
    "agent_code",
    "agent_version",
    "mission_id",
    "orchestration_run_id",
    "project_code",
    "month_key",
    "scope_summary",
    "initiator_type",
    "initiator_id",
    "trigger_type",
    "trigger_reason",
    "thread_id",
    "requested_at",
)


def compute_agent_run_identity_digest(run: AgentRun) -> str:
    """Canonical digest of immutable AgentRun identity fields only."""
    payload = run.to_dict()
    identity = {field: payload[field] for field in _IMMUTABLE_RUN_IDENTITY_FIELDS}
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=_JSON_SEPARATORS,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_store_event(event: ObservabilityEvent) -> ObservabilityEvent:
    if not isinstance(event, ObservabilityEvent):
        raise ObservabilityContractError(
            CODE_OBSERVABILITY_CONTRACT_BLOCKER,
            "ObservabilityEvent is required",
        )
    payload = event.to_dict()
    try:
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=_JSON_SEPARATORS,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ObservabilityContractError(
            CODE_OBSERVABILITY_CONTRACT_BLOCKER,
            f"ObservabilityEvent is not JSON-serializable: {exc}",
        ) from exc
    try:
        assert_no_secrets_in_payload(payload)
    except AssertionError as exc:
        raise ObservabilityContractError(
            CODE_OBSERVABILITY_CONTRACT_BLOCKER,
            "ObservabilityEvent failed secret scan",
        ) from exc
    return event


def validate_store_run(run: AgentRun) -> AgentRun:
    if not isinstance(run, AgentRun):
        raise ObservabilityContractError(
            CODE_OBSERVABILITY_CONTRACT_BLOCKER,
            "AgentRun is required",
        )
    payload = run.to_dict()
    try:
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=_JSON_SEPARATORS,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ObservabilityContractError(
            CODE_OBSERVABILITY_CONTRACT_BLOCKER,
            f"AgentRun is not JSON-serializable: {exc}",
        ) from exc
    try:
        assert_no_secrets_in_payload(payload)
    except AssertionError as exc:
        raise ObservabilityContractError(
            CODE_OBSERVABILITY_CONTRACT_BLOCKER,
            "AgentRun failed secret scan",
        ) from exc
    return run


def _require_bounded_limit(limit: int, *, maximum: int, label: str) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ObservabilityStoreError(
            CODE_OBSERVABILITY_STORE_BLOCKER,
            f"{label} must be int",
        )
    if limit < 1 or limit > maximum:
        raise ObservabilityStoreError(
            CODE_OBSERVABILITY_STORE_BLOCKER,
            f"{label} must be between 1 and {maximum}",
        )
    return limit


def _agent_run_from_dict(payload: dict[str, Any]) -> AgentRun:
    scope = payload.get("scope_summary")
    safe_summary = payload.get("safe_summary")
    safe_counts = payload.get("safe_counts")
    return build_agent_run(
        run_id=payload["run_id"],
        request_id=payload["request_id"],
        agent_code=payload["agent_code"],
        agent_version=payload["agent_version"],
        mission_id=payload["mission_id"],
        project_code=payload["project_code"],
        month_key=payload["month_key"],
        initiator_type=payload["initiator_type"],
        initiator_id=payload["initiator_id"],
        trigger_type=payload["trigger_type"],
        trigger_reason=payload["trigger_reason"],
        operational_status=payload["operational_status"],
        requested_at=_parse_iso_datetime(payload["requested_at"]),
        updated_at=_parse_iso_datetime(payload["updated_at"]),
        thread_id=payload["thread_id"],
        attempt_n=int(payload["attempt_n"]),
        resume_n=int(payload["resume_n"]),
        projection_version=int(payload["projection_version"]),
        orchestration_run_id=payload.get("orchestration_run_id"),
        scope_summary=scope if isinstance(scope, dict) else {},
        authorization_id=payload.get("authorization_id"),
        authorized_by=payload.get("authorized_by"),
        security_policy_version=payload.get("security_policy_version"),
        lifecycle_status=payload.get("lifecycle_status"),
        current_stage_id=payload.get("current_stage_id"),
        current_node=payload.get("current_node"),
        started_at=_parse_optional_iso_datetime(payload.get("started_at")),
        completed_at=_parse_optional_iso_datetime(payload.get("completed_at")),
        checkpoint_id=payload.get("checkpoint_id"),
        snapshot_id=payload.get("snapshot_id"),
        package_id=payload.get("package_id"),
        interrupt_id=payload.get("interrupt_id"),
        decision_id=payload.get("decision_id"),
        handoff_id=payload.get("handoff_id"),
        safe_summary=safe_summary if isinstance(safe_summary, dict) else {},
        safe_counts=safe_counts if isinstance(safe_counts, dict) else {},
        error_code=payload.get("error_code"),
        safe_error_summary=payload.get("safe_error_summary"),
        schema_version=payload["schema_version"],
    )


def _observability_event_from_dict(payload: dict[str, Any]) -> ObservabilityEvent:
    from agents.observability.contracts import (
        build_observability_event,
        human_decision_record_observability_context_from_dict,
        human_decision_request_observability_context_from_dict,
    )

    detail = payload.get("detail")
    request_payload = payload.get("human_decision_request")
    record_payload = payload.get("human_decision_record")
    return build_observability_event(
        event_id=payload["event_id"],
        run_id=payload["run_id"],
        agent_code=payload["agent_code"],
        occurred_at=_parse_iso_datetime(payload["occurred_at"]),
        event_type=payload["event_type"],
        status=payload["status"],
        title=payload["title"],
        family=payload.get("family"),
        stage_id=payload.get("stage_id"),
        span_id=payload.get("span_id"),
        request_id=payload.get("request_id"),
        mission_id=payload.get("mission_id"),
        orchestration_run_id=payload.get("orchestration_run_id"),
        authorization_id=payload.get("authorization_id"),
        checkpoint_id=payload.get("checkpoint_id"),
        interrupt_id=payload.get("interrupt_id"),
        decision_id=payload.get("decision_id"),
        artifact_type=payload.get("artifact_type"),
        artifact_id=payload.get("artifact_id"),
        handoff_id=payload.get("handoff_id"),
        tool_name=payload.get("tool_name"),
        node_name=payload.get("node_name"),
        attempt_n=int(payload.get("attempt_n", 1)),
        resume_n=int(payload.get("resume_n", 0)),
        human_decision_request=(
            None
            if request_payload is None
            else human_decision_request_observability_context_from_dict(request_payload)
        ),
        human_decision_record=(
            None
            if record_payload is None
            else human_decision_record_observability_context_from_dict(record_payload)
        ),
        detail=detail if isinstance(detail, dict) else {},
        schema_version=payload["schema_version"],
        allow_legacy_missing_hitl_subcontracts=True,
    )


def _parse_iso_datetime(value: str) -> Any:
    from datetime import datetime

    return datetime.fromisoformat(value)


def _parse_optional_iso_datetime(value: object) -> Any:
    if value is None:
        return None
    return _parse_iso_datetime(str(value))


def _serialize_agent_run(run: AgentRun) -> str:
    return json.dumps(
        run.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=_JSON_SEPARATORS,
        allow_nan=False,
    )


def _serialize_event(event: ObservabilityEvent) -> str:
    return json.dumps(
        event.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=_JSON_SEPARATORS,
        allow_nan=False,
    )


def execute_create_run(
    *,
    run: AgentRun,
    existing_identity_digest: Optional[str],
) -> CreateRunResult:
    validated = validate_store_run(run)
    digest = compute_agent_run_identity_digest(validated)
    if existing_identity_digest is None:
        return CreateRunResult(
            outcome=CreateRunOutcome.CREATED,
            run_id=validated.run_id,
            projection_version=validated.projection_version,
        )
    if existing_identity_digest == digest:
        return CreateRunResult(
            outcome=CreateRunOutcome.IDEMPOTENT_REPLAY,
            run_id=validated.run_id,
            projection_version=validated.projection_version,
        )
    raise ObservabilityRunIdentityConflictError(
        f"run_id {validated.run_id!r} already exists with different immutable identity",
    )


def execute_append_event_and_project_run(
    *,
    event: ObservabilityEvent,
    expected_projection_version: int,
    projection_change: AgentRunProjectionChange,
    existing_fingerprint: Optional[str],
    current_run: Optional[AgentRun],
) -> tuple[AppendEventResult, AgentRun, str, int]:
    """
    Shared replay-before-CAS append semantics.

    Returns (result, updated_run_or_current, fingerprint, append_sequence).
    append_sequence is 0 when replay (no new sequence).
    """
    artifact = validate_store_event(event)
    fingerprint = compute_observability_event_fingerprint(artifact)

    if existing_fingerprint is not None:
        if existing_fingerprint != fingerprint:
            raise ObservabilityEventConflictError(
                "OBSERVABILITY_EVENT_CONFLICT",
                "event_id already recorded with a different payload",
            )
        if current_run is None:
            raise ObservabilityRunNotFoundError(
                f"run_id {artifact.run_id!r} not found for replay",
            )
        return (
            AppendEventResult(
                outcome=RecordOutcome.IDEMPOTENT_REPLAY,
                event_id=artifact.event_id,
                run_id=artifact.run_id,
                projection_version=current_run.projection_version,
            ),
            current_run,
            fingerprint,
            0,
        )

    if current_run is None:
        raise ObservabilityRunNotFoundError(f"run_id {artifact.run_id!r} not found")

    if current_run.projection_version != expected_projection_version:
        raise ObservabilityProjectionVersionConflictError(
            "expected_projection_version does not match stored projection_version",
        )

    projected = apply_agent_run_projection_change(current_run, projection_change)
    updated = build_agent_run(
        run_id=projected.run_id,
        request_id=projected.request_id,
        agent_code=projected.agent_code,
        agent_version=projected.agent_version,
        mission_id=projected.mission_id,
        project_code=projected.project_code,
        month_key=projected.month_key,
        initiator_type=projected.initiator_type,
        initiator_id=projected.initiator_id,
        trigger_type=projected.trigger_type,
        trigger_reason=projected.trigger_reason,
        operational_status=projected.operational_status,
        requested_at=projected.requested_at,
        updated_at=projected.updated_at,
        thread_id=projected.thread_id,
        attempt_n=projected.attempt_n,
        resume_n=projected.resume_n,
        projection_version=current_run.projection_version + 1,
        orchestration_run_id=projected.orchestration_run_id,
        scope_summary=_dict_from_tuple(projected.scope_summary),
        authorization_id=projected.authorization_id,
        authorized_by=projected.authorized_by,
        security_policy_version=projected.security_policy_version,
        lifecycle_status=projected.lifecycle_status,
        current_stage_id=projected.current_stage_id,
        current_node=projected.current_node,
        started_at=projected.started_at,
        completed_at=projected.completed_at,
        checkpoint_id=projected.checkpoint_id,
        snapshot_id=projected.snapshot_id,
        package_id=projected.package_id,
        interrupt_id=projected.interrupt_id,
        decision_id=projected.decision_id,
        handoff_id=projected.handoff_id,
        safe_summary=_dict_from_tuple(projected.safe_summary),
        safe_counts=_dict_from_tuple(projected.safe_counts),
        error_code=projected.error_code,
        safe_error_summary=projected.safe_error_summary,
        schema_version=projected.schema_version,
    )

    return (
        AppendEventResult(
            outcome=RecordOutcome.CREATED,
            event_id=artifact.event_id,
            run_id=artifact.run_id,
            projection_version=updated.projection_version,
        ),
        updated,
        fingerprint,
        1,
    )


def _dict_from_tuple(value: tuple[Any, ...]) -> dict[str, Any]:
    from agents.observability.contracts import _unfreeze_jsonable

    unfrozen = _unfreeze_jsonable(value)
    if isinstance(unfrozen, dict):
        return unfrozen
    return {}


@dataclass
class _StoredEvent:
    event: ObservabilityEvent
    fingerprint: str
    append_sequence: int


class InMemoryObservabilityStore:
    """Non-durable store-contract test double with durable semantics."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runs: dict[str, AgentRun] = {}
        self._identity_digests: dict[str, str] = {}
        self._event_fingerprints: dict[str, str] = {}
        self._events_by_run: dict[str, list[_StoredEvent]] = {}
        self._next_sequence: dict[str, int] = {}

    def create_run(self, run: AgentRun) -> CreateRunResult:
        with self._lock:
            existing_digest = self._identity_digests.get(run.run_id)
            result = execute_create_run(run=run, existing_identity_digest=existing_digest)
            if result.outcome is CreateRunOutcome.CREATED:
                validated = validate_store_run(run)
                self._runs[validated.run_id] = validated
                self._identity_digests[validated.run_id] = compute_agent_run_identity_digest(
                    validated
                )
                self._events_by_run.setdefault(validated.run_id, [])
                self._next_sequence.setdefault(validated.run_id, 1)
            elif run.run_id not in self._runs:
                raise ObservabilityRunNotFoundError(f"run_id {run.run_id!r} not found")
            stored = self._runs[run.run_id]
            return CreateRunResult(
                outcome=result.outcome,
                run_id=stored.run_id,
                projection_version=stored.projection_version,
            )

    def get_run(self, run_id: str) -> AgentRun:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise ObservabilityRunNotFoundError(f"run_id {run_id!r} not found")
            return run

    def append_event_and_project_run(
        self,
        *,
        event: ObservabilityEvent,
        expected_projection_version: int,
        projection_change: AgentRunProjectionChange,
    ) -> AppendEventResult:
        with self._lock:
            existing_fp = self._event_fingerprints.get(event.event_id)
            current = self._runs.get(event.run_id)
            result, updated, fingerprint, seq_delta = execute_append_event_and_project_run(
                event=event,
                expected_projection_version=expected_projection_version,
                projection_change=projection_change,
                existing_fingerprint=existing_fp,
                current_run=current,
            )
            if result.outcome is RecordOutcome.IDEMPOTENT_REPLAY:
                return result

            sequence = self._next_sequence[event.run_id]
            self._next_sequence[event.run_id] = sequence + 1
            self._runs[event.run_id] = updated
            self._event_fingerprints[event.event_id] = fingerprint
            self._events_by_run.setdefault(event.run_id, []).append(
                _StoredEvent(
                    event=validate_store_event(event),
                    fingerprint=fingerprint,
                    append_sequence=sequence,
                )
            )
            return result

    def list_events(
        self,
        run_id: str,
        *,
        limit: int = DEFAULT_LIST_EVENTS_LIMIT,
    ) -> tuple[ObservabilityEvent, ...]:
        bounded = _require_bounded_limit(limit, maximum=MAX_LIST_EVENTS_LIMIT, label="limit")
        with self._lock:
            if run_id not in self._runs:
                raise ObservabilityRunNotFoundError(f"run_id {run_id!r} not found")
            items = self._events_by_run.get(run_id, [])
            ordered = sorted(items, key=lambda item: item.append_sequence)
            return tuple(item.event for item in ordered[:bounded])

    def list_runs(
        self,
        *,
        limit: int = DEFAULT_LIST_RUNS_LIMIT,
        agent_code: Optional[str] = None,
    ) -> tuple[AgentRun, ...]:
        bounded = _require_bounded_limit(limit, maximum=MAX_LIST_RUNS_LIMIT, label="limit")
        with self._lock:
            runs = list(self._runs.values())
            if agent_code is not None:
                runs = [run for run in runs if run.agent_code == agent_code]
            runs.sort(key=lambda run: (run.requested_at, run.run_id))
            return tuple(runs[:bounded])
