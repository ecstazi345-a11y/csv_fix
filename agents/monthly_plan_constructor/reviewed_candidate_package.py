"""
Constructor Reviewed Candidate Package V1 — pure deterministic artifact builder.

Inputs:
  CandidatePackage
  + ordered HumanReviewEvent sequence
  + authoritative ConstructorException sequence

Output:
  immutable ReviewedCandidatePackage with derived dispositions:
    INCLUDED | EXCLUDED | UNRESOLVED

Laws:
  Recommendation != Human Review
  Human Review != Effective Disposition
  Effective Disposition != Human Confirm
  Human Confirm != Handoff
  CAPABILITY != AUTHORITY

No lifecycle/HITL wiring. No persistence. No LLM. No product writes.
No wall-clock stamps and no random UUID inside the builder.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_NOT_AVAILABLE,
    LABOR_PROVISIONAL,
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
    CandidatePackage,
    CandidateRecord,
)
from agents.monthly_plan_constructor.exception_engine import (
    SEVERITY_BLOCKING,
    SEVERITY_NON_BLOCKING,
    SEVERITY_WARNING,
    ConstructorException,
)
from agents.monthly_plan_constructor.human_review_contracts import (
    HumanReviewDecision,
    HumanReviewEvent,
    normalize_human_review_events,
)

SCHEMA_VERSION = "1.0"
CODE_REVIEWED_PACKAGE_CONTRACT_BLOCKER = "REVIEWED_PACKAGE_CONTRACT_BLOCKER"

REASON_NO_HUMAN_REVIEW = "NO_HUMAN_REVIEW"
REASON_HUMAN_REMOVE = "HUMAN_REMOVE"
REASON_REQUIRES_CLARIFICATION = "REQUIRES_CLARIFICATION"
REASON_HUMAN_ADD = "HUMAN_ADD"
REASON_LABOR_VALIDATED = "LABOR_VALIDATED"
REASON_LABOR_PROVISIONAL = "LABOR_PROVISIONAL"
REASON_LABOR_NORM_UNRESOLVED = "LABOR_NORM_UNRESOLVED"
REASON_LABOR_NOT_AVAILABLE = "LABOR_NOT_AVAILABLE"


class ReviewedDisposition(str, Enum):
    """Derived professional disposition (not Confirm / handoff authority)."""

    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"
    UNRESOLVED = "UNRESOLVED"


class ReviewedPackageError(ValueError):
    """Fail-closed Reviewed Candidate Package contract violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ReviewedCandidateRecord:
    """One candidate after Human Review + professional pre-confirm gates."""

    candidate_id: str
    source_candidate: CandidateRecord
    human_review_decision: Optional[HumanReviewDecision]
    effective_review_event: Optional[HumanReviewEvent]
    disposition: ReviewedDisposition
    disposition_reason_codes: tuple[str, ...]
    blocking_exception_codes: tuple[str, ...]


@dataclass(frozen=True)
class ReviewedCandidatePackage:
    """
    Immutable Reviewed Candidate Package V1.

    Persistence: NOT IMPLEMENTED.
    Human Confirm / handoff: NOT IMPLEMENTED.
    """

    schema_version: str
    reviewed_package_id: str
    source_candidate_package_id: str
    run_id: str
    mission_id: str
    snapshot_id: Optional[str]
    review_projection_fingerprint: str
    exception_fingerprint: str
    reviewed_records: tuple[ReviewedCandidateRecord, ...]
    included_count: int
    excluded_count: int
    unresolved_count: int
    created_at: datetime


