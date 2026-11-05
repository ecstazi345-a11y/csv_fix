"""Django wiring for the Human Command interpreter provider.

Views must not hardcode a vendor. Selection stays in the shared agent layer.
"""
from __future__ import annotations

from typing import Optional

from agents.human_surface.command_interpreter_provider import CommandInterpreterProvider
from agents.human_surface.command_understanding import select_command_provider


def resolve_command_provider() -> Optional[CommandInterpreterProvider]:
    """Prefer Yandex when configured; otherwise OpenAI. No cross-provider fallback."""
    selected = select_command_provider("yandex")
    if selected is not None:
        return selected
    return select_command_provider("openai")
