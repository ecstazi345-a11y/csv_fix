"""
Increment 10.4 — durable ObservabilityRecorder adapter backed by ObservabilityStore.

Implements existing ObservabilityRecorder interface unchanged.
"""

from __future__ import annotations

from agents.observability.contracts import ObservabilityEvent
from agents.observability.projection import project_agent_run_event
from agents.observability.recorder import RecordOutcome, RecordResult
from agents.observability.store import (
    CODE_OBSERVABILITY_STORE_BLOCKER,
    ObservabilityRunNotFoundError,
    ObservabilityStore,
    ObservabilityStoreError,
    validate_store_event,
)


class StoreObservabilityRecorder:
    """Durable recorder that atomically appends events and projects AgentRun state."""

    def __init__(self, store: ObservabilityStore) -> None:
        if store is None:
            raise ObservabilityStoreError(
                CODE_OBSERVABILITY_STORE_BLOCKER,
                "ObservabilityStore is required",
            )
        self._store = store

    def record_event(self, event: ObservabilityEvent) -> RecordResult:
        artifact = validate_store_event(event)
        try:
            current_run = self._store.get_run(artifact.run_id)
        except ObservabilityRunNotFoundError as exc:
            raise ObservabilityStoreError(
                CODE_OBSERVABILITY_STORE_BLOCKER,
                f"unknown run_id {artifact.run_id!r}; create_run is required before record_event",
            ) from exc

        projection_change = project_agent_run_event(current_run, artifact)
        append_result = self._store.append_event_and_project_run(
            event=artifact,
            expected_projection_version=current_run.projection_version,
            projection_change=projection_change,
        )
        return RecordResult(
            outcome=append_result.outcome,
            event_id=append_result.event_id,
            run_id=append_result.run_id,
        )
