"""Typed pending clarification draft and safe fragment continuation.

An active NEEDS_CLARIFICATION draft may absorb a short human fragment that fills
only unresolved scope fields. Empty intent is allowed. Resolved fields are never
silently overwritten. Confirmed drafts are not mutable here.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Optional

from agents.human_surface.command_interpretation import (
    INTENT_FORM_CANDIDATE_PACKAGE,
    INTENT_FORM_MONTHLY_COMMITMENT,
    STATE_NEEDS_CLARIFICATION,
    CommandInterpretation,
)
from agents.human_surface.command_interpreter_provider import (
    EXTRACTION_FIELDS,
    CommandExtraction,
    InterpreterUsage,
    resolve_extraction,
    validate_extraction,
)
from agents.human_surface.work_context import WorkContextCatalog

PENDING_CLARIFICATION = "PENDING_CLARIFICATION"
SOURCE_HUMAN_CLARIFICATION = "HUMAN_CLARIFICATION"

_HINT_BY_FIELD = {
    "project": "project_hint",
    "period": "period_hint",
    "queue": "queue_hint",
    "title": "title_hint",
    "discipline": "discipline_hint",
}
_SCOPE_VALUE = {
    "project": lambda scope: str(scope.get("project_label") or scope.get("project_code") or ""),
    "period": lambda scope: str(scope.get("planning_month") or scope.get("month_key") or ""),
    "queue": lambda scope: str(scope.get("queue") or ""),
    "title": lambda scope: str(scope.get("facility") or ""),
    "discipline": lambda scope: str(scope.get("discipline") or ""),
}


class ClarificationRejected(ValueError):
    """A clarification fragment cannot be applied to the pending draft."""


@dataclass(frozen=True)
class PendingClarificationDraft:
    command_id: str
    interpretation_id: str
    intent: str
    source_text: str
    resolved_scope: dict[str, str]
    unresolved_fields: tuple[str, ...]
    ambiguities: tuple[str, ...]
    extracted_hints: Optional[dict[str, str]]
    status: str = PENDING_CLARIFICATION

    def as_dict(self) -> dict[str, object]:
        return {
            "command_id": self.command_id,
            "interpretation_id": self.interpretation_id,
            "intent": self.intent,
            "source_text": self.source_text,
            "resolved_scope": dict(self.resolved_scope),
            "unresolved_fields": list(self.unresolved_fields),
            "ambiguities": list(self.ambiguities),
            "extracted_hints": dict(self.extracted_hints) if self.extracted_hints else None,
            "status": PENDING_CLARIFICATION,
            "mission_created": False,
            "constructor_run_created": False,
        }


@dataclass(frozen=True)
class ClarificationContinuationResult:
    handled: bool
    interpretation: Optional[CommandInterpretation] = None
    extraction: Optional[CommandExtraction] = None
    usage: Optional[InterpreterUsage] = None
    channel: str = ""
    applied: bool = False
    conflict: bool = False
    message: str = ""
    fragment_text: str = ""


def pending_from_interpretation(
    interpretation: CommandInterpretation,
    *,
    source_text: str,
    extraction: Optional[CommandExtraction] = None,
) -> Optional[PendingClarificationDraft]:
    """Build a pending draft only while the interpretation still needs clarification."""
    if interpretation.processing_state != STATE_NEEDS_CLARIFICATION:
        return None
    text = str(source_text or "").strip()
    if not text or not interpretation.command_id or not interpretation.interpretation_id:
        return None
    hints = extraction.as_dict() if extraction is not None else None
    return PendingClarificationDraft(
        command_id=interpretation.command_id,
        interpretation_id=interpretation.interpretation_id,
        intent=interpretation.intent,
        source_text=text,
        resolved_scope=dict(interpretation.resolved_scope),
        unresolved_fields=tuple(interpretation.unresolved_fields),
        ambiguities=tuple(interpretation.ambiguities),
        extracted_hints=hints,
    )


def pending_from_mapping(raw: object) -> Optional[PendingClarificationDraft]:
    if not isinstance(raw, Mapping):
        return None
    if str(raw.get("status") or "") != PENDING_CLARIFICATION:
        return None
    command_id = str(raw.get("command_id") or "").strip()
    interpretation_id = str(raw.get("interpretation_id") or "").strip()
    source_text = str(raw.get("source_text") or "").strip()
    if not command_id or not interpretation_id or not source_text:
        return None
    scope = raw.get("resolved_scope")
    unresolved = raw.get("unresolved_fields") or ()
    ambiguities = raw.get("ambiguities") or ()
    hints = raw.get("extracted_hints")
    return PendingClarificationDraft(
        command_id=command_id,
        interpretation_id=interpretation_id,
        intent=str(raw.get("intent") or ""),
        source_text=source_text,
        resolved_scope=dict(scope) if isinstance(scope, Mapping) else {},
        unresolved_fields=tuple(str(item) for item in unresolved),
        ambiguities=tuple(str(item) for item in ambiguities),
        extracted_hints=dict(hints) if isinstance(hints, Mapping) else None,
    )


def continue_clarification(
    pending: PendingClarificationDraft,
    fragment_text: str,
    catalog: WorkContextCatalog,
    *,
    fragment_extraction: Optional[CommandExtraction] = None,
    usage: Optional[InterpreterUsage] = None,
    channel: str = "",
    confirmation_is_active: bool = False,
) -> ClarificationContinuationResult:
    """Merge one human fragment into the pending draft when safe."""
    piece = str(fragment_text or "").strip()
    if not piece:
        raise ClarificationRejected("clarification fragment is empty")
    if confirmation_is_active:
        raise ClarificationRejected("confirmed draft cannot be changed silently")

    fragment = fragment_extraction or local_fragment_extraction(piece)
    if fragment is None:
        return ClarificationContinuationResult(handled=False, fragment_text=piece)

    # A fresh multi-field professional command is not a clarification fragment.
    if fragment.intent in {
        INTENT_FORM_CANDIDATE_PACKAGE,
        INTENT_FORM_MONTHLY_COMMITMENT,
    } and _looks_like_new_assignment(fragment):
        return ClarificationContinuationResult(handled=False, fragment_text=piece)

    base = hints_from_pending(pending)
    merged_hints, filled, conflicts = merge_unresolved_hints(
        base_hints=base,
        fragment=fragment,
        unresolved_fields=pending.unresolved_fields,
        resolved_scope=pending.resolved_scope,
    )
    if conflicts:
        note = (
            "Уточнение не применено: нельзя молча заменить уже определённое поле ("
            + ", ".join(conflicts)
            + ")."
        )
        base_extraction = validate_extraction(base)
        blocked = resolve_extraction(
            base_extraction,
            catalog,
            command_id=pending.command_id,
        )
        blocked = replace(
            blocked,
            ambiguities=tuple(dict.fromkeys([*blocked.ambiguities, note])),
            unresolved_fields=tuple(dict.fromkeys([*blocked.unresolved_fields, *pending.unresolved_fields])),
            processing_state=STATE_NEEDS_CLARIFICATION,
            headline="Нужно уточнение",
            status_label="Нужно уточнение",
        )
        return ClarificationContinuationResult(
            handled=True,
            interpretation=blocked,
            extraction=base_extraction,
            usage=usage,
            channel=channel or "clarification",
            applied=False,
            conflict=True,
            message=note,
            fragment_text=piece,
        )
    if not filled:
        return ClarificationContinuationResult(handled=False, fragment_text=piece)

    merged_hints["intent"] = pending.intent or merged_hints.get("intent") or ""
    if pending.intent and not merged_hints.get("target_agent_hint"):
        merged_hints["target_agent_hint"] = "constructor"
    extraction = validate_extraction(merged_hints)
    interpretation = resolve_extraction(
        extraction,
        catalog,
        command_id=pending.command_id,
    )
    interpretation = _with_clarification_provenance(
        interpretation,
        pending=pending,
        filled_fields=filled,
    )
    return ClarificationContinuationResult(
        handled=True,
        interpretation=interpretation,
        extraction=extraction,
        usage=usage,
        channel=channel or "clarification",
        applied=True,
        conflict=False,
        message="Уточнение применено к текущему поручению",
        fragment_text=piece,
    )


def apply_clarification_fragment(
    pending: PendingClarificationDraft,
    fragment: str,
    catalog: WorkContextCatalog,
    *,
    confirmation_is_active: bool = False,
    fragment_extraction: Optional[CommandExtraction] = None,
) -> CommandInterpretation:
    """Compatibility wrapper used by unit tests."""
    result = continue_clarification(
        pending,
        fragment,
        catalog,
        fragment_extraction=fragment_extraction,
        confirmation_is_active=confirmation_is_active,
    )
    if confirmation_is_active:
        raise ClarificationRejected("confirmed draft cannot be changed silently")
    if not result.handled or result.interpretation is None:
        raise ClarificationRejected("clarification fragment was not applied")
    if result.conflict:
        raise ClarificationRejected(result.message or "clarification conflict")
    return result.interpretation


def hints_from_pending(pending: PendingClarificationDraft) -> dict[str, str]:
    if pending.extracted_hints is not None:
        base = {field: str(pending.extracted_hints.get(field) or "") for field in EXTRACTION_FIELDS}
    else:
        scope = pending.resolved_scope
        base = {field: "" for field in EXTRACTION_FIELDS}
        base["project_hint"] = str(scope.get("project_label") or "")
        base["period_hint"] = str(scope.get("planning_month") or scope.get("month_key") or "")
        base["queue_hint"] = str(scope.get("queue") or "")
        base["title_hint"] = str(scope.get("facility") or "")
        base["discipline_hint"] = str(scope.get("discipline") or "")
    base["intent"] = pending.intent or base.get("intent") or ""
    if base["intent"] and not base.get("target_agent_hint"):
        base["target_agent_hint"] = "constructor"
    return base


def merge_unresolved_hints(
    *,
    base_hints: Mapping[str, str],
    fragment: CommandExtraction,
    unresolved_fields: tuple[str, ...],
    resolved_scope: Mapping[str, str],
) -> tuple[dict[str, str], tuple[str, ...], tuple[str, ...]]:
    """Fill unresolved hints only. Conflicting resolved values are reported, not written."""
    merged = {field: str(base_hints.get(field) or "") for field in EXTRACTION_FIELDS}
    frag = fragment.as_dict()
    unresolved = set(unresolved_fields)
    filled: list[str] = []
    conflicts: list[str] = []
    for field, hint_key in _HINT_BY_FIELD.items():
        value = str(frag.get(hint_key) or "").strip()
        if not value:
            continue
        if field in unresolved:
            merged[hint_key] = value
            filled.append(field)
            continue
        current = _SCOPE_VALUE[field](resolved_scope).strip()
        if not current:
            # Not marked unresolved but blank — still allow fill.
            merged[hint_key] = value
            filled.append(field)
            continue
        if _same_scope_token(field, current, value):
            continue
        conflicts.append(field)
    return merged, tuple(dict.fromkeys(filled)), tuple(dict.fromkeys(conflicts))


def local_fragment_extraction(fragment: str) -> Optional[CommandExtraction]:
    """Deterministic short-fragment parse. Empty intent is intentional and valid."""
    text = str(fragment or "").strip()
    if not text:
        return None
    folded = text.casefold().replace("ё", "е")
    values = {field: "" for field in EXTRACTION_FIELDS}
    if "дисциплин" in folded:
        tail = text[folded.index("дисциплин") + len("дисциплин") :].strip(" :,-")
        if tail:
            values["discipline_hint"] = tail
    else:
        for stem, label in (
            ("автоматизац", "автоматизация"),
            ("автоматик", "автоматика"),
            ("вентиляц", "вентиляция"),
            ("электри", "электрика"),
        ):
            if stem in folded:
                values["discipline_hint"] = label
                break
    if "очеред" in folded or folded in {
        "1",
        "2",
        "первая",
        "первой",
        "первую",
        "вторая",
        "второй",
        "вторую",
    }:
        if any(token in folded for token in ("1", "перв")):
            values["queue_hint"] = "1"
        elif any(token in folded for token in ("2", "втор")):
            values["queue_hint"] = "2"
    if "титул" in folded:
        import re

        found = re.search(r"(\d{4,6}-\d{2,3})", text)
        if found:
            values["title_hint"] = found.group(1)
    if not any(values[key] for key in _HINT_BY_FIELD.values()):
        return None
    return validate_extraction(values)


def _with_clarification_provenance(
    interpretation: CommandInterpretation,
    *,
    pending: PendingClarificationDraft,
    filled_fields: tuple[str, ...],
) -> CommandInterpretation:
    resolved = dict(interpretation.resolved_scope)
    for key, value in pending.resolved_scope.items():
        if key.endswith("_source") and key not in resolved and value:
            resolved[key] = value
    for field in filled_fields:
        if field == "discipline" and resolved.get("discipline"):
            resolved["discipline_source"] = SOURCE_HUMAN_CLARIFICATION
        elif field == "queue" and resolved.get("queue"):
            resolved["queue_source"] = SOURCE_HUMAN_CLARIFICATION
        elif field == "title" and resolved.get("facility"):
            resolved["title_source"] = SOURCE_HUMAN_CLARIFICATION
        elif field == "project" and resolved.get("project_code"):
            resolved["project_source"] = SOURCE_HUMAN_CLARIFICATION
        elif field == "period" and resolved.get("month_key"):
            resolved["period_source"] = SOURCE_HUMAN_CLARIFICATION
    return replace(interpretation, resolved_scope=resolved)


def _same_scope_token(field: str, current: str, incoming: str) -> bool:
    left = current.casefold().replace("ё", "е").strip()
    right = incoming.casefold().replace("ё", "е").strip()
    if left == right:
        return True
    if field == "discipline":
        return left.startswith(right) or right.startswith(left)
    if field == "period":
        return left.replace("-", " ") == right.replace("-", " ")
    return False


def _looks_like_new_assignment(fragment: CommandExtraction) -> bool:
    filled = sum(
        1
        for key in (
            "project_hint",
            "period_hint",
            "queue_hint",
            "title_hint",
            "discipline_hint",
        )
        if str(getattr(fragment, key) or "").strip()
    )
    return filled >= 3
