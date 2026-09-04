"""
Increment 11A — run-scoped real-data CandidateAssembler adapter.

Wires existing trusted reads + domain remainder truth into the existing
CandidateAssembler port. Does not change Constructor profession or core
contracts. ConstructorRealityRow remains identity-only.

Blind Shadow Phase A: existing month plan lines are never read.
already_planned_qty is therefore 0. That is experiment isolation, not a
redefinition of production planning semantics.

No product writes. No Supabase client. No global snapshot cache.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

import pandas as pd

from agents.monthly_plan_constructor.candidate_package import LABOR_UNRESOLVED
from agents.monthly_plan_constructor.domain import build_constructor_proposal
from agents.monthly_plan_constructor.lifecycle import CandidateAssemblyResult
from agents.monthly_plan_constructor.mission_scope import (
    ConstructorMissionScope,
    bind_scope_to_mission,
)
from agents.monthly_plan_constructor.secure_read_tools import (
    ConstructorRealityRead,
    ConstructorRealityRow,
    SecureReadError,
)
from security.agent_execution_context import AgentExecutionContext
from security.trusted_read_executor import (
    execute_constructor_adjustments_read,
    execute_constructor_scope_read,
)
from utils.month_key import normalize_month_key

CODE_ASSEMBLER_BLOCKER = "REAL_DATA_ASSEMBLER_BLOCKER"
CODE_SNAPSHOT_MISSING = "SNAPSHOT_MISSING"
CODE_SNAPSHOT_MISMATCH = "SNAPSHOT_MISMATCH"
CODE_ADJUSTMENTS_READ_FAILED = "ADJUSTMENTS_READ_FAILED"
CODE_DUPLICATE_CANDIDATE_ID = "DUPLICATE_CANDIDATE_ID"
CODE_DOMAIN_BLOCKER = "DOMAIN_BLOCKER"

_EMPTY_TOKENS = frozenset({"", "nan", "none", "<na>"})
_MAX_CANDIDATE_ID_LEN = 128
_SECRET_META_KEYS = frozenset(
    {
        "credential",
        "api_key",
        "apikey",
        "authorization",
        "password",
        "jwt",
        "secret",
        "supabase",
        "client",
    }
)


class RealDataAssemblerError(ValueError):
    """Fail-closed Shadow real-data assembly violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class _RunScopedSnapshot:
    mission: ConstructorMissionScope
    identity_keys: tuple[tuple[str, ...], ...]
    scope_frame: pd.DataFrame
    adjustments_frame: pd.DataFrame


def _cell(raw: Mapping[str, Any], *names: str) -> str:
    for name in names:
        if name not in raw:
            continue
        value = raw.get(name)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        text = str(value).strip()
        if text.lower() in _EMPTY_TOKENS:
            continue
        return text
    return ""


