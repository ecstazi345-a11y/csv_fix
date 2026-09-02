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
    HandoffStatus,
    HumanDecisionConsequenceView,
    HumanDecisionRecordView,
    HumanDecisionRequestView,
    ProfessionalExecutionState,
    ProfessionalExecutionStepKind,
    ProfessionalExecutionStepView,
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
from agents.observability.contracts import OperationalStatus

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = REPO_ROOT / "pages" / "53_AI_Центр_управления_агентами.py"
APP_PY = REPO_ROOT / "app.py"

FIXED_AT = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)

_FORBIDDEN_IMPORTS = (
    "sqlite3",
    "agents.observability.sqlite_store",
    "agents.observability.store",
    "agents.monthly_plan_constructor",
    "supabase",
)

_PROHIBITED_WRITE_LABELS = (
    "Запустить",
    "Продолжить",
    "Согласовать",
    "Отклонить",
    "Остановить",
    "Перезапустить",
    "Удалить",
    "Передать",
    "Изменить",
)

_FORBIDDEN_API_SNIPPETS = (
    "run_control",
    "append_event",
    "create_run",
    "SqliteObservabilityStore",
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
        self.button = lambda *a, **k: False
        self.rerun = lambda: None
        self.columns = self._columns
        self.expander = MagicMock()
        self.expander.return_value.__enter__ = lambda s: s
        self.expander.return_value.__exit__ = lambda s, *a: None

    def markdown(self, text: str, *args: Any, **kwargs: Any) -> None:
        self.markdown_calls.append(str(text))

    def warning(self, text: str, *args: Any, **kwargs: Any) -> None:
        self.warning_calls.append(str(text))

    def info(self, text: str, *args: Any, **kwargs: Any) -> None:
        self.info_calls.append(str(text))

    def error(self, text: str, *args: Any, **kwargs: Any) -> None:
        self.error_calls.append(str(text))

    def write(self, *args: Any, **kwargs: Any) -> None:
        self.write_calls.append(args)

    def dataframe(self, data: Any, *args: Any, **kwargs: Any) -> None:
        self.dataframe_calls.append(data)

    def radio(self, label: str, *, options: list[str], index: int = 0, **kwargs: Any) -> str:
        self.radio_calls.append({"label": label, "options": options, "index": index})
        return options[index]

    def selectbox(self, label: str, options: list[str], **kwargs: Any) -> str:
        return options[0]

    def _columns(self, spec: Any, **kwargs: Any) -> list[Any]:
        count = spec if isinstance(spec, int) else len(spec)
        mocks = [MagicMock() for _ in range(count)]
        for mock in mocks:
            mock.__enter__ = lambda s: s
            mock.__exit__ = lambda s, *a: None
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

    def test_main_reads_query_port_catalog_filtered_snapshot(self) -> None:
        page, _st = _load_page_module()
        fake = _FakeQueryPort()
        with patch.object(page, "_cached_query_port", return_value=fake):
            with redirect_stdout(io.StringIO()):
                page.main()
        self.assertEqual(len(fake.list_calls), 2)
        self.assertEqual(fake.list_calls[0]["limit"], 200)
        self.assertEqual(fake.snapshot_calls, ["run-page-001"])


if __name__ == "__main__":
    unittest.main()
