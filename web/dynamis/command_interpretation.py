"""Session draft of a command interpretation. Not a mission and not a run."""
from __future__ import annotations

from typing import Mapping, MutableMapping, Optional

from agents.human_surface.command_clarification import (
    ClarificationRejected,
    continue_clarification,
    pending_from_interpretation,
    pending_from_mapping,
)
from agents.human_surface.command_understanding import understand_command
from agents.human_surface.work_context import WorkContextCatalog, load_work_context_catalog

from .command_provider import resolve_command_provider
from .human_command import HUMAN_COMMAND_SESSION_KEY, HumanCommand, HUMAN_COMMAND_SOURCE, HUMAN_COMMAND_INPUT_MODE, HUMAN_COMMAND_RECEIVED

INTERPRETATION_SESSION_KEY = "dynamis_command_interpretation"
CLARIFICATION_SESSION_KEY = "dynamis_pending_clarification"
CLARIFICATION_APPLIED_STATUS = "Уточнение применено к текущему поручению"
UNDEFINED_RU = "Не определено / Требуется уточнение"
_MONTHLY_COMMITMENT_NOTE = (
    "Цель понята: месячное обязательство. Scope полностью определён. "
    "Доступный первый этап: Constructor / формирование кандидатного состава. "
    "Месячное обязательство ещё не сформировано. "
    "Ожидается подтверждение начала первого этапа."
)
_MONTHLY_COMMITMENT_INCOMPLETE_NOTE = (
    "Цель: месячное обязательство. Доступный первый этап: Constructor / "
    "формирование кандидатного состава. Месячное обязательство ещё не сформировано."
)

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
    provider = resolve_command_provider()
    if _try_remember_clarification(session, command, catalog, provider):
        return
    understood = understand_command(
        command_id=command.command_id,
        raw_text=command.raw_text,
        catalog=catalog,
        provider=provider,
    )
    _store_interpretation_session(
        session,
        interpretation=understood.interpretation,
        channel=understood.channel,
        extraction=understood.extraction,
        usage=understood.usage,
        provider_error=understood.provider_error,
        source_text=command.raw_text,
        clarification_applied=False,
        clarification_fragment="",
        clarification_message="",
    )


def _try_remember_clarification(
    session: MutableMapping[str, object],
    command: HumanCommand,
    catalog: WorkContextCatalog,
    provider,
) -> bool:
    pending = pending_from_mapping(session.get(CLARIFICATION_SESSION_KEY))
    if pending is None:
        return False
    from .command_confirmation import load_valid_confirmation

    confirmation_active = load_valid_confirmation(session) is not None
    if confirmation_active:
        return False

    fragment_extraction = None
    usage = None
    channel = "clarification"
    provider_error = ""
    if provider is not None:
        try:
            result = provider.extract(command.raw_text)
        except Exception:
            result = None
        if result is not None:
            usage = result.usage
            channel = str(getattr(usage, "provider", "") or "") or channel
            if result.failure is not None:
                provider_error = str(result.failure.safe_error_message or "").strip()
            fragment_extraction = result.extraction

    try:
        continued = continue_clarification(
            pending,
            command.raw_text,
            catalog,
            fragment_extraction=fragment_extraction,
            usage=usage,
            channel=channel,
            confirmation_is_active=False,
        )
    except ClarificationRejected:
        return False
    if not continued.handled or continued.interpretation is None:
        return False

    # Keep the original command identity/text as authority for confirmation.
    session[HUMAN_COMMAND_SESSION_KEY] = {
        "command_id": pending.command_id,
        "raw_text": pending.source_text,
        "source": HUMAN_COMMAND_SOURCE,
        "input_mode": HUMAN_COMMAND_INPUT_MODE,
        "created_at": command.created_at,
        "processing_state": HUMAN_COMMAND_RECEIVED,
    }
    _store_interpretation_session(
        session,
        interpretation=continued.interpretation,
        channel=continued.channel or channel,
        extraction=continued.extraction,
        usage=continued.usage,
        provider_error=provider_error,
        source_text=pending.source_text,
        clarification_applied=continued.applied,
        clarification_fragment=continued.fragment_text,
        clarification_message=continued.message,
    )
    return True


