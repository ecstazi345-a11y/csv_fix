# ============================================================
# Page 51 — MPO-004A Agent Cockpit (READ-ONLY)
# Compact observation surface over monthly planning orchestrator.
# No writes, no LLM, no approve/reject.
# ============================================================

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import pandas as pd
import streamlit as st

from services.monthly_plan_labor_service import load_labor_lines
from services.monthly_planning_orchestrator_service import run_monthly_planning_orchestrator
from services.mpo_cockpit_display import (
    action_label,
    finding_compact_line,
    finding_label,
    format_kpi_value,
    is_bare_project_label,
    prioritize_findings,
    recommendation_label,
    severity_label,
    status_headline,
    step_statuses,
    validation_label,
)
from utils.month_key import format_month_key_ru, normalize_month_key

st.set_page_config(layout="wide", page_title="Оркестратор месячного плана")

SS_LAST_RUN = "mpo_cockpit_last_run"
SS_RUN_SCOPE = "mpo_cockpit_run_scope"

# title, field, format kind, unit caption
KPI_SPECS = [
    ("Строк плана", "plan_line_count", "int", "строк"),
    ("Требуется", "required_hours_total", "hours", "чел·ч"),
    ("Утверждённая мощность", "approved_available_hours_total", "hours", "чел·ч"),
    ("Покрытие", "resource_coverage", "coverage", "%"),
    ("Дефицит", "resource_gap_hours", "hours", "чел·ч"),
    ("Заблокировано", "blocking_line_count", "int", "строк"),
]

st.markdown(
    """
<style>
div[data-testid="stVerticalBlockBorderWrapper"] {
  border: 1px solid rgba(49, 51, 63, 0.18);
  border-radius: 10px;
  padding: 0.35rem 0.75rem 0.55rem 0.75rem;
}
.mpo-kpi-title { font-size: 0.78rem; color: #5c6370; margin-bottom: 0.15rem; }
.mpo-kpi-value { font-size: 1.35rem; font-weight: 650; line-height: 1.2; }
.mpo-kpi-unit { font-size: 0.75rem; color: #6b7280; }
.mpo-status-title { font-size: 1.35rem; font-weight: 700; letter-spacing: 0.01em; margin: 0.1rem 0; }
.mpo-status-reason { font-size: 1.05rem; margin: 0.25rem 0 0.1rem 0; }
.mpo-muted { color: #5c6370; font-size: 0.9rem; }
.mpo-step { font-size: 0.92rem; white-space: nowrap; }
.mpo-hd-title { font-size: 1.15rem; font-weight: 700; margin-bottom: 0.35rem; }
</style>
""",
    unsafe_allow_html=True,
)


