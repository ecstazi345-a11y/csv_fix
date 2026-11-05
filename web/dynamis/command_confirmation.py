"""Session record of one human confirmation. Not a mission and not a run."""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping, MutableMapping, Optional

from agents.human_surface.command_confirmation import (
    CONFIRMATION_CONFIRMED,
    CONFIRMED_BY_HUMAN_SURFACE,
    ConfirmationRejected,
    HumanConfirmation,
    confirm_typed_draft,
    same_scope,
    scope_snapshot,
)
from agents.human_surface.command_interpretation import (
    STATE_NEEDS_CONFIRMATION,
    interpret_command,
)
from agents.human_surface.command_interpreter_provider import (
    ExtractionRejected,
    resolve_extraction,
    validate_extraction,
)
from agents.human_surface.work_context import WorkContextCatalog, load_work_context_catalog

from .command_interpretation import CLARIFICATION_SESSION_KEY, INTERPRETATION_SESSION_KEY
from .human_command import HumanCommand, load_human_command

CONFIRMATION_SESSION_KEY = "dynamis_command_confirmation"
CONFIRMATION_LABEL = "Поручение подтверждено"
CONFIRMATION_REJECTED_NOTICE = (
    "Поручение не подтверждено. Черновик не готов к подтверждению."
)


class ConfirmationReceipt:
    def __init__(self, accepted: bool, notice: str, confirmation: Optional[HumanConfirmation] = None) -> None:
        self.accepted = accepted
        self.notice = notice
        self.confirmation = confirmation


def accept_command_confirmation(
    session: MutableMapping[str, object],
    catalog: Optional[WorkContextCatalog] = None,
) -> ConfirmationReceipt:
    """Confirm the current draft only when a fresh reading agrees with it."""
    command = load_human_command(session)
    stored = session.get(INTERPRETATION_SESSION_KEY)
    if command is None or not isinstance(stored, Mapping):
        return _rejected()
    if stored.get("command_id") != command.command_id:
        return _rejected()
    if catalog is None:
        catalog = load_work_context_catalog()
    fresh = interpret_command(
        command_id=command.command_id,
        raw_text=command.raw_text,
        catalog=catalog,
    )
    if not _stored_agrees(stored, fresh, command):
        fresh = _fresh_from_extraction(stored, command.command_id, catalog)
        if fresh is None or not _stored_agrees(stored, fresh, command):
            return _rejected()
    try:
        confirmation = confirm_typed_draft(
            fresh,
            catalog=catalog,
            source_text=command.raw_text,
            confirmed_by=CONFIRMED_BY_HUMAN_SURFACE,
        )
    except ConfirmationRejected:
        return _rejected()
    shown_id = str(stored.get("interpretation_id") or "").strip()
    if not shown_id:
        return _rejected()
    confirmation = HumanConfirmation(
        confirmation_id=confirmation.confirmation_id,
        command_id=confirmation.command_id,
        interpretation_id=shown_id,
        target_agent=confirmation.target_agent,
        resolved_scope=MappingProxyType(dict(confirmation.resolved_scope)),
        confirmed_by=confirmation.confirmed_by,
        confirmed_at=confirmation.confirmed_at,
        confirmation_state=CONFIRMATION_CONFIRMED,
        source_text=command.raw_text,
    )
    session[CONFIRMATION_SESSION_KEY] = confirmation.as_dict()
    session.pop(CLARIFICATION_SESSION_KEY, None)
    _touch(session)
    return ConfirmationReceipt(accepted=True, notice="", confirmation=confirmation)


def load_valid_confirmation(session: Mapping[str, object]) -> Optional[HumanConfirmation]:
    """Return the confirmation only while its command, interpretation, and scope still match."""
    raw = session.get(CONFIRMATION_SESSION_KEY)
    command = load_human_command(session)
    stored = session.get(INTERPRETATION_SESSION_KEY)
    if not isinstance(raw, Mapping) or command is None or not isinstance(stored, Mapping):
        return None
    if raw.get("confirmation_state") != CONFIRMATION_CONFIRMED:
        return None
    if raw.get("confirmed_by") != CONFIRMED_BY_HUMAN_SURFACE:
        return None
    if raw.get("command_id") != command.command_id or raw.get("source_text") != command.raw_text:
        return None
    if raw.get("interpretation_id") != stored.get("interpretation_id"):
        return None
    if stored.get("processing_state") != STATE_NEEDS_CONFIRMATION:
        return None
    if not same_scope(raw.get("resolved_scope"), stored.get("resolved_scope")):
        return None
    if stored.get("target_agent") != raw.get("target_agent"):
        return None
    try:
        snapshot = scope_snapshot(raw.get("resolved_scope"))
    except ConfirmationRejected:
        return None
    confirmation_id = str(raw.get("confirmation_id") or "").strip()
    confirmed_at = str(raw.get("confirmed_at") or "").strip()
    if not confirmation_id or not confirmed_at:
        return None
    return HumanConfirmation(
        confirmation_id=confirmation_id,
        command_id=command.command_id,
        interpretation_id=str(stored.get("interpretation_id") or ""),
        target_agent=str(raw.get("target_agent") or ""),
        resolved_scope=MappingProxyType(snapshot),
        confirmed_by=CONFIRMED_BY_HUMAN_SURFACE,
        confirmed_at=confirmed_at,
        confirmation_state=CONFIRMATION_CONFIRMED,
        source_text=command.raw_text,
    )


def command_confirmation_template_context(session: Mapping[str, object]) -> dict[str, object]:
    confirmation = load_valid_confirmation(session)
    if confirmation is None:
        return {
            "confirmation_received": False,
            "confirmation_state": "",
            "confirmation_label": "",
            "confirmation_id": "",
        }
    return {
        "confirmation_received": True,
        "confirmation_state": confirmation.confirmation_state,
        "confirmation_label": CONFIRMATION_LABEL,
        "confirmation_id": confirmation.confirmation_id,
    }


def _stored_agrees(stored: Mapping[str, object], fresh: object, command: HumanCommand) -> bool:
    from agents.human_surface.command_interpretation import CommandInterpretation

    if not isinstance(fresh, CommandInterpretation):
        return False
    if stored.get("processing_state") != fresh.processing_state:
        return False
    if stored.get("command_id") != command.command_id or fresh.command_id != command.command_id:
        return False
    if stored.get("target_agent") != fresh.target_agent:
        return False
    if stored.get("intent") != fresh.intent:
        return False
    if _texts(stored.get("unresolved_fields")) != fresh.unresolved_fields:
        return False
    if _texts(stored.get("ambiguities")) != fresh.ambiguities:
        return False
    return same_scope(stored.get("resolved_scope"), fresh.resolved_scope)


def _fresh_from_extraction(stored: Mapping[str, object], command_id: str, catalog: WorkContextCatalog):
    """Replay stored hints through the resolver. This does not call a provider."""
    try:
        extraction = validate_extraction(stored.get("validated_extraction"))
    except ExtractionRejected:
        return None
    return resolve_extraction(extraction, catalog, command_id=command_id)


def _texts(value: object) -> Optional[tuple[str, ...]]:
    if not isinstance(value, (list, tuple)):
        return None
    return tuple(str(item) for item in value)


def _rejected() -> ConfirmationReceipt:
    return ConfirmationReceipt(accepted=False, notice=CONFIRMATION_REJECTED_NOTICE)


def _touch(session: MutableMapping[str, object]) -> None:
    if getattr(session, "modified", None) is not None:
        session.modified = True
