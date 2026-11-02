"""Agent-neutral Human Command input for the Django Control Room.

This stores one received text draft in the Django session. It does not interpret
the text, launch an agent, or write runtime or product databases.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, MutableMapping, Optional
from uuid import uuid4

HUMAN_COMMAND_SOURCE = "django_control_room"
HUMAN_COMMAND_INPUT_MODE = "text"
HUMAN_COMMAND_RECEIVED = "RECEIVED"
HUMAN_COMMAND_SESSION_KEY = "dynamis_human_command"
MAX_HUMAN_COMMAND_LENGTH = 1000

EMPTY_COMMAND_NOTICE = "Пустая команда не отправлена."
LONG_COMMAND_NOTICE = (
    f"Команда длиннее {MAX_HUMAN_COMMAND_LENGTH} символов и не отправлена."
)
COMMAND_RECEIVED_STATUS = "Команда получена"


@dataclass(frozen=True)
class HumanCommand:
    command_id: str
    raw_text: str
    source: str
    input_mode: str
    created_at: str
    processing_state: str

    def as_dict(self) -> dict[str, str]:
        return {
            "command_id": self.command_id,
            "raw_text": self.raw_text,
            "source": self.source,
            "input_mode": self.input_mode,
            "created_at": self.created_at,
            "processing_state": self.processing_state,
        }


@dataclass(frozen=True)
class HumanCommandReceipt:
    accepted: bool
    notice: str
    command: Optional[HumanCommand] = None


def validate_human_command_text(raw_text: object) -> tuple[str, str]:
    """Return the accepted text, or an empty text and a fail-safe notice."""
    text = raw_text if isinstance(raw_text, str) else ""
    text = text.strip()
    if not text:
        return "", EMPTY_COMMAND_NOTICE
    if len(text) > MAX_HUMAN_COMMAND_LENGTH:
        return "", LONG_COMMAND_NOTICE
    return text, ""


def accept_human_command(session: MutableMapping[str, object], raw_text: object) -> HumanCommandReceipt:
    text, notice = validate_human_command_text(raw_text)
    if notice:
        return HumanCommandReceipt(accepted=False, notice=notice)
    command = HumanCommand(
        command_id=str(uuid4()),
        raw_text=text,
        source=HUMAN_COMMAND_SOURCE,
        input_mode=HUMAN_COMMAND_INPUT_MODE,
        created_at=datetime.now(timezone.utc).isoformat(),
        processing_state=HUMAN_COMMAND_RECEIVED,
    )
    session[HUMAN_COMMAND_SESSION_KEY] = command.as_dict()
    modified = getattr(session, "modified", None)
    if modified is not None:
        session.modified = True
    return HumanCommandReceipt(accepted=True, notice="", command=command)


def load_human_command(session: Mapping[str, object]) -> Optional[HumanCommand]:
    raw = session.get(HUMAN_COMMAND_SESSION_KEY)
    if not isinstance(raw, Mapping):
        return None
    text, notice = validate_human_command_text(raw.get("raw_text"))
    if notice or raw.get("processing_state") != HUMAN_COMMAND_RECEIVED:
        return None
    if raw.get("source") != HUMAN_COMMAND_SOURCE or raw.get("input_mode") != HUMAN_COMMAND_INPUT_MODE:
        return None
    command_id = str(raw.get("command_id") or "").strip()
    created_at = str(raw.get("created_at") or "").strip()
    if not command_id or not created_at:
        return None
    return HumanCommand(
        command_id=command_id,
        raw_text=text,
        source=HUMAN_COMMAND_SOURCE,
        input_mode=HUMAN_COMMAND_INPUT_MODE,
        created_at=created_at,
        processing_state=HUMAN_COMMAND_RECEIVED,
    )


def human_command_template_context(session: Mapping[str, object]) -> dict[str, object]:
    command = load_human_command(session)
    if command is None:
        return {
            "command_received": False,
            "command_text": "",
            "command_status": "",
            "command_id": "",
            "command_processing_state": "",
        }
    return {
        "command_received": True,
        "command_text": command.raw_text,
        "command_status": COMMAND_RECEIVED_STATUS,
        "command_id": command.command_id,
        "command_processing_state": command.processing_state,
    }
