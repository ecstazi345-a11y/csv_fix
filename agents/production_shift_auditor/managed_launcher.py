"""PSAA I1 — ManagedRuntimeLauncher binding for joint assess_shift.

Reuses existing Run Control Protocol. No LangGraph. No acceptance authority.
Process-local result cache — not production durable history.

Security boundary: get_result is an INTERNAL process-local accessor on this
launcher instance. Knowing a run_id alone is not an authorization grant.
Callers that hold project scope MUST pass project_code. This is not an
external/public query API and must not be published as one.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, Union

from agents.observability.contracts import (
    EventStatus,
    EventType,
    AgentRun,
    RunRequest,
    build_observability_event,
    _unfreeze_jsonable,
)
from agents.observability.durable_recorder import StoreObservabilityRecorder
from agents.observability.recorder import InMemoryObservabilityRecorder, ObservabilityRecorder
from agents.observability.sqlite_store import SqliteObservabilityStore
from agents.production_shift_auditor import AGENT_CODE, AGENT_VERSION
from agents.production_shift_auditor.contracts import ShiftAuditInput
from agents.production_shift_auditor.managed_run_contracts import (
    CODE_PSAA_AGENT_IDENTITY,
    CODE_PSAA_EXECUTION_FAILED,
    CODE_PSAA_INVALID_INPUT,
    CODE_PSAA_MANAGED_LAUNCHER_BLOCKER,
    CODE_PSAA_MISSING_SOURCE,
    CODE_PSAA_SCOPE_MISMATCH,
    PSAA_MONTH_KEY_COMPATIBILITY_SENTINEL,
    PsaaManagedCompletionStatus,
    PsaaManagedLauncherError,
    PsaaManagedRunResult,
)
from agents.production_shift_auditor.professional_assessment import (
    ShiftProfessionalAssessment,
    assess_shift,
)
from agents.production_shift_auditor.s04_contracts import LaborCostRateReference
from agents.production_shift_auditor.s04_execution_cost import (
    scenario_rate_1000_rub_per_man_hour,
)
from agents.run_control.contracts import ManagedRuntimeLauncher
from security.agent_execution_context import AgentExecutionContext

AuditInputResolver = Callable[
    [RunRequest, AgentRun, AgentExecutionContext],
    ShiftAuditInput,
]

# Explicit artifact durability labels for observability consumers.
_ARTIFACT_STORAGE_KIND = "PROCESS_LOCAL"
_ARTIFACT_DURABLE_PERSISTENCE = False
_ARTIFACT_REFERENCE_KIND = "PROCESS_LOCAL_SUMMARY_ONLY"


class PsaaManagedRuntimeLauncher:
    """
    PSAA-specific ManagedRuntimeLauncher.

    launch() accepts/schedules execution (thread by default). Successful return
    means launch acceptance only — not professional completion.
    """

    def __init__(
        self,
        *,
        audit_input_resolver: AuditInputResolver,
        observability_db_path: Union[str, Path, None] = None,
        recorder: Optional[ObservabilityRecorder] = None,
        cost_rates: Sequence[LaborCostRateReference] = (),
        assess_kwargs: Optional[Mapping[str, Any]] = None,
        sync_execution: bool = False,
        daemon: bool = False,
    ) -> None:
        if audit_input_resolver is None or not callable(audit_input_resolver):
            raise PsaaManagedLauncherError(
                CODE_PSAA_MANAGED_LAUNCHER_BLOCKER,
                "audit_input_resolver is required",
            )
        self._audit_input_resolver = audit_input_resolver
        self._observability_db_path = (
            str(observability_db_path) if observability_db_path is not None else None
        )
        self._external_recorder = recorder
        self._cost_rates = tuple(cost_rates) or (scenario_rate_1000_rub_per_man_hour(),)
        self._assess_kwargs = dict(assess_kwargs or {})
        self._sync_execution = bool(sync_execution)
        self._daemon = bool(daemon)
        self._results: dict[str, PsaaManagedRunResult] = {}
        self._lock = threading.RLock()
        self._threads: list[threading.Thread] = []

    def launch(
        self,
        *,
        run_request: RunRequest,
        agent_run: AgentRun,
        context: AgentExecutionContext,
    ) -> None:
        self._validate_launch_envelope(
            run_request=run_request,
            agent_run=agent_run,
            context=context,
        )
        if self._sync_execution:
            self._run_worker(run_request, agent_run, context)
            return
        worker = threading.Thread(
            target=self._run_worker,
            args=(run_request, agent_run, context),
            name=f"psaa-runtime-{agent_run.run_id}",
            daemon=self._daemon,
        )
        with self._lock:
            self._threads.append(worker)
        worker.start()

    def wait(self, timeout: Optional[float] = None) -> None:
        with self._lock:
            threads = list(self._threads)
        for thread in threads:
            thread.join(timeout=timeout)

    def get_result(
        self,
        run_id: str,
        *,
        project_code: Optional[str] = None,
    ) -> Optional[PsaaManagedRunResult]:
        """INTERNAL process-local accessor — not an authorized external API.

        Knowledge of run_id alone is NOT sufficient authorization for
        cross-project access. When project_code is provided, mismatches return
        None (fail closed). Callers with authorized project scope must pass it.
        """
        with self._lock:
            result = self._results.get(run_id)
            if result is None:
                return None
            if project_code is not None and result.project_code != project_code:
                return None
            return result

    def _validate_launch_envelope(
        self,
        *,
        run_request: RunRequest,
        agent_run: AgentRun,
        context: AgentExecutionContext,
    ) -> None:
        if run_request.agent_code != AGENT_CODE:
            raise PsaaManagedLauncherError(
                CODE_PSAA_AGENT_IDENTITY,
                f"agent_code must be {AGENT_CODE!r}",
            )
        if agent_run.agent_code != AGENT_CODE:
            raise PsaaManagedLauncherError(
                CODE_PSAA_AGENT_IDENTITY,
                f"agent_run.agent_code must be {AGENT_CODE!r}",
            )
        if context.agent_code != AGENT_CODE:
            raise PsaaManagedLauncherError(
                CODE_PSAA_AGENT_IDENTITY,
                f"context.agent_code must be {AGENT_CODE!r}",
            )
        if agent_run.run_id != context.run_id:
            raise PsaaManagedLauncherError(
                CODE_PSAA_MANAGED_LAUNCHER_BLOCKER,
                "agent_run.run_id must equal context.run_id",
            )
        if run_request.project_code != agent_run.project_code:
            raise PsaaManagedLauncherError(
                CODE_PSAA_SCOPE_MISMATCH,
                "run_request.project_code must equal agent_run.project_code",
            )
        if context.project_code != agent_run.project_code:
            raise PsaaManagedLauncherError(
                CODE_PSAA_SCOPE_MISMATCH,
                "context.project_code must equal agent_run.project_code",
            )
        if agent_run.mission_id != run_request.requested_mission_id:
            raise PsaaManagedLauncherError(
                CODE_PSAA_MANAGED_LAUNCHER_BLOCKER,
                "agent_run.mission_id must equal run_request.requested_mission_id",
            )
        if agent_run.authorization_id is not None:
            if context.authorization_id != agent_run.authorization_id:
                raise PsaaManagedLauncherError(
                    CODE_PSAA_MANAGED_LAUNCHER_BLOCKER,
                    "authorization_id mismatch between AgentRun and AgentExecutionContext",
                )
        if run_request.month_key != PSAA_MONTH_KEY_COMPATIBILITY_SENTINEL:
            # Soft warning path: still allow only the documented sentinel for PSAA
            raise PsaaManagedLauncherError(
                CODE_PSAA_MANAGED_LAUNCHER_BLOCKER,
                "PSAA managed runs must use NOT_A_PLANNING_MONTH month_key sentinel",
            )

    def _run_worker(
        self,
        run_request: RunRequest,
        agent_run: AgentRun,
        context: AgentExecutionContext,
    ) -> None:
        store: SqliteObservabilityStore | None = None
        recorder: ObservabilityRecorder
        owns_store = False
        try:
            if self._observability_db_path is not None:
                store = SqliteObservabilityStore(self._observability_db_path)
                owns_store = True
                recorder = StoreObservabilityRecorder(store)
            elif self._external_recorder is not None:
                recorder = self._external_recorder
            else:
                recorder = InMemoryObservabilityRecorder()

            self._emit(
                recorder,
                agent_run,
                EventType.RUN_ADVANCING,
                "PSAA managed professional execution advancing",
                detail={"stage": "source_and_scope_validation"},
            )

            try:
                audit_input = self._audit_input_resolver(run_request, agent_run, context)
            except PsaaManagedLauncherError as exc:
                self._fail(recorder, agent_run, run_request, exc.code, str(exc))
                return
            except Exception as exc:  # noqa: BLE001
                self._fail(
                    recorder,
                    agent_run,
                    run_request,
                    CODE_PSAA_MISSING_SOURCE,
                    f"source resolution failed: {exc}",
                )
                return

            try:
                audit_input = _validate_resolved_audit_input(
                    audit_input=audit_input,
                    run_request=run_request,
                    context=context,
                )
            except PsaaManagedLauncherError as exc:
                self._fail(recorder, agent_run, run_request, exc.code, str(exc))
                return

            self._emit(
                recorder,
                agent_run,
                EventType.STAGE_STARTED,
                "PSAA joint professional assessment started",
                detail={"stage": "assess_shift", "skills": "S01-S12"},
            )

            try:
                assessment = assess_shift(
                    audit_input,
                    audit_id=f"psaa_managed:{agent_run.run_id}",
                    run_id=agent_run.run_id,
                    cost_rates=self._cost_rates,
                    authorized_project_scopes=(context.project_code,),
                    **self._assess_kwargs,
                )
            except Exception as exc:  # noqa: BLE001
                self._fail(
                    recorder,
                    agent_run,
                    run_request,
                    CODE_PSAA_EXECUTION_FAILED,
                    f"assess_shift failed: {exc}",
                    detail={"traceback_tail": traceback.format_exc()[-400:]},
                )
                return

            try:
                result = _build_success_result(
                    run_request=run_request,
                    agent_run=agent_run,
                    assessment=assessment,
                )
                # Emit terminal success only after a professional result exists.
                # Publish process-local result only after RUN_COMPLETED is recorded
                # so a failed publication path cannot leave a false COMPLETED status
                # without a matching terminal event — and never emit RUN_COMPLETED
                # without a successfully built professional result.
                self._emit(
                    recorder,
                    agent_run,
                    EventType.STAGE_COMPLETED,
                    "PSAA joint professional assessment completed",
                    detail={
                        "stage": "assess_shift",
                        "audit_id": result.audit_id,
                        "skills_executed": 12,
                    },
                )
                artifact_detail = result.to_safe_summary()
                artifact_detail.update(
                    {
                        "storage_kind": _ARTIFACT_STORAGE_KIND,
                        "durable_persistence": _ARTIFACT_DURABLE_PERSISTENCE,
                        "artifact_reference_kind": _ARTIFACT_REFERENCE_KIND,
                        "production_artifact_verified": False,
                        "durable_professional_history": False,
                    }
                )
                self._emit(
                    recorder,
                    agent_run,
                    EventType.ARTIFACT_CREATED,
                    "PSAA process-local professional result summary (not durable history)",
                    artifact_type="PsaaManagedRunResult",
                    artifact_id=result.audit_id,
                    detail=artifact_detail,
                )
                self._emit(
                    recorder,
                    agent_run,
                    EventType.RUN_COMPLETED,
                    "PSAA managed run completed",
                    detail={
                        "professional_assessment_completed": True,
                        "professional_recommendation_generated": True,
                        "physical_execution_verified": False,
                        "managerial_acceptance_performed": False,
                        "durable_history_schema_unchanged": True,
                        "process_local_result": True,
                        "durable_professional_history": False,
                    },
                )
                with self._lock:
                    self._results[agent_run.run_id] = result
            except Exception as exc:  # noqa: BLE001
                self._fail(
                    recorder,
                    agent_run,
                    run_request,
                    CODE_PSAA_EXECUTION_FAILED,
                    f"result publication failed: {exc}",
                    detail={"traceback_tail": traceback.format_exc()[-400:]},
                )
                return
        finally:
            if owns_store and store is not None:
                store.close()

    def _fail(
        self,
        recorder: ObservabilityRecorder,
        agent_run: AgentRun,
        run_request: RunRequest,
        code: str,
        message: str,
        *,
        detail: Optional[Mapping[str, Any]] = None,
    ) -> None:
        scope = _scope_dict(run_request)
        failed = PsaaManagedRunResult(
            run_id=agent_run.run_id,
            request_id=run_request.request_id,
            agent_code=AGENT_CODE,
            agent_version=AGENT_VERSION,
            project_code=agent_run.project_code,
            mission_id=agent_run.mission_id,
            month_key_compatibility=PSAA_MONTH_KEY_COMPATIBILITY_SENTINEL,
            work_date=str(scope.get("work_date") or ""),
            crew_id=str(scope.get("crew_id") or ""),
            shift_type=scope.get("shift_type"),
            source_kind="UNKNOWN",
            source_record_ids=(),
            audit_id=f"failed:{agent_run.run_id}",
            completion_status=PsaaManagedCompletionStatus.FAILED,
            professional_assessment=None,
            claimed_labor_man_minutes=None,
            target_fund_man_minutes=None,
            scenario_direct_labor_cost_exact=None,
            unit_labor_observation_count=0,
            knowledge_candidate_count=0,
            verified_knowledge_count=0,
            approved_labor_norm_count=0,
            human_decision_required=False,
            shift_recommendation=None,
            evidence_authority_ceiling="NOT_ESTABLISHED",
            managerial_acceptance_status="NOT_PERFORMED",
            physical_execution_verified_status="PHYSICAL_EXECUTION_VERIFIED_NO",
            error_code=code,
            safe_error_summary=message[:500],
        )
        with self._lock:
            self._results[agent_run.run_id] = failed
        self._emit(
            recorder,
            agent_run,
            EventType.RUN_FAILED,
            "PSAA managed run failed",
            status=EventStatus.FAILED,
            detail={"error_code": code, "safe_error_summary": message[:200], **dict(detail or {})},
        )

    def _emit(
        self,
        recorder: ObservabilityRecorder,
        agent_run: AgentRun,
        event_type: EventType,
        title: str,
        *,
        status: EventStatus = EventStatus.OK,
        detail: Optional[Mapping[str, Any]] = None,
        artifact_type: Optional[str] = None,
        artifact_id: Optional[str] = None,
    ) -> None:
        event = build_observability_event(
            event_id=f"evt_{uuid.uuid4().hex[:16]}",
            run_id=agent_run.run_id,
            agent_code=AGENT_CODE,
            occurred_at=datetime.now(timezone.utc),
            event_type=event_type,
            status=status,
            title=title,
            request_id=agent_run.request_id,
            mission_id=agent_run.mission_id,
            authorization_id=agent_run.authorization_id,
            attempt_n=agent_run.attempt_n,
            resume_n=agent_run.resume_n,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            detail=dict(detail or {}),
        )
        recorder.record_event(event)


def _scope_dict(run_request: RunRequest) -> dict[str, Any]:
    raw = _unfreeze_jsonable(run_request.scope_request)
    return dict(raw) if isinstance(raw, dict) else {}


def fixed_audit_input_resolver(audit_input: ShiftAuditInput) -> AuditInputResolver:
    """Fixture/test helper — NOT a production trusted source adapter.

    Caller-supplied resolvers remain untrusted until they pass launcher
    validation of authorized project scope and declared shift grain.
    """

    def _resolve(
        run_request: RunRequest,
        agent_run: AgentRun,
        context: AgentExecutionContext,
    ) -> ShiftAuditInput:
        if audit_input.project_code != context.project_code:
            raise PsaaManagedLauncherError(
                CODE_PSAA_SCOPE_MISMATCH,
                "prebuilt audit_input project_code does not match authorized scope",
            )
        return audit_input

    return _resolve


def _validate_resolved_audit_input(
    *,
    audit_input: Any,
    run_request: RunRequest,
    context: AgentExecutionContext,
) -> ShiftAuditInput:
    """Enforce that resolved source cannot bypass authorized scope / grain."""
    if not isinstance(audit_input, ShiftAuditInput):
        raise PsaaManagedLauncherError(
            CODE_PSAA_INVALID_INPUT,
            "audit_input_resolver must return ShiftAuditInput",
        )
    if not audit_input.operations:
        raise PsaaManagedLauncherError(
            CODE_PSAA_INVALID_INPUT,
            "ShiftAuditInput.operations is empty",
        )
    if audit_input.project_code != context.project_code:
        raise PsaaManagedLauncherError(
            CODE_PSAA_SCOPE_MISMATCH,
            "audit_input.project_code does not match authorized project scope",
        )
    if audit_input.project_code != run_request.project_code:
        raise PsaaManagedLauncherError(
            CODE_PSAA_SCOPE_MISMATCH,
            "audit_input.project_code does not match run_request.project_code",
        )

    scope = _scope_dict(run_request)
    declared_work_date = scope.get("work_date")
    declared_crew_id = scope.get("crew_id")
    if declared_work_date is not None and str(declared_work_date) != str(
        audit_input.work_date
    ):
        raise PsaaManagedLauncherError(
            CODE_PSAA_SCOPE_MISMATCH,
            "audit_input.work_date does not match scope_request.work_date",
        )
    if declared_crew_id is not None and str(declared_crew_id) != str(audit_input.crew_id):
        raise PsaaManagedLauncherError(
            CODE_PSAA_SCOPE_MISMATCH,
            "audit_input.crew_id does not match scope_request.crew_id",
        )
    declared_shift_type = scope.get("shift_type")
    if (
        declared_shift_type is not None
        and audit_input.shift_type is not None
        and str(declared_shift_type) != str(audit_input.shift_type)
    ):
        raise PsaaManagedLauncherError(
            CODE_PSAA_SCOPE_MISMATCH,
            "audit_input.shift_type does not match scope_request.shift_type",
        )
    return audit_input


def _build_success_result(
    *,
    run_request: RunRequest,
    agent_run: AgentRun,
    assessment: ShiftProfessionalAssessment,
) -> PsaaManagedRunResult:
    s01 = assessment.s01
    s04 = assessment.s04
    s09 = assessment.s09
    s12 = assessment.s12
    shift_rec = None
    if s09.shift_summary is not None:
        shift_rec = s09.shift_summary.shift_level_recommendation.value
    return PsaaManagedRunResult(
        run_id=agent_run.run_id,
        request_id=run_request.request_id,
        agent_code=AGENT_CODE,
        agent_version=AGENT_VERSION,
        project_code=agent_run.project_code,
        mission_id=agent_run.mission_id,
        month_key_compatibility=PSAA_MONTH_KEY_COMPATIBILITY_SENTINEL,
        work_date=assessment.audit_input.work_date,
        crew_id=assessment.audit_input.crew_id,
        shift_type=assessment.audit_input.shift_type,
        source_kind=assessment.audit_input.source_kind.value,
        source_record_ids=tuple(assessment.audit_input.source_record_ids),
        audit_id=s01.audit_id,
        completion_status=PsaaManagedCompletionStatus.COMPLETED,
        professional_assessment=assessment,
        claimed_labor_man_minutes=s01.s01_metrics.claimed_total_man_minutes,
        target_fund_man_minutes=s01.s01_metrics.target_fund_man_minutes,
        scenario_direct_labor_cost_exact=(
            s04.cost_conservation.total_calculated_direct_labor_cost_exact
        ),
        unit_labor_observation_count=s12.shift_summary.unit_labor_observation_count,
        knowledge_candidate_count=s12.shift_summary.knowledge_candidate_count,
        verified_knowledge_count=s12.shift_summary.verified_knowledge_count,
        approved_labor_norm_count=s12.shift_summary.approved_labor_norm_count,
        human_decision_required=bool(s09.human_decision_required),
        shift_recommendation=shift_rec,
        evidence_authority_ceiling=s12.s08_authority_ceiling_status,
        managerial_acceptance_status=s12.managerial_acceptance_status,
        physical_execution_verified_status=s12.physical_execution_verified_status,
    )

