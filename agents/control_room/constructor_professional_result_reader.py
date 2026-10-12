"""
Read-only Control Room adapter: Constructor durable checkpoint → professional DTOs.

Opens checkpoints.sqlite beside the observability file. Does not create files,
run DDL, mutate checkpoints, or start Constructor execution.
Page 53 must not import this module.
"""

from __future__ import annotations

import math
import sqlite3
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

from langgraph.checkpoint.sqlite import SqliteSaver

from agents.control_room.dtos import (
    ConstructorCandidateResultView,
    ConstructorProfessionalResultView,
    ConstructorRowDecisionView,
    ProfessionalResultAvailability,
    inconsistent_constructor_professional_result,
    unavailable_constructor_professional_result,
)
from agents.monthly_plan_constructor.durable_checkpoint import (
    build_constructor_jsonplus_serializer,
)
from agents.monthly_plan_constructor.langgraph_runtime import CONSTRUCTOR_AGENT_CODE
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_PROFESSIONAL_WORK_COMPLETED,
    ConstructorLifecycleState,
)

CHECKPOINTS_DB_FILENAME = "checkpoints.sqlite"


def sibling_checkpoint_path(observability_db_path: Union[str, Path]) -> Path:
    return Path(observability_db_path).resolve().parent / CHECKPOINTS_DB_FILENAME


