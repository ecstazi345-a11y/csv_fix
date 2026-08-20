"""
MPO-004A — pure display helpers for Agent Cockpit.

No Streamlit, no DB, no LLM. Used by page 51 and unit tests.
"""

from __future__ import annotations

from typing import Any, Optional

# Primary reason shown under the main status headline.
RECOMMENDATION_RU: dict[str, str] = {
    "READY_FOR_HUMAN_DECISION": "Готов к решению",
    "READY_WITH_WARNINGS": "Готов к решению с предупреждениями",
    "RESOURCE_DEFICIT": "Дефицит ресурсов",
    "ADMISSION_BLOCKED": "Есть блокирующий допуск",
    "MIXED_CONDITION": "Смешанное состояние",
    "NOT_READY_DATA_GAPS": "Недостаточно данных для решения",
}

# Large status headline (user layer).
STATUS_HEADLINE_RU: dict[str, str] = {
    "READY_FOR_HUMAN_DECISION": "МЕСЯЧНЫЙ ПЛАН ГОТОВ К РЕШЕНИЮ",
    "READY_WITH_WARNINGS": "МЕСЯЧНЫЙ ПЛАН ГОТОВ К РЕШЕНИЮ С ПРЕДУПРЕЖДЕНИЯМИ",
    "RESOURCE_DEFICIT": "МЕСЯЧНЫЙ ПЛАН ТРЕБУЕТ РЕШЕНИЯ",
    "ADMISSION_BLOCKED": "МЕСЯЧНЫЙ ПЛАН ТРЕБУЕТ РЕШЕНИЯ",
    "MIXED_CONDITION": "МЕСЯЧНЫЙ ПЛАН ТРЕБУЕТ РЕШЕНИЯ",
    "NOT_READY_DATA_GAPS": "НЕДОСТАТОЧНО ДАННЫХ ДЛЯ РЕШЕНИЯ",
}

VALIDATION_RU: dict[str, str] = {
    "PASS": "Пройдено",
    "PASS_WITH_WARNINGS": "С предупреждениями",
    "BLOCKED": "Недостаточно данных",
}

ACTION_RU: dict[str, str] = {
    "REVIEW_PLAN": "Пересмотреть месячное обязательство",
    "REVIEW_ADMISSION": "Проверить и снять блокирующие допуски",
    "REVIEW_RESOURCE_PLAN": "Проверить ресурсный план",
    "FIX_DATA_QUALITY": "Устранить проблемы качества данных",
    "WAIT_NOT_REQUIRED_LAYER": "Проверить корректировки исключаемого объёма",
}

SEVERITY_RU: dict[str, str] = {
    "BLOCKER": "Критично",
    "WARNING": "Внимание",
    "INFO": "Инфо",
}

SEVERITY_ICON: dict[str, str] = {
    "BLOCKER": "🔴",
    "WARNING": "🟠",
    "INFO": "🔵",
}

SEVERITY_RANK: dict[str, int] = {
    "BLOCKER": 0,
    "WARNING": 1,
    "INFO": 2,
}

FINDING_RU: dict[str, str] = {
    "CAPACITY_DATA_MISSING": "Нет утверждённой мощности",
    "RESOURCE_DEFICIT": "Дефицит ресурсов",
    "ADMISSION_BLOCKED": "Блокирующий допуск",
    "scope_remaining_not_joined": "Остаток BOQ требует проверки",
    "not_required_adjustments_not_applied": "Не учтены корректировки исключаемого объёма",
    "scope_read_failed": "Ошибка чтения объёма BOQ",
    "no_plan_lines": "Нет строк плана",
    "completed_boq_still_requested": "Выполненный объём всё ещё в плане",
    "admission_status_unavailable": "Статус допуска недоступен",
    "blank_project_code": "Пустой код проекта",
    "month_normalization_issue": "Проблема нормализации месяца",
}

STEP_LABELS: list[tuple[str, str]] = [
    ("GATHER", "Сбор данных"),
    ("ANALYZE", "Анализ"),
    ("VALIDATE", "Проверка"),
    ("HUMAN_DECISION", "Решение человека"),
]

BARE_PROJECT_LABELS = frozenset({"бхк", "bhk"})


def is_bare_project_label(value: Any) -> bool:
    text = str(value or "").strip()
    return text.casefold() in BARE_PROJECT_LABELS


def _space_int(num: int) -> str:
    return f"{num:,}".replace(",", " ")


