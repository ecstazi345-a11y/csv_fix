"""Mission draft and Constructor result read-model tests. No runtime launch."""

from __future__ import annotations

import unittest

from agents.control_room.dtos import (
    ConstructorCandidateResultView,
    ConstructorDecisionRegistryView,
    ConstructorProfessionalResultView,
    ConstructorRowDecisionView,
    ProfessionalResultAvailability,
)
from agents.human_surface.mission_draft import (
    ContextOptionSets,
    apply_global_command,
    command_draft_lines,
    empty_working_context,
    global_command_preview_lines,
    merge_context_options,
    mission_draft_lines,
    mission_from_context,
    parse_command_text,
    parse_global_command,
    parse_mission_text,
)
from agents.human_surface.result_view import (
    select_workspace_records,
    workspace_result_lines,
)


def _result() -> ConstructorProfessionalResultView:
    return ConstructorProfessionalResultView(
        availability=ProfessionalResultAvailability.AVAILABLE,
        run_id="run-80",
        mission_id="mission-80",
        professional_status="WAITING_FOR_HUMAN_REVIEW",
        project_id="PRJ_001_БХК",
        month="октябрь-2026",
        facility_id="16160-13",
        discipline="ВЕНТИЛЯЦИЯ",
        source_candidate_package_id="pkg",
        reviewed_package_id="",
        included_count=None,
        excluded_count=None,
        unresolved_count=None,
        confirm_event_id="",
        confirm_decision="",
        confirm_actor_type="",
        confirm_actor_id="",
        path_statuses=("WAITING_FOR_HUMAN_REVIEW",),
        candidates=(
            ConstructorCandidateResultView(
                candidate_id="c-1",
                boq_code="BOQ-C1",
                name="Решетка",
                unit="м2",
                remaining_qty="1",
                already_planned_qty="0",
                available_qty="1",
                labor_status="UNRESOLVED",
                recommendation="HUMAN_REVIEW_REQUIRED",
                exception_codes=(),
                human_review_decision="",
                final_disposition="",
                final_reason_code="",
            ),
            ConstructorCandidateResultView(
                candidate_id="c-2",
                boq_code="BOQ-C2",
                name="Клапан",
                unit="м2",
                remaining_qty="1",
                already_planned_qty="0",
                available_qty="1",
                labor_status="UNRESOLVED",
                recommendation="HUMAN_REVIEW_REQUIRED",
                exception_codes=(),
                human_review_decision="",
                final_disposition="",
                final_reason_code="",
            ),
        ),
        package_candidate_count=2,
    )


def _record(order: int, outcome: str, boq: str, name: str) -> ConstructorRowDecisionView:
    return ConstructorRowDecisionView(
        source_identity=f"{order}|{boq}",
        source_order=order,
        boq_code=boq,
        name=name,
        unit="м2",
        system="П1" if outcome == "EXCLUDED_COMPLETED" else None,
        remaining_qty=None if outcome == "EXCLUDED_INVALID" else "1",
        already_planned_qty=None if outcome == "EXCLUDED_INVALID" else "0",
        available_qty=None if outcome == "EXCLUDED_INVALID" else "1",
        outcome=outcome,
        reason_code=outcome,
        reason_text="Сохранённое основание",
        requires_human=None if outcome == "CANDIDATE" else False,
        candidate_created=outcome == "CANDIDATE",
        candidate_id="c-1" if boq == "BOQ-C1" else ("c-2" if boq == "BOQ-C2" else ""),
    )


def _eighty() -> tuple[ConstructorRowDecisionView, ...]:
    plan = (
        ("CANDIDATE", 2),
        ("EXCLUDED_COMPLETED", 38),
        ("EXCLUDED_NO_REMAINDER", 20),
        ("EXCLUDED_ALREADY_PLANNED", 3),
        ("EXCLUDED_INVALID", 16),
        ("EXCLUDED_OVERRUN", 1),
    )
    rows = []
    order = 0
    for outcome, count in plan:
        for index in range(count):
            boq = "BOQ-C1" if outcome == "CANDIDATE" and index == 0 else (
                "BOQ-C2" if outcome == "CANDIDATE" else f"BOQ-{order:03d}"
            )
            rows.append(_record(order, outcome, boq, "Решетка" if boq == "BOQ-C1" else f"Работа {order}"))
            order += 1
    return tuple(rows)


