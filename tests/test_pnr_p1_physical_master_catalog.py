"""P-1 Physical Master Catalog Level 1 tests. No live Supabase writes."""

from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path
from typing import Any
from uuid import UUID

from services import pnr_p1_physical_master_catalog as catalog
from services.pnr_left_execution_hierarchy import reset_dependent_selections
from services.pnr_p1_engineering_context import SECTION_TITLES

CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "pnr_p1_physical_master_catalog.py"
)
PAGE_PATH = (
    Path(__file__).resolve().parents[1] / "pages" / "60_ПНР_Фиксация_факта.py"
)
PASSPORT_PATH = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "pnr_p1_engineering_context.py"
)


class Level1CatalogContractTests(unittest.TestCase):
    def test_system_code_is_p1(self) -> None:
        self.assertEqual(catalog.system_code(), "П-1")
        self.assertTrue(all(item.system_code == "П-1" for item in catalog.contours()))

    def test_exactly_four_contours_in_approved_order(self) -> None:
        contours = catalog.contours()
        self.assertEqual(len(contours), 4)
        self.assertEqual(
            [item.contour_name for item in contours],
            [
                "Воздушный контур",
                "Тепловой контур",
                "Холодильный контур",
                "Автоматизация и электромеханика",
            ],
        )
        self.assertEqual([item.sort_order for item in contours], [1, 2, 3, 4])
        self.assertEqual(
            [catalog.contour_label(item) for item in contours],
            [
                "01. Воздушный контур",
                "02. Тепловой контур",
                "03. Холодильный контур",
                "04. Автоматизация и электромеханика",
            ],
        )

    def test_air_has_eight_approved_classes(self) -> None:
        names = [item.class_name for item in catalog.object_classes_for(catalog.CONTOUR_AIR)]
        self.assertEqual(
            names,
            [
                "Воздухозабор / выброс",
                "Установка",
                "Воздуховоды",
                "Фасонные элементы",
                "Клапаны",
                "Шумоглушители",
                "Воздухораспределители",
                "Обслуживаемая физическая среда",
            ],
        )
        self.assertEqual(len(names), 8)

    def test_thermal_has_six_approved_classes(self) -> None:
        names = [
            item.class_name
            for item in catalog.object_classes_for(catalog.CONTOUR_THERMAL)
        ]
        self.assertEqual(
            names,
            [
                "Источник / граница подключения",
                "ИТП / узел регулирования",
                "Трубопроводы",
                "Насосы",
                "Арматура",
                "Нагреватель",
            ],
        )
        self.assertEqual(len(names), 6)

    def test_refrigeration_has_ten_approved_classes_and_is_visible(self) -> None:
        refrigeration = catalog.contour_by_code(catalog.CONTOUR_REFRIGERATION)
        self.assertIsNotNone(refrigeration)
        assert refrigeration is not None
        names = [item.class_name for item in refrigeration.object_classes]
        self.assertEqual(
            names,
            [
                "Источник холода / холодильная машина",
                "Компрессор",
                "Конденсатор",
                "Испаритель / воздухоохладитель",
                "Фреоновые трубопроводы",
                "Жидкостная линия",
                "Газовая линия",
                "Дренаж конденсата",
                "Арматура",
                "Холодильный агент",
            ],
        )
        self.assertEqual(len(names), 10)
        self.assertIn(refrigeration, catalog.contours())

    def test_automation_em_has_eight_approved_classes(self) -> None:
        names = [
            item.class_name
            for item in catalog.object_classes_for(catalog.CONTOUR_AUTOMATION_EM)
        ]
        self.assertEqual(
            names,
            [
                "ШСАУ",
                "Силовое питание",
                "Преобразователи частоты",
                "Электродвигатели",
                "Датчики",
                "Исполнительные механизмы",
                "Кабельные / сигнальные связи",
                "Верхний уровень управления",
            ],
        )
        self.assertEqual(len(names), 8)

    def test_total_level1_entries_is_32(self) -> None:
        self.assertEqual(len(catalog.all_object_classes()), 32)
        self.assertEqual(sum(len(item.object_classes) for item in catalog.contours()), 32)

    def test_no_applicability_logic(self) -> None:
        source = CATALOG_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "NOT_APPLICABLE",
            "APPLICABLE",
            "required / optional",
            "present / absent",
            "enabled / disabled",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("not_applicable", source.lower())

    def test_system_contour_class_instance_are_distinct(self) -> None:
        contours = catalog.contours()
        classes = catalog.all_object_classes()
        contour_codes = {item.contour_code for item in contours}
        class_codes = {item.class_code for item in classes}
        self.assertNotIn("П-1", contour_codes)
        self.assertNotIn("П-1", class_codes)
        self.assertTrue(contour_codes.isdisjoint(class_codes))
        self.assertFalse(catalog.is_level1_class_code(catalog.SYSTEM_CODE))
        self.assertFalse(catalog.is_level1_class_code(catalog.CONTOUR_AIR))
        self.assertTrue(catalog.is_level1_contour_code(catalog.CONTOUR_REFRIGERATION))
        joined = " ".join(item.class_name for item in classes)
        self.assertNotIn("П1.1 / 795-U-030A", joined)
        self.assertNotIn("П1.2 / 795-U-030B", joined)
        self.assertNotIn("A132M4F", joined)
        catalog_source = CATALOG_PATH.read_text(encoding="utf-8")
        self.assertNotIn("proto:", catalog_source)

    def test_unknown_contour_returns_no_classes(self) -> None:
        self.assertEqual(catalog.object_classes_for("unknown-contour"), ())
        self.assertEqual(catalog.object_classes_for(None), ())

    def test_contour_change_resets_stale_class_child(self) -> None:
        air_unit = next(
            item.class_code
            for item in catalog.object_classes_for(catalog.CONTOUR_AIR)
            if item.class_name == "Установка"
        )
        thermal_classes = {
            item.class_code for item in catalog.object_classes_for(catalog.CONTOUR_THERMAL)
        }
        self.assertNotIn(air_unit, thermal_classes)
        state: dict[str, Any] = {
            catalog.SESSION_TRACK_P1_L1_CONTOUR: catalog.CONTOUR_AIR,
            catalog.WIDGET_P1_L1_CLASS: air_unit,
        }
        changed = reset_dependent_selections(
            state,
            tracker_key=catalog.SESSION_TRACK_P1_L1_CONTOUR,
            parent_value=catalog.CONTOUR_THERMAL,
            child_keys=catalog.CHILD_KEYS_AFTER_P1_L1_CONTOUR,
        )
        self.assertTrue(changed)
        self.assertNotIn(catalog.WIDGET_P1_L1_CLASS, state)
        remaining = catalog.object_classes_for(catalog.CONTOUR_THERMAL)
        self.assertTrue(all(item.class_name != "Установка" for item in remaining))

    def test_class_code_is_not_a_uuid(self) -> None:
        for item in catalog.all_object_classes():
            with self.assertRaises(ValueError):
                UUID(item.class_code)

    def test_catalog_has_no_uuid_generation_or_runtime_deps(self) -> None:
        source = CATALOG_PATH.read_text(encoding="utf-8")
        self.assertNotIn("uuid4", source)
        self.assertNotIn("import uuid", source)
        self.assertNotIn("from uuid", source)
        self.assertNotIn("create_client", source)
        self.assertNotIn("SUPABASE", source)
        self.assertNotIn("import streamlit", source)
        self.assertNotIn("from streamlit", source)
        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        self.assertEqual(imported, {"__future__", "dataclasses"})
        self.assertNotIn("streamlit", imported)
        self.assertNotIn("supabase", imported)
        self.assertNotIn("uuid", imported)
        self.assertNotIn("fuzzy", inspect.getsource(catalog.object_classes_for).lower())


