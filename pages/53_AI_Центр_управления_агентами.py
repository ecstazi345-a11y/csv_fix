# ============================================================
# Page 53 — DYNAMIS · Цифровые сотрудники
# Thin human surface. Reads through the Query Port.
# Launch goes only through the Mission Command Port after ЗАПУСТИТЬ.
# Does not write product state.
# ============================================================

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import streamlit as st

from agents.control_room.dtos import (
    AgentRunListView,
    AgentRunSnapshot,
    ConstructorDecisionRegistryView,
    ConstructorProfessionalResultView,
    ConstructorRowDecisionView,
    DerivationState,
    HandoffStatus,
    ProfessionalExecutionStepKind,
    ProfessionalResultAvailability,
    constructor_row_awaits_human_review,
    empty_constructor_decision_registry,
    inconsistent_constructor_professional_result,
)
from agents.control_room.errors import (
    ControlRoomQueryBlockerError,
    ControlRoomQueryError,
    ControlRoomRunNotFoundError,
    ControlRoomStorageUnavailableError,
)
from agents.control_room.factory import (
    AGENT_OBSERVABILITY_DB_PATH_ENV,
    ControlRoomConfigurationError,
    build_agent_control_room_query_port,
    resolve_observability_db_path,
)
from agents.human_surface.mission_draft import (
    COMMAND_EXECUTION_REQUIRED_RU,
    CONFIRM_COMMAND_PORT_REQUIRED_RU,
    CONSTRUCTOR_AGENT_CODE,
    GLOBAL_VOICE_RECORDED_RU,
    HANDOFF_COMMAND_PORT_REQUIRED_RU,
    HITL_COMMAND_PORT_REQUIRED_RU,
    EXISTING_MONTHLY_ANALYSIS_RU,
    EXISTING_MONTHLY_WORK_ACTION_RU,
    SEPARATE_ASSIGNMENT_RU,
    WORK_CONTEXT_OUT_OF_SCOPE_RU,
    WORK_CONTEXT_SLICE_RU,
    GlobalCommandDraft,
    MissionDraft,
    WorkingContext,
    apply_global_command,
    empty_working_context,
    global_command_preview_lines,
    mission_from_context,
    parse_global_command,
)
from agents.human_surface.workforce import (
    CONTOURS,
    contour_by_code,
    contour_from_option_label,
    contour_option_label,
    contour_title,
    employee_by_code,
    employee_from_option_label,
    employee_option_label,
    employee_title,
    employees_of,
)
from agents.human_surface.mission_recovery import (
    CONTINUES_EXECUTION_RU,
    REALITY_LOADED,
    RECOVERY_CONTINUE_RU,
    RecoveredMission,
    find_usable_professional_run,
    load_recovery_decision,
    operational_status_for_run,
    working_context_from_mission,
)
from agents.human_surface.pre_admission_export import (
    EXPORT_BUTTON_LABEL,
    EXPORT_INTRO_RU,
    EXPORT_SECTION_TITLE,
    EXPORT_UNAVAILABLE_RU,
    build_pre_admission_workbook,
    export_available,
    export_filename,
)
from agents.human_surface.mission_command import (
    MissionCommandError,
    active_result_run_id,
    different_mission_state,
    launch_monthly_plan_mission,
    launch_status_label,
    mission_gaps,
    mission_idempotency_key,
    mission_preview_lines,
)
from agents.human_surface.human_review_batch import (
    prepare_batch_from_text,
    submit_human_review_batch,
)
from agents.human_surface.final_confirm_command import (
    STALE_PREVIEW_RU,
    FinalConfirmError,
    find_current_approved_package,
    not_ready_message,
    prepare_final_monthly_approval_preview,
    submit_final_monthly_confirm,
)
from agents.human_surface.human_review_command import (
    HumanReviewAction,
    HumanReviewCommand,
    HumanReviewCommandError,
    prepare_human_review_surface,
    submit_human_review_decision,
)
from agents.human_surface.human_review_focus import (
    build_focus_set_from_work_context,
    durable_exception_detail_rows,
    grouped_review_summary,
)
from agents.human_surface.monthly_commitment_draft import (
    NON_CANDIDATE_CLARIFICATION_RU,
    build_monthly_commitment_draft,
    build_work_context_review_summary,
    composition_table_dicts,
    is_non_candidate_reference_error,
)
from agents.human_surface.work_context import (
    DISCIPLINES_UNAVAILABLE_RU,
    PACKAGES_UNAVAILABLE_RU,
    PROJECTS_UNAVAILABLE_RU,
    QUEUES_UNAVAILABLE_RU,
    SYSTEMS_UNAVAILABLE_RU,
    TITLES_UNAVAILABLE_RU,
    WorkContextCatalog,
    align_working_context,
    load_work_context_catalog,
    selector_options,
)
from agents.human_surface.result_view import (
    MODULE5_TITLE_RU,
    build_module5_result_summary_from_records,
    candidate_situation_line,
    filter_records_by_work_context,
    human_decision_tally,
    module5_filter_options,
    module5_kpi_tiles,
    module5_state_timestamp,
    order_records_by_candidate_ids,
    professional_status_line,
    select_workspace_records,
    workspace_run_banner,
    workspace_table_rows,
)
from agents.control_room.presentation import (
    CONSTRUCTOR_CANDIDATES_TITLE_RU,
    CONSTRUCTOR_COMPLETED_LINE_RU,
    CONSTRUCTOR_EMPLOYEE_SUBTITLE_RU,
    CONSTRUCTOR_EMPLOYEE_TITLE_RU,
    CONSTRUCTOR_EVIDENCE_TITLE_RU,
    CONSTRUCTOR_HUMAN_REQUEST_RU,
    CONSTRUCTOR_HUMAN_TITLE_RU,
    CONSTRUCTOR_OUTCOME_TITLE_RU,
    CONSTRUCTOR_PATH_TITLE_RU,
    CONSTRUCTOR_WORK_TITLE_RU,
    NO_NEXT_TRANSFER_RU,
    PROFESSIONAL_RESULT_INCONSISTENT_RU,
    PROFESSIONAL_RESULT_UNAVAILABLE_RU,
    AUTHORITY_NOT_MODELED_RU,
    CATALOG_INCOMPLETE_FILTER_RU,
    DIGITAL_ORG_HISTORY_INCOMPLETE_RU,
    DIGITAL_ORG_SECTION_SUBTITLE_RU,
    DIGITAL_ORG_SECTION_TITLE_RU,
    EMPTY_RUNS_INCOMPLETE_CATALOG_RU,
    EMPTY_RUNS_RU,
    EVENTS_COMPLETE_FALSE_RU,
    EXECUTION_PATH_INCOMPLETE_RU,
    HANDOFF_INCONSISTENT_RU,
    HANDOFF_LEGACY_INCOMPLETE_RU,
    HANDOFF_NOT_CONFIRMED_INCOMPLETE_RU,
    HANDOFF_NOT_OBSERVED_RU,
    HUMAN_DECISION_HEADER_RU,
    POST_DECISION_HEADER_RU,
    RUNS_COMPLETE_FALSE_RU,
    TARGET_ROLE_LABEL_RU,
    WAITING_FOR_HUMAN_RU,
    agent_role_ru,
    all_operational_status_options,
    artifact_type_ru,
    catalog_filter_values,
    decision_code_ru,
    derivation_execution_path_warning,
    derivation_stage_warning,
    digital_org_handoff_status_lines,
    digital_org_receiver_honesty_lines,
    digital_org_source_completion_line,
    CONSTRUCTOR_AGENT_RECOMMENDATION_TITLE_RU,
    CONSTRUCTOR_CANDIDATES_TITLE_RU,
    CONSTRUCTOR_COMPLETED_LINE_RU,
    CONSTRUCTOR_EVIDENCE_TITLE_RU,
    CONSTRUCTOR_HUMAN_TITLE_RU,
    CONSTRUCTOR_MISSION_TITLE_RU,
    CONSTRUCTOR_NEXT_TRANSFER_RU,
    CONSTRUCTOR_OUTCOME_TITLE_RU,
    CONSTRUCTOR_RESULT_TITLE_RU,
    CONSTRUCTOR_FINAL_PACKAGE_TITLE_RU,
    CONSTRUCTOR_REGISTRY_TITLE_RU,
    CONSTRUCTOR_ALREADY_PLANNED_GAP_RU,
    CONSTRUCTOR_HITL_QUESTION_RU,
    CONSTRUCTOR_HITL_WRITE_UNAVAILABLE_RU,
    CONSTRUCTOR_MISSING_ROW_ARTIFACT_RU,
    constructor_context_system,
    constructor_decision_summary_tiles,
    constructor_decision_table_rows,
    constructor_detail_gap_line,
    constructor_discipline_display,
    constructor_final_package_lines,
    constructor_funnel_steps,
    constructor_funnel_warnings,
    constructor_hitl_actions_visible,
    constructor_month_display,
    constructor_package_summary_lines,
    constructor_path_labels,
    constructor_project_short,
    constructor_registry_filter_options,
    constructor_registry_query,
    constructor_row_outcome_label,
    constructor_processing_scale_lines,
    constructor_rows_for_view,
    constructor_saved_decision_label,
    constructor_stop_reason,
    constructor_stored_quantity_lines,
    constructor_work_lines,
    constructor_work_table_rows,
    constructor_workspace_views,
    execution_path_summary_rows,
    execution_step_title,
    format_timestamp_moscow,
    disposition_ru,
    handoff_status_ru,
    handoff_type_ru,
    human_decision_reason_text,
    recommendation_ru,
    operational_status_ru,
    post_decision_lines,
    professional_execution_state_ru,
    professional_status_ru,
    run_radio_label,
    short_run_id,
    stage_display_state_ru,
    stage_step_duration,
    status_icon,
    timeline_rows,
    tool_name_ru,
)
from agents.control_room.query_port import AgentControlRoomQueryPort
from agents.observability.contracts import OperationalStatus

logger = logging.getLogger(__name__)

SS_SELECTED_RUN = "control_room_selected_run_id"
FILTER_ALL = "Все"
CATALOG_LIMIT = 200
LIST_LIMIT = 50


def _ensure_observability_env() -> None:
    """Bind Page 53 to the same durable observability store the live launcher uses."""
    if str(os.environ.get(AGENT_OBSERVABILITY_DB_PATH_ENV) or "").strip():
        return
    try:
        path = resolve_observability_db_path()
    except ControlRoomConfigurationError:
        return
    os.environ[AGENT_OBSERVABILITY_DB_PATH_ENV] = str(Path(path).resolve())


def _build_query_port() -> AgentControlRoomQueryPort:
    """Fresh Query Port each call — no cache_resource (stale composition hides durable results)."""
    _ensure_observability_env()
    return build_agent_control_room_query_port()


def _safe_query_port() -> Optional[AgentControlRoomQueryPort]:
    try:
        return _build_query_port()
    except ControlRoomConfigurationError:
        st.error(
            "Хранилище наблюдаемости не настроено или недоступно. "
            "Состояние запусков не подтверждено."
        )
        return None
    except Exception:
        logger.exception("Control Room query port initialization failed")
        st.error("Не удалось загрузить данные Центра управления агентами.")
        return None


def _filter_value(raw: str) -> Optional[str]:
    if raw == FILTER_ALL:
        return None
    return raw


def _status_filter_value(label: str) -> Optional[str]:
    if label == FILTER_ALL:
        return None
    for ru_label, code in all_operational_status_options():
        if ru_label == label:
            return code
    return label


def _load_catalog(port: AgentControlRoomQueryPort) -> AgentRunListView:
    return port.list_runs(limit=CATALOG_LIMIT)


def _load_filtered_runs(
    port: AgentControlRoomQueryPort,
    *,
    agent_code: Optional[str],
    project_code: Optional[str],
    month_key: Optional[str],
    operational_status: Optional[str],
) -> AgentRunListView:
    kwargs: dict[str, Any] = {"limit": LIST_LIMIT}
    if agent_code is not None:
        kwargs["agent_code"] = agent_code
    if project_code is not None:
        kwargs["project_code"] = project_code
    if month_key is not None:
        kwargs["month_key"] = month_key
    if operational_status is not None:
        kwargs["operational_status"] = operational_status
    return port.list_runs(**kwargs)


def _load_snapshot(port: AgentControlRoomQueryPort, run_id: str) -> Optional[AgentRunSnapshot]:
    try:
        return port.get_run_snapshot(run_id)
    except ControlRoomRunNotFoundError:
        st.warning("Запуск не найден или уже недоступен.")
        st.session_state.pop(SS_SELECTED_RUN, None)
        return None
    except ControlRoomQueryBlockerError:
        st.error("Некорректный параметр запроса.")
        return None
    except ControlRoomStorageUnavailableError:
        st.error(
            "Хранилище наблюдаемости не настроено или недоступно. "
            "Состояние запусков не подтверждено."
        )
        return None
    except ControlRoomQueryError:
        logger.exception("Control Room query failed for run_id=%s", run_id)
        st.error("Не удалось загрузить данные Центра управления агентами.")
        return None
    except Exception:
        logger.exception("Unexpected Control Room snapshot failure for run_id=%s", run_id)
        st.error("Не удалось загрузить данные Центра управления агентами.")
        return None


def _render_filters(
    catalog: AgentRunListView,
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], bool]:
    agents, projects, months = catalog_filter_values(catalog.items)
    status_options = [FILTER_ALL] + [label for label, _code in all_operational_status_options()]

    c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1.0, 1.2, 0.6])
    with c1:
        agent_sel = st.selectbox("Агент", [FILTER_ALL, *agents], key="control_room_filter_agent")
    with c2:
        project_sel = st.selectbox("Проект", [FILTER_ALL, *projects], key="control_room_filter_project")
    with c3:
        month_sel = st.selectbox("Месяц", [FILTER_ALL, *months], key="control_room_filter_month")
    with c4:
        status_sel = st.selectbox("Статус", status_options, key="control_room_filter_status")
    with c5:
        st.markdown("<div style='height:1.55rem'></div>", unsafe_allow_html=True)
        refresh = st.button("Обновить", use_container_width=True, key="control_room_refresh")

    if not catalog.runs_complete:
        st.info(CATALOG_INCOMPLETE_FILTER_RU)

    return (
        _filter_value(agent_sel),
        _filter_value(project_sel),
        _filter_value(month_sel),
        _status_filter_value(status_sel),
        refresh,
    )


