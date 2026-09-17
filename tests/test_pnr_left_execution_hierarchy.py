"""LEFT execution hierarchy v0.1 tests. No live Supabase writes."""

from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

from services import pnr_left_execution_hierarchy as hier
from services.pnr_p1_engineering_context import SECTION_TITLES
from services.pnr_p1_slice_prototype import KEY_MOTOR

PAGE_PATH = (
    Path(__file__).resolve().parents[1] / "pages" / "60_ПНР_Фиксация_факта.py"
)
HELPER_PATH = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "pnr_left_execution_hierarchy.py"
)


class HierarchyContractTests(unittest.TestCase):
    def test_approved_labels_and_order(self) -> None:
        labels = hier.hierarchy_labels()
        self.assertEqual(labels[0], "Общие данные")
        self.assertEqual(labels[1], "Система")
        self.assertEqual(labels[2], "Физический объект")
        self.assertEqual(labels[3], "Раздел работ")
        self.assertEqual(labels[4], "Конкретная работа")
        self.assertEqual(labels[5], "Операция")
        self.assertEqual(labels[6], "Фактическое исполнение")
        self.assertEqual(labels[7], "Инспекция / проверка результата")
        self.assertEqual(labels[8], "Доказательства исполнения")
        self.assertEqual(labels[9], "Документальная готовность")
        self.assertEqual(labels[10], "Актирование / признание результата")
        self.assertEqual(labels[11], "Статус работы")
        self.assertLess(labels.index("Система"), labels.index("Физический объект"))
        self.assertLess(labels.index("Физический объект"), labels.index("Раздел работ"))
        self.assertLess(labels.index("Раздел работ"), labels.index("Конкретная работа"))
        self.assertLess(labels.index("Конкретная работа"), labels.index("Операция"))

    def test_general_data_field_order(self) -> None:
        self.assertEqual(
            hier.GENERAL_FIELD_ORDER,
            (
                "Проект",
                "Очередь",
                "Вид работ",
                "Титул",
                "Наименование титула",
                "Дисциплина",
                "Система",
            ),
        )

    def test_demo_chain_shsau_automation_pti(self) -> None:
        sections = {item.key: item.label for item in hier.work_sections_for(hier.KEY_SHSAU_P11)}
        self.assertEqual(sections[hier.WS_AUTO], "Автоматизация")
        subs = {
            item.key: item.label
            for item in hier.automation_subcontexts_for(hier.KEY_SHSAU_P11, hier.WS_AUTO)
        }
        self.assertEqual(subs[hier.WS_AUTO_PTI], "ПТИ")
        works = hier.required_works_for_hierarchy(
            hier.KEY_SHSAU_P11, hier.WS_AUTO, hier.WS_AUTO_PTI
        )
        self.assertEqual([item.code for item in works], [hier.RW_SHSAU_P1_READY])
        self.assertEqual(works[0].title, "Проверить готовность П-1")
        ops = hier.operations_for_required_work(hier.RW_SHSAU_P1_READY)
        self.assertEqual([item.label for item in ops], ["Проверка готовности", "Пробный пуск"])
        self.assertTrue(all(item.prototype for item in ops))
        self.assertTrue(all(item.live_operation_code is None for item in ops))

    def test_cascade_filters_lower_levels(self) -> None:
        motor_sections = {item.key for item in hier.work_sections_for(hier.KEY_MOTOR_P11)}
        self.assertIn(hier.WS_MECH, motor_sections)
        self.assertNotIn(hier.WS_AUTO, motor_sections)
        self.assertEqual(
            hier.automation_subcontexts_for(hier.KEY_MOTOR_P11, hier.WS_AUTO),
            (),
        )
        self.assertEqual(
            hier.required_works_for_hierarchy(
                hier.KEY_MOTOR_P11, hier.WS_AUTO, hier.WS_AUTO_PTI
            ),
            (),
        )
        self.assertEqual(
            hier.required_works_for_hierarchy(hier.KEY_MOTOR_P11, hier.WS_MECH),
            hier.required_works_for_hierarchy(KEY_MOTOR, hier.WS_MECH),
        )

    def test_parent_change_clears_incompatible_child_state(self) -> None:
        state: dict[str, object] = {
            hier.SESSION_TRACK_PHYSICAL: hier.KEY_SHSAU_P11,
            hier.SESSION_TRACK_WORK_SECTION: hier.WS_AUTO,
            hier.SESSION_TRACK_AUTO_SUB: hier.WS_AUTO_PTI,
            hier.SESSION_TRACK_REQUIRED_WORK: hier.RW_SHSAU_P1_READY,
            "pnr_work_section_key": hier.WS_AUTO,
            "pnr_auto_subcontext": hier.WS_AUTO_PTI,
            "pnr_required_work": hier.RW_SHSAU_P1_READY,
            "pnr_proto_operation_key": hier.OP_READY_CHECK,
            "pnr_operation_id": "should-clear",
            "pnr_operation_mode": "x",
        }
        changed = hier.apply_hierarchy_cascade(
            state,
            physical_key=hier.KEY_MOTOR_P11,
            work_section_key=hier.WS_AUTO,
            auto_subcontext_key=hier.WS_AUTO_PTI,
            required_work_code=hier.RW_SHSAU_P1_READY,
        )
        self.assertTrue(changed["physical"])
        self.assertNotIn("pnr_work_section_key", state)
        self.assertNotIn("pnr_auto_subcontext", state)
        self.assertNotIn("pnr_required_work", state)
        self.assertNotIn("pnr_proto_operation_key", state)
        self.assertNotIn("pnr_operation_id", state)

    def test_prototype_identities_cannot_be_submitted(self) -> None:
        self.assertTrue(hier.is_prototype_physical_identity(hier.KEY_SHSAU_P11))
        self.assertFalse(hier.permits_live_execution_identity(hier.KEY_SHSAU_P11))
        self.assertFalse(hier.permits_live_execution_identity(hier.KEY_MOTOR_P11))
        self.assertTrue(hier.permits_live_execution_identity("1796501a-44a6-4d3a-855b-7ea16b9fdc2c"))

    def test_helper_has_no_supabase_write(self) -> None:
        source = HELPER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("create_client", source)
        self.assertNotIn("SUPABASE_URL", source)
        self.assertNotIn("SUPABASE_SECRET_KEY", source)
        self.assertNotIn("pnr_service", source)
        self.assertNotIn("INSERT", source)
        self.assertNotIn("CREATE TABLE", source)
        self.assertNotIn("uuid4", source)

    def test_live_shsau_object_maps_explicitly_to_prototype_cascade(self) -> None:
        live_id = hier.LIVE_SHSAU_P1_OBJECT_ID
        self.assertEqual(live_id, "1796501a-44a6-4d3a-855b-7ea16b9fdc2c")
        self.assertEqual(
            hier.CASCADE_PRESENTATION_ALIASES,
            {live_id: hier.KEY_SHSAU_P11},
        )
        self.assertEqual(hier.presentation_cascade_key(live_id), hier.KEY_SHSAU_P11)
        self.assertEqual(hier.work_section_resolution_mode(live_id), hier.PROTOTYPE_MODE)
        self.assertTrue(hier.permits_live_execution_identity(live_id))
        self.assertFalse(hier.is_prototype_physical_identity(live_id))

    def test_arbitrary_persisted_object_does_not_receive_shsau_cascade(self) -> None:
        other = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        self.assertEqual(hier.presentation_cascade_key(other), other)
        self.assertEqual(hier.work_section_resolution_mode(other), hier.LIVE_SCOPES_MODE)
        self.assertEqual(hier.work_sections_for(other), ())
        self.assertEqual(
            hier.required_works_for_hierarchy(other, hier.WS_AUTO, hier.WS_AUTO_PTI),
            (),
        )

    def test_no_fuzzy_label_mapping_for_cascade(self) -> None:
        fn_src = inspect.getsource(hier.presentation_cascade_key)
        self.assertNotIn("label", fn_src.lower())
        self.assertNotIn("fuzzy", fn_src.lower())
        self.assertNotIn("ШСАУ", fn_src)
        self.assertNotIn("шкаф", fn_src.lower())
        self.assertEqual(
            hier.presentation_cascade_key("Шкаф системы автоматического управления P1"),
            "Шкаф системы автоматического управления P1",
        )
        self.assertEqual(hier.presentation_cascade_key("ШСАУ-P1"), "ШСАУ-P1")
        self.assertEqual(hier.presentation_cascade_key("ШСАУ П1.1"), "ШСАУ П1.1")

    def test_live_shsau_cascade_resolves_demo_chain(self) -> None:
        live_id = hier.LIVE_SHSAU_P1_OBJECT_ID
        sections = {item.key: item.label for item in hier.work_sections_for(live_id)}
        self.assertEqual(sections[hier.WS_AUTO], "Автоматизация")
        subs = {
            item.key: item.label
            for item in hier.automation_subcontexts_for(live_id, hier.WS_AUTO)
        }
        self.assertEqual(subs[hier.WS_AUTO_PTI], "ПТИ")
        works = hier.required_works_for_hierarchy(live_id, hier.WS_AUTO, hier.WS_AUTO_PTI)
        self.assertEqual([item.code for item in works], [hier.RW_SHSAU_P1_READY])
        self.assertEqual(works[0].title, "Проверить готовность П-1")
        ops = hier.operations_for_required_work(hier.RW_SHSAU_P1_READY)
        self.assertEqual(
            [item.label for item in ops],
            ["Проверка готовности", "Пробный пуск"],
        )

    def test_live_shsau_parent_change_still_resets_stale_children(self) -> None:
        state: dict[str, object] = {
            hier.SESSION_TRACK_PHYSICAL: hier.LIVE_SHSAU_P1_OBJECT_ID,
            hier.SESSION_TRACK_WORK_SECTION: hier.WS_AUTO,
            "pnr_work_section_key": hier.WS_AUTO,
            "pnr_auto_subcontext": hier.WS_AUTO_PTI,
            "pnr_required_work": hier.RW_SHSAU_P1_READY,
            "pnr_proto_operation_key": hier.OP_READY_CHECK,
        }
        changed = hier.apply_hierarchy_cascade(
            state,
            physical_key=hier.KEY_MOTOR_P11,
            work_section_key=hier.WS_AUTO,
            auto_subcontext_key=hier.WS_AUTO_PTI,
            required_work_code=hier.RW_SHSAU_P1_READY,
        )
        self.assertTrue(changed["physical"])
        self.assertNotIn("pnr_work_section_key", state)
        self.assertNotIn("pnr_auto_subcontext", state)
        self.assertNotIn("pnr_required_work", state)
        self.assertNotIn("pnr_proto_operation_key", state)


