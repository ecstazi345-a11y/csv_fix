"""
Increment 10.7 — Control Room page guards and behavior tests.

Static AST guards + deterministic Query Port read flow via Streamlit stub.
No browser automation.
"""

from __future__ import annotations

import ast
import importlib.util
import io
import re
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pandas as pd

from agents.control_room.dtos import (
    AgentEventView,
    ConstructorCandidateResultView,
    ConstructorDecisionRegistryView,
    ConstructorProfessionalResultView,
    ConstructorRowDecisionView,
    ProfessionalResultAvailability,
    AgentHandoffView,
    AgentHumanDecisionSurfaceView,
    AgentHumanWaitView,
    AgentProfessionalExecutionPathView,
    AgentRunDetail,
    AgentRunListView,
    AgentRunSnapshot,
    AgentRunSummary,
    AgentStageOccurrenceView,
    AgentStageView,
    DerivationState,
    DigitalOrganizationExecutionView,
    HandoffStatus,
    HumanDecisionConsequenceView,
    HumanDecisionRecordView,
    HumanDecisionRequestView,
    ProfessionalExecutionState,
    ProfessionalExecutionStepKind,
    ProfessionalExecutionStepView,
    empty_constructor_decision_registry,
    unavailable_constructor_professional_result,
    RealityRefreshStepView,
    StageDisplayState,
    WaitClosedBy,
)
from agents.control_room.presentation import (
    AUTHORITY_NOT_MODELED_RU,
    EVENTS_COMPLETE_FALSE_RU,
    EXECUTION_PATH_INCOMPLETE_RU,
    HUMAN_DECISION_HEADER_RU,
    RUNS_COMPLETE_FALSE_RU,
    WAITING_FOR_HUMAN_RU,
    operational_status_ru,
    professional_stage_id_ru,
)
from agents.human_surface.mission_draft import parse_mission_text
from agents.observability.contracts import OperationalStatus

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = REPO_ROOT / "pages" / "53_AI_Центр_управления_агентами.py"
APP_PY = REPO_ROOT / "app.py"

FIXED_AT = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)

_FORBIDDEN_IMPORTS = (
    "sqlite3",
    "langgraph",
    "agents.observability.sqlite_store",
    "agents.observability.store",
    "agents.monthly_plan_constructor",
    "agents.control_room.constructor_professional_result_reader",
    "supabase",
)

_PROHIBITED_WRITE_LABELS = (
    "Продолжить",
    "Согласовать",
    "Отклонить",
    "Остановить",
    "Перезапустить",
    "Удалить",
)

_FORBIDDEN_API_SNIPPETS = (
    "run_control",
    "append_event",
    "create_run",
    "SqliteObservabilityStore",
    "SqliteSaver",
    "checkpoints.sqlite",
    "ObservabilityStore",
    "ObservabilityEvent",
)

_RAW_DUMP_SNIPPETS = (
    "__dict__",
    "asdict(",
    "event.detail",
    "safe_summary",
    "safe_counts",
)


class _SessionState(dict):
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


def _cache_resource_stub(*args: Any, **kwargs: Any) -> Any:
    def decorator(fn: Any) -> Any:
        fn.clear = lambda: None  # type: ignore[attr-defined]
        return fn

    if args and callable(args[0]) and not kwargs:
        return decorator(args[0])
    return decorator


class _StreamlitStub(ModuleType):
    def __init__(self) -> None:
        super().__init__("streamlit")
        self.session_state = _SessionState()
        self.markdown_calls: list[str] = []
        self.warning_calls: list[str] = []
        self.info_calls: list[str] = []
        self.error_calls: list[str] = []
        self.write_calls: list[Any] = []
        self.dataframe_calls: list[Any] = []
        self.radio_calls: list[dict[str, Any]] = []
        self.set_page_config = lambda **kwargs: None
        self.cache_resource = _cache_resource_stub
        self.cache_data = _cache_resource_stub
        self.title = lambda *a, **k: None
        self.caption = lambda *a, **k: None
        self.subheader = lambda *a, **k: None
        self.code = lambda *a, **k: None
        self.button_calls: list[dict[str, Any]] = []
        self.rerun = lambda: None
        self.columns = self._columns
        self.expander_depth = 0
        self.expander_labels: list[str] = []
        self.primary_markdown: list[str] = []
        self.technical_markdown: list[str] = []
        self.primary_writes: list[Any] = []
        self.technical_writes: list[Any] = []
        self.container = MagicMock()
        self.container.return_value.__enter__ = lambda s: s
        self.container.return_value.__exit__ = lambda s, *a: None

    def expander(self, label: str = "", *args: Any, **kwargs: Any):
        stub = self

        class _Expander:
            def __enter__(self_inner):
                stub.expander_depth += 1
                stub.expander_labels.append(str(label))
                return stub

            def __exit__(self_inner, exc_type, exc, tb) -> bool:
                stub.expander_depth -= 1
                return False

        return _Expander()

    def markdown(self, text: str, *args: Any, **kwargs: Any) -> None:
        rendered = str(text)
        self.markdown_calls.append(rendered)
        if self.expander_depth:
            self.technical_markdown.append(rendered)
        else:
            self.primary_markdown.append(rendered)

    def warning(self, text: str, *args: Any, **kwargs: Any) -> None:
        self.warning_calls.append(str(text))

    def info(self, text: str, *args: Any, **kwargs: Any) -> None:
        self.info_calls.append(str(text))

    def error(self, text: str, *args: Any, **kwargs: Any) -> None:
        self.error_calls.append(str(text))

    def write(self, *args: Any, **kwargs: Any) -> None:
        self.write_calls.append(args)
        if self.expander_depth:
            self.technical_writes.append(args)
        else:
            self.primary_writes.append(args)

    def dataframe(self, data: Any, *args: Any, **kwargs: Any) -> None:
        self.dataframe_calls.append(data)

    def radio(self, label: str, *, options: list[str], index: int = 0, **kwargs: Any) -> str:
        self.radio_calls.append({"label": label, "options": options, "index": index})
        return options[index]

    def selectbox(self, label: str, options: list[str], **kwargs: Any) -> str:
        if not options:
            return ""
        index = int(kwargs.get("index") or 0)
        return options[index]

    def multiselect(self, label: str, options: list[str] | None = None, **kwargs: Any) -> list[str]:
        return []

    def text_input(self, label: str, *args: Any, **kwargs: Any) -> str:
        return ""

    def text_area(self, label: str, *args: Any, **kwargs: Any) -> str:
        return ""

    def button(self, label: str, *args: Any, **kwargs: Any) -> bool:
        self.button_calls.append({"label": str(label), "disabled": bool(kwargs.get("disabled", False))})
        return False

    def download_button(self, label: str, *args: Any, **kwargs: Any) -> bool:
        self.button_calls.append({"label": str(label), "disabled": bool(kwargs.get("disabled", False))})
        return False

    def _columns(self, spec: Any, **kwargs: Any) -> list[Any]:
        count = spec if isinstance(spec, int) else len(spec)
        mocks = [MagicMock() for _ in range(count)]
        for mock in mocks:
            mock.__enter__ = lambda s: s
            mock.__exit__ = lambda s, *a: None
            mock.markdown = self.markdown
            mock.write = self.write
            mock.warning = self.warning
            mock.info = self.info
            mock.caption = self.caption
            mock.dataframe = self.dataframe
            mock.selectbox = self.selectbox
            mock.multiselect = self.multiselect
            mock.button = self.button
            mock.radio = self.radio
            mock.text_input = self.text_input
        return mocks


