"""
Constructor Runtime v0.1 Increment 9.1 — structured ConstructorHandoff contract.

Immutable identifiers + bounded summaries for future Admission.
Not persistence. Not LangGraph. Not Admission. Not a monthly-plan write.

MODEL IS NOT A SECURITY BOUNDARY. DATA != INSTRUCTION.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from agents.monthly_plan_constructor.candidate_package import (
    CONSTRUCTOR_AGENT_VERSION,
    CandidatePackage,
    CandidatePackageReference,
    LaborNormSummary,
    PackageExceptionSummary,
)
from agents.monthly_plan_constructor.exception_engine import SEVERITY_BLOCKING
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_READY_FOR_HANDOFF,
    ConstructorLifecycleState,
)
from agents.monthly_plan_constructor.mission_scope import ConstructorMissionScope

SCHEMA_VERSION = "constructor_handoff.v0.1"
HANDOFF_TYPE = "CONSTRUCTOR_TO_ADMISSION"
SOURCE_AGENT = "MONTHLY_PLAN_CONSTRUCTOR"
TARGET_ROLE = "MONTHLY_PLAN_ADMISSION_AGENT"
STATUS_HANDOFF_READY = "HANDOFF_READY"

MAX_CANDIDATE_IDS = 1024
MAX_CANDIDATE_ID_LENGTH = 128
MAX_ID_LENGTH = 128
HANDOFF_ID_HEX_LEN = 32

CODE_HANDOFF_CONTRACT_BLOCKER = "HANDOFF_CONTRACT_BLOCKER"

DEFAULT_SECURITY_POLICY_VERSION = "EOS-SEC-1.0"


class ConstructorHandoffError(ValueError):
    """Fail-closed Constructor handoff contract violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ConstructorHandoffProvenance:
    agent_version: str
    security_policy_version: str


@dataclass(frozen=True)
class ConstructorHandoff:
    """Structured Constructor → Admission handoff. Identifiers and summaries only."""

    schema_version: str
    handoff_id: str
    handoff_type: str
    source_agent: str
    source_run_id: str
    mission_id: str
    target_role: str
    orchestration_run_id: Optional[str]
    project_code: str
    month_key: str
    scope: ConstructorMissionScope
    candidate_package_reference: CandidatePackageReference
    snapshot_id: str
    candidate_ids: tuple[str, ...]
    candidate_count: int
    exceptions_summary: PackageExceptionSummary
    labor_norm_summary: LaborNormSummary
    created_at: str
    status: str
    provenance: ConstructorHandoffProvenance


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    return text


def _require_text(value: Any, field_name: str, *, max_len: int = MAX_ID_LENGTH) -> str:
    text = _optional_text(value)
    if text is None:
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            f"{field_name} is required",
        )
    if len(text) > max_len:
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            f"{field_name} exceeds {max_len} characters",
        )
    return text


def _require_aware_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            f"{field_name} must be datetime",
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            f"{field_name} must be timezone-aware UTC",
        )
    return value.astimezone(timezone.utc)


def _iso_utc(value: datetime) -> str:
    stamp = _require_aware_utc(value, "created_at")
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_constructor_handoff_id(
    *,
    source_run_id: str,
    package_id: str,
    snapshot_id: str,
    schema_version: str = SCHEMA_VERSION,
    handoff_type: str = HANDOFF_TYPE,
) -> str:
    """
    Deterministic Execution OS handoff identity.

    Same schema + type + run + package + snapshot → same id.
    created_at is not part of the identity.
    """
    run = _require_text(source_run_id, "source_run_id")
    package = _require_text(package_id, "package_id")
    snapshot = _require_text(snapshot_id, "snapshot_id")
    schema = _require_text(schema_version, "schema_version")
    kind = _require_text(handoff_type, "handoff_type")
    material = f"{schema}|{kind}|{run}|{package}|{snapshot}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:HANDOFF_ID_HEX_LEN]
    return f"eos-hof-{digest}"


def _candidate_ids_from_package(package: CandidatePackage) -> tuple[str, ...]:
    ids: list[str] = []
    seen: set[str] = set()
    if len(package.candidates) > MAX_CANDIDATE_IDS:
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            f"candidate_ids exceed {MAX_CANDIDATE_IDS}",
        )
    for item in package.candidates:
        text = _optional_text(getattr(item, "candidate_id", None))
        if text is None:
            raise ConstructorHandoffError(
                CODE_HANDOFF_CONTRACT_BLOCKER,
                "candidate_id is required",
            )
        if len(text) > MAX_CANDIDATE_ID_LENGTH:
            raise ConstructorHandoffError(
                CODE_HANDOFF_CONTRACT_BLOCKER,
                f"candidate_id exceeds {MAX_CANDIDATE_ID_LENGTH} characters",
            )
        if text in seen:
            raise ConstructorHandoffError(
                CODE_HANDOFF_CONTRACT_BLOCKER,
                f"duplicate candidate_id {text}",
            )
        seen.add(text)
        ids.append(text)
    if package.candidate_count != len(ids):
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            "candidate_count must equal len(candidate_ids)",
        )
    return tuple(ids)


