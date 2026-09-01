"""
Increment 10.2 — RunControlRegistry tests.
"""

from __future__ import annotations

import threading
import unittest

from agents.run_control.contracts import (
    CODE_IDEMPOTENCY_CONFLICT,
    CODE_IDEMPOTENCY_IN_PROGRESS,
    ManagedRunStartResult,
    ReservationKind,
    ReservationState,
    RunControlError,
    StartOutcome,
    TerminalFailureKind,
    TerminalFailureRecord,
)
from agents.run_control.registry import InMemoryRunControlRegistry
from agents.observability.contracts import InitiatorType, OperationalStatus, TriggerType, build_agent_run, build_run_request
from datetime import datetime, timezone

FIXED_AT = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)


def _sample_result(request_id: str = "req-001", run_id: str = "run-001") -> ManagedRunStartResult:
    run_request = build_run_request(
        request_id=request_id,
        requested_at=FIXED_AT,
        agent_code="MONTHLY_PLAN_CONSTRUCTOR",
        initiator_type=InitiatorType.HUMAN,
        initiator_id="operator-local",
        trigger_type=TriggerType.MANUAL,
        trigger_reason="manual-start",
        project_code="PRJ_001",
        month_key="2026-09",
        requested_mission_id="mission-001",
        idempotency_key="idem-001",
    )
    agent_run = build_agent_run(
        run_id=run_id,
        request_id=request_id,
        agent_code="MONTHLY_PLAN_CONSTRUCTOR",
        agent_version="0.1",
        mission_id="mission-001",
        project_code="PRJ_001",
        month_key="2026-09",
        initiator_type=InitiatorType.HUMAN,
        initiator_id="operator-local",
        trigger_type=TriggerType.MANUAL,
        trigger_reason="manual-start",
        operational_status=OperationalStatus.RUNNING,
        requested_at=FIXED_AT,
        updated_at=FIXED_AT,
        thread_id=run_id,
    )
    return ManagedRunStartResult(
        outcome=StartOutcome.AUTHORIZED,
        run_request=run_request,
        agent_run=agent_run,
    )


class InMemoryRunControlRegistryTests(unittest.TestCase):
    def test_01_new_reservation_uses_candidate_ids(self) -> None:
        reg = InMemoryRunControlRegistry()
        decision = reg.decide_reservation(
            idempotency_key="idem-a",
            canonical_request_digest="digest-a",
            candidate_request_id="req-a",
            candidate_run_id="run-a",
        )
        self.assertEqual(decision.kind, ReservationKind.NEW)
        self.assertEqual(decision.request_id, "req-a")
        self.assertEqual(decision.run_id, "run-a")

    def test_02_same_key_same_digest_replay_after_store(self) -> None:
        reg = InMemoryRunControlRegistry()
        reg.decide_reservation(
            idempotency_key="idem-a",
            canonical_request_digest="digest-a",
            candidate_request_id="req-a",
            candidate_run_id="run-a",
        )
        result = _sample_result("req-a", "run-a")
        reg.store_result(
            idempotency_key="idem-a",
            canonical_request_digest="digest-a",
            result=result,
        )
        decision = reg.decide_reservation(
            idempotency_key="idem-a",
            canonical_request_digest="digest-a",
            candidate_request_id="req-b",
            candidate_run_id="run-b",
        )
        self.assertEqual(decision.kind, ReservationKind.IDEMPOTENT_REPLAY)
        self.assertEqual(decision.request_id, "req-a")
        self.assertEqual(decision.run_id, "run-a")
        cached = reg.get_cached_result(
            idempotency_key="idem-a",
            canonical_request_digest="digest-a",
        )
        self.assertIs(cached, result)

    def test_03_same_key_different_digest_conflict(self) -> None:
        reg = InMemoryRunControlRegistry()
        reg.decide_reservation(
            idempotency_key="idem-a",
            canonical_request_digest="digest-a",
            candidate_request_id="req-a",
            candidate_run_id="run-a",
        )
        with self.assertRaises(RunControlError) as ctx:
            reg.decide_reservation(
                idempotency_key="idem-a",
                canonical_request_digest="digest-b",
                candidate_request_id="req-b",
                candidate_run_id="run-b",
            )
        self.assertEqual(ctx.exception.code, CODE_IDEMPOTENCY_CONFLICT)

    def test_04_in_progress_without_result_fails_closed(self) -> None:
        reg = InMemoryRunControlRegistry()
        reg.decide_reservation(
            idempotency_key="idem-a",
            canonical_request_digest="digest-a",
            candidate_request_id="req-a",
            candidate_run_id="run-a",
        )
        with self.assertRaises(RunControlError) as ctx:
            reg.decide_reservation(
                idempotency_key="idem-a",
                canonical_request_digest="digest-a",
                candidate_request_id="req-b",
                candidate_run_id="run-b",
            )
        self.assertEqual(ctx.exception.code, CODE_IDEMPOTENCY_IN_PROGRESS)

    def test_05_terminal_failure_replay_kind(self) -> None:
        reg = InMemoryRunControlRegistry()
        reg.decide_reservation(
            idempotency_key="idem-a",
            canonical_request_digest="digest-a",
            candidate_request_id="req-a",
            candidate_run_id="run-a",
        )
        reg.store_terminal_failure(
            idempotency_key="idem-a",
            canonical_request_digest="digest-a",
            failure=TerminalFailureRecord(
                failure_kind=TerminalFailureKind.CONTROL_PLANE_FAILURE,
                error_code="CONTROL_PLANE_FAILURE",
                request_id="req-a",
                run_id="run-a",
            ),
        )
        decision = reg.decide_reservation(
            idempotency_key="idem-a",
            canonical_request_digest="digest-a",
            candidate_request_id="req-b",
            candidate_run_id="run-b",
        )
        self.assertEqual(decision.kind, ReservationKind.TERMINAL_FAILURE_REPLAY)
        self.assertEqual(reg.reservation_state(idempotency_key="idem-a"), ReservationState.TERMINAL_FAILURE)

    def test_06_thread_safe_reservation(self) -> None:
        reg = InMemoryRunControlRegistry()
        errors: list[Exception] = []
        barrier = threading.Barrier(2)

        def worker(candidate: str) -> None:
            try:
                barrier.wait(timeout=2)
                reg.decide_reservation(
                    idempotency_key="idem-thread",
                    canonical_request_digest="digest-thread",
                    candidate_request_id=f"req-{candidate}",
                    candidate_run_id=f"run-{candidate}",
                )
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=worker, args=("a",))
        t2 = threading.Thread(target=worker, args=("b",))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)
        self.assertEqual(reg.reservation_count(), 1)
        self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()
