"""
Increment 10.6 — agent-neutral Control Room query port.

Control Room → AgentControlRoomQueryPort → ObservabilityStore
Read-only. No writes. No LLM. No raw event detail.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Protocol

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
from agents.control_room.dtos import (
    AgentRunDetail,
    AgentRunListView,
    AgentRunSnapshot,
    AgentRunSummary,
    ConstructorDecisionRegistryView,
    ConstructorProfessionalResultView,
    ConstructorRowDecisionView,
    ProfessionalResultAvailability,
    constructor_row_awaits_human_review,
    empty_constructor_decision_registry,
    unavailable_constructor_professional_result,
    inconsistent_constructor_professional_result,
)
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


class ConstructorProfessionalResultReader(Protocol):
    """Read-only Constructor checkpoint adapter. Page 53 must not call this directly."""

    def read(self, *, run_id: str, agent_code: str) -> ConstructorProfessionalResultView:
        ...


class AgentControlRoomQueryPort:
    """Bounded read-only Control Room query surface over durable observability truth."""

    def __init__(
        self,
        store: ObservabilityStore,
        *,
        professional_result_reader: Optional[ConstructorProfessionalResultReader] = None,
    ) -> None:
        if store is None:
            raise ControlRoomQueryBlockerError("ObservabilityStore is required")
        self._store = store
        self._professional_result_reader = professional_result_reader

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
            stage=derive_stage_view(
                events,
                events_complete=events_complete,
                operational_status=run.operational_status,
            ),
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

    def get_constructor_professional_result(self, run_id: str) -> ConstructorProfessionalResultView:
        """Observability proves the run exists. The checkpoint adapter supplies professional state."""
        normalized_run_id = _require_run_id(run_id)
        if self._professional_result_reader is None:
            return unavailable_constructor_professional_result()
        try:
            run = self._store.get_run(normalized_run_id)
        except ObservabilityRunNotFoundError as exc:
            raise ControlRoomRunNotFoundError(str(exc)) from exc
        except ObservabilityStorageFailureError as exc:
            raise ControlRoomStorageUnavailableError("storage unavailable") from exc
        except ObservabilityStoreError as exc:
            raise _translate_store_error(exc) from exc
        try:
            return self._professional_result_reader.read(
                run_id=normalized_run_id,
                agent_code=str(run.agent_code or ""),
            )
        except Exception:
            return inconsistent_constructor_professional_result()

    def get_constructor_decision_registry(
        self,
        run_id: str,
        *,
        outcome: Optional[str] = None,
        system: Optional[str] = None,
        text: Optional[str] = None,
        attention_only: bool = False,
        selected_identity: Optional[str] = None,
    ) -> ConstructorDecisionRegistryView:
        """Filtered read of stored row decisions. Does not run Constructor logic."""
        professional = self.get_constructor_professional_result(run_id)
        if professional.availability is not ProfessionalResultAvailability.AVAILABLE:
            return empty_constructor_decision_registry(professional)
        reader = self._professional_result_reader
        loader = getattr(reader, "read_row_decisions", None)
        if reader is None or not callable(loader):
            return empty_constructor_decision_registry(professional)
        try:
            run = self._store.get_run(_require_run_id(run_id))
            records = tuple(
                loader(
                    run_id=_require_run_id(run_id),
                    agent_code=str(run.agent_code or ""),
                )
            )
        except Exception:
            return empty_constructor_decision_registry(
                inconsistent_constructor_professional_result()
            )
        if any(not isinstance(item, ConstructorRowDecisionView) for item in records):
            return empty_constructor_decision_registry(
                inconsistent_constructor_professional_result()
            )
        counts: dict[str, int] = {}
        systems: set[str] = set()
        attention = 0
        for record in records:
            counts[record.outcome] = counts.get(record.outcome, 0) + 1
            if record.system:
                systems.add(record.system)
            if constructor_row_awaits_human_review(record, professional):
                attention += 1
        filtered = _filter_row_decisions(
            records,
            professional,
            outcome=_optional_text(outcome),
            system=_optional_text(system),
            text=_optional_text(text),
            attention_only=bool(attention_only),
        )
        identity = _optional_text(selected_identity)
        selected = None
        if identity:
            selected = next(
                (item for item in records if item.source_identity == identity),
                None,
            )
        return ConstructorDecisionRegistryView(
            availability=ProfessionalResultAvailability.AVAILABLE,
            professional=professional,
            total_count=len(records),
            outcome_counts=tuple(sorted(counts.items())),
            known_systems=tuple(sorted(systems)),
            attention_count=attention,
            records=filtered,
            selected=selected,
        )


def _filter_row_decisions(
    records: tuple[ConstructorRowDecisionView, ...],
    professional: ConstructorProfessionalResultView,
    *,
    outcome: Optional[str],
    system: Optional[str],
    text: Optional[str],
    attention_only: bool,
) -> tuple[ConstructorRowDecisionView, ...]:
    needle = text.casefold() if text else ""
    kept: list[ConstructorRowDecisionView] = []
    for record in records:
        if outcome and record.outcome != outcome:
            continue
        if system and (record.system or "") != system:
            continue
        if needle:
            haystack = " ".join(
                (record.boq_code, record.name, record.system or "")
            ).casefold()
            if needle not in haystack:
                continue
        if attention_only and not constructor_row_awaits_human_review(record, professional):
            continue
        kept.append(record)
    return tuple(kept)


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
