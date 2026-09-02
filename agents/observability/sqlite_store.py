"""
Increment 10.4 — file-backed SQLite ObservabilityStore.

Agent-neutral. Stdlib sqlite3 only. No product Supabase. No SQL exposure to callers.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Optional, Union

from agents.observability.contracts import AgentRun, ObservabilityContractError, ObservabilityEvent
from agents.observability.projection import AgentRunProjectionChange
from agents.observability.recorder import RecordOutcome
from agents.observability.store import (
    DEFAULT_LIST_EVENTS_LIMIT,
    DEFAULT_LIST_RUNS_LIMIT,
    AppendEventResult,
    CreateRunOutcome,
    CreateRunResult,
    ObservabilityProjectionVersionConflictError,
    ObservabilityRunIdentityConflictError,
    ObservabilityRunNotFoundError,
    ObservabilityStorageFailureError,
    _agent_run_from_dict,
    _observability_event_from_dict,
    _require_bounded_limit,
    _serialize_agent_run,
    _serialize_event,
    compute_agent_run_identity_digest,
    execute_append_event_and_project_run,
    execute_create_run,
    validate_store_event,
    validate_store_run,
    MAX_LIST_EVENTS_LIMIT,
    MAX_LIST_RUNS_LIMIT,
)

_SCHEMA_VERSION = 1

_BOOTSTRAP_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    identity_digest TEXT NOT NULL,
    projection_version INTEGER NOT NULL,
    run_payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_run_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    append_sequence INTEGER NOT NULL,
    event_fingerprint TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    event_payload TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id),
    UNIQUE (run_id, append_sequence)
);

CREATE INDEX IF NOT EXISTS idx_agent_run_events_run_sequence
    ON agent_run_events(run_id, append_sequence);
"""