def _summary(**overrides: Any) -> AgentRunSummary:
    payload = {
        "run_id": "run-page-001",
        "agent_code": "MONTHLY_PLAN_CONSTRUCTOR",
        "project_code": "PRJ_001",
        "month_key": "2026-09",
        "mission_id": "mission-001",
        "operational_status": OperationalStatus.RUNNING.value,
        "requested_at": FIXED_AT,
        "updated_at": FIXED_AT,
        "started_at": FIXED_AT,
        "completed_at": None,
        "projection_version": 1,
    }
    payload.update(overrides)
    return AgentRunSummary(**payload)


def _detail(**overrides: Any) -> AgentRunDetail:
    payload = {
        "run_id": "run-page-001",
        "agent_code": "MONTHLY_PLAN_CONSTRUCTOR",
        "project_code": "PRJ_001",
        "month_key": "2026-09",
        "mission_id": "mission-001",
        "operational_status": OperationalStatus.RUNNING.value,
        "requested_at": FIXED_AT,
        "updated_at": FIXED_AT,
        "started_at": FIXED_AT,
        "completed_at": None,
        "projection_version": 1,
        "request_id": "req-001",
        "agent_version": "0.1",
        "orchestration_run_id": None,
        "initiator_type": "HUMAN",
        "initiator_id": "operator",
        "trigger_type": "MANUAL",
        "trigger_reason": "manual",
        "attempt_n": 1,
        "resume_n": 0,
        "lifecycle_status": None,
        "interrupt_id": None,
        "decision_id": None,
        "handoff_id": None,
        "error_code": None,
        "safe_error_summary": None,
        "safe_summary": (("phase", "running"),),
        "safe_counts": (("candidates", 1),),
    }
    payload.update(overrides)
    return AgentRunDetail(**payload)


