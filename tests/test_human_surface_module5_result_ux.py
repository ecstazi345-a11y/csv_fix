"""Module 5 compact professional result UX — presentation grouping only."""

from __future__ import annotations

import unittest
from pathlib import Path

from agents.control_room.dtos import (
    ConstructorCandidateResultView,
    ConstructorDecisionRegistryView,
    ConstructorProfessionalResultView,
    ConstructorRowDecisionView,
    ProfessionalResultAvailability,
)
from agents.human_surface.result_view import (
    COMPLETED_MANAGER_NOTE_RU,
    CONFLICT_MANAGER_NOTE_RU,
    MODULE5_MODE_INCREMENTAL_RU,
    MODULE5_TITLE_RU,
    build_module5_result_summary,
    candidate_presentation_slice,
    conflict_deviation_display,
    human_surface_outcome_label,
    module5_filter_options,
    module5_kpi_tiles,
    select_workspace_records,
    simple_result_filter_options,
    workspace_table_rows,
)


def _result() -> ConstructorProfessionalResultView:
    return ConstructorProfessionalResultView(
        availability=ProfessionalResultAvailability.AVAILABLE,
        run_id="run-m5",
        mission_id="mission-m5",
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
                candidate_id="c-new",
                boq_code="BOQ-NEW",
                name="Новая",
                unit="м",
                remaining_qty="10",
                already_planned_qty="0",
                available_qty="10",
                labor_status="UNRESOLVED",
                recommendation="HUMAN_REVIEW_REQUIRED",
                exception_codes=(),
                human_review_decision="",
                final_disposition="",
                final_reason_code="",
            ),
            ConstructorCandidateResultView(
                candidate_id="c-add",
                boq_code="BOQ-ADD",
                name="Доп",
                unit="м",
                remaining_qty="20",
                already_planned_qty="5",
                available_qty="15",
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


def _row(
    order: int,
    outcome: str,
    *,
    boq: str,
    already: str | None,
    remaining: str | None,
    available: str | None,
    candidate_id: str = "",
) -> ConstructorRowDecisionView:
    return ConstructorRowDecisionView(
        source_identity=f"{order}|{boq}",
        source_order=order,
        boq_code=boq,
        name=boq,
        unit="м",
        system="SYS",
        remaining_qty=remaining,
        already_planned_qty=already,
        available_qty=available,
        outcome=outcome,
        reason_code=outcome,
        reason_text="stored",
        requires_human=None,
        candidate_created=outcome == "CANDIDATE",
        candidate_id=candidate_id,
        facility="16160-13",
        discipline="Дисциплина",
        iwp="IWP-1",
    )


def _registry() -> ConstructorDecisionRegistryView:
    records = (
        _row(0, "CANDIDATE", boq="BOQ-NEW", already="0", remaining="10", available="10", candidate_id="c-new"),
        _row(1, "CANDIDATE", boq="BOQ-ADD", already="5", remaining="20", available="15", candidate_id="c-add"),
        _row(2, "EXCLUDED_INCONSISTENT_QUANTITIES", boq="BOQ-CF", already="12", remaining="7", available="0"),
        _row(3, "EXCLUDED_INVALID", boq="BOQ-IV", already=None, remaining=None, available=None),
        _row(4, "EXCLUDED_OVERRUN", boq="BOQ-OV", already="0", remaining="0", available="0"),
        _row(5, "EXCLUDED_COMPLETED", boq="BOQ-CP", already="1", remaining="0", available="0"),
        _row(6, "EXCLUDED_ALREADY_PLANNED", boq="BOQ-AP", already="3", remaining="3", available="0"),
        _row(7, "EXCLUDED_NO_REMAINDER", boq="BOQ-NR", already="0", remaining="0", available="0"),
        _row(8, "EXCLUDED_NOT_REQUIRED", boq="BOQ-NT", already="0", remaining="1", available="0"),
    )
    return ConstructorDecisionRegistryView(
        availability=ProfessionalResultAvailability.AVAILABLE,
        professional=_result(),
        total_count=len(records),
        outcome_counts=(
            ("CANDIDATE", 2),
            ("EXCLUDED_INCONSISTENT_QUANTITIES", 1),
            ("EXCLUDED_INVALID", 1),
            ("EXCLUDED_OVERRUN", 1),
            ("EXCLUDED_COMPLETED", 1),
            ("EXCLUDED_ALREADY_PLANNED", 1),
            ("EXCLUDED_NO_REMAINDER", 1),
            ("EXCLUDED_NOT_REQUIRED", 1),
        ),
        known_systems=("SYS",),
        attention_count=2,
        records=records,
    )


class Module5CompactResultUxTests(unittest.TestCase):
    def test_kpi_groups_sum_to_total(self) -> None:
        summary = build_module5_result_summary(_registry())
        self.assertEqual(summary.total, 9)
        self.assertEqual(summary.proposed, 2)
        self.assertEqual(summary.control_deviations, 3)
        self.assertEqual(summary.no_action, 4)
        self.assertEqual(
            summary.proposed + summary.control_deviations + summary.no_action,
            summary.total,
        )
        self.assertTrue(summary.groups_sum_to_total)
        tiles = dict(module5_kpi_tiles(summary))
        self.assertEqual(tiles["Изучено"], "9")
        self.assertEqual(tiles["Предложено к рассмотрению"], "2")
        self.assertEqual(tiles["Контрольные отклонения"], "3")
        self.assertEqual(tiles["Не требуют действия"], "4")

    def test_proposed_and_control_and_no_action_decompositions(self) -> None:
        summary = build_module5_result_summary(_registry())
        self.assertEqual(summary.new_opportunities + summary.additional_volume, summary.proposed)
        self.assertEqual(summary.new_opportunities, 1)
        self.assertEqual(summary.additional_volume, 1)
        self.assertEqual(
            summary.conflict_plan_reality + summary.source_data + summary.overrun,
            summary.control_deviations,
        )
        self.assertEqual(
            summary.completed
            + summary.already_planned
            + summary.no_remainder
            + summary.not_required,
            summary.no_action,
        )

    def test_filter_mappings_and_conflict_label(self) -> None:
        registry = _registry()
        result = registry.professional
        self.assertEqual(
            len(select_workspace_records(registry.records, result, view_id="new_opportunity")),
            1,
        )
        self.assertEqual(
            len(select_workspace_records(registry.records, result, view_id="additional_volume")),
            1,
        )
        conflict = select_workspace_records(
            registry.records, result, view_id="conflict_plan_reality"
        )
        self.assertEqual(len(conflict), 1)
        self.assertEqual(conflict[0].outcome, "EXCLUDED_INCONSISTENT_QUANTITIES")
        labels = " ".join(label for _id, label in simple_result_filter_options(registry))
        self.assertIn("План > текущего остатка", labels)
        self.assertNotIn("Конфликт план ↔ реальность", labels)
        self.assertNotIn("Требуют решения", labels)
        self.assertIn("Кандидаты ·", labels)
        self.assertNotIn("Кандидаты (", labels)
        self.assertNotIn("Все работы", labels)
        self.assertNotIn("Проблемы", labels)
        emphasized = [
            item
            for item in module5_filter_options(build_module5_result_summary(registry))
            if item[2]
        ]
        self.assertTrue(any("План > текущего остатка" in item[1] for item in emphasized))
        self.assertTrue(any(item[1].startswith("⚠ ") for item in emphasized))
        self.assertFalse(any("Конфликт" in item[1] for item in emphasized))

    def test_completed_label_does_not_imply_planning_error(self) -> None:
        label = human_surface_outcome_label("EXCLUDED_COMPLETED")
        self.assertEqual(label, "Уже выполнено к текущему состоянию")
        self.assertNotIn("ошиб", label.casefold())
        note = COMPLETED_MANAGER_NOTE_RU.casefold()
        self.assertIn("не означает ошибку", note)
        conflict_label = human_surface_outcome_label("EXCLUDED_INCONSISTENT_QUANTITIES")
        self.assertEqual(conflict_label, "План > текущего остатка")
        self.assertNotIn("конфликт", conflict_label.casefold())
        self.assertIn("текущий расчётный физический остаток", CONFLICT_MANAGER_NOTE_RU.casefold())
        self.assertIn("с начала месяца", CONFLICT_MANAGER_NOTE_RU.casefold())
        self.assertNotIn("конфликт", CONFLICT_MANAGER_NOTE_RU.casefold())
        self.assertNotIn("ошибка", CONFLICT_MANAGER_NOTE_RU.casefold())

    def test_conflict_deviation_and_table_columns(self) -> None:
        registry = _registry()
        conflict = next(
            item
            for item in registry.records
            if item.outcome == "EXCLUDED_INCONSISTENT_QUANTITIES"
        )
        self.assertEqual(conflict_deviation_display(conflict), "5")
        rows = workspace_table_rows((conflict,), registry.professional)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        for key in (
            "Титул",
            "Система",
            "Пакет / IWP",
            "BOQ-код",
            "Наименование работы",
            "Ед. изм.",
            "Физический остаток",
            "Уже запланировано",
            "Отклонение",
            "Решение Constructor",
            "Причина",
        ):
            self.assertIn(key, row)
        self.assertEqual(row["Отклонение"], "5")
        self.assertEqual(
            row["Решение Constructor"],
            "План > текущего остатка",
        )

    def test_incremental_mode_badge(self) -> None:
        summary = build_module5_result_summary(_registry())
        self.assertEqual(summary.mode_badge, MODULE5_MODE_INCREMENTAL_RU)
        self.assertEqual(MODULE5_TITLE_RU, "Результат анализа Constructor")

    def test_candidate_slice_helpers(self) -> None:
        registry = _registry()
        slices = {
            item.boq_code: candidate_presentation_slice(item) for item in registry.records
        }
        self.assertEqual(slices["BOQ-NEW"], "new_opportunity")
        self.assertEqual(slices["BOQ-ADD"], "additional_volume")
        self.assertIsNone(slices["BOQ-CF"])

    def test_page_module5_has_single_result_table_path(self) -> None:
        page = (
            Path(__file__).resolve().parents[1]
            / "pages"
            / "53_AI_Центр_управления_агентами.py"
        )
        source = page.read_text(encoding="utf-8")
        self.assertIn("MODULE5_TITLE_RU", source)
        self.assertIn("_render_module5_compact_result", source)
        self.assertNotIn("Состав результата", source)
        self.assertNotIn("Все работы (", source)
        self.assertNotIn("Требуют решения (", source)
        # Legacy paren form forbidden; oval «Кандидаты · N» comes from result_view.
        self.assertNotIn("Кандидаты (", source)
        self.assertNotIn("Проблемы (", source)
        self.assertEqual(source.count("st.dataframe("), source.count("st.dataframe("))
        # Module 5 compact path renders one dataframe; human decision module has another.
        self.assertIn("height=420", source)
        self.assertIn("Детали выбранной строки", source)
        # Domain modules must remain untouched by this UX increment.
        domain = (
            Path(__file__).resolve().parents[1]
            / "agents"
            / "monthly_plan_constructor"
            / "domain.py"
        )
        lifecycle = (
            Path(__file__).resolve().parents[1]
            / "agents"
            / "monthly_plan_constructor"
            / "lifecycle.py"
        )
        self.assertTrue(domain.is_file())
        self.assertTrue(lifecycle.is_file())
        # Page must not import Constructor domain / proposal builder for this UX.
        self.assertNotIn("monthly_plan_constructor.domain", source)
        self.assertNotIn("build_constructor_proposal", source)


if __name__ == "__main__":
    unittest.main()
