"""Work-context catalog uses the monthly planning scope, not invented rows."""

from __future__ import annotations

import unittest

import pandas as pd

from agents.human_surface.mission_draft import (
    apply_global_command,
    empty_working_context,
    parse_global_command,
)
from agents.human_surface.work_context import (
    PACKAGES_UNAVAILABLE_RU,
    catalog_from_frame,
    align_working_context,
    queue_from_facility,
    selector_options,
)


def _scope() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "project_code": "PRJ_001_БХК",
                "facility_building": "16160-13",
                "construction_discipline": "ВЕНТИЛЯЦИЯ",
                "system_label": "П1, П2",
                "iwp_id": "",
            },
            {
                "project_code": "PRJ_001_БХК",
                "facility_building": "16160-17",
                "construction_discipline": "ВЕНТИЛЯЦИЯ",
                "system_label": "П3, В2, В6, В8",
                "iwp_id": None,
            },
            {
                "project_code": "PRJ_001_БХК",
                "facility_building": "26160-13",
                "construction_discipline": "Электрика",
                "system_label": "Э1",
                "iwp_id": "",
            },
            {
                "project_code": "PRJ_001_БХК",
                "facility_building": "26160-17",
                "construction_discipline": "Электрика",
                "system_label": "Э2",
                "iwp_id": "",
            },
            {
                "project_code": "БХК",
                "facility_building": "Титул без очереди",
                "construction_discipline": "Отопление",
                "system_label": "",
                "iwp_id": "",
            },
        ]
    )


class WorkContextCatalogTests(unittest.TestCase):
    def test_empty_scope_keeps_months_and_disables_missing_sources(self) -> None:
        catalog = catalog_from_frame(pd.DataFrame())
        options = selector_options(catalog)
        self.assertEqual(options.months[0], "январь 2026")
        self.assertIn("ноябрь 2026", options.months)
        self.assertEqual(options.projects, ())
        self.assertEqual(options.queues, ())
        self.assertEqual(options.titles, ())
        self.assertEqual(options.systems, ())
        self.assertEqual(options.packages, ())
        self.assertFalse(catalog.packages_available)
        self.assertIn("недоступны", PACKAGES_UNAVAILABLE_RU)

    def test_scope_rows_drive_project_queue_title_and_systems(self) -> None:
        catalog = catalog_from_frame(_scope())
        self.assertTrue(catalog.projects_available)
        self.assertFalse(catalog.packages_available)
        self.assertEqual(queue_from_facility("16160-13"), "1")
        self.assertEqual(queue_from_facility("Титул без очереди"), "")
        options = selector_options(catalog, project="БХК", queue="1")
        self.assertEqual(options.projects, ("БХК",))
        self.assertEqual(options.queues, ("1", "2"))
        self.assertEqual(options.titles, ("16160-13", "16160-17"))
        self.assertNotIn("13", options.titles)
        self.assertNotIn("17", options.titles)
        self.assertEqual(
            selector_options(catalog, project="БХК", queue="2").titles,
            ("26160-13", "26160-17"),
        )
        self.assertEqual(
            selector_options(catalog, project="БХК").titles,
            ("16160-13", "16160-17", "26160-13", "26160-17"),
        )
        self.assertIn("Вентиляция", options.disciplines)
        self.assertNotIn("Электрика", options.disciplines)
        narrowed = selector_options(
            catalog,
            project="БХК",
            queue="1",
            titles=("16160-13", "16160-17"),
            discipline="Вентиляция",
        )
        self.assertEqual(narrowed.systems, ("П1", "П2", "П3", "В2", "В6", "В8"))
        self.assertNotIn("Э1", narrowed.systems)
        self.assertEqual(narrowed.packages, ())

    def test_ok_apply_uses_the_same_context_and_parse_does_not(self) -> None:
        catalog = catalog_from_frame(_scope())
        current = empty_working_context()
        draft = parse_global_command(
            "БХК, ноябрь 2026, первая очередь, титулы 13 и 17, вентиляция, "
            "П1 П2 П3 В2 В6 В8. "
            "Работаем в контуре месячного производственного обязательства. "
            "Привлечь инженера формирования месячного плана. "
            "Остальные системы в ноябрь не включать."
        )
        self.assertIsNone(current.project)
        self.assertEqual(current.titles, ())
        alignment = align_working_context(apply_global_command(current, draft), catalog)
        applied = alignment.context
        self.assertEqual(alignment.messages, ())
        self.assertEqual(applied.project, "БХК")
        self.assertEqual(applied.planning_month, "ноябрь 2026")
        self.assertEqual(applied.queue, "1")
        self.assertEqual(applied.titles, ("16160-13", "16160-17"))
        self.assertEqual(applied.discipline, "Вентиляция")
        self.assertEqual(applied.systems, ("П1", "П2", "П3", "В2", "В6", "В8"))
        self.assertIsNone(applied.packages)
        self.assertEqual(applied.agent_code, "MONTHLY_PLAN_CONSTRUCTOR")
        self.assertEqual(applied.contour_code, "MONTHLY_PRODUCTION_COMMITMENT")

    def test_short_title_alias_follows_queue_and_fails_closed_without_it(self) -> None:
        catalog = catalog_from_frame(_scope())
        current = empty_working_context()
        queue_one = parse_global_command("БХК, октябрь 2026, очередь 1, титул 13")
        resolved = align_working_context(apply_global_command(current, queue_one), catalog)
        self.assertEqual(resolved.context.titles, ("16160-13",))
        self.assertEqual(resolved.messages, ())
        queue_two = parse_global_command("БХК, октябрь 2026, очередь 2, титул 13")
        resolved_two = align_working_context(apply_global_command(current, queue_two), catalog)
        self.assertEqual(resolved_two.context.titles, ("26160-13",))
        ambiguous = parse_global_command("БХК, октябрь 2026, титулы 13 и 17")
        blocked = align_working_context(apply_global_command(current, ambiguous), catalog)
        self.assertEqual(blocked.context.titles, ())
        self.assertEqual(
            blocked.messages,
            ("Для титулов 13 и 17 необходимо определить очередь.",),
        )


if __name__ == "__main__":
    unittest.main()
