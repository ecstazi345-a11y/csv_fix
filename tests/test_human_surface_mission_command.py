"""Human Surface launch port. Does not start a live Constructor run."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from agents.human_surface.mission_command import (
    MissionCommandError,
    MissionLaunchResult,
    active_result_run_id,
    different_mission_state,
    formal_mission,
    launch_monthly_plan_mission,
    mission_idempotency_key,
    mission_preview_lines,
    reset_launch_memory_for_tests,
)
from agents.human_surface.mission_draft import (
    CONSTRUCTOR_AGENT_CODE,
    CURRENT_CONSTRUCTOR_RUN_ID,
    WorkingContext,
)
from agents.human_surface.work_context import ScopeFact, WorkContextCatalog
from agents.monthly_plan_constructor.domain import build_constructor_proposal
from agents.monthly_plan_constructor.mission_scope import build_constructor_mission_scope, bind_scope_to_mission
from agents.monthly_plan_constructor.secure_read_tools import (
    DEFAULT_SCOPE_READ_CAPABILITIES,
    SecureReadError,
    _assert_optional_capabilities,
)


ROOT = Path(__file__).resolve().parents[1]


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
                packages=("IWP-13",),
            ),
            ScopeFact(
                project_label="БХК",
                project_code="PRJ_001_БХК",
                queue="1",
                facility="16160-17",
                title="16160-17",
                discipline="Автоматизация",
                systems=("АСУТП",),
                packages=("IWP-17",),
            ),
            ScopeFact(
                project_label="БХК",
                project_code="PRJ_001_БХК",
                queue="2",
                facility="26160-13",
                title="26160-13",
                discipline="Вентиляция",
                systems=("В-1",),
                packages=(),
            ),
        ),
    )


def _context(intent: str = "Сформировать кандидатный состав месячного плана.") -> WorkingContext:
    return WorkingContext(
        project="БХК",
        planning_month="октябрь 2026",
        queue="1",
        titles=("16160-13", "16160-17"),
        discipline="Автоматизация",
        systems=("АСУТП",),
        packages="IWP-13, IWP-17",
        agent_code=CONSTRUCTOR_AGENT_CODE,
        intent=intent,
        contour_code="MONTHLY_PRODUCTION_COMMITMENT",
    )


class MissionCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_launch_memory_for_tests()

    def test_context_and_assignment_build_a_formal_draft(self) -> None:
        draft = formal_mission(_context())
        self.assertEqual(draft.unresolved_fields, ())
        self.assertEqual(draft.titles, ("16160-13", "16160-17"))
        self.assertEqual(
            mission_preview_lines(_context())[:6],
            (
                "Цифровой сотрудник: Инженер формирования месячного плана",
                "Контур: Месячное производственное обязательство",
                "Проект: БХК",
                "Месяц: октябрь 2026",
                "Очередь: 1",
                "Титулы: 16160-13, 16160-17",
            ),
        )

    def test_typing_an_assignment_does_not_launch(self) -> None:
        calls: list[object] = []

        def starter(start_input: object) -> MissionLaunchResult:
            calls.append(start_input)
            raise AssertionError("starter must not run")

        formal_mission(_context("СФОРМИРОВАТЬ"))
        self.assertEqual(calls, [])
        self.assertIsNone(active_result_run_id(None))
        self.assertNotEqual(active_result_run_id(None), CURRENT_CONSTRUCTOR_RUN_ID)

    def test_explicit_launch_uses_one_port_call_and_rerun_keeps_the_run(self) -> None:
        calls: list[object] = []

        def starter(start_input: object) -> MissionLaunchResult:
            calls.append(start_input)
            return MissionLaunchResult(
                run_id="run-new-1",
                mission_id=str(getattr(start_input, "requested_mission_id")),
                status="STARTING",
                started_at="2026-10-12T12:00:00+00:00",
            )

        first = launch_monthly_plan_mission(_context(), _catalog(), starter=starter)
        second = launch_monthly_plan_mission(_context(), _catalog(), starter=starter)
        self.assertEqual(len(calls), 1)
        self.assertEqual(first.run_id, "run-new-1")
        self.assertEqual(second.run_id, first.run_id)
        self.assertEqual(active_result_run_id(first.run_id), "run-new-1")
        start_input = calls[0]
        self.assertEqual(start_input.agent_code, CONSTRUCTOR_AGENT_CODE)
        self.assertEqual(start_input.project_code, "PRJ_001_БХК")
        self.assertEqual(start_input.month_key, "октябрь-2026")
        self.assertEqual(start_input.scope_request["facility"], ["16160-13", "16160-17"])
        self.assertEqual(start_input.scope_request["discipline"], "Автоматизация")
        self.assertNotIn("queue", start_input.scope_request)
        self.assertNotEqual(first.run_id, CURRENT_CONSTRUCTOR_RUN_ID)

    def test_project_and_month_alone_launch_one_unrestricted_run(self) -> None:
        calls: list[object] = []

        def starter(start_input: object) -> MissionLaunchResult:
            calls.append(start_input)
            return MissionLaunchResult(
                run_id="run-broad-1",
                mission_id="mission-broad-1",
                status="STARTING",
                started_at="2026-10-12T12:00:00+00:00",
            )

        context = WorkingContext(
            project="БХК",
            planning_month="октябрь 2026",
            agent_code=CONSTRUCTOR_AGENT_CODE,
            intent=(
                "Сформировать единый кандидатный состав "
                "месячного производственного обязательства "
                "по всему доступному производственному горизонту месяца."
            ),
            contour_code="MONTHLY_PRODUCTION_COMMITMENT",
        )
        draft = formal_mission(context)
        self.assertEqual(draft.unresolved_fields, ())
        self.assertEqual(draft.titles, ())
        self.assertEqual(draft.systems, ())
        preview = "\n".join(mission_preview_lines(context))
        self.assertIn("Все очереди", preview)
        self.assertIn("Все титулы", preview)
        self.assertIn("Все дисциплины", preview)
        self.assertIn("Все системы", preview)
        self.assertIn("Все пакеты", preview)
        self.assertNotIn("Все системы", context.systems)
        first = launch_monthly_plan_mission(context, _catalog(), starter=starter)
        second = launch_monthly_plan_mission(context, _catalog(), starter=starter)
        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].scope_request, {})
        self.assertEqual(calls[0].project_code, "PRJ_001_БХК")
        self.assertEqual(calls[0].month_key, "октябрь-2026")

    def test_missing_context_does_not_call_the_starter(self) -> None:
        calls: list[object] = []

        def starter(start_input: object) -> MissionLaunchResult:
            calls.append(start_input)
            raise AssertionError("starter must not run")

        incomplete = WorkingContext(
            project="БХК",
            agent_code=CONSTRUCTOR_AGENT_CODE,
            intent="Сформировать кандидатный состав месячного плана.",
            contour_code="MONTHLY_PRODUCTION_COMMITMENT",
        )
        with self.assertRaises(MissionCommandError) as caught:
            launch_monthly_plan_mission(incomplete, _catalog(), starter=starter)
        self.assertIn("месяц", caught.exception.message)
        self.assertNotIn("титулы", caught.exception.message)
        self.assertNotIn("системы", caught.exception.message)
        self.assertEqual(calls, [])

    def test_filters_narrow_one_scope_and_do_not_replace_each_other(self) -> None:
        seen: list[dict] = []

        def starter(start_input: object) -> MissionLaunchResult:
            seen.append(dict(start_input.scope_request))
            return MissionLaunchResult(
                run_id=f"run-scope-{len(seen)}",
                mission_id=f"mission-scope-{len(seen)}",
                status="STARTING",
                started_at="2026-10-12T12:00:00+00:00",
            )

        def launch(**extra: object) -> None:
            payload = dict(
                project="БХК",
                planning_month="октябрь 2026",
                agent_code=CONSTRUCTOR_AGENT_CODE,
                contour_code="MONTHLY_PRODUCTION_COMMITMENT",
                intent="Сформировать единый кандидатный состав.",
            )
            payload.update(extra)
            launch_monthly_plan_mission(WorkingContext(**payload), _catalog(), starter=starter)

        launch()
        launch(queue="1")
        launch(titles=("16160-13",))
        launch(discipline="Автоматизация")
        launch(systems=("АСУТП",))
        launch(packages="IWP-13")
        launch(queue="1", discipline="Автоматизация", titles=("16160-13",))
        self.assertEqual(seen[0], {})
        self.assertEqual(seen[1], {"facility": ["16160-13", "16160-17"]})
        self.assertNotIn("queue", seen[1])
        self.assertEqual(seen[2], {"facility": ["16160-13"]})
        self.assertEqual(seen[3], {"discipline": "Автоматизация"})
        self.assertEqual(seen[4], {"system": ["АСУТП"]})
        self.assertEqual(seen[5], {"iwp": ["IWP-13"]})
        self.assertEqual(
            seen[6],
            {"facility": ["16160-13"], "discipline": "Автоматизация"},
        )
        self.assertNotIn("queue", seen[6])
        self.assertEqual(len(seen), 7)

    def test_empty_optional_filters_stay_unrestricted(self) -> None:
        calls: list[object] = []

        def starter(start_input: object) -> MissionLaunchResult:
            calls.append(start_input)
            return MissionLaunchResult(
                run_id="run-empty-filters",
                mission_id="mission-empty-filters",
                status="STARTING",
                started_at="2026-10-12T12:00:00+00:00",
            )

        context = WorkingContext(
            project="БХК",
            planning_month="октябрь 2026",
            queue="",
            titles=(),
            discipline="",
            systems=(),
            packages="",
            agent_code=CONSTRUCTOR_AGENT_CODE,
            intent="Сформировать единый кандидатный состав.",
            contour_code="MONTHLY_PRODUCTION_COMMITMENT",
        )
        launch_monthly_plan_mission(context, _catalog(), starter=starter)
        request = calls[0].scope_request
        self.assertEqual(request, {})
        for key in ("queue", "facility", "discipline", "system", "iwp"):
            self.assertNotIn(key, request)
        scope = _mission_scope(calls[0])
        self.assertIsNone(scope.queue_scope)
        self.assertIsNone(scope.facility_scope)
        self.assertIsNone(scope.discipline_scope)
        self.assertIsNone(scope.system_scope)
        self.assertIsNone(scope.iwp_scope)
        _assert_optional_capabilities(scope, DEFAULT_SCOPE_READ_CAPABILITIES)
        rows = pd.DataFrame(
            [
                _source_row("16160-13", "BOQ-A"),
                _source_row("26160-13", "BOQ-B"),
            ]
        )
        bound = bind_scope_to_mission(rows, scope)
        self.assertEqual(len(bound), len(rows))
        self.assertGreater(len(bound), 0)

    def test_queue_without_titles_resolves_to_that_queue_only(self) -> None:
        calls: list[object] = []

        def starter(start_input: object) -> MissionLaunchResult:
            calls.append(start_input)
            return MissionLaunchResult(
                run_id="run-queue-1",
                mission_id="mission-queue-1",
                status="STARTING",
                started_at="2026-10-12T12:00:00+00:00",
            )

        context = WorkingContext(
            project="БХК",
            planning_month="октябрь 2026",
            queue="1",
            agent_code=CONSTRUCTOR_AGENT_CODE,
            intent="Сформировать единый кандидатный состав.",
            contour_code="MONTHLY_PRODUCTION_COMMITMENT",
        )
        launch_monthly_plan_mission(context, _catalog(), starter=starter)
        self.assertEqual(len(calls), 1)
        request = calls[0].scope_request
        self.assertEqual(request, {"facility": ["16160-13", "16160-17"]})
        self.assertNotIn("26160-13", request["facility"])
        scope = _mission_scope(calls[0])
        self.assertIsNone(scope.queue_scope)
        _assert_optional_capabilities(scope, DEFAULT_SCOPE_READ_CAPABILITIES)

    def test_multi_title_scope_is_one_run(self) -> None:
        calls: list[object] = []

        def starter(start_input: object) -> MissionLaunchResult:
            calls.append(start_input)
            return MissionLaunchResult(
                run_id="run-multi-title",
                mission_id="mission-multi-title",
                status="STARTING",
                started_at="2026-10-12T12:00:00+00:00",
            )

        context = WorkingContext(
            project="БХК",
            planning_month="октябрь 2026",
            queue="1",
            titles=("16160-17", "16160-13"),
            agent_code=CONSTRUCTOR_AGENT_CODE,
            intent="Сформировать единый кандидатный состав.",
            contour_code="MONTHLY_PRODUCTION_COMMITMENT",
        )
        launch_monthly_plan_mission(context, _catalog(), starter=starter)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].scope_request["facility"], ["16160-13", "16160-17"])
        self.assertNotIn("queue", calls[0].scope_request)

    def test_resolved_broad_scope_keeps_one_decision_per_source_row(self) -> None:
        calls: list[object] = []

        def starter(start_input: object) -> MissionLaunchResult:
            calls.append(start_input)
            return MissionLaunchResult(
                run_id="run-broad-decisions",
                mission_id="mission-broad-decisions",
                status="STARTING",
                started_at="2026-10-12T12:00:00+00:00",
            )

        context = WorkingContext(
            project="БХК",
            planning_month="октябрь 2026",
            queue="1",
            agent_code=CONSTRUCTOR_AGENT_CODE,
            intent="Сформировать единый кандидатный состав.",
            contour_code="MONTHLY_PRODUCTION_COMMITMENT",
        )
        launch_monthly_plan_mission(context, _catalog(), starter=starter)
        facilities = calls[0].scope_request["facility"]
        source = [
            _source_row("16160-13", "BOQ-1"),
            _source_row("16160-13", "BOQ-2"),
            _source_row("16160-17", "BOQ-3"),
            _source_row("26160-13", "BOQ-OTHER-QUEUE"),
        ]
        self.assertNotEqual(len(source), 80)
        scope = _mission_scope(calls[0])
        bound = bind_scope_to_mission(pd.DataFrame(source), scope)
        expected = [row for row in source if row["facility_building"] in facilities]
        self.assertEqual(len(bound), len(expected))
        self.assertGreater(len(bound), 0)
        self.assertNotIn("BOQ-OTHER-QUEUE", set(bound["boq_code"]))
        proposal = build_constructor_proposal(
            bound,
            pd.DataFrame(),
            pd.DataFrame(),
            calls[0].project_code,
            calls[0].month_key,
        )
        self.assertTrue(proposal["ok"])
        self.assertEqual(len(proposal["row_decisions"]), len(bound))
        self.assertEqual(len(proposal["row_decisions"]), len(expected))

    def test_narrow_title_and_discipline_do_not_send_queue(self) -> None:
        calls: list[object] = []

        def starter(start_input: object) -> MissionLaunchResult:
            calls.append(start_input)
            return MissionLaunchResult(
                run_id="run-narrow",
                mission_id="mission-narrow",
                status="STARTING",
                started_at="2026-10-12T12:00:00+00:00",
            )

        context = WorkingContext(
            project="БХК",
            planning_month="октябрь 2026",
            titles=("16160-13",),
            discipline="Вентиляция",
            agent_code=CONSTRUCTOR_AGENT_CODE,
            intent="Сформировать кандидатный состав месячного плана.",
            contour_code="MONTHLY_PRODUCTION_COMMITMENT",
        )
        launch_monthly_plan_mission(context, _catalog(), starter=starter)
        self.assertEqual(
            calls[0].scope_request,
            {"facility": ["16160-13"], "discipline": "Вентиляция"},
        )
        scope = _mission_scope(calls[0])
        self.assertIsNone(scope.queue_scope)
        self.assertEqual(scope.facility_scope, ("16160-13",))
        self.assertEqual(scope.discipline_scope, ("ВЕНТИЛЯЦИЯ",))
        _assert_optional_capabilities(scope, DEFAULT_SCOPE_READ_CAPABILITIES)

    def test_unresolved_queue_does_not_launch(self) -> None:
        calls: list[object] = []

        def starter(start_input: object) -> MissionLaunchResult:
            calls.append(start_input)
            raise AssertionError("starter must not run")

        unknown_queue = WorkingContext(
            project="БХК",
            planning_month="октябрь 2026",
            queue="9",
            agent_code=CONSTRUCTOR_AGENT_CODE,
            intent="Сформировать единый кандидатный состав.",
            contour_code="MONTHLY_PRODUCTION_COMMITMENT",
        )
        with self.assertRaises(MissionCommandError) as unknown:
            launch_monthly_plan_mission(unknown_queue, _catalog(), starter=starter)
        self.assertIn("очереди 9", unknown.exception.message)

        outside = WorkingContext(
            project="БХК",
            planning_month="октябрь 2026",
            queue="1",
            titles=("26160-13",),
            agent_code=CONSTRUCTOR_AGENT_CODE,
            intent="Сформировать единый кандидатный состав.",
            contour_code="MONTHLY_PRODUCTION_COMMITMENT",
        )
        with self.assertRaises(MissionCommandError) as mismatched:
            launch_monthly_plan_mission(outside, _catalog(), starter=starter)
        self.assertIn("26160-13", mismatched.exception.message)
        self.assertEqual(calls, [])

    def test_queue_scope_is_the_read_gate_that_stops_before_rows(self) -> None:
        rejected = build_constructor_mission_scope(
            project_code="PRJ_001_БХК",
            month_key="октябрь-2026",
            facility_scope=("16160-13", "16160-17"),
            queue_scope="1",
        )
        with self.assertRaises(SecureReadError) as caught:
            _assert_optional_capabilities(rejected, DEFAULT_SCOPE_READ_CAPABILITIES)
        self.assertIn("queue_scope is set but the approved read tool cannot enforce it", str(caught.exception))

    def test_launch_identity_survives_rerun_and_warns_only_after_a_change(self) -> None:
        context = _context()
        identity = mission_idempotency_key(context)
        self.assertFalse(different_mission_state(identity, identity, "run-a", "run-a"))
        self.assertFalse(different_mission_state(identity, identity, None, "run-a"))
        changed_intent = WorkingContext(
            project=context.project,
            planning_month=context.planning_month,
            queue=context.queue,
            titles=context.titles,
            discipline=context.discipline,
            systems=context.systems,
            packages=context.packages,
            agent_code=context.agent_code,
            intent="Другое поручение",
            contour_code=context.contour_code,
        )
        changed_queue = WorkingContext(
            project=context.project,
            planning_month=context.planning_month,
            queue="2",
            titles=context.titles,
            discipline=context.discipline,
            systems=context.systems,
            packages=context.packages,
            agent_code=context.agent_code,
            intent=context.intent,
            contour_code=context.contour_code,
        )
        self.assertTrue(
            different_mission_state(mission_idempotency_key(changed_intent), identity, "run-a", "run-a")
        )
        self.assertTrue(
            different_mission_state(mission_idempotency_key(changed_queue), identity, "run-a", "run-a")
        )
        self.assertTrue(different_mission_state(identity, None, "run-old", None))
        self.assertEqual(active_result_run_id("run-a"), "run-a")
        self.assertNotEqual(active_result_run_id("run-a"), CURRENT_CONSTRUCTOR_RUN_ID)

    def test_unconnected_employee_does_not_launch(self) -> None:
        calls: list[object] = []

        def starter(start_input: object) -> MissionLaunchResult:
            calls.append(start_input)
            raise AssertionError("starter must not run")

        blocked = WorkingContext(
            project="БХК",
            planning_month="октябрь 2026",
            agent_code="ADMISSION_AGENT",
            intent="Сформировать план.",
            contour_code="MONTHLY_PRODUCTION_COMMITMENT",
        )
        with self.assertRaises(MissionCommandError):
            launch_monthly_plan_mission(blocked, _catalog(), starter=starter)
        self.assertEqual(calls, [])

    def test_existing_launcher_is_reused_and_page_does_not_own_it(self) -> None:
        port = (ROOT / "agents" / "human_surface" / "mission_command.py").read_text(encoding="utf-8")
        page = (ROOT / "pages" / "53_AI_Центр_управления_агентами.py").read_text(encoding="utf-8")
        launcher = (ROOT / "agents" / "monthly_plan_constructor" / "managed_launcher.py").read_text(encoding="utf-8")
        self.assertIn("build_constructor_shadow_composition", port)
        self.assertIn("composition.start", port)
        self.assertNotIn("build_constructor_shadow_composition", page)
        self.assertNotIn("agents.monthly_plan_constructor", page)
        self.assertNotIn("sqlite3", page)
        self.assertIn("def launch(", launcher)
        self.assertNotIn("CREATE TABLE", port)
        self.assertNotIn("ALTER TABLE", port)
        self.assertNotIn("scope[\"queue\"]", port)
        self.assertNotIn("scope['queue']", port)


def _mission_scope(start_input: object):
    request = start_input.scope_request
    return build_constructor_mission_scope(
        project_code=start_input.project_code,
        month_key=start_input.month_key,
        facility_scope=request.get("facility"),
        discipline_scope=request.get("discipline"),
        system_scope=request.get("system"),
        iwp_scope=request.get("iwp"),
        queue_scope=request.get("queue"),
    )


def _source_row(facility: str, boq_code: str) -> dict[str, object]:
    return {
        "project_code": "PRJ_001_БХК",
        "month_key": "октябрь-2026",
        "facility_building": facility,
        "facility": facility,
        "construction_discipline": "Автоматизация",
        "discipline": "Автоматизация",
        "system_label": "АСУТП",
        "system": "АСУТП",
        "iwp_id": "",
        "iwp": "",
        "boq_code": boq_code,
        "boq_name": boq_code,
        "unit": "м",
        "total_project_qty": 10.0,
        "total_qty": 10.0,
        "executed_qty_all_time": 0.0,
        "executed_qty": 0.0,
        "unit_price": 10.0,
        "total_project_value": 100.0,
        "total_value": 100.0,
        "planning_remaining_qty": 10.0,
        "manual_executed_before_system": 0.0,
        "manual_verified_remaining_qty": float("nan"),
    }


if __name__ == "__main__":
    unittest.main()
