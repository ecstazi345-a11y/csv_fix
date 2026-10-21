"""
Human Review Focus Set V2 — temporary professional decision context.

Visible № aliases are interaction-only. Durable events always store
authoritative candidate_id / package_id / run_id.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from agents.human_surface.human_review_command import (
    HumanReviewCandidateContext,
    HumanReviewCommandError,
    HumanReviewSurfaceSnapshot,
)
from agents.human_surface.mission_draft import WorkingContext
from agents.monthly_plan_constructor.candidate_package import CandidatePackage

CODE_FOCUS_SET_BLOCKER = "HUMAN_REVIEW_FOCUS_SET_BLOCKER"
_ALL = "Все"


@dataclass(frozen=True)
class HumanReviewFocusFilter:
    facility: Optional[str] = None
    discipline: Optional[str] = None
    system: Optional[str] = None
    iwp: Optional[str] = None


@dataclass(frozen=True)
class HumanReviewFocusSet:
    """Temporary decision context bound to package + checkpoint + filter hash."""

    focus_set_id: str
    run_id: str
    package_id: str
    expected_checkpoint_id: str
    filter_scope: HumanReviewFocusFilter
    ordered_candidate_ids: tuple[str, ...]
    created_at: datetime
    focus_hash: str

    @property
    def size(self) -> int:
        return len(self.ordered_candidate_ids)


@dataclass(frozen=True)
class HumanReviewFocusRow:
    alias_number: int
    candidate_id: str
    facility: str
    discipline: str
    system: str
    iwp: str
    boq_code: str
    name: str
    unit: str
    constructor_proposed_qty: float
    current_decision_label: str
    warning_lines: tuple[str, ...]


def _norm_filter(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    if not text or text == _ALL:
        return None
    return text


def _scope_dict(scope: HumanReviewFocusFilter) -> dict[str, Optional[str]]:
    return {
        "facility": _norm_filter(scope.facility),
        "discipline": _norm_filter(scope.discipline),
        "system": _norm_filter(scope.system),
        "iwp": _norm_filter(scope.iwp),
    }


def compute_focus_hash(
    *,
    run_id: str,
    package_id: str,
    expected_checkpoint_id: str,
    filter_scope: HumanReviewFocusFilter,
    ordered_candidate_ids: Sequence[str],
) -> str:
    payload = {
        "run_id": run_id,
        "package_id": package_id,
        "expected_checkpoint_id": expected_checkpoint_id,
        "filter_scope": _scope_dict(filter_scope),
        "ordered_candidate_ids": list(ordered_candidate_ids),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def focus_filter_options(
    candidates: Sequence[HumanReviewCandidateContext],
) -> dict[str, tuple[str, ...]]:
    """Distinct values present in the current package surface (cascading callers apply)."""

    def uniq(attr: str) -> tuple[str, ...]:
        values = sorted(
            {
                str(getattr(item, attr) or "").strip()
                for item in candidates
                if str(getattr(item, attr) or "").strip()
            }
        )
        return tuple(values)

    return {
        "facility": uniq("facility"),
        "discipline": uniq("discipline"),
        "system": uniq("system"),
        "iwp": uniq("iwp"),
    }


def cascade_focus_options(
    candidates: Sequence[HumanReviewCandidateContext],
    scope: HumanReviewFocusFilter,
) -> dict[str, tuple[str, ...]]:
    """Options narrowed by already selected higher-level dimensions."""
    facility = _norm_filter(scope.facility)
    discipline = _norm_filter(scope.discipline)
    system = _norm_filter(scope.system)

    def keep(item: HumanReviewCandidateContext) -> bool:
        if facility and str(item.facility or "").strip() != facility:
            return False
        if discipline and str(item.discipline or "").strip() != discipline:
            return False
        if system and str(item.system or "").strip() != system:
            return False
        return True

    narrowed = tuple(item for item in candidates if keep(item))
    return focus_filter_options(narrowed)


def _multi_filter_values(raw: Optional[str]) -> Optional[frozenset[str]]:
    text = _norm_filter(raw)
    if text is None:
        return None
    parts = frozenset(part.strip() for part in text.split("|") if part.strip())
    return parts or None


def filter_candidates(
    candidates: Sequence[HumanReviewCandidateContext],
    scope: HumanReviewFocusFilter,
) -> tuple[HumanReviewCandidateContext, ...]:
    facilities = _multi_filter_values(scope.facility)
    discipline = _norm_filter(scope.discipline)
    systems = _multi_filter_values(scope.system)
    iwps = _multi_filter_values(scope.iwp)
    kept: list[HumanReviewCandidateContext] = []
    for item in candidates:
        if facilities and str(item.facility or "").strip() not in facilities:
            continue
        if discipline and str(item.discipline or "").strip() != discipline:
            continue
        if systems and str(item.system or "").strip() not in systems:
            continue
        if iwps and str(item.iwp or "").strip() not in iwps:
            continue
        kept.append(item)
    return tuple(kept)


def filter_candidates_by_work_context(
    candidates: Sequence[HumanReviewCandidateContext],
    context: Optional[WorkingContext],
) -> tuple[HumanReviewCandidateContext, ...]:
    """Scope Human Review candidates to applied Work Context (no second UI filter)."""
    if context is None:
        return tuple(candidates)
    titles = tuple(str(item).strip() for item in (context.titles or ()) if str(item).strip())
    discipline = _norm_filter(context.discipline)
    if discipline and discipline.casefold() in {"все дисциплины", "все", "all"}:
        discipline = None
    systems = tuple(str(item).strip() for item in (context.systems or ()) if str(item).strip())
    packages_raw = str(context.packages or "").strip()
    packages: tuple[str, ...] = ()
    if packages_raw and packages_raw.casefold() not in {"все", "все пакеты", "all"}:
        packages = tuple(
            part.strip()
            for part in packages_raw.replace(";", ",").split(",")
            if part.strip()
        )
    kept: list[HumanReviewCandidateContext] = []
    for item in candidates:
        if titles and str(item.facility or "").strip() not in titles:
            continue
        if discipline and str(item.discipline or "").strip() != discipline:
            continue
        if systems and str(item.system or "").strip() not in systems:
            continue
        if packages and str(item.iwp or "").strip() not in packages:
            continue
        kept.append(item)
    return tuple(kept)


def work_context_to_focus_filter(
    context: Optional[WorkingContext],
) -> HumanReviewFocusFilter:
    """Encode applied Work Context into FocusFilter (multi-values via '|')."""
    if context is None:
        return HumanReviewFocusFilter()
    titles = tuple(str(item).strip() for item in (context.titles or ()) if str(item).strip())
    discipline = _norm_filter(context.discipline)
    if discipline and discipline.casefold() in {"все дисциплины", "все", "all"}:
        discipline = None
    systems = tuple(str(item).strip() for item in (context.systems or ()) if str(item).strip())
    packages_raw = str(context.packages or "").strip()
    packages: tuple[str, ...] = ()
    if packages_raw and packages_raw.casefold() not in {"все", "все пакеты", "all"}:
        packages = tuple(
            part.strip()
            for part in packages_raw.replace(";", ",").split(",")
            if part.strip()
        )
    return HumanReviewFocusFilter(
        facility="|".join(titles) if titles else None,
        discipline=discipline,
        system="|".join(systems) if systems else None,
        iwp="|".join(packages) if packages else None,
    )


def build_focus_set_from_work_context(
    surface: HumanReviewSurfaceSnapshot,
    context: Optional[WorkingContext],
    *,
    focus_set_id: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> HumanReviewFocusSet:
    """
    Auto Focus Set bound to Work Context + package + checkpoint.

    Visible № aliases resolve only through this temporary set.
    Round-trips through validate_focus_set_against_surface via filter_scope.
    """
    scope = work_context_to_focus_filter(context)
    return build_human_review_focus_set(
        surface,
        scope,
        focus_set_id=focus_set_id,
        created_at=created_at,
    )


def durable_approved_composition_rows(
    surface: HumanReviewSurfaceSnapshot,
) -> tuple[dict[str, str], ...]:
    """Main Human Decision table: accepted / quantity-adjusted only."""
    rows: list[dict[str, str]] = []
    for item in surface.candidates:
        label = item.current_decision_label
        if label not in {"ПРИНЯТО", "ИЗМЕНЁН ОБЪЁМ"}:
            continue
        approved = item.human_approved_qty
        rows.append(
            {
                "Титул": item.facility or "—",
                "Дисциплина": item.discipline or "—",
                "Система": item.system or "—",
                "Пакет/IWP": item.iwp or "—",
                "BOQ": item.boq_code or "—",
                "Наименование работы": item.name or "—",
                "Ед. изм.": item.unit or "—",
                "Предложение Constructor": f"{item.constructor_proposed_qty:g}",
                "Объём человека": (
                    f"{approved:g}" if approved is not None else f"{item.constructor_proposed_qty:g}"
                ),
                "Статус решения": "СКОРРЕКТИРОВАНО" if label == "ИЗМЕНЁН ОБЪЁМ" else "ПРИНЯТО",
            }
        )
    return tuple(rows)


def durable_exception_detail_rows(
    surface: HumanReviewSurfaceSnapshot,
    *,
    labels: Sequence[str],
) -> tuple[dict[str, str], ...]:
    allowed = {str(item) for item in labels}
    rows: list[dict[str, str]] = []
    for item in surface.candidates:
        if item.current_decision_label not in allowed:
            continue
        rows.append(
            {
                "Титул": item.facility or "—",
                "Дисциплина": item.discipline or "—",
                "BOQ": item.boq_code or "—",
                "Наименование": item.name or "—",
                "Статус": item.current_decision_label,
                "Причина": item.reason_text or "—",
            }
        )
    return tuple(rows)


def build_human_review_focus_set(
    surface: HumanReviewSurfaceSnapshot,
    filter_scope: HumanReviewFocusFilter,
    *,
    focus_set_id: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> HumanReviewFocusSet:
    stamp = created_at or datetime.now(timezone.utc)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise HumanReviewCommandError("created_at must be timezone-aware UTC")
    stamp = stamp.astimezone(timezone.utc)
    filtered = filter_candidates(surface.candidates, filter_scope)
    ordered = tuple(item.candidate_id for item in filtered)
    scope = HumanReviewFocusFilter(
        facility=_norm_filter(filter_scope.facility),
        discipline=_norm_filter(filter_scope.discipline),
        system=_norm_filter(filter_scope.system),
        iwp=_norm_filter(filter_scope.iwp),
    )
    focus_hash = compute_focus_hash(
        run_id=surface.run_id,
        package_id=surface.package_id,
        expected_checkpoint_id=surface.expected_checkpoint_id,
        filter_scope=scope,
        ordered_candidate_ids=ordered,
    )
    return HumanReviewFocusSet(
        focus_set_id=focus_set_id or f"fs-{uuid.uuid4().hex[:16]}",
        run_id=surface.run_id,
        package_id=surface.package_id,
        expected_checkpoint_id=surface.expected_checkpoint_id,
        filter_scope=scope,
        ordered_candidate_ids=ordered,
        created_at=stamp,
        focus_hash=focus_hash,
    )


def focus_rows(
    surface: HumanReviewSurfaceSnapshot,
    focus: HumanReviewFocusSet,
) -> tuple[HumanReviewFocusRow, ...]:
    by_id = {item.candidate_id: item for item in surface.candidates}
    rows: list[HumanReviewFocusRow] = []
    for index, candidate_id in enumerate(focus.ordered_candidate_ids, start=1):
        item = by_id.get(candidate_id)
        if item is None:
            raise HumanReviewCommandError(
                f"focus candidate_id {candidate_id!r} missing from surface",
                code=CODE_FOCUS_SET_BLOCKER,
            )
        rows.append(
            HumanReviewFocusRow(
                alias_number=index,
                candidate_id=item.candidate_id,
                facility=item.facility,
                discipline=item.discipline,
                system=item.system,
                iwp=item.iwp,
                boq_code=item.boq_code,
                name=item.name,
                unit=item.unit,
                constructor_proposed_qty=item.constructor_proposed_qty,
                current_decision_label=item.current_decision_label,
                warning_lines=item.warning_lines,
            )
        )
    return tuple(rows)


def resolve_focus_alias(focus: HumanReviewFocusSet, alias_number: int) -> str:
    if alias_number < 1 or alias_number > len(focus.ordered_candidate_ids):
        raise HumanReviewCommandError(
            f"unknown focus row alias №{alias_number}",
            code=CODE_FOCUS_SET_BLOCKER,
        )
    return focus.ordered_candidate_ids[alias_number - 1]


def validate_focus_set_against_surface(
    focus: HumanReviewFocusSet,
    surface: HumanReviewSurfaceSnapshot,
) -> HumanReviewFocusSet:
    """Fail closed when filter/package/checkpoint/candidate set diverged."""
    if focus.run_id != surface.run_id:
        raise HumanReviewCommandError("focus_set run_id mismatch", code=CODE_FOCUS_SET_BLOCKER)
    if focus.package_id != surface.package_id:
        raise HumanReviewCommandError(
            "focus_set package_id mismatch",
            code=CODE_FOCUS_SET_BLOCKER,
        )
    if focus.expected_checkpoint_id != surface.expected_checkpoint_id:
        raise HumanReviewCommandError(
            "focus_set expected_checkpoint_id is stale",
            code=CODE_FOCUS_SET_BLOCKER,
        )
    rebuilt = build_human_review_focus_set(
        surface,
        focus.filter_scope,
        focus_set_id=focus.focus_set_id,
        created_at=focus.created_at,
    )
    if rebuilt.focus_hash != focus.focus_hash:
        raise HumanReviewCommandError(
            "focus_set is stale; rebuild Focus Set",
            code=CODE_FOCUS_SET_BLOCKER,
        )
    if rebuilt.ordered_candidate_ids != focus.ordered_candidate_ids:
        raise HumanReviewCommandError(
            "focus_set candidate order/set changed",
            code=CODE_FOCUS_SET_BLOCKER,
        )
    return focus


def professional_slice_summary(
    rows: Sequence[HumanReviewFocusRow],
) -> Mapping[str, int]:
    accepted = changed = excluded = deferred = needs = not_reviewed = 0
    for row in rows:
        label = row.current_decision_label
        if label == "ПРИНЯТО":
            accepted += 1
        elif label == "ИЗМЕНЁН ОБЪЁМ":
            changed += 1
        elif label == "ИСКЛЮЧЕНО":
            excluded += 1
        elif label == "ПЕРЕНЕСЕНО":
            deferred += 1
        elif label == "НУЖНЫ ДАННЫЕ":
            needs += 1
        else:
            not_reviewed += 1
    return {
        "total": len(rows),
        "accepted": accepted,
        "changed_qty": changed,
        "excluded": excluded,
        "deferred": deferred,
        "needs_data": needs,
        "not_reviewed": not_reviewed,
    }


def grouped_review_summary(
    surface: HumanReviewSurfaceSnapshot,
) -> tuple[tuple[str, str, Mapping[str, int]], ...]:
    """TITLE → DISCIPLINE rollup over all package candidates."""
    buckets: dict[tuple[str, str], list[HumanReviewCandidateContext]] = {}
    for item in surface.candidates:
        key = (item.facility or "—", item.discipline or "—")
        buckets.setdefault(key, []).append(item)
    rows_out: list[tuple[str, str, Mapping[str, int]]] = []
    for (facility, discipline), items in sorted(buckets.items()):
        fake_rows = [
            HumanReviewFocusRow(
                alias_number=0,
                candidate_id=item.candidate_id,
                facility=item.facility,
                discipline=item.discipline,
                system=item.system,
                iwp=item.iwp,
                boq_code=item.boq_code,
                name=item.name,
                unit=item.unit,
                constructor_proposed_qty=item.constructor_proposed_qty,
                current_decision_label=item.current_decision_label,
                warning_lines=item.warning_lines,
            )
            for item in items
        ]
        rows_out.append((facility, discipline, professional_slice_summary(fake_rows)))
    return tuple(rows_out)


UNRESOLVED_DECISION_LABEL = "НЕ РАССМОТРЕНО"
REQUIRES_DECISION_LABEL = "ТРЕБУЕТ РЕШЕНИЯ"
CANDIDATE_TYPE_NEW_RU = "Новые возможности"
CANDIDATE_TYPE_ADDITIONAL_RU = "Доп. объём"


def is_unresolved_candidate(item: HumanReviewCandidateContext) -> bool:
    label = str(item.current_decision_label or "").strip()
    return not label or label == UNRESOLVED_DECISION_LABEL


def candidate_type_label(item: HumanReviewCandidateContext) -> str:
    """Presentation type of a package candidate (matches Module 5 oval slices)."""
    if float(item.already_planned_qty or 0.0) > 0:
        return CANDIDATE_TYPE_ADDITIONAL_RU
    return CANDIDATE_TYPE_NEW_RU


def unresolved_focus_rows(
    surface: HumanReviewSurfaceSnapshot,
    focus: HumanReviewFocusSet,
) -> tuple[HumanReviewFocusRow, ...]:
    """Unresolved candidates of the current Work Context, in Focus alias order."""
    return tuple(
        row
        for row in focus_rows(surface, focus)
        if not str(row.current_decision_label or "").strip()
        or str(row.current_decision_label).strip() == UNRESOLVED_DECISION_LABEL
    )


def unresolved_table_dicts(
    surface: HumanReviewSurfaceSnapshot,
    focus: HumanReviewFocusSet,
) -> tuple[dict[str, str], ...]:
    """Operable unresolved list. ``№`` is the current Focus alias for commands."""
    by_id = {item.candidate_id: item for item in surface.candidates}
    rows: list[dict[str, str]] = []
    for row in unresolved_focus_rows(surface, focus):
        item = by_id.get(row.candidate_id)
        baseline = float(item.already_planned_qty or 0.0) if item is not None else 0.0
        rows.append(
            {
                "№": str(row.alias_number),
                "Титул": row.facility or "—",
                "Дисциплина": row.discipline or "—",
                "Система": row.system or "—",
                "Пакет / IWP": row.iwp or "—",
                "BOQ": row.boq_code or "—",
                "Наименование": row.name or "—",
                "Ед. изм.": row.unit or "—",
                "Предложено Constructor": f"{row.constructor_proposed_qty:g}",
                "Уже запланировано": f"{baseline:g}",
                "Тип кандидата": (
                    candidate_type_label(item) if item is not None else CANDIDATE_TYPE_NEW_RU
                ),
                "Состояние": REQUIRES_DECISION_LABEL,
                "candidate_id": row.candidate_id,
            }
        )
    return tuple(rows)


def unresolved_context_groups(
    surface: HumanReviewSurfaceSnapshot,
) -> tuple[dict[str, str], ...]:
    """Where unresolved candidates remain: Title → Discipline → System → Package.

    Navigation/help summary only. It is not a filter and selects nothing.
    """
    counts: dict[tuple[str, str, str, str], int] = {}
    for item in surface.candidates:
        if not is_unresolved_candidate(item):
            continue
        key = (
            str(item.facility or "").strip() or "—",
            str(item.discipline or "").strip() or "—",
            str(item.system or "").strip() or "—",
            str(item.iwp or "").strip() or "—",
        )
        counts[key] = counts.get(key, 0) + 1
    return tuple(
        {
            "Титул": facility,
            "Дисциплина": discipline,
            "Система": system,
            "Пакет / IWP": iwp,
            "Осталось": str(count),
        }
        for (facility, discipline, system, iwp), count in sorted(counts.items())
    )


def recorded_decision_table_dicts(
    surface: HumanReviewSurfaceSnapshot,
) -> tuple[dict[str, str], ...]:
    """Durably recorded decisions, shown separately below unresolved work."""
    rows: list[dict[str, str]] = []
    for item in surface.candidates:
        if is_unresolved_candidate(item):
            continue
        rows.append(
            {
                "Титул": item.facility or "—",
                "Дисциплина": item.discipline or "—",
                "Система": item.system or "—",
                "Пакет / IWP": item.iwp or "—",
                "BOQ": item.boq_code or "—",
                "Наименование": item.name or "—",
                "Статус решения": str(item.current_decision_label or "").strip(),
                "candidate_id": item.candidate_id,
            }
        )
    rows.sort(
        key=lambda row: (
            row["Титул"],
            row["Дисциплина"],
            row["Система"],
            row["Пакет / IWP"],
            row["BOQ"],
            row["candidate_id"],
        )
    )
    return tuple(rows)


def package_candidate_ids(package: CandidatePackage) -> tuple[str, ...]:
    return tuple(str(item.candidate_id) for item in package.candidates)


def filter_scope_as_dict(scope: HumanReviewFocusFilter) -> dict[str, Any]:
    return _scope_dict(scope)
