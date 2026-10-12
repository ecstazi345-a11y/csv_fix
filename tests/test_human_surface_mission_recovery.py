"""Durable Human Surface mission recovery. No launch and no product writes."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from agents.human_surface.mission_draft import CONSTRUCTOR_AGENT_CODE
from agents.human_surface.mission_recovery import (
    DurableRunEvidence,
    decide_recovery,
    load_recovery_decision,
    working_context_from_mission,
)
from agents.human_surface.work_context import PLANNING_MONTHS_2026


WHEN = datetime(2026, 10, 12, 14, 24, tzinfo=timezone.utc)


def _evidence(**overrides: object) -> DurableRunEvidence:
    payload = dict(
        run_id="run-active",
        mission_id="mission-hs-active",
        initiator_id="human-surface",
        agent_code=CONSTRUCTOR_AGENT_CODE,
        project_code="PRJ_001_БХК",
        month_key="октябрь-2026",
        operational_status="RUNNING",
        requested_at=WHEN,
        scope_summary={"facility": ["16160-13", "16160-17"]},
        trigger_reason="Сформировать кандидатный состав месячного плана",
        lifecycle_status="REALITY_LOADED",
    )
    payload.update(overrides)
    return DurableRunEvidence(**payload)


class MissionRecoveryTests(unittest.TestCase):
    def test_one_executing_human_surface_run_is_recovered_with_scope(self) -> None:
        older_wait = _evidence(
            run_id="run-old-wait",
            mission_id="mission-hs-old",
            operational_status="WAITING_FOR_HUMAN",
            requested_at=datetime(2026, 10, 12, 13, 0, tzinfo=timezone.utc),
            lifecycle_status="WAITING_FOR_HUMAN",
            scope_summary={"queue": "1"},
        )
        completed_other = _evidence(
            run_id="run-history",
            mission_id="mission-history",
            initiator_id="live-proof-operator",
            operational_status="COMPLETED",
            scope_summary={"facility": "16160-13", "discipline": "ВЕНТИЛЯЦИЯ"},
        )
        decision = decide_recovery((older_wait, completed_other, _evidence()), months=PLANNING_MONTHS_2026)
        self.assertFalse(decision.ambiguous)
        selected = decision.selected
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected.run_id, "run-active")
        self.assertEqual(selected.mission_id, "mission-hs-active")
        self.assertEqual(selected.project_label, "БХК")
        self.assertEqual(selected.planning_month, "октябрь 2026")
        self.assertEqual(selected.queue, "1")
        self.assertEqual(selected.titles, ("16160-13", "16160-17"))
        self.assertIsNone(selected.discipline)
        self.assertEqual(selected.systems, ())
        self.assertEqual(selected.lifecycle_status, "REALITY_LOADED")
        context = working_context_from_mission(selected)
        self.assertEqual(context.project, "БХК")
        self.assertEqual(context.planning_month, "октябрь 2026")
        self.assertEqual(context.queue, "1")
        self.assertEqual(context.titles, ("16160-13", "16160-17"))
        self.assertEqual(context.agent_code, CONSTRUCTOR_AGENT_CODE)

    def test_two_executing_runs_are_not_guessed(self) -> None:
        first = _evidence(run_id="run-a", requested_at=datetime(2026, 10, 12, 10, tzinfo=timezone.utc))
        second = _evidence(run_id="run-b", requested_at=datetime(2026, 10, 12, 11, tzinfo=timezone.utc))
        decision = decide_recovery((first, second))
        self.assertTrue(decision.ambiguous)
        self.assertIsNone(decision.selected)
        self.assertEqual([item.run_id for item in decision.choices], ["run-b", "run-a"])

    def test_non_human_surface_run_is_not_recovered(self) -> None:
        foreign = _evidence(initiator_id="live-proof-operator", run_id="run-foreign")
        decision = decide_recovery((foreign,))
        self.assertIsNone(decision.selected)
        self.assertFalse(decision.ambiguous)
        self.assertEqual(decision.choices, ())

    def test_completed_human_surface_run_is_not_recovered(self) -> None:
        done = _evidence(operational_status="COMPLETED", lifecycle_status="PROFESSIONAL_WORK_COMPLETED")
        decision = decide_recovery((done,))
        self.assertIsNone(decision.selected)
        self.assertFalse(decision.ambiguous)

    def test_mixed_queues_do_not_invent_one_queue(self) -> None:
        mixed = _evidence(scope_summary={"facility": ["16160-13", "26160-13"]})
        selected = decide_recovery((mixed,)).selected
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertIsNone(selected.queue)
        self.assertEqual(selected.titles, ("16160-13", "26160-13"))

    def test_loader_without_a_store_does_not_select_a_run(self) -> None:
        decision = load_recovery_decision(object())
        self.assertIsNone(decision.selected)
        self.assertFalse(decision.ambiguous)
