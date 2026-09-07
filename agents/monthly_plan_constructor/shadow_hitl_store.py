"""
Increment 11C.3 — Persistent SQLite HITL store for Shadow runtime.

Explicit infrastructure bootstrap only. Implements ConstructorHitlStore
write API. Read methods exist only on this concrete class for reopen proof.

Creates only:
<repository_root>/.runtime/shadow/constructor/hitl.sqlite

Not LangGraph checkpoint memory. Not observability. Not resume authority.
Not Execution ownership. Not a product database.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Union

from agents.monthly_plan_constructor.hitl_contracts import (
    ConstructorHumanDecisionRequest,
    ConstructorResumeCommand,
    HitlContractError,
    ScopeSummary,
    build_human_decision_request,
    build_resume_command,
)
from agents.monthly_plan_constructor.shadow_runtime_stores import (
    resolve_constructor_shadow_runtime_paths,
)

CODE_SHADOW_HITL_STORE_BLOCKER = "SHADOW_HITL_STORE_BLOCKER"

_JSON_DUMP_KWARGS: dict[str, Any] = {
    "ensure_ascii": False,
    "sort_keys": True,
    "allow_nan": False,
    "separators": (",", ":"),
}

_BOOTSTRAP_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS hitl_open_requests (
    interrupt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    mission_id TEXT NOT NULL,
    wait_ordinal INTEGER NOT NULL,
    status TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE (run_id, wait_ordinal)
);

CREATE TABLE IF NOT EXISTS hitl_answers (
    decision_id TEXT PRIMARY KEY,
    interrupt_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    mission_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (interrupt_id) REFERENCES hitl_open_requests(interrupt_id)
);
"""