def _require_aware_utc(value: Any, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ReviewedPackageError(
            CODE_REVIEWED_PACKAGE_CONTRACT_BLOCKER,
            f"{field_name} must be datetime",
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReviewedPackageError(
            CODE_REVIEWED_PACKAGE_CONTRACT_BLOCKER,
            f"{field_name} must be timezone-aware UTC",
        )
    return value.astimezone(timezone.utc)


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    return text


def _require_package(package: Any) -> CandidatePackage:
    if not isinstance(package, CandidatePackage):
        raise ReviewedPackageError(
            CODE_REVIEWED_PACKAGE_CONTRACT_BLOCKER,
            "package must be CandidatePackage",
        )
    return package


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_hex(payload: Any) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return digest


def _review_event_canonical(event: HumanReviewEvent) -> dict[str, Any]:
    return {
        "schema_version": event.schema_version,
        "review_event_id": event.review_event_id,
        "run_id": event.run_id,
        "mission_id": event.mission_id,
        "package_id": event.package_id,
        "candidate_id": event.candidate_id,
        "decision": event.decision.value,
        "actor_type": event.actor_type,
        "actor_id": event.actor_id,
        "reviewed_at": event.reviewed_at.isoformat(),
    }


def _exception_canonical(item: ConstructorException) -> dict[str, Any]:
    return {
        "exception_id": item.exception_id,
        "exception_code": item.exception_code,
        "severity": item.severity,
        "route": item.route,
        "package_id": item.package_id or "",
        "candidate_id": item.candidate_id or "",
        "resolution_id": item.resolution_id or "",
        "reason": item.reason,
        "source_capability": item.source_capability,
        "observed_at": item.observed_at.isoformat(),
    }


def _summarize_exceptions(
    exceptions: Sequence[ConstructorException],
) -> tuple[int, int, int]:
    blocking = 0
    non_blocking = 0
    warning = 0
    for item in exceptions:
        if item.severity == SEVERITY_BLOCKING:
            blocking += 1
        elif item.severity == SEVERITY_NON_BLOCKING:
            non_blocking += 1
        elif item.severity == SEVERITY_WARNING:
            warning += 1
        else:
            raise ReviewedPackageError(
                CODE_REVIEWED_PACKAGE_CONTRACT_BLOCKER,
                f"unknown exception severity {item.severity!r}",
            )
    return blocking, non_blocking, warning


def _reconcile_exceptions(
    package: CandidatePackage,
    exceptions: Sequence[ConstructorException],
) -> tuple[ConstructorException, ...]:
    if exceptions is None or isinstance(exceptions, (str, bytes)):
        raise ReviewedPackageError(
            CODE_REVIEWED_PACKAGE_CONTRACT_BLOCKER,
            "exceptions must be a sequence of ConstructorException",
        )
    items: list[ConstructorException] = []
    candidate_ids = {c.candidate_id for c in package.candidates}
    for raw in exceptions:
        if not isinstance(raw, ConstructorException):
            raise ReviewedPackageError(
                CODE_REVIEWED_PACKAGE_CONTRACT_BLOCKER,
                "exceptions must contain ConstructorException only",
            )
        if raw.package_id is not None and raw.package_id != package.package_id:
            raise ReviewedPackageError(
                CODE_REVIEWED_PACKAGE_CONTRACT_BLOCKER,
                "exception.package_id mismatch with CandidatePackage",
            )
        cand = _optional_text(raw.candidate_id)
        if cand is not None and cand not in candidate_ids:
            raise ReviewedPackageError(
                CODE_REVIEWED_PACKAGE_CONTRACT_BLOCKER,
                f"orphan exception candidate_id {cand!r}",
            )
        items.append(raw)

    blocking, non_blocking, warning = _summarize_exceptions(items)
    summary = package.exception_summary
    if (
        summary.blocking_count != blocking
        or summary.non_blocking_count != non_blocking
        or summary.warning_count != warning
    ):
        raise ReviewedPackageError(
            CODE_REVIEWED_PACKAGE_CONTRACT_BLOCKER,
            "exception_summary mismatch with supplied ConstructorException set",
        )
    return tuple(items)


def _effective_review_events(
    normalized_events: Sequence[HumanReviewEvent],
) -> dict[str, HumanReviewEvent]:
    """Latest winning event per candidate_id; INPUT ORDER authoritative."""
    effective: dict[str, HumanReviewEvent] = {}
    for event in normalized_events:
        effective[event.candidate_id] = event
    return effective


def _build_review_projection_fingerprint(
    package: CandidatePackage,
    effective_by_candidate: Mapping[str, HumanReviewEvent],
) -> str:
    """
    Fingerprint of authoritative effective review state.

    Ordered by source CandidatePackage candidate order.
    Idempotent duplicate replay does not change effective winners.
    """
    rows: list[dict[str, Any]] = []
    for candidate in package.candidates:
        event = effective_by_candidate.get(candidate.candidate_id)
        if event is None:
            rows.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "decision": None,
                    "review_event": None,
                }
            )
        else:
            rows.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "decision": event.decision.value,
                    "review_event": _review_event_canonical(event),
                }
            )
    return _sha256_hex(
        {
            "source_candidate_package_id": package.package_id,
            "effective_reviews": rows,
        }
    )


