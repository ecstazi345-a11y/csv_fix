"""
Increment 10.8A — structured HITL read contract tests.

Agent-neutral observability subcontracts + Control Room Human Decision Surface.
No Streamlit. No write-path changes. No LLM.
"""

from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timezone
from typing import Any

from agents.control_room.dtos import DerivationState
from agents.control_room.query_port import AgentControlRoomQueryPort
from agents.observability.contracts import (
    HUMAN_DECISION_RECORD_OBSERVABILITY_SCHEMA_VERSION,
    HUMAN_DECISION_REQUEST_OBSERVABILITY_SCHEMA_VERSION,
    EventFamily,
    EventStatus,
    EventType,
    InitiatorType,
    ObservabilityContractError,
    OperationalStatus,
    TriggerType,
    build_agent_run,
    build_human_decision_record_observability_context,
    build_human_decision_request_observability_context,
    build_observability_event,
    human_decision_record_observability_context_from_dict,
    human_decision_request_observability_context_from_dict,
)
from agents.observability.projection import project_agent_run_event
from agents.observability.recorder import RecordOutcome, compute_observability_event_fingerprint
from agents.observability.store import InMemoryObservabilityStore, _observability_event_from_dict

FIXED_AT = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
LATER_AT = datetime(2026, 9, 2, 12, 30, 0, tzinfo=timezone.utc)


def _run(**overrides: Any):
    payload = {
        "run_id": "run-001",
        "request_id": "req-001",
        "agent_code": "GENERIC_AGENT",
        "agent_version": "0.1",
        "mission_id": "mission-001",
        "project_code": "PRJ_001",
        "month_key": "2026-09",
        "initiator_type": InitiatorType.HUMAN,
        "initiator_id": "operator-local",
        "trigger_type": TriggerType.MANUAL,
        "trigger_reason": "manual",
        "operational_status": OperationalStatus.RUNNING,
        "requested_at": FIXED_AT,
        "updated_at": FIXED_AT,
        "thread_id": "run-001",
        "scope_summary": {},
        "safe_summary": {},
        "safe_counts": {},
        "projection_version": 0,
    }
    payload.update(overrides)
    return build_agent_run(**payload)


def _append(store: InMemoryObservabilityStore, **event_kwargs: Any) -> None:
    allow_legacy = event_kwargs.pop("allow_legacy_missing_hitl_subcontracts", False)
    event = build_observability_event(
        event_id=event_kwargs.pop("event_id"),
        run_id="run-001",
        agent_code="GENERIC_AGENT",
        occurred_at=event_kwargs.pop("occurred_at", FIXED_AT),
        event_type=event_kwargs.pop("event_type"),
        status=event_kwargs.pop("status", EventStatus.OK),
        title=event_kwargs.pop("title", "event"),
        allow_legacy_missing_hitl_subcontracts=allow_legacy,
        **event_kwargs,
    )
    run = store.get_run("run-001")
    change = project_agent_run_event(run, event)
    store.append_event_and_project_run(
        event=event,
        expected_projection_version=run.projection_version,
        projection_change=change,
    )