def _safe(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none"} else text


@st.cache_data(ttl=60, show_spinner=False)
def _load_labor_all() -> pd.DataFrame:
    return load_labor_lines()


def _project_options(labor: pd.DataFrame) -> list[str]:
    if labor is None or labor.empty or "project_code" not in labor.columns:
        return []
    values: list[str] = []
    seen: set[str] = set()
    for raw in labor["project_code"].tolist():
        text = _safe(raw)
        if not text or is_bare_project_label(text):
            continue
        if text in seen:
            continue
        seen.add(text)
        values.append(text)
    return sorted(values)


def _month_options_for_project(labor: pd.DataFrame, project_code: str) -> list[tuple[str, str]]:
    if labor is None or labor.empty or "month_key" not in labor.columns:
        return []
    df = labor
    if project_code and "project_code" in df.columns:
        mask = df["project_code"].astype(str).str.strip() == project_code
        df = df.loc[mask]
    pairs: list[tuple[str, str]] = []
    seen_raw: set[str] = set()
    for raw in df["month_key"].tolist():
        stored = _safe(raw)
        if not stored or stored in seen_raw:
            continue
        seen_raw.add(stored)
        canon = normalize_month_key(stored)
        label = format_month_key_ru(canon) if canon else None
        pairs.append((label or stored, stored))
    pairs.sort(key=lambda item: normalize_month_key(item[1]) or item[1], reverse=True)
    return pairs


def _scope_matches(project_code: str, month_key: str) -> bool:
    scope = st.session_state.get(SS_RUN_SCOPE)
    if not isinstance(scope, dict):
        return False
    return (
        _safe(scope.get("project_code")) == _safe(project_code)
        and _safe(scope.get("month_key")) == _safe(month_key)
    )


def _findings_source(run: dict[str, Any]) -> list[dict[str, Any]]:
    hd = run.get("human_decision")
    if isinstance(hd, dict) and isinstance(hd.get("findings"), list):
        return [f for f in hd["findings"] if isinstance(f, dict)]
    analysis = run.get("analysis")
    if isinstance(analysis, dict) and isinstance(analysis.get("findings"), list):
        return [f for f in analysis["findings"] if isinstance(f, dict)]
    return []


def _warnings_source(run: dict[str, Any]) -> list[Any]:
    hd = run.get("human_decision")
    if isinstance(hd, dict) and isinstance(hd.get("warnings"), list):
        return list(hd["warnings"])
    return [
        f
        for f in _findings_source(run)
        if str(f.get("severity") or "").upper() == "WARNING"
    ]


def _recommendation_code(run: dict[str, Any]) -> str:
    hd = run.get("human_decision") if isinstance(run.get("human_decision"), dict) else {}
    analysis = run.get("analysis") if isinstance(run.get("analysis"), dict) else {}
    return _safe(hd.get("recommendation_code") or analysis.get("recommendation_code"))


def _render_stepper(run: Optional[dict[str, Any]]) -> None:
    steps = step_statuses(run)
    icons = {
        "done": "●",
        "current": "◉",
        "error": "✕",
        "skipped": "○",
        "pending": "○",
    }
    parts: list[str] = []
    for i, step in enumerate(steps):
        icon = icons.get(step["ui"], "○")
        parts.append(f"{icon} {step['label']}")
        if i < len(steps) - 1:
            parts.append("→")
    st.markdown(
        f"<div class='mpo-step'>{' '.join(parts)}</div>",
        unsafe_allow_html=True,
    )


def _render_status_card(run: dict[str, Any], *, failed: bool) -> None:
    with st.container(border=True):
        if failed:
            err = run.get("error") if isinstance(run.get("error"), dict) else {}
            st.markdown(
                "<div class='mpo-status-title'>АНАЛИЗ НЕ ВЫПОЛНЕН</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div class='mpo-status-reason'>"
                f"{_safe(err.get('message')) or 'Неизвестная ошибка'}"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.caption("Запустите анализ повторно после проверки данных.")
            return

        rec = _recommendation_code(run)
        st.markdown(
            f"<div class='mpo-status-title'>{status_headline(rec)}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div class='mpo-status-reason'>Основная причина: "
            f"<b>{recommendation_label(rec)}</b></div>",
            unsafe_allow_html=True,
        )
        if _safe(run.get("state")) == "HUMAN_DECISION":
            st.markdown(
                "<div class='mpo-muted'>Анализ завершён. Требуется решение человека.</div>",
                unsafe_allow_html=True,
            )


def _render_kpi(run: Optional[dict[str, Any]], *, failed: bool) -> None:
    summary: dict[str, Any] = {}
    if not failed and isinstance(run, dict):
        analysis = run.get("analysis")
        if isinstance(analysis, dict) and isinstance(analysis.get("summary"), dict):
            summary = analysis["summary"]

    cols = st.columns(6)
    for col, (title, key, kind, unit) in zip(cols, KPI_SPECS):
        with col:
            with st.container(border=True):
                value = "—" if failed else format_kpi_value(summary.get(key), kind=kind)
                st.markdown(
                    f"<div class='mpo-kpi-title'>{title}</div>"
                    f"<div class='mpo-kpi-value'>{value}</div>"
                    f"<div class='mpo-kpi-unit'>{unit}</div>",
                    unsafe_allow_html=True,
                )


def _warning_text(item: Any) -> str:
    if isinstance(item, dict):
        code = _safe(item.get("code"))
        if code:
            return finding_label(code)
        return _safe(item.get("message")) or str(item)
    return _safe(item) or str(item)


def _render_findings_block(findings: list[dict[str, Any]]) -> None:
    st.markdown("#### Что обнаружил оркестратор")
    if not findings:
        st.caption("Существенных факторов не обнаружено.")
        return

    top = prioritize_findings(findings, limit=5)
    for finding in top:
        st.markdown(finding_compact_line(finding))

    with st.expander("Все выявленные факторы", expanded=False):
        ordered = prioritize_findings(findings)
        for finding in ordered:
            code = _safe(finding.get("code"))
            sev = severity_label(finding.get("severity"))
            title = finding_label(code)
            count = finding.get("count")
            count_bit = f" · {count}" if count not in (None, "") else ""
            st.markdown(f"**{title}** — {sev}{count_bit}")
            ids = finding.get("plan_line_ids")
            if isinstance(ids, list) and ids:
                with st.expander(f"Затронутые строки ({len(ids)})", expanded=False):
                    shown = [_safe(x) for x in ids if _safe(x)]
                    st.code(", ".join(shown[:40]) + (" …" if len(shown) > 40 else ""))


def _render_warnings_compact(run: dict[str, Any]) -> None:
    warnings = _warnings_source(run)
    if not warnings:
        return
    st.caption(f"Дополнительные предупреждения: {len(warnings)}")
    with st.expander("Показать предупреждения", expanded=False):
        for item in warnings:
            st.markdown(f"- {_warning_text(item)}")


def _render_human_decision(run: dict[str, Any]) -> None:
    if _safe(run.get("state")) != "HUMAN_DECISION":
        return
    hd = run.get("human_decision") if isinstance(run.get("human_decision"), dict) else {}
    validation = run.get("validation") if isinstance(run.get("validation"), dict) else {}
    analysis = run.get("analysis") if isinstance(run.get("analysis"), dict) else {}
    rec = _safe(hd.get("recommendation_code") or analysis.get("recommendation_code"))
    action = hd.get("suggested_next_action") or analysis.get("suggested_next_action")

    with st.container(border=True):
        st.markdown(
            "<div class='mpo-hd-title'>ТРЕБУЕТСЯ РЕШЕНИЕ ЧЕЛОВЕКА</div>",
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.caption("Статус проверки")
            st.markdown(f"**{validation_label(validation.get('status'))}**")
        with c2:
            st.caption("Основная причина")
            st.markdown(f"**{recommendation_label(rec)}**")
        with c3:
            st.caption("Следующее действие")
            st.markdown(f"**{action_label(action)}**")
        st.caption("Запись решений в этом экране недоступна.")


def _render_trace(run: dict[str, Any]) -> None:
    with st.expander("Техническая информация о запуске", expanded=False):
        m1, m2, m3 = st.columns(3)
        with m1:
            st.caption("run_id")
            st.code(_safe(run.get("run_id")) or "—")
            st.caption("project_code")
            st.code(_safe(run.get("project_code")) or "—")
        with m2:
            st.caption("started_at")
            st.code(_safe(run.get("started_at")) or "—")
            st.caption("month_key_input")
            st.code(_safe(run.get("month_key_input")) or "—")
        with m3:
            st.caption("finished_at")
            st.code(_safe(run.get("finished_at")) or "—")
            st.caption("month_key_canonical")
            st.code(_safe(run.get("month_key_canonical")) or "—")

        trace = run.get("trace") if isinstance(run.get("trace"), list) else []
        if trace:
            rows = []
            for event in trace:
                if not isinstance(event, dict):
                    continue
                rows.append(
                    {
                        "stage": event.get("stage"),
                        "duration_ms": event.get("duration_ms"),
                        "status": event.get("status"),
                        "tool": event.get("tool"),
                        "error": event.get("error"),
                    }
                )
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        gather = run.get("gather") if isinstance(run.get("gather"), dict) else {}
        if gather.get("sources") is not None:
            st.caption("sources")
            st.json(gather.get("sources"))

        hd = run.get("human_decision") if isinstance(run.get("human_decision"), dict) else {}
        evidence = hd.get("evidence") if isinstance(hd.get("evidence"), dict) else {}
        if evidence.get("source_trace") is not None:
            st.caption("source_trace")
            st.json(evidence.get("source_trace"))

        with st.expander("Сырой run (debug)", expanded=False):
            st.code(json.dumps(run, ensure_ascii=False, indent=2, default=str))


def _render_result(run: dict[str, Any]) -> None:
    failed = _safe(run.get("state")) == "FAILED"
    _render_stepper(run)
    st.write("")
    _render_status_card(run, failed=failed)
    st.write("")
    _render_kpi(run, failed=failed)
    if failed:
        _render_trace(run)
        return
    st.write("")
    findings = _findings_source(run)
    _render_findings_block(findings)
    _render_warnings_compact(run)
    st.write("")
    _render_human_decision(run)
    st.write("")
    _render_trace(run)


# ---------------------------------------------------------------------------
# Header + control bar
# ---------------------------------------------------------------------------
st.title("Оркестратор месячного плана")
st.caption("Детерминированный анализ выполнимости месячного обязательства")

labor_all = _load_labor_all()
projects = _project_options(labor_all)

ctrl1, ctrl2, ctrl3 = st.columns([1.6, 1.2, 1.0])
with ctrl1:
    project_sel = st.selectbox(
        "Проект",
        options=projects if projects else [""],
        index=0,
        key="mpo_cockpit_project",
        disabled=not bool(projects),
    )
month_pairs = _month_options_for_project(labor_all, project_sel) if project_sel else []
month_labels = [p[0] for p in month_pairs]
month_by_label = {p[0]: p[1] for p in month_pairs}
with ctrl2:
    month_label = st.selectbox(
        "Месяц",
        options=month_labels if month_labels else [""],
        index=0,
        key="mpo_cockpit_month",
        disabled=not bool(month_labels),
    )
month_raw = month_by_label.get(month_label, "") if month_label else ""
with ctrl3:
    st.markdown("<div style='height:1.55rem'></div>", unsafe_allow_html=True)
    run_clicked = st.button(
        "Запустить анализ",
        type="primary",
        use_container_width=True,
        disabled=not (project_sel and month_raw),
        key="mpo_cockpit_run_btn",
    )

if run_clicked and project_sel and month_raw:
    with st.spinner("Анализ…"):
        run_result = run_monthly_planning_orchestrator(
            project_code=project_sel,
            month_key=month_raw,
        )
    st.session_state[SS_LAST_RUN] = run_result
    st.session_state[SS_RUN_SCOPE] = {
        "project_code": project_sel,
        "month_key": month_raw,
    }

last_run = st.session_state.get(SS_LAST_RUN)
has_run = isinstance(last_run, dict)
scope_ok = has_run and _scope_matches(project_sel, month_raw)

if not has_run:
    st.info("Выберите проект и месяц, затем запустите анализ.")
elif not scope_ok:
    st.warning(
        "Параметры изменены. Запустите анализ заново для выбранного проекта и месяца."
    )
else:
    _render_result(last_run)