def _build_exception_fingerprint(
    exceptions: Sequence[ConstructorException],
) -> str:
    rows = [_exception_canonical(item) for item in exceptions]
    # Sort for stability of unordered but equivalent sets; keep codes deterministic.
    rows_sorted = sorted(
        rows,
        key=lambda row: (
            row["exception_code"],
            row["candidate_id"],
            row["exception_id"],
            row["severity"],
        ),
    )
    return _sha256_hex({"exceptions": rows_sorted})


def _package_global_blocking_codes(
    exceptions: Sequence[ConstructorException],
) -> tuple[str, ...]:
    codes: list[str] = []
    for item in exceptions:
        if item.severity != SEVERITY_BLOCKING:
            continue
        if _optional_text(item.candidate_id) is not None:
            continue
        codes.append(item.exception_code)
    return tuple(dict.fromkeys(codes))


def _candidate_blocking_codes(
    exceptions: Sequence[ConstructorException],
    candidate_id: str,
) -> tuple[str, ...]:
    codes: list[str] = []
    for item in exceptions:
        if item.severity != SEVERITY_BLOCKING:
            continue
        if _optional_text(item.candidate_id) != candidate_id:
            continue
        codes.append(item.exception_code)
    return tuple(dict.fromkeys(codes))


def _dispose_candidate(
    candidate: CandidateRecord,
    *,
    effective_event: Optional[HumanReviewEvent],
    candidate_blocking: Sequence[str],
    package_blocking: Sequence[str],
) -> tuple[
    ReviewedDisposition,
    tuple[str, ...],
    tuple[str, ...],
    Optional[HumanReviewDecision],
]:
    decision = effective_event.decision if effective_event is not None else None
    blockers = tuple(dict.fromkeys([*candidate_blocking, *package_blocking]))

    if decision is None:
        return (
            ReviewedDisposition.UNRESOLVED,
            (REASON_NO_HUMAN_REVIEW,),
            blockers,
            None,
        )

    if decision == HumanReviewDecision.REMOVE:
        return (
            ReviewedDisposition.EXCLUDED,
            (REASON_HUMAN_REMOVE,),
            blockers,
            decision,
        )

    if decision == HumanReviewDecision.REQUIRES_CLARIFICATION:
        return (
            ReviewedDisposition.UNRESOLVED,
            (REASON_REQUIRES_CLARIFICATION,),
            blockers,
            decision,
        )

    if decision != HumanReviewDecision.ADD:
        raise ReviewedPackageError(
            CODE_REVIEWED_PACKAGE_CONTRACT_BLOCKER,
            f"unsupported human review decision {decision!r}",
        )

    # HUMAN ADD path — intent only until gates pass.
    labor = str(candidate.labor_norm_status or "").strip().upper()
    if labor == LABOR_UNRESOLVED:
        return (
            ReviewedDisposition.UNRESOLVED,
            (REASON_LABOR_NORM_UNRESOLVED,),
            blockers,
            decision,
        )
    if labor == LABOR_NOT_AVAILABLE:
        return (
            ReviewedDisposition.UNRESOLVED,
            (REASON_LABOR_NOT_AVAILABLE,),
            blockers,
            decision,
        )
    if blockers:
        return (
            ReviewedDisposition.UNRESOLVED,
            tuple(blockers),
            blockers,
            decision,
        )
    if labor == LABOR_VALIDATED:
        return (
            ReviewedDisposition.INCLUDED,
            (REASON_HUMAN_ADD, REASON_LABOR_VALIDATED),
            (),
            decision,
        )
    if labor == LABOR_PROVISIONAL:
        return (
            ReviewedDisposition.INCLUDED,
            (REASON_HUMAN_ADD, REASON_LABOR_PROVISIONAL),
            (),
            decision,
        )
    raise ReviewedPackageError(
        CODE_REVIEWED_PACKAGE_CONTRACT_BLOCKER,
        f"unsupported labor_norm_status for reviewed disposition: {labor!r}",
    )


