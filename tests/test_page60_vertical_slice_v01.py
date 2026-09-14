"""
Page60 Vertical Slice v0.1 tests. No live Supabase writes.

Run:
  python -m unittest tests.test_page60_vertical_slice_v01 -v
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path
from uuid import UUID

from services import pnr_p1_slice_prototype as proto

PAGE_PATH = (
    Path(__file__).resolve().parents[1] / "pages" / "60_ПНР_Фиксация_факта.py"
)
HELPER_PATH = (
    Path(__file__).resolve().parents[1] / "services" / "pnr_p1_slice_prototype.py"
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


class PrototypeHelperTests(unittest.TestCase):
    def test_keys_are_not_uuids_or_live_object_ids(self) -> None:
        live_object_id = "1796501a-44a6-4d3a-855b-7ea16b9fdc2c"
        for key in (
            proto.KEY_P1,
            proto.KEY_P11,
            proto.KEY_VEROSA,
            proto.KEY_FAN_UNIT,
            proto.KEY_FAN,
            proto.KEY_MOTOR,
        ):
            self.assertTrue(key.startswith("proto:"))
            self.assertNotEqual(key, live_object_id)
            with self.assertRaises(ValueError):
                UUID(key)

    def test_graph_contains_first_slice_nodes(self) -> None:
        labels = " ".join(node.label for node in proto.NODES)
        self.assertIn("П-1", labels)
        self.assertIn("П1.1 / 795-U-030A", labels)
        self.assertIn("ВЕРОСА", labels)
        self.assertIn("Вентиляторный узел", labels)
        self.assertIn("Вентилятор", labels)
        self.assertIn("Электродвигатель", labels)
        self.assertEqual(proto.TREE_LINES[0], "П-1")

    def test_required_work_only_for_motor(self) -> None:
        codes = [item.code for item in proto.required_works_for(proto.KEY_MOTOR)]
        self.assertEqual(codes, [proto.RW_MOTOR_01, proto.RW_MOTOR_02, proto.RW_MOTOR_03])
        self.assertEqual(proto.required_works_for(proto.KEY_FAN), ())
        self.assertEqual(proto.required_works_for(proto.KEY_P1), ())

    def test_work_and_step_are_distinct(self) -> None:
        rw03 = proto.required_work_by_code(proto.RW_MOTOR_03)
        self.assertNotEqual(rw03.code, rw03.step.operation_code)
        self.assertEqual(rw03.step.operation_code, proto.COM_ELEC_002)
        rw01 = proto.required_work_by_code(proto.RW_MOTOR_01)
        self.assertTrue(rw01.step.candidate)
        rw02 = proto.required_work_by_code(proto.RW_MOTOR_02)
        self.assertIsNone(rw02.step)

    def test_measurement_flags(self) -> None:
        self.assertFalse(proto.measurement_capture_enabled(proto.RW_MOTOR_01))
        self.assertFalse(proto.measurement_capture_enabled(proto.RW_MOTOR_02))
        self.assertTrue(proto.measurement_capture_enabled(proto.RW_MOTOR_03))
        self.assertTrue(proto.observation_capture_enabled(proto.RW_MOTOR_01))
        self.assertTrue(proto.observation_capture_enabled(proto.RW_MOTOR_02))

    def test_prototype_write_disabled(self) -> None:
        self.assertFalse(proto.allows_execution_event_write(proto.KEY_MOTOR))
        self.assertFalse(proto.allows_execution_event_write(proto.KEY_FAN))
        self.assertTrue(proto.allows_execution_event_write("1796501a-44a6-4d3a-855b-7ea16b9fdc2c"))

    def test_no_thresholds_in_helper(self) -> None:
        text = HELPER_PATH.read_text(encoding="utf-8")
        for forbidden in ("ГОСТ", "kV", "кВ", "МОм", "MOhm", "70%"):
            self.assertNotIn(forbidden, text)

    def test_helper_has_no_io(self) -> None:
        source = HELPER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("supabase", source)
        self.assertNotIn("create_client", source)
        self.assertNotIn("uuid4", source)
        self.assertNotIn("open(", source)
        self.assertNotIn("pnr_service", source)


class Page60VerticalSliceSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = PAGE_PATH.read_text(encoding="utf-8")
        self.helper = HELPER_PATH.read_text(encoding="utf-8")

    def test_layout_wide_and_columns(self) -> None:
        self.assertIn('layout="wide"', self.source)
        self.assertIn('st.columns([3, 7], gap="large")', self.source)
        self.assertNotIn("st.columns([3, 2]", self.source)

    def test_passport_tabs_and_execution_expander(self) -> None:
        self.assertIn("st.tabs(list(PASSPORT_TABS))", self.source)
        self.assertIn("NAV_TITLE", self.source)
        self.assertIn("PASSPORT_TITLE", self.source)
        self.assertIn("GRAPH_TITLE", self.source)
        self.assertIn(
            "st.expander(EXECUTION_EXPANDER_TITLE, expanded=False)",
            self.source,
        )
        self.assertIn("_render_p1_passport", self.source)
        self.assertIn("PASSPORT_CONTEXT_HEADING", self.source)
        self.assertIn("SELECTED_OBJECT_HEADING", self.source)
        self.assertIn("group_consecutive_by_provenance", self.source)
        self.assertNotIn("RIGHT_MODES", self.source)
        self.assertNotIn("EXECUTION_GRAPH_HEADING", self.source)
        self.assertNotIn("HISTORY_HEADING", self.source)

    def test_passport_visible_language_cleaned(self) -> None:
        from services import pnr_p1_engineering_context as ctx

        self.assertIn("_render_bullet_list", self.source)
        self.assertIn("format_status_text", self.source)
        self.assertIn("RELATED_NOT_CHILDREN", self.source)
        self.assertNotIn("Read-only engineering context", self.source)
        self.assertNotIn("Engineering Context prototype", self.source)
        self.assertNotIn("children", ctx.RELATED_NOT_CHILDREN)
        self.assertNotIn("persist", ctx.GRAPH_NOT_REGISTRY_CAPTION)
        self.assertNotIn("increment", ctx.DOC_READINESS_NOT_CALCULATED)
        self.assertIn("В1", dict(ctx.RELATED_VENTILATION))
        self.assertIn("В2", dict(ctx.RELATED_VENTILATION))
        self.assertIn("АВ1 / АВ2", dict(ctx.RELATED_VENTILATION))
        self.assertIn("ПЕ1 / ПЕ2", dict(ctx.RELATED_VENTILATION))
        self.assertIn("не входят в её состав", ctx.RELATED_NOT_CHILDREN)

    def test_language_gate_preserved(self) -> None:
        self.assertIn('"Работа из справочника"', self.source)
        self.assertIn('"Работы нет в списке"', self.source)
        self.assertIn('"Невозможно выполнить — есть препятствие"', self.source)
        self.assertIn("PNR-WS-08-COMPLEX-P1", self.source)
        self.assertIn("professional_p1_pilot_work_scopes", self.source)

    def test_work_and_step_labels_in_page(self) -> None:
        self.assertIn('"Конкретная работа"', self.source)
        self.assertIn("Технологический шаг", self.source)
        self.assertNotIn("Операция из справочника", self.source)

    def test_prototype_save_disabled_and_no_write(self) -> None:
        self.assertIn("structured_write_permitted", self.source)
        self.assertIn("disabled=True", self.source)
        self.assertIn("SAVE_DISABLED_REASON", self.source)
        self.assertIn(
            "if submitted and structured_write_permitted(str(physical_selection)):",
            self.source,
        )
        write_block = self.source.split("create_structured_execution_event(**kwargs)", 1)[0]
        self.assertIn("structured_write_permitted", write_block)

    def test_no_agent_runtime_or_sql(self) -> None:
        imported = _imported_modules(self.source)
        self.assertNotIn("agents.monthly_plan_constructor", imported)
        self.assertNotIn("docs.agentic_architecture", imported)
        self.assertNotIn("st.dataframe", self.source)
        self.assertFalse(re.search(r"create table", self.source, flags=re.I))

    def test_no_fake_events_or_thresholds(self) -> None:
        self.assertNotIn("41bd0c13", self.source)
        self.assertNotIn("41bd0c13", self.helper)
        for forbidden in ("ГОСТ", "kV", "кВ", "МОм"):
            self.assertNotIn(forbidden, self.source)
            self.assertNotIn(forbidden, self.helper)

    def test_page_write_helper_matches_prototype_law(self) -> None:
        spec = ast.parse(self.source)
        names: dict[str, ast.FunctionDef] = {
            node.name: node
            for node in spec.body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("structured_write_permitted", names)
        src = ast.get_source_segment(self.source, names["structured_write_permitted"])
        self.assertIsNotNone(src)
        self.assertIn("allows_execution_event_write", src or "")


if __name__ == "__main__":
    unittest.main()