def _render_run_list(list_view: AgentRunListView) -> Optional[str]:
    if not list_view.runs_complete:
        st.info(RUNS_COMPLETE_FALSE_RU)

    if not list_view.items:
        if list_view.runs_complete:
            st.info(EMPTY_RUNS_RU)
        else:
            st.info(EMPTY_RUNS_INCOMPLETE_CATALOG_RU)
        st.caption("Запуски появляются после управляемого старта через Run Control.")
        return None

    labels = [run_radio_label(item) for item in list_view.items]
    run_ids = [item.run_id for item in list_view.items]
    current = st.session_state.get(SS_SELECTED_RUN)
    index = run_ids.index(current) if current in run_ids else 0

    selected_label = st.radio(
        "Доступные запуски",
        options=labels,
        index=index,
        key="control_room_run_radio",
    )
    selected_id = run_ids[labels.index(selected_label)]
    st.session_state[SS_SELECTED_RUN] = selected_id
    return selected_id


def _render_human_decision_block(snapshot: AgentRunSnapshot, step_index: int) -> None:
    path = snapshot.professional_execution_path
    if step_index >= len(path.steps):
        return
    step = path.steps[step_index]
    if step.step_kind is not ProfessionalExecutionStepKind.HUMAN_DECISION:
        return
    surface = step.human_decision
    if surface is None:
        return

    st.markdown(f"**{HUMAN_DECISION_HEADER_RU}**")
    if surface.wait.wait_ordinal is not None:
        st.write(f"**Ожидание:** № {surface.wait.wait_ordinal}")
    st.write(f"**Почему остановлена автономность:** {human_decision_reason_text(surface)}")

    if surface.request is not None and surface.request.allowed_decisions:
        labels = [decision_code_ru(code) for code in surface.request.allowed_decisions]
        st.write(f"**Допустимые решения:** {', '.join(labels)}")
        st.write(f"**Основания:** {len(surface.request.evidence_refs)} структурированных ссылок")
        if surface.request.evidence_refs:
            with st.expander("Идентификаторы оснований"):
                for ref in surface.request.evidence_refs:
                    st.code(ref)
    elif surface.request is not None:
        st.write("**Допустимые решения:** —")

    st.caption(AUTHORITY_NOT_MODELED_RU)

    if surface.decision is not None:
        st.write(f"**Решение:** {decision_code_ru(surface.decision.decision_code)}")
        st.write(
            f"**Решение отправил:** {surface.decision.actor_id} "
            f"({surface.decision.actor_type})"
        )
        st.write(f"**Время:** {format_timestamp_moscow(surface.decision.received_at)} МСК")

    post_lines = post_decision_lines(surface)
    if post_lines:
        st.markdown(f"**{POST_DECISION_HEADER_RU}**")
        for line in post_lines:
            st.write(f"• {line}")


def _render_execution_step_detail(snapshot: AgentRunSnapshot, step_index: int) -> None:
    step = snapshot.professional_execution_path.steps[step_index]
    st.markdown(f"**{execution_step_title(step)}**")
    st.write(f"**Состояние:** {professional_execution_state_ru(step.professional_state)}")
    st.write(f"**Начало:** {format_timestamp_moscow(step.started_at)} МСК")
    if step.completed_at is not None:
        st.write(f"**Окончание:** {format_timestamp_moscow(step.completed_at)} МСК")
    duration = stage_step_duration(step, read_at=snapshot.read_at)
    if duration != "—":
        st.write(f"**Длительность:** {duration}")
    if step.attempt_n > 1:
        st.write(f"**Попытка:** {step.attempt_n}")
    if step.resume_n > 0:
        st.write(f"**Эпизод возобновления:** {step.resume_n}")

    if step.tools:
        st.write("**Использованные инструменты:**")
        for tool in step.tools:
            st.write(f"• {tool_name_ru(tool.tool_name)}")

    if step.artifacts:
        st.write("**Созданные результаты:**")
        for artifact in step.artifacts:
            st.write(f"• {artifact_type_ru(artifact.artifact_type)}")
            st.caption(f"ID: …{artifact.artifact_id[-4:] if len(artifact.artifact_id) > 4 else artifact.artifact_id}")

    if step.step_kind is ProfessionalExecutionStepKind.HUMAN_DECISION:
        _render_human_decision_block(snapshot, step_index)

    with st.expander("Технические идентификаторы этапа"):
        st.code(step.step_id)
        if step.stage_id:
            st.code(step.stage_id)


def _load_constructor_professional(
    snapshot: AgentRunSnapshot,
    port: Optional[AgentControlRoomQueryPort],
) -> Optional[ConstructorProfessionalResultView]:
    if port is None or snapshot.run.agent_code != "MONTHLY_PLAN_CONSTRUCTOR":
        return None
    getter = getattr(port, "get_constructor_professional_result", None)
    if not callable(getter):
        return None
    try:
        return getter(snapshot.run.run_id)
    except Exception:
        return inconsistent_constructor_professional_result()


def _load_constructor_registry(
    snapshot: AgentRunSnapshot,
    port: Optional[AgentControlRoomQueryPort],
    **filters: Any,
) -> Optional[ConstructorDecisionRegistryView]:
    if port is None or snapshot.run.agent_code != "MONTHLY_PLAN_CONSTRUCTOR":
        return None
    getter = getattr(port, "get_constructor_decision_registry", None)
    if not callable(getter):
        return None
    bound_run_id = active_result_run_id(filters.pop("bound_run_id", None))
    target_run_id = bound_run_id or active_result_run_id(snapshot.run.run_id)
    if not target_run_id:
        return None
    try:
        return getter(target_run_id, **filters)
    except Exception as exc:
        # Never convert a professional-result read failure into fake «ещё не сформирован».
        logger.exception(
            "Constructor decision registry read failed for run_id=%s",
            target_run_id,
        )
        st.error(
            "Не удалось прочитать профессиональный результат Constructor "
            f"(run_id={target_run_id}): {exc}"
        )
        return empty_constructor_decision_registry(
            inconsistent_constructor_professional_result()
        )


