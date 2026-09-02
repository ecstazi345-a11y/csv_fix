"""
Increment 10.8B — Professional execution path visualization tests.

Streamlit stub pattern. No browser automation.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Optional

import pandas as pd

from agents.control_room.dtos import (
    AgentHandoffView,
    AgentHumanDecisionSurfaceView,
    AgentHumanWaitView,
    AgentProfessionalExecutionPathView,
    AgentRunDetail,
    AgentRunSnapshot,
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
    StageArtifactView,
    StageDisplayState,
    StageToolExecutionView,
    ToolExecutionStatus,
    WaitClosedBy,
)
from agents.control_room.presentation import (
    AUTHORITY_NOT_MODELED_RU,
    EXECUTION_PATH_INCOMPLETE_RU,
    HUMAN_DECISION_HEADER_RU,
    POST_DECISION_HEADER_RU,
    professional_stage_id_ru,
    tool_name_ru,
)
from agents.observability.contracts import OperationalStatus

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = REPO_ROOT / "pages" / "53_AI_Центр_управления_агентами.py"
FIXED_AT = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
LATER_AT = datetime(2026, 9, 2, 12, 30, 0, tzinfo=timezone.utc)


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
        self.write_calls: list[tuple[Any, ...]] = []
        self.warning_calls: list[str] = []
        self.info_calls: list[str] = []
        self.caption_calls: list[str] = []
        self.dataframe_calls: list[Any] = []
        self.expander_stack: list[str] = []
        self.cache_resource = _cache_resource_stub

    def set_page_config(self, **kwargs: Any) -> None:
        return None

    def title(self, text: str) -> None:
        self.markdown_calls.append(text)

    def subheader(self, text: str) -> None:
        self.markdown_calls.append(text)

    def markdown(self, body: str, **kwargs: Any) -> None:
        self.markdown_calls.append(body)

    def write(self, *args: Any, **kwargs: Any) -> None:
        self.write_calls.append(args)

    def warning(self, body: str) -> None:
        self.warning_calls.append(body)

    def info(self, body: str) -> None:
        self.info_calls.append(body)

    def caption(self, body: str) -> None:
        self.caption_calls.append(body)

    def error(self, body: str) -> None:
        return None

    def columns(self, spec: Any, **kwargs: Any) -> tuple[Any, ...]:
        return tuple(_ColumnStub() for _ in range(len(spec) if isinstance(spec, list) else spec))

    def selectbox(self, label: str, options: list[Any], **kwargs: Any) -> Any:
        return options[0]

    def button(self, label: str, **kwargs: Any) -> bool:
        return False

    def radio(self, label: str, options: list[Any], **kwargs: Any) -> Any:
        return options[kwargs.get("index", 0)]

    def dataframe(self, data: Any, **kwargs: Any) -> None:
        self.dataframe_calls.append(data)

    def code(self, body: str) -> None:
        return None

    def rerun(self) -> None:
        return None

    class _ExpanderContext:
        def __init__(self, stub: _StreamlitStub, label: str) -> None:
            self._stub = stub
            self._label = label

        def __enter__(self) -> _StreamlitStub:
            self._stub.expander_stack.append(self._label)
            return self._stub

        def __exit__(self, *args: Any) -> None:
            if self._stub.expander_stack:
                self._stub.expander_stack.pop()

    def expander(self, label: str, **kwargs: Any) -> _ExpanderContext:
        return self._ExpanderContext(self, label)


class _ColumnStub:
    def __enter__(self) -> _ColumnStub:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def markdown(self, *args: Any, **kwargs: Any) -> None:
        return None

    def selectbox(self, *args: Any, **kwargs: Any) -> Any:
        options = args[1] if len(args) > 1 else kwargs.get("options", [])
        return options[0] if options else None

    def button(self, *args: Any, **kwargs: Any) -> bool:
        return False


def _detail(**overrides: Any) -> AgentRunDetail:
    payload = {
        "run_id": "run-viz-001",
        "agent_code": "MONTHLY_PLAN_CONSTRUCTOR",
        "project_code": "PRJ_001",
        "month_key": "2026-09",
        "mission_id": "mission-001",
        "operational_status": OperationalStatus.RUNNING.value,
        "requested_at": FIXED_AT,
        "updated_at": FIXED_AT,
        "started_at": FIXED_AT,
        "completed_at": None,
        "projection_version": 3,
        "request_id": "req-001",
        "agent_version": "0.1",
        "orchestration_run_id": "orch-001",
        "initiator_type": "HUMAN",
        "initiator_id": "operator-local",
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


def _human_surface(
    *,
    wait_ordinal: int = 1,
    waiting: bool = False,
    with_decision: bool = False,
    with_consequence: bool = False,
    legacy_request: bool = False,
) -> AgentHumanDecisionSurfaceView:
    wait = AgentHumanWaitView(
        waiting_for_human=waiting,
        interrupt_id=f"intr-{wait_ordinal}",
        wait_started_at=FIXED_AT,
        decision_id="dec-001" if with_decision else None,
        wait_closed_by=WaitClosedBy.RESUMED if with_decision else None,
        wait_ordinal=wait_ordinal,
        derivation_state=DerivationState.OK,
    )
    request = None
    if not legacy_request:
        request = HumanDecisionRequestView(
            interrupt_id=f"intr-{wait_ordinal}",
            wait_ordinal=wait_ordinal,
            stage_id="HUMAN_GATE",
            reason_code="AMBIGUOUS_SCOPE",
            human_readable_reason="Нужно уточнение области",
            allowed_decisions=("CLARIFY_SCOPE", "ABORT_RUN"),
            evidence_refs=("ref-001", "ref-002"),
            derivation_state=DerivationState.OK,
        )
    else:
        request = HumanDecisionRequestView(
            interrupt_id=f"intr-{wait_ordinal}",
            wait_ordinal=wait_ordinal,
            stage_id="HUMAN_GATE",
            reason_code="",
            human_readable_reason=None,
            allowed_decisions=(),
            evidence_refs=(),
            derivation_state=DerivationState.INCOMPLETE,
        )
    decision = None
    if with_decision:
        decision = HumanDecisionRecordView(
            decision_id="dec-001",
            interrupt_id=f"intr-{wait_ordinal}",
            wait_ordinal=wait_ordinal,
            decision_code="CLARIFY_SCOPE",
            actor_id="operator-local",
            actor_type="HUMAN",
            received_at=LATER_AT,
            derivation_state=DerivationState.OK,
        )
    consequence = None
    if with_consequence:
        consequence = HumanDecisionConsequenceView(
            decision_received_at=LATER_AT,
            closed_by=WaitClosedBy.RESUMED,
            closed_at=LATER_AT,
            reality_refresh_started_at=LATER_AT,
            reality_refresh_completed_at=LATER_AT,
            reality_refresh_failed_at=None,
            next_stage_id="CANDIDATE_ASSEMBLY",
            next_stage_started_at=LATER_AT,
            terminal_event_type=None,
            derivation_state=DerivationState.OK,
        )
    return AgentHumanDecisionSurfaceView(
        wait=wait,
        request=request,
        decision=decision,
        consequence=consequence,
        authority_modeled=False,
    )


def _path_snapshot(**overrides: Any) -> AgentRunSnapshot:
    completed_stage = ProfessionalExecutionStepView(
        step_kind=ProfessionalExecutionStepKind.STAGE,
        step_id="stage-done",
        stage_id="REALITY_READ",
        professional_state=ProfessionalExecutionState.COMPLETED,
        started_at=FIXED_AT,
        completed_at=LATER_AT,
        attempt_n=1,
        resume_n=0,
        derivation_state=DerivationState.OK,
        tools=(
            StageToolExecutionView(
                tool_name="load_constructor_scope",
                status=ToolExecutionStatus.COMPLETED,
                stage_id="REALITY_READ",
                attempt_n=1,
                resume_n=0,
                started_at=FIXED_AT,
                completed_at=LATER_AT,
            ),
        ),
        artifacts=(
            StageArtifactView(
                artifact_type="snapshot",
                artifact_id="snap-001",
                stage_id="REALITY_READ",
                resume_n=0,
                created_at=LATER_AT,
            ),
        ),
        human_decision=None,
        reality_refresh=None,
        handoff_id=None,
    )
    running_stage = ProfessionalExecutionStepView(
        step_kind=ProfessionalExecutionStepKind.STAGE,
        step_id="stage-run",
        stage_id="CANDIDATE_ASSEMBLY",
        professional_state=ProfessionalExecutionState.RUNNING,
        started_at=LATER_AT,
        completed_at=None,
        attempt_n=1,
        resume_n=0,
        derivation_state=DerivationState.OK,
        tools=(),
        artifacts=(),
        human_decision=None,
        reality_refresh=None,
        handoff_id=None,
    )
    hitl_step = ProfessionalExecutionStepView(
        step_kind=ProfessionalExecutionStepKind.HUMAN_DECISION,
        step_id="wait-1",
        stage_id="HUMAN_GATE",
        professional_state=ProfessionalExecutionState.WAITING_FOR_HUMAN,
        started_at=FIXED_AT,
        completed_at=None,
        attempt_n=1,
        resume_n=1,
        derivation_state=DerivationState.OK,
        tools=(),
        artifacts=(),
        human_decision=_human_surface(waiting=True),
        reality_refresh=None,
        handoff_id=None,
    )
    payload = {
        "run": _detail(),
        "stage": AgentStageView(
            current_stage=AgentStageOccurrenceView(
                stage_id="CANDIDATE_ASSEMBLY",
                node_name="assemble",
                attempt_n=1,
                resume_n=0,
                artifact_id="",
                display_state=StageDisplayState.RUNNING,
                started_at=LATER_AT,
                completed_at=None,
                started_event_id="stage-run",
                terminal_event_id=None,
            ),
            occurrences=(),
            derivation_state=DerivationState.OK,
        ),
        "human_wait": AgentHumanWaitView(
            waiting_for_human=False,
            interrupt_id=None,
            wait_started_at=None,
            decision_id=None,
            wait_closed_by=None,
            wait_ordinal=None,
            derivation_state=DerivationState.OK,
        ),
        "human_decision_surface": _human_surface(),
        "handoff": AgentHandoffView(
            handoff_id=None,
            status=HandoffStatus.NOT_STARTED,
            created_at=None,
            persisted_at=None,
            derivation_state=DerivationState.OK,
        ),
        "professional_execution_path": AgentProfessionalExecutionPathView(
            steps=(completed_stage, hitl_step, running_stage),
            derivation_state=DerivationState.OK,
            history_complete=True,
        ),
        "timeline_events": (),
        "events_complete": True,
        "read_at": LATER_AT,
    }
    payload.update(overrides)
    return AgentRunSnapshot(**payload)


def _load_page_module() -> tuple[ModuleType, _StreamlitStub]:
    module_name = "page53_execution_viz_test"
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


def _flat_text(st: _StreamlitStub) -> str:
    parts: list[str] = []
    parts.extend(st.markdown_calls)
    parts.extend(st.warning_calls)
    parts.extend(st.info_calls)
    parts.extend(st.caption_calls)
    for args in st.write_calls:
        parts.extend(str(arg) for arg in args)
    for df in st.dataframe_calls:
        if isinstance(df, pd.DataFrame):
            parts.append(df.to_string())
    return " ".join(parts)


class ExecutionVisualizationTests(unittest.TestCase):
    def test_run_header_and_professional_path_rendered(self) -> None:
        page, st = _load_page_module()
        snap = _path_snapshot()
        page._render_selected_run(snap)
        text = _flat_text(st)
        self.assertIn("Выбранный запуск", text)
        self.assertIn("Профессиональный маршрут выполнения", text)
        self.assertIn(snap.run.agent_code, text)
        self.assertIn(snap.run.project_code, text)
        self.assertIn(professional_stage_id_ru("REALITY_READ"), text)

    def test_completed_and_running_stage_labels(self) -> None:
        page, st = _load_page_module()
        page._render_selected_run(_path_snapshot())
        path_df = st.dataframe_calls[0]
        self.assertIsInstance(path_df, pd.DataFrame)
        joined = path_df.to_string()
        self.assertIn(professional_stage_id_ru("REALITY_READ"), joined)
        self.assertIn(professional_stage_id_ru("CANDIDATE_ASSEMBLY"), joined)

    def test_duration_column_present(self) -> None:
        page, st = _load_page_module()
        page._render_selected_run(_path_snapshot())
        path_df = st.dataframe_calls[0]
        self.assertIn("Длительность", path_df.columns)

    def test_tool_and_artifact_shown_in_expander(self) -> None:
        page, st = _load_page_module()
        page._render_selected_run(_path_snapshot())
        text = _flat_text(st)
        self.assertIn(tool_name_ru("load_constructor_scope"), text)
        self.assertIn("Снимок производственной реальности", text)

    def test_hitl_embedded_with_allowed_decisions_and_evidence(self) -> None:
        page, st = _load_page_module()
        page._render_selected_run(_path_snapshot())
        text = _flat_text(st)
        self.assertIn(HUMAN_DECISION_HEADER_RU, text)
        self.assertIn("CLARIFY_SCOPE", text.replace("Уточнить область миссии", "CLARIFY_SCOPE") or text)
        self.assertIn("Уточнить область миссии", text)
        self.assertIn("2 структурированных ссылок", text)
        self.assertIn(AUTHORITY_NOT_MODELED_RU, text)

    def test_decision_actor_and_post_decision_consequence(self) -> None:
        page, st = _load_page_module()
        completed_hitl = ProfessionalExecutionStepView(
            step_kind=ProfessionalExecutionStepKind.HUMAN_DECISION,
            step_id="wait-done",
            stage_id="HUMAN_GATE",
            professional_state=ProfessionalExecutionState.COMPLETED,
            started_at=FIXED_AT,
            completed_at=LATER_AT,
            attempt_n=1,
            resume_n=1,
            derivation_state=DerivationState.OK,
            tools=(),
            artifacts=(),
            human_decision=_human_surface(with_decision=True, with_consequence=True),
            reality_refresh=None,
            handoff_id=None,
        )
        path = AgentProfessionalExecutionPathView(
            steps=(completed_hitl,),
            derivation_state=DerivationState.OK,
            history_complete=True,
        )
        page._render_selected_run(_path_snapshot(professional_execution_path=path))
        text = _flat_text(st)
        self.assertIn("operator-local", text)
        self.assertIn(POST_DECISION_HEADER_RU, text)
        self.assertIn("Производственная реальность повторно проверена.", text)

    def test_reality_refresh_step_title(self) -> None:
        page, st = _load_page_module()
        refresh_step = ProfessionalExecutionStepView(
            step_kind=ProfessionalExecutionStepKind.REALITY_REFRESH,
            step_id="rr-1",
            stage_id="REALITY_REVALIDATION",
            professional_state=ProfessionalExecutionState.COMPLETED,
            started_at=FIXED_AT,
            completed_at=LATER_AT,
            attempt_n=1,
            resume_n=1,
            derivation_state=DerivationState.OK,
            tools=(),
            artifacts=(),
            human_decision=None,
            reality_refresh=RealityRefreshStepView(
                stage_id="REALITY_REVALIDATION",
                resume_n=1,
                started_at=FIXED_AT,
                completed_at=LATER_AT,
                failed_at=None,
                derivation_state=DerivationState.OK,
            ),
            handoff_id=None,
        )
        path = AgentProfessionalExecutionPathView(
            steps=(refresh_step,),
            derivation_state=DerivationState.OK,
            history_complete=True,
        )
        page._render_selected_run(_path_snapshot(professional_execution_path=path))
        text = _flat_text(st)
        self.assertIn(professional_stage_id_ru("REALITY_REVALIDATION"), text)

    def test_incomplete_history_warning(self) -> None:
        page, st = _load_page_module()
        path = AgentProfessionalExecutionPathView(
            steps=(),
            derivation_state=DerivationState.INCOMPLETE,
            history_complete=False,
        )
        page._render_selected_run(
            _path_snapshot(professional_execution_path=path, events_complete=False)
        )
        self.assertTrue(any(EXECUTION_PATH_INCOMPLETE_RU in text for text in st.info_calls))

    def test_inconsistent_path_warning(self) -> None:
        page, st = _load_page_module()
        path = AgentProfessionalExecutionPathView(
            steps=(),
            derivation_state=DerivationState.INCONSISTENT,
            history_complete=True,
        )
        page._render_selected_run(_path_snapshot(professional_execution_path=path))
        self.assertTrue(st.warning_calls)

    def test_audit_timeline_secondary_caption(self) -> None:
        page, st = _load_page_module()
        from agents.control_room.dtos import AgentEventView

        snap = _path_snapshot(
            timeline_events=(
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
        )
        page._render_selected_run(snap)
        self.assertTrue(
            any("Вторичная служебная лента" in text for text in st.caption_calls)
        )
        self.assertEqual(len(st.dataframe_calls), 2)

    def test_legacy_hitl_context_message(self) -> None:
        page, st = _load_page_module()
        hitl_step = ProfessionalExecutionStepView(
            step_kind=ProfessionalExecutionStepKind.HUMAN_DECISION,
            step_id="wait-legacy",
            stage_id="HUMAN_GATE",
            professional_state=ProfessionalExecutionState.INCOMPLETE,
            started_at=FIXED_AT,
            completed_at=None,
            attempt_n=1,
            resume_n=1,
            derivation_state=DerivationState.INCOMPLETE,
            tools=(),
            artifacts=(),
            human_decision=_human_surface(legacy_request=True),
            reality_refresh=None,
            handoff_id=None,
        )
        path = AgentProfessionalExecutionPathView(
            steps=(hitl_step,),
            derivation_state=DerivationState.INCOMPLETE,
            history_complete=True,
        )
        page._render_selected_run(_path_snapshot(professional_execution_path=path))
        text = _flat_text(st)
        self.assertIn("Профессиональный контекст ожидания недоступен", text)

    def test_no_write_controls_in_page_source(self) -> None:
        source = PAGE_PATH.read_text(encoding="utf-8")
        for label in ("Согласовать", "Отклонить", "Продолжить", "Перезапустить"):
            self.assertNotIn(label, source)


if __name__ == "__main__":
    unittest.main()
