"""
P-1 Engineering Context Passport v0.2 tests. No live Supabase writes.

Run:
  python -m unittest tests.test_pnr_p1_engineering_context -v
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from services import pnr_p1_engineering_context as ctx

HELPER_PATH = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "pnr_p1_engineering_context.py"
)
PAGE_PATH = (
    Path(__file__).resolve().parents[1] / "pages" / "60_ПНР_Фиксация_факта.py"
)


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
    return names


class PassportModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = HELPER_PATH.read_text(encoding="utf-8")

    def test_five_tabs_and_twelve_sections(self) -> None:
        self.assertEqual(
            ctx.PASSPORT_TABS,
            (
                "Обзор",
                "Физическая система",
                "Функциональная логика",
                "Источники",
                "Конфликты",
            ),
        )
        self.assertEqual(len(ctx.SECTION_TITLES), 12)
        self.assertEqual(
            ctx.SECTION_TITLES["01"], "01. Идентификация системы"
        )
        self.assertEqual(
            ctx.SECTION_TITLES["02"], "02. Назначение и функциональная граница"
        )
        self.assertEqual(
            ctx.SECTION_TITLES["03"],
            "03. Обслуживаемые помещения и физические зоны",
        )
        self.assertEqual(
            ctx.SECTION_TITLES["04"],
            "04. Физическая среда и функциональный поток",
        )
        self.assertEqual(
            ctx.SECTION_TITLES["05"],
            "05. Проектные характеристики и требуемые режимы",
        )
        self.assertEqual(
            ctx.SECTION_TITLES["06"],
            "06. Операционный граф физических объектов системы П-1",
        )
        self.assertEqual(
            ctx.SECTION_TITLES["07"],
            "07. Энергетические и технологические контуры",
        )
        self.assertEqual(
            ctx.SECTION_TITLES["08"],
            "08. Автоматизация и функциональная логика",
        )
        self.assertEqual(
            ctx.SECTION_TITLES["09"],
            "09. Внешние интерфейсы и зависимости",
        )
        self.assertEqual(
            ctx.SECTION_TITLES["10"],
            "10. Источники, ревизии и происхождение данных",
        )
        self.assertEqual(
            ctx.SECTION_TITLES["11"],
            "11. Конфликты, неопределённость и отсутствующий контекст",
        )
        self.assertEqual(
            ctx.SECTION_TITLES["12"], "12. Документальная модель системы"
        )

    def test_purpose_and_served_spaces(self) -> None:
        purpose = " ".join(fact.value for fact in ctx.PURPOSE_FACTS)
        self.assertIn(
            "П-1 обеспечивает приточную механическую вентиляцию помещения компрессоров",
            purpose,
        )
        self.assertIn("рабочую зону помещения компрессоров", purpose)
        self.assertIn("маслохозяйства", purpose)
        names = [space["name"] for space in ctx.SERVED_SPACES]
        self.assertEqual(
            names, ["Помещение компрессоров", "Маслохозяйство"]
        )
        compressor = ctx.SERVED_SPACES[0]
        self.assertEqual(compressor["supply"].value, "рабочая зона")
        self.assertEqual(compressor["internal_temperature"].value, "+10 °C")
        oil = ctx.SERVED_SPACES[1]
        self.assertEqual(oil["internal_temperature"].value, "+10 °C")
        self.assertNotIn("supply", oil)

    def test_physical_medium_and_functional_flow(self) -> None:
        self.assertEqual(ctx.PHYSICAL_MEDIUM.value, "ВОЗДУХ")
        self.assertEqual(ctx.FUNCTIONAL_FLOW_TRUNK[0], "НАРУЖНЫЙ ВОЗДУХ")
        self.assertIn("ПРИТОЧНАЯ УСТАНОВКА П-1", ctx.FUNCTIONAL_FLOW_TRUNK)
        self.assertEqual(ctx.FUNCTIONAL_FLOW_COMPRESSOR, "ПОМЕЩЕНИЕ КОМПРЕССОРОВ")
        self.assertEqual(ctx.FUNCTIONAL_FLOW_OIL, "МАСЛОХОЗЯЙСТВО")
        self.assertEqual(ctx.FUNCTIONAL_FLOW_WORKING_ZONE, "РАБОЧАЯ ЗОНА")
        self.assertIn(ctx.FUNCTIONAL_FLOW_COMPRESSOR, ctx.AIR_FLOW_CHAIN)
        self.assertIn(ctx.FUNCTIONAL_FLOW_OIL, ctx.AIR_FLOW_CHAIN)
        self.assertEqual(
            ctx.FLOW_NOT_ROUTING_CAPTION,
            "Функциональная схема потока. Не является подтверждённой трассировкой воздуховодов.",
        )
        html = ctx.functional_flow_html()
        self.assertIn("ПОМЕЩЕНИЕ КОМПРЕССОРОВ", html)
        self.assertIn("МАСЛОХОЗЯЙСТВО", html)
        self.assertIn("РАБОЧАЯ ЗОНА", html)

    def test_design_context_and_provenance(self) -> None:
        values = {label: fact.value for label, fact in ctx.DESIGN_FACTS}
        self.assertEqual(values["Расход воздуха"], "18 515 м³/ч")
        self.assertEqual(values["Давление"], "1034 Па")
        self.assertEqual(values["Мощность электродвигателя"], "11,0 кВт")
        self.assertEqual(values["Температура воздуха после нагрева"], "+10 °C")
        self.assertEqual(values["Тепловая мощность"], "334 900 Вт")
        self.assertNotIn("Расчётная наружная температура", values)
        for _label, fact in ctx.DESIGN_FACTS:
            self.assertEqual(fact.source_document, ctx.DSS_CODE)
            self.assertEqual(fact.revision, ctx.DSS_REV)
            self.assertIsNone(fact.source_location)
        climate = {label: fact.value for label, fact in ctx.CLIMATE_FACTS}
        self.assertEqual(climate["Расчётная наружная температура"], "−44 °C")
        self.assertEqual(climate["Тёплый период"], "+13 °C")
        self.assertEqual(
            climate["Средняя температура отопительного периода"], "−11,6 °C"
        )
        self.assertEqual(
            climate["Продолжительность отопительного периода"], "344 дня"
        )

    def test_physical_graph_heading_and_p11_ownership(self) -> None:
        self.assertEqual(
            ctx.GRAPH_TITLE,
            "Операционный граф физических объектов системы П-1",
        )
        text = "\n".join(ctx.PHYSICAL_GRAPH_LINES)
        self.assertTrue(text.startswith("П-1"))
        self.assertIn("П1.1 / 795-U-030A [РАБОЧАЯ]", text)
        self.assertIn("ВЕРОСА-500-194-02-61-УХЛ3", text)
        self.assertIn("ШСАУ П1.1", text)
        self.assertIn("Блочный ИТП П1.1", text)
        self.assertIn("П1.2 / 795-U-030B [РЕЗЕРВНАЯ]", text)
        p11 = text.split("П1.2 / 795-U-030B [РЕЗЕРВНАЯ]", 1)[0]
        self.assertIn("ВЕРОСА-500-194-02-61-УХЛ3", p11)
        self.assertIn("ШСАУ П1.1", p11)
        self.assertIn("Блочный ИТП П1.1", p11)
        p12 = text.split("П1.2 / 795-U-030B [РЕЗЕРВНАЯ]", 1)[1]
        self.assertNotIn("ВЕРОСА", p12)
        self.assertNotIn("Фильтр G4", p12)

    def test_three_energy_flows(self) -> None:
        self.assertEqual(ctx.AIR_CONTOUR[0], "Наружный воздух")
        self.assertIn("обслуживаемые помещения", ctx.AIR_CONTOUR)
        self.assertEqual(
            ctx.THERMAL_CONTOUR[0],
            "Блочно-модульная водогрейная котельная УКПГ-2",
        )
        self.assertIn("45% пропиленгликоль", ctx.THERMAL_CONTOUR)
        self.assertEqual(ctx.ELECTROMECHANICAL_CONTOUR[0], "Электроснабжение")
        self.assertIn("перемещение воздуха", ctx.ELECTROMECHANICAL_CONTOUR)

    def test_automation_and_external_relations(self) -> None:
        standby = " ".join(ctx.AUTOMATION_STANDBY)
        self.assertIn("П1.1 — рабочая", standby)
        self.assertIn("П1.2 — резервная", standby)
        self.assertIn("автоматический запуск резервной", standby)
        functions = " ".join(ctx.AUTOMATION_FUNCTIONS)
        self.assertIn("два ШСАУ", functions)
        self.assertIn("защит", functions)
        self.assertEqual(ctx.FIRE_STOP_CHAIN[-1], "останов П-1")
        self.assertIn("Электроснабжение", ctx.EXTERNAL_DEPENDENCIES)
        self.assertIn("Пожарная автоматика", ctx.EXTERNAL_DEPENDENCIES)
        related = dict(ctx.RELATED_VENTILATION)
        self.assertIn("В1", related)
        self.assertIn("В2", related)
        self.assertIn("АВ1 / АВ2", related)
        self.assertIn("ПЕ1 / ПЕ2", related)
        graph = "\n".join(ctx.PHYSICAL_GRAPH_LINES)
        self.assertNotIn("АВ1", graph)

    def test_source_register_and_document_model(self) -> None:
        families = [row.family for row in ctx.SOURCE_REGISTER]
        self.assertEqual(families, ["DSS", "DTS", "REQ", "MTO"])
        dss = ctx.SOURCE_REGISTER[0]
        self.assertEqual(dss.code, "2400-R-NG-795-MH-DSS-0015-00")
        self.assertEqual(dss.revision, "06C")
        self.assertEqual(dss.dated, "29.08.2023")
        dts = ctx.SOURCE_REGISTER[1]
        self.assertEqual(dts.code, "2400-R-NG-795-MH-DTS-0033-00")
        self.assertEqual(dts.revision, "01D")
        self.assertEqual(dts.dated, "25.12.2020")
        req = ctx.SOURCE_REGISTER[2]
        self.assertEqual(req.code, "2400-R-NG-795-MH-REQ-0033-00")
        self.assertIsNone(req.revision)
        mto = ctx.SOURCE_REGISTER[3]
        self.assertEqual(mto.code, "2400-R-NG-795-MH-MTO-0018-00")
        self.assertEqual(mto.revision, "04C")
        self.assertEqual(
            ctx.SOURCE_DOCUMENT_FAMILIES, ("DSS", "DTS", "REQ", "MTO")
        )
        self.assertIn("сведения отсутствуют", ctx.DOC_EXECUTION_NOT_FORMED)
        self.assertEqual(ctx.DOC_READINESS_NOT_CALCULATED, "не определена")

    def test_dss_dts_conflict_has_no_winner(self) -> None:
        conflict = ctx.CONFLICT_P1_PARAMETERS
        self.assertEqual(conflict.code, "КОНФЛИКТ 01")
        self.assertEqual(conflict.title, "Параметры П-1")
        self.assertIn("18 515 м³/ч", conflict.left_values)
        self.assertIn("1034 Па", conflict.left_values)
        self.assertIn("18 515 × 1,06 = 19 625 м³/ч", conflict.right_values)
        self.assertIn("800 Па", conflict.right_values)
        self.assertEqual(
            conflict.status, "КОНФЛИКТ / ТРЕБУЕТ ИНЖЕНЕРНОЙ ПРОВЕРКИ"
        )
        missing = " ".join(ctx.MISSING_CONTEXT)
        self.assertIn("актуальные контролируемые ревизии", missing)
        self.assertIn("подтверждённая идентификация отдельных компонентов П1.1", missing)
        self.assertIn("детализированный состав П1.2", missing)
        self.assertIn("точная трасса воздуховодов", missing)
        self.assertIn("часть паспортных характеристик оборудования", missing)
        self.assertEqual(len(ctx.MISSING_CONTEXT), 5)

    def test_no_required_work_execution_event_or_db(self) -> None:
        imported = _imported_modules(self.source)
        self.assertNotIn("services.pnr_p1_slice_prototype", imported)
        self.assertNotIn("services.pnr_service", imported)
        self.assertNotIn("supabase", imported)
        forbidden = (
            "RW-MOTOR",
            "required_works_for",
            "create_structured_execution_event",
            "supabase",
            "create_client",
            "uuid4",
            "uuid.uuid4",
            "psycopg",
        )
        for token in forbidden:
            self.assertNotIn(token, self.source)
        self.assertNotIn("open(", self.source)

    def test_identification_and_header(self) -> None:
        self.assertEqual(ctx.PASSPORT_TITLE, "Паспорт инженерного контекста системы П-1")
        self.assertEqual(ctx.NAV_TITLE, "Навигация по физической системе")
        self.assertEqual(ctx.CANONICAL_SYSTEM_LABEL, "П-1")
        self.assertTrue(ctx.is_p1_system_context("П-1"))
        self.assertFalse(ctx.is_p1_system_context("P1"))
        labels = {label for label, _fact in ctx.IDENTIFICATION_FACTS}
        self.assertIn("Проект", labels)
        self.assertIn("Титул", labels)
        self.assertIn("Система", labels)
        values = {label: fact.value for label, fact in ctx.IDENTIFICATION_FACTS}
        self.assertEqual(values["Система"], "П-1")
        self.assertEqual(values["Рабочая установка"], "П1.1 / 795-U-030A")
        self.assertEqual(values["Резервная установка"], "П1.2 / 795-U-030B")
        self.assertEqual(values["Основное оборудование"], "ВЕРОСА-500-194-02-61-УХЛ3")
        self.assertEqual(
            values["Схема"], "рабочая + резервная / 100% резервирование"
        )
        self.assertIn("Помещение компрессоров", ctx.HEADER_SERVES)
        self.assertIn("Маслохозяйство", ctx.HEADER_SERVES)
        self.assertEqual(ctx.HEADER_CONFIGURATION, "100% резервирование")

    def test_per_fact_provenance_is_preserved(self) -> None:
        for _label, fact in ctx.IDENTIFICATION_FACTS:
            self.assertTrue(hasattr(fact, "source_document"))
            self.assertTrue(hasattr(fact, "revision"))
            self.assertTrue(hasattr(fact, "source_location"))
            self.assertTrue(hasattr(fact, "authority_status"))
            self.assertTrue(hasattr(fact, "verification_status"))
            self.assertIsNone(fact.source_location)
        for _label, fact in ctx.DESIGN_FACTS + ctx.CLIMATE_FACTS:
            self.assertIsNone(fact.source_location)
            self.assertEqual(fact.source_document, ctx.DSS_CODE)

    def test_source_attribution_audit_not_all_dss(self) -> None:
        by_label = {label: fact for label, fact in ctx.IDENTIFICATION_FACTS}
        self.assertEqual(by_label["Система"].source_document, ctx.DSS_CODE)
        self.assertEqual(by_label["Система"].authority_status, ctx.STATUS_CONFIRMED)
        self.assertEqual(by_label["Рабочая установка"].source_document, ctx.DTS_CODE)
        self.assertEqual(
            by_label["Рабочая установка"].verification_status,
            ctx.STATUS_REVISION_CHECK,
        )
        self.assertEqual(by_label["Резервная установка"].source_document, ctx.DTS_CODE)
        self.assertEqual(by_label["Основное оборудование"].source_document, ctx.REQ_CODE)
        self.assertEqual(
            by_label["Основное оборудование"].verification_status,
            ctx.STATUS_REVISION_CHECK,
        )
        self.assertIsNone(by_label["Схема"].source_document)
        self.assertEqual(
            by_label["Схема"].verification_status, ctx.STATUS_REVISION_CHECK
        )

    def test_mixed_provenance_cannot_share_one_source(self) -> None:
        all_facts = [fact for _label, fact in ctx.IDENTIFICATION_FACTS]
        self.assertIsNone(ctx.shared_provenance(all_facts))
        groups = ctx.group_consecutive_by_provenance(ctx.IDENTIFICATION_FACTS)
        self.assertGreater(len(groups), 1)
        sources = {fact.source_document for _label, fact in ctx.IDENTIFICATION_FACTS}
        self.assertIn(ctx.DSS_CODE, sources)
        self.assertIn(ctx.DTS_CODE, sources)
        self.assertIn(ctx.REQ_CODE, sources)
        dss_only = [
            fact
            for _label, fact in ctx.IDENTIFICATION_FACTS
            if fact.source_document == ctx.DSS_CODE
        ]
        shared = ctx.shared_provenance(dss_only)
        self.assertIsNotNone(shared)
        self.assertEqual(shared.source_document, ctx.DSS_CODE)
        caption = ctx.format_provenance_caption(dss_only[0])
        self.assertTrue(caption.startswith("Источник: "))
        self.assertIn("DSS-0015-00", caption)
        self.assertIn("рев. 06C", caption)

    def test_product_language_has_no_internal_development_wording(self) -> None:
        visible = "\n".join(
            [
                ctx.GRAPH_NOT_REGISTRY_CAPTION,
                ctx.DOC_EXECUTION_NOT_FORMED,
                ctx.DOC_READINESS_NOT_CALCULATED,
                ctx.RELATED_NOT_CHILDREN,
                ctx.PASSPORT_REQUIRES_P1_CONTEXT,
                ctx.PASSPORT_NOT_OBJECT_CAPTION,
                ctx.FLOW_NOT_ROUTING_CAPTION,
                *ctx.MISSING_CONTEXT,
            ]
        )
        for forbidden in (
            "Read-only engineering context",
            "persist",
            "increment",
            "children",
            "Engineering Context prototype",
            "prototype",
        ):
            self.assertNotIn(forbidden, visible)
        self.assertEqual(
            ctx.GRAPH_NOT_REGISTRY_CAPTION,
            "Статус модели: предварительная инженерная структура. "
            "Идентификация отдельных физических объектов требует подтверждения.",
        )
        self.assertIn("не входят в её состав", ctx.RELATED_NOT_CHILDREN)

    def test_source_status_not_duplicated_when_identical(self) -> None:
        same = ctx.format_status_text(
            ctx.STATUS_CONFIRMED, ctx.STATUS_CONFIRMED
        )
        self.assertEqual(same, ctx.STATUS_CONFIRMED)
        self.assertEqual(same.count(ctx.STATUS_CONFIRMED), 1)
        different = ctx.format_status_text(
            ctx.STATUS_CONFIRMED, ctx.STATUS_REVISION_CHECK
        )
        self.assertIn("Статус источника:", different)
        self.assertIn("Статус проверки:", different)
        caption = ctx.format_provenance_caption(ctx.DESIGN_FACTS[0][1])
        self.assertEqual(caption.count(ctx.STATUS_CONFIRMED), 1)


class Page60PassportWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = PAGE_PATH.read_text(encoding="utf-8")

    def test_page_uses_passport_not_slice_right_panel(self) -> None:
        self.assertIn('st.columns([3, 7], gap="large")', self.source)
        self.assertIn("st.tabs(list(PASSPORT_TABS))", self.source)
        self.assertIn("SECTION_TITLES", self.source)
        self.assertIn("_render_kv_groups", self.source)
        self.assertIn("group_consecutive_by_provenance", self.source)
        self.assertIn("shared_provenance", self.source)
        self.assertIn("PASSPORT_CONTEXT_HEADING", self.source)
        self.assertIn("SELECTED_OBJECT_HEADING", self.source)
        self.assertIn("functional_flow_html", self.source)
        self.assertIn("FLOW_NOT_ROUTING_CAPTION", self.source)
        self.assertNotIn("_render_engineering_fact", self.source)
        self.assertNotIn(
            "{fact.source_document} · {fact.revision} · {fact.authority_status}",
            self.source,
        )
        self.assertIn("_render_passport_overview", self.source)
        self.assertIn("_render_passport_physical", self.source)
        self.assertIn("_render_passport_logic", self.source)
        self.assertIn("_render_passport_sources", self.source)
        self.assertIn("_render_passport_conflicts", self.source)
        self.assertIn("_render_bullet_list", self.source)
        self.assertIn("format_status_text", self.source)
        self.assertNotIn(
            "{record.authority_status} · {record.verification_status}",
            self.source,
        )
        self.assertIn(
            "st.expander(EXECUTION_EXPANDER_TITLE, expanded=False)",
            self.source,
        )
        write_block = self.source.split(
            "create_structured_execution_event(**kwargs)", 1
        )[0]
        self.assertIn("structured_write_permitted", write_block)
        self.assertNotIn("st.columns([3, 2]", self.source)


if __name__ == "__main__":
    unittest.main()
