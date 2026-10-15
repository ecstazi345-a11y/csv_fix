"""
Human Review Batch Command Port V2 — focus-bound conversational decisions.

Interpretation → deterministic resolve → preview → explicit confirm →
atomic multi-event resume via existing V1 durable contracts.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Sequence

from agents.human_surface.human_review_command import (
    ACTOR_ID_HUMAN_SURFACE,
    HumanReviewAction,
    HumanReviewCommand,
    HumanReviewCommandError,
    HumanReviewRuntimePort,
    HumanReviewSurfaceSnapshot,
    _SUBMIT_LOCK,
    _require_text,
    _validate_and_build_event,
    default_human_review_runtime,
    prepare_human_review_surface,
    require_durable_human_review_event_ids,
)
from agents.human_surface.human_review_focus import (
    CODE_FOCUS_SET_BLOCKER,
    HumanReviewFocusRow,
    HumanReviewFocusSet,
    focus_rows,
    professional_slice_summary,
    validate_focus_set_against_surface,
)
from agents.human_surface.monthly_commitment_draft import NON_CANDIDATE_CLARIFICATION_RU
from agents.human_surface.human_review_intent import (
    ReviewIntentDraft,
    ReviewIntentKind,
    ReviewIntentOperation,
    default_review_intent_interpreter,
)
from agents.monthly_plan_constructor.human_review_contracts import (
    RESOLUTION_KIND_DEFER_TO_PERIOD,
    HumanReviewDecision,
    HumanReviewEvent,
)
from agents.monthly_plan_constructor.lifecycle import STATUS_WAITING_FOR_HUMAN_REVIEW
from agents.monthly_plan_constructor.professional_review_resume import (
    ProfessionalHumanReviewResumeCommand,
    SCHEMA_VERSION as REVIEW_RESUME_SCHEMA,
    build_professional_review_wait_request,
)

CODE_BATCH_BLOCKER = "HUMAN_REVIEW_BATCH_BLOCKER"


class BatchResolution(str, Enum):
    ACCEPT = "ACCEPT"
    EXCLUDE = "EXCLUDE"
    CHANGE_QUANTITY = "CHANGE_QUANTITY"
    NEEDS_DATA = "NEEDS_DATA"
    DEFER_TO_PERIOD = "DEFER_TO_PERIOD"


@dataclass(frozen=True)
class HumanReviewBatchOperation:
    candidate_id: str
    alias_number: Optional[int]
    boq_code: str
    resolution: BatchResolution
    approved_qty: Optional[float] = None
    constructor_proposed_qty: Optional[float] = None
    target_period: Optional[str] = None
    reason_text: Optional[str] = None


@dataclass(frozen=True)
class HumanReviewBatchDraft:
    focus_set_id: str
    focus_hash: str
    run_id: str
    package_id: str
    expected_checkpoint_id: str
    source_text: str
    operations: tuple[HumanReviewBatchOperation, ...]


@dataclass(frozen=True)
class HumanReviewBatchPreviewCounts:
    accept: int
    defer: int
    change_qty: int
    exclude: int
    needs_data: int

    @property
    def total(self) -> int:
        return (
            self.accept
            + self.defer
            + self.change_qty
            + self.exclude
            + self.needs_data
        )


@dataclass(frozen=True)
class HumanReviewBatchPreview:
    draft: HumanReviewBatchDraft
    counts: HumanReviewBatchPreviewCounts
    exception_lines: tuple[str, ...]
    accept_lines: tuple[str, ...]
    focus_facility: Optional[str]
    focus_discipline: Optional[str]
    focus_size: int
    clarification_lines: tuple[str, ...] = ()
    reasons_complete: bool = True
    # Review-by-exceptions: durable prior state in current Work Context Focus Set.
    prior_deferred_in_focus: int = 0
    prior_accepted_in_focus: int = 0
    prior_changed_in_focus: int = 0
    prior_excluded_in_focus: int = 0
    prior_needs_data_in_focus: int = 0
    prior_unresolved_in_focus: int = 0


@dataclass(frozen=True)
class HumanReviewBatchSubmitResult:
    run_id: str
    professional_status: str
    expected_checkpoint_id: str
    event_ids: tuple[str, ...]
    operation_count: int


def _batch_fail(message: str, *, code: str = CODE_BATCH_BLOCKER) -> None:
    raise HumanReviewCommandError(message, code=code)


def _row_by_candidate(
    rows: Sequence[HumanReviewFocusRow],
) -> dict[str, HumanReviewFocusRow]:
    return {row.candidate_id: row for row in rows}


def _resolve_targets(
    op: ReviewIntentOperation,
    focus: HumanReviewFocusSet,
    rows: Sequence[HumanReviewFocusRow],
) -> tuple[HumanReviewFocusRow, ...]:
    if op.target.remainder:
        _batch_fail("ACCEPT_REMAINDER must be expanded by resolver")
    if op.target.boq_code:
        code = op.target.boq_code.strip().casefold()
        matches = [row for row in rows if row.boq_code.casefold() == code]
        if not matches:
            _batch_fail(NON_CANDIDATE_CLARIFICATION_RU)
        if len(matches) > 1:
            _batch_fail(f"ambiguous BOQ {op.target.boq_code!r} in Focus Set")
        return (matches[0],)
    if not op.target.alias_numbers:
        _batch_fail(f"operation has no target: {op.raw_clause!r}")
    resolved: list[HumanReviewFocusRow] = []
    by_alias = {row.alias_number: row for row in rows}
    for number in op.target.alias_numbers:
        row = by_alias.get(number)
        if row is None:
            _batch_fail(NON_CANDIDATE_CLARIFICATION_RU, code=CODE_FOCUS_SET_BLOCKER)
        resolved.append(row)
    return tuple(resolved)


def _to_batch_resolution(kind: ReviewIntentKind) -> BatchResolution:
    if kind is ReviewIntentKind.ACCEPT:
        return BatchResolution.ACCEPT
    if kind is ReviewIntentKind.EXCLUDE:
        return BatchResolution.EXCLUDE
    if kind is ReviewIntentKind.CHANGE_QUANTITY:
        return BatchResolution.CHANGE_QUANTITY
    if kind is ReviewIntentKind.NEEDS_DATA:
        return BatchResolution.NEEDS_DATA
    if kind is ReviewIntentKind.DEFER_TO_PERIOD:
        return BatchResolution.DEFER_TO_PERIOD
    _batch_fail(f"unsupported intent kind {kind!r}")


def resolve_intent_to_batch_draft(
    intent: ReviewIntentDraft,
    *,
    focus: HumanReviewFocusSet,
    surface: HumanReviewSurfaceSnapshot,
) -> HumanReviewBatchDraft:
    validate_focus_set_against_surface(focus, surface)
    rows = focus_rows(surface, focus)
    by_id = _row_by_candidate(rows)
    explicit: dict[str, HumanReviewBatchOperation] = {}
    accept_remainder = False

    for op in intent.operations:
        if op.kind is ReviewIntentKind.ACCEPT_REMAINDER:
            accept_remainder = True
            continue
        for row in _resolve_targets(op, focus, rows):
            if row.candidate_id in explicit:
                _batch_fail(
                    f"candidate {row.boq_code} targeted by multiple clauses",
                )
            resolution = _to_batch_resolution(op.kind)
            # Missing reason/qty allowed at preview; durable submit still requires them.
            if resolution is BatchResolution.CHANGE_QUANTITY:
                if op.approved_qty is not None:
                    if op.approved_qty <= 0:
                        _batch_fail("approved_qty must be > 0")
                    if op.approved_qty > row.constructor_proposed_qty + 1e-12:
                        _batch_fail(
                            "approved_qty must not exceed Constructor proposed quantity",
                        )
            if resolution is BatchResolution.DEFER_TO_PERIOD and not op.target_period:
                _batch_fail("DEFER_TO_PERIOD requires target_period")
            explicit[row.candidate_id] = HumanReviewBatchOperation(
                candidate_id=row.candidate_id,
                alias_number=row.alias_number,
                boq_code=row.boq_code,
                resolution=resolution,
                approved_qty=op.approved_qty,
                constructor_proposed_qty=row.constructor_proposed_qty,
                target_period=op.target_period,
                reason_text=(op.reason_text or "").strip() or None,
            )

    operations = list(explicit.values())
    if accept_remainder:
        for row in rows:
            if row.candidate_id in explicit:
                continue
            # Accept only currently unreviewed rows in this Focus Set.
            # REQUIRES_CLARIFICATION ("НУЖНЫ ДАННЫЕ") stays unresolved until explicit.
            if row.current_decision_label != "НЕ РАССМОТРЕНО":
                continue
            operations.append(
                HumanReviewBatchOperation(
                    candidate_id=row.candidate_id,
                    alias_number=row.alias_number,
                    boq_code=row.boq_code,
                    resolution=BatchResolution.ACCEPT,
                    approved_qty=row.constructor_proposed_qty,
                    constructor_proposed_qty=row.constructor_proposed_qty,
                    reason_text=None,
                )
            )

    if not operations:
        _batch_fail("batch draft is empty")

    # Stable order by alias / focus order.
    order = {cid: index for index, cid in enumerate(focus.ordered_candidate_ids)}
    operations.sort(key=lambda item: order.get(item.candidate_id, 10**9))
    return HumanReviewBatchDraft(
        focus_set_id=focus.focus_set_id,
        focus_hash=focus.focus_hash,
        run_id=focus.run_id,
        package_id=focus.package_id,
        expected_checkpoint_id=focus.expected_checkpoint_id,
        source_text=intent.source_text,
        operations=tuple(operations),
    )


def _reason_required(resolution: BatchResolution) -> bool:
    return resolution in {
        BatchResolution.EXCLUDE,
        BatchResolution.CHANGE_QUANTITY,
        BatchResolution.NEEDS_DATA,
        BatchResolution.DEFER_TO_PERIOD,
    }


def _clarification_for_missing_reason(resolution: BatchResolution) -> str:
    if resolution is BatchResolution.DEFER_TO_PERIOD:
        return "Укажите причину переноса."
    if resolution is BatchResolution.EXCLUDE:
        return "Укажите причину исключения."
    if resolution is BatchResolution.CHANGE_QUANTITY:
        return "Укажите причину корректировки."
    if resolution is BatchResolution.NEEDS_DATA:
        return "Укажите, какие данные нужны."
    return "Укажите причину решения."


def _clarification_for_missing_qty() -> str:
    return "Укажите новый объём."


def build_batch_preview(
    draft: HumanReviewBatchDraft,
    *,
    focus: HumanReviewFocusSet,
    surface: Optional[HumanReviewSurfaceSnapshot] = None,
) -> HumanReviewBatchPreview:
    accept = defer = change = exclude = needs = 0
    exceptions: list[str] = []
    accepts: list[str] = []
    clarifications: list[str] = []
    reasons_complete = True
    prior_deferred = prior_accepted = prior_changed = prior_excluded = prior_needs = 0
    prior_unresolved = focus.size
    if surface is not None:
        slice_counts = professional_slice_summary(focus_rows(surface, focus))
        prior_accepted = int(slice_counts["accepted"])
        prior_changed = int(slice_counts["changed_qty"])
        prior_deferred = int(slice_counts["deferred"])
        prior_excluded = int(slice_counts["excluded"])
        prior_needs = int(slice_counts["needs_data"])
        prior_unresolved = int(slice_counts["not_reviewed"])
    for op in draft.operations:
        alias = f"№{op.alias_number}" if op.alias_number else "—"
        head = f"{alias} / {op.boq_code}"
        reason = (op.reason_text or "").strip()
        if (
            op.resolution is BatchResolution.CHANGE_QUANTITY
            and op.approved_qty is None
        ):
            reasons_complete = False
            note = _clarification_for_missing_qty()
            if note not in clarifications:
                clarifications.append(note)
        if _reason_required(op.resolution) and not reason:
            reasons_complete = False
            note = _clarification_for_missing_reason(op.resolution)
            if note not in clarifications:
                clarifications.append(note)
            reason_display = "требуется указать"
        else:
            reason_display = reason or "—"
        if op.resolution is BatchResolution.ACCEPT:
            accept += 1
            accepts.append(f"{head} → принять")
        elif op.resolution is BatchResolution.DEFER_TO_PERIOD:
            defer += 1
            exceptions.append(
                f"{head} → перенести на {op.target_period}\nПричина: {reason_display}"
            )
        elif op.resolution is BatchResolution.CHANGE_QUANTITY:
            change += 1
            qty_display = (
                op.approved_qty if op.approved_qty is not None else "требуется указать"
            )
            exceptions.append(
                f"{head}\n{op.constructor_proposed_qty} → {qty_display}\n"
                f"Причина: {reason_display}"
            )
        elif op.resolution is BatchResolution.EXCLUDE:
            exclude += 1
            exceptions.append(f"{head} → исключить\nПричина: {reason_display}")
        elif op.resolution is BatchResolution.NEEDS_DATA:
            needs += 1
            exceptions.append(f"{head} → нужны данные\nПричина: {reason_display}")
    counts = HumanReviewBatchPreviewCounts(
        accept=accept,
        defer=defer,
        change_qty=change,
        exclude=exclude,
        needs_data=needs,
    )
    if counts.total != len(draft.operations):
        _batch_fail("preview counts do not reconcile with operations")
    return HumanReviewBatchPreview(
        draft=draft,
        counts=counts,
        exception_lines=tuple(exceptions),
        accept_lines=tuple(accepts),
        focus_facility=focus.filter_scope.facility,
        focus_discipline=focus.filter_scope.discipline,
        focus_size=focus.size,
        clarification_lines=tuple(clarifications),
        reasons_complete=reasons_complete,
        prior_deferred_in_focus=prior_deferred,
        prior_accepted_in_focus=prior_accepted,
        prior_changed_in_focus=prior_changed,
        prior_excluded_in_focus=prior_excluded,
        prior_needs_data_in_focus=prior_needs,
        prior_unresolved_in_focus=prior_unresolved,
    )


def prepare_batch_from_text(
    text: str,
    *,
    focus: HumanReviewFocusSet,
    surface: Optional[HumanReviewSurfaceSnapshot] = None,
    runtime: Optional[HumanReviewRuntimePort] = None,
    default_year: int = 2026,
    context_period: Optional[str] = None,
) -> HumanReviewBatchPreview:
    """Text → interpreter → resolve → preview. Never writes."""
    snap = surface or prepare_human_review_surface(focus.run_id, runtime=runtime)
    validate_focus_set_against_surface(focus, snap)
    intent = default_review_intent_interpreter().interpret(
        text,
        default_year=default_year,
        context_period=context_period,
    )
    draft = resolve_intent_to_batch_draft(intent, focus=focus, surface=snap)
    return build_batch_preview(draft, focus=focus, surface=snap)


def _operation_to_command(
    op: HumanReviewBatchOperation,
    *,
    run_id: str,
    package_id: str,
    expected_checkpoint_id: str,
) -> HumanReviewCommand:
    if op.resolution is BatchResolution.ACCEPT:
        return HumanReviewCommand(
            run_id=run_id,
            package_id=package_id,
            candidate_id=op.candidate_id,
            action=HumanReviewAction.ACCEPT,
            expected_checkpoint_id=expected_checkpoint_id,
            reason_text=op.reason_text,
        )
    if op.resolution is BatchResolution.EXCLUDE:
        return HumanReviewCommand(
            run_id=run_id,
            package_id=package_id,
            candidate_id=op.candidate_id,
            action=HumanReviewAction.EXCLUDE,
            expected_checkpoint_id=expected_checkpoint_id,
            reason_text=op.reason_text,
        )
    if op.resolution is BatchResolution.CHANGE_QUANTITY:
        return HumanReviewCommand(
            run_id=run_id,
            package_id=package_id,
            candidate_id=op.candidate_id,
            action=HumanReviewAction.CHANGE_QUANTITY,
            expected_checkpoint_id=expected_checkpoint_id,
            approved_qty=op.approved_qty,
            reason_text=op.reason_text,
        )
    if op.resolution is BatchResolution.NEEDS_DATA:
        return HumanReviewCommand(
            run_id=run_id,
            package_id=package_id,
            candidate_id=op.candidate_id,
            action=HumanReviewAction.NEEDS_DATA,
            expected_checkpoint_id=expected_checkpoint_id,
            reason_text=op.reason_text,
        )
    if op.resolution is BatchResolution.DEFER_TO_PERIOD:
        return HumanReviewCommand(
            run_id=run_id,
            package_id=package_id,
            candidate_id=op.candidate_id,
            action=HumanReviewAction.DEFER_TO_PERIOD,
            expected_checkpoint_id=expected_checkpoint_id,
            reason_text=op.reason_text,
            resolution_kind=RESOLUTION_KIND_DEFER_TO_PERIOD,
            target_period=op.target_period,
        )
    _batch_fail(f"unsupported resolution {op.resolution!r}")


def submit_human_review_batch(
    draft: HumanReviewBatchDraft,
    *,
    focus: HumanReviewFocusSet,
    runtime: Optional[HumanReviewRuntimePort] = None,
    now: Optional[datetime] = None,
    confirmed: bool = False,
) -> HumanReviewBatchSubmitResult:
    """Validate entire batch, then append all events in one durable resume."""
    if not confirmed:
        _batch_fail("explicit batch confirmation required")
    if draft.focus_set_id != focus.focus_set_id or draft.focus_hash != focus.focus_hash:
        _batch_fail("batch draft focus_set binding mismatch", code=CODE_FOCUS_SET_BLOCKER)
    for op in draft.operations:
        if (
            op.resolution is BatchResolution.CHANGE_QUANTITY
            and op.approved_qty is None
        ):
            _batch_fail(_clarification_for_missing_qty())
        if _reason_required(op.resolution) and not (op.reason_text or "").strip():
            _batch_fail(_clarification_for_missing_reason(op.resolution))

    port = runtime or default_human_review_runtime()
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        _batch_fail("now must be timezone-aware UTC")
    stamp = stamp.astimezone(timezone.utc)

    with _SUBMIT_LOCK:
        surface = prepare_human_review_surface(draft.run_id, runtime=port)
        validate_focus_set_against_surface(focus, surface)
        if draft.expected_checkpoint_id != surface.expected_checkpoint_id:
            _batch_fail("expected_checkpoint_id is stale; reload Human Review surface")
        lifecycle = port.load_lifecycle(draft.run_id)
        if lifecycle.status != STATUS_WAITING_FOR_HUMAN_REVIEW:
            _batch_fail(
                f"run is not waiting for Human Review (status={lifecycle.status})",
            )
        current_ckpt = port.current_checkpoint_id(draft.run_id)
        if draft.expected_checkpoint_id != current_ckpt:
            _batch_fail("expected_checkpoint_id is stale; reload Human Review surface")

        events: list[HumanReviewEvent] = []
        for op in draft.operations:
            command = _operation_to_command(
                op,
                run_id=draft.run_id,
                package_id=draft.package_id,
                expected_checkpoint_id=draft.expected_checkpoint_id,
            )
            events.append(
                _validate_and_build_event(
                    command,
                    lifecycle=lifecycle,
                    reviewed_at=stamp,
                )
            )

        wait = build_professional_review_wait_request(lifecycle, created_at=stamp)
        resume = ProfessionalHumanReviewResumeCommand(
            schema_version=REVIEW_RESUME_SCHEMA,
            interrupt_id=wait.interrupt_id,
            run_id=str(lifecycle.run_id),
            review_events=tuple(events),
            answered_at=stamp,
            expected_checkpoint_id=draft.expected_checkpoint_id,
        )
        updated = port.resume_professional_review(
            run_id=str(lifecycle.run_id),
            resume_command=resume,
        )
        expected_ids = tuple(str(event.review_event_id) for event in events)
        require_durable_human_review_event_ids(
            updated,
            expected_ids,
            where="resume result",
        )
        # Read-after-write: never treat in-memory resume payload as committed truth.
        durable = port.load_lifecycle(str(lifecycle.run_id))
        require_durable_human_review_event_ids(
            durable,
            expected_ids,
            where="readback",
        )
        return HumanReviewBatchSubmitResult(
            run_id=str(durable.run_id),
            professional_status=str(durable.status),
            expected_checkpoint_id=port.current_checkpoint_id(str(durable.run_id)),
            event_ids=expected_ids,
            operation_count=len(events),
        )
