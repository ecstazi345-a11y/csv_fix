"""
Increment 10.2 — Run Control service, events, and security tests.
"""

from __future__ import annotations

import ast
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

from agents.observability.contracts import (
    EventType,
    InitiatorType,
    OperationalStatus,
    TriggerType,
    build_observability_event,
)
from agents.observability.recorder import InMemoryObservabilityRecorder
from agents.run_control.contracts import (
    CODE_CONTROL_PLANE_FAILURE,
    CODE_IDEMPOTENCY_CONFLICT,
    CODE_SYSTEM_EVENT_DIRECT_START_FORBIDDEN,
    ManagedRunStartInput,
    ManagedRuntimeLauncher,
    RunControlError,
    StartOutcome,
)
from agents.run_control.registry import InMemoryRunControlRegistry
from agents.run_control.service import RunControlService
from security.agent_execution_context import ContextIssueError

FIXED_AT = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
REPO = __import__("pathlib").Path(__file__).resolve().parents[1]


def _start_input(**overrides: Any) -> ManagedRunStartInput:
    payload = dict(
        agent_code="MONTHLY_PLAN_CONSTRUCTOR",
        initiator_type=InitiatorType.HUMAN,
        initiator_id="operator-local",
        trigger_type=TriggerType.MANUAL,
        trigger_reason="manual-start",
        project_code="PRJ_001_БХК",
        month_key="2026-09",
        requested_mission_id="mission-001",
        idempotency_key="idem-human-001",
        scope_request={"facility": "A"},
        metadata={"ui": "control-room"},
    )
    payload.update(overrides)
    return ManagedRunStartInput(**payload)


@dataclass
class _LaunchCall:
    run_id: str
    authorization_id: str


@dataclass
class FakeLauncher:
    calls: list[_LaunchCall] = field(default_factory=list)
    fail: bool = False

    def launch(self, *, run_request, agent_run, context) -> None:
        if self.fail:
            raise RuntimeError("launcher-fail")
        self.calls.append(
            _LaunchCall(run_id=agent_run.run_id, authorization_id=context.authorization_id)
        )


class FailingRecorder(InMemoryObservabilityRecorder):
    def record_event(self, event):
        raise RuntimeError("recorder-down")


class RunControlServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = InMemoryRunControlRegistry()
        self.recorder = InMemoryObservabilityRecorder()
        self.launcher = FakeLauncher()
        self.service = RunControlService(registry=self.registry, recorder=self.recorder)
        self.issuer_calls = 0

    def _start(self, **overrides):
        with patch(
            "agents.run_control.service.issue_read_only_agent_context",
            side_effect=self._issue_context,
        ) as mocked:
            result = self.service.start(
                _start_input(**overrides),
                launcher=self.launcher,
                requested_at=FIXED_AT,
            )
        return result, mocked

    def _issue_context(self, **kwargs):
        self.issuer_calls += 1
        from security.agent_execution_context import issue_read_only_agent_context

        return issue_read_only_agent_context(**kwargs)

    def _events_for_run(self, run_id: str):
        return self.recorder.events_for_run(run_id)

    def test_01_mints_request_and_run_ids(self) -> None:
        result, _ = self._start()
        self.assertTrue(result.run_request.request_id.startswith("req-"))
        self.assertTrue(result.agent_run.run_id.startswith("run-"))

    def test_02_run_request_uses_minted_ids(self) -> None:
        result, _ = self._start()
        self.assertEqual(result.run_request.request_id, result.agent_run.request_id)
        self.assertNotEqual(result.run_request.request_id, result.agent_run.run_id)

    def test_03_thread_id_equals_run_id(self) -> None:
        result, _ = self._start()
        self.assertEqual(result.agent_run.thread_id, result.agent_run.run_id)

    def test_04_authorization_id_on_success(self) -> None:
        result, _ = self._start()
        self.assertIsNotNone(result.authorization_id)
        self.assertEqual(result.authorization_id, self.launcher.calls[0].authorization_id)

    def test_05_authorized_event_order(self) -> None:
        result, _ = self._start()
        types = [event.event_type for event in self._events_for_run(result.agent_run.run_id)]
        self.assertEqual(
            types,
            [
                EventType.RUN_REQUESTED,
                EventType.RUN_AUTHORIZATION_STARTED,
                EventType.RUN_AUTHORIZED,
                EventType.MISSION_BOUND,
                EventType.RUN_STARTED,
            ],
        )

    def test_06_denied_event_order(self) -> None:
        with patch(
            "agents.run_control.service.issue_read_only_agent_context",
            side_effect=ContextIssueError("UNKNOWN_AGENT", "denied"),
        ):
            result = self.service.start(
                _start_input(agent_code="UNKNOWN_AGENT_X"),
                launcher=self.launcher,
                requested_at=FIXED_AT,
            )
        self.assertEqual(result.outcome, StartOutcome.AUTHORIZATION_DENIED)
        types = [event.event_type for event in self._events_for_run(result.agent_run.run_id)]
        self.assertEqual(
            types,
            [
                EventType.RUN_REQUESTED,
                EventType.RUN_AUTHORIZATION_STARTED,
                EventType.RUN_DENIED,
            ],
        )
        self.assertEqual(len(self.launcher.calls), 0)

    def test_07_launcher_called_once_on_success(self) -> None:
        result, _ = self._start()
        self.assertEqual(len(self.launcher.calls), 1)
        self.assertEqual(self.launcher.calls[0].run_id, result.agent_run.run_id)

    def test_08_starting_operational_status_after_launch_acceptance(self) -> None:
        result, _ = self._start()
        self.assertEqual(result.agent_run.operational_status, OperationalStatus.STARTING)

    def test_09_mission_id_preserved(self) -> None:
        result, _ = self._start(requested_mission_id="mission-xyz")
        self.assertEqual(result.agent_run.mission_id, "mission-xyz")
        self.assertEqual(result.run_request.requested_mission_id, "mission-xyz")

    def test_10_idempotent_replay_same_ids(self) -> None:
        first, _ = self._start()
        self.issuer_calls = 0
        self.launcher.calls.clear()
        second, _ = self._start()
        self.assertEqual(second.outcome, StartOutcome.IDEMPOTENT_REPLAY)
        self.assertEqual(second.run_request.request_id, first.run_request.request_id)
        self.assertEqual(second.agent_run.run_id, first.agent_run.run_id)

    def test_11_idempotent_replay_no_second_auth(self) -> None:
        self._start()
        self.issuer_calls = 0
        self._start()
        self.assertEqual(self.issuer_calls, 0)

    def test_12_idempotent_replay_no_second_launcher(self) -> None:
        self._start()
        self.launcher.calls.clear()
        self._start()
        self.assertEqual(len(self.launcher.calls), 0)

    def test_13_idempotent_replay_no_second_run_started(self) -> None:
        first, _ = self._start()
        count_after_first = len(self._events_for_run(first.agent_run.run_id))
        self._start()
        self.assertEqual(len(self._events_for_run(first.agent_run.run_id)), count_after_first)

    def test_14_idempotency_conflict(self) -> None:
        self._start()
        with self.assertRaises(RunControlError) as ctx:
            self._start(scope_request={"facility": "B"})
        self.assertEqual(ctx.exception.code, CODE_IDEMPOTENCY_CONFLICT)

    def test_15_conflict_no_launcher(self) -> None:
        self._start()
        self.launcher.calls.clear()
        with self.assertRaises(RunControlError):
            self._start(scope_request={"facility": "B"})
        self.assertEqual(len(self.launcher.calls), 0)

    def test_16_system_event_constructor_rejected(self) -> None:
        with self.assertRaises(RunControlError) as ctx:
            self.service.start(
                _start_input(trigger_type=TriggerType.SYSTEM_EVENT),
                launcher=self.launcher,
                requested_at=FIXED_AT,
            )
        self.assertEqual(ctx.exception.code, CODE_SYSTEM_EVENT_DIRECT_START_FORBIDDEN)
        self.assertEqual(len(self.launcher.calls), 0)

    def test_17_system_event_no_auth(self) -> None:
        with patch(
            "agents.run_control.service.issue_read_only_agent_context",
            side_effect=AssertionError("should not authorize"),
        ):
            with self.assertRaises(RunControlError):
                self.service.start(
                    _start_input(trigger_type=TriggerType.SYSTEM_EVENT),
                    launcher=self.launcher,
                    requested_at=FIXED_AT,
                )

    def test_18_recorder_failure_before_launcher(self) -> None:
        service = RunControlService(
            registry=InMemoryRunControlRegistry(),
            recorder=FailingRecorder(),
        )
        with self.assertRaises(RunControlError) as ctx:
            service.start(_start_input(), launcher=self.launcher, requested_at=FIXED_AT)
        self.assertEqual(ctx.exception.code, CODE_CONTROL_PLANE_FAILURE)
        self.assertEqual(len(self.launcher.calls), 0)

    def test_19_secret_like_metadata_rejected(self) -> None:
        with self.assertRaises(Exception):
            self.service.start(
                _start_input(metadata={"supabase_secret_key": "leak"}),
                launcher=self.launcher,
                requested_at=FIXED_AT,
            )

    def test_20_denial_replay_does_not_reauthorize(self) -> None:
        with patch(
            "agents.run_control.service.issue_read_only_agent_context",
            side_effect=ContextIssueError("UNKNOWN_AGENT", "denied"),
        ):
            self.service.start(
                _start_input(agent_code="UNKNOWN_AGENT_X", idempotency_key="idem-deny"),
                launcher=self.launcher,
                requested_at=FIXED_AT,
            )
        with patch(
            "agents.run_control.service.issue_read_only_agent_context",
            side_effect=AssertionError("should not reauthorize"),
        ):
            replay = self.service.start(
                _start_input(agent_code="UNKNOWN_AGENT_X", idempotency_key="idem-deny"),
                launcher=self.launcher,
                requested_at=FIXED_AT,
            )
        self.assertEqual(replay.outcome, StartOutcome.IDEMPOTENT_REPLAY)

    def test_21_launcher_failure_propagates(self) -> None:
        self.launcher.fail = True
        with self.assertRaises(RunControlError) as ctx:
            self._start(idempotency_key="idem-launcher-fail")
        self.assertEqual(ctx.exception.code, "LAUNCH_OUTCOME_UNKNOWN")

    def test_22_no_constructor_langgraph_import(self) -> None:
        service_path = REPO / "agents" / "run_control" / "service.py"
        tree = ast.parse(service_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                self.assertNotIn("langgraph", node.module)
                self.assertNotIn("monthly_plan_constructor", node.module)


class RunControlSecurityTests(unittest.TestCase):
    def test_23_events_do_not_persist_full_context(self) -> None:
        registry = InMemoryRunControlRegistry()
        recorder = InMemoryObservabilityRecorder()
        launcher = FakeLauncher()
        service = RunControlService(registry=registry, recorder=recorder)
        result = service.start(_start_input(), launcher=launcher, requested_at=FIXED_AT)
        for event in recorder.events_for_run(result.agent_run.run_id):
            payload = event.to_dict()
            self.assertNotIn("allowed_tools", payload.get("detail", {}))
            dumped = str(payload).lower()
            self.assertNotIn("supabase_secret", dumped)

    def test_24_observability_event_secret_rejected(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        with self.assertRaises(Exception):
            recorder.record_event(
                build_observability_event(
                    event_id="evt-001",
                    run_id="run-001",
                    agent_code="MONTHLY_PLAN_CONSTRUCTOR",
                    occurred_at=FIXED_AT,
                    event_type=EventType.RUN_REQUESTED,
                    status="OK",
                    title="bad",
                    detail={"password": "secret"},
                )
            )


if __name__ == "__main__":
    unittest.main()
