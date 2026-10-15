"""
Human Review Command Port V1 — owner row decisions into Constructor runtime.

Page 53 stays thin: it only builds a formal HumanReviewCommand and calls
submit_human_review_decision / prepare_human_review_surface.

Does not write product tables. Does not execute Human Confirm or Handoff.
Append-only HumanReviewEvent history; latest event wins for current view.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

from agents.monthly_plan_constructor.candidate_package import CandidatePackage
from agents.monthly_plan_constructor.durable_checkpoint import (
    require_durable_resume_checkpoint,
    resolve_current_checkpoint_id,
)
from agents.monthly_plan_constructor.human_review_contracts import (
    CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
    RESOLUTION_KIND_DEFER_TO_PERIOD,
    HumanReviewContractError,
    HumanReviewDecision,
    HumanReviewEvent,
    build_human_review_event,
    project_effective_human_review_events,
)
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_WAITING_FOR_HUMAN_REVIEW,
    ConstructorLifecycleState,
)
from agents.monthly_plan_constructor.professional_review_resume import (
    ProfessionalHumanReviewResumeCommand,
    SCHEMA_VERSION as REVIEW_RESUME_SCHEMA,
    build_professional_review_wait_request,
)

CODE_HUMAN_REVIEW_COMMAND_BLOCKER = "HUMAN_REVIEW_COMMAND_BLOCKER"
ACTOR_ID_HUMAN_SURFACE = "human-surface-operator"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_RETAINED: list[object] = []
_SUBMIT_LOCK = threading.Lock()


class HumanReviewCommandError(ValueError):
    """Fail-closed Human Review Command Port violation."""

    def __init__(self, message: str, *, code: str = CODE_HUMAN_REVIEW_COMMAND_BLOCKER) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class HumanReviewAction(str, Enum):
    ACCEPT = "ACCEPT"
    EXCLUDE = "EXCLUDE"
    CHANGE_QUANTITY = "CHANGE_QUANTITY"
    NEEDS_DATA = "NEEDS_DATA"
    DEFER_TO_PERIOD = "DEFER_TO_PERIOD"


@dataclass(frozen=True)
class HumanReviewCommand:
    """Formal row decision. UI proposed quantity is never authoritative."""

    run_id: str
    package_id: str
    candidate_id: str
    action: HumanReviewAction
    expected_checkpoint_id: str
    approved_qty: Optional[float] = None
    reason_text: Optional[str] = None
    actor_id: str = ACTOR_ID_HUMAN_SURFACE
    resolution_kind: Optional[str] = None
    target_period: Optional[str] = None


@dataclass(frozen=True)
class HumanReviewCandidateContext:
    candidate_id: str
    facility: str
    discipline: str
    system: str
    iwp: str
    boq_code: str
    name: str
    unit: str
    remaining_qty: float
    already_planned_qty: float
    constructor_proposed_qty: float
    current_decision_label: str
    warning_lines: tuple[str, ...]
    human_approved_qty: Optional[float] = None
    reason_text: Optional[str] = None


@dataclass(frozen=True)
class HumanReviewSurfaceSnapshot:
    run_id: str
    mission_id: str
    package_id: str
    professional_status: str
    expected_checkpoint_id: str
    interrupt_id: str
    candidates: tuple[HumanReviewCandidateContext, ...]
    reviewed_count: int
    accepted_count: int
    changed_qty_count: int
    excluded_count: int
    deferred_count: int
    needs_data_count: int
    not_reviewed_count: int


@dataclass(frozen=True)
class HumanReviewSubmitResult:
    run_id: str
    candidate_id: str
    action: HumanReviewAction
    decision: HumanReviewDecision
    review_event_id: str
    professional_status: str
    expected_checkpoint_id: str
    constructor_proposed_qty: float
    human_approved_qty: Optional[float]
    reason_text: Optional[str]


class HumanReviewRuntimePort(Protocol):
    """Injectable durable runtime boundary for tests and production."""

    def load_lifecycle(self, run_id: str) -> ConstructorLifecycleState: ...

    def current_checkpoint_id(self, run_id: str) -> str: ...

    def resume_professional_review(
        self,
        *,
        run_id: str,
        resume_command: ProfessionalHumanReviewResumeCommand,
    ) -> ConstructorLifecycleState: ...


def _text(value: Any) -> str:
    return str(value or "").strip()


def _require_text(value: Any, field: str) -> str:
    text = _text(value)
    if not text:
        raise HumanReviewCommandError(f"{field} is required")
    return text


def _finite_qty(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HumanReviewCommandError(f"{field} must be a finite number")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise HumanReviewCommandError(f"{field} must be a finite number")
    return number


def _decision_label(event: Optional[HumanReviewEvent]) -> str:
    if event is None:
        return "НЕ РАССМОТРЕНО"
    if event.decision is HumanReviewDecision.REMOVE:
        if str(event.resolution_kind or "").upper() == RESOLUTION_KIND_DEFER_TO_PERIOD:
            return "ПЕРЕНЕСЕНО"
        return "ИСКЛЮЧЕНО"
    if event.decision is HumanReviewDecision.REQUIRES_CLARIFICATION:
        return "НУЖНЫ ДАННЫЕ"
    if event.decision is HumanReviewDecision.ADD:
        proposed = event.constructor_proposed_qty
        approved = event.human_approved_qty
        if (
            proposed is not None
            and approved is not None
            and abs(float(approved) - float(proposed)) > 1e-12
        ):
            return "ИЗМЕНЁН ОБЪЁМ"
        return "ПРИНЯТО"
    return "НЕ РАССМОТРЕНО"


def _action_to_decision(action: HumanReviewAction) -> HumanReviewDecision:
    if action is HumanReviewAction.ACCEPT:
        return HumanReviewDecision.ADD
    if action is HumanReviewAction.EXCLUDE:
        return HumanReviewDecision.REMOVE
    if action is HumanReviewAction.DEFER_TO_PERIOD:
        return HumanReviewDecision.REMOVE
    if action is HumanReviewAction.CHANGE_QUANTITY:
        return HumanReviewDecision.ADD
    if action is HumanReviewAction.NEEDS_DATA:
        return HumanReviewDecision.REQUIRES_CLARIFICATION
    raise HumanReviewCommandError(f"unsupported action {action!r}")


def _find_candidate(package: CandidatePackage, candidate_id: str) -> Any:
    for item in package.candidates:
        if str(item.candidate_id) == candidate_id:
            return item
    raise HumanReviewCommandError(
        f"candidate_id {candidate_id!r} is not in package",
        code=CODE_HUMAN_REVIEW_CONTRACT_BLOCKER,
    )


def require_durable_human_review_event_ids(
    lifecycle: ConstructorLifecycleState,
    expected_event_ids: Sequence[str],
    *,
    where: str,
) -> None:
    """Fail closed unless every expected review_event_id is present on lifecycle."""
    have = {
        str(event.review_event_id)
        for event in tuple(lifecycle.human_review_events or ())
    }
    missing = [eid for eid in expected_event_ids if str(eid) not in have]
    if missing:
        raise HumanReviewCommandError(
            f"durable Human Review {where} missing committed events "
            f"(missing={len(missing)}, expected={len(tuple(expected_event_ids))})",
            code=CODE_HUMAN_REVIEW_COMMAND_BLOCKER,
        )


def _validate_and_build_event(
    command: HumanReviewCommand,
    *,
    lifecycle: ConstructorLifecycleState,
    reviewed_at: datetime,
) -> HumanReviewEvent:
    run_id = _require_text(command.run_id, "run_id")
    package_id = _require_text(command.package_id, "package_id")
    candidate_id = _require_text(command.candidate_id, "candidate_id")
    expected = _require_text(command.expected_checkpoint_id, "expected_checkpoint_id")
    if not isinstance(command.action, HumanReviewAction):
        raise HumanReviewCommandError("unsupported action")
    if lifecycle.status != STATUS_WAITING_FOR_HUMAN_REVIEW:
        raise HumanReviewCommandError(
            f"run is not waiting for Human Review (status={lifecycle.status})",
        )
    if lifecycle.package is None:
        raise HumanReviewCommandError("candidate package is missing")
    package = lifecycle.package
    if str(package.package_id) != package_id:
        raise HumanReviewCommandError("package_id mismatch")
    if str(lifecycle.run_id) != run_id:
        raise HumanReviewCommandError("run_id mismatch")
    candidate = _find_candidate(package, candidate_id)
    proposed = _finite_qty(candidate.available_to_add_qty, "constructor_proposed_qty")
    reason = _text(command.reason_text) or None
    approved: Optional[float] = None
    action = command.action
    if action is HumanReviewAction.ACCEPT:
        approved = proposed
        # comment optional when quantity unchanged
    elif action is HumanReviewAction.EXCLUDE:
        if not reason:
            raise HumanReviewCommandError("EXCLUDE requires reason_text")
        approved = 0.0
    elif action is HumanReviewAction.CHANGE_QUANTITY:
        if not reason:
            raise HumanReviewCommandError("CHANGE_QUANTITY requires reason_text")
        if command.approved_qty is None:
            raise HumanReviewCommandError("CHANGE_QUANTITY requires approved_qty")
        approved = _finite_qty(command.approved_qty, "approved_qty")
        if approved <= 0:
            raise HumanReviewCommandError("approved_qty must be > 0")
        if approved > proposed + 1e-12:
            raise HumanReviewCommandError(
                "approved_qty must not exceed Constructor proposed quantity",
            )
    elif action is HumanReviewAction.NEEDS_DATA:
        if not reason:
            raise HumanReviewCommandError("NEEDS_DATA requires reason_text")
        approved = None
    elif action is HumanReviewAction.DEFER_TO_PERIOD:
        if not reason:
            raise HumanReviewCommandError("DEFER_TO_PERIOD requires reason_text")
        if not _text(command.target_period):
            raise HumanReviewCommandError("DEFER_TO_PERIOD requires target_period")
        approved = 0.0
    else:
        raise HumanReviewCommandError(f"unsupported action {action!r}")

    resolution_kind = _text(command.resolution_kind) or None
    target_period = _text(command.target_period) or None
    if action is HumanReviewAction.DEFER_TO_PERIOD:
        resolution_kind = RESOLUTION_KIND_DEFER_TO_PERIOD
        target_period = _text(command.target_period)

    try:
        return build_human_review_event(
            review_event_id=f"hre-{uuid.uuid4().hex}",
            run_id=run_id,
            mission_id=str(lifecycle.mission_id),
            package_id=package_id,
            candidate_id=candidate_id,
            decision=_action_to_decision(action),
            actor_id=_require_text(command.actor_id, "actor_id"),
            reviewed_at=reviewed_at,
            constructor_proposed_qty=proposed,
            human_approved_qty=approved,
            reason_text=reason,
            resolution_kind=resolution_kind,
            target_period=target_period,
        )
    except HumanReviewContractError as exc:
        raise HumanReviewCommandError(str(exc), code=getattr(exc, "code", CODE_HUMAN_REVIEW_COMMAND_BLOCKER)) from exc


def prepare_human_review_surface(
    run_id: str,
    *,
    runtime: Optional[HumanReviewRuntimePort] = None,
) -> HumanReviewSurfaceSnapshot:
    """Read-only surface binding for Page 53 Human Decision area."""
    port = runtime or default_human_review_runtime()
    lifecycle = port.load_lifecycle(run_id)
    if lifecycle.status != STATUS_WAITING_FOR_HUMAN_REVIEW:
        raise HumanReviewCommandError(
            f"run is not waiting for Human Review (status={lifecycle.status})",
        )
    if lifecycle.package is None:
        raise HumanReviewCommandError("candidate package is missing")
    checkpoint_id = port.current_checkpoint_id(run_id)
    wait = build_professional_review_wait_request(lifecycle)
    effective = project_effective_human_review_events(
        tuple(lifecycle.human_review_events or ()),
        lifecycle.package,
    )
    contexts: list[HumanReviewCandidateContext] = []
    accepted = changed = excluded = deferred = needs = 0
    for item in lifecycle.package.candidates:
        event = effective.get(str(item.candidate_id))
        label = _decision_label(event)
        if label == "ПРИНЯТО":
            accepted += 1
        elif label == "ИЗМЕНЁН ОБЪЁМ":
            changed += 1
        elif label == "ИСКЛЮЧЕНО":
            excluded += 1
        elif label == "ПЕРЕНЕСЕНО":
            deferred += 1
        elif label == "НУЖНЫ ДАННЫЕ":
            needs += 1
        warnings: list[str] = []
        rem = float(item.remaining_qty)
        plan = float(item.already_planned_qty)
        if plan > rem + 1e-12:
            warnings.append("План > текущего остатка")
        approved_qty = None
        reason = None
        if event is not None:
            if event.human_approved_qty is not None:
                approved_qty = float(event.human_approved_qty)
            reason = str(event.reason_text or "").strip() or None
        contexts.append(
            HumanReviewCandidateContext(
                candidate_id=str(item.candidate_id),
                facility=str(item.facility or ""),
                discipline=str(item.discipline or ""),
                system=str(item.system or ""),
                iwp=str(item.iwp or ""),
                boq_code=str(item.boq_code or ""),
                name=str(item.boq_name or ""),
                unit=str(item.unit or ""),
                remaining_qty=rem,
                already_planned_qty=plan,
                constructor_proposed_qty=float(item.available_to_add_qty),
                current_decision_label=label,
                warning_lines=tuple(warnings),
                human_approved_qty=approved_qty,
                reason_text=reason,
            )
        )
    total = len(contexts)
    reviewed = accepted + changed + excluded + deferred + needs
    return HumanReviewSurfaceSnapshot(
        run_id=str(lifecycle.run_id),
        mission_id=str(lifecycle.mission_id),
        package_id=str(lifecycle.package.package_id),
        professional_status=str(lifecycle.status),
        expected_checkpoint_id=checkpoint_id,
        interrupt_id=wait.interrupt_id,
        candidates=tuple(contexts),
        reviewed_count=reviewed,
        accepted_count=accepted,
        changed_qty_count=changed,
        excluded_count=excluded,
        deferred_count=deferred,
        needs_data_count=needs,
        not_reviewed_count=max(0, total - reviewed),
    )


def submit_human_review_decision(
    command: HumanReviewCommand,
    *,
    runtime: Optional[HumanReviewRuntimePort] = None,
    now: Optional[datetime] = None,
) -> HumanReviewSubmitResult:
    """Validate → checkpoint-bound resume → durable append-only HumanReviewEvent."""
    port = runtime or default_human_review_runtime()
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise HumanReviewCommandError("now must be timezone-aware UTC")
    stamp = stamp.astimezone(timezone.utc)

    with _SUBMIT_LOCK:
        lifecycle = port.load_lifecycle(command.run_id)
        current_ckpt = port.current_checkpoint_id(command.run_id)
        expected = _require_text(command.expected_checkpoint_id, "expected_checkpoint_id")
        if expected != current_ckpt:
            raise HumanReviewCommandError(
                "expected_checkpoint_id is stale; reload Human Review surface",
            )
        event = _validate_and_build_event(
            command,
            lifecycle=lifecycle,
            reviewed_at=stamp,
        )
        wait = build_professional_review_wait_request(lifecycle, created_at=stamp)
        resume = ProfessionalHumanReviewResumeCommand(
            schema_version=REVIEW_RESUME_SCHEMA,
            interrupt_id=wait.interrupt_id,
            run_id=str(lifecycle.run_id),
            review_events=(event,),
            answered_at=stamp,
            expected_checkpoint_id=expected,
        )
        updated = port.resume_professional_review(
            run_id=str(lifecycle.run_id),
            resume_command=resume,
        )
        expected_ids = (str(event.review_event_id),)
        require_durable_human_review_event_ids(
            updated,
            expected_ids,
            where="resume result",
        )
        durable = port.load_lifecycle(str(lifecycle.run_id))
        require_durable_human_review_event_ids(
            durable,
            expected_ids,
            where="readback",
        )
        return HumanReviewSubmitResult(
            run_id=str(durable.run_id),
            candidate_id=event.candidate_id,
            action=command.action,
            decision=event.decision,
            review_event_id=event.review_event_id,
            professional_status=str(durable.status),
            expected_checkpoint_id=port.current_checkpoint_id(str(durable.run_id)),
            constructor_proposed_qty=float(event.constructor_proposed_qty or 0.0),
            human_approved_qty=event.human_approved_qty,
            reason_text=event.reason_text,
        )


# ---------------------------------------------------------------------------
# Production runtime adapter (shadow stores + LangGraph resume)
# ---------------------------------------------------------------------------


class _ShadowHumanReviewRuntime:
    def __init__(self, *, repository_root: Path) -> None:
        self._root = repository_root

    def _writer_checkpoint_path(self) -> Path:
        """Same checkpoints.sqlite the Human Review reader / Query Port observe."""
        from agents.control_room.constructor_professional_result_reader import (
            sibling_checkpoint_path,
        )
        from agents.control_room.factory import resolve_observability_db_path

        return sibling_checkpoint_path(resolve_observability_db_path())

    def _open_checkpointer(self) -> Any:
        from agents.monthly_plan_constructor.shadow_checkpoint_store import (
            open_constructor_shadow_checkpoint_store,
        )

        # Writer identity MUST match reader: sibling of AGENT_OBSERVABILITY_DB_PATH.
        store = open_constructor_shadow_checkpoint_store(
            checkpoints_db_path=self._writer_checkpoint_path(),
        )
        _RETAINED.append(store)
        return store.checkpointer

    def load_lifecycle(self, run_id: str) -> ConstructorLifecycleState:
        from agents.control_room.constructor_professional_result_reader import (
            _load_lifecycle,
        )

        ckpt = self._writer_checkpoint_path()
        lifecycle = _load_lifecycle(ckpt, thread_id=_require_text(run_id, "run_id"))
        if lifecycle is None or not isinstance(lifecycle, ConstructorLifecycleState):
            raise HumanReviewCommandError("run checkpoint / lifecycle not found")
        return lifecycle

    def current_checkpoint_id(self, run_id: str) -> str:
        checkpointer = self._open_checkpointer()
        resolved = resolve_current_checkpoint_id(
            checkpointer,
            thread_id=_require_text(run_id, "run_id"),
            checkpoint_id=None,
        )
        if not resolved:
            raise HumanReviewCommandError("current checkpoint_id is unavailable")
        return str(resolved)

    def resume_professional_review(
        self,
        *,
        run_id: str,
        resume_command: ProfessionalHumanReviewResumeCommand,
    ) -> ConstructorLifecycleState:
        from langgraph.types import Command

        from agents.monthly_plan_constructor.langgraph_runtime import (
            build_constructor_langgraph,
        )
        from agents.monthly_plan_constructor.real_data_assembler import (
            RealDataShadowAdapter,
        )
        from agents.monthly_plan_constructor.shadow_handoff_store import (
            bootstrap_constructor_shadow_handoff_store,
        )
        from agents.monthly_plan_constructor.shadow_hitl_store import (
            bootstrap_constructor_shadow_hitl_store,
        )
        from security.agent_execution_context import issue_read_only_agent_context

        lifecycle = self.load_lifecycle(run_id)
        expected = _require_text(
            resume_command.expected_checkpoint_id,
            "expected_checkpoint_id",
        )
        checkpointer = self._open_checkpointer()
        context = issue_read_only_agent_context(
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            project_code=str(lifecycle.scope.project_code if lifecycle.scope else ""),
            run_id=str(lifecycle.run_id),
        )
        require_durable_resume_checkpoint(
            expected_checkpoint_id=expected,
            current_checkpoint_id=resolve_current_checkpoint_id(
                checkpointer,
                thread_id=str(lifecycle.run_id),
                checkpoint_id=None,
            ),
            context=context,
        )
        adapter = RealDataShadowAdapter()
        hitl = bootstrap_constructor_shadow_hitl_store(repository_root=self._root)
        handoff = bootstrap_constructor_shadow_handoff_store(repository_root=self._root)
        _RETAINED.extend([hitl, handoff])
        scope = lifecycle.scope
        if scope is None:
            raise HumanReviewCommandError("mission scope missing on lifecycle")
        app = build_constructor_langgraph(
            context=context,
            project_code=scope.project_code,
            month_key=scope.month_key,
            assemble_candidates=adapter,
            scope_reader=adapter.scope_reader,
            facility_scope=scope.facility_scope,
            discipline_scope=scope.discipline_scope,
            system_scope=scope.system_scope,
            iwp_scope=scope.iwp_scope,
            queue_scope=scope.queue_scope,
            checkpointer=checkpointer,
            hitl_store=hitl,
            handoff_store=handoff,
            now=resume_command.answered_at,
        )
        config = {"configurable": {"thread_id": str(lifecycle.run_id)}}
        out = app.invoke(Command(resume=resume_command), config)
        updated = out.get("lifecycle") if isinstance(out, dict) else None
        if not isinstance(updated, ConstructorLifecycleState):
            snap = app.get_state(config)
            values = getattr(snap, "values", None) or {}
            updated = values.get("lifecycle")
        if not isinstance(updated, ConstructorLifecycleState):
            raise HumanReviewCommandError("resume did not return ConstructorLifecycleState")
        return updated


_DEFAULT_RUNTIME: Optional[HumanReviewRuntimePort] = None


def default_human_review_runtime(
    *,
    repository_root: Optional[Path] = None,
) -> HumanReviewRuntimePort:
    global _DEFAULT_RUNTIME
    if _DEFAULT_RUNTIME is None:
        _DEFAULT_RUNTIME = _ShadowHumanReviewRuntime(
            repository_root=repository_root or _REPOSITORY_ROOT,
        )
    return _DEFAULT_RUNTIME


def reset_default_human_review_runtime_for_tests() -> None:
    """Test helper only."""
    global _DEFAULT_RUNTIME
    _DEFAULT_RUNTIME = None
