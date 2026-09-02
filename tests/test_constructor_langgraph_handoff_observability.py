"""
Increment 10.3E — Constructor LangGraph handoff / completion observability.

Non-Postgres only. In-memory handoff store + observability recorder.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import patch

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
)
from agents.monthly_plan_constructor.exception_engine import CODE_AMBIGUOUS_SCOPE
from agents.monthly_plan_constructor.handoff_contracts import (
    ConstructorHandoff,
    ConstructorHandoffError,
    SOURCE_AGENT,
    TARGET_ROLE,
    compute_constructor_handoff_id,
)
from agents.monthly_plan_constructor.handoff_store import (
    CODE_HANDOFF_IMMUTABILITY_CONFLICT,
    ConstructorHandoffStoreError,
    HandoffStorePutResult,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_OBSERVED_PRODUCTIVITY,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    LaborNormEvidence,
    SOURCE_PROJECT_HISTORY,
)
from agents.monthly_plan_constructor.langgraph_runtime import (
    run_constructor_langgraph,
)
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_READY_FOR_HANDOFF,
    STATUS_WAITING_FOR_HUMAN,
)
from agents.monthly_plan_constructor.mission_scope import ConstructorMissionScope
from agents.monthly_plan_constructor.runtime_instrumentation import (
    RUN_CONTROL_OWNED_EVENT_TYPES,
    ConstructorRuntimeEventKey,
    compute_constructor_runtime_event_id,
)
from agents.observability.contracts import EventStatus, EventType
from agents.observability.recorder import (
    InMemoryObservabilityRecorder,
    RecordOutcome,
    RecordResult,
)
from security.agent_execution_context import issue_read_only_agent_context

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"
MISSION_ID = "mission-inc-10-3e"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
FIXED_AT = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
AGENT_CODE = "MONTHLY_PLAN_CONSTRUCTOR"

STAGE_EVENT_TYPES = frozenset(
    {
        EventType.STAGE_STARTED,
        EventType.STAGE_COMPLETED,
        EventType.STAGE_FAILED,
    }
)

HITL_EVENT_TYPES = frozenset(
    {
        EventType.HUMAN_WAIT_STARTED,
        EventType.HUMAN_DECISION_RECEIVED,
        EventType.RUN_RESUMED,
        EventType.REALITY_REFRESH_STARTED,
        EventType.REALITY_REFRESH_COMPLETED,
    }
)

HANDOFF_EVENT_TYPES = frozenset(
    {
        EventType.HANDOFF_CREATED,
        EventType.HANDOFF_PERSISTED,
        EventType.HANDOFF_PERSIST_FAILED,
        EventType.RUN_COMPLETED,
    }
)


def _context(*, run_id: str):
    return issue_read_only_agent_context(
        agent_code=AGENT_CODE,
        project_code=PROJECT,
        run_id=run_id,
    )


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


class StubAssembler:
    def __call__(self, reality_read, scope: ConstructorMissionScope):
        from agents.monthly_plan_constructor.lifecycle import CandidateAssemblyResult

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
                    "boq_code": "BOQ-001",
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

    def __call__(self, context, mission: ConstructorMissionScope):
        self.calls += 1
        return list(self.rows)


class InMemoryHandoffStore:
    def __init__(self) -> None:
        self._records: dict[str, ConstructorHandoff] = {}
        self.put_calls = 0

    def get(self, handoff_id: str) -> Optional[ConstructorHandoff]:
        return self._records.get(handoff_id)

    def put_if_absent(self, handoff: ConstructorHandoff) -> HandoffStorePutResult:
        self.put_calls += 1
        existing = self._records.get(handoff.handoff_id)
        if existing is None:
            self._records[handoff.handoff_id] = handoff
            return HandoffStorePutResult(created=True, stored_handoff=handoff)
        return HandoffStorePutResult(created=False, stored_handoff=existing)

    def artifacts(self) -> list[ConstructorHandoff]:
        return list(self._records.values())


class ReplaySameStore:
    def __init__(self) -> None:
        self.put_calls = 0
        self.last: Optional[ConstructorHandoff] = None

    def get(self, handoff_id: str) -> Optional[ConstructorHandoff]:
        if self.last is not None and self.last.handoff_id == handoff_id:
            return self.last
        return None

    def put_if_absent(self, handoff: ConstructorHandoff) -> HandoffStorePutResult:
        self.put_calls += 1
        self.last = handoff
        return HandoffStorePutResult(created=False, stored_handoff=handoff)


class ConflictStore:
    def get(self, handoff_id: str) -> Optional[ConstructorHandoff]:
        return None

    def put_if_absent(self, handoff: ConstructorHandoff) -> HandoffStorePutResult:
        mutated = replace(handoff, created_at="2099-01-01T00:00:00Z")
        return HandoffStorePutResult(created=False, stored_handoff=mutated)


class BoomStore:
    def get(self, handoff_id: str) -> Optional[ConstructorHandoff]:
        return None

    def put_if_absent(self, handoff: ConstructorHandoff) -> HandoffStorePutResult:
        raise RuntimeError("store exploded")


@dataclass
class FailingRecorder:
    fail_on: int = 1
    calls: int = 0
    events: list[Any] = field(default_factory=list)

    def record_event(self, event: Any) -> RecordResult:
        self.calls += 1
        if self.calls >= self.fail_on:
            raise RuntimeError("recorder-down")
        backend = InMemoryObservabilityRecorder()
        for prior in self.events:
            backend.record_event(prior)
        result = backend.record_event(event)
        self.events.append(event)
        return result


def _detail_dict(event) -> dict[str, Any]:
    return dict(event.to_dict().get("detail") or {})


def _run(
    *,
    run_id: str,
    recorder: InMemoryObservabilityRecorder | None = None,
    handoff_store: Any | None = None,
    labor_evidence=(_history(),),
    **kwargs,
):
    return run_constructor_langgraph(
        context=_context(run_id=run_id),
        project_code=PROJECT,
        month_key=MONTH,
        assemble_candidates=StubAssembler(),
        labor_evidence=labor_evidence,
        scope_reader=RecordingReader(),
        mission_id=MISSION_ID,
        run_id=run_id,
        now=FIXED_AT,
        handoff_store=handoff_store,
        recorder=recorder,
        **kwargs,
    )


def _events(recorder: InMemoryObservabilityRecorder, run_id: str):
    return list(recorder.events_for_run(run_id))


def _event_types(recorder: InMemoryObservabilityRecorder, run_id: str):
    return {event.event_type for event in _events(recorder, run_id)}


def _events_of_type(recorder: InMemoryObservabilityRecorder, run_id: str, event_type: EventType):
    return [e for e in _events(recorder, run_id) if e.event_type == event_type]


def _expected_handoff_id(state) -> str:
    package = state.package
    reality = state.reality_read
    assert package is not None and reality is not None
    return compute_constructor_handoff_id(
        source_run_id=state.run_id,
        package_id=package.package_id,
        snapshot_id=reality.snapshot_id,
    )


class TestRecorderNoneParity(unittest.TestCase):
    def test_recorder_none_preserves_handoff_behavior(self) -> None:
        from agents.monthly_plan_constructor import langgraph_runtime as lg

        store = InMemoryHandoffStore()
        with patch.object(
            lg, "persist_constructor_handoff", wraps=lg.persist_constructor_handoff
        ) as spy:
            state = _run(run_id="run-10-3e-none", handoff_store=store, recorder=None)
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(len(store.artifacts()), 1)


class TestReadyAloneNoCompletion(unittest.TestCase):
    def test_ready_without_store_does_not_emit_run_completed(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        state = _run(run_id="run-10-3e-ready-only", recorder=recorder, handoff_store=None)
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        recorded = _event_types(recorder, "run-10-3e-ready-only")
        self.assertNotIn(EventType.RUN_COMPLETED, recorded)
        self.assertTrue(recorded.isdisjoint(HANDOFF_EVENT_TYPES))


class TestHappyPathObservability(unittest.TestCase):
    def test_handoff_created_persisted_and_run_completed(self) -> None:
        run_id = "run-10-3e-happy"
        recorder = InMemoryObservabilityRecorder()
        store = InMemoryHandoffStore()
        state = _run(run_id=run_id, recorder=recorder, handoff_store=store)
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        expected_id = _expected_handoff_id(state)
        created = _events_of_type(recorder, run_id, EventType.HANDOFF_CREATED)
        persisted = _events_of_type(recorder, run_id, EventType.HANDOFF_PERSISTED)
        completed = _events_of_type(recorder, run_id, EventType.RUN_COMPLETED)
        self.assertEqual(len(created), 1)
        self.assertEqual(len(persisted), 1)
        self.assertEqual(len(completed), 1)
        self.assertEqual(created[0].handoff_id, expected_id)
        self.assertEqual(persisted[0].handoff_id, expected_id)
        self.assertEqual(completed[0].handoff_id, expected_id)
        self.assertEqual(created[0].stage_id, "HANDOFF_PREPARATION")
        self.assertEqual(persisted[0].stage_id, "HANDOFF_PERSISTENCE")
        self.assertEqual(completed[0].stage_id, "RUN_COMPLETION")

    def test_handoff_event_uses_real_handoff_id(self) -> None:
        run_id = "run-10-3e-id"
        recorder = InMemoryObservabilityRecorder()
        state = _run(run_id=run_id, recorder=recorder, handoff_store=InMemoryHandoffStore())
        expected_id = _expected_handoff_id(state)
        created = _events_of_type(recorder, run_id, EventType.HANDOFF_CREATED)[0]
        self.assertTrue(expected_id.startswith("eos-hof-"))
        self.assertEqual(created.handoff_id, expected_id)
        detail = _detail_dict(created)
        self.assertEqual(detail.get("source_agent"), SOURCE_AGENT)
        self.assertEqual(detail.get("target_role"), TARGET_ROLE)

    def test_no_full_handoff_payload_leakage(self) -> None:
        run_id = "run-10-3e-minimize"
        recorder = InMemoryObservabilityRecorder()
        _run(run_id=run_id, recorder=recorder, handoff_store=InMemoryHandoffStore())
        for event in _events(recorder, run_id):
            if event.event_type not in HANDOFF_EVENT_TYPES:
                continue
            detail_payload = json.dumps(_detail_dict(event), ensure_ascii=False).lower()
            for banned in (
                "candidate_ids",
                "candidate_id",
                "secret",
                "token",
                "credential",
                "agentexecutioncontext",
                "scope",
            ):
                self.assertNotIn(banned, detail_payload, msg=f"{event.event_type} detail leaked {banned}")


class TestPersistenceFailure(unittest.TestCase):
    def test_immutability_conflict_emits_persist_failed_not_completed(self) -> None:
        run_id = "run-10-3e-conflict"
        recorder = InMemoryObservabilityRecorder()
        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            _run(run_id=run_id, recorder=recorder, handoff_store=ConflictStore())
        self.assertEqual(caught.exception.code, CODE_HANDOFF_IMMUTABILITY_CONFLICT)
        types = _event_types(recorder, run_id)
        self.assertIn(EventType.HANDOFF_CREATED, types)
        self.assertIn(EventType.HANDOFF_PERSIST_FAILED, types)
        self.assertNotIn(EventType.HANDOFF_PERSISTED, types)
        self.assertNotIn(EventType.RUN_COMPLETED, types)
        failed = _events_of_type(recorder, run_id, EventType.HANDOFF_PERSIST_FAILED)[0]
        self.assertEqual(failed.status, EventStatus.FAILED)
        self.assertEqual(
            _detail_dict(failed).get("error_code"),
            CODE_HANDOFF_IMMUTABILITY_CONFLICT,
        )

    def test_unexpected_store_runtime_exception(self) -> None:
        run_id = "run-10-3e-boom"
        recorder = InMemoryObservabilityRecorder()
        with self.assertRaises(RuntimeError) as caught:
            _run(run_id=run_id, recorder=recorder, handoff_store=BoomStore())
        self.assertEqual(str(caught.exception), "store exploded")
        types = _event_types(recorder, run_id)
        self.assertIn(EventType.HANDOFF_CREATED, types)
        self.assertIn(EventType.HANDOFF_PERSIST_FAILED, types)
        self.assertNotIn(EventType.RUN_COMPLETED, types)
        failed = _events_of_type(recorder, run_id, EventType.HANDOFF_PERSIST_FAILED)[0]
        self.assertEqual(failed.status, EventStatus.FAILED)
        self.assertEqual(_detail_dict(failed).get("exception_type"), "RuntimeError")
        self.assertNotIn("store exploded", json.dumps(failed.to_dict()))

    def test_persistence_failure_remains_primary_when_failure_event_recording_fails(
        self,
    ) -> None:
        from agents.monthly_plan_constructor import langgraph_runtime as lg

        run_id = "run-10-3e-fail-chain"
        recorder = InMemoryObservabilityRecorder()
        original_emit = lg.ConstructorRuntimeInstrumentation.emit

        def patched_emit(self, **kwargs):
            if kwargs["key"].event_type == EventType.HANDOFF_PERSIST_FAILED:
                raise RuntimeError("recorder-down-on-fail-event")
            return original_emit(self, **kwargs)

        with patch.object(lg.ConstructorRuntimeInstrumentation, "emit", patched_emit):
            with self.assertRaises(RuntimeError) as caught:
                _run(run_id=run_id, recorder=recorder, handoff_store=BoomStore())
        self.assertEqual(str(caught.exception), "store exploded")
        recorder_failure = caught.exception.__cause__
        self.assertIsInstance(recorder_failure, RuntimeError)
        self.assertEqual(str(recorder_failure), "recorder-down-on-fail-event")
        types = _event_types(recorder, run_id)
        self.assertIn(EventType.HANDOFF_CREATED, types)
        self.assertNotIn(EventType.HANDOFF_PERSISTED, types)
        self.assertNotIn(EventType.HANDOFF_PERSIST_FAILED, types)
        self.assertNotIn(EventType.RUN_COMPLETED, types)
        for event in _events(recorder, run_id):
            payload = json.dumps(event.to_dict(), ensure_ascii=False).lower()
            self.assertNotIn("store exploded", payload)


class TestBuildFailure(unittest.TestCase):
    def test_build_failure_no_false_persisted_or_completed(self) -> None:
        from agents.monthly_plan_constructor import langgraph_runtime as lg

        run_id = "run-10-3e-build-fail"
        recorder = InMemoryObservabilityRecorder()

        def boom_build(*args, **kwargs):
            raise ConstructorHandoffError("HANDOFF_CONTRACT_BLOCKER", "build blocked")

        with patch.object(lg, "build_constructor_handoff", side_effect=boom_build):
            with self.assertRaises(ConstructorHandoffError):
                _run(run_id=run_id, recorder=recorder, handoff_store=InMemoryHandoffStore())
        types = _event_types(recorder, run_id)
        self.assertTrue(types.isdisjoint(HANDOFF_EVENT_TYPES))


class TestReplayIdempotency(unittest.TestCase):
    def test_same_handoff_replay_idempotent(self) -> None:
        run_id = "run-10-3e-replay"
        recorder = InMemoryObservabilityRecorder()
        state = _run(run_id=run_id, recorder=recorder, handoff_store=ReplaySameStore())
        expected_id = _expected_handoff_id(state)
        created = _events_of_type(recorder, run_id, EventType.HANDOFF_CREATED)[0]
        key = ConstructorRuntimeEventKey(
            run_id=run_id,
            event_type=EventType.HANDOFF_CREATED,
            stage_id="HANDOFF_PREPARATION",
            node_name="persist_handoff",
            attempt_n=1,
            resume_n=0,
            semantic_occurrence_key=f"handoff-{expected_id}",
            artifact_correlation_id=expected_id,
        )
        replay = recorder.record_event(created)
        self.assertEqual(replay.outcome, RecordOutcome.IDEMPOTENT_REPLAY)
        self.assertEqual(
            compute_constructor_runtime_event_id(key),
            created.event_id,
        )

    def test_no_duplicate_handoff_semantic_events(self) -> None:
        run_id = "run-10-3e-no-dup"
        recorder = InMemoryObservabilityRecorder()
        _run(run_id=run_id, recorder=recorder, handoff_store=InMemoryHandoffStore())
        for event_type in (
            EventType.HANDOFF_CREATED,
            EventType.HANDOFF_PERSISTED,
            EventType.RUN_COMPLETED,
        ):
            matches = _events_of_type(recorder, run_id, event_type)
            self.assertEqual(len(matches), 1, msg=event_type.value)


class TestRecorderFailurePolicy(unittest.TestCase):
    def test_recorder_failure_before_persistence_skips_store(self) -> None:
        from agents.monthly_plan_constructor import langgraph_runtime as lg

        run_id = "run-10-3e-rec-pre"
        store = InMemoryHandoffStore()
        failing = FailingRecorder(fail_on=1)
        with patch.object(
            lg, "persist_constructor_handoff", wraps=lg.persist_constructor_handoff
        ) as spy:
            with self.assertRaises(RuntimeError):
                _run(
                    run_id=run_id,
                    recorder=failing,  # type: ignore[arg-type]
                    handoff_store=store,
                )
        self.assertEqual(spy.call_count, 0)
        self.assertEqual(len(store.artifacts()), 0)

    def test_recorder_failure_after_persistence_preserves_business_truth(self) -> None:
        from agents.monthly_plan_constructor import langgraph_runtime as lg

        run_id = "run-10-3e-rec-post"
        store = InMemoryHandoffStore()
        recorder = InMemoryObservabilityRecorder()
        original_emit = lg.ConstructorRuntimeInstrumentation.emit
        persist_emit_calls = {"count": 0}

        def patched_emit(self, **kwargs):
            if kwargs["key"].event_type == EventType.HANDOFF_PERSISTED:
                persist_emit_calls["count"] += 1
                raise RuntimeError("recorder-down")
            return original_emit(self, **kwargs)

        with patch.object(lg.ConstructorRuntimeInstrumentation, "emit", patched_emit):
            with self.assertRaises(RuntimeError):
                _run(run_id=run_id, recorder=recorder, handoff_store=store)
        self.assertEqual(persist_emit_calls["count"], 1)
        self.assertEqual(len(store.artifacts()), 1)
        types = _event_types(recorder, run_id)
        self.assertIn(EventType.HANDOFF_CREATED, types)
        self.assertNotIn(EventType.HANDOFF_PERSIST_FAILED, types)
        self.assertNotIn(EventType.RUN_COMPLETED, types)

    def test_recorder_failure_is_not_handoff_persist_failed(self) -> None:
        run_id = "run-10-3e-rec-not-fail"
        failing = FailingRecorder(fail_on=1)
        with self.assertRaises(RuntimeError):
            _run(
                run_id=run_id,
                recorder=failing,  # type: ignore[arg-type]
                handoff_store=InMemoryHandoffStore(),
            )


class TestNoDuplication(unittest.TestCase):
    def test_no_stage_handoff_duplication(self) -> None:
        run_id = "run-10-3e-no-stage"
        recorder = InMemoryObservabilityRecorder()
        _run(run_id=run_id, recorder=recorder, handoff_store=InMemoryHandoffStore())
        handoff_stage_events = [
            e
            for e in _events(recorder, run_id)
            if e.stage_id in {"HANDOFF_PREPARATION", "HANDOFF_PERSISTENCE", "RUN_COMPLETION"}
            and e.event_type in STAGE_EVENT_TYPES
        ]
        self.assertEqual(handoff_stage_events, [])

    def test_no_hitl_or_run_control_duplication(self) -> None:
        run_id = "run-10-3e-no-hitl-rc"
        recorder = InMemoryObservabilityRecorder()
        _run(run_id=run_id, recorder=recorder, handoff_store=InMemoryHandoffStore())
        recorded = _event_types(recorder, run_id)
        self.assertTrue(recorded.isdisjoint(HITL_EVENT_TYPES))
        self.assertTrue(recorded.isdisjoint(RUN_CONTROL_OWNED_EVENT_TYPES))

    def test_no_artifact_created_for_handoff(self) -> None:
        run_id = "run-10-3e-no-artifact"
        recorder = InMemoryObservabilityRecorder()
        _run(run_id=run_id, recorder=recorder, handoff_store=InMemoryHandoffStore())
        artifacts = _events_of_type(recorder, run_id, EventType.ARTIFACT_CREATED)
        handoff_ids = {
            e.handoff_id
            for e in _events(recorder, run_id)
            if e.event_type in HANDOFF_EVENT_TYPES and e.handoff_id
        }
        for event in artifacts:
            self.assertNotIn(event.artifact_id, handoff_ids)


class TestWaitingDoesNotHandoff(unittest.TestCase):
    def test_waiting_for_human_no_handoff_events(self) -> None:
        run_id = "run-10-3e-wait"
        recorder = InMemoryObservabilityRecorder()
        state = _run(
            run_id=run_id,
            recorder=recorder,
            handoff_store=InMemoryHandoffStore(),
            facility_scope=["ALL", FACILITY_TARGET],
            labor_evidence=(),
        )
        self.assertEqual(state.status, STATUS_WAITING_FOR_HUMAN)
        self.assertTrue(_event_types(recorder, run_id).isdisjoint(HANDOFF_EVENT_TYPES))


if __name__ == "__main__":
    unittest.main()