def _store_interpretation_session(
    session: MutableMapping[str, object],
    *,
    interpretation,
    channel: str,
    extraction,
    usage,
    provider_error: str,
    source_text: str,
    clarification_applied: bool,
    clarification_fragment: str,
    clarification_message: str,
) -> None:
    payload = interpretation.as_dict()
    payload["interpretation_channel"] = channel
    if extraction is not None:
        payload["validated_extraction"] = extraction.as_dict()
    if usage is not None:
        payload["provider_usage"] = {
            "provider": usage.provider,
            "model": usage.model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "latency_ms": usage.latency_ms,
            "provider_call_count": usage.provider_call_count,
            "retry_count": usage.retry_count,
            "request_id": usage.request_id,
            "http_status": usage.http_status,
            "error_category": usage.error_category,
            "error_code": usage.error_code,
            "schema_validation_pass": usage.schema_validation_pass,
            "success": usage.success,
        }
    if provider_error:
        payload["provider_error"] = provider_error
    if clarification_applied:
        payload["clarification_applied"] = True
        payload["clarification_fragment"] = clarification_fragment
        payload["clarification_message"] = clarification_message or CLARIFICATION_APPLIED_STATUS
    elif clarification_message:
        payload["clarification_applied"] = False
        payload["clarification_fragment"] = clarification_fragment
        payload["clarification_message"] = clarification_message
    session[INTERPRETATION_SESSION_KEY] = payload
    pending = pending_from_interpretation(
        interpretation,
        source_text=source_text,
        extraction=extraction,
    )
    if pending is None:
        session.pop(CLARIFICATION_SESSION_KEY, None)
    else:
        session[CLARIFICATION_SESSION_KEY] = pending.as_dict()
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
    extraction = stored.get("validated_extraction")
    usage = stored.get("provider_usage")
    scope = stored.get("resolved_scope") if isinstance(stored.get("resolved_scope"), Mapping) else {}
    state = str(stored.get("processing_state") or "")
    channel = str(stored.get("interpretation_channel") or "")
    schema_pass = _schema_validation_label(stored, extraction, usage)
    resolution_pass = "YES" if state == "NEEDS_CONFIRMATION" else "NO"
    return {
        "interpretation_headline": str(stored.get("headline") or ""),
        "interpretation_status": str(stored.get("status_label") or ""),
        "interpretation_facts": tuple(tuple(item) for item in preview),
        "interpretation_state": state,
        "interpretation_can_confirm": state == "NEEDS_CONFIRMATION",
        "interpretation_note": _note(stored),
        "interpretation_law": _law(stored),
        "interpretation_channel": channel,
        "llm_view_visible": bool(extraction) or bool(usage) or bool(stored.get("provider_error")),
        "llm_provider": _usage_text(usage, "provider", channel if channel not in {"", "deterministic", "unavailable"} else ""),
        "llm_model": _usage_text(usage, "model"),
        "llm_intent": _extraction_text(extraction, "intent"),
        "llm_agent_hint": _extraction_text(extraction, "target_agent_hint"),
        "llm_project_hint": _extraction_text(extraction, "project_hint"),
        "llm_period_hint": _extraction_text(extraction, "period_hint"),
        "llm_queue_hint": _extraction_text(extraction, "queue_hint"),
        "llm_title_hint": _extraction_text(extraction, "title_hint"),
        "llm_discipline_hint": _extraction_text(extraction, "discipline_hint"),
        "llm_system_hint": _extraction_text(extraction, "system_hint"),
        "llm_iwp_hint": _extraction_text(extraction, "iwp_hint"),
        "canonical_agent": _canonical_text(stored.get("target_agent")),
        "canonical_project": _canonical_text(scope.get("project_code")),
        "canonical_period": _canonical_text(scope.get("month_key")),
        "canonical_queue": _canonical_text(scope.get("queue")),
        "canonical_queue_source": _canonical_text(scope.get("queue_source"))
        if str(scope.get("queue_source") or "").strip()
        else "",
        "canonical_title": _canonical_text(scope.get("facility")),
        "canonical_discipline": _canonical_text(scope.get("discipline")),
        "canonical_discipline_source": _canonical_text(scope.get("discipline_source"))
        if str(scope.get("discipline_source") or "").strip()
        else "",
        "status_interpretation_state": state or UNDEFINED_RU,
        "status_schema_validation": schema_pass,
        "status_deterministic_resolution": resolution_pass,
        "clarification_pending": bool(session.get(CLARIFICATION_SESSION_KEY)),
        "clarification_applied": bool(stored.get("clarification_applied")),
        "clarification_message": str(stored.get("clarification_message") or ""),
        "clarification_fragment": str(stored.get("clarification_fragment") or ""),
        "telemetry_visible": bool(usage),
        "telemetry_input_tokens": _usage_number(usage, "input_tokens"),
        "telemetry_output_tokens": _usage_number(usage, "output_tokens"),
        "telemetry_total_tokens": _usage_number(usage, "total_tokens"),
        "telemetry_latency_ms": _usage_number(usage, "latency_ms"),
        "telemetry_provider_calls": _usage_number(usage, "provider_call_count"),
        "telemetry_retries": _usage_number(usage, "retry_count"),
        "telemetry_request_id": _usage_text(usage, "request_id"),
        "provider_error_safe": _safe_provider_error(stored.get("provider_error")),
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
        "interpretation_channel": "",
        "llm_view_visible": False,
        "llm_provider": "",
        "llm_model": "",
        "llm_intent": "",
        "llm_agent_hint": "",
        "llm_project_hint": "",
        "llm_period_hint": "",
        "llm_queue_hint": "",
        "llm_title_hint": "",
        "llm_discipline_hint": "",
        "llm_system_hint": "",
        "llm_iwp_hint": "",
        "canonical_agent": UNDEFINED_RU,
        "canonical_project": UNDEFINED_RU,
        "canonical_period": UNDEFINED_RU,
        "canonical_queue": UNDEFINED_RU,
        "canonical_queue_source": "",
        "canonical_title": UNDEFINED_RU,
        "canonical_discipline": UNDEFINED_RU,
        "canonical_discipline_source": "",
        "status_interpretation_state": "",
        "status_schema_validation": "",
        "status_deterministic_resolution": "",
        "clarification_pending": False,
        "clarification_applied": False,
        "clarification_message": "",
        "clarification_fragment": "",
        "telemetry_visible": False,
        "telemetry_input_tokens": "",
        "telemetry_output_tokens": "",
        "telemetry_total_tokens": "",
        "telemetry_latency_ms": "",
        "telemetry_provider_calls": "",
        "telemetry_retries": "",
        "telemetry_request_id": "",
        "provider_error_safe": "",
    }