def _render_constructor_employee(
    snapshot: AgentRunSnapshot,
    result: ConstructorProfessionalResultView,
    port: Optional[AgentControlRoomQueryPort] = None,
) -> None:
    if result.availability == ProfessionalResultAvailability.UNAVAILABLE:
        st.info(PROFESSIONAL_RESULT_UNAVAILABLE_RU)
        return
    if result.availability == ProfessionalResultAvailability.INCONSISTENT:
        st.error(PROFESSIONAL_RESULT_INCONSISTENT_RU)
        return

    handoff = snapshot.handoff
    handoff_absent = handoff.handoff_id is None and handoff.status is HandoffStatus.NOT_STARTED
    registry = _load_constructor_registry(snapshot, port)
    if (
        registry is not None
        and registry.availability == ProfessionalResultAvailability.AVAILABLE
        and registry.total_count > 0
    ):
        _render_constructor_registry(snapshot, result, registry, port)
        return

    st.markdown(f"## {CONSTRUCTOR_EMPLOYEE_TITLE_RU}")
    st.write(result.project_id)
    st.write(constructor_month_display(result.month))
    st.write(result.facility_id or "—")
    st.write(constructor_discipline_display(result.discipline))
    st.write(f"**Статус:** {professional_status_ru(result.professional_status)}")

    funnel = st.columns(len(constructor_funnel_steps(result)))
    for column, (label, value) in zip(funnel, constructor_funnel_steps(result)):
        column.markdown(f"**{label}**")
        column.markdown(f"## {value}")
    for warning in constructor_funnel_warnings(result):
        st.warning(warning)
    gap_line = constructor_detail_gap_line(result)
    if gap_line:
        st.info(gap_line)

    views = constructor_workspace_views(result)
    view_labels = [label for _view_id, label in views]
    selected_view_label = st.radio(
        "Разрез списка",
        options=view_labels,
        horizontal=True,
        key=f"constructor_work_view_{result.run_id}",
    )
    view_id = next(view_key for view_key, label in views if label == selected_view_label)
    visible = constructor_rows_for_view(result, view_id)

    table_column, inspector_column = st.columns([0.68, 0.32], gap="large")
    with table_column:
        st.markdown(f"### {CONSTRUCTOR_CANDIDATES_TITLE_RU}")
        if view_id == "already_planned":
            st.info(CONSTRUCTOR_ALREADY_PLANNED_GAP_RU)
        elif view_id == "data_gap":
            st.info(CONSTRUCTOR_MISSING_ROW_ARTIFACT_RU)
        elif visible:
            st.dataframe(
                pd.DataFrame(list(constructor_work_table_rows(visible))),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("В этом разрезе сохранённых позиций нет.")
    with inspector_column:
        _render_constructor_inspector(result, visible)

    st.markdown(f"### {CONSTRUCTOR_OUTCOME_TITLE_RU}")
    for line in constructor_package_summary_lines(result, handoff_absent=handoff_absent):
        st.write(line)
    if result.professional_status == "PROFESSIONAL_WORK_COMPLETED":
        st.markdown(f"**{CONSTRUCTOR_COMPLETED_LINE_RU}**")
    elif not handoff_absent:
        st.write(f"**Передача:** {handoff_status_ru(handoff.status.value)}")

    with st.expander(CONSTRUCTOR_EVIDENCE_TITLE_RU):
        _render_constructor_technical_evidence(snapshot, result)
        _render_service_run_card(snapshot)


def _render_constructor_registry(
    snapshot: AgentRunSnapshot,
    result: ConstructorProfessionalResultView,
    base: ConstructorDecisionRegistryView,
    port: Optional[AgentControlRoomQueryPort],
) -> None:
    _render_constructor_context_bar(snapshot, result, base)
    tiles = constructor_decision_summary_tiles(base)
    summary = st.columns(len(tiles))
    for column, (label, value) in zip(summary, tiles):
        column.markdown(f"**{label}**")
        column.markdown(f"## {value}")

    options = constructor_registry_filter_options(base)
    labels = [label for _key, label in options]
    selected_label = st.radio(
        "Разрез реестра",
        options=labels,
        horizontal=True,
        key=f"constructor_registry_filter_{result.run_id}",
    )
    filter_id = next(key for key, label in options if label == selected_label)
    query = constructor_registry_query(filter_id)
    search = st.text_input(
        "Поиск",
        placeholder="BOQ, наименование или система",
        key=f"constructor_registry_search_{result.run_id}",
    )
    system_options = ["Все", *base.known_systems]
    selected_system = st.selectbox(
        "Система",
        options=system_options,
        key=f"constructor_registry_system_{result.run_id}",
    )
    registry = base
    system_filter = None if selected_system == "Все" else selected_system
    if query or str(search or "").strip() or system_filter:
        loaded = _load_constructor_registry(
            snapshot,
            port,
            text=str(search or "").strip() or None,
            system=system_filter,
            **query,
        )
        if loaded is not None:
            registry = loaded

    records = registry.records
    table_column, inspector_column = st.columns([0.68, 0.32], gap="large")
    with table_column:
        st.markdown(f"### {CONSTRUCTOR_REGISTRY_TITLE_RU}")
        if records:
            st.dataframe(
                pd.DataFrame(list(constructor_decision_table_rows(records, result))),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("В этом разрезе сохранённых решений нет.")
    with inspector_column:
        _render_decision_inspector(result, records)

    st.markdown(f"### {CONSTRUCTOR_FINAL_PACKAGE_TITLE_RU}")
    for line in constructor_final_package_lines(base):
        st.write(line)

    with st.expander(CONSTRUCTOR_EVIDENCE_TITLE_RU):
        for outcome, count in base.outcome_counts:
            st.write(f"{outcome}: {count}")
        st.write(f"Run ID: {result.run_id}")
        st.write(f"Mission ID: {result.mission_id}")
        st.write(f"Candidate Package ID: {result.source_candidate_package_id or '—'}")
        st.write(f"Профессиональный статус: {result.professional_status or '—'}")
        completed = any(event.event_type == "RUN_COMPLETED" for event in snapshot.timeline_events)
        st.write(f"RUN_COMPLETED: {'зафиксирован' if completed else 'не зафиксирован'}")
        handoff = snapshot.handoff
        handoff_none = handoff.handoff_id is None and handoff.status is HandoffStatus.NOT_STARTED
        st.write(f"Передача: {'не выполнялась' if handoff_none else handoff_status_ru(handoff.status.value)}")


def _render_constructor_context_bar(
    snapshot: AgentRunSnapshot,
    result: ConstructorProfessionalResultView,
    registry: ConstructorDecisionRegistryView,
) -> None:
    fields = (
        ("Проект", constructor_project_short(result.project_id) or "—"),
        ("Месяц", constructor_month_display(result.month) or "—"),
        ("Титул / объект", result.facility_id or "—"),
        ("Дисциплина", constructor_discipline_display(result.discipline) or "—"),
        ("Система", constructor_context_system(registry)),
        ("Контур", "—"),
        ("Цифровой сотрудник", agent_role_ru(snapshot.run.agent_code)),
        ("Миссия", result.mission_id or "—"),
    )
    columns = st.columns(len(fields))
    for column, (label, value) in zip(columns, fields):
        column.markdown(f"**{label}**")
        column.markdown(str(value))


def _render_decision_inspector(
    result: ConstructorProfessionalResultView,
    records: tuple[ConstructorRowDecisionView, ...],
) -> None:
    st.markdown("### Выбранная позиция")
    if not records:
        st.caption("Позиция не выбрана.")
        return
    labels = [f"{item.boq_code} · {item.source_order}" for item in records]
    default_index = 0
    for index, item in enumerate(records):
        if constructor_row_awaits_human_review(item, result):
            default_index = index
            break
    selected_label = st.selectbox(
        "Позиция",
        options=labels,
        index=default_index,
        key=f"constructor_decision_{result.run_id}",
    )
    item = records[labels.index(selected_label)]
    row = constructor_decision_table_rows((item,), result)[0]
    st.markdown(f"#### {item.boq_code}")
    st.write(item.name or "—")
    st.write(f"**СИСТЕМА**  \n{item.system or '—'}")
    st.write(f"**ОСТАТОК**  \n{row['Остаток']}")
    st.write(f"**УЖЕ В ПЛАНЕ**  \n{row['Уже в плане']}")
    st.write(f"**ДОСТУПНО**  \n{row['Доступно']}")
    st.write(f"**РЕШЕНИЕ CONSTRUCTOR**  \n{constructor_row_outcome_label(item.outcome)}")
    st.write("**ПОЧЕМУ ПРИНЯТО ЭТО РЕШЕНИЕ**")
    st.write(item.reason_text or "—")
    st.write(f"**ТРЕБУЕТСЯ ЧЕЛОВЕК**  \n{row['Требуется человек']}")
    in_package = "Да" if item.candidate_created else "Нет"
    st.write(f"**В CANDIDATE PACKAGE**  \n{in_package}")
    if constructor_row_awaits_human_review(item, result) and constructor_hitl_actions_visible(
        result.professional_status
    ):
        st.write(CONSTRUCTOR_HITL_QUESTION_RU)
        st.button("✓ ОК", disabled=True, key=f"constructor_ok_{item.source_identity}")
        st.button("✕ НЕ ОК", disabled=True, key=f"constructor_not_ok_{item.source_identity}")
        st.button("НУЖНЫ ДАННЫЕ", disabled=True, key=f"constructor_need_{item.source_identity}")
        st.caption(CONSTRUCTOR_HITL_WRITE_UNAVAILABLE_RU)


def _render_constructor_inspector(
    result: ConstructorProfessionalResultView,
    visible: tuple,
) -> None:
    st.markdown("### Выбранная позиция")
    if not visible:
        st.caption("Позиция не выбрана.")
        return
    labels = [item.boq_code for item in visible]
    selected_code = st.selectbox(
        "Позиция",
        options=labels,
        key=f"constructor_position_{result.run_id}_{'-'.join(labels)}",
    )
    item = next(candidate for candidate in visible if candidate.boq_code == selected_code)
    quantities = constructor_work_table_rows((item,))[0]
    st.markdown(f"#### {item.boq_code}")
    st.write(item.name or "—")
    st.write(f"**ОСТАТОК**  \n{quantities['Остаток']}")
    st.write(f"**УЖЕ В ПЛАНЕ**  \n{quantities['Уже в плане']}")
    st.write(f"**ДОСТУПНО**  \n{quantities['Доступно']}")
    st.write(f"**НОРМА ТРУДА**  \n{quantities['Норма труда']}")
    st.write("**ПОЧЕМУ ОСТАНОВИЛСЯ CONSTRUCTOR**")
    st.write(constructor_stop_reason(item))
    st.markdown(f"**{CONSTRUCTOR_AGENT_RECOMMENDATION_TITLE_RU}**")
    st.write(recommendation_ru(item.recommendation))
    st.markdown(f"**{CONSTRUCTOR_HUMAN_TITLE_RU}**")
    if constructor_hitl_actions_visible(result.professional_status):
        st.write(CONSTRUCTOR_HITL_QUESTION_RU)
        st.button("✓ ОК", disabled=True, key=f"constructor_ok_{item.candidate_id}")
        st.button("✕ НЕ ОК", disabled=True, key=f"constructor_not_ok_{item.candidate_id}")
        st.button("НУЖНЫ ДАННЫЕ", disabled=True, key=f"constructor_need_{item.candidate_id}")
        st.caption(CONSTRUCTOR_HITL_WRITE_UNAVAILABLE_RU)
    else:
        st.write(constructor_saved_decision_label(item.human_review_decision))
        st.write(f"Итог: {disposition_ru(item.final_disposition)}")


def _render_constructor_technical_evidence(
    snapshot: AgentRunSnapshot,
    result: ConstructorProfessionalResultView,
) -> None:
    st.write(CONSTRUCTOR_MISSING_ROW_ARTIFACT_RU)
    for line in constructor_processing_scale_lines(result):
        st.write(line)
    if result.mission_scope_source:
        st.caption(f"Источник снимка scope: {result.mission_scope_source}")
    for line in constructor_stored_quantity_lines(result):
        st.write(line)
    work_lines = constructor_work_lines(result)
    if work_lines:
        st.markdown(f"**{CONSTRUCTOR_WORK_TITLE_RU}**")
        for line in work_lines:
            st.write(line)
    labels = constructor_path_labels(result)
    if labels:
        st.markdown(f"**{CONSTRUCTOR_PATH_TITLE_RU}**")
        st.write(" → ".join(labels))
    st.write(f"Run ID: {result.run_id}")
    st.write(f"Mission ID: {result.mission_id}")
    st.write(f"Candidate Package ID: {result.source_candidate_package_id or '—'}")
    st.write(f"Reviewed Package ID: {result.reviewed_package_id or '—'}")
    st.write(f"Human Confirm ID: {result.confirm_event_id or '—'}")
    st.write(f"Профессиональный статус: {result.professional_status or '—'}")
    completed = any(event.event_type == "RUN_COMPLETED" for event in snapshot.timeline_events)
    st.write(f"RUN_COMPLETED: {'зафиксирован' if completed else 'не зафиксирован'}")
    handoff = snapshot.handoff
    handoff_none = handoff.handoff_id is None and handoff.status is HandoffStatus.NOT_STARTED
    st.write(f"Передача: {'не выполнялась' if handoff_none else handoff_status_ru(handoff.status.value)}")


def _render_selected_run(
    snapshot: AgentRunSnapshot,
    port: Optional[AgentControlRoomQueryPort] = None,
) -> None:
    professional = _load_constructor_professional(snapshot, port)
    if (
        professional is not None
        and professional.availability == ProfessionalResultAvailability.AVAILABLE
    ):
        _render_constructor_employee(snapshot, professional, port)
        return
    if professional is not None:
        _render_constructor_employee(snapshot, professional, port)
    _render_service_run_card(snapshot)


def _render_service_run_card(snapshot: AgentRunSnapshot) -> None:
    run = snapshot.run
    st.subheader("Выбранный запуск")

    if run.operational_status == OperationalStatus.WAITING_FOR_HUMAN.value:
        st.warning(WAITING_FOR_HUMAN_RU)

    icon = status_icon(run.operational_status)
    st.markdown(f"**Статус:** {icon} {operational_status_ru(run.operational_status)}")
    st.write(f"**Цифровой сотрудник:** {run.agent_code}")
    st.write(f"**Проект:** {run.project_code}")
    st.write(f"**Месяц:** {run.month_key}")
    st.write(f"**Миссия:** {run.mission_id}")
    st.write(f"**Запрошен:** {format_timestamp_moscow(run.requested_at)} МСК")
    if run.started_at is not None:
        st.write(f"**Начат:** {format_timestamp_moscow(run.started_at)} МСК")
    st.write(f"**Обновлён:** {format_timestamp_moscow(run.updated_at)} МСК")
    if run.completed_at is not None:
        st.write(f"**Завершён:** {format_timestamp_moscow(run.completed_at)} МСК")
    st.caption(f"Версия состояния: {run.projection_version}")

    with st.expander("Технические идентификаторы"):
        st.code(run.run_id)
        if run.orchestration_run_id:
            st.code(f"orchestration: {run.orchestration_run_id}")

    handoff = snapshot.handoff
    if run.operational_status == OperationalStatus.COMPLETED.value:
        if handoff.status.value != "NOT_STARTED":
            st.write(f"**Передача:** {handoff_status_ru(handoff.status.value)}")

    path_warning = derivation_execution_path_warning(snapshot.professional_execution_path.derivation_state)
    if path_warning:
        st.warning(path_warning)

    stage_warning = derivation_stage_warning(snapshot.stage.derivation_state)
    if stage_warning:
        st.warning(stage_warning)

    if not snapshot.professional_execution_path.history_complete:
        st.info(EXECUTION_PATH_INCOMPLETE_RU)
    elif not snapshot.events_complete:
        st.info(EVENTS_COMPLETE_FALSE_RU)

    st.markdown("### Профессиональный маршрут выполнения")
    exec_path = snapshot.professional_execution_path
    if exec_path.steps:
        summary_df = pd.DataFrame(list(execution_path_summary_rows(exec_path, read_at=snapshot.read_at)))
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        for index in range(len(exec_path.steps)):
            step = exec_path.steps[index]
            label = f"{index + 1}. {execution_step_title(step)}"
            with st.expander(label, expanded=step.step_kind is ProfessionalExecutionStepKind.HUMAN_DECISION):
                _render_execution_step_detail(snapshot, index)
    else:
        st.caption("В доступном окне событий профессиональный маршрут не зафиксирован.")

    _render_digital_organization(snapshot)

    current = snapshot.stage.current_stage
    if snapshot.stage.derivation_state is DerivationState.OK and current is not None:
        st.markdown("**Текущая стадия (сводка)**")
        state = current.display_state.value
        st.write(f"{current.stage_id} — {stage_display_state_ru(state)}")
        st.caption(f"Начало: {format_timestamp_moscow(current.started_at)} МСК")

    st.markdown("### Доступное окно событий")
    st.caption("Вторичная служебная лента — не полная история.")
    if snapshot.timeline_events:
        st.dataframe(
            pd.DataFrame(list(timeline_rows(snapshot.timeline_events))),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("В доступном окне событий записей нет.")


def _render_digital_organization(snapshot: AgentRunSnapshot) -> None:
    org = snapshot.digital_organization
    st.markdown(f"### {DIGITAL_ORG_SECTION_TITLE_RU}")
    st.caption(DIGITAL_ORG_SECTION_SUBTITLE_RU)

    if not org.history_complete:
        st.info(DIGITAL_ORG_HISTORY_INCOMPLETE_RU)

    if org.derivation_state is DerivationState.INCONSISTENT:
        st.warning(HANDOFF_INCONSISTENT_RU)

    with st.container(border=True):
        st.markdown(f"**{agent_role_ru(org.source_agent_code)}**")
        completion = digital_org_source_completion_line(org)
        if completion:
            st.write(f"✓ {completion}")
        else:
            st.write(
                f"**Статус источника:** {status_icon(org.source_operational_status)} "
                f"{operational_status_ru(org.source_operational_status)}"
            )
        if org.source_completed_at is not None:
            st.caption(f"Завершён: {format_timestamp_moscow(org.source_completed_at)} МСК")

    handoff = org.handoff
    if handoff is None or handoff.status is HandoffStatus.NOT_STARTED:
        if handoff is None and not org.history_complete:
            st.info(HANDOFF_NOT_CONFIRMED_INCOMPLETE_RU)
        elif handoff is None:
            st.info(HANDOFF_NOT_OBSERVED_RU)
        else:
            st.info(NO_NEXT_TRANSFER_RU)
        return

    st.markdown("↓")

    if handoff.artifact_type or handoff.artifact_id:
        with st.container(border=True):
            if handoff.artifact_type:
                st.markdown(f"**{artifact_type_ru(handoff.artifact_type)}**")
            else:
                st.markdown("**Бизнес-артефакт**")
            if handoff.artifact_id:
                short_id = (
                    f"…{handoff.artifact_id[-8:]}"
                    if len(handoff.artifact_id) > 8
                    else handoff.artifact_id
                )
                st.caption(f"ID: {short_id}")

        st.markdown("↓")

    transfer_ok = handoff.status is HandoffStatus.PERSISTED
    transfer_failed = handoff.status is HandoffStatus.PERSIST_FAILED
    with st.container(border=True):
        st.markdown("**Передача**")
        for line in digital_org_handoff_status_lines(handoff.status):
            if transfer_failed:
                st.error(line)
            elif transfer_ok:
                st.write(f"✓ {line}")
            else:
                st.write(line)
        if handoff.derivation_state is DerivationState.INCOMPLETE and (
            handoff.handoff_type is None or handoff.target_role_code is None
        ):
            st.info(HANDOFF_LEGACY_INCOMPLETE_RU)

    if handoff.target_role_code and not transfer_failed:
        st.markdown("↓")
    elif handoff.target_role_code and transfer_failed:
        st.caption("Предназначенная роль известна, но долговременная передача не подтверждена.")

    if handoff.target_role_code:
        with st.container(border=True):
            st.markdown(f"**{agent_role_ru(handoff.target_role_code)}**")
            st.caption(TARGET_ROLE_LABEL_RU)
            if transfer_ok or handoff.status is HandoffStatus.CREATED:
                for line in digital_org_receiver_honesty_lines():
                    st.write(f"• {line}")
            elif transfer_failed:
                st.write(f"• {digital_org_receiver_honesty_lines()[0]}")
    elif handoff.derivation_state is DerivationState.INCOMPLETE:
        st.info(HANDOFF_LEGACY_INCOMPLETE_RU)

    with st.expander("Технические идентификаторы передачи"):
        if handoff.handoff_id:
            st.code(handoff.handoff_id)
        if handoff.handoff_type:
            st.write(f"Тип: {handoff_type_ru(handoff.handoff_type)}")
            st.code(handoff.handoff_type)
        st.code(org.source_run_id)
        if handoff.target_role_code:
            st.code(handoff.target_role_code)
        if handoff.artifact_type:
            st.write(f"artifact_type: {handoff.artifact_type}")
        if handoff.artifact_id:
            st.code(handoff.artifact_id)
        if handoff.created_at is not None:
            st.write(f"created_at: {format_timestamp_moscow(handoff.created_at)} МСК")
        if handoff.persisted_at is not None:
            st.write(f"persisted_at: {format_timestamp_moscow(handoff.persisted_at)} МСК")
        if handoff.failed_at is not None:
            st.write(f"failed_at: {format_timestamp_moscow(handoff.failed_at)} МСК")


def _render_global_command_bar(catalog: WorkContextCatalog) -> None:
    st.markdown("## Быстрая команда")
    st.caption("Текст и голос только формируют черновик. Сами по себе они ничего не исполняют.")
    if _command_mode() == "voice":
        _render_global_voice()
        return
    if "dynamis_global_text" not in st.session_state:
        st.session_state["dynamis_global_text"] = ""
    command = st.text_area(
        "Команда",
        placeholder="Напишите или продиктуйте задачу…",
        key="dynamis_global_text",
    )
    if st.button("РАСПОЗНАТЬ КОМАНДУ", key="dynamis_parse_global"):
        st.session_state["dynamis_pending_command"] = parse_global_command(
            str(command or ""),
            horizon_year=_horizon_year(st.session_state.get("dynamis_working_context")),
        )
    pending = st.session_state.get("dynamis_pending_command")
    if isinstance(pending, GlobalCommandDraft):
        _render_command_preview(pending, catalog)


def _command_mode() -> str:
    options = ["ТЕКСТОМ", "🎤 ГОЛОСОМ"]
    control = getattr(st, "segmented_control", None)
    if callable(control):
        if st.session_state.get("dynamis_global_channel") not in options:
            st.session_state["dynamis_global_channel"] = "ТЕКСТОМ"
        chosen = control(
            "Режим команды",
            options,
            key="dynamis_global_channel",
            label_visibility="collapsed",
        )
        return "voice" if chosen and "ГОЛОС" in str(chosen) else "text"
    mode = st.session_state.get("dynamis_command_mode", "text")
    text_col, voice_col = st.columns(2)
    if text_col.button(
        "ТЕКСТОМ",
        key="dynamis_mode_text",
        type="primary" if mode == "text" else "secondary",
    ):
        st.session_state["dynamis_command_mode"] = "text"
        mode = "text"
    if voice_col.button(
        "🎤 ГОЛОСОМ",
        key="dynamis_mode_voice",
        type="primary" if mode == "voice" else "secondary",
    ):
        st.session_state["dynamis_command_mode"] = "voice"
        mode = "voice"
    return mode


def _render_global_voice() -> None:
    audio_input = getattr(st, "audio_input", None)
    if not callable(audio_input):
        st.info(GLOBAL_VOICE_RECORDED_RU)
        return
    audio = audio_input("Голосовая команда", key="dynamis_global_voice")
    if audio is not None:
        st.info(GLOBAL_VOICE_RECORDED_RU)


def _render_command_preview(draft: GlobalCommandDraft, catalog: WorkContextCatalog) -> None:
    st.markdown("## Команда распознана")
    for line in global_command_preview_lines(draft):
        st.write(line)
    if draft.unresolved_fields:
        st.warning("Не удалось определить: " + ", ".join(draft.unresolved_fields))
    if draft.kind == "context":
        if st.button("ОК · ПРИМЕНИТЬ", key="dynamis_apply_command", type="primary"):
            _apply_pending_context(draft, catalog)
        if st.button("ИЗМЕНИТЬ", key="dynamis_edit_command"):
            st.session_state.pop("dynamis_pending_command", None)
        if st.button("ОТМЕНА", key="dynamis_cancel_command"):
            st.session_state.pop("dynamis_pending_command", None)
            st.session_state["dynamis_global_text"] = ""
        return
    st.button("ПОДТВЕРДИТЬ", key="dynamis_confirm_work_command")
    st.info(COMMAND_EXECUTION_REQUIRED_RU)
    if st.button("ИЗМЕНИТЬ", key="dynamis_edit_work_command"):
        st.session_state.pop("dynamis_pending_command", None)
    if st.button("ОТМЕНА", key="dynamis_cancel_work_command"):
        st.session_state.pop("dynamis_pending_command", None)


def _apply_pending_context(draft: GlobalCommandDraft, catalog: WorkContextCatalog) -> None:
    current = st.session_state.get("dynamis_working_context")
    if not isinstance(current, WorkingContext):
        current = empty_working_context()
    alignment = align_working_context(apply_global_command(current, draft), catalog)
    updated = alignment.context
    missing_systems = tuple(item for item in draft.included_systems if item not in updated.systems)
    st.session_state["dynamis_unmatched_systems"] = missing_systems
    st.session_state["dynamis_context_messages"] = alignment.messages
    st.session_state["dynamis_working_context"] = updated
    st.session_state["dynamis_mission_draft"] = mission_from_context(updated, draft.source_text)
    st.session_state["dynamis_assignment_text"] = updated.intent or ""
    _write_context_fields(updated)
    st.session_state.pop("dynamis_pending_command", None)


_UNSET = "Не выбрано"
_ALL_QUEUES = "Все очереди"
_ALL_DISCIPLINES = "Все дисциплины"
_ALL_TITLES = "Все титулы"
_ALL_SYSTEMS = "Все системы"
_ALL_PACKAGES = "Все пакеты"
_RUNNING_STATUSES = {"REQUESTED", "AUTHORIZING", "STARTING", "RUNNING", "RETRYING"}
_WAITING_STATUSES = {"WAITING_FOR_HUMAN", "WAITING_FOR_HUMAN_REVIEW"}
_FAILED_STATUSES = {"FAILED", "ABORTED", "AUTHORIZATION_DENIED"}
_COMPLETED_STATUSES = {"COMPLETED", "PROFESSIONAL_WORK_COMPLETED", "REVIEWED_PACKAGE_READY"}


def _write_context_fields(context: WorkingContext) -> None:
    st.session_state["dynamis_field_project"] = context.project or _UNSET
    st.session_state["dynamis_field_month"] = context.planning_month or _UNSET
    st.session_state["dynamis_field_queue"] = context.queue or _ALL_QUEUES
    st.session_state["dynamis_field_titles"] = list(context.titles)
    st.session_state["dynamis_field_discipline"] = context.discipline or _ALL_DISCIPLINES
    st.session_state["dynamis_field_systems"] = list(context.systems)
    st.session_state["dynamis_field_packages"] = [context.packages] if context.packages else []
    st.session_state["dynamis_field_contour"] = contour_title(context.contour_code)
    st.session_state["dynamis_field_employee"] = employee_title(context.agent_code)


def _single_choice(
    owner: Any,
    label: str,
    options: tuple[str, ...],
    current: Optional[str],
    key: str,
    *,
    empty_label: str = _UNSET,
) -> Optional[str]:
    if not options:
        owner.selectbox(label, ["—"], disabled=True, key=f"{key}_unavailable")
        return None
    allowed = [empty_label, *options]
    if key not in st.session_state or st.session_state.get(key) not in allowed:
        st.session_state[key] = current if current in options else empty_label
    chosen = owner.selectbox(label, allowed, key=key)
    if chosen in (None, "", empty_label, _UNSET, "—"):
        return None
    return str(chosen)


def _multi_choice(
    owner: Any,
    label: str,
    options: tuple[str, ...],
    current: tuple[str, ...],
    key: str,
    *,
    placeholder: str,
) -> tuple[str, ...]:
    if not options:
        owner.selectbox(label, ["—"], disabled=True, key=f"{key}_unavailable")
        return ()
    selected = [item for item in current if item in options]
    stored = st.session_state.get(key)
    if not isinstance(stored, list) or any(item not in options for item in stored):
        st.session_state[key] = selected
    chosen = owner.multiselect(label, list(options), key=key, placeholder=placeholder)
    if not isinstance(chosen, (list, tuple)):
        return ()
    return tuple(str(item) for item in chosen if str(item) in options)


def _horizon_year(context: object) -> Optional[str]:
    if not isinstance(context, WorkingContext) or not context.planning_month:
        return None
    parts = context.planning_month.split()
    if len(parts) == 2 and parts[1].isdigit():
        return parts[1]
    return None


def _render_working_context(catalog: WorkContextCatalog) -> None:
    st.markdown("## Рабочий контекст")
    context = st.session_state.get("dynamis_working_context")
    if not isinstance(context, WorkingContext):
        context = empty_working_context()
        st.session_state["dynamis_working_context"] = context
    choices = selector_options(
        catalog,
        project=context.project,
        queue=context.queue,
        titles=context.titles,
        discipline=context.discipline,
    )
    first = st.columns(4)
    project = _single_choice(first[0], "Проект", choices.projects, context.project, "dynamis_field_project")
    month = _single_choice(first[1], "Месяц", choices.months, context.planning_month, "dynamis_field_month")
    queue = _single_choice(
        first[2], "Очередь", choices.queues, context.queue, "dynamis_field_queue", empty_label=_ALL_QUEUES
    )
    titles = _multi_choice(
        first[3], "Титулы", choices.titles, context.titles, "dynamis_field_titles", placeholder=_ALL_TITLES
    )
    second = st.columns(3)
    discipline = _single_choice(
        second[0],
        "Дисциплина",
        choices.disciplines,
        context.discipline,
        "dynamis_field_discipline",
        empty_label=_ALL_DISCIPLINES,
    )
    systems = _multi_choice(
        second[1], "Системы", choices.systems, context.systems, "dynamis_field_systems", placeholder=_ALL_SYSTEMS
    )
    packages = _multi_choice(
        second[2],
        "Пакеты",
        choices.packages,
        (context.packages,) if context.packages else (),
        "dynamis_field_packages",
        placeholder=_ALL_PACKAGES,
    )
    for message, options in (
        (PROJECTS_UNAVAILABLE_RU, choices.projects),
        (QUEUES_UNAVAILABLE_RU, choices.queues),
        (TITLES_UNAVAILABLE_RU, choices.titles),
        (DISCIPLINES_UNAVAILABLE_RU, choices.disciplines),
        (SYSTEMS_UNAVAILABLE_RU, choices.systems),
        (PACKAGES_UNAVAILABLE_RU, choices.packages),
    ):
        if not options:
            st.caption(message)
    unmatched = st.session_state.get("dynamis_unmatched_systems") or ()
    if unmatched:
        st.caption("В источнике месячного плана нет систем: " + ", ".join(unmatched) + ".")
    messages = tuple(st.session_state.get("dynamis_context_messages") or ())
    if queue:
        messages = tuple(item for item in messages if "необходимо определить очередь" not in item)
        st.session_state["dynamis_context_messages"] = messages
    for message in messages:
        st.warning(message)
    updated = WorkingContext(
        project=project if choices.projects else context.project,
        planning_month=month if choices.months else context.planning_month,
        queue=queue if choices.queues else context.queue,
        titles=titles if choices.titles else context.titles,
        discipline=discipline if choices.disciplines else context.discipline,
        systems=systems if choices.systems else context.systems,
        packages=(
            ", ".join(packages) if packages else None
        ) if choices.packages else context.packages,
        agent_code=context.agent_code or CONSTRUCTOR_AGENT_CODE,
        excluded_scope_rule=context.excluded_scope_rule,
        intent=context.intent,
        contour_code=context.contour_code,
    )
    st.session_state["dynamis_working_context"] = updated
    if any((updated.project, updated.planning_month, updated.queue, updated.titles, updated.discipline, updated.systems, updated.intent)):
        st.session_state["dynamis_mission_draft"] = mission_from_context(
            updated,
            getattr(st.session_state.get("dynamis_mission_draft"), "source_text", ""),
        )


def _required_choice(owner: Any, label: str, options: tuple[str, ...], current: Optional[str], key: str) -> Optional[str]:
    if not options:
        owner.selectbox(label, ["—"], disabled=True, key=f"{key}_unavailable")
        return None
    if key not in st.session_state or st.session_state.get(key) not in options:
        st.session_state[key] = current if current in options else options[0]
    chosen = owner.selectbox(label, list(options), key=key)
    if chosen in options:
        return str(chosen)
    return options[0]


def _render_assignee_picker() -> None:
    st.markdown("## Кому поручить")
    context = st.session_state.get("dynamis_working_context")
    if not isinstance(context, WorkingContext):
        context = empty_working_context()
    st.markdown("### Профессиональный контур")
    contour_labels = tuple(contour_option_label(item) for item in CONTOURS)
    current_contour = contour_by_code(context.contour_code)
    current_label = contour_option_label(current_contour) if current_contour is not None else None
    chosen_label = _required_choice(st, "Контур", contour_labels, current_label, "dynamis_field_contour")
    contour = contour_from_option_label(chosen_label)
    st.markdown("### Цифровой сотрудник")
    roster = employees_of(contour.code if contour is not None else None)
    employee_labels = tuple(employee_option_label(item) for item in roster)
    current_employee = employee_by_code(context.agent_code)
    current_employee_label = (
        employee_option_label(current_employee)
        if current_employee is not None and current_employee in roster
        else None
    )
    chosen_employee = _required_choice(
        st,
        "Цифровой сотрудник",
        employee_labels,
        current_employee_label,
        "dynamis_field_employee",
    )
    employee = employee_from_option_label(
        chosen_employee,
        contour.code if contour is not None else None,
    )
    st.session_state["dynamis_working_context"] = WorkingContext(
        project=context.project,
        planning_month=context.planning_month,
        queue=context.queue,
        titles=context.titles,
        discipline=context.discipline,
        systems=context.systems,
        packages=context.packages,
        agent_code=employee.code if employee is not None else None,
        excluded_scope_rule=context.excluded_scope_rule,
        intent=context.intent,
        contour_code=contour.code if contour is not None else context.contour_code,
    )


def _render_assignment() -> None:
    st.markdown("## Поручение")
    context = st.session_state.get("dynamis_working_context")
    if not isinstance(context, WorkingContext):
        context = empty_working_context()
    if "dynamis_assignment_text" not in st.session_state:
        st.session_state["dynamis_assignment_text"] = context.intent or ""
    text = st.text_area(
        "Текст поручения",
        placeholder=(
            "Сформировать кандидатный состав месячного плана "
            "по выбранному производственному фронту."
        ),
        key="dynamis_assignment_text",
    )
    intent = str(text or "").strip() or None
    updated = WorkingContext(
        project=context.project,
        planning_month=context.planning_month,
        queue=context.queue,
        titles=context.titles,
        discipline=context.discipline,
        systems=context.systems,
        packages=context.packages,
        agent_code=context.agent_code,
        excluded_scope_rule=context.excluded_scope_rule,
        intent=intent,
        contour_code=context.contour_code,
    )
    st.session_state["dynamis_working_context"] = updated
    if intent:
        st.session_state["dynamis_mission_draft"] = mission_from_context(
            updated,
            getattr(st.session_state.get("dynamis_mission_draft"), "source_text", ""),
        )
    if updated.excluded_scope_rule:
        st.caption(updated.excluded_scope_rule)


def _catalog_project_code(catalog: WorkContextCatalog, project_label: str) -> str:
    codes = {
        item.project_code
        for item in catalog.facts
        if item.project_label == project_label and item.project_code
    }
    if len(codes) == 1:
        return next(iter(codes))
    return ""


def _stored_planning_month_key(display: str) -> str:
    return " ".join(str(display or "").split()).replace(" ", "-")


def _find_usable_professional_for_context(
    catalog: WorkContextCatalog,
    context: WorkingContext,
    port: Optional[AgentControlRoomQueryPort],
) -> Optional[RecoveredMission]:
    if port is None:
        return None
    project_code = _catalog_project_code(catalog, str(context.project or ""))
    month_key = _stored_planning_month_key(str(context.planning_month or ""))
    if not project_code or not month_key:
        return None
    try:
        return find_usable_professional_run(
            port,
            project_code=project_code,
            month_key=month_key,
            queue=str(context.queue or "").strip() or None,
        )
    except Exception:
        logger.exception("Usable professional run lookup failed")
        return None


def _monthly_workspace_key(context: WorkingContext) -> str:
    """Identity for an existing monthly analysis — ignores Title/Discipline slice."""
    payload = "|".join(
        (
            str(context.agent_code or CONSTRUCTOR_AGENT_CODE),
            str(context.project or ""),
            str(context.planning_month or ""),
            str(context.queue or ""),
            "monthly-workspace",
        )
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"hs-month-{digest}"


def _bind_usable_run_ids(mission: RecoveredMission, context: WorkingContext) -> None:
    """Attach existing monthly run without overwriting the user's Work Context slice."""
    st.session_state["dynamis_active_run_id"] = mission.run_id
    st.session_state["dynamis_active_mission_id"] = mission.mission_id
    st.session_state["dynamis_launch_status"] = (
        mission.lifecycle_status or mission.operational_status
    )
    st.session_state["dynamis_execution_lifecycle"] = mission.lifecycle_status
    st.session_state["dynamis_launch_failure"] = ""
    st.session_state["dynamis_recovery_resolved"] = True
    st.session_state["dynamis_recovery_choices"] = ()
    monthly_key = _monthly_workspace_key(context)
    st.session_state["dynamis_launch_key"] = monthly_key
    st.session_state["dynamis_launched_mission_identity"] = monthly_key


def _clear_active_run_binding() -> None:
    st.session_state.pop("dynamis_active_run_id", None)
    st.session_state.pop("dynamis_active_mission_id", None)
    st.session_state.pop("dynamis_launch_key", None)
    st.session_state.pop("dynamis_launched_mission_identity", None)
    st.session_state.pop("dynamis_launch_status", None)
    st.session_state.pop("dynamis_execution_lifecycle", None)


def _ensure_existing_monthly_workspace(
    catalog: WorkContextCatalog,
    port: Optional[AgentControlRoomQueryPort],
) -> None:
    """Bind Project+Month(+Queue) usable run; unbind when month has no usable analysis."""
    context = st.session_state.get("dynamis_working_context")
    if not isinstance(context, WorkingContext):
        return
    if not str(context.project or "").strip() or not str(context.planning_month or "").strip():
        return
    project_code = _catalog_project_code(catalog, str(context.project or ""))
    month_key = _stored_planning_month_key(str(context.planning_month or ""))
    # Without authoritative Project+Month codes, keep any recovered binding as-is.
    if not project_code or not month_key:
        return
    usable = _find_usable_professional_for_context(catalog, context, port)
    if usable is not None:
        active = active_result_run_id(st.session_state.get("dynamis_active_run_id"))
        if active != usable.run_id:
            _bind_usable_run_ids(usable, context)
        else:
            # Keep monthly identity aligned so Title/Discipline changes stay slices.
            monthly_key = _monthly_workspace_key(context)
            st.session_state["dynamis_launch_key"] = monthly_key
            st.session_state["dynamis_launched_mission_identity"] = monthly_key
        return
    active = active_result_run_id(st.session_state.get("dynamis_active_run_id"))
    if not active or port is None:
        return
    # Confirmed: this Project+Month(+Queue) has no usable analysis — free ЗАПУСТИТЬ.
    _clear_active_run_binding()


def _work_context_out_of_package_scope(
    registry: ConstructorDecisionRegistryView,
    context: Optional[WorkingContext],
) -> bool:
    if context is None:
        return False
    has_slice = bool(
        context.titles
        or str(context.discipline or "").strip()
        or context.systems
        or str(context.packages or "").strip()
    )
    if not has_slice:
        return False
    if not registry.records:
        return False
    scoped = filter_records_by_work_context(registry.records, context)
    return len(scoped) == 0


def _render_existing_monthly_workspace_panel(usable: RecoveredMission) -> None:
    st.markdown("## Месячный анализ сформирован")
    st.info(EXISTING_MONTHLY_ANALYSIS_RU)
    st.write(f"**Статус:** {EXISTING_MONTHLY_WORK_ACTION_RU}")
    st.write(f"**Run ID:** {usable.run_id}")
    st.caption(WORK_CONTEXT_SLICE_RU)


def _render_mission_draft(catalog: WorkContextCatalog) -> None:
    context = st.session_state.get("dynamis_working_context")
    if not isinstance(context, WorkingContext):
        st.markdown("## Задача распознана")
        st.warning("Чтобы запустить задачу, не хватает: рабочий контекст.")
        st.button("ЗАПУСТИТЬ", key="dynamis_launch_mission", disabled=True)
        return
    for message in st.session_state.get("dynamis_context_messages") or ():
        st.warning(message)
    port = _safe_query_port()
    usable = _find_usable_professional_for_context(catalog, context, port)
    if usable is not None:
        _bind_usable_run_ids(usable, context)
        _render_existing_monthly_workspace_panel(usable)
        return
    st.markdown("## Задача распознана")
    gaps = mission_gaps(context)
    if gaps:
        st.warning("Чтобы запустить задачу, не хватает: " + ", ".join(gaps) + ".")
        st.button("ЗАПУСТИТЬ", key="dynamis_launch_mission", disabled=True)
        if st.button("ИЗМЕНИТЬ", key="dynamis_edit_mission"):
            st.info("Измените рабочий контекст или поручение. Запуск не выполнен.")
        return
    for line in mission_preview_lines(context):
        st.write(line)
    key = mission_idempotency_key(context)
    launched = (
        st.session_state.get("dynamis_launch_key") == key
        and bool(active_result_run_id(st.session_state.get("dynamis_active_run_id")))
    )
    inflight = st.session_state.get("dynamis_launch_inflight") == key
    if launched:
        st.info("Задача запущена")
        st.write(f"Цифровой сотрудник: {employee_title(context.agent_code)}")
        st.write(f"Статус: {launch_status_label(str(st.session_state.get('dynamis_launch_status') or ''))}")
    clicked = st.button("ЗАПУСТИТЬ", key="dynamis_launch_mission", disabled=launched or inflight, type="primary")
    if st.button("ИЗМЕНИТЬ", key="dynamis_edit_mission"):
        st.info("Измените рабочий контекст или поручение. Запуск не выполнен.")
    if not clicked or launched or inflight:
        return
    st.session_state["dynamis_launch_inflight"] = key
    try:
        result = launch_monthly_plan_mission(context, catalog, query_port=port)
    except MissionCommandError as exc:
        st.session_state["dynamis_launch_inflight"] = None
        st.session_state["dynamis_launch_failure"] = exc.message
        st.error("Не удалось подтвердить запуск задачи.")
        return
    confirmed_run = active_result_run_id(getattr(result, "run_id", None))
    if not confirmed_run:
        st.session_state["dynamis_launch_inflight"] = None
        st.session_state["dynamis_launch_failure"] = "Запуск не вернул run_id."
        st.error("Не удалось подтвердить запуск задачи.")
        return
    if bool(getattr(result, "reused_existing", False)):
        st.session_state["dynamis_launch_inflight"] = None
        st.session_state["dynamis_launch_failure"] = ""
        recovered = _find_usable_professional_for_context(catalog, context, port)
        if recovered is not None:
            _bind_usable_run_ids(recovered, context)
            _render_existing_monthly_workspace_panel(recovered)
        else:
            st.session_state["dynamis_active_run_id"] = confirmed_run
            st.session_state["dynamis_active_mission_id"] = (
                active_result_run_id(getattr(result, "mission_id", None)) or ""
            )
            st.info(EXISTING_MONTHLY_ANALYSIS_RU)
        return
    status_text = str(getattr(result, "status", "") or "").strip().upper()
    if status_text in _FAILED_STATUSES:
        st.session_state["dynamis_launch_inflight"] = None
        st.session_state["dynamis_launch_failure"] = (
            f"Новый запуск завершился со статусом {status_text}."
        )
        restore = _find_usable_professional_for_context(catalog, context, port)
        if restore is not None:
            _bind_usable_run_ids(restore, context)
            st.error("Не удалось завершить новый запуск. Восстановлен существующий результат.")
            _render_existing_monthly_workspace_panel(restore)
            return
        # No prior usable professional result — surface the failed run honestly.
    st.session_state["dynamis_active_run_id"] = confirmed_run
    st.session_state["dynamis_active_mission_id"] = active_result_run_id(getattr(result, "mission_id", None)) or ""
    st.session_state["dynamis_launch_status"] = result.status
    st.session_state["dynamis_launch_key"] = key
    st.session_state["dynamis_launched_mission_identity"] = key
    st.session_state["dynamis_launch_inflight"] = None
    st.session_state["dynamis_launch_failure"] = ""
    st.info("Задача запущена")
    st.write(f"Цифровой сотрудник: {employee_title(context.agent_code)}")
    st.write(f"Статус: {launch_status_label(result.status)}")


def _render_constructor_workspace(
    snapshot: Optional[AgentRunSnapshot],
    registry: Optional[ConstructorDecisionRegistryView],
) -> None:
    st.markdown(f"## {MODULE5_TITLE_RU}")
    result = registry.professional if registry is not None else None
    draft = st.session_state.get("dynamis_mission_draft")
    context = st.session_state.get("dynamis_working_context")
    if isinstance(context, WorkingContext):
        current_identity = mission_idempotency_key(context)
    elif isinstance(draft, MissionDraft):
        current_identity = "unlaunched-draft"
    else:
        current_identity = ""
    launched_identity = st.session_state.get("dynamis_launched_mission_identity")
    shown_run_id = result.run_id if result is not None and result.run_id else None
    active_run_id = active_result_run_id(st.session_state.get("dynamis_active_run_id"))
    professional_ready = (
        result is not None
        and str(result.professional_status or "").strip() == "WAITING_FOR_HUMAN_REVIEW"
        and str(getattr(result, "source_candidate_package_id", "") or "").strip()
    )
    if current_identity and different_mission_state(
        current_identity,
        str(launched_identity) if launched_identity else None,
        shown_run_id,
        active_run_id,
    ):
        if professional_ready:
            st.info(WORK_CONTEXT_SLICE_RU)
        else:
            st.warning(SEPARATE_ASSIGNMENT_RU)
    operational = str(getattr(getattr(snapshot, "run", None), "operational_status", "") or "")
    professional_status = str(result.professional_status or "") if result is not None else ""
    ready = (
        registry is not None
        and result is not None
        and registry.availability == ProfessionalResultAvailability.AVAILABLE
        and result.availability == ProfessionalResultAvailability.AVAILABLE
        and registry.total_count > 0
    )
    # Observability may still project RUNNING; it must not hide an AVAILABLE
    # professional result, and must not invent fake pending after a read failure.
    read_failed = (
        registry is not None
        and registry.availability == ProfessionalResultAvailability.INCONSISTENT
    )
    if operational in _FAILED_STATUSES or professional_status == "FAILED":
        st.error("Не удалось завершить задачу.")
        _write_result_pending()
    elif ready and result is not None and registry is not None:
        if isinstance(context, WorkingContext) and _work_context_out_of_package_scope(
            registry, context
        ):
            st.warning(WORK_CONTEXT_OUT_OF_SCOPE_RU)
            st.caption(WORK_CONTEXT_SLICE_RU)
        _render_module5_compact_result(snapshot, result, registry)
    elif read_failed:
        st.error(PROFESSIONAL_RESULT_INCONSISTENT_RU)
        _refresh_status_button()
    elif (
        registry is not None
        and result is not None
        and result.availability == ProfessionalResultAvailability.UNAVAILABLE
        and active_run_id
    ):
        st.info(PROFESSIONAL_RESULT_UNAVAILABLE_RU)
        _refresh_status_button()
    elif operational in _WAITING_STATUSES or professional_status in _WAITING_STATUSES:
        st.info("Требуется решение человека.")
        _write_result_pending()
        _refresh_status_button()
    elif active_run_id:
        if st.session_state.get("dynamis_execution_lifecycle") == REALITY_LOADED:
            st.info(CONTINUES_EXECUTION_RU)
        else:
            st.info("Инженер формирования месячного плана выполняет задачу.")
        _write_result_pending()
        _refresh_status_button()
    else:
        _write_result_pending()
    _render_human_decision(result if ready else None, registry if ready else None)
    _render_human_outcome(result if ready else None, registry if ready else None)
    _render_next_step(result.run_id if result is not None and result.run_id else None)
    _render_pre_admission_export(registry if ready else None)
    _render_technical_evidence(snapshot, registry)


def _applied_working_context() -> Optional[WorkingContext]:
    context = st.session_state.get("dynamis_working_context")
    return context if isinstance(context, WorkingContext) else None


def _render_module5_compact_result(
    snapshot: Optional[AgentRunSnapshot],
    result: ConstructorProfessionalResultView,
    registry: ConstructorDecisionRegistryView,
) -> None:
    context = _applied_working_context()
    scoped_records = filter_records_by_work_context(registry.records, context)
    summary = build_module5_result_summary_from_records(scoped_records)
    meta_bits = [workspace_run_banner(result)]
    as_of = None
    if snapshot is not None:
        as_of = getattr(getattr(snapshot, "run", None), "updated_at", None)
    stamp = module5_state_timestamp(as_of)
    if stamp:
        meta_bits.append(stamp)
    if summary.mode_badge:
        meta_bits.append(summary.mode_badge)
    st.caption(" · ".join(meta_bits))
    if constructor_hitl_actions_visible(str(result.professional_status or "")):
        st.caption(f"Статус: {professional_status_line(result)}")

    kpi_cols = st.columns(4)
    for column, (label, value) in zip(kpi_cols, module5_kpi_tiles(summary)):
        with column:
            st.metric(label, value)

    options = module5_filter_options(summary)
    labels = [label for _key, label, _emph in options]
    pills = getattr(st, "pills", None)
    filter_key = f"dynamis_result_filter_{result.run_id}"
    if callable(pills):
        selected_label = pills(
            "Фильтр результата",
            options=labels,
            selection_mode="single",
            default=labels[0] if labels else None,
            key=filter_key,
            label_visibility="collapsed",
        )
    else:
        selected_label = st.radio(
            "Фильтр результата",
            options=labels,
            horizontal=True,
            key=filter_key,
            label_visibility="collapsed",
        )
    if not selected_label:
        selected_label = labels[0]
    view_id = next(key for key, label, _emph in options if label == selected_label)

    search = st.text_input(
        "Поиск",
        placeholder="BOQ, титул, наименование или система",
        key=f"dynamis_result_search_{result.run_id}",
        label_visibility="collapsed",
    )
    records = select_workspace_records(
        scoped_records,
        result,
        view_id=view_id,
        text=str(search or ""),
    )

    focus = None
    surface = None
    # Command surface belongs to Result Analysis + Work Context, not only «Кандидаты».
    if str(result.professional_status or "").strip() == "WAITING_FOR_HUMAN_REVIEW":
        try:
            surface = prepare_human_review_surface(str(result.run_id))
            focus = build_focus_set_from_work_context(surface, context)
            if view_id == "candidates":
                records = order_records_by_candidate_ids(
                    records, focus.ordered_candidate_ids
                )
        except HumanReviewCommandError:
            surface = None
            focus = None
        except Exception:
            logger.exception("Work-context Focus Set prepare failed")
            surface = None
            focus = None

    if records:
        st.dataframe(
            pd.DataFrame(list(workspace_table_rows(records, result))),
            use_container_width=True,
            hide_index=True,
            height=420,
        )
    else:
        st.caption("В этом разрезе сохранённых работ нет.")
    with st.expander("Детали выбранной строки", expanded=False):
        _render_selected_work(result, records)

    if surface is not None and focus is not None:
        _render_decision_command_panel(surface, focus, context=context)


def _write_result_pending() -> None:
    st.write("Candidate Package: ещё не сформирован")
    st.write("Профессиональный результат: ещё не сформирован")


def _refresh_status_button() -> None:
    if st.button("ОБНОВИТЬ СТАТУС", key="dynamis_refresh_status"):
        rerun = getattr(st, "rerun", None)
        if callable(rerun):
            rerun()


def _period_label_ru(period: Optional[str]) -> str:
    """Display helper: 2026-11 → «ноябрь 2026»."""
    text = str(period or "").strip()
    months = {
        "01": "январь",
        "02": "февраль",
        "03": "март",
        "04": "апрель",
        "05": "май",
        "06": "июнь",
        "07": "июль",
        "08": "август",
        "09": "сентябрь",
        "10": "октябрь",
        "11": "ноябрь",
        "12": "декабрь",
    }
    match = re.fullmatch(r"(20\d{2})-(\d{2})", text)
    if not match:
        return text or "—"
    return f"{months.get(match.group(2), match.group(2))} {match.group(1)}"


def _planning_month_to_period(planning_month: Optional[str]) -> Optional[str]:
    """«октябрь 2026» → 2026-10 for yearless defer resolution."""
    text = str(planning_month or "").strip().casefold().replace("ё", "е")
    if not text:
        return None
    month_map = {
        "январ": "01",
        "феврал": "02",
        "март": "03",
        "апрел": "04",
        "ма": "05",
        "июн": "06",
        "июл": "07",
        "август": "08",
        "сентябр": "09",
        "октябр": "10",
        "ноябр": "11",
        "декабр": "12",
    }
    year_match = re.search(r"(20\d{2})", text)
    if not year_match:
        return None
    year = year_match.group(1)
    for stem, month in month_map.items():
        if stem == "ма" and not re.search(r"\bма[йяе]\b", text):
            continue
        if stem in text:
            return f"{year}-{month}"
    return None


def _render_decision_command_panel(
    surface: Any,
    focus: Any,
    *,
    context: Optional[WorkingContext] = None,
) -> None:
    """Command input immediately under the main candidate table. Preview before write."""
    st.markdown("### Команда решения")
    batch_key = f"dynamis_hr_batch_preview_{surface.run_id}"
    error_key = f"dynamis_hr_batch_error_{surface.run_id}"
    default_year = 2026
    year_text = _horizon_year(context) if context is not None else None
    if year_text and str(year_text).isdigit():
        default_year = int(year_text)
    from_period_label = (
        str(context.planning_month).strip()
        if isinstance(context, WorkingContext) and context.planning_month
        else "—"
    )
    context_period = (
        _planning_month_to_period(context.planning_month)
        if isinstance(context, WorkingContext)
        else None
    )
    # Form binds textarea + recognize in one submit so the command never arrives empty.
    with st.form(key=f"dynamis_hr_command_form_{surface.run_id}", clear_on_submit=False):
        command_text = st.text_area(
            "КОМАНДА РЕШЕНИЯ",
            placeholder=(
                "№2 перенести на ноябрь — нет строительной готовности.\n"
                "№5 принять 50 м — объём требует корректировки.\n"
                "Остальные принять."
            ),
            key=f"dynamis_hr_command_text_{surface.run_id}",
            height=120,
        )
        recognize = st.form_submit_button("РАСПОЗНАТЬ КОМАНДУ")
    if recognize:
        try:
            preview = prepare_batch_from_text(
                str(command_text or ""),
                focus=focus,
                surface=surface,
                default_year=default_year,
                context_period=context_period,
            )
            st.session_state[batch_key] = {
                "focus_set_id": focus.focus_set_id,
                "focus_hash": focus.focus_hash,
                "checkpoint_id": focus.expected_checkpoint_id,
                "preview": preview,
                "focus": focus,
            }
            st.session_state.pop(error_key, None)
        except HumanReviewCommandError as exc:
            st.session_state.pop(batch_key, None)
            if is_non_candidate_reference_error(exc.message):
                st.session_state[error_key] = NON_CANDIDATE_CLARIFICATION_RU
            else:
                st.session_state[error_key] = (
                    f"Не удалось распознать команду: {exc.message}"
                )
        except Exception as exc:
            logger.exception("Human Review command parse failed")
            st.session_state.pop(batch_key, None)
            st.session_state[error_key] = (
                f"Не удалось распознать команду: {exc}"
            )

    parse_error = str(st.session_state.get(error_key) or "").strip()
    if parse_error:
        st.error(parse_error)

    stored = st.session_state.get(batch_key)
    if (
        isinstance(stored, dict)
        and stored.get("focus_hash") == focus.focus_hash
        and stored.get("checkpoint_id") == focus.expected_checkpoint_id
    ):
        preview = stored.get("preview")
        bound_focus = stored.get("focus") or focus
        if preview is not None:
            st.markdown("### Команда распознана")
            facility = preview.focus_facility or "Все"
            discipline = preview.focus_discipline or "Все"
            st.write(f"**Контекст:** {facility} · {discipline}")
            st.write(f"**Кандидатов в контексте:** {preview.focus_size}")
            prior_deferred = int(getattr(preview, "prior_deferred_in_focus", 0) or 0)
            prior_accepted = int(getattr(preview, "prior_accepted_in_focus", 0) or 0)
            prior_changed = int(getattr(preview, "prior_changed_in_focus", 0) or 0)
            if prior_deferred or prior_accepted or prior_changed:
                st.markdown("**Уже решено ранее (текущий контекст):**")
                if prior_deferred:
                    st.write(f"Перенесено: {prior_deferred}")
                if prior_accepted:
                    st.write(f"Принято: {prior_accepted}")
                if prior_changed:
                    st.write(f"Изменён объём: {prior_changed}")
            st.markdown("**Новые решения:**")
            st.write(f"Принять: {preview.counts.accept}")
            st.write(f"Перенести: {preview.counts.defer}")
            st.write(f"Скорректировать: {preview.counts.change_qty}")
            st.write(f"Исключить: {preview.counts.exclude}")
            st.write(f"Нужны данные: {preview.counts.needs_data}")
            if preview.exception_lines:
                st.markdown("**Исключения:**")
                for line in preview.exception_lines:
                    st.write(line)
            if preview.accept_lines:
                with st.expander(f"Принятые ({len(preview.accept_lines)})", expanded=False):
                    for line in preview.accept_lines:
                        st.write(line)
            for op in preview.draft.operations:
                if op.resolution.value != "DEFER_TO_PERIOD":
                    continue
                alias = f"№{op.alias_number}" if op.alias_number else "—"
                st.write(f"**{alias} / {op.boq_code}**")
                st.write("Решение: Перенести")
                st.write(f"Из: {from_period_label}")
                st.write(f"В: {_period_label_ru(op.target_period)}")
                reason = (op.reason_text or "").strip()
                st.write(
                    f"Причина: {reason}"
                    if reason
                    else "Причина: требуется указать до подтверждения"
                )
            clarifications = tuple(getattr(preview, "clarification_lines", ()) or ())
            reasons_ok = bool(getattr(preview, "reasons_complete", True))
            if clarifications:
                for line in clarifications:
                    st.warning(line)
            if reasons_ok:
                if st.button(
                    "ПОДТВЕРДИТЬ РЕШЕНИЯ",
                    key=f"dynamis_hr_commit_batch_{surface.run_id}",
                    type="primary",
                ):
                    try:
                        submit_result = submit_human_review_batch(
                            preview.draft,
                            focus=bound_focus,
                            confirmed=True,
                        )
                        # Read-after-write law: UI committed state only from durable surface.
                        surface_after = prepare_human_review_surface(
                            str(surface.run_id)
                        )
                        durable_by_id = {
                            item.candidate_id: item.current_decision_label
                            for item in surface_after.candidates
                        }
                        missing = [
                            op.candidate_id
                            for op in preview.draft.operations
                            if durable_by_id.get(op.candidate_id, "НЕ РАССМОТРЕНО")
                            == "НЕ РАССМОТРЕНО"
                        ]
                        if missing or int(submit_result.operation_count or 0) < 1:
                            raise HumanReviewCommandError(
                                "Durable Human Review readback does not contain "
                                "confirmed decisions. Preview is not committed truth."
                            )
                        st.session_state.pop(batch_key, None)
                        st.session_state.pop(error_key, None)
                        st.session_state[f"dynamis_hr_command_text_{surface.run_id}"] = ""
                        st.success("Пакет решений записан в durable Human Review.")
                        rerun = getattr(st, "rerun", None)
                        if callable(rerun):
                            rerun()
                    except HumanReviewCommandError as exc:
                        st.session_state[error_key] = exc.message
                        st.error(exc.message)
                    except Exception:
                        logger.exception("Human Review batch submit failed")
                        st.error("Не удалось записать пакет Human Review.")
            else:
                st.caption("Подтверждение недоступно, пока не указаны обязательные причины.")
    elif isinstance(stored, dict):
        st.warning(
            "Предпросмотр устарел после смены рабочего контекста / checkpoint. "
            "Распознайте команду снова."
        )
        st.session_state.pop(batch_key, None)


def _render_human_decision(
    result: Optional[ConstructorProfessionalResultView],
    registry: Optional[ConstructorDecisionRegistryView],
) -> None:
    st.markdown("## Решение человека")
    if result is None or registry is None:
        st.write("Решения человека появятся после формирования результата цифровым сотрудником.")
        return
    if str(result.professional_status or "").strip() != "WAITING_FOR_HUMAN_REVIEW":
        st.write("Human Review для текущего запуска сейчас недоступен.")
        return
    try:
        surface = prepare_human_review_surface(str(result.run_id))
    except HumanReviewCommandError as exc:
        st.error(exc.message)
        st.info(HITL_COMMAND_PORT_REQUIRED_RU)
        return
    except Exception:
        logger.exception("Human Review surface prepare failed")
        st.error("Не удалось загрузить Human Review Command Port.")
        st.info(HITL_COMMAND_PORT_REQUIRED_RU)
        return

    context = _applied_working_context()
    focus = None
    try:
        focus = build_focus_set_from_work_context(surface, context)
    except Exception:
        logger.exception("Work-context summary focus failed")
        focus = None

    if focus is not None:
        ctx_summary = build_work_context_review_summary(surface, focus)
        st.markdown("### Текущий рабочий контекст")
        st.write(f"**Контекст:** {ctx_summary.facility} · {ctx_summary.discipline}")
        st.write(f"Рассмотрено: {ctx_summary.reviewed} / {ctx_summary.total}")
        st.write(f"Принято: {ctx_summary.accepted}")
        st.write(f"Изменён объём: {ctx_summary.changed_qty}")
        st.write(f"Перенесено: {ctx_summary.deferred}")
        st.write(f"Исключено: {ctx_summary.excluded}")
        st.write(f"Нужны данные: {ctx_summary.needs_data}")
        st.write(f"Не рассмотрено: {ctx_summary.not_reviewed}")
    else:
        total = surface.reviewed_count + surface.not_reviewed_count
        st.write(f"Рассмотрено: {surface.reviewed_count} / {total}")
        st.write(f"Принято: {surface.accepted_count}")
        st.write(f"Изменён объём: {surface.changed_qty_count}")
        st.write(f"Перенесено: {surface.deferred_count}")
        st.write(f"Исключено: {surface.excluded_count}")
        st.write(f"Нужны данные: {surface.needs_data_count}")
        st.write(f"Не рассмотрено: {surface.not_reviewed_count}")

    draft = build_monthly_commitment_draft(surface)
    st.markdown("### Текущий черновик месячного обязательства")
    st.write(f"Итоговых позиций: {draft.counts.final_positions}")
    st.write(f"Базовый состав: {draft.counts.baseline}")
    st.write(f"Добавлено Constructor: {draft.counts.added_constructor}")
    st.write(f"Изменён объём: {draft.counts.changed_qty}")
    st.write(f"Перенесено: {draft.counts.deferred}")
    st.write(f"Исключено: {draft.counts.excluded}")
    st.write(f"Нужны данные: {draft.counts.needs_data}")
    st.write(f"Не рассмотрено: {draft.counts.unresolved}")

    composition = composition_table_dicts(draft)
    if composition:
        display_cols = [c for c in composition[0].keys() if c != "candidate_id"]
        st.dataframe(
            pd.DataFrame([{k: row[k] for k in display_cols} for row in composition]),
            use_container_width=True,
            hide_index=True,
            height=320,
        )
    else:
        st.caption(
            "Текущий черновик месячного обязательства пока без утверждённых позиций — "
            "подтвердите решения в блоке команды выше."
        )

    deferred = durable_exception_detail_rows(surface, labels=("ПЕРЕНЕСЕНО",))
    excluded = durable_exception_detail_rows(surface, labels=("ИСКЛЮЧЕНО",))
    needs = durable_exception_detail_rows(surface, labels=("НУЖНЫ ДАННЫЕ",))
    if deferred:
        with st.expander(f"Перенесено ({len(deferred)})", expanded=False):
            st.dataframe(pd.DataFrame(list(deferred)), use_container_width=True, hide_index=True)
    if excluded:
        with st.expander(f"Исключено ({len(excluded)})", expanded=False):
            st.dataframe(pd.DataFrame(list(excluded)), use_container_width=True, hide_index=True)
    if needs:
        with st.expander(f"Нужны данные ({len(needs)})", expanded=False):
            st.dataframe(pd.DataFrame(list(needs)), use_container_width=True, hide_index=True)

    if surface.not_reviewed_count == 0 and surface.needs_data_count == 0 and surface.candidates:
        st.markdown("### Сводка по титулам / дисциплинам")
        for facility_name, discipline_name, counts in grouped_review_summary(surface):
            st.write(
                f"**{facility_name}** / {discipline_name}: "
                f"принято {counts['accepted']} · "
                f"изменено {counts['changed_qty']} · "
                f"перенесено {counts['deferred']} · "
                f"исключено {counts['excluded']}"
            )
        st.caption(
            "Финальное подтверждение месячного обязательства станет доступно "
            "отдельным действием (не в этом increment)."
        )


def _render_human_decision_single_row_v1(surface: Any) -> None:
    """Preserved V1 single-row confirmation path (drill-down / fallback)."""
    labels = [
        f"№? · {item.boq_code} · {item.facility} · {item.current_decision_label}"
        for item in surface.candidates
    ]
    selected_label = st.selectbox(
        "Кандидат",
        options=labels,
        key=f"dynamis_hr_candidate_{surface.run_id}",
    )
    candidate = surface.candidates[labels.index(selected_label)]
    st.write(f"**Титул:** {candidate.facility or '—'}")
    st.write(f"**Дисциплина:** {candidate.discipline or '—'}")
    st.write(f"**Система:** {candidate.system or '—'}")
    st.write(f"**Пакет / IWP:** {candidate.iwp or '—'}")
    st.write(f"**BOQ:** {candidate.boq_code}")
    st.write(candidate.name or "—")
    st.write(f"**Ед. изм.:** {candidate.unit or '—'}")
    st.write(f"**Текущий физический остаток:** {candidate.remaining_qty}")
    st.write(f"**Уже в месячном плане:** {candidate.already_planned_qty}")
    st.write(f"**Предложение Constructor:** {candidate.constructor_proposed_qty}")
    st.write(f"**Текущее решение:** {candidate.current_decision_label}")
    for warning in candidate.warning_lines:
        st.warning(warning)

    draft_key = f"dynamis_hr_draft_{surface.run_id}"
    action_cols = st.columns(4)
    if action_cols[0].button("ПРИНЯТЬ", key=f"dynamis_hr_accept_{surface.run_id}"):
        st.session_state[draft_key] = {
            "candidate_id": candidate.candidate_id,
            "action": HumanReviewAction.ACCEPT.value,
            "approved_qty": candidate.constructor_proposed_qty,
            "reason_text": "",
            "checkpoint_id": surface.expected_checkpoint_id,
            "package_id": surface.package_id,
            "proposed_qty": candidate.constructor_proposed_qty,
            "boq_code": candidate.boq_code,
            "unit": candidate.unit,
        }
    if action_cols[1].button("ИСКЛЮЧИТЬ", key=f"dynamis_hr_exclude_{surface.run_id}"):
        st.session_state[draft_key] = {
            "candidate_id": candidate.candidate_id,
            "action": HumanReviewAction.EXCLUDE.value,
            "approved_qty": 0.0,
            "reason_text": "",
            "checkpoint_id": surface.expected_checkpoint_id,
            "package_id": surface.package_id,
            "proposed_qty": candidate.constructor_proposed_qty,
            "boq_code": candidate.boq_code,
            "unit": candidate.unit,
        }
    if action_cols[2].button("ИЗМЕНИТЬ ОБЪЁМ", key=f"dynamis_hr_change_{surface.run_id}"):
        st.session_state[draft_key] = {
            "candidate_id": candidate.candidate_id,
            "action": HumanReviewAction.CHANGE_QUANTITY.value,
            "approved_qty": candidate.constructor_proposed_qty,
            "reason_text": "",
            "checkpoint_id": surface.expected_checkpoint_id,
            "package_id": surface.package_id,
            "proposed_qty": candidate.constructor_proposed_qty,
            "boq_code": candidate.boq_code,
            "unit": candidate.unit,
        }
    if action_cols[3].button("НУЖНЫ ДАННЫЕ", key=f"dynamis_hr_need_{surface.run_id}"):
        st.session_state[draft_key] = {
            "candidate_id": candidate.candidate_id,
            "action": HumanReviewAction.NEEDS_DATA.value,
            "approved_qty": None,
            "reason_text": "",
            "checkpoint_id": surface.expected_checkpoint_id,
            "package_id": surface.package_id,
            "proposed_qty": candidate.constructor_proposed_qty,
            "boq_code": candidate.boq_code,
            "unit": candidate.unit,
        }

    draft = st.session_state.get(draft_key)
    if not isinstance(draft, dict) or draft.get("candidate_id") != candidate.candidate_id:
        st.caption("Выберите решение, затем подтвердите его явно.")
        return

    action = HumanReviewAction(str(draft.get("action")))
    st.markdown("### Предпросмотр решения")
    st.write(f"Кандидат: {draft.get('boq_code')} · {candidate.facility}")
    st.write(f"Решение: {action.value}")
    st.write(f"Constructor: {draft.get('proposed_qty')} {draft.get('unit') or ''}".rstrip())
    approved_qty = draft.get("approved_qty")
    reason_text = str(draft.get("reason_text") or "")
    if action is HumanReviewAction.CHANGE_QUANTITY:
        approved_qty = st.number_input(
            "Утверждаю объём",
            min_value=0.0,
            max_value=float(draft.get("proposed_qty") or 0.0),
            value=float(approved_qty if approved_qty is not None else draft.get("proposed_qty") or 0.0),
            key=f"dynamis_hr_qty_{surface.run_id}_{candidate.candidate_id}",
        )
        draft["approved_qty"] = float(approved_qty)
        st.write(f"Утверждаю: {approved_qty} {draft.get('unit') or ''}".rstrip())
    elif action is HumanReviewAction.ACCEPT:
        st.write(f"Утверждаю: {draft.get('proposed_qty')} {draft.get('unit') or ''}".rstrip())
    elif action is HumanReviewAction.EXCLUDE:
        st.write("Утверждаю: 0")
    needs_reason = action in {
        HumanReviewAction.EXCLUDE,
        HumanReviewAction.CHANGE_QUANTITY,
        HumanReviewAction.NEEDS_DATA,
    }
    reason_text = st.text_area(
        "Причина" + ("" if needs_reason else " (необязательно)"),
        value=reason_text,
        key=f"dynamis_hr_reason_{surface.run_id}_{candidate.candidate_id}",
    )
    draft["reason_text"] = reason_text
    st.session_state[draft_key] = draft

    if st.button("ПОДТВЕРДИТЬ РЕШЕНИЕ", key=f"dynamis_hr_commit_{surface.run_id}", type="primary"):
        try:
            candidate_id = str(draft.get("candidate_id"))
            submit_human_review_decision(
                HumanReviewCommand(
                    run_id=surface.run_id,
                    package_id=str(draft.get("package_id") or surface.package_id),
                    candidate_id=candidate_id,
                    action=action,
                    expected_checkpoint_id=str(
                        draft.get("checkpoint_id") or surface.expected_checkpoint_id
                    ),
                    approved_qty=(
                        None
                        if action is HumanReviewAction.NEEDS_DATA
                        else float(draft.get("approved_qty") or 0.0)
                    ),
                    reason_text=str(draft.get("reason_text") or "").strip() or None,
                )
            )
            surface_after = prepare_human_review_surface(str(surface.run_id))
            label = next(
                (
                    item.current_decision_label
                    for item in surface_after.candidates
                    if item.candidate_id == candidate_id
                ),
                "НЕ РАССМОТРЕНО",
            )
            if label == "НЕ РАССМОТРЕНО":
                raise HumanReviewCommandError(
                    "Durable Human Review readback does not contain "
                    "confirmed decision. Preview is not committed truth."
                )
            st.session_state.pop(draft_key, None)
            st.success("Решение записано в durable Human Review.")
            rerun = getattr(st, "rerun", None)
            if callable(rerun):
                rerun()
        except HumanReviewCommandError as exc:
            st.error(exc.message)
        except Exception:
            logger.exception("Human Review submit failed")
            st.error("Не удалось записать решение Human Review.")


def _render_pre_admission_export(registry: Optional[ConstructorDecisionRegistryView]) -> None:
    st.markdown(f"## {EXPORT_SECTION_TITLE}")
    st.write(EXPORT_INTRO_RU)
    context = st.session_state.get("dynamis_working_context")
    if not isinstance(context, WorkingContext):
        context = None
    if not export_available(registry):
        st.button(EXPORT_BUTTON_LABEL, key="dynamis_pre_admission_export", disabled=True)
        st.write(EXPORT_UNAVAILABLE_RU)
        return
    project = context.project if context is not None and context.project else "БХК"
    month = context.planning_month if context is not None and context.planning_month else ""
    payload = build_pre_admission_workbook(
        registry,
        project=project,
        month_display=month,
        context=context,
    )
    st.download_button(
        EXPORT_BUTTON_LABEL,
        data=payload,
        file_name=export_filename(project, month),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dynamis_pre_admission_export",
    )


def _render_selected_work(
    result: ConstructorProfessionalResultView,
    records: tuple[ConstructorRowDecisionView, ...],
) -> None:
    st.markdown("### Выбранная работа")
    if not records:
        st.caption("Работа не выбрана.")
        return
    labels = [f"{item.boq_code} · {item.source_order}" for item in records]
    default_index = 0
    for index, item in enumerate(records):
        if constructor_row_awaits_human_review(item, result):
            default_index = index
            break
    selected_label = st.selectbox(
        "Работа",
        options=labels,
        index=default_index,
        key=f"dynamis_selected_work_{result.run_id}",
    )
    item = records[labels.index(selected_label)]
    row = workspace_table_rows((item,), result)[0]
    st.markdown(f"#### {item.boq_code}")
    st.write(item.name or "—")
    st.write(f"**Система:** {item.system or '—'}")
    st.write(f"**Пакет / IWP:** {row['Пакет / IWP']}")
    st.write(f"**Физический остаток:** {row['Физический остаток']}")
    st.write(f"**Уже запланировано:** {row['Уже запланировано']}")
    st.write(f"**Доступный объём:** {row['Доступный объём']}")
    st.write(f"**Отклонение:** {row['Отклонение']}")
    st.write(f"**Решение Constructor:** {row['Решение Constructor']}")
    st.write("**Основание**")
    st.write(item.reason_text or "—")
    situation = candidate_situation_line(item, result)
    if situation:
        st.write(situation)


_FINAL_PREVIEW_TOKEN = "dynamis_final_approval_preview"


def _render_human_outcome(
    result: Optional[ConstructorProfessionalResultView],
    registry: Optional[ConstructorDecisionRegistryView],
) -> None:
    st.markdown("## Итог")
    if result is None or registry is None or not result.run_id:
        st.session_state.pop(_FINAL_PREVIEW_TOKEN, None)
        st.write("Итоговый состав ещё не сформирован.")
        st.button("ПОДТВЕРДИТЬ РЕЗУЛЬТАТ", disabled=True, key="dynamis_confirm_package")
        st.info(CONFIRM_COMMAND_PORT_REQUIRED_RU)
        return
    try:
        preview = prepare_final_monthly_approval_preview(str(result.run_id))
    except Exception:
        logger.exception("Final monthly approval preview failed")
        st.session_state.pop(_FINAL_PREVIEW_TOKEN, None)
        _write_registry_outcome(result, registry)
        st.button("ПОДТВЕРДИТЬ РЕЗУЛЬТАТ", disabled=True, key="dynamis_confirm_package")
        st.info(CONFIRM_COMMAND_PORT_REQUIRED_RU)
        return
    readiness = preview.readiness
    reviewed = (
        readiness.accepted_count
        + readiness.changed_qty_count
        + readiness.excluded_count
        + readiness.deferred_count
        + readiness.needs_data_count
    )
    st.write(f"Рассмотрено: {reviewed}")
    st.write(f"Осталось решить: {readiness.not_reviewed_count}")
    st.write(f"Требуют данных: {readiness.needs_data_count}")
    st.write(f"Перенесено: {readiness.deferred_count}")
    st.write(f"Исключено: {readiness.excluded_count}")
    if not readiness.ready:
        st.session_state.pop(_FINAL_PREVIEW_TOKEN, None)
        if readiness.unresolved_human_count > 0:
            st.write(not_ready_message(readiness.unresolved_human_count))
        else:
            st.write("Месячное обязательство нельзя утвердить: нет позиций кандидата.")
        st.button(
            "ПОДТВЕРДИТЬ МЕСЯЧНОЕ ОБЯЗАТЕЛЬСТВО",
            disabled=True,
            key="dynamis_confirm_package",
        )
        return
    _render_final_preview_table(preview)
    existing = find_current_approved_package(str(result.run_id))
    if existing is not None:
        st.session_state.pop(_FINAL_PREVIEW_TOKEN, None)
        _write_approved_banner(existing)
        return
    shown = st.session_state.get(_FINAL_PREVIEW_TOKEN)
    if st.button("ПОДТВЕРДИТЬ МЕСЯЧНОЕ ОБЯЗАТЕЛЬСТВО", key="dynamis_confirm_package"):
        if shown is None:
            st.error(STALE_PREVIEW_RU)
        else:
            try:
                confirmed = submit_final_monthly_confirm(shown)
            except FinalConfirmError as exc:
                st.error(exc.message)
            except Exception:
                logger.exception("Final monthly confirm failed")
                st.error("Не удалось подтвердить месячное обязательство.")
            else:
                st.session_state.pop(_FINAL_PREVIEW_TOKEN, None)
                _write_approved_banner(confirmed.package)
                return
    st.session_state[_FINAL_PREVIEW_TOKEN] = preview


def _write_registry_outcome(
    result: ConstructorProfessionalResultView,
    registry: ConstructorDecisionRegistryView,
) -> None:
    proposed = sum(1 for item in registry.records if item.outcome == "CANDIDATE")
    excluded = sum(1 for item in registry.records if str(item.outcome).startswith("EXCLUDED_"))
    attention = sum(
        1 for item in registry.records if constructor_row_awaits_human_review(item, result)
    )
    _agreed, _removed, clarify = human_decision_tally(result)
    st.write(f"Рассмотрено Constructor: {registry.total_count}")
    st.write(f"Предложено к включению: {proposed}")
    st.write(f"Исключено: {excluded}")
    st.write(f"Требует решения человека: {attention}")
    st.write("Перенесено: не зафиксировано")
    st.write(f"Нужны данные: {clarify}")


def _render_final_preview_table(preview: object) -> None:
    lines = getattr(preview, "professional_lines", ())
    if not lines:
        st.caption("В итоговом составе текущего месяца нет включаемых позиций.")
        return
    rows = [
        {
            "Титул": item.facility,
            "Дисциплина": item.discipline,
            "Система": item.system,
            "Пакет / IWP": item.iwp,
            "BOQ": item.boq_code,
            "Наименование": item.name,
            "Ед. изм.": item.unit,
            "Базовый объём": item.baseline_qty,
            "Добавлено Constructor": item.constructor_delta_qty,
            "Итоговый объём": item.final_qty,
            "Статус": item.source_status,
        }
        for item in lines
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _write_approved_banner(package: object) -> None:
    st.write("МЕСЯЧНОЕ ОБЯЗАТЕЛЬСТВО УТВЕРЖДЕНО")
    st.write(f"approved_package_id: {package.approved_package_id}")
    approved_at = getattr(package, "approved_at", None)
    stamp = approved_at.isoformat() if hasattr(approved_at, "isoformat") else str(approved_at)
    st.write(f"approved_at: {stamp}")
    st.write(f"approved_by: {package.approved_by}")
    st.write(f"source package: {package.source_candidate_package_id}")
    st.write(f"source run: {package.source_run_id}")


def _render_next_step(run_id: Optional[str] = None) -> None:
    st.markdown("## Передать дальше")
    st.write("Инженер производственной готовности и допуска")
    st.button(
        "ПЕРЕДАТЬ ИНЖЕНЕРУ ПРОИЗВОДСТВЕННОЙ ГОТОВНОСТИ И ДОПУСКА",
        disabled=True,
        key="dynamis_handoff",
    )
    approved = False
    if run_id:
        try:
            approved = find_current_approved_package(str(run_id)) is not None
        except Exception:
            logger.exception("Approved package lookup failed")
            approved = False
    if approved:
        st.write(
            "Утверждённый пакет готов к передаче. "
            "Контур передачи будет подключён следующим шагом."
        )
    else:
        st.write("Передача станет доступна после подтверждения итогового состава.")
    st.info(HANDOFF_COMMAND_PORT_REQUIRED_RU)


def _render_technical_evidence(
    snapshot: Optional[AgentRunSnapshot],
    registry: Optional[ConstructorDecisionRegistryView],
) -> None:
    with st.expander(CONSTRUCTOR_EVIDENCE_TITLE_RU):
        result = registry.professional if registry is not None else None
        active_run = active_result_run_id(st.session_state.get("dynamis_active_run_id"))
        active_mission = active_result_run_id(st.session_state.get("dynamis_active_mission_id"))
        result_run = active_result_run_id(getattr(result, "run_id", None)) if result is not None else None
        result_mission = active_result_run_id(getattr(result, "mission_id", None)) if result is not None else None
        shown_run = active_run or result_run
        shown_mission = active_mission or result_mission
        failure = str(st.session_state.get("dynamis_launch_failure") or "").strip()
        if shown_run or shown_mission or result is not None or failure:
            st.write(f"Run ID: {shown_run or '—'}")
            st.write(f"Mission ID: {shown_mission or '—'}")
        if result is not None:
            st.write(f"Candidate Package ID: {result.source_candidate_package_id or '—'}")
            st.write(f"Профессиональный статус: {result.professional_status or '—'}")
            for outcome, count in registry.outcome_counts:
                st.write(f"{outcome}: {count}")
        if failure and not shown_run:
            st.write(failure)
        if snapshot is None:
            return
        st.write(f"Операционный статус: {snapshot.run.operational_status}")
        handoff = snapshot.handoff
        handoff_none = handoff.handoff_id is None and handoff.status is HandoffStatus.NOT_STARTED
        st.write(f"Передача: {'не выполнялась' if handoff_none else handoff_status_ru(handoff.status.value)}")
        if snapshot.timeline_events:
            st.markdown("**События**")
            for event in snapshot.timeline_events:
                st.write(f"{event.event_type}: {event.status}")


def _apply_recovered_mission(mission: RecoveredMission) -> None:
    context = working_context_from_mission(mission)
    identity = mission_idempotency_key(context)
    st.session_state["dynamis_working_context"] = context
    st.session_state["dynamis_assignment_text"] = context.intent or ""
    st.session_state["dynamis_active_run_id"] = mission.run_id
    st.session_state["dynamis_active_mission_id"] = mission.mission_id
    st.session_state["dynamis_launched_mission_identity"] = identity
    st.session_state["dynamis_launch_key"] = identity
    st.session_state["dynamis_launch_status"] = mission.operational_status
    st.session_state["dynamis_execution_lifecycle"] = mission.lifecycle_status
    st.session_state["dynamis_launch_failure"] = ""
    st.session_state["dynamis_global_text"] = ""
    st.session_state.pop("dynamis_pending_command", None)
    st.session_state["dynamis_recovery_choices"] = ()
    st.session_state["dynamis_recovery_resolved"] = True
    _write_context_fields(context)


def _restore_durable_mission_if_needed(
    port: Optional[AgentControlRoomQueryPort],
    catalog: Optional[WorkContextCatalog] = None,
) -> None:
    if port is None:
        return
    active = active_result_run_id(st.session_state.get("dynamis_active_run_id"))
    context = st.session_state.get("dynamis_working_context")
    status = ""
    if active:
        try:
            status = operational_status_for_run(port, active).upper()
        except Exception:
            logger.exception("Active run status lookup failed")
    if active and status in _FAILED_STATUSES:
        usable = None
        if isinstance(context, WorkingContext) and catalog is not None:
            usable = _find_usable_professional_for_context(catalog, context, port)
        if usable is None:
            try:
                decision = load_recovery_decision(port)
            except Exception:
                decision = None
                logger.exception("Human Surface mission recovery failed")
            if decision is not None and decision.selected is not None:
                usable = decision.selected
        if usable is not None and usable.run_id != active:
            # Preserve the user's current Work Context slice — only rebind the run.
            if isinstance(context, WorkingContext):
                _bind_usable_run_ids(usable, context)
            else:
                _apply_recovered_mission(usable)
            st.session_state["dynamis_recovery_resolved"] = True
            st.session_state["dynamis_recovery_choices"] = ()
            return
    if active:
        return
    if st.session_state.get("dynamis_recovery_resolved"):
        return
    # Prefer Project+Month(+Queue) usable professional result before generic recovery.
    if isinstance(context, WorkingContext) and catalog is not None:
        usable = _find_usable_professional_for_context(catalog, context, port)
        if usable is not None:
            _bind_usable_run_ids(usable, context)
            st.session_state["dynamis_recovery_resolved"] = True
            st.session_state["dynamis_recovery_choices"] = ()
            return
    project_code = None
    month_key = None
    if isinstance(context, WorkingContext) and catalog is not None:
        project_code = _catalog_project_code(catalog, str(context.project or "")) or None
        month_key = _stored_planning_month_key(str(context.planning_month or "")) or None
    try:
        decision = load_recovery_decision(
            port,
            project_code=project_code,
            month_key=month_key,
        )
    except Exception:
        logger.exception("Human Surface mission recovery failed")
        st.session_state["dynamis_recovery_resolved"] = True
        return
    if decision.ambiguous:
        st.session_state["dynamis_recovery_choices"] = decision.choices
        return
    st.session_state["dynamis_recovery_choices"] = ()
    st.session_state["dynamis_recovery_resolved"] = True
    if decision.selected is not None:
        _apply_recovered_mission(decision.selected)


def _render_recovery_choices() -> None:
    if active_result_run_id(st.session_state.get("dynamis_active_run_id")):
        return
    choices = tuple(st.session_state.get("dynamis_recovery_choices") or ())
    if not choices:
        return
    st.markdown("## Ранее запущенная задача")
    labels = [
        " · ".join(
            part
            for part in (
                item.project_label or "—",
                item.planning_month or "—",
                item.operational_status or "—",
                item.run_id,
            )
            if part
        )
        for item in choices
    ]
    selected = st.radio("Задача", labels, key="dynamis_recovery_choice")
    if not st.button(RECOVERY_CONTINUE_RU, key="dynamis_recover_mission"):
        return
    index = labels.index(str(selected))
    _apply_recovered_mission(choices[index])
    rerun = getattr(st, "rerun", None)
    if callable(rerun):
        rerun()


def main() -> None:
    # Page config / global navigation belong exclusively to app.py.
    st.markdown("# Рабочее место цифровых сотрудников")
    st.caption(
        "Постановка задач · профессиональное исполнение · "
        "решения человека · передача результата"
    )
    catalog = load_work_context_catalog()
    port = _safe_query_port()
    _restore_durable_mission_if_needed(port, catalog)
    _render_global_command_bar(catalog)
    _render_recovery_choices()
    _render_working_context(catalog)
    # After WC is applied: bind/unbind monthly run for Project+Month(+Queue).
    _ensure_existing_monthly_workspace(catalog, port)
    _render_assignee_picker()
    _render_assignment()
    context = st.session_state.get("dynamis_working_context")
    if isinstance(context, WorkingContext) and (
        context.intent
        or (
            str(context.project or "").strip()
            and str(context.planning_month or "").strip()
        )
    ):
        _render_mission_draft(catalog)
    snapshot = None
    registry = None
    run_id = active_result_run_id(st.session_state.get("dynamis_active_run_id"))
    if port is not None and run_id:
        loaded = _load_snapshot(port, run_id)
        if loaded is not None and active_result_run_id(loaded.run.run_id) == run_id:
            snapshot = loaded
        if loaded is not None and loaded.run.agent_code == "MONTHLY_PLAN_CONSTRUCTOR":
            registry = _load_constructor_registry(loaded, port, bound_run_id=run_id)
    _render_constructor_workspace(snapshot, registry)


main()
