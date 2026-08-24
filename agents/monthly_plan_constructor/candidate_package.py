"""
Constructor Runtime v0.1 Increment 2 — Candidate Package artifact.

Structured business result for later Admission handoff.
Not a DataFrame, Streamlit table, or monthly-plan write.

package_id is a UUID generated at creation: the artifact is the result of one
Constructor computation. Rebuild after reality change → new package, not mutation.
Do not use Python hash() (process-unstable). Not tied to UI/session_state.

Physical available qty != resource-feasible qty != approved commitment qty.
Fail closed if any supplied candidate is outside the mission. No scope expansion.
Pure: no Streamlit, Supabase, HTTP, filesystem, LLM, shell, or writes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence, Union

import pandas as pd

from agents.monthly_plan_constructor.mission_scope import (
    CODE_DATA_CONTRACT_BLOCKER,
    ConstructorMissionScope,
    MissionScopeError,
    assert_rows_belong_to_mission_scope,
)

SCHEMA_VERSION = "1.0"
CONSTRUCTOR_AGENT_CODE = "MONTHLY_PLAN_CONSTRUCTOR"
CONSTRUCTOR_AGENT_VERSION = "0.1"

LABOR_VALIDATED = "VALIDATED"
LABOR_PROVISIONAL = "PROVISIONAL"
LABOR_UNRESOLVED = "UNRESOLVED"
LABOR_NOT_AVAILABLE = "NOT_AVAILABLE"
LABOR_STATUSES = frozenset(
    {LABOR_VALIDATED, LABOR_PROVISIONAL, LABOR_UNRESOLVED, LABOR_NOT_AVAILABLE}
)

CandidateInput = Union["CandidateRecord", Mapping[str, Any]]


class CandidatePackageError(ValueError):
    """Fail-closed Candidate Package contract violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _require_text(value: Any, field_name: str) -> str:
    if value is None:
        raise CandidatePackageError(
            CODE_DATA_CONTRACT_BLOCKER,
            f"{field_name} is required",
        )
    if isinstance(value, float) and pd.isna(value):
        raise CandidatePackageError(
            CODE_DATA_CONTRACT_BLOCKER,
            f"{field_name} is required",
        )
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        raise CandidatePackageError(
            CODE_DATA_CONTRACT_BLOCKER,
            f"{field_name} is required",
        )
    return text


def _optional_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>"}:
        return ""
    return text


def _require_finite_qty(value: Any, field_name: str) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise CandidatePackageError(
            CODE_DATA_CONTRACT_BLOCKER,
            f"{field_name} is required",
        )
    try:
        qty = float(value)
    except (TypeError, ValueError) as exc:
        raise CandidatePackageError(
            CODE_DATA_CONTRACT_BLOCKER,
            f"{field_name} must be numeric",
        ) from exc
    if qty != qty or qty in {float("inf"), float("-inf")}:
        raise CandidatePackageError(
            CODE_DATA_CONTRACT_BLOCKER,
            f"{field_name} must be finite",
        )
    return qty


def _optional_finite_qty(value: Any, default: float) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "<na>"}:
        return default
    return _require_finite_qty(value, "quantity")


