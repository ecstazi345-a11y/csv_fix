"""Focused Django Human Surface tests — mock LND service, no product writes."""
from __future__ import annotations

import os
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

    def test_empty_command_is_not_accepted(self) -> None:
        response = self.client.post(reverse("control_room"), {"raw_text": "   "})
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Пустая команда не отправлена.", body)
        self.assertNotIn("Команда получена", body)
        self.assertNotIn("dynamis_human_command", self.client.session)

    def test_control_room_view_reads_without_write_actions(self) -> None:
        source = Path(__file__).with_name("views.py").read_text(encoding="utf-8")
        start = source.index("def control_room")
        end = source.index("\ndef architecture")
        room_view = source[start:end]
        room = Path(__file__).with_name("control_room_state.py").read_text(encoding="utf-8")
        adapter = Path(__file__).with_name("constructor_read_model.py").read_text(encoding="utf-8")
        commands = Path(__file__).with_name("human_command.py").read_text(encoding="utf-8")
        preview = Path(__file__).with_name("command_interpretation.py").read_text(encoding="utf-8")
        confirmation = Path(__file__).with_name("command_confirmation.py").read_text(encoding="utf-8")
        interpreter = (
            Path(__file__).resolve().parents[2]
            / "agents"
            / "human_surface"
            / "command_interpretation.py"
        ).read_text(encoding="utf-8")
        authority = (
            Path(__file__).resolve().parents[2]
            / "agents"
            / "human_surface"
            / "command_confirmation.py"
        ).read_text(encoding="utf-8")
        for blob in (room_view, room, adapter, commands, preview, confirmation, interpreter, authority):
            lowered = blob.lower()
            self.assertNotIn("launch_monthly_plan_mission", blob)
            self.assertNotIn("submit_human_review", blob)
            self.assertNotIn("import supabase", lowered)
            self.assertNotIn("services.supabase", lowered)
            self.assertNotIn("create_run", blob)
            self.assertNotIn("append_event", blob)
            self.assertNotIn("executescript", lowered)
            self.assertNotIn("openai", lowered)
            self.assertNotIn("yandex", lowered)
            self.assertNotIn("deepseek", lowered)
            self.assertNotIn("launch_monthly_plan_mission", blob)
        self.assertIn("control_room_context()", room_view)
        self.assertIn("load_constructor_control_room", room_view)
        self.assertIn("AgentControlRoomQueryPort", adapter)
        self.assertIn("resolve_observability_db_path", adapter)
        self.assertIn("mode=ro", adapter)
        self.assertNotIn(r"C:\csv_fix\.runtime", adapter)

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
        self.assertIn("shiftKey", script)
        self.assertIn("requestSubmit", script)
        self.assertNotIn("paste", script.lower())
        css = (
            Path(__file__).resolve().parent / "static" / "dynamis" / "control_room.css"
        ).read_text(encoding="utf-8")
        self.assertIn("grid-template-columns: 188px minmax(0, 1fr);", css)
        self.assertIn(
            "grid-template-columns: minmax(0, 24fr) 12px minmax(0, 52fr) 12px minmax(0, 24fr);",
            css,
        )
        self.assertIn("grid-template-rows: minmax(0, 68fr) 12px minmax(0, 32fr);", css)


def _file_fingerprint(root: Path) -> dict[str, tuple[int, int]]:
    if not root.exists():
        return {}
    found: dict[str, tuple[int, int]] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        stat = path.stat()
        found[str(path)] = (stat.st_size, stat.st_mtime_ns)
    return found


class _FakeConstructorPort:
    def __init__(self, snapshot, professional, registry) -> None:
        self.snapshot = snapshot
        self.professional = professional
        self.registry = registry
        self._store = self

    def close(self) -> None:
        return None

    def list_runs(self, **kwargs):
        from agents.control_room.dtos import AgentRunListView, AgentRunSummary

        run = self.snapshot.run
        return AgentRunListView(
            items=(
                AgentRunSummary(
                    run_id=run.run_id,
                    agent_code=run.agent_code,
                    project_code=run.project_code,
                    month_key=run.month_key,
                    mission_id=run.mission_id,
                    operational_status=run.operational_status,
                    requested_at=run.requested_at,
                    updated_at=run.updated_at,
                    started_at=run.started_at,
                    completed_at=run.completed_at,
                    projection_version=run.projection_version,
                ),
            ),
            runs_complete=True,
            source_count=1,
        )

    def get_run_snapshot(self, run_id: str, **kwargs):
        return self.snapshot

    def get_constructor_professional_result(self, run_id: str):
        return self.professional

    def get_constructor_decision_registry(self, run_id: str, **kwargs):
        return self.registry


def _proof_snapshot():
    from datetime import datetime, timezone

    from agents.control_room.dtos import (
        AgentEventView,
        AgentHumanDecisionSurfaceView,
        AgentHumanWaitView,
        AgentHandoffView,
        AgentProfessionalExecutionPathView,
        AgentRunDetail,
        AgentRunSnapshot,
        AgentStageOccurrenceView,
        AgentStageView,
        DerivationState,
        DigitalOrganizationExecutionView,
        HandoffStatus,
        ProfessionalExecutionState,
        ProfessionalExecutionStepKind,
        ProfessionalExecutionStepView,
        StageDisplayState,
    )

    when = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
    stage = AgentStageOccurrenceView(
        stage_id="stage-1",
        node_name="review",
        attempt_n=1,
        resume_n=0,
        artifact_id="",
        display_state=StageDisplayState.RUNNING,
        started_at=when,
        completed_at=None,
        started_event_id="evt-1",
        terminal_event_id=None,
    )
    wait = AgentHumanWaitView(
        waiting_for_human=False,
        interrupt_id=None,
        wait_started_at=None,
        decision_id=None,
        wait_closed_by=None,
        wait_ordinal=None,
        derivation_state=DerivationState.OK,
    )
    handoff = AgentHandoffView(
        handoff_id=None,
        status=HandoffStatus.NOT_STARTED,
        created_at=None,
        persisted_at=None,
        failed_at=None,
        handoff_type=None,
        target_role_code=None,
        artifact_type=None,
        artifact_id=None,
        derivation_state=DerivationState.OK,
    )
    run = AgentRunDetail(
        run_id="run-d1-proof",
        agent_code="MONTHLY_PLAN_CONSTRUCTOR",
        project_code="PRJ_001_БХК",
        month_key="ноябрь-2026",
        mission_id="mission-d1",
        operational_status="STARTING",
        requested_at=when,
        updated_at=when,
        started_at=when,
        completed_at=None,
        projection_version=1,
        request_id="req-d1",
        agent_version="0.1",
        orchestration_run_id=None,
        initiator_type="HUMAN",
        initiator_id="operator",
        trigger_type="MANUAL",
        trigger_reason="manual",
        attempt_n=1,
        resume_n=0,
        lifecycle_status=None,
        interrupt_id=None,
        decision_id=None,
        handoff_id=None,
        error_code=None,
        safe_error_summary=None,
        safe_summary=(),
        safe_counts=(),
    )
    return AgentRunSnapshot(
        run=run,
        stage=AgentStageView(
            current_stage=stage,
            occurrences=(stage,),
            derivation_state=DerivationState.OK,
        ),
        human_wait=wait,
        human_decision_surface=AgentHumanDecisionSurfaceView(
            wait=wait,
            request=None,
            decision=None,
            consequence=None,
            authority_modeled=False,
        ),
        handoff=handoff,
        professional_execution_path=AgentProfessionalExecutionPathView(
            steps=(
                ProfessionalExecutionStepView(
                    step_kind=ProfessionalExecutionStepKind.STAGE,
                    step_id="evt-1",
                    stage_id="stage-1",
                    professional_state=ProfessionalExecutionState.WAITING_FOR_HUMAN,
                    started_at=when,
                    completed_at=None,
                    attempt_n=1,
                    resume_n=0,
                    derivation_state=DerivationState.OK,
                    tools=(),
                    artifacts=(),
                    human_decision=None,
                    reality_refresh=None,
                    handoff_id=None,
                ),
            ),
            derivation_state=DerivationState.OK,
            history_complete=True,
        ),
        digital_organization=DigitalOrganizationExecutionView(
            source_agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            source_run_id="run-d1-proof",
            source_operational_status="STARTING",
            source_completed_at=None,
            handoff=None,
            history_complete=True,
            derivation_state=DerivationState.OK,
        ),
        timeline_events=(
            AgentEventView(
                event_id="evt-1",
                event_type="HUMAN_WAIT_STARTED",
                family="HUMAN",
                status="OK",
                title="Ожидание решения человека",
                occurred_at=when,
                stage_id="stage-1",
                node_name="review",
                attempt_n=1,
                resume_n=0,
                interrupt_id=None,
                decision_id=None,
                handoff_id=None,
                artifact_type=None,
                artifact_id=None,
                tool_name=None,
            ),
        ),
        events_complete=True,
        read_at=when,
    )


def _proof_professional():
    from agents.control_room.dtos import (
        ConstructorCandidateResultView,
        ConstructorProfessionalResultView,
        ProfessionalResultAvailability,
    )

    return ConstructorProfessionalResultView(
        availability=ProfessionalResultAvailability.AVAILABLE,
        run_id="run-d1-proof",
        mission_id="mission-d1",
        professional_status="WAITING_FOR_HUMAN_REVIEW",
        project_id="PRJ_001_БХК",
        month="ноябрь-2026",
        facility_id="",
        discipline="Автоматизация",
        source_candidate_package_id="package-d1",
        reviewed_package_id="",
        included_count=None,
        excluded_count=None,
        unresolved_count=None,
        confirm_event_id="",
        confirm_decision="",
        confirm_actor_type="",
        confirm_actor_id="",
        path_statuses=("PACKAGE_BUILT", "WAITING_FOR_HUMAN_REVIEW"),
        candidates=(
            ConstructorCandidateResultView(
                candidate_id="cand-1",
                boq_code="1500-02-03-09",
                name="Монтаж прибора",
                unit="шт",
                remaining_qty="2",
                already_planned_qty="0",
                available_qty="2",
                labor_status="UNRESOLVED",
                recommendation="HUMAN_REVIEW_REQUIRED",
                exception_codes=(),
                human_review_decision="",
                final_disposition="",
                final_reason_code="",
            ),
        ),
        mission_scope_row_count=None,
        package_candidate_count=None,
    )