class Page60HierarchySourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = PAGE_PATH.read_text(encoding="utf-8")

    def test_page_uses_hierarchy_sections(self) -> None:
        for name in (
            "SECTION_GENERAL",
            "SECTION_SYSTEM",
            "SECTION_PHYSICAL",
            "SECTION_WORK_SECTION",
            "SECTION_REQUIRED_WORK",
            "SECTION_OPERATION",
            "SECTION_FACTUAL",
            "SECTION_INSPECTION",
            "SECTION_EVIDENCE",
            "SECTION_DOC_READY",
            "SECTION_ACCEPTANCE",
            "SECTION_WORK_STATUS",
        ):
            self.assertIn(name, self.source)
        self.assertIn("reset_dependent_selections", self.source)
        self.assertIn("pnr_left_execution_hierarchy", self.source)

    def test_passport_remains_system_level_with_twelve_sections(self) -> None:
        self.assertIn("_render_p1_passport", self.source)
        self.assertIn("st.tabs(list(PASSPORT_TABS))", self.source)
        for key in ("01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"):
            self.assertIn(key, SECTION_TITLES)
        self.assertEqual(len(SECTION_TITLES), 12)
        self.assertNotIn("object-specific Passport", self.source)
        self.assertNotIn("ШСАУ diagram", self.source)

    def test_event_write_contract_unchanged(self) -> None:
        self.assertIn("create_structured_execution_event(**kwargs)", self.source)
        self.assertIn("build_structured_kwargs", self.source)
        self.assertNotIn("create_execution_event(", self.source)
        self.assertNotRegex(self.source, r"(?<!path)\.insert\(")
        self.assertNotIn(".update(", self.source)
        self.assertNotIn(".upsert(", self.source)
        self.assertNotIn("CREATE TABLE", self.source)

    def test_hierarchy_introduces_no_supabase_client(self) -> None:
        tree = ast.parse(self.source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertIn("services.pnr_left_execution_hierarchy", imported)
        self.assertNotIn("services.supabase_client", imported)
        self.assertNotIn("supabase", imported)

    def test_fp_read_helper_does_not_call_stop(self) -> None:
        tree = ast.parse(self.source)
        names = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("load_functional_position_id", names)
        fn_src = ast.get_source_segment(self.source, names["load_functional_position_id"])
        self.assertIsNotNone(fn_src)
        self.assertNotIn("st.stop", fn_src or "")

    def test_fp_read_failure_does_not_stop_page_and_write_stays_closed(self) -> None:
        self.assertIn("fp_unresolved", self.source)
        self.assertIn("load_functional_position_id", self.source)
        self.assertIn("and not fp_unresolved", self.source)
        self.assertIn(
            "if submitted and structured_write_permitted(str(physical_selection)):",
            self.source,
        )
        write_block = self.source.split("create_structured_execution_event(**kwargs)", 1)[0]
        self.assertIn("fp_unresolved", write_block)
        call_marker = (
            "functional_position_id, fp_unresolved = load_functional_position_id(object_id)"
        )
        self.assertIn(call_marker, self.source)
        fp_handler = self.source.split(call_marker, 1)[1]
        fp_handler = fp_handler.split('st.markdown(f"### {SECTION_WORK_SECTION}")', 1)[0]
        self.assertNotIn("st.stop()", fp_handler)

    def test_lower_presentation_sections_remain(self) -> None:
        for heading in (
            "SECTION_FACTUAL",
            "SECTION_INSPECTION",
            "SECTION_EVIDENCE",
            "SECTION_DOC_READY",
            "SECTION_ACCEPTANCE",
            "SECTION_WORK_STATUS",
        ):
            self.assertIn(f'st.markdown(f"### {{{heading}}}")', self.source)

    def test_page_has_no_database_write_api(self) -> None:
        self.assertNotIn("CREATE TABLE", self.source)
        self.assertNotIn("ALTER TABLE", self.source)
        self.assertNotRegex(self.source, r"(?<!path)\.insert\(")
        self.assertNotIn(".upsert(", self.source)
        self.assertNotIn(".delete(", self.source)


if __name__ == "__main__":
    unittest.main()
