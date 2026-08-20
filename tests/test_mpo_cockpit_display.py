"""Pure display helpers for MPO-004A Agent Cockpit."""

from __future__ import annotations

from services.mpo_cockpit_display import (
    ACTION_RU,
    FINDING_RU,
    RECOMMENDATION_RU,
    STATUS_HEADLINE_RU,
    action_label,
    finding_compact_line,
    finding_label,
    format_kpi_value,
    prioritize_findings,
    recommendation_label,
    run_matches_scope,
    status_headline,
    step_statuses,
    validation_label,
)


REQUIRED_RECS = {
    "READY_FOR_HUMAN_DECISION",
    "READY_WITH_WARNINGS",
    "RESOURCE_DEFICIT",
    "ADMISSION_BLOCKED",
    "MIXED_CONDITION",
    "NOT_READY_DATA_GAPS",
}

REQUIRED_ACTIONS = {
    "REVIEW_PLAN",
    "REVIEW_ADMISSION",
    "REVIEW_RESOURCE_PLAN",
    "FIX_DATA_QUALITY",
    "WAIT_NOT_REQUIRED_LAYER",
}

REQUIRED_FINDINGS = {
    "CAPACITY_DATA_MISSING",
    "RESOURCE_DEFICIT",
    "ADMISSION_BLOCKED",
    "scope_remaining_not_joined",
    "not_required_adjustments_not_applied",
    "scope_read_failed",
    "no_plan_lines",
    "completed_boq_still_requested",
    "admission_status_unavailable",
}


def test_recommendation_mapping_covers_all_codes():
    assert REQUIRED_RECS <= set(RECOMMENDATION_RU)
    assert REQUIRED_RECS <= set(STATUS_HEADLINE_RU)
    assert recommendation_label("ADMISSION_BLOCKED") == "Есть блокирующий допуск"
    assert status_headline("ADMISSION_BLOCKED") == "МЕСЯЧНЫЙ ПЛАН ТРЕБУЕТ РЕШЕНИЯ"


def test_action_mapping_covers_all_codes():
    assert REQUIRED_ACTIONS <= set(ACTION_RU)
    assert action_label("REVIEW_ADMISSION") == "Проверить и снять блокирующие допуски"
    assert action_label("REVIEW_PLAN") == "Пересмотреть месячное обязательство"


def test_finding_mapping_min_spec():
    assert REQUIRED_FINDINGS <= set(FINDING_RU)
    assert finding_label("scope_remaining_not_joined") == "Остаток BOQ требует проверки"
    assert finding_label("weird_new_code") == "weird_new_code"


def test_validation_labels():
    assert validation_label("PASS") == "Пройдено"
    assert validation_label("PASS_WITH_WARNINGS") == "С предупреждениями"
    assert validation_label("BLOCKED") == "Недостаточно данных"


def test_none_kpi_is_net_dannykh_not_zero():
    assert format_kpi_value(None) == "Нет данных"
    assert format_kpi_value(None, kind="coverage") == "Нет данных"
    assert format_kpi_value(None, kind="hours") == "Нет данных"
    assert format_kpi_value(0, kind="int") == "0"
    assert format_kpi_value(0.0, kind="hours") == "0"
    assert format_kpi_value(11773, kind="int") == "11 773"
    assert format_kpi_value(0.79, kind="coverage") == "79 %"


def test_findings_priority_and_compact_line():
    findings = [
        {"code": "no_plan_lines", "severity": "INFO", "count": 1},
        {"code": "scope_remaining_not_joined", "severity": "WARNING", "count": 16},
        {"code": "ADMISSION_BLOCKED", "severity": "BLOCKER", "count": 12},
    ]
    top = prioritize_findings(findings, limit=5)
    assert [f["code"] for f in top] == [
        "ADMISSION_BLOCKED",
        "scope_remaining_not_joined",
        "no_plan_lines",
    ]
    assert finding_compact_line(top[0]) == "🔴 Блокирующий допуск — 12 строк"


def test_failed_fixture_stepper_does_not_mark_later_done():
    run = {
        "state": "FAILED",
        "trace": [{"stage": "GATHER", "status": "ERROR"}],
        "analysis": None,
        "snapshot": None,
        "human_decision": None,
        "error": {"code": "X", "message": "boom"},
    }
    steps = step_statuses(run)
    assert steps[0]["ui"] == "error"
    assert all(s["ui"] != "done" for s in steps[1:])


def test_human_decision_fixture_stepper():
    run = {
        "state": "HUMAN_DECISION",
        "trace": [
            {"stage": "GATHER", "status": "OK"},
            {"stage": "ANALYZE", "status": "OK"},
            {"stage": "VALIDATE", "status": "OK"},
            {"stage": "HUMAN_DECISION", "status": "OK"},
        ],
    }
    steps = step_statuses(run)
    assert [s["ui"] for s in steps] == ["done", "done", "done", "current"]
    assert all("GATHER" not in s["label"] for s in steps)


def test_stale_scope_detection():
    run = {"project_code": "P1", "month_key_input": "август-2026"}
    assert run_matches_scope(run, "P1", "август-2026")
    assert not run_matches_scope(run, "P1", "июль-2026")


def test_pre_run_stepper_is_pending():
    steps = step_statuses(None)
    assert all(s["ui"] == "pending" for s in steps)