class RequestSubcontractTests(unittest.TestCase):
    def test_schema_version(self) -> None:
        ctx = build_human_decision_request_observability_context(
            reason_code="WAIT",
            allowed_decisions=("CONTINUE",),
        )
        self.assertEqual(ctx.schema_version, HUMAN_DECISION_REQUEST_OBSERVABILITY_SCHEMA_VERSION)

    def test_allowed_decisions_bounds(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_human_decision_request_observability_context(
                reason_code="WAIT",
                allowed_decisions=(),
            )
        with self.assertRaises(ObservabilityContractError):
            build_human_decision_request_observability_context(
                reason_code="WAIT",
                allowed_decisions=tuple(f"D{i}" for i in range(9)),
            )

    def test_duplicate_allowed_decisions_rejected(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_human_decision_request_observability_context(
                reason_code="WAIT",
                allowed_decisions=("CONTINUE", "CONTINUE"),
            )

    def test_evidence_refs_bounds_and_duplicates(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_human_decision_request_observability_context(
                reason_code="WAIT",
                allowed_decisions=("CONTINUE",),
                evidence_refs=tuple(f"ref-{i}" for i in range(33)),
            )
        with self.assertRaises(ObservabilityContractError):
            build_human_decision_request_observability_context(
                reason_code="WAIT",
                allowed_decisions=("CONTINUE",),
                evidence_refs=("ref-1", "ref-1"),
            )

    def test_secret_scan_rejects_human_readable_reason(self) -> None:
        sentinel = "eos-sec-hitl-reason-leak-test-value"
        old = os.environ.get("SUPABASE_KEY")
        os.environ["SUPABASE_KEY"] = sentinel
        try:
            with self.assertRaises(ObservabilityContractError):
                build_human_decision_request_observability_context(
                    reason_code="WAIT",
                    allowed_decisions=("CONTINUE",),
                    human_readable_reason=f"operator note references {sentinel}",
                )
        finally:
            if old is None:
                os.environ.pop("SUPABASE_KEY", None)
            else:
                os.environ["SUPABASE_KEY"] = old

    def test_round_trip_serialization(self) -> None:
        ctx = build_human_decision_request_observability_context(
            reason_code="AMBIGUOUS_SCOPE",
            allowed_decisions=("CLARIFY_SCOPE", "ABORT_RUN"),
            human_readable_reason="Needs clarification",
            evidence_refs=("ev-1",),
        )
        restored = human_decision_request_observability_context_from_dict(ctx.to_dict())
        self.assertEqual(restored, ctx)


class RecordSubcontractTests(unittest.TestCase):
    def test_schema_version(self) -> None:
        ctx = build_human_decision_record_observability_context(
            decision_code="ABORT_RUN",
            actor_id="operator-1",
            actor_type="HUMAN",
        )
        self.assertEqual(ctx.schema_version, HUMAN_DECISION_RECORD_OBSERVABILITY_SCHEMA_VERSION)

    def test_secret_scan_on_actor_fields(self) -> None:
        sentinel = "eos-sec-hitl-actor-leak-test-value"
        old = os.environ.get("SUPABASE_KEY")
        os.environ["SUPABASE_KEY"] = sentinel
        try:
            with self.assertRaises(ObservabilityContractError):
                build_human_decision_record_observability_context(
                    decision_code="ABORT_RUN",
                    actor_id=sentinel,
                    actor_type="HUMAN",
                )
        finally:
            if old is None:
                os.environ.pop("SUPABASE_KEY", None)
            else:
                os.environ["SUPABASE_KEY"] = old

    def test_round_trip_serialization(self) -> None:
        ctx = build_human_decision_record_observability_context(
            decision_code="CLARIFY_SCOPE",
            actor_id="operator-1",
            actor_type="HUMAN",
        )
        restored = human_decision_record_observability_context_from_dict(ctx.to_dict())
        self.assertEqual(restored, ctx)


class EventPlacementTests(unittest.TestCase):
    def test_run_resumed_rejects_subcontracts(self) -> None:
        request = build_human_decision_request_observability_context(
            reason_code="WAIT",
            allowed_decisions=("CONTINUE",),
        )
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(
                event_id="evt-res",
                run_id="run-001",
                agent_code="GENERIC_AGENT",
                occurred_at=FIXED_AT,
                event_type=EventType.RUN_RESUMED,
                status=EventStatus.OK,
                title="Resumed",
                resume_n=1,
                human_decision_request=request,
            )


class FingerprintTests(unittest.TestCase):
    def test_identical_replay_idempotent_fingerprint(self) -> None:
        request = build_human_decision_request_observability_context(
            reason_code="WAIT",
            allowed_decisions=("CONTINUE",),
        )
        kwargs = {
            "event_id": "evt-fp-1",
            "run_id": "run-001",
            "agent_code": "GENERIC_AGENT",
            "occurred_at": FIXED_AT,
            "event_type": EventType.HUMAN_WAIT_STARTED,
            "status": EventStatus.OK,
            "title": "Wait",
            "interrupt_id": "intr-001",
            "human_decision_request": request,
        }
        first = build_observability_event(**kwargs)
        second = build_observability_event(**kwargs)
        self.assertEqual(
            compute_observability_event_fingerprint(first),
            compute_observability_event_fingerprint(second),
        )

    def test_changed_semantics_different_fingerprint(self) -> None:
        base = {
            "event_id": "evt-fp-2",
            "run_id": "run-001",
            "agent_code": "GENERIC_AGENT",
            "occurred_at": FIXED_AT,
            "event_type": EventType.HUMAN_WAIT_STARTED,
            "status": EventStatus.OK,
            "title": "Wait",
            "interrupt_id": "intr-001",
        }
        a = build_observability_event(
            **base,
            human_decision_request=build_human_decision_request_observability_context(
                reason_code="A",
                allowed_decisions=("CONTINUE",),
            ),
        )
        b = build_observability_event(
            **base,
            human_decision_request=build_human_decision_request_observability_context(
                reason_code="B",
                allowed_decisions=("CONTINUE",),
            ),
        )
        self.assertNotEqual(
            compute_observability_event_fingerprint(a),
            compute_observability_event_fingerprint(b),
        )


class HumanDecisionSurfaceReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryObservabilityStore()
        self.store.create_run(_run())
        self.port = AgentControlRoomQueryPort(self.store)

    def test_structured_surface_views(self) -> None:
        _append(
            self.store,
            event_id="wait-1",
            event_type=EventType.HUMAN_WAIT_STARTED,
            family=EventFamily.HITL,
            stage_id="HUMAN_GATE",
            resume_n=1,
            interrupt_id="intr-001",
            title="Wait",
            human_decision_request=build_human_decision_request_observability_context(
                reason_code="AMBIGUOUS_SCOPE",
                allowed_decisions=("CLARIFY_SCOPE", "ABORT_RUN"),
                evidence_refs=("ev-1",),
            ),
        )
        _append(
            self.store,
            event_id="dec-1",
            event_type=EventType.HUMAN_DECISION_RECEIVED,
            family=EventFamily.HITL,
            stage_id="HUMAN_GATE",
            resume_n=1,
            interrupt_id="intr-001",
            decision_id="dec-001",
            title="Decision",
            occurred_at=LATER_AT,
            human_decision_record=build_human_decision_record_observability_context(
                decision_code="CLARIFY_SCOPE",
                actor_id="operator-1",
                actor_type="HUMAN",
            ),
        )
        surface = self.port.get_run_snapshot("run-001").human_decision_surface
        self.assertFalse(surface.authority_modeled)
        self.assertEqual(surface.request.reason_code, "AMBIGUOUS_SCOPE")
        self.assertEqual(surface.decision.decision_code, "CLARIFY_SCOPE")
        self.assertEqual(surface.consequence.decision_received_at, LATER_AT)

    def test_old_event_incomplete_not_fabricated(self) -> None:
        _append(
            self.store,
            event_id="wait-legacy",
            event_type=EventType.HUMAN_WAIT_STARTED,
            family=EventFamily.HITL,
            stage_id="HUMAN_GATE",
            resume_n=1,
            interrupt_id="intr-001",
            title="Legacy wait",
            detail={"reason_code": "FAKE", "allowed_decisions": ["FAKE"]},
            allow_legacy_missing_hitl_subcontracts=True,
        )
        surface = self.port.get_run_snapshot("run-001").human_decision_surface
        self.assertEqual(surface.request.derivation_state, DerivationState.INCOMPLETE)
        self.assertEqual(surface.request.reason_code, "")

    def test_legacy_stored_event_deserializes(self) -> None:
        legacy_payload = {
            "schema_version": "observability_event.v0.1",
            "event_id": "evt-store-legacy",
            "run_id": "run-001",
            "agent_code": "GENERIC_AGENT",
            "occurred_at": FIXED_AT.isoformat(),
            "family": EventFamily.HITL.value,
            "event_type": EventType.HUMAN_WAIT_STARTED.value,
            "status": EventStatus.OK.value,
            "title": "Stored legacy",
            "interrupt_id": "intr-legacy",
            "attempt_n": 1,
            "resume_n": 1,
            "detail": {},
        }
        event = _observability_event_from_dict(legacy_payload)
        self.assertIsNone(event.human_decision_request)
        self.assertIsNone(event.to_dict()["human_decision_request"])


class StoreReplayTests(unittest.TestCase):
    def test_same_event_id_structured_replay_is_idempotent(self) -> None:
        store = InMemoryObservabilityStore()
        store.create_run(_run())
        request = build_human_decision_request_observability_context(
            reason_code="WAIT",
            allowed_decisions=("CONTINUE",),
        )
        event = build_observability_event(
            event_id="evt-replay",
            run_id="run-001",
            agent_code="GENERIC_AGENT",
            occurred_at=FIXED_AT,
            event_type=EventType.HUMAN_WAIT_STARTED,
            status=EventStatus.OK,
            title="Wait",
            interrupt_id="intr-001",
            human_decision_request=request,
        )
        run = store.get_run("run-001")
        change = project_agent_run_event(run, event)
        first = store.append_event_and_project_run(
            event=event,
            expected_projection_version=0,
            projection_change=change,
        )
        run2 = store.get_run("run-001")
        replay = store.append_event_and_project_run(
            event=event,
            expected_projection_version=run2.projection_version,
            projection_change=change,
        )
        self.assertEqual(first.outcome, RecordOutcome.CREATED)
        self.assertEqual(replay.outcome, RecordOutcome.IDEMPOTENT_REPLAY)


if __name__ == "__main__":
    unittest.main()
