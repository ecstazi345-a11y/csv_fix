"""
Constructor Managed Runtime Launcher — local managed runtime backend v0.1.

Accepts/schedules authorized Constructor execution on a background thread.
Successful launch() return means scheduling only — not RUNNING or graph completion.

This thread backend is replaceable by future subprocess / external worker backends
without changing Run Control or observability contracts.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Optional, Union

from agents.monthly_plan_constructor.langgraph_runtime import (
    CONSTRUCTOR_AGENT_CODE,
    run_constructor_langgraph,
)
from agents.monthly_plan_constructor.lifecycle import (
    CandidateAssembler,
    LaborEvidenceInput,
)
from agents.monthly_plan_constructor.secure_read_tools import ScopeReader
from agents.observability.contracts import AgentRun, RunRequest
from agents.observability.durable_recorder import StoreObservabilityRecorder
from agents.observability.sqlite_store import SqliteObservabilityStore
from security.agent_execution_context import AgentExecutionContext

CODE_MANAGED_LAUNCHER_BLOCKER = "MANAGED_LAUNCHER_BLOCKER"


class ManagedLauncherError(ValueError):
    """Fail-closed Constructor managed launcher violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ConstructorManagedRuntimeLauncher:
    """
    Constructor-specific ManagedRuntimeLauncher bridge.

    Local backend v0.1: background thread in the same Python process.
    AgentExecutionContext is passed by object reference — valid only for this backend.
    Future subprocess/external workers must reconstruct safe context from stable refs.
    """

    def __init__(
        self,
        *,
        observability_db_path: Union[str, Path],
        assemble_candidates: CandidateAssembler,
        scope_reader: ScopeReader,
        labor_evidence: LaborEvidenceInput = (),
        handoff_store_factory: Optional[Callable[[], Any]] = None,
        checkpointer_factory: Optional[Callable[[], Any]] = None,
        hitl_store_factory: Optional[Callable[[], Any]] = None,
        daemon: bool = False,
    ) -> None:
        if assemble_candidates is None or not callable(assemble_candidates):
            raise ManagedLauncherError(
                CODE_MANAGED_LAUNCHER_BLOCKER,
                "assemble_candidates is required",
            )
        if scope_reader is None or not callable(scope_reader):
            raise ManagedLauncherError(
                CODE_MANAGED_LAUNCHER_BLOCKER,
                "scope_reader is required",
            )
        self._observability_db_path = str(observability_db_path)
        self._assemble_candidates = assemble_candidates
        self._scope_reader = scope_reader
        self._labor_evidence = labor_evidence
        self._handoff_store_factory = handoff_store_factory
        self._checkpointer_factory = checkpointer_factory
        self._hitl_store_factory = hitl_store_factory
        self._daemon = daemon
        self._last_thread: threading.Thread | None = None

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
        worker = threading.Thread(
            target=self._run_worker,
            args=(run_request, agent_run, context),
            name=f"constructor-runtime-{agent_run.run_id}",
            daemon=self._daemon,
        )
        worker.start()
        self._last_thread = worker

    def _validate_launch_envelope(
        self,
        *,
        run_request: RunRequest,
        agent_run: AgentRun,
        context: AgentExecutionContext,
    ) -> None:
        if run_request.agent_code != CONSTRUCTOR_AGENT_CODE:
            raise ManagedLauncherError(
                CODE_MANAGED_LAUNCHER_BLOCKER,
                f"agent_code must be {CONSTRUCTOR_AGENT_CODE!r}",
            )
        if agent_run.agent_code != CONSTRUCTOR_AGENT_CODE:
            raise ManagedLauncherError(
                CODE_MANAGED_LAUNCHER_BLOCKER,
                f"agent_run.agent_code must be {CONSTRUCTOR_AGENT_CODE!r}",
            )
        if context.agent_code != CONSTRUCTOR_AGENT_CODE:
            raise ManagedLauncherError(
                CODE_MANAGED_LAUNCHER_BLOCKER,
                f"context.agent_code must be {CONSTRUCTOR_AGENT_CODE!r}",
            )
        if agent_run.run_id != context.run_id:
            raise ManagedLauncherError(
                CODE_MANAGED_LAUNCHER_BLOCKER,
                "agent_run.run_id must equal context.run_id",
            )
        if run_request.project_code != agent_run.project_code:
            raise ManagedLauncherError(
                CODE_MANAGED_LAUNCHER_BLOCKER,
                "run_request.project_code must equal agent_run.project_code",
            )
        if context.project_code != agent_run.project_code:
            raise ManagedLauncherError(
                CODE_MANAGED_LAUNCHER_BLOCKER,
                "context.project_code must equal agent_run.project_code",
            )
        if agent_run.mission_id != run_request.requested_mission_id:
            raise ManagedLauncherError(
                CODE_MANAGED_LAUNCHER_BLOCKER,
                "agent_run.mission_id must equal run_request.requested_mission_id",
            )
        if agent_run.authorization_id is not None:
            if context.authorization_id != agent_run.authorization_id:
                raise ManagedLauncherError(
                    CODE_MANAGED_LAUNCHER_BLOCKER,
                    "authorization_id mismatch between AgentRun and AgentExecutionContext",
                )

    def _run_worker(
        self,
        run_request: RunRequest,
        agent_run: AgentRun,
        context: AgentExecutionContext,
    ) -> None:
        store = SqliteObservabilityStore(self._observability_db_path)
        try:
            recorder = StoreObservabilityRecorder(store)
            scope_kwargs = _scope_kwargs_from_run(run_request, agent_run)
            handoff_store = (
                self._handoff_store_factory() if self._handoff_store_factory else None
            )
            checkpointer = (
                self._checkpointer_factory() if self._checkpointer_factory else None
            )
            hitl_store = self._hitl_store_factory() if self._hitl_store_factory else None
            run_constructor_langgraph(
                context=context,
                project_code=run_request.project_code,
                month_key=run_request.month_key,
                assemble_candidates=self._assemble_candidates,
                labor_evidence=self._labor_evidence,
                scope_reader=self._scope_reader,
                mission_id=run_request.requested_mission_id,
                run_id=agent_run.run_id,
                checkpointer=checkpointer,
                hitl_store=hitl_store,
                handoff_store=handoff_store,
                orchestration_run_id=run_request.orchestration_run_id,
                security_policy_version=context.security_policy_version,
                recorder=recorder,
                **scope_kwargs,
            )
        finally:
            store.close()


def _scope_kwargs_from_run(
    run_request: RunRequest,
    agent_run: AgentRun,
) -> dict[str, Any]:
    scope = _scope_mapping(run_request, agent_run)
    kwargs: dict[str, Any] = {}
    for source_key, target_key in (
        ("facility", "facility_scope"),
        ("facility_building", "facility_scope"),
        ("discipline", "discipline_scope"),
        ("construction_discipline", "discipline_scope"),
        ("system", "system_scope"),
        ("system_label", "system_scope"),
        ("iwp", "iwp_scope"),
        ("iwp_id", "iwp_scope"),
        ("queue", "queue_scope"),
    ):
        if source_key in scope and kwargs.get(target_key) is None:
            kwargs[target_key] = scope[source_key]
    return kwargs


def _scope_mapping(run_request: RunRequest, agent_run: AgentRun) -> dict[str, Any]:
    from agents.observability.contracts import _unfreeze_jsonable

    merged: dict[str, Any] = {}
    request_scope = _unfreeze_jsonable(run_request.scope_request)
    if isinstance(request_scope, dict):
        merged.update(request_scope)
    run_scope = _unfreeze_jsonable(agent_run.scope_summary)
    if isinstance(run_scope, dict):
        merged.update(run_scope)
    return merged
