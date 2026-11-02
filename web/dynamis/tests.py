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
        for blob in (room_view, room, adapter, commands):
            lowered = blob.lower()
            self.assertNotIn("launch_monthly_plan_mission", blob)
            self.assertNotIn("submit_human_review", blob)
            self.assertNotIn("import supabase", lowered)
            self.assertNotIn("services.supabase", lowered)
            self.assertNotIn("create_run", blob)
            self.assertNotIn("append_event", blob)
            self.assertNotIn("executescript", lowered)
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
        self.assertIn("Constructor не запущен", body)
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
