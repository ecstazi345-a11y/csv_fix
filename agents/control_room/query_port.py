"""
Increment 10.6 — agent-neutral Control Room query port.

Control Room → AgentControlRoomQueryPort → ObservabilityStore
Read-only. No writes. No LLM. No raw event detail.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from agents.control_room.derivations import (
    agent_run_to_detail,
    agent_run_to_summary,
    build_event_timeline,
    derive_digital_organization_view,
    derive_handoff_view,
    derive_human_decision_surface,
    derive_human_wait_view,
    derive_professional_execution_path,
    derive_stage_view,
)
from agents.control_room.dtos import AgentRunDetail, AgentRunListView, AgentRunSnapshot, AgentRunSummary
from agents.control_room.errors import (
    ControlRoomQueryBlockerError,
    ControlRoomRunNotFoundError,
    ControlRoomStorageUnavailableError,
)
from agents.observability.contracts import OperationalStatus
from agents.observability.store import (
    CODE_OBSERVABILITY_STORE_BLOCKER,
    MAX_LIST_EVENTS_LIMIT,
    MAX_LIST_RUNS_LIMIT,
    ObservabilityRunNotFoundError,
    ObservabilityStorageFailureError,
    ObservabilityStore,
    ObservabilityStoreError,
)

DEFAULT_EVENT_LIMIT = 200
MAX_EVENT_LIMIT = MAX_LIST_EVENTS_LIMIT

DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = MAX_LIST_RUNS_LIMIT


class AgentControlRoomQueryPort:
    """Bounded read-only Control Room query surface over durable observability truth."""

    def __init__(self, store: ObservabilityStore) -> None:
        if store is None:
            raise ControlRoomQueryBlockerError("ObservabilityStore is required")
        self._store = store

    def list_runs(
        self,
        *,
        agent_code: Optional[str] = None,
        project_code: Optional[str] = None,
        month_key: Optional[str] = None,
        operational_status: Optional[str | OperationalStatus] = None,
        limit: int = DEFAULT_LIST_LIMIT,
    ) -> AgentRunListView:
        bounded_limit = _require_result_limit(limit)
        status_filter = _normalize_operational_status_filter(operational_status)

        try:
            source_runs = self._store.list_runs(
                limit=MAX_LIST_RUNS_LIMIT,
                agent_code=_optional_text(agent_code),
            )
        except ObservabilityStorageFailureError as exc:
            raise ControlRoomStorageUnavailableError("storage unavailable") from exc
        except ObservabilityStoreError as exc:
            raise _translate_store_error(exc) from exc

        runs_complete = len(source_runs) < MAX_LIST_RUNS_LIMIT
        filtered = _apply_run_filters(
            source_runs,
            project_code=_optional_text(project_code),
            month_key=_optional_text(month_key),
            operational_status=status_filter,
        )
        ordered = sorted(
            filtered,
            key=lambda run: (run.updated_at, run.run_id),
            reverse=True,
        )
        items = tuple(agent_run_to_summary(run) for run in ordered[:bounded_limit])
        return AgentRunListView(
            items=items,
            runs_complete=runs_complete,
            source_count=len(source_runs),
        )

    def get_run(self, run_id: str) -> AgentRunDetail:
        normalized_run_id = _require_run_id(run_id)
        try:
            run = self._store.get_run(normalized_run_id)
        except ObservabilityRunNotFoundError as exc:
            raise ControlRoomRunNotFoundError(str(exc)) from exc
        except ObservabilityStorageFailureError as exc:
            raise ControlRoomStorageUnavailableError("storage unavailable") from exc
        except ObservabilityStoreError as exc:
            raise _translate_store_error(exc) from exc
        return agent_run_to_detail(run)

    def get_run_snapshot(
        self,
        run_id: str,
        *,
        event_limit: int = DEFAULT_EVENT_LIMIT,
    ) -> AgentRunSnapshot:
        normalized_run_id = _require_run_id(run_id)
        bounded_event_limit = _require_event_limit(event_limit)
        read_at = datetime.now(timezone.utc)

        try:
            run = self._store.get_run(normalized_run_id)
            events = self._store.list_events(normalized_run_id, limit=bounded_event_limit)
        except ObservabilityRunNotFoundError as exc:
            raise ControlRoomRunNotFoundError(str(exc)) from exc
        except ObservabilityStorageFailureError as exc:
            raise ControlRoomStorageUnavailableError("storage unavailable") from exc
        except ObservabilityStoreError as exc:
            raise _translate_store_error(exc) from exc

        events_complete = len(events) < bounded_event_limit
        detail = agent_run_to_detail(run)
        human_wait = derive_human_wait_view(run, events, events_complete=events_complete)
        handoff = derive_handoff_view(run, events, events_complete=events_complete)
        return AgentRunSnapshot(
            run=detail,
            stage=derive_stage_view(events, events_complete=events_complete),
            human_wait=human_wait,
            human_decision_surface=derive_human_decision_surface(
                run,
                events,
                human_wait=human_wait,
                events_complete=events_complete,
            ),
            handoff=handoff,
            professional_execution_path=derive_professional_execution_path(
                run,
                events,
                events_complete=events_complete,
            ),
            digital_organization=derive_digital_organization_view(
                detail,
                handoff,
                events_complete=events_complete,
            ),
            timeline_events=build_event_timeline(events),
            events_complete=events_complete,
            read_at=read_at,
        )


def _require_run_id(run_id: str) -> str:
    text = str(run_id or "").strip()
    if not text:
        raise ControlRoomQueryBlockerError("run_id is required")
    return text


def _optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_result_limit(limit: int) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ControlRoomQueryBlockerError("limit must be int")
    if limit < 1 or limit > MAX_LIST_LIMIT:
        raise ControlRoomQueryBlockerError(f"limit must be between 1 and {MAX_LIST_LIMIT}")
    return limit


def _require_event_limit(limit: int) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ControlRoomQueryBlockerError("event_limit must be int")
    if limit < 1 or limit > MAX_EVENT_LIMIT:
        raise ControlRoomQueryBlockerError(f"event_limit must be between 1 and {MAX_EVENT_LIMIT}")
    return limit


def _normalize_operational_status_filter(
    operational_status: Optional[str | OperationalStatus],
) -> Optional[OperationalStatus]:
    if operational_status is None:
        return None
    if isinstance(operational_status, OperationalStatus):
        return operational_status
    text = str(operational_status).strip()
    if not text:
        raise ControlRoomQueryBlockerError("operational_status must be non-empty when provided")
    try:
        return OperationalStatus(text)
    except ValueError as exc:
        raise ControlRoomQueryBlockerError("operational_status is invalid") from exc


def _apply_run_filters(
    runs: tuple[object, ...],
    *,
    project_code: Optional[str],
    month_key: Optional[str],
    operational_status: Optional[OperationalStatus],
) -> list[object]:
    filtered = list(runs)
    if project_code is not None:
        filtered = [run for run in filtered if run.project_code == project_code]
    if month_key is not None:
        filtered = [run for run in filtered if run.month_key == month_key]
    if operational_status is not None:
        filtered = [run for run in filtered if run.operational_status is operational_status]
    return filtered


def _translate_store_error(exc: ObservabilityStoreError) -> ControlRoomQueryError:
    from agents.control_room.errors import ControlRoomQueryError

    if exc.code == CODE_OBSERVABILITY_STORE_BLOCKER:
        return ControlRoomQueryBlockerError(str(exc))
    return ControlRoomQueryError(exc.code, str(exc))
