"""
PNR MVP-0.3 / FIELD-1B / FIELD-1C — server-side boundary for PNR catalog
reads and event writes.

Streamlit must not talk to Supabase directly. This module uses
SUPABASE_URL + SUPABASE_SECRET_KEY only. Isolated from daily_progress,
monthly planning, and Agent Runtime.

Legacy path: create_execution_event — single pnr_execution_events INSERT.
Structured path: create_structured_execution_event — one RPC transaction.
FIELD-1C adds narrow SELECT helpers for the field capture form.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

TABLE_SYSTEMS = "eos_systems"
TABLE_OBJECTS = "pnr_objects"
TABLE_SCOPES = "pnr_work_scopes"
TABLE_OPERATIONS = "pnr_operations"
TABLE_EVENTS = "pnr_execution_events"
TABLE_PROJECTS = "eos_projects"
TABLE_TITLES = "eos_titles"
TABLE_DISCIPLINES = "eos_disciplines"
TABLE_WORK_TYPES = "eos_work_types"
TABLE_WORK_CONTEXTS = "eos_system_work_contexts"
TABLE_OBJECT_POSITION_MAP = "pnr_object_position_map"

RPC_CREATE_STRUCTURED_EVENT = "create_pnr_structured_execution_event"
WORK_TYPE_CODE_PNR = "PNR"

RESULT_VALUES = frozenset({"PASS", "FAIL", "PARTIAL", "BLOCKED"})
DEFAULT_SOURCE = "STREAMLIT"
DEFAULT_EVENT_LIMIT = 200

EXECUTION_STATUS_VALUES = frozenset(
    {"COMPLETED", "NOT_COMPLETED", "PARTIAL", "BLOCKED"}
)
EVALUATION_STATUS_VALUES = frozenset(
    {"CONFORMS", "DOES_NOT_CONFORM", "NOT_EVALUATED"}
)
STATUS_PAIR_TO_RESULT: dict[tuple[str, str], str] = {
    ("COMPLETED", "CONFORMS"): "PASS",
    ("COMPLETED", "NOT_EVALUATED"): "PASS",
    ("COMPLETED", "DOES_NOT_CONFORM"): "FAIL",
    ("NOT_COMPLETED", "NOT_EVALUATED"): "FAIL",
    ("PARTIAL", "NOT_EVALUATED"): "PARTIAL",
    ("PARTIAL", "DOES_NOT_CONFORM"): "PARTIAL",
    ("BLOCKED", "NOT_EVALUATED"): "BLOCKED",
}
BLOCKED_CONSTRAINT_CATEGORIES = frozenset(
    {
        "DOCUMENTATION",
        "CONSTRUCTION_READINESS",
        "ADJACENT_WORK",
        "MATERIALS",
        "EQUIPMENT",
        "POWER_SUPPLY",
        "WORKING_MEDIUM",
        "OBJECT_ACCESS",
        "PERMIT_SAFETY",
        "PERSONNEL",
        "INSTRUMENT",
        "AUTOMATION_SOFTWARE",
        "THIRD_PARTY_DECISION",
        "WEATHER_EXTERNAL",
        "OTHER",
    }
)

SYSTEM_FIELDS = (
    "system_id",
    "project_code",
    "system_code",
    "system_name",
)
OBJECT_FIELDS = (
    "object_id",
    "system_id",
    "object_code",
    "object_name",
    "object_kind",
)
SCOPE_FIELDS = (
    "work_scope_id",
    "scope_code",
    "scope_name",
    "sequence_no",
)
OPERATION_FIELDS = (
    "operation_id",
    "work_scope_id",
    "operation_code",
    "operation_name",
    "sequence_no",
)
EVENT_FIELDS = (
    "event_id",
    "system_id",
    "object_id",
    "operation_id",
    "unmapped_operation_name",
    "result",
    "occurred_at",
    "people_count",
    "duration_hours",
    "labor_hours",
    "reason",
    "comment",
    "source",
    "created_at",
)
PROJECT_FIELDS = (
    "project_id",
    "project_code",
    "project_name",
)
TITLE_FIELDS = (
    "title_id",
    "project_id",
    "title_code",
    "title_name",
)
DISCIPLINE_FIELDS = (
    "discipline_id",
    "discipline_code",
    "discipline_name",
)
WORK_TYPE_FIELDS = (
    "work_type_id",
    "work_type_code",
    "work_type_name",
)
WORK_CONTEXT_FIELDS = (
    "system_work_context_id",
    "title_id",
    "discipline_id",
    "work_type_id",
    "system_id",
    "context_system_code",
)
OBJECT_POSITION_MAP_FIELDS = (
    "object_id",
    "position_id",
    "system_id",
    "mapping_type",
)

STRUCTURED_EVENT_FIELDS = EVENT_FIELDS + (
    "functional_position_id",
    "execution_status",
    "evaluation_status",
    "observation_text",
    "retry_of_event_id",
    "work_scope_id",
)


class PnrError(Exception):
    """Base PNR service error. Message is safe to show in UI."""


class PnrConfigError(PnrError):
    """Missing server credentials. Fail closed."""


class PnrValidationError(PnrError):
    """Caller input rejected before INSERT."""


class PnrServiceError(PnrError):
    """Supabase / transport failure. No secrets in message."""


def get_pnr_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    secret = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not str(url).strip() or not secret or not str(secret).strip():
        raise PnrConfigError(
            "PNR недоступен: на сервере не задан SUPABASE_URL или SUPABASE_SECRET_KEY."
        )
    return create_client(url, secret)


def _client(client: Optional[Client] = None) -> Client:
    if client is not None:
        return client
    return get_pnr_client()


def _pick(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {key: row.get(key) for key in fields}


def _nonempty_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_id(value: Any, label: str) -> str:
    text = _nonempty_text(value)
    if text is None:
        raise PnrValidationError(f"Не указан {label}.")
    return text


def _require_aware_datetime(value: Any) -> datetime:
    parsed: datetime
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise PnrValidationError("Не указано время события.")
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise PnrValidationError(
                "Некорректное время события. Нужна дата/время с часовым поясом."
            ) from exc
    else:
        raise PnrValidationError("Некорректное время события.")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PnrValidationError(
            "Время события должно содержать часовой пояс. Локальное время без зоны отклонено."
        )
    return parsed


def _optional_int(value: Any, label: str) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise PnrValidationError(f"{label}: ожидается целое число.")
    return value


def _optional_decimal(value: Any, label: str) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise PnrValidationError(f"{label}: некорректное число.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PnrValidationError(f"{label}: некорректное число.") from exc
    if not number.is_finite():
        raise PnrValidationError(f"{label}: некорректное число.")
    return number


def _json_number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _query_error(action: str) -> PnrServiceError:
    return PnrServiceError(f"Не удалось выполнить {action} PNR. Повторите попытку.")


def list_active_systems(
    *,
    project_code: Optional[str] = None,
    client: Optional[Client] = None,
) -> list[dict[str, Any]]:
    db = _client(client)
    try:
        query = (
            db.table(TABLE_SYSTEMS)
            .select(",".join(SYSTEM_FIELDS))
            .eq("is_active", True)
        )
        filtered = _nonempty_text(project_code)
        if filtered:
            query = query.eq("project_code", filtered)
        response = query.execute()
    except PnrError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _query_error("чтение систем") from exc
    return [_pick(row, SYSTEM_FIELDS) for row in (response.data or [])]


def list_active_objects(
    *,
    system_id: Any,
    client: Optional[Client] = None,
) -> list[dict[str, Any]]:
    sid = _require_id(system_id, "систему")
    db = _client(client)
    try:
        response = (
            db.table(TABLE_OBJECTS)
            .select(",".join(OBJECT_FIELDS))
            .eq("is_active", True)
            .eq("system_id", sid)
            .execute()
        )
    except PnrError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _query_error("чтение объектов") from exc
    return [_pick(row, OBJECT_FIELDS) for row in (response.data or [])]


def list_active_work_scopes(
    *,
    client: Optional[Client] = None,
) -> list[dict[str, Any]]:
    db = _client(client)
    try:
        response = (
            db.table(TABLE_SCOPES)
            .select(",".join(SCOPE_FIELDS))
            .eq("is_active", True)
            .execute()
        )
    except PnrError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _query_error("чтение разделов работ") from exc
    return [_pick(row, SCOPE_FIELDS) for row in (response.data or [])]


def list_active_operations(
    *,
    work_scope_id: Any,
    client: Optional[Client] = None,
) -> list[dict[str, Any]]:
    wid = _require_id(work_scope_id, "раздел работ")
    db = _client(client)
    try:
        response = (
            db.table(TABLE_OPERATIONS)
            .select(",".join(OPERATION_FIELDS))
            .eq("is_active", True)
            .eq("work_scope_id", wid)
            .execute()
        )
    except PnrError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _query_error("чтение операций") from exc
    return [_pick(row, OPERATION_FIELDS) for row in (response.data or [])]


def list_recent_execution_events(
    *,
    limit: int = DEFAULT_EVENT_LIMIT,
    client: Optional[Client] = None,
) -> list[dict[str, Any]]:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise PnrValidationError("Некорректный лимит журнала.")
    db = _client(client)
    try:
        response = (
            db.table(TABLE_EVENTS)
            .select(",".join(EVENT_FIELDS))
            .order("occurred_at", desc=True)
            .limit(limit)
            .execute()
        )
    except PnrError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _query_error("чтение журнала") from exc
    return [_pick(row, EVENT_FIELDS) for row in (response.data or [])]


def _sort_rows(
    rows: list[dict[str, Any]], *keys: str
) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: tuple(str(row.get(key) or "") for key in keys),
    )


def list_active_projects(
    *,
    client: Optional[Client] = None,
) -> list[dict[str, Any]]:
    db = _client(client)
    try:
        response = (
            db.table(TABLE_PROJECTS)
            .select(",".join(PROJECT_FIELDS))
            .eq("is_active", True)
            .execute()
        )
    except PnrError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _query_error("чтение проектов") from exc
    return _sort_rows(
        [_pick(row, PROJECT_FIELDS) for row in (response.data or [])],
        "project_name",
        "project_code",
    )


def list_active_titles(
    *,
    project_id: Any,
    client: Optional[Client] = None,
) -> list[dict[str, Any]]:
    pid = _require_id(project_id, "проект")
    db = _client(client)
    try:
        response = (
            db.table(TABLE_TITLES)
            .select(",".join(TITLE_FIELDS))
            .eq("is_active", True)
            .eq("project_id", pid)
            .execute()
        )
    except PnrError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _query_error("чтение титулов") from exc
    return _sort_rows(
        [_pick(row, TITLE_FIELDS) for row in (response.data or [])],
        "title_name",
        "title_code",
    )


def list_active_work_types(
    *,
    client: Optional[Client] = None,
) -> list[dict[str, Any]]:
    db = _client(client)
    try:
        response = (
            db.table(TABLE_WORK_TYPES)
            .select(",".join(WORK_TYPE_FIELDS))
            .eq("is_active", True)
            .execute()
        )
    except PnrError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _query_error("чтение видов работ") from exc
    return _sort_rows(
        [_pick(row, WORK_TYPE_FIELDS) for row in (response.data or [])],
        "work_type_name",
        "work_type_code",
    )


def get_work_type_by_code(
    *,
    work_type_code: Any,
    client: Optional[Client] = None,
) -> Optional[dict[str, Any]]:
    code = _nonempty_text(work_type_code)
    if code is None:
        raise PnrValidationError("Не указан код вида работ.")
    db = _client(client)
    try:
        response = (
            db.table(TABLE_WORK_TYPES)
            .select(",".join(WORK_TYPE_FIELDS))
            .eq("is_active", True)
            .eq("work_type_code", code)
            .limit(2)
            .execute()
        )
    except PnrError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _query_error("чтение вида работ") from exc
    rows = [_pick(row, WORK_TYPE_FIELDS) for row in (response.data or [])]
    if not rows:
        return None
    return rows[0]


def list_context_disciplines(
    *,
    title_id: Any,
    work_type_id: Any,
    client: Optional[Client] = None,
) -> list[dict[str, Any]]:
    tid = _require_id(title_id, "титул")
    wid = _require_id(work_type_id, "вид работ")
    db = _client(client)
    try:
        context_response = (
            db.table(TABLE_WORK_CONTEXTS)
            .select("discipline_id")
            .eq("is_active", True)
            .eq("title_id", tid)
            .eq("work_type_id", wid)
            .execute()
        )
        discipline_ids = {
            str(row.get("discipline_id"))
            for row in (context_response.data or [])
            if row.get("discipline_id")
        }
        if not discipline_ids:
            return []
        discipline_response = (
            db.table(TABLE_DISCIPLINES)
            .select(",".join(DISCIPLINE_FIELDS))
            .eq("is_active", True)
            .execute()
        )
    except PnrError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _query_error("чтение дисциплин") from exc
    rows = [
        _pick(row, DISCIPLINE_FIELDS)
        for row in (discipline_response.data or [])
        if str(row.get("discipline_id")) in discipline_ids
    ]
    return _sort_rows(rows, "discipline_name", "discipline_code")


def list_system_work_contexts(
    *,
    title_id: Any,
    work_type_id: Any,
    discipline_id: Any,
    client: Optional[Client] = None,
) -> list[dict[str, Any]]:
    tid = _require_id(title_id, "титул")
    wid = _require_id(work_type_id, "вид работ")
    did = _require_id(discipline_id, "дисциплину")
    db = _client(client)
    try:
        response = (
            db.table(TABLE_WORK_CONTEXTS)
            .select(",".join(WORK_CONTEXT_FIELDS))
            .eq("is_active", True)
            .eq("title_id", tid)
            .eq("work_type_id", wid)
            .eq("discipline_id", did)
            .execute()
        )
    except PnrError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _query_error("чтение систем рабочего контекста") from exc
    return _sort_rows(
        [_pick(row, WORK_CONTEXT_FIELDS) for row in (response.data or [])],
        "context_system_code",
    )


def resolve_object_functional_position_id(
    *,
    object_id: Any,
    client: Optional[Client] = None,
) -> Optional[str]:
    oid = _require_id(object_id, "объект")
    db = _client(client)
    try:
        response = (
            db.table(TABLE_OBJECT_POSITION_MAP)
            .select(",".join(OBJECT_POSITION_MAP_FIELDS))
            .eq("object_id", oid)
            .limit(2)
            .execute()
        )
    except PnrError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _query_error("чтение связи объекта с позицией") from exc
    rows = response.data or []
    if len(rows) == 0:
        return None
    if len(rows) > 1:
        raise PnrValidationError(
            "Неоднозначная связь объекта с функциональной позицией."
        )
    return _nonempty_text(rows[0].get("position_id"))


def _load_object(db: Client, object_id: str) -> dict[str, Any]:
    try:
        response = (
            db.table(TABLE_OBJECTS)
            .select("object_id,system_id")
            .eq("object_id", object_id)
            .limit(1)
            .execute()
        )
    except PnrError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _query_error("проверку объекта") from exc
    rows = response.data or []
    if not rows:
        raise PnrValidationError("Объект не найден.")
    return rows[0]


def create_execution_event(
    *,
    system_id: Any,
    object_id: Any,
    result: Any,
    occurred_at: Any,
    operation_id: Any = None,
    unmapped_operation_name: Any = None,
    people_count: Any = None,
    duration_hours: Any = None,
    labor_hours: Any = None,
    reason: Any = None,
    comment: Any = None,
    source: Any = DEFAULT_SOURCE,
    client: Optional[Client] = None,
) -> dict[str, Any]:
    sid = _require_id(system_id, "систему")
    oid = _require_id(object_id, "объект")
    occurred = _require_aware_datetime(occurred_at)

    result_text = _nonempty_text(result)
    if result_text not in RESULT_VALUES:
        raise PnrValidationError(
            "Результат должен быть PASS, FAIL, PARTIAL или BLOCKED."
        )

    catalog_id = _nonempty_text(operation_id)
    unmapped = _nonempty_text(unmapped_operation_name)
    if catalog_id and unmapped:
        raise PnrValidationError(
            "Укажите операцию из каталога или название некаталожной операции, не оба варианта."
        )
    if not catalog_id and not unmapped:
        raise PnrValidationError(
            "Укажите операцию из каталога или название операции, которой нет в справочнике."
        )

    people = _optional_int(people_count, "Количество людей")
    if people is not None and people <= 0:
        raise PnrValidationError("Количество людей должно быть больше 0.")

    duration = _optional_decimal(duration_hours, "Продолжительность")
    if duration is not None and duration < 0:
        raise PnrValidationError("Продолжительность не может быть отрицательной.")

    labor = _optional_decimal(labor_hours, "Трудозатраты")
    if people is not None and duration is not None:
        labor = Decimal(people) * duration
    elif labor is not None and labor < 0:
        raise PnrValidationError("Трудозатраты не могут быть отрицательными.")

    db = _client(client)
    obj = _load_object(db, oid)
    object_system = _nonempty_text(obj.get("system_id"))
    if object_system != sid:
        raise PnrValidationError("Объект не принадлежит выбранной системе.")

    payload: dict[str, Any] = {
        "system_id": sid,
        "object_id": oid,
        "operation_id": catalog_id,
        "unmapped_operation_name": unmapped,
        "result": result_text,
        "occurred_at": occurred.isoformat(),
        "people_count": people,
        "duration_hours": None if duration is None else _json_number(duration),
        "labor_hours": None if labor is None else _json_number(labor),
        "reason": _nonempty_text(reason),
        "comment": _nonempty_text(comment),
        "source": _nonempty_text(source) or DEFAULT_SOURCE,
    }

    try:
        response = db.table(TABLE_EVENTS).insert(payload).execute()
    except PnrError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _query_error("сохранение события") from exc

    rows = response.data or []
    if rows:
        return _pick(rows[0], EVENT_FIELDS)
    return {key: payload.get(key) for key in EVENT_FIELDS}


def _require_status_pair(execution_status: Any, evaluation_status: Any) -> tuple[str, str, str]:
    execution = _nonempty_text(execution_status)
    evaluation = _nonempty_text(evaluation_status)
    if execution not in EXECUTION_STATUS_VALUES or evaluation not in EVALUATION_STATUS_VALUES:
        raise PnrValidationError(
            "Некорректная пара execution_status / evaluation_status."
        )
    result = STATUS_PAIR_TO_RESULT.get((execution, evaluation))
    if result is None:
        raise PnrValidationError(
            "Некорректная пара execution_status / evaluation_status."
        )
    return execution, evaluation, result


def _optional_provided_text(value: Any, label: str) -> Optional[str]:
    if value is None:
        return None
    text = _nonempty_text(value)
    if text is None:
        raise PnrValidationError(f"{label} не может быть пустым.")
    return text


def _load_event(db: Client, event_id: str) -> dict[str, Any]:
    try:
        response = (
            db.table(TABLE_EVENTS)
            .select(
                "event_id,system_id,object_id,operation_id,"
                "unmapped_operation_name,work_scope_id"
            )
            .eq("event_id", event_id)
            .limit(1)
            .execute()
        )
    except PnrError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _query_error("проверку исходного события") from exc
    rows = response.data or []
    if not rows:
        raise PnrValidationError("Исходное событие для повторной попытки не найдено.")
    return rows[0]


def _validate_measurements(measurements: Any) -> list[dict[str, Any]]:
    if measurements is None:
        items: list[Any] = []
    elif isinstance(measurements, list):
        items = measurements
    else:
        raise PnrValidationError("Измерения должны быть списком.")
    prepared: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        label = f"Измерение {index}"
        if not isinstance(item, dict):
            raise PnrValidationError(f"{label}: ожидается объект.")
        name = _nonempty_text(item.get("parameter_name"))
        if name is None:
            raise PnrValidationError(f"{label}: укажите parameter_name.")
        unit = _nonempty_text(item.get("unit"))
        if unit is None:
            raise PnrValidationError(f"{label}: укажите unit.")
        number = _optional_decimal(item.get("value"), f"{label}: value")
        if number is None:
            raise PnrValidationError(f"{label}: укажите value.")
        recorded = _require_aware_datetime(item.get("recorded_at"))
        code = item.get("parameter_code")
        point = item.get("measurement_point")
        instrument = item.get("instrument_text")
        prepared.append(
            {
                "parameter_name": name,
                "value": _json_number(number),
                "unit": unit,
                "recorded_at": recorded.isoformat(),
                "parameter_code": _optional_provided_text(code, f"{label}: parameter_code")
                if code is not None
                else None,
                "measurement_point": _optional_provided_text(
                    point, f"{label}: measurement_point"
                )
                if point is not None
                else None,
                "instrument_text": _optional_provided_text(
                    instrument, f"{label}: instrument_text"
                )
                if instrument is not None
                else None,
            }
        )
    return prepared


def _validate_blocked_detail(detail: Any) -> dict[str, Any]:
    if not isinstance(detail, dict):
        raise PnrValidationError("Для BLOCKED требуется blocked_detail.")
    category = _nonempty_text(detail.get("constraint_category"))
    if category not in BLOCKED_CONSTRAINT_CATEGORIES:
        raise PnrValidationError("Некорректная категория блокировки.")
    description_raw = detail.get("constraint_description")
    description = (
        _optional_provided_text(description_raw, "Описание блокировки")
        if description_raw is not None
        else None
    )
    if category == "OTHER" and description is None:
        raise PnrValidationError(
            "Для категории OTHER укажите описание блокировки."
        )
    other_work = detail.get("other_work_available")
    if other_work is not None and not isinstance(other_work, bool):
        raise PnrValidationError("other_work_available: ожидается true/false.")
    return {
        "constraint_category": category,
        "constraint_description": description,
        "other_work_available": other_work,
    }


def _validate_partial_detail(detail: Any) -> dict[str, Any]:
    if not isinstance(detail, dict):
        raise PnrValidationError("Для PARTIAL требуется partial_detail.")
    completed = _nonempty_text(detail.get("completed_text"))
    remaining = _nonempty_text(detail.get("remaining_text"))
    if completed is None or remaining is None:
        raise PnrValidationError(
            "Для PARTIAL укажите completed_text и remaining_text."
        )
    return {
        "completed_text": completed,
        "remaining_text": remaining,
    }


def _rpc_row(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        raise PnrServiceError("Не удалось выполнить сохранение события PNR. Повторите попытку.")
    return _pick(data, STRUCTURED_EVENT_FIELDS)


def create_structured_execution_event(
    *,
    system_id: Any,
    object_id: Any,
    work_scope_id: Any,
    execution_status: Any,
    evaluation_status: Any,
    occurred_at: Any,
    operation_id: Any = None,
    unmapped_operation_name: Any = None,
    functional_position_id: Any = None,
    observation_text: Any = None,
    retry_of_event_id: Any = None,
    people_count: Any = None,
    duration_hours: Any = None,
    labor_hours: Any = None,
    reason: Any = None,
    comment: Any = None,
    source: Any = DEFAULT_SOURCE,
    measurements: Any = None,
    blocked_detail: Any = None,
    partial_detail: Any = None,
    client: Optional[Client] = None,
) -> dict[str, Any]:
    sid = _require_id(system_id, "систему")
    oid = _require_id(object_id, "объект")
    wid = _require_id(work_scope_id, "раздел работ")
    occurred = _require_aware_datetime(occurred_at)
    execution, evaluation, result = _require_status_pair(
        execution_status, evaluation_status
    )

    catalog_id = _nonempty_text(operation_id)
    unmapped = _nonempty_text(unmapped_operation_name)
    if catalog_id and unmapped:
        raise PnrValidationError(
            "Укажите операцию из каталога или название некаталожной операции, не оба варианта."
        )
    if not catalog_id and not unmapped:
        raise PnrValidationError(
            "Укажите операцию из каталога или название операции, которой нет в справочнике."
        )

    people = _optional_int(people_count, "Количество людей")
    if people is not None and people <= 0:
        raise PnrValidationError("Количество людей должно быть больше 0.")

    duration = _optional_decimal(duration_hours, "Продолжительность")
    if duration is not None and duration < 0:
        raise PnrValidationError("Продолжительность не может быть отрицательной.")

    labor = _optional_decimal(labor_hours, "Трудозатраты")
    if people is not None and duration is not None:
        labor = Decimal(people) * duration
    elif labor is not None and labor < 0:
        raise PnrValidationError("Трудозатраты не могут быть отрицательными.")

    observation = _optional_provided_text(observation_text, "Наблюдение")
    fp_id = _nonempty_text(functional_position_id)
    retry_id = _nonempty_text(retry_of_event_id)

    event_id = str(uuid.uuid4())
    if retry_id is not None and retry_id == event_id:
        raise PnrValidationError("Повторная попытка не может ссылаться на то же событие.")

    prepared_measurements = _validate_measurements(measurements)

    if execution == "BLOCKED":
        if blocked_detail is None:
            raise PnrValidationError("Для BLOCKED требуется blocked_detail.")
        prepared_blocked = _validate_blocked_detail(blocked_detail)
    elif blocked_detail is not None:
        raise PnrValidationError("blocked_detail допустим только для BLOCKED.")
    else:
        prepared_blocked = None

    if execution == "PARTIAL":
        if partial_detail is None:
            raise PnrValidationError("Для PARTIAL требуется partial_detail.")
        prepared_partial = _validate_partial_detail(partial_detail)
    elif partial_detail is not None:
        raise PnrValidationError("partial_detail допустим только для PARTIAL.")
    else:
        prepared_partial = None

    db = _client(client)
    obj = _load_object(db, oid)
    object_system = _nonempty_text(obj.get("system_id"))
    if object_system != sid:
        raise PnrValidationError("Объект не принадлежит выбранной системе.")

    if retry_id is not None:
        prior = _load_event(db, retry_id)
        prior_system = _nonempty_text(prior.get("system_id"))
        prior_object = _nonempty_text(prior.get("object_id"))
        if prior_system != sid:
            raise PnrValidationError(
                "Повторная попытка должна относиться к той же системе."
            )
        if prior_object != oid:
            raise PnrValidationError(
                "Повторная попытка должна относиться к тому же объекту."
            )
        prior_op = _nonempty_text(prior.get("operation_id"))
        prior_unmapped = _nonempty_text(prior.get("unmapped_operation_name"))
        if prior_op != catalog_id or prior_unmapped != unmapped:
            raise PnrValidationError(
                "Повторная попытка должна относиться к той же операции."
            )
        prior_scope = _nonempty_text(prior.get("work_scope_id"))
        if prior_scope is not None and prior_scope != wid:
            raise PnrValidationError(
                "Повторная попытка должна относиться к тому же разделу работ."
            )

    payload: dict[str, Any] = {
        "event_id": event_id,
        "system_id": sid,
        "object_id": oid,
        "work_scope_id": wid,
        "functional_position_id": fp_id,
        "execution_status": execution,
        "evaluation_status": evaluation,
        "observation_text": observation,
        "retry_of_event_id": retry_id,
        "occurred_at": occurred.isoformat(),
        "operation_id": catalog_id,
        "unmapped_operation_name": unmapped,
        "people_count": people,
        "duration_hours": None if duration is None else _json_number(duration),
        "labor_hours": None if labor is None else _json_number(labor),
        "reason": _nonempty_text(reason),
        "comment": _nonempty_text(comment),
        "source": _nonempty_text(source) or DEFAULT_SOURCE,
        "measurements": prepared_measurements,
        "blocked_detail": prepared_blocked,
        "partial_detail": prepared_partial,
    }

    try:
        response = db.rpc(RPC_CREATE_STRUCTURED_EVENT, {"p_payload": payload}).execute()
    except PnrError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _query_error("сохранение события") from exc

    row = _rpc_row(response.data)
    if not row.get("event_id"):
        row["event_id"] = event_id
    if not row.get("result"):
        row["result"] = result
    return row