def _norm_part(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in _EMPTY_TOKENS:
        return ""
    return text.upper()


def _norm_month(value: Any) -> str:
    text = str(value or "").strip()
    canonical = normalize_month_key(text)
    if canonical:
        return canonical
    return _norm_part(text)


def _identity_from_mapping(
    raw: Mapping[str, Any],
    mission: ConstructorMissionScope,
) -> tuple[str, ...]:
    return (
        _norm_part(_cell(raw, "project_code") or mission.project_code),
        _norm_month(_cell(raw, "month_key") or mission.month_key),
        _norm_part(_cell(raw, "facility", "facility_building")),
        _norm_part(_cell(raw, "discipline", "construction_discipline")),
        _norm_part(_cell(raw, "system", "system_label")),
        _norm_part(_cell(raw, "iwp", "iwp_id")),
        _norm_part(_cell(raw, "queue", "construction_queue")),
        _norm_part(_cell(raw, "boq_code")),
    )


def _identity_from_reality_row(row: ConstructorRealityRow) -> tuple[str, ...]:
    return (
        _norm_part(row.project_code),
        _norm_month(row.month_key),
        _norm_part(row.facility),
        _norm_part(row.discipline),
        _norm_part(row.system),
        _norm_part(row.iwp),
        _norm_part(row.queue),
        _norm_part(row.boq_code),
    )


def _mission_identity(scope: ConstructorMissionScope) -> tuple[str, ...]:
    return (
        _norm_part(scope.project_code),
        _norm_month(scope.month_key_canonical or scope.month_key),
        tuple(scope.facility_scope or ()),
        tuple(scope.discipline_scope or ()),
        tuple(scope.system_scope or ()),
        tuple(scope.iwp_scope or ()),
        tuple(scope.queue_scope or ()),
    )


def _safe_read_meta(meta: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in meta.items():
        lowered = str(key).strip().lower()
        if any(token in lowered for token in _SECRET_META_KEYS):
            continue
        if lowered == "audit_event":
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[str(key)] = value
    return safe


def _raise_if_read_error(meta: Mapping[str, Any], *, code: str, label: str) -> None:
    error = meta.get("error")
    if error:
        raise SecureReadError(code, f"{label} failed: {error}")


def _candidate_id_from_grain(grain: tuple[str, ...]) -> str:
    joined = "|".join(grain)
    if len(joined) <= _MAX_CANDIDATE_ID_LEN:
        return joined
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _map_domain_candidate(
    candidate: Mapping[str, Any],
    scope: ConstructorMissionScope,
) -> dict[str, Any]:
    grain = (
        _norm_part(candidate.get("project_code") or scope.project_code),
        _norm_month(candidate.get("month_key") or scope.month_key),
        _norm_part(candidate.get("facility")),
        _norm_part(candidate.get("discipline")),
        _norm_part(candidate.get("system")),
        _norm_part(candidate.get("iwp")),
        "",
        _norm_part(candidate.get("boq_code")),
    )
    return {
        "candidate_id": _candidate_id_from_grain(grain),
        "project_code": str(candidate.get("project_code") or scope.project_code),
        "month_key": str(candidate.get("month_key") or scope.month_key),
        "facility": str(candidate.get("facility") or ""),
        "discipline": str(candidate.get("discipline") or ""),
        "system": str(candidate.get("system") or ""),
        "iwp": str(candidate.get("iwp") or ""),
        "queue": "",
        "boq_code": str(candidate.get("boq_code") or ""),
        "boq_name": str(candidate.get("boq_name") or ""),
        "unit": str(candidate.get("unit") or ""),
        "remaining_qty": candidate.get("remaining_qty"),
        "already_planned_qty": candidate.get("already_planned_qty"),
        "available_to_add_qty": candidate.get("available_to_add_qty"),
        "availability_status": str(candidate.get("availability_status") or ""),
        "labor_norm_status": LABOR_UNRESOLVED,
    }


def _require_proposal_ok(proposal: Mapping[str, Any]) -> None:
    errors = list(proposal.get("errors") or [])
    if errors or not proposal.get("ok"):
        raise RealDataAssemblerError(
            CODE_DOMAIN_BLOCKER,
            "build_constructor_proposal returned a non-OK result",
        )
    for issue in proposal.get("human_issues") or []:
        if str(issue.get("severity") or "").strip().upper() == "BLOCKER":
            raise RealDataAssemblerError(
                CODE_DOMAIN_BLOCKER,
                f"blocking domain issue {issue.get('code')}",
            )


class RealDataShadowAdapter:
    """
    One adapter instance = one run/composition.

    scope_reader captures a quantity-bearing snapshot after trusted reads.
    assemble_candidates / __call__ maps that snapshot through domain truth.
    """

    def __init__(self) -> None:
        self._snapshot: Optional[_RunScopedSnapshot] = None
        self._last_safe_scope_meta: dict[str, Any] = {}
        self._last_safe_adjustments_meta: dict[str, Any] = {}

    def scope_reader(
        self,
        context: AgentExecutionContext,
        mission: ConstructorMissionScope,
    ) -> Sequence[Mapping[str, Any]]:
        if context is None or not isinstance(context, AgentExecutionContext):
            raise SecureReadError("SECURITY_DENIED", "AgentExecutionContext is required")
        if not isinstance(mission, ConstructorMissionScope):
            raise SecureReadError(
                "DATA_CONTRACT_BLOCKER",
                "mission must be ConstructorMissionScope",
            )

        scope_frame, scope_meta = execute_constructor_scope_read(context)
        _raise_if_read_error(scope_meta, code="READ_FAILED", label="scope read")
        adjustments_frame, adjustments_meta = execute_constructor_adjustments_read(
            context
        )
        _raise_if_read_error(
            adjustments_meta,
            code=CODE_ADJUSTMENTS_READ_FAILED,
            label="adjustments read",
        )

        work = scope_frame.copy() if scope_frame is not None else pd.DataFrame()
        if "month_key" not in work.columns:
            work["month_key"] = mission.month_key
        scoped = bind_scope_to_mission(work, mission)
        records = scoped.to_dict(orient="records")
        identity_keys = tuple(_identity_from_mapping(row, mission) for row in records)

        self._snapshot = _RunScopedSnapshot(
            mission=mission,
            identity_keys=identity_keys,
            scope_frame=scoped.copy(),
            adjustments_frame=(
                adjustments_frame.copy()
                if adjustments_frame is not None
                else pd.DataFrame()
            ),
        )
        self._last_safe_scope_meta = _safe_read_meta(scope_meta)
        self._last_safe_adjustments_meta = _safe_read_meta(adjustments_meta)
        return records

    def assemble_candidates(
        self,
        reality_read: ConstructorRealityRead,
        scope: ConstructorMissionScope,
    ) -> CandidateAssemblyResult:
        snapshot = self._snapshot
        if snapshot is None:
            raise RealDataAssemblerError(
                CODE_SNAPSHOT_MISSING,
                "no run-scoped quantity snapshot has been captured",
            )
        if not isinstance(reality_read, ConstructorRealityRead):
            raise RealDataAssemblerError(
                CODE_ASSEMBLER_BLOCKER,
                "reality_read must be ConstructorRealityRead",
            )
        if not isinstance(scope, ConstructorMissionScope):
            raise RealDataAssemblerError(
                CODE_ASSEMBLER_BLOCKER,
                "scope must be ConstructorMissionScope",
            )
        self._assert_snapshot_matches(snapshot, reality_read, scope)

        proposal = build_constructor_proposal(
            snapshot.scope_frame,
            snapshot.adjustments_frame,
            pd.DataFrame(),
            scope.project_code,
            scope.month_key,
        )
        _require_proposal_ok(proposal)

        mapped: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in proposal.get("candidates") or []:
            if not isinstance(item, Mapping):
                raise RealDataAssemblerError(
                    CODE_ASSEMBLER_BLOCKER,
                    "domain candidate must be a mapping",
                )
            payload = _map_domain_candidate(item, scope)
            candidate_id = str(payload["candidate_id"])
            if candidate_id in seen_ids:
                raise RealDataAssemblerError(
                    CODE_DUPLICATE_CANDIDATE_ID,
                    f"duplicate candidate_id {candidate_id}",
                )
            seen_ids.add(candidate_id)
            mapped.append(payload)

        counts = proposal.get("counts") or {}
        return CandidateAssemblyResult(
            candidates=tuple(mapped),
            scanned_count=int(counts.get("scanned") or 0),
            excluded_completed_count=int(counts.get("excluded_completed") or 0),
            excluded_no_remainder_count=int(counts.get("excluded_no_remainder") or 0),
            already_planned_count=int(counts.get("excluded_already_planned") or 0),
        )

    def __call__(
        self,
        reality_read: ConstructorRealityRead,
        scope: ConstructorMissionScope,
    ) -> CandidateAssemblyResult:
        return self.assemble_candidates(reality_read, scope)

    def _assert_snapshot_matches(
        self,
        snapshot: _RunScopedSnapshot,
        reality_read: ConstructorRealityRead,
        scope: ConstructorMissionScope,
    ) -> None:
        if _mission_identity(snapshot.mission) != _mission_identity(scope):
            raise RealDataAssemblerError(
                CODE_SNAPSHOT_MISMATCH,
                "captured snapshot mission does not match assembly scope",
            )
        if _mission_identity(reality_read.scope) != _mission_identity(scope):
            raise RealDataAssemblerError(
                CODE_SNAPSHOT_MISMATCH,
                "reality_read.scope does not match assembly scope",
            )
        reality_keys = tuple(_identity_from_reality_row(row) for row in reality_read.rows)
        if sorted(reality_keys) != sorted(snapshot.identity_keys):
            raise RealDataAssemblerError(
                CODE_SNAPSHOT_MISMATCH,
                "captured snapshot identity does not match ConstructorRealityRead",
            )
