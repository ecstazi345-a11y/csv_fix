"""
Durable management decisions for War Room (Page 23) — R1.

Table: public.monthly_plan_management_decisions
RPC:   apply_monthly_plan_management_decision
       cancel_monthly_plan_management_decision

DB stores English decision codes. Page 23 UI uses Russian labels.
This module owns the EN↔RU mapping and SoT load/apply/cancel.

Does not write passport / constraints / plan lines.
Does not import Page 23.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client

from services.supabase_client import supabase

load_dotenv()

TABLE = "monthly_plan_management_decisions"
RPC_APPLY = "apply_monthly_plan_management_decision"
RPC_CANCEL = "cancel_monthly_plan_management_decision"

DECISION_INCLUDE = "INCLUDE"
DECISION_INCLUDE_RISK = "INCLUDE_RISK"
DECISION_EXCLUDE = "EXCLUDE"
DECISION_DEFER = "DEFER"

DECISION_CODES = frozenset(
    {
        DECISION_INCLUDE,
        DECISION_INCLUDE_RISK,
        DECISION_EXCLUDE,
        DECISION_DEFER,
    }
)

# Page 23 session / UI labels (WR2_MGMT_*)
DECISION_RU_INCLUDE = "Включить в паспорт"
DECISION_RU_INCLUDE_RISK = "Включить с риском"
DECISION_RU_EXCLUDE = "Исключить"
DECISION_RU_DEFER = "Отложить"
DECISION_RU_DEFER_LONG = "Отложить рассмотрение"

DECISION_EN_TO_RU: dict[str, str] = {
    DECISION_INCLUDE: DECISION_RU_INCLUDE,
    DECISION_INCLUDE_RISK: DECISION_RU_INCLUDE_RISK,
    DECISION_EXCLUDE: DECISION_RU_EXCLUDE,
    DECISION_DEFER: DECISION_RU_DEFER,
}

DECISION_RU_TO_EN: dict[str, str] = {
    DECISION_RU_INCLUDE: DECISION_INCLUDE,
    DECISION_RU_INCLUDE_RISK: DECISION_INCLUDE_RISK,
    DECISION_RU_EXCLUDE: DECISION_EXCLUDE,
    DECISION_RU_DEFER: DECISION_DEFER,
    DECISION_RU_DEFER_LONG: DECISION_DEFER,
    # Also accept English as already-normalized
    DECISION_INCLUDE: DECISION_INCLUDE,
    DECISION_INCLUDE_RISK: DECISION_INCLUDE_RISK,
    DECISION_EXCLUDE: DECISION_EXCLUDE,
    DECISION_DEFER: DECISION_DEFER,
}

STATUS_ACTIVE = "ACTIVE"
STATUS_CANCELLED = "CANCELLED"

SELECT_COLS = (
    "decision_id,project_code,month_key,plan_line_id,"
    "boq_code,boq_name,facility_building,construction_discipline,"
    "decision,decision_status,"
    "admission_outcome_at_decision,management_override,"
    "decision_basis,decision_comment,responsible_person,review_deadline,"
    "risk_description,risk_impact,risk_mitigation_owner,risk_mitigation_deadline,"
    "risk_acceptance_basis,risk_manager_comment,risk_blocker,"
    "decided_by,decided_at,updated_by,updated_at,source_page,created_at"
)


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "none", "nan", "nat", "<na>"}:
        return ""
    return text


def normalize_decision_code(decision: Any) -> str:
    """Map RU UI label or EN code → EN DB code. Empty if unknown."""
    raw = safe_text(decision)
    if not raw:
        return ""
    upper = raw.upper()
    if upper in DECISION_CODES:
        return upper
    return DECISION_RU_TO_EN.get(raw, "")


def decision_to_ru(decision: Any) -> str:
    code = normalize_decision_code(decision)
    return DECISION_EN_TO_RU.get(code, safe_text(decision))


def _is_concrete_scope(project_code: Any, month_key: Any) -> bool:
    project = safe_text(project_code)
    month = safe_text(month_key)
    if not project or not month:
        return False
    if project == "Все" or month == "Все":
        return False
    return True


def get_write_client() -> Optional[Client]:
    secret_key = os.getenv("SUPABASE_SECRET_KEY")
    url = os.getenv("SUPABASE_URL")
    if not secret_key or not url:
        return None
    return create_client(url, secret_key)


def _rpc_client() -> Client:
    """Prefer service role for writes; anon is also granted EXECUTE on R1 RPCs."""
    write = get_write_client()
    return write if write is not None else supabase


def _normalize_rpc_data(data: Any) -> dict[str, Any]:
    if isinstance(data, list) and len(data) == 1:
        data = data[0]
    if isinstance(data, dict):
        return data
    return {"raw": data}


def _normalize_rpc_error(exc: BaseException, *, rpc_name: str) -> str:
    raw = safe_text(getattr(exc, "message", None) or str(exc))
    # PostgREST often wraps: {'message': '...', 'code': 'P0001', ...}
    if "message" in raw and rpc_name in raw:
        try:
            # keep readable fragment
            marker = f"{rpc_name}:"
            if marker in raw:
                return raw.split(marker, 1)[-1].strip().strip("'\"}") or raw
        except Exception:  # noqa: BLE001
            pass
    if f"{rpc_name}:" in raw:
        return raw.split(f"{rpc_name}:", 1)[-1].strip() or raw
    return raw


def _result_ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def _result_err(error: str) -> dict[str, Any]:
    return {"ok": False, "data": None, "error": error}


def _validate_apply_inputs(
    *,
    project_code: Any,
    month_key: Any,
    plan_line_id: Any,
    decision: Any,
    decided_by: Any,
    payload: dict[str, Any],
) -> tuple[Optional[str], str, dict[str, Any]]:
    """Returns (error, en_decision, payload) — error is None when valid."""
    if not _is_concrete_scope(project_code, month_key):
        return "Укажите конкретный project_code и month_key (не «Все»)", "", {}
    pid = safe_text(plan_line_id)
    if not pid:
        return "Не указан plan_line_id", "", {}
    code = normalize_decision_code(decision)
    if not code:
        return f"Некорректное решение: {safe_text(decision)}", "", {}
    actor = safe_text(decided_by)
    if not actor:
        return "Не указан decided_by", "", {}

    basis = safe_text(payload.get("decision_basis"))
    comment = safe_text(payload.get("decision_comment"))
    responsible = safe_text(payload.get("responsible_person"))
    review_deadline = safe_text(payload.get("review_deadline"))
    if not basis:
        return "Не указано основание решения (decision_basis)", "", {}
    if not responsible:
        return "Не указан ответственный (responsible_person)", "", {}
    # review_deadline and decision_comment are optional (empty → null in RPC payload).

    if code == DECISION_INCLUDE_RISK:
        required_risk = (
            "risk_description",
            "risk_impact",
            "risk_mitigation_owner",
            "risk_mitigation_deadline",
            "risk_acceptance_basis",
            "risk_manager_comment",
        )
        for key in required_risk:
            if not safe_text(payload.get(key)):
                return f"Для INCLUDE_RISK обязательно поле {key}", "", {}

    clean_payload = dict(payload)
    clean_payload["decision_basis"] = basis
    clean_payload["decision_comment"] = comment
    clean_payload["responsible_person"] = responsible
    clean_payload["review_deadline"] = review_deadline
    return None, code, clean_payload


@st.cache_data(ttl=300, show_spinner=False)
def load_management_decisions(project_code: str, month_key: str) -> list[dict[str, Any]]:
    """
    Load ACTIVE management decisions for one concrete project+month.

    Rejects Project/Month = «Все» or empty → [].
    Single filtered SELECT (no N+1).
    """
    if not _is_concrete_scope(project_code, month_key):
        return []

    project = safe_text(project_code)
    month = safe_text(month_key)
    response = (
        supabase.table(TABLE)
        .select(SELECT_COLS)
        .eq("project_code", project)
        .eq("month_key", month)
        .eq("decision_status", STATUS_ACTIVE)
        .order("decided_at", desc=True)
        .limit(5000)
        .execute()
    )
    rows = list(response.data or [])
    # Defense in depth: never return CANCELLED even if filter drifts
    return [
        row
        for row in rows
        if safe_text(row.get("decision_status")).upper() == STATUS_ACTIVE
    ]


def clear_management_decisions_cache() -> bool:
    """Invalidate load_management_decisions cache."""
    try:
        load_management_decisions.clear()
        return True
    except Exception:  # noqa: BLE001
        return False


def apply_management_decision(
    *,
    project_code: str,
    month_key: str,
    plan_line_id: str,
    decision: str,
    decided_by: str,
    payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Call RPC apply_monthly_plan_management_decision.

    decision: EN code or RU UI label.
    payload: decision_basis, decision_comment, responsible_person, review_deadline,
             risk_* fields, boq_*, admission_outcome_at_decision, etc.

    Returns: {"ok": bool, "data": dict | None, "error": str | None}
    """
    err, code, clean_payload = _validate_apply_inputs(
        project_code=project_code,
        month_key=month_key,
        plan_line_id=plan_line_id,
        decision=decision,
        decided_by=decided_by,
        payload=dict(payload or {}),
    )
    if err:
        return _result_err(err)

    rpc_payload = {
        "p_project_code": safe_text(project_code),
        "p_month_key": safe_text(month_key),
        "p_plan_line_id": safe_text(plan_line_id),
        "p_decision": code,
        "p_decided_by": safe_text(decided_by),
        "p_payload": clean_payload,
    }

    try:
        response = _rpc_client().rpc(RPC_APPLY, rpc_payload).execute()
        data = _normalize_rpc_data(response.data)
        clear_management_decisions_cache()
        return _result_ok(data)
    except Exception as exc:  # noqa: BLE001
        return _result_err(_normalize_rpc_error(exc, rpc_name=RPC_APPLY))


