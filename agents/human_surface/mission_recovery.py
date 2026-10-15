"""Read-only recovery of one Human Surface mission after session loss.

Streamlit session is not the execution record. This module does not launch,
write, or create a store. Ambiguous unfinished runs stay unselected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from agents.human_surface.mission_draft import CONSTRUCTOR_AGENT_CODE, WorkingContext
from agents.human_surface.work_context import PLANNING_MONTHS_2026, project_label, queue_from_facility
from agents.human_surface.workforce import contour_code_for_employee
from agents.observability.contracts import TERMINAL_OPERATIONAL_STATUSES, _unfreeze_jsonable
from utils.month_key import normalize_month_key


HUMAN_SURFACE_INITIATOR = "human-surface"
RECOVERY_CONTINUE_RU = "Продолжить ранее запущенную задачу"
CONTINUES_EXECUTION_RU = "Инженер формирования месячного плана продолжает выполнение задачи."
REALITY_LOADED = "REALITY_LOADED"
STATUS_WAITING_FOR_HUMAN_REVIEW = "WAITING_FOR_HUMAN_REVIEW"
_TERMINAL_OPS = frozenset(
    member.value if hasattr(member, "value") else str(member)
    for member in TERMINAL_OPERATIONAL_STATUSES
)

_EXECUTING = frozenset({"REQUESTED", "AUTHORIZING", "STARTING", "RUNNING", "RETRYING"})
_WAITING = frozenset({"WAITING_FOR_HUMAN", "WAITING_FOR_HUMAN_REVIEW"})


@dataclass(frozen=True)
class DurableRunEvidence:
    run_id: str
    mission_id: str
    initiator_id: str
    agent_code: str
    project_code: str
    month_key: str
    operational_status: str
    requested_at: datetime
    scope_summary: Mapping[str, Any]
    trigger_reason: str = ""
    lifecycle_status: str = ""
    has_candidate_package: bool = False


@dataclass(frozen=True)
class RecoveredMission:
    run_id: str
    mission_id: str
    project_label: str
    planning_month: str
    queue: Optional[str]
    titles: tuple[str, ...]
    discipline: Optional[str]
    systems: tuple[str, ...]
    packages: Optional[str]
    intent: str
    operational_status: str
    lifecycle_status: str
    requested_at: datetime


@dataclass(frozen=True)
class RecoveryDecision:
    selected: Optional[RecoveredMission]
    choices: tuple[RecoveredMission, ...]
    ambiguous: bool


def decide_recovery(
    evidence: Sequence[DurableRunEvidence],
    *,
    months: Sequence[str] = PLANNING_MONTHS_2026,
    project_code: Optional[str] = None,
    month_key: Optional[str] = None,
) -> RecoveryDecision:
    """Pick one unfinished human-surface Constructor run, or refuse to guess.

    Prefer durable professional WAITING_FOR_HUMAN_REVIEW runs that already
    carry a Candidate Package over executing/waiting shells and FAILED noise.
    """
    professional = tuple(
        item
        for item in evidence
        if _is_usable_professional(item)
        and _matches_project_month(item, project_code=project_code, month_key=month_key)
    )
    if professional:
        # Same Project+Month: reuse the earliest durable packaged result.
        # Distinct Project/Month groups without a filter stay ambiguous.
        groups: dict[tuple[str, str], list[DurableRunEvidence]] = {}
        for item in professional:
            month_norm = normalize_month_key(str(item.month_key or "").replace(" ", "-"))
            key = (str(item.project_code or "").strip(), str(month_norm or ""))
            groups.setdefault(key, []).append(item)
        if len(groups) == 1:
            only = next(iter(groups.values()))
            chosen = sorted(only, key=lambda item: (item.requested_at, item.run_id))[0]
            return RecoveryDecision(
                selected=_to_mission(chosen, months),
                choices=(),
                ambiguous=False,
            )
        choices = tuple(_to_mission(item, months) for item in _newest_first(professional))
        return RecoveryDecision(selected=None, choices=choices, ambiguous=True)

    unfinished = tuple(
        item
        for item in evidence
        if _is_recoverable_unfinished(item)
        and _matches_project_month(item, project_code=project_code, month_key=month_key)
    )
    executing = tuple(item for item in unfinished if item.operational_status in _EXECUTING)
    waiting = tuple(item for item in unfinished if item.operational_status in _WAITING)
    if len(executing) == 1:
        chosen = _to_mission(executing[0], months)
        return RecoveryDecision(selected=chosen, choices=(), ambiguous=False)
    if len(executing) > 1:
        choices = tuple(_to_mission(item, months) for item in _newest_first(executing))
        return RecoveryDecision(selected=None, choices=choices, ambiguous=True)
    if len(waiting) == 1:
        chosen = _to_mission(waiting[0], months)
        return RecoveryDecision(selected=chosen, choices=(), ambiguous=False)
    if len(waiting) > 1:
        choices = tuple(_to_mission(item, months) for item in _newest_first(waiting))
        return RecoveryDecision(selected=None, choices=choices, ambiguous=True)
    return RecoveryDecision(selected=None, choices=(), ambiguous=False)


def working_context_from_mission(mission: RecoveredMission) -> WorkingContext:
    return WorkingContext(
        project=mission.project_label or None,
        planning_month=mission.planning_month or None,
        queue=mission.queue,
        titles=mission.titles,
        discipline=mission.discipline,
        systems=mission.systems,
        packages=mission.packages,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        intent=mission.intent or None,
        contour_code=contour_code_for_employee(CONSTRUCTOR_AGENT_CODE),
    )


def load_recovery_decision(
    port: object,
    *,
    project_code: Optional[str] = None,
    month_key: Optional[str] = None,
) -> RecoveryDecision:
    """Read durable runs through the existing query port. Does not launch."""
    evidence = list_durable_run_evidence(port)
    return decide_recovery(
        evidence,
        project_code=project_code,
        month_key=month_key,
    )


def list_durable_run_evidence(port: object) -> tuple[DurableRunEvidence, ...]:
    store = getattr(port, "_store", None)
    list_runs = getattr(store, "list_runs", None)
    if store is None or not callable(list_runs):
        return ()
    runs = list_runs(agent_code=CONSTRUCTOR_AGENT_CODE, limit=200)
    return tuple(_evidence_from_run(store, run) for run in runs)


def find_usable_professional_run(
    port: object,
    *,
    project_code: str,
    month_key: str,
    queue: Optional[str] = None,
    months: Sequence[str] = PLANNING_MONTHS_2026,
) -> Optional[RecoveredMission]:
    """Durable Project+Month(+Queue) professional WAITING run with Candidate Package."""
    evidence = list_durable_run_evidence(port)
    matches = tuple(
        item
        for item in evidence
        if _is_usable_professional(item)
        and _matches_project_month(item, project_code=project_code, month_key=month_key)
        and _matches_queue(item, queue=queue)
    )
    if not matches:
        return None
    # Prefer oldest usable professional result for the month (first completed package).
    chosen = tuple(sorted(matches, key=lambda item: (item.requested_at, item.run_id)))[0]
    return _to_mission(chosen, months)


def operational_status_for_run(port: object, run_id: str) -> str:
    """Read durable operational status for one run_id. Empty when unknown."""
    target = str(run_id or "").strip()
    if not target:
        return ""
    for item in list_durable_run_evidence(port):
        if item.run_id == target:
            return str(item.operational_status or "").strip()
    return ""


def _is_usable_professional(item: DurableRunEvidence) -> bool:
    if item.initiator_id != HUMAN_SURFACE_INITIATOR:
        return False
    if item.agent_code != CONSTRUCTOR_AGENT_CODE:
        return False
    if not str(item.run_id or "").strip():
        return False
    status = str(item.operational_status or "").strip()
    if status in _TERMINAL_OPS:
        return False
    if str(item.lifecycle_status or "").strip() != STATUS_WAITING_FOR_HUMAN_REVIEW:
        return False
    return bool(item.has_candidate_package)


def _matches_project_month(
    item: DurableRunEvidence,
    *,
    project_code: Optional[str],
    month_key: Optional[str],
) -> bool:
    project = str(project_code or "").strip()
    month = str(month_key or "").strip()
    if project and str(item.project_code or "").strip() != project:
        return False
    if month:
        left = normalize_month_key(str(item.month_key or "").replace(" ", "-"))
        right = normalize_month_key(month.replace(" ", "-"))
        if left is None or right is None or left != right:
            return False
    return True


def _matches_queue(item: DurableRunEvidence, *, queue: Optional[str]) -> bool:
    wanted = str(queue or "").strip()
    if not wanted:
        return True
    scope = item.scope_summary if isinstance(item.scope_summary, Mapping) else {}
    facilities = _scope_values(scope, "facility") or _scope_values(scope, "facility_building")
    if not facilities:
        # Unrestricted facility scope covers every queue for this project/month.
        return True
    found = {queue_from_facility(name) for name in facilities}
    found.discard("")
    return wanted in found


def _is_recoverable_unfinished(item: DurableRunEvidence) -> bool:
    if item.initiator_id != HUMAN_SURFACE_INITIATOR:
        return False
    if item.agent_code != CONSTRUCTOR_AGENT_CODE:
        return False
    if not str(item.run_id or "").strip():
        return False
    status = str(item.operational_status or "").strip()
    if status in _TERMINAL_OPS:
        return False
    return status in _EXECUTING or status in _WAITING


def _newest_first(items: Sequence[DurableRunEvidence]) -> tuple[DurableRunEvidence, ...]:
    return tuple(sorted(items, key=lambda item: (item.requested_at, item.run_id), reverse=True))


def _to_mission(item: DurableRunEvidence, months: Sequence[str]) -> RecoveredMission:
    scope = item.scope_summary if isinstance(item.scope_summary, Mapping) else {}
    titles = _scope_values(scope, "facility") or _scope_values(scope, "facility_building")
    return RecoveredMission(
        run_id=item.run_id,
        mission_id=item.mission_id,
        project_label=project_label(item.project_code),
        planning_month=_display_month(item.month_key, months),
        queue=_unique_queue(titles),
        titles=titles,
        discipline=_single_scope_value(scope, "discipline"),
        systems=_scope_values(scope, "system"),
        packages=_packages(scope),
        intent=str(item.trigger_reason or "").strip(),
        operational_status=item.operational_status,
        lifecycle_status=str(item.lifecycle_status or "").strip(),
        requested_at=item.requested_at,
    )


def _unique_queue(titles: Sequence[str]) -> Optional[str]:
    if not titles:
        return None
    found = {queue_from_facility(item) for item in titles}
    found.discard("")
    if len(found) == 1:
        return next(iter(found))
    return None


def _display_month(stored: str, months: Sequence[str]) -> str:
    canonical = normalize_month_key(stored)
    if canonical is None:
        text = " ".join(str(stored or "").split())
        return text if text in months else ""
    matches = [
        item
        for item in months
        if normalize_month_key(str(item).replace(" ", "-")) == canonical
    ]
    if len(matches) == 1:
        return matches[0]
    return ""


def _scope_values(scope: Mapping[str, Any], key: str) -> tuple[str, ...]:
    raw = scope.get(key)
    if isinstance(raw, str):
        text = raw.strip()
        return (text,) if text else ()
    if isinstance(raw, (list, tuple)):
        found: list[str] = []
        for item in raw:
            text = str(item or "").strip()
            if text and text not in found:
                found.append(text)
        return tuple(found)
    return ()


def _single_scope_value(scope: Mapping[str, Any], key: str) -> Optional[str]:
    values = _scope_values(scope, key)
    if len(values) == 1:
        return values[0]
    return None


def _packages(scope: Mapping[str, Any]) -> Optional[str]:
    values = _scope_values(scope, "iwp")
    if not values:
        return None
    return ", ".join(values)


def _evidence_from_run(store: object, run: object) -> DurableRunEvidence:
    status = getattr(run, "operational_status", "")
    status_text = status.value if hasattr(status, "value") else str(status or "")
    requested = getattr(run, "requested_at", None)
    if not isinstance(requested, datetime):
        requested = datetime.fromtimestamp(0, timezone.utc)
    lifecycle_status, has_package = _checkpoint_truth(
        store,
        str(getattr(run, "run_id", "") or ""),
    )
    return DurableRunEvidence(
        run_id=str(getattr(run, "run_id", "") or ""),
        mission_id=str(getattr(run, "mission_id", "") or ""),
        initiator_id=str(getattr(run, "initiator_id", "") or ""),
        agent_code=str(getattr(run, "agent_code", "") or ""),
        project_code=str(getattr(run, "project_code", "") or ""),
        month_key=str(getattr(run, "month_key", "") or ""),
        operational_status=status_text,
        requested_at=requested,
        scope_summary=_scope_mapping(getattr(run, "scope_summary", {})),
        trigger_reason=str(getattr(run, "trigger_reason", "") or ""),
        lifecycle_status=lifecycle_status,
        has_candidate_package=has_package,
    )


def _scope_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        thawed = _unfreeze_jsonable(value)
    except Exception:
        return {}
    return thawed if isinstance(thawed, dict) else {}


def _checkpoint_lifecycle(store: object, run_id: str) -> str:
    status, _has_package = _checkpoint_truth(store, run_id)
    return status


def _checkpoint_truth(store: object, run_id: str) -> tuple[str, bool]:
    db_path = getattr(store, "_db_path", None)
    if not db_path or not run_id:
        return "", False
    try:
        from agents.control_room.constructor_professional_result_reader import (
            _load_lifecycle,
            sibling_checkpoint_path,
        )

        lifecycle = _load_lifecycle(sibling_checkpoint_path(db_path), thread_id=run_id)
    except Exception:
        return "", False
    if lifecycle is None:
        return "", False
    status = str(getattr(lifecycle, "status", "") or "")
    package = getattr(lifecycle, "package", None)
    package_id = str(getattr(package, "package_id", "") or "").strip() if package is not None else ""
    return status, bool(package_id)
