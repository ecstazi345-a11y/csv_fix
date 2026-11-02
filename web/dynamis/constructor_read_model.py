"""Django read adapter for the Constructor Control Room.

Consumes AgentControlRoomQueryPort. Does not launch Constructor, write a
decision, hand off, or create a runtime database.

The official factory builds SqliteObservabilityStore, and that store commits a
schema bootstrap when it opens. This adapter therefore resolves the same
configured path and opens it with the store's read methods on a read-only
SQLite connection, then passes that store to the official query port.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from agents.control_room.constructor_professional_result_reader import (
    ConstructorProfessionalResultReader,
    sibling_checkpoint_path,
)
from agents.control_room.dtos import (
    AgentRunSnapshot,
    ConstructorDecisionRegistryView,
    ConstructorProfessionalResultView,
    ConstructorRowDecisionView,
    DerivationState,
    ProfessionalResultAvailability,
)
from agents.control_room.errors import (
    ControlRoomQueryError,
    ControlRoomStorageUnavailableError,
)
from agents.control_room.factory import (
    ControlRoomConfigurationError,
    resolve_observability_db_path,
)
from agents.control_room.presentation import (
    DERIVATION_STAGE_INCONSISTENT_RU,
    EVENTS_COMPLETE_FALSE_RU,
    PROFESSIONAL_RESULT_INCONSISTENT_RU,
    PROFESSIONAL_RESULT_UNAVAILABLE_RU,
    constructor_management_scale_lines,
    constructor_month_display,
    constructor_path_labels,
    constructor_project_short,
    constructor_quantity_display,
    constructor_row_outcome_label,
    constructor_work_lines,
    event_type_ru,
    format_timestamp_moscow,
    handoff_status_ru,
    human_review_decision_ru,
    labor_status_ru,
    operational_status_ru,
    professional_path_status_ru,
    recommendation_ru,
    stage_display_state_ru,
)
from agents.control_room.query_port import AgentControlRoomQueryPort
from agents.monthly_plan_constructor.langgraph_runtime import CONSTRUCTOR_AGENT_CODE
from agents.observability.sqlite_store import SqliteObservabilityStore

NOT_IN_CONTRACT = "Недоступно в текущем контракте чтения"
RUNTIME_UNAVAILABLE = "Constructor runtime недоступен"
NO_CONSTRUCTOR_RUNS = "Запусков Constructor в хранилище нет"

_WAITING_PROFESSIONAL_STATUSES = frozenset(
    {"WAITING_FOR_HUMAN_REVIEW", "WAITING_FOR_HUMAN_CONFIRM"}
)
_PREVIEW_LIMIT = 4
_BLOCKING_COUNT_KEY = "blocking_count"
_NON_BLOCKING_COUNT_KEY = "non_blocking_count"


class _ReadOnlyObservabilityStore(SqliteObservabilityStore):
    """Official store reads against an existing file. Does not bootstrap or commit."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = str(db_path)
        self._lock = threading.RLock()
        uri = db_path.resolve().as_uri() + "?mode=ro"
        self._connection = sqlite3.connect(uri, uri=True, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row


def load_constructor_control_room(
    *,
    agents: Optional[list[dict[str, Any]]] = None,
    port_factory: Any = None,
) -> dict[str, Any]:
    """Return Control Room context keys for the latest Constructor run."""
    factory = port_factory or _open_query_port
    port = None
    try:
        port = factory()
        return _read_latest(port, agents)
    except ControlRoomConfigurationError:
        return _unavailable(agents, RUNTIME_UNAVAILABLE)
    except (ControlRoomStorageUnavailableError, ControlRoomQueryError, OSError, sqlite3.Error):
        return _unavailable(agents, RUNTIME_UNAVAILABLE)
    except Exception:
        return _unavailable(agents, RUNTIME_UNAVAILABLE)
    finally:
        _close_port(port)


def constructor_runtime_store_path() -> Optional[Path]:
    """Existing observability file from the official configuration, or None."""
    try:
        return resolve_observability_db_path()
    except ControlRoomConfigurationError:
        return None


def _open_query_port() -> AgentControlRoomQueryPort:
    db_path = resolve_observability_db_path()
    store = _ReadOnlyObservabilityStore(db_path)
    checkpoint = sibling_checkpoint_path(db_path)
    reader = ConstructorProfessionalResultReader(checkpoint) if checkpoint.is_file() else None
    port = AgentControlRoomQueryPort(store, professional_result_reader=reader)
    port._dynamis_store_path = str(db_path)
    return port


def _close_port(port: Any) -> None:
    store = getattr(port, "_store", None)
    close = getattr(store, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception:
        return


def _read_latest(port: AgentControlRoomQueryPort, agents: Optional[list[dict[str, Any]]]) -> dict[str, Any]:
    listed = port.list_runs(agent_code=CONSTRUCTOR_AGENT_CODE, limit=1)
    if not listed.items:
        return _unavailable(agents, NO_CONSTRUCTOR_RUNS)
    run_id = listed.items[0].run_id
    snapshot = port.get_run_snapshot(run_id)
    professional = port.get_constructor_professional_result(run_id)
    registry = port.get_constructor_decision_registry(run_id)
    store_path = str(getattr(port, "_dynamis_store_path", "") or "")
    return _present(snapshot, professional, registry, agents, store_path)


def _present(
    snapshot: AgentRunSnapshot,
    professional: ConstructorProfessionalResultView,
    registry: ConstructorDecisionRegistryView,
    agents: Optional[list[dict[str, Any]]],
    store_path: str,
) -> dict[str, Any]:
    run = snapshot.run
    availability = professional.availability
    professional_known = availability is ProfessionalResultAvailability.AVAILABLE
    status_code = str(professional.professional_status or "").strip() if professional_known else ""
    operational = str(run.operational_status or "").strip()
    tone = "working" if operational == "RUNNING" else "waiting"
    status_label = operational_status_ru(operational) or "—"
    summary = _summary(professional, status_code, operational)
    package_id = _package_id(professional)
    candidate_count = _candidate_count(professional, registry)
    blocking = _safe_count(run.safe_counts, _BLOCKING_COUNT_KEY)
    non_blocking = _safe_count(run.safe_counts, _NON_BLOCKING_COUNT_KEY)
    human_decision = _human_decision(snapshot, professional)
    wait_text = _wait_text(snapshot)
    by_candidate, by_boq = _record_index(registry)
    table_rows = _table_rows(professional, by_candidate, by_boq)
    preview_rows, candidates_note, excluded_note = _preview_rows(
        professional, registry, by_candidate, by_boq
    )
    candidates_empty = _candidates_empty_note(professional, table_rows)
    clarify_empty = "" if any(row["tab"] == "clarify" for row in preview_rows) else (
        "В текущем контракте чтения нет кандидатов с кодами исключений."
        if professional_known
        else _professional_gap(professional)
    )
    if any(row["tab"] == "excluded" for row in preview_rows):
        excluded_empty = ""
    elif registry.availability is ProfessionalResultAvailability.AVAILABLE:
        excluded_empty = "Исключённых позиций в текущем контракте чтения нет."
    else:
        excluded_empty = NOT_IN_CONTRACT
    audit_note = "События официального контракта чтения."
    if not snapshot.events_complete:
        audit_note = f"{audit_note} {EVENTS_COMPLETE_FALSE_RU}"
    facts = (
        ("Запуск", run.run_id),
        ("Статус запуска", status_label),
        ("Профессиональный статус", _professional_status_text(professional)),
        ("Миссия", run.mission_id or NOT_IN_CONTRACT),
        ("Проект", constructor_project_short(run.project_code)),
        ("Период", _month_text(run.month_key)),
        ("Состав миссии", _mission_scope(professional)),
        ("Текущая стадия", _current_stage(snapshot, status_code, professional_known)),
        ("Создан", format_timestamp_moscow(run.requested_at)),
        ("Начат", format_timestamp_moscow(run.started_at)),
        ("Обновлён", format_timestamp_moscow(run.updated_at)),
        ("Кандидатный пакет", package_id),
        ("Кандидатов", candidate_count),
        ("Блокирующие исключения", blocking),
        ("Неблокирующие исключения", non_blocking),
        ("Ожидание человека", wait_text),
        ("Последнее событие", _latest_event(snapshot)),
    )
    return {
        "runtime_notice": "",
        "runtime_available": True,
        "constructor_status": status_label,
        "constructor_tone": tone,
        "constructor_summary": summary,
        "constructor_facts": facts,
        "kpis": _kpis(professional, candidate_count, human_decision),
        "activity": _activity(professional, human_decision),
        "preview_rows": preview_rows,
        "table_rows": table_rows,
        "audit_rows": _audit_rows(snapshot),
        "decision_summary": (
            ("Результат Constructor", summary),
            ("Кандидатный пакет", package_id),
            ("Кандидатов", candidate_count),
            ("Решение человека", human_decision),
            ("Блокирующие исключения", blocking),
            ("Неблокирующие исключения", non_blocking),
            ("Передача", handoff_status_ru(snapshot.handoff.status)),
        ),
        "table_note": (
            f"Чтение запуска {run.run_id}. Страница не изменяет пакет и не записывает решение человека."
        ),
        "audit_note": audit_note,
        "candidates_note": candidates_note,
        "excluded_note": excluded_note,
        "candidates_empty_note": candidates_empty,
        "clarify_empty_note": clarify_empty,
        "excluded_empty_note": excluded_empty,
        "agents": _agents(
            agents,
            status=status_label,
            tone=tone,
            description=summary,
        ),
        "read_model_meta": {
            "store_path": store_path,
            "run_id": run.run_id,
            "operational_status": operational,
            "professional_status": status_code,
            "mission_id": run.mission_id,
            "package_id": package_id,
            "candidate_count": candidate_count,
            "human_decision": human_decision,
            "human_wait": wait_text,
        },
    }


def _unavailable(agents: Optional[list[dict[str, Any]]], notice: str) -> dict[str, Any]:
    return {
        "runtime_notice": notice,
        "runtime_available": False,
        "constructor_status": "НЕДОСТУПЕН",
        "constructor_tone": "waiting",
        "constructor_summary": notice,
        "constructor_facts": (("Состояние Constructor", notice),),
        "kpis": (),
        "activity": (("pending", notice),),
        "preview_rows": (),
        "table_rows": (),
        "audit_rows": (),
        "decision_summary": (
            ("Состояние Constructor", notice),
            ("Кандидатный пакет", NOT_IN_CONTRACT),
            ("Решение человека", NOT_IN_CONTRACT),
        ),
        "table_note": notice,
        "audit_note": notice,
        "candidates_note": "",
        "excluded_note": "",
        "candidates_empty_note": notice,
        "clarify_empty_note": notice,
        "excluded_empty_note": notice,
        "agents": _agents(agents, status="НЕДОСТУПЕН", tone="waiting", description=notice),
        "read_model_meta": {
            "store_path": "",
            "run_id": "",
            "operational_status": "",
            "professional_status": "",
            "mission_id": "",
            "package_id": "",
            "candidate_count": "",
            "human_decision": "",
            "human_wait": "",
        },
    }


def _agents(
    agents: Optional[list[dict[str, Any]]],
    *,
    status: str,
    tone: str,
    description: str,
) -> list[dict[str, Any]]:
    source = list(agents or [])
    updated: list[dict[str, Any]] = []
    for agent in source:
        if agent.get("code") == "constructor":
            updated.append(
                {
                    **agent,
                    "status": status,
                    "tone": tone,
                    "description": description,
                }
            )
        else:
            updated.append(dict(agent))
    return updated


def _summary(
    professional: ConstructorProfessionalResultView,
    status_code: str,
    operational: str,
) -> str:
    if professional.availability is ProfessionalResultAvailability.AVAILABLE:
        lines = constructor_work_lines(professional)
        if lines:
            return lines[-1]
        if status_code:
            return professional_path_status_ru(status_code)
    if professional.availability is ProfessionalResultAvailability.INCONSISTENT:
        return PROFESSIONAL_RESULT_INCONSISTENT_RU
    if professional.availability is ProfessionalResultAvailability.UNAVAILABLE:
        return PROFESSIONAL_RESULT_UNAVAILABLE_RU
    return operational_status_ru(operational) or NOT_IN_CONTRACT


def _professional_status_text(professional: ConstructorProfessionalResultView) -> str:
    if professional.availability is ProfessionalResultAvailability.INCONSISTENT:
        return PROFESSIONAL_RESULT_INCONSISTENT_RU
    if professional.availability is not ProfessionalResultAvailability.AVAILABLE:
        return PROFESSIONAL_RESULT_UNAVAILABLE_RU
    status = str(professional.professional_status or "").strip()
    if not status:
        return NOT_IN_CONTRACT
    return professional_path_status_ru(status)


def _professional_gap(professional: ConstructorProfessionalResultView) -> str:
    if professional.availability is ProfessionalResultAvailability.INCONSISTENT:
        return PROFESSIONAL_RESULT_INCONSISTENT_RU
    return PROFESSIONAL_RESULT_UNAVAILABLE_RU


def _package_id(professional: ConstructorProfessionalResultView) -> str:
    if professional.availability is not ProfessionalResultAvailability.AVAILABLE:
        return _professional_gap(professional)
    package_id = str(professional.source_candidate_package_id or "").strip()
    return package_id or NOT_IN_CONTRACT


def _candidate_count(
    professional: ConstructorProfessionalResultView,
    registry: ConstructorDecisionRegistryView,
) -> str:
    if professional.availability is ProfessionalResultAvailability.AVAILABLE:
        if professional.package_candidate_count is not None:
            return str(professional.package_candidate_count)
    if registry.availability is ProfessionalResultAvailability.AVAILABLE:
        counts = dict(registry.outcome_counts)
        if "CANDIDATE" in counts:
            return str(counts["CANDIDATE"])
    if professional.availability is ProfessionalResultAvailability.AVAILABLE:
        return NOT_IN_CONTRACT
    return _professional_gap(professional)


def _safe_count(safe_counts: tuple[tuple[str, Any], ...], key: str) -> str:
    values = dict(safe_counts)
    if key not in values:
        return NOT_IN_CONTRACT
    return str(values[key])


def _human_decision(
    snapshot: AgentRunSnapshot,
    professional: ConstructorProfessionalResultView,
) -> str:
    observed_waiting = _observed_waiting(snapshot)
    if professional.availability is ProfessionalResultAvailability.AVAILABLE:
        status = str(professional.professional_status or "").strip()
        if status in _WAITING_PROFESSIONAL_STATUSES or observed_waiting:
            return "Требуется"
        if status == "PROFESSIONAL_WORK_COMPLETED" and not observed_waiting:
            return "Не требуется"
        if status:
            return professional_path_status_ru(status)
        return NOT_IN_CONTRACT
    if observed_waiting:
        return "Требуется"
    return NOT_IN_CONTRACT


def _observed_waiting(snapshot: AgentRunSnapshot) -> bool:
    wait = snapshot.human_wait
    return wait.derivation_state is DerivationState.OK and bool(wait.waiting_for_human)


def _wait_text(snapshot: AgentRunSnapshot) -> str:
    if snapshot.human_wait.derivation_state is not DerivationState.OK:
        return NOT_IN_CONTRACT
    return "Да" if snapshot.human_wait.waiting_for_human else "Нет"


def _month_text(month_key: str) -> str:
    return constructor_month_display(month_key)


def _mission_scope(professional: ConstructorProfessionalResultView) -> str:
    if professional.availability is not ProfessionalResultAvailability.AVAILABLE:
        return _professional_gap(professional)
    lines = [
        line
        for line in constructor_management_scale_lines(professional)
        if not line.startswith("Кандидатов")
    ]
    return " · ".join(lines) if lines else NOT_IN_CONTRACT


def _current_stage(
    snapshot: AgentRunSnapshot,
    status_code: str,
    professional_known: bool,
) -> str:
    parts: list[str] = []
    if professional_known and status_code:
        parts.append(professional_path_status_ru(status_code))
    stage = snapshot.stage
    if stage.derivation_state is DerivationState.INCONSISTENT:
        parts.append(DERIVATION_STAGE_INCONSISTENT_RU)
    elif stage.current_stage is not None:
        parts.append(stage_display_state_ru(stage.current_stage.display_state))
    elif not parts:
        return NOT_IN_CONTRACT
    return " · ".join(parts) if parts else NOT_IN_CONTRACT


def _latest_event(snapshot: AgentRunSnapshot) -> str:
    if not snapshot.timeline_events:
        return NOT_IN_CONTRACT
    event = snapshot.timeline_events[-1]
    return f"{event_type_ru(event.event_type)} · {format_timestamp_moscow(event.occurred_at)}"


def _kpis(
    professional: ConstructorProfessionalResultView,
    candidate_count: str,
    human_decision: str,
) -> tuple[tuple[str, str], ...]:
    tiles: list[tuple[str, str]] = []
    if (
        professional.availability is ProfessionalResultAvailability.AVAILABLE
        and professional.mission_scope_row_count is not None
    ):
        tiles.append((str(professional.mission_scope_row_count), "Строк в миссии"))
    if candidate_count.isdigit():
        tiles.append((candidate_count, "Кандидатов"))
    if human_decision in {"Требуется", "Не требуется"}:
        tiles.append((human_decision, "Решение человека"))
    return tuple(tiles)


def _activity(
    professional: ConstructorProfessionalResultView,
    human_decision: str,
) -> tuple[tuple[str, str], ...]:
    if professional.availability is not ProfessionalResultAvailability.AVAILABLE:
        return (("pending", _professional_gap(professional)),)
    labels = list(constructor_path_labels(professional))
    if not labels:
        return (("pending", NOT_IN_CONTRACT),)
    rows = [("done", label) for label in labels[:-1]]
    last_state = "pending" if human_decision == "Требуется" else "done"
    rows.append((last_state, labels[-1]))
    return tuple(rows)


def _record_index(
    registry: ConstructorDecisionRegistryView,
) -> tuple[dict[str, ConstructorRowDecisionView], dict[str, ConstructorRowDecisionView]]:
    by_candidate: dict[str, ConstructorRowDecisionView] = {}
    by_boq: dict[str, ConstructorRowDecisionView] = {}
    if registry.availability is not ProfessionalResultAvailability.AVAILABLE:
        return by_candidate, by_boq
    for record in registry.records:
        if record.candidate_id and record.candidate_id not in by_candidate:
            by_candidate[record.candidate_id] = record
        if record.boq_code and record.boq_code not in by_boq:
            by_boq[record.boq_code] = record
    return by_candidate, by_boq


def _match_record(
    candidate_id: str,
    boq_code: str,
    by_candidate: dict[str, ConstructorRowDecisionView],
    by_boq: dict[str, ConstructorRowDecisionView],
) -> Optional[ConstructorRowDecisionView]:
    if candidate_id and candidate_id in by_candidate:
        return by_candidate[candidate_id]
    if boq_code and boq_code in by_boq:
        return by_boq[boq_code]
    return None


def _table_rows(
    professional: ConstructorProfessionalResultView,
    by_candidate: dict[str, ConstructorRowDecisionView],
    by_boq: dict[str, ConstructorRowDecisionView],
) -> tuple[dict[str, str], ...]:
    if professional.availability is not ProfessionalResultAvailability.AVAILABLE:
        return ()
    rows: list[dict[str, str]] = []
    for candidate in professional.candidates:
        record = _match_record(candidate.candidate_id, candidate.boq_code, by_candidate, by_boq)
        decision = str(candidate.human_review_decision or "").strip()
        status = (
            human_review_decision_ru(decision)
            if decision
            else recommendation_ru(candidate.recommendation)
        )
        comment_parts: list[str] = []
        if candidate.labor_status:
            comment_parts.append(labor_status_ru(candidate.labor_status))
        if candidate.exception_codes:
            comment_parts.append(", ".join(candidate.exception_codes))
        if record is not None and record.reason_text:
            comment_parts.append(record.reason_text)
        rows.append(
            {
                "boq": candidate.boq_code or "—",
                "name": candidate.name or "—",
                "title": (record.facility if record is not None and record.facility else "")
                or professional.facility_id
                or "—",
                "discipline": (record.discipline if record is not None and record.discipline else "")
                or professional.discipline
                or "—",
                "place": _place(record),
                "remaining": _qty(candidate.remaining_qty, candidate.unit),
                "planned": _qty(candidate.already_planned_qty, candidate.unit),
                "proposed": _qty(candidate.available_qty, candidate.unit),
                "status": status or "—",
                "comment": " · ".join(comment_parts),
            }
        )
    return tuple(rows)


def _preview_rows(
    professional: ConstructorProfessionalResultView,
    registry: ConstructorDecisionRegistryView,
    by_candidate: dict[str, ConstructorRowDecisionView],
    by_boq: dict[str, ConstructorRowDecisionView],
) -> tuple[tuple[dict[str, str], ...], str, str]:
    rows: list[dict[str, str]] = []
    candidates_note = ""
    excluded_note = ""
    if professional.availability is ProfessionalResultAvailability.AVAILABLE:
        candidates = tuple(professional.candidates)
        for candidate in candidates[:_PREVIEW_LIMIT]:
            record = _match_record(
                candidate.candidate_id, candidate.boq_code, by_candidate, by_boq
            )
            decision = str(candidate.human_review_decision or "").strip()
            rows.append(
                _preview(
                    "candidates",
                    candidate.boq_code,
                    candidate.name,
                    _place(record),
                    candidate.remaining_qty,
                    candidate.already_planned_qty,
                    candidate.available_qty,
                    candidate.unit,
                    human_review_decision_ru(decision)
                    if decision
                    else recommendation_ru(candidate.recommendation),
                )
            )
        if len(candidates) > _PREVIEW_LIMIT:
            candidates_note = f"Показаны {_PREVIEW_LIMIT} из {len(candidates)}."
        for candidate in candidates:
            if not candidate.exception_codes:
                continue
            record = _match_record(
                candidate.candidate_id, candidate.boq_code, by_candidate, by_boq
            )
            rows.append(
                _preview(
                    "clarify",
                    candidate.boq_code,
                    candidate.name,
                    _place(record),
                    candidate.remaining_qty,
                    candidate.already_planned_qty,
                    candidate.available_qty,
                    candidate.unit,
                    ", ".join(candidate.exception_codes),
                )
            )
    if registry.availability is ProfessionalResultAvailability.AVAILABLE:
        excluded = tuple(record for record in registry.records if record.outcome != "CANDIDATE")
        for record in excluded[:_PREVIEW_LIMIT]:
            rows.append(
                _preview(
                    "excluded",
                    record.boq_code,
                    record.name,
                    _place(record),
                    record.remaining_qty,
                    record.already_planned_qty,
                    record.available_qty,
                    record.unit,
                    constructor_row_outcome_label(record.outcome),
                )
            )
        if len(excluded) > _PREVIEW_LIMIT:
            excluded_note = f"Показаны {_PREVIEW_LIMIT} из {len(excluded)}."
    return tuple(rows), candidates_note, excluded_note


def _preview(
    tab: str,
    boq: str,
    name: str,
    place: str,
    remaining: Optional[str],
    planned: Optional[str],
    proposed: Optional[str],
    unit: str,
    status: str,
) -> dict[str, str]:
    return {
        "tab": tab,
        "boq": boq or "—",
        "name": name or "—",
        "place": place or "—",
        "remaining": _qty(remaining, unit),
        "planned": _qty(planned, unit),
        "proposed": _qty(proposed, unit),
        "status": status or "—",
    }


def _candidates_empty_note(
    professional: ConstructorProfessionalResultView,
    table_rows: tuple[dict[str, str], ...],
) -> str:
    if table_rows:
        return ""
    if professional.availability is ProfessionalResultAvailability.AVAILABLE:
        return "Кандидатов в текущем контракте чтения нет."
    return _professional_gap(professional)


def _audit_rows(snapshot: AgentRunSnapshot) -> tuple[dict[str, str], ...]:
    run = snapshot.run
    rows: list[dict[str, str]] = []
    for event in reversed(snapshot.timeline_events):
        artifact_type = str(event.artifact_type or "").strip()
        artifact_id = str(event.artifact_id or "").strip()
        if artifact_type and artifact_id:
            artifact = f"{artifact_type} {artifact_id}"
        else:
            artifact = artifact_type or artifact_id or "—"
        rows.append(
            {
                "run": run.run_id,
                "mission": run.mission_id or "—",
                "event": event_type_ru(event.event_type),
                "timestamp": format_timestamp_moscow(event.occurred_at),
                "agent": "Constructor",
                "artifact": artifact,
                "handoff": str(event.handoff_id or "").strip() or "—",
                "status": str(event.status or "").strip() or "—",
            }
        )
    return tuple(rows)


def _place(record: Optional[ConstructorRowDecisionView]) -> str:
    if record is None:
        return "—"
    parts = [part for part in (str(record.system or "").strip(), str(record.iwp or "").strip()) if part]
    return " / ".join(parts) if parts else "—"


def _qty(stored: Optional[str], unit: str) -> str:
    return constructor_quantity_display("" if stored is None else str(stored), unit)
