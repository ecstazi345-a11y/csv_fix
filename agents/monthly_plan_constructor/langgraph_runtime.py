"""
Constructor Runtime v0.1 Increment 7 — LangGraph orchestration.

Thin named-node graph over Pure Python one-stage lifecycle advance.
Not a second business implementation. Not HITL. Not handoff. Not Control Room.
Durable pause/resume is owned by a later increment — this module compiles without one.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.monthly_plan_constructor.lifecycle import (
    CODE_LIFECYCLE_CONTRACT_BLOCKER,
    STATUS_CREATED,
    STATUS_LABOR_RESOLVED,
    STATUS_MISSION_BOUND,
    STATUS_PACKAGE_BUILT,
    STATUS_REALITY_LOADED,
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


def _route_by_status(state: ConstructorGraphState) -> str:
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
    if status in TERMINAL_STATUSES:
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
):
    """
    Build compiled Constructor LangGraph with dependencies closed over at build time.

    Dependencies stay outside graph business state. No durable persistence backend.
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

    graph = StateGraph(ConstructorGraphState)
    graph.add_node(NODE_BIND_MISSION, bind_mission)
    graph.add_node(NODE_LOAD_REALITY, load_reality)
    graph.add_node(NODE_BUILD_PACKAGE, build_package)
    graph.add_node(NODE_RESOLVE_LABOR, resolve_labor)
    graph.add_node(NODE_EVALUATE_EXCEPTIONS, evaluate_exceptions)

    graph.add_edge(START, NODE_BIND_MISSION)
    graph.add_conditional_edges(
        NODE_BIND_MISSION,
        _route_by_status,
        {
            NODE_LOAD_REALITY: NODE_LOAD_REALITY,
            END: END,
        },
    )
    graph.add_conditional_edges(
        NODE_LOAD_REALITY,
        _route_by_status,
        {
            NODE_BUILD_PACKAGE: NODE_BUILD_PACKAGE,
            END: END,
        },
    )
    graph.add_conditional_edges(
        NODE_BUILD_PACKAGE,
        _route_by_status,
        {
            NODE_RESOLVE_LABOR: NODE_RESOLVE_LABOR,
            END: END,
        },
    )
    graph.add_conditional_edges(
        NODE_RESOLVE_LABOR,
        _route_by_status,
        {
            NODE_EVALUATE_EXCEPTIONS: NODE_EVALUATE_EXCEPTIONS,
            END: END,
        },
    )
    graph.add_conditional_edges(
        NODE_EVALUATE_EXCEPTIONS,
        _route_by_status,
        {
            END: END,
        },
    )

    # Increment 7: compile without a persistence backend.
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
) -> ConstructorLifecycleState:
    """
    Invoke Constructor LangGraph to a terminal ConstructorLifecycleState.

    READY_FOR_HANDOFF is eligibility only — no handoff execution.
    WAITING_FOR_HUMAN ends the run (Increment 8 owns durable resume).
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
    initial = create_lifecycle_state(
        mission_id=_resolve_mission_id(mission_id),
        run_id=run_id or context.run_id,
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
    )
    result = app.invoke({"lifecycle": initial})
    lifecycle = result.get("lifecycle")
    if lifecycle is None or not isinstance(lifecycle, ConstructorLifecycleState):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "LangGraph invoke did not return ConstructorLifecycleState",
        )
    if lifecycle.status not in TERMINAL_STATUSES:
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            f"LangGraph ended on non-terminal status {lifecycle.status}",
        )
    return lifecycle
