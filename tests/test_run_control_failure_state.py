"""
Increment 10.2 — Run Control failure state, concurrency, and security tests.
"""

from __future__ import annotations

import ast
import threading
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

from agents.observability.contracts import EventType, InitiatorType, TriggerType, compute_run_request_digest
from agents.observability.recorder import InMemoryObservabilityRecorder
from agents.run_control.contracts import (
    CODE_CONTROL_PLANE_FAILURE,
    CODE_IDEMPOTENCY_IN_PROGRESS,
    CODE_LAUNCH_OUTCOME_UNKNOWN,
    CODE_SYSTEM_EVENT_DIRECT_START_FORBIDDEN,
    ManagedRunStartInput,
    ReservationState,
    RunControlError,
    StartOutcome,
    TerminalFailureKind,
)
from agents.run_control.registry import InMemoryRunControlRegistry
from agents.run_control.service import RunControlService
from security.agent_execution_context import AgentExecutionContext, ContextIssueError

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


def _digest_for_input(start_input: ManagedRunStartInput) -> str:
    return compute_run_request_digest(
        agent_code=start_input.agent_code,
        initiator_type=start_input.initiator_type,
        initiator_id=start_input.initiator_id,
        project_code=start_input.project_code,
        month_key=start_input.month_key,
        scope_request=dict(start_input.scope_request or {}),
        requested_mission_id=start_input.requested_mission_id,
        orchestration_run_id=start_input.orchestration_run_id,
        predecessor_run_id=start_input.predecessor_run_id,
        trigger_type=start_input.trigger_type,
    )


@dataclass
class _LaunchCall:
    run_id: str
    authorization_id: str
    context_type: str


@dataclass
class FakeLauncher:
    calls: list[_LaunchCall] = field(default_factory=list)
    fail: bool = False
    gate: threading.Event | None = None
    release: threading.Event | None = None

    def launch(self, *, run_request, agent_run, context) -> None:
        if self.gate is not None:
            self.gate.set()
        if self.release is not None:
            self.release.wait(timeout=5)
        if self.fail:
            raise RuntimeError("launcher-fail")
        self.calls.append(
            _LaunchCall(
                run_id=agent_run.run_id,
                authorization_id=context.authorization_id,
                context_type=type(context).__name__,
            )
        )


class EventFailRecorder(InMemoryObservabilityRecorder):
    def __init__(self, fail_on: EventType) -> None:
        super().__init__()
        self.fail_on = fail_on

    def record_event(self, event):
        if event.event_type is self.fail_on:
            raise RuntimeError(f"recorder-down-on-{event.event_type.value}")
        return super().record_event(event)


class RunControlConcurrentTests(unittest.TestCase):
    def test_01_concurrent_service_start_single_auth_and_launch(self) -> None:
        registry = InMemoryRunControlRegistry()
        recorder = InMemoryObservabilityRecorder()
        launcher = FakeLauncher()
        service = RunControlService(registry=registry, recorder=recorder)
        issuer_calls = 0
        barrier = threading.Barrier(2)
        results: list[Any] = []
        errors: list[Exception] = []

        def counting_issue_context(**kwargs):
            nonlocal issuer_calls
            issuer_calls += 1
            from security.agent_execution_context import issue_read_only_agent_context

            return issue_read_only_agent_context(**kwargs)

        def worker() -> None:
            try:
                barrier.wait(timeout=2)
                with patch(
                    "agents.run_control.service.issue_read_only_agent_context",
                    side_effect=counting_issue_context,
                ):
                    results.append(
                        service.start(
                            _start_input(idempotency_key="idem-concurrent"),
                            launcher=launcher,
                            requested_at=FIXED_AT,
                        )
                    )
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        self.assertEqual(issuer_calls, 1)
        self.assertLessEqual(len(launcher.calls), 1)
        self.assertEqual(len(results) + len(errors), 2)
        run_ids = {item.agent_run.run_id for item in results}
        for exc in errors:
            if isinstance(exc, RunControlError):
                self.assertEqual(exc.code, CODE_IDEMPOTENCY_IN_PROGRESS)
        if run_ids:
            events = recorder.events_for_run(next(iter(run_ids)))
            self.assertEqual(len([e for e in events if e.event_type is EventType.RUN_REQUESTED]), 1)


