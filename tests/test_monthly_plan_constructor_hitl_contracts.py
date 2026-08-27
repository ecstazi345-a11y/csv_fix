"""
Increment 8 — HITL contract tests.

No Streamlit, Supabase, Postgres connection, LLM, or product writes.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from agents.monthly_plan_constructor.hitl_contracts import (
    DECISION_ABORT_RUN,
    DECISION_CLARIFY_SCOPE,
    HitlContractError,
    ScopeSummary,
    build_human_decision_request,
    build_resume_command,
    coerce_resume_command,
    compute_eos_interrupt_id,
    count_wait_ordinal,
)
from agents.monthly_plan_constructor.lifecycle import LifecycleTransition

FIXED_AT = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)


class TestEosInterruptId(unittest.TestCase):
    def test_deterministic(self) -> None:
        a = compute_eos_interrupt_id(
            run_id="run-1", wait_ordinal=1, reason_code="AMBIGUOUS_SCOPE"
        )
        b = compute_eos_interrupt_id(
            run_id="run-1", wait_ordinal=1, reason_code="AMBIGUOUS_SCOPE"
        )
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("eos-int-"))

    def test_distinct_ordinal(self) -> None:
        a = compute_eos_interrupt_id(
            run_id="run-1", wait_ordinal=1, reason_code="AMBIGUOUS_SCOPE"
        )
        b = compute_eos_interrupt_id(
            run_id="run-1", wait_ordinal=2, reason_code="AMBIGUOUS_SCOPE"
        )
        self.assertNotEqual(a, b)

    def test_wait_ordinal_count(self) -> None:
        transitions = (
            LifecycleTransition("CREATED", "WAITING_FOR_HUMAN", FIXED_AT),
            LifecycleTransition("WAITING_FOR_HUMAN", "APPLYING_HUMAN_DECISION", FIXED_AT),
            LifecycleTransition("APPLYING_HUMAN_DECISION", "REVALIDATING_REALITY", FIXED_AT),
            LifecycleTransition("REVALIDATING_REALITY", "WAITING_FOR_HUMAN", FIXED_AT),
        )
        self.assertEqual(count_wait_ordinal(transitions), 2)


class TestDecisionRequest(unittest.TestCase):
    def test_valid_request(self) -> None:
        req = build_human_decision_request(
            run_id="run-1",
            mission_id="mission-1",
            reason_code="AMBIGUOUS_SCOPE",
            route="WAIT_HUMAN",
            severity="BLOCKING",
            human_readable_reason="ambiguous facility scope",
            wait_ordinal=1,
            current_scope_summary=ScopeSummary(
                project_code="PRJ_001_БХК",
                month_key="сентябрь-2026",
                facility_scope=None,
                discipline_scope=None,
                system_scope=None,
                iwp_scope=None,
                queue_scope=None,
            ),
            created_at=FIXED_AT,
        )
        self.assertEqual(req.allowed_decisions, (DECISION_CLARIFY_SCOPE, DECISION_ABORT_RUN))
        self.assertEqual(
            req.interrupt_id,
            compute_eos_interrupt_id(
                run_id="run-1", wait_ordinal=1, reason_code="AMBIGUOUS_SCOPE"
            ),
        )

    def test_same_pending_wait_same_id(self) -> None:
        kwargs = dict(
            run_id="run-1",
            mission_id="mission-1",
            reason_code="AMBIGUOUS_SCOPE",
            route="WAIT_HUMAN",
            severity="BLOCKING",
            human_readable_reason="ambiguous",
            wait_ordinal=1,
            current_scope_summary=ScopeSummary(
                None, None, None, None, None, None, None
            ),
            created_at=FIXED_AT,
        )
        a = build_human_decision_request(**kwargs)  # type: ignore[arg-type]
        b = build_human_decision_request(**kwargs)  # type: ignore[arg-type]
        self.assertEqual(a.interrupt_id, b.interrupt_id)

    def test_later_wait_distinct_id(self) -> None:
        base = dict(
            run_id="run-1",
            mission_id="mission-1",
            reason_code="AMBIGUOUS_SCOPE",
            route="WAIT_HUMAN",
            severity="BLOCKING",
            human_readable_reason="ambiguous",
            current_scope_summary=ScopeSummary(
                None, None, None, None, None, None, None
            ),
            created_at=FIXED_AT,
        )
        a = build_human_decision_request(wait_ordinal=1, **base)  # type: ignore[arg-type]
        b = build_human_decision_request(wait_ordinal=2, **base)  # type: ignore[arg-type]
        self.assertNotEqual(a.interrupt_id, b.interrupt_id)

    def test_security_denied_not_resumable(self) -> None:
        with self.assertRaises(HitlContractError):
            build_human_decision_request(
                run_id="run-1",
                mission_id="mission-1",
                reason_code="SECURITY_DENIED",
                route="FAIL_RUN",
                severity="BLOCKING",
                human_readable_reason="denied",
                wait_ordinal=1,
                current_scope_summary=ScopeSummary(
                    None, None, None, None, None, None, None
                ),
                created_at=FIXED_AT,
            )


class TestResumeCommand(unittest.TestCase):
    def test_valid_command(self) -> None:
        cmd = build_resume_command(
            decision_id="dec-1",
            interrupt_id="eos-int-abc",
            run_id="run-1",
            mission_id="mission-1",
            decision=DECISION_CLARIFY_SCOPE,
            actor_id="human-1",
            parameters={"facility_scope": ["FACILITY_TARGET"]},
            comment="narrow facility",
            submitted_at=FIXED_AT,
        )
        self.assertEqual(cmd.decision, DECISION_CLARIFY_SCOPE)
        self.assertEqual(cmd.parameters["facility_scope"], ["FACILITY_TARGET"])

    def test_invalid_decision_rejected(self) -> None:
        with self.assertRaises(HitlContractError):
            build_resume_command(
                decision_id="dec-1",
                interrupt_id="eos-int-abc",
                run_id="run-1",
                mission_id="mission-1",
                decision="APPROVE_ALL",
                actor_id="human-1",
                submitted_at=FIXED_AT,
            )

    def test_malformed_id_rejected(self) -> None:
        with self.assertRaises(HitlContractError):
            build_resume_command(
                decision_id="bad id with spaces!",
                interrupt_id="eos-int-abc",
                run_id="run-1",
                mission_id="mission-1",
                decision=DECISION_ABORT_RUN,
                actor_id="human-1",
                submitted_at=FIXED_AT,
            )

    def test_bounded_comment(self) -> None:
        with self.assertRaises(HitlContractError):
            build_resume_command(
                decision_id="dec-1",
                interrupt_id="eos-int-abc",
                run_id="run-1",
                mission_id="mission-1",
                decision=DECISION_ABORT_RUN,
                actor_id="human-1",
                comment="x" * 501,
                submitted_at=FIXED_AT,
            )

    def test_unexpected_parameter_rejected(self) -> None:
        with self.assertRaises(HitlContractError):
            build_resume_command(
                decision_id="dec-1",
                interrupt_id="eos-int-abc",
                run_id="run-1",
                mission_id="mission-1",
                decision=DECISION_CLARIFY_SCOPE,
                actor_id="human-1",
                parameters={"shell_command": "rm -rf"},
                submitted_at=FIXED_AT,
            )

    def test_coerce_mapping(self) -> None:
        cmd = coerce_resume_command(
            {
                "decision_id": "dec-1",
                "interrupt_id": "eos-int-abc",
                "run_id": "run-1",
                "mission_id": "mission-1",
                "decision": DECISION_ABORT_RUN,
                "actor_id": "human-1",
                "submitted_at": FIXED_AT,
            }
        )
        self.assertEqual(cmd.decision, DECISION_ABORT_RUN)

    def test_frozen(self) -> None:
        cmd = build_resume_command(
            decision_id="dec-1",
            interrupt_id="eos-int-abc",
            run_id="run-1",
            mission_id="mission-1",
            decision=DECISION_ABORT_RUN,
            actor_id="human-1",
            submitted_at=FIXED_AT,
        )
        with self.assertRaises(Exception):
            cmd.decision = DECISION_CLARIFY_SCOPE  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