def _labor_status(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return LABOR_UNRESOLVED
    text = str(value).strip().upper()
    if not text or text in {"NAN", "NONE", "<NA>"}:
        return LABOR_UNRESOLVED
    if text not in LABOR_STATUSES:
        raise CandidatePackageError(
            CODE_DATA_CONTRACT_BLOCKER,
            f"unknown labor_norm_status {text}",
        )
    return text


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _non_negative_int(value: Any, field_name: str) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise CandidatePackageError(
            CODE_DATA_CONTRACT_BLOCKER,
            f"{field_name} must be provided; counts are not manufactured",
        )
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise CandidatePackageError(
            CODE_DATA_CONTRACT_BLOCKER,
            f"{field_name} must be an integer",
        ) from exc
    if number < 0:
        raise CandidatePackageError(
            CODE_DATA_CONTRACT_BLOCKER,
            f"{field_name} must be >= 0",
        )
    return number


@dataclass(frozen=True)
class CandidateRecord:
    """
    One physical planning candidate.

    available_to_add_qty is Candidate Available Physical Quantity.
    It is not resource-feasible qty and not approved commitment qty.
    No crew, labor_hours, labor_cost, or unit_price on this record.
    """

    candidate_id: str
    project_code: str
    month_key: str
    facility: str
    discipline: str
    system: str
    iwp: str
    queue: str
    boq_code: str
    boq_name: str
    unit: str
    remaining_qty: float
    already_planned_qty: float
    available_to_add_qty: float
    availability_status: str
    labor_norm_status: str
    labor_norm_resolution_ref: Optional[str]
    source_snapshot_id: Optional[str]


@dataclass(frozen=True)
class CandidatePackageSummary:
    scanned_count: int
    candidate_count: int
    excluded_completed_count: int
    excluded_no_remainder_count: int
    already_planned_count: int


@dataclass(frozen=True)
class LaborNormSummary:
    validated: int
    provisional: int
    unresolved: int
    coverage_note: str


@dataclass(frozen=True)
class PackageExceptionSummary:
    blocking_count: int
    non_blocking_count: int
    warning_count: int


@dataclass(frozen=True)
class CandidatePackageProvenance:
    mission_id: str
    snapshot_id: Optional[str]
    agent_code: str
    agent_version: str
    created_at: str


@dataclass(frozen=True)
class CandidatePackageReference:
    """Bounded pointer for future graph state — not the full candidate list."""

    package_id: str
    schema_version: str
    project_code: str
    month_key: str
    candidate_count: int
    created_at: str


@dataclass(frozen=True)
class CandidatePackage:
    package_id: str
    schema_version: str
    mission_id: str
    run_id: Optional[str]
    project_code: str
    month_key: str
    scope: ConstructorMissionScope
    created_at: str
    summary: CandidatePackageSummary
    candidates: tuple[CandidateRecord, ...]
    provenance: CandidatePackageProvenance
    labor_norm_summary: LaborNormSummary
    exception_summary: PackageExceptionSummary

    @property
    def candidate_count(self) -> int:
        return self.summary.candidate_count

    def as_reference(self) -> CandidatePackageReference:
        return CandidatePackageReference(
            package_id=self.package_id,
            schema_version=self.schema_version,
            project_code=self.project_code,
            month_key=self.month_key,
            candidate_count=self.summary.candidate_count,
            created_at=self.created_at,
        )


def _normalize_candidate(
    item: CandidateInput,
    *,
    source_snapshot_id: Optional[str],
) -> CandidateRecord:
    if isinstance(item, CandidateRecord):
        data: Mapping[str, Any] = {
            f.name: getattr(item, f.name) for f in fields(item)
        }
    elif isinstance(item, Mapping):
        data = item
    else:
        raise CandidatePackageError(
            CODE_DATA_CONTRACT_BLOCKER,
            "candidate must be CandidateRecord or mapping",
        )

    available = _require_finite_qty(
        data.get("available_to_add_qty"),
        "available_to_add_qty",
    )
    remaining = _optional_finite_qty(data.get("remaining_qty"), available)
    already_planned = _optional_finite_qty(data.get("already_planned_qty"), 0.0)
    labor_ref = _optional_text(data.get("labor_norm_resolution_ref"))
    snapshot = _optional_text(data.get("source_snapshot_id")) or source_snapshot_id

    return CandidateRecord(
        candidate_id=_require_text(data.get("candidate_id"), "candidate_id"),
        project_code=_require_text(data.get("project_code"), "project_code"),
        month_key=_require_text(data.get("month_key"), "month_key"),
        facility=_optional_text(data.get("facility")),
        discipline=_optional_text(data.get("discipline")),
        system=_optional_text(data.get("system")),
        iwp=_optional_text(data.get("iwp")),
        queue=_optional_text(data.get("queue")),
        boq_code=_require_text(data.get("boq_code"), "boq_code"),
        boq_name=_optional_text(data.get("boq_name")),
        unit=_optional_text(data.get("unit")),
        remaining_qty=remaining,
        already_planned_qty=already_planned,
        available_to_add_qty=available,
        availability_status=_optional_text(data.get("availability_status")),
        labor_norm_status=_labor_status(data.get("labor_norm_status")),
        labor_norm_resolution_ref=labor_ref or None,
        source_snapshot_id=snapshot,
    )


def _scope_assertion_frame(candidates: Sequence[CandidateRecord]) -> pd.DataFrame:
    rows = []
    for item in candidates:
        rows.append(
            {
                "project_code": item.project_code,
                "month_key": item.month_key,
                "facility": item.facility,
                "facility_building": item.facility,
                "discipline": item.discipline,
                "construction_discipline": item.discipline,
                "system": item.system,
                "system_label": item.system,
                "iwp": item.iwp,
                "iwp_id": item.iwp,
                "construction_queue": item.queue,
                "queue": item.queue,
                "boq_code": item.boq_code,
            }
        )
    return pd.DataFrame(rows)


def _assert_candidates_in_scope(
    candidates: Sequence[CandidateRecord],
    scope: ConstructorMissionScope,
) -> None:
    if not candidates:
        return
    try:
        assert_rows_belong_to_mission_scope(_scope_assertion_frame(candidates), scope)
    except MissionScopeError as exc:
        raise CandidatePackageError(
            exc.code,
            "candidate outside mission scope; package construction fail closed",
        ) from exc


def _labor_summary(candidates: Sequence[CandidateRecord]) -> LaborNormSummary:
    validated = 0
    provisional = 0
    unresolved = 0
    for item in candidates:
        if item.labor_norm_status == LABOR_VALIDATED:
            validated += 1
        elif item.labor_norm_status == LABOR_PROVISIONAL:
            provisional += 1
        else:
            unresolved += 1
    return LaborNormSummary(
        validated=validated,
        provisional=provisional,
        unresolved=unresolved,
        coverage_note=(
            "UNRESOLVED/NOT_AVAILABLE does not remove a physical candidate"
        ),
    )


def build_candidate_package(
    scope: ConstructorMissionScope,
    candidates: Sequence[CandidateInput],
    *,
    mission_id: str,
    scanned_count: int,
    excluded_completed_count: int = 0,
    excluded_no_remainder_count: int = 0,
    already_planned_count: int = 0,
    run_id: Optional[str] = None,
    created_at: Optional[str] = None,
    snapshot_id: Optional[str] = None,
    agent_code: str = CONSTRUCTOR_AGENT_CODE,
    agent_version: str = CONSTRUCTOR_AGENT_VERSION,
    exception_summary: Optional[PackageExceptionSummary] = None,
) -> CandidatePackage:
    """
    Build an immutable Candidate Package from already scoped/classified records.

    Does not expand mission scope. Out-of-scope input fails closed (no filter-fallback).
    Does not mutate ``candidates``.
    """
    if not isinstance(scope, ConstructorMissionScope):
        raise CandidatePackageError(
            CODE_DATA_CONTRACT_BLOCKER,
            "scope must be ConstructorMissionScope",
        )
    if candidates is None or isinstance(candidates, (str, bytes)):
        raise CandidatePackageError(
            CODE_DATA_CONTRACT_BLOCKER,
            "candidates must be a sequence of records",
        )

    mission = _require_text(mission_id, "mission_id")
    scanned = _non_negative_int(scanned_count, "scanned_count")
    excluded_completed = _non_negative_int(
        excluded_completed_count, "excluded_completed_count"
    )
    excluded_no_remainder = _non_negative_int(
        excluded_no_remainder_count, "excluded_no_remainder_count"
    )
    already_planned = _non_negative_int(
        already_planned_count, "already_planned_count"
    )

    source_list = list(candidates)
    normalized: list[CandidateRecord] = [
        _normalize_candidate(item, source_snapshot_id=snapshot_id)
        for item in source_list
    ]

    seen_ids: set[str] = set()
    for item in normalized:
        if item.candidate_id in seen_ids:
            raise CandidatePackageError(
                CODE_DATA_CONTRACT_BLOCKER,
                f"duplicate candidate_id {item.candidate_id}",
            )
        seen_ids.add(item.candidate_id)

    _assert_candidates_in_scope(normalized, scope)

    candidate_count = len(normalized)
    if scanned < candidate_count:
        raise CandidatePackageError(
            CODE_DATA_CONTRACT_BLOCKER,
            "scanned_count cannot be less than candidate_count",
        )

    created = _optional_text(created_at) or _utc_now_iso()
    package_id = str(uuid.uuid4())
    frozen_candidates = tuple(normalized)
    summary = CandidatePackageSummary(
        scanned_count=scanned,
        candidate_count=candidate_count,
        excluded_completed_count=excluded_completed,
        excluded_no_remainder_count=excluded_no_remainder,
        already_planned_count=already_planned,
    )
    if summary.candidate_count != len(frozen_candidates):
        raise CandidatePackageError(
            CODE_DATA_CONTRACT_BLOCKER,
            "candidate_count must equal len(candidates)",
        )

    return CandidatePackage(
        package_id=package_id,
        schema_version=SCHEMA_VERSION,
        mission_id=mission,
        run_id=_optional_text(run_id) or None,
        project_code=scope.project_code,
        month_key=scope.month_key,
        scope=scope,
        created_at=created,
        summary=summary,
        candidates=frozen_candidates,
        provenance=CandidatePackageProvenance(
            mission_id=mission,
            snapshot_id=_optional_text(snapshot_id) or None,
            agent_code=_require_text(agent_code, "agent_code"),
            agent_version=_require_text(agent_version, "agent_version"),
            created_at=created,
        ),
        labor_norm_summary=_labor_summary(frozen_candidates),
        exception_summary=exception_summary
        or PackageExceptionSummary(
            blocking_count=0,
            non_blocking_count=0,
            warning_count=0,
        ),
    )
