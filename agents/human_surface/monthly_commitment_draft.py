"""
Monthly Commitment Draft — cumulative composition of durably reviewed Work Contexts.

Authoritative inputs only:
  1) Candidate Package row identity + already_planned baseline
  2) latest effective Human Review decisions on the surface

Draft scope = UNION of contexts that already have confirmed Human Review
decisions (not package-wide baseline, not current Work Context alone).

Visible composition is a professional projection:
  one physical identity → one commitment row
  (baseline + confirmed Constructor delta merged).

Not a second source of truth. Never writes production monthly plan tables.
Streamlit session_state is not used.
"""

from __future__ import annotations

from dataclasses import dataclass

from agents.human_surface.human_review_command import (
    HumanReviewCandidateContext,
    HumanReviewSurfaceSnapshot,
)
from agents.human_surface.human_review_focus import (
    HumanReviewFocusSet,
    focus_rows,
    professional_slice_summary,
)

STATUS_BASELINE = "Базовый состав"
STATUS_ACCEPTED = "ПРИНЯТО"
STATUS_CHANGED = "ИЗМЕНЁН ОБЪЁМ"
STATUS_DEFERRED = "ПЕРЕНЕСЕНО"
STATUS_EXCLUDED = "ИСКЛЮЧЕНО"
STATUS_NEEDS_DATA = "НУЖНЫ ДАННЫЕ"
STATUS_UNRESOLVED = "НЕ РАССМОТРЕНО"

# Unambiguous floating-point machine residue only — not a business tolerance.
_FLOAT_RESIDUE_ABS = 1e-12

# Professional Work Context identity available on package candidates.
# Facility/title + discipline match Page53 Work Context filters.
ContextIdentity = tuple[str, str]

# Strongest physical commitment identity available without invention.
PhysicalIdentity = tuple[str, str, str, str, str, str]

IDENTITY_AMBIGUITY_WARNING_RU = (
    "Одинаковая физическая идентичность встречается у разных candidate_id — "
    "позиции не объединены (fail-closed)."
)


@dataclass(frozen=True)
class MonthlyCommitmentDraftCounts:
    baseline: int
    added_constructor: int
    changed_qty: int
    deferred: int
    excluded: int
    needs_data: int
    unresolved: int
    final_positions: int = 0


@dataclass(frozen=True)
class MonthlyCommitmentDraftRow:
    """One professional monthly commitment position (projection only)."""

    facility: str
    discipline: str
    system: str
    iwp: str
    boq_code: str
    name: str
    unit: str
    baseline_qty: float
    constructor_delta_qty: float
    final_qty: float
    source_status: str
    candidate_id: str
    identity_warning: str = ""

    @property
    def qty(self) -> float:
        """Final commitment quantity — kept for callers that still read ``qty``."""
        return self.final_qty


@dataclass(frozen=True)
class MonthlyCommitmentDraftView:
    """Cumulative draft over durably reviewed professional contexts only."""

    run_id: str
    package_id: str
    counts: MonthlyCommitmentDraftCounts
    composition_rows: tuple[MonthlyCommitmentDraftRow, ...]
    deferred_rows: tuple[MonthlyCommitmentDraftRow, ...]
    excluded_rows: tuple[MonthlyCommitmentDraftRow, ...]
    needs_data_rows: tuple[MonthlyCommitmentDraftRow, ...]


@dataclass(frozen=True)
class WorkContextReviewSummary:
    facility: str
    discipline: str
    total: int
    reviewed: int
    accepted: int
    changed_qty: int
    deferred: int
    excluded: int
    needs_data: int
    not_reviewed: int


def _normalize_residue(value: float) -> float:
    """Zero only unambiguous float machine residue. Preserves small physical values."""
    number = float(value)
    if abs(number) < _FLOAT_RESIDUE_ABS:
        return 0.0
    return number


def _format_qty(value: float) -> str:
    number = _normalize_residue(value)
    if number == 0.0:
        return "0"
    text = f"{number:.12f}".rstrip("0").rstrip(".")
    return text or "0"


def _qty_for_decision(item: HumanReviewCandidateContext) -> float:
    if item.human_approved_qty is not None:
        return _normalize_residue(float(item.human_approved_qty))
    return _normalize_residue(float(item.constructor_proposed_qty))


def _physical_identity(item: HumanReviewCandidateContext) -> PhysicalIdentity:
    """Identity used to keep distinct physical positions separate (never BOQ-only)."""
    return (
        str(item.facility or "").strip(),
        str(item.discipline or "").strip(),
        str(item.system or "").strip(),
        str(item.iwp or "").strip(),
        str(item.boq_code or "").strip(),
        str(item.candidate_id or "").strip(),
    )


def _display_identity_key(row: MonthlyCommitmentDraftRow) -> tuple[str, str, str, str, str]:
    """Cross-candidate ambiguity key — excludes candidate_id."""
    return (
        row.facility,
        row.discipline,
        row.system,
        row.iwp,
        row.boq_code,
    )