def build_reviewed_candidate_package(
    package: CandidatePackage,
    review_events: Sequence[HumanReviewEvent],
    exceptions: Sequence[ConstructorException],
    *,
    created_at: datetime,
) -> ReviewedCandidatePackage:
    """
    Build immutable Reviewed Candidate Package V1.

    Uses Human Review Contract normalization as sole review authority.
    Consumes ConstructorException severity; does not reclassify it.
    """
    source = _require_package(package)
    run_id = _optional_text(source.run_id)
    if run_id is None:
        raise ReviewedPackageError(
            CODE_REVIEWED_PACKAGE_CONTRACT_BLOCKER,
            "package.run_id is required to build Reviewed Candidate Package",
        )
    stamp = _require_aware_utc(created_at, "created_at")

    normalized_reviews = normalize_human_review_events(review_events, source)
    effective_by_candidate = _effective_review_events(normalized_reviews)
    exception_items = _reconcile_exceptions(source, exceptions)

    review_fp = _build_review_projection_fingerprint(source, effective_by_candidate)
    exception_fp = _build_exception_fingerprint(exception_items)
    package_blockers = _package_global_blocking_codes(exception_items)

    records: list[ReviewedCandidateRecord] = []
    included = 0
    excluded = 0
    unresolved = 0
    for candidate in source.candidates:
        event = effective_by_candidate.get(candidate.candidate_id)
        cand_blockers = _candidate_blocking_codes(
            exception_items, candidate.candidate_id
        )
        disposition, reasons, blockers, decision = _dispose_candidate(
            candidate,
            effective_event=event,
            candidate_blocking=cand_blockers,
            package_blocking=package_blockers,
        )
        if disposition == ReviewedDisposition.INCLUDED:
            included += 1
        elif disposition == ReviewedDisposition.EXCLUDED:
            excluded += 1
        else:
            unresolved += 1
        records.append(
            ReviewedCandidateRecord(
                candidate_id=candidate.candidate_id,
                source_candidate=candidate,
                human_review_decision=decision,
                effective_review_event=event,
                disposition=disposition,
                disposition_reason_codes=reasons,
                blocking_exception_codes=blockers,
            )
        )

    reviewed_package_id = _sha256_hex(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact": "ReviewedCandidatePackage",
            "source_candidate_package_id": source.package_id,
            "review_projection_fingerprint": review_fp,
            "exception_fingerprint": exception_fp,
        }
    )

    if included + excluded + unresolved != len(records):
        raise ReviewedPackageError(
            CODE_REVIEWED_PACKAGE_CONTRACT_BLOCKER,
            "disposition counts must equal reviewed record count",
        )

    return ReviewedCandidatePackage(
        schema_version=SCHEMA_VERSION,
        reviewed_package_id=reviewed_package_id,
        source_candidate_package_id=source.package_id,
        run_id=run_id,
        mission_id=source.mission_id,
        snapshot_id=source.provenance.snapshot_id,
        review_projection_fingerprint=review_fp,
        exception_fingerprint=exception_fp,
        reviewed_records=tuple(records),
        included_count=included,
        excluded_count=excluded,
        unresolved_count=unresolved,
        created_at=stamp,
    )
