"""
Constructor Runtime v0.1 Increment 1 — mission scope contract + binder.

Security/business boundary, not a UI filter.
Fail closed. No scope expansion. project_code + month_key are mandatory.
Pure: no Streamlit, Supabase, HTTP, filesystem, LLM, shell, or writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Union

import pandas as pd

from utils.month_key import normalize_month_key

CODE_DATA_CONTRACT_BLOCKER = "DATA_CONTRACT_BLOCKER"
CODE_AMBIGUOUS_SCOPE = "AMBIGUOUS_SCOPE"

_ALL_TOKEN = "all"

# Proven grain rule (same as domain._norm_key_part): strip + uppercase. No fuzzy match.
_EMPTY_TOKENS = frozenset({"", "nan", "none", "<na>"})
_FORBIDDEN_PROJECT_TOKENS = frozenset({"все", "all", "nan", "none"})

# Product column aliases for one business dimension. Order matches MPCA grain helpers.
_DIMENSION_COLUMNS: dict[str, tuple[str, ...]] = {
    "facility_scope": ("facility_building", "facility"),
    "discipline_scope": ("construction_discipline", "discipline"),
    "system_scope": ("system_label", "system"),
    "iwp_scope": ("iwp_id", "iwp"),
    "queue_scope": ("construction_queue", "queue"),
}

ScopeValue = Union[str, Sequence[str], None]


class MissionScopeError(ValueError):
    """Fail-closed mission/scope contract violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ConstructorMissionScope:
    """Normalized mission slice. Optional None = ALL inside this project+month only."""

    project_code: str
    month_key: str
    month_key_canonical: str
    facility_scope: Optional[tuple[str, ...]]
    discipline_scope: Optional[tuple[str, ...]]
    system_scope: Optional[tuple[str, ...]]
    iwp_scope: Optional[tuple[str, ...]]
    queue_scope: Optional[tuple[str, ...]]


# Spec alias: same business object as MonthlyPlanningScope.
MonthlyPlanningScope = ConstructorMissionScope