class MissionDraftTests(unittest.TestCase):
    def test_sentence_and_slash_assignment_parse_without_guessing(self) -> None:
        sentence = parse_mission_text(
            "Собери мне по проекту БХК, 1 очередь, титулы 13 и 17, "
            "дисциплина вентиляция, системы П1 П2 П3 В1 В2 В3, на ноябрь 2026"
        )
        slash = parse_mission_text(
            "БХК / 1 очередь / титулы 13,17 / вентиляция / П1 П2 П3 В1 В2 В3 / ноябрь 2026"
        )
        for draft in (sentence, slash):
            self.assertEqual(draft.agent_code, "MONTHLY_PLAN_CONSTRUCTOR")
            self.assertEqual(draft.unresolved_fields, ())
            lines = dict(mission_draft_lines(draft))
            self.assertEqual(lines["Проект"], "БХК")
            self.assertEqual(lines["Очередь"], "1")
            self.assertEqual(lines["Титулы"], "13, 17")
            self.assertEqual(lines["Дисциплина"], "Вентиляция")
            self.assertEqual(lines["Системы"], "П1, П2, П3, В1, В2, В3")
            self.assertEqual(lines["Горизонт"], "ноябрь 2026")

    def test_missing_field_stays_unresolved(self) -> None:
        draft = parse_mission_text("проект БХК, вентиляция, ноябрь 2026")
        self.assertIn("queue", draft.unresolved_fields)
        self.assertIn("titles", draft.unresolved_fields)
        self.assertIn("systems", draft.unresolved_fields)
        self.assertNotIn("project", draft.unresolved_fields)

    def test_follow_up_command_does_not_invent_the_rest_count(self) -> None:
        draft = parse_command_text(
            "Передай агенту допуска 12 согласованных кодов. Остальные перенеси на ноябрь 2026."
        )
        self.assertEqual(
            command_draft_lines(draft),
            (
                "12 работ → передать Агенту допуска",
                "остальные → перенести на ноябрь 2026",
            ),
        )
        self.assertIn("defer_count", draft.unresolved_fields)
        self.assertEqual(draft.intents[0].action, "HANDOFF")
        self.assertEqual(draft.intents[1].action, "DEFER")

    def test_global_context_command_fills_the_same_formal_fields(self) -> None:
        draft = parse_global_command(
            "Проект БХК, ноябрь 2026, первая очередь, титулы 13 и 17. "
            "Выбери Constructor. По дисциплине вентиляция сформируй план "
            "по системам П1, П2, П3, В2, В6 и В8. "
            "Остальные системы в ноябрь вообще не включать."
        )
        self.assertEqual(draft.kind, "context")
        self.assertEqual(draft.unresolved_fields, ())
        self.assertEqual(draft.agent_code, "MONTHLY_PLAN_CONSTRUCTOR")
        self.assertEqual(draft.included_systems, ("П1", "П2", "П3", "В2", "В6", "В8"))
        self.assertEqual(
            draft.excluded_scope_rule,
            "Остальные системы не входят в плановый scope ноября 2026.",
        )
        self.assertEqual(draft.intent, "Сформировать кандидатный состав месячного плана.")
        self.assertEqual(
            global_command_preview_lines(draft)[:8],
            (
                "Контур: Месячное производственное обязательство",
                "Цифровой сотрудник: Инженер формирования месячного плана",
                "Проект: БХК",
                "Месяц: ноябрь 2026",
                "Очередь: 1",
                "Титулы: 13, 17",
                "Дисциплина: Вентиляция",
                "Системы: П1, П2, П3, В2, В6, В8",
            ),
        )
        self.assertIn("Правило: остальные системы в ноябрь не включать.", global_command_preview_lines(draft))
        applied = apply_global_command(empty_working_context(), draft)
        mission = mission_from_context(applied, draft.source_text)
        self.assertEqual(mission.project, "БХК")
        self.assertEqual(mission.systems, draft.included_systems)
        self.assertEqual(mission.unresolved_fields, ())
        self.assertNotIn("В1", mission.systems)

    def test_global_work_command_is_not_authority_and_keeps_positions(self) -> None:
        draft = parse_global_command(
            "Первую и вторую позиции согласовать. Третью не включать. "
            "Четвёртую перенести на декабрь. "
            "После подтверждения передать согласованные Агенту допуска.",
            horizon_year="2026",
        )
        self.assertEqual(draft.kind, "work")
        self.assertEqual(
            [(item.position, item.action) for item in draft.work_actions],
            [(1, "APPROVE"), (2, "APPROVE"), (3, "REJECT"), (4, "DEFER")],
        )
        self.assertEqual(draft.work_actions[3].target_month, "декабрь 2026")
        self.assertEqual(draft.next_agent, "ADMISSION")
        self.assertEqual(
            global_command_preview_lines(draft),
            (
                "2 работы → согласовать",
                "1 работа → не включать",
                "1 работа → перенести на декабрь 2026",
                "согласованные → подготовить к передаче Агенту допуска",
            ),
        )
        self.assertEqual(apply_global_command(empty_working_context(), draft).project, None)

    def test_global_command_selects_contour_and_employee_together(self) -> None:
        draft = parse_global_command(
            "БХК, ноябрь 2026, первая очередь, титулы 13 и 17, вентиляция, "
            "П1 П2 П3 В2 В6 В8. "
            "Работаем в контуре месячного производственного обязательства. "
            "Привлечь инженера формирования месячного плана. "
            "Остальные системы в ноябрь не включать."
        )
        self.assertEqual(draft.kind, "context")
        self.assertEqual(draft.unresolved_fields, ())
        self.assertEqual(draft.project, "БХК")
        self.assertEqual(draft.planning_month, "ноябрь 2026")
        self.assertEqual(draft.queue, "1")
        self.assertEqual(draft.titles, ("13", "17"))
        self.assertEqual(draft.discipline, "Вентиляция")
        self.assertEqual(draft.included_systems, ("П1", "П2", "П3", "В2", "В6", "В8"))
        self.assertEqual(draft.contour_code, "MONTHLY_PRODUCTION_COMMITMENT")
        self.assertEqual(draft.agent_code, "MONTHLY_PLAN_CONSTRUCTOR")
        self.assertEqual(
            draft.excluded_scope_rule,
            "Остальные системы не входят в плановый scope ноября 2026.",
        )
        applied = apply_global_command(empty_working_context(), draft)
        self.assertEqual(applied.contour_code, draft.contour_code)
        self.assertEqual(applied.agent_code, draft.agent_code)
        self.assertEqual(applied.titles, ("13", "17"))
        self.assertEqual(applied.systems, draft.included_systems)
        self.assertIn("Контур: Месячное производственное обязательство", global_command_preview_lines(draft))
        self.assertIn("Цифровой сотрудник: Инженер формирования месячного плана", global_command_preview_lines(draft))
        observed = ContextOptionSets(projects=("БХК",), systems=("П1",))
        merged = merge_context_options(observed, applied)
        self.assertEqual(merged.projects, ("БХК",))
        self.assertEqual(merged.titles, ("13", "17"))
        self.assertEqual(merged.systems, ("П1", "П2", "П3", "В2", "В6", "В8"))
        self.assertNotIn("П9", merged.systems)