class ShadowHitlStoreError(ValueError):
    """Fail-closed Shadow HITL store infrastructure / integrity violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ConstructorShadowHitlStore:
    """
    Owned SQLite HITL resource implementing ConstructorHitlStore writes.

    Request rows and answer rows are separate immutable records.
    Presence of an answer is derived from the answer table, not by rewriting
    the original request.
    """

    def __init__(self, *, db_path: Path, connection: sqlite3.Connection) -> None:
        self._db_path = db_path
        self._connection = connection
        self._closed = False
        self._lock = threading.Lock()

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def connection(self) -> sqlite3.Connection:
        self._require_open()
        return self._connection

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._connection.close()

    def __enter__(self) -> "ConstructorShadowHitlStore":
        self._require_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def upsert_open_request(self, request: ConstructorHumanDecisionRequest) -> None:
        self._require_open()
        if not isinstance(request, ConstructorHumanDecisionRequest):
            raise ShadowHitlStoreError(
                CODE_SHADOW_HITL_STORE_BLOCKER,
                "request must be ConstructorHumanDecisionRequest",
            )
        payload = _request_to_payload(request)
        payload_json = _json_dumps(payload)
        created_at = _datetime_to_iso(request.created_at)
        with self._lock:
            try:
                self._connection.execute("BEGIN")
                row = self._connection.execute(
                    """
                    SELECT payload_json
                    FROM hitl_open_requests
                    WHERE interrupt_id = ?
                    """,
                    (request.interrupt_id,),
                ).fetchone()
                if row is not None:
                    existing = _request_from_payload(_json_loads(row["payload_json"]))
                    if _request_identity(existing) != _request_identity(request):
                        raise ShadowHitlStoreError(
                            CODE_SHADOW_HITL_STORE_BLOCKER,
                            "conflicting HITL request for interrupt_id",
                        )
                    self._connection.execute("COMMIT")
                    return
                self._connection.execute(
                    """
                    INSERT INTO hitl_open_requests (
                        interrupt_id, run_id, mission_id, wait_ordinal,
                        status, reason_code, created_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.interrupt_id,
                        request.run_id,
                        request.mission_id,
                        request.wait_ordinal,
                        request.status,
                        request.reason_code,
                        created_at,
                        payload_json,
                    ),
                )
                self._connection.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise ShadowHitlStoreError(
                    CODE_SHADOW_HITL_STORE_BLOCKER,
                    "HITL request identity collision",
                ) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def record_answer(
        self,
        *,
        interrupt_id: str,
        command: ConstructorResumeCommand,
    ) -> None:
        self._require_open()
        if not isinstance(command, ConstructorResumeCommand):
            raise ShadowHitlStoreError(
                CODE_SHADOW_HITL_STORE_BLOCKER,
                "command must be ConstructorResumeCommand",
            )
        bound_interrupt_id = str(interrupt_id or "").strip()
        if not bound_interrupt_id:
            raise ShadowHitlStoreError(
                CODE_SHADOW_HITL_STORE_BLOCKER,
                "interrupt_id is required",
            )
        if command.interrupt_id != bound_interrupt_id:
            raise ShadowHitlStoreError(
                CODE_SHADOW_HITL_STORE_BLOCKER,
                "interrupt_id mismatch",
            )
        payload_json = _json_dumps(_command_to_payload(command))
        submitted_at = _datetime_to_iso(command.submitted_at)
        with self._lock:
            try:
                self._connection.execute("BEGIN")
                request_row = self._connection.execute(
                    """
                    SELECT interrupt_id, run_id, mission_id
                    FROM hitl_open_requests
                    WHERE interrupt_id = ?
                    """,
                    (bound_interrupt_id,),
                ).fetchone()
                if request_row is None:
                    raise ShadowHitlStoreError(
                        CODE_SHADOW_HITL_STORE_BLOCKER,
                        "HITL request not found",
                    )
                if command.interrupt_id != request_row["interrupt_id"]:
                    raise ShadowHitlStoreError(
                        CODE_SHADOW_HITL_STORE_BLOCKER,
                        "interrupt_id mismatch",
                    )
                if command.run_id != request_row["run_id"]:
                    raise ShadowHitlStoreError(
                        CODE_SHADOW_HITL_STORE_BLOCKER,
                        "run_id mismatch",
                    )
                if command.mission_id != request_row["mission_id"]:
                    raise ShadowHitlStoreError(
                        CODE_SHADOW_HITL_STORE_BLOCKER,
                        "mission_id mismatch",
                    )
                answer_row = self._connection.execute(
                    """
                    SELECT payload_json
                    FROM hitl_answers
                    WHERE interrupt_id = ?
                    """,
                    (bound_interrupt_id,),
                ).fetchone()
                if answer_row is not None:
                    existing = _command_from_payload(
                        _json_loads(answer_row["payload_json"])
                    )
                    if _command_identity(existing) != _command_identity(command):
                        raise ShadowHitlStoreError(
                            CODE_SHADOW_HITL_STORE_BLOCKER,
                            "conflicting HITL answer for interrupt_id",
                        )
                    self._connection.execute("COMMIT")
                    return
                self._connection.execute(
                    """
                    INSERT INTO hitl_answers (
                        decision_id, interrupt_id, run_id, mission_id,
                        decision, submitted_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        command.decision_id,
                        command.interrupt_id,
                        command.run_id,
                        command.mission_id,
                        command.decision,
                        submitted_at,
                        payload_json,
                    ),
                )
                self._connection.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise ShadowHitlStoreError(
                    CODE_SHADOW_HITL_STORE_BLOCKER,
                    "HITL answer identity collision",
                ) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def get_request(
        self,
        interrupt_id: str,
    ) -> Optional[ConstructorHumanDecisionRequest]:
        self._require_open()
        key = str(interrupt_id or "").strip()
        if not key:
            raise ShadowHitlStoreError(
                CODE_SHADOW_HITL_STORE_BLOCKER,
                "interrupt_id is required",
            )
        with self._lock:
            row = self._connection.execute(
                """
                SELECT interrupt_id, run_id, mission_id, wait_ordinal,
                       status, reason_code, created_at, payload_json
                FROM hitl_open_requests
                WHERE interrupt_id = ?
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        request = _request_from_payload(_json_loads(row["payload_json"]))
        _require_request_columns_match(request, row)
        return request

    def get_answer_for_interrupt(
        self,
        interrupt_id: str,
    ) -> Optional[ConstructorResumeCommand]:
        self._require_open()
        key = str(interrupt_id or "").strip()
        if not key:
            raise ShadowHitlStoreError(
                CODE_SHADOW_HITL_STORE_BLOCKER,
                "interrupt_id is required",
            )
        with self._lock:
            row = self._connection.execute(
                """
                SELECT decision_id, interrupt_id, run_id, mission_id,
                       decision, submitted_at, payload_json
                FROM hitl_answers
                WHERE interrupt_id = ?
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        command = _command_from_payload(_json_loads(row["payload_json"]))
        _require_command_columns_match(command, row)
        return command

    def _require_open(self) -> None:
        if self._closed:
            raise ShadowHitlStoreError(
                CODE_SHADOW_HITL_STORE_BLOCKER,
                "ConstructorShadowHitlStore is closed",
            )


def bootstrap_constructor_shadow_hitl_store(
    *,
    repository_root: Union[str, Path],
) -> ConstructorShadowHitlStore:
    """
    Explicit Shadow HITL infrastructure bootstrap.

    Resolves canonical paths, creates the runtime directory, opens only
    hitl.sqlite, and applies the HITL schema.
    """
    paths = resolve_constructor_shadow_runtime_paths(
        repository_root=repository_root,
    )
    try:
        paths.runtime_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ShadowHitlStoreError(
            CODE_SHADOW_HITL_STORE_BLOCKER,
            "canonical Shadow runtime directory could not be created",
        ) from exc

    try:
        connection = sqlite3.connect(
            str(paths.hitl_db_path),
            check_same_thread=False,
        )
    except sqlite3.Error as exc:
        raise ShadowHitlStoreError(
            CODE_SHADOW_HITL_STORE_BLOCKER,
            "hitl.sqlite could not be opened",
        ) from exc
    connection.row_factory = sqlite3.Row

    try:
        _apply_hitl_schema(connection)
        return ConstructorShadowHitlStore(
            db_path=paths.hitl_db_path,
            connection=connection,
        )
    except BaseException:
        connection.close()
        raise


def _apply_hitl_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(_BOOTSTRAP_SQL)
    connection.commit()


def _json_dumps(payload: Mapping[str, Any]) -> str:
    try:
        return json.dumps(payload, **_JSON_DUMP_KWARGS)
    except (TypeError, ValueError) as exc:
        raise ShadowHitlStoreError(
            CODE_SHADOW_HITL_STORE_BLOCKER,
            "HITL payload is not JSON-safe",
        ) from exc


def _json_loads(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ShadowHitlStoreError(
            CODE_SHADOW_HITL_STORE_BLOCKER,
            "HITL payload JSON is corrupt",
        ) from exc
    if not isinstance(payload, dict):
        raise ShadowHitlStoreError(
            CODE_SHADOW_HITL_STORE_BLOCKER,
            "HITL payload JSON must be an object",
        )
    return payload


def _datetime_to_iso(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise ShadowHitlStoreError(
            CODE_SHADOW_HITL_STORE_BLOCKER,
            "timestamp must be datetime",
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise ShadowHitlStoreError(
            CODE_SHADOW_HITL_STORE_BLOCKER,
            "timestamp must be timezone-aware UTC",
        )
    return value.astimezone(timezone.utc).isoformat()


def _datetime_from_iso(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ShadowHitlStoreError(
            CODE_SHADOW_HITL_STORE_BLOCKER,
            "timestamp is required",
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ShadowHitlStoreError(
            CODE_SHADOW_HITL_STORE_BLOCKER,
            "timestamp is not ISO-8601",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ShadowHitlStoreError(
            CODE_SHADOW_HITL_STORE_BLOCKER,
            "timestamp must be timezone-aware UTC",
        )
    return parsed.astimezone(timezone.utc)


def _optional_str_tuple(value: Any) -> Optional[tuple[str, ...]]:
    if value is None:
        return None
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    raise ShadowHitlStoreError(
        CODE_SHADOW_HITL_STORE_BLOCKER,
        "scope dimension must be list, str, or null",
    )


def _scope_to_payload(summary: ScopeSummary) -> dict[str, Any]:
    return {
        "project_code": summary.project_code,
        "month_key": summary.month_key,
        "facility_scope": (
            list(summary.facility_scope) if summary.facility_scope is not None else None
        ),
        "discipline_scope": (
            list(summary.discipline_scope)
            if summary.discipline_scope is not None
            else None
        ),
        "system_scope": (
            list(summary.system_scope) if summary.system_scope is not None else None
        ),
        "iwp_scope": list(summary.iwp_scope) if summary.iwp_scope is not None else None,
        "queue_scope": (
            list(summary.queue_scope) if summary.queue_scope is not None else None
        ),
    }


def _scope_from_payload(payload: Any) -> ScopeSummary:
    if not isinstance(payload, dict):
        raise ShadowHitlStoreError(
            CODE_SHADOW_HITL_STORE_BLOCKER,
            "current_scope_summary must be an object",
        )
    return ScopeSummary(
        project_code=payload.get("project_code"),
        month_key=payload.get("month_key"),
        facility_scope=_optional_str_tuple(payload.get("facility_scope")),
        discipline_scope=_optional_str_tuple(payload.get("discipline_scope")),
        system_scope=_optional_str_tuple(payload.get("system_scope")),
        iwp_scope=_optional_str_tuple(payload.get("iwp_scope")),
        queue_scope=_optional_str_tuple(payload.get("queue_scope")),
    )


def _json_safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        encoded = json.loads(json.dumps(dict(value), **_JSON_DUMP_KWARGS))
    except (TypeError, ValueError) as exc:
        raise ShadowHitlStoreError(
            CODE_SHADOW_HITL_STORE_BLOCKER,
            "HITL payload is not JSON-safe",
        ) from exc
    if not isinstance(encoded, dict):
        raise ShadowHitlStoreError(
            CODE_SHADOW_HITL_STORE_BLOCKER,
            "HITL payload is not JSON-safe",
        )
    return encoded


def _request_to_payload(request: ConstructorHumanDecisionRequest) -> dict[str, Any]:
    return {
        "schema_version": request.schema_version,
        "interrupt_id": request.interrupt_id,
        "run_id": request.run_id,
        "mission_id": request.mission_id,
        "project_code": request.project_code,
        "reason_code": request.reason_code,
        "route": request.route,
        "severity": request.severity,
        "human_readable_reason": request.human_readable_reason,
        "required_decision_type": request.required_decision_type,
        "allowed_decisions": list(request.allowed_decisions),
        "current_scope_summary": _scope_to_payload(request.current_scope_summary),
        "evidence_refs": list(request.evidence_refs),
        "created_at": _datetime_to_iso(request.created_at),
        "status": request.status,
        "source_capability": request.source_capability,
        "authorization_id_ref": request.authorization_id_ref,
        "wait_ordinal": request.wait_ordinal,
    }


def _request_from_payload(payload: Mapping[str, Any]) -> ConstructorHumanDecisionRequest:
    try:
        return build_human_decision_request(
            run_id=payload["run_id"],
            mission_id=payload["mission_id"],
            reason_code=payload["reason_code"],
            route=payload["route"],
            severity=payload["severity"],
            human_readable_reason=payload["human_readable_reason"],
            wait_ordinal=int(payload["wait_ordinal"]),
            current_scope_summary=_scope_from_payload(
                payload.get("current_scope_summary")
            ),
            evidence_refs=payload.get("evidence_refs") or (),
            authorization_id_ref=payload.get("authorization_id_ref"),
            project_code=payload.get("project_code"),
            created_at=_datetime_from_iso(payload.get("created_at")),
            status=str(payload.get("status") or "OPEN"),
            source_capability=str(payload.get("source_capability") or "HITL"),
            interrupt_id=payload["interrupt_id"],
        )
    except (KeyError, TypeError, ValueError, HitlContractError) as exc:
        raise ShadowHitlStoreError(
            CODE_SHADOW_HITL_STORE_BLOCKER,
            "HITL request payload could not be reconstructed",
        ) from exc


def _command_to_payload(command: ConstructorResumeCommand) -> dict[str, Any]:
    return {
        "schema_version": command.schema_version,
        "decision_id": command.decision_id,
        "interrupt_id": command.interrupt_id,
        "run_id": command.run_id,
        "mission_id": command.mission_id,
        "expected_checkpoint_id": command.expected_checkpoint_id,
        "actor_type": command.actor_type,
        "actor_id": command.actor_id,
        "decision": command.decision,
        "parameters": _json_safe_mapping(command.parameters),
        "comment": command.comment,
        "submitted_at": _datetime_to_iso(command.submitted_at),
        "idempotency_key": command.idempotency_key,
    }


def _command_from_payload(payload: Mapping[str, Any]) -> ConstructorResumeCommand:
    try:
        return build_resume_command(
            decision_id=payload["decision_id"],
            interrupt_id=payload["interrupt_id"],
            run_id=payload["run_id"],
            mission_id=payload["mission_id"],
            decision=payload["decision"],
            actor_id=payload["actor_id"],
            actor_type=str(payload.get("actor_type") or "HUMAN"),
            parameters=payload.get("parameters") or {},
            comment=payload.get("comment"),
            expected_checkpoint_id=payload.get("expected_checkpoint_id"),
            submitted_at=_datetime_from_iso(payload.get("submitted_at")),
            idempotency_key=payload.get("idempotency_key"),
        )
    except (KeyError, TypeError, ValueError, HitlContractError) as exc:
        raise ShadowHitlStoreError(
            CODE_SHADOW_HITL_STORE_BLOCKER,
            "HITL answer payload could not be reconstructed",
        ) from exc


def _request_identity(request: ConstructorHumanDecisionRequest) -> tuple[Any, ...]:
    return (
        request.schema_version,
        request.interrupt_id,
        request.run_id,
        request.mission_id,
        request.project_code,
        request.reason_code,
        request.route,
        request.severity,
        request.human_readable_reason,
        request.required_decision_type,
        request.allowed_decisions,
        request.current_scope_summary,
        request.evidence_refs,
        request.status,
        request.source_capability,
        request.authorization_id_ref,
        request.wait_ordinal,
    )


def _command_identity(command: ConstructorResumeCommand) -> tuple[Any, ...]:
    return (
        command.schema_version,
        command.decision_id,
        command.interrupt_id,
        command.run_id,
        command.mission_id,
        command.expected_checkpoint_id,
        command.actor_type,
        command.actor_id,
        command.decision,
        _json_dumps(_json_safe_mapping(command.parameters)),
        command.comment,
        _datetime_to_iso(command.submitted_at),
        command.idempotency_key,
    )


def _require_request_columns_match(
    request: ConstructorHumanDecisionRequest,
    row: sqlite3.Row,
) -> None:
    if (
        request.interrupt_id != row["interrupt_id"]
        or request.run_id != row["run_id"]
        or request.mission_id != row["mission_id"]
        or request.wait_ordinal != row["wait_ordinal"]
        or request.status != row["status"]
        or request.reason_code != row["reason_code"]
        or _datetime_to_iso(request.created_at) != row["created_at"]
    ):
        raise ShadowHitlStoreError(
            CODE_SHADOW_HITL_STORE_BLOCKER,
            "HITL request columns diverge from payload",
        )


def _require_command_columns_match(
    command: ConstructorResumeCommand,
    row: sqlite3.Row,
) -> None:
    if (
        command.decision_id != row["decision_id"]
        or command.interrupt_id != row["interrupt_id"]
        or command.run_id != row["run_id"]
        or command.mission_id != row["mission_id"]
        or command.decision != row["decision"]
        or _datetime_to_iso(command.submitted_at) != row["submitted_at"]
    ):
        raise ShadowHitlStoreError(
            CODE_SHADOW_HITL_STORE_BLOCKER,
            "HITL answer columns diverge from payload",
        )
