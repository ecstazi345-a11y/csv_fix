"""
Генерация записей monthly_plan_constraints из monthly_plan_review_queue.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict

from dotenv import load_dotenv
from supabase import Client, create_client

from services.supabase_client import supabase

load_dotenv()

TABLE_QUEUE = "monthly_plan_review_queue"
TABLE_CONSTRAINTS = "monthly_plan_constraints"

# Page 14 сейчас пишет «ОЖИДАЕТ ПРОВЕРКИ»; SENT_TO_REVIEW — целевой статус очереди.
ELIGIBLE_REVIEW_STATUSES = ("SENT_TO_REVIEW", "ОЖИДАЕТ ПРОВЕРКИ")

CHUNK_SIZE = 200


class ConstraintsSummary(TypedDict):
    created_count: int
    skipped_count: int
    source_rows_count: int
    errors: List[str]


def get_write_client() -> Optional[Client]:
    url = os.getenv("SUPABASE_URL")
    secret_key = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not secret_key:
        return None
    return create_client(url, secret_key)


def get_constraint_templates() -> List[Dict[str, str]]:
    """Шаблоны проверок по слоям допуска (7 записей на строку очереди)."""
    return [
        {
            "gate_layer": "EXECUTABILITY",
            "responsible_department": "Участок",
            "check_name": "Фронт физически открыт",
        },
        {
            "gate_layer": "EXECUTABILITY",
            "responsible_department": "ПТО",
            "check_name": "РД / IWP / исполнительность",
        },
        {
            "gate_layer": "EXECUTABILITY",
            "responsible_department": "МТО",
            "check_name": "Материалы и оборудование",
        },
        {
            "gate_layer": "EXECUTABILITY",
            "responsible_department": "ОТиТБ",
            "check_name": "Наряды / безопасность",
        },
        {
            "gate_layer": "EXECUTABILITY",
            "responsible_department": "QAQC",
            "check_name": "Контроль качества / приёмка",
        },
        {
            "gate_layer": "ACCEPTABILITY",
            "responsible_department": "Коммерческий отдел",
            "check_name": "Возможность предъявления",
        },
        {
            "gate_layer": "CREW_ECONOMICS",
            "responsible_department": "Руководство",
            "check_name": "Экономика звена",
        },
    ]


def _dedup_key(
    line_id: Any,
    responsible_department: str,
    check_name: str,
) -> Tuple[str, str, str]:
    return (str(line_id or ""), responsible_department, check_name)


def _fetch_queue_rows(
    project_code: Optional[str],
    month_key: Optional[str],
    draft_id: Optional[str],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    errors: List[str] = []
    query = (
        supabase.table(TABLE_QUEUE)
        .select("*")
        .in_("review_status", list(ELIGIBLE_REVIEW_STATUSES))
    )
    if project_code:
        query = query.eq("project_code", project_code)
    if month_key:
        query = query.eq("month_key", month_key)
    if draft_id:
        query = query.eq("draft_id", draft_id)

    try:
        response = query.limit(10000).execute()
    except Exception as exc:  # noqa: BLE001
        return [], [f"Ошибка чтения {TABLE_QUEUE}: {exc}"]

    return list(response.data or []), errors


def _fetch_existing_keys(
    client: Client,
    line_ids: List[str],
) -> Tuple[Set[Tuple[str, str, str]], List[str]]:
    keys: Set[Tuple[str, str, str]] = set()
    errors: List[str] = []
    unique_ids = [lid for lid in dict.fromkeys(line_ids) if lid]
    if not unique_ids:
        return keys, errors

    for offset in range(0, len(unique_ids), CHUNK_SIZE):
        chunk = unique_ids[offset : offset + CHUNK_SIZE]
        try:
            response = (
                client.table(TABLE_CONSTRAINTS)
                .select("line_id, responsible_department, check_name")
                .in_("line_id", chunk)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Ошибка чтения существующих constraints: {exc}")
            continue
        for row in response.data or []:
            keys.add(
                _dedup_key(
                    row.get("line_id"),
                    str(row.get("responsible_department") or ""),
                    str(row.get("check_name") or ""),
                )
            )
    return keys, errors


def _plan_line_as_constraint_source(plan_line: Dict[str, Any]) -> Dict[str, Any]:
    """v2 plan line / session item → source dict for _build_constraint_row."""
    crew_id = (
        plan_line.get("crew_code")
        or plan_line.get("crew_id")
        or plan_line.get("crew")
    )
    required_hours = plan_line.get("required_hours")
    if required_hours is None:
        required_hours = plan_line.get("labor_hours")

    return {
        "draft_id": None,
        "line_id": str(plan_line.get("plan_line_id") or "").strip() or None,
        "review_id": None,
        "project_code": plan_line.get("project_code"),
        "month_key": plan_line.get("month_key"),
        "facility_building": plan_line.get("facility") or plan_line.get("facility_building"),
        "construction_discipline": plan_line.get("discipline")
        or plan_line.get("construction_discipline"),
        "boq_code": plan_line.get("boq_code"),
        "boq_name": plan_line.get("boq_name"),
        "crew_id": crew_id,
        "plan_value": plan_line.get("plan_value"),
        "required_hours": required_hours,
    }


def _build_constraint_row(
    queue_row: Dict[str, Any],
    template: Dict[str, str],
) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    plan_value = queue_row.get("plan_value")
    dept = template["responsible_department"]

    row: Dict[str, Any] = {
        "draft_id": queue_row.get("draft_id"),
        "line_id": queue_row.get("line_id"),
        "review_id": queue_row.get("review_id") or queue_row.get("id"),
        "project_code": queue_row.get("project_code"),
        "month_key": queue_row.get("month_key"),
        "facility_building": queue_row.get("facility_building"),
        "construction_discipline": queue_row.get("construction_discipline"),
        "boq_code": queue_row.get("boq_code"),
        "boq_name": queue_row.get("boq_name"),
        "crew_id": queue_row.get("crew_id"),
        "plan_value": plan_value,
        "required_hours": queue_row.get("required_hours"),
        "gate_layer": template["gate_layer"],
        "responsible_department": dept,
        "check_name": template["check_name"],
        "check_status": "ОЖИДАЕТ",
        "resolution_status": "OPEN",
        "constraint_created_at": now_iso,
        "value_at_risk": plan_value if plan_value is not None else 0,
        "owner_department": dept,
        "target_resolution_date": None,
        "severity": "MEDIUM",
    }
    return row


def _insert_batch(client: Client, rows: List[Dict[str, Any]]) -> Optional[str]:
    if not rows:
        return None
    try:
        client.table(TABLE_CONSTRAINTS).insert(rows).execute()
        return None
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        lifecycle_fields = (
            "constraint_created_at",
            "value_at_risk",
            "owner_department",
            "severity",
        )
        if not any(field in msg for field in lifecycle_fields):
            return str(exc)
        slim_rows = [
            {k: v for k, v in row.items() if k not in lifecycle_fields}
            for row in rows
        ]
        try:
            client.table(TABLE_CONSTRAINTS).insert(slim_rows).execute()
            return None
        except Exception as retry_exc:  # noqa: BLE001
            return str(retry_exc)


def create_constraints_for_review_queue(
    project_code: Optional[str] = None,
    month_key: Optional[str] = None,
    draft_id: Optional[str] = None,
) -> ConstraintsSummary:
    """
    Создаёт по 7 constraints на каждую строку очереди в статусе допуска к проверке.
    Уникальность: line_id + responsible_department + check_name.
    """
    summary: ConstraintsSummary = {
        "created_count": 0,
        "skipped_count": 0,
        "source_rows_count": 0,
        "errors": [],
    }

    write_client = get_write_client()
    if write_client is None:
        summary["errors"].append(
            "SUPABASE_SECRET_KEY не задан в .env — запись в monthly_plan_constraints недоступна."
        )
        return summary

    queue_rows, read_errors = _fetch_queue_rows(project_code, month_key, draft_id)
    summary["errors"].extend(read_errors)
    summary["source_rows_count"] = len(queue_rows)
    if not queue_rows:
        return summary

    line_ids = [str(r.get("line_id")) for r in queue_rows if r.get("line_id")]
    existing_keys, existing_errors = _fetch_existing_keys(write_client, line_ids)
    summary["errors"].extend(existing_errors)

    templates = get_constraint_templates()
    to_insert: List[Dict[str, Any]] = []

    for queue_row in queue_rows:
        line_id = queue_row.get("line_id")
        for template in templates:
            key = _dedup_key(
                line_id,
                template["responsible_department"],
                template["check_name"],
            )
            if key in existing_keys:
                summary["skipped_count"] += 1
                continue
            to_insert.append(_build_constraint_row(queue_row, template))
            existing_keys.add(key)

    for offset in range(0, len(to_insert), CHUNK_SIZE):
        batch = to_insert[offset : offset + CHUNK_SIZE]
        err = _insert_batch(write_client, batch)
        if err:
            summary["errors"].append(f"Ошибка insert (batch {offset // CHUNK_SIZE + 1}): {err}")
        else:
            summary["created_count"] += len(batch)

    return summary


def create_constraints_for_plan_lines(plan_lines: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Создаёт по 7 constraints на каждую v2 строку плана (monthly_plan_lines_v2).
    line_id = plan_line_id; draft_id и review_id = NULL.
    Уникальность: line_id + responsible_department + check_name.
    """
    summary: Dict[str, Any] = {
        "created": 0,
        "skipped": 0,
        "errors": [],
    }

    write_client = get_write_client()
    if write_client is None:
        summary["errors"].append(
            "SUPABASE_SECRET_KEY не задан в .env — запись в monthly_plan_constraints недоступна."
        )
        return summary

    valid_lines: List[Dict[str, Any]] = []
    for line in plan_lines:
        plan_line_id = str(line.get("plan_line_id") or "").strip()
        if not plan_line_id:
            summary["errors"].append("Строка без plan_line_id пропущена.")
            continue
        valid_lines.append(line)

    if not valid_lines:
        return summary

    line_ids = [str(line.get("plan_line_id")) for line in valid_lines]
    existing_keys, existing_errors = _fetch_existing_keys(write_client, line_ids)
    summary["errors"].extend(existing_errors)

    templates = get_constraint_templates()
    to_insert: List[Dict[str, Any]] = []

    for plan_line in valid_lines:
        line_id = plan_line.get("plan_line_id")
        source = _plan_line_as_constraint_source(plan_line)
        for template in templates:
            key = _dedup_key(
                line_id,
                template["responsible_department"],
                template["check_name"],
            )
            if key in existing_keys:
                summary["skipped"] += 1
                continue
            to_insert.append(_build_constraint_row(source, template))
            existing_keys.add(key)

    for offset in range(0, len(to_insert), CHUNK_SIZE):
        batch = to_insert[offset : offset + CHUNK_SIZE]
        err = _insert_batch(write_client, batch)
        if err:
            summary["errors"].append(
                f"Ошибка insert (batch {offset // CHUNK_SIZE + 1}): {err}"
            )
        else:
            summary["created"] += len(batch)

    return summary
