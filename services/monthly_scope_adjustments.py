"""Production pipeline корректировок scope (v1). Источник: pages/10_Planning_Конструктор_месячного_плана.py"""

from __future__ import annotations

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


def save_adjustment(row: pd.Series, manual_exec, manual_verified, reason: str, comment: str):
    write_client = get_supabase_write_client()
    if write_client is None:
        raise RuntimeError(
            "SUPABASE_SECRET_KEY не задан в .env — запись корректировок недоступна."
        )
    payload = {
        "project_code": str(row.get("project_code", "")).strip(),
        "facility_building": str(row.get("facility_building") or "").strip(),
        "construction_discipline": str(row.get("construction_discipline") or "").strip(),
        "boq_code": str(row.get("boq_code", "")).strip().upper(),
        "manual_executed_before_system": safe_float(manual_exec),
        "manual_verified_remaining_qty": safe_float(manual_verified),
        "reason": reason.strip() if reason else None,
        "comment": comment.strip() if comment else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = write_client.table(ADJUSTMENTS_TABLE).upsert(
        payload,
        on_conflict="project_code,facility_building,construction_discipline,boq_code",
    ).execute()
    if getattr(resp, "error", None):
        raise RuntimeError(f"Supabase upsert error: {resp.error}")
    return resp
