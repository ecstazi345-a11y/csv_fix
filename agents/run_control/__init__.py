"""
Execution OS Increment 10.2 — agent-neutral Run Control.

Process-local idempotency / start coordination only.
NON-DURABLE. NOT observability store. NOT AgentRun projection store.
"""

from agents.run_control.contracts import (
    CODE_CONTROL_PLANE_FAILURE,
    CODE_IDEMPOTENCY_CONFLICT,
    CODE_IDEMPOTENCY_IN_PROGRESS,
    CODE_LAUNCH_OUTCOME_UNKNOWN,
    CODE_RUN_CONTROL_BLOCKER,
    CODE_SYSTEM_EVENT_DIRECT_START_FORBIDDEN,
    ManagedRunStartInput,
    ManagedRunStartResult,
    ManagedRuntimeLauncher,
    ReservationDecision,
    ReservationKind,
    ReservationState,
    RunControlError,
    RunControlRegistry,
    StartOutcome,
    TerminalFailureKind,
    TerminalFailureRecord,
)
from agents.run_control.registry import InMemoryRunControlRegistry
from agents.run_control.service import RunControlService

__all__ = [
    "CODE_CONTROL_PLANE_FAILURE",
    "CODE_IDEMPOTENCY_CONFLICT",
    "CODE_IDEMPOTENCY_IN_PROGRESS",
    "CODE_LAUNCH_OUTCOME_UNKNOWN",
    "CODE_RUN_CONTROL_BLOCKER",
    "CODE_SYSTEM_EVENT_DIRECT_START_FORBIDDEN",
    "InMemoryRunControlRegistry",
    "ManagedRunStartInput",
    "ManagedRunStartResult",
    "ManagedRuntimeLauncher",
    "ReservationDecision",
    "ReservationKind",
    "ReservationState",
    "RunControlError",
    "RunControlRegistry",
    "RunControlService",
    "StartOutcome",
    "TerminalFailureKind",
    "TerminalFailureRecord",
]