def _side_row(
    item: HumanReviewCandidateContext,
    *,
    qty: float,
    source_status: str,
) -> MonthlyCommitmentDraftRow:
    cleaned = _normalize_residue(qty)
    return MonthlyCommitmentDraftRow(
        facility=item.facility or "—",
        discipline=item.discipline or "—",
        system=item.system or "—",
        iwp=item.iwp or "—",
        boq_code=item.boq_code or "—",
        name=item.name or "—",
        unit=item.unit or "—",
        baseline_qty=0.0,
        constructor_delta_qty=cleaned,
        final_qty=cleaned,
        source_status=source_status,
        candidate_id=item.candidate_id,
    )


def _commitment_row(
    item: HumanReviewCandidateContext,
    *,
    baseline_qty: float,
    constructor_delta_qty: float,
    source_status: str,
) -> MonthlyCommitmentDraftRow:
    baseline = _normalize_residue(baseline_qty)
    delta = _normalize_residue(constructor_delta_qty)
    return MonthlyCommitmentDraftRow(
        facility=item.facility or "—",
        discipline=item.discipline or "—",
        system=item.system or "—",
        iwp=item.iwp or "—",
        boq_code=item.boq_code or "—",
        name=item.name or "—",
        unit=item.unit or "—",
        baseline_qty=baseline,
        constructor_delta_qty=delta,
        final_qty=_normalize_residue(baseline + delta),
        source_status=source_status,
        candidate_id=item.candidate_id,
    )


def _context_identity(item: HumanReviewCandidateContext) -> ContextIdentity:
    """Strongest Work Context key carried on package candidates without invention."""
    return (
        str(item.facility or "").strip(),
        str(item.discipline or "").strip(),
    )


def _has_confirmed_decision(item: HumanReviewCandidateContext) -> bool:
    label = str(item.current_decision_label or "").strip()
    return bool(label) and label != STATUS_UNRESOLVED


def reviewed_context_identities(
    surface: HumanReviewSurfaceSnapshot,
) -> frozenset[ContextIdentity]:
    """Contexts that already have at least one durable Human Review decision."""
    return frozenset(
        _context_identity(item)
        for item in surface.candidates
        if _has_confirmed_decision(item)
    )


def _sort_key(row: MonthlyCommitmentDraftRow) -> tuple[str, str, str, str, str, str]:
    return (
        row.facility,
        row.discipline,
        row.system,
        row.iwp,
        row.boq_code,
        row.candidate_id,
    )


def _mark_ambiguous_identities(
    rows: list[MonthlyCommitmentDraftRow],
) -> list[MonthlyCommitmentDraftRow]:
    """Fail-closed: same physical display key on different candidates stays separate."""
    counts: dict[tuple[str, str, str, str, str], int] = {}
    for row in rows:
        key = _display_identity_key(row)
        counts[key] = counts.get(key, 0) + 1
    if not any(n > 1 for n in counts.values()):
        return rows
    marked: list[MonthlyCommitmentDraftRow] = []
    for row in rows:
        if counts[_display_identity_key(row)] > 1:
            marked.append(
                MonthlyCommitmentDraftRow(
                    facility=row.facility,
                    discipline=row.discipline,
                    system=row.system,
                    iwp=row.iwp,
                    boq_code=row.boq_code,
                    name=row.name,
                    unit=row.unit,
                    baseline_qty=row.baseline_qty,
                    constructor_delta_qty=row.constructor_delta_qty,
                    final_qty=row.final_qty,
                    source_status=row.source_status,
                    candidate_id=row.candidate_id,
                    identity_warning=IDENTITY_AMBIGUITY_WARNING_RU,
                )
            )
        else:
            marked.append(row)
    return marked