class RunControlClassAFailureTests(unittest.TestCase):
    def _assert_control_plane_replay(
        self,
        *,
        fail_on: EventType,
        idempotency_key: str,
        denial: bool = False,
    ) -> None:
        registry = InMemoryRunControlRegistry()
        recorder = EventFailRecorder(fail_on)
        launcher = FakeLauncher()
        service = RunControlService(registry=registry, recorder=recorder)
        agent_code = "UNKNOWN_AGENT_X" if denial else "MONTHLY_PLAN_CONSTRUCTOR"
        start = _start_input(idempotency_key=idempotency_key, agent_code=agent_code)
        digest = _digest_for_input(start)

        def issuer(**kwargs):
            if denial:
                raise ContextIssueError("UNKNOWN_AGENT", "denied")
            from security.agent_execution_context import issue_read_only_agent_context

            return issue_read_only_agent_context(**kwargs)

        with patch("agents.run_control.service.issue_read_only_agent_context", side_effect=issuer):
            with self.assertRaises(RunControlError) as first_ctx:
                service.start(start, launcher=launcher, requested_at=FIXED_AT)
        self.assertEqual(first_ctx.exception.code, CODE_CONTROL_PLANE_FAILURE)
        self.assertEqual(registry.reservation_state(idempotency_key=idempotency_key), ReservationState.TERMINAL_FAILURE)
        failure = registry.get_terminal_failure(idempotency_key=idempotency_key, canonical_request_digest=digest)
        self.assertIsNotNone(failure)
        assert failure is not None
        self.assertEqual(failure.failure_kind, TerminalFailureKind.CONTROL_PLANE_FAILURE)

        launcher.calls.clear()
        with patch(
            "agents.run_control.service.issue_read_only_agent_context",
            side_effect=AssertionError("should not reauthorize"),
        ):
            with self.assertRaises(RunControlError) as replay_ctx:
                service.start(start, launcher=launcher, requested_at=FIXED_AT)
        self.assertEqual(replay_ctx.exception.code, CODE_CONTROL_PLANE_FAILURE)
        self.assertEqual(replay_ctx.exception.args[0], first_ctx.exception.args[0])
        self.assertEqual(len(launcher.calls), 0)

    def test_02_fail_on_run_requested(self) -> None:
        self._assert_control_plane_replay(
            fail_on=EventType.RUN_REQUESTED,
            idempotency_key="idem-fail-run-requested",
        )

    def test_03_fail_on_run_authorization_started(self) -> None:
        self._assert_control_plane_replay(
            fail_on=EventType.RUN_AUTHORIZATION_STARTED,
            idempotency_key="idem-fail-auth-started",
        )

    def test_04_fail_on_run_authorized(self) -> None:
        self._assert_control_plane_replay(
            fail_on=EventType.RUN_AUTHORIZED,
            idempotency_key="idem-fail-authorized",
        )

    def test_05_fail_on_mission_bound(self) -> None:
        self._assert_control_plane_replay(
            fail_on=EventType.MISSION_BOUND,
            idempotency_key="idem-fail-mission-bound",
        )

    def test_06_fail_on_run_started(self) -> None:
        self._assert_control_plane_replay(
            fail_on=EventType.RUN_STARTED,
            idempotency_key="idem-fail-run-started",
        )

    def test_07_denial_path_fail_on_run_denied(self) -> None:
        self._assert_control_plane_replay(
            fail_on=EventType.RUN_DENIED,
            idempotency_key="idem-fail-run-denied",
            denial=True,
        )


class RunControlLaunchUnknownTests(unittest.TestCase):
    def test_08_launch_unknown_terminal_and_replay(self) -> None:
        registry = InMemoryRunControlRegistry()
        recorder = InMemoryObservabilityRecorder()
        launcher = FakeLauncher(fail=True)
        service = RunControlService(registry=registry, recorder=recorder)
        idem = "idem-launch-unknown"
        start = _start_input(idempotency_key=idem)
        digest = _digest_for_input(start)

        with self.assertRaises(RunControlError) as first_ctx:
            service.start(start, launcher=launcher, requested_at=FIXED_AT)
        self.assertEqual(first_ctx.exception.code, CODE_LAUNCH_OUTCOME_UNKNOWN)
        self.assertEqual(registry.reservation_state(idempotency_key=idem), ReservationState.TERMINAL_FAILURE)

        failure = registry.get_terminal_failure(idempotency_key=idem, canonical_request_digest=digest)
        self.assertIsNotNone(failure)
        assert failure is not None
        self.assertEqual(failure.failure_kind, TerminalFailureKind.LAUNCH_OUTCOME_UNKNOWN)
        request_id = failure.request_id
        run_id = failure.run_id

        with patch(
            "agents.run_control.service.issue_read_only_agent_context",
            side_effect=AssertionError("should not reauthorize"),
        ):
            with self.assertRaises(RunControlError) as replay_ctx:
                service.start(start, launcher=launcher, requested_at=FIXED_AT)
        self.assertEqual(replay_ctx.exception.code, CODE_LAUNCH_OUTCOME_UNKNOWN)
        self.assertEqual(failure.request_id, request_id)
        self.assertEqual(failure.run_id, run_id)
        self.assertEqual(len(launcher.calls), 0)
        self.assertEqual(len(recorder.events_for_run(run_id)), 5)


