"""Human authority over one already interpreted typed mission draft.

The result is a confirmed request for a later controlled launch. It is not a
runtime mission, not an agent run, and it does not start Constructor.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Mapping
from uuid import uuid4

from agents.human_surface.command_interpretation import (
    INTENT_FORM_CANDIDATE_PACKAGE,
    INTENT_FORM_MONTHLY_COMMITMENT,
    STATE_NEEDS_CONFIRMATION,
    CommandInterpretation,
)
from agents.human_surface.work_context import WorkContextCatalog
from agents.human_surface.workforce import CONSTRUCTOR_AGENT_CODE
from agents.monthly_plan_constructor.mission_scope import (
    MissionScopeError,
    build_constructor_mission_scope,
)
from utils.month_key import format_month_key_ru, normalize_month_key

CONFIRMATION_CONFIRMED = "CONFIRMED"
CONFIRMED_BY_HUMAN_SURFACE = "human-surface-operator"
SCOPE_FIELDS = (
    "project_code",
    "project_label",
    "month_key",
    "planning_month",
    "queue",
    "facility",
    "discipline",
)


class ConfirmationRejected(ValueError):
    """The draft cannot be confirmed. No authority record is created."""


@dataclass(frozen=True)
class HumanConfirmation:
    confirmation_id: str
    command_id: str
    interpretation_id: str
    target_agent: str
    resolved_scope: Mapping[str, str]
    confirmed_by: str
    confirmed_at: str
    confirmation_state: str
    source_text: str

    def as_dict(self) -> dict[str, object]:
        return {
            "confirmation_id": self.confirmation_id,
            "command_id": self.command_id,
            "interpretation_id": self.interpretation_id,
            "target_agent": self.target_agent,
            "resolved_scope": dict(self.resolved_scope),
            "confirmed_by": self.confirmed_by,
            "confirmed_at": self.confirmed_at,
            "confirmation_state": CONFIRMATION_CONFIRMED,
            "source_text": self.source_text,
            "mission_created": False,
            "constructor_run_created": False,
        }


def scope_snapshot(resolved: object) -> dict[str, str]:
    """Copy the exact typed scope. Missing or blank fields fail closed."""
    if not isinstance(resolved, Mapping):
        raise ConfirmationRejected("resolved scope is missing")
    snapshot: dict[str, str] = {}
    for key in SCOPE_FIELDS:
        value = resolved.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ConfirmationRejected(f"{key} is unresolved")
        snapshot[key] = value.strip()
    return snapshot


def confirm_typed_draft(
    interpretation: CommandInterpretation,
    *,
    catalog: WorkContextCatalog,
    source_text: str,
    confirmed_by: str = CONFIRMED_BY_HUMAN_SURFACE,
) -> HumanConfirmation:
    """Bind authority to one ready draft. The scope is snapshotted, not widened."""
    if confirmed_by != CONFIRMED_BY_HUMAN_SURFACE:
        raise ConfirmationRejected("confirmed_by is not the human surface actor")
    if interpretation.processing_state != STATE_NEEDS_CONFIRMATION:
        raise ConfirmationRejected("interpretation is not waiting for confirmation")
    if interpretation.unresolved_fields or interpretation.ambiguities:
        raise ConfirmationRejected("interpretation still has open questions")
    if interpretation.target_agent != CONSTRUCTOR_AGENT_CODE:
        raise ConfirmationRejected("target agent is not confirmable")
    if interpretation.intent not in {
        INTENT_FORM_CANDIDATE_PACKAGE,
        INTENT_FORM_MONTHLY_COMMITMENT,
    }:
        raise ConfirmationRejected("intent is not confirmable")
    if interpretation.mission_created:
        raise ConfirmationRejected("a draft must not already be a mission")
    if not str(interpretation.command_id or "").strip():
        raise ConfirmationRejected("command_id is missing")
    if not str(interpretation.interpretation_id or "").strip():
        raise ConfirmationRejected("interpretation_id is missing")
    text = str(source_text or "").strip()
    if not text:
        raise ConfirmationRejected("source command is missing")
    snapshot = scope_snapshot(interpretation.resolved_scope)
    _require_constructor_scope(snapshot)
    if not _scope_is_in_catalog(snapshot, catalog):
        raise ConfirmationRejected("resolved scope is not in the catalog")
    return HumanConfirmation(
        confirmation_id=str(uuid4()),
        command_id=interpretation.command_id,
        interpretation_id=interpretation.interpretation_id,
        target_agent=interpretation.target_agent,
        resolved_scope=MappingProxyType(snapshot),
        confirmed_by=confirmed_by,
        confirmed_at=datetime.now(timezone.utc).isoformat(),
        confirmation_state=CONFIRMATION_CONFIRMED,
        source_text=text,
    )


def same_scope(left: object, right: object) -> bool:
    try:
        return scope_snapshot(left) == scope_snapshot(right)
    except ConfirmationRejected:
        return False


def _require_constructor_scope(snapshot: Mapping[str, str]) -> None:
    try:
        scope = build_constructor_mission_scope(
            project_code=snapshot["project_code"],
            month_key=snapshot["month_key"],
            facility_scope=(snapshot["facility"],),
            discipline_scope=(snapshot["discipline"],),
            queue_scope=(snapshot["queue"],),
        )
    except MissionScopeError as exc:
        raise ConfirmationRejected("ConstructorMissionScope rejected the draft") from exc
    month = format_month_key_ru(scope.month_key_canonical)
    period = normalize_month_key(snapshot["planning_month"].replace(" ", "-"))
    if (
        scope.project_code != snapshot["project_code"].upper()
        or month != snapshot["month_key"]
        or period != scope.month_key_canonical
        or scope.queue_scope != (snapshot["queue"].upper(),)
        or scope.facility_scope != (snapshot["facility"].upper(),)
        or scope.discipline_scope != (snapshot["discipline"].upper(),)
    ):
        raise ConfirmationRejected("resolved scope does not match ConstructorMissionScope")


def _scope_is_in_catalog(snapshot: Mapping[str, str], catalog: WorkContextCatalog) -> bool:
    if catalog is None or catalog.error or not catalog.facts:
        return False
    if snapshot["planning_month"] not in catalog.months:
        return False
    return any(
        fact.project_code == snapshot["project_code"]
        and fact.project_label == snapshot["project_label"]
        and fact.queue == snapshot["queue"]
        and fact.title == snapshot["facility"]
        and fact.discipline == snapshot["discipline"]
        for fact in catalog.facts
    )
