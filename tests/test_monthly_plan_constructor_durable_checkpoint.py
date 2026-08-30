"""
Increment 8 — durable checkpoint helper fail-closed unit tests.

Direct tests of resolve_current_checkpoint_id / require_durable_resume_checkpoint.
No Postgres, no Streamlit, no product graph compile. Fakes only.

Kept out of test_monthly_plan_constructor_langgraph_runtime.py so helper
negatives do not mix with InMemorySaver HITL orchestration proofs.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from agents.monthly_plan_constructor.durable_checkpoint import (
    require_durable_resume_checkpoint,
    resolve_current_checkpoint_id,
)
from agents.monthly_plan_constructor.hitl_contracts import (
    CODE_HITL_CONTRACT_BLOCKER,
    HitlContractError,
)
from agents.monthly_plan_constructor.lifecycle import (
    CODE_LIFECYCLE_CONTRACT_BLOCKER,
    LifecycleError,
)
from security.agent_execution_context import (
    AgentExecutionContext,
    issue_read_only_agent_context,
)

PROJECT = "PRJ_001_БХК"
EXPECTED = "ckpt-expected-1"


def _live_context(*, run_id: str = "run-durable-helper") -> AgentExecutionContext:
    return issue_read_only_agent_context(
        agent_code="MONTHLY_PLAN_CONSTRUCTOR",
        project_code=PROJECT,
        run_id=run_id,
    )


def _expired_context(*, run_id: str = "run-durable-helper") -> AgentExecutionContext:
    live = _live_context(run_id=run_id)
    return AgentExecutionContext(
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


class _FakeCheckpointer:
    def __init__(self, tup) -> None:
        self.tup = tup
        self.calls: list[object] = []

    def get_tuple(self, config):
        self.calls.append(config)
        return self.tup


class TestRequireDurableResumeCheckpoint(unittest.TestCase):
    def test_expired_context_fail_closed(self) -> None:
        expired = _expired_context()
        self.assertTrue(expired.is_expired())
        with self.assertRaises(LifecycleError) as raised:
            require_durable_resume_checkpoint(
                expected_checkpoint_id=EXPECTED,
                current_checkpoint_id=EXPECTED,
                context=expired,
            )
        self.assertEqual(raised.exception.code, CODE_LIFECYCLE_CONTRACT_BLOCKER)
        self.assertIn("expired", str(raised.exception).lower())

    def test_missing_current_checkpoint_id_fail_closed(self) -> None:
        ctx = _live_context()
        for current in (None, "", "   "):
            with self.subTest(current=current):
                with self.assertRaises(HitlContractError) as raised:
                    require_durable_resume_checkpoint(
                        expected_checkpoint_id=EXPECTED,
                        current_checkpoint_id=current,
                        context=ctx,
                    )
                self.assertEqual(raised.exception.code, CODE_HITL_CONTRACT_BLOCKER)
                self.assertIn("could not be resolved", str(raised.exception))

    def test_missing_context_fail_closed(self) -> None:
        with self.assertRaises(LifecycleError) as raised:
            require_durable_resume_checkpoint(
                expected_checkpoint_id=EXPECTED,
                current_checkpoint_id=EXPECTED,
                context=None,
            )
        self.assertEqual(raised.exception.code, CODE_LIFECYCLE_CONTRACT_BLOCKER)


class TestResolveCurrentCheckpointId(unittest.TestCase):
    def test_none_checkpointer_fail_closed(self) -> None:
        with self.assertRaises(HitlContractError) as raised:
            resolve_current_checkpoint_id(None, thread_id="run-1")
        self.assertEqual(raised.exception.code, CODE_HITL_CONTRACT_BLOCKER)
        self.assertIn("checkpointer is required", str(raised.exception))

    def test_empty_or_invalid_thread_id_fail_closed(self) -> None:
        saver = _FakeCheckpointer(
            SimpleNamespace(config={"configurable": {"checkpoint_id": EXPECTED}})
        )
        for thread_id in ("", "   ", None):
            with self.subTest(thread_id=thread_id):
                with self.assertRaises(HitlContractError) as raised:
                    resolve_current_checkpoint_id(saver, thread_id=thread_id)  # type: ignore[arg-type]
                self.assertEqual(raised.exception.code, CODE_HITL_CONTRACT_BLOCKER)
                self.assertIn("thread_id is required", str(raised.exception))
        self.assertEqual(saver.calls, [])

    def test_get_tuple_none_fail_closed(self) -> None:
        saver = _FakeCheckpointer(None)
        with self.assertRaises(HitlContractError) as raised:
            resolve_current_checkpoint_id(saver, thread_id="run-1")
        self.assertEqual(raised.exception.code, CODE_HITL_CONTRACT_BLOCKER)
        self.assertIn("not found", str(raised.exception).lower())
        self.assertEqual(len(saver.calls), 1)

    def test_tuple_missing_checkpoint_id_fail_closed(self) -> None:
        cases = (
            SimpleNamespace(),
            SimpleNamespace(config=None),
            SimpleNamespace(config={"configurable": {}}),
            SimpleNamespace(config={"configurable": {"checkpoint_id": "   "}}),
        )
        for tup in cases:
            with self.subTest(tup=tup):
                saver = _FakeCheckpointer(tup)
                with self.assertRaises(HitlContractError) as raised:
                    resolve_current_checkpoint_id(saver, thread_id="run-1")
                self.assertEqual(raised.exception.code, CODE_HITL_CONTRACT_BLOCKER)
                self.assertIn("missing from runtime tuple", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