def transcribe_stored_quantity(value: Any) -> str:
    """Transcribe a stored int/float without rounding a residual to zero."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("quantity must be int or float")
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise ValueError("quantity must be finite")
    return format(value, ".16g")


class ConstructorProfessionalResultReader:
    """Read ConstructorLifecycleState for one run_id. Observe only."""

    def __init__(self, checkpoint_db_path: Union[str, Path]) -> None:
        self._checkpoint_db_path = Path(checkpoint_db_path)

    def read(self, *, run_id: str, agent_code: str) -> ConstructorProfessionalResultView:
        if str(agent_code or "").strip() != CONSTRUCTOR_AGENT_CODE:
            return unavailable_constructor_professional_result()
        thread_id = str(run_id or "").strip()
        if not thread_id:
            return unavailable_constructor_professional_result()
        if not self._checkpoint_db_path.is_file():
            return unavailable_constructor_professional_result()
        try:
            lifecycle = _load_lifecycle(self._checkpoint_db_path, thread_id=thread_id)
        except sqlite3.Error:
            return inconsistent_constructor_professional_result()
        except Exception:
            return inconsistent_constructor_professional_result()
        if lifecycle is None:
            return unavailable_constructor_professional_result()
        if not isinstance(lifecycle, ConstructorLifecycleState):
            return inconsistent_constructor_professional_result()
        try:
            return map_constructor_lifecycle(lifecycle)
        except Exception:
            return inconsistent_constructor_professional_result()

    def read_row_decisions(
        self,
        *,
        run_id: str,
        agent_code: str,
    ) -> tuple[ConstructorRowDecisionView, ...]:
        if str(agent_code or "").strip() != CONSTRUCTOR_AGENT_CODE:
            return ()
        thread_id = str(run_id or "").strip()
        if not thread_id or not self._checkpoint_db_path.is_file():
            return ()
        lifecycle = _load_lifecycle(self._checkpoint_db_path, thread_id=thread_id)
        if not isinstance(lifecycle, ConstructorLifecycleState):
            raise ValueError("checkpoint lifecycle is missing")
        return map_constructor_row_decisions(lifecycle)


def map_constructor_lifecycle(
    lifecycle: ConstructorLifecycleState,
) -> ConstructorProfessionalResultView:
    scope = lifecycle.scope
    package = lifecycle.package
    if scope is None or package is None:
        return unavailable_constructor_professional_result()

    reviewed = lifecycle.reviewed_package
    reviewed_by_id: dict[str, Any] = {}
    included_count: Optional[int] = None
    excluded_count: Optional[int] = None
    unresolved_count: Optional[int] = None
    reviewed_package_id = ""
    if reviewed is not None:
        records = tuple(getattr(reviewed, "reviewed_records", ()) or ())
        included_count = int(reviewed.included_count)
        excluded_count = int(reviewed.excluded_count)
        unresolved_count = int(reviewed.unresolved_count)
        if included_count + excluded_count + unresolved_count != len(records):
            return inconsistent_constructor_professional_result()
        if str(reviewed.source_candidate_package_id) != str(package.package_id):
            return inconsistent_constructor_professional_result()
        if str(reviewed.run_id) != str(lifecycle.run_id):
            return inconsistent_constructor_professional_result()
        reviewed_package_id = str(reviewed.reviewed_package_id)
        for record in records:
            source = record.source_candidate
            candidate_id = str(source.candidate_id)
            if candidate_id in reviewed_by_id:
                return inconsistent_constructor_professional_result()
            reviewed_by_id[candidate_id] = record

    package_ids = [str(item.candidate_id) for item in package.candidates]
    if reviewed is not None and set(reviewed_by_id) != set(package_ids):
        return inconsistent_constructor_professional_result()

    confirm_event_id = ""
    confirm_decision = ""
    confirm_actor_type = ""
    confirm_actor_id = ""
    confirms = tuple(lifecycle.human_confirm_events or ())
    if len(confirms) > 1:
        return inconsistent_constructor_professional_result()
    if lifecycle.status == STATUS_PROFESSIONAL_WORK_COMPLETED and len(confirms) != 1:
        return inconsistent_constructor_professional_result()
    if len(confirms) == 1:
        confirm = confirms[0]
        if str(confirm.run_id) != str(lifecycle.run_id):
            return inconsistent_constructor_professional_result()
        if reviewed is not None and str(confirm.reviewed_package_id) != reviewed_package_id:
            return inconsistent_constructor_professional_result()
        confirm_event_id = str(confirm.confirm_event_id)
        confirm_decision = _enum_text(confirm.decision)
        confirm_actor_type = str(confirm.actor_type)
        confirm_actor_id = str(confirm.actor_id)

    exceptions_by_candidate = _exception_codes_by_candidate(lifecycle.exceptions)
    candidates = tuple(
        _map_candidate(
            item,
            reviewed_by_id.get(str(item.candidate_id)),
            exceptions_by_candidate.get(str(item.candidate_id), ()),
        )
        for item in package.candidates
    )
    scope_row_count, scope_source = _mission_scope_facts(lifecycle)
    summary = package.summary
    scanned_count = _non_negative(summary.scanned_count, "scanned_count")
    package_candidate_count = _non_negative(summary.candidate_count, "candidate_count")
    excluded_completed_count = _non_negative(
        summary.excluded_completed_count, "excluded_completed_count"
    )
    excluded_no_remainder_count = _non_negative(
        summary.excluded_no_remainder_count, "excluded_no_remainder_count"
    )
    already_planned_count = _non_negative(
        summary.already_planned_count, "already_planned_count"
    )
    if package_candidate_count != len(package.candidates):
        return inconsistent_constructor_professional_result()
    if scanned_count < package_candidate_count:
        return inconsistent_constructor_professional_result()
    return ConstructorProfessionalResultView(
        availability=ProfessionalResultAvailability.AVAILABLE,
        run_id=str(lifecycle.run_id),
        mission_id=str(lifecycle.mission_id),
        professional_status=str(lifecycle.status),
        project_id=str(scope.project_code),
        month=str(scope.month_key),
        facility_id=_scope_text(scope.facility_scope),
        discipline=_scope_text(scope.discipline_scope),
        source_candidate_package_id=str(package.package_id),
        reviewed_package_id=reviewed_package_id,
        included_count=included_count,
        excluded_count=excluded_count,
        unresolved_count=unresolved_count,
        confirm_event_id=confirm_event_id,
        confirm_decision=confirm_decision,
        confirm_actor_type=confirm_actor_type,
        confirm_actor_id=confirm_actor_id,
        path_statuses=_path_statuses(lifecycle),
        candidates=candidates,
        mission_scope_row_count=scope_row_count,
        mission_scope_source=scope_source,
        scanned_count=scanned_count,
        excluded_completed_count=excluded_completed_count,
        excluded_no_remainder_count=excluded_no_remainder_count,
        already_planned_count=already_planned_count,
        package_candidate_count=package_candidate_count,
    )


def _mission_scope_facts(lifecycle: ConstructorLifecycleState) -> tuple[Optional[int], str]:
    reality = lifecycle.reality_read
    if reality is None:
        return None, ""
    row_count = _non_negative(reality.row_count, "reality_read.row_count")
    rows = tuple(getattr(reality, "rows", ()) or ())
    if row_count != len(rows):
        raise ValueError("reality_read.row_count does not match stored rows")
    provenance = getattr(reality, "provenance", None)
    if provenance is not None:
        provenance_count = _non_negative(provenance.row_count, "provenance.row_count")
        if provenance_count != row_count:
            raise ValueError("provenance.row_count does not match reality_read.row_count")
    source = str(getattr(provenance, "source_reference", "") or "").strip()
    return row_count, source


def _non_negative(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an int")
    if value < 0:
        raise ValueError(f"{label} must be non-negative")
    return value


def _map_candidate(
    item: Any,
    reviewed: Any,
    exception_codes: tuple[str, ...],
) -> ConstructorCandidateResultView:
    decision = ""
    disposition = ""
    reason = ""
    if reviewed is not None:
        decision = _enum_text(reviewed.human_review_decision)
        disposition = _enum_text(reviewed.disposition)
        reasons = tuple(reviewed.disposition_reason_codes or ())
        reason = str(reasons[0]) if reasons else ""
    recommendation = str(item.recommendation or "")
    return ConstructorCandidateResultView(
        candidate_id=str(item.candidate_id),
        boq_code=str(item.boq_code),
        name=str(item.boq_name),
        unit=str(item.unit),
        remaining_qty=transcribe_stored_quantity(item.remaining_qty),
        already_planned_qty=transcribe_stored_quantity(item.already_planned_qty),
        available_qty=transcribe_stored_quantity(item.available_to_add_qty),
        labor_status=str(item.labor_norm_status or ""),
        recommendation=recommendation,
        exception_codes=exception_codes,
        human_review_decision=decision,
        final_disposition=disposition,
        final_reason_code=reason,
    )


def _exception_codes_by_candidate(exceptions: Any) -> dict[str, tuple[str, ...]]:
    if exceptions is None:
        return {}
    grouped: dict[str, list[str]] = {}
    for item in tuple(getattr(exceptions, "exceptions", ()) or ()):
        candidate_id = str(getattr(item, "candidate_id", "") or "").strip()
        code = str(getattr(item, "exception_code", "") or "").strip()
        if not candidate_id or not code:
            continue
        grouped.setdefault(candidate_id, [])
        if code not in grouped[candidate_id]:
            grouped[candidate_id].append(code)
    return {key: tuple(value) for key, value in grouped.items()}


def _path_statuses(lifecycle: ConstructorLifecycleState) -> tuple[str, ...]:
    ordered: list[str] = []
    for transition in tuple(lifecycle.transitions or ()):
        status = str(getattr(transition, "to_status", "") or "").strip()
        if status and status not in ordered:
            ordered.append(status)
    current = str(lifecycle.status or "").strip()
    if current and current not in ordered:
        ordered.append(current)
    return tuple(ordered)


def _scope_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(parts)
    raise TypeError("scope value must be text or a sequence of text")


def _enum_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def map_constructor_row_decisions(
    lifecycle: ConstructorLifecycleState,
) -> tuple[ConstructorRowDecisionView, ...]:
    raw = tuple(getattr(lifecycle, "row_decisions", ()) or ())
    records = tuple(_map_row_decision(item) for item in raw)
    identities = [item.source_identity for item in records]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate row decision identity")
    reality = lifecycle.reality_read
    if records and reality is not None:
        row_count = _non_negative(reality.row_count, "reality_read.row_count")
        if row_count != len(records):
            raise ValueError("scope rows and decision records differ")
    return records


def _map_row_decision(record: Any) -> ConstructorRowDecisionView:
    requires_human = getattr(record, "requires_human", None)
    if requires_human is not None and not isinstance(requires_human, bool):
        raise TypeError("requires_human must be true, false, or unknown")
    system = getattr(record, "system", None)
    system_text = str(system).strip() if system is not None else ""
    return ConstructorRowDecisionView(
        source_identity=str(record.source_identity),
        source_order=int(record.source_order),
        boq_code=str(record.boq_code or ""),
        name=str(record.boq_name or ""),
        unit=str(record.unit or ""),
        system=system_text or None,
        remaining_qty=_optional_quantity(getattr(record, "remaining_qty", None)),
        already_planned_qty=_optional_quantity(getattr(record, "already_planned_qty", None)),
        available_qty=_optional_quantity(getattr(record, "available_qty", None)),
        outcome=str(record.outcome or ""),
        reason_code=str(record.reason_code or ""),
        reason_text=str(record.reason_text or ""),
        requires_human=requires_human,
        candidate_created=bool(record.candidate_created),
        candidate_id=str(getattr(record, "candidate_id", "") or ""),
        facility=str(getattr(record, "facility", "") or ""),
        discipline=str(getattr(record, "discipline", "") or ""),
        iwp=str(getattr(record, "iwp", "") or ""),
    )


def _optional_quantity(value: Any) -> Optional[str]:
    if value is None:
        return None
    return transcribe_stored_quantity(value)


def _load_lifecycle(db_path: Path, *, thread_id: str) -> Optional[Any]:
    connection = _open_readonly(db_path)
    try:
        serializer = build_constructor_jsonplus_serializer()
        checkpointer = SqliteSaver(connection, serde=serializer)
        tup = checkpointer.get_tuple(
            {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
        )
        if tup is None:
            return None
        checkpoint = getattr(tup, "checkpoint", None) or {}
        values = checkpoint.get("channel_values") if isinstance(checkpoint, dict) else None
        if not isinstance(values, dict):
            raise ValueError("checkpoint channel_values missing")
        return values.get("lifecycle")
    finally:
        connection.close()


def _open_readonly(db_path: Path) -> sqlite3.Connection:
    uri = db_path.resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, check_same_thread=False)
