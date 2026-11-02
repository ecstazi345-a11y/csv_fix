"""Session draft of a command interpretation. Not a mission and not a run."""
from __future__ import annotations

from typing import Mapping, MutableMapping, Optional

from agents.human_surface.command_interpretation import interpret_command
from agents.human_surface.work_context import WorkContextCatalog, load_work_context_catalog

from .human_command import HUMAN_COMMAND_SESSION_KEY, HumanCommand

INTERPRETATION_SESSION_KEY = "dynamis_command_interpretation"

_FIELD_RU = {
    "project": "проект",
    "period": "период",
    "queue": "очередь",
    "title": "титул",
    "discipline": "дисциплина",
    "scope": "состав миссии",
    "intent": "поручение",
}


def remember_command_interpretation(
    session: MutableMapping[str, object],
    command: HumanCommand,
    catalog: Optional[WorkContextCatalog] = None,
) -> None:
    if catalog is None:
        catalog = load_work_context_catalog()
    result = interpret_command(
        command_id=command.command_id,
        raw_text=command.raw_text,
        catalog=catalog,
    )
    session[INTERPRETATION_SESSION_KEY] = result.as_dict()
    if getattr(session, "modified", None) is not None:
        session.modified = True


def command_interpretation_template_context(session: Mapping[str, object]) -> dict[str, object]:
    stored = session.get(INTERPRETATION_SESSION_KEY)
    command = session.get(HUMAN_COMMAND_SESSION_KEY)
    if not isinstance(stored, Mapping):
        return _empty_context()
    if isinstance(command, Mapping) and stored.get("command_id") != command.get("command_id"):
        return _empty_context()
    preview = stored.get("preview") or ()
    return {
        "interpretation_headline": str(stored.get("headline") or ""),
        "interpretation_status": str(stored.get("status_label") or ""),
        "interpretation_facts": tuple(tuple(item) for item in preview),
        "interpretation_state": str(stored.get("processing_state") or ""),
        "interpretation_can_confirm": stored.get("processing_state") == "NEEDS_CONFIRMATION",
        "interpretation_note": _note(stored),
        "interpretation_law": "Constructor ещё не запущен. Черновик не заменяет миссию текущего запуска.",
    }


def _empty_context() -> dict[str, object]:
    return {
        "interpretation_headline": "",
        "interpretation_status": "",
        "interpretation_facts": (),
        "interpretation_state": "",
        "interpretation_can_confirm": False,
        "interpretation_note": "",
        "interpretation_law": "",
    }


def _note(stored: Mapping[str, object]) -> str:
    parts: list[str] = []
    if stored.get("processing_state") == "REJECTED":
        parts.append("Это не профессиональное поручение. Черновик миссии не создан.")
    unresolved = stored.get("unresolved_fields") or ()
    if isinstance(unresolved, (list, tuple)) and unresolved:
        labels = [_FIELD_RU.get(str(item), str(item)) for item in unresolved]
        parts.append("Не определено: " + ", ".join(labels) + ".")
    ambiguities = stored.get("ambiguities") or ()
    if isinstance(ambiguities, (list, tuple)):
        parts.extend(str(item) for item in ambiguities if str(item).strip())
    return " ".join(parts)
