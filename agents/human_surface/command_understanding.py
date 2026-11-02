"""Choose a deterministic reading or one provider extraction, then resolve it.

A clear command never calls a provider. A provider failure keeps the
deterministic reading and does not start an agent.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agents.human_surface.command_interpretation import (
    STATE_NEEDS_CLARIFICATION,
    CommandInterpretation,
    interpret_command,
)
from agents.human_surface.command_interpreter_provider import (
    CommandExtraction,
    CommandInterpreterProvider,
    InterpreterUsage,
    resolve_extraction,
    resolved_for_confirmation,
)
from agents.human_surface.work_context import WorkContextCatalog

CHANNEL_DETERMINISTIC = "deterministic"
CHANNEL_PROVIDER = "openai"
CHANNEL_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class UnderstoodCommand:
    interpretation: CommandInterpretation
    channel: str
    extraction: Optional[CommandExtraction]
    usage: Optional[InterpreterUsage]


def understand_command(
    *,
    command_id: str,
    raw_text: str,
    catalog: WorkContextCatalog,
    provider: Optional[CommandInterpreterProvider] = None,
) -> UnderstoodCommand:
    """Resolve one command. The provider is used only when the fast path is incomplete."""
    direct = interpret_command(command_id=command_id, raw_text=raw_text, catalog=catalog)
    if direct.processing_state != STATE_NEEDS_CLARIFICATION:
        return UnderstoodCommand(direct, CHANNEL_DETERMINISTIC, None, None)
    if provider is None and (catalog.error or not catalog.facts):
        return UnderstoodCommand(direct, CHANNEL_UNAVAILABLE, None, None)
    selected = provider if provider is not None else _default_provider()
    if selected is None:
        return UnderstoodCommand(direct, CHANNEL_UNAVAILABLE, None, None)
    try:
        result = selected.extract(raw_text)
    except Exception:
        return UnderstoodCommand(direct, CHANNEL_UNAVAILABLE, None, None)
    if result.extraction is None:
        return UnderstoodCommand(direct, CHANNEL_UNAVAILABLE, None, result.usage)
    resolved = resolve_extraction(result.extraction, catalog, command_id=command_id)
    channel = result.usage.provider or CHANNEL_PROVIDER
    if not resolved_for_confirmation(resolved):
        return UnderstoodCommand(resolved, channel, None, result.usage)
    return UnderstoodCommand(resolved, channel, result.extraction, result.usage)


def select_command_provider(name: str) -> Optional[CommandInterpreterProvider]:
    """Return one named provider. An unknown name or a missing provider does not fall back."""
    normalized = str(name or "").strip().lower()
    if normalized == "yandex":
        from agents.human_surface.yandex_command_interpreter import build_yandex_provider

        return build_yandex_provider()
    if normalized == "openai":
        from agents.human_surface.openai_command_interpreter import build_openai_provider

        return build_openai_provider()
    return None


def _default_provider() -> Optional[CommandInterpreterProvider]:
    try:
        from agents.human_surface.openai_command_interpreter import build_openai_provider
    except Exception:
        return None
    return build_openai_provider()
