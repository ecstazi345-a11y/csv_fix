"""
Constructor Runtime v0.1 Increment 7–8 — LangGraph orchestration.

Thin named-node graph over Pure Python one-stage lifecycle advance.
Increment 8 adds optional durable checkpointer + human_wait interrupt path.
Not a second business implementation. Not handoff. Not Control Room.

NORMAL ADVANCE != HUMAN RESUME.
FUNCTION != GRAPH NODE for apply_constructor_resume_command.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agents.monthly_plan_constructor.hitl_contracts import ConstructorHitlStore
from agents.monthly_plan_constructor.hitl_resume import (
    apply_constructor_resume_command,
    build_decision_request_from_lifecycle,
    revalidate_constructor_resume_reality,
)
from agents.monthly_plan_constructor.lifecycle import (
    CODE_LIFECYCLE_CONTRACT_BLOCKER,
    INVOCATION_STOP_STATUSES,
    STATUS_CREATED,
    STATUS_LABOR_RESOLVED,
    STATUS_MISSION_BOUND,
    STATUS_PACKAGE_BUILT,
    STATUS_REALITY_LOADED,
    STATUS_REVALIDATING_REALITY,
    STATUS_WAITING_FOR_HUMAN,
    TERMINAL_STATUSES,
    CandidateAssembler,
    ConstructorLifecycleState,
    LaborEvidenceInput,
    LifecycleError,
    advance_constructor_lifecycle,
    create_lifecycle_state,
)
from agents.monthly_plan_constructor.mission_scope import ScopeValue
from agents.monthly_plan_constructor.secure_read_tools import ScopeReader
from security.agent_execution_context import AgentExecutionContext

NODE_BIND_MISSION = "bind_mission"
NODE_LOAD_REALITY = "load_reality"
NODE_BUILD_PACKAGE = "build_package"
NODE_RESOLVE_LABOR = "resolve_labor"
NODE_EVALUATE_EXCEPTIONS = "evaluate_exceptions"
NODE_HUMAN_WAIT = "human_wait"
NODE_REVALIDATE_REALITY = "revalidate_reality"


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


def _route_by_status(state: ConstructorGraphState, *, hitl_enabled: bool) -> str:
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
):
    """
    Build compiled Constructor LangGraph with dependencies closed over at build time.

    Dependencies stay outside graph business state.
    checkpointer is optional; when omitted, WAIT ends the invocation (Inc 7 compat).
    When provided, WAIT routes to human_wait → interrupt().
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
        return {"lifecycle": _advance(lifecycle)}

    def load_reality(state: ConstructorGraphState) -> ConstructorGraphState:
        lifecycle = _require_status(
            state, STATUS_MISSION_BOUND, node_name=NODE_LOAD_REALITY
        )
        return {"lifecycle": _advance(lifecycle)}

    def build_package(state: ConstructorGraphState) -> ConstructorGraphState:
        lifecycle = _require_status(
            state, STATUS_REALITY_LOADED, node_name=NODE_BUILD_PACKAGE
        )
        return {"lifecycle": _advance(lifecycle)}

    def resolve_labor(state: ConstructorGraphState) -> ConstructorGraphState:
        lifecycle = _require_status(
            state, STATUS_PACKAGE_BUILT, node_name=NODE_RESOLVE_LABOR
        )
        return {"lifecycle": _advance(lifecycle)}

    def evaluate_exceptions(state: ConstructorGraphState) -> ConstructorGraphState:
        lifecycle = _require_status(
            state, STATUS_LABOR_RESOLVED, node_name=NODE_EVALUATE_EXCEPTIONS
        )
        return {"lifecycle": _advance(lifecycle)}

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
        request = build_decision_request_from_lifecycle(lifecycle, created_at=now)
        if hitl_store is not None:
            # MUST be idempotent — LangGraph replays code before interrupt().
            hitl_store.upsert_open_request(request)
        resume_payload = interrupt(request)
        updated = apply_constructor_resume_command(
            lifecycle,
            resume_payload,
            context=context,
            project_code=project_code,
            month_key=month_key,
            now=now,
        )
        if hitl_store is not None:
            from agents.monthly_plan_constructor.hitl_contracts import coerce_resume_command

            hitl_store.record_answer(
                interrupt_id=request.interrupt_id,
                command=coerce_resume_command(resume_payload),
            )
        return {"lifecycle": updated}

    def revalidate_reality(state: ConstructorGraphState) -> ConstructorGraphState:
        lifecycle = _require_status(
            state, STATUS_REVALIDATING_REALITY, node_name=NODE_REVALIDATE_REALITY
        )
        return {
            "lifecycle": revalidate_constructor_resume_reality(
                lifecycle,
                context=context,
                scope_reader=scope_reader,
                now=now,
            )
        }

    def route(state: ConstructorGraphState) -> str:
        return _route_by_status(state, hitl_enabled=hitl_enabled)

    graph = StateGraph(ConstructorGraphState)
    graph.add_node(NODE_BIND_MISSION, bind_mission)
    graph.add_node(NODE_LOAD_REALITY, load_reality)
    graph.add_node(NODE_BUILD_PACKAGE, build_package)
    graph.add_node(NODE_RESOLVE_LABOR, resolve_labor)
    graph.add_node(NODE_EVALUATE_EXCEPTIONS, evaluate_exceptions)
    if hitl_enabled:
        graph.add_node(NODE_HUMAN_WAIT, human_wait)
        graph.add_node(NODE_REVALIDATE_REALITY, revalidate_reality)

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

    graph.add_edge(START, NODE_BIND_MISSION)
    graph.add_conditional_edges(NODE_BIND_MISSION, route, path_map)
    graph.add_conditional_edges(NODE_LOAD_REALITY, route, path_map)
    graph.add_conditional_edges(NODE_BUILD_PACKAGE, route, path_map)
    graph.add_conditional_edges(NODE_RESOLVE_LABOR, route, path_map)
    graph.add_conditional_edges(NODE_EVALUATE_EXCEPTIONS, route, path_map)
    if hitl_enabled:
        graph.add_conditional_edges(NODE_HUMAN_WAIT, route, path_map)
        graph.add_conditional_edges(NODE_REVALIDATE_REALITY, route, path_map)

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
) -> ConstructorLifecycleState:
    """
    Invoke Constructor LangGraph to an invocation-stop ConstructorLifecycleState.

    READY_FOR_HANDOFF is eligibility only — no handoff execution.
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
