"""PSAA-02 — append-only Shift Audit History stores.

Patterns reused from Constructor handoff stores:
put-if-absent · content-hash conflict · read-after-write verify.

Not a product write into daily_progress / Airtable.
Not observability event store.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from agents.production_shift_auditor.history_contracts import (
    CODE_HISTORY_BLOCKER,
    CODE_HISTORY_CONFLICT,
    CODE_HISTORY_PROJECT_DENIED,
    CODE_HISTORY_READBACK_MISMATCH,
    CODE_HISTORY_WRITE_FAILED,
    STATUS_CREATED,
    STATUS_IDEMPOTENT_REPLAY,
    PersistHistoryResult,
    ShiftAuditHistoryError,
    ShiftAuditHistoryRecord,
    canonical_json,
    record_from_dict,
)

_TABLE = "psaa_shift_audit_history"

_BOOTSTRAP_SQL = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
    audit_id TEXT PRIMARY KEY,
    project_code TEXT NOT NULL,
    work_date TEXT NOT NULL,
    shift_type TEXT,
    crew_id TEXT NOT NULL,
    record_content_hash TEXT NOT NULL,
    audited_at_utc TEXT NOT NULL,
    persisted_at_utc TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_psaa_audit_history_grain
ON {_TABLE} (project_code, work_date, crew_id, shift_type);

CREATE INDEX IF NOT EXISTS ix_psaa_audit_history_project
ON {_TABLE} (project_code, audited_at_utc);
"""


@runtime_checkable
class ShiftAuditHistoryStore(Protocol):
    def put_if_absent(self, record: ShiftAuditHistoryRecord) -> PersistHistoryResult:
        ...

    def get_by_audit_id(
        self, audit_id: str, *, project_code: str
    ) -> Optional[ShiftAuditHistoryRecord]:
        ...

    def list_for_shift(
        self,
        *,
        project_code: str,
        work_date: str,
        crew_id: str,
        shift_type: Optional[str] = None,
    ) -> tuple[ShiftAuditHistoryRecord, ...]:
        ...


class InMemoryShiftAuditHistoryStore:
    """Process-local store for unit tests. Not durability proof."""

    def __init__(self, *, fail_next_write: bool = False) -> None:
        self._lock = threading.RLock()
        self._by_id: dict[str, ShiftAuditHistoryRecord] = {}
        self.fail_next_write = fail_next_write

    def put_if_absent(self, record: ShiftAuditHistoryRecord) -> PersistHistoryResult:
        with self._lock:
            if self.fail_next_write:
                self.fail_next_write = False
                raise ShiftAuditHistoryError(
                    CODE_HISTORY_WRITE_FAILED, "injected write failure"
                )
            existing = self._by_id.get(record.audit_id)
            if existing is None:
                self._by_id[record.audit_id] = record
                readback = self._by_id[record.audit_id]
                _assert_readback(record, readback)
                return PersistHistoryResult(status=STATUS_CREATED, record=readback)
            if existing.record_content_hash != record.record_content_hash:
                raise ShiftAuditHistoryError(
                    CODE_HISTORY_CONFLICT,
                    "audit_id already persisted with a different content hash",
                )
            return PersistHistoryResult(
                status=STATUS_IDEMPOTENT_REPLAY, record=existing
            )

    def get_by_audit_id(
        self, audit_id: str, *, project_code: str
    ) -> Optional[ShiftAuditHistoryRecord]:
        with self._lock:
            rec = self._by_id.get(audit_id)
            if rec is None:
                return None
            if rec.project_code != project_code:
                raise ShiftAuditHistoryError(
                    CODE_HISTORY_PROJECT_DENIED,
                    "audit belongs to a different project_code",
                )
            return rec

    def list_for_shift(
        self,
        *,
        project_code: str,
        work_date: str,
        crew_id: str,
        shift_type: Optional[str] = None,
    ) -> tuple[ShiftAuditHistoryRecord, ...]:
        with self._lock:
            rows = [
                r
                for r in self._by_id.values()
                if r.project_code == project_code
                and r.work_date == work_date
                and r.crew_id == crew_id
                and (
                    shift_type is None
                    or (r.shift_type or "") == (shift_type or "")
                )
            ]
            rows.sort(key=lambda r: (r.audited_at_utc, r.audit_id))
            return tuple(rows)


