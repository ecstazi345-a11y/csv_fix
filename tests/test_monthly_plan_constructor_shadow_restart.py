"""
Increment 11C.5 — Integrated Constructor durable-state reopen / restart proof.

TEST-ONLY integration proof. No production recovery coordinator.
No resume authority. No managed-launcher continuation. No real Shadow.

Process A persists legitimate Constructor state through existing runtime APIs
and exits. Process B is a brand-new Python interpreter that reopens the same
tmp_path runtime root using only explicit fixture identities.

Claims this file may prove:
  PROCESS_INDEPENDENT_STATE_RECONSTRUCTION
  INTEGRATED_DURABLE_STATE_REOPEN
  ACTUAL_PROCESS_BOUNDARY

Claims this file must not strengthen:
  AUTOMATIC_EXECUTION_CONTINUATION_AFTER_PROCESS_DEATH: NOT PROVEN
  RESUME_AUTHORITY: NOT IMPLEMENTED
  RECEIVER_ACK / TARGET_RUN / OWNERSHIP_TRANSFER: NOT IMPLEMENTED
  CROSS_STORE_ATOMICITY: NOT CLAIMED
  PRODUCTION_RECOVERY_COORDINATOR: NOT IMPLEMENTED

Test-harness mismatch detection is DETECTABILITY, not production enforcement.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

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
    resolve_current_checkpoint_id,
)
from agents.monthly_plan_constructor.handoff_contracts import TARGET_ROLE
from agents.monthly_plan_constructor.handoff_store import (
    compute_constructor_handoff_payload_digest,
)
from agents.monthly_plan_constructor.hitl_resume import build_decision_request_from_lifecycle
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
    STATUS_READY_FOR_HANDOFF,
    STATUS_WAITING_FOR_HUMAN,
    CandidateAssemblyResult,
    ConstructorLifecycleState,
)
from agents.monthly_plan_constructor.mission_scope import ConstructorMissionScope
from agents.monthly_plan_constructor.shadow_checkpoint_store import (
    bootstrap_constructor_shadow_checkpoint_store,
)
from agents.monthly_plan_constructor.shadow_handoff_store import (
    bootstrap_constructor_shadow_handoff_store,
)
from agents.monthly_plan_constructor.shadow_hitl_store import (
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
from agents.observability.store import DEFAULT_LIST_EVENTS_LIMIT, ObservabilityRunNotFoundError
from agents.observability.sqlite_store import SqliteObservabilityStore
from security.agent_execution_context import AgentExecutionContext, issue_read_only_agent_context

TEST_FILE = Path(__file__).resolve()
REAL_RUNTIME = REPO_ROOT / ".runtime"
RESULT_PREFIX = "EOS_11C5_RESULT="
SUBPROCESS_TIMEOUT_SECONDS = 180

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
FIXED_AT = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)

WAIT_RUN_ID = "run-11c5-wait"
WAIT_MISSION_ID = "mission-11c5-wait"
COMPLETE_RUN_ID = "run-11c5-complete"
COMPLETE_MISSION_ID = "mission-11c5-complete"
WRONG_RUN_ID = "run-11c5-does-not-exist"
WRONG_MISSION_ID = "mission-11c5-does-not-exist"

SCENARIO_WAIT = "wait"
SCENARIO_COMPLETE = "complete"

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
            "real C:\\csv_fix\\.runtime already exists; 11C.5 must stop "
            "rather than delete or reuse it"
        )


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _bounded_subprocess_env() -> dict[str, str]:
    """Pass only what Python/Windows need. Do not propagate product secrets."""
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
    def __call__(self, context, mission: ConstructorMissionScope) -> list[dict[str, object]]:
        return [
            {
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
        ]


def _history() -> LaborNormEvidence:
    return LaborNormEvidence(
        evidence_id="ev-project",
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
            initiator_id="operator-11c5",
            trigger_type=TriggerType.MANUAL,
            trigger_reason="increment-11c5-restart-proof",
            operational_status=OperationalStatus.REQUESTED,
            requested_at=FIXED_AT,
            updated_at=FIXED_AT,
            thread_id=run_id,
            scope_summary={"proof": "11C.5"},
        )
    )


def _thread_config(run_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": run_id}}


def _lifecycle_from_tuple(tup: Any) -> Optional[ConstructorLifecycleState]:
    if tup is None:
        return None
    checkpoint = getattr(tup, "checkpoint", None) or {}
    values = checkpoint.get("channel_values") or {}
    lifecycle = values.get("lifecycle")
    if isinstance(lifecycle, ConstructorLifecycleState):
        return lifecycle
    return None


def _hitl_interrupt_ids_for_run(hitl_store: Any, run_id: str) -> list[str]:
    """Test-harness presence probe. Not a production HITL list API."""
    rows = hitl_store.connection.execute(
        "SELECT interrupt_id FROM hitl_open_requests WHERE run_id = ? ORDER BY wait_ordinal",
        (run_id,),
    ).fetchall()
    return [str(row["interrupt_id"]) for row in rows]


def _handoff_ids_for_source_run(handoff_store: Any, run_id: str) -> list[str]:
    """Test-harness presence probe. Not a production handoff list API."""
    rows = handoff_store.connection.execute(
        "SELECT handoff_id FROM constructor_handoffs WHERE source_run_id = ? ORDER BY handoff_id",
        (run_id,),
    ).fetchall()
    return [str(row["handoff_id"]) for row in rows]


def _assess_recovery(
    *,
    scenario: str,
    fixture_run_id: str,
    fixture_mission_id: str,
    lookup_run_id: str,
    lookup_mission_id: str,
    lifecycle: Optional[ConstructorLifecycleState],
    checkpoint_id: Optional[str],
    thread_id: Optional[str],
    hitl_ids: list[str],
    hitl_request: Any,
    hitl_answer: Any,
    handoff_ids: list[str],
    handoff: Any,
    agent_run: Any,
    event_types: list[str],
) -> list[str]:
    """
    TEST HARNESS ONLY.

    DETECTABILITY != PRODUCTION ENFORCEMENT.
    Returning reasons means RECOVERY_INCONSISTENCY_DETECTED, not that a
    production Recovery Coordinator exists.
    """
    reasons: list[str] = []
    if lookup_run_id != fixture_run_id:
        reasons.append("lookup_run_id_differs_from_fixture")
    if lookup_mission_id != fixture_mission_id:
        reasons.append("lookup_mission_id_differs_from_fixture")
    if lifecycle is None or not checkpoint_id:
        reasons.append("checkpoint_missing_for_lookup_run_id")
        return reasons
    if lifecycle.run_id != fixture_run_id:
        reasons.append("checkpoint_run_id_mismatch")
    if lifecycle.mission_id != fixture_mission_id:
        reasons.append("checkpoint_mission_id_mismatch")
    if thread_id != fixture_run_id:
        reasons.append("thread_id_must_equal_run_id")
    if agent_run is None:
        reasons.append("observability_run_missing")
    else:
        if agent_run.run_id != fixture_run_id:
            reasons.append("observability_run_id_mismatch")
        if agent_run.mission_id != fixture_mission_id:
            reasons.append("observability_mission_id_mismatch")
        if agent_run.thread_id != fixture_run_id:
            reasons.append("observability_thread_id_mismatch")

    if scenario == SCENARIO_WAIT:
        if lifecycle.status != STATUS_WAITING_FOR_HUMAN:
            reasons.append("wait_lifecycle_status_mismatch")
        if hitl_request is None:
            reasons.append("wait_hitl_request_missing")
        else:
            if hitl_request.run_id != fixture_run_id:
                reasons.append("hitl_run_id_mismatch")
            if hitl_request.mission_id != fixture_mission_id:
                reasons.append("hitl_mission_id_mismatch")
        if hitl_answer is not None:
            reasons.append("wait_hitl_answer_must_be_absent")
        if handoff_ids or handoff is not None:
            reasons.append("wait_unexpected_handoff")
        if agent_run is not None and agent_run.operational_status is not OperationalStatus.WAITING_FOR_HUMAN:
            reasons.append("wait_observability_status_mismatch")
        if EventType.HUMAN_WAIT_STARTED.value not in event_types:
            reasons.append("wait_human_wait_started_missing")
        if EventType.RUN_RESUMED.value in event_types:
            reasons.append("wait_auto_resume_event_present")
        if EventType.HANDOFF_PERSISTED.value in event_types or EventType.RUN_COMPLETED.value in event_types:
            reasons.append("wait_terminal_handoff_events_present")
    elif scenario == SCENARIO_COMPLETE:
        if lifecycle.status != STATUS_READY_FOR_HANDOFF:
            reasons.append("complete_lifecycle_status_mismatch")
        if hitl_ids or hitl_request is not None or hitl_answer is not None:
            reasons.append("complete_unexpected_hitl")
        if handoff is None:
            reasons.append("complete_handoff_missing")
        else:
            if handoff.source_run_id != fixture_run_id:
                reasons.append("handoff_source_run_id_mismatch")
            if handoff.mission_id != fixture_mission_id:
                reasons.append("handoff_mission_id_mismatch")
            if handoff.target_role != TARGET_ROLE:
                reasons.append("handoff_target_role_not_intended_only")
        if agent_run is not None and agent_run.operational_status is not OperationalStatus.COMPLETED:
            reasons.append("complete_observability_status_mismatch")
        if EventType.HANDOFF_PERSISTED.value not in event_types:
            reasons.append("complete_handoff_persisted_missing")
        if EventType.RUN_COMPLETED.value not in event_types:
            reasons.append("complete_run_completed_missing")
    else:
        reasons.append("unknown_scenario")
    return reasons


def _observability_snapshot(store: SqliteObservabilityStore, run_id: str) -> tuple[Any, list[Any]]:
    try:
        agent_run = store.get_run(run_id)
    except ObservabilityRunNotFoundError:
        return None, []
    events = list(store.list_events(run_id, limit=DEFAULT_LIST_EVENTS_LIMIT))
    return agent_run, events


def role_process_a(
    *,
    repository_root: Path,
    run_id: str,
    mission_id: str,
    scenario: str,
) -> int:
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
        kwargs: dict[str, Any] = dict(
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
        )
        if scenario == SCENARIO_WAIT:
            kwargs["facility_scope"] = ["ALL", FACILITY_TARGET]
        else:
            kwargs["labor_evidence"] = (_history(),)
            kwargs["handoff_store"] = stores.handoff
        lifecycle = run_constructor_langgraph(**kwargs)
        tup = stores.checkpoint.checkpointer.get_tuple(_thread_config(run_id))
        persisted = _lifecycle_from_tuple(tup)
        if persisted is None:
            raise RuntimeError("Process A checkpoint tuple missing ConstructorLifecycleState")
        checkpoint_id = resolve_current_checkpoint_id(
            stores.checkpoint.checkpointer,
            thread_id=run_id,
        )
        hitl_ids = _hitl_interrupt_ids_for_run(stores.hitl, run_id)
        handoff_ids = _handoff_ids_for_source_run(stores.handoff, run_id)
        hitl_request = None
        hitl_answer = None
        interrupt_id = None
        wait_ordinal = None
        if lifecycle.status == STATUS_WAITING_FOR_HUMAN:
            derived = build_decision_request_from_lifecycle(lifecycle)
            interrupt_id = derived.interrupt_id
            wait_ordinal = derived.wait_ordinal
            hitl_request = stores.hitl.get_request(interrupt_id)
            hitl_answer = stores.hitl.get_answer_for_interrupt(interrupt_id)
        handoff = stores.handoff.get(handoff_ids[0]) if handoff_ids else None
        agent_run, events = _observability_snapshot(stores.observability, run_id)
        payload = {
            "role": "process-a",
            "pid": os.getpid(),
            "scenario": scenario,
            "run_id": run_id,
            "mission_id": mission_id,
            "thread_id": run_id,
            "checkpoint_id": checkpoint_id,
            "lifecycle_status": lifecycle.status,
            "persisted_lifecycle_status": persisted.status,
            "interrupt_id": interrupt_id,
            "wait_ordinal": wait_ordinal,
            "hitl_reason_code": None if hitl_request is None else hitl_request.reason_code,
            "hitl_route": None if hitl_request is None else hitl_request.route,
            "hitl_created_at": None if hitl_request is None else _iso(hitl_request.created_at),
            "hitl_ids": hitl_ids,
            "hitl_answer_present": hitl_answer is not None,
            "handoff_ids": handoff_ids,
            "handoff_id": None if handoff is None else handoff.handoff_id,
            "source_run_id": None if handoff is None else handoff.source_run_id,
            "package_id": None if handoff is None else handoff.candidate_package_reference.package_id,
            "snapshot_id": None if handoff is None else handoff.snapshot_id,
            "target_role": None if handoff is None else handoff.target_role,
            "handoff_created_at": None if handoff is None else handoff.created_at,
            "payload_digest": None
            if handoff is None
            else compute_constructor_handoff_payload_digest(handoff),
            "operational_status": None if agent_run is None else agent_run.operational_status.value,
            "run_started_at": None if agent_run is None else _iso(agent_run.started_at),
            "run_requested_at": None if agent_run is None else _iso(agent_run.requested_at),
            "event_ids": [event.event_id for event in events],
            "event_types": [event.event_type.value for event in events],
            "event_occurred_at": [_iso(event.occurred_at) for event in events],
            "projection_version": None if agent_run is None else agent_run.projection_version,
            "authorization_id_ref": lifecycle.authorization_id,
            "resume_invoked": False,
            "run_control_reservation": "PROCESS_LOCAL_NOT_REHYDRATED",
        }
        _emit_result(payload)
        return 0
    finally:
        stores.close()


def role_process_b(
    *,
    repository_root: Path,
    run_id: str,
    mission_id: str,
    scenario: str,
    lookup_run_id: str,
    lookup_mission_id: str,
) -> int:
    """
    READ / RECONSTRUCTION ONLY.

    Compiles the Constructor graph solely so LangGraph get_state can read the
    durable checkpoint. Does not invoke, stream, or Command(resume=...).
    A live AgentExecutionContext is required to compile the graph; it is NOT
    recovered authority and is not treated as a resume/start token.

    RUN_CONTROL_RESERVATION: PROCESS_LOCAL_NOT_REHYDRATED
    Persistent state != persistent Run Control authority.
    """
    stores = _open_stores(repository_root)
    try:
        event_count_before = 0
        try:
            event_count_before = len(
                stores.observability.list_events(lookup_run_id, limit=DEFAULT_LIST_EVENTS_LIMIT)
            )
        except ObservabilityRunNotFoundError:
            event_count_before = 0

        reconstruction_context = issue_read_only_agent_context(
            agent_code=CONSTRUCTOR_AGENT_CODE,
            project_code=PROJECT,
            run_id=lookup_run_id,
        )
        assert isinstance(reconstruction_context, AgentExecutionContext)
        app = build_constructor_langgraph(
            context=reconstruction_context,
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            scope_reader=RecordingReader(),
            labor_evidence=(_history(),),
            now=FIXED_AT,
            checkpointer=stores.checkpoint.checkpointer,
            hitl_store=None,
            handoff_store=None,
            recorder=None,
        )
        snapshot = app.get_state(_thread_config(lookup_run_id))
        tup = stores.checkpoint.checkpointer.get_tuple(_thread_config(lookup_run_id))
        lifecycle = None
        if snapshot is not None and isinstance(snapshot.values, dict):
            candidate = snapshot.values.get("lifecycle")
            if isinstance(candidate, ConstructorLifecycleState):
                lifecycle = candidate
        if lifecycle is None:
            lifecycle = _lifecycle_from_tuple(tup)
        checkpoint_id = None
        thread_id = None
        if snapshot is not None and isinstance(getattr(snapshot, "config", None), dict):
            configurable = snapshot.config.get("configurable") or {}
            checkpoint_id = configurable.get("checkpoint_id")
            thread_id = configurable.get("thread_id")
        if checkpoint_id is None and tup is not None:
            configurable = (getattr(tup, "config", None) or {}).get("configurable") or {}
            checkpoint_id = configurable.get("checkpoint_id")
            thread_id = configurable.get("thread_id")

        hitl_ids = _hitl_interrupt_ids_for_run(stores.hitl, lookup_run_id)
        handoff_ids = _handoff_ids_for_source_run(stores.handoff, lookup_run_id)
        hitl_request = None
        hitl_answer = None
        interrupt_id = None
        wait_ordinal = None
        if lifecycle is not None and lifecycle.status == STATUS_WAITING_FOR_HUMAN:
            derived = build_decision_request_from_lifecycle(lifecycle)
            interrupt_id = derived.interrupt_id
            wait_ordinal = derived.wait_ordinal
            hitl_request = stores.hitl.get_request(interrupt_id)
            hitl_answer = stores.hitl.get_answer_for_interrupt(interrupt_id)
        elif hitl_ids:
            hitl_request = stores.hitl.get_request(hitl_ids[0])
            hitl_answer = stores.hitl.get_answer_for_interrupt(hitl_ids[0])
            if hitl_request is not None:
                interrupt_id = hitl_request.interrupt_id
                wait_ordinal = hitl_request.wait_ordinal
        handoff = None
        if handoff_ids:
            handoff = stores.handoff.get(handoff_ids[0])
        agent_run, events = _observability_snapshot(stores.observability, lookup_run_id)
        event_types = [event.event_type.value for event in events]
        reasons = _assess_recovery(
            scenario=scenario,
            fixture_run_id=run_id,
            fixture_mission_id=mission_id,
            lookup_run_id=lookup_run_id,
            lookup_mission_id=lookup_mission_id,
            lifecycle=lifecycle,
            checkpoint_id=None if checkpoint_id is None else str(checkpoint_id),
            thread_id=None if thread_id is None else str(thread_id),
            hitl_ids=hitl_ids,
            hitl_request=hitl_request,
            hitl_answer=hitl_answer,
            handoff_ids=handoff_ids,
            handoff=handoff,
            agent_run=agent_run,
            event_types=event_types,
        )
        if (
            lifecycle is not None
            and lookup_mission_id != lifecycle.mission_id
            and "checkpoint_mission_id_mismatch" not in reasons
        ):
            reasons.append("checkpoint_mission_id_mismatch")
        payload = {
            "role": "process-b",
            "pid": os.getpid(),
            "scenario": scenario,
            "run_id": None if lifecycle is None else lifecycle.run_id,
            "mission_id": None if lifecycle is None else lifecycle.mission_id,
            "lookup_run_id": lookup_run_id,
            "lookup_mission_id": lookup_mission_id,
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
            "lifecycle_status": None if lifecycle is None else lifecycle.status,
            "interrupt_id": interrupt_id,
            "wait_ordinal": wait_ordinal,
            "hitl_reason_code": None if hitl_request is None else hitl_request.reason_code,
            "hitl_route": None if hitl_request is None else hitl_request.route,
            "hitl_allowed_decisions": None
            if hitl_request is None
            else list(hitl_request.allowed_decisions),
            "hitl_created_at": None if hitl_request is None else _iso(hitl_request.created_at),
            "hitl_ids": hitl_ids,
            "hitl_answer_present": hitl_answer is not None,
            "handoff_ids": handoff_ids,
            "handoff_id": None if handoff is None else handoff.handoff_id,
            "source_run_id": None if handoff is None else handoff.source_run_id,
            "package_id": None if handoff is None else handoff.candidate_package_reference.package_id,
            "snapshot_id": None if handoff is None else handoff.snapshot_id,
            "target_role": None if handoff is None else handoff.target_role,
            "handoff_created_at": None if handoff is None else handoff.created_at,
            "payload_digest": None
            if handoff is None
            else compute_constructor_handoff_payload_digest(handoff),
            "operational_status": None if agent_run is None else agent_run.operational_status.value,
            "run_started_at": None if agent_run is None else _iso(agent_run.started_at),
            "run_requested_at": None if agent_run is None else _iso(agent_run.requested_at),
            "event_ids": [event.event_id for event in events],
            "event_types": event_types,
            "event_occurred_at": [_iso(event.occurred_at) for event in events],
            "projection_version": None if agent_run is None else agent_run.projection_version,
            "authorization_id_ref": None if lifecycle is None else lifecycle.authorization_id,
            "inconsistency_detected": bool(reasons),
            "inconsistency_reasons": reasons,
            "authority_rehydration": "FORBIDDEN",
            "resume_invoked": False,
            "human_approval_created": False,
            "resume_authority_created": False,
            "start_authority_created": False,
            "operator_authority_created": False,
            "receiver_authority_created": False,
            "tool_authorization_created": False,
            "run_control_reservation": "PROCESS_LOCAL_NOT_REHYDRATED",
            "receiver_ack": "NOT_IMPLEMENTED",
            "target_run": "NOT_IMPLEMENTED",
            "ownership_transfer": "NOT_IMPLEMENTED",
            "new_professional_events": len(events) - event_count_before,
            "live_context_treated_as_authority": False,
            "graph_invoke_called": False,
        }
        _emit_result(payload)
        return 0
    finally:
        stores.close()


def _spawn(
    *,
    role: str,
    repository_root: Path,
    run_id: str,
    mission_id: str,
    scenario: str,
    lookup_run_id: Optional[str] = None,
    lookup_mission_id: Optional[str] = None,
) -> subprocess.CompletedProcess[str]:
    command = [
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
        "--scenario",
        scenario,
    ]
    if lookup_run_id is not None:
        command.extend(["--lookup-run-id", lookup_run_id])
    if lookup_mission_id is not None:
        command.extend(["--lookup-mission-id", lookup_mission_id])
    return subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        shell=False,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
        check=False,
        env=_bounded_subprocess_env(),
    )


def _assert_proc(proc: subprocess.CompletedProcess[str], label: str) -> dict[str, Any]:
    if proc.returncode != 0:
        raise AssertionError(
            f"{label} exited {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return _parse_result(proc.stdout)


def _run_a_then_b(
    tmp_path: Path,
    *,
    run_id: str,
    mission_id: str,
    scenario: str,
    lookup_run_id: Optional[str] = None,
    lookup_mission_id: Optional[str] = None,
    process_a_scenario: Optional[str] = None,
    process_b_scenario: Optional[str] = None,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    _require_real_runtime_absent()
    parent_pid = os.getpid()
    persist_scenario = process_a_scenario or scenario
    recover_scenario = process_b_scenario or scenario
    proc_a = _spawn(
        role="process-a",
        repository_root=tmp_path,
        run_id=run_id,
        mission_id=mission_id,
        scenario=persist_scenario,
    )
    result_a = _assert_proc(proc_a, "process-a")
    assert proc_a.returncode == 0
    proc_b = _spawn(
        role="process-b",
        repository_root=tmp_path,
        run_id=run_id,
        mission_id=mission_id,
        scenario=recover_scenario,
        lookup_run_id=lookup_run_id,
        lookup_mission_id=lookup_mission_id,
    )
    result_b = _assert_proc(proc_b, "process-b")
    assert result_a["pid"] != result_b["pid"]
    assert result_a["pid"] != parent_pid
    assert result_b["pid"] != parent_pid
    assert not REAL_RUNTIME.exists()
    return result_a, result_b, parent_pid


def test_real_runtime_root_absent_before_tests() -> None:
    _require_real_runtime_absent()


def test_waiting_for_human_survives_new_process(tmp_path: Path) -> None:
    result_a, result_b, _parent_pid = _run_a_then_b(
        tmp_path,
        run_id=WAIT_RUN_ID,
        mission_id=WAIT_MISSION_ID,
        scenario=SCENARIO_WAIT,
    )
    assert result_b["inconsistency_detected"] is False, result_b.get("inconsistency_reasons")
    assert result_a["lifecycle_status"] == STATUS_WAITING_FOR_HUMAN
    assert result_b["lifecycle_status"] == STATUS_WAITING_FOR_HUMAN
    assert result_b["run_id"] == WAIT_RUN_ID
    assert result_b["mission_id"] == WAIT_MISSION_ID
    assert result_b["thread_id"] == WAIT_RUN_ID
    assert result_b["checkpoint_id"] == result_a["checkpoint_id"]
    assert result_b["interrupt_id"] == result_a["interrupt_id"]
    assert result_b["wait_ordinal"] == result_a["wait_ordinal"]
    assert result_b["hitl_reason_code"] == result_a["hitl_reason_code"]
    assert result_b["hitl_route"] == result_a["hitl_route"]
    assert result_b["hitl_created_at"] == result_a["hitl_created_at"]
    assert result_b["hitl_answer_present"] is False
    assert result_b["handoff_ids"] == []
    assert result_b["handoff_id"] is None
    assert result_b["operational_status"] == OperationalStatus.WAITING_FOR_HUMAN.value
    assert result_b["event_ids"] == result_a["event_ids"]
    assert result_b["event_occurred_at"] == result_a["event_occurred_at"]
    assert result_b["run_started_at"] == result_a["run_started_at"]
    assert result_b["run_requested_at"] == result_a["run_requested_at"]
    assert result_b["new_professional_events"] == 0
    assert result_b["resume_invoked"] is False
    assert result_b["resume_authority_created"] is False
    assert result_b["human_approval_created"] is False
    assert result_b["run_control_reservation"] == "PROCESS_LOCAL_NOT_REHYDRATED"
    assert result_b["authority_rehydration"] == "FORBIDDEN"
    assert EventType.RUN_RESUMED.value not in result_b["event_types"]


def test_completed_handoff_survives_new_process(tmp_path: Path) -> None:
    result_a, result_b, _parent_pid = _run_a_then_b(
        tmp_path,
        run_id=COMPLETE_RUN_ID,
        mission_id=COMPLETE_MISSION_ID,
        scenario=SCENARIO_COMPLETE,
    )
    assert result_b["inconsistency_detected"] is False, result_b.get("inconsistency_reasons")
    assert result_a["lifecycle_status"] == STATUS_READY_FOR_HANDOFF
    assert result_b["lifecycle_status"] == STATUS_READY_FOR_HANDOFF
    assert result_b["run_id"] == COMPLETE_RUN_ID
    assert result_b["mission_id"] == COMPLETE_MISSION_ID
    assert result_b["thread_id"] == COMPLETE_RUN_ID
    assert result_b["checkpoint_id"] == result_a["checkpoint_id"]
    assert result_b["handoff_id"] == result_a["handoff_id"]
    assert result_b["source_run_id"] == COMPLETE_RUN_ID
    assert result_b["package_id"] == result_a["package_id"]
    assert result_b["snapshot_id"] == result_a["snapshot_id"]
    assert result_b["target_role"] == TARGET_ROLE
    assert result_b["handoff_created_at"] == result_a["handoff_created_at"]
    assert result_b["payload_digest"] == result_a["payload_digest"]
    assert result_b["hitl_ids"] == []
    assert result_b["operational_status"] == OperationalStatus.COMPLETED.value
    assert EventType.HANDOFF_PERSISTED.value in result_b["event_types"]
    assert EventType.RUN_COMPLETED.value in result_b["event_types"]
    assert result_b["event_ids"] == result_a["event_ids"]
    assert result_b["event_occurred_at"] == result_a["event_occurred_at"]
    assert result_b["receiver_ack"] == "NOT_IMPLEMENTED"
    assert result_b["target_run"] == "NOT_IMPLEMENTED"
    assert result_b["ownership_transfer"] == "NOT_IMPLEMENTED"
    assert result_b["new_professional_events"] == 0
    assert result_b["run_control_reservation"] == "PROCESS_LOCAL_NOT_REHYDRATED"


def test_wrong_run_id_is_not_successful_recovery(tmp_path: Path) -> None:
    _result_a, result_b, _parent_pid = _run_a_then_b(
        tmp_path,
        run_id=WAIT_RUN_ID,
        mission_id=WAIT_MISSION_ID,
        scenario=SCENARIO_WAIT,
        lookup_run_id=WRONG_RUN_ID,
    )
    assert result_b["inconsistency_detected"] is True
    assert "checkpoint_missing_for_lookup_run_id" in result_b["inconsistency_reasons"]
    assert result_b["run_id"] is None


def test_wait_recovery_rejects_unexpected_handoff_from_completed_run(tmp_path: Path) -> None:
    """WAIT recovery of a COMPLETED run is rejected by the test harness."""
    _result_a, result_b, _parent_pid = _run_a_then_b(
        tmp_path,
        run_id=COMPLETE_RUN_ID,
        mission_id=COMPLETE_MISSION_ID,
        scenario=SCENARIO_COMPLETE,
        process_b_scenario=SCENARIO_WAIT,
    )
    assert result_b["inconsistency_detected"] is True
    reasons = set(result_b["inconsistency_reasons"])
    assert "wait_unexpected_handoff" in reasons or "wait_lifecycle_status_mismatch" in reasons


def test_complete_recovery_rejects_missing_handoff_from_wait_run(tmp_path: Path) -> None:
    """COMPLETE recovery of a WAIT run is rejected by the test harness."""
    _result_a, result_b, _parent_pid = _run_a_then_b(
        tmp_path,
        run_id=WAIT_RUN_ID,
        mission_id=WAIT_MISSION_ID,
        scenario=SCENARIO_WAIT,
        process_b_scenario=SCENARIO_COMPLETE,
    )
    assert result_b["inconsistency_detected"] is True
    reasons = set(result_b["inconsistency_reasons"])
    assert "complete_handoff_missing" in reasons or "complete_lifecycle_status_mismatch" in reasons


def test_cross_store_mission_id_mismatch_is_detected(tmp_path: Path) -> None:
    _result_a, result_b, _parent_pid = _run_a_then_b(
        tmp_path,
        run_id=WAIT_RUN_ID,
        mission_id=WAIT_MISSION_ID,
        scenario=SCENARIO_WAIT,
        lookup_mission_id=WRONG_MISSION_ID,
    )
    assert result_b["inconsistency_detected"] is True
    assert "lookup_mission_id_differs_from_fixture" in result_b["inconsistency_reasons"]


def test_wait_and_complete_identities_stay_isolated(tmp_path: Path) -> None:
    """Legal separate runs in one runtime root must not cross-attach identities."""
    _require_real_runtime_absent()
    wait_a = _assert_proc(
        _spawn(
            role="process-a",
            repository_root=tmp_path,
            run_id=WAIT_RUN_ID,
            mission_id=WAIT_MISSION_ID,
            scenario=SCENARIO_WAIT,
        ),
        "process-a-wait",
    )
    complete_a = _assert_proc(
        _spawn(
            role="process-a",
            repository_root=tmp_path,
            run_id=COMPLETE_RUN_ID,
            mission_id=COMPLETE_MISSION_ID,
            scenario=SCENARIO_COMPLETE,
        ),
        "process-a-complete",
    )
    wait_b = _assert_proc(
        _spawn(
            role="process-b",
            repository_root=tmp_path,
            run_id=WAIT_RUN_ID,
            mission_id=WAIT_MISSION_ID,
            scenario=SCENARIO_WAIT,
        ),
        "process-b-wait",
    )
    complete_b = _assert_proc(
        _spawn(
            role="process-b",
            repository_root=tmp_path,
            run_id=COMPLETE_RUN_ID,
            mission_id=COMPLETE_MISSION_ID,
            scenario=SCENARIO_COMPLETE,
        ),
        "process-b-complete",
    )
    assert wait_b["inconsistency_detected"] is False, wait_b.get("inconsistency_reasons")
    assert complete_b["inconsistency_detected"] is False, complete_b.get("inconsistency_reasons")
    assert wait_b["handoff_id"] is None
    assert complete_b["handoff_id"] == complete_a["handoff_id"]
    assert complete_b["source_run_id"] != wait_a["run_id"]
    assert complete_b["source_run_id"] != WAIT_RUN_ID
    assert complete_b["handoff_id"] not in wait_b["handoff_ids"]
    assert complete_b["mission_id"] != wait_b["mission_id"]
    # Test-harness detectability only: attaching the other run's handoff
    # to the WAIT identity is a recovery inconsistency.
    assert complete_b["source_run_id"] != wait_b["run_id"]
    assert not REAL_RUNTIME.exists()


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Increment 11C.5 Constructor restart proof")
    parser.add_argument("--role", required=True, choices=("process-a", "process-b"))
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mission-id", required=True)
    parser.add_argument("--scenario", required=True, choices=(SCENARIO_WAIT, SCENARIO_COMPLETE))
    parser.add_argument("--lookup-run-id")
    parser.add_argument("--lookup-mission-id")
    args = parser.parse_args(argv)
    repository_root = Path(args.repository_root)
    lookup_run_id = args.lookup_run_id or args.run_id
    lookup_mission_id = args.lookup_mission_id or args.mission_id
    if args.role == "process-a":
        return role_process_a(
            repository_root=repository_root,
            run_id=args.run_id,
            mission_id=args.mission_id,
            scenario=args.scenario,
        )
    return role_process_b(
        repository_root=repository_root,
        run_id=args.run_id,
        mission_id=args.mission_id,
        scenario=args.scenario,
        lookup_run_id=lookup_run_id,
        lookup_mission_id=lookup_mission_id,
    )


if __name__ == "__main__":
    if any(arg == "--role" for arg in sys.argv[1:]):
        raise SystemExit(_main())
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q", str(TEST_FILE)]))
