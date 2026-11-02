"""Provider-neutral extraction for one human command.

A provider may only return hints. Canonical project, period, queue, title, and
discipline stay with the existing command resolver. This module does not call a
model, a database, or an agent runtime.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Optional, Protocol

from agents.human_surface.command_interpretation import (
    STATE_NEEDS_CONFIRMATION,
    CommandInterpretation,
    interpret_command,
)
from agents.human_surface.work_context import WorkContextCatalog

EXTRACTION_FIELDS = (
    "intent",
    "target_agent_hint",
    "project_hint",
    "period_hint",
    "queue_hint",
    "title_hint",
    "discipline_hint",
    "system_hint",
    "iwp_hint",
)
_ALLOWED_INTENTS = frozenset({"", "FORM_CANDIDATE_PACKAGE"})
_ALLOWED_AGENT_HINTS = frozenset({"", "constructor"})
_MAX_HINT = 80
_CANONICAL_CODE = re.compile(r"prj_|mission-|run-", re.IGNORECASE)
_UNSAFE = ("select ", "insert ", "update ", "delete ", "drop ", ";", "--", "```")


class ExtractionRejected(ValueError):
    """The model payload is not a valid hint structure."""


@dataclass(frozen=True)
class CommandExtraction:
    intent: str
    target_agent_hint: str
    project_hint: str
    period_hint: str
    queue_hint: str
    title_hint: str
    discipline_hint: str
    system_hint: str = ""
    iwp_hint: str = ""

    def as_dict(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in EXTRACTION_FIELDS}


@dataclass(frozen=True)
class InterpreterUsage:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int
    success: bool
    provider_call_count: int = 1
    retry_count: int = 0
    request_id: str = ""
    http_status: Optional[int] = None
    error_category: str = ""
    error_code: str = ""
    schema_validation_pass: Optional[bool] = None


@dataclass(frozen=True)
class ProviderFailure:
    """Sanitized provider failure. It never carries credentials or the raw request."""

    category: str
    error_type: str
    error_code: str
    error_param: str
    http_status: Optional[int]
    request_id: str
    safe_error_message: str


@dataclass(frozen=True)
class ProviderExtractionResult:
    extraction: Optional[CommandExtraction]
    usage: InterpreterUsage
    failure: Optional[ProviderFailure] = None


class CommandInterpreterProvider(Protocol):
    """One structured extraction. No tools and no canonical identifiers."""

    def extract(self, raw_text: str) -> ProviderExtractionResult:
        """Return hints for the raw command, or a failed usage record."""


def validate_extraction(payload: object) -> CommandExtraction:
    """Accept only the closed hint schema. Unknown or unsafe fields fail closed."""
    if not isinstance(payload, Mapping):
        raise ExtractionRejected("extraction must be an object")
    if set(payload) != set(EXTRACTION_FIELDS):
        raise ExtractionRejected("extraction fields do not match the schema")
    values: dict[str, str] = {}
    for field in EXTRACTION_FIELDS:
        value = payload[field]
        if not isinstance(value, str):
            raise ExtractionRejected(f"{field} must be text")
        text = value.strip()
        if len(text) > _MAX_HINT or any(char in text for char in "\n\r\t"):
            raise ExtractionRejected(f"{field} is not a short hint")
        folded = text.casefold()
        if _CANONICAL_CODE.search(folded) or any(token in folded for token in _UNSAFE):
            raise ExtractionRejected(f"{field} is not a hint")
        values[field] = text
    if values["intent"] not in _ALLOWED_INTENTS:
        raise ExtractionRejected("intent is outside the allowed vocabulary")
    if values["target_agent_hint"] not in _ALLOWED_AGENT_HINTS:
        raise ExtractionRejected("target agent hint is outside the allowed vocabulary")
    return CommandExtraction(**values)


def extraction_command_text(extraction: CommandExtraction) -> str:
    """Speak the hints in the form the existing resolver already understands."""
    if extraction.intent != "FORM_CANDIDATE_PACKAGE":
        return ""
    parts = ["Сформируй кандидатный состав"]
    if extraction.period_hint:
        parts.append("на " + extraction.period_hint)
    if extraction.project_hint:
        parts.append("по " + extraction.project_hint)
    queue = _queue_hint(extraction.queue_hint)
    if queue:
        parts.append(queue + " очередь")
    if extraction.title_hint:
        parts.append("титул " + extraction.title_hint)
    if extraction.discipline_hint:
        parts.append(extraction.discipline_hint)
    return " ".join(parts)


def resolve_extraction(
    extraction: CommandExtraction,
    catalog: WorkContextCatalog,
    *,
    command_id: str,
) -> CommandInterpretation:
    """Prove the hints through the existing resolver. Hints are not canonical ids."""
    return interpret_command(
        command_id=command_id,
        raw_text=extraction_command_text(extraction),
        catalog=catalog,
    )


def resolved_for_confirmation(interpretation: CommandInterpretation) -> bool:
    return interpretation.processing_state == STATE_NEEDS_CONFIRMATION


def _queue_hint(value: str) -> str:
    folded = value.casefold().replace("ё", "е").strip()
    if folded in {"1", "1-я", "1я", "первая", "первой", "первую"}:
        return "1"
    if folded in {"2", "2-я", "2я", "вторая", "второй", "вторую"}:
        return "2"
    return value.strip()
