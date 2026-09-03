# ============================================================
# Page 53 — Центр управления цифровыми сотрудниками (READ-ONLY)
# Execution OS Agent Control Room Core — observe only via Query Port
# ============================================================

from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd
import streamlit as st

from agents.control_room.dtos import (
    AgentRunListView,
    AgentRunSnapshot,
    DerivationState,
    HandoffStatus,
    ProfessionalExecutionStepKind,
)
from agents.control_room.errors import (
    ControlRoomQueryBlockerError,
    ControlRoomQueryError,
    ControlRoomRunNotFoundError,
    ControlRoomStorageUnavailableError,
)
from agents.control_room.factory import (
    ControlRoomConfigurationError,
    build_agent_control_room_query_port,
)
from agents.control_room.presentation import (
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
    execution_path_summary_rows,
    execution_step_title,
    format_timestamp_moscow,
    handoff_status_ru,
    handoff_type_ru,
    human_decision_reason_text,
    operational_status_ru,
    post_decision_lines,
    professional_execution_state_ru,
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


@st.cache_resource
def _cached_query_port() -> AgentControlRoomQueryPort:
    return build_agent_control_room_query_port()


def _safe_query_port() -> Optional[AgentControlRoomQueryPort]:
    try:
        return _cached_query_port()
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


def _render_selected_run(snapshot: AgentRunSnapshot) -> None:
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
    if handoff is None:
        if not org.history_complete:
            st.info(HANDOFF_NOT_CONFIRMED_INCOMPLETE_RU)
        else:
            st.info(HANDOFF_NOT_OBSERVED_RU)
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


def main() -> None:
    st.set_page_config(layout="wide", page_title="Центр управления агентами")
    st.title("Центр управления цифровыми сотрудниками")
    st.caption("Наблюдение за управляемыми запусками агентной среды Execution OS")
    st.markdown("**Режим:** наблюдение")

    port = _safe_query_port()
    if port is None:
        return

    try:
        catalog = _load_catalog(port)
    except ControlRoomQueryError:
        logger.exception("Control Room catalog load failed")
        st.error("Не удалось загрузить данные Центра управления агентами.")
        return
    except Exception:
        logger.exception("Unexpected Control Room catalog failure")
        st.error("Не удалось загрузить данные Центра управления агентами.")
        return

    agent_code, project_code, month_key, operational_status, refresh = _render_filters(catalog)
    if refresh:
        st.rerun()

    try:
        list_view = _load_filtered_runs(
            port,
            agent_code=agent_code,
            project_code=project_code,
            month_key=month_key,
            operational_status=operational_status,
        )
    except ControlRoomQueryBlockerError:
        st.error("Некорректный параметр запроса.")
        return
    except ControlRoomQueryError:
        logger.exception("Control Room filtered list load failed")
        st.error("Не удалось загрузить данные Центра управления агентами.")
        return
    except Exception:
        logger.exception("Unexpected Control Room list failure")
        st.error("Не удалось загрузить данные Центра управления агентами.")
        return

    left, right = st.columns([0.35, 0.65], gap="large")
    with left:
        st.markdown("### Запуски")
        selected_run_id = _render_run_list(list_view)

    with right:
        if selected_run_id:
            snapshot = _load_snapshot(port, selected_run_id)
            if snapshot is not None:
                _render_selected_run(snapshot)
        else:
            st.info("Выберите запуск в списке слева.")


main()