def _law(stored: Mapping[str, object]) -> str:
    if stored.get("intent") == "FORM_MONTHLY_COMMITMENT":
        return (
            "Constructor ещё не запущен. Подтверждение относится только к первому этапу "
            "(кандидатный состав). Месячное обязательство ещё не сформировано."
        )
    return "Constructor ещё не запущен. Черновик не заменяет миссию текущего запуска."


def _note(stored: Mapping[str, object]) -> str:
    parts: list[str] = []
    clarification_message = str(stored.get("clarification_message") or "").strip()
    if clarification_message:
        parts.append(clarification_message)
    if stored.get("processing_state") == "REJECTED":
        parts.append("Это не профессиональное поручение. Черновик миссии не создан.")
    if stored.get("intent") == "FORM_MONTHLY_COMMITMENT":
        if stored.get("processing_state") == "NEEDS_CONFIRMATION":
            parts.append(_MONTHLY_COMMITMENT_NOTE)
        else:
            parts.append(_MONTHLY_COMMITMENT_INCOMPLETE_NOTE)
    unresolved = stored.get("unresolved_fields") or ()
    if isinstance(unresolved, (list, tuple)) and unresolved:
        labels = [_FIELD_RU.get(str(item), str(item)) for item in unresolved]
        parts.append("Не определено: " + ", ".join(labels) + ".")
    ambiguities = stored.get("ambiguities") or ()
    if isinstance(ambiguities, (list, tuple)):
        for item in ambiguities:
            text = str(item).strip()
            if text and text not in parts:
                parts.append(text)
    return " ".join(parts)


def _extraction_text(extraction: object, key: str) -> str:
    if not isinstance(extraction, Mapping):
        return UNDEFINED_RU
    value = extraction.get(key)
    if value is None:
        return UNDEFINED_RU
    text = str(value)
    return text if text else '""'


def _canonical_text(value: object) -> str:
    text = str(value or "").strip()
    return text if text else UNDEFINED_RU


def _usage_text(usage: object, key: str, default: str = "") -> str:
    if not isinstance(usage, Mapping):
        return default
    text = str(usage.get(key) or "").strip()
    return text or default


def _usage_number(usage: object, key: str) -> str:
    if not isinstance(usage, Mapping) or key not in usage:
        return UNDEFINED_RU
    value = usage.get(key)
    if value is None or value == "":
        return UNDEFINED_RU
    return str(value)


def _schema_validation_label(stored: Mapping[str, object], extraction: object, usage: object) -> str:
    if isinstance(extraction, Mapping):
        return "YES"
    if isinstance(usage, Mapping) and usage.get("schema_validation_pass") is False:
        return "NO"
    if stored.get("interpretation_channel") == "deterministic":
        return "N/A"
    if stored.get("provider_error"):
        return "NO"
    return UNDEFINED_RU


def _safe_provider_error(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.casefold()
    for token in ("authorization", "api_key", "api-key", "bearer ", "aqvn", "sk-"):
        if token in lowered:
            return "Ошибка провайдера скрыта: обнаружен чувствительный фрагмент."
    return text[:240]
