"""Focused Django Human Surface tests — mock LND service, no product writes."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse

from services.labor_norm_decisions import (
    DECISION_MANUAL_PROVISIONAL,
    DECISION_REJECTED,
    LaborNormDecisionRecord,
)


def _valid_manual_payload(**overrides):
    payload = {
        "action": "save",
        "project_code": "PRJ_001_БХК",
        "facility_building": "16160-13",
        "construction_discipline": "Вентиляция",
        "boq_code": "2041-01-27-02",
        "unit_of_measure": "м3 / m3",
        "boq_name": "Изоляция",
        "decision": DECISION_MANUAL_PROVISIONAL,
        "approved_norm": "2.5",
        "comment": "временная норма для django surface",
        "approved_by": "operator.django",
    }
    payload.update(overrides)
    return payload


@override_settings(
    ROOT_URLCONF="config.urls",
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
)
class DynamisHumanSurfaceTests(SimpleTestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_home_get_200(self) -> None:
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DYNAMIS")
        self.assertContains(
            response,
            "AI-native оркестрация физического исполнения инженерно-критической инфраструктуры",
        )

    def test_labor_norm_get_200(self) -> None:
        response = self.client.get(reverse("labor_norm_decision"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Принять временное решение")

    def test_architecture_get_200(self) -> None:
        with patch("dynamis.views.save_decision") as save_mock, patch(
            "dynamis.views.get_active_decision"
        ) as get_mock:
            response = self.client.get(reverse("architecture"))
        self.assertEqual(response.status_code, 200)
        save_mock.assert_not_called()
        get_mock.assert_not_called()
        self.assertContains(response, "Архитектура исполнения")
        self.assertContains(
            response,
            "AI-native оркестрация физического исполнения инженерно-критической инфраструктуры",
        )
        self.assertContains(response, "Операционный граф физического исполнения")
        self.assertContains(response, "П1")
        self.assertContains(response, "Агент исполнимости")
        self.assertContains(response, "Агент производственного обязательства")
        self.assertContains(response, "Готово к ПНР")

    def test_navigation_includes_architecture(self) -> None:
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Архитектура исполнения")
        self.assertContains(response, reverse("architecture"))

    def test_initial_get_does_not_call_service(self) -> None:
        with patch("dynamis.views.save_decision") as save_mock, patch(
            "dynamis.views.get_active_decision"
        ) as get_mock:
            response = self.client.get(reverse("labor_norm_decision"))
        self.assertEqual(response.status_code, 200)
        save_mock.assert_not_called()
        get_mock.assert_not_called()

    def test_manual_provisional_post_calls_save(self) -> None:
        with patch(
            "dynamis.views.save_decision",
            return_value={
                "ok": True,
                "data": {
                    "status": "inserted",
                    "decision_id": "dec-1",
                    "decision": DECISION_MANUAL_PROVISIONAL,
                    "approved_norm": 2.5,
                },
                "error": None,
            },
        ) as save_mock:
            response = self.client.post(
                reverse("labor_norm_decision"), _valid_manual_payload()
            )
        self.assertEqual(response.status_code, 200)
        save_mock.assert_called_once()
        draft = save_mock.call_args.args[0]
        self.assertEqual(draft.decision, DECISION_MANUAL_PROVISIONAL)
        self.assertEqual(draft.approved_norm, 2.5)
        self.assertContains(response, "dec-1")

    def test_rejected_post_calls_save_without_norm(self) -> None:
        with patch(
            "dynamis.views.save_decision",
            return_value={
                "ok": True,
                "data": {
                    "status": "inserted",
                    "decision_id": "dec-2",
                    "decision": DECISION_REJECTED,
                    "approved_norm": None,
                },
                "error": None,
            },
        ) as save_mock:
            response = self.client.post(
                reverse("labor_norm_decision"),
                _valid_manual_payload(
                    decision=DECISION_REJECTED,
                    approved_norm="",
                    comment="отклонить через django",
                ),
            )
        self.assertEqual(response.status_code, 200)
        save_mock.assert_called_once()
        draft = save_mock.call_args.args[0]
        self.assertEqual(draft.decision, DECISION_REJECTED)
        self.assertIsNone(draft.approved_norm)

    def test_invalid_form_does_not_call_service(self) -> None:
        with patch("dynamis.views.save_decision") as save_mock:
            response = self.client.post(
                reverse("labor_norm_decision"),
                _valid_manual_payload(comment="", approved_by=""),
            )
        self.assertEqual(response.status_code, 200)
        save_mock.assert_not_called()

    def test_service_error_shown_without_traceback(self) -> None:
        with patch(
            "dynamis.views.save_decision",
            return_value={"ok": False, "data": None, "error": "RPC failed"},
        ):
            response = self.client.post(
                reverse("labor_norm_decision"), _valid_manual_payload()
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "RPC failed")
        self.assertNotContains(response, "Traceback")

    def test_explicit_readback_calls_get_active(self) -> None:
        record = LaborNormDecisionRecord(
            decision_id="dec-3",
            project_code="PRJ_001_БХК",
            facility_building="16160-13",
            construction_discipline="Вентиляция",
            boq_code="2041-01-27-02",
            unit_of_measure="м3 / m3",
            decision=DECISION_REJECTED,
            decision_status="ACTIVE",
            approved_by="operator.django",
            approved_at="2026-10-01T00:00:00+00:00",
            approved_norm=None,
        )
        with patch("dynamis.views.get_active_decision", return_value=record) as get_mock:
            response = self.client.post(
                reverse("labor_norm_decision"),
                {
                    "action": "readback",
                    "project_code": "PRJ_001_БХК",
                    "facility_building": "16160-13",
                    "construction_discipline": "Вентиляция",
                    "boq_code": "2041-01-27-02",
                    "unit_of_measure": "м3 / m3",
                    "decision": DECISION_REJECTED,
                    "approved_by": "operator.django",
                    "comment": "x",
                },
            )
        self.assertEqual(response.status_code, 200)
        get_mock.assert_called_once()
        self.assertContains(response, "dec-3")

    def test_readback_error_fail_soft(self) -> None:
        with patch(
            "dynamis.views.get_active_decision",
            side_effect=RuntimeError("SSL EOF"),
        ):
            response = self.client.post(
                reverse("labor_norm_decision"),
                {
                    "action": "readback",
                    "project_code": "PRJ_001_БХК",
                    "facility_building": "16160-13",
                    "construction_discipline": "Вентиляция",
                    "boq_code": "2041-01-27-02",
                    "unit_of_measure": "м3 / m3",
                    "decision": DECISION_REJECTED,
                    "approved_by": "operator.django",
                    "comment": "x",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Не удалось прочитать")
        self.assertNotContains(response, "Traceback")

    def test_no_import_from_pages(self) -> None:
        web_root = Path(__file__).resolve().parents[1]
        offenders = []
        for path in web_root.rglob("*.py"):
            if path.name == "tests.py" and path.parent.name == "dynamis":
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if (
                    stripped.startswith("from pages")
                    or stripped.startswith("import pages")
                    or " pages." in stripped
                ):
                    offenders.append(f"{path}:{stripped}")
        self.assertEqual(offenders, [])


@override_settings(
    ROOT_URLCONF="config.urls",
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
)
class ControlRoomShellTests(SimpleTestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_control_room_get_renders_shell(self) -> None:
        response = self.client.get(reverse("control_room"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        for text in (
            "Диалог с DYNAMIS",
            "Цифровая организация / Месячное обязательство",
            "Constructor Agent",
            "Admission Agent",
            "Constraint Agent",
            "Resource Agent",
            "Economic Agent",
            "Decision Agent",
            "Детальная таблица кандидатов",
            "Аудит и трассировка",
            "Запустить Constructor Agent",
            "Передать в Admission Agent",
        ):
            self.assertIn(text, body)
        self.assertNotIn("launch_monthly_plan", body)
        self.assertEqual(body.count('data-demo="launch"'), 1)
        self.assertEqual(body.count('data-demo="admission"'), 1)

    def test_control_room_post_is_rejected(self) -> None:
        response = self.client.post(reverse("control_room"), {})
        self.assertEqual(response.status_code, 405)

    def test_control_room_view_does_not_touch_runtime(self) -> None:
        source = Path(__file__).with_name("views.py").read_text(encoding="utf-8")
        start = source.index("def control_room")
        end = source.index("\ndef architecture")
        room_view = source[start:end]
        room = Path(__file__).with_name("control_room_state.py").read_text(encoding="utf-8")
        for blob in (room_view, room):
            self.assertNotIn("launch_monthly_plan_mission", blob)
            self.assertNotIn("submit_human_review", blob)
            self.assertNotIn("import supabase", blob.lower())
            self.assertNotIn("services.supabase", blob.lower())
        self.assertIn("control_room_context()", room_view)

    def test_control_room_layout_is_resizable_and_local(self) -> None:
        response = self.client.get(reverse("control_room"))
        body = response.content.decode("utf-8")
        for marker in (
            'data-splitter="left"',
            'data-splitter="right"',
            'data-splitter="bottom"',
            'data-collapse="left"',
            'data-collapse="right"',
            "Сбросить раскладку",
            "Открыть на весь экран",
        ):
            self.assertIn(marker, body)
        script = (
            Path(__file__).resolve().parent / "static" / "dynamis" / "control_room.js"
        ).read_text(encoding="utf-8")
        self.assertIn("dynamis.control-room.layout", script)
        self.assertIn("localStorage", script)
        self.assertIn("left: 0.24", script)
        self.assertIn("center: 0.52", script)
        self.assertIn("right: 0.24", script)
        self.assertIn("bottom: 0.32", script)
        self.assertNotIn("sqlite", script.lower())
        self.assertNotIn("supabase", script.lower())
