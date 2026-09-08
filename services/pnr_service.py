"""
PNR MVP-0.3 — server-side boundary for PNR catalog reads and event INSERT.

Streamlit must not talk to Supabase directly. This module uses
SUPABASE_URL + SUPABASE_SECRET_KEY only. Isolated from daily_progress,
monthly planning, and Agent Runtime.
"""

from __future__ import annotations

import os
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

RESULT_VALUES = frozenset({"PASS", "FAIL", "PARTIAL", "BLOCKED"})
DEFAULT_SOURCE = "STREAMLIT"
DEFAULT_EVENT_LIMIT = 200

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
