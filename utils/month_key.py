"""
Canonical month_key helper for Execution OS (R1.2+).

Storage preference for new tables: YYYY-MM (e.g. 2026-07).
Does NOT migrate legacy plan / DP / passport month keys.
"""

from __future__ import annotations

from typing import Optional

_RU_MONTH_TO_NUM: dict[str, int] = {
    "январь": 1,
    "февраль": 2,
    "март": 3,
    "апрель": 4,
    "май": 5,
    "июнь": 6,
    "июль": 7,
    "август": 8,
    "сентябрь": 9,
    "октябрь": 10,
    "ноябрь": 11,
    "декабрь": 12,
}

_EN_MONTH_TO_NUM: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def normalize_month_key(value: object) -> Optional[str]:
    """
    Normalize month labels to canonical YYYY-MM.

    Supported:
      июль-2026, July-2026, 2026-07 → 2026-07
    Invalid / empty → None
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "все", "все месяца"}:
        return None

    # Already canonical: YYYY-MM
    if len(text) == 7 and text[4] == "-":
        year_part, month_part = text[:4], text[5:]
        if year_part.isdigit() and month_part.isdigit():
            month_num = int(month_part)
            year_num = int(year_part)
            if 1 <= month_num <= 12 and 1900 <= year_num <= 2100:
                return f"{year_num:04d}-{month_num:02d}"

    # Name-Year: июль-2026 / July-2026
    if "-" not in text:
        return None
    name_part, year_part = text.rsplit("-", 1)
    name_part = name_part.strip()
    year_part = year_part.strip()
    if not year_part.isdigit():
        return None
    year_num = int(year_part)
    if year_num < 1900 or year_num > 2100:
        return None

    name_lower = name_part.casefold()
    month_num = _RU_MONTH_TO_NUM.get(name_lower) or _EN_MONTH_TO_NUM.get(name_lower)
    if not month_num:
        return None
    return f"{year_num:04d}-{month_num:02d}"


def format_month_key_ru(canonical: object) -> Optional[str]:
    """Format YYYY-MM as Russian display label (июль-2026). None if invalid."""
    normalized = normalize_month_key(canonical)
    if not normalized:
        return None
    year = int(normalized[:4])
    month = int(normalized[5:7])
    ru_names = (
        "январь",
        "февраль",
        "март",
        "апрель",
        "май",
        "июнь",
        "июль",
        "август",
        "сентябрь",
        "октябрь",
        "ноябрь",
        "декабрь",
    )
    return f"{ru_names[month - 1]}-{year}"
