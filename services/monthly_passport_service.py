"""
Формирование Approved Monthly Plan Passport после контура допуска.

Поток: Plan Lines v2 (primary) / Review Queue (legacy fallback)
     → Constraints → War Room → Passport → Week → Day

Release 1 (cumulative working passport):
- one active passport per project_code + month_key;
- rebuild keeps the same passport_id and atomically replaces lines via RPC;
- APPROVED means ACTIVE WORKING PASSPORT (rebuildable); CLOSE/LOCK later;
- revision/history is not stored (R2);
- Page 12 / Excel only read current lines and do not finalize or lock the passport.
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
TABLE_PLAN_LINES_V2 = "monthly_plan_lines_v2"
TABLE_PASSPORTS = "monthly_plan_passports"
TABLE_PASSPORT_LINES = "monthly_plan_passport_lines"

_raw_passport_source_mode = os.getenv("PASSPORT_SOURCE_MODE", "v2_primary").strip().lower()
PASSPORT_SOURCE_MODE = (
    _raw_passport_source_mode
    if _raw_passport_source_mode in ("v2_primary", "queue_only")
    else "v2_primary"
)

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


class PassportSummary(TypedDict, total=False):
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
    source_kind: Optional[str]
    previous_rows: int
    current_rows: int
    added_count: int
    removed_count: int
    updated_count: int


RPC_REPLACE_MONTHLY_PASSPORT = "replace_monthly_passport"
PLACEHOLDER_PASSPORT_ID = "00000000-0000-0000-0000-000000000000"


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


def _fetch_v2_plan_lines(
    client: Any,
    project_code: str,
    month_key: str,
) -> List[Dict[str, Any]]:
    response = (
        client.table(TABLE_PLAN_LINES_V2)
        .select("*")
        .eq("project_code", project_code)
        .eq("month_key", month_key)
        .eq("status", "SENT_TO_ADMISSION")
        .limit(10000)
        .execute()
    )
    return list(response.data or [])


def _map_v2_row_to_passport_source_row(v2_row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    plan_line_id = str(v2_row.get("plan_line_id") or "").strip()
    if not plan_line_id:
        return None
    return {
        "source_kind": "v2",
        "line_id": plan_line_id,
        "draft_id": None,
        "review_id": None,
        "project_code": v2_row.get("project_code"),
        "month_key": v2_row.get("month_key"),
        "facility_building": v2_row.get("facility"),
        "construction_discipline": v2_row.get("discipline"),
        "boq_code": v2_row.get("boq_code"),
        "boq_name": v2_row.get("boq_name"),
        "unit_of_measure": v2_row.get("unit"),
        "crew_id": v2_row.get("crew"),
        "planned_qty": v2_row.get("planned_qty"),
        "unit_price": v2_row.get("unit_price"),
        "plan_value": v2_row.get("plan_value"),
        "required_hours": v2_row.get("labor_hours"),
        "labor_rate_per_hour": v2_row.get("labor_rate_per_hour"),
        "labor_cost": v2_row.get("labor_cost"),
        "comment": None,
        "management_override": False,
        "override_by": None,
        "override_at": None,
        "override_reason": None,
        "override_risk_comment": None,
        "override_basis": None,
    }


def _map_queue_row_to_passport_source_row(queue_row: Dict[str, Any]) -> Dict[str, Any]:
    mapped = dict(queue_row)
    mapped["source_kind"] = "legacy_queue"
    return mapped


def load_passport_source_rows(
    client: Any,
    project_code: str,
    month_key: str,
    draft_id: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[str], Optional[str]]:
    """
    Returns (source_rows, errors, source_kind).

    source_kind is "v2", "legacy_queue", or None when no rows.
    """
    errors: List[str] = []

    if PASSPORT_SOURCE_MODE == "queue_only":
        queue_rows, queue_errors = _fetch_queue_rows(project_code, month_key, draft_id)
        errors.extend(queue_errors)
        if not queue_rows:
            return [], errors, None
        return (
            [_map_queue_row_to_passport_source_row(row) for row in queue_rows],
            errors,
            "legacy_queue",
        )

    # v2_primary
    try:
        v2_rows = _fetch_v2_plan_lines(client, project_code, month_key)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Ошибка чтения {TABLE_PLAN_LINES_V2}: {exc}")
        v2_rows = []

    if v2_rows:
        source_rows: List[Dict[str, Any]] = []
        for v2_row in v2_rows:
            mapped = _map_v2_row_to_passport_source_row(v2_row)
            if mapped is None:
                errors.append(
                    f"Пропущена строка {TABLE_PLAN_LINES_V2} без plan_line_id "
                    f"(boq_code={v2_row.get('boq_code')!r})."
                )
                continue
            source_rows.append(mapped)
        if source_rows:
            return source_rows, errors, "v2"
        # All v2 rows lacked plan_line_id — fall through to legacy queue.

    queue_rows, queue_errors = _fetch_queue_rows(project_code, month_key, draft_id)
    errors.extend(queue_errors)
    if not queue_rows:
        return [], errors, None
    return (
        [_map_queue_row_to_passport_source_row(row) for row in queue_rows],
        errors,
        "legacy_queue",
    )


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
    """Читает поля override из строки источника (queue / PassportSourceRow)."""
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
    source_row: Dict[str, Any],
    counts: ConstraintCounts,
    admission_status: str,
    override: Dict[str, Any],
) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    has_override = override.get("management_override") and admission_status == "APPROVED_BY_OVERRIDE"

    row: Dict[str, Any] = {
        "passport_id": passport_id,
        "draft_id": source_row.get("draft_id"),
        "line_id": source_row.get("line_id"),
        "review_id": source_row.get("review_id") or source_row.get("id"),
        "project_code": source_row.get("project_code"),
        "month_key": source_row.get("month_key"),
        "facility_building": source_row.get("facility_building"),
        "construction_discipline": source_row.get("construction_discipline"),
        "boq_code": source_row.get("boq_code"),
        "boq_name": source_row.get("boq_name"),
        "unit_of_measure": source_row.get("unit_of_measure"),
        "crew_id": source_row.get("crew_id"),
        "planned_qty": source_row.get("planned_qty"),
        "unit_price": source_row.get("unit_price"),
        "plan_value": source_row.get("plan_value"),
        "required_hours": source_row.get("required_hours"),
        "labor_rate_per_hour": source_row.get("labor_rate_per_hour"),
        "labor_cost": source_row.get("labor_cost"),
        "admission_status": admission_status,
        "constraints_total": counts["constraints_total"],
        "constraints_pass": counts["constraints_pass"],
        "constraints_warning": counts["constraints_warning"],
        "constraints_hold": counts["constraints_hold"],
        "constraints_fail": counts["constraints_fail"],
        "week_plan_status": "NOT_DECOMPOSED",
        "comment": source_row.get("comment"),
        "management_override": has_override,
        "override_by": override.get("override_by") if has_override else None,
        "override_at": override.get("override_at") or (now_iso if has_override else None),
        "override_reason": override.get("override_reason") if has_override else None,
        "override_risk_comment": override.get("override_risk_comment") if has_override else None,
        "override_basis": override.get("override_basis") if has_override else None,
    }
    return row


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _line_payload_for_rpc(row: Dict[str, Any]) -> Dict[str, Any]:
    """Strip passport_id — RPC assigns it. Keep JSON-serializable values."""
    payload: Dict[str, Any] = {}
    for key, value in row.items():
        if key == "passport_id":
            continue
        payload[key] = _json_safe_value(value)
    return payload


def validate_passport_line_payloads(
    project_code: str,
    month_key: str,
    lines: List[Dict[str, Any]],
) -> List[str]:
    """Pre-RPC validation. Returns list of error messages (empty = ok)."""
    errors: List[str] = []
    if not lines:
        errors.append("Пустой состав паспорта запрещён.")
        return errors

    seen_line_ids: set[str] = set()
    for idx, row in enumerate(lines):
        line_id = str(row.get("line_id") or "").strip()
        boq_code = str(row.get("boq_code") or "").strip()
        if not line_id:
            errors.append(f"Строка #{idx + 1}: отсутствует line_id (source_plan_line_id).")
        elif line_id in seen_line_ids:
            errors.append(f"Дублирующий line_id: {line_id}")
        else:
            seen_line_ids.add(line_id)
        if not boq_code:
            errors.append(f"Строка #{idx + 1}: отсутствует boq_code.")
        row_project = str(row.get("project_code") or "").strip()
        row_month = str(row.get("month_key") or "").strip()
        if row_project and row_project != project_code:
            errors.append(
                f"Строка {boq_code or line_id}: project_code={row_project!r} "
                f"не совпадает с {project_code!r}."
            )
        if row_month and row_month != month_key:
            errors.append(
                f"Строка {boq_code or line_id}: month_key={row_month!r} "
                f"не совпадает с {month_key!r}."
            )
    return errors


def _call_replace_monthly_passport(
    client: Client,
    *,
    project_code: str,
    month_key: str,
    draft_id: Optional[str],
    created_by: str,
    lines: List[Dict[str, Any]],
    header_totals: Dict[str, Any],
) -> Dict[str, Any]:
    payload = {
        "p_project_code": project_code,
        "p_month_key": month_key,
        "p_draft_id": draft_id,
        "p_created_by": created_by,
        "p_lines": lines,
        "p_header_totals": header_totals,
        "p_expected_rows": len(lines),
    }
    response = client.rpc(RPC_REPLACE_MONTHLY_PASSPORT, payload).execute()
    data = response.data
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        raise RuntimeError(f"RPC {RPC_REPLACE_MONTHLY_PASSPORT} returned unexpected payload: {data!r}")
    return data


def create_monthly_passport(
    project_code: str,
    month_key: str,
    draft_id: Optional[str] = None,
    created_by: str = "Пользователь Streamlit",
) -> PassportSummary:
    """
    Формирует или атомарно пересобирает Approved Monthly Plan Passport
    через RPC replace_monthly_passport (одна Postgres-транзакция).

    Источник: v2 plan lines (primary) / Review Queue (legacy fallback) + constraints.
    Включает READY_WITH_RISK, APPROVED_TO_EXECUTE, APPROVED_BY_OVERRIDE.

    Release 1: rebuild replaces the current passport composition in place.
    Passport revision / version history is not stored yet (technical debt for R2).
    Status APPROVED means ACTIVE WORKING PASSPORT (rebuildable), not a closed month.
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
        "source_kind": None,
        "previous_rows": 0,
        "current_rows": 0,
        "added_count": 0,
        "removed_count": 0,
        "updated_count": 0,
    }

    write_client = get_write_client()
    if write_client is None:
        summary["errors"].append(
            "SUPABASE_SECRET_KEY не задан в .env — запись в monthly_plan_passports недоступна."
        )
        return summary

    source_rows, read_errors, source_kind = load_passport_source_rows(
        supabase,
        project_code,
        month_key,
        draft_id,
    )
    summary["errors"].extend(read_errors)
    summary["source_kind"] = source_kind
    if not source_rows:
        summary["status"] = "no_source_rows"
        if PASSPORT_SOURCE_MODE == "queue_only":
            summary["errors"].append(
                f"Нет строк источника паспорта для project_code={project_code}, "
                f"month_key={month_key}. Проверена только legacy {TABLE_QUEUE}."
            )
        else:
            summary["errors"].append(
                f"Нет строк источника паспорта для project_code={project_code}, "
                f"month_key={month_key}. Проверены {TABLE_PLAN_LINES_V2} и "
                f"legacy {TABLE_QUEUE}."
            )
        return summary

    line_ids = [str(r.get("line_id")) for r in source_rows if r.get("line_id")]
    constraints_by_line = _fetch_constraints_for_lines(line_ids)

    admission_counts = {
        "total_source_rows": len(source_rows),
        "included_rows": 0,
        "blocked_rows": 0,
        "blocked_without_override": 0,
        "override_included_rows": 0,
        "waiting_rows": 0,
        "ready_with_risk_rows": 0,
        "approved_to_execute_rows": 0,
    }

    lines_to_insert: List[Dict[str, Any]] = []
    resolved_draft_id = draft_id or source_rows[0].get("draft_id")

    for source_row in source_rows:
        line_id = str(source_row.get("line_id") or "")
        if not line_id:
            summary["errors"].append(
                f"Пропущена source-строка без line_id (boq_code={source_row.get('boq_code')!r})."
            )
            continue
        constraint_rows = constraints_by_line.get(line_id, [])
        counts = _count_constraints(constraint_rows)
        override = _read_override_from_queue(source_row)
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
                "_source_row": source_row,
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
        _safe_float(item["_source_row"].get("plan_value")) for item in lines_to_insert
    )
    total_hours = sum(
        _safe_float(item["_source_row"].get("required_hours")) for item in lines_to_insert
    )
    total_labor_cost = sum(
        _safe_float(item["_source_row"].get("labor_cost")) for item in lines_to_insert
    )

    payload_rows = [
        _line_payload_for_rpc(
            _build_passport_line(
                passport_id=PLACEHOLDER_PASSPORT_ID,
                source_row=item["_source_row"],
                counts=item["_counts"],
                admission_status=item["_admission_status"],
                override=item["_override"],
            )
        )
        for item in lines_to_insert
    ]

    validation_errors = validate_passport_line_payloads(
        project_code, month_key, payload_rows
    )
    if validation_errors:
        summary["errors"].extend(validation_errors)
        summary["status"] = "validation_error"
        return summary

    draft_uuid: Optional[str] = None
    if resolved_draft_id not in (None, ""):
        draft_uuid = str(resolved_draft_id)

    header_totals = {
        "passport_name": f"Monthly Plan Passport | {project_code} | {month_key}",
        "total_plan_value": total_value,
        "total_required_hours": total_hours,
        "total_labor_cost": total_labor_cost,
        "admission_summary": admission_counts,
    }

    try:
        # Release 1: rebuild replaces current composition; no revision history yet.
        rpc_result = _call_replace_monthly_passport(
            write_client,
            project_code=project_code,
            month_key=month_key,
            draft_id=draft_uuid,
            created_by=created_by,
            lines=payload_rows,
            header_totals=header_totals,
        )
    except Exception as exc:  # noqa: BLE001
        summary["errors"].append(f"Ошибка RPC {RPC_REPLACE_MONTHLY_PASSPORT}: {exc}")
        return summary

    status = str(rpc_result.get("status") or "error")
    summary["status"] = status
    summary["passport_id"] = str(rpc_result.get("passport_id") or "") or None
    summary["previous_rows"] = int(rpc_result.get("previous_rows") or 0)
    summary["current_rows"] = int(rpc_result.get("current_rows") or 0)
    summary["added_count"] = int(rpc_result.get("added_count") or 0)
    summary["removed_count"] = int(rpc_result.get("removed_count") or 0)
    summary["updated_count"] = int(rpc_result.get("updated_count") or 0)
    summary["created_lines"] = summary["current_rows"]
    summary["total_value"] = total_value
    summary["total_hours"] = total_hours
    summary["blocked_without_override"] = admission_counts["blocked_without_override"]

    if status not in ("created", "rebuilt"):
        summary["errors"].append(
            f"RPC вернул неожиданный status={status!r}: {rpc_result}"
        )
        summary["status"] = "error"
    return summary


# Legacy batch insert kept for diagnostics / optional admin tools only.
# Production create/rebuild path must use replace_monthly_passport RPC.
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