"""Display helpers for monthly_plan_constraints (read-only, no save logic)."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable, Mapping

import pandas as pd

GENERIC_BLOCK_REASONS = frozenset(
    {
        "Есть блокирующие ограничения",
        "Обнаружены блокирующие ограничения",
        "Есть блокирующие ограничения.",
        "Обнаружены блокирующие ограничения.",
        "Есть ограничения",
        "Обнаружены ограничения",
        "Есть ограничения.",
        "Обнаружены ограничения.",
    }
)

_TEMPLATE_BLOCK_DESCRIPTIONS = frozenset(
    {
        "Зафиксировать ограничение и назначить корректирующее действие",
        "Запросить уточнение у ответственного отдела",
        "Критерии допуска выполнены",
        "Есть непроверенные / частично снятые / рискованные ограничения",
    }
)

MIN_BLOCK_DESCRIPTION_LEN = 15

_AUDIT_BOILERPLATE_PREFIXES = (
    "Тип решения:",
    "Причина:",
    "Действие:",
    "Ответственный:",
    "Срок:",
    "ФИО принявшего решение:",
    "Дата и время:",
    "Решение:",
    "Комментарий:",
)

_SECTION_LABELS = ("Причина:", "Комментарий:", "Действие:")

_STATUS_NOISE = frozenset(
    {
        "ЗАБЛОКИРОВАНО",
        "БЛОКИРОВАНО",
        "HOLD",
        "FAIL",
        "Блокировка",
        "Заблокировано",
        "БЛОКИРОВКА",
    }
)

_JOURNAL_LINE_RE = re.compile(r"^\[(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})\]\s*(.+)$")

_CHECK_STATUS_LABELS = {
    "PASS": "Допущено",
    "WARNING": "Требует уточнения",
    "ОЖИДАЕТ": "Ожидает проверки",
    "HOLD": "Заблокировано",
    "FAIL": "Не пройдено",
}


def safe_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def is_generic_block_reason(text: str) -> bool:
    cleaned = safe_text(text)
    if not cleaned:
        return False
    if cleaned in GENERIC_BLOCK_REASONS:
        return True
    lowered = cleaned.lower()
    return lowered in {item.lower() for item in GENERIC_BLOCK_REASONS}


def is_insufficient_block_description(text: str, *, min_len: int = MIN_BLOCK_DESCRIPTION_LEN) -> bool:
    """True if description is too short or only audit/template boilerplate."""
    cleaned = safe_text(text)
    if len(cleaned) < min_len:
        return True
    substance = _strip_audit_boilerplate(cleaned)
    if len(substance) < min_len:
        return True
    if is_generic_block_reason(substance):
        return True
    if substance in _TEMPLATE_BLOCK_DESCRIPTIONS:
        return True
    if substance.lower() in {item.lower() for item in _TEMPLATE_BLOCK_DESCRIPTIONS}:
        return True
    return False


def _normalize_check_status(value: Any) -> str:
    text = safe_text(value).upper()
    if text in _CHECK_STATUS_LABELS:
        return text
    if text in ("ОЖИДАЕТ",):
        return "ОЖИДАЕТ"
    return text


def _is_noise_line(stripped: str) -> bool:
    if not stripped:
        return True
    if stripped in _STATUS_NOISE or stripped.upper() in _STATUS_NOISE:
        return True
    if re.match(r"^\d{2}\.\d{2}\.\d{4}(\s+\d{2}:\d{2})?", stripped):
        return True
    if re.search(r"\d{2}:\d{2}", stripped) and stripped.endswith("МСК"):
        return True
    return False


def _strip_journal_prefix(text: str) -> str:
    cleaned = safe_text(text)
    marker = "): "
    marker_idx = cleaned.find(marker)
    if cleaned.startswith("[") and marker_idx > 0:
        return cleaned[marker_idx + len(marker) :].strip()
    return cleaned


def _extract_labeled_section(text: str, label: str) -> str:
    lines = text.splitlines()
    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped.startswith(label):
            continue
        inline = stripped[len(label) :].strip()
        collected: list[str] = []
        if inline:
            collected.append(inline)
        for follow in lines[index + 1 :]:
            follow_stripped = follow.strip()
            if not follow_stripped:
                if collected:
                    break
                continue
            if any(follow_stripped.startswith(prefix) for prefix in _AUDIT_BOILERPLATE_PREFIXES):
                break
            collected.append(follow_stripped)
        return " ".join(collected).strip()
    return ""


def _strip_audit_boilerplate(text: str) -> str:
    cleaned = safe_text(text)
    if not cleaned:
        return ""

    for label in _SECTION_LABELS:
        section = _extract_labeled_section(cleaned, label)
        if section and not is_generic_block_reason(section):
            return section

    lines: list[str] = []
    for raw_line in cleaned.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if _JOURNAL_LINE_RE.match(stripped):
            continue
        if any(stripped.startswith(prefix) for prefix in _AUDIT_BOILERPLATE_PREFIXES):
            continue
        if _is_noise_line(stripped):
            continue
        if is_generic_block_reason(stripped):
            continue
        lines.append(stripped)
    if lines:
        return " ".join(lines).strip()
    action = _extract_labeled_section(cleaned, "Действие:")
    if action and not is_generic_block_reason(action):
        return action
    return ""


def _comment_substance(comment: str) -> str:
    cleaned = safe_text(comment)
    if not cleaned:
        return ""

    journal_bodies: list[str] = []
    free_lines: list[str] = []
    for raw_line in cleaned.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        match = _JOURNAL_LINE_RE.match(stripped)
        if match:
            body = _strip_audit_boilerplate(_strip_journal_prefix(safe_text(match.group(2))))
            if body and not is_generic_block_reason(body):
                journal_bodies.append(body)
            continue
        if any(stripped.startswith(prefix) for prefix in _AUDIT_BOILERPLATE_PREFIXES):
            continue
        if _is_noise_line(stripped):
            continue
        if is_generic_block_reason(stripped):
            continue
        free_lines.append(stripped)

    if journal_bodies:
        return journal_bodies[-1]
    if free_lines:
        return free_lines[-1]
    return ""


def _row_get(row: Mapping[str, Any] | Any, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    if hasattr(row, "get"):
        return row.get(key)
    return getattr(row, key, None)


def constraint_block_substance(row: Mapping[str, Any] | Any) -> str:
    root = _strip_audit_boilerplate(safe_text(_row_get(row, "root_cause")))
    if root and not is_generic_block_reason(root):
        return root

    block = safe_text(_row_get(row, "block_reason"))
    if block and not is_generic_block_reason(block):
        return block

    comment_text = _comment_substance(safe_text(_row_get(row, "comment")))
    if comment_text and not is_generic_block_reason(comment_text):
        return comment_text

    action = _extract_labeled_section(safe_text(_row_get(row, "root_cause")), "Действие:")
    if action and not is_generic_block_reason(action):
        return action

    if root:
        return root
    if block:
        return block
    return "Есть блокирующие ограничения"


def _format_target_date(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "не указан"
    if isinstance(value, date):
        return value.isoformat()
    text = safe_text(value)
    if not text:
        return "не указан"
    try:
        parsed = pd.to_datetime(text)
        if pd.isna(parsed):
            return text
        return parsed.date().isoformat()
    except Exception:  # noqa: BLE001
        return text


def constraint_decision_line(
    row: Mapping[str, Any] | Any,
    dept_label_func: Callable[[Any], str] | None = None,
) -> str:
    status = _normalize_check_status(_row_get(row, "check_status"))
    dept_raw = safe_text(_row_get(row, "responsible_department"))
    if dept_label_func is not None:
        dept = safe_text(dept_label_func(dept_raw)) or dept_raw or "не указан"
    else:
        dept = dept_raw or "не указан"

    actor = (
        safe_text(_row_get(row, "updated_by"))
        or safe_text(_row_get(row, "owner_name"))
        or "не указано"
    )
    substance = constraint_block_substance(row)
    target = _format_target_date(_row_get(row, "target_resolution_date"))

    if status in ("HOLD", "FAIL"):
        return f"Заблокировано: {dept} — {actor} — {substance}. Срок: {target}"

    status_label = _CHECK_STATUS_LABELS.get(status, status or "—")
    return f"{status_label}: {dept} — {actor} — {substance}"


def constraint_decision_line_compact(
    row: Mapping[str, Any] | Any,
    dept_label_func: Callable[[Any], str] | None = None,
) -> str:
    """War Room registry format: dept — actor — substance. Срок: date."""
    dept_raw = safe_text(_row_get(row, "responsible_department"))
    if dept_label_func is not None:
        dept = safe_text(dept_label_func(dept_raw)) or dept_raw or "не указан"
    else:
        dept = dept_raw or "не указан"

    actor = (
        safe_text(_row_get(row, "updated_by"))
        or safe_text(_row_get(row, "owner_name"))
        or "не указано"
    )
    substance = constraint_block_substance(row)
    target = _format_target_date(_row_get(row, "target_resolution_date"))
    return f"{dept} — {actor} — {substance}. Срок: {target}"


def registry_specific_block_reason(row: Mapping[str, Any] | Any) -> str:
    """Non-generic block_reason only (short user-entered reason field)."""
    block = safe_text(_row_get(row, "block_reason"))
    if block and not is_generic_block_reason(block):
        return block
    return ""