def build_monthly_commitment_draft(
    surface: HumanReviewSurfaceSnapshot,
) -> MonthlyCommitmentDraftView:
    """
    Deterministic projection over UNION of durably reviewed contexts:

      baseline (already_planned > 0) inside reviewed contexts
      + ACCEPT / CHANGE_QUANTITY
      − DEFER / EXCLUDE (side lists; not month composition)
      NEEDS_DATA / UNRESOLVED (within reviewed contexts only)

    Visible composition merges baseline + Constructor delta for the same
    physical candidate identity into one professional commitment row.
    """
    reviewed = reviewed_context_identities(surface)
    composition: list[MonthlyCommitmentDraftRow] = []
    deferred: list[MonthlyCommitmentDraftRow] = []
    excluded: list[MonthlyCommitmentDraftRow] = []
    needs: list[MonthlyCommitmentDraftRow] = []
    baseline = added = changed = defer_n = excl_n = need_n = unresolved = 0
    seen_physical: set[PhysicalIdentity] = set()

    for item in surface.candidates:
        if _context_identity(item) not in reviewed:
            continue

        planned = _normalize_residue(float(item.already_planned_qty or 0.0))
        label = str(item.current_decision_label or "").strip() or STATUS_UNRESOLVED
        physical = _physical_identity(item)

        if label == STATUS_DEFERRED:
            defer_n += 1
            deferred.append(
                _side_row(
                    item,
                    qty=float(item.constructor_proposed_qty),
                    source_status=STATUS_DEFERRED,
                )
            )
            continue
        if label == STATUS_EXCLUDED:
            excl_n += 1
            excluded.append(
                _side_row(
                    item,
                    qty=float(item.constructor_proposed_qty),
                    source_status=STATUS_EXCLUDED,
                )
            )
            continue
        if label == STATUS_NEEDS_DATA:
            need_n += 1
            needs.append(
                _side_row(
                    item,
                    qty=float(item.constructor_proposed_qty),
                    source_status=STATUS_NEEDS_DATA,
                )
            )
            continue

        has_baseline = planned > 0.0
        if has_baseline:
            baseline += 1

        if label == STATUS_ACCEPTED:
            added += 1
            delta = _qty_for_decision(item)
            composition.append(
                _commitment_row(
                    item,
                    baseline_qty=planned,
                    constructor_delta_qty=delta,
                    source_status=STATUS_ACCEPTED,
                )
            )
            seen_physical.add(physical)
        elif label == STATUS_CHANGED:
            changed += 1
            delta = _qty_for_decision(item)
            composition.append(
                _commitment_row(
                    item,
                    baseline_qty=planned,
                    constructor_delta_qty=delta,
                    source_status=STATUS_CHANGED,
                )
            )
            seen_physical.add(physical)
        else:
            unresolved += 1
            if has_baseline:
                composition.append(
                    _commitment_row(
                        item,
                        baseline_qty=planned,
                        constructor_delta_qty=0.0,
                        source_status=STATUS_BASELINE,
                    )
                )
                seen_physical.add(physical)

    composition = _mark_ambiguous_identities(composition)
    composition.sort(key=_sort_key)
    deferred.sort(key=_sort_key)
    excluded.sort(key=_sort_key)
    needs.sort(key=_sort_key)

    return MonthlyCommitmentDraftView(
        run_id=surface.run_id,
        package_id=surface.package_id,
        counts=MonthlyCommitmentDraftCounts(
            baseline=baseline,
            added_constructor=added,
            changed_qty=changed,
            deferred=defer_n,
            excluded=excl_n,
            needs_data=need_n,
            unresolved=unresolved,
            final_positions=len(composition),
        ),
        composition_rows=tuple(composition),
        deferred_rows=tuple(deferred),
        excluded_rows=tuple(excluded),
        needs_data_rows=tuple(needs),
    )


def composition_table_dicts(
    draft: MonthlyCommitmentDraftView,
) -> tuple[dict[str, str], ...]:
    """Display rows for Page 53 — one professional position per physical identity."""
    rows: list[dict[str, str]] = []
    for item in draft.composition_rows:
        row = {
            "Титул": item.facility,
            "Дисциплина": item.discipline,
            "Система": item.system,
            "Пакет / IWP": item.iwp,
            "BOQ": item.boq_code,
            "Наименование": item.name,
            "Ед. изм.": item.unit,
            "Базовый объём": _format_qty(item.baseline_qty),
            "Добавлено Constructor": _format_qty(item.constructor_delta_qty),
            "Итоговый объём": _format_qty(item.final_qty),
            "Статус": item.source_status,
            "candidate_id": item.candidate_id,
        }
        if item.identity_warning:
            row["Предупреждение"] = item.identity_warning
        rows.append(row)
    return tuple(rows)


def build_work_context_review_summary(
    surface: HumanReviewSurfaceSnapshot,
    focus: HumanReviewFocusSet,
) -> WorkContextReviewSummary:
    rows = focus_rows(surface, focus)
    counts = professional_slice_summary(rows)
    reviewed = (
        counts["accepted"]
        + counts["changed_qty"]
        + counts["excluded"]
        + counts["deferred"]
        + counts["needs_data"]
    )
    facility = focus.filter_scope.facility or "Все"
    discipline = focus.filter_scope.discipline or "Все"
    return WorkContextReviewSummary(
        facility=facility,
        discipline=discipline,
        total=int(counts["total"]),
        reviewed=reviewed,
        accepted=int(counts["accepted"]),
        changed_qty=int(counts["changed_qty"]),
        deferred=int(counts["deferred"]),
        excluded=int(counts["excluded"]),
        needs_data=int(counts["needs_data"]),
        not_reviewed=int(counts["not_reviewed"]),
    )


NON_CANDIDATE_CLARIFICATION_RU = (
    "Позиция не является кандидатом Constructor. "
    "Для изменения результата требуется отдельное "
    "обоснованное профессиональное решение."
)


def is_non_candidate_reference_error(message: str) -> bool:
    text = str(message or "").casefold()
    return (
        "unknown focus row alias" in text
        or "unknown boq" in text
        or "не является кандидатом" in text
    )
