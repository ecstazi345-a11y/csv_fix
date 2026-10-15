"""Constructor launch hygiene — no accidental runs over usable professional results."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from agents.human_surface.mission_command import (
    MissionLaunchResult,
    launch_monthly_plan_mission,
    reset_launch_memory_for_tests,
)
from agents.human_surface.mission_draft import (
    CONSTRUCTOR_AGENT_CODE,
    EXISTING_MONTHLY_ANALYSIS_RU,
    WORK_CONTEXT_SLICE_RU,
)
from agents.human_surface.mission_recovery import (
    DurableRunEvidence,
    decide_recovery,
    find_usable_professional_run,
)
from agents.human_surface.work_context import ScopeFact, WorkContextCatalog
from agents.human_surface.mission_draft import WorkingContext

WHEN = datetime(2026, 10, 13, 11, 33, tzinfo=timezone.utc)
PAGE = (
    Path(__file__).resolve().parents[1]
    / "pages"
    / "53_AI_Центр_управления_агентами.py"
)


def _catalog() -> WorkContextCatalog:
    return WorkContextCatalog(
        source="test",
        error="",
        months=("октябрь 2026",),
        facts=(
            ScopeFact(
                project_label="БХК",
                project_code="PRJ_001_БХК",
                queue="1",
                facility="16160-13",
                title="16160-13",
                discipline="Автоматизация",
                systems=("АСУТП",),
                packages=(),
            ),
        ),
    )


def _context(**overrides: object) -> WorkingContext:
    payload = dict(
        project="БХК",
        planning_month="октябрь 2026",
        queue="1",
        titles=("16160-13",),
        discipline="Автоматизация",
        systems=(),
        packages=None,
        agent_code=CONSTRUCTOR_AGENT_CODE,
        intent="Сформировать кандидатный состав.",
        contour_code="MONTHLY_PRODUCTION_COMMITMENT",
    )
    payload.update(overrides)
    return WorkingContext(**payload)


def _evidence(**overrides: object) -> DurableRunEvidence:
    payload = dict(
        run_id="run-a0c70277-486b-439d-a6be-7599411ffc37",
        mission_id="mission-hs-64b62cbcb56220fb604625d3",
        initiator_id="human-surface",
        agent_code=CONSTRUCTOR_AGENT_CODE,
        project_code="PRJ_001_БХК",
        month_key="октябрь-2026",
        operational_status="RUNNING",
        requested_at=WHEN,
        scope_summary={"facility": ["16160-13", "16160-17"]},
        trigger_reason="Сформировать",
        lifecycle_status="WAITING_FOR_HUMAN_REVIEW",
        has_candidate_package=True,
    )
    payload.update(overrides)
    return DurableRunEvidence(**payload)


class LaunchHygieneRecoveryTests(unittest.TestCase):
    def test_prefers_professional_waiting_package_over_failed(self) -> None:
        failed = _evidence(
            run_id="run-58c0d06b-672f-41e7-940e-8c152918b909",
            mission_id="mission-hs-cac018749e6639aa0dbf056b",
            operational_status="FAILED",
            lifecycle_status="FAILED",
            has_candidate_package=False,
            requested_at=datetime(2026, 10, 14, 17, 9, tzinfo=timezone.utc),
        )
        decision = decide_recovery((failed, _evidence()))
        self.assertFalse(decision.ambiguous)
        self.assertIsNotNone(decision.selected)
        assert decision.selected is not None
        self.assertEqual(
            decision.selected.run_id,
            "run-a0c70277-486b-439d-a6be-7599411ffc37",
        )

    def test_find_usable_filters_project_month(self) -> None:
        class _Store:
            def list_runs(self, **kwargs):
                return (
                    _evidence(),
                    _evidence(
                        run_id="run-other-month",
                        month_key="ноябрь-2026",
                        requested_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
                    ),
                )

        class _Port:
            _store = _Store()

        # list_runs returns evidence-like objects? find uses _evidence_from_run on store runs.
        # Use decide/find with patched list_durable_run_evidence instead.
        evidence = (
            _evidence(),
            _evidence(
                run_id="run-other-month",
                month_key="ноябрь-2026",
                requested_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
            ),
        )
        with patch(
            "agents.human_surface.mission_recovery.list_durable_run_evidence",
            return_value=evidence,
        ):
            found = find_usable_professional_run(
                object(),
                project_code="PRJ_001_БХК",
                month_key="октябрь-2026",
            )
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.run_id, "run-a0c70277-486b-439d-a6be-7599411ffc37")


class LaunchHygienePortTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_launch_memory_for_tests()

    def test_launch_reuses_existing_waiting_professional_no_starter(self) -> None:
        calls: list[object] = []

        def starter(start_input: object) -> MissionLaunchResult:
            calls.append(start_input)
            raise AssertionError("starter must not run when reusable professional exists")

        usable = _evidence()
        with patch(
            "agents.human_surface.mission_recovery.find_usable_professional_run",
            return_value=__import__(
                "agents.human_surface.mission_recovery", fromlist=["RecoveredMission"]
            ).RecoveredMission(
                run_id=usable.run_id,
                mission_id=usable.mission_id,
                project_label="БХК",
                planning_month="октябрь 2026",
                queue="1",
                titles=("16160-13", "16160-17"),
                discipline=None,
                systems=(),
                packages=None,
                intent="Сформировать",
                operational_status="RUNNING",
                lifecycle_status="WAITING_FOR_HUMAN_REVIEW",
                requested_at=WHEN,
            ),
        ):
            result = launch_monthly_plan_mission(
                _context(),
                _catalog(),
                starter=starter,
                query_port=object(),
            )
        self.assertEqual(calls, [])
        self.assertTrue(result.reused_existing)
        self.assertEqual(result.run_id, usable.run_id)

    def test_work_context_change_does_not_require_launch_strings(self) -> None:
        page = PAGE.read_text(encoding="utf-8")
        self.assertIn("WORK_CONTEXT_SLICE_RU", page)
        self.assertIn("EXISTING_MONTHLY_ANALYSIS_RU", page)
        self.assertIn("find_usable_professional_run", page)
        self.assertIn("reused_existing", page)
        self.assertIn("_FAILED_STATUSES", page)
        self.assertTrue(WORK_CONTEXT_SLICE_RU)
        self.assertTrue(EXISTING_MONTHLY_ANALYSIS_RU)

    def test_failed_launch_does_not_steal_when_usable_exists_page_guard(self) -> None:
        text = PAGE.read_text(encoding="utf-8")
        # Failed status path restores usable professional before setting active.
        failed_idx = text.index("status_text in _FAILED_STATUSES")
        restore_idx = text.index("_find_usable_professional_for_context", failed_idx)
        assign_idx = text.index(
            'st.session_state["dynamis_active_run_id"] = confirmed_run',
            failed_idx,
        )
        self.assertLess(restore_idx, assign_idx)
        self.assertIn("Восстановлен существующий результат", text)
        self.assertIn("operational_status_for_run", text)


if __name__ == "__main__":
    unittest.main()
