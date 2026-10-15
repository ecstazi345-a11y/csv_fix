"""
Human Review Intent Interpreter V2 — text → structured draft intents.

Provider-neutral. Deterministic Russian grammar for V2 commands.
LLM is NOT a security boundary; execution always re-resolves via Focus Set.
Voice STT must feed the same textual command contract later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol, Sequence

from agents.human_surface.human_review_command import HumanReviewCommandError

CODE_INTENT_BLOCKER = "HUMAN_REVIEW_INTENT_BLOCKER"

_MONTH_TO_PERIOD = {
    "январ": "01",
    "феврал": "02",
    "март": "03",
    "апрел": "04",
    "ма": "05",  # май / мая
    "июн": "06",
    "июл": "07",
    "август": "08",
    "сентябр": "09",
    "октябр": "10",
    "ноябр": "11",
    "декабр": "12",
}


class ReviewIntentKind(str, Enum):
    ACCEPT = "ACCEPT"
    EXCLUDE = "EXCLUDE"
    CHANGE_QUANTITY = "CHANGE_QUANTITY"
    NEEDS_DATA = "NEEDS_DATA"
    DEFER_TO_PERIOD = "DEFER_TO_PERIOD"
    ACCEPT_REMAINDER = "ACCEPT_REMAINDER"


@dataclass(frozen=True)
class ReviewIntentTarget:
    """Unresolved target from text — resolved later against Focus Set."""

    alias_numbers: tuple[int, ...] = ()
    boq_code: Optional[str] = None
    remainder: bool = False


@dataclass(frozen=True)
class ReviewIntentOperation:
    kind: ReviewIntentKind
    target: ReviewIntentTarget
    approved_qty: Optional[float] = None
    target_period: Optional[str] = None
    reason_text: Optional[str] = None
    raw_clause: str = ""


@dataclass(frozen=True)
class ReviewIntentDraft:
    source_text: str
    operations: tuple[ReviewIntentOperation, ...]


class ReviewIntentInterpreter(Protocol):
    def interpret(
        self,
        text: str,
        *,
        default_year: int = 2026,
        context_period: Optional[str] = None,
    ) -> ReviewIntentDraft: ...


def _fail(message: str) -> None:
    raise HumanReviewCommandError(message, code=CODE_INTENT_BLOCKER)


def _is_alias_list_glue(between: str) -> bool:
    """True when text between two №N tokens is only list glue (», «и»), not a new clause."""
    folded = between.casefold().replace("ё", "е").strip()
    if not folded:
        return True
    return bool(re.fullmatch(r"[,;/]|и|да|,?\s*и", folded))


def _split_on_number_headers(fragment: str) -> list[str]:
    """
    SEGMENTATION LAW: each explicit №N starts a new command clause,
    unless №N continues a multi-target list (№1, №2 / №1 и №2).
    Action / qty / period / reason must not leak across №N headers.
    """
    text = fragment.strip()
    if not text:
        return []
    matches = list(re.finditer(r"№\s*\d+", text, flags=re.IGNORECASE))
    if len(matches) <= 1:
        return [text]
    cuts = [matches[0].start()]
    for index in range(1, len(matches)):
        between = text[matches[index - 1].end() : matches[index].start()]
        if _is_alias_list_glue(between):
            continue
        cuts.append(matches[index].start())
    segments: list[str] = []
    prefix = text[: cuts[0]].strip(" \t\r\n;,-")
    if prefix:
        # Leading reason/noise without № — keep only if no later № segments (rare).
        segments.append(prefix)
    for index, start in enumerate(cuts):
        end = cuts[index + 1] if index + 1 < len(cuts) else len(text)
        part = text[start:end].strip(" \t\r\n;,-")
        if part:
            segments.append(part)
    return segments or [text]


def _split_clauses(text: str) -> list[str]:
    normalized = str(text or "").strip()
    if not normalized:
        _fail("command text is required")
    # 1) Split on newlines / sentence boundaries.
    parts = re.split(r"(?:\n+|(?<=[.!?])\s+(?=[А-ЯA-Z0-9«\"№]))", normalized)
    # 2) Inside each part, segment on explicit №N headers (independent clauses).
    clauses: list[str] = []
    for part in parts:
        chunk = part.strip(" \t\r\n;,-")
        if not chunk:
            continue
        clauses.extend(_split_on_number_headers(chunk))
    return clauses or [normalized]


def _parse_alias_numbers(fragment: str) -> tuple[int, ...]:
    text = fragment.casefold()
    # «позиции с 15 по 18»
    range_match = re.search(
        r"(?:позици\w*|№)\s*с\s*(\d+)\s*по\s*(\d+)",
        text,
        flags=re.IGNORECASE,
    )
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2))
        if end < start:
            _fail(f"invalid row range {start}-{end}")
        return tuple(range(start, end + 1))
    # «позиции 9, 11 и 12» / «позицию 4»
    nums = [int(n) for n in re.findall(r"\d+", fragment)]
    # Prefer numbers that appear near позиция/№ tokens.
    if re.search(r"позици|№", text, flags=re.IGNORECASE):
        near = re.findall(
            r"(?:позици\w*|№)\s*(\d+(?:\s*[,и]\s*\d+)*)",
            fragment,
            flags=re.IGNORECASE,
        )
        collected: list[int] = []
        for block in near:
            collected.extend(int(n) for n in re.findall(r"\d+", block))
        if collected:
            return tuple(dict.fromkeys(collected))
    return tuple(dict.fromkeys(nums))


def _parse_boq(fragment: str) -> Optional[str]:
    match = re.search(
        r"(?:код|boq)\s*[:=]?\s*([0-9]{3,4}(?:-[0-9]{2}){2,4})",
        fragment,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    match = re.search(r"\b([0-9]{4}(?:-[0-9]{2}){2,3})\b", fragment)
    if match and not re.search(r"позици|№", fragment, flags=re.IGNORECASE):
        return match.group(1).strip()
    return None


def _parse_qty(fragment: str) -> Optional[float]:
    """Parse approved quantity; never treat row aliases or BOQ digits as qty."""
    patterns = (
        r"объ[её]м\s*[:=]?\s*(\d+(?:[.,]\d+)?)",
        r"(?:принять|утверждаю)\s+(\d+(?:[.,]\d+)?)\s*(?:м|метр\w*)?",
        r"(?<![\d-])(\d+(?:[.,]\d+)?)\s*(?:м|метр\w*)\b",
        r"(?:qty|quantity)\s*[:=]?\s*(\d+(?:[.,]\d+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, fragment, flags=re.IGNORECASE)
        if match:
            return float(match.group(1).replace(",", "."))
    return None


def _resolve_yearless_month(
    month: str,
    *,
    default_year: int,
    context_period: Optional[str],
) -> str:
    """
    When year is omitted: next occurrence of that month relative to context,
    if unambiguous. Same calendar month without year is ambiguous.
    """
    ctx = re.fullmatch(r"(20\d{2})-(\d{2})", str(context_period or "").strip())
    if ctx is None:
        return f"{default_year}-{month}"
    context_year = int(ctx.group(1))
    context_month = int(ctx.group(2))
    target_month = int(month)
    if target_month > context_month:
        return f"{context_year}-{month}"
    if target_month < context_month:
        return f"{context_year + 1}-{month}"
    _fail(
        f"ambiguous target period for month {month}: specify year "
        f"(current context is {context_period})"
    )


def _parse_period(
    fragment: str,
    *,
    default_year: int,
    context_period: Optional[str] = None,
) -> Optional[str]:
    """Parse target period. Supports «ноябрь», «ноябрь 2026», «ноябрь-2026»."""
    text = fragment.casefold().replace("ё", "е")
    iso = re.search(r"(20\d{2})-(\d{2})\b", text)
    if iso:
        return f"{iso.group(1)}-{iso.group(2)}"
    # «ноябрь-2026» / «ноябрь 2026» — month name bound to an explicit year.
    for stem, month in _MONTH_TO_PERIOD.items():
        if stem == "ма" and not re.search(r"\bма[йяе]\b", text):
            continue
        named = re.search(
            rf"{stem}\w*\s*[-\s]\s*(20\d{{2}})\b",
            text,
            flags=re.IGNORECASE,
        )
        if named:
            return f"{named.group(1)}-{month}"
    year_match = re.search(r"(20\d{2})", text)
    if year_match:
        year = int(year_match.group(1))
        for stem, month in _MONTH_TO_PERIOD.items():
            if stem in text:
                if stem == "ма" and not re.search(r"\bма[йяе]\b", text):
                    continue
                return f"{year}-{month}"
        return None
    for stem, month in _MONTH_TO_PERIOD.items():
        if stem in text:
            # Avoid matching «мая» inside unrelated words poorly — stems are short.
            if stem == "ма" and not re.search(r"\bма[йяе]\b", text):
                continue
            return _resolve_yearless_month(
                month,
                default_year=default_year,
                context_period=context_period,
            )
    return None


def _extract_reason(clause: str, *, drop_prefixes: Sequence[str]) -> Optional[str]:
    text = clause.strip()
    for prefix in drop_prefixes:
        text = re.sub(prefix, "", text, flags=re.IGNORECASE).strip(" \t\r\n.;,—-")
    # After removing the action head, leftover is reason.
    text = re.sub(
        r"^(?:позици\w*|№|код|boq)[^.]*?[.!]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" \t\r\n.;,—-")
    return text or None


def _is_accept_remainder(clause: str) -> bool:
    """ACCEPT ALL / ACCEPT REMAINDER for the current Work-Context candidate set."""
    text = clause.casefold().replace("ё", "е").strip()
    # Mixed clause with a targeted exception is not a pure remainder/all command.
    if re.search(r"(?:позици\w*|№)\s*\d", text) and re.search(
        r"исключ|перенес|отлож|нужн\w*\s+данн|объ[её]м",
        text,
    ):
        return False
    patterns = (
        r"остальн\w*\s+(?:принят|добав)",
        r"(?:принят|добав)\w*\s+остальн",
        r"все\s+остальн\w*\s+(?:кандидат\w*\s+)?(?:принят|добав)",
        r"все\s+кандидат\w*\s+по\s+текущему\s+срез\w*\s+(?:принят|добав)",
        r"все\s+кандидат\w*\s+(?:принят|добав)",
        r"(?:добавить|принять)\s+все",
        r"все\s+(?:добавить|принять|ок)\b",
        r"^все\s+ок\b",
        r"^все\s+ок[.!]?\s*$",
        r"^добавить\s+все\b",
        r"^принять\s+все\b",
        r"^все\s+добавить\b",
        r"^все\s+принять\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _looks_like_new_action(clause: str) -> bool:
    """True when clause starts a new decision, not a reason continuation."""
    folded = clause.casefold()
    if _is_accept_remainder(clause):
        return True
    if re.search(r"(?:позици\w*|№)\s*\d", folded):
        return True
    if re.search(r"(?:код|boq)\s*[:=]?\s*\d", folded):
        return True
    if re.search(r"\b\d{4}(?:-\d{2}){2,3}\b", folded) and re.search(
        r"принят|объ[её]м|исключ|перенес|нужн",
        folded,
    ):
        return True
    return False


def _classify_clause(
    clause: str,
    *,
    default_year: int,
    context_period: Optional[str] = None,
) -> ReviewIntentOperation:
    text = clause.strip()
    folded = text.casefold()

    if _is_accept_remainder(text):
        return ReviewIntentOperation(
            kind=ReviewIntentKind.ACCEPT_REMAINDER,
            target=ReviewIntentTarget(remainder=True),
            reason_text=None,
            raw_clause=text,
        )

    boq = _parse_boq(text)
    aliases = () if boq else _parse_alias_numbers(text)
    target = ReviewIntentTarget(alias_numbers=aliases, boq_code=boq)

    if re.search(r"перенес|отлож", folded):
        period = _parse_period(
            text,
            default_year=default_year,
            context_period=context_period,
        )
        if period is None:
            _fail("defer command requires target period (e.g. ноябрь)")
        reason = _extract_reason(
            text,
            drop_prefixes=(
                r".{0,80}?перенес\w*\s+(?:на|в)\s+\S+(?:[-\s]*20\d{2})?",
                r".{0,80}?отлож\w*\s+(?:на|в)\s+\S+(?:[-\s]*20\d{2})?",
            ),
        )
        return ReviewIntentOperation(
            kind=ReviewIntentKind.DEFER_TO_PERIOD,
            target=target,
            target_period=period,
            reason_text=reason,
            raw_clause=text,
        )

    if re.search(r"исключ|убрал|убрать", folded):
        reason = _extract_reason(
            text,
            drop_prefixes=(r".{0,80}?исключ\w*", r".{0,80}?убрал\w*", r".{0,80}?убрать"),
        )
        return ReviewIntentOperation(
            kind=ReviewIntentKind.EXCLUDE,
            target=target,
            reason_text=reason,
            raw_clause=text,
        )

    if re.search(r"нужн\w*\s+данн|требует\w*\s+уточн|clarif", folded):
        reason = _extract_reason(
            text,
            drop_prefixes=(r".{0,80}?нужн\w*\s+данн\w*", r".{0,80}?требует\w*\s+уточн\w*"),
        )
        return ReviewIntentOperation(
            kind=ReviewIntentKind.NEEDS_DATA,
            target=target,
            reason_text=reason,
            raw_clause=text,
        )

    qty = _parse_qty(text)
    change_qty_intent = bool(
        re.search(
            r"скорректир|корректир|измен\w*\s+(?:объ|количеств)|"
            r"ошибк\w*\s+объ|объ[её]м\s*[:=]?\s*\d|"
            r"(?:принять|утверждаю)\s+\d",
            folded,
        )
        or (
            qty is not None
            and re.search(r"объ[её]м|метр|принять\s+\d|утвержд", folded)
        )
    )
    if change_qty_intent:
        # Incomplete OK at parse/preview: approved_qty may be MISSING.
        reason = _extract_reason(
            text,
            drop_prefixes=(
                r".{0,100}?(?:скорректир\w*|корректир\w*|измен\w*)\s*(?:объ[её]м\w*|количеств\w*)?",
                r".{0,100}?(?:объ[её]м|принять|утверждаю)\s*\d+(?:[.,]\d+)?\s*(?:м|метр\w*)?",
            ),
        )
        return ReviewIntentOperation(
            kind=ReviewIntentKind.CHANGE_QUANTITY,
            target=target,
            approved_qty=qty,
            reason_text=reason,
            raw_clause=text,
        )

    if re.search(r"принят", folded):
        return ReviewIntentOperation(
            kind=ReviewIntentKind.ACCEPT,
            target=target,
            reason_text=_extract_reason(text, drop_prefixes=(r".{0,80}?принят\w*",)),
            raw_clause=text,
        )

    _fail(f"unsupported review command clause: {text!r}")


class DeterministicRussianReviewIntentInterpreter:
    """Minimum deterministic Russian grammar for Human Review V2 commands."""

    def interpret(
        self,
        text: str,
        *,
        default_year: int = 2026,
        context_period: Optional[str] = None,
    ) -> ReviewIntentDraft:
        clauses = _split_clauses(text)
        operations: list[ReviewIntentOperation] = []
        pending_reason: list[str] = []
        for clause in clauses:
            # Pure reason continuation after an action clause.
            if operations and not _looks_like_new_action(clause):
                prev = operations[-1]
                merged_reason = " ".join(
                    part for part in (prev.reason_text, clause) if part
                ).strip()
                operations[-1] = ReviewIntentOperation(
                    kind=prev.kind,
                    target=prev.target,
                    approved_qty=prev.approved_qty,
                    target_period=prev.target_period,
                    reason_text=merged_reason or None,
                    raw_clause=f"{prev.raw_clause} {clause}".strip(),
                )
                continue
            op = _classify_clause(
                clause,
                default_year=default_year,
                context_period=context_period,
            )
            if pending_reason and op.reason_text is None:
                op = ReviewIntentOperation(
                    kind=op.kind,
                    target=op.target,
                    approved_qty=op.approved_qty,
                    target_period=op.target_period,
                    reason_text=" ".join(pending_reason),
                    raw_clause=op.raw_clause,
                )
                pending_reason = []
            operations.append(op)
        if not operations:
            _fail("no review operations recognized")
        return ReviewIntentDraft(source_text=str(text or "").strip(), operations=tuple(operations))


def default_review_intent_interpreter() -> ReviewIntentInterpreter:
    return DeterministicRussianReviewIntentInterpreter()
