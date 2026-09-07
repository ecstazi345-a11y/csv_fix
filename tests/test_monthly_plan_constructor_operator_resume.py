"""
Increment 11D — bounded operator / resume path.

Explicit ConstructorResumeCommand is mandatory. Process B does not auto-resume.
Live AgentExecutionContext is resume execution authorization.
Operator actor_id is structured attribution, not authenticated human identity.

HUMAN_IDENTITY_AUTHENTICATION: NOT IMPLEMENTED
ENTERPRISE_IAM: NOT IMPLEMENTED
AUTOMATIC_PROCESS_RECOVERY: NOT IMPLEMENTED
CROSS_STORE_ATOMICITY: NOT CLAIMED
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_ROOT_STR = str(REPO_ROOT)
if _ROOT_STR not in sys.path:
    sys.path.insert(0, _ROOT_STR)

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
)
from agents.monthly_plan_constructor.durable_checkpoint import (
    build_constructor_jsonplus_serializer,
    resolve_current_checkpoint_id,
)
from agents.monthly_plan_constructor.exception_engine import (
    CODE_AMBIGUOUS_SCOPE,
    CODE_READ_FAILED,
)
from agents.monthly_plan_constructor.hitl_contracts import (
    ACTOR_TYPE_HUMAN,
    ACTOR_TYPE_LOCAL_APPLICATION,
    CODE_HITL_CONTRACT_BLOCKER,
    DECISION_ABORT_RUN,
    DECISION_CLARIFY_SCOPE,
    HitlContractError,
    build_resume_command,
    compute_eos_interrupt_id,
)
from agents.monthly_plan_constructor.hitl_resume import (
    build_decision_request_from_lifecycle,
    validate_constructor_resume_command,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_OBSERVED_PRODUCTIVITY,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    LaborNormEvidence,
    SOURCE_PROJECT_HISTORY,
)
from agents.monthly_plan_constructor.langgraph_runtime import (
    CONSTRUCTOR_AGENT_CODE,
    build_constructor_langgraph,
    run_constructor_langgraph,
)
from agents.monthly_plan_constructor.lifecycle import (
    CODE_LIFECYCLE_CONTRACT_BLOCKER,
    STATUS_FAILED,
    STATUS_READY_FOR_HANDOFF,
    STATUS_WAITING_FOR_HUMAN,
    CandidateAssemblyResult,
    ConstructorLifecycleState,
    LifecycleError,
    create_lifecycle_state,
)
from agents.monthly_plan_constructor.mission_scope import ConstructorMissionScope
from agents.monthly_plan_constructor.secure_read_tools import SecureReadError
from agents.monthly_plan_constructor.shadow_checkpoint_store import (
    bootstrap_constructor_shadow_checkpoint_store,
)
from agents.monthly_plan_constructor.shadow_handoff_store import (
    bootstrap_constructor_shadow_handoff_store,
)
from agents.monthly_plan_constructor.shadow_hitl_store import (
    CODE_SHADOW_HITL_STORE_BLOCKER,
    ShadowHitlStoreError,
    bootstrap_constructor_shadow_hitl_store,
)
from agents.monthly_plan_constructor.shadow_runtime_stores import (
    resolve_constructor_shadow_runtime_paths,
)
from agents.observability.contracts import (
    EventType,
    InitiatorType,
    OperationalStatus,
    TriggerType,
    build_agent_run,
)
from agents.observability.durable_recorder import StoreObservabilityRecorder
from agents.observability.recorder import InMemoryObservabilityRecorder
from agents.observability.sqlite_store import SqliteObservabilityStore
from agents.observability.store import DEFAULT_LIST_EVENTS_LIMIT
from security.agent_execution_context import (
    ACTOR_ID_EXECUTION_OS_LOCAL_HOST,
    AgentExecutionContext,
    issue_read_only_agent_context,
)

TEST_FILE = Path(__file__).resolve()
REAL_RUNTIME = REPO_ROOT / ".runtime"
RESULT_PREFIX = "EOS_11D_RESULT="
SUBPROCESS_TIMEOUT_SECONDS = 180

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
FIXED_AT = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
MISSION_ID = "mission-11d-operator"
OPERATOR_ACTOR_ID = "operator-human-11d"
FRESH_RUN_ID = "run-11d-fresh-process"

_SECRET_ENV_MARKERS = (
    "SUPABASE",
    "AIRTABLE",
    "OPENAI",
    "ANTHROPIC",
    "API_KEY",
    "SERVICE_ROLE",
    "DATABASE_URL",
    "DATABASE_PASSWORD",
    "POSTGRES",
    "PGPASSWORD",
    "SECRET",
    "ACCESS_TOKEN",
)


def _require_real_runtime_absent() -> None:
    if REAL_RUNTIME.exists():
        pytest.fail(
            "real C:\\csv_fix\\.runtime already exists; 11D must stop "
            "rather than delete or reuse it"
        )


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _bounded_subprocess_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if any(marker in upper for marker in _SECRET_ENV_MARKERS):
            continue
        env[key] = value
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        _ROOT_STR if not existing else _ROOT_STR + os.pathsep + existing
    )
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _emit_result(payload: dict[str, Any]) -> None:
    print(RESULT_PREFIX + json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def _parse_result(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip().startswith(RESULT_PREFIX)]
    if not lines:
        raise AssertionError(f"missing {RESULT_PREFIX} JSON line in subprocess stdout:\n{stdout}")
    return json.loads(lines[-1][len(RESULT_PREFIX) :])


def _raw(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "project_code": PROJECT,
        "month_key": MONTH,
        "facility": FACILITY_TARGET,
        "facility_building": FACILITY_TARGET,
        "discipline": DISCIPLINE_VENT,
        "construction_discipline": DISCIPLINE_VENT,
        "system": "SYS-1",
        "system_label": "SYS-1",
        "iwp": "IWP-1",
        "iwp_id": "IWP-1",
        "boq_code": "BOQ-001",
        "boq_name": "Воздуховод",
        "unit_of_measure": "м2",
    }
    base.update(overrides)
    return base


class StubAssembler:
    def __call__(self, reality_read, scope: ConstructorMissionScope) -> CandidateAssemblyResult:
        return CandidateAssemblyResult(
            candidates=(
                {
                    "candidate_id": CANDIDATE_ID,
                    "project_code": PROJECT,
                    "month_key": MONTH,
                    "facility": FACILITY_TARGET,
                    "discipline": DISCIPLINE_VENT,
                    "system": "SYS-1",
                    "iwp": "IWP-1",
                    "queue": "Q1",
                    "boq_code": "BOQ-001",
                    "boq_name": "Воздуховод",
                    "unit": "м2",
                    "remaining_qty": 10.0,
                    "already_planned_qty": 0.0,
                    "available_to_add_qty": 10.0,
                    "availability_status": "Доступно",
                    "labor_norm_status": LABOR_UNRESOLVED,
                },
            ),
            scanned_count=1,
        )


class RecordingReader:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows if rows is not None else [_raw()]
        self.calls = 0

    def __call__(self, context, mission: ConstructorMissionScope) -> list[dict[str, object]]:
        self.calls += 1
        return list(self.rows)


class FailingRefreshReader:
    def __init__(self, *, fail_code: str = CODE_READ_FAILED) -> None:
        self.calls = 0
        self.fail_code = fail_code

    def __call__(self, context, mission: ConstructorMissionScope) -> list[dict[str, object]]:
        self.calls += 1
        raise SecureReadError(self.fail_code, "refresh read failed")


@dataclass
class OrderHitlStore:
    order: list[str] = field(default_factory=list)
    open_ids: list[str] = field(default_factory=list)
    answers: dict[str, Any] = field(default_factory=dict)
    open_calls: int = 0
    answer_calls: int = 0

    def upsert_open_request(self, request) -> None:
        self.open_calls += 1
        if request.interrupt_id not in self.open_ids:
            self.open_ids.append(request.interrupt_id)

    def record_answer(self, *, interrupt_id: str, command) -> None:
        self.order.append("record_answer")
        self.answer_calls += 1
        self.answers[interrupt_id] = command


def _history() -> LaborNormEvidence:
    return LaborNormEvidence(
        evidence_id="ev-project-11d",
        candidate_id=CANDIDATE_ID,
        source_type=SOURCE_PROJECT_HISTORY,
        labor_hours_per_unit=1.42,
        unit="м2",
        source_reference="project-history-run",
        source_version="2026-08",
        planning_use_status=LABOR_VALIDATED,
        basis=BASIS_OBSERVED_PRODUCTIVITY,
        hours_quality=HOURS_VALIDATED_PRODUCTIVE_DIRECT,
        executed_quantity_validated=True,
    )


def _context(*, run_id: str, project_code: str = PROJECT) -> AgentExecutionContext:
    return issue_read_only_agent_context(
        agent_code=CONSTRUCTOR_AGENT_CODE,
        project_code=project_code,
        run_id=run_id,
    )


def _expired_context(live: AgentExecutionContext) -> AgentExecutionContext:
    expired = AgentExecutionContext(
        actor_id=live.actor_id,
        actor_type=live.actor_type,
        agent_code=live.agent_code,
        agent_version=live.agent_version,
        run_id=live.run_id,
        project_code=live.project_code,
        allowed_tools=live.allowed_tools,
        permission_tier=live.permission_tier,
        authorization_id=live.authorization_id,
        issued_at=live.issued_at,
        expires_at=(datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
        security_policy_version=live.security_policy_version,
        write_allowed=False,
    )
    assert expired.is_expired()
    return expired


def _hitl_app(
    *,
    run_id: str,
    context: AgentExecutionContext | None = None,
    reader: Any | None = None,
    store: Any | None = None,
    recorder: Any | None = None,
    checkpointer: Any | None = None,
):
    from langgraph.checkpoint.memory import InMemorySaver

    ctx = context or _context(run_id=run_id)
    saver = checkpointer or InMemorySaver(serde=build_constructor_jsonplus_serializer())
    app = build_constructor_langgraph(
        context=ctx,
        project_code=PROJECT,
        month_key=MONTH,
        facility_scope=["ALL", FACILITY_TARGET],
        assemble_candidates=StubAssembler(),
        scope_reader=reader if reader is not None else RecordingReader(),
        labor_evidence=(_history(),),
        now=FIXED_AT,
        checkpointer=saver,
        hitl_store=store if store is not None else OrderHitlStore(),
        recorder=recorder,
    )
    return app, ctx


def _wait(app, *, run_id: str, mission_id: str = MISSION_ID, authorization_id: str):
    initial = create_lifecycle_state(
        mission_id=mission_id,
        run_id=run_id,
        authorization_id=authorization_id,
        created_at=FIXED_AT,
    )
    config = {"configurable": {"thread_id": run_id}}
    out1 = app.invoke({"lifecycle": initial}, config)
    assert out1["lifecycle"].status == STATUS_WAITING_FOR_HUMAN
    req = build_decision_request_from_lifecycle(out1["lifecycle"])
    snap = app.get_state(config)
    checkpoint_id = snap.config["configurable"]["checkpoint_id"]
    return out1, req, config, checkpoint_id


def _command(
    *,
    req,
    checkpoint_id: str,
    run_id: str,
    decision_id: str,
    decision: str = DECISION_CLARIFY_SCOPE,
    actor_id: str = OPERATOR_ACTOR_ID,
    actor_type: str = ACTOR_TYPE_HUMAN,
    comment: str | None = None,
    interrupt_id: str | None = None,
    expected_checkpoint_id: str | None = None,
    parameters: dict[str, Any] | None = None,
):
    return build_resume_command(
        decision_id=decision_id,
        interrupt_id=interrupt_id or req.interrupt_id,
        run_id=run_id,
        mission_id=MISSION_ID,
        decision=decision,
        actor_id=actor_id,
        actor_type=actor_type,
        parameters=parameters if parameters is not None else {"facility_scope": [FACILITY_TARGET]},
        expected_checkpoint_id=expected_checkpoint_id if expected_checkpoint_id is not None else checkpoint_id,
        submitted_at=FIXED_AT,
        comment=comment,
    )


def _event_types(recorder: InMemoryObservabilityRecorder, run_id: str) -> set[Any]:
    return {event.event_type for event in recorder.events_for_run(run_id)}


@dataclass
class OpenedStores:
    paths: Any
    checkpoint: Any
    hitl: Any
    handoff: Any
    observability: SqliteObservabilityStore

    def close(self) -> None:
        for item in (self.checkpoint, self.hitl, self.handoff, self.observability):
            closer = getattr(item, "close", None)
            if closer is not None:
                closer()


def _open_stores(repository_root: Path) -> OpenedStores:
    paths = resolve_constructor_shadow_runtime_paths(repository_root=repository_root)
    checkpoint = bootstrap_constructor_shadow_checkpoint_store(repository_root=repository_root)
    hitl = bootstrap_constructor_shadow_hitl_store(repository_root=repository_root)
    handoff = bootstrap_constructor_shadow_handoff_store(repository_root=repository_root)
    observability = SqliteObservabilityStore(paths.observability_db_path)
    return OpenedStores(
        paths=paths,
        checkpoint=checkpoint,
        hitl=hitl,
        handoff=handoff,
        observability=observability,
    )


def _create_observability_run(*, store: SqliteObservabilityStore, run_id: str, mission_id: str) -> None:
    store.create_run(
        build_agent_run(
            run_id=run_id,
            request_id=f"req-{run_id}",
            agent_code=CONSTRUCTOR_AGENT_CODE,
            agent_version="0.1",
            mission_id=mission_id,
            project_code=PROJECT,
            month_key=MONTH,
            initiator_type=InitiatorType.HUMAN,
            initiator_id=OPERATOR_ACTOR_ID,
            trigger_type=TriggerType.MANUAL,
            trigger_reason="increment-11d-operator-resume",
            operational_status=OperationalStatus.REQUESTED,
            requested_at=FIXED_AT,
            updated_at=FIXED_AT,
            thread_id=run_id,
            scope_summary={"proof": "11D"},
        )
    )


def _lifecycle_from_tuple(tup: Any) -> Optional[ConstructorLifecycleState]:
    if tup is None:
        return None
    checkpoint = getattr(tup, "checkpoint", None) or {}
    values = checkpoint.get("channel_values") or {}
    lifecycle = values.get("lifecycle")
    if isinstance(lifecycle, ConstructorLifecycleState):
        return lifecycle
    return None


def test_real_runtime_root_absent_before_tests() -> None:
    _require_real_runtime_absent()


def test_valid_operator_resume_persists_before_apply_and_refreshes() -> None:
    from langgraph.types import Command

    from agents.monthly_plan_constructor import langgraph_runtime as lg_runtime

    run_id = "run-11d-valid"
    store = OrderHitlStore()
    reader = RecordingReader()
    recorder = InMemoryObservabilityRecorder()
    app, ctx = _hitl_app(run_id=run_id, store=store, reader=reader, recorder=recorder)
    out1, req, config, ckpt = _wait(
        app, run_id=run_id, authorization_id=ctx.authorization_id
    )
    reads_after_wait = reader.calls
    cmd = _command(req=req, checkpoint_id=ckpt, run_id=run_id, decision_id="dec-11d-valid")
    original_apply = lg_runtime.apply_constructor_resume_command

    def wrapped_apply(*args: Any, **kwargs: Any):
        store.order.append("apply")
        return original_apply(*args, **kwargs)

    with patch.object(lg_runtime, "apply_constructor_resume_command", wrapped_apply):
        out2 = app.invoke(Command(resume=cmd), config)

    assert store.order[:2] == ["record_answer", "apply"]
    assert store.answer_calls == 1
    assert req.interrupt_id in store.answers
    assert store.answers[req.interrupt_id].decision_id == "dec-11d-valid"
    assert out2["lifecycle"].status == STATUS_READY_FOR_HANDOFF
    assert reader.calls > reads_after_wait
    types = _event_types(recorder, run_id)
    assert EventType.HUMAN_DECISION_RECEIVED in types
    assert EventType.RUN_RESUMED in types
    assert EventType.REALITY_REFRESH_STARTED in types
    assert EventType.REALITY_REFRESH_COMPLETED in types
    assert out1["lifecycle"].status == STATUS_WAITING_FOR_HUMAN


def test_actor_type_not_human_rejected() -> None:
    from langgraph.types import Command

    from agents.monthly_plan_constructor import langgraph_runtime as lg_runtime

    run_id = "run-11d-actor-type"
    store = OrderHitlStore()
    reader = RecordingReader()
    app, ctx = _hitl_app(run_id=run_id, store=store, reader=reader)
    _, req, config, ckpt = _wait(app, run_id=run_id, authorization_id=ctx.authorization_id)
    cmd = _command(
        req=req,
        checkpoint_id=ckpt,
        run_id=run_id,
        decision_id="dec-11d-actor-type",
        actor_type=ACTOR_TYPE_LOCAL_APPLICATION,
    )
    with patch.object(
        lg_runtime,
        "apply_constructor_resume_command",
        wraps=lg_runtime.apply_constructor_resume_command,
    ) as apply_spy:
        with pytest.raises(HitlContractError) as raised:
            app.invoke(Command(resume=cmd), config)
    assert raised.value.code == CODE_HITL_CONTRACT_BLOCKER
    assert "actor_type" in str(raised.value).lower()
    apply_spy.assert_not_called()
    assert store.answer_calls == 0
    assert reader.calls == 0
    held = app.get_state(config)
    assert held.values["lifecycle"].status == STATUS_WAITING_FOR_HUMAN


def test_blank_actor_id_rejected_at_command_construction() -> None:
    with pytest.raises(HitlContractError) as raised:
        build_resume_command(
            decision_id="dec-11d-blank",
            interrupt_id="int-11d-blank",
            run_id="run-11d-blank",
            mission_id=MISSION_ID,
            decision=DECISION_CLARIFY_SCOPE,
            actor_id="",
            actor_type=ACTOR_TYPE_HUMAN,
            parameters={"facility_scope": [FACILITY_TARGET]},
            expected_checkpoint_id="ckpt-11d",
            submitted_at=FIXED_AT,
        )
    assert raised.value.code == CODE_HITL_CONTRACT_BLOCKER
    assert "actor_id" in str(raised.value).lower()


def test_reserved_host_actor_id_rejected() -> None:
    from langgraph.types import Command

    from agents.monthly_plan_constructor import langgraph_runtime as lg_runtime

    run_id = "run-11d-reserved"
    store = OrderHitlStore()
    reader = RecordingReader()
    app, ctx = _hitl_app(run_id=run_id, store=store, reader=reader)
    _, req, config, ckpt = _wait(app, run_id=run_id, authorization_id=ctx.authorization_id)
    cmd = _command(
        req=req,
        checkpoint_id=ckpt,
        run_id=run_id,
        decision_id="dec-11d-reserved",
        actor_id=ACTOR_ID_EXECUTION_OS_LOCAL_HOST,
    )
    with patch.object(
        lg_runtime,
        "apply_constructor_resume_command",
        wraps=lg_runtime.apply_constructor_resume_command,
    ) as apply_spy:
        with pytest.raises(HitlContractError) as raised:
            app.invoke(Command(resume=cmd), config)
    assert raised.value.code == CODE_HITL_CONTRACT_BLOCKER
    assert "reserved" in str(raised.value).lower()
    apply_spy.assert_not_called()
    assert store.answer_calls == 0
    assert reader.calls == 0
    held = app.get_state(config)
    assert held.values["lifecycle"].status == STATUS_WAITING_FOR_HUMAN


def test_expired_live_context_rejected() -> None:
    from langgraph.types import Command

    from agents.monthly_plan_constructor import langgraph_runtime as lg_runtime

    run_id = "run-11d-expired"
    live = _context(run_id=run_id)
    expired = _expired_context(live)
    store = OrderHitlStore()
    reader = RecordingReader()
    app, _ = _hitl_app(run_id=run_id, context=expired, store=store, reader=reader)
    _, req, config, ckpt = _wait(
        app, run_id=run_id, authorization_id=expired.authorization_id
    )
    cmd = _command(req=req, checkpoint_id=ckpt, run_id=run_id, decision_id="dec-11d-expired")
    with patch.object(
        lg_runtime,
        "apply_constructor_resume_command",
        wraps=lg_runtime.apply_constructor_resume_command,
    ) as apply_spy:
        with pytest.raises(LifecycleError) as raised:
            app.invoke(Command(resume=cmd), config)
    assert raised.value.code == CODE_LIFECYCLE_CONTRACT_BLOCKER
    assert "expired" in str(raised.value).lower()
    apply_spy.assert_not_called()
    assert store.answer_calls == 0
    assert reader.calls == 0
    held = app.get_state(config)
    assert held.values["lifecycle"].status == STATUS_WAITING_FOR_HUMAN


def test_wrong_run_live_context_rejected() -> None:
    run_id = "run-11d-wrong-run"
    store = OrderHitlStore()
    reader = RecordingReader()
    app, ctx = _hitl_app(run_id=run_id, store=store, reader=reader)
    out1, req, config, ckpt = _wait(
        app, run_id=run_id, authorization_id=ctx.authorization_id
    )
    cmd = _command(req=req, checkpoint_id=ckpt, run_id=run_id, decision_id="dec-11d-wrong-run")
    wrong = _context(run_id="run-11d-other-binding")
    with pytest.raises(LifecycleError) as raised:
        validate_constructor_resume_command(
            out1["lifecycle"],
            cmd,
            context=wrong,
            project_code=PROJECT,
            month_key=MONTH,
            checkpoint_id=ckpt,
            now=FIXED_AT,
            require_expected_checkpoint=True,
        )
    assert raised.value.code == CODE_LIFECYCLE_CONTRACT_BLOCKER
    assert "run_id" in str(raised.value).lower()
    assert store.answer_calls == 0
    assert reader.calls == 0
    held = app.get_state(config)
    assert held.values["lifecycle"].status == STATUS_WAITING_FOR_HUMAN


def test_stale_checkpoint_rejected_before_continuation() -> None:
    from langgraph.types import Command

    from agents.monthly_plan_constructor import langgraph_runtime as lg_runtime

    run_id = "run-11d-stale-ckpt"
    store = OrderHitlStore()
    reader = RecordingReader()
    recorder = InMemoryObservabilityRecorder()
    app, ctx = _hitl_app(run_id=run_id, store=store, reader=reader, recorder=recorder)
    _, req, config, ckpt = _wait(app, run_id=run_id, authorization_id=ctx.authorization_id)
    cmd = _command(
        req=req,
        checkpoint_id=ckpt,
        run_id=run_id,
        decision_id="dec-11d-stale",
        expected_checkpoint_id="ckpt-stale-11d-not-current",
    )
    with patch.object(
        lg_runtime,
        "apply_constructor_resume_command",
        wraps=lg_runtime.apply_constructor_resume_command,
    ) as apply_spy:
        with pytest.raises(HitlContractError) as raised:
            app.invoke(Command(resume=cmd), config)
    assert raised.value.code == CODE_HITL_CONTRACT_BLOCKER
    assert "checkpoint" in str(raised.value).lower()
    apply_spy.assert_not_called()
    assert store.answer_calls == 0
    assert reader.calls == 0
    types = _event_types(recorder, run_id)
    assert EventType.RUN_RESUMED not in types
    assert EventType.REALITY_REFRESH_STARTED not in types
    held = app.get_state(config)
    assert held.values["lifecycle"].status == STATUS_WAITING_FOR_HUMAN


def test_wrong_interrupt_rejected() -> None:
    from langgraph.types import Command

    from agents.monthly_plan_constructor import langgraph_runtime as lg_runtime

    run_id = "run-11d-wrong-interrupt"
    store = OrderHitlStore()
    reader = RecordingReader()
    recorder = InMemoryObservabilityRecorder()
    app, ctx = _hitl_app(run_id=run_id, store=store, reader=reader, recorder=recorder)
    _, req, config, ckpt = _wait(app, run_id=run_id, authorization_id=ctx.authorization_id)
    wrong_interrupt = compute_eos_interrupt_id(
        run_id=run_id,
        wait_ordinal=9,
        reason_code=CODE_AMBIGUOUS_SCOPE,
    )
    assert wrong_interrupt != req.interrupt_id
    cmd = _command(
        req=req,
        checkpoint_id=ckpt,
        run_id=run_id,
        decision_id="dec-11d-wrong-int",
        interrupt_id=wrong_interrupt,
    )
    with patch.object(
        lg_runtime,
        "apply_constructor_resume_command",
        wraps=lg_runtime.apply_constructor_resume_command,
    ) as apply_spy:
        with pytest.raises(HitlContractError) as raised:
            app.invoke(Command(resume=cmd), config)
    assert raised.value.code == CODE_HITL_CONTRACT_BLOCKER
    assert "interrupt" in str(raised.value).lower()
    apply_spy.assert_not_called()
    assert store.answer_calls == 0
    assert reader.calls == 0
    types = _event_types(recorder, run_id)
    assert EventType.RUN_RESUMED not in types
    assert EventType.REALITY_REFRESH_STARTED not in types
    held = app.get_state(config)
    assert held.values["lifecycle"].status == STATUS_WAITING_FOR_HUMAN


def test_conflicting_replay_fail_closed(tmp_path: Path) -> None:
    from langgraph.types import Command

    from agents.monthly_plan_constructor import langgraph_runtime as lg_runtime

    _require_real_runtime_absent()
    run_id = "run-11d-conflict"
    hitl = bootstrap_constructor_shadow_hitl_store(repository_root=tmp_path)
    reader = RecordingReader()
    try:
        app, ctx = _hitl_app(run_id=run_id, store=hitl, reader=reader)
        _, req, config, ckpt = _wait(
            app, run_id=run_id, authorization_id=ctx.authorization_id
        )
        cmd_a = _command(
            req=req,
            checkpoint_id=ckpt,
            run_id=run_id,
            decision_id="dec-11d-conflict-a",
        )
        cmd_b = _command(
            req=req,
            checkpoint_id=ckpt,
            run_id=run_id,
            decision_id="dec-11d-conflict-b",
            decision=DECISION_ABORT_RUN,
            comment="conflicting abort",
            parameters={},
        )
        hitl.record_answer(interrupt_id=req.interrupt_id, command=cmd_a)
        with patch.object(
            lg_runtime,
            "apply_constructor_resume_command",
            wraps=lg_runtime.apply_constructor_resume_command,
        ) as apply_spy:
            with pytest.raises(ShadowHitlStoreError) as raised:
                app.invoke(Command(resume=cmd_b), config)
        assert raised.value.code == CODE_SHADOW_HITL_STORE_BLOCKER
        apply_spy.assert_not_called()
        preserved = hitl.get_answer_for_interrupt(req.interrupt_id)
        assert preserved is not None
        assert preserved.decision_id == "dec-11d-conflict-a"
        assert preserved.decision == DECISION_CLARIFY_SCOPE
        assert reader.calls == 0
        held = app.get_state(config)
        assert held.values["lifecycle"].status == STATUS_WAITING_FOR_HUMAN
    finally:
        hitl.close()
    assert not REAL_RUNTIME.exists()


def test_identical_retry_safe_then_double_execution_blocked(tmp_path: Path) -> None:
    from langgraph.types import Command

    _require_real_runtime_absent()
    run_id = "run-11d-retry"
    hitl = bootstrap_constructor_shadow_hitl_store(repository_root=tmp_path)
    reader = RecordingReader()
    recorder = InMemoryObservabilityRecorder()
    try:
        app, ctx = _hitl_app(
            run_id=run_id, store=hitl, reader=reader, recorder=recorder
        )
        _, req, config, ckpt = _wait(
            app, run_id=run_id, authorization_id=ctx.authorization_id
        )
        cmd = _command(
            req=req,
            checkpoint_id=ckpt,
            run_id=run_id,
            decision_id="dec-11d-retry",
        )
        hitl.record_answer(interrupt_id=req.interrupt_id, command=cmd)
        assert hitl.get_answer_for_interrupt(req.interrupt_id) is not None
        out2 = app.invoke(Command(resume=cmd), config)
        assert out2["lifecycle"].status == STATUS_READY_FOR_HANDOFF
        first_reads = reader.calls
        assert first_reads >= 1
        resumed = [
            event
            for event in recorder.events_for_run(run_id)
            if event.event_type == EventType.RUN_RESUMED
        ]
        assert len(resumed) == 1
        second_error = None
        try:
            app.invoke(Command(resume=cmd), config)
        except (HitlContractError, LifecycleError) as exc:
            second_error = exc
        held = app.get_state(config)
        assert held.values["lifecycle"].status == STATUS_READY_FOR_HANDOFF
        assert reader.calls == first_reads
        resumed_after = [
            event
            for event in recorder.events_for_run(run_id)
            if event.event_type == EventType.RUN_RESUMED
        ]
        assert len(resumed_after) == 1
        if second_error is not None:
            assert getattr(second_error, "code", None) in {
                CODE_HITL_CONTRACT_BLOCKER,
                CODE_LIFECYCLE_CONTRACT_BLOCKER,
            }
    finally:
        hitl.close()
    assert not REAL_RUNTIME.exists()


@pytest.mark.parametrize(
    ("fail_code", "expected_status"),
    (
        (CODE_READ_FAILED, STATUS_FAILED),
        (CODE_AMBIGUOUS_SCOPE, STATUS_WAITING_FOR_HUMAN),
    ),
)
def test_reality_refresh_failure_matches_domain_mapping(
    fail_code: str,
    expected_status: str,
) -> None:
    from langgraph.types import Command

    run_id = f"run-11d-refresh-{fail_code.lower()}"
    store = OrderHitlStore()
    reader = FailingRefreshReader(fail_code=fail_code)
    recorder = InMemoryObservabilityRecorder()
    app, ctx = _hitl_app(run_id=run_id, store=store, reader=reader, recorder=recorder)
    _, req, config, ckpt = _wait(app, run_id=run_id, authorization_id=ctx.authorization_id)
    cmd = _command(
        req=req,
        checkpoint_id=ckpt,
        run_id=run_id,
        decision_id=f"dec-11d-refresh-{fail_code.lower()}",
    )
    out2 = app.invoke(Command(resume=cmd), config)
    assert store.answer_calls == 1
    assert out2["lifecycle"].status == expected_status
    assert out2["lifecycle"].status != STATUS_READY_FOR_HANDOFF
    assert reader.calls >= 1
    types = _event_types(recorder, run_id)
    assert EventType.HUMAN_DECISION_RECEIVED in types
    assert EventType.REALITY_REFRESH_STARTED in types


def test_abort_run_persists_before_apply_and_skips_refresh() -> None:
    from langgraph.types import Command

    from agents.monthly_plan_constructor import langgraph_runtime as lg_runtime

    run_id = "run-11d-abort"
    store = OrderHitlStore()
    reader = RecordingReader()
    recorder = InMemoryObservabilityRecorder()
    app, ctx = _hitl_app(run_id=run_id, store=store, reader=reader, recorder=recorder)
    _, req, config, ckpt = _wait(app, run_id=run_id, authorization_id=ctx.authorization_id)
    cmd = _command(
        req=req,
        checkpoint_id=ckpt,
        run_id=run_id,
        decision_id="dec-11d-abort",
        decision=DECISION_ABORT_RUN,
        comment="operator abort",
        parameters={},
    )
    original_apply = lg_runtime.apply_constructor_resume_command

    def wrapped_apply(*args: Any, **kwargs: Any):
        store.order.append("apply")
        return original_apply(*args, **kwargs)

    with patch.object(lg_runtime, "apply_constructor_resume_command", wrapped_apply):
        out2 = app.invoke(Command(resume=cmd), config)

    assert store.order[:2] == ["record_answer", "apply"]
    assert out2["lifecycle"].status == STATUS_FAILED
    assert reader.calls == 0
    types = _event_types(recorder, run_id)
    assert EventType.HUMAN_DECISION_RECEIVED in types
    assert EventType.RUN_ABORTED in types
    assert EventType.RUN_RESUMED not in types
    assert EventType.REALITY_REFRESH_STARTED not in types
    assert EventType.HANDOFF_PERSISTED not in types


def role_process_a(*, repository_root: Path, run_id: str, mission_id: str) -> int:
    stores = _open_stores(repository_root)
    try:
        _create_observability_run(
            store=stores.observability,
            run_id=run_id,
            mission_id=mission_id,
        )
        recorder = StoreObservabilityRecorder(stores.observability)
        context = issue_read_only_agent_context(
            agent_code=CONSTRUCTOR_AGENT_CODE,
            project_code=PROJECT,
            run_id=run_id,
        )
        lifecycle = run_constructor_langgraph(
            context=context,
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            scope_reader=RecordingReader(),
            mission_id=mission_id,
            run_id=run_id,
            now=FIXED_AT,
            checkpointer=stores.checkpoint.checkpointer,
            hitl_store=stores.hitl,
            recorder=recorder,
            facility_scope=["ALL", FACILITY_TARGET],
        )
        if lifecycle.status != STATUS_WAITING_FOR_HUMAN:
            raise RuntimeError(f"Process A expected WAIT, got {lifecycle.status}")
        tup = stores.checkpoint.checkpointer.get_tuple({"configurable": {"thread_id": run_id}})
        persisted = _lifecycle_from_tuple(tup)
        if persisted is None:
            raise RuntimeError("Process A checkpoint tuple missing ConstructorLifecycleState")
        checkpoint_id = resolve_current_checkpoint_id(
            stores.checkpoint.checkpointer,
            thread_id=run_id,
        )
        derived = build_decision_request_from_lifecycle(lifecycle)
        hitl_request = stores.hitl.get_request(derived.interrupt_id)
        hitl_answer = stores.hitl.get_answer_for_interrupt(derived.interrupt_id)
        agent_run = stores.observability.get_run(run_id)
        events = list(stores.observability.list_events(run_id, limit=DEFAULT_LIST_EVENTS_LIMIT))
        _emit_result(
            {
                "role": "process-a",
                "pid": os.getpid(),
                "run_id": run_id,
                "mission_id": mission_id,
                "checkpoint_id": checkpoint_id,
                "lifecycle_status": lifecycle.status,
                "persisted_lifecycle_status": persisted.status,
                "interrupt_id": derived.interrupt_id,
                "wait_ordinal": derived.wait_ordinal,
                "hitl_answer_present": hitl_answer is not None,
                "hitl_authorization_id_ref": None
                if hitl_request is None
                else hitl_request.authorization_id_ref,
                "authorization_id": context.authorization_id,
                "resume_invoked": False,
                "event_types": [event.event_type.value for event in events],
                "operational_status": agent_run.operational_status.value,
            }
        )
        return 0
    finally:
        stores.close()


def role_process_b(*, repository_root: Path, run_id: str, mission_id: str) -> int:
    from langgraph.types import Command

    stores = _open_stores(repository_root)
    try:
        context_b = issue_read_only_agent_context(
            agent_code=CONSTRUCTOR_AGENT_CODE,
            project_code=PROJECT,
            run_id=run_id,
        )
        recorder = StoreObservabilityRecorder(stores.observability)
        reader = RecordingReader()
        app = build_constructor_langgraph(
            context=context_b,
            project_code=PROJECT,
            month_key=MONTH,
            facility_scope=["ALL", FACILITY_TARGET],
            assemble_candidates=StubAssembler(),
            scope_reader=reader,
            labor_evidence=(_history(),),
            now=FIXED_AT,
            checkpointer=stores.checkpoint.checkpointer,
            hitl_store=stores.hitl,
            handoff_store=stores.handoff,
            recorder=recorder,
        )
        config = {"configurable": {"thread_id": run_id}}
        snapshot = app.get_state(config)
        lifecycle = snapshot.values.get("lifecycle") if snapshot is not None else None
        if not isinstance(lifecycle, ConstructorLifecycleState):
            raise RuntimeError("Process B could not reopen WAIT lifecycle")
        if lifecycle.status != STATUS_WAITING_FOR_HUMAN:
            raise RuntimeError(f"Process B expected WAIT, got {lifecycle.status}")
        req = build_decision_request_from_lifecycle(lifecycle)
        checkpoint_id = snapshot.config["configurable"]["checkpoint_id"]
        cmd = build_resume_command(
            decision_id="dec-11d-fresh-b",
            interrupt_id=req.interrupt_id,
            run_id=run_id,
            mission_id=mission_id,
            decision=DECISION_CLARIFY_SCOPE,
            actor_id=OPERATOR_ACTOR_ID,
            actor_type=ACTOR_TYPE_HUMAN,
            parameters={"facility_scope": [FACILITY_TARGET]},
            expected_checkpoint_id=checkpoint_id,
            submitted_at=FIXED_AT,
        )
        out2 = app.invoke(Command(resume=cmd), config)
        resumed = out2["lifecycle"]
        answer = stores.hitl.get_answer_for_interrupt(req.interrupt_id)
        events = list(stores.observability.list_events(run_id, limit=DEFAULT_LIST_EVENTS_LIMIT))
        handoff_rows = stores.handoff.connection.execute(
            "SELECT handoff_id FROM constructor_handoffs WHERE source_run_id = ?",
            (run_id,),
        ).fetchall()
        _emit_result(
            {
                "role": "process-b",
                "pid": os.getpid(),
                "run_id": run_id,
                "mission_id": mission_id,
                "lifecycle_status": resumed.status,
                "interrupt_id": req.interrupt_id,
                "expected_checkpoint_id": checkpoint_id,
                "hitl_answer_present": answer is not None,
                "hitl_decision_id": None if answer is None else answer.decision_id,
                "authorization_id_b": context_b.authorization_id,
                "resume_invoked": True,
                "automatic_resume": False,
                "reader_calls": reader.calls,
                "handoff_count": len(handoff_rows),
                "event_types": [event.event_type.value for event in events],
            }
        )
        return 0
    finally:
        stores.close()


def _spawn_role(*, role: str, repository_root: Path, run_id: str, mission_id: str):
    cmd = [
        sys.executable,
        str(TEST_FILE),
        "--role",
        role,
        "--repository-root",
        str(repository_root),
        "--run-id",
        run_id,
        "--mission-id",
        mission_id,
    ]
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=_bounded_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
        shell=False,
        check=False,
    )


def test_fresh_process_explicit_operator_resume(tmp_path: Path) -> None:
    _require_real_runtime_absent()
    proc_a = _spawn_role(
        role="process-a",
        repository_root=tmp_path,
        run_id=FRESH_RUN_ID,
        mission_id=MISSION_ID,
    )
    assert proc_a.returncode == 0, proc_a.stderr
    result_a = _parse_result(proc_a.stdout)
    assert result_a["lifecycle_status"] == STATUS_WAITING_FOR_HUMAN
    assert result_a["hitl_answer_present"] is False
    assert result_a["resume_invoked"] is False
    assert EventType.RUN_RESUMED.value not in result_a["event_types"]

    proc_b = _spawn_role(
        role="process-b",
        repository_root=tmp_path,
        run_id=FRESH_RUN_ID,
        mission_id=MISSION_ID,
    )
    assert proc_b.returncode == 0, proc_b.stderr
    result_b = _parse_result(proc_b.stdout)
    assert result_a["pid"] != result_b["pid"]
    assert result_a["pid"] != os.getpid()
    assert result_b["pid"] != os.getpid()
    assert result_b["resume_invoked"] is True
    assert result_b["automatic_resume"] is False
    assert result_b["lifecycle_status"] == STATUS_READY_FOR_HANDOFF
    assert result_b["hitl_answer_present"] is True
    assert result_b["hitl_decision_id"] == "dec-11d-fresh-b"
    assert result_b["authorization_id_b"] != result_a["authorization_id"]
    assert result_b["reader_calls"] >= 1
    assert EventType.HUMAN_DECISION_RECEIVED.value in result_b["event_types"]
    assert EventType.RUN_RESUMED.value in result_b["event_types"]
    assert EventType.REALITY_REFRESH_STARTED.value in result_b["event_types"]
    assert EventType.REALITY_REFRESH_COMPLETED.value in result_b["event_types"]
    assert not REAL_RUNTIME.exists()


def test_real_runtime_root_absent_after_tests() -> None:
    _require_real_runtime_absent()


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Increment 11D operator resume proof")
    parser.add_argument("--role", required=True, choices=("process-a", "process-b"))
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mission-id", required=True)
    args = parser.parse_args(argv)
    repository_root = Path(args.repository_root)
    if args.role == "process-a":
        return role_process_a(
            repository_root=repository_root,
            run_id=args.run_id,
            mission_id=args.mission_id,
        )
    return role_process_b(
        repository_root=repository_root,
        run_id=args.run_id,
        mission_id=args.mission_id,
    )


if __name__ == "__main__":
    if any(arg == "--role" for arg in sys.argv[1:]):
        raise SystemExit(_main())
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q", str(TEST_FILE)]))
