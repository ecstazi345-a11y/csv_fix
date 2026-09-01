"""
Increment 10.2 — in-memory RunControlRegistry.

NON-DURABLE · PROCESS-LOCAL · CONTRACT / DEVELOPMENT IMPLEMENTATION ONLY.
NOT AgentRun projection store. NOT observability store.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from agents.run_control.contracts import (
    CODE_IDEMPOTENCY_CONFLICT,
    CODE_IDEMPOTENCY_IN_PROGRESS,
    ManagedRunStartResult,
    ReservationDecision,
    ReservationKind,
    ReservationState,
    RunControlError,
    RunControlRegistry,
    TerminalFailureRecord,
)


@dataclass(frozen=True)
class _ReservationEntry:
    canonical_request_digest: str
    request_id: str
    run_id: str
    state: ReservationState
    result: ManagedRunStartResult | None = None
    failure: TerminalFailureRecord | None = None


class InMemoryRunControlRegistry(RunControlRegistry):
    """
    Thread-safe process-local idempotency registry.

    Retains minimum immutable control result to prevent duplicate
    authorization / launch on replay within the same process.
  """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_key: dict[str, _ReservationEntry] = {}

    def decide_reservation(
        self,
        *,
        idempotency_key: str,
        canonical_request_digest: str,
        candidate_request_id: str,
        candidate_run_id: str,
    ) -> ReservationDecision:
        with self._lock:
            existing = self._by_key.get(idempotency_key)
            if existing is None:
                self._by_key[idempotency_key] = _ReservationEntry(
                    canonical_request_digest=canonical_request_digest,
                    request_id=candidate_request_id,
                    run_id=candidate_run_id,
                    state=ReservationState.IN_PROGRESS,
                )
                return ReservationDecision(
                    kind=ReservationKind.NEW,
                    request_id=candidate_request_id,
                    run_id=candidate_run_id,
                )
            if existing.canonical_request_digest != canonical_request_digest:
                raise RunControlError(
                    CODE_IDEMPOTENCY_CONFLICT,
                    "idempotency_key already reserved with a different semantic digest",
                )
            if existing.state is ReservationState.RESULT_AVAILABLE:
                return ReservationDecision(
                    kind=ReservationKind.IDEMPOTENT_REPLAY,
                    request_id=existing.request_id,
                    run_id=existing.run_id,
                )
            if existing.state is ReservationState.TERMINAL_FAILURE:
                return ReservationDecision(
                    kind=ReservationKind.TERMINAL_FAILURE_REPLAY,
                    request_id=existing.request_id,
                    run_id=existing.run_id,
                )
            raise RunControlError(
                CODE_IDEMPOTENCY_IN_PROGRESS,
                "idempotent start already in progress for this idempotency_key",
            )

    def get_cached_result(
        self,
        *,
        idempotency_key: str,
        canonical_request_digest: str,
    ) -> ManagedRunStartResult | None:
        with self._lock:
            existing = self._require_existing(idempotency_key, canonical_request_digest)
            if existing.state is not ReservationState.RESULT_AVAILABLE:
                return None
            return existing.result

    def get_terminal_failure(
        self,
        *,
        idempotency_key: str,
        canonical_request_digest: str,
    ) -> TerminalFailureRecord | None:
        with self._lock:
            existing = self._require_existing(idempotency_key, canonical_request_digest)
            if existing.state is not ReservationState.TERMINAL_FAILURE:
                return None
            return existing.failure

    def store_result(
        self,
        *,
        idempotency_key: str,
        canonical_request_digest: str,
        result: ManagedRunStartResult,
    ) -> None:
        with self._lock:
            existing = self._require_existing(idempotency_key, canonical_request_digest)
            if existing.state is not ReservationState.IN_PROGRESS:
                raise RunControlError(
                    "RUN_CONTROL_REGISTRY_STATE",
                    "cannot store result unless reservation is IN_PROGRESS",
                )
            self._by_key[idempotency_key] = _ReservationEntry(
                canonical_request_digest=canonical_request_digest,
                request_id=existing.request_id,
                run_id=existing.run_id,
                state=ReservationState.RESULT_AVAILABLE,
                result=result,
            )

    def store_terminal_failure(
        self,
        *,
        idempotency_key: str,
        canonical_request_digest: str,
        failure: TerminalFailureRecord,
    ) -> None:
        with self._lock:
            existing = self._by_key.get(idempotency_key)
            if existing is None:
                raise RunControlError(
                    "RUN_CONTROL_REGISTRY_STATE",
                    "cannot store terminal failure without prior reservation",
                )
            if existing.canonical_request_digest != canonical_request_digest:
                raise RunControlError(
                    CODE_IDEMPOTENCY_CONFLICT,
                    "idempotency_key digest mismatch on store_terminal_failure",
                )
            if existing.state is not ReservationState.IN_PROGRESS:
                return
            self._by_key[idempotency_key] = _ReservationEntry(
                canonical_request_digest=canonical_request_digest,
                request_id=existing.request_id,
                run_id=existing.run_id,
                state=ReservationState.TERMINAL_FAILURE,
                failure=failure,
            )

    def reservation_state(self, *, idempotency_key: str) -> ReservationState | None:
        with self._lock:
            existing = self._by_key.get(idempotency_key)
            return None if existing is None else existing.state

    def reservation_count(self) -> int:
        """Test inspection only."""
        with self._lock:
            return len(self._by_key)

    def _require_existing(
        self,
        idempotency_key: str,
        canonical_request_digest: str,
    ) -> _ReservationEntry:
        existing = self._by_key.get(idempotency_key)
        if existing is None:
            raise RunControlError(
                "RUN_CONTROL_REGISTRY_STATE",
                "reservation not found",
            )
        if existing.canonical_request_digest != canonical_request_digest:
            raise RunControlError(
                CODE_IDEMPOTENCY_CONFLICT,
                "idempotency_key already reserved with a different semantic digest",
            )
        return existing
