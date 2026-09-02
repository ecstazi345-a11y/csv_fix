# ============================================================
# Page 53 — Центр управления цифровыми сотрудниками (READ-ONLY)
# Execution OS Agent Control Room Core — observe only via Query Port
# ============================================================

from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd
import streamlit as st

from agents.control_room.dtos import AgentRunListView, AgentRunSnapshot, DerivationState
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
    CATALOG_INCOMPLETE_FILTER_RU,
    EMPTY_RUNS_INCOMPLETE_CATALOG_RU,
    EMPTY_RUNS_RU,
    EVENTS_COMPLETE_FALSE_RU,
    RUNS_COMPLETE_FALSE_RU,
    WAITING_FOR_HUMAN_RU,
    all_operational_status_options,
    catalog_filter_values,
    derivation_stage_warning,
    format_timestamp_moscow,
    handoff_status_ru,
    operational_status_ru,
    run_radio_label,
    short_run_id,
    stage_display_state_ru,
    stage_history_rows,
    status_icon,
    timeline_rows,
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
    st.write(f"**Начат:** {format_timestamp_moscow(run.started_at)} МСК")
    st.write(f"**Обновлён:** {format_timestamp_moscow(run.updated_at)} МСК")
    if run.completed_at is not None:
        st.write(f"**Завершён:** {format_timestamp_moscow(run.completed_at)} МСК")
    st.caption(f"Версия состояния: {run.projection_version}")

    with st.expander("Технические идентификаторы"):
        st.code(run.run_id)

    handoff = snapshot.handoff
    if run.operational_status == OperationalStatus.COMPLETED.value:
        if handoff.status.value != "NOT_STARTED":
            st.write(f"**Передача:** {handoff_status_ru(handoff.status.value)}")

    stage_warning = derivation_stage_warning(snapshot.stage.derivation_state)
    if stage_warning:
        st.warning(stage_warning)

    current = snapshot.stage.current_stage
    if snapshot.stage.derivation_state is DerivationState.OK and current is not None:
        st.markdown("**Текущая стадия**")
        state = current.display_state.value
        st.write(f"{current.stage_id} — {stage_display_state_ru(state)}")
        st.caption(f"Начало: {format_timestamp_moscow(current.started_at)} МСК")

    if snapshot.stage.occurrences:
        st.markdown("**История стадий**")
        st.dataframe(
            pd.DataFrame(list(stage_history_rows(snapshot.stage.occurrences))),
            use_container_width=True,
            hide_index=True,
        )

    if not snapshot.events_complete:
        st.info(EVENTS_COMPLETE_FALSE_RU)

    st.markdown("**Доступное окно событий**")
    if snapshot.timeline_events:
        st.dataframe(
            pd.DataFrame(list(timeline_rows(snapshot.timeline_events))),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("В доступном окне событий записей нет.")


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
