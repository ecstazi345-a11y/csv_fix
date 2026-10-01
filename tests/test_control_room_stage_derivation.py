"""
Control Room stage derivation — append-order + terminal-status laws.

Presentation/derivation only. No runtime emission changes. No store changes.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from agents.control_room.derivations import (
    derive_professional_execution_path,
    derive_stage_view,
)
from agents.control_room.dtos import (
    DerivationState,
    ProfessionalExecutionState,
    StageDisplayState,
)
from agents.observability.contracts import (
    EventStatus,
    EventType,
    InitiatorType,
    OperationalStatus,
    TriggerType,
    build_agent_run,
    build_human_decision_request_observability_context,
    build_observability_event,
)

FIXED_AT = datetime(2026, 10, 1, 10, 44, 22, 521716, tzinfo=timezone.utc)
REPO = Path(__file__).resolve().parents[1]
REAL_OBS = REPO / ".runtime" / "constructor_first_run" / "observability.sqlite"
REAL_RUN_ID = "run-18a75e52-00d7-4e79-8e6b-ee03b7c14f1e"


def _event(
    *,
    event_id: str,
    event_type: EventType,
    stage_id: str | None = None,
    node_name: str | None = None,
    artifact_id: str | None = None,
    attempt_n: int = 1,
    resume_n: int = 0,
    occurred_at: datetime = FIXED_AT,
) -> object:
    kwargs: dict = {
        "event_id": event_id,
        "run_id": "run-stage-derivation",
        "agent_code": "MONTHLY_PLAN_CONSTRUCTOR",
        "occurred_at": occurred_at,
        "event_type": event_type,
        "status": EventStatus.OK,
        "title": event_type.value,
        "stage_id": stage_id,
        "node_name": node_name,
        "artifact_id": artifact_id,
        "artifact_type": "SNAPSHOT" if artifact_id else None,
        "attempt_n": attempt_n,
        "resume_n": resume_n,
        "request_id": "req-1",
        "mission_id": "mission-1",
    }
    if event_type is EventType.HUMAN_WAIT_STARTED:
        kwargs["interrupt_id"] = "intr-1"
        kwargs["human_decision_request"] = build_human_decision_request_observability_context(
            reason_code="AMBIGUOUS_SCOPE",
            allowed_decisions=("CLARIFY_SCOPE", "ABORT_RUN"),
        )
    return build_observability_event(**kwargs)


def _run(status: OperationalStatus) -> object:
    return build_agent_run(
        run_id="run-stage-derivation",
        request_id="req-1",
        agent_code="MONTHLY_PLAN_CONSTRUCTOR",
        agent_version="0.1",
        mission_id="mission-1",
        project_code="PRJ_001_БХК",
        month_key="октябрь-2026",
        initiator_type=InitiatorType.HUMAN,
        initiator_id="operator",
        trigger_type=TriggerType.MANUAL,
        trigger_reason="stage-derivation-test",
        operational_status=status,
        requested_at=FIXED_AT,
        updated_at=FIXED_AT,
        thread_id="run-stage-derivation",
        attempt_n=1,
        resume_n=0,
        projection_version=1,
        started_at=FIXED_AT if status is not OperationalStatus.REQUESTED else None,
        completed_at=FIXED_AT
        if status
        in {
            OperationalStatus.COMPLETED,
            OperationalStatus.FAILED,
            OperationalStatus.ABORTED,
        }
        else None,
    )


class ControlRoomStageDerivationTests(unittest.TestCase):
    def test_case1_same_timestamps_completed_not_running(self) -> None:
        events = (
            _event(
                event_id="e1",
                event_type=EventType.STAGE_STARTED,
                stage_id="REALITY_READ",
                node_name="load_reality",
                artifact_id=None,
            ),
            _event(
                event_id="e2",
                event_type=EventType.STAGE_COMPLETED,
                stage_id="REALITY_READ",
                node_name="load_reality",
                artifact_id="snap-1",
            ),
            _event(
                event_id="e3",
                event_type=EventType.STAGE_STARTED,
                stage_id="CANDIDATE_ASSEMBLY",
                node_name="build_package",
                artifact_id="snap-1",
            ),
            _event(
                event_id="e4",
                event_type=EventType.STAGE_COMPLETED,
                stage_id="CANDIDATE_ASSEMBLY",
                node_name="build_package",
                artifact_id="snap-1",
            ),
            _event(event_id="e5", event_type=EventType.RUN_COMPLETED, stage_id=None),
        )
        view = derive_stage_view(
            events,
            events_complete=True,
            operational_status=OperationalStatus.COMPLETED,
        )
        self.assertIs(view.derivation_state, DerivationState.OK)
        self.assertIsNone(view.current_stage)
        self.assertEqual(len(view.occurrences), 2)
        self.assertIs(view.occurrences[0].display_state, StageDisplayState.COMPLETED)
        self.assertEqual(view.occurrences[0].artifact_id, "snap-1")
        self.assertIs(view.occurrences[1].display_state, StageDisplayState.COMPLETED)

        path = derive_professional_execution_path(
            _run(OperationalStatus.COMPLETED),  # type: ignore[arg-type]
            events,
            events_complete=True,
        )
        self.assertIs(path.derivation_state, DerivationState.OK)
        stage_steps = [s for s in path.steps if s.stage_id == "REALITY_READ"]
        self.assertTrue(stage_steps)
        self.assertIs(stage_steps[0].professional_state, ProfessionalExecutionState.COMPLETED)

    def test_case2_identical_timestamps_append_order(self) -> None:
        events = (
            _event(
                event_id="a",
                event_type=EventType.STAGE_STARTED,
                stage_id="S1",
                node_name="n1",
            ),
            _event(
                event_id="b",
                event_type=EventType.STAGE_COMPLETED,
                stage_id="S1",
                node_name="n1",
                artifact_id="art",
            ),
            _event(
                event_id="c",
                event_type=EventType.STAGE_STARTED,
                stage_id="S2",
                node_name="n2",
                artifact_id="art",
            ),
            _event(
                event_id="d",
                event_type=EventType.STAGE_COMPLETED,
                stage_id="S2",
                node_name="n2",
                artifact_id="art",
            ),
        )
        view = derive_stage_view(events, events_complete=True)
        self.assertEqual([o.stage_id for o in view.occurrences], ["S1", "S2"])
        self.assertIs(view.derivation_state, DerivationState.OK)

    def test_case3_active_running_still_shown(self) -> None:
        events = (
            _event(
                event_id="a",
                event_type=EventType.STAGE_STARTED,
                stage_id="REALITY_READ",
                node_name="load_reality",
            ),
            _event(
                event_id="b",
                event_type=EventType.STAGE_COMPLETED,
                stage_id="REALITY_READ",
                node_name="load_reality",
                artifact_id="snap",
            ),
            _event(
                event_id="c",
                event_type=EventType.STAGE_STARTED,
                stage_id="CANDIDATE_ASSEMBLY",
                node_name="build_package",
                artifact_id="snap",
            ),
            _event(event_id="d", event_type=EventType.RUN_ADVANCING),
        )
        view = derive_stage_view(
            events,
            events_complete=True,
            operational_status=OperationalStatus.RUNNING,
        )
        self.assertIsNotNone(view.current_stage)
        assert view.current_stage is not None
        self.assertEqual(view.current_stage.stage_id, "CANDIDATE_ASSEMBLY")
        self.assertIs(view.current_stage.display_state, StageDisplayState.RUNNING)
        self.assertIs(view.derivation_state, DerivationState.OK)

    def test_case4_waiting_for_human_not_masked(self) -> None:
        events = (
            _event(
                event_id="a",
                event_type=EventType.STAGE_STARTED,
                stage_id="CANDIDATE_ASSEMBLY",
                node_name="build_package",
            ),
            _event(
                event_id="b",
                event_type=EventType.HUMAN_WAIT_STARTED,
                stage_id="CANDIDATE_ASSEMBLY",
                node_name="build_package",
                resume_n=1,
            ),
        )
        view = derive_stage_view(
            events,
            events_complete=True,
            operational_status=OperationalStatus.WAITING_FOR_HUMAN,
        )
        self.assertIsNotNone(view.current_stage)
        assert view.current_stage is not None
        self.assertIs(view.current_stage.display_state, StageDisplayState.RUNNING)
        self.assertEqual(view.current_stage.stage_id, "CANDIDATE_ASSEMBLY")

    def test_case5_failed_run_not_active_running(self) -> None:
        events = (
            _event(
                event_id="a",
                event_type=EventType.STAGE_STARTED,
                stage_id="REALITY_READ",
                node_name="load_reality",
            ),
            _event(
                event_id="b",
                event_type=EventType.STAGE_FAILED,
                stage_id="REALITY_READ",
                node_name="load_reality",
            ),
            _event(event_id="c", event_type=EventType.RUN_FAILED),
        )
        view = derive_stage_view(
            events,
            events_complete=True,
            operational_status=OperationalStatus.FAILED,
        )
        self.assertIsNone(view.current_stage)
        self.assertIs(view.occurrences[0].display_state, StageDisplayState.FAILED)

    def test_case6_aborted_run_not_active_running(self) -> None:
        events = (
            _event(
                event_id="a",
                event_type=EventType.STAGE_STARTED,
                stage_id="EXCEPTION_ANALYSIS",
                node_name="evaluate_exceptions",
            ),
            _event(event_id="b", event_type=EventType.RUN_ABORTED),
        )
        view = derive_stage_view(
            events,
            events_complete=True,
            operational_status=OperationalStatus.ABORTED,
        )
        self.assertIsNone(view.current_stage)

    @unittest.skipUnless(REAL_OBS.is_file(), "local first-run observability store missing")
    def test_real_first_run_store_no_false_inconsistent(self) -> None:
        from agents.observability.sqlite_store import SqliteObservabilityStore
        from agents.control_room.query_port import AgentControlRoomQueryPort

        store = SqliteObservabilityStore(REAL_OBS)
        try:
            port = AgentControlRoomQueryPort(store)
            snap = port.get_run_snapshot(REAL_RUN_ID)
        finally:
            store.close()

        self.assertEqual(str(snap.run.operational_status), "COMPLETED")
        self.assertIs(snap.stage.derivation_state, DerivationState.OK)
        self.assertIsNone(snap.stage.current_stage)
        self.assertGreaterEqual(len(snap.stage.occurrences), 4)
        self.assertTrue(
            all(o.display_state is not StageDisplayState.RUNNING for o in snap.stage.occurrences)
        )
        self.assertIs(snap.professional_execution_path.derivation_state, DerivationState.OK)


if __name__ == "__main__":
    unittest.main()
