"""PSAA I1 — managed-run contracts (process-local result envelope).

Compatible with existing Run Control / Observability. Does not extend durable
history schema. Does not grant acceptance authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping, Optional

from agents.production_shift_auditor import AGENT_CODE, AGENT_VERSION
from agents.production_shift_auditor.professional_assessment import (
    ShiftProfessionalAssessment,
)
from agents.run_control.contracts import (
    CODE_RUN_CONTROL_BLOCKER,
    ManagedRunStartInput,
    RunControlError,
)
from agents.observability.contracts import InitiatorType, TriggerType

# Compatibility carrier for ManagedRunStartInput.month_key when planning-month
# semantics do not apply. Validated only as non-empty text by Run Control /
# observability — NOT a Constructor planning month, NOT a calendar production
# planning period. Shift grain lives in scope_request.
PSAA_MONTH_KEY_COMPATIBILITY_SENTINEL = "NOT_A_PLANNING_MONTH"

CODE_PSAA_MANAGED_LAUNCHER_BLOCKER = "PSAA_MANAGED_LAUNCHER_BLOCKER"
CODE_PSAA_SCOPE_MISMATCH = "PSAA_SCOPE_MISMATCH"
CODE_PSAA_INVALID_INPUT = "PSAA_INVALID_INPUT"
CODE_PSAA_MISSING_SOURCE = "PSAA_MISSING_SOURCE"
CODE_PSAA_AGENT_IDENTITY = "PSAA_AGENT_IDENTITY"
CODE_PSAA_EXECUTION_FAILED = "PSAA_EXECUTION_FAILED"


class PsaaManagedCompletionStatus(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PsaaManagedLauncherError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class PsaaManagedRunResult:
    """Process-local managed professional result. NOT production durable history."""

    run_id: str
    request_id: str
    agent_code: str
    agent_version: str
    project_code: str
    mission_id: str
    month_key_compatibility: str
    work_date: str
    crew_id: str
    shift_type: Optional[str]
    source_kind: str
    source_record_ids: tuple[str, ...]
    audit_id: str
    completion_status: PsaaManagedCompletionStatus
    professional_assessment: Optional[ShiftProfessionalAssessment]
    claimed_labor_man_minutes: Optional[float]
    target_fund_man_minutes: Optional[float]
    scenario_direct_labor_cost_exact: Optional[str]
    unit_labor_observation_count: int
    knowledge_candidate_count: int
    verified_knowledge_count: int
    approved_labor_norm_count: int
    human_decision_required: bool
    shift_recommendation: Optional[str]
    evidence_authority_ceiling: str
    managerial_acceptance_status: str
    physical_execution_verified_status: str
    error_code: Optional[str] = None
    safe_error_summary: Optional[str] = None
    artifact_schema_note: str = (
        "joint_ShiftProfessionalAssessment_process_local_v0.1_not_durable_history"
    )

    def to_safe_summary(self) -> dict[str, Any]:
        """Bounded summary safe for observability detail / Query Port refs."""
        # Prefer strings/ints/bools — observability detail rejects unbounded floats.
        return {
            "agent_code": self.agent_code,
            "project_code": self.project_code,
            "work_date": self.work_date,
            "crew_id": self.crew_id,
            "audit_id": self.audit_id,
            "completion_status": self.completion_status.value,
            "claimed_labor_man_minutes": (
                None
                if self.claimed_labor_man_minutes is None
                else str(self.claimed_labor_man_minutes)
            ),
            "target_fund_man_minutes": (
                None
                if self.target_fund_man_minutes is None
                else str(self.target_fund_man_minutes)
            ),
            "scenario_direct_labor_cost_exact": self.scenario_direct_labor_cost_exact,
            "unit_labor_observation_count": self.unit_labor_observation_count,
            "knowledge_candidate_count": self.knowledge_candidate_count,
            "verified_knowledge_count": self.verified_knowledge_count,
            "approved_labor_norm_count": self.approved_labor_norm_count,
            "human_decision_required": self.human_decision_required,
            "shift_recommendation": self.shift_recommendation,
            "evidence_authority_ceiling": self.evidence_authority_ceiling,
            "managerial_acceptance_status": self.managerial_acceptance_status,
            "physical_execution_verified_status": self.physical_execution_verified_status,
            "month_key_compatibility": self.month_key_compatibility,
            "error_code": self.error_code,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        # Full assessment is large; expose via professional_assessment field object
        if self.professional_assessment is not None:
            payload["professional_assessment"] = {
                "s01": self.professional_assessment.s01.to_dict(),
                "s10": self.professional_assessment.s10.to_dict(),
                "s02": self.professional_assessment.s02.to_dict(),
                "s03": self.professional_assessment.s03.to_dict(),
                "s11": self.professional_assessment.s11.to_dict(),
                "s04": self.professional_assessment.s04.to_dict(),
                "s05": self.professional_assessment.s05.to_dict(),
                "s06": self.professional_assessment.s06.to_dict(),
                "s07": self.professional_assessment.s07.to_dict(),
                "s08": self.professional_assessment.s08.to_dict(),
                "s09": self.professional_assessment.s09.to_dict(),
                "s12": self.professional_assessment.s12.to_dict(),
            }
        payload["completion_status"] = self.completion_status.value
        return payload


def build_psaa_managed_start_input(
    *,
    project_code: str,
    work_date: str,
    crew_id: str,
    requested_mission_id: str,
    idempotency_key: str,
    initiator_id: str = "operator-local",
    shift_type: Optional[str] = None,
    trigger_reason: str = "psaa-managed-start",
    scope_extra: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> ManagedRunStartInput:
    """Build ManagedRunStartInput for PSAA without inventing a planning month."""
    scope: dict[str, Any] = {
        "execution_contour": "EXECUTION",
        "grain": "SHIFT",
        "work_date": work_date,
        "crew_id": crew_id,
        "month_key_semantics": "NOT_A_PLANNING_MONTH",
        "month_key_compatibility_sentinel": PSAA_MONTH_KEY_COMPATIBILITY_SENTINEL,
    }
    if shift_type is not None:
        scope["shift_type"] = shift_type
    if scope_extra:
        scope.update(dict(scope_extra))
    try:
        return ManagedRunStartInput(
            agent_code=AGENT_CODE,
            initiator_type=InitiatorType.HUMAN,
            initiator_id=initiator_id,
            trigger_type=TriggerType.MANUAL,
            trigger_reason=trigger_reason,
            project_code=project_code,
            month_key=PSAA_MONTH_KEY_COMPATIBILITY_SENTINEL,
            requested_mission_id=requested_mission_id,
            idempotency_key=idempotency_key,
            scope_request=scope,
            requested_agent_version=AGENT_VERSION,
            metadata=dict(metadata or {"source": "psaa_managed_run_v0.1"}),
        )
    except RunControlError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RunControlError(CODE_RUN_CONTROL_BLOCKER, str(exc)) from exc