class WorkspaceReadModelTests(unittest.TestCase):
    def test_real_distribution_filters_to_two_human_decisions(self) -> None:
        records = _eighty()
        result = _result()
        registry = ConstructorDecisionRegistryView(
            availability=ProfessionalResultAvailability.AVAILABLE,
            professional=result,
            total_count=len(records),
            outcome_counts=(
                ("CANDIDATE", 2),
                ("EXCLUDED_COMPLETED", 38),
                ("EXCLUDED_NO_REMAINDER", 20),
                ("EXCLUDED_ALREADY_PLANNED", 3),
                ("EXCLUDED_INVALID", 16),
                ("EXCLUDED_OVERRUN", 1),
            ),
            known_systems=("П1",),
            attention_count=2,
            records=records,
        )
        lines = workspace_result_lines(registry)
        self.assertIn("Изучено: 80", lines)
        self.assertIn("Предложено к рассмотрению: 2", lines)
        self.assertIn("Выполнено: 38", lines)
        self.assertEqual(len(select_workspace_records(records, result, view_id="all")), 80)
        self.assertEqual(len(select_workspace_records(records, result, view_id="CANDIDATE")), 2)
        self.assertEqual(len(select_workspace_records(records, result, view_id="attention")), 2)
        self.assertEqual(len(select_workspace_records(records, result, view_id="completed")), 38)
        self.assertEqual(len(select_workspace_records(records, result, view_id="excluded")), 78)
        found = select_workspace_records(records, result, view_id="all", text="решет")
        self.assertEqual(len(found), 1)
        self.assertIsNone(next(item for item in records if item.outcome == "EXCLUDED_INVALID").remaining_qty)


if __name__ == "__main__":
    unittest.main()