def cancel_management_decision(
    *,
    project_code: str,
    month_key: str,
    plan_line_id: str,
    cancelled_by: str,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """
    Call RPC cancel_monthly_plan_management_decision (idempotent).

    Returns ok=True for status cancelled | already_cancelled | not_found
    (not_found is soft-success for UI clear paths).
    """
    if not _is_concrete_scope(project_code, month_key):
        return _result_err("Укажите конкретный project_code и month_key (не «Все»)")
    pid = safe_text(plan_line_id)
    if not pid:
        return _result_err("Не указан plan_line_id")
    actor = safe_text(cancelled_by)
    if not actor:
        return _result_err("Не указан cancelled_by")

    rpc_payload = {
        "p_project_code": safe_text(project_code),
        "p_month_key": safe_text(month_key),
        "p_plan_line_id": pid,
        "p_cancelled_by": actor,
        "p_reason": safe_text(reason) or None,
    }

    try:
        response = _rpc_client().rpc(RPC_CANCEL, rpc_payload).execute()
        data = _normalize_rpc_data(response.data)
        clear_management_decisions_cache()
        status = safe_text(data.get("status"))
        if status in {"cancelled", "already_cancelled", "not_found"}:
            return _result_ok(data)
        return _result_ok(data)
    except Exception as exc:  # noqa: BLE001
        return _result_err(_normalize_rpc_error(exc, rpc_name=RPC_CANCEL))


def delete_test_mgmt_rows(*, project_code: str = "TEST_MGMT") -> dict[str, Any]:
    """
    Hard-delete TEST_MGMT fixture rows via service_role (cleanup only).
    Never call with product project_code.
    """
    project = safe_text(project_code)
    if project != "TEST_MGMT":
        return _result_err("delete_test_mgmt_rows разрешён только для TEST_MGMT")
    client = get_write_client()
    if client is None:
        return _result_err("Нет SUPABASE_SECRET_KEY — cleanup delete недоступен")
    try:
        response = (
            client.table(TABLE)
            .delete()
            .eq("project_code", "TEST_MGMT")
            .execute()
        )
        clear_management_decisions_cache()
        return _result_ok({"deleted": response.data or []})
    except Exception as exc:  # noqa: BLE001
        return _result_err(safe_text(exc))