def _snapshot(**overrides: Any) -> AgentRunSnapshot:
    stage = AgentStageView(
        current_stage=AgentStageOccurrenceView(
            stage_id="stage-1",
            node_name="node-1",
            attempt_n=1,
            resume_n=0,
            artifact_id="",
            display_state=StageDisplayState.RUNNING,
            started_at=FIXED_AT,
            completed_at=None,
            started_event_id="evt-1",
            terminal_event_id=None,
        ),
        occurrences=(
            AgentStageOccurrenceView(
                stage_id="stage-1",
                node_name="node-1",
                attempt_n=1,
                resume_n=0,
                artifact_id="",
                display_state=StageDisplayState.RUNNING,
                started_at=FIXED_AT,
                completed_at=None,
                started_event_id="evt-1",
                terminal_event_id=None,
            ),
        ),
        derivation_state=DerivationState.OK,
    )
    payload = {
        "run": _detail(),
        "stage": stage,
        "human_wait": AgentHumanWaitView(
            waiting_for_human=False,
            interrupt_id=None,
            wait_started_at=None,
            decision_id=None,
            wait_closed_by=None,
            wait_ordinal=None,
            derivation_state=DerivationState.OK,
        ),
        "human_decision_surface": AgentHumanDecisionSurfaceView(
            wait=AgentHumanWaitView(
                waiting_for_human=False,
                interrupt_id=None,
                wait_started_at=None,
                decision_id=None,
                wait_closed_by=None,
                wait_ordinal=None,
                derivation_state=DerivationState.OK,
            ),
            request=None,
            decision=None,
            consequence=None,
            authority_modeled=False,
        ),
        "handoff": AgentHandoffView(
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
        ),
        "professional_execution_path": AgentProfessionalExecutionPathView(
            steps=(
                ProfessionalExecutionStepView(
                    step_kind=ProfessionalExecutionStepKind.STAGE,
                    step_id="evt-1",
                    stage_id="stage-1",
                    professional_state=ProfessionalExecutionState.RUNNING,
                    started_at=FIXED_AT,
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
        "digital_organization": DigitalOrganizationExecutionView(
            source_agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            source_run_id="run-page-001",
            source_operational_status=OperationalStatus.RUNNING.value,
            source_completed_at=None,
            handoff=None,
            history_complete=True,
            derivation_state=DerivationState.OK,
        ),
        "timeline_events": (
            AgentEventView(
                event_id="evt-1",
                event_type="RUN_STARTED",
                family="RUN",
                status="OK",
                title="Run started",
                occurred_at=FIXED_AT,
                stage_id=None,
                node_name=None,
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
        "events_complete": True,
        "read_at": FIXED_AT,
    }
    payload.update(overrides)
    return AgentRunSnapshot(**payload)


class _FakeQueryPort:
    def __init__(
        self,
        *,
        catalog: Optional[AgentRunListView] = None,
        filtered: Optional[AgentRunListView] = None,
        snapshot: Optional[AgentRunSnapshot] = None,
    ) -> None:
        self.catalog = catalog or AgentRunListView(items=(_summary(),), runs_complete=True, source_count=1)
        self.filtered = filtered or self.catalog
        self.snapshot = snapshot or _snapshot()
        self.list_calls: list[dict[str, Any]] = []
        self.snapshot_calls: list[str] = []

    def list_runs(self, **kwargs: Any) -> AgentRunListView:
        self.list_calls.append(dict(kwargs))
        if kwargs.get("limit") == 200:
            return self.catalog
        return self.filtered

    def get_run_snapshot(self, run_id: str, **kwargs: Any) -> AgentRunSnapshot:
        self.snapshot_calls.append(run_id)
        return self.snapshot


def _recovered(run_id: str, mission_id: str):
    from datetime import datetime, timezone

    from agents.human_surface.mission_recovery import RecoveredMission

    return RecoveredMission(
        run_id=run_id,
        mission_id=mission_id,
        project_label="БХК",
        planning_month="октябрь 2026",
        queue="1",
        titles=("16160-13", "16160-17"),
        discipline=None,
        systems=(),
        packages=None,
        intent="Сформировать кандидатный состав месячного плана",
        operational_status="RUNNING",
        lifecycle_status="REALITY_LOADED",
        requested_at=datetime(2026, 10, 12, 14, 24, tzinfo=timezone.utc),
    )


def _recovery_catalog():
    from agents.human_surface.work_context import WorkContextCatalog

    return WorkContextCatalog(source="test", error="", months=(), facts=())


def _load_page_module() -> tuple[ModuleType, _StreamlitStub]:
    module_name = "page53_control_room_test"
    for key in list(sys.modules):
        if key == module_name or key == "streamlit":
            del sys.modules[key]
    st = _StreamlitStub()
    sys.modules["streamlit"] = st
    spec = importlib.util.spec_from_file_location(module_name, PAGE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    st.session_state.clear()
    for name in (
        "info_calls",
        "warning_calls",
        "error_calls",
        "write_calls",
        "button_calls",
        "markdown_calls",
        "primary_markdown",
        "technical_markdown",
        "primary_writes",
        "technical_writes",
        "dataframe_calls",
        "radio_calls",
        "expander_labels",
    ):
        getattr(st, name).clear()
    return module, st


class ControlRoomPageGuardTests(unittest.TestCase):
    def test_page_exists(self) -> None:
        self.assertTrue(PAGE_PATH.is_file())

    def test_app_navigation_points_to_page(self) -> None:
        text = APP_PY.read_text(encoding="utf-8")
        block_match = re.search(
            r'"▌ Контур агентной оркестрации"\s*:\s*\[(.*?)\]',
            text,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(block_match)
        block = block_match.group(1)
        pages = re.findall(r'"([^"]+\.py)"', block)
        self.assertIn("52_Архитектура_агентной_оркестрации_месячного_плана.py", pages)
        self.assertIn("53_AI_Центр_управления_агентами.py", pages)
        self.assertEqual(pages.index("53_AI_Центр_управления_агентами.py"), pages.index("52_Архитектура_агентной_оркестрации_месячного_плана.py") + 1)
        self.assertIn('"53_AI_Центр_управления_агентами.py": "Центр управления агентами"', text)

    def test_page_forbidden_imports_absent(self) -> None:
        source = PAGE_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in _FORBIDDEN_IMPORTS:
                        if alias.name == forbidden or alias.name.startswith(f"{forbidden}."):
                            self.fail(f"forbidden import: {alias.name}")
            if isinstance(node, ast.ImportFrom) and node.module:
                for forbidden in _FORBIDDEN_IMPORTS:
                    if node.module == forbidden or node.module.startswith(f"{forbidden}."):
                        self.fail(f"forbidden import from: {node.module}")

    def test_page_no_prohibited_write_labels(self) -> None:
        source = PAGE_PATH.read_text(encoding="utf-8")
        for label in _PROHIBITED_WRITE_LABELS:
            self.assertNotIn(label, source, f"prohibited write label found: {label}")
        self.assertNotIn("MISSION_COMMAND_PORT_REQUIRED_RU", source)
        self.assertNotIn(
            "Формирование новой миссии из свободного поручения ещё требует Mission Command Port.",
            source,
        )
        self.assertIn("HITL_COMMAND_PORT_REQUIRED_RU", source)
        self.assertIn("HANDOFF_COMMAND_PORT_REQUIRED_RU", source)
        messages = (REPO_ROOT / "agents" / "human_surface" / "mission_draft.py").read_text(encoding="utf-8")
        self.assertIn("Mission Command Port", messages)
        self.assertIn("HITL Command Port", messages)
        self.assertIn("Handoff Command Port", messages)
        self.assertNotIn("sqlite3", source)
        self.assertNotIn(".commit(", source)

    def test_page_no_forbidden_api_snippets(self) -> None:
        source = PAGE_PATH.read_text(encoding="utf-8")
        for snippet in _FORBIDDEN_API_SNIPPETS:
            self.assertNotIn(snippet, source, f"forbidden snippet: {snippet}")

    def test_page_no_raw_dump_snippets(self) -> None:
        source = PAGE_PATH.read_text(encoding="utf-8")
        for snippet in _RAW_DUMP_SNIPPETS:
            self.assertNotIn(snippet, source, f"raw dump snippet: {snippet}")

    def test_unsafe_html_has_no_operational_interpolation(self) -> None:
        source = PAGE_PATH.read_text(encoding="utf-8")
        for match in re.finditer(r"unsafe_allow_html\s*=\s*True", source):
            start = max(0, match.start() - 200)
            window = source[start : match.start() + 120]
            self.assertNotIn("{", window)
            self.assertNotIn("f\"", window)
            self.assertNotIn("f'", window)


class ControlRoomPageBehaviorTests(unittest.TestCase):
    def test_run_list_uses_full_run_id_selection(self) -> None:
        page, st = _load_page_module()
        list_view = AgentRunListView(items=(_summary(run_id="run-full-id-123"),), runs_complete=True, source_count=1)
        st.session_state["control_room_selected_run_id"] = "run-full-id-123"
        selected = page._render_run_list(list_view)
        self.assertEqual(selected, "run-full-id-123")
        self.assertEqual(st.session_state["control_room_selected_run_id"], "run-full-id-123")

    def test_runs_complete_false_warning(self) -> None:
        page, st = _load_page_module()
        list_view = AgentRunListView(items=(), runs_complete=False, source_count=0)
        page._render_run_list(list_view)
        self.assertTrue(any(RUNS_COMPLETE_FALSE_RU in text for text in st.info_calls))

    def test_selected_snapshot_renders_ru_status_stage_timeline(self) -> None:
        page, st = _load_page_module()
        snap = _snapshot()
        page._render_selected_run(snap)
        status_ru = operational_status_ru(snap.run.operational_status)
        flat_writes = " ".join(str(arg) for args in st.write_calls for arg in args)
        self.assertIn(status_ru, flat_writes)
        self.assertTrue(st.dataframe_calls)
        timeline_df = st.dataframe_calls[-1]
        self.assertIsInstance(timeline_df, pd.DataFrame)
        self.assertIn("Событие", timeline_df.columns)

    def test_events_complete_false_warning(self) -> None:
        page, st = _load_page_module()
        snap = _snapshot(events_complete=False)
        page._render_selected_run(snap)
        self.assertTrue(any(EVENTS_COMPLETE_FALSE_RU in text for text in st.info_calls))

    def test_inconsistent_stage_warning(self) -> None:
        page, st = _load_page_module()
        stage = AgentStageView(current_stage=None, occurrences=(), derivation_state=DerivationState.INCONSISTENT)
        snap = _snapshot(stage=stage)
        page._render_selected_run(snap)
        self.assertTrue(st.warning_calls)

    def test_waiting_for_human_headline_only(self) -> None:
        page, st = _load_page_module()
        snap = _snapshot(
            run=_detail(operational_status=OperationalStatus.WAITING_FOR_HUMAN.value),
            human_wait=AgentHumanWaitView(
                waiting_for_human=True,
                interrupt_id="intr-1",
                wait_started_at=FIXED_AT,
                decision_id=None,
                wait_closed_by=None,
                wait_ordinal=1,
                derivation_state=DerivationState.OK,
            ),
        )
        page._render_selected_run(snap)
        self.assertIn(WAITING_FOR_HUMAN_RU, st.warning_calls)
        source = PAGE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("Согласовать", source)
        self.assertNotIn("Отклонить", source)

    def test_main_reads_current_constructor_run(self) -> None:
        page, st = _load_page_module()
        fake = _FakeQueryPort()
        with patch.object(page, "_cached_query_port", return_value=fake):
            with redirect_stdout(io.StringIO()):
                page.main()
        self.assertEqual(fake.snapshot_calls, [])
        self.assertNotIn("run-76ae10af-69f7-4588-91f5-5b0f5d28052a", "\n".join(st.primary_markdown))
        st.session_state["dynamis_active_run_id"] = "run-new-1"
        with patch.object(page, "_cached_query_port", return_value=fake):
            with redirect_stdout(io.StringIO()):
                page.main()
        self.assertEqual(fake.snapshot_calls, ["run-new-1"])
        text = "\n".join(st.primary_markdown)
        self.assertIn("Рабочее место цифровых сотрудников", text)
        self.assertIn("Быстрая команда", text)
        self.assertIn("Рабочий контекст", text)
        self.assertIn("Кому поручить", text)
        self.assertIn("Профессиональный контур", text)
        self.assertIn("Поручение", text)
        self.assertIn("ТЕКСТОМ", "\n".join(st.button_calls and [item["label"] for item in st.button_calls]))
        self.assertNotIn('options=["Текстом", "Голосом"]', PAGE_PATH.read_text(encoding="utf-8"))

    def test_launch_button_calls_port_once_and_rerun_keeps_the_run(self) -> None:
        from agents.human_surface.mission_command import MissionLaunchResult
        from agents.human_surface.mission_draft import WorkingContext
        from agents.human_surface.work_context import ScopeFact, WorkContextCatalog

        page, st = _load_page_module()
        catalog = WorkContextCatalog(
            source="test",
            error="",
            months=("октябрь 2026",),
            facts=(
                ScopeFact(
                    project_label="БХК",
                    project_code="PRJ_001_БХК",
                    queue="1",
                    facility="16160-13",
                    title="16160-13",
                    discipline="Автоматизация",
                    systems=("АСУТП",),
                    packages=(),
                ),
            ),
        )
        st.session_state["dynamis_working_context"] = WorkingContext(
            project="БХК",
            planning_month="октябрь 2026",
            queue="1",
            titles=("16160-13",),
            discipline="Автоматизация",
            systems=("АСУТП",),
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            intent="Сформировать кандидатный состав месячного плана.",
            contour_code="MONTHLY_PRODUCTION_COMMITMENT",
        )
        calls: list[str] = []

        def fake_launch(context: WorkingContext, received: WorkContextCatalog) -> MissionLaunchResult:
            calls.append("launch")
            self.assertEqual(context.titles, ("16160-13",))
            self.assertEqual(received.source, "test")
            return MissionLaunchResult(
                run_id="run-new-1",
                mission_id="mission-new-1",
                status="STARTING",
                started_at="2026-10-12T12:00:00+00:00",
            )

        def button(label: str, *args: Any, **kwargs: Any) -> bool:
            st.button_calls.append({"label": str(label), "disabled": bool(kwargs.get("disabled", False))})
            return str(label) == "ЗАПУСТИТЬ" and not kwargs.get("disabled", False)

        st.button = button
        with patch.object(page, "launch_monthly_plan_mission", side_effect=fake_launch):
            page._render_mission_draft(catalog)
            page._render_mission_draft(catalog)
        self.assertEqual(calls, ["launch"])
        self.assertEqual(st.session_state["dynamis_active_run_id"], "run-new-1")
        self.assertEqual(st.session_state["dynamis_active_mission_id"], "mission-new-1")
        self.assertEqual(st.session_state["dynamis_launched_mission_identity"], st.session_state["dynamis_launch_key"])
        self.assertIn("Задача запущена", st.info_calls)
        page._render_technical_evidence(None, None)
        technical = "\n".join(str(item) for item in st.technical_writes)
        self.assertIn("Run ID: run-new-1", technical)
        self.assertIn("Mission ID: mission-new-1", technical)
        rendered = "\n".join(str(item) for item in st.primary_writes)
        self.assertIn("16160-13", rendered)
        self.assertIn("Статус: Запуск", rendered)
        self.assertNotIn("STARTING", rendered)
        self.assertNotIn("run-76ae10af-69f7-4588-91f5-5b0f5d28052a", rendered)

    def test_unchanged_launch_does_not_warn_and_running_is_not_an_error(self) -> None:
        from agents.human_surface.mission_command import mission_idempotency_key
        from agents.human_surface.mission_draft import WorkingContext

        page, st = _load_page_module()
        context = WorkingContext(
            project="БХК",
            planning_month="октябрь 2026",
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            intent="Сформировать единый кандидатный состав.",
            contour_code="MONTHLY_PRODUCTION_COMMITMENT",
        )
        identity = mission_idempotency_key(context)
        st.session_state["dynamis_working_context"] = context
        st.session_state["dynamis_launched_mission_identity"] = identity
        st.session_state["dynamis_active_run_id"] = "run-new-1"
        page._render_constructor_workspace(_snapshot(), None)
        text = "\n".join(st.info_calls + st.warning_calls)
        self.assertIn("выполняет задачу", text)
        self.assertIn("ОБНОВИТЬ СТАТУС", [item["label"] for item in st.button_calls])
        self.assertNotIn("разные состояния", text)
        self.assertNotIn("недоступен", text)

    def test_missing_run_id_does_not_claim_launch_or_read_a_result(self) -> None:
        from agents.human_surface.mission_command import MissionLaunchResult
        from agents.human_surface.mission_draft import WorkingContext
        from agents.human_surface.work_context import ScopeFact, WorkContextCatalog

        page, st = _load_page_module()
        catalog = WorkContextCatalog(
            source="test",
            error="",
            months=("октябрь 2026",),
            facts=(
                ScopeFact(
                    project_label="БХК",
                    project_code="PRJ_001_БХК",
                    queue="1",
                    facility="16160-13",
                    title="16160-13",
                    discipline="Автоматизация",
                    systems=(),
                    packages=(),
                ),
            ),
        )
        st.session_state["dynamis_working_context"] = WorkingContext(
            project="БХК",
            planning_month="октябрь 2026",
            queue="1",
            titles=("16160-13",),
            discipline="Автоматизация",
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            intent="Сформировать кандидатный состав месячного плана.",
            contour_code="MONTHLY_PRODUCTION_COMMITMENT",
        )

        def empty_launch(context: WorkingContext, received: WorkContextCatalog) -> MissionLaunchResult:
            return MissionLaunchResult(
                run_id="",
                mission_id="mission-missing",
                status="STARTING",
                started_at="2026-10-12T12:00:00+00:00",
            )

        def button(label: str, *args: Any, **kwargs: Any) -> bool:
            return str(label) == "ЗАПУСТИТЬ" and not kwargs.get("disabled", False)

        st.button = button
        with patch.object(page, "launch_monthly_plan_mission", side_effect=empty_launch):
            page._render_mission_draft(catalog)
        self.assertNotIn("dynamis_active_run_id", st.session_state)
        self.assertNotIn("Задача запущена", st.info_calls)
        self.assertIn("Не удалось подтвердить запуск задачи.", st.error_calls)
        self.assertNotIn("выполняет задачу", "\n".join(st.info_calls))
        st.button = lambda *args, **kwargs: False
        fake = _FakeQueryPort()
        with patch.object(page, "_cached_query_port", return_value=fake):
            with redirect_stdout(io.StringIO()):
                page.main()
        self.assertEqual(fake.snapshot_calls, [])
        page._render_constructor_workspace(
            _snapshot(run=_detail(operational_status=OperationalStatus.STARTING.value)),
            None,
        )
        self.assertNotIn("выполняет задачу", "\n".join(st.info_calls))
        technical = "\n".join(str(item) for item in st.technical_writes)
        self.assertIn("Запуск не вернул run_id.", technical)
        self.assertNotIn("Задача запущена", "\n".join(st.info_calls))

    def test_unavailable_result_still_shows_the_stored_run(self) -> None:
        page, st = _load_page_module()
        st.session_state["dynamis_active_run_id"] = "run-live-1"
        st.session_state["dynamis_active_mission_id"] = "mission-live-1"
        registry = empty_constructor_decision_registry(unavailable_constructor_professional_result())
        snap = _snapshot(run=_detail(run_id="run-live-1", operational_status=OperationalStatus.STARTING.value))
        page._render_constructor_workspace(snap, registry)
        self.assertIn("выполняет задачу", "\n".join(st.info_calls))
        technical = "\n".join(str(item) for item in st.technical_writes)
        self.assertIn("Run ID: run-live-1", technical)
        self.assertIn("Mission ID: mission-live-1", technical)
        self.assertIn("Операционный статус: STARTING", technical)
        self.assertNotIn("Run ID: —", technical)

    def test_reader_uses_the_stored_run_and_not_an_older_one(self) -> None:
        page, st = _load_page_module()
        fake = _FakeQueryPort()
        recorded: list[str] = []

        def registry(run_id: str, **kwargs: Any):
            recorded.append(run_id)
            return empty_constructor_decision_registry(unavailable_constructor_professional_result())

        fake.get_constructor_decision_registry = registry
        st.session_state["dynamis_active_run_id"] = "run-live-1"
        with patch.object(page, "_cached_query_port", return_value=fake):
            with redirect_stdout(io.StringIO()):
                page.main()
        self.assertEqual(fake.snapshot_calls, ["run-live-1"])
        self.assertEqual(recorded, ["run-live-1"])
        self.assertNotIn("run-76ae10af-69f7-4588-91f5-5b0f5d28052a", fake.snapshot_calls)
        self.assertNotIn("run-830bc0c5-5a10-4ab6-9a19-da822662e041", fake.snapshot_calls)

    def test_session_run_identity_is_not_reset_on_render(self) -> None:
        source = PAGE_PATH.read_text(encoding="utf-8")
        self.assertNotRegex(source, r'\["dynamis_active_run_id"\]\s*=\s*None')
        self.assertNotRegex(source, r'\["dynamis_active_mission_id"\]\s*=\s*None')
        self.assertNotRegex(source, r'\["dynamis_launched_mission_identity"\]\s*=\s*None')
        self.assertNotIn("Продолжить", source)
        self.assertNotIn("composition.start", source)

    def test_existing_session_run_is_not_replaced_by_recovery(self) -> None:
        from agents.human_surface.mission_recovery import RecoveredMission, RecoveryDecision

        page, st = _load_page_module()
        st.session_state["dynamis_active_run_id"] = "run-session"
        st.session_state["dynamis_active_mission_id"] = "mission-session"
        decision = RecoveryDecision(
            selected=_recovered("run-other", "mission-other"),
            choices=(),
            ambiguous=False,
        )
        with patch.object(page, "load_recovery_decision", return_value=decision):
            page._restore_durable_mission_if_needed(_FakeQueryPort())
        self.assertEqual(st.session_state["dynamis_active_run_id"], "run-session")
        self.assertEqual(st.session_state["dynamis_active_mission_id"], "mission-session")

    def test_missing_session_recovers_one_run_without_launch(self) -> None:
        from agents.human_surface.mission_recovery import RecoveryDecision

        page, st = _load_page_module()
        mission = _recovered("run-830bc0c5", "mission-hs-recovered")
        decision = RecoveryDecision(selected=mission, choices=(), ambiguous=False)
        fake = _FakeQueryPort()
        recorded: list[str] = []

        def registry(run_id: str, **kwargs: Any):
            recorded.append(run_id)
            return empty_constructor_decision_registry(unavailable_constructor_professional_result())

        fake.get_constructor_decision_registry = registry
        launches: list[str] = []
        with patch.object(page, "load_recovery_decision", return_value=decision):
            with patch.object(page, "launch_monthly_plan_mission", side_effect=launches.append):
                with patch.object(page, "_cached_query_port", return_value=fake):
                    with patch.object(page, "load_work_context_catalog", return_value=_recovery_catalog()):
                        with redirect_stdout(io.StringIO()):
                            page.main()
        self.assertEqual(launches, [])
        self.assertEqual(st.session_state["dynamis_active_run_id"], "run-830bc0c5")
        self.assertEqual(st.session_state["dynamis_active_mission_id"], "mission-hs-recovered")
        self.assertEqual(st.session_state["dynamis_working_context"].project, "БХК")
        self.assertEqual(st.session_state["dynamis_working_context"].planning_month, "октябрь 2026")
        self.assertEqual(fake.snapshot_calls, ["run-830bc0c5"])
        self.assertEqual(recorded, ["run-830bc0c5"])
        self.assertNotIn("run-76ae10af-69f7-4588-91f5-5b0f5d28052a", fake.snapshot_calls)
        self.assertIn(page.CONTINUES_EXECUTION_RU, st.info_calls)

    def test_ambiguous_recovery_does_not_choose_a_run(self) -> None:
        from agents.human_surface.mission_recovery import RecoveryDecision

        page, st = _load_page_module()
        decision = RecoveryDecision(
            selected=None,
            choices=(_recovered("run-a", "mission-a"), _recovered("run-b", "mission-b")),
            ambiguous=True,
        )
        with patch.object(page, "load_recovery_decision", return_value=decision):
            page._restore_durable_mission_if_needed(_FakeQueryPort())
        self.assertNotIn("dynamis_active_run_id", st.session_state)
        self.assertEqual(
            [item.run_id for item in st.session_state["dynamis_recovery_choices"]],
            ["run-a", "run-b"],
        )

    def test_constructor_employee_renders_stored_scale_without_false_claims(self) -> None:
        page, st = _load_page_module()
        result = ConstructorProfessionalResultView(
            availability=ProfessionalResultAvailability.AVAILABLE,
            run_id="run-page-001",
            mission_id="mission-001",
            professional_status="PROFESSIONAL_WORK_COMPLETED",
            project_id="PRJ_001_БХК",
            month="октябрь-2026",
            facility_id="16160-13",
            discipline="ВЕНТИЛЯЦИЯ",
            source_candidate_package_id="pkg-1",
            reviewed_package_id="rev-1",
            included_count=0,
            excluded_count=2,
            unresolved_count=0,
            confirm_event_id="cfm-1",
            confirm_decision="CONFIRM",
            confirm_actor_type="HUMAN",
            confirm_actor_id="human-owner-live-proof",
            path_statuses=("PROFESSIONAL_WORK_COMPLETED",),
            candidates=(
                ConstructorCandidateResultView(
                    candidate_id="c-1",
                    boq_code="2041-01-22-02",
                    name="Воздуховод",
                    unit="м2 / m2",
                    remaining_qty="9.079999999999998",
                    already_planned_qty="9.07",
                    available_qty="0.00999999999999801",
                    labor_status="UNRESOLVED",
                    recommendation="HUMAN_REVIEW_REQUIRED",
                    exception_codes=("LABOR_NORM_UNRESOLVED",),
                    human_review_decision="REMOVE",
                    final_disposition="EXCLUDED",
                    final_reason_code="HUMAN_REMOVE",
                ),
                ConstructorCandidateResultView(
                    candidate_id="c-2",
                    boq_code="2041-01-27-02",
                    name="Кладка",
                    unit="м3 / m3",
                    remaining_qty="1.150000000000002",
                    already_planned_qty="1.15",
                    available_qty="2.220446049250313e-15",
                    labor_status="UNRESOLVED",
                    recommendation="HUMAN_REVIEW_REQUIRED",
                    exception_codes=("LABOR_NORM_UNRESOLVED",),
                    human_review_decision="REMOVE",
                    final_disposition="EXCLUDED",
                    final_reason_code="HUMAN_REMOVE",
                ),
            ),
            mission_scope_row_count=80,
            mission_scope_source="monthly_scope_picker_view",
            scanned_count=64,
            excluded_completed_count=38,
            excluded_no_remainder_count=20,
            already_planned_count=3,
            package_candidate_count=2,
        )
        event = AgentEventView(
            event_id="evt-done",
            event_type="RUN_COMPLETED",
            family="RUN",
            status="COMPLETED",
            title="completed",
            occurred_at=FIXED_AT,
            stage_id=None,
            node_name=None,
            attempt_n=1,
            resume_n=0,
            interrupt_id=None,
            decision_id=None,
            handoff_id=None,
            artifact_type=None,
            artifact_id=None,
            tool_name=None,
        )
        snap = _snapshot(timeline_events=(event,))
        st.button_calls.clear()
        page._render_constructor_employee(snap, result)
        primary = "\n".join(
            st.primary_markdown
            + [str(item) for item in st.primary_writes]
            + [str(item) for item in st.dataframe_calls]
            + st.warning_calls
            + st.info_calls
        )
        technical = "\n".join(st.technical_markdown + [str(item) for item in st.technical_writes])
        self.assertIn("Конструктор месячного плана", primary)
        self.assertIn("В контуре миссии", primary)
        self.assertIn("Проверено", primary)
        self.assertIn("Кандидатов Constructor", primary)
        self.assertIn("2 / 2", primary)
        self.assertIn("16 строк:", primary)
        self.assertIn("1 проверенная строка:", primary)
        self.assertIn("2 из 80", primary)
        self.assertIn("2041-01-22-02", primary)
        self.assertIn("2041-01-27-02", primary)
        self.assertIn("9,08 м²", primary)
        self.assertIn("0,01 м²", primary)
        candidate_tables = [
            frame
            for frame in st.dataframe_calls
            if hasattr(frame, "columns") and "BOQ" in list(frame.columns) and len(frame) == 2
        ]
        candidate_cells = " ".join(candidate_tables[-1].astype(str).to_numpy().ravel())
        self.assertIn("1,15 м³", candidate_cells)
        self.assertIn("≈ 0 м³", candidate_cells)
        self.assertNotIn("м2 / m2", primary)
        self.assertNotIn("м3 / m3", primary)
        self.assertIn("Требуется решение человека", primary)
        self.assertIn("Нет подтверждённой нормы труда.", primary)
        self.assertIn("✕ НЕ ОК / исключено", primary)
        self.assertIn("Подтверждено человеком", primary)
        self.assertIn("Включено человеком: 0", primary)
        self.assertIn("Исключено: 2", primary)
        self.assertIn("Итоговый пакет: 0 работ", primary)
        self.assertIn("Не выполнялась", primary)
        self.assertNotIn("9.079999999999998", primary)
        self.assertNotIn("2.220446049250313e-15", primary)
        self.assertNotIn("run-page-001", primary)
        self.assertNotIn("pkg-1", primary)
        self.assertEqual(st.button_calls, [])
        self.assertIn("Технические доказательства и аудит", st.expander_labels)
        self.assertIn("Run ID: run-page-001", technical)
        self.assertIn("Candidate Package ID: pkg-1", technical)
        self.assertIn("9.079999999999998", technical)
        self.assertIn("RUN_COMPLETED: зафиксирован", technical)
        self.assertNotIn("81", primary + technical)
        self.assertNotIn("месячный план утверждён", (primary + technical).casefold())
        self.assertNotIn("Admission", primary + technical)
        self.assertNotIn("Executability", primary + technical)
        source = PAGE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("sqlite3", source)
        self.assertNotIn("SqliteSaver", source)
        self.assertNotIn("checkpoints.sqlite", source)
        self.assertNotIn("supabase", source.casefold())

    def test_constructor_registry_shows_all_live_decisions(self) -> None:
        page, st = _load_page_module()
        candidates = (
            ConstructorCandidateResultView(
                candidate_id="c-1",
                boq_code="2041-01-22-02",
                name="Решетка",
                unit="м2 / m2",
                remaining_qty="9.079999999999998",
                already_planned_qty="9.07",
                available_qty="0.00999999999999801",
                labor_status="UNRESOLVED",
                recommendation="HUMAN_REVIEW_REQUIRED",
                exception_codes=(),
                human_review_decision="",
                final_disposition="",
                final_reason_code="",
            ),
            ConstructorCandidateResultView(
                candidate_id="c-2",
                boq_code="2041-01-27-02",
                name="Изоляция",
                unit="м3 / m3",
                remaining_qty="1.15",
                already_planned_qty="1.15",
                available_qty="0",
                labor_status="UNRESOLVED",
                recommendation="HUMAN_REVIEW_REQUIRED",
                exception_codes=(),
                human_review_decision="",
                final_disposition="",
                final_reason_code="",
            ),
        )
        result = ConstructorProfessionalResultView(
            availability=ProfessionalResultAvailability.AVAILABLE,
            run_id="run-76ae10af-69f7-4588-91f5-5b0f5d28052a",
            mission_id="live-proof-row-decision-20261012T084022Z",
            professional_status="WAITING_FOR_HUMAN_REVIEW",
            project_id="PRJ_001_БХК",
            month="октябрь-2026",
            facility_id="16160-13",
            discipline="ВЕНТИЛЯЦИЯ",
            source_candidate_package_id="pkg-live",
            reviewed_package_id="",
            included_count=None,
            excluded_count=None,
            unresolved_count=None,
            confirm_event_id="",
            confirm_decision="",
            confirm_actor_type="",
            confirm_actor_id="",
            path_statuses=("WAITING_FOR_HUMAN_REVIEW",),
            candidates=candidates,
            package_candidate_count=2,
        )
        records = _registry_records()
        registry = ConstructorDecisionRegistryView(
            availability=ProfessionalResultAvailability.AVAILABLE,
            professional=result,
            total_count=len(records),
            outcome_counts=(
                ("CANDIDATE", 2),
                ("EXCLUDED_ALREADY_PLANNED", 3),
                ("EXCLUDED_COMPLETED", 38),
                ("EXCLUDED_INVALID", 16),
                ("EXCLUDED_NO_REMAINDER", 20),
                ("EXCLUDED_OVERRUN", 1),
            ),
            known_systems=("AHU-001",),
            attention_count=2,
            records=records,
        )
        snap = _snapshot()
        before_buttons = len(st.button_calls)
        before_frames = len(st.dataframe_calls)
        page._render_constructor_registry(snap, result, registry, port=None)
        primary = "\n".join(
            st.primary_markdown
            + [str(item) for item in st.primary_writes]
        )
        technical = "\n".join(str(item) for item in st.technical_writes)
        rendered_frames = st.dataframe_calls[before_frames:]
        rendered_cells = " ".join(
            " ".join(frame.astype(str).to_numpy().ravel()) for frame in rendered_frames
        )
        self.assertIn("РЕЕСТР РЕШЕНИЙ CONSTRUCTOR", primary)
        self.assertIn("РАБОТ В МИССИИ", primary)
        self.assertEqual(len(rendered_frames[0]), 80)
        self.assertIn("Кандидат Constructor", rendered_cells)
        self.assertIn("Не включать · работа выполнена", rendered_cells)
        self.assertIn("Не включать · остатка нет", rendered_cells)
        self.assertIn("Уже включено в план", rendered_cells)
        self.assertIn("Не включать · исходные данные невалидны", rendered_cells)
        self.assertIn("Не включать · выявлено превышение", rendered_cells)
        self.assertIn("9,08 м²", rendered_cells)
        self.assertIn("0,01 м²", rendered_cells)
        self.assertNotIn("EXCLUDED_COMPLETED", rendered_cells)
        self.assertNotIn("9.079999999999998", rendered_cells)
        self.assertIn("ещё не подтверждён", primary)
        self.assertIn("решений человека: 0 / 2", primary)
        rendered_buttons = st.button_calls[before_buttons:]
        self.assertIn("✓ ОК", [item["label"] for item in rendered_buttons])
        self.assertTrue(all(item["disabled"] for item in rendered_buttons))
        self.assertIn("EXCLUDED_COMPLETED: 38", technical)
        self.assertNotIn("16 строк:", primary)
        source = PAGE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("sqlite3", source)
        self.assertNotIn("checkpoints.sqlite", source)

    def test_workspace_binds_waiting_run_registry(self) -> None:
        page, st = _load_page_module()
        records = _registry_records()
        candidates = (
            ConstructorCandidateResultView(
                candidate_id="c-1",
                boq_code="2041-01-22-02",
                name="Решетка",
                unit="м2 / m2",
                remaining_qty="9.079999999999998",
                already_planned_qty="9.07",
                available_qty="0.00999999999999801",
                labor_status="UNRESOLVED",
                recommendation="HUMAN_REVIEW_REQUIRED",
                exception_codes=(),
                human_review_decision="",
                final_disposition="",
                final_reason_code="",
            ),
            ConstructorCandidateResultView(
                candidate_id="c-2",
                boq_code="BOQ-001",
                name="Изоляция",
                unit="м2 / m2",
                remaining_qty="1",
                already_planned_qty="0",
                available_qty="1",
                labor_status="UNRESOLVED",
                recommendation="HUMAN_REVIEW_REQUIRED",
                exception_codes=(),
                human_review_decision="",
                final_disposition="",
                final_reason_code="",
            ),
        )
        result = ConstructorProfessionalResultView(
            availability=ProfessionalResultAvailability.AVAILABLE,
            run_id="run-76ae10af-69f7-4588-91f5-5b0f5d28052a",
            mission_id="live-proof-row-decision-20261012T084022Z",
            professional_status="WAITING_FOR_HUMAN_REVIEW",
            project_id="PRJ_001_БХК",
            month="октябрь-2026",
            facility_id="16160-13",
            discipline="ВЕНТИЛЯЦИЯ",
            source_candidate_package_id="pkg-live",
            reviewed_package_id="",
            included_count=None,
            excluded_count=None,
            unresolved_count=None,
            confirm_event_id="",
            confirm_decision="",
            confirm_actor_type="",
            confirm_actor_id="",
            path_statuses=("WAITING_FOR_HUMAN_REVIEW",),
            candidates=candidates,
            package_candidate_count=2,
        )
        registry = ConstructorDecisionRegistryView(
            availability=ProfessionalResultAvailability.AVAILABLE,
            professional=result,
            total_count=len(records),
            outcome_counts=(
                ("CANDIDATE", 2),
                ("EXCLUDED_ALREADY_PLANNED", 3),
                ("EXCLUDED_COMPLETED", 38),
                ("EXCLUDED_INVALID", 16),
                ("EXCLUDED_NO_REMAINDER", 20),
                ("EXCLUDED_OVERRUN", 1),
            ),
            known_systems=("AHU-001",),
            attention_count=2,
            records=records,
        )
        st.session_state["dynamis_mission_draft"] = parse_mission_text(
            "БХК / 1 очередь / титулы 13,17 / вентиляция / П1 П2 П3 В1 В2 В3 / ноябрь 2026"
        )
        before = len(st.dataframe_calls)
        page._render_constructor_workspace(_snapshot(), registry)
        text = "\n".join(
            st.primary_markdown
            + [str(item) for item in st.primary_writes]
            + st.info_calls
            + st.warning_calls
        )
        frame = st.dataframe_calls[before]
        cells = " ".join(frame.astype(str).to_numpy().ravel())
        self.assertIn("БХК · октябрь 2026", text)
        self.assertIn("разные состояния", text)
        self.assertIn("В контуре миссии: 80", text)
        self.assertIn("Выполнено: 38", text)
        self.assertIn("Кандидаты: 2", text)
        self.assertIn("Требуют решения человека: 2", text)
        self.assertEqual(len(frame), 80)
        self.assertIn("Кандидат Constructor", cells)
        self.assertNotIn("EXCLUDED_COMPLETED", cells)
        self.assertIn("HITL Command Port", text)
        self.assertIn("после подтверждения итогового состава", text)
        self.assertIn("Рассмотрено Constructor: 80", text)
        self.assertIn("Предложено к включению: 2", text)
        self.assertIn("Временный выпуск без допуска", "\n".join(st.primary_markdown))
        buttons = [
            item
            for item in st.button_calls
            if item["label"] in {
                "ОК",
                "НЕ ОК",
                "В ДРУГОЙ МЕСЯЦ",
                "НУЖНЫ ДАННЫЕ",
                "ПОДТВЕРДИТЬ РЕЗУЛЬТАТ",
                "ПЕРЕДАТЬ ИНЖЕНЕРУ ПРОИЗВОДСТВЕННОЙ ГОТОВНОСТИ И ДОПУСКА",
            }
        ]
        self.assertGreaterEqual(len(buttons), 5)
        self.assertTrue(all(item["disabled"] for item in buttons))
        export_buttons = [item for item in st.button_calls if "XLSX" in item["label"]]
        self.assertEqual(len(export_buttons), 1)
        self.assertFalse(export_buttons[0]["disabled"])

    def test_modules_5_to_9_stay_visible_without_a_professional_result(self) -> None:
        from agents.human_surface.mission_recovery import CONTINUES_EXECUTION_RU

        page, st = _load_page_module()
        st.session_state["dynamis_active_run_id"] = "run-830bc0c5-5a10-4ab6-9a19-da822662e041"
        st.session_state["dynamis_execution_lifecycle"] = "REALITY_LOADED"
        page._render_constructor_workspace(None, None)
        markdown = "\n".join(st.primary_markdown)
        text = "\n".join(
            st.primary_markdown
            + [str(item) for item in st.primary_writes]
            + st.info_calls
        )
        for heading in (
            "Результат работы",
            "Решение человека",
            "Итог",
            "Передать дальше",
            "Временный выпуск без допуска",
        ):
            self.assertIn(heading, markdown)
        self.assertIn(CONTINUES_EXECUTION_RU, text)
        self.assertIn("Candidate Package: ещё не сформирован", text)
        self.assertIn("Профессиональный результат: ещё не сформирован", text)
        self.assertIn("Решения человека появятся после формирования результата цифровым сотрудником.", text)
        self.assertIn("Итоговый состав ещё не сформирован.", text)
        self.assertIn("Выгрузка станет доступна после формирования предварительного состава Constructor.", text)
        labels = [item["label"] for item in st.button_calls]
        self.assertIn("ПЕРЕДАТЬ ИНЖЕНЕРУ ПРОИЗВОДСТВЕННОЙ ГОТОВНОСТИ И ДОПУСКА", labels)
        self.assertIn("ПОДТВЕРДИТЬ РЕЗУЛЬТАТ", labels)
        self.assertNotIn("530", text)
        self.assertEqual(st.dataframe_calls, [])
        export_buttons = [item for item in st.button_calls if "XLSX" in item["label"]]
        self.assertEqual(len(export_buttons), 1)
        self.assertTrue(export_buttons[0]["disabled"])


def _registry_records() -> tuple[ConstructorRowDecisionView, ...]:
    plan = (
        ("CANDIDATE", 2, "9.079999999999998", "9.07", "0.00999999999999801"),
        ("EXCLUDED_COMPLETED", 38, "0", "0", "0"),
        ("EXCLUDED_NO_REMAINDER", 20, "0", "0", "0"),
        ("EXCLUDED_ALREADY_PLANNED", 3, "10", "10", "0"),
        ("EXCLUDED_INVALID", 16, None, None, None),
        ("EXCLUDED_OVERRUN", 1, "0", "0", "0"),
    )
    records: list[ConstructorRowDecisionView] = []
    order = 0
    for outcome, count, remaining, planned, available in plan:
        for _ in range(count):
            boq = "2041-01-22-02" if outcome == "CANDIDATE" and order == 0 else f"BOQ-{order:03d}"
            records.append(
                ConstructorRowDecisionView(
                    source_identity=f"{order}|{boq}",
                    source_order=order,
                    boq_code=boq,
                    name=f"Работа {order}",
                    unit="м2 / m2",
                    system="AHU-001" if outcome == "EXCLUDED_COMPLETED" else None,
                    remaining_qty=remaining,
                    already_planned_qty=planned,
                    available_qty=available,
                    outcome=outcome,
                    reason_code=outcome,
                    reason_text="Сохранённое основание",
                    requires_human=None if outcome == "CANDIDATE" else False,
                    candidate_created=outcome == "CANDIDATE",
                    candidate_id="c-1" if order == 0 else ("c-2" if outcome == "CANDIDATE" else ""),
                )
            )
            order += 1
    return tuple(records)


if __name__ == "__main__":
    unittest.main()
