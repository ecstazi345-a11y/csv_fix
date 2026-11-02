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
