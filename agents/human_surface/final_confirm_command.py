"""
Final Human Confirm command port.

Package-wide preview, readiness, stale protection, durable approval.
Streamlit does not write the store. Work Context and oval are not inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from agents.human_surface.human_review_command import (
    ACTOR_ID_HUMAN_SURFACE,
    HumanReviewCandidateContext,
    HumanReviewRuntimePort,
    default_human_review_runtime,
    prepare_human_review_surface,
)
from agents.human_surface.monthly_commitment_draft import (
    IDENTITY_AMBIGUITY_WARNING_RU,
    STATUS_ACCEPTED,
    STATUS_CHANGED,
    STATUS_DEFERRED,
    STATUS_EXCLUDED,
    STATUS_NEEDS_DATA,
    STATUS_UNRESOLVED,
)
from agents.human_surface.work_context import queue_from_facility
from agents.monthly_plan_constructor.approved_monthly_package import (
    PROVENANCE_HUMAN_SURFACE,
    SCHEMA_VERSION,
    STATUS_APPROVED,
    ApprovedMonthlyLine,
    ApprovedMonthlyPackage,
    ApprovedMonthlySummary,
    approval_identity,
    content_hash_for,
    sha256_hex,
)
from agents.monthly_plan_constructor.human_review_contracts import (
    project_effective_human_review_events,
)
from agents.monthly_plan_constructor.lifecycle import ConstructorLifecycleState
from agents.monthly_plan_constructor.shadow_approved_monthly_package_store import (
    CODE_APPROVED_STORE_CONFLICT,
    ApprovedMonthlyPackageStore,
    ApprovedMonthlyPackageStoreError,
    open_approved_monthly_package_store,
    open_existing_approved_monthly_package_store,
)

CODE_STALE_APPROVAL_PREVIEW = "STALE_APPROVAL_PREVIEW"
CODE_NOT_READY = "NOT_READY"
CODE_READBACK_MISMATCH = "READBACK_MISMATCH"
CODE_FINAL_CONFIRM_BLOCKER = "FINAL_CONFIRM_BLOCKER"

STATUS_CONFIRM_APPROVED = "APPROVED"
STATUS_CONFIRM_ALREADY = "ALREADY_APPROVED"

NOT_READY_RU = (
    "Кандидатный состав нельзя подтвердить:\n"
    "остались позиции, требующие решения человека: {count}."
)
STALE_PREVIEW_RU = (
    "Результат изменился после формирования предварительного просмотра. "
    "Обновите итог и подтвердите его повторно."
)
_FLOAT_RESIDUE_ABS = 1e-12


class FinalConfirmError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class FinalApprovalReadiness:
    candidate_count: int
    accepted_count: int
    changed_qty_count: int
    excluded_count: int
    deferred_count: int
    needs_data_count: int
    not_reviewed_count: int
    ready: bool

    @property
    def unresolved_human_count(self) -> int:
        return self.not_reviewed_count + self.needs_data_count


@dataclass(frozen=True)
class FinalMonthlyApprovalPreview:
    project_code: str
    month_key: str
    queue: Optional[str]
    source_run_id: str
    source_mission_id: str
    source_candidate_package_id: str
    expected_checkpoint_id: str
    review_content_hash: str
    readiness: FinalApprovalReadiness
    professional_lines: tuple[ApprovedMonthlyLine, ...]
    summary: ApprovedMonthlySummary
    preview_content_hash: str


@dataclass(frozen=True)
class FinalConfirmResult:
    status: str
    package: ApprovedMonthlyPackage


def not_ready_message(count: int) -> str:
    return NOT_READY_RU.format(count=int(count))


def canonical_qty(value: object) -> str:
    number = float(value or 0.0)
    if abs(number) < _FLOAT_RESIDUE_ABS:
        number = 0.0
    text = f"{number:.12f}".rstrip("0").rstrip(".")
    return text or "0"


def review_content_hash(lifecycle: ConstructorLifecycleState) -> str:
    """Semantic effective decisions in package candidate order.

    Event id and timestamp are excluded so a re-entered identical decision
    does not mint a new approval version.
    """
    package = lifecycle.package
    if package is None:
        raise FinalConfirmError(CODE_FINAL_CONFIRM_BLOCKER, "candidate package is missing")
    effective = project_effective_human_review_events(
        tuple(lifecycle.human_review_events or ()),
        package,
    )
    rows = []
    for candidate in package.candidates:
        event = effective.get(str(candidate.candidate_id))
        if event is None:
            rows.append(
                {
                    "candidate_id": str(candidate.candidate_id),
                    "decision": None,
                    "constructor_proposed_qty": None,
                    "human_approved_qty": None,
                    "resolution_kind": None,
                    "target_period": None,
                    "reason_text": None,
                }
            )
            continue
        rows.append(
            {
                "candidate_id": str(candidate.candidate_id),
                "decision": event.decision.value,
                "constructor_proposed_qty": _optional_qty(event.constructor_proposed_qty),
                "human_approved_qty": _optional_qty(event.human_approved_qty),
                "resolution_kind": event.resolution_kind,
                "target_period": event.target_period,
                "reason_text": event.reason_text,
            }
        )
    return sha256_hex(
        {
            "source_candidate_package_id": str(package.package_id),
            "effective_decisions": rows,
        }
    )


def prepare_final_monthly_approval_preview(
    run_id: str,
    *,
    runtime: Optional[HumanReviewRuntimePort] = None,
) -> FinalMonthlyApprovalPreview:
    port = runtime or default_human_review_runtime()
    lifecycle = port.load_lifecycle(run_id)
    surface = prepare_human_review_surface(run_id, runtime=port)
    checkpoint_id = port.current_checkpoint_id(run_id)
    if lifecycle.package is None or lifecycle.scope is None:
        raise FinalConfirmError(CODE_FINAL_CONFIRM_BLOCKER, "package scope is missing")
    readiness = FinalApprovalReadiness(
        candidate_count=len(surface.candidates),
        accepted_count=surface.accepted_count,
        changed_qty_count=surface.changed_qty_count,
        excluded_count=surface.excluded_count,
        deferred_count=surface.deferred_count,
        needs_data_count=surface.needs_data_count,
        not_reviewed_count=surface.not_reviewed_count,
        ready=(
            len(surface.candidates) > 0
            and surface.not_reviewed_count == 0
            and surface.needs_data_count == 0
        ),
    )
    lines = _professional_lines(
        surface.candidates,
        project_code=str(lifecycle.scope.project_code),
        month_key=str(lifecycle.scope.month_key),
    )
    summary = ApprovedMonthlySummary(
        final_positions=len(lines),
        baseline_positions=sum(1 for item in lines if _qty_positive(item.baseline_qty)),
        constructor_additions=sum(1 for item in lines if _qty_positive(item.constructor_delta_qty)),
        changed_qty=surface.changed_qty_count,
        accepted=surface.accepted_count,
        excluded=surface.excluded_count,
        deferred=surface.deferred_count,
        unresolved=surface.not_reviewed_count,
        needs_data=surface.needs_data_count,
    )
    queue = _authoritative_queue(lifecycle, surface.candidates)
    review_hash = review_content_hash(lifecycle)
    preview_hash = sha256_hex(
        {
            "project_code": str(lifecycle.scope.project_code),
            "month_key": str(lifecycle.scope.month_key),
            "queue": queue,
            "source_run_id": surface.run_id,
            "source_candidate_package_id": surface.package_id,
            "review_content_hash": review_hash,
            "professional_lines": [
                {
                    "facility": item.facility,
                    "discipline": item.discipline,
                    "system": item.system,
                    "iwp": item.iwp,
                    "boq_code": item.boq_code,
                    "name": item.name,
                    "unit": item.unit,
                    "baseline_qty": item.baseline_qty,
                    "constructor_delta_qty": item.constructor_delta_qty,
                    "final_qty": item.final_qty,
                    "source_status": item.source_status,
                    "candidate_id": item.candidate_id,
                    "identity_warning": item.identity_warning,
                }
                for item in lines
            ],
            "summary": {
                "final_positions": summary.final_positions,
                "baseline_positions": summary.baseline_positions,
                "constructor_additions": summary.constructor_additions,
                "changed_qty": summary.changed_qty,
                "accepted": summary.accepted,
                "excluded": summary.excluded,
                "deferred": summary.deferred,
                "unresolved": summary.unresolved,
                "needs_data": summary.needs_data,
            },
        }
    )
    return FinalMonthlyApprovalPreview(
        project_code=str(lifecycle.scope.project_code),
        month_key=str(lifecycle.scope.month_key),
        queue=queue,
        source_run_id=surface.run_id,
        source_mission_id=surface.mission_id,
        source_candidate_package_id=surface.package_id,
        expected_checkpoint_id=checkpoint_id,
        review_content_hash=review_hash,
        readiness=readiness,
        professional_lines=lines,
        summary=summary,
        preview_content_hash=preview_hash,
    )


def submit_final_monthly_confirm(
    preview: FinalMonthlyApprovalPreview,
    *,
    approved_by: str = ACTOR_ID_HUMAN_SURFACE,
    runtime: Optional[HumanReviewRuntimePort] = None,
    store: Optional[ApprovedMonthlyPackageStore] = None,
    now: Optional[datetime] = None,
) -> FinalConfirmResult:
    port = runtime or default_human_review_runtime()
    current = prepare_final_monthly_approval_preview(preview.source_run_id, runtime=port)
    if (
        current.expected_checkpoint_id != preview.expected_checkpoint_id
        or current.review_content_hash != preview.review_content_hash
        or current.preview_content_hash != preview.preview_content_hash
    ):
        raise FinalConfirmError(CODE_STALE_APPROVAL_PREVIEW, STALE_PREVIEW_RU)
    if not current.readiness.ready:
        pending = current.readiness.unresolved_human_count
        if pending > 0:
            raise FinalConfirmError(CODE_NOT_READY, not_ready_message(pending))
        raise FinalConfirmError(
            CODE_NOT_READY,
            "Кандидатный состав нельзя подтвердить: нет позиций кандидата.",
        )
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise FinalConfirmError(CODE_FINAL_CONFIRM_BLOCKER, "approved_at must be timezone-aware")
    stamp = stamp.astimezone(timezone.utc)
    actor = str(approved_by or "").strip() or ACTOR_ID_HUMAN_SURFACE
    package_id = approval_identity(
        source_candidate_package_id=current.source_candidate_package_id,
        source_review_content_hash=current.review_content_hash,
        source_preview_content_hash=current.preview_content_hash,
    )
    digest = content_hash_for(
        project_code=current.project_code,
        month_key=current.month_key,
        queue=current.queue,
        source_run_id=current.source_run_id,
        source_candidate_package_id=current.source_candidate_package_id,
        source_review_content_hash=current.review_content_hash,
        source_preview_content_hash=current.preview_content_hash,
        professional_lines=current.professional_lines,
        summary_counts=current.summary,
    )
    artifact = ApprovedMonthlyPackage(
        schema_version=SCHEMA_VERSION,
        approved_package_id=package_id,
        project_code=current.project_code,
        month_key=current.month_key,
        queue=current.queue,
        source_run_id=current.source_run_id,
        source_candidate_package_id=current.source_candidate_package_id,
        source_review_content_hash=current.review_content_hash,
        source_preview_content_hash=current.preview_content_hash,
        source_checkpoint_id=current.expected_checkpoint_id,
        approved_at=stamp,
        approved_by=actor,
        status=STATUS_APPROVED,
        professional_lines=current.professional_lines,
        summary_counts=current.summary,
        content_hash=digest,
        provenance=PROVENANCE_HUMAN_SURFACE,
    )
    owned = store is None
    target = store if store is not None else _open_production_store()
    try:
        try:
            written = target.put_if_absent(artifact)
        except ApprovedMonthlyPackageStoreError as exc:
            raise FinalConfirmError(exc.code or CODE_APPROVED_STORE_CONFLICT, str(exc)) from exc
        readback = target.get_by_id(written.package.approved_package_id)
        _require_readback(readback, artifact)
        status = STATUS_CONFIRM_APPROVED if written.created else STATUS_CONFIRM_ALREADY
        return FinalConfirmResult(status=status, package=readback)
    finally:
        if owned:
            target.close()


def find_current_approved_package(
    run_id: str,
    *,
    runtime: Optional[HumanReviewRuntimePort] = None,
    store: Optional[ApprovedMonthlyPackageStore] = None,
) -> Optional[ApprovedMonthlyPackage]:
    """Read the approval that matches the current review snapshot. No writes."""
    try:
        preview = prepare_final_monthly_approval_preview(run_id, runtime=runtime)
    except Exception:
        return None
    owned = False
    target = store
    if target is None:
        path = _production_store_path()
        if not path.is_file():
            return None
        target = open_existing_approved_monthly_package_store(path)
        owned = True
        if target is None:
            return None
    try:
        return target.find_by_source_package_and_review_hash(
            source_candidate_package_id=preview.source_candidate_package_id,
            source_review_content_hash=preview.review_content_hash,
            source_preview_content_hash=preview.preview_content_hash,
        )
    finally:
        if owned and target is not None:
            target.close()


def _require_readback(
    readback: Optional[ApprovedMonthlyPackage],
    expected: ApprovedMonthlyPackage,
) -> None:
    if readback is None or readback.content_hash != expected.content_hash:
        raise FinalConfirmError(CODE_READBACK_MISMATCH, "approved package read-back mismatch")
    if (
        readback.source_candidate_package_id != expected.source_candidate_package_id
        or readback.source_review_content_hash != expected.source_review_content_hash
        or readback.source_preview_content_hash != expected.source_preview_content_hash
        or readback.source_checkpoint_id != expected.source_checkpoint_id
        or readback.source_run_id != expected.source_run_id
    ):
        raise FinalConfirmError(CODE_READBACK_MISMATCH, "approved package binding mismatch")


def _professional_lines(
    candidates: tuple[HumanReviewCandidateContext, ...],
    *,
    project_code: str,
    month_key: str,
) -> tuple[ApprovedMonthlyLine, ...]:
    rows: list[ApprovedMonthlyLine] = []
    for item in candidates:
        label = str(item.current_decision_label or "").strip() or STATUS_UNRESOLVED
        if label in {STATUS_EXCLUDED, STATUS_DEFERRED, STATUS_NEEDS_DATA, STATUS_UNRESOLVED}:
            continue
        if label not in {STATUS_ACCEPTED, STATUS_CHANGED}:
            continue
        baseline = _normalize(item.already_planned_qty)
        delta = _decision_qty(item)
        rows.append(
            ApprovedMonthlyLine(
                project_code=project_code,
                month_key=month_key,
                facility=item.facility or "—",
                discipline=item.discipline or "—",
                system=item.system or "—",
                iwp=item.iwp or "—",
                boq_code=item.boq_code or "—",
                name=item.name or "—",
                unit=item.unit or "—",
                baseline_qty=canonical_qty(baseline),
                constructor_delta_qty=canonical_qty(delta),
                final_qty=canonical_qty(baseline + delta),
                source_status=label,
                candidate_id=item.candidate_id,
            )
        )
    return tuple(_mark_ambiguous(rows))


def _mark_ambiguous(rows: list[ApprovedMonthlyLine]) -> list[ApprovedMonthlyLine]:
    counts: dict[tuple[str, str, str, str, str], int] = {}
    for row in rows:
        key = (row.facility, row.discipline, row.system, row.iwp, row.boq_code)
        counts[key] = counts.get(key, 0) + 1
    if not any(count > 1 for count in counts.values()):
        return rows
    marked: list[ApprovedMonthlyLine] = []
    for row in rows:
        key = (row.facility, row.discipline, row.system, row.iwp, row.boq_code)
        warning = IDENTITY_AMBIGUITY_WARNING_RU if counts[key] > 1 else ""
        marked.append(
            ApprovedMonthlyLine(
                project_code=row.project_code,
                month_key=row.month_key,
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
                identity_warning=warning,
            )
        )
    return marked


def _decision_qty(item: HumanReviewCandidateContext) -> float:
    if item.human_approved_qty is not None:
        return _normalize(item.human_approved_qty)
    return _normalize(item.constructor_proposed_qty)


def _normalize(value: object) -> float:
    number = float(value or 0.0)
    if abs(number) < _FLOAT_RESIDUE_ABS:
        return 0.0
    return number


def _optional_qty(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    return canonical_qty(value)


def _qty_positive(text: str) -> bool:
    return _normalize(text) > 0.0


def _authoritative_queue(lifecycle: ConstructorLifecycleState, candidates: tuple) -> Optional[str]:
    scope = lifecycle.scope
    if scope is not None and scope.queue_scope:
        values = tuple(str(item).strip() for item in scope.queue_scope if str(item).strip())
        if len(values) == 1:
            return values[0]
        return None
    queues = set()
    for item in candidates:
        queue = queue_from_facility(str(getattr(item, "facility", "") or ""))
        if not queue:
            return None
        queues.add(queue)
    if len(queues) == 1:
        return next(iter(queues))
    return None


def _production_store_path():
    from agents.control_room.constructor_professional_result_reader import (
        sibling_checkpoint_path,
    )
    from agents.control_room.factory import resolve_observability_db_path

    return sibling_checkpoint_path(resolve_observability_db_path()).parent / (
        "approved_monthly_packages.sqlite"
    )


def _open_production_store() -> ApprovedMonthlyPackageStore:
    return open_approved_monthly_package_store(_production_store_path())
