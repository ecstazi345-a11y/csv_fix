"""
Increment 11B — Shadow Runtime Composition Root.

Wires existing Run Control + managed launcher + RealDataShadowAdapter.
Does not change Constructor profession, core contracts, quantity law,
HITL behavior, or persistent store policy.

One composition = one adapter = one launcher = one Shadow run.
Constructing the composition does not start a run.

No product writes. No product database client. No plan-line benchmark read.
No Control Room observability env default. No persistent Shadow directory policy.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Union

from agents.monthly_plan_constructor.lifecycle import LaborEvidenceInput
from agents.monthly_plan_constructor.managed_launcher import (
    ConstructorManagedRuntimeLauncher,
)
from agents.monthly_plan_constructor.real_data_assembler import RealDataShadowAdapter
from agents.observability.durable_recorder import StoreObservabilityRecorder
from agents.observability.sqlite_store import SqliteObservabilityStore
from agents.run_control.contracts import (
    ManagedRunStartInput,
    ManagedRunStartResult,
    RunControlRegistry,
)
from agents.run_control.registry import InMemoryRunControlRegistry
from agents.run_control.service import RunControlService

CODE_SHADOW_COMPOSITION_BLOCKER = "SHADOW_COMPOSITION_BLOCKER"
CODE_COMPOSITION_ALREADY_STARTED = "COMPOSITION_ALREADY_STARTED"


class ShadowCompositionError(ValueError):
    """Fail-closed Shadow composition-root violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ConstructorShadowComposition:
    """
    Explicit one-run Shadow wiring.

    Not a singleton. Not a Control Room. Not a persistence policy.
    """

    adapter: RealDataShadowAdapter
    launcher: ConstructorManagedRuntimeLauncher
    service: RunControlService
    observability_db_path: str
    _start_lock: threading.Lock = field(
        default_factory=threading.Lock,
        repr=False,
        compare=False,
    )
    _started: list[bool] = field(
        default_factory=lambda: [False],
        repr=False,
        compare=False,
    )

    def start(
        self,
        start_input: ManagedRunStartInput,
        *,
        requested_at: Optional[datetime] = None,
    ) -> ManagedRunStartResult:
        """
        One-shot managed start. Delegates to RunControlService.

        Does not issue AgentExecutionContext. Run Control remains the issuer.
        """
        with self._start_lock:
            if self._started[0]:
                raise ShadowCompositionError(
                    CODE_COMPOSITION_ALREADY_STARTED,
                    "ConstructorShadowComposition.start is one-shot",
                )
            self._started[0] = True
        return self.service.start(
            start_input,
            launcher=self.launcher,
            requested_at=requested_at,
        )


def build_constructor_shadow_composition(
    *,
    observability_db_path: Union[str, Path],
    checkpointer_factory: Callable[[], Any],
    hitl_store_factory: Callable[[], Any],
    handoff_store_factory: Callable[[], Any],
    labor_evidence: LaborEvidenceInput = (),
    registry: Optional[RunControlRegistry] = None,
) -> ConstructorShadowComposition:
    """
    Wire one Shadow composition. Does not start a run.

    Required store factories are accepted, not invented.
    Persistent Shadow filesystem policy belongs to Increment 11C.
    """
    path_text = _require_observability_db_path(observability_db_path)
    checkpointer_factory = _require_factory(
        checkpointer_factory,
        "checkpointer_factory",
    )
    hitl_store_factory = _require_factory(hitl_store_factory, "hitl_store_factory")
    handoff_store_factory = _require_factory(
        handoff_store_factory,
        "handoff_store_factory",
    )

    adapter = RealDataShadowAdapter()
    launcher = ConstructorManagedRuntimeLauncher(
        observability_db_path=path_text,
        assemble_candidates=adapter,
        scope_reader=adapter.scope_reader,
        labor_evidence=labor_evidence,
        checkpointer_factory=checkpointer_factory,
        hitl_store_factory=hitl_store_factory,
        handoff_store_factory=handoff_store_factory,
    )
    store = _open_observability_store(path_text)
    recorder = StoreObservabilityRecorder(store)
    service = RunControlService(
        registry=registry if registry is not None else InMemoryRunControlRegistry(),
        recorder=recorder,
        durable_store=store,
    )
    return ConstructorShadowComposition(
        adapter=adapter,
        launcher=launcher,
        service=service,
        observability_db_path=path_text,
    )


def _require_observability_db_path(value: Any) -> str:
    if value is None:
        raise ShadowCompositionError(
            CODE_SHADOW_COMPOSITION_BLOCKER,
            "observability_db_path is required",
        )
    if not isinstance(value, (str, Path)):
        raise ShadowCompositionError(
            CODE_SHADOW_COMPOSITION_BLOCKER,
            "observability_db_path must be a filesystem path",
        )
    text = str(value).strip()
    if not text:
        raise ShadowCompositionError(
            CODE_SHADOW_COMPOSITION_BLOCKER,
            "observability_db_path is required",
        )
    path = Path(text)
    if path.exists() and path.is_dir():
        raise ShadowCompositionError(
            CODE_SHADOW_COMPOSITION_BLOCKER,
            "observability_db_path must not be a directory",
        )
    return str(path)


def _require_factory(value: Any, name: str) -> Callable[[], Any]:
    if value is None or not callable(value):
        raise ShadowCompositionError(
            CODE_SHADOW_COMPOSITION_BLOCKER,
            f"{name} is required",
        )
    return value


def _open_observability_store(path_text: str) -> SqliteObservabilityStore:
    try:
        return SqliteObservabilityStore(path_text)
    except ShadowCompositionError:
        raise
    except Exception as exc:
        raise ShadowCompositionError(
            CODE_SHADOW_COMPOSITION_BLOCKER,
            "observability store could not be opened from the explicit path",
        ) from exc