class SqliteShiftAuditHistoryStore:
    """Durable SQLite append-only store (local runtime). Not production Supabase."""

    def __init__(self, *, db_path: Path, connection: sqlite3.Connection) -> None:
        self.db_path = Path(db_path)
        self._conn = connection
        self._lock = threading.RLock()
        self._closed = False

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._conn.close()
                self._closed = True

    def put_if_absent(self, record: ShiftAuditHistoryRecord) -> PersistHistoryResult:
        self._require_open()
        payload = canonical_json(record.to_dict())
        with self._lock:
            try:
                cur = self._conn.execute(
                    f"SELECT record_content_hash, payload_json FROM {_TABLE} WHERE audit_id = ?",
                    (record.audit_id,),
                )
                row = cur.fetchone()
                if row is None:
                    self._conn.execute(
                        f"""
                        INSERT INTO {_TABLE} (
                            audit_id, project_code, work_date, shift_type, crew_id,
                            record_content_hash, audited_at_utc, persisted_at_utc, payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            record.audit_id,
                            record.project_code,
                            record.work_date,
                            record.shift_type,
                            record.crew_id,
                            record.record_content_hash,
                            record.audited_at_utc,
                            record.persisted_at_utc,
                            payload,
                        ),
                    )
                    self._conn.commit()
                    readback = self.get_by_audit_id(
                        record.audit_id, project_code=record.project_code
                    )
                    if readback is None:
                        raise ShiftAuditHistoryError(
                            CODE_HISTORY_READBACK_MISMATCH, "missing after insert"
                        )
                    _assert_readback(record, readback)
                    return PersistHistoryResult(status=STATUS_CREATED, record=readback)

                existing_hash, existing_payload = row[0], row[1]
                if existing_hash != record.record_content_hash:
                    raise ShiftAuditHistoryError(
                        CODE_HISTORY_CONFLICT,
                        "audit_id already persisted with a different content hash",
                    )
                existing = record_from_dict(json.loads(existing_payload))
                return PersistHistoryResult(
                    status=STATUS_IDEMPOTENT_REPLAY, record=existing
                )
            except ShiftAuditHistoryError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise ShiftAuditHistoryError(
                    CODE_HISTORY_WRITE_FAILED, f"sqlite write failed: {exc}"
                ) from exc

    def get_by_audit_id(
        self, audit_id: str, *, project_code: str
    ) -> Optional[ShiftAuditHistoryRecord]:
        self._require_open()
        with self._lock:
            cur = self._conn.execute(
                f"SELECT project_code, payload_json FROM {_TABLE} WHERE audit_id = ?",
                (audit_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            if str(row[0]) != project_code:
                raise ShiftAuditHistoryError(
                    CODE_HISTORY_PROJECT_DENIED,
                    "audit belongs to a different project_code",
                )
            return record_from_dict(json.loads(row[1]))

    def list_for_shift(
        self,
        *,
        project_code: str,
        work_date: str,
        crew_id: str,
        shift_type: Optional[str] = None,
    ) -> tuple[ShiftAuditHistoryRecord, ...]:
        self._require_open()
        with self._lock:
            if shift_type is None:
                cur = self._conn.execute(
                    f"""
                    SELECT payload_json FROM {_TABLE}
                    WHERE project_code = ? AND work_date = ? AND crew_id = ?
                    ORDER BY audited_at_utc ASC, audit_id ASC
                    """,
                    (project_code, work_date, crew_id),
                )
            else:
                cur = self._conn.execute(
                    f"""
                    SELECT payload_json FROM {_TABLE}
                    WHERE project_code = ? AND work_date = ? AND crew_id = ?
                      AND IFNULL(shift_type, '') = ?
                    ORDER BY audited_at_utc ASC, audit_id ASC
                    """,
                    (project_code, work_date, crew_id, shift_type),
                )
            return tuple(record_from_dict(json.loads(r[0])) for r in cur.fetchall())

    def _require_open(self) -> None:
        if self._closed:
            raise ShiftAuditHistoryError(CODE_HISTORY_BLOCKER, "history store is closed")


def open_sqlite_history_store(db_path: Path) -> SqliteShiftAuditHistoryStore:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_BOOTSTRAP_SQL)
    conn.commit()
    return SqliteShiftAuditHistoryStore(db_path=path, connection=conn)


def open_existing_sqlite_history_store(
    db_path: Path,
) -> Optional[SqliteShiftAuditHistoryStore]:
    path = Path(db_path)
    if not path.is_file():
        return None
    conn = sqlite3.connect(path)
    return SqliteShiftAuditHistoryStore(db_path=path, connection=conn)


def default_psaa_history_db_path() -> Path:
    """Local runtime path under repository .runtime (not product Supabase)."""
    root = Path(__file__).resolve().parents[2]
    return root / ".runtime" / "psaa" / "shift_audit_history.sqlite"


def _assert_readback(
    expected: ShiftAuditHistoryRecord, actual: ShiftAuditHistoryRecord
) -> None:
    if (
        actual.audit_id != expected.audit_id
        or actual.project_code != expected.project_code
        or actual.record_content_hash != expected.record_content_hash
        or actual.input_content_hash != expected.input_content_hash
        or actual.artifact_content_hash != expected.artifact_content_hash
        or actual.math_integrity_status != expected.math_integrity_status
    ):
        raise ShiftAuditHistoryError(
            CODE_HISTORY_READBACK_MISMATCH, "history read-back mismatch"
        )