@override_settings(
    ROOT_URLCONF="config.urls",
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
)
class ConstructorReadModelTests(SimpleTestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_adapter_shows_contract_fields_and_does_not_invent_counts(self) -> None:
        from agents.control_room.dtos import empty_constructor_decision_registry

        from dynamis.constructor_read_model import (
            NOT_IN_CONTRACT,
            load_constructor_control_room,
        )

        professional = _proof_professional()
        port = _FakeConstructorPort(
            _proof_snapshot(),
            professional,
            empty_constructor_decision_registry(professional),
        )
        state = load_constructor_control_room(
            agents=[{"code": "constructor", "name": "Constructor Agent", "status": "РАБОТАЕТ", "tone": "working", "description": "demo"}],
            port_factory=lambda: port,
        )
        self.assertEqual(state["read_model_meta"]["run_id"], "run-d1-proof")
        self.assertEqual(state["read_model_meta"]["package_id"], "package-d1")
        self.assertEqual(state["read_model_meta"]["human_decision"], "Требуется")
        self.assertEqual(state["read_model_meta"]["candidate_count"], NOT_IN_CONTRACT)
        rendered = " ".join(value for _label, value in state["constructor_facts"])
        self.assertIn(NOT_IN_CONTRACT, rendered)
        self.assertNotIn("660", rendered)
        self.assertEqual(state["agents"][0]["status"], "Запуск")
        self.assertEqual(state["table_rows"][0]["boq"], "1500-02-03-09")
        self.assertTrue(state["kpis"] == () or all(value != "660" for value, _label in state["kpis"]))

    def test_control_room_renders_adapter_state_without_demo_constructor(self) -> None:
        from dynamis.constructor_read_model import load_constructor_control_room
        from agents.control_room.dtos import empty_constructor_decision_registry

        professional = _proof_professional()
        port = _FakeConstructorPort(
            _proof_snapshot(),
            professional,
            empty_constructor_decision_registry(professional),
        )
        state = load_constructor_control_room(port_factory=lambda: port)
        with patch("dynamis.constructor_read_model.load_constructor_control_room", return_value=state):
            response = self.client.get(reverse("control_room"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("run-d1-proof", body)
        self.assertIn("package-d1", body)
        self.assertIn("Требуется", body)
        self.assertIn("Недоступно в текущем контракте чтения", body)
        self.assertNotIn("Демонстрационный фрагмент", body)
        self.assertNotIn("660", body)
        self.assertNotIn("Проверено позиций BOQ", body)
        self.assertIn('data-splitter="left"', body)
        self.assertEqual(body.count('data-demo="launch"'), 1)
        self.assertEqual(body.count('data-demo="admission"'), 1)

    def test_missing_store_fails_safe_and_creates_no_database(self) -> None:
        import os
        import tempfile

        from dynamis.constructor_read_model import load_constructor_control_room

        missing = Path(tempfile.gettempdir()) / "dynamis-d1-missing-observability.sqlite"
        if missing.exists():
            missing.unlink()
        with patch.dict(os.environ, {"AGENT_OBSERVABILITY_DB_PATH": str(missing)}):
            state = load_constructor_control_room(agents=[])
        self.assertFalse(missing.exists())
        self.assertFalse(state["runtime_available"])
        self.assertIn("недоступен", state["runtime_notice"].casefold())
        self.assertEqual(state["kpis"], ())
        self.assertEqual(state["table_rows"], ())

    def test_live_control_room_reads_existing_constructor_run_without_writes(self) -> None:
        from dynamis.constructor_read_model import (
            constructor_runtime_store_path,
            load_constructor_control_room,
        )

        store = constructor_runtime_store_path()
        self.assertIsNotNone(store)
        assert store is not None
        before = _file_fingerprint(store.parent)
        django_db = Path(__file__).resolve().parents[1] / "db.sqlite3"
        django_before = django_db.stat().st_mtime_ns if django_db.exists() else None
        response = self.client.get(reverse("control_room"))
        after_get = _file_fingerprint(store.parent)
        state = load_constructor_control_room()
        after_load = _file_fingerprint(store.parent)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(before, after_get)
        self.assertEqual(after_get, after_load)
        if django_before is not None:
            self.assertEqual(django_db.stat().st_mtime_ns, django_before)
        body = response.content.decode("utf-8")
        self.assertNotIn("Демонстрационный фрагмент", body)
        self.assertNotIn("Проверено позиций BOQ", body)
        self.assertNotIn(">660<", body)
        self.assertTrue(state["runtime_available"])
        run_id = state["read_model_meta"]["run_id"]
        self.assertTrue(run_id)
        self.assertIn(run_id, body)
        self.assertIn("Недоступно в текущем контракте чтения", body)


_ACCEPTED_COMMAND = (
    "Сформируй кандидатный состав на ноябрь 2026 по БХК, "
    "первая очередь, титул 16160-13, автоматика."
)
_ACCEPTED_RUN_ID = "run-3b457b4e-6183-44eb-83e4-803ce595691d"


@override_settings(
    ROOT_URLCONF="config.urls",
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
)
class HumanCommandInputTests(SimpleTestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_command_bar_is_a_plain_text_control(self) -> None:
        response = self.client.get(reverse("control_room"))
        body = response.content.decode("utf-8")
        self.assertIn("<textarea", body)
        self.assertIn('name="raw_text"', body)
        self.assertIn("Отправить", body)
        self.assertIn('method="post"', body)
        self.assertNotIn("Команда получена", body)
        script = (
            Path(__file__).resolve().parent / "static" / "dynamis" / "control_room.js"
        ).read_text(encoding="utf-8")
        self.assertNotIn("onpaste", script.lower())
        self.assertNotIn("clipboard", script.lower())
        self.assertIn("bindCommandSubmit", script)
        self.assertIn("DYNAMIS обрабатывает поручение…", script)
        self.assertIn("isSubmitting", script)

    def test_command_submit_lock_allows_one_enter_and_one_click(self) -> None:
        import shutil
        import subprocess
        import tempfile

        cscript = shutil.which("cscript")
        self.assertTrue(cscript)
        source = (
            Path(__file__).resolve().parent / "static" / "dynamis" / "control_room.js"
        ).read_text(encoding="utf-8")
        start = source.index("function bindCommandSubmit")
        end = source.index("if (typeof module", start)
        function_source = source[start:end]
        harness = function_source + r"""
function target() {
  var listeners = {};
  return {
    addEventListener: function (type, fn) {
      if (!listeners[type]) listeners[type] = [];
      listeners[type].push(fn);
    },
    emit: function (type, event) {
      var list = listeners[type] || [];
      for (var i = 0; i < list.length; i++) list[i](event);
    }
  };
}
function press(input, key, shiftKey) {
  var event = { key: key, shiftKey: !!shiftKey, prevented: false, preventDefault: function () { this.prevented = true; } };
  input.emit("keydown", event);
  return event;
}
function bind(text) {
  var form = target();
  var input = target();
  input.value = text;
  var button = { disabled: false };
  var notices = [];
  var submits = 0;
  var emit = form.emit;
  form.emit = function (type, event) {
    emit(type, event);
    if (type === "submit" && !event.prevented) submits += 1;
  };
  form.requestSubmit = function () {
    var event = { prevented: false, preventDefault: function () { this.prevented = true; } };
    form.emit("submit", event);
  };
  form.submit = function () { submits += 1; };
  bindCommandSubmit(form, input, button, function (notice) { notices.push(notice); });
  return { form: form, input: input, button: button, notices: notices, count: function () { return submits; } };
}
var enter = bind("discipline");
var firstEnter = press(enter.input, "Enter", false);
press(enter.input, "Enter", false);
var click = bind("discipline");
var firstClick = { prevented: false, preventDefault: function () { this.prevented = true; } };
click.form.emit("submit", firstClick);
var secondClick = { prevented: false, preventDefault: function () { this.prevented = true; } };
click.form.emit("submit", secondClick);
var shift = bind("line");
var shiftEnter = press(shift.input, "Enter", true);
var empty = bind("   ");
press(empty.input, "Enter", false);
var expectedNotice = "DYNAMIS обрабатывает поручение…";
WScript.Echo([
  firstEnter.prevented ? 1 : 0,
  enter.count(),
  enter.button.disabled ? 1 : 0,
  enter.notices[0] === expectedNotice ? "NOTICE_OK" : "NOTICE_BAD",
  firstClick.prevented ? 1 : 0,
  secondClick.prevented ? 1 : 0,
  click.count(),
  click.button.disabled ? 1 : 0,
  shiftEnter.prevented ? 1 : 0,
  shift.count(),
  empty.count(),
  empty.button.disabled ? 1 : 0
].join("|"));
"""
        with tempfile.NamedTemporaryFile(
            "w", suffix=".js", delete=False, encoding="utf-16"
        ) as handle:
            handle.write(harness)
            harness_path = handle.name
        completed = subprocess.run(
            [cscript, "//Nologo", harness_path],
            check=False,
            capture_output=True,
            text=True,
            encoding="cp866",
            errors="replace",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        parts = completed.stdout.strip().split("|")
        self.assertEqual(parts[0], "1")
        self.assertEqual(parts[1], "1")
        self.assertEqual(parts[2], "1")
        self.assertEqual(parts[3], "NOTICE_OK")
        self.assertEqual(parts[4], "0")
        self.assertEqual(parts[5], "1")
        self.assertEqual(parts[6], "1")
        self.assertEqual(parts[7], "1")
        self.assertEqual(parts[8], "0")
        self.assertEqual(parts[9], "0")
        self.assertEqual(parts[10], "0")
        self.assertEqual(parts[11], "0")

    def test_submit_shows_received_command_without_interpretation(self) -> None:
        response = self.client.post(
            reverse("control_room"),
            {"raw_text": _ACCEPTED_COMMAND},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn(_ACCEPTED_COMMAND, body)
        self.assertIn("Команда получена", body)
        self.assertIn("Constructor ещё не запущен", body)
        self.assertNotIn("DYNAMIS понимает команду", body)
        self.assertNotIn("все дисциплины", body)
        stored = self.client.session["dynamis_human_command"]
        self.assertEqual(stored["raw_text"], _ACCEPTED_COMMAND)
        self.assertEqual(stored["source"], "django_control_room")
        self.assertEqual(stored["input_mode"], "text")
        self.assertEqual(stored["processing_state"], "RECEIVED")
        self.assertTrue(stored["command_id"])
        self.assertTrue(stored["created_at"])

    def test_multiline_cyrillic_command_is_kept_verbatim(self) -> None:
        text = "Первая строка поручения\nВторая строка, без разбора полей"
        response = self.client.post(
            reverse("control_room"),
            {"raw_text": f"  {text}  "},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session["dynamis_human_command"]["raw_text"], text)
        body = response.content.decode("utf-8")
        self.assertIn("Первая строка поручения", body)
        self.assertIn("Вторая строка, без разбора полей", body)

    def test_rejected_command_keeps_the_previous_draft(self) -> None:
        from dynamis.human_command import MAX_HUMAN_COMMAND_LENGTH

        self.client.post(
            reverse("control_room"),
            {"raw_text": _ACCEPTED_COMMAND},
            follow=True,
        )
        kept = self.client.session["dynamis_human_command"]["command_id"]
        response = self.client.post(reverse("control_room"), {"raw_text": "  "})
        body = response.content.decode("utf-8")
        self.assertIn("Пустая команда не отправлена.", body)
        self.assertIn(_ACCEPTED_COMMAND, body)
        self.assertEqual(self.client.session["dynamis_human_command"]["command_id"], kept)
        too_long = "я" * (MAX_HUMAN_COMMAND_LENGTH + 1)
        response = self.client.post(reverse("control_room"), {"raw_text": too_long})
        self.assertIn("не отправлена", response.content.decode("utf-8"))
        self.assertEqual(self.client.session["dynamis_human_command"]["raw_text"], _ACCEPTED_COMMAND)
        self.assertEqual(self.client.session["dynamis_human_command"]["command_id"], kept)

    def test_long_command_is_rejected(self) -> None:
        from dynamis.human_command import MAX_HUMAN_COMMAND_LENGTH

        too_long = "я" * (MAX_HUMAN_COMMAND_LENGTH + 1)
        response = self.client.post(reverse("control_room"), {"raw_text": too_long})
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("не отправлена", body)
        self.assertNotIn("Команда получена", body)
        self.assertNotIn(too_long, body)
        self.assertNotIn("dynamis_human_command", self.client.session)

    def test_accepted_command_does_not_replace_or_write_constructor_run(self) -> None:
        from dynamis.constructor_read_model import (
            constructor_runtime_store_path,
            load_constructor_control_room,
        )

        store = constructor_runtime_store_path()
        self.assertIsNotNone(store)
        assert store is not None
        before_files = _file_fingerprint(store.parent)
        django_db = Path(__file__).resolve().parents[1] / "db.sqlite3"
        django_before = django_db.stat().st_mtime_ns if django_db.exists() else None
        before = load_constructor_control_room()["read_model_meta"]
        response = self.client.post(
            reverse("control_room"),
            {"raw_text": _ACCEPTED_COMMAND},
            follow=True,
        )
        after = load_constructor_control_room()["read_model_meta"]
        after_files = _file_fingerprint(store.parent)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(before["run_id"], _ACCEPTED_RUN_ID)
        self.assertEqual(after["run_id"], before["run_id"])
        self.assertEqual(after["mission_id"], before["mission_id"])
        self.assertEqual(after["package_id"], before["package_id"])
        self.assertEqual(before_files, after_files)
        if django_before is not None:
            self.assertEqual(django_db.stat().st_mtime_ns, django_before)
        body = response.content.decode("utf-8")
        self.assertIn(_ACCEPTED_RUN_ID, body)
        self.assertIn(_ACCEPTED_COMMAND, body)
        self.assertIn('data-splitter="left"', body)
        self.assertIn('data-splitter="bottom"', body)


def _scope_catalog():
    import pandas as pd

    from agents.human_surface.work_context import catalog_from_frame

    frame = pd.DataFrame(
        [
            {
                "project_code": "PRJ_001_БХК",
                "facility_building": "16160-13",
                "construction_discipline": "Автоматизация",
            },
            {
                "project_code": "PRJ_001_БХК",
                "facility_building": "16160-17",
                "construction_discipline": "Автоматизация",
            },
            {
                "project_code": "PRJ_001_БХК",
                "facility_building": "26160-13",
                "construction_discipline": "Вентиляция",
            },
        ]
    )
    return catalog_from_frame(frame)


def _interpret(text: str):
    from agents.human_surface.command_interpretation import interpret_command

    return interpret_command(command_id="cmd-test", raw_text=text, catalog=_scope_catalog())


@override_settings(
    ROOT_URLCONF="config.urls",
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
)
class CommandInterpretationTests(SimpleTestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_accepted_example_resolves_typed_preview(self) -> None:
        result = _interpret(_ACCEPTED_COMMAND)
        self.assertEqual(result.processing_state, "NEEDS_CONFIRMATION")
        self.assertEqual(result.resolution_status, "INTERPRETED")
        self.assertEqual(result.target_agent, "MONTHLY_PLAN_CONSTRUCTOR")
        self.assertEqual(result.intent, "FORM_CANDIDATE_PACKAGE")
        self.assertEqual(result.resolved_scope["project_code"], "PRJ_001_БХК")
        self.assertEqual(result.resolved_scope["month_key"], "ноябрь-2026")
        self.assertEqual(result.resolved_scope["queue"], "1")
        self.assertEqual(result.resolved_scope["facility"], "16160-13")
        self.assertEqual(result.resolved_scope["discipline"], "Автоматизация")
        self.assertEqual(result.unresolved_fields, ())
        self.assertEqual(result.ambiguities, ())
        self.assertFalse(result.mission_created)
        preview = dict(result.preview)
        self.assertEqual(preview["Агент"], "Constructor")
        self.assertEqual(preview["Проект"], "PRJ_001_БХК / БХК")
        self.assertEqual(preview["Период"], "ноябрь 2026")
        self.assertEqual(preview["Статус"], "Ожидается подтверждение")

    def test_vocabulary_is_not_one_hardcoded_sentence(self) -> None:
        result = _interpret(
            "Собери кандидатный состав на ноябрь-2026 по БХК, 1-я очередь, титул 16160-17, автоматизация."
        )
        self.assertEqual(result.processing_state, "NEEDS_CONFIRMATION")
        self.assertEqual(result.resolved_scope["month_key"], "ноябрь-2026")
        self.assertEqual(result.resolved_scope["queue"], "1")
        self.assertEqual(result.resolved_scope["facility"], "16160-17")
        self.assertEqual(result.resolved_scope["discipline"], "Автоматизация")

    def test_unknown_project_needs_clarification(self) -> None:
        result = _interpret("Сформируй кандидатный состав по проекту ABCXYZ")
        self.assertEqual(result.processing_state, "NEEDS_CLARIFICATION")
        self.assertNotIn("project_code", result.resolved_scope)
        self.assertIn("project", result.unresolved_fields)
        self.assertFalse(result.mission_created)

    def test_ambiguous_title_needs_clarification(self) -> None:
        result = _interpret(
            "Сформируй кандидатный состав на ноябрь 2026 по БХК, титул 13, автоматика."
        )
        self.assertEqual(result.processing_state, "NEEDS_CLARIFICATION")
        self.assertNotIn("facility", result.resolved_scope)
        self.assertTrue(result.ambiguities)

    def test_live_catalog_resolves_the_accepted_example(self) -> None:
        from agents.human_surface.command_interpretation import interpret_command
        from agents.human_surface.work_context import load_work_context_catalog

        catalog = load_work_context_catalog()
        self.assertFalse(catalog.error)
        self.assertTrue(catalog.facts)
        result = interpret_command(
            command_id="live",
            raw_text=_ACCEPTED_COMMAND,
            catalog=catalog,
        )
        self.assertEqual(result.processing_state, "NEEDS_CONFIRMATION")
        self.assertEqual(result.resolved_scope["project_code"], "PRJ_001_БХК")
        self.assertEqual(result.resolved_scope["facility"], "16160-13")
        self.assertEqual(result.resolved_scope["discipline"], "Автоматизация")
        self.assertFalse(result.mission_created)

    def test_unprofessional_text_creates_no_mission_draft(self) -> None:
        result = _interpret("привет")
        self.assertEqual(result.processing_state, "REJECTED")
        self.assertEqual(result.resolved_scope, {})
        self.assertEqual(result.preview, ())
        self.assertFalse(result.mission_created)

    def test_control_room_shows_preview_without_new_constructor_run(self) -> None:
        from dynamis.constructor_read_model import (
            constructor_runtime_store_path,
            load_constructor_control_room,
        )

        store = constructor_runtime_store_path()
        self.assertIsNotNone(store)
        assert store is not None
        before_files = _file_fingerprint(store.parent)
        before = load_constructor_control_room()["read_model_meta"]["run_id"]
        with patch(
            "dynamis.command_interpretation.load_work_context_catalog",
            return_value=_scope_catalog(),
        ):
            response = self.client.post(
                reverse("control_room"),
                {"raw_text": _ACCEPTED_COMMAND},
                follow=True,
            )
        after = load_constructor_control_room()["read_model_meta"]["run_id"]
        after_files = _file_fingerprint(store.parent)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Поручение понято", body)
        self.assertIn("PRJ_001_БХК / БХК", body)
        self.assertIn("ноябрь 2026", body)
        self.assertIn("16160-13", body)
        self.assertIn("Автоматизация", body)
        self.assertIn("Ожидается подтверждение", body)
        self.assertIn("Constructor ещё не запущен", body)
        self.assertIn("Подтвердить поручение", body)
        self.assertIn('name="action" value="confirm"', body)
        self.assertNotIn("Поручение подтверждено", body)
        self.assertIn('type="button" class="cr-btn cr-btn-primary" data-demo="launch"', body)
        self.assertIn(_ACCEPTED_RUN_ID, body)
        self.assertEqual(before, _ACCEPTED_RUN_ID)
        self.assertEqual(after, before)
        self.assertEqual(before_files, after_files)
        stored = self.client.session["dynamis_command_interpretation"]
        self.assertEqual(stored["processing_state"], "NEEDS_CONFIRMATION")
        self.assertFalse(stored["mission_created"])
        self.assertTrue(stored["interpretation_id"])
        self.assertEqual(stored["command_id"], self.client.session["dynamis_human_command"]["command_id"])
        self.assertIn('data-splitter="left"', body)
        self.assertIn('data-splitter="right"', body)
        self.assertIn('data-splitter="bottom"', body)


def _catalog_patches():
    catalog = _scope_catalog()
    return catalog, (
        patch("dynamis.command_interpretation.load_work_context_catalog", return_value=catalog),
        patch("dynamis.command_confirmation.load_work_context_catalog", return_value=catalog),
    )


@override_settings(
    ROOT_URLCONF="config.urls",
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
)
class CommandConfirmationTests(SimpleTestCase):
    def setUp(self) -> None:
        self.client = Client()

    def _confirm_page(self, text: str = _ACCEPTED_COMMAND):
        from services.monthly_plan_constructor_read_service import load_constructor_scope

        _catalog, patches = _catalog_patches()
        with patches[0], patches[1], patch(
            "services.monthly_plan_constructor_read_service.load_constructor_scope",
            wraps=load_constructor_scope,
        ) as scope_load:
            posted = self.client.post(reverse("control_room"), {"raw_text": text}, follow=True)
            confirmed = self.client.post(reverse("control_room"), {"action": "confirm"}, follow=True)
        return posted, confirmed, scope_load

    def test_valid_draft_can_be_confirmed(self) -> None:
        from agents.human_surface.command_confirmation import confirm_typed_draft

        draft = _interpret(_ACCEPTED_COMMAND)
        confirmed = confirm_typed_draft(
            draft,
            catalog=_scope_catalog(),
            source_text=_ACCEPTED_COMMAND,
        )
        self.assertEqual(confirmed.confirmation_state, "CONFIRMED")
        self.assertEqual(confirmed.command_id, draft.command_id)
        self.assertEqual(confirmed.interpretation_id, draft.interpretation_id)
        self.assertEqual(confirmed.target_agent, "MONTHLY_PLAN_CONSTRUCTOR")
        self.assertFalse(confirmed.as_dict()["mission_created"])
        self.assertFalse(confirmed.as_dict()["constructor_run_created"])
        _posted, response, _scope_load = self._confirm_page()
        body = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Поручение подтверждено", body)
        self.assertIn("Constructor ещё не запущен", body)
        self.assertNotIn("Подтвердить поручение", body)
        self.assertNotIn("Ожидается подтверждение", body)
        self.assertEqual(self.client.session["dynamis_command_confirmation"]["confirmation_state"], "CONFIRMED")

    def test_confirmation_stores_exact_scope_snapshot(self) -> None:
        from agents.human_surface.command_confirmation import confirm_typed_draft

        draft = _interpret(_ACCEPTED_COMMAND)
        confirmed = confirm_typed_draft(
            draft,
            catalog=_scope_catalog(),
            source_text=_ACCEPTED_COMMAND,
        )
        self.assertEqual(
            dict(confirmed.resolved_scope),
            {
                "project_code": "PRJ_001_БХК",
                "project_label": "БХК",
                "month_key": "ноябрь-2026",
                "planning_month": "ноябрь 2026",
                "queue": "1",
                "facility": "16160-13",
                "discipline": "Автоматизация",
            },
        )
        with self.assertRaises(TypeError):
            confirmed.resolved_scope["facility"] = "16160-17"
        _posted, _response, _scope_load = self._confirm_page()
        stored = self.client.session["dynamis_command_confirmation"]["resolved_scope"]
        self.assertEqual(stored["project_code"], "PRJ_001_БХК")
        self.assertEqual(stored["month_key"], "ноябрь-2026")
        self.assertEqual(stored["queue"], "1")
        self.assertEqual(stored["facility"], "16160-13")
        self.assertEqual(stored["discipline"], "Автоматизация")

    def test_confirmed_command_does_not_create_constructor_run(self) -> None:
        from dynamis.constructor_read_model import (
            constructor_runtime_store_path,
            load_constructor_control_room,
        )

        store = constructor_runtime_store_path()
        self.assertIsNotNone(store)
        assert store is not None
        before_files = _file_fingerprint(store.parent)
        django_db = Path(__file__).resolve().parents[1] / "db.sqlite3"
        django_before = django_db.stat().st_mtime_ns if django_db.exists() else None
        before = load_constructor_control_room()["read_model_meta"]
        _posted, response, scope_load = self._confirm_page()
        after = load_constructor_control_room()["read_model_meta"]
        self.assertEqual(before["run_id"], _ACCEPTED_RUN_ID)
        self.assertEqual(after["run_id"], before["run_id"])
        self.assertEqual(after["mission_id"], before["mission_id"])
        self.assertEqual(after["package_id"], before["package_id"])
        self.assertEqual(before_files, _file_fingerprint(store.parent))
        if django_before is not None:
            self.assertEqual(django_db.stat().st_mtime_ns, django_before)
        body = response.content.decode("utf-8")
        self.assertIn(_ACCEPTED_RUN_ID, body)
        self.assertIn(_ACCEPTED_COMMAND, body)
        self.assertIn("Поручение подтверждено", body)
        self.assertNotIn("dynamis_command_confirmation", body)
        scope_load.assert_not_called()

    def test_unresolved_draft_cannot_be_confirmed(self) -> None:
        from agents.human_surface.command_confirmation import ConfirmationRejected, confirm_typed_draft

        draft = _interpret("Сформируй кандидатный состав по проекту ABCXYZ")
        with self.assertRaises(ConfirmationRejected):
            confirm_typed_draft(
                draft,
                catalog=_scope_catalog(),
                source_text="Сформируй кандидатный состав по проекту ABCXYZ",
            )
        _catalog, patches = _catalog_patches()
        with patches[0], patches[1]:
            self.client.post(
                reverse("control_room"),
                {"raw_text": "Сформируй кандидатный состав по проекту ABCXYZ"},
                follow=True,
            )
            response = self.client.post(reverse("control_room"), {"action": "confirm"})
        self.assertIn("Поручение не подтверждено", response.content.decode("utf-8"))
        self.assertNotIn("dynamis_command_confirmation", self.client.session)

    def test_ambiguous_draft_cannot_be_confirmed(self) -> None:
        from agents.human_surface.command_confirmation import ConfirmationRejected, confirm_typed_draft

        text = "Сформируй кандидатный состав на ноябрь 2026 по БХК, титул 13, автоматика."
        draft = _interpret(text)
        self.assertTrue(draft.ambiguities)
        with self.assertRaises(ConfirmationRejected):
            confirm_typed_draft(draft, catalog=_scope_catalog(), source_text=text)
        _catalog, patches = _catalog_patches()
        with patches[0], patches[1]:
            self.client.post(reverse("control_room"), {"raw_text": text}, follow=True)
            response = self.client.post(reverse("control_room"), {"action": "confirm"})
        self.assertIn("Поручение не подтверждено", response.content.decode("utf-8"))
        self.assertNotIn("dynamis_command_confirmation", self.client.session)
        self.assertEqual(
            self.client.session["dynamis_command_interpretation"]["processing_state"],
            "NEEDS_CLARIFICATION",
        )

    def _write_session(self, session) -> None:
        from django.conf import settings

        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

    def test_changed_command_invalidates_prior_confirmation(self) -> None:
        self._confirm_page()
        previous = self.client.session["dynamis_command_confirmation"]["confirmation_id"]
        session = self.client.session
        command = dict(session["dynamis_human_command"])
        command["raw_text"] = command["raw_text"] + "\nуточнение"
        session["dynamis_human_command"] = command
        self._write_session(session)
        edited = self.client.get(reverse("control_room"))
        self.assertNotIn("Поручение подтверждено", edited.content.decode("utf-8"))
        _catalog, patches = _catalog_patches()
        with patches[0], patches[1]:
            response = self.client.post(
                reverse("control_room"),
                {
                    "raw_text": (
                        "Собери кандидатный состав на ноябрь-2026 по БХК, "
                        "1-я очередь, титул 16160-17, автоматизация."
                    )
                },
                follow=True,
            )
        body = response.content.decode("utf-8")
        self.assertNotIn("Поручение подтверждено", body)
        self.assertIn("Подтвердить поручение", body)
        self.assertNotEqual(
            self.client.session["dynamis_command_confirmation"]["command_id"],
            self.client.session["dynamis_human_command"]["command_id"],
        )
        self.assertEqual(self.client.session["dynamis_command_confirmation"]["confirmation_id"], previous)

    def test_changed_interpretation_invalidates_prior_confirmation(self) -> None:
        self._confirm_page()
        session = self.client.session
        stored = dict(session["dynamis_command_interpretation"])
        original_id = stored["interpretation_id"]
        stored["interpretation_id"] = "changed-interpretation"
        session["dynamis_command_interpretation"] = stored
        self._write_session(session)
        hidden = self.client.get(reverse("control_room"))
        self.assertNotIn("Поручение подтверждено", hidden.content.decode("utf-8"))
        self.assertIn("Подтвердить поручение", hidden.content.decode("utf-8"))
        session = self.client.session
        stored = dict(session["dynamis_command_interpretation"])
        stored["interpretation_id"] = original_id
        scope = dict(stored["resolved_scope"])
        scope["facility"] = "16160-17"
        stored["resolved_scope"] = scope
        session["dynamis_command_interpretation"] = stored
        self._write_session(session)
        shifted = self.client.get(reverse("control_room"))
        self.assertNotIn("Поручение подтверждено", shifted.content.decode("utf-8"))

    def test_empty_confirmation_request_fails_safe(self) -> None:
        from dataclasses import replace

        from agents.human_surface.command_confirmation import ConfirmationRejected, confirm_typed_draft

        response = self.client.post(reverse("control_room"), {"action": "confirm"})
        body = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Поручение не подтверждено", body)
        self.assertNotIn("dynamis_command_confirmation", self.client.session)
        self.assertNotIn("Команда получена", body)
        forged = self.client.post(
            reverse("control_room"),
            {"action": "confirm", "project_code": "PRJ_001_БХК", "confirmation_id": "forged"},
        )
        self.assertIn("Поручение не подтверждено", forged.content.decode("utf-8"))
        self.assertNotIn("dynamis_command_confirmation", self.client.session)
        draft = _interpret(_ACCEPTED_COMMAND)
        with self.assertRaises(ConfirmationRejected):
            confirm_typed_draft(
                replace(draft, target_agent="UNKNOWN_AGENT"),
                catalog=_scope_catalog(),
                source_text=_ACCEPTED_COMMAND,
            )
        with self.assertRaises(ConfirmationRejected):
            confirm_typed_draft(
                replace(draft, resolved_scope={**draft.resolved_scope, "month_key": "not-a-month"}),
                catalog=_scope_catalog(),
                source_text=_ACCEPTED_COMMAND,
            )

    def test_confirmation_page_keeps_existing_run_and_layout(self) -> None:
        _posted, response, _scope_load = self._confirm_page()
        body = response.content.decode("utf-8")
        css = (
            Path(__file__).resolve().parent / "static" / "dynamis" / "control_room.css"
        ).read_text(encoding="utf-8")
        self.assertIn(_ACCEPTED_RUN_ID, body)
        self.assertIn('data-splitter="left"', body)
        self.assertIn('data-splitter="right"', body)
        self.assertIn('data-splitter="bottom"', body)
        self.assertIn("grid-template-columns: 188px minmax(0, 1fr);", css)
        self.assertIn(
            "grid-template-columns: minmax(0, 24fr) 12px minmax(0, 52fr) 12px minmax(0, 24fr);",
            css,
        )
        self.assertIn("grid-template-rows: minmax(0, 68fr) 12px minmax(0, 32fr);", css)
        self.assertIn('type="button" class="cr-btn cr-btn-primary" data-demo="launch"', body)


_MESSY_COMMANDS = (
    "бхк нояб 1 очер 16160 13 автоматик сформируй кандидатов",
    "сформируй кондидатный соства по бхк на ноябр первая очередь автомаитка 16160-13",
    "сделай мне на ноябрь что можно взять по автоматике на 13 титуле по бхк первой очереди",
)


def _accepted_extraction():
    from agents.human_surface.command_interpreter_provider import CommandExtraction

    return CommandExtraction(
        intent="FORM_CANDIDATE_PACKAGE",
        target_agent_hint="constructor",
        project_hint="БХК",
        period_hint="ноябрь 2026",
        queue_hint="1",
        title_hint="16160-13",
        discipline_hint="автоматика",
    )


def _status_error(cls, status: int, code: str, param: str = "text", message: str = "failed"):
    import httpx

    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(
        status,
        request=request,
        headers={"x-request-id": "req_diag_1"},
        json={"error": {"message": message, "code": code, "param": param}},
    )
    return cls(message, response=response, body={"message": message, "code": code, "param": param})


class _HintProvider:
    def __init__(self, extraction=None, fail: bool = False) -> None:
        from agents.human_surface.command_interpreter_provider import (
            InterpreterUsage,
            ProviderExtractionResult,
        )

        self.calls: list[str] = []
        self.extraction = _accepted_extraction() if extraction is None else extraction
        self.fail = fail
        self._usage = InterpreterUsage("openai", "gpt-4.1-mini", 12, 8, 20, 5, not fail)
        self._result_type = ProviderExtractionResult

    def extract(self, raw_text: str):
        self.calls.append(raw_text)
        extraction = None if self.fail else self.extraction
        return self._result_type(extraction=extraction, usage=self._usage)


@override_settings(
    ROOT_URLCONF="config.urls",
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
)
class CommandInterpreterProviderTests(SimpleTestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_clear_command_does_not_call_provider(self) -> None:
        from agents.human_surface.command_understanding import understand_command

        provider = _HintProvider()
        understood = understand_command(
            command_id="clear",
            raw_text=_ACCEPTED_COMMAND,
            catalog=_scope_catalog(),
            provider=provider,
        )
        self.assertEqual(provider.calls, [])
        self.assertEqual(understood.channel, "deterministic")
        self.assertIsNone(understood.extraction)
        self.assertEqual(understood.interpretation.resolved_scope["project_code"], "PRJ_001_БХК")
        self.assertEqual(understood.interpretation.resolved_scope["facility"], "16160-13")

    def test_provider_hints_resolve_to_one_canonical_scope(self) -> None:
        from agents.human_surface.command_understanding import understand_command

        for text in (_ACCEPTED_COMMAND, *_MESSY_COMMANDS):
            provider = _HintProvider()
            understood = understand_command(
                command_id="hint",
                raw_text=text,
                catalog=_scope_catalog(),
                provider=provider,
            )
            scope = understood.interpretation.resolved_scope
            if text == _ACCEPTED_COMMAND:
                self.assertEqual(provider.calls, [])
                self.assertEqual(understood.channel, "deterministic")
            else:
                self.assertEqual(provider.calls, [text])
                self.assertEqual(understood.channel, "openai")
            self.assertEqual(understood.interpretation.processing_state, "NEEDS_CONFIRMATION")
            self.assertEqual(scope["project_code"], "PRJ_001_БХК")
            self.assertEqual(scope["month_key"], "ноябрь-2026")
            self.assertEqual(scope["queue"], "1")
            self.assertEqual(scope["facility"], "16160-13")
            self.assertEqual(scope["discipline"], "Автоматизация")
            self.assertNotIn("PRJ_001_БХК", provider.extraction.as_dict().values())

    def test_schema_rejects_prose_codes_and_extra_fields(self) -> None:
        from agents.human_surface.command_interpreter_provider import (
            ExtractionRejected,
            validate_extraction,
        )

        valid = _accepted_extraction().as_dict()
        self.assertEqual(validate_extraction(valid).project_hint, "БХК")
        with self.assertRaises(ExtractionRejected):
            validate_extraction("Проект БХК, титул 16160-13")
        coded = dict(valid)
        coded["project_hint"] = "PRJ_001_БХК"
        with self.assertRaises(ExtractionRejected):
            validate_extraction(coded)
        extra = dict(valid)
        extra["project_code"] = "PRJ_001_БХК"
        with self.assertRaises(ExtractionRejected):
            validate_extraction(extra)

    def test_provider_failure_keeps_deterministic_reading(self) -> None:
        from agents.human_surface.command_understanding import understand_command

        understood = understand_command(
            command_id="down",
            raw_text=_MESSY_COMMANDS[0],
            catalog=_scope_catalog(),
            provider=_HintProvider(fail=True),
        )
        self.assertEqual(understood.channel, "unavailable")
        self.assertIsNone(understood.extraction)
        self.assertNotEqual(understood.interpretation.processing_state, "NEEDS_CONFIRMATION")
        self.assertFalse(understood.interpretation.mission_created)

    def test_request_contains_only_the_command_and_a_short_schema(self) -> None:
        from agents.human_surface.openai_command_interpreter import (
            MAX_OUTPUT_TOKENS,
            MODEL,
            TEMPERATURE,
            request_arguments,
        )

        payload = request_arguments(_MESSY_COMMANDS[0])
        self.assertEqual(
            set(payload),
            {
                "model",
                "instructions",
                "input",
                "temperature",
                "max_output_tokens",
                "store",
                "text",
            },
        )
        self.assertEqual(payload["model"], MODEL)
        self.assertEqual(payload["temperature"], TEMPERATURE)
        self.assertEqual(payload["max_output_tokens"], MAX_OUTPUT_TOKENS)
        self.assertLessEqual(MAX_OUTPUT_TOKENS, 160)
        self.assertEqual(payload["input"], _MESSY_COMMANDS[0])
        self.assertEqual(payload["model"], "gpt-4.1-mini")
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["max_output_tokens"], 160)
        self.assertIs(payload["store"], False)
        self.assertNotIn("api_key", payload)
        self.assertNotIn("tools", payload)
        schema = payload["text"]["format"]
        self.assertEqual(schema["type"], "json_schema")
        self.assertIs(schema["strict"], True)
        self.assertEqual(schema["name"], "command_extraction")
        self.assertIs(schema["schema"]["additionalProperties"], False)
        self.assertEqual(set(schema["schema"]["required"]), set(schema["schema"]["properties"]))
        blob = str(payload).casefold()
        self.assertNotIn("candidate package", blob)
        self.assertNotIn("boq", blob)
        self.assertNotIn("prj_", blob)
        self.assertNotIn("observability", blob)
        source = (
            Path(__file__).resolve().parents[2]
            / "agents"
            / "human_surface"
            / "openai_command_interpreter.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("tools=", source)
        self.assertNotIn("supabase", source.lower())
        self.assertNotIn("create_run", source)
        self.assertNotIn("launch_monthly_plan_mission", source)

    def test_production_client_disables_sdk_retries(self) -> None:
        import json
        from unittest.mock import MagicMock

        from agents.human_surface.openai_command_interpreter import (
            MAX_SDK_RETRIES,
            MODEL,
            OpenAICommandInterpreter,
        )

        response = MagicMock()
        response.output_text = json.dumps(_accepted_extraction().as_dict(), ensure_ascii=False)
        response.usage.input_tokens = 3
        response.usage.output_tokens = 4
        response.usage.total_tokens = 7
        with patch("openai.OpenAI") as client_cls:
            client_cls.return_value.responses.create.return_value = response
            result = OpenAICommandInterpreter().extract(_MESSY_COMMANDS[0])
        client_cls.assert_called_once_with(max_retries=0)
        self.assertEqual(MAX_SDK_RETRIES, 0)
        client_cls.return_value.responses.create.assert_called_once()
        self.assertEqual(
            client_cls.return_value.responses.create.call_args.kwargs["model"],
            MODEL,
        )
        self.assertTrue(result.usage.success)
        self.assertIsNone(result.failure)
        self.assertEqual(result.extraction.project_hint, "БХК")

    def test_provider_failures_are_classified_once_and_redacted(self) -> None:
        import httpx
        from openai import (
            APIConnectionError,
            APITimeoutError,
            AuthenticationError,
            BadRequestError,
            InternalServerError,
            RateLimitError,
        )

        from agents.human_surface.openai_command_interpreter import OpenAICommandInterpreter

        cases = (
            (
                _status_error(
                    AuthenticationError,
                    401,
                    "invalid_api_key",
                    message="rejected sk-testSecretValue123 Bearer abcdef",
                ),
                "authentication",
                401,
            ),
            (_status_error(RateLimitError, 429, "insufficient_quota"), "rate_or_billing", 429),
            (_status_error(BadRequestError, 400, "invalid_request_error", param="text.format"), "configuration", 400),
            (_status_error(InternalServerError, 500, "server_error"), "provider_server", 500),
            (
                APIConnectionError(
                    message="Connection error.",
                    request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                ),
                "network",
                None,
            ),
            (
                APITimeoutError(httpx.Request("POST", "https://api.openai.com/v1/responses")),
                "network",
                None,
            ),
        )
        for exc, category, status in cases:
            with patch("openai.OpenAI") as client_cls:
                client_cls.return_value.responses.create.side_effect = exc
                result = OpenAICommandInterpreter().extract(_MESSY_COMMANDS[0])
            client_cls.return_value.responses.create.assert_called_once()
            self.assertIsNone(result.extraction)
            self.assertFalse(result.usage.success)
            self.assertEqual(result.failure.category, category)
            self.assertEqual(result.failure.http_status, status)
            self.assertEqual(result.failure.error_type, type(exc).__name__)
            self.assertNotIn("sk-", result.failure.safe_error_message)
            self.assertNotIn("Bearer", result.failure.safe_error_message)

    def test_invalid_structured_response_fails_closed_without_another_call(self) -> None:
        from unittest.mock import MagicMock

        from agents.human_surface.openai_command_interpreter import OpenAICommandInterpreter

        response = MagicMock()
        response.output_text = "это не JSON и ключ sk-liveSecretValue123"
        response.usage.input_tokens = 9
        response.usage.output_tokens = 2
        response.usage.total_tokens = 11
        with patch("openai.OpenAI") as client_cls:
            client_cls.return_value.responses.create.return_value = response
            result = OpenAICommandInterpreter().extract(_MESSY_COMMANDS[0])
        client_cls.return_value.responses.create.assert_called_once()
        self.assertEqual(result.failure.category, "response_validation")
        self.assertEqual(result.usage.total_tokens, 11)
        self.assertNotIn("sk-", result.failure.safe_error_message)
        self.assertIsNone(result.extraction)

    def test_messy_command_confirms_without_a_second_provider_call_or_run(self) -> None:
        from dynamis.constructor_read_model import (
            constructor_runtime_store_path,
            load_constructor_control_room,
        )

        provider = _HintProvider()
        store = constructor_runtime_store_path()
        self.assertIsNotNone(store)
        assert store is not None
        before_files = _file_fingerprint(store.parent)
        before = load_constructor_control_room()["read_model_meta"]["run_id"]
        catalog = _scope_catalog()
        with patch(
            "dynamis.command_interpretation.load_work_context_catalog",
            return_value=catalog,
        ), patch(
            "dynamis.command_confirmation.load_work_context_catalog",
            return_value=catalog,
        ), patch(
            "dynamis.command_interpretation.resolve_command_provider",
            return_value=provider,
        ):
            preview = self.client.post(
                reverse("control_room"),
                {"raw_text": _MESSY_COMMANDS[0]},
                follow=True,
            )
            confirmed = self.client.post(
                reverse("control_room"),
                {"action": "confirm"},
                follow=True,
            )
        body = confirmed.content.decode("utf-8")
        self.assertEqual(provider.calls, [_MESSY_COMMANDS[0]])
        self.assertIn("Интерпретация: OpenAI + проверка DYNAMIS", preview.content.decode("utf-8"))
        self.assertIn("Интерпретация: OpenAI + проверка DYNAMIS", body)
        self.assertIn("Поручение подтверждено", body)
        self.assertIn("Constructor ещё не запущен", body)
        self.assertIn("PRJ_001_БХК / БХК", body)
        self.assertEqual(
            self.client.session["dynamis_command_confirmation"]["confirmation_state"],
            "CONFIRMED",
        )
        self.assertFalse(self.client.session["dynamis_command_confirmation"]["mission_created"])
        self.assertFalse(
            self.client.session["dynamis_command_confirmation"]["constructor_run_created"]
        )
        self.assertEqual(load_constructor_control_room()["read_model_meta"]["run_id"], before)
        self.assertEqual(before, _ACCEPTED_RUN_ID)
        self.assertEqual(before_files, _file_fingerprint(store.parent))
        self.assertIn('data-splitter="left"', body)
        self.assertIn('data-splitter="right"', body)
        self.assertIn('data-splitter="bottom"', body)


_YANDEX_BASE_URL = "https://ai.api.cloud.yandex.net/v1"
_YANDEX_MODEL_URI = "gpt://b1g8bjuch0rbhn2rkpqg/yandexgpt/latest"
_YANDEX_FOLDER_ID = "b1g8bjuch0rbhn2rkpqg"
_YANDEX_FAKE_KEY = "AQVNunitkeyvalue0001"


def _yandex_env() -> dict[str, str]:
    return {
        "YANDEX_API_KEY": _YANDEX_FAKE_KEY,
        "YANDEX_FOLDER_ID": _YANDEX_FOLDER_ID,
        "YANDEX_BASE_URL": _YANDEX_BASE_URL,
        "YANDEX_MODEL_URI": _YANDEX_MODEL_URI,
    }


def _yandex_completion(content: str):
    from unittest.mock import MagicMock

    response = MagicMock()
    response.choices[0].message.content = content
    response.usage.prompt_tokens = 11
    response.usage.completion_tokens = 7
    response.usage.total_tokens = 18
    response.id = "chatcmpl_yandex_1"
    return response


@override_settings(
    ROOT_URLCONF="config.urls",
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
)
class YandexCommandInterpreterTests(SimpleTestCase):
    def test_yandex_provider_is_selected_without_openai_fallback(self) -> None:
        from agents.human_surface.command_understanding import select_command_provider
        from agents.human_surface.yandex_command_interpreter import YandexCommandInterpreter

        with patch.dict(os.environ, _yandex_env(), clear=False), patch(
            "agents.human_surface.openai_command_interpreter.build_openai_provider"
        ) as openai_builder:
            selected = select_command_provider("yandex")
        openai_builder.assert_not_called()
        self.assertIsInstance(selected, YandexCommandInterpreter)

    def test_missing_key_fails_closed_without_a_request_or_resolver(self) -> None:
        from agents.human_surface.command_understanding import select_command_provider
        from agents.human_surface.yandex_command_interpreter import interpret_with_yandex

        blocked = {**_yandex_env(), "YANDEX_API_KEY": ""}
        with patch.dict(os.environ, blocked, clear=False), patch("openai.OpenAI") as client_cls, patch(
            "agents.human_surface.yandex_command_interpreter.resolve_extraction"
        ) as resolver, patch(
            "agents.human_surface.openai_command_interpreter.build_openai_provider"
        ) as openai_builder:
            selected = select_command_provider("yandex")
            attempt = interpret_with_yandex(
                command_id="cmd-yandex",
                raw_text="бхк ноябрь",
                catalog=_scope_catalog(),
            )
        self.assertIsNone(selected)
        client_cls.assert_not_called()
        resolver.assert_not_called()
        openai_builder.assert_not_called()
        self.assertIsNone(attempt.result.extraction)
        self.assertEqual(attempt.result.usage.provider_call_count, 0)
        self.assertEqual(attempt.result.usage.retry_count, 0)
        self.assertFalse(attempt.result.usage.schema_validation_pass)
        self.assertFalse(attempt.deterministic_resolution_pass)
        self.assertFalse(attempt.mission_created)
        self.assertFalse(attempt.constructor_run_created)

    def test_client_uses_configured_endpoint_once_without_retries_or_tools(self) -> None:
        import json

        import httpx

        from agents.human_surface.yandex_command_interpreter import (
            CONNECT_TIMEOUT_SECONDS,
            MAX_SDK_RETRIES,
            POOL_TIMEOUT_SECONDS,
            READ_TIMEOUT_SECONDS,
            WRITE_TIMEOUT_SECONDS,
            YandexCommandInterpreter,
            yandex_configuration,
            yandex_key_present,
        )

        self.assertTrue(yandex_key_present())
        public = yandex_configuration()
        self.assertEqual(public["base_url"], _YANDEX_BASE_URL)
        self.assertEqual(public["model"], _YANDEX_MODEL_URI)
        self.assertEqual(public["folder_id"], _YANDEX_FOLDER_ID)
        self.assertNotIn("api_key", public)
        self.assertEqual(MAX_SDK_RETRIES, 0)
        payload = json.dumps(_accepted_extraction().as_dict(), ensure_ascii=False)
        with patch.dict(os.environ, _yandex_env(), clear=False), patch("openai.OpenAI") as client_cls:
            client_cls.return_value.chat.completions.create.return_value = _yandex_completion(payload)
            result = YandexCommandInterpreter().extract("бхк ноябрь")
        client_cls.assert_called_once()
        client_cls.return_value.chat.completions.create.assert_called_once()
        constructor = client_cls.call_args.kwargs
        request = client_cls.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(constructor["base_url"], _YANDEX_BASE_URL)
        self.assertEqual(constructor["project"], _YANDEX_FOLDER_ID)
        self.assertEqual(constructor["max_retries"], 0)
        self.assertTrue(constructor["api_key"] == _YANDEX_FAKE_KEY)
        timeout = constructor["timeout"]
        self.assertIsInstance(timeout, httpx.Timeout)
        self.assertEqual(timeout.connect, CONNECT_TIMEOUT_SECONDS)
        self.assertEqual(timeout.connect, 20.0)
        self.assertEqual(timeout.read, READ_TIMEOUT_SECONDS)
        self.assertEqual(timeout.read, 60.0)
        self.assertEqual(timeout.write, WRITE_TIMEOUT_SECONDS)
        self.assertEqual(timeout.write, 30.0)
        self.assertEqual(timeout.pool, POOL_TIMEOUT_SECONDS)
        self.assertEqual(timeout.pool, 20.0)
        self.assertEqual(request["model"], _YANDEX_MODEL_URI)
        self.assertEqual(request["temperature"], 0)
        self.assertEqual(request["max_tokens"], 160)
        self.assertEqual(request["response_format"], {"type": "json_object"})
        self.assertNotIn("tools", request)
        self.assertNotIn("timeout", request)
        self.assertNotIn("api_key", request)
        self.assertNotIn(_YANDEX_FAKE_KEY, json.dumps(request, ensure_ascii=False))
        self.assertTrue(result.usage.schema_validation_pass)
        self.assertEqual(result.usage.provider, "yandex")
        self.assertEqual(result.usage.provider_call_count, 1)
        self.assertEqual(result.usage.retry_count, 0)
        self.assertEqual(result.usage.input_tokens, 11)
        self.assertEqual(result.usage.output_tokens, 7)
        self.assertEqual(result.usage.total_tokens, 18)
        self.assertEqual(result.extraction.project_hint, "БХК")

    def test_valid_extraction_reaches_the_existing_resolver_once(self) -> None:
        import json

        from agents.human_surface.yandex_command_interpreter import interpret_with_yandex

        payload = json.dumps(_accepted_extraction().as_dict(), ensure_ascii=False)
        with patch.dict(os.environ, _yandex_env(), clear=False), patch("openai.OpenAI") as client_cls, patch(
            "agents.human_surface.openai_command_interpreter.build_openai_provider"
        ) as openai_builder:
            client_cls.return_value.chat.completions.create.return_value = _yandex_completion(payload)
            attempt = interpret_with_yandex(
                command_id="cmd-yandex",
                raw_text="бхк нояб 1 очер 16160 13 автоматик",
                catalog=_scope_catalog(),
            )
        client_cls.return_value.chat.completions.create.assert_called_once()
        openai_builder.assert_not_called()
        self.assertTrue(attempt.deterministic_resolution_pass)
        self.assertEqual(attempt.interpretation.resolved_scope["project_code"], "PRJ_001_БХК")
        self.assertEqual(attempt.interpretation.resolved_scope["month_key"], "ноябрь-2026")
        self.assertEqual(attempt.interpretation.resolved_scope["queue"], "1")
        self.assertEqual(attempt.interpretation.resolved_scope["facility"], "16160-13")
        self.assertEqual(attempt.interpretation.resolved_scope["discipline"], "Автоматизация")
        self.assertFalse(attempt.interpretation.mission_created)
        self.assertFalse(attempt.mission_created)
        self.assertFalse(attempt.constructor_run_created)
        self.assertEqual(attempt.result.usage.provider_call_count, 1)
        self.assertEqual(attempt.result.usage.retry_count, 0)

    def test_malformed_response_fails_closed_before_the_resolver(self) -> None:
        from agents.human_surface.yandex_command_interpreter import interpret_with_yandex

        with patch.dict(os.environ, _yandex_env(), clear=False), patch("openai.OpenAI") as client_cls, patch(
            "agents.human_surface.yandex_command_interpreter.resolve_extraction"
        ) as resolver:
            client_cls.return_value.chat.completions.create.return_value = _yandex_completion(
                "не json, ключ AQVNunitkeyvalue0001"
            )
            attempt = interpret_with_yandex(
                command_id="cmd-yandex",
                raw_text="бхк",
                catalog=_scope_catalog(),
            )
        client_cls.return_value.chat.completions.create.assert_called_once()
        resolver.assert_not_called()
        self.assertIsNone(attempt.result.extraction)
        self.assertEqual(attempt.result.failure.category, "response_validation")
        self.assertFalse(attempt.result.usage.schema_validation_pass)
        self.assertFalse(attempt.deterministic_resolution_pass)
        self.assertFalse(attempt.mission_created)
        self.assertFalse(attempt.constructor_run_created)
        self.assertNotIn(_YANDEX_FAKE_KEY, attempt.result.failure.safe_error_message)
        self.assertNotIn("AQVN", attempt.result.failure.safe_error_message)

    def test_provider_error_does_not_resolve_or_create_a_mission(self) -> None:
        from openai import AuthenticationError

        from agents.human_surface.yandex_command_interpreter import interpret_with_yandex

        secret_message = "rejected key AQVNunitkeyvalue0001 and sk-liveSecretValue123"
        with patch.dict(os.environ, _yandex_env(), clear=False), patch("openai.OpenAI") as client_cls, patch(
            "agents.human_surface.yandex_command_interpreter.resolve_extraction"
        ) as resolver, self.assertLogs("dynamis.command_interpreter", level="INFO") as captured:
            client_cls.return_value.chat.completions.create.side_effect = _status_error(
                AuthenticationError,
                401,
                "invalid_api_key",
                message=secret_message,
            )
            attempt = interpret_with_yandex(
                command_id="cmd-yandex",
                raw_text="бхк",
                catalog=_scope_catalog(),
            )
        client_cls.return_value.chat.completions.create.assert_called_once()
        resolver.assert_not_called()
        self.assertEqual(attempt.result.failure.category, "authentication")
        self.assertEqual(attempt.result.failure.http_status, 401)
        self.assertEqual(attempt.result.failure.error_code, "invalid_api_key")
        self.assertEqual(attempt.result.usage.provider, "yandex")
        self.assertEqual(attempt.result.usage.provider_call_count, 1)
        self.assertEqual(attempt.result.usage.retry_count, 0)
        self.assertFalse(attempt.result.usage.success)
        self.assertFalse(attempt.result.usage.schema_validation_pass)
        self.assertFalse(attempt.deterministic_resolution_pass)
        self.assertIsNone(attempt.interpretation)
        self.assertFalse(attempt.mission_created)
        self.assertFalse(attempt.constructor_run_created)
        self.assertNotIn(_YANDEX_FAKE_KEY, attempt.result.failure.safe_error_message)
        self.assertNotIn("sk-", attempt.result.failure.safe_error_message)
        logged = "\n".join(captured.output)
        self.assertNotIn(_YANDEX_FAKE_KEY, logged)
        self.assertNotIn("sk-liveSecretValue123", logged)

    def test_adapter_has_no_runtime_or_provider_fallback(self) -> None:
        source = Path(__file__).resolve().parents[2].joinpath(
            "agents", "human_surface", "yandex_command_interpreter.py"
        ).read_text(encoding="utf-8").casefold()
        self.assertEqual(source.count("chat.completions.create"), 1)
        self.assertIn("httpx.timeout(", source)
        self.assertNotIn("responses.create", source)
        self.assertNotIn("build_openai_provider", source)
        self.assertNotIn("launch_monthly_plan", source)
        self.assertNotIn("supabase", source)
        self.assertNotIn("create_run", source)
        self.assertNotIn("append_event", source)
        self.assertNotIn("monthly_plan_constructor -> constructor", source)
        self.assertNotIn("normalize", source)

    def test_yandex_instruction_requires_exact_string_contract(self) -> None:
        from agents.human_surface.command_interpreter_provider import EXTRACTION_FIELDS
        from agents.human_surface.yandex_command_interpreter import (
            _INSTRUCTION,
            yandex_request_arguments,
        )

        text = _INSTRUCTION
        for key in EXTRACTION_FIELDS:
            self.assertIn(key, text)
        self.assertIn("FORM_CANDIDATE_PACKAGE", text)
        self.assertIn("constructor", text)
        self.assertIn("string", text.casefold())
        self.assertIn("null", text.casefold())
        self.assertIn("markdown", text.casefold())
        self.assertIn("MONTHLY_PLAN_CONSTRUCTOR", text)
        self.assertIn('""', text)
        request = yandex_request_arguments("бхк ноябрь", _YANDEX_MODEL_URI)
        self.assertEqual(request["messages"][0]["content"], _INSTRUCTION)
        self.assertNotIn("PRJ_001", _INSTRUCTION)

    def test_invalid_extraction_preserves_safe_rejection_detail(self) -> None:
        import json

        from agents.human_surface.yandex_command_interpreter import interpret_with_yandex

        bad = _accepted_extraction().as_dict()
        bad["target_agent_hint"] = "MONTHLY_PLAN_CONSTRUCTOR"
        with patch.dict(os.environ, _yandex_env(), clear=False), patch("openai.OpenAI") as client_cls, patch(
            "agents.human_surface.yandex_command_interpreter.resolve_extraction"
        ) as resolver:
            client_cls.return_value.chat.completions.create.return_value = _yandex_completion(
                json.dumps(bad, ensure_ascii=False)
            )
            attempt = interpret_with_yandex(
                command_id="cmd-yandex",
                raw_text="бхк",
                catalog=_scope_catalog(),
            )
        client_cls.return_value.chat.completions.create.assert_called_once()
        resolver.assert_not_called()
        self.assertIsNone(attempt.result.extraction)
        self.assertEqual(attempt.result.failure.category, "response_validation")
        self.assertEqual(attempt.result.failure.error_type, "ExtractionRejected")
        detail = attempt.result.failure.safe_error_message
        self.assertTrue(detail.startswith("ExtractionRejected:"))
        self.assertIn("target agent hint is outside the allowed vocabulary", detail)
        self.assertFalse(attempt.deterministic_resolution_pass)
        self.assertFalse(attempt.mission_created)
        self.assertFalse(attempt.constructor_run_created)

    def test_extraction_rejected_secret_text_is_redacted(self) -> None:
        from agents.human_surface.command_interpreter_provider import ExtractionRejected
        from agents.human_surface.openai_command_interpreter import classify_provider_failure

        failure = classify_provider_failure(
            ExtractionRejected("bad key AQVNunitkeyvalue0001 and sk-liveSecretValue123")
        )
        self.assertEqual(failure.category, "response_validation")
        self.assertTrue(failure.safe_error_message.startswith("ExtractionRejected:"))
        self.assertNotIn("AQVN", failure.safe_error_message)
        self.assertNotIn("sk-liveSecretValue123", failure.safe_error_message)
        self.assertIn("[redacted]", failure.safe_error_message)

    def test_openai_provider_keeps_sdk_default_timeout(self) -> None:
        """Yandex bounded timeout must not leak into the OpenAI provider client."""
        import json
        from unittest.mock import MagicMock

        from agents.human_surface.openai_command_interpreter import OpenAICommandInterpreter

        response = MagicMock()
        response.output_text = json.dumps(_accepted_extraction().as_dict(), ensure_ascii=False)
        response.usage.input_tokens = 3
        response.usage.output_tokens = 4
        response.usage.total_tokens = 7
        with patch("openai.OpenAI") as client_cls:
            client_cls.return_value.responses.create.return_value = response
            OpenAICommandInterpreter().extract(_MESSY_COMMANDS[0])
        client_cls.assert_called_once_with(max_retries=0)
        self.assertNotIn("timeout", client_cls.call_args.kwargs)


def _partial_yandex_extraction():
    from agents.human_surface.command_interpreter_provider import CommandExtraction

    return CommandExtraction(
        intent="FORM_CANDIDATE_PACKAGE",
        target_agent_hint="constructor",
        project_hint="БХК",
        period_hint="ноябрь",
        queue_hint="1",
        title_hint="16160-13",
        discipline_hint="",
        system_hint="",
        iwp_hint="",
    )


class _YandexSurfaceProvider:
    def __init__(self, extraction=None, *, fail: bool = False, leak_secret: bool = False) -> None:
        from agents.human_surface.command_interpreter_provider import (
            InterpreterUsage,
            ProviderExtractionResult,
            ProviderFailure,
        )

        self.calls: list[str] = []
        self.extraction = _accepted_extraction() if extraction is None else extraction
        self.fail = fail
        self.leak_secret = leak_secret
        self._usage = InterpreterUsage(
            "yandex",
            _YANDEX_MODEL_URI,
            11,
            7,
            18,
            42,
            not fail,
            provider_call_count=1,
            retry_count=0,
            request_id="chatcmpl_yandex_surface",
            schema_validation_pass=False if fail else True,
        )
        self._result_type = ProviderExtractionResult
        self._failure_type = ProviderFailure

    def extract(self, raw_text: str):
        self.calls.append(raw_text)
        if not self.fail:
            return self._result_type(extraction=self.extraction, usage=self._usage)
        message = (
            "rejected key AQVNunitkeyvalue0001 and sk-liveSecretValue123"
            if self.leak_secret
            else "YandexGPT request failed"
        )
        return self._result_type(
            extraction=None,
            usage=self._usage,
            failure=self._failure_type(
                category="provider_error",
                error_type="ProviderError",
                error_code="failed",
                error_param="",
                http_status=500,
                request_id="chatcmpl_yandex_surface",
                safe_error_message=message,
            ),
        )


@override_settings(
    ROOT_URLCONF="config.urls",
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
)
class YandexControlRoomSurfaceTests(SimpleTestCase):
    def setUp(self) -> None:
        self.client = Client()

    def _post_with_provider(self, provider, text: str = _MESSY_COMMANDS[0]):
        catalog = _scope_catalog()
        with patch(
            "dynamis.command_interpretation.load_work_context_catalog",
            return_value=catalog,
        ), patch(
            "dynamis.command_interpretation.resolve_command_provider",
            return_value=provider,
        ):
            return self.client.post(reverse("control_room"), {"raw_text": text}, follow=True)

    def test_django_provider_prefers_yandex_without_view_hardcode(self) -> None:
        from dynamis.command_provider import resolve_command_provider
        from agents.human_surface.yandex_command_interpreter import YandexCommandInterpreter

        views = Path(__file__).with_name("views.py").read_text(encoding="utf-8")
        start = views.index("def control_room")
        end = views.index("\ndef architecture")
        room_view = views[start:end].casefold()
        self.assertNotIn("yandex", room_view)
        self.assertNotIn("openai", room_view)
        self.assertNotIn("build_yandex_provider", room_view)
        with patch.dict(os.environ, _yandex_env(), clear=False), patch(
            "agents.human_surface.openai_command_interpreter.build_openai_provider"
        ) as openai_builder:
            selected = resolve_command_provider()
        openai_builder.assert_not_called()
        self.assertIsInstance(selected, YandexCommandInterpreter)

    def test_valid_yandex_extraction_is_shown_without_mission_or_constructor(self) -> None:
        provider = _YandexSurfaceProvider()
        response = self._post_with_provider(provider)
        body = response.content.decode("utf-8")
        self.assertEqual(provider.calls, [_MESSY_COMMANDS[0]])
        self.assertIn(_MESSY_COMMANDS[0], body)
        self.assertIn("Интерпретация: YandexGPT + проверка DYNAMIS", body)
        self.assertIn("Что поняла LLM", body)
        self.assertIn("yandex", body)
        self.assertIn(_YANDEX_MODEL_URI, body)
        self.assertIn("FORM_CANDIDATE_PACKAGE", body)
        self.assertIn("constructor", body)
        self.assertIn("БХК", body)
        self.assertIn("ноябрь 2026", body)
        self.assertIn("Что подтвердил DYNAMIS", body)
        self.assertIn("PRJ_001_БХК", body)
        self.assertIn("ноябрь-2026", body)
        self.assertIn("Автоматизация", body)
        self.assertIn("NEEDS_CONFIRMATION", body)
        self.assertIn("Schema validation</dt><dd>YES</dd>", body)
        self.assertIn("Deterministic resolution</dt><dd>YES</dd>", body)
        self.assertIn("LLM telemetry", body)
        self.assertIn("chatcmpl_yandex_surface", body)
        self.assertIn("Input tokens</dt><dd>11</dd>", body)
        self.assertIn("Output tokens</dt><dd>7</dd>", body)
        self.assertIn("Total tokens</dt><dd>18</dd>", body)
        self.assertIn("Latency ms</dt><dd>42</dd>", body)
        stored = self.client.session["dynamis_command_interpretation"]
        self.assertEqual(stored["interpretation_channel"], "yandex")
        self.assertFalse(stored["mission_created"])
        self.assertNotIn("dynamis_command_confirmation", self.client.session)
        self.assertNotIn(_YANDEX_FAKE_KEY, body)
        self.assertNotIn("AQVN", body)
        self.assertNotIn("Authorization", body)

    def test_needs_clarification_is_shown_honestly(self) -> None:
        provider = _YandexSurfaceProvider(extraction=_partial_yandex_extraction())
        response = self._post_with_provider(provider)
        body = response.content.decode("utf-8")
        self.assertEqual(provider.calls, [_MESSY_COMMANDS[0]])
        self.assertIn("Что поняла LLM", body)
        self.assertIn("FORM_CANDIDATE_PACKAGE", body)
        self.assertIn("constructor", body)
        self.assertIn("БХК", body)
        self.assertIn("ноябрь", body)
        self.assertIn("16160-13", body)
        self.assertIn("Discipline hint</dt><dd>&quot;&quot;</dd>", body)
        self.assertIn("NEEDS_CLARIFICATION", body)
        self.assertIn("Не определено / Требуется уточнение", body)
        self.assertIn("Не определено:", body)
        self.assertIn("Schema validation</dt><dd>YES</dd>", body)
        self.assertIn("Deterministic resolution</dt><dd>NO</dd>", body)
        stored = self.client.session["dynamis_command_interpretation"]
        self.assertEqual(stored["processing_state"], "NEEDS_CLARIFICATION")
        self.assertEqual(stored["interpretation_channel"], "yandex")
        self.assertFalse(stored["mission_created"])
        self.assertTrue(stored.get("unresolved_fields"))
        self.assertNotIn("dynamis_command_confirmation", self.client.session)
        self.assertNotIn("Поручение подтверждено", body)

    def test_provider_failure_is_fail_closed_and_secret_safe(self) -> None:
        provider = _YandexSurfaceProvider(fail=True, leak_secret=True)
        response = self._post_with_provider(provider)
        body = response.content.decode("utf-8")
        self.assertEqual(provider.calls, [_MESSY_COMMANDS[0]])
        self.assertIn("Интеллектуальная интерпретация недоступна.", body)
        self.assertIn("Ошибка провайдера:", body)
        self.assertIn("чувствительный фрагмент", body)
        self.assertNotIn(_YANDEX_FAKE_KEY, body)
        self.assertNotIn("AQVN", body)
        self.assertNotIn("sk-liveSecretValue123", body)
        self.assertIn("LLM telemetry", body)
        self.assertIn("chatcmpl_yandex_surface", body)
        stored = self.client.session["dynamis_command_interpretation"]
        self.assertEqual(stored["interpretation_channel"], "unavailable")
        self.assertFalse(stored["mission_created"])
        self.assertNotIn("dynamis_command_confirmation", self.client.session)
        self.assertNotIn("Поручение подтверждено", body)

    def test_yandex_surface_keeps_d2c_confirmation_semantics(self) -> None:
        provider = _YandexSurfaceProvider()
        catalog = _scope_catalog()
        with patch(
            "dynamis.command_interpretation.load_work_context_catalog",
            return_value=catalog,
        ), patch(
            "dynamis.command_confirmation.load_work_context_catalog",
            return_value=catalog,
        ), patch(
            "dynamis.command_interpretation.resolve_command_provider",
            return_value=provider,
        ):
            preview = self.client.post(
                reverse("control_room"),
                {"raw_text": _MESSY_COMMANDS[0]},
                follow=True,
            )
            confirmed = self.client.post(
                reverse("control_room"),
                {"action": "confirm"},
                follow=True,
            )
        body = confirmed.content.decode("utf-8")
        self.assertIn("Интерпретация: YandexGPT + проверка DYNAMIS", preview.content.decode("utf-8"))
        self.assertIn("Поручение подтверждено", body)
        self.assertIn("Constructor ещё не запущен", body)
        self.assertEqual(
            self.client.session["dynamis_command_confirmation"]["confirmation_state"],
            "CONFIRMED",
        )
        self.assertFalse(self.client.session["dynamis_command_confirmation"]["mission_created"])
        self.assertFalse(
            self.client.session["dynamis_command_confirmation"]["constructor_run_created"]
        )


def _manual_scope_catalog(rows):
    from agents.human_surface.work_context import ScopeFact, WorkContextCatalog

    facts = tuple(
        ScopeFact(
            project_label=row["project_label"],
            project_code=row["project_code"],
            queue=row["queue"],
            facility=row["facility"],
            title=row["facility"],
            discipline=row["discipline"],
            systems=(),
            packages=(),
        )
        for row in rows
    )
    return WorkContextCatalog(
        source="test",
        error="",
        months=("ноябрь 2026",),
        facts=facts,
    )


@override_settings(
    ROOT_URLCONF="config.urls",
    ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"],
)
def _quoted_human_command(body: str) -> str:
    marker = '<p class="cr-kicker">Команда человека</p>'
    start = body.index(marker)
    open_tag = '<blockquote class="cr-command">'
    quote_start = body.index(open_tag, start)
    quote_end = body.index("</blockquote>", quote_start)
    return body[quote_start + len(open_tag):quote_end]


class SemanticScopeD2B2Tests(SimpleTestCase):
    def test_candidate_package_intent_stays_candidate_package(self) -> None:
        from agents.human_surface.command_interpretation import INTENT_FORM_CANDIDATE_PACKAGE

        result = _interpret(
            "Сформируй кандидатный состав на ноябрь 2026 по БХК, "
            "титул 16160-13, автоматизация."
        )
        self.assertEqual(result.intent, INTENT_FORM_CANDIDATE_PACKAGE)
        self.assertEqual(result.processing_state, "NEEDS_CONFIRMATION")
        self.assertEqual(result.resolved_scope["queue"], "1")
        self.assertEqual(result.resolved_scope["queue_source"], "CANONICAL_TITLE_RELATION")
        self.assertFalse(result.mission_created)

    def test_monthly_commitment_is_not_collapsed_to_candidate_package(self) -> None:
        from agents.human_surface.command_interpretation import (
            INTENT_FORM_CANDIDATE_PACKAGE,
            INTENT_FORM_MONTHLY_COMMITMENT,
        )
        from agents.human_surface.command_interpreter_provider import (
            CommandExtraction,
            resolve_extraction,
            validate_extraction,
        )

        result = _interpret(
            "Сформируй месячное обязательство на ноябрь 2026 по БХК, "
            "титул 16160-13, автоматизация."
        )
        self.assertEqual(result.intent, INTENT_FORM_MONTHLY_COMMITMENT)
        self.assertNotEqual(result.intent, INTENT_FORM_CANDIDATE_PACKAGE)
        self.assertEqual(result.processing_state, "NEEDS_CONFIRMATION")
        self.assertEqual(result.resolution_status, "INTERPRETED")
        self.assertEqual(result.unresolved_fields, ())
        self.assertEqual(result.ambiguities, ())
        self.assertEqual(result.resolved_scope.get("queue"), "1")
        self.assertEqual(result.resolved_scope.get("queue_source"), "CANONICAL_TITLE_RELATION")
        preview = dict(result.preview)
        self.assertEqual(preview["Цель"], "Месячное обязательство")
        self.assertEqual(preview["Scope"], "Полностью определён")
        self.assertIn("кандидатного состава", preview["Первый этап"])
        self.assertEqual(preview["Закон"], "Месячное обязательство ещё не сформировано")
        self.assertEqual(
            preview["Статус"],
            "Ожидается подтверждение начала первого этапа",
        )
        self.assertFalse(result.mission_created)
        payload = validate_extraction(
            CommandExtraction(
                intent=INTENT_FORM_MONTHLY_COMMITMENT,
                target_agent_hint="constructor",
                project_hint="БХК",
                period_hint="ноябрь 2026",
                queue_hint="",
                title_hint="16160-13",
                discipline_hint="автоматизация",
            ).as_dict()
        )
        resolved = resolve_extraction(payload, _scope_catalog(), command_id="monthly")
        self.assertEqual(resolved.intent, INTENT_FORM_MONTHLY_COMMITMENT)
        self.assertNotEqual(resolved.intent, INTENT_FORM_CANDIDATE_PACKAGE)
        self.assertEqual(resolved.processing_state, "NEEDS_CONFIRMATION")

    def test_fully_resolved_monthly_commitment_is_confirmable_without_mission(self) -> None:
        from agents.human_surface.command_confirmation import confirm_typed_draft
        from agents.human_surface.command_interpretation import INTENT_FORM_MONTHLY_COMMITMENT

        draft = _interpret(
            "Сформируй месячное обязательство на ноябрь 2026 по БХК, "
            "титул 16160-13, автоматизация."
        )
        self.assertEqual(draft.intent, INTENT_FORM_MONTHLY_COMMITMENT)
        self.assertEqual(draft.processing_state, "NEEDS_CONFIRMATION")
        confirmed = confirm_typed_draft(
            draft,
            catalog=_scope_catalog(),
            source_text=(
                "Сформируй месячное обязательство на ноябрь 2026 по БХК, "
                "титул 16160-13, автоматизация."
            ),
        )
        self.assertEqual(confirmed.confirmation_state, "CONFIRMED")
        self.assertFalse(confirmed.as_dict()["mission_created"])
        self.assertFalse(confirmed.as_dict()["constructor_run_created"])
        self.assertFalse(draft.mission_created)

    def test_incomplete_monthly_commitment_still_needs_clarification(self) -> None:
        from agents.human_surface.command_interpretation import INTENT_FORM_MONTHLY_COMMITMENT

        result = _interpret(
            "Сформируй месячное обязательство на ноябрь 2026 по БХК, титул 16160-13."
        )
        self.assertEqual(result.intent, INTENT_FORM_MONTHLY_COMMITMENT)
        self.assertEqual(result.processing_state, "NEEDS_CLARIFICATION")
        self.assertIn("discipline", result.unresolved_fields)
        self.assertFalse(result.mission_created)

    def test_title_to_queue_unique_relationship_enriches_deterministically(self) -> None:
        from agents.human_surface.command_interpreter_provider import (
            CommandExtraction,
            resolve_extraction,
        )

        extraction = CommandExtraction(
            intent="FORM_CANDIDATE_PACKAGE",
            target_agent_hint="constructor",
            project_hint="БХК",
            period_hint="ноябрь 2026",
            queue_hint="",
            title_hint="16160-13",
            discipline_hint="автоматизация",
        )
        resolved = resolve_extraction(extraction, _scope_catalog(), command_id="enrich")
        self.assertEqual(resolved.processing_state, "NEEDS_CONFIRMATION")
        self.assertEqual(resolved.resolved_scope["queue"], "1")
        self.assertEqual(resolved.resolved_scope["queue_source"], "CANONICAL_TITLE_RELATION")
        self.assertEqual(extraction.queue_hint, "")

    def test_ambiguous_title_to_queue_needs_clarification(self) -> None:
        from agents.human_surface.command_interpretation import interpret_command

        catalog = _manual_scope_catalog(
            [
                {
                    "project_label": "БХК",
                    "project_code": "PRJ_001_БХК",
                    "queue": "1",
                    "facility": "16160-13",
                    "discipline": "Автоматизация",
                },
                {
                    "project_label": "БХК",
                    "project_code": "PRJ_001_БХК",
                    "queue": "2",
                    "facility": "16160-13",
                    "discipline": "Автоматизация",
                },
            ]
        )
        result = interpret_command(
            command_id="amb",
            raw_text=(
                "Сформируй кандидатный состав на ноябрь 2026 по БХК, "
                "титул 16160-13, автоматизация."
            ),
            catalog=catalog,
        )
        self.assertEqual(result.processing_state, "NEEDS_CLARIFICATION")
        self.assertNotIn("queue", result.resolved_scope)
        self.assertNotIn("queue_source", result.resolved_scope)
        self.assertIn("queue", result.unresolved_fields)

    def test_missing_title_to_queue_relationship_needs_clarification(self) -> None:
        from agents.human_surface.command_interpretation import interpret_command

        catalog = _manual_scope_catalog(
            [
                {
                    "project_label": "БХК",
                    "project_code": "PRJ_001_БХК",
                    "queue": "",
                    "facility": "16160-13",
                    "discipline": "Автоматизация",
                },
            ]
        )
        result = interpret_command(
            command_id="miss",
            raw_text=(
                "Сформируй кандидатный состав на ноябрь 2026 по БХК, "
                "титул 16160-13, автоматизация."
            ),
            catalog=catalog,
        )
        self.assertEqual(result.processing_state, "NEEDS_CLARIFICATION")
        self.assertNotIn("queue", result.resolved_scope)
        self.assertNotIn("queue_source", result.resolved_scope)
        self.assertIn("queue", result.unresolved_fields)

    def test_inferred_queue_provenance_is_canonical_title_relation(self) -> None:
        result = _interpret(
            "Сформируй кандидатный состав на ноябрь 2026 по БХК, "
            "титул 16160-13, автоматизация."
        )
        self.assertEqual(result.resolved_scope["queue_source"], "CANONICAL_TITLE_RELATION")
        spoken = _interpret(_ACCEPTED_COMMAND)
        self.assertEqual(spoken.resolved_scope["queue"], "1")
        self.assertNotIn("queue_source", spoken.resolved_scope)

    def test_llm_is_not_authority_for_inferred_queue(self) -> None:
        from agents.human_surface.command_interpreter_provider import CommandExtraction
        from agents.human_surface.command_understanding import understand_command

        class _QueueGuessProvider:
            def __init__(self) -> None:
                from agents.human_surface.command_interpreter_provider import (
                    InterpreterUsage,
                    ProviderExtractionResult,
                )

                self.calls: list[str] = []
                self._usage = InterpreterUsage("yandex", "test", 1, 1, 2, 1, True)
                self._type = ProviderExtractionResult

            def extract(self, raw_text: str):
                self.calls.append(raw_text)
                return self._type(
                    extraction=CommandExtraction(
                        intent="FORM_CANDIDATE_PACKAGE",
                        target_agent_hint="constructor",
                        project_hint="БХК",
                        period_hint="ноябрь 2026",
                        queue_hint="",
                        title_hint="16160-13",
                        discipline_hint="автоматизация",
                    ),
                    usage=self._usage,
                )

        provider = _QueueGuessProvider()
        understood = understand_command(
            command_id="llm-queue",
            raw_text="бхк нояб 16160 13 автоматик сформируй кандидатов",
            catalog=_scope_catalog(),
            provider=provider,
        )
        self.assertEqual(provider.calls, ["бхк нояб 16160 13 автоматик сформируй кандидатов"])
        self.assertEqual(understood.extraction.queue_hint if understood.extraction else None, "")
        self.assertEqual(understood.interpretation.resolved_scope["queue"], "1")
        self.assertEqual(
            understood.interpretation.resolved_scope["queue_source"],
            "CANONICAL_TITLE_RELATION",
        )

    def test_clarification_foundation_merges_fragment_and_blocks_confirmed(self) -> None:
        from agents.human_surface.command_clarification import (
            ClarificationRejected,
            apply_clarification_fragment,
            pending_from_interpretation,
        )
        from agents.human_surface.command_interpretation import interpret_command

        catalog = _manual_scope_catalog(
            [
                {
                    "project_label": "БХК",
                    "project_code": "PRJ_001_БХК",
                    "queue": "1",
                    "facility": "99999-01",
                    "discipline": "Автоматизация",
                },
                {
                    "project_label": "БХК",
                    "project_code": "PRJ_001_БХК",
                    "queue": "2",
                    "facility": "99999-01",
                    "discipline": "Автоматизация",
                },
            ]
        )
        source = (
            "Сформируй кандидатный состав на ноябрь 2026 по БХК, "
            "титул 99999-01, автоматизация."
        )
        draft = interpret_command(command_id="clr", raw_text=source, catalog=catalog)
        self.assertEqual(draft.processing_state, "NEEDS_CLARIFICATION")
        self.assertIn("queue", draft.unresolved_fields)
        pending = pending_from_interpretation(draft, source_text=source)
        self.assertIsNotNone(pending)
        assert pending is not None
        with self.assertRaises(ClarificationRejected):
            apply_clarification_fragment(
                pending,
                "первая очередь",
                catalog,
                confirmation_is_active=True,
            )
        merged = apply_clarification_fragment(
            pending,
            "первая очередь",
            catalog,
            confirmation_is_active=False,
        )
        self.assertEqual(merged.resolved_scope.get("queue"), "1")
        self.assertEqual(merged.processing_state, "NEEDS_CONFIRMATION")
        self.assertFalse(merged.mission_created)

    def test_scope_change_invalidates_prior_confirmation(self) -> None:
        catalog = _scope_catalog()
        self.client = Client()
        with patch(
            "dynamis.command_interpretation.load_work_context_catalog",
            return_value=catalog,
        ), patch(
            "dynamis.command_confirmation.load_work_context_catalog",
            return_value=catalog,
        ), patch(
            "dynamis.command_interpretation.resolve_command_provider",
            return_value=None,
        ):
            self.client.post(
                reverse("control_room"),
                {"raw_text": _ACCEPTED_COMMAND},
                follow=True,
            )
            self.client.post(reverse("control_room"), {"action": "confirm"}, follow=True)
            self.assertEqual(
                self.client.session["dynamis_command_confirmation"]["confirmation_state"],
                "CONFIRMED",
            )
            changed = self.client.post(
                reverse("control_room"),
                {
                    "raw_text": (
                        "Сформируй кандидатный состав на ноябрь 2026 по БХК, "
                        "титул 16160-17, автоматизация."
                    )
                },
                follow=True,
            )
        body = changed.content.decode("utf-8")
        self.assertNotIn("Поручение подтверждено", body)
        self.assertIn("16160-17", body)
        self.assertIn("Ожидается подтверждение", body)
        self.assertEqual(
            self.client.session["dynamis_command_interpretation"]["resolved_scope"]["facility"],
            "16160-17",
        )
        self.assertFalse(self.client.session["dynamis_command_interpretation"]["mission_created"])

    def test_discipline_fragment_continues_pending_draft_with_empty_intent(self) -> None:
        from agents.human_surface.command_interpreter_provider import (
            CommandExtraction,
            InterpreterUsage,
            ProviderExtractionResult,
        )

        class _FragmentProvider:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def extract(self, raw_text: str):
                self.calls.append(raw_text)
                if "дисциплин" in raw_text.casefold():
                    extraction = CommandExtraction(
                        intent="",
                        target_agent_hint="",
                        project_hint="",
                        period_hint="",
                        queue_hint="",
                        title_hint="",
                        discipline_hint="автоматизация",
                    )
                else:
                    extraction = CommandExtraction(
                        intent="FORM_CANDIDATE_PACKAGE",
                        target_agent_hint="constructor",
                        project_hint="БХК",
                        period_hint="ноябрь 2026",
                        queue_hint="",
                        title_hint="16160-13",
                        discipline_hint="",
                    )
                return ProviderExtractionResult(
                    extraction=extraction,
                    usage=InterpreterUsage("yandex", "test-model", 3, 2, 5, 9, True),
                )

        provider = _FragmentProvider()
        catalog = _scope_catalog()
        self.client = Client()
        first = (
            "сформируй кандидатный состав по БХК на ноябрь 2026 титул 16160-13"
        )
        with patch(
            "dynamis.command_interpretation.load_work_context_catalog",
            return_value=catalog,
        ), patch(
            "dynamis.command_interpretation.resolve_command_provider",
            return_value=provider,
        ):
            preview = self.client.post(
                reverse("control_room"),
                {"raw_text": first},
                follow=True,
            )
            stored = self.client.session["dynamis_command_interpretation"]
            self.assertEqual(stored["processing_state"], "NEEDS_CLARIFICATION")
            self.assertIn("discipline", stored["unresolved_fields"])
            self.assertIsNotNone(self.client.session.get("dynamis_pending_clarification"))
            continued = self.client.post(
                reverse("control_room"),
                {"raw_text": "дисциплина автоматизация"},
                follow=True,
            )
        body = continued.content.decode("utf-8")
        preview_body = preview.content.decode("utf-8")
        self.assertEqual(_quoted_human_command(preview_body), first)
        self.assertNotIn("Исходное поручение", preview_body)
        self.assertEqual(_quoted_human_command(body), "дисциплина автоматизация")
        self.assertIn(f'<p class="cr-kicker">Исходное поручение</p>\n                <p class="cr-muted">{first}</p>', body)
        for line in (
            "Пирометры перенеси в декабрь.",
            "Эта позиция выполнена, мастер ошибся.",
            "Остальные передавай в допуск.",
        ):
            self.assertIn(line, preview_body)
            self.assertIn(line, body)
        self.assertIn("Уточнение применено к текущему поручению", body)
        self.assertIn("NEEDS_CONFIRMATION", body)
        self.assertIn("Schema validation</dt><dd>YES</dd>", body)
        self.assertIn("Deterministic resolution</dt><dd>YES</dd>", body)
        self.assertIn("Автоматизация", body)
        self.assertIn("HUMAN_CLARIFICATION", body)
        self.assertIn("PRJ_001_БХК", body)
        self.assertIn("ноябрь-2026", body)
        self.assertIn("16160-13", body)
        final = self.client.session["dynamis_command_interpretation"]
        self.assertEqual(final["processing_state"], "NEEDS_CONFIRMATION")
        self.assertEqual(final["intent"], "FORM_CANDIDATE_PACKAGE")
        self.assertEqual(final["resolved_scope"]["project_code"], "PRJ_001_БХК")
        self.assertEqual(final["resolved_scope"]["month_key"], "ноябрь-2026")
        self.assertEqual(final["resolved_scope"]["queue"], "1")
        self.assertEqual(final["resolved_scope"]["facility"], "16160-13")
        self.assertEqual(final["resolved_scope"]["discipline"], "Автоматизация")
        self.assertEqual(final["resolved_scope"]["discipline_source"], "HUMAN_CLARIFICATION")
        self.assertFalse(final["mission_created"])
        self.assertNotIn("dynamis_command_confirmation", self.client.session)
        self.assertIsNone(self.client.session.get("dynamis_pending_clarification"))
        self.assertEqual(self.client.session["dynamis_human_command"]["raw_text"], first)
        self.assertIn("дисциплина автоматизация", provider.calls)
        self.assertNotIn("REJECTED", body)
        self.assertIn(first, preview.content.decode("utf-8"))

    def test_discipline_fragment_without_pending_draft_is_rejected(self) -> None:
        catalog = _scope_catalog()
        self.client = Client()
        with patch(
            "dynamis.command_interpretation.load_work_context_catalog",
            return_value=catalog,
        ), patch(
            "dynamis.command_interpretation.resolve_command_provider",
            return_value=None,
        ):
            response = self.client.post(
                reverse("control_room"),
                {"raw_text": "дисциплина автоматизация"},
                follow=True,
            )
        body = response.content.decode("utf-8")
        stored = self.client.session["dynamis_command_interpretation"]
        self.assertIn(stored["processing_state"], {"REJECTED", "NEEDS_CLARIFICATION"})
        self.assertNotEqual(stored["processing_state"], "NEEDS_CONFIRMATION")
        self.assertFalse(stored["mission_created"])
        self.assertNotIn("Уточнение применено к текущему поручению", body)
        self.assertNotEqual(stored.get("intent"), "FORM_CANDIDATE_PACKAGE")
        self.assertNotIn("PRJ_001_БХК", stored.get("resolved_scope") or {})

    def test_clarification_does_not_overwrite_resolved_title(self) -> None:
        from agents.human_surface.command_clarification import (
            continue_clarification,
            pending_from_interpretation,
        )
        from agents.human_surface.command_interpretation import interpret_command
        from agents.human_surface.command_interpreter_provider import CommandExtraction

        incomplete = "Сформируй кандидатный состав на ноябрь 2026 по БХК, титул 16160-13"
        draft = interpret_command(
            command_id="ow",
            raw_text=incomplete,
            catalog=_scope_catalog(),
        )
        self.assertEqual(draft.processing_state, "NEEDS_CLARIFICATION")
        self.assertEqual(draft.resolved_scope.get("facility"), "16160-13")
        pending = pending_from_interpretation(draft, source_text=incomplete)
        assert pending is not None
        result = continue_clarification(
            pending,
            "титул 16160-17",
            _scope_catalog(),
            fragment_extraction=CommandExtraction(
                intent="",
                target_agent_hint="",
                project_hint="",
                period_hint="",
                queue_hint="",
                title_hint="16160-17",
                discipline_hint="",
            ),
        )
        self.assertTrue(result.handled)
        self.assertTrue(result.conflict)
        self.assertFalse(result.applied)
        self.assertEqual(result.interpretation.resolved_scope.get("facility"), "16160-13")
        self.assertNotEqual(result.interpretation.resolved_scope.get("facility"), "16160-17")
        self.assertEqual(result.interpretation.processing_state, "NEEDS_CLARIFICATION")

    def test_confirmed_draft_blocks_clarification_merge(self) -> None:
        from agents.human_surface.command_clarification import ClarificationRejected, continue_clarification
        from agents.human_surface.command_confirmation import confirm_typed_draft
        from agents.human_surface.command_interpretation import interpret_command
        from agents.human_surface.command_clarification import pending_from_interpretation

        incomplete = "Сформируй кандидатный состав на ноябрь 2026 по БХК, титул 16160-13"
        draft = interpret_command(
            command_id="blocked",
            raw_text=incomplete,
            catalog=_scope_catalog(),
        )
        pending = pending_from_interpretation(draft, source_text=incomplete)
        assert pending is not None
        ready = _interpret(
            "Сформируй кандидатный состав на ноябрь 2026 по БХК, "
            "титул 16160-13, автоматизация."
        )
        confirm_typed_draft(
            ready,
            catalog=_scope_catalog(),
            source_text=(
                "Сформируй кандидатный состав на ноябрь 2026 по БХК, "
                "титул 16160-13, автоматизация."
            ),
        )
        with self.assertRaises(ClarificationRejected):
            continue_clarification(
                pending,
                "дисциплина автоматизация",
                _scope_catalog(),
                confirmation_is_active=True,
            )