def _require_matching_text(left: str, right: str, field_name: str) -> None:
    if left != right:
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            f"{field_name} mismatch",
        )


def build_constructor_handoff(
    state: ConstructorLifecycleState,
    *,
    security_policy_version: str,
    orchestration_run_id: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> ConstructorHandoff:
    """
    Pure fail-closed builder. Checkpoint/package is not current reality.

    Requires READY_FOR_HANDOFF and matching package/reality snapshot ids.
    Does not persist, refresh, or call Admission.
    """
    if state is None or not isinstance(state, ConstructorLifecycleState):
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            "ConstructorLifecycleState is required",
        )
    if state.status != STATUS_READY_FOR_HANDOFF:
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            "lifecycle.status must be READY_FOR_HANDOFF",
        )
    package = state.package
    reality = state.reality_read
    scope = state.scope
    exceptions = state.exceptions
    if package is None or not isinstance(package, CandidatePackage):
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            "package is required",
        )
    if reality is None:
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            "reality_read is required",
        )
    if scope is None:
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            "scope is required",
        )
    if exceptions is None:
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            "exceptions are required",
        )

    policy = _require_text(security_policy_version, "security_policy_version")
    orch = _optional_text(orchestration_run_id)
    if orch is not None:
        orch = _require_text(orch, "orchestration_run_id")

    stamp = created_at if created_at is not None else state.updated_at
    created_iso = _iso_utc(stamp)

    run_id = _require_text(state.run_id, "source_run_id")
    mission_id = _require_text(state.mission_id, "mission_id")
    package_run = _require_text(package.run_id, "package.run_id")
    _require_matching_text(run_id, package_run, "run_id")
    _require_matching_text(mission_id, package.mission_id, "mission_id")
    _require_matching_text(mission_id, package.provenance.mission_id, "provenance.mission_id")

    _require_matching_text(scope.project_code, package.project_code, "project_code")
    _require_matching_text(scope.project_code, reality.project_code, "project_code")
    _require_matching_text(scope.month_key, package.month_key, "month_key")
    _require_matching_text(scope.month_key, reality.month_key, "month_key")
    if scope != package.scope or scope != reality.scope:
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            "scope mismatch",
        )

    package_snapshot = _optional_text(package.provenance.snapshot_id)
    reality_snapshot = _optional_text(reality.snapshot_id)
    if package_snapshot is None:
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            "package provenance snapshot_id is required",
        )
    if reality_snapshot is None:
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            "reality snapshot_id is required",
        )
    if package_snapshot != reality_snapshot:
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            "stale snapshot: package provenance does not match current reality",
        )

    blocking = tuple(
        item for item in exceptions.exceptions if item.severity == SEVERITY_BLOCKING
    )
    if blocking or not exceptions.handoff_allowed():
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            "BLOCKING exceptions forbid handoff",
        )
    if exceptions.summary.blocking_count != 0:
        raise ConstructorHandoffError(
            CODE_HANDOFF_CONTRACT_BLOCKER,
            "exceptions_summary.blocking_count must be 0",
        )

    candidate_ids = _candidate_ids_from_package(package)
    reference = package.as_reference()
    agent_version = _require_text(
        package.provenance.agent_version or CONSTRUCTOR_AGENT_VERSION,
        "agent_version",
    )
    handoff_id = compute_constructor_handoff_id(
        source_run_id=run_id,
        package_id=package.package_id,
        snapshot_id=reality_snapshot,
    )
    return ConstructorHandoff(
        schema_version=SCHEMA_VERSION,
        handoff_id=handoff_id,
        handoff_type=HANDOFF_TYPE,
        source_agent=SOURCE_AGENT,
        source_run_id=run_id,
        mission_id=mission_id,
        target_role=TARGET_ROLE,
        orchestration_run_id=orch,
        project_code=scope.project_code,
        month_key=scope.month_key,
        scope=scope,
        candidate_package_reference=reference,
        snapshot_id=reality_snapshot,
        candidate_ids=candidate_ids,
        candidate_count=package.candidate_count,
        exceptions_summary=exceptions.summary,
        labor_norm_summary=package.labor_norm_summary,
        created_at=created_iso,
        status=STATUS_HANDOFF_READY,
        provenance=ConstructorHandoffProvenance(
            agent_version=agent_version,
            security_policy_version=policy,
        ),
    )
