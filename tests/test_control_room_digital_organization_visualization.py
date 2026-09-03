"""
Increment 10.9B — Digital Organization visualization tests.

Streamlit stub pattern. Observe-only. No browser automation. No LLM.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Optional

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
    DigitalOrganizationExecutionView,
    HandoffStatus,
    ProfessionalExecutionState,
    ProfessionalExecutionStepKind,
    ProfessionalExecutionStepView,
    StageDisplayState,
)
from agents.control_room.presentation import (
    DIGITAL_ORG_HISTORY_INCOMPLETE_RU,
    DIGITAL_ORG_SECTION_TITLE_RU,
    HANDOFF_CREATED_NOT_PERSISTED_RU,
    HANDOFF_CREATED_ORG_RU,
    HANDOFF_INCONSISTENT_RU,
    HANDOFF_LEGACY_INCOMPLETE_RU,
    HANDOFF_NOT_OBSERVED_RU,
    HANDOFF_PERSIST_FAILED_ORG_RU,
    HANDOFF_PERSISTED_ORG_RU,
    OWNERSHIP_NOT_PROVEN_RU,
    RECEIVER_ACCEPTANCE_NOT_CONFIRMED_RU,
    RECEIVER_START_NOT_CONFIRMED_RU,
    SOURCE_ROLE_COMPLETED_RU,
    TARGET_ROLE_LABEL_RU,
    agent_role_ru,
)
from agents.observability.contracts import OperationalStatus

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = REPO_ROOT / "pages" / "53_AI_Центр_управления_агентами.py"
CONTROL_ROOM_ROOT = REPO_ROOT / "agents" / "control_room"
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
        self.error_calls: list[str] = []
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
        self.error_calls.append(body)

    def container(self, **kwargs: Any) -> Any:
        return self.expander("container")

    def columns(self, spec: Any, **kwargs: Any) -> tuple[Any, ...]:
        count = len(spec) if isinstance(spec, list) else int(spec)
        return tuple(_ColumnStub() for _ in range(count))

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
        def __init__(self, stub: "_StreamlitStub", label: str) -> None:
            self._stub = stub
            self._label = label

        def __enter__(self) -> "_StreamlitStub":
            self._stub.expander_stack.append(self._label)
            return self._stub

        def __exit__(self, *args: Any) -> None:
            if self._stub.expander_stack:
                self._stub.expander_stack.pop()

    def expander(self, label: str, **kwargs: Any) -> _ExpanderContext:
        return self._ExpanderContext(self, label)


class _ColumnStub:
    def __enter__(self) -> "_ColumnStub":
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
        "run_id": "run-org-001",
        "agent_code": "MONTHLY_PLAN_CONSTRUCTOR",
        "project_code": "PRJ_001",
        "month_key": "2026-09",
        "mission_id": "mission-001",
        "operational_status": OperationalStatus.COMPLETED.value,
        "requested_at": FIXED_AT,
        "updated_at": LATER_AT,
        "started_at": FIXED_AT,
        "completed_at": LATER_AT,
        "projection_version": 4,
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
        "handoff_id": "handoff-001",
        "error_code": None,
        "safe_error_summary": None,
        "safe_summary": (),
        "safe_counts": (),
    }
    payload.update(overrides)
    return AgentRunDetail(**payload)


def _handoff(**overrides: Any) -> AgentHandoffView:
    payload = {
        "handoff_id": "handoff-001",
        "status": HandoffStatus.PERSISTED,
        "created_at": FIXED_AT,
        "persisted_at": LATER_AT,
        "failed_at": None,
        "handoff_type": "CONSTRUCTOR_TO_ADMISSION",
        "target_role_code": "MONTHLY_PLAN_ADMISSION_AGENT",
        "artifact_type": "package",
        "artifact_id": "pkg-001",
        "derivation_state": DerivationState.OK,
    }
    payload.update(overrides)
    return AgentHandoffView(**payload)


def _org_snapshot(
    *,
    run: Optional[AgentRunDetail] = None,
    handoff: Optional[AgentHandoffView] = None,
    history_complete: bool = True,
    derivation_state: Optional[DerivationState] = None,
    events_complete: bool = True,
) -> AgentRunSnapshot:
    detail = run or _detail()
    handoff_view = handoff
    org_handoff = None if handoff_view is None else handoff_view
    org_derivation = derivation_state or (
        DerivationState.OK if handoff_view is None else handoff_view.derivation_state
    )
    path = AgentProfessionalExecutionPathView(
        steps=(
            ProfessionalExecutionStepView(
                step_kind=ProfessionalExecutionStepKind.STAGE,
                step_id="stage-1",
                stage_id="REALITY_READ",
                professional_state=ProfessionalExecutionState.COMPLETED,
                started_at=FIXED_AT,
                completed_at=LATER_AT,
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
        history_complete=history_complete,
    )
    return AgentRunSnapshot(
        run=detail,
        stage=AgentStageView(
            current_stage=None,
            occurrences=(),
            derivation_state=DerivationState.OK,
        ),
        human_wait=AgentHumanWaitView(
            waiting_for_human=False,
            interrupt_id=None,
            wait_started_at=None,
            decision_id=None,
            wait_closed_by=None,
            wait_ordinal=None,
            derivation_state=DerivationState.OK,
        ),
        human_decision_surface=AgentHumanDecisionSurfaceView(
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
        handoff=handoff_view
        or AgentHandoffView(
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
        professional_execution_path=path,
        digital_organization=DigitalOrganizationExecutionView(
            source_agent_code=detail.agent_code,
            source_run_id=detail.run_id,
            source_operational_status=detail.operational_status,
            source_completed_at=detail.completed_at,
            handoff=org_handoff,
            history_complete=history_complete,
            derivation_state=org_derivation,
        ),
        timeline_events=(),
        events_complete=events_complete,
        read_at=LATER_AT,
    )


def _load_page_module() -> tuple[ModuleType, _StreamlitStub]:
    module_name = "page53_digital_org_viz_test"
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


def _all_text(st: _StreamlitStub) -> str:
    parts: list[str] = []
    parts.extend(st.markdown_calls)
    parts.extend(st.info_calls)
    parts.extend(st.warning_calls)
    parts.extend(st.error_calls)
    parts.extend(st.caption_calls)
    for args in st.write_calls:
        parts.extend(str(arg) for arg in args)
    return "\n".join(parts)


class DigitalOrganizationVisualizationTests(unittest.TestCase):
    def test_section_title_and_source_completion(self) -> None:
        page, st = _load_page_module()
        page._render_selected_run(_org_snapshot(handoff=_handoff()))
        text = _all_text(st)
        self.assertIn(DIGITAL_ORG_SECTION_TITLE_RU, text)
        self.assertIn(agent_role_ru("MONTHLY_PLAN_CONSTRUCTOR"), text)
        self.assertIn(SOURCE_ROLE_COMPLETED_RU, text)

    def test_artifact_and_persisted_handoff(self) -> None:
        page, st = _load_page_module()
        page._render_selected_run(_org_snapshot(handoff=_handoff()))
        text = _all_text(st)
        self.assertIn("Пакет кандидатов", text)
        self.assertIn(HANDOFF_PERSISTED_ORG_RU, text)
        self.assertIn(agent_role_ru("MONTHLY_PLAN_ADMISSION_AGENT"), text)
        self.assertIn(TARGET_ROLE_LABEL_RU, text)

    def test_created_not_persisted_wording(self) -> None:
        page, st = _load_page_module()
        page._render_selected_run(
            _org_snapshot(
                handoff=_handoff(
                    status=HandoffStatus.CREATED,
                    persisted_at=None,
                )
            )
        )
        text = _all_text(st)
        self.assertIn(HANDOFF_CREATED_ORG_RU, text)
        self.assertIn(HANDOFF_CREATED_NOT_PERSISTED_RU, text)
        self.assertNotIn(HANDOFF_PERSISTED_ORG_RU, text)

    def test_persist_failure_wording(self) -> None:
        page, st = _load_page_module()
        page._render_selected_run(
            _org_snapshot(
                run=_detail(operational_status=OperationalStatus.FAILED.value),
                handoff=_handoff(
                    status=HandoffStatus.PERSIST_FAILED,
                    persisted_at=None,
                    failed_at=LATER_AT,
                ),
            )
        )
        text = _all_text(st)
        self.assertTrue(any(HANDOFF_PERSIST_FAILED_ORG_RU in err for err in st.error_calls))
        self.assertIn(agent_role_ru("MONTHLY_PLAN_ADMISSION_AGENT"), text)
        self.assertNotIn("✓ " + HANDOFF_PERSISTED_ORG_RU, text)

    def test_receiver_honesty_no_false_claims(self) -> None:
        page, st = _load_page_module()
        page._render_selected_run(_org_snapshot(handoff=_handoff()))
        text = _all_text(st)
        self.assertIn(RECEIVER_START_NOT_CONFIRMED_RU, text)
        self.assertIn(RECEIVER_ACCEPTANCE_NOT_CONFIRMED_RU, text)
        self.assertIn(OWNERSHIP_NOT_PROVEN_RU, text)
        for banned in (
            "Получатель не запущен",
            "Получателя нет",
            "receiver_observed",
            "target_run",
            "Ответственность передана",
            "Владение задачей перешло",
            "Получатель принял",
            "оркестрация завершена",
            "Процесс полностью завершён",
        ):
            self.assertNotIn(banned, text)

    def test_legacy_incomplete_wording(self) -> None:
        page, st = _load_page_module()
        page._render_selected_run(
            _org_snapshot(
                handoff=_handoff(
                    status=HandoffStatus.CREATED,
                    handoff_type=None,
                    target_role_code=None,
                    artifact_type=None,
                    artifact_id=None,
                    persisted_at=None,
                    derivation_state=DerivationState.INCOMPLETE,
                ),
                derivation_state=DerivationState.INCOMPLETE,
            )
        )
        text = _all_text(st)
        self.assertIn(HANDOFF_LEGACY_INCOMPLETE_RU, text)
        self.assertNotIn(agent_role_ru("MONTHLY_PLAN_ADMISSION_AGENT"), text)

    def test_inconsistent_warning(self) -> None:
        page, st = _load_page_module()
        page._render_selected_run(
            _org_snapshot(
                handoff=_handoff(derivation_state=DerivationState.INCONSISTENT),
                derivation_state=DerivationState.INCONSISTENT,
            )
        )
        self.assertTrue(any(HANDOFF_INCONSISTENT_RU in w for w in st.warning_calls))

    def test_no_handoff_case(self) -> None:
        page, st = _load_page_module()
        page._render_selected_run(_org_snapshot(handoff=None))
        text = _all_text(st)
        self.assertIn(HANDOFF_NOT_OBSERVED_RU, text)

    def test_incomplete_history_wording(self) -> None:
        page, st = _load_page_module()
        page._render_selected_run(
            _org_snapshot(handoff=_handoff(), history_complete=False, events_complete=False)
        )
        text = _all_text(st)
        self.assertIn(DIGITAL_ORG_HISTORY_INCOMPLETE_RU, text)

    def test_execution_path_and_audit_timeline_preserved(self) -> None:
        page, st = _load_page_module()
        page._render_selected_run(_org_snapshot(handoff=_handoff()))
        text = _all_text(st)
        self.assertIn("Профессиональный маршрут выполнения", text)
        self.assertIn("Доступное окно событий", text)
        self.assertIn("Вторичная служебная лента", text)
        title_idx = text.find(DIGITAL_ORG_SECTION_TITLE_RU)
        path_idx = text.find("Профессиональный маршрут выполнения")
        audit_idx = text.find("Доступное окно событий")
        self.assertGreater(title_idx, path_idx)
        self.assertGreater(audit_idx, title_idx)

    def test_no_write_controls(self) -> None:
        page, st = _load_page_module()
        page._render_selected_run(_org_snapshot(handoff=_handoff()))
        text = _all_text(st)
        for label in (
            "Запустить",
            "Продолжить",
            "Согласовать",
            "Отклонить",
            "Передать",
            "Старт целевого",
        ):
            self.assertNotIn(label, text)


class DigitalOrganizationArchitectureGuards(unittest.TestCase):
    def test_control_room_has_no_constructor_imports(self) -> None:
        for path in CONTROL_ROOM_ROOT.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(alias.name.startswith("agents.monthly_plan_constructor"))
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertFalse(node.module.startswith("agents.monthly_plan_constructor"))
                    self.assertNotEqual(node.module, "agents.monthly_plan_constructor.handoff_contracts")

    def test_page_has_no_forbidden_write_or_raw_access(self) -> None:
        source = PAGE_PATH.read_text(encoding="utf-8")
        for banned in (
            "ConstructorHandoffStore",
            "SqliteObservabilityStore",
            "event.detail",
            "__dict__",
            "asdict(",
            "openai",
            "anthropic",
        ):
            self.assertNotIn(banned, source)


if __name__ == "__main__":
    unittest.main()
