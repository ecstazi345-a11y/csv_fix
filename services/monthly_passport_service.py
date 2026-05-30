"""
Формирование Approved Monthly Plan Passport после контура допуска.

Поток: Draft → Review Queue → Constraints → War Room → Passport → Week → Day
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, TypedDict

from dotenv import load_dotenv
from supabase import Client, create_client

from services.supabase_client import supabase

load_dotenv()

TABLE_QUEUE = "monthly_plan_review_queue"
TABLE_PASSPORTS = "monthly_plan_passports"
TABLE_PASSPORT_LINES = "monthly_plan_passport_lines"

CONSTRAINT_SOURCES = (
    "monthly_plan_constraints_dashboard_v2",
    "monthly_plan_constraints_dashboard_v1",
    "monthly_plan_constraints",
)

ELIGIBLE_REVIEW_STATUSES = ("SENT_TO_REVIEW", "ОЖИДАЕТ ПРОВЕРКИ", "APPROVED")

INCLUDED_STATUSES = frozenset(
    {"READY_WITH_RISK", "APPROVED_TO_EXECUTE", "APPROVED_BY_OVERRIDE"}
)

CHUNK_SIZE = 200


class PassportSummary(TypedDict):
    status: str
    passport_id: Optional[str]
    created_lines: int
    skipped_blocked: int
    blocked_without_override: int
    override_included_rows: int
    skipped_waiting: int
    total_value: float
    total_hours: float
    errors: List[str]


class ConstraintCounts(TypedDict):
    constraints_total: int
    constraints_pass: int
    constraints_warning: int
    constraints_hold: int
    constraints_fail: int
    constraints_waiting: int


def get_write_client() -> Optional[Client]:
    url = os.getenv("SUPABASE_URL")
    secret_key = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not secret_key:
        return None
    return create_client(url, secret_key)


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("true", "1", "yes", "t")


def _fetch_queue_rows(
    project_code: str,
    month_key: str,
    draft_id: Optional[str],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    errors: List[str] = []
    query = (
        supabase.table(TABLE_QUEUE)
        .select("*")
        .eq("project_code", project_code)
        .eq("month_key", month_key)
        .in_("review_status", list(ELIGIBLE_REVIEW_STATUSES))
    )
    if draft_id:
        query = query.eq("draft_id", draft_id)

    try:
        response = query.limit(10000).execute()
    except Exception as exc:  # noqa: BLE001
        return [], [f"Ошибка чтения {TABLE_QUEUE}: {exc}"]

    return list(response.data or []), errors


def _fetch_existing_approved_passport(
    client: Client,
    project_code: str,
    month_key: str,
    draft_id: Optional[str],
) -> Optional[str]:
    query = (
        client.table(TABLE_PASSPORTS)
        .select("passport_id")
        .eq("project_code", project_code)
        .eq("month_key", month_key)
        .eq("passport_status", "APPROVED")
    )
    if draft_id:
        query = query.eq("draft_id", draft_id)

    try:
        response = query.limit(1).execute()
    except Exception:  # noqa: BLE001
        return None

    rows = response.data or []
    if not rows:
        return None
    return str(rows[0].get("passport_id") or "")


def _fetch_constraints_for_lines(line_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """Загружает ограничения по line_id из dashboard v2 → v1 → таблицы."""
    unique_ids = [lid for lid in dict.fromkeys(line_ids) if lid]
    by_line: Dict[str, List[Dict[str, Any]]] = {lid: [] for lid in unique_ids}
    if not unique_ids:
        return by_line

    loaded = False
    for source in CONSTRAINT_SOURCES:
        try:
            for offset in range(0, len(unique_ids), CHUNK_SIZE):
                chunk = unique_ids[offset : offset + CHUNK_SIZE]
                response = (
                    supabase.table(source)
                    .select("line_id, check_status")
                    .in_("line_id", chunk)
                    .limit(10000)
                    .execute()
                )
                for row in response.data or []:
                    line_id = str(row.get("line_id") or "")
                    if line_id in by_line:
                        by_line[line_id].append(row)
            if any(by_line.values()):
                loaded = True
                break
        except Exception:  # noqa: BLE001
            continue

    if not loaded:
        return {lid: [] for lid in unique_ids}
    return by_line


def _count_constraints(rows: List[Dict[str, Any]]) -> ConstraintCounts:
    counts: ConstraintCounts = {
        "constraints_total": len(rows),
        "constraints_pass": 0,
        "constraints_warning": 0,
        "constraints_hold": 0,
        "constraints_fail": 0,
        "constraints_waiting": 0,
    }
    for row in rows:
        status = str(row.get("check_status") or "").strip().upper()
        if status == "PASS":
            counts["constraints_pass"] += 1
        elif status == "WARNING":
            counts["constraints_warning"] += 1
        elif status == "HOLD":
            counts["constraints_hold"] += 1
        elif status == "FAIL":
            counts["constraints_fail"] += 1
        elif status in ("ОЖИДАЕТ", "WAITING"):
            counts["constraints_waiting"] += 1
    return counts


def _resolve_admission_status(
    counts: ConstraintCounts,
    has_override: bool,
) -> str:
    """
    Правила допуска строки в Monthly Passport.

    Management Override =
    ручное управленческое решение о допуске строки несмотря на HOLD/FAIL.
    """
    total = counts["constraints_total"]

    if total == 0:
        return "NO_CHECKS"

    if counts["constraints_waiting"] > 0:
        return "WAITING_CHECKS"

    if counts["constraints_hold"] > 0 or counts["constraints_fail"] > 0:
        if has_override:
            return "APPROVED_BY_OVERRIDE"
        return "BLOCKED"

    if counts["constraints_warning"] > 0:
        return "READY_WITH_RISK"

    if counts["constraints_pass"] == total:
        return "APPROVED_TO_EXECUTE"

    return "WAITING_CHECKS"


def _read_override_from_queue(queue_row: Dict[str, Any]) -> Dict[str, Any]:
    """Читает поля override из строки очереди (если колонки уже есть в БД)."""
    return {
        "management_override": _safe_bool(queue_row.get("management_override")),
        "override_by": queue_row.get("override_by"),
        "override_at": queue_row.get("override_at"),
        "override_reason": queue_row.get("override_reason"),
        "override_risk_comment": queue_row.get("override_risk_comment"),
        "override_basis": queue_row.get("override_basis"),
    }


def _build_passport_line(
    passport_id: str,
    queue_row: Dict[str, Any],
    counts: ConstraintCounts,
    admission_status: str,
    override: Dict[str, Any],
) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    has_override = override.get("management_override") and admission_status == "APPROVED_BY_OVERRIDE"

    row: Dict[str, Any] = {
        "passport_id": passport_id,
        "draft_id": queue_row.get("draft_id"),
        "line_id": queue_row.get("line_id"),
        "review_id": queue_row.get("review_id") or queue_row.get("id"),
        "project_code": queue_row.get("project_code"),
        "month_key": queue_row.get("month_key"),
        "facility_building": queue_row.get("facility_building"),
        "construction_discipline": queue_row.get("construction_discipline"),
        "boq_code": queue_row.get("boq_code"),
        "boq_name": queue_row.get("boq_name"),
        "unit_of_measure": queue_row.get("unit_of_measure"),
        "crew_id": queue_row.get("crew_id"),
        "planned_qty": queue_row.get("planned_qty"),
        "unit_price": queue_row.get("unit_price"),
        "plan_value": queue_row.get("plan_value"),
        "required_hours": queue_row.get("required_hours"),
        "labor_rate_per_hour": queue_row.get("labor_rate_per_hour"),
        "labor_cost": queue_row.get("labor_cost"),
        "admission_status": admission_status,
        "constraints_total": counts["constraints_total"],
        "constraints_pass": counts["constraints_pass"],
        "constraints_warning": counts["constraints_warning"],
        "constraints_hold": counts["constraints_hold"],
        "constraints_fail": counts["constraints_fail"],
        "week_plan_status": "NOT_DECOMPOSED",
        "comment": queue_row.get("comment"),
        "management_override": has_override,
        "override_by": override.get("override_by") if has_override else None,
        "override_at": override.get("override_at") or (now_iso if has_override else None),
        "override_reason": override.get("override_reason") if has_override else None,
        "override_risk_comment": override.get("override_risk_comment") if has_override else None,
        "override_basis": override.get("override_basis") if has_override else None,
    }
    return row


def _insert_lines_batch(client: Client, rows: List[Dict[str, Any]]) -> Optional[str]:
    if not rows:
        return None
    try:
        client.table(TABLE_PASSPORT_LINES).insert(rows).execute()
        return None
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        override_fields = (
            "management_override",
            "override_by",
            "override_at",
            "override_reason",
            "override_risk_comment",
            "override_basis",
        )
        if not any(field in msg for field in override_fields):
            return str(exc)
        slim_rows = [
            {k: v for k, v in row.items() if k not in override_fields}
            for row in rows
        ]
        try:
            client.table(TABLE_PASSPORT_LINES).insert(slim_rows).execute()
            return None
        except Exception as retry_exc:  # noqa: BLE001
            return str(retry_exc)


def create_monthly_passport(
    project_code: str,
    month_key: str,
    draft_id: Optional[str] = None,
    created_by: str = "Пользователь Streamlit",
) -> PassportSummary:
    """
    Формирует Approved Monthly Plan Passport из очереди допуска и ограничений.

    Включает строки со статусами READY_WITH_RISK, APPROVED_TO_EXECUTE,
    APPROVED_BY_OVERRIDE (Management Override).
    """
    summary: PassportSummary = {
        "status": "error",
        "passport_id": None,
        "created_lines": 0,
        "skipped_blocked": 0,
        "blocked_without_override": 0,
        "override_included_rows": 0,
        "skipped_waiting": 0,
        "total_value": 0.0,
        "total_hours": 0.0,
        "errors": [],
    }

    write_client = get_write_client()
    if write_client is None:
        summary["errors"].append(
            "SUPABASE_SECRET_KEY не задан в .env — запись в monthly_plan_passports недоступна."
        )
        return summary

    existing_id = _fetch_existing_approved_passport(
        write_client, project_code, month_key, draft_id
    )
    if existing_id:
        summary["status"] = "already_exists"
        summary["passport_id"] = existing_id
        return summary

    queue_rows, read_errors = _fetch_queue_rows(project_code, month_key, draft_id)
    summary["errors"].extend(read_errors)
    if not queue_rows:
        summary["status"] = "no_source_rows"
        summary["errors"].append(
            f"Нет строк в {TABLE_QUEUE} для project_code={project_code}, month_key={month_key}."
        )
        return summary

    line_ids = [str(r.get("line_id")) for r in queue_rows if r.get("line_id")]
    constraints_by_line = _fetch_constraints_for_lines(line_ids)

    admission_counts = {
        "total_source_rows": len(queue_rows),
        "included_rows": 0,
        "blocked_rows": 0,
        "blocked_without_override": 0,
        "override_included_rows": 0,
        "waiting_rows": 0,
        "ready_with_risk_rows": 0,
        "approved_to_execute_rows": 0,
    }

    lines_to_insert: List[Dict[str, Any]] = []
    resolved_draft_id = draft_id or queue_rows[0].get("draft_id")

    for queue_row in queue_rows:
        line_id = str(queue_row.get("line_id") or "")
        constraint_rows = constraints_by_line.get(line_id, [])
        counts = _count_constraints(constraint_rows)
        override = _read_override_from_queue(queue_row)
        admission_status = _resolve_admission_status(counts, override["management_override"])

        if admission_status == "BLOCKED":
            admission_counts["blocked_rows"] += 1
            if not override["management_override"]:
                admission_counts["blocked_without_override"] += 1
            summary["skipped_blocked"] += 1
            continue

        if admission_status == "WAITING_CHECKS":
            admission_counts["waiting_rows"] += 1
            summary["skipped_waiting"] += 1
            continue

        if admission_status == "NO_CHECKS":
            continue

        if admission_status not in INCLUDED_STATUSES:
            summary["skipped_blocked"] += 1
            continue

        if admission_status == "APPROVED_BY_OVERRIDE":
            admission_counts["override_included_rows"] += 1
            summary["override_included_rows"] += 1
        elif admission_status == "READY_WITH_RISK":
            admission_counts["ready_with_risk_rows"] += 1
        elif admission_status == "APPROVED_TO_EXECUTE":
            admission_counts["approved_to_execute_rows"] += 1

        admission_counts["included_rows"] += 1
        lines_to_insert.append(
            {
                "_queue_row": queue_row,
                "_counts": counts,
                "_admission_status": admission_status,
                "_override": override,
            }
        )

    if not lines_to_insert:
        summary["status"] = "no_eligible_lines"
        summary["errors"].append(
            "Нет строк, допущенных в паспорт: все BLOCKED / WAITING_CHECKS / NO_CHECKS."
        )
        return summary

    total_value = sum(
        _safe_float(item["_queue_row"].get("plan_value")) for item in lines_to_insert
    )
    total_hours = sum(
        _safe_float(item["_queue_row"].get("required_hours")) for item in lines_to_insert
    )

    now_iso = datetime.now(timezone.utc).isoformat()
    passport_name = f"Monthly Plan Passport | {project_code} | {month_key}"

    passport_header: Dict[str, Any] = {
        "draft_id": resolved_draft_id,
        "project_code": project_code,
        "month_key": month_key,
        "passport_status": "APPROVED",
        "passport_name": passport_name,
        "created_by": created_by,
        "approved_by": created_by,
        "approved_at": now_iso,
        "total_plan_value": total_value,
        "total_required_hours": total_hours,
        "total_labor_cost": sum(
            _safe_float(item["_queue_row"].get("labor_cost")) for item in lines_to_insert
        ),
        "rows_count": len(lines_to_insert),
        "admission_summary": admission_counts,
    }

    try:
        insert_resp = write_client.table(TABLE_PASSPORTS).insert(passport_header).execute()
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append(f"Ошибка insert {TABLE_PASSPORTS}: {exc}")
        return summary

    inserted = insert_resp.data or []
    if not inserted:
        summary["errors"].append("Insert паспорта не вернул passport_id.")
        return summary

    passport_id = str(inserted[0].get("passport_id") or "")
    summary["passport_id"] = passport_id

    payload_rows = [
        _build_passport_line(
            passport_id=passport_id,
            queue_row=item["_queue_row"],
            counts=item["_counts"],
            admission_status=item["_admission_status"],
            override=item["_override"],
        )
        for item in lines_to_insert
    ]

    for offset in range(0, len(payload_rows), CHUNK_SIZE):
        batch = payload_rows[offset : offset + CHUNK_SIZE]
        err = _insert_lines_batch(write_client, batch)
        if err:
            summary["errors"].append(
                f"Ошибка insert строк паспорта (batch {offset // CHUNK_SIZE + 1}): {err}"
            )
        else:
            summary["created_lines"] += len(batch)

    if summary["created_lines"] == 0:
        summary["status"] = "error"
        return summary

    summary["status"] = "created"
    summary["total_value"] = total_value
    summary["total_hours"] = total_hours
    summary["blocked_without_override"] = admission_counts["blocked_without_override"]
    return summary
