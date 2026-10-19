"""
Immutable Approved Monthly Package.

Confirms one package-wide professional snapshot.
Not a HumanConfirmEvent and not a ReviewedCandidatePackage.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

SCHEMA_VERSION = "1.0"
STATUS_APPROVED = "APPROVED"
PROVENANCE_HUMAN_SURFACE = "HUMAN_SURFACE_FINAL_CONFIRM"

CODE_APPROVED_PACKAGE_BLOCKER = "APPROVED_PACKAGE_BLOCKER"


class ApprovedMonthlyPackageError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ApprovedMonthlyLine:
    project_code: str
    month_key: str
    facility: str
    discipline: str
    system: str
    iwp: str
    boq_code: str
    name: str
    unit: str
    baseline_qty: str
    constructor_delta_qty: str
    final_qty: str
    source_status: str
    candidate_id: str
    identity_warning: str = ""


@dataclass(frozen=True)
class ApprovedMonthlySummary:
    final_positions: int
    baseline_positions: int
    constructor_additions: int
    changed_qty: int
    accepted: int
    excluded: int
    deferred: int
    unresolved: int
    needs_data: int


@dataclass(frozen=True)
class ApprovedMonthlyPackage:
    schema_version: str
    approved_package_id: str
    project_code: str
    month_key: str
    queue: Optional[str]
    source_run_id: str
    source_candidate_package_id: str
    source_review_content_hash: str
    source_preview_content_hash: str
    source_checkpoint_id: str
    approved_at: datetime
    approved_by: str
    status: str
    professional_lines: tuple[ApprovedMonthlyLine, ...]
    summary_counts: ApprovedMonthlySummary
    content_hash: str
    provenance: str


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def line_payload(line: ApprovedMonthlyLine) -> dict[str, str]:
    return {
        "project_code": line.project_code,
        "month_key": line.month_key,
        "facility": line.facility,
        "discipline": line.discipline,
        "system": line.system,
        "iwp": line.iwp,
        "boq_code": line.boq_code,
        "name": line.name,
        "unit": line.unit,
        "baseline_qty": line.baseline_qty,
        "constructor_delta_qty": line.constructor_delta_qty,
        "final_qty": line.final_qty,
        "source_status": line.source_status,
        "candidate_id": line.candidate_id,
        "identity_warning": line.identity_warning,
    }


def summary_payload(summary: ApprovedMonthlySummary) -> dict[str, int]:
    return {
        "final_positions": summary.final_positions,
        "baseline_positions": summary.baseline_positions,
        "constructor_additions": summary.constructor_additions,
        "changed_qty": summary.changed_qty,
        "accepted": summary.accepted,
        "excluded": summary.excluded,
        "deferred": summary.deferred,
        "unresolved": summary.unresolved,
        "needs_data": summary.needs_data,
    }


def approval_identity(
    *,
    source_candidate_package_id: str,
    source_review_content_hash: str,
    source_preview_content_hash: str,
) -> str:
    digest = sha256_hex(
        {
            "source_candidate_package_id": source_candidate_package_id,
            "source_review_content_hash": source_review_content_hash,
            "source_preview_content_hash": source_preview_content_hash,
        }
    )
    return f"amp-{digest[:32]}"


def content_hash_for(
    *,
    project_code: str,
    month_key: str,
    queue: Optional[str],
    source_run_id: str,
    source_candidate_package_id: str,
    source_review_content_hash: str,
    source_preview_content_hash: str,
    professional_lines: Sequence[ApprovedMonthlyLine],
    summary_counts: ApprovedMonthlySummary,
) -> str:
    return sha256_hex(
        {
            "schema_version": SCHEMA_VERSION,
            "project_code": project_code,
            "month_key": month_key,
            "queue": queue,
            "source_run_id": source_run_id,
            "source_candidate_package_id": source_candidate_package_id,
            "source_review_content_hash": source_review_content_hash,
            "source_preview_content_hash": source_preview_content_hash,
            "professional_lines": [line_payload(item) for item in professional_lines],
            "summary_counts": summary_payload(summary_counts),
        }
    )


def package_to_payload(package: ApprovedMonthlyPackage) -> dict[str, Any]:
    return {
        "schema_version": package.schema_version,
        "approved_package_id": package.approved_package_id,
        "project_code": package.project_code,
        "month_key": package.month_key,
        "queue": package.queue,
        "source_run_id": package.source_run_id,
        "source_candidate_package_id": package.source_candidate_package_id,
        "source_review_content_hash": package.source_review_content_hash,
        "source_preview_content_hash": package.source_preview_content_hash,
        "source_checkpoint_id": package.source_checkpoint_id,
        "approved_at": package.approved_at.astimezone(timezone.utc).isoformat(),
        "approved_by": package.approved_by,
        "status": package.status,
        "professional_lines": [line_payload(item) for item in package.professional_lines],
        "summary_counts": summary_payload(package.summary_counts),
        "content_hash": package.content_hash,
        "provenance": package.provenance,
    }


def package_from_payload(payload: dict[str, Any]) -> ApprovedMonthlyPackage:
    lines = tuple(
        ApprovedMonthlyLine(
            project_code=str(item["project_code"]),
            month_key=str(item["month_key"]),
            facility=str(item["facility"]),
            discipline=str(item["discipline"]),
            system=str(item["system"]),
            iwp=str(item["iwp"]),
            boq_code=str(item["boq_code"]),
            name=str(item["name"]),
            unit=str(item["unit"]),
            baseline_qty=str(item["baseline_qty"]),
            constructor_delta_qty=str(item["constructor_delta_qty"]),
            final_qty=str(item["final_qty"]),
            source_status=str(item["source_status"]),
            candidate_id=str(item["candidate_id"]),
            identity_warning=str(item.get("identity_warning") or ""),
        )
        for item in payload["professional_lines"]
    )
    counts = payload["summary_counts"]
    summary = ApprovedMonthlySummary(
        final_positions=int(counts["final_positions"]),
        baseline_positions=int(counts["baseline_positions"]),
        constructor_additions=int(counts["constructor_additions"]),
        changed_qty=int(counts["changed_qty"]),
        accepted=int(counts["accepted"]),
        excluded=int(counts["excluded"]),
        deferred=int(counts["deferred"]),
        unresolved=int(counts["unresolved"]),
        needs_data=int(counts["needs_data"]),
    )
    approved_at = datetime.fromisoformat(str(payload["approved_at"]))
    if approved_at.tzinfo is None:
        raise ApprovedMonthlyPackageError(
            CODE_APPROVED_PACKAGE_BLOCKER,
            "approved_at must be timezone-aware",
        )
    return ApprovedMonthlyPackage(
        schema_version=str(payload["schema_version"]),
        approved_package_id=str(payload["approved_package_id"]),
        project_code=str(payload["project_code"]),
        month_key=str(payload["month_key"]),
        queue=payload.get("queue"),
        source_run_id=str(payload["source_run_id"]),
        source_candidate_package_id=str(payload["source_candidate_package_id"]),
        source_review_content_hash=str(payload["source_review_content_hash"]),
        source_preview_content_hash=str(payload["source_preview_content_hash"]),
        source_checkpoint_id=str(payload["source_checkpoint_id"]),
        approved_at=approved_at.astimezone(timezone.utc),
        approved_by=str(payload["approved_by"]),
        status=str(payload["status"]),
        professional_lines=lines,
        summary_counts=summary,
        content_hash=str(payload["content_hash"]),
        provenance=str(payload["provenance"]),
    )