class SqliteObservabilityStore:
    """File-backed durable ObservabilityStore using stdlib sqlite3."""

    def __init__(self, db_path: Union[str, Path]) -> None:
        self._db_path = str(db_path)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self._db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.executescript(_BOOTSTRAP_SQL)
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def create_run(self, run: AgentRun) -> CreateRunResult:
        validated = validate_store_run(run)
        digest = compute_agent_run_identity_digest(validated)
        payload = _serialize_agent_run(validated)
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                row = self._connection.execute(
                    "SELECT identity_digest, projection_version FROM agent_runs WHERE run_id = ?",
                    (validated.run_id,),
                ).fetchone()
                if row is None:
                    self._connection.execute(
                        """
                        INSERT INTO agent_runs (run_id, identity_digest, projection_version, run_payload)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            validated.run_id,
                            digest,
                            validated.projection_version,
                            payload,
                        ),
                    )
                    self._connection.commit()
                    return CreateRunResult(
                        outcome=CreateRunOutcome.CREATED,
                        run_id=validated.run_id,
                        projection_version=validated.projection_version,
                    )
                if row["identity_digest"] != digest:
                    self._connection.rollback()
                    raise ObservabilityRunIdentityConflictError(
                        f"run_id {validated.run_id!r} already exists with different immutable identity",
                    )
                self._connection.commit()
                return CreateRunResult(
                    outcome=CreateRunOutcome.IDEMPOTENT_REPLAY,
                    run_id=validated.run_id,
                    projection_version=int(row["projection_version"]),
                )
            except (
                ObservabilityRunIdentityConflictError,
                ObservabilityRunNotFoundError,
                ObservabilityStorageFailureError,
            ):
                self._connection.rollback()
                raise
            except Exception as exc:
                self._connection.rollback()
                raise ObservabilityStorageFailureError(str(exc)) from exc

    def get_run(self, run_id: str) -> AgentRun:
        with self._lock:
            row = self._connection.execute(
                "SELECT run_payload FROM agent_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise ObservabilityRunNotFoundError(f"run_id {run_id!r} not found")
            import json

            return _agent_run_from_dict(json.loads(row["run_payload"]))

    def append_event_and_project_run(
        self,
        *,
        event: ObservabilityEvent,
        expected_projection_version: int,
        projection_change: AgentRunProjectionChange,
    ) -> AppendEventResult:
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                existing_fp_row = self._connection.execute(
                    "SELECT event_fingerprint FROM agent_run_events WHERE event_id = ?",
                    (event.event_id,),
                ).fetchone()
                existing_fp = (
                    None if existing_fp_row is None else str(existing_fp_row["event_fingerprint"])
                )
                run_row = self._connection.execute(
                    "SELECT run_payload, projection_version FROM agent_runs WHERE run_id = ?",
                    (event.run_id,),
                ).fetchone()
                current_run = None
                if run_row is not None:
                    import json

                    current_run = _agent_run_from_dict(json.loads(run_row["run_payload"]))

                result, updated, fingerprint, _seq_delta = execute_append_event_and_project_run(
                    event=event,
                    expected_projection_version=expected_projection_version,
                    projection_change=projection_change,
                    existing_fingerprint=existing_fp,
                    current_run=current_run,
                )
                if result.outcome is RecordOutcome.IDEMPOTENT_REPLAY:
                    self._connection.commit()
                    return result

                seq_row = self._connection.execute(
                    "SELECT COALESCE(MAX(append_sequence), 0) AS max_seq FROM agent_run_events WHERE run_id = ?",
                    (event.run_id,),
                ).fetchone()
                next_sequence = int(seq_row["max_seq"]) + 1
                artifact = validate_store_event(event)
                self._connection.execute(
                    """
                    INSERT INTO agent_run_events (
                        event_id, run_id, append_sequence, event_fingerprint, occurred_at, event_payload
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact.event_id,
                        artifact.run_id,
                        next_sequence,
                        fingerprint,
                        artifact.occurred_at.astimezone(
                            __import__("datetime").timezone.utc
                        ).isoformat(),
                        _serialize_event(artifact),
                    ),
                )
                update_cursor = self._connection.execute(
                    """
                    UPDATE agent_runs
                    SET projection_version = ?, run_payload = ?
                    WHERE run_id = ? AND projection_version = ?
                    """,
                    (
                        updated.projection_version,
                        _serialize_agent_run(updated),
                        updated.run_id,
                        expected_projection_version,
                    ),
                )
                if update_cursor.rowcount != 1:
                    self._connection.rollback()
                    raise ObservabilityProjectionVersionConflictError(
                        "expected_projection_version does not match stored projection_version",
                    )
                self._connection.commit()
                return result
            except (
                ObservabilityRunNotFoundError,
                ObservabilityStorageFailureError,
                ObservabilityProjectionVersionConflictError,
                ObservabilityContractError,
            ):
                self._connection.rollback()
                raise
            except Exception as exc:
                self._connection.rollback()
                from agents.observability.recorder import ObservabilityEventConflictError

                if isinstance(
                    exc,
                    (
                        ObservabilityEventConflictError,
                        ObservabilityProjectionVersionConflictError,
                        ObservabilityRunNotFoundError,
                        ObservabilityRunIdentityConflictError,
                        ObservabilityContractError,
                    ),
                ):
                    raise
                raise ObservabilityStorageFailureError(str(exc)) from exc

    def list_events(
        self,
        run_id: str,
        *,
        limit: int = DEFAULT_LIST_EVENTS_LIMIT,
    ) -> tuple[ObservabilityEvent, ...]:
        bounded = _require_bounded_limit(limit, maximum=MAX_LIST_EVENTS_LIMIT, label="limit")
        with self._lock:
            exists = self._connection.execute(
                "SELECT 1 FROM agent_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if exists is None:
                raise ObservabilityRunNotFoundError(f"run_id {run_id!r} not found")
            rows = self._connection.execute(
                """
                SELECT event_payload
                FROM agent_run_events
                WHERE run_id = ?
                ORDER BY append_sequence ASC
                LIMIT ?
                """,
                (run_id, bounded),
            ).fetchall()
            import json

            return tuple(_observability_event_from_dict(json.loads(row["event_payload"])) for row in rows)

    def list_runs(
        self,
        *,
        limit: int = DEFAULT_LIST_RUNS_LIMIT,
        agent_code: Optional[str] = None,
    ) -> tuple[AgentRun, ...]:
        bounded = _require_bounded_limit(limit, maximum=MAX_LIST_RUNS_LIMIT, label="limit")
        with self._lock:
            if agent_code is None:
                rows = self._connection.execute(
                    """
                    SELECT run_payload
                    FROM agent_runs
                    ORDER BY json_extract(run_payload, '$.requested_at'), run_id
                    LIMIT ?
                    """,
                    (bounded,),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    """
                    SELECT run_payload
                    FROM agent_runs
                    WHERE json_extract(run_payload, '$.agent_code') = ?
                    ORDER BY json_extract(run_payload, '$.requested_at'), run_id
                    LIMIT ?
                    """,
                    (agent_code, bounded),
                ).fetchall()
            import json

            return tuple(_agent_run_from_dict(json.loads(row["run_payload"])) for row in rows)
