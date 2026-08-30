"""
Constructor Runtime v0.1 Increment 8 — durable checkpoint serializer / factory surface.

NO automatic database connection.
NO saver.setup().
NO DDL.
Graph business state remains ConstructorLifecycleState only.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence, Tuple

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from agents.monthly_plan_constructor.hitl_contracts import (
    CODE_HITL_CONTRACT_BLOCKER,
    HitlContractError,
)
from agents.monthly_plan_constructor.lifecycle import (
    CODE_LIFECYCLE_CONTRACT_BLOCKER,
    LifecycleError,
)
from security.agent_execution_context import AgentExecutionContext

# Explicit Constructor artifact allowlist for msgpack deserialization.
# Do not use wildcard / True in production Constructor checkpointers.
ConstructorMsgpackAllowEntry = Tuple[str, str]

CONSTRUCTOR_MSGPACK_ALLOWLIST: tuple[ConstructorMsgpackAllowEntry, ...] = (
    # lifecycle
    ("agents.monthly_plan_constructor.lifecycle", "ConstructorLifecycleState"),
    ("agents.monthly_plan_constructor.lifecycle", "LifecycleTransition"),
    # mission scope
    ("agents.monthly_plan_constructor.mission_scope", "ConstructorMissionScope"),
    # secure read
    ("agents.monthly_plan_constructor.secure_read_tools", "ConstructorRealityRead"),
    ("agents.monthly_plan_constructor.secure_read_tools", "ConstructorRealityRow"),
    ("agents.monthly_plan_constructor.secure_read_tools", "ConstructorReadProvenance"),
    ("agents.monthly_plan_constructor.secure_read_tools", "ScopeReadCapabilities"),
    # candidate package
    ("agents.monthly_plan_constructor.candidate_package", "CandidatePackage"),
    ("agents.monthly_plan_constructor.candidate_package", "CandidateRecord"),
    ("agents.monthly_plan_constructor.candidate_package", "CandidatePackageSummary"),
    ("agents.monthly_plan_constructor.candidate_package", "LaborNormSummary"),
    ("agents.monthly_plan_constructor.candidate_package", "PackageExceptionSummary"),
    ("agents.monthly_plan_constructor.candidate_package", "CandidatePackageProvenance"),
    ("agents.monthly_plan_constructor.candidate_package", "CandidatePackageReference"),
    # labor
    ("agents.monthly_plan_constructor.labor_norm_resolver", "LaborNormResolutionSet"),
    ("agents.monthly_plan_constructor.labor_norm_resolver", "LaborNormResolution"),
    ("agents.monthly_plan_constructor.labor_norm_resolver", "LaborNormEvidence"),
    # exceptions
    ("agents.monthly_plan_constructor.exception_engine", "ConstructorExceptionSet"),
    ("agents.monthly_plan_constructor.exception_engine", "ConstructorException"),
    ("agents.monthly_plan_constructor.exception_engine", "ConstructorExceptionDetails"),
    # HITL contracts (interrupt / audit payloads may appear beside lifecycle)
    ("agents.monthly_plan_constructor.hitl_contracts", "ConstructorHumanDecisionRequest"),
    ("agents.monthly_plan_constructor.hitl_contracts", "ConstructorResumeCommand"),
    ("agents.monthly_plan_constructor.hitl_contracts", "ScopeSummary"),
)


def build_constructor_jsonplus_serializer(
    *,
    pickle_fallback: bool = False,
    extra_allowed_msgpack_modules: Optional[
        Sequence[ConstructorMsgpackAllowEntry]
    ] = None,
) -> JsonPlusSerializer:
    """
    Safe Constructor checkpoint serializer.

    pickle_fallback must remain False for business checkpoints.
    """
    if pickle_fallback:
        raise ValueError(
            "pickle_fallback=True is forbidden for Constructor durable checkpoints"
        )
    allow: list[ConstructorMsgpackAllowEntry] = list(CONSTRUCTOR_MSGPACK_ALLOWLIST)
    if extra_allowed_msgpack_modules:
        allow.extend(tuple(item) for item in extra_allowed_msgpack_modules)
    return JsonPlusSerializer(
        pickle_fallback=False,
        allowed_msgpack_modules=allow,
    )


def build_postgres_checkpointer(
    conn: Any,
    *,
    pipe: Any = None,
    serde: Optional[JsonPlusSerializer] = None,
) -> Any:
    """
    Explicit PostgresSaver construction from an ALREADY OPEN connection.

    Does not:
    - read DSN from environment into graph state;
    - open a connection;
    - call saver.setup();
    - execute DDL.

    Caller owns infrastructure connection lifecycle and a later setup gate.
    """
    from langgraph.checkpoint.postgres import PostgresSaver

    return PostgresSaver(
        conn,
        pipe=pipe,
        serde=serde or build_constructor_jsonplus_serializer(),
    )


def resolve_current_checkpoint_id(
    checkpointer: Any,
    *,
    thread_id: str,
    checkpoint_id: Optional[str] = None,
    checkpoint_ns: str = "",
) -> str:
    """
    Resolve the opaque current checkpoint_id from an already-open checkpointer.

    thread_id must equal run_id. Does not open connections or call setup().
    """
    if checkpointer is None:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "checkpointer is required to resolve checkpoint_id",
        )
    tid = str(thread_id or "").strip()
    if not tid:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "thread_id is required to resolve checkpoint_id",
        )
    configurable: dict[str, Any] = {
        "thread_id": tid,
        "checkpoint_ns": checkpoint_ns,
    }
    if checkpoint_id is not None and str(checkpoint_id).strip():
        configurable["checkpoint_id"] = str(checkpoint_id).strip()
    tup = checkpointer.get_tuple({"configurable": configurable})
    if tup is None:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "durable checkpoint not found",
        )
    found = None
    cfg = getattr(tup, "config", None)
    if isinstance(cfg, dict):
        found = (cfg.get("configurable") or {}).get("checkpoint_id")
    if found is None or not str(found).strip():
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "checkpoint_id missing from runtime tuple",
        )
    return str(found).strip()


def require_durable_resume_checkpoint(
    *,
    expected_checkpoint_id: Optional[str],
    current_checkpoint_id: Optional[str],
    context: Any,
) -> str:
    """
    Fail-closed durable resume gate.

    expected_checkpoint_id is mandatory at the durability boundary.
    current_checkpoint_id must already be resolved from PostgreSQL/runtime.
    context must be a live AgentExecutionContext — never deserialized from
    a checkpoint.
    """
    if context is None or not isinstance(context, AgentExecutionContext):
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "AgentExecutionContext is required for durable resume",
        )
    if context.is_expired():
        raise LifecycleError(
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
            "AgentExecutionContext expired; revalidation required",
        )
    expected = (
        str(expected_checkpoint_id).strip() if expected_checkpoint_id is not None else ""
    )
    if not expected:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "expected_checkpoint_id is required for durable resume",
        )
    current = (
        str(current_checkpoint_id).strip() if current_checkpoint_id is not None else ""
    )
    if not current:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "current checkpoint_id could not be resolved",
        )
    if expected != current:
        raise HitlContractError(
            CODE_HITL_CONTRACT_BLOCKER,
            "expected_checkpoint_id mismatch",
        )
    return current
