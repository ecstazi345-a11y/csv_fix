"""
Increment 10.2 — Run Control service.

Owns request_id / run_id minting, idempotency, authorization, Class A events,
and managed runtime launcher handoff. Agent-neutral. Not durable.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from agents.observability.contracts import (
    EventStatus,
    EventType,
    OperationalStatus,
    TriggerType,
    build_agent_run,
    build_observability_event,
    build_run_request,
    compute_run_request_digest,
)
from agents.observability.recorder import ObservabilityRecorder
from agents.run_control.contracts import (
    CODE_CONTROL_PLANE_FAILURE,
    CODE_LAUNCH_OUTCOME_UNKNOWN,
    CODE_RUN_CONTROL_BLOCKER,
    CODE_SYSTEM_EVENT_DIRECT_START_FORBIDDEN,
    ManagedRunStartInput,
    ManagedRunStartResult,
    ManagedRuntimeLauncher,
    ReservationKind,
    RunControlError,
    RunControlRegistry,
    StartOutcome,
    TerminalFailureKind,
    TerminalFailureRecord,
)
from security.agent_execution_context import (
    ContextIssueError,
    issue_read_only_agent_context,
)

_AGENT_VERSION_DEFAULT = "0.1"


class RunControlService:
    """
    Process-local managed start coordinator.

    NON-DURABLE. Restart loses idempotency registry state (10.4 later).
    """

    def __init__(
        self,
        *,
        registry: RunControlRegistry,
        recorder: ObservabilityRecorder,
    ) -> None:
        if registry is None:
            raise RunControlError(CODE_RUN_CONTROL_BLOCKER, "RunControlRegistry is required")
        if recorder is None:
            raise RunControlError(CODE_RUN_CONTROL_BLOCKER, "ObservabilityRecorder is required")
        self._registry = registry
        self._recorder = recorder

    def start(
        self,
        start_input: ManagedRunStartInput,
        *,
        launcher: ManagedRuntimeLauncher,
        requested_at: Optional[datetime] = None,
    ) -> ManagedRunStartResult:
        self._reject_system_event_direct_start(start_input)

        stamp = _require_aware_utc(requested_at or _utc_now())
        digest = compute_run_request_digest(
            agent_code=start_input.agent_code,
            initiator_type=start_input.initiator_type,
            initiator_id=start_input.initiator_id,
            project_code=start_input.project_code,
            month_key=start_input.month_key,
            scope_request=dict(start_input.scope_request or {}),
            requested_mission_id=start_input.requested_mission_id,
            orchestration_run_id=start_input.orchestration_run_id,
            predecessor_run_id=start_input.predecessor_run_id,
            trigger_type=start_input.trigger_type,
        )

        candidate_request_id = _mint_id("req")
        candidate_run_id = _mint_id("run")
        decision = self._registry.decide_reservation(
            idempotency_key=start_input.idempotency_key,
            canonical_request_digest=digest,
            candidate_request_id=candidate_request_id,
            candidate_run_id=candidate_run_id,
        )

        if decision.kind is ReservationKind.IDEMPOTENT_REPLAY:
            cached = self._registry.get_cached_result(
                idempotency_key=start_input.idempotency_key,
                canonical_request_digest=digest,
            )
            if cached is None:
                raise RunControlError(
                    CODE_RUN_CONTROL_BLOCKER,
                    "idempotent replay reservation missing cached result",
                )
            return ManagedRunStartResult(
                outcome=StartOutcome.IDEMPOTENT_REPLAY,
                run_request=cached.run_request,
                agent_run=cached.agent_run,
                authorization_id=cached.authorization_id,
            )

        if decision.kind is ReservationKind.TERMINAL_FAILURE_REPLAY:
            failure = self._registry.get_terminal_failure(
                idempotency_key=start_input.idempotency_key,
                canonical_request_digest=digest,
            )
            if failure is None:
                raise RunControlError(
                    CODE_RUN_CONTROL_BLOCKER,
                    "terminal failure replay missing cached failure record",
                )
            raise _failure_to_error(failure)

        request_id = decision.request_id
        run_id = decision.run_id
        try:
            return self._execute_new_start(
                start_input=start_input,
                digest=digest,
                request_id=request_id,
                run_id=run_id,
                stamp=stamp,
                launcher=launcher,
            )
        except RunControlError as exc:
            if exc.code == CODE_CONTROL_PLANE_FAILURE:
                self._terminalize_control_plane_failure(
                    idempotency_key=start_input.idempotency_key,
                    canonical_request_digest=digest,
                    request_id=request_id,
                    run_id=run_id,
                    failed_event_type=_failed_event_type_from_message(str(exc)),
                    safe_message=str(exc),
                )
            raise

    def _execute_new_start(
        self,
        *,
        start_input: ManagedRunStartInput,
        digest: str,
        request_id: str,
        run_id: str,
        stamp: datetime,
        launcher: ManagedRuntimeLauncher,
    ) -> ManagedRunStartResult:
        run_request = build_run_request(
            request_id=request_id,
            requested_at=stamp,
            agent_code=start_input.agent_code,
            requested_agent_version=start_input.requested_agent_version,
            initiator_type=start_input.initiator_type,
            initiator_id=start_input.initiator_id,
            trigger_type=start_input.trigger_type,
            trigger_reason=start_input.trigger_reason,
            project_code=start_input.project_code,
            month_key=start_input.month_key,
            scope_request=dict(start_input.scope_request or {}),
            orchestration_run_id=start_input.orchestration_run_id,
            predecessor_run_id=start_input.predecessor_run_id,
            requested_mission_id=start_input.requested_mission_id,
            idempotency_key=start_input.idempotency_key,
            metadata=dict(start_input.metadata or {}),
        )

        agent_run = build_agent_run(
            run_id=run_id,
            request_id=request_id,
            agent_code=run_request.agent_code,
            agent_version=start_input.requested_agent_version or _AGENT_VERSION_DEFAULT,
            mission_id=run_request.requested_mission_id,
            project_code=run_request.project_code,
            month_key=run_request.month_key,
            initiator_type=run_request.initiator_type,
            initiator_id=run_request.initiator_id,
            trigger_type=run_request.trigger_type,
            trigger_reason=run_request.trigger_reason,
            operational_status=OperationalStatus.REQUESTED,
            requested_at=stamp,
            updated_at=stamp,
            thread_id=run_id,
            orchestration_run_id=run_request.orchestration_run_id,
            scope_summary=dict(start_input.scope_request or {}),
        )

        self._record_class_a(
            event_type=EventType.RUN_REQUESTED,
            title="Run requested",
            run_request=run_request,
            agent_run=agent_run,
            occurred_at=stamp,
        )

        agent_run = _with_operational_status(agent_run, OperationalStatus.AUTHORIZING, stamp)
        self._record_class_a(
            event_type=EventType.RUN_AUTHORIZATION_STARTED,
            title="Run authorization started",
            run_request=run_request,
            agent_run=agent_run,
            occurred_at=stamp,
        )

        try:
            context = issue_read_only_agent_context(
                agent_code=run_request.agent_code,
                project_code=run_request.project_code,
                run_id=run_id,
            )
        except ContextIssueError as exc:
            denied_run = _terminal_agent_run(
                agent_run,
                OperationalStatus.AUTHORIZATION_DENIED,
                stamp,
                error_code=exc.code,
                safe_error_summary=str(exc),
            )
            try:
                self._record_class_a(
                    event_type=EventType.RUN_DENIED,
                    title="Run authorization denied",
                    run_request=run_request,
                    agent_run=denied_run,
                    occurred_at=stamp,
                    status=EventStatus.DENIED,
                    detail={"reason_code": exc.code},
                )
            except RunControlError as record_exc:
                if record_exc.code == CODE_CONTROL_PLANE_FAILURE:
                    self._terminalize_control_plane_failure(
                        idempotency_key=start_input.idempotency_key,
                        canonical_request_digest=digest,
                        request_id=request_id,
                        run_id=run_id,
                        failed_event_type=EventType.RUN_DENIED.value,
                        safe_message=str(record_exc),
                    )
                raise
            result = ManagedRunStartResult(
                outcome=StartOutcome.AUTHORIZATION_DENIED,
                run_request=run_request,
                agent_run=denied_run,
                authorization_id=None,
            )
            self._registry.store_result(
                idempotency_key=start_input.idempotency_key,
                canonical_request_digest=digest,
                result=result,
            )
            return result

        authorized_run = _with_operational_status(
            agent_run,
            OperationalStatus.AUTHORIZING,
            stamp,
            authorization_id=context.authorization_id,
            authorized_by=run_request.initiator_id,
            security_policy_version=context.security_policy_version,
        )
        self._record_class_a(
            event_type=EventType.RUN_AUTHORIZED,
            title="Run authorized",
            run_request=run_request,
            agent_run=authorized_run,
            occurred_at=stamp,
            authorization_id=context.authorization_id,
        )

        bound_run = _with_operational_status(
            authorized_run,
            OperationalStatus.STARTING,
            stamp,
            mission_id=run_request.requested_mission_id,
        )
        self._record_class_a(
            event_type=EventType.MISSION_BOUND,
            title="Mission bound",
            run_request=run_request,
            agent_run=bound_run,
            occurred_at=stamp,
            mission_id=run_request.requested_mission_id,
        )

        starting_run = bound_run
        self._record_class_a(
            event_type=EventType.RUN_STARTED,
            title="Run started",
            run_request=run_request,
            agent_run=starting_run,
            occurred_at=stamp,
            authorization_id=context.authorization_id,
            mission_id=run_request.requested_mission_id,
        )

        try:
            launcher.launch(
                run_request=run_request,
                agent_run=starting_run,
                context=context,
            )
        except Exception as exc:
            failure = TerminalFailureRecord(
                failure_kind=TerminalFailureKind.LAUNCH_OUTCOME_UNKNOWN,
                error_code=CODE_LAUNCH_OUTCOME_UNKNOWN,
                request_id=request_id,
                run_id=run_id,
                safe_message="managed runtime launcher raised before outcome was known",
            )
            self._registry.store_terminal_failure(
                idempotency_key=start_input.idempotency_key,
                canonical_request_digest=digest,
                failure=failure,
            )
            raise RunControlError(
                CODE_LAUNCH_OUTCOME_UNKNOWN,
                failure.safe_message or CODE_LAUNCH_OUTCOME_UNKNOWN,
            ) from exc

        running_run = _with_operational_status(
            starting_run,
            OperationalStatus.RUNNING,
            stamp,
            authorization_id=context.authorization_id,
        )
        result = ManagedRunStartResult(
            outcome=StartOutcome.AUTHORIZED,
            run_request=run_request,
            agent_run=running_run,
            authorization_id=context.authorization_id,
        )
        self._registry.store_result(
            idempotency_key=start_input.idempotency_key,
            canonical_request_digest=digest,
            result=result,
        )
        return result

    def _reject_system_event_direct_start(self, start_input: ManagedRunStartInput) -> None:
        if start_input.trigger_type is TriggerType.SYSTEM_EVENT:
            raise RunControlError(
                CODE_SYSTEM_EVENT_DIRECT_START_FORBIDDEN,
                "SYSTEM_EVENT is orchestration ingress; direct managed start is forbidden",
            )

    def _terminalize_control_plane_failure(
        self,
        *,
        idempotency_key: str,
        canonical_request_digest: str,
        request_id: str,
        run_id: str,
        failed_event_type: str | None,
        safe_message: str,
    ) -> None:
        self._registry.store_terminal_failure(
            idempotency_key=idempotency_key,
            canonical_request_digest=canonical_request_digest,
            failure=TerminalFailureRecord(
                failure_kind=TerminalFailureKind.CONTROL_PLANE_FAILURE,
                error_code=CODE_CONTROL_PLANE_FAILURE,
                request_id=request_id,
                run_id=run_id,
                failed_event_type=failed_event_type,
                safe_message=safe_message,
            ),
        )

    def _record_class_a(
        self,
        *,
        event_type: EventType,
        title: str,
        run_request: Any,
        agent_run: Any,
        occurred_at: datetime,
        status: EventStatus = EventStatus.OK,
        authorization_id: str | None = None,
        mission_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        event = build_observability_event(
            event_id=_mint_id("evt"),
            run_id=agent_run.run_id,
            agent_code=run_request.agent_code,
            occurred_at=occurred_at,
            event_type=event_type,
            status=status,
            title=title,
            request_id=run_request.request_id,
            mission_id=mission_id or agent_run.mission_id,
            orchestration_run_id=run_request.orchestration_run_id,
            authorization_id=authorization_id,
            attempt_n=agent_run.attempt_n,
            resume_n=agent_run.resume_n,
            detail=detail or {},
        )
        try:
            self._recorder.record_event(event)
        except Exception as exc:
            raise RunControlError(
                CODE_CONTROL_PLANE_FAILURE,
                f"Class A observability record failed for {event_type.value}: {exc}",
            ) from exc


def _failure_to_error(failure: TerminalFailureRecord) -> RunControlError:
    message = failure.safe_message or failure.error_code
    return RunControlError(failure.error_code, message)


def _failed_event_type_from_message(message: str) -> str | None:
    marker = "Class A observability record failed for "
    if marker not in message:
        return None
    fragment = message.split(marker, 1)[1]
    return fragment.split(":", 1)[0].strip()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_aware_utc(value: datetime, field_name: str = "requested_at") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise RunControlError(CODE_RUN_CONTROL_BLOCKER, f"{field_name} must be timezone-aware UTC")
    return value.astimezone(timezone.utc)


def _mint_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _with_operational_status(
    agent_run: Any,
    status: OperationalStatus,
    updated_at: datetime,
    **updates: Any,
) -> Any:
    payload = {
        "run_id": agent_run.run_id,
        "request_id": agent_run.request_id,
        "agent_code": agent_run.agent_code,
        "agent_version": agent_run.agent_version,
        "mission_id": updates.get("mission_id", agent_run.mission_id),
        "project_code": agent_run.project_code,
        "month_key": agent_run.month_key,
        "initiator_type": agent_run.initiator_type,
        "initiator_id": agent_run.initiator_id,
        "trigger_type": agent_run.trigger_type,
        "trigger_reason": agent_run.trigger_reason,
        "operational_status": status,
        "requested_at": agent_run.requested_at,
        "updated_at": updated_at,
        "thread_id": agent_run.thread_id,
        "attempt_n": agent_run.attempt_n,
        "resume_n": agent_run.resume_n,
        "projection_version": agent_run.projection_version,
        "orchestration_run_id": agent_run.orchestration_run_id,
        "scope_summary": dict(agent_run.to_dict().get("scope_summary") or {}),
        "authorization_id": updates.get("authorization_id", agent_run.authorization_id),
        "authorized_by": updates.get("authorized_by", agent_run.authorized_by),
        "security_policy_version": updates.get(
            "security_policy_version", agent_run.security_policy_version
        ),
        "lifecycle_status": agent_run.lifecycle_status,
        "current_stage_id": agent_run.current_stage_id,
        "current_node": agent_run.current_node,
        "started_at": agent_run.started_at,
        "completed_at": agent_run.completed_at,
        "checkpoint_id": agent_run.checkpoint_id,
        "snapshot_id": agent_run.snapshot_id,
        "package_id": agent_run.package_id,
        "interrupt_id": agent_run.interrupt_id,
        "decision_id": agent_run.decision_id,
        "handoff_id": agent_run.handoff_id,
        "safe_summary": dict(agent_run.to_dict().get("safe_summary") or {}),
        "safe_counts": dict(agent_run.to_dict().get("safe_counts") or {}),
        "error_code": updates.get("error_code", agent_run.error_code),
        "safe_error_summary": updates.get("safe_error_summary", agent_run.safe_error_summary),
    }
    return build_agent_run(**payload)


def _terminal_agent_run(
    agent_run: Any,
    status: OperationalStatus,
    updated_at: datetime,
    *,
    error_code: str | None = None,
    safe_error_summary: str | None = None,
) -> Any:
    return build_agent_run(
        run_id=agent_run.run_id,
        request_id=agent_run.request_id,
        agent_code=agent_run.agent_code,
        agent_version=agent_run.agent_version,
        mission_id=agent_run.mission_id,
        project_code=agent_run.project_code,
        month_key=agent_run.month_key,
        initiator_type=agent_run.initiator_type,
        initiator_id=agent_run.initiator_id,
        trigger_type=agent_run.trigger_type,
        trigger_reason=agent_run.trigger_reason,
        operational_status=status,
        requested_at=agent_run.requested_at,
        updated_at=updated_at,
        completed_at=updated_at,
        thread_id=agent_run.thread_id,
        attempt_n=agent_run.attempt_n,
        resume_n=agent_run.resume_n,
        projection_version=agent_run.projection_version,
        orchestration_run_id=agent_run.orchestration_run_id,
        scope_summary=dict(agent_run.to_dict().get("scope_summary") or {}),
        error_code=error_code,
        safe_error_summary=safe_error_summary,
    )
