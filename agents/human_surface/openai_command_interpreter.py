"""OpenAI adapter for one structured command extraction.

The request carries the raw command and a short instruction. It does not carry
a catalog, a candidate package, dialogue history, or runtime events. The model
cannot call tools.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

from agents.human_surface.command_interpreter_provider import (
    EXTRACTION_FIELDS,
    ExtractionRejected,
    CommandInterpreterProvider,
    InterpreterUsage,
    ProviderExtractionResult,
    ProviderFailure,
    validate_extraction,
)

MODEL = "gpt-4.1-mini"
MAX_OUTPUT_TOKENS = 160
TEMPERATURE = 0
MAX_SDK_RETRIES = 0
PROVIDER_NAME = "openai"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOG = logging.getLogger("dynamis.command_interpreter")
_SAFE_MESSAGE_LIMIT = 180
_SECRET_TEXT = re.compile(
    r"(AQVN[A-Za-z0-9_\-]{8,})|(sk-[A-Za-z0-9_\-]{8,})|(Bearer\s+\S+)|(api[_-]?key\s*[=:]\s*\S+)",
    re.IGNORECASE,
)
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_INSTRUCTION = (
    "Извлеки поля одной команды планировщика. Верни только JSON по схеме. "
    "Не присваивай коды проектов, титулов и систем. "
    "Пиши намёки так, как их сказал человек, исправив только явную опечатку. "
    "intent: FORM_CANDIDATE_PACKAGE, если просят сформировать, собрать или подготовить "
    "кандидатный состав или кандидатов. "
    "FORM_MONTHLY_COMMITMENT, если просят месячное обязательство, месячное "
    "производственное обязательство или плановое обязательство на месяц. "
    "Не своди месячное обязательство к FORM_CANDIDATE_PACKAGE. Иначе пустая строка. "
    "target_agent_hint: constructor, если речь о конструкторе или кандидатном составе. "
    "Иначе пустая строка. "
    "project_hint: название проекта словами, без кода. "
    "period_hint: месяц и год, например ноябрь 2026. Пусто, если месяца нет. "
    "queue_hint: 1 или 2. Пусто, если очередь не названа. "
    "title_hint: код титула с дефисом, если человек назвал его части, например 16160-13. "
    "Не выдумывай титул. "
    "discipline_hint: дисциплина словами человека. "
    "system_hint и iwp_hint: пустые строки, если их не назвали. "
    "Без пояснений и без других полей."
)
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["", "FORM_CANDIDATE_PACKAGE", "FORM_MONTHLY_COMMITMENT"],
        },
        "target_agent_hint": {"type": "string", "enum": ["", "constructor"]},
        "project_hint": {"type": "string"},
        "period_hint": {"type": "string"},
        "queue_hint": {"type": "string"},
        "title_hint": {"type": "string"},
        "discipline_hint": {"type": "string"},
        "system_hint": {"type": "string"},
        "iwp_hint": {"type": "string"},
    },
    "required": list(EXTRACTION_FIELDS),
}


def openai_key_present() -> bool:
    """True when the environment has a non-empty key. The value is never returned."""
    _load_env()
    return bool(str(os.getenv("OPENAI_API_KEY") or "").strip())


def request_arguments(raw_text: str) -> dict[str, object]:
    """Exact model request. The key is not part of this payload."""
    return {
        "model": MODEL,
        "instructions": _INSTRUCTION,
        "input": str(raw_text or "").strip()[:1000],
        "temperature": TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "command_extraction",
                "strict": True,
                "schema": _SCHEMA,
            }
        },
    }


class OpenAICommandInterpreter:
    """One Responses API call. A schema or transport failure returns no extraction."""

    def extract(self, raw_text: str) -> ProviderExtractionResult:
        started = time.perf_counter()
        arguments = request_arguments(raw_text)
        response = None
        try:
            response = command_interpreter_client().responses.create(**arguments)
            extraction = validate_extraction(json.loads(getattr(response, "output_text", "") or ""))
            usage = _usage(response, success=True, started=started)
        except Exception as exc:
            failure = classify_provider_failure(exc)
            usage = _usage(response, success=False, started=started) if response is not None else _failed_usage(started)
            _LOG.info(
                "command extraction failed provider=%s model=%s category=%s error_type=%s http_status=%s",
                usage.provider,
                usage.model,
                failure.category,
                failure.error_type,
                failure.http_status,
            )
            return ProviderExtractionResult(extraction=None, usage=usage, failure=failure)
        _log_usage(usage)
        return ProviderExtractionResult(extraction=extraction, usage=usage)


def command_interpreter_client():
    """One fail-fast client. The SDK must not repeat a failed command request."""
    _load_env()
    from openai import OpenAI

    return OpenAI(max_retries=MAX_SDK_RETRIES)


def build_openai_provider() -> CommandInterpreterProvider | None:
    if not openai_key_present():
        return None
    return OpenAICommandInterpreter()


def _load_env() -> None:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env")


def _usage(response: object, *, success: bool, started: float) -> InterpreterUsage:
    raw = getattr(response, "usage", None)
    input_tokens = int(getattr(raw, "input_tokens", 0) or 0)
    output_tokens = int(getattr(raw, "output_tokens", 0) or 0)
    total_tokens = int(getattr(raw, "total_tokens", 0) or (input_tokens + output_tokens))
    return InterpreterUsage(
        provider=PROVIDER_NAME,
        model=MODEL,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        latency_ms=int((time.perf_counter() - started) * 1000),
        success=success,
    )


def classify_provider_failure(exc: BaseException) -> ProviderFailure:
    """Map one provider exception to a closed category. The request itself is dropped."""
    status = getattr(exc, "status_code", None)
    http_status = status if isinstance(status, int) else None
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    request_id = ""
    if headers is not None:
        request_id = _safe_token(headers.get("x-request-id"))
    return ProviderFailure(
        category=_failure_category(exc, http_status),
        error_type=type(exc).__name__,
        error_code=_safe_token(getattr(exc, "code", None)),
        error_param=_safe_token(getattr(exc, "param", None)),
        http_status=http_status,
        request_id=request_id,
        safe_error_message=_safe_message(_failure_message(exc)),
    )


def _failure_message(exc: BaseException) -> str:
    """Prefer provider message; keep ExtractionRejected/JSON detail for diagnostics."""
    message = getattr(exc, "message", None)
    if isinstance(message, str) and message.strip():
        return message
    if isinstance(exc, (ExtractionRejected, json.JSONDecodeError)):
        detail = " ".join(str(exc).split())
        if detail:
            return f"{type(exc).__name__}: {detail}"
    return type(exc).__name__


def _failure_category(exc: BaseException, http_status: int | None) -> str:
    import httpx
    from openai import (
        APIConnectionError,
        APIStatusError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        PermissionDeniedError,
        RateLimitError,
        UnprocessableEntityError,
    )

    if isinstance(exc, (json.JSONDecodeError, ExtractionRejected)):
        return "response_validation"
    if isinstance(exc, (APITimeoutError, APIConnectionError, httpx.TimeoutException, httpx.TransportError)):
        return "network"
    if isinstance(exc, (AuthenticationError, PermissionDeniedError)) or http_status in {401, 403}:
        return "authentication"
    if isinstance(exc, RateLimitError) or http_status == 429:
        return "rate_or_billing"
    if isinstance(exc, (BadRequestError, UnprocessableEntityError)) or http_status in {400, 422}:
        return "configuration"
    if isinstance(exc, APIStatusError) and http_status is not None and http_status >= 500:
        return "provider_server"
    if isinstance(exc, (TypeError, ValueError)):
        return "configuration"
    return "unknown"


def _safe_message(value: object) -> str:
    text = _SECRET_TEXT.sub("[redacted]", str(value or ""))
    text = " ".join(text.split())
    return text[:_SAFE_MESSAGE_LIMIT]


def _safe_token(value: object) -> str:
    text = str(value or "").strip()
    if not _SAFE_TOKEN.fullmatch(text):
        return ""
    return text


def _failed_usage(started: float) -> InterpreterUsage:
    return InterpreterUsage(
        provider=PROVIDER_NAME,
        model=MODEL,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        latency_ms=int((time.perf_counter() - started) * 1000),
        success=False,
    )


def _log_usage(usage: InterpreterUsage) -> None:
    _LOG.info(
        "command extraction provider=%s model=%s input_tokens=%s output_tokens=%s total_tokens=%s latency_ms=%s success=%s",
        usage.provider,
        usage.model,
        usage.input_tokens,
        usage.output_tokens,
        usage.total_tokens,
        usage.latency_ms,
        usage.success,
    )