def _norm_key_part(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in _EMPTY_TOKENS:
        return ""
    return text.upper()


def _normalize_optional_scope(field_name: str, value: ScopeValue) -> Optional[tuple[str, ...]]:
    if value is None:
        return None
    if isinstance(value, str):
        items: list[str] = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        raise MissionScopeError(
            CODE_DATA_CONTRACT_BLOCKER,
            f"{field_name} must be str, list, tuple, or None",
        )

    cleaned: list[str] = []
    saw_all = False
    for item in items:
        if item is None:
            continue
        if isinstance(item, float) and pd.isna(item):
            continue
        text = str(item).strip()
        if text.lower() in _EMPTY_TOKENS:
            continue
        if text.casefold() == _ALL_TOKEN:
            saw_all = True
            continue
        cleaned.append(_norm_key_part(text))

    if saw_all and cleaned:
        raise MissionScopeError(
            CODE_AMBIGUOUS_SCOPE,
            f"{field_name} mixes ALL with specific values",
        )
    if saw_all or not cleaned:
        return None

    unique: list[str] = []
    seen: set[str] = set()
    for part in cleaned:
        if part in seen:
            continue
        seen.add(part)
        unique.append(part)
    return tuple(unique)


def build_constructor_mission_scope(
    *,
    project_code: Any,
    month_key: Any,
    facility_scope: ScopeValue = None,
    discipline_scope: ScopeValue = None,
    system_scope: ScopeValue = None,
    iwp_scope: ScopeValue = None,
    queue_scope: ScopeValue = None,
) -> ConstructorMissionScope:
    """Build an immutable mission scope. Invalid project/month fail closed."""
    project = _norm_key_part(project_code)
    if not project or project.casefold() in _FORBIDDEN_PROJECT_TOKENS:
        raise MissionScopeError(
            CODE_DATA_CONTRACT_BLOCKER,
            "project_code is required and must be a specific project",
        )

    stored_month = "" if month_key is None else str(month_key).strip()
    canonical = normalize_month_key(month_key)
    if not stored_month or canonical is None:
        raise MissionScopeError(
            CODE_DATA_CONTRACT_BLOCKER,
            "month_key is required and must be a known stored/canonical month",
        )

    return ConstructorMissionScope(
        project_code=project,
        month_key=stored_month,
        month_key_canonical=canonical,
        facility_scope=_normalize_optional_scope("facility_scope", facility_scope),
        discipline_scope=_normalize_optional_scope("discipline_scope", discipline_scope),
        system_scope=_normalize_optional_scope("system_scope", system_scope),
        iwp_scope=_normalize_optional_scope("iwp_scope", iwp_scope),
        queue_scope=_normalize_optional_scope("queue_scope", queue_scope),
    )


def _require_columns(df: pd.DataFrame, names: Sequence[str], code: str, reason: str) -> None:
    missing = [name for name in names if name not in df.columns]
    if missing:
        raise MissionScopeError(code, f"{reason}: missing columns {missing}")


def _present_aliases(df: pd.DataFrame, aliases: Sequence[str]) -> list[str]:
    return [name for name in aliases if name in df.columns]


def _resolved_dimension_series(df: pd.DataFrame, aliases: Sequence[str]) -> pd.Series:
    present = _present_aliases(df, aliases)
    resolved = pd.Series([""] * len(df), index=df.index, dtype=object)
    for column in present:
        candidate = df[column].map(_norm_key_part)
        resolved = resolved.where(resolved.astype(str) != "", candidate)
    return resolved.map(_norm_key_part)


def _row_belongs_to_mission(
    row: Mapping[str, Any],
    scope: ConstructorMissionScope,
    *,
    require_optional_columns: bool,
) -> bool:
    if "project_code" not in row:
        return False
    if "month_key" not in row:
        return False
    if _norm_key_part(row.get("project_code")) != scope.project_code:
        return False
    row_month = normalize_month_key(row.get("month_key"))
    if row_month != scope.month_key_canonical:
        return False

    for field_name, aliases in _DIMENSION_COLUMNS.items():
        requested: Optional[tuple[str, ...]] = getattr(scope, field_name)
        if requested is None:
            continue
        present = [name for name in aliases if name in row]
        if require_optional_columns and not present:
            raise MissionScopeError(
                CODE_AMBIGUOUS_SCOPE,
                f"{field_name} is set but none of {list(aliases)} are present",
            )
        if not present:
            return False
        resolved = ""
        for name in aliases:
            if name not in row:
                continue
            resolved = _norm_key_part(row.get(name))
            if resolved:
                break
        if resolved not in requested:
            return False
    return True


def assert_rows_belong_to_mission_scope(
    rows: pd.DataFrame,
    scope: ConstructorMissionScope,
) -> None:
    """Post-bind invariant: every row is inside the mission. Fail closed otherwise."""
    if not isinstance(rows, pd.DataFrame):
        raise MissionScopeError(CODE_DATA_CONTRACT_BLOCKER, "rows must be a DataFrame")
    _require_columns(
        rows,
        ("project_code", "month_key"),
        CODE_DATA_CONTRACT_BLOCKER,
        "cannot prove project/month membership",
    )
    for field_name, aliases in _DIMENSION_COLUMNS.items():
        requested = getattr(scope, field_name)
        if requested is None:
            continue
        if not _present_aliases(rows, aliases):
            raise MissionScopeError(
                CODE_AMBIGUOUS_SCOPE,
                f"{field_name} is set but none of {list(aliases)} are present",
            )

    if rows.empty:
        return

    records = rows.to_dict(orient="records")
    for record in records:
        if not _row_belongs_to_mission(record, scope, require_optional_columns=True):
            raise MissionScopeError(
                CODE_DATA_CONTRACT_BLOCKER,
                "post-bind assertion failed: row is outside mission scope",
            )


def bind_scope_to_mission(
    rows: pd.DataFrame,
    scope: ConstructorMissionScope,
) -> pd.DataFrame:
    """
    Return only rows that belong to the mission.

    Input scope may stay the same or narrow. It never expands.
    Unknown requested values yield an empty in-scope frame, not a wider fallback.
    Missing requested dimension columns fail closed.
    Does not mutate ``rows``.
    """
    if not isinstance(scope, ConstructorMissionScope):
        raise MissionScopeError(
            CODE_DATA_CONTRACT_BLOCKER,
            "scope must be ConstructorMissionScope",
        )
    if not isinstance(rows, pd.DataFrame):
        raise MissionScopeError(CODE_DATA_CONTRACT_BLOCKER, "rows must be a DataFrame")

    _require_columns(
        rows,
        ("project_code", "month_key"),
        CODE_DATA_CONTRACT_BLOCKER,
        "cannot prove project/month membership",
    )
    for field_name, aliases in _DIMENSION_COLUMNS.items():
        requested = getattr(scope, field_name)
        if requested is None:
            continue
        if not _present_aliases(rows, aliases):
            raise MissionScopeError(
                CODE_AMBIGUOUS_SCOPE,
                f"{field_name} is set but none of {list(aliases)} are present",
            )

    work = rows.copy()
    project_ok = work["project_code"].map(_norm_key_part) == scope.project_code
    month_ok = work["month_key"].map(normalize_month_key) == scope.month_key_canonical
    mask = project_ok & month_ok

    for field_name, aliases in _DIMENSION_COLUMNS.items():
        requested = getattr(scope, field_name)
        if requested is None:
            continue
        allowed = set(requested)
        resolved = _resolved_dimension_series(work, aliases)
        mask = mask & resolved.isin(allowed)

    scoped = work.loc[mask].copy()
    scoped.reset_index(drop=True, inplace=True)
    assert_rows_belong_to_mission_scope(scoped, scope)
    return scoped


bind_rows_to_mission_scope = bind_scope_to_mission
