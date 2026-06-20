"""Production pipeline корректировок scope (v1). Источник: pages/10_Planning_Конструктор_месячного_плана.py"""

from __future__ import annotations

from typing import Any

import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from supabase import Client, create_client

from services.supabase_client import supabase

SCOPE_VIEW = "monthly_scope_picker_view"
ADJUSTMENTS_TABLE = "monthly_scope_manual_adjustments"


def safe_float(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@st.cache_resource
def get_supabase_write_client() -> Client | None:
    url = os.getenv("SUPABASE_URL")
    secret_key = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not secret_key:
        return None
    return create_client(url, secret_key)


@st.cache_data(ttl=300)
def load_scope(limit: int = 10000) -> pd.DataFrame:
    response = supabase.table(SCOPE_VIEW).select("*").limit(limit).execute()
    return pd.DataFrame(response.data or [])


@st.cache_data(ttl=120)
def load_adjustments(limit: int = 10000) -> pd.DataFrame:
    """Anon key may be blocked by RLS — fallback to write client (service role)."""
    client = get_supabase_write_client() or supabase
    try:
        response = client.table(ADJUSTMENTS_TABLE).select("*").limit(limit).execute()
        return pd.DataFrame(response.data or [])
    except Exception:
        return pd.DataFrame()


def fetch_all_adjustments_history(limit: int = 10000) -> pd.DataFrame:
    """Все ручные корректировки из monthly_scope_manual_adjustments."""
    client = get_supabase_write_client() or supabase
    try:
        response = (
            client.table(ADJUSTMENTS_TABLE)
            .select("*")
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )
        return pd.DataFrame(response.data or [])
    except Exception:
        return pd.DataFrame()


def fetch_adjustments_history_for_boq(
    project_code: str,
    facility_building: str,
    construction_discipline: str,
    boq_code: str,
) -> pd.DataFrame:
    """История корректировок по ключу BOQ (history-ready, сейчас ≤1 запись из-за upsert)."""
    client = get_supabase_write_client() or supabase
    try:
        response = (
            client.table(ADJUSTMENTS_TABLE)
            .select("*")
            .eq("project_code", project_code)
            .eq("facility_building", facility_building)
            .eq("construction_discipline", construction_discipline)
            .eq("boq_code", boq_code)
            .order("updated_at", desc=True)
            .execute()
        )
        return pd.DataFrame(response.data or [])
    except Exception:
        return pd.DataFrame()


def delete_adjustment(row: pd.Series) -> None:
    """Удалить корректировку по ключу BOQ (только одна строка)."""
    write_client = get_supabase_write_client()
    if write_client is None:
        raise RuntimeError(
            "SUPABASE_SECRET_KEY не задан в .env — удаление корректировок недоступно."
        )
    project_code = str(row.get("project_code", "")).strip()
    facility_building = str(row.get("facility_building") or "").strip()
    construction_discipline = str(row.get("construction_discipline") or "").strip()
    boq_code = str(row.get("boq_code", "")).strip().upper()
    if not all([project_code, facility_building, construction_discipline, boq_code]):
        raise ValueError("Неполный ключ BOQ для удаления корректировки.")
    resp = (
        write_client.table(ADJUSTMENTS_TABLE)
        .delete()
        .eq("project_code", project_code)
        .eq("facility_building", facility_building)
        .eq("construction_discipline", construction_discipline)
        .eq("boq_code", boq_code)
        .execute()
    )
    if getattr(resp, "error", None):
        raise RuntimeError(f"Supabase delete error: {resp.error}")


def adjustments_support_not_required_columns() -> bool:
    """Проверка наличия колонок исключения остатка в Supabase."""
    client = get_supabase_write_client() or supabase
    try:
        client.table(ADJUSTMENTS_TABLE).select("not_required_qty").limit(1).execute()
        return True
    except Exception:
        return False


def _fetch_adjustment_row_for_boq(
    project_code: str,
    facility_building: str,
    construction_discipline: str,
    boq_code: str,
) -> dict[str, Any]:
    df = fetch_adjustments_history_for_boq(
        project_code,
        facility_building,
        construction_discipline,
        boq_code,
    )
    if df.empty:
        return {}
    return df.iloc[0].to_dict()


def save_not_required_exclusion(
    row: pd.Series,
    not_required_qty: float,
    reason: str,
    responsible_person: str,
    comment: str,
):
    """Сохранить исключение остатка, не затирая manual_executed_before_system."""
    if not adjustments_support_not_required_columns():
        raise RuntimeError(
            "В Supabase отсутствуют колонки not_required_*. "
            "Выполните sql/monthly_scope_not_required_exclusion.sql"
        )
    write_client = get_supabase_write_client()
    if write_client is None:
        raise RuntimeError(
            "SUPABASE_SECRET_KEY не задан в .env — запись корректировок недоступна."
        )
    project_code = str(row.get("project_code", "")).strip()
    facility_building = str(row.get("facility_building") or "").strip()
    construction_discipline = str(row.get("construction_discipline") or "").strip()
    boq_code = str(row.get("boq_code", "")).strip().upper()
    existing = _fetch_adjustment_row_for_boq(
        project_code,
        facility_building,
        construction_discipline,
        boq_code,
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "project_code": project_code,
        "facility_building": facility_building,
        "construction_discipline": construction_discipline,
        "boq_code": boq_code,
        "manual_executed_before_system": safe_float(existing.get("manual_executed_before_system")),
        "manual_verified_remaining_qty": safe_float(existing.get("manual_verified_remaining_qty")),
        "reason": existing.get("reason"),
        "comment": existing.get("comment"),
        "updated_by": existing.get("updated_by"),
        "not_required_qty": safe_float(not_required_qty) or 0.0,
        "not_required_reason": reason.strip() if reason else None,
        "not_required_responsible_person": responsible_person.strip() if responsible_person else None,
        "not_required_comment": comment.strip() if comment else None,
        "not_required_updated_at": now_iso,
        "updated_at": now_iso,
    }
    resp = write_client.table(ADJUSTMENTS_TABLE).upsert(
        payload,
        on_conflict="project_code,facility_building,construction_discipline,boq_code",
    ).execute()
    if getattr(resp, "error", None):
        raise RuntimeError(f"Supabase upsert error: {resp.error}")
    return resp


def save_adjustment(
    row: pd.Series,
    manual_exec,
    manual_verified,
    reason: str,
    comment: str,
    *,
    updated_by: str | None = None,
):
    write_client = get_supabase_write_client()
    if write_client is None:
        raise RuntimeError(
            "SUPABASE_SECRET_KEY не задан в .env — запись корректировок недоступна."
        )
    project_code = str(row.get("project_code", "")).strip()
    facility_building = str(row.get("facility_building") or "").strip()
    construction_discipline = str(row.get("construction_discipline") or "").strip()
    boq_code = str(row.get("boq_code", "")).strip().upper()
    existing = _fetch_adjustment_row_for_boq(
        project_code,
        facility_building,
        construction_discipline,
        boq_code,
    )
    payload = {
        "project_code": project_code,
        "facility_building": facility_building,
        "construction_discipline": construction_discipline,
        "boq_code": boq_code,
        "manual_executed_before_system": safe_float(manual_exec),
        "manual_verified_remaining_qty": safe_float(manual_verified),
        "reason": reason.strip() if reason else None,
        "comment": comment.strip() if comment else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    responsible = str(updated_by or "").strip()
    if responsible:
        payload["updated_by"] = responsible
    if adjustments_support_not_required_columns():
        payload.update(
            {
                "not_required_qty": safe_float(existing.get("not_required_qty")) or 0.0,
                "not_required_reason": existing.get("not_required_reason"),
                "not_required_responsible_person": existing.get("not_required_responsible_person"),
                "not_required_comment": existing.get("not_required_comment"),
                "not_required_updated_at": existing.get("not_required_updated_at"),
            }
        )
    resp = write_client.table(ADJUSTMENTS_TABLE).upsert(
        payload,
        on_conflict="project_code,facility_building,construction_discipline,boq_code",
    ).execute()
    if getattr(resp, "error", None):
        raise RuntimeError(f"Supabase upsert error: {resp.error}")
    return resp
