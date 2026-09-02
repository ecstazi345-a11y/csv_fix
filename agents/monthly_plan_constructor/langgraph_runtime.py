"""
Constructor Runtime v0.1 Increment 7–9.3 — LangGraph orchestration.

Thin named-node graph over Pure Python one-stage lifecycle advance.
Increment 8 adds optional durable checkpointer + human_wait interrupt path.
Increment 9.3 adds optional persist_handoff after READY_FOR_HANDOFF.
Not a second business implementation. Not Control Room.

NORMAL ADVANCE != HUMAN RESUME.
FUNCTION != GRAPH NODE for apply_constructor_resume_command.
READY_FOR_HANDOFF remains professional eligibility; persist does not change it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional, TypedDict

from langgraph.config import get_config
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agents.monthly_plan_constructor.durable_checkpoint import (
    require_durable_resume_checkpoint,
    resolve_current_checkpoint_id,
)
from agents.monthly_plan_constructor.handoff_contracts import (
    DEFAULT_SECURITY_POLICY_VERSION,
    build_constructor_handoff,
)
from agents.monthly_plan_constructor.handoff_store import (
    ConstructorHandoffStore,
    persist_constructor_handoff,
)
from agents.monthly_plan_constructor.hitl_contracts import (
    CODE_HITL_CONTRACT_BLOCKER,
    CODE_RUN_ABORTED_BY_HUMAN,
    ConstructorHitlStore,
    DECISION_ABORT_RUN,
    HitlContractError,
    coerce_resume_command,
    count_wait_ordinal,
)
from agents.monthly_plan_constructor.hitl_resume import (
    apply_constructor_resume_command,
    build_decision_request_from_lifecycle,
    revalidate_constructor_resume_reality,
)
from agents.monthly_plan_constructor.lifecycle import (
    CODE_LIFECYCLE_CONTRACT_BLOCKER,
    INVOCATION_STOP_STATUSES,
    STATUS_CREATED,
    STATUS_FAILED,
    STATUS_LABOR_RESOLVED,
    STATUS_MISSION_BOUND,
    STATUS_PACKAGE_BUILT,
    STATUS_READY_FOR_HANDOFF,
    STATUS_REALITY_LOADED,
    STATUS_REVALIDATING_REALITY,
    STATUS_WAITING_FOR_HUMAN,
    TERMINAL_STATUSES,
    CandidateAssembler,
    ConstructorLifecycleState,
    LaborEvidenceInput,
    LifecycleError,
    LifecycleTransition,
    advance_constructor_lifecycle,
    advance_constructor_reality_read_step,
    create_lifecycle_state,
)
from agents.monthly_plan_constructor.mission_scope import ScopeValue
from agents.monthly_plan_constructor.runtime_instrumentation import (
    ConstructorRuntimeEventKey,
    ConstructorRuntimeInstrumentation,
)
from agents.monthly_plan_constructor.secure_read_tools import (
    CODE_SECURITY_DENIED,
    ScopeReader,
)
from agents.observability.contracts import EventStatus, EventType
from agents.observability.recorder import ObservabilityRecorder
from security.agent_execution_context import (
    AgentExecutionContext,
    TOOL_LOAD_SCOPE,
)

CONSTRUCTOR_AGENT_CODE = "MONTHLY_PLAN_CONSTRUCTOR"

NODE_BIND_MISSION = "bind_mission"
NODE_LOAD_REALITY = "load_reality"
NODE_BUILD_PACKAGE = "build_package"
NODE_RESOLVE_LABOR = "resolve_labor"
NODE_EVALUATE_EXCEPTIONS = "evaluate_exceptions"
NODE_HUMAN_WAIT = "human_wait"
NODE_REVALIDATE_REALITY = "revalidate_reality"
NODE_PERSIST_HANDOFF = "persist_handoff"

_CORE_STAGE_BY_NODE: dict[str, str] = {
    NODE_LOAD_REALITY: "REALITY_READ",
    NODE_BUILD_PACKAGE: "CANDIDATE_ASSEMBLY",
    NODE_RESOLVE_LABOR: "LABOR_NORM_RESOLUTION",
    NODE_EVALUATE_EXCEPTIONS: "EXCEPTION_ANALYSIS",
}


class ConstructorGraphState(TypedDict):
    """Thin LangGraph envelope — authoritative business truth is lifecycle only."""

    lifecycle: ConstructorLifecycleState


def _resolve_mission_id(mission_id: Optional[str]) -> str:
    if mission_id is None:
        return f"mission-{uuid.uuid4()}"
    text = str(mission_id).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return f"mission-{uuid.uuid4()}"
    return text


def _require_status(
    state: ConstructorGraphState,
    expected: str,
    *,
    node_name: str,
) -> ConstructorLifecycleState:
    lifecycle = state.get("lifecycle")  # type: ignore[assignment]
    if lifecycle is None or not isinstance(lifecycle, ConstructorLifecycleState):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            f"{node_name}: ConstructorLifecycleState required in graph state",
        )
    if lifecycle.status != expected:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            f"{node_name}: expected status {expected}, got {lifecycle.status}",
        )
    return lifecycle


def _route_by_status(
    state: ConstructorGraphState,
    *,
    hitl_enabled: bool,
    handoff_enabled: bool,
) -> str:
    """Route using authoritative lifecycle.status only."""
    lifecycle = state.get("lifecycle")  # type: ignore[assignment]
    if lifecycle is None or not isinstance(lifecycle, ConstructorLifecycleState):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "routing requires ConstructorLifecycleState",
        )
    status = lifecycle.status
    if status == STATUS_MISSION_BOUND:
        return NODE_LOAD_REALITY
    if status == STATUS_REALITY_LOADED:
        return NODE_BUILD_PACKAGE
    if status == STATUS_PACKAGE_BUILT:
        return NODE_RESOLVE_LABOR
    if status == STATUS_LABOR_RESOLVED:
        return NODE_EVALUATE_EXCEPTIONS
    if status == STATUS_WAITING_FOR_HUMAN:
        return NODE_HUMAN_WAIT if hitl_enabled else END
    if status == STATUS_REVALIDATING_REALITY:
        if not hitl_enabled:
            raise LifecycleError(
                CODE_LIFECYCLE_CONTRACT_BLOCKER,
                "REVALIDATING_REALITY requires HITL-enabled graph",
            )
        return NODE_REVALIDATE_REALITY
    # READY is an invocation-stop status; persist must win before the general END map.
    if status == STATUS_READY_FOR_HANDOFF:
        if handoff_enabled:
            return NODE_PERSIST_HANDOFF
        return END
    if status in INVOCATION_STOP_STATUSES:
        return END
    raise LifecycleError(
        CODE_LIFECYCLE_CONTRACT_BLOCKER,
        f"unexpected lifecycle status for routing: {status}",
    )


def build_constructor_langgraph(
    *,
    context: AgentExecutionContext,
    project_code: Any,
    month_key: Any,
    assemble_candidates: CandidateAssembler,
    labor_evidence: LaborEvidenceInput = (),
    facility_scope: ScopeValue = None,
    discipline_scope: ScopeValue = None,
    system_scope: ScopeValue = None,
    iwp_scope: ScopeValue = None,
    queue_scope: ScopeValue = None,
    scope_reader: Optional[ScopeReader] = None,
    now: Optional[datetime] = None,
    checkpointer: Any = None,
    hitl_store: Optional[ConstructorHitlStore] = None,
    handoff_store: Optional[ConstructorHandoffStore] = None,
    security_policy_version: Optional[str] = None,
    orchestration_run_id: Optional[str] = None,
    recorder: ObservabilityRecorder | None = None,
):
    """
    Build compiled Constructor LangGraph with dependencies closed over at build time.

    Dependencies stay outside graph business state.
    checkpointer is optional; when omitted, WAIT ends the invocation (Inc 7 compat).
    When provided, WAIT routes to human_wait → interrupt().
    handoff_store is optional; when omitted, READY ends the invocation (Inc 7–8 compat).
    When provided, READY routes to persist_handoff → END without changing lifecycle.status.
    """
    if context is None or not isinstance(context, AgentExecutionContext):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "AgentExecutionContext is required",
        )
    if assemble_candidates is None or not callable(assemble_candidates):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "assemble_candidates port is required",
        )

    hitl_enabled = checkpointer is not None
    handoff_enabled = handoff_store is not None
    resolved_security_policy_version = (
        DEFAULT_SECURITY_POLICY_VERSION
        if security_policy_version is None
        else security_policy_version
    )
    instrumentation = (
        ConstructorRuntimeInstrumentation(recorder=recorder)
        if recorder is not None
        else None
    )
    event_stamp = now

    def _advance(lifecycle: ConstructorLifecycleState) -> ConstructorLifecycleState:
        return advance_constructor_lifecycle(
            lifecycle,
            context=context,
            project_code=project_code,
            month_key=month_key,
            assemble_candidates=assemble_candidates,
            labor_evidence=labor_evidence,
            facility_scope=facility_scope,
            discipline_scope=discipline_scope,
            system_scope=system_scope,
            iwp_scope=iwp_scope,
            queue_scope=queue_scope,
            scope_reader=scope_reader,
            now=now,
        )

    def bind_mission(state: ConstructorGraphState) -> ConstructorGraphState:
        lifecycle = _require_status(state, STATUS_CREATED, node_name=NODE_BIND_MISSION)
        if instrumentation is None:
            return {"lifecycle": _advance(lifecycle)}
        stamp = event_stamp or lifecycle.updated_at
        return {
            "lifecycle": _instrumented_bind_mission(
                lifecycle,
                advance_fn=_advance,
                instrumentation=instrumentation,
                occurred_at=stamp,
            )
        }

    def load_reality(state: ConstructorGraphState) -> ConstructorGraphState:
        lifecycle = _require_status(
            state, STATUS_MISSION_BOUND, node_name=NODE_LOAD_REALITY
        )
        if instrumentation is None:
            return {"lifecycle": _advance(lifecycle)}
        stamp = event_stamp or lifecycle.updated_at
        return {
            "lifecycle": _instrumented_reality_read_advance(
                lifecycle,
                node_name=NODE_LOAD_REALITY,
                stage_id=_CORE_STAGE_BY_NODE[NODE_LOAD_REALITY],
                instrumentation=instrumentation,
                occurred_at=stamp,
                context=context,
                scope_reader=scope_reader,
            )
        }

    def build_package(state: ConstructorGraphState) -> ConstructorGraphState:
        lifecycle = _require_status(
            state, STATUS_REALITY_LOADED, node_name=NODE_BUILD_PACKAGE
        )
        if instrumentation is None:
            return {"lifecycle": _advance(lifecycle)}
        stamp = event_stamp or lifecycle.updated_at
        return {
            "lifecycle": _instrumented_advance(
                lifecycle,
                node_name=NODE_BUILD_PACKAGE,
                stage_id=_CORE_STAGE_BY_NODE[NODE_BUILD_PACKAGE],
                advance_fn=_advance,
                instrumentation=instrumentation,
                occurred_at=stamp,
            )
        }

    def resolve_labor(state: ConstructorGraphState) -> ConstructorGraphState:
        lifecycle = _require_status(
            state, STATUS_PACKAGE_BUILT, node_name=NODE_RESOLVE_LABOR
        )
        if instrumentation is None:
            return {"lifecycle": _advance(lifecycle)}
        stamp = event_stamp or lifecycle.updated_at
        return {
            "lifecycle": _instrumented_advance(
                lifecycle,
                node_name=NODE_RESOLVE_LABOR,
                stage_id=_CORE_STAGE_BY_NODE[NODE_RESOLVE_LABOR],
                advance_fn=_advance,
                instrumentation=instrumentation,
                occurred_at=stamp,
            )
        }

    def evaluate_exceptions(state: ConstructorGraphState) -> ConstructorGraphState:
        lifecycle = _require_status(
            state, STATUS_LABOR_RESOLVED, node_name=NODE_EVALUATE_EXCEPTIONS
        )
        if instrumentation is None:
            return {"lifecycle": _advance(lifecycle)}
        stamp = event_stamp or lifecycle.updated_at
        return {
            "lifecycle": _instrumented_advance(
                lifecycle,
                node_name=NODE_EVALUATE_EXCEPTIONS,
                stage_id=_CORE_STAGE_BY_NODE[NODE_EVALUATE_EXCEPTIONS],
                advance_fn=_advance,
                instrumentation=instrumentation,
                occurred_at=stamp,
            )
        }

    def human_wait(state: ConstructorGraphState) -> ConstructorGraphState:
        """
        Thin HITL orchestration node.

        First entry: interrupt(request) pauses.
        Resume replay: rebuild request, idempotent OPEN upsert, interrupt returns
        resume payload, then dedicated apply helper runs.
        """
        lifecycle = _require_status(
            state, STATUS_WAITING_FOR_HUMAN, node_name=NODE_HUMAN_WAIT
        )
        if instrumentation is None:
            request = build_decision_request_from_lifecycle(lifecycle, created_at=now)
            if hitl_store is not None:
                hitl_store.upsert_open_request(request)
            resume_payload = interrupt(request)
            resume = coerce_resume_command(resume_payload)
            cfg = get_config()
            configurable = cfg.get("configurable") or {}
            thread_id = str(configurable.get("thread_id") or "").strip()
            if thread_id != lifecycle.run_id:
                raise HitlContractError(
                    CODE_HITL_CONTRACT_BLOCKER,
                    "thread_id must equal run_id",
                )
            runtime_ckpt = configurable.get("checkpoint_id")
            resolved = resolve_current_checkpoint_id(
                checkpointer,
                thread_id=thread_id,
                checkpoint_id=str(runtime_ckpt) if runtime_ckpt else None,
            )
            require_durable_resume_checkpoint(
                expected_checkpoint_id=resume.expected_checkpoint_id,
                current_checkpoint_id=resolved,
                context=context,
            )
            updated = apply_constructor_resume_command(
                lifecycle,
                resume,
                context=context,
                project_code=project_code,
                month_key=month_key,
                checkpoint_id=resolved,
                now=now,
            )
            if hitl_store is not None:
                hitl_store.record_answer(
                    interrupt_id=request.interrupt_id,
                    command=resume,
                )
            return {"lifecycle": updated}
        stamp = event_stamp or lifecycle.updated_at
        return {
            "lifecycle": _instrumented_human_wait(
                lifecycle,
                node_name=NODE_HUMAN_WAIT,
                instrumentation=instrumentation,
                occurred_at=stamp,
                context=context,
                project_code=project_code,
                month_key=month_key,
                checkpointer=checkpointer,
                hitl_store=hitl_store,
                now=now,
            )
        }

    def revalidate_reality(state: ConstructorGraphState) -> ConstructorGraphState:
        lifecycle = _require_status(
            state, STATUS_REVALIDATING_REALITY, node_name=NODE_REVALIDATE_REALITY
        )
        if instrumentation is None:
            return {
                "lifecycle": revalidate_constructor_resume_reality(
                    lifecycle,
                    context=context,
                    scope_reader=scope_reader,
                    now=now,
                )
            }
        stamp = event_stamp or lifecycle.updated_at
        return {
            "lifecycle": _instrumented_revalidate_reality_refresh(
                lifecycle,
                node_name=NODE_REVALIDATE_REALITY,
                instrumentation=instrumentation,
                occurred_at=stamp,
                context=context,
                scope_reader=scope_reader,
                now=now,
            )
        }

    def persist_handoff(state: ConstructorGraphState) -> ConstructorGraphState:
        lifecycle = _require_status(
            state, STATUS_READY_FOR_HANDOFF, node_name=NODE_PERSIST_HANDOFF
        )
        if handoff_store is None:
            raise LifecycleError(
                CODE_LIFECYCLE_CONTRACT_BLOCKER,
                "persist_handoff requires ConstructorHandoffStore",
            )
        if instrumentation is None:
            artifact = build_constructor_handoff(
                lifecycle,
                security_policy_version=resolved_security_policy_version,
                orchestration_run_id=orchestration_run_id,
                created_at=lifecycle.updated_at,
            )
            persist_constructor_handoff(store=handoff_store, handoff=artifact)
            return {"lifecycle": lifecycle}
        stamp = event_stamp or lifecycle.updated_at
        return {
            "lifecycle": _instrumented_persist_handoff(
                lifecycle,
                node_name=NODE_PERSIST_HANDOFF,
                instrumentation=instrumentation,
                occurred_at=stamp,
                handoff_store=handoff_store,
                security_policy_version=resolved_security_policy_version,
                orchestration_run_id=orchestration_run_id,
            )
        }

    def route(state: ConstructorGraphState) -> str:
        return _route_by_status(
            state,
            hitl_enabled=hitl_enabled,
            handoff_enabled=handoff_enabled,
        )

    graph = StateGraph(ConstructorGraphState)
    graph.add_node(NODE_BIND_MISSION, bind_mission)
    graph.add_node(NODE_LOAD_REALITY, load_reality)
    graph.add_node(NODE_BUILD_PACKAGE, build_package)
    graph.add_node(NODE_RESOLVE_LABOR, resolve_labor)
    graph.add_node(NODE_EVALUATE_EXCEPTIONS, evaluate_exceptions)
    if hitl_enabled:
        graph.add_node(NODE_HUMAN_WAIT, human_wait)
        graph.add_node(NODE_REVALIDATE_REALITY, revalidate_reality)
    if handoff_enabled:
        graph.add_node(NODE_PERSIST_HANDOFF, persist_handoff)

    hitl_path = {
        NODE_LOAD_REALITY: NODE_LOAD_REALITY,
        NODE_BUILD_PACKAGE: NODE_BUILD_PACKAGE,
        NODE_RESOLVE_LABOR: NODE_RESOLVE_LABOR,
        NODE_EVALUATE_EXCEPTIONS: NODE_EVALUATE_EXCEPTIONS,
        NODE_HUMAN_WAIT: NODE_HUMAN_WAIT,
        NODE_REVALIDATE_REALITY: NODE_REVALIDATE_REALITY,
        END: END,
    }
    compat_path = {
        NODE_LOAD_REALITY: NODE_LOAD_REALITY,
        NODE_BUILD_PACKAGE: NODE_BUILD_PACKAGE,
        NODE_RESOLVE_LABOR: NODE_RESOLVE_LABOR,
        NODE_EVALUATE_EXCEPTIONS: NODE_EVALUATE_EXCEPTIONS,
        END: END,
    }
    path_map = hitl_path if hitl_enabled else compat_path
    if handoff_enabled:
        path_map = {**path_map, NODE_PERSIST_HANDOFF: NODE_PERSIST_HANDOFF}

    graph.add_edge(START, NODE_BIND_MISSION)
    graph.add_conditional_edges(NODE_BIND_MISSION, route, path_map)
    graph.add_conditional_edges(NODE_LOAD_REALITY, route, path_map)
    graph.add_conditional_edges(NODE_BUILD_PACKAGE, route, path_map)
    graph.add_conditional_edges(NODE_RESOLVE_LABOR, route, path_map)
    graph.add_conditional_edges(NODE_EVALUATE_EXCEPTIONS, route, path_map)
    if hitl_enabled:
        graph.add_conditional_edges(NODE_HUMAN_WAIT, route, path_map)
        graph.add_conditional_edges(NODE_REVALIDATE_REALITY, route, path_map)
    if handoff_enabled:
        # persist_handoff leaves READY unchanged — a conditional edge would loop.
        graph.add_edge(NODE_PERSIST_HANDOFF, END)

    if checkpointer is not None:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()


def run_constructor_langgraph(
    *,
    context: AgentExecutionContext,
    project_code: Any,
    month_key: Any,
    assemble_candidates: CandidateAssembler,
    labor_evidence: LaborEvidenceInput = (),
    facility_scope: ScopeValue = None,
    discipline_scope: ScopeValue = None,
    system_scope: ScopeValue = None,
    iwp_scope: ScopeValue = None,
    queue_scope: ScopeValue = None,
    mission_id: Optional[str] = None,
    run_id: Optional[str] = None,
    scope_reader: Optional[ScopeReader] = None,
    now: Optional[datetime] = None,
    checkpointer: Any = None,
    hitl_store: Optional[ConstructorHitlStore] = None,
    handoff_store: Optional[ConstructorHandoffStore] = None,
    security_policy_version: Optional[str] = None,
    orchestration_run_id: Optional[str] = None,
    recorder: ObservabilityRecorder | None = None,
) -> ConstructorLifecycleState:
    """
    Invoke Constructor LangGraph to an invocation-stop ConstructorLifecycleState.

    READY_FOR_HANDOFF is eligibility only. Optional handoff_store persists the
    structured artifact via Increment 9.2; lifecycle.status is not changed.
    Without checkpointer, WAITING_FOR_HUMAN ends the run (Inc 7 compatible).
    With checkpointer, WAIT interrupts inside human_wait (caller resumes via Command).
    """
    if context is None or not isinstance(context, AgentExecutionContext):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "AgentExecutionContext is required",
        )
    if assemble_candidates is None or not callable(assemble_candidates):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "assemble_candidates port is required",
        )
    resolved_run_id = run_id or context.run_id
    initial = create_lifecycle_state(
        mission_id=_resolve_mission_id(mission_id),
        run_id=resolved_run_id,
        authorization_id=context.authorization_id,
        created_at=now,
    )
    # Pin advance timestamps to the same stamp used for create (Inc 6 now semantics).
    app = build_constructor_langgraph(
        context=context,
        project_code=project_code,
        month_key=month_key,
        assemble_candidates=assemble_candidates,
        labor_evidence=labor_evidence,
        facility_scope=facility_scope,
        discipline_scope=discipline_scope,
        system_scope=system_scope,
        iwp_scope=iwp_scope,
        queue_scope=queue_scope,
        scope_reader=scope_reader,
        now=initial.created_at,
        checkpointer=checkpointer,
        hitl_store=hitl_store,
        handoff_store=handoff_store,
        security_policy_version=security_policy_version,
        orchestration_run_id=orchestration_run_id,
        recorder=recorder,
    )
    invoke_kwargs: dict[str, Any] = {}
    if checkpointer is not None:
        invoke_kwargs["config"] = {
            "configurable": {
                "thread_id": resolved_run_id,
            }
        }
    result = app.invoke({"lifecycle": initial}, **invoke_kwargs)
    lifecycle = result.get("lifecycle")
    if lifecycle is None or not isinstance(lifecycle, ConstructorLifecycleState):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "LangGraph invoke did not return ConstructorLifecycleState",
        )
    # Interrupted WAIT still returns lifecycle in WAIT; treat as stop.
    if lifecycle.status not in TERMINAL_STATUSES:
        # Pending interrupt may leave status WAIT which is terminal; other mid-states fail.
        if not (
            checkpointer is not None
            and lifecycle.status == STATUS_WAITING_FOR_HUMAN
        ):
            raise LifecycleError(
                CODE_LIFECYCLE_CONTRACT_BLOCKER,
                f"LangGraph ended on non-terminal status {lifecycle.status}",
            )
    return lifecycle


def _count_reality_loaded_transitions(
    transitions: tuple[LifecycleTransition, ...],
) -> int:
    return sum(1 for item in transitions if item.to_status == STATUS_REALITY_LOADED)


def _derive_resume_n(lifecycle: ConstructorLifecycleState) -> int:
    return max(0, _count_reality_loaded_transitions(lifecycle.transitions) - 1)


def _semantic_occurrence_key(
    lifecycle: ConstructorLifecycleState,
    *,
    stage_id: str,
) -> str:
    if stage_id == "REALITY_READ":
        return "initial"
    if stage_id == "CANDIDATE_ASSEMBLY":
        if lifecycle.reality_read is None:
            raise LifecycleError(
                CODE_LIFECYCLE_CONTRACT_BLOCKER,
                "reality_read required for CANDIDATE_ASSEMBLY occurrence key",
            )
        return f"snapshot-{lifecycle.reality_read.read_id}"
    if stage_id == "LABOR_NORM_RESOLUTION":
        if lifecycle.package is None:
            raise LifecycleError(
                CODE_LIFECYCLE_CONTRACT_BLOCKER,
                "package required for LABOR_NORM_RESOLUTION occurrence key",
            )
        return f"package-{lifecycle.package.package_id}"
    if stage_id == "EXCEPTION_ANALYSIS":
        if lifecycle.labor_resolutions is None:
            raise LifecycleError(
                CODE_LIFECYCLE_CONTRACT_BLOCKER,
                "labor_resolutions required for EXCEPTION_ANALYSIS occurrence key",
            )
        return f"package-{lifecycle.labor_resolutions.package_id}"
    raise LifecycleError(
        CODE_LIFECYCLE_CONTRACT_BLOCKER,
        f"unsupported core stage_id {stage_id}",
    )


def _artifact_correlation_id(
    lifecycle: ConstructorLifecycleState,
    *,
    stage_id: str,
) -> Optional[str]:
    if stage_id == "REALITY_READ":
        return None
    if stage_id == "CANDIDATE_ASSEMBLY":
        return lifecycle.reality_read.read_id if lifecycle.reality_read is not None else None
    if stage_id == "LABOR_NORM_RESOLUTION":
        return lifecycle.package.package_id if lifecycle.package is not None else None
    if stage_id == "EXCEPTION_ANALYSIS":
        if lifecycle.labor_resolutions is None:
            return None
        return lifecycle.labor_resolutions.package_id
    return None


_SECURITY_TOOL_DENIAL_CODES = frozenset(
    {
        CODE_SECURITY_DENIED,
        "TOOL_NOT_ALLOWED",
        "CONTEXT_EXPIRED",
        "CONTEXT_MISSING",
    }
)


def _tool_denied_status_for_error_code(error_code: Optional[str]) -> EventStatus:
    code = str(error_code or "").strip().upper()
    if code in _SECURITY_TOOL_DENIAL_CODES:
        return EventStatus.DENIED
    return EventStatus.FAILED


def _is_new_reality_read(
    before: ConstructorLifecycleState,
    after: ConstructorLifecycleState,
) -> bool:
    if after.reality_read is None:
        return False
    if before.reality_read is None:
        return True
    return before.reality_read.read_id != after.reality_read.read_id


def _is_new_package(
    before: ConstructorLifecycleState,
    after: ConstructorLifecycleState,
) -> bool:
    if after.package is None:
        return False
    if before.package is None:
        return True
    return before.package.package_id != after.package.package_id


def _emit_run_advancing(
    *,
    lifecycle: ConstructorLifecycleState,
    instrumentation: ConstructorRuntimeInstrumentation,
    occurred_at: datetime,
) -> None:
    advancing_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=EventType.RUN_ADVANCING,
        semantic_occurrence_key="start",
        attempt_n=1,
        resume_n=0,
    )
    instrumentation.emit(
        key=advancing_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title="Run advancing",
        status=EventStatus.OK,
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
    )


def _emit_run_failed(
    *,
    lifecycle: ConstructorLifecycleState,
    instrumentation: ConstructorRuntimeInstrumentation,
    occurred_at: datetime,
    semantic_occurrence_key: str,
    stage_id: Optional[str] = None,
    node_name: Optional[str] = None,
    resume_n: int = 0,
    handoff_id: Optional[str] = None,
    orchestration_run_id: Optional[str] = None,
) -> None:
    failed_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=EventType.RUN_FAILED,
        stage_id=stage_id,
        node_name=node_name,
        attempt_n=1,
        resume_n=resume_n,
        semantic_occurrence_key=semantic_occurrence_key,
        artifact_correlation_id=handoff_id,
    )
    instrumentation.emit(
        key=failed_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title="Run failed",
        status=EventStatus.FAILED,
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        orchestration_run_id=orchestration_run_id,
        handoff_id=handoff_id,
        detail={
            "professional_status": lifecycle.status,
            "error_code": str(lifecycle.error_code or ""),
        },
    )


def _emit_run_aborted(
    *,
    lifecycle: ConstructorLifecycleState,
    instrumentation: ConstructorRuntimeInstrumentation,
    occurred_at: datetime,
    decision_id: str,
    node_name: str,
    wait_ordinal: int,
    resume: Any,
    checkpoint_id: Optional[str],
    interrupt_id: Optional[str],
) -> None:
    aborted_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=EventType.RUN_ABORTED,
        stage_id="HUMAN_GATE",
        node_name=node_name,
        attempt_n=1,
        resume_n=wait_ordinal,
        semantic_occurrence_key=f"abort-{decision_id}",
        artifact_correlation_id=decision_id,
    )
    instrumentation.emit(
        key=aborted_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title="Run aborted",
        status=EventStatus.FAILED,
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        checkpoint_id=checkpoint_id,
        interrupt_id=interrupt_id,
        decision_id=decision_id,
        detail={
            "decision_type": resume.decision,
            "actor_type": resume.actor_type,
            "actor_id": resume.actor_id,
            "wait_ordinal": str(wait_ordinal),
            "professional_status": lifecycle.status,
            "error_code": str(lifecycle.error_code or CODE_RUN_ABORTED_BY_HUMAN),
        },
    )


def _instrumented_bind_mission(
    lifecycle: ConstructorLifecycleState,
    *,
    advance_fn: Any,
    instrumentation: ConstructorRuntimeInstrumentation,
    occurred_at: datetime,
) -> ConstructorLifecycleState:
    _emit_run_advancing(
        lifecycle=lifecycle,
        instrumentation=instrumentation,
        occurred_at=occurred_at,
    )
    updated = advance_fn(lifecycle)
    if updated.status == STATUS_FAILED:
        _emit_run_failed(
            lifecycle=updated,
            instrumentation=instrumentation,
            occurred_at=occurred_at,
            semantic_occurrence_key="run-failed/MISSION_BINDING/bind-mission",
            stage_id="MISSION_BINDING",
            node_name=NODE_BIND_MISSION,
        )
    return updated


def _emit_reality_snapshot_artifact(
    *,
    lifecycle: ConstructorLifecycleState,
    reality_read: Any,
    stage_id: str,
    node_name: str,
    stage_semantic_key: str,
    resume_n: int,
    instrumentation: ConstructorRuntimeInstrumentation,
    occurred_at: datetime,
) -> None:
    read_id = reality_read.read_id
    artifact_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=EventType.ARTIFACT_CREATED,
        stage_id=stage_id,
        node_name=node_name,
        attempt_n=1,
        resume_n=resume_n,
        semantic_occurrence_key=f"{stage_semantic_key}/artifact-snapshot-{read_id}",
        artifact_correlation_id=read_id,
    )
    instrumentation.emit(
        key=artifact_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title="Reality snapshot artifact created",
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        snapshot_id=read_id,
        tool_name=TOOL_LOAD_SCOPE,
        detail={
            "artifact_type": "snapshot",
            "schema_version": str(reality_read.schema_version),
            "row_count": str(reality_read.row_count),
            "tool_name": str(reality_read.tool_name),
        },
    )


def _emit_candidate_package_artifact(
    *,
    lifecycle: ConstructorLifecycleState,
    package: Any,
    stage_id: str,
    node_name: str,
    stage_semantic_key: str,
    resume_n: int,
    instrumentation: ConstructorRuntimeInstrumentation,
    occurred_at: datetime,
    snapshot_id: Optional[str],
) -> None:
    package_id = package.package_id
    artifact_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=EventType.ARTIFACT_CREATED,
        stage_id=stage_id,
        node_name=node_name,
        attempt_n=1,
        resume_n=resume_n,
        semantic_occurrence_key=f"{stage_semantic_key}/artifact-package-{package_id}",
        artifact_correlation_id=package_id,
    )
    detail: dict[str, str] = {
        "artifact_type": "package",
        "schema_version": str(package.schema_version),
        "candidate_count": str(package.candidate_count),
    }
    if snapshot_id:
        detail["snapshot_id"] = snapshot_id
    instrumentation.emit(
        key=artifact_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title="Candidate package artifact created",
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        snapshot_id=snapshot_id,
        package_id=package_id,
        detail=detail,
    )


def _instrumented_reality_read_advance(
    lifecycle: ConstructorLifecycleState,
    *,
    node_name: str,
    stage_id: str,
    instrumentation: ConstructorRuntimeInstrumentation,
    occurred_at: datetime,
    context: AgentExecutionContext,
    scope_reader: Optional[ScopeReader],
) -> ConstructorLifecycleState:
    status_before = lifecycle.status
    resume_n = 0
    semantic_key = _semantic_occurrence_key(lifecycle, stage_id=stage_id)
    tool_semantic_key = f"{semantic_key}/tool-{TOOL_LOAD_SCOPE}"

    started_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=EventType.STAGE_STARTED,
        stage_id=stage_id,
        node_name=node_name,
        attempt_n=1,
        resume_n=resume_n,
        semantic_occurrence_key=semantic_key,
        artifact_correlation_id=None,
    )
    instrumentation.emit(
        key=started_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title=f"{stage_id} started",
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        detail={"professional_status_before": status_before},
    )

    tool_started_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=EventType.TOOL_CALL_STARTED,
        stage_id=stage_id,
        node_name=node_name,
        attempt_n=1,
        resume_n=resume_n,
        semantic_occurrence_key=tool_semantic_key,
        artifact_correlation_id=None,
    )
    instrumentation.emit(
        key=tool_started_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title=f"{TOOL_LOAD_SCOPE} started",
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        tool_name=TOOL_LOAD_SCOPE,
        detail={"professional_status_before": status_before},
    )

    updated = advance_constructor_reality_read_step(
        lifecycle,
        context=context,
        scope_reader=scope_reader,
        at=occurred_at,
    )

    if _is_new_reality_read(lifecycle, updated):
        tool_terminal_type = EventType.TOOL_CALL_COMPLETED
        tool_terminal_status = EventStatus.OK
    else:
        tool_terminal_type = EventType.TOOL_CALL_DENIED
        tool_terminal_status = _tool_denied_status_for_error_code(updated.error_code)

    tool_terminal_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=tool_terminal_type,
        stage_id=stage_id,
        node_name=node_name,
        attempt_n=1,
        resume_n=resume_n,
        semantic_occurrence_key=tool_semantic_key,
        artifact_correlation_id=None,
    )
    instrumentation.emit(
        key=tool_terminal_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title=f"{TOOL_LOAD_SCOPE} {tool_terminal_type.value.lower().replace('_', ' ')}",
        status=tool_terminal_status,
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        tool_name=TOOL_LOAD_SCOPE,
        detail={
            "professional_status_after": updated.status,
            "error_code": str(updated.error_code or ""),
        },
    )

    if _is_new_reality_read(lifecycle, updated):
        _emit_reality_snapshot_artifact(
            lifecycle=lifecycle,
            reality_read=updated.reality_read,
            stage_id=stage_id,
            node_name=node_name,
            stage_semantic_key=semantic_key,
            resume_n=resume_n,
            instrumentation=instrumentation,
            occurred_at=occurred_at,
        )

    if updated.status == STATUS_FAILED:
        terminal_type = EventType.STAGE_FAILED
        terminal_status = EventStatus.FAILED
    else:
        terminal_type = EventType.STAGE_COMPLETED
        terminal_status = EventStatus.OK

    terminal_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=terminal_type,
        stage_id=stage_id,
        node_name=node_name,
        attempt_n=1,
        resume_n=resume_n,
        semantic_occurrence_key=semantic_key,
        artifact_correlation_id=None,
    )
    instrumentation.emit(
        key=terminal_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title=f"{stage_id} {terminal_type.value.lower().replace('_', ' ')}",
        status=terminal_status,
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        snapshot_id=updated.reality_read.read_id if updated.reality_read else None,
        detail={
            "professional_status_before": status_before,
            "professional_status_after": updated.status,
        },
    )
    if updated.status == STATUS_FAILED:
        _emit_run_failed(
            lifecycle=updated,
            instrumentation=instrumentation,
            occurred_at=occurred_at,
            semantic_occurrence_key=f"run-failed/{stage_id}/{semantic_key}",
            stage_id=stage_id,
            node_name=node_name,
            resume_n=resume_n,
        )
    return updated


def _instrumented_advance(
    lifecycle: ConstructorLifecycleState,
    *,
    node_name: str,
    stage_id: str,
    advance_fn: Any,
    instrumentation: ConstructorRuntimeInstrumentation,
    occurred_at: datetime,
) -> ConstructorLifecycleState:
    status_before = lifecycle.status
    resume_n = 0 if stage_id == "REALITY_READ" else _derive_resume_n(lifecycle)
    semantic_key = _semantic_occurrence_key(lifecycle, stage_id=stage_id)
    artifact_corr = _artifact_correlation_id(lifecycle, stage_id=stage_id)

    started_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=EventType.STAGE_STARTED,
        stage_id=stage_id,
        node_name=node_name,
        attempt_n=1,
        resume_n=resume_n,
        semantic_occurrence_key=semantic_key,
        artifact_correlation_id=artifact_corr,
    )
    instrumentation.emit(
        key=started_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title=f"{stage_id} started",
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        snapshot_id=lifecycle.reality_read.read_id if lifecycle.reality_read else None,
        package_id=(
            lifecycle.package.package_id
            if lifecycle.package is not None
            else lifecycle.labor_resolutions.package_id
            if lifecycle.labor_resolutions is not None
            else None
        ),
        detail={"professional_status_before": status_before},
    )

    updated = advance_fn(lifecycle)

    if (
        stage_id == "CANDIDATE_ASSEMBLY"
        and _is_new_package(lifecycle, updated)
        and updated.package is not None
    ):
        snapshot_id = (
            lifecycle.reality_read.read_id if lifecycle.reality_read is not None else None
        )
        _emit_candidate_package_artifact(
            lifecycle=lifecycle,
            package=updated.package,
            stage_id=stage_id,
            node_name=node_name,
            stage_semantic_key=semantic_key,
            resume_n=resume_n,
            instrumentation=instrumentation,
            occurred_at=occurred_at,
            snapshot_id=snapshot_id,
        )

    if updated.status == STATUS_FAILED:
        terminal_type = EventType.STAGE_FAILED
        terminal_status = EventStatus.FAILED
    else:
        terminal_type = EventType.STAGE_COMPLETED
        terminal_status = EventStatus.OK

    terminal_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=terminal_type,
        stage_id=stage_id,
        node_name=node_name,
        attempt_n=1,
        resume_n=resume_n,
        semantic_occurrence_key=semantic_key,
        artifact_correlation_id=artifact_corr,
    )
    instrumentation.emit(
        key=terminal_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title=f"{stage_id} {terminal_type.value.lower().replace('_', ' ')}",
        status=terminal_status,
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        snapshot_id=updated.reality_read.read_id if updated.reality_read else None,
        package_id=(
            updated.package.package_id
            if updated.package is not None
            else updated.labor_resolutions.package_id
            if updated.labor_resolutions is not None
            else None
        ),
        detail={
            "professional_status_before": status_before,
            "professional_status_after": updated.status,
        },
    )
    if updated.status == STATUS_FAILED:
        _emit_run_failed(
            lifecycle=updated,
            instrumentation=instrumentation,
            occurred_at=occurred_at,
            semantic_occurrence_key=f"run-failed/{stage_id}/{semantic_key}",
            stage_id=stage_id,
            node_name=node_name,
            resume_n=resume_n,
        )
    return updated


def _hitl_wait_ordinal(lifecycle: ConstructorLifecycleState) -> int:
    ordinal = count_wait_ordinal(lifecycle.transitions)
    return max(1, ordinal)


def _instrumented_human_wait(
    lifecycle: ConstructorLifecycleState,
    *,
    node_name: str,
    instrumentation: ConstructorRuntimeInstrumentation,
    occurred_at: datetime,
    context: AgentExecutionContext,
    project_code: Any,
    month_key: Any,
    checkpointer: Any,
    hitl_store: Optional[ConstructorHitlStore],
    now: Optional[datetime],
) -> ConstructorLifecycleState:
    request = build_decision_request_from_lifecycle(lifecycle, created_at=now)
    wait_ordinal = request.wait_ordinal
    if hitl_store is not None:
        hitl_store.upsert_open_request(request)

    wait_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=EventType.HUMAN_WAIT_STARTED,
        stage_id="HUMAN_GATE",
        node_name=node_name,
        attempt_n=1,
        resume_n=wait_ordinal,
        semantic_occurrence_key=f"wait-{wait_ordinal}",
        artifact_correlation_id=None,
    )
    instrumentation.emit(
        key=wait_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title="Human wait started",
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        interrupt_id=request.interrupt_id,
        detail={
            "reason_code": request.reason_code,
            "wait_ordinal": str(wait_ordinal),
            "route": request.route,
            "severity": request.severity,
            "professional_status_before": lifecycle.status,
        },
    )

    resume_payload = interrupt(request)
    resume = coerce_resume_command(resume_payload)
    cfg = get_config()
    configurable = cfg.get("configurable") or {}
    thread_id = str(configurable.get("thread_id") or "").strip()
    if thread_id != lifecycle.run_id:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "thread_id must equal run_id",
        )
    runtime_ckpt = configurable.get("checkpoint_id")
    resolved = resolve_current_checkpoint_id(
        checkpointer,
        thread_id=thread_id,
        checkpoint_id=str(runtime_ckpt) if runtime_ckpt else None,
    )
    require_durable_resume_checkpoint(
        expected_checkpoint_id=resume.expected_checkpoint_id,
        current_checkpoint_id=resolved,
        context=context,
    )

    decision_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=EventType.HUMAN_DECISION_RECEIVED,
        stage_id="HUMAN_GATE",
        node_name=node_name,
        attempt_n=1,
        resume_n=wait_ordinal,
        semantic_occurrence_key=f"decision-{resume.decision_id}",
        artifact_correlation_id=resume.decision_id,
    )
    instrumentation.emit(
        key=decision_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title="Human decision received",
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        checkpoint_id=resolved,
        interrupt_id=request.interrupt_id,
        decision_id=resume.decision_id,
        detail={
            "decision_type": resume.decision,
            "actor_type": resume.actor_type,
            "actor_id": resume.actor_id,
            "reason_code": str(lifecycle.error_code or ""),
            "wait_ordinal": str(wait_ordinal),
            "route": request.route,
            "severity": request.severity,
            "professional_status_before": lifecycle.status,
        },
    )

    updated = apply_constructor_resume_command(
        lifecycle,
        resume,
        context=context,
        project_code=project_code,
        month_key=month_key,
        checkpoint_id=resolved,
        now=now,
    )

    if resume.decision == DECISION_ABORT_RUN:
        _emit_run_aborted(
            lifecycle=updated,
            instrumentation=instrumentation,
            occurred_at=occurred_at,
            decision_id=resume.decision_id,
            node_name=node_name,
            wait_ordinal=wait_ordinal,
            resume=resume,
            checkpoint_id=resolved,
            interrupt_id=request.interrupt_id,
        )
    elif updated.status == STATUS_REVALIDATING_REALITY:
        resumed_key = ConstructorRuntimeEventKey(
            run_id=lifecycle.run_id,
            event_type=EventType.RUN_RESUMED,
            stage_id="HUMAN_GATE",
            node_name=node_name,
            attempt_n=1,
            resume_n=wait_ordinal,
            semantic_occurrence_key=f"resume-{resume.decision_id}",
            artifact_correlation_id=resume.decision_id,
        )
        instrumentation.emit(
            key=resumed_key,
            occurred_at=occurred_at,
            agent_code=CONSTRUCTOR_AGENT_CODE,
            title="Run resumed",
            mission_id=lifecycle.mission_id,
            authorization_id=lifecycle.authorization_id,
            checkpoint_id=resolved,
            interrupt_id=request.interrupt_id,
            decision_id=resume.decision_id,
            detail={
                "decision_type": resume.decision,
                "wait_ordinal": str(wait_ordinal),
                "professional_status_before": lifecycle.status,
                "professional_status_after": updated.status,
            },
        )

    if hitl_store is not None:
        hitl_store.record_answer(
            interrupt_id=request.interrupt_id,
            command=resume,
        )
    return updated


def _instrumented_revalidate_reality_refresh(
    lifecycle: ConstructorLifecycleState,
    *,
    node_name: str,
    instrumentation: ConstructorRuntimeInstrumentation,
    occurred_at: datetime,
    context: AgentExecutionContext,
    scope_reader: Optional[ScopeReader],
    now: Optional[datetime],
) -> ConstructorLifecycleState:
    stage_id = "REALITY_REVALIDATION"
    wait_ordinal = _hitl_wait_ordinal(lifecycle)
    refresh_semantic_key = f"refresh-{wait_ordinal}"
    tool_semantic_key = f"{refresh_semantic_key}/tool-{TOOL_LOAD_SCOPE}"
    status_before = lifecycle.status

    refresh_started_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=EventType.REALITY_REFRESH_STARTED,
        stage_id=stage_id,
        node_name=node_name,
        attempt_n=1,
        resume_n=wait_ordinal,
        semantic_occurrence_key=refresh_semantic_key,
        artifact_correlation_id=None,
    )
    instrumentation.emit(
        key=refresh_started_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title="Reality refresh started",
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        detail={
            "wait_ordinal": str(wait_ordinal),
            "professional_status_before": status_before,
        },
    )

    tool_started_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=EventType.TOOL_CALL_STARTED,
        stage_id=stage_id,
        node_name=node_name,
        attempt_n=1,
        resume_n=wait_ordinal,
        semantic_occurrence_key=tool_semantic_key,
        artifact_correlation_id=None,
    )
    instrumentation.emit(
        key=tool_started_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title=f"{TOOL_LOAD_SCOPE} started",
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        tool_name=TOOL_LOAD_SCOPE,
        detail={
            "wait_ordinal": str(wait_ordinal),
            "professional_status_before": status_before,
        },
    )

    updated = revalidate_constructor_resume_reality(
        lifecycle,
        context=context,
        scope_reader=scope_reader,
        now=now,
    )

    if _is_new_reality_read(lifecycle, updated):
        tool_terminal_type = EventType.TOOL_CALL_COMPLETED
        tool_terminal_status = EventStatus.OK
    else:
        tool_terminal_type = EventType.TOOL_CALL_DENIED
        tool_terminal_status = _tool_denied_status_for_error_code(updated.error_code)

    tool_terminal_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=tool_terminal_type,
        stage_id=stage_id,
        node_name=node_name,
        attempt_n=1,
        resume_n=wait_ordinal,
        semantic_occurrence_key=tool_semantic_key,
        artifact_correlation_id=None,
    )
    instrumentation.emit(
        key=tool_terminal_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title=f"{TOOL_LOAD_SCOPE} {tool_terminal_type.value.lower().replace('_', ' ')}",
        status=tool_terminal_status,
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        tool_name=TOOL_LOAD_SCOPE,
        detail={
            "professional_status_after": updated.status,
            "error_code": str(updated.error_code or ""),
        },
    )

    refresh_ok = updated.status == STATUS_REALITY_LOADED
    refresh_completed_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=EventType.REALITY_REFRESH_COMPLETED,
        stage_id=stage_id,
        node_name=node_name,
        attempt_n=1,
        resume_n=wait_ordinal,
        semantic_occurrence_key=refresh_semantic_key,
        artifact_correlation_id=None,
    )
    instrumentation.emit(
        key=refresh_completed_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title="Reality refresh completed",
        status=EventStatus.OK if refresh_ok else EventStatus.FAILED,
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        detail={
            "professional_status_before": status_before,
            "professional_status_after": updated.status,
            "error_code": str(updated.error_code or ""),
        },
    )

    if _is_new_reality_read(lifecycle, updated) and updated.reality_read is not None:
        _emit_reality_snapshot_artifact(
            lifecycle=lifecycle,
            reality_read=updated.reality_read,
            stage_id=stage_id,
            node_name=node_name,
            stage_semantic_key=refresh_semantic_key,
            resume_n=wait_ordinal,
            instrumentation=instrumentation,
            occurred_at=occurred_at,
        )

    if updated.status == STATUS_FAILED:
        _emit_run_failed(
            lifecycle=updated,
            instrumentation=instrumentation,
            occurred_at=occurred_at,
            semantic_occurrence_key=f"run-failed/REALITY_REVALIDATION/{refresh_semantic_key}",
            stage_id=stage_id,
            node_name=node_name,
            resume_n=wait_ordinal,
        )

    return updated


def _safe_persistence_error_detail(exc: BaseException) -> dict[str, str]:
    detail: dict[str, str] = {"exception_type": type(exc).__name__}
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code.strip():
        detail["error_code"] = code.strip()
    return detail


def _emit_handoff_persist_failed(
    *,
    lifecycle: ConstructorLifecycleState,
    handoff_id: str,
    node_name: str,
    instrumentation: ConstructorRuntimeInstrumentation,
    occurred_at: datetime,
    exc: BaseException,
    orchestration_run_id: Optional[str],
) -> None:
    resume_n = _derive_resume_n(lifecycle)
    failed_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=EventType.HANDOFF_PERSIST_FAILED,
        stage_id="HANDOFF_PERSISTENCE",
        node_name=node_name,
        attempt_n=1,
        resume_n=resume_n,
        semantic_occurrence_key=f"handoff-{handoff_id}/persist-failed",
        artifact_correlation_id=handoff_id,
    )
    instrumentation.emit(
        key=failed_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title="Handoff persistence failed",
        status=EventStatus.FAILED,
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        orchestration_run_id=orchestration_run_id,
        handoff_id=handoff_id,
        detail=_safe_persistence_error_detail(exc),
    )


def _instrumented_persist_handoff(
    lifecycle: ConstructorLifecycleState,
    *,
    node_name: str,
    instrumentation: ConstructorRuntimeInstrumentation,
    occurred_at: datetime,
    handoff_store: ConstructorHandoffStore,
    security_policy_version: str,
    orchestration_run_id: Optional[str],
) -> ConstructorLifecycleState:
    artifact = build_constructor_handoff(
        lifecycle,
        security_policy_version=security_policy_version,
        orchestration_run_id=orchestration_run_id,
        created_at=lifecycle.updated_at,
    )
    handoff_id = artifact.handoff_id
    resume_n = _derive_resume_n(lifecycle)
    package_id = artifact.candidate_package_reference.package_id

    created_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=EventType.HANDOFF_CREATED,
        stage_id="HANDOFF_PREPARATION",
        node_name=node_name,
        attempt_n=1,
        resume_n=resume_n,
        semantic_occurrence_key=f"handoff-{handoff_id}",
        artifact_correlation_id=handoff_id,
    )
    instrumentation.emit(
        key=created_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title="Handoff created",
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        orchestration_run_id=orchestration_run_id,
        handoff_id=handoff_id,
        package_id=package_id,
        detail={
            "schema_version": artifact.schema_version,
            "source_agent": artifact.source_agent,
            "target_role": artifact.target_role,
            "candidate_count": str(artifact.candidate_count),
        },
    )

    try:
        persist_result = persist_constructor_handoff(store=handoff_store, handoff=artifact)
    except Exception as persist_exc:
        try:
            _emit_handoff_persist_failed(
                lifecycle=lifecycle,
                handoff_id=handoff_id,
                node_name=node_name,
                instrumentation=instrumentation,
                occurred_at=occurred_at,
                exc=persist_exc,
                orchestration_run_id=orchestration_run_id,
            )
        except Exception as recorder_exc:
            raise persist_exc from recorder_exc
        try:
            _emit_run_failed(
                lifecycle=lifecycle,
                instrumentation=instrumentation,
                occurred_at=occurred_at,
                semantic_occurrence_key=f"handoff-failure/{handoff_id}",
                stage_id="HANDOFF_PERSISTENCE",
                node_name=node_name,
                resume_n=resume_n,
                handoff_id=handoff_id,
                orchestration_run_id=orchestration_run_id,
            )
        except Exception as run_failed_recorder_exc:
            raise persist_exc from run_failed_recorder_exc
        raise persist_exc

    persisted_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=EventType.HANDOFF_PERSISTED,
        stage_id="HANDOFF_PERSISTENCE",
        node_name=node_name,
        attempt_n=1,
        resume_n=resume_n,
        semantic_occurrence_key=f"handoff-{handoff_id}/persist",
        artifact_correlation_id=handoff_id,
    )
    instrumentation.emit(
        key=persisted_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title="Handoff persisted",
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        orchestration_run_id=orchestration_run_id,
        handoff_id=handoff_id,
        package_id=package_id,
        detail={
            "persistence_status": persist_result.status,
            "payload_digest": persist_result.payload_digest,
        },
    )

    completed_key = ConstructorRuntimeEventKey(
        run_id=lifecycle.run_id,
        event_type=EventType.RUN_COMPLETED,
        stage_id="RUN_COMPLETION",
        node_name=node_name,
        attempt_n=1,
        resume_n=resume_n,
        semantic_occurrence_key="completion",
        artifact_correlation_id=None,
    )
    instrumentation.emit(
        key=completed_key,
        occurred_at=occurred_at,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        title="Constructor run completed",
        mission_id=lifecycle.mission_id,
        authorization_id=lifecycle.authorization_id,
        orchestration_run_id=orchestration_run_id,
        handoff_id=handoff_id,
        detail={
            "professional_status": lifecycle.status,
        },
    )

    return lifecycle
