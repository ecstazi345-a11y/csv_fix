"""
Multi-Model AI Router для Agent Harness (Execution OS).

Пока только mock-архитектура: без реальных API-вызовов, без расхода токенов.
Реальные провайдеры (OpenAI, DeepSeek, GigaChat, YandexGPT) будут подключены позже.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, TypedDict

from dotenv import load_dotenv

load_dotenv()

# --- Провайдеры и env-ключи ---

PROVIDER_ENV_KEYS: Dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "gigachat": "GIGACHAT_API_KEY",
    "yandexgpt": "YANDEXGPT_API_KEY",
}

PROVIDER_ROLES: Dict[str, str] = {
    "openai": "сильный reasoning",
    "deepseek": "дешёвые массовые задачи",
    "gigachat": "русский корпоративный контур",
    "yandexgpt": "русский корпоративный контур",
}

# Политика маршрутизации: task_type → предпочтительный провайдер
TASK_ROUTING_POLICY: Dict[str, str] = {
    "war_room_summary": "openai",
    "contract_claim_analysis": "openai",
    "bulk_classification": "deepseek",
    "constraint_category_detection": "deepseek",
    "simple_summary": "deepseek",
    "official_letter_draft": "gigachat",
}

# Приоритет русских корпоративных провайдеров (если оба доступны)
RU_CORPORATE_PROVIDERS = ("gigachat", "yandexgpt")

MOCK_RESULT_TEXT = "AI Router готов. Реальный вызов модели будет подключён позже."


class ProviderInfo(TypedDict):
    provider: str
    available: bool
    role: str


class AiTaskResult(TypedDict):
    status: str
    provider: str
    task_type: str
    result: str
    tokens_used: int
    cost: float


def _is_provider_available(provider: str) -> bool:
    """Проверяет наличие ключа провайдера в окружении."""
    env_key = PROVIDER_ENV_KEYS.get(provider)
    if not env_key:
        return False
    value = os.getenv(env_key)
    return bool(value and str(value).strip())


def get_available_providers() -> List[ProviderInfo]:
    """
    Возвращает список провайдеров с флагом доступности по env vars.
    """
    result: List[ProviderInfo] = []
    for provider, role in PROVIDER_ROLES.items():
        result.append(
            {
                "provider": provider,
                "available": _is_provider_available(provider),
                "role": role,
            }
        )
    return result


def _pick_ru_corporate_provider() -> str:
    """Выбирает gigachat или yandexgpt — первый доступный, иначе gigachat по умолчанию."""
    for provider in RU_CORPORATE_PROVIDERS:
        if _is_provider_available(provider):
            return provider
    return "gigachat"


def route_task(
    task_type: str,
    complexity: str = "medium",
    data_sensitivity: str = "normal",
) -> str:
    """
    Выбирает провайдера по типу задачи, сложности и чувствительности данных.

    Правила (в порядке приоритета):
    - complexity == "high" → openai
    - task_type из TASK_ROUTING_POLICY
    - data_sensitivity == "ru_internal" → gigachat / yandexgpt
    - default → openai
    """
    if complexity == "high":
        return "openai"

    if task_type in TASK_ROUTING_POLICY:
        policy_provider = TASK_ROUTING_POLICY[task_type]
        if policy_provider in RU_CORPORATE_PROVIDERS:
            return _pick_ru_corporate_provider()
        return policy_provider

    if data_sensitivity == "ru_internal":
        return _pick_ru_corporate_provider()

    return "openai"


def run_ai_task(
    task_type: str,
    prompt: str,
    context: Optional[Dict[str, Any]] = None,
    provider: Optional[str] = None,
    complexity: str = "medium",
    data_sensitivity: str = "normal",
) -> AiTaskResult:
    """
    Mock-выполнение AI-задачи.

    Реальный вызов API будет добавлен позже; сейчас возвращает заглушку
    с выбранным провайдером и нулевой стоимостью.
    """
    selected = provider or route_task(
        task_type=task_type,
        complexity=complexity,
        data_sensitivity=data_sensitivity,
    )

    # prompt и context зарезервированы для будущей интеграции
    _ = prompt
    _ = context

    return {
        "status": "mock",
        "provider": selected,
        "task_type": task_type,
        "result": MOCK_RESULT_TEXT,
        "tokens_used": 0,
        "cost": 0.0,
    }