class Page60Level1WiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = PAGE_PATH.read_text(encoding="utf-8")

    def test_page_uses_catalog_without_replacing_instance_identity(self) -> None:
        self.assertIn("pnr_p1_physical_master_catalog", self.source)
        self.assertIn("WIDGET_P1_L1_CLASS", self.source)
        self.assertIn("WIDGET_P1_L1_CONTOUR", self.source)
        self.assertIn('key="pnr_physical_selection"', self.source)
        self.assertIn(
            "object_id = None if prototype_selected else str(physical_selection)",
            self.source,
        )
        self.assertNotIn("object_id=class_code", self.source)
        self.assertNotIn("object_id=str(class_code)", self.source)
        self.assertNotIn("physical_selection = class_code", self.source)
        self.assertNotIn("pnr_physical_selection\"] = ", self.source)

    def test_write_contract_still_uses_physical_selection(self) -> None:
        self.assertIn(
            "if submitted and structured_write_permitted(str(physical_selection)):",
            self.source,
        )
        self.assertIn("object_id=str(object_id)", self.source)
        self.assertNotIn("object_id=str(level1_class_code)", self.source)
        self.assertNotIn("functional_position_id=class_code", self.source)
        kwargs_call = self.source.split("kwargs = build_structured_kwargs(", 1)[1]
        kwargs_call = kwargs_call.split("fingerprint = submit_fingerprint(kwargs)", 1)[0]
        self.assertIn("object_id=str(object_id)", kwargs_call)
        self.assertNotIn("WIDGET_P1_L1_CLASS", kwargs_call)
        self.assertNotIn("class_code", kwargs_call)

    def test_passport_sections_unchanged(self) -> None:
        self.assertEqual(len(SECTION_TITLES), 12)
        self.assertIn("_render_p1_passport", self.source)
        passport = PASSPORT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("pnr_p1_physical_master_catalog", passport)


if __name__ == "__main__":
    unittest.main()
