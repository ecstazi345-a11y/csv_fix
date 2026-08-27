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
