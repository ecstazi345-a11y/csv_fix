"""YandexGPT adapter for one structured command extraction.

The client uses the OpenAI-compatible endpoint. It does not call OpenAI and it
does not repeat a failed request. Hints still have to pass the existing resolver.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agents.human_surface.command_interpretation import CommandInterpretation
from agents.human_surface.command_interpreter_provider import (
    CommandInterpreterProvider,
    InterpreterUsage,
    ProviderExtractionResult,
    ProviderFailure,
    resolve_extraction,
    resolved_for_confirmation,
    validate_extraction,
)
from agents.human_surface.openai_command_interpreter import classify_provider_failure
from agents.human_surface.work_context import WorkContextCatalog

PROVIDER_NAME = "yandex"
MAX_OUTPUT_TOKENS = 160
TEMPERATURE = 0
MAX_SDK_RETRIES = 0
# Bounded transport timeouts for Yandex only. OpenAI provider keeps SDK defaults.
CONNECT_TIMEOUT_SECONDS = 20.0
READ_TIMEOUT_SECONDS = 60.0
WRITE_TIMEOUT_SECONDS = 30.0
POOL_TIMEOUT_SECONDS = 20.0
_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOG = logging.getLogger("dynamis.command_interpreter")
_YANDEX_SECRET = re.compile(r"(AQVN[A-Za-z0-9_\-]{8,})|(sk-[A-Za-z0-9_\-]{8,})|(Bearer\s+\S+)", re.IGNORECASE)
_INSTRUCTION = (
    "Извлеки поля одной команды планировщика. Верни РОВНО один JSON-объект "
    "и только эти ключи: intent, target_agent_hint, project_hint, period_hint, "
    "queue_hint, title_hint, discipline_hint, system_hint, iwp_hint. "
    "Все значения — только строки (string). Не используй null. "
    "Не добавляй другие поля. Без markdown и без code fences. "
    "Не присваивай коды проектов (PRJ_...), mission ID или run ID. "
    "intent: только FORM_CANDIDATE_PACKAGE, если просят сформировать, собрать "
    "или подготовить кандидатный состав или кандидатов; "
    "только FORM_MONTHLY_COMMITMENT, если просят месячное обязательство, "
    "месячное производственное обязательство или плановое обязательство на месяц; "
    "не своди месячное обязательство к FORM_CANDIDATE_PACKAGE; иначе пустая строка \"\". "
    "target_agent_hint: только constructor, если речь о конструкторе или "
    "кандидатном составе; иначе пустая строка \"\". "
    "Не пиши MONTHLY_PLAN_CONSTRUCTOR, Constructor Agent или иные обозначения агента. "
    "project_hint: название проекта словами, без кода. "
    "period_hint: месяц и год, например ноябрь 2026; пустая строка, если месяца нет. "
    "queue_hint: 1 или 2; пустая строка, если очередь не названа. "
    "title_hint: код титула с дефисом, если человек назвал его части, например 16160-13. "
    "Не выдумывай титул. "
    "discipline_hint: дисциплина словами человека. "
    "system_hint и iwp_hint: пустые строки \"\", если их не назвали. "
    "Без пояснений."
)


@dataclass(frozen=True)
class YandexInterpretationAttempt:
    result: Optional[ProviderExtractionResult]
    interpretation: Optional[CommandInterpretation]
    deterministic_resolution_pass: bool
    mission_created: bool = False
    constructor_run_created: bool = False


def yandex_key_present() -> bool:
    """True when the key env var is non-empty. The value is never returned."""
    _load_env()
    return bool(str(os.getenv("YANDEX_API_KEY") or "").strip())


def yandex_configuration() -> Optional[dict[str, str]]:
    """Public settings only. The API key is intentionally absent."""
    _load_env()
    folder = str(os.getenv("YANDEX_FOLDER_ID") or "").strip()
    base_url = str(os.getenv("YANDEX_BASE_URL") or "").strip()
    model = str(os.getenv("YANDEX_MODEL_URI") or "").strip()
    if not (yandex_key_present() and folder and base_url and model):
        return None
    return {"base_url": base_url, "folder_id": folder, "model": model}


def yandex_request_arguments(raw_text: str, model: str) -> dict[str, object]:
    """Chat request without credentials, tools, or project data."""
    return {
        "model": model,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "messages": [
            {"role": "system", "content": _INSTRUCTION},
            {"role": "user", "content": str(raw_text or "").strip()[:1000]},
        ],
        "response_format": {"type": "json_object"},
    }


class YandexCommandInterpreter:
    """One chat completion. A transport or schema failure does not call the resolver."""

    def extract(self, raw_text: str) -> ProviderExtractionResult:
        started = time.perf_counter()
        settings = yandex_configuration()
        if settings is None:
            usage = _usage(
                model="",
                started=started,
                success=False,
                call_count=0,
                schema_validation_pass=False,
                error_category="configuration",
            )
            return ProviderExtractionResult(extraction=None, usage=usage)
        arguments = yandex_request_arguments(raw_text, settings["model"])
        response = None
        try:
            response = yandex_client().chat.completions.create(**arguments)
            extraction = validate_extraction(json.loads(_message_text(response)))
            usage = _usage(
                model=settings["model"],
                started=started,
                success=True,
                response=response,
                schema_validation_pass=True,
            )
        except Exception as exc:
            failure = _redact_failure(classify_provider_failure(exc))
            usage = _usage(
                model=settings["model"],
                started=started,
                success=False,
                response=response,
                schema_validation_pass=False,
                failure=failure,
            )
            _LOG.info(
                "command extraction failed provider=%s model=%s category=%s error_type=%s http_status=%s",
                PROVIDER_NAME,
                settings["model"],
                failure.category,
                failure.error_type,
                failure.http_status,
            )
            return ProviderExtractionResult(extraction=None, usage=usage, failure=failure)
        return ProviderExtractionResult(extraction=extraction, usage=usage)


def build_yandex_provider() -> CommandInterpreterProvider | None:
    if yandex_configuration() is None:
        return None
    return YandexCommandInterpreter()


def interpret_with_yandex(
    *,
    command_id: str,
    raw_text: str,
    catalog: WorkContextCatalog,
    provider: Optional[CommandInterpreterProvider] = None,
) -> YandexInterpretationAttempt:
    """Extract once, then resolve only a schema-valid hint set."""
    selected = provider if provider is not None else build_yandex_provider()
    if selected is None:
        return YandexInterpretationAttempt(
            result=YandexCommandInterpreter().extract(raw_text),
            interpretation=None,
            deterministic_resolution_pass=False,
        )
    result = selected.extract(raw_text)
    if result.extraction is None or result.usage.schema_validation_pass is not True:
        return YandexInterpretationAttempt(result=result, interpretation=None, deterministic_resolution_pass=False)
    resolved = resolve_extraction(result.extraction, catalog, command_id=command_id)
    passed = _resolution_passed(resolved)
    return YandexInterpretationAttempt(
        result=result,
        interpretation=resolved,
        deterministic_resolution_pass=passed,
        mission_created=bool(resolved.mission_created),
    )


def yandex_client():
    """Fail-fast client. Missing configuration raises before a request is sent."""
    settings = yandex_configuration()
    if settings is None:
        raise RuntimeError("Yandex command interpreter is not configured")
    _load_env()
    import httpx
    from openai import OpenAI

    return OpenAI(
        api_key=str(os.getenv("YANDEX_API_KEY") or "").strip(),
        base_url=settings["base_url"],
        project=settings["folder_id"],
        max_retries=MAX_SDK_RETRIES,
        timeout=httpx.Timeout(
            connect=CONNECT_TIMEOUT_SECONDS,
            read=READ_TIMEOUT_SECONDS,
            write=WRITE_TIMEOUT_SECONDS,
            pool=POOL_TIMEOUT_SECONDS,
        ),
    )


def _resolution_passed(resolved: CommandInterpretation) -> bool:
    return resolved_for_confirmation(resolved) and not resolved.mission_created


def _message_text(response: object) -> str:
    choices = getattr(response, "choices", None) or ()
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    return content if isinstance(content, str) else ""


def _usage(
    *,
    model: str,
    started: float,
    success: bool,
    call_count: int = 1,
    response: object | None = None,
    schema_validation_pass: bool = False,
    failure: Optional[ProviderFailure] = None,
    error_category: str = "",
) -> InterpreterUsage:
    raw = getattr(response, "usage", None)
    return InterpreterUsage(
        provider=PROVIDER_NAME,
        model=model,
        input_tokens=int(getattr(raw, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(raw, "completion_tokens", 0) or 0),
        total_tokens=int(getattr(raw, "total_tokens", 0) or 0),
        latency_ms=int((time.perf_counter() - started) * 1000),
        success=success,
        provider_call_count=call_count,
        retry_count=0,
        request_id=_response_id(response) or ("" if failure is None else failure.request_id),
        http_status=None if failure is None else failure.http_status,
        error_category=error_category or ("" if failure is None else failure.category),
        error_code="" if failure is None else failure.error_code,
        schema_validation_pass=schema_validation_pass,
    )


def _response_id(response: object | None) -> str:
    text = str(getattr(response, "id", "") or "").strip()
    if not text or _YANDEX_SECRET.search(text):
        return ""
    return text[:80]


def _redact_failure(failure: ProviderFailure) -> ProviderFailure:
    return ProviderFailure(
        category=failure.category,
        error_type=failure.error_type,
        error_code=failure.error_code,
        error_param=failure.error_param,
        http_status=failure.http_status,
        request_id=failure.request_id,
        safe_error_message=_redact(failure.safe_error_message),
    )


def _redact(value: object) -> str:
    return _YANDEX_SECRET.sub("[redacted]", str(value or ""))


def _load_env() -> None:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env")
