"""
Increment 10.9A — structured handoff observability read contract tests.

Agent-neutral observability subcontracts + Control Room AgentHandoffView enrichment.
No Streamlit. No write-path changes. No LLM.
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from typing import Any

from agents.control_room.dtos import DerivationState, HandoffStatus
from agents.control_room.query_port import AgentControlRoomQueryPort
from agents.observability.contracts import (
    HANDOFF_OBSERVABILITY_SCHEMA_VERSION,
    EventFamily,
    EventStatus,
    EventType,
    InitiatorType,
    ObservabilityContractError,
    OperationalStatus,
    TriggerType,
    build_agent_run,
    build_handoff_observability_context,
    build_observability_event,
    handoff_observability_context_from_dict,
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


def _handoff_context(**overrides: Any):
    payload = {
        "handoff_type": "CONSTRUCTOR_TO_ADMISSION",
        "target_role_code": "MONTHLY_PLAN_ADMISSION_AGENT",
    }
    payload.update(overrides)
    return build_handoff_observability_context(**payload)


def _append(store: InMemoryObservabilityStore, **event_kwargs: Any) -> None:
    allow_legacy = event_kwargs.pop("allow_legacy_missing_handoff_subcontract", False)
    event = build_observability_event(
        event_id=event_kwargs.pop("event_id"),
        run_id="run-001",
        agent_code="GENERIC_AGENT",
        occurred_at=event_kwargs.pop("occurred_at", FIXED_AT),
        event_type=event_kwargs.pop("event_type"),
        status=event_kwargs.pop("status", EventStatus.OK),
        title=event_kwargs.pop("title", "event"),
        allow_legacy_missing_handoff_subcontract=allow_legacy,
        **event_kwargs,
    )
    run = store.get_run("run-001")
    change = project_agent_run_event(run, event)
    store.append_event_and_project_run(
        event=event,
        expected_projection_version=run.projection_version,
        projection_change=change,
    )


class HandoffSubcontractTests(unittest.TestCase):
    def test_valid_subcontract(self) -> None:
        ctx = _handoff_context()
        self.assertEqual(ctx.schema_version, HANDOFF_OBSERVABILITY_SCHEMA_VERSION)
        self.assertEqual(ctx.handoff_type, "CONSTRUCTOR_TO_ADMISSION")
        self.assertEqual(ctx.target_role_code, "MONTHLY_PLAN_ADMISSION_AGENT")

    def test_invalid_schema_rejected(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_handoff_observability_context(
                handoff_type="CONSTRUCTOR_TO_ADMISSION",
                target_role_code="MONTHLY_PLAN_ADMISSION_AGENT",
                schema_version="handoff_observability.v9.9",
            )

    def test_empty_handoff_type_rejected(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_handoff_observability_context(
                handoff_type="",
                target_role_code="MONTHLY_PLAN_ADMISSION_AGENT",
            )

    def test_oversized_handoff_type_rejected(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_handoff_observability_context(
                handoff_type="X" * 65,
                target_role_code="MONTHLY_PLAN_ADMISSION_AGENT",
            )

    def test_empty_target_role_rejected(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_handoff_observability_context(
                handoff_type="CONSTRUCTOR_TO_ADMISSION",
                target_role_code="",
            )

    def test_oversized_target_role_rejected(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_handoff_observability_context(
                handoff_type="CONSTRUCTOR_TO_ADMISSION",
                target_role_code="Y" * 65,
            )

    def test_round_trip_serialization(self) -> None:
        ctx = _handoff_context(
            handoff_type="ADMISSION_TO_CONSTRAINT",
            target_role_code="MONTHLY_PLAN_CONSTRAINT_AGENT",
        )
        restored = handoff_observability_context_from_dict(ctx.to_dict())
        self.assertEqual(restored, ctx)


class EventPlacementTests(unittest.TestCase):
    def _handoff_created_base(self) -> dict[str, Any]:
        return {
            "event_id": "evt-ho-1",
            "run_id": "run-001",
            "agent_code": "GENERIC_AGENT",
            "occurred_at": FIXED_AT,
            "event_type": EventType.HANDOFF_CREATED,
            "status": EventStatus.OK,
            "title": "Handoff created",
            "handoff_id": "handoff-001",
            "artifact_type": "package",
            "artifact_id": "pkg-001",
        }

    def test_handoff_created_requires_context(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(**self._handoff_created_base())

    def test_handoff_created_accepts_context(self) -> None:
        event = build_observability_event(
            **self._handoff_created_base(),
            handoff_observability=_handoff_context(),
        )
        self.assertIsNotNone(event.handoff_observability)

    def test_handoff_persisted_rejects_context(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(
                event_id="evt-ho-2",
                run_id="run-001",
                agent_code="GENERIC_AGENT",
                occurred_at=FIXED_AT,
                event_type=EventType.HANDOFF_PERSISTED,
                status=EventStatus.OK,
                title="Handoff persisted",
                handoff_id="handoff-001",
                handoff_observability=_handoff_context(),
            )

    def test_run_completed_rejects_context(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            build_observability_event(
                event_id="evt-ho-3",
                run_id="run-001",
                agent_code="GENERIC_AGENT",
                occurred_at=FIXED_AT,
                event_type=EventType.RUN_COMPLETED,
                status=EventStatus.OK,
                title="Run completed",
                handoff_observability=_handoff_context(),
            )


class FingerprintTests(unittest.TestCase):
    def test_identical_replay_idempotent_fingerprint(self) -> None:
        kwargs = {
            "event_id": "evt-fp-ho-1",
            "run_id": "run-001",
            "agent_code": "GENERIC_AGENT",
            "occurred_at": FIXED_AT,
            "event_type": EventType.HANDOFF_CREATED,
            "status": EventStatus.OK,
            "title": "Handoff created",
            "handoff_id": "handoff-001",
            "artifact_type": "package",
            "artifact_id": "pkg-001",
            "handoff_observability": _handoff_context(),
        }
        first = build_observability_event(**kwargs)
        second = build_observability_event(**kwargs)
        self.assertEqual(
            compute_observability_event_fingerprint(first),
            compute_observability_event_fingerprint(second),
        )

    def test_changed_handoff_type_different_fingerprint(self) -> None:
        base = {
            "event_id": "evt-fp-ho-2",
            "run_id": "run-001",
            "agent_code": "GENERIC_AGENT",
            "occurred_at": FIXED_AT,
            "event_type": EventType.HANDOFF_CREATED,
            "status": EventStatus.OK,
            "title": "Handoff created",
            "handoff_id": "handoff-001",
            "artifact_type": "package",
            "artifact_id": "pkg-001",
        }
        a = build_observability_event(
            **base,
            handoff_observability=_handoff_context(handoff_type="TYPE_A"),
        )
        b = build_observability_event(
            **base,
            handoff_observability=_handoff_context(handoff_type="TYPE_B"),
        )
        self.assertNotEqual(
            compute_observability_event_fingerprint(a),
            compute_observability_event_fingerprint(b),
        )

    def test_changed_target_role_different_fingerprint(self) -> None:
        base = {
            "event_id": "evt-fp-ho-3",
            "run_id": "run-001",
            "agent_code": "GENERIC_AGENT",
            "occurred_at": FIXED_AT,
            "event_type": EventType.HANDOFF_CREATED,
            "status": EventStatus.OK,
            "title": "Handoff created",
            "handoff_id": "handoff-001",
            "artifact_type": "package",
            "artifact_id": "pkg-001",
        }
        a = build_observability_event(
            **base,
            handoff_observability=_handoff_context(target_role_code="ROLE_A"),
        )
        b = build_observability_event(
            **base,
            handoff_observability=_handoff_context(target_role_code="ROLE_B"),
        )
        self.assertNotEqual(
            compute_observability_event_fingerprint(a),
            compute_observability_event_fingerprint(b),
        )


class HandoffViewReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryObservabilityStore()
        self.store.create_run(_run())
        self.port = AgentControlRoomQueryPort(self.store)

    def test_structured_handoff_view(self) -> None:
        _append(
            self.store,
            event_id="ho-create",
            event_type=EventType.HANDOFF_CREATED,
            family=EventFamily.HANDOFF,
            stage_id="HANDOFF_PREPARATION",
            handoff_id="handoff-001",
            artifact_type="package",
            artifact_id="pkg-001",
            title="Handoff created",
            handoff_observability=_handoff_context(),
        )
        _append(
            self.store,
            event_id="ho-persist",
            event_type=EventType.HANDOFF_PERSISTED,
            family=EventFamily.HANDOFF,
            stage_id="HANDOFF_PERSISTENCE",
            handoff_id="handoff-001",
            title="Handoff persisted",
            occurred_at=LATER_AT,
        )
        view = self.port.get_run_snapshot("run-001").handoff
        self.assertEqual(view.handoff_id, "handoff-001")
        self.assertEqual(view.status, HandoffStatus.PERSISTED)
        self.assertEqual(view.handoff_type, "CONSTRUCTOR_TO_ADMISSION")
        self.assertEqual(view.target_role_code, "MONTHLY_PLAN_ADMISSION_AGENT")
        self.assertEqual(view.artifact_type, "package")
        self.assertEqual(view.artifact_id, "pkg-001")
        self.assertEqual(view.created_at, FIXED_AT)
        self.assertEqual(view.persisted_at, LATER_AT)
        self.assertIsNone(view.failed_at)
        self.assertEqual(view.derivation_state, DerivationState.OK)
        self.assertNotIn("receiver_observed", view.__dict__)
        self.assertNotIn("target_run_id", view.__dict__)

    def test_legacy_event_incomplete_not_fabricated(self) -> None:
        _append(
            self.store,
            event_id="ho-legacy",
            event_type=EventType.HANDOFF_CREATED,
            family=EventFamily.HANDOFF,
            stage_id="HANDOFF_PREPARATION",
            handoff_id="handoff-legacy",
            title="Legacy handoff",
            detail={
                "handoff_type": "FAKE_TYPE",
                "target_role": "FAKE_ROLE",
                "source_agent": "FAKE_AGENT",
            },
            allow_legacy_missing_handoff_subcontract=True,
        )
        view = self.port.get_run_snapshot("run-001").handoff
        self.assertEqual(view.derivation_state, DerivationState.INCOMPLETE)
        self.assertIsNone(view.handoff_type)
        self.assertIsNone(view.target_role_code)
        self.assertNotIn("source_agent", view.__dict__)

    def test_source_agent_remains_envelope_truth(self) -> None:
        _append(
            self.store,
            event_id="ho-src",
            event_type=EventType.HANDOFF_CREATED,
            family=EventFamily.HANDOFF,
            stage_id="HANDOFF_PREPARATION",
            handoff_id="handoff-001",
            artifact_type="package",
            artifact_id="pkg-001",
            title="Handoff created",
            handoff_observability=_handoff_context(),
        )
        events = self.store.list_events("run-001")
        created = next(e for e in events if e.event_type is EventType.HANDOFF_CREATED)
        self.assertEqual(created.agent_code, "GENERIC_AGENT")
        view = self.port.get_run_snapshot("run-001").handoff
        self.assertNotIn("source_agent_code", view.__dict__)


class LegacyStoreDeserializeTests(unittest.TestCase):
    def test_legacy_stored_event_deserializes(self) -> None:
        legacy_payload = {
            "schema_version": "observability_event.v0.1",
            "event_id": "evt-store-legacy-ho",
            "run_id": "run-001",
            "agent_code": "GENERIC_AGENT",
            "occurred_at": FIXED_AT.isoformat(),
            "family": EventFamily.HANDOFF.value,
            "event_type": EventType.HANDOFF_CREATED.value,
            "status": EventStatus.OK.value,
            "title": "Stored legacy handoff",
            "handoff_id": "handoff-legacy",
            "attempt_n": 1,
            "resume_n": 0,
            "detail": {},
        }
        event = _observability_event_from_dict(legacy_payload)
        self.assertIsNone(event.handoff_observability)
        self.assertIsNone(event.to_dict()["handoff_observability"])


class StoreReplayTests(unittest.TestCase):
    def test_same_event_id_structured_replay_is_idempotent(self) -> None:
        store = InMemoryObservabilityStore()
        store.create_run(_run())
        event = build_observability_event(
            event_id="evt-replay-ho",
            run_id="run-001",
            agent_code="GENERIC_AGENT",
            occurred_at=FIXED_AT,
            event_type=EventType.HANDOFF_CREATED,
            status=EventStatus.OK,
            title="Handoff created",
            handoff_id="handoff-001",
            artifact_type="package",
            artifact_id="pkg-001",
            handoff_observability=_handoff_context(),
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

    def test_roundtrip_preserves_subcontract(self) -> None:
        event = build_observability_event(
            event_id="evt-rt-ho",
            run_id="run-001",
            agent_code="GENERIC_AGENT",
            occurred_at=FIXED_AT,
            event_type=EventType.HANDOFF_CREATED,
            status=EventStatus.OK,
            title="Handoff created",
            handoff_id="handoff-001",
            artifact_type="package",
            artifact_id="pkg-001",
            handoff_observability=_handoff_context(),
        )
        restored = _observability_event_from_dict(event.to_dict())
        self.assertEqual(restored.handoff_observability, event.handoff_observability)


class SecretScanTests(unittest.TestCase):
    def test_secret_scan_rejects_handoff_fields(self) -> None:
        sentinel = "EOSSECHANDOFFLEAK01"
        old = os.environ.get("SUPABASE_KEY")
        os.environ["SUPABASE_KEY"] = sentinel
        try:
            with self.assertRaises(ObservabilityContractError):
                build_handoff_observability_context(
                    handoff_type=sentinel,
                    target_role_code="MONTHLY_PLAN_ADMISSION_AGENT",
                )
        finally:
            if old is None:
                os.environ.pop("SUPABASE_KEY", None)
            else:
                os.environ["SUPABASE_KEY"] = old


if __name__ == "__main__":
    unittest.main()