class RunControlInProgressTests(unittest.TestCase):
    def test_09_in_progress_during_launcher_then_cached_replay(self) -> None:
        registry = InMemoryRunControlRegistry()
        recorder = InMemoryObservabilityRecorder()
        gate = threading.Event()
        release = threading.Event()
        launcher = FakeLauncher(gate=gate, release=release)
        service = RunControlService(registry=registry, recorder=recorder)
        idem = "idem-in-progress-launcher"
        results: list[Any] = []

        def first_start() -> None:
            results.append(
                service.start(_start_input(idempotency_key=idem), launcher=launcher, requested_at=FIXED_AT)
            )

        t1 = threading.Thread(target=first_start)
        t1.start()
        self.assertTrue(gate.wait(timeout=5))
        with self.assertRaises(RunControlError) as in_progress:
            service.start(_start_input(idempotency_key=idem), launcher=launcher, requested_at=FIXED_AT)
        self.assertEqual(in_progress.exception.code, CODE_IDEMPOTENCY_IN_PROGRESS)
        release.set()
        t1.join(timeout=5)
        self.assertEqual(len(results), 1)
        replay = service.start(_start_input(idempotency_key=idem), launcher=launcher, requested_at=FIXED_AT)
        self.assertEqual(replay.outcome, StartOutcome.IDEMPOTENT_REPLAY)


class RunControlSystemEventTests(unittest.TestCase):
    def test_10_system_event_rejected_for_arbitrary_agents(self) -> None:
        launcher = FakeLauncher()
        service = RunControlService(
            registry=InMemoryRunControlRegistry(),
            recorder=InMemoryObservabilityRecorder(),
        )
        for agent_code in ("MONTHLY_PLAN_CONSTRUCTOR", "FUTURE_AGENT_X"):
            with self.subTest(agent_code=agent_code):
                with patch(
                    "agents.run_control.service.issue_read_only_agent_context",
                    side_effect=AssertionError("should not authorize"),
                ):
                    with self.assertRaises(RunControlError) as ctx:
                        service.start(
                            _start_input(agent_code=agent_code, trigger_type=TriggerType.SYSTEM_EVENT),
                            launcher=launcher,
                            requested_at=FIXED_AT,
                        )
                self.assertEqual(ctx.exception.code, CODE_SYSTEM_EVENT_DIRECT_START_FORBIDDEN)
        self.assertEqual(len(launcher.calls), 0)


class RunControlSecurityContextTests(unittest.TestCase):
    def test_11_launcher_receives_context_registry_does_not_cache_it(self) -> None:
        registry = InMemoryRunControlRegistry()
        recorder = InMemoryObservabilityRecorder()
        launcher = FakeLauncher()
        service = RunControlService(registry=registry, recorder=recorder)
        result = service.start(_start_input(idempotency_key="idem-sec-ctx"), launcher=launcher, requested_at=FIXED_AT)

        self.assertEqual(len(launcher.calls), 1)
        self.assertEqual(launcher.calls[0].context_type, AgentExecutionContext.__name__)
        self.assertIsNotNone(result.authorization_id)

        entry = registry._by_key["idem-sec-ctx"]  # noqa: SLF001 test inspection
        self.assertIsNotNone(entry.result)
        assert entry.result is not None
        self.assertIsNotNone(entry.result.authorization_id)
        self.assertNotIn("execution_context", entry.result.__dataclass_fields__)

        replay = service.start(_start_input(idempotency_key="idem-sec-ctx"), launcher=launcher, requested_at=FIXED_AT)
        self.assertEqual(replay.outcome, StartOutcome.IDEMPOTENT_REPLAY)
        self.assertEqual(replay.authorization_id, result.authorization_id)
        self.assertEqual(len(launcher.calls), 1)


class RunControlArchitectureTests(unittest.TestCase):
    def test_12_production_package_has_no_constructor_dependency(self) -> None:
        forbidden_tokens = (
            "monthly_plan_constructor",
            "mission_scope",
            "langgraph",
            "streamlit",
            "supabase",
        )
        run_control_dir = REPO / "agents" / "run_control"
        for path in run_control_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        for token in forbidden_tokens:
                            self.assertNotIn(token, alias.name.lower(), f"{path.name}: {alias.name}")
                if isinstance(node, ast.ImportFrom) and node.module:
                    for token in forbidden_tokens:
                        self.assertNotIn(token, node.module.lower(), f"{path.name}: {node.module}")
            lowered = text.lower()
            self.assertNotIn("agent_code_monthly_plan_constructor", lowered, path.name)
            self.assertNotIn('agent_code == "monthly_plan_constructor"', lowered)


if __name__ == "__main__":
    unittest.main()