def format_kpi_value(value: Any, *, kind: str = "number") -> str:
    """None → «Нет данных». Zero is a real zero except for None."""
    if value is None:
        return "Нет данных"
    if isinstance(value, float) and value != value:  # NaN
        return "Нет данных"
    if kind == "coverage":
        try:
            return f"{float(value) * 100:.0f} %"
        except (TypeError, ValueError):
            return "Нет данных"
    if kind == "int":
        try:
            return _space_int(int(value))
        except (TypeError, ValueError):
            return "Нет данных"
    if kind == "hours":
        try:
            num = float(value)
            if abs(num - round(num)) < 1e-9:
                return _space_int(int(round(num)))
            # one decimal, space thousands
            whole = int(abs(num))
            frac = abs(num) - whole
            sign = "-" if num < 0 else ""
            return f"{sign}{_space_int(whole)}.{int(round(frac * 10))}"
        except (TypeError, ValueError):
            return "Нет данных"
    return str(value)


def recommendation_label(code: Any) -> str:
    key = str(code or "").strip()
    return RECOMMENDATION_RU.get(key, key or "—")


def status_headline(code: Any) -> str:
    key = str(code or "").strip()
    return STATUS_HEADLINE_RU.get(key, "МЕСЯЧНЫЙ ПЛАН ТРЕБУЕТ РЕШЕНИЯ")


def validation_label(code: Any) -> str:
    key = str(code or "").strip()
    return VALIDATION_RU.get(key, key or "—")


def action_label(code: Any) -> str:
    key = str(code or "").strip()
    return ACTION_RU.get(key, key or "—")


def severity_label(code: Any) -> str:
    key = str(code or "").strip().upper()
    return SEVERITY_RU.get(key, key or "—")


def severity_icon(code: Any) -> str:
    key = str(code or "").strip().upper()
    return SEVERITY_ICON.get(key, "⚪")


def finding_label(code: Any) -> str:
    key = str(code or "").strip()
    return FINDING_RU.get(key, key or "—")


def finding_count_phrase(count: Any) -> str:
    if count is None or count == "":
        return ""
    try:
        n = int(count)
    except (TypeError, ValueError):
        return ""
    if n == 1:
        return "1 строка"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return f"{_space_int(n)} строки"
    return f"{_space_int(n)} строк"


def finding_compact_line(finding: dict[str, Any]) -> str:
    code = str(finding.get("code") or "").strip()
    sev = str(finding.get("severity") or "").strip().upper()
    icon = severity_icon(sev)
    title = finding_label(code)
    phrase = finding_count_phrase(finding.get("count"))
    if phrase:
        return f"{icon} {title} — {phrase}"
    return f"{icon} {title}"


def prioritize_findings(findings: list[dict[str, Any]], *, limit: Optional[int] = None) -> list[dict[str, Any]]:
    ordered = sorted(
        [f for f in findings if isinstance(f, dict)],
        key=lambda f: (
            SEVERITY_RANK.get(str(f.get("severity") or "").strip().upper(), 9),
            -int(f.get("count") or 0) if str(f.get("count") or "").replace("-", "").isdigit() else 0,
        ),
    )
    if limit is None:
        return ordered
    return ordered[: max(0, int(limit))]


def run_matches_scope(run: Optional[dict[str, Any]], project_code: str, month_key: str) -> bool:
    if not isinstance(run, dict):
        return False
    scope = run.get("mpo_cockpit_run_scope")
    if isinstance(scope, dict):
        return (
            str(scope.get("project_code") or "").strip() == str(project_code or "").strip()
            and str(scope.get("month_key") or "").strip() == str(month_key or "").strip()
        )
    return (
        str(run.get("project_code") or "").strip() == str(project_code or "").strip()
        and str(run.get("month_key_input") or "").strip() == str(month_key or "").strip()
    )


def step_statuses(run: Optional[dict[str, Any]]) -> list[dict[str, str]]:
    """Derive stepper UI from trace + final state. No fake animation."""
    result: list[dict[str, str]] = []
    if not isinstance(run, dict):
        for code, label in STEP_LABELS:
            result.append({"code": code, "label": label, "ui": "pending"})
        return result

    state = str(run.get("state") or "").strip()
    trace = run.get("trace") if isinstance(run.get("trace"), list) else []
    by_stage: dict[str, str] = {}
    for event in trace:
        if not isinstance(event, dict):
            continue
        stage = str(event.get("stage") or "").strip()
        status = str(event.get("status") or "").strip().upper()
        if stage:
            by_stage[stage] = status

    if state == "FAILED":
        for code, label in STEP_LABELS:
            ui = "error" if code == "GATHER" else "skipped"
            result.append({"code": code, "label": label, "ui": ui})
        return result

    if state == "HUMAN_DECISION":
        for code, label in STEP_LABELS:
            if code == "HUMAN_DECISION":
                ui = "current"
            elif by_stage.get(code) == "ERROR":
                ui = "error"
            else:
                ui = "done"
            result.append({"code": code, "label": label, "ui": ui})
        return result

    for code, label in STEP_LABELS:
        status = by_stage.get(code)
        if status == "ERROR":
            ui = "error"
        elif status == "OK":
            ui = "done"
        else:
            ui = "pending"
        result.append({"code": code, "label": label, "ui": ui})
    return result
