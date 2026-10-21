"""Constructor candidate-package semantics + professional handoff.

Surgical checks only: terminology, handoff gating, exact immutable artifact
reference, idempotency, honest receiver state, no fake Admission run.
"""

from __future__ import annotations

import json
import sqlite3
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from agents.human_surface import candidate_handoff as handoff_module
from agents.human_surface.candidate_handoff import (
    HANDOFF_OBJECT_KIND,
    HANDOFF_TYPE,
    RECEIVER_NOT_CONNECTED,
    SOURCE_ROLE_CODE,
    STATUS_ALREADY_HANDED_OFF,
    STATUS_HANDOFF_PERSISTED,
    TARGET_ROLE_CODE,
    CandidateHandoffError,
    find_existing_approved_candidate_handoff,
    open_handoff_store,
    submit_approved_candidate_handoff,
    submit_handoff_for_package,
)
from agents.human_surface.final_confirm_command import not_ready_message
from agents.monthly_plan_constructor.approved_monthly_package import (
    ApprovedMonthlyLine,
    ApprovedMonthlyPackage,
    ApprovedMonthlySummary,
)

FIXED_AT = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 10, 21, 13, 0, 0, tzinfo=timezone.utc)
HANDOFF_LABEL = "ПЕРЕДАТЬ ИНЖЕНЕРУ ПРОИЗВОДСТВЕННОЙ ГОТОВНОСТИ И ДОПУСКА"


def _package() -> ApprovedMonthlyPackage:
    line = ApprovedMonthlyLine(
        project_code="PRJ_001_БХК",
        month_key="октябрь-2026",
        facility="16160-13",
        discipline="Вентиляция",
        system="SYS-1",
        iwp="IWP-1",
        boq_code="BOQ-1",
        name="Work",
        unit="м",
        baseline_qty="0",
        constructor_delta_qty="1",
        final_qty="1",
        source_status="ACCEPTED",
        candidate_id="cand-1",
    )
    return ApprovedMonthlyPackage(
        schema_version="1.0",
        approved_package_id="amp-test-001",
        project_code="PRJ_001_БХК",
        month_key="октябрь-2026",
        queue="1",
        source_run_id="run-test-001",
        source_candidate_package_id="3ef26b0e-1f5c-41ef-a06e-e39758749273",
        source_review_content_hash="review-hash",
        source_preview_content_hash="preview-hash",
        source_checkpoint_id="ckpt-1",
        approved_at=FIXED_AT,
        approved_by="human-surface-operator",
        status="APPROVED",
        professional_lines=(line,),
        summary_counts=ApprovedMonthlySummary(1, 0, 1, 0, 1, 0, 0, 0, 0),
        content_hash="artifact-content-hash-001",
        provenance="HUMAN_SURFACE_FINAL_CONFIRM",
    )


def _row_count(db_path: Path) -> int:
    connection = sqlite3.connect(db_path)
    try:
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM professional_handoffs"
            ).fetchone()[0]
        )
    finally:
        connection.close()


class CandidatePackageSemanticsTests(unittest.TestCase):
    def test_ui_no_longer_claims_production_commitment(self) -> None:
        from tests.test_control_room_page_guards import PAGE_PATH

        source = PAGE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("МЕСЯЧНОЕ ОБЯЗАТЕЛЬСТВО УТВЕРЖДЕНО", source)
        self.assertNotIn("ПОДТВЕРДИТЬ МЕСЯЧНОЕ ОБЯЗАТЕЛЬСТВО", source)
        self.assertNotIn("Текущий черновик месячного обязательства", source)
        self.assertIn("КАНДИДАТНЫЙ СОСТАВ МЕСЯЦА ПОДТВЕРЖДЁН", source)
        self.assertIn("ПОДТВЕРДИТЬ КАНДИДАТНЫЙ СОСТАВ", source)
        self.assertIn("Черновик кандидатного состава месяца", source)
        self.assertIn("Это ещё не производственное обязательство.", source)
        self.assertIn("Пакет подтверждён человеком и готов к проверке", source)
        self.assertIn("производственной готовности и допуска.", source)
        self.assertIn("Кандидатный состав нельзя подтвердить:", not_ready_message(3))
        self.assertIn(
            "остались позиции, требующие решения человека: 3",
            not_ready_message(3),
        )


class ApprovedCandidateHandoffStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "approved_monthly_packages.sqlite"
        self.store = open_handoff_store(self.db_path)

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def test_handoff_persists_exact_immutable_artifact_reference(self) -> None:
        package = _package()
        result = submit_handoff_for_package(
            package, store=self.store, created_by="human-surface-operator", now=FIXED_AT
        )
        self.assertEqual(result.status, STATUS_HANDOFF_PERSISTED)
        handoff = result.handoff
        self.assertTrue(handoff.handoff_id.startswith("eos-hof-"))
        self.assertEqual(handoff.source_role_code, SOURCE_ROLE_CODE)
        self.assertEqual(handoff.source_role_code, "MONTHLY_PLAN_CONSTRUCTOR")
        self.assertEqual(handoff.target_role_code, TARGET_ROLE_CODE)
        self.assertEqual(handoff.target_role_code, "MONTHLY_PLAN_ADMISSION_AGENT")
        self.assertEqual(handoff.project_code, package.project_code)
        self.assertEqual(handoff.month_key, package.month_key)
        self.assertEqual(handoff.source_run_id, package.source_run_id)
        self.assertEqual(
            handoff.source_candidate_package_id, package.source_candidate_package_id
        )
        self.assertEqual(handoff.human_approved_package_id, package.approved_package_id)
        self.assertEqual(handoff.artifact_content_hash, package.content_hash)
        self.assertEqual(handoff.handoff_type, HANDOFF_TYPE)
        self.assertEqual(handoff.handed_off_object, HANDOFF_OBJECT_KIND)
        self.assertEqual(
            handoff.handed_off_object, "HUMAN_APPROVED_MONTHLY_CANDIDATE_PACKAGE"
        )
        self.assertEqual(handoff.created_by, "human-surface-operator")
        self.assertEqual(handoff.professional_status, STATUS_HANDOFF_PERSISTED)
        self.assertEqual(handoff.receiver_status, RECEIVER_NOT_CONNECTED)
        self.assertEqual(_row_count(self.db_path), 1)

        connection = sqlite3.connect(self.db_path)
        try:
            payload = json.loads(
                connection.execute(
                    "SELECT payload_json FROM professional_handoffs"
                ).fetchone()[0]
            )
        finally:
            connection.close()
        self.assertEqual(payload["human_approved_package_id"], "amp-test-001")
        self.assertEqual(
            payload["artifact_content_hash"], "artifact-content-hash-001"
        )
        self.assertEqual(payload["receiver_status"], "RECEIVER_NOT_CONNECTED")
        self.assertNotIn("monthly_production_commitment", json.dumps(payload).lower())

    def test_repeated_handoff_is_idempotent(self) -> None:
        package = _package()
        first = submit_handoff_for_package(
            package, store=self.store, created_by="human-surface-operator", now=FIXED_AT
        )
        second = submit_handoff_for_package(
            package, store=self.store, created_by="human-surface-operator", now=LATER
        )
        self.assertEqual(second.status, STATUS_ALREADY_HANDED_OFF)
        self.assertEqual(second.handoff.handoff_id, first.handoff.handoff_id)
        self.assertEqual(second.handoff.created_at, first.handoff.created_at)
        self.assertEqual(_row_count(self.db_path), 1)

    def test_no_approved_artifact_blocks_handoff(self) -> None:
        original = handoff_module.find_current_approved_package
        handoff_module.find_current_approved_package = lambda run_id: None
        try:
            with self.assertRaises(CandidateHandoffError):
                submit_approved_candidate_handoff("run-missing", store=self.store)
        finally:
            handoff_module.find_current_approved_package = original
        self.assertEqual(_row_count(self.db_path), 0)

    def test_existing_lookup_never_creates_missing_store(self) -> None:
        missing = Path(self._tmp.name) / "missing" / "approved_monthly_packages.sqlite"
        original_package = handoff_module.find_current_approved_package
        original_path = handoff_module.production_handoff_db_path
        handoff_module.find_current_approved_package = lambda run_id: _package()
        handoff_module.production_handoff_db_path = lambda: missing
        try:
            found = find_existing_approved_candidate_handoff("run-test-001")
        finally:
            handoff_module.find_current_approved_package = original_package
            handoff_module.production_handoff_db_path = original_path
        self.assertIsNone(found)
        self.assertFalse(missing.exists())

    def test_no_fake_admission_run_created(self) -> None:
        source = Path(handoff_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("create_run", source)
        self.assertNotIn("observability", source.lower())
        self.assertNotIn("default_human_review_runtime", source)
        self.assertNotIn("RECEIVED", source)
        self.assertNotIn("ADMITTED", source)
        self.assertNotIn("READY_FOR_EXECUTION", source)
        result = submit_handoff_for_package(
            _package(), store=self.store, created_by="human-surface-operator", now=FIXED_AT
        )
        self.assertEqual(result.handoff.receiver_status, RECEIVER_NOT_CONNECTED)
        self.assertEqual(_row_count(self.db_path), 1)


class CandidateHandoffPageTests(unittest.TestCase):
    def _handoff_buttons(self, st) -> list[dict]:
        return [item for item in st.button_calls if item["label"] == HANDOFF_LABEL]

    def _writes(self, st) -> str:
        return " ".join(str(item) for args in st.write_calls for item in args)

    def test_handoff_disabled_without_approved_package(self) -> None:
        from tests.test_control_room_page_guards import _load_page_module

        page, st = _load_page_module()
        page.find_current_approved_package = lambda run_id: None
        page._render_next_step("run-page")
        buttons = self._handoff_buttons(st)
        self.assertEqual(len(buttons), 1)
        self.assertTrue(buttons[0]["disabled"])
        self.assertIn(
            "Передача станет доступна после подтверждения кандидатного состава.",
            self._writes(st),
        )

    def test_approved_package_enables_handoff(self) -> None:
        from tests.test_control_room_page_guards import _load_page_module

        page, st = _load_page_module()
        page.find_current_approved_package = lambda run_id: SimpleNamespace(
            approved_package_id="amp-page"
        )
        page.find_existing_approved_candidate_handoff = lambda run_id: None
        page._render_next_step("run-page")
        buttons = self._handoff_buttons(st)
        self.assertEqual(len(buttons), 1)
        self.assertFalse(buttons[0]["disabled"])

    def test_existing_handoff_shows_receiver_not_connected(self) -> None:
        from tests.test_control_room_page_guards import _load_page_module

        page, st = _load_page_module()
        page.find_current_approved_package = lambda run_id: SimpleNamespace(
            approved_package_id="amp-page"
        )
        page.find_existing_approved_candidate_handoff = lambda run_id: SimpleNamespace(
            handoff_id="eos-hof-page",
            professional_status=STATUS_HANDOFF_PERSISTED,
            receiver_status=RECEIVER_NOT_CONNECTED,
        )
        page._render_next_step("run-page")
        buttons = self._handoff_buttons(st)
        self.assertEqual(len(buttons), 1)
        self.assertTrue(buttons[0]["disabled"])
        text = self._writes(st)
        self.assertIn(
            "ПАКЕТ ПЕРЕДАН В КОНТУР ПРОИЗВОДСТВЕННОЙ ГОТОВНОСТИ И ДОПУСКА", text
        )
        self.assertIn("Передано в контур допуска", text)
        self.assertIn("Receiver: ещё не подключён", text)
        self.assertNotIn("RECEIVED", text)
        self.assertNotIn("ACCEPTED", text)
        self.assertNotIn("ADMITTED", text)
        self.assertNotIn("READY FOR EXECUTION", text)
        self.assertNotIn("MONTHLY COMMITMENT CREATED", text)

    def test_click_submits_once_without_claiming_receiver(self) -> None:
        from tests.test_control_room_page_guards import _load_page_module

        page, st = _load_page_module()
        calls: list[str] = []

        def _submit(run_id: str):
            calls.append(run_id)
            return SimpleNamespace(
                status=STATUS_HANDOFF_PERSISTED,
                handoff=SimpleNamespace(handoff_id="eos-hof-page"),
            )

        def _button(label: str, *args, **kwargs):
            st.button_calls.append(
                {"label": str(label), "disabled": bool(kwargs.get("disabled", False))}
            )
            return str(label) == HANDOFF_LABEL

        st.button = _button
        page.find_current_approved_package = lambda run_id: SimpleNamespace(
            approved_package_id="amp-page"
        )
        page.find_existing_approved_candidate_handoff = lambda run_id: None
        page.submit_approved_candidate_handoff = _submit
        page._render_next_step("run-page")
        self.assertEqual(calls, ["run-page"])
        text = self._writes(st)
        self.assertIn("Передано в контур допуска", text)
        self.assertIn("Receiver: ещё не подключён", text)
        self.assertNotIn("ADMITTED", text)

    def test_navigation_contract_unchanged(self) -> None:
        from tests.test_control_room_page_guards import APP_PY, PAGE_PATH

        page_source = PAGE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("st.navigation", page_source)
        self.assertNotIn("NAV_SECTIONS", page_source)
        app_source = APP_PY.read_text(encoding="utf-8")
        self.assertIn("53_AI_Центр_управления_агентами.py", app_source)
        self.assertIn("st.navigation", app_source)


if __name__ == "__main__":
    unittest.main()
