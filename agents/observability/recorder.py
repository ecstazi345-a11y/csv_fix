"""
Increment 10.1B — agent-neutral ObservabilityRecorder Protocol + in-memory test double.

Records immutable ObservabilityEvent facts only.
Not Run Control. Not durable store. Not AgentRun projection. Not Constructor logic.
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
    ObservabilityContractError,
    ObservabilityEvent,
)
from security.sanitize import assert_no_secrets_in_payload

_JSON_SEPARATORS = (",", ":")

CODE_OBSERVABILITY_EVENT_CONFLICT = "OBSERVABILITY_EVENT_CONFLICT"


class ObservabilityEventConflictError(ValueError):
    """Fail-closed immutable event_id replay conflict."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class RecordOutcome(str, Enum):
    CREATED = "CREATED"
    IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"


@dataclass(frozen=True)
class RecordResult:
    """Deterministic record outcome. No database internals."""

    outcome: RecordOutcome
    event_id: str
    run_id: str


@runtime_checkable
class ObservabilityRecorder(Protocol):
    """Agent-neutral append-only event recording port."""

    def record_event(self, event: ObservabilityEvent) -> RecordResult:
        ...


def compute_observability_event_fingerprint(event: ObservabilityEvent) -> str:
    """
    SHA-256 fingerprint of canonical event payload.

    Uses ObservabilityEvent.to_dict() + deterministic JSON encoding.
    Internal comparison metadata — does not replace event_id.
    """
    if not isinstance(event, ObservabilityEvent):
        raise ObservabilityContractError(
            CODE_OBSERVABILITY_CONTRACT_BLOCKER,
            "ObservabilityEvent is required for fingerprint",
        )
    payload = event.to_dict()
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=_JSON_SEPARATORS,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_recordable_event(event: Any) -> ObservabilityEvent:
    if event is None or not isinstance(event, ObservabilityEvent):
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


class InMemoryObservabilityRecorder:
    """
    Non-durable TEST / CONTRACT PROOF recorder.

    NOT Control Room production truth. NOT durable observability.
    Append-only. No delete/clear API.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: list[ObservabilityEvent] = []
        self._fingerprints: dict[str, str] = {}

    def record_event(self, event: ObservabilityEvent) -> RecordResult:
        artifact = _validate_recordable_event(event)
        fingerprint = compute_observability_event_fingerprint(artifact)
        with self._lock:
            existing = self._fingerprints.get(artifact.event_id)
            if existing is None:
                self._fingerprints[artifact.event_id] = fingerprint
                self._events.append(artifact)
                return RecordResult(
                    outcome=RecordOutcome.CREATED,
                    event_id=artifact.event_id,
                    run_id=artifact.run_id,
                )
            if existing != fingerprint:
                raise ObservabilityEventConflictError(
                    CODE_OBSERVABILITY_EVENT_CONFLICT,
                    "event_id already recorded with a different payload",
                )
            return RecordResult(
                outcome=RecordOutcome.IDEMPOTENT_REPLAY,
                event_id=artifact.event_id,
                run_id=artifact.run_id,
            )

    def snapshot_events(self) -> tuple[ObservabilityEvent, ...]:
        """In-memory test inspection only. Returns immutable copy-safe snapshot."""
        with self._lock:
            return tuple(self._events)

    def events_for_run(self, run_id: str) -> tuple[ObservabilityEvent, ...]:
        """In-memory test inspection only. Filter by run_id without mutating storage."""
        if not isinstance(run_id, str) or not run_id.strip():
            raise ObservabilityContractError(
                CODE_OBSERVABILITY_CONTRACT_BLOCKER,
                "run_id is required",
            )
        with self._lock:
            return tuple(item for item in self._events if item.run_id == run_id)
