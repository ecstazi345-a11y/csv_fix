"""
Minimal row-level decision records for one Constructor run.

Observes the outcome the existing Constructor pipeline already assigned
to each mission-scope input row. Does not classify rows, does not create
candidates, and does not change CandidatePackage.
"""

from __future__ import annotations

import math
import numbers
from dataclasses import dataclass
from typing import Any, Optional, Sequence

import pandas as pd

OUTCOME_CANDIDATE = "CANDIDATE"
OUTCOME_UNCLASSIFIED = "UNCLASSIFIED"
REASON_UNKNOWN = "UNKNOWN"

CODE_ROW_DECISION_BLOCKER = "ROW_DECISION_BLOCKER"


class RowDecisionError(ValueError):
    """Fail closed when a scope row would disappear from the record set."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ConstructorRowDecisionRecord:
    """One existing Constructor outcome for one input row."""

    source_order: int
    source_identity: str
    boq_code: str
    boq_name: str
    unit: str
    system: Optional[str]
    project_code: str
    facility: str
    discipline: str
    month_key: str
    iwp: str
    remaining_qty: Optional[float]
    already_planned_qty: Optional[float]
    available_qty: Optional[float]
    outcome: str
    reason_code: str
    reason_text: str
    requires_human: Optional[bool]
    candidate_created: bool
    candidate_id: Optional[str] = None


def known_quantity(value: Any) -> Optional[float]:
    """Return a calculated number, or None when the pipeline did not produce one.

    A real zero stays zero. Missing, blank, and non-numeric values stay None.
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    if not isinstance(value, numbers.Real):
        return None
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def known_system(value: Any) -> Optional[str]:
    """Return a system label only when the source row actually has one."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>", "null"}:
        return None
    return text


def source_order_from_row(row: Any) -> int:
    raw = row.get("_source_order") if hasattr(row, "get") else None
    if isinstance(raw, bool) or raw is None:
        raise RowDecisionError(
            CODE_ROW_DECISION_BLOCKER,
            "scope row is missing its source order",
        )
    try:
        if pd.isna(raw):
            raise RowDecisionError(
                CODE_ROW_DECISION_BLOCKER,
                "scope row is missing its source order",
            )
    except RowDecisionError:
        raise
    except (TypeError, ValueError) as exc:
        raise RowDecisionError(
            CODE_ROW_DECISION_BLOCKER,
            "scope row source order is not an integer",
        ) from exc
    if isinstance(raw, numbers.Integral):
        order = int(raw)
    elif isinstance(raw, numbers.Real):
        number = float(raw)
        if not number.is_integer():
            raise RowDecisionError(
                CODE_ROW_DECISION_BLOCKER,
                "scope row source order is not an integer",
            )
        order = int(number)
    else:
        raise RowDecisionError(
            CODE_ROW_DECISION_BLOCKER,
            "scope row source order is not an integer",
        )
    if order < 0:
        raise RowDecisionError(
            CODE_ROW_DECISION_BLOCKER,
            "scope row source order is negative",
        )
    return order


def observe_scope_row(
    *,
    source_order: int,
    project_code: str,
    facility: str,
    discipline: str,
    month_key: str,
    system: Optional[str],
    iwp: str,
    boq_code: str,
    boq_name: str,
    unit: str,
    remaining_qty: Optional[float],
    already_planned_qty: Optional[float],
    available_qty: Optional[float],
    outcome: str,
    reason_code: str,
    reason_text: str,
    requires_human: Optional[bool],
    candidate_created: bool,
) -> ConstructorRowDecisionRecord:
    if isinstance(source_order, bool) or not isinstance(source_order, int) or source_order < 0:
        raise RowDecisionError(
            CODE_ROW_DECISION_BLOCKER,
            "scope row source order is not a non-negative integer",
        )
    if requires_human is not None and not isinstance(requires_human, bool):
        raise RowDecisionError(
            CODE_ROW_DECISION_BLOCKER,
            "requires_human must be true, false, or unknown",
        )
    if not isinstance(candidate_created, bool):
        raise RowDecisionError(
            CODE_ROW_DECISION_BLOCKER,
            "candidate_created must be true or false",
        )
    for label, quantity in (
        ("remaining_qty", remaining_qty),
        ("already_planned_qty", already_planned_qty),
        ("available_qty", available_qty),
    ):
        if quantity is not None and (
            isinstance(quantity, bool) or not isinstance(quantity, (int, float))
        ):
            raise RowDecisionError(
                CODE_ROW_DECISION_BLOCKER,
                f"{label} must be a calculated number or unknown",
            )
        if isinstance(quantity, float) and (math.isnan(quantity) or math.isinf(quantity)):
            raise RowDecisionError(
                CODE_ROW_DECISION_BLOCKER,
                f"{label} must be a calculated number or unknown",
            )
    identity = "|".join(
        (
            str(source_order),
            project_code,
            facility,
            discipline,
            boq_code,
        )
    )
    return ConstructorRowDecisionRecord(
        source_order=source_order,
        source_identity=identity,
        boq_code=boq_code,
        boq_name=boq_name,
        unit=unit,
        system=system,
        project_code=project_code,
        facility=facility,
        discipline=discipline,
        month_key=month_key,
        iwp=iwp,
        remaining_qty=None if remaining_qty is None else float(remaining_qty),
        already_planned_qty=(
            None if already_planned_qty is None else float(already_planned_qty)
        ),
        available_qty=None if available_qty is None else float(available_qty),
        outcome=outcome,
        reason_code=reason_code,
        reason_text=reason_text,
        requires_human=requires_human,
        candidate_created=candidate_created,
        candidate_id=None,
    )


def validate_row_decisions(
    records: Sequence[ConstructorRowDecisionRecord],
    *,
    scope_row_count: int,
) -> tuple[ConstructorRowDecisionRecord, ...]:
    """Require one record for every input row, in input order."""
    if isinstance(scope_row_count, bool) or not isinstance(scope_row_count, int):
        raise RowDecisionError(
            CODE_ROW_DECISION_BLOCKER,
            "scope row count is not an integer",
        )
    if scope_row_count < 0:
        raise RowDecisionError(
            CODE_ROW_DECISION_BLOCKER,
            "scope row count is negative",
        )
    ordered = tuple(sorted(records, key=lambda item: item.source_order))
    if len(ordered) != scope_row_count:
        raise RowDecisionError(
            CODE_ROW_DECISION_BLOCKER,
            f"scope rows {scope_row_count} != decision records {len(ordered)}",
        )
    orders = [item.source_order for item in ordered]
    if orders != list(range(scope_row_count)):
        raise RowDecisionError(
            CODE_ROW_DECISION_BLOCKER,
            "decision records do not cover every scope row exactly once",
        )
    return ordered
