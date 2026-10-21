"""
Professional Handoff of the Human-Approved Monthly Candidate Package.

Transfers HUMAN INTENT / PROPOSED MONTHLY SCOPE to the production-readiness
and Admission contour. It is NOT a monthly production commitment, does NOT
create an Admission run, and has NO connected receiver yet:

    HANDOFF_PERSISTED + RECEIVER NOT CONNECTED

Mirrors the existing Final Confirm store pattern: deterministic identity,
put-if-absent idempotency, read-after-write verification. Streamlit never
writes the store directly.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agents.human_surface.final_confirm_command import find_current_approved_package
from agents.monthly_plan_constructor.approved_monthly_package import (
    ApprovedMonthlyPackage,
    canonical_json,
)

SCHEMA_VERSION = "approved_candidate_handoff.v1"
# Existing Constructor handoff architecture codes (handoff_contracts.py).
SOURCE_ROLE_CODE = "MONTHLY_PLAN_CONSTRUCTOR"
TARGET_ROLE_CODE = "MONTHLY_PLAN_ADMISSION_AGENT"
TARGET_ROLE_RU = "Инженер производственной готовности и допуска"
HANDOFF_TYPE = "CONSTRUCTOR_TO_ADMISSION"
HANDOFF_OBJECT_KIND = "HUMAN_APPROVED_MONTHLY_CANDIDATE_PACKAGE"

STATUS_HANDOFF_PERSISTED = "HANDOFF_PERSISTED"
STATUS_ALREADY_HANDED_OFF = "ALREADY_HANDED_OFF"
RECEIVER_NOT_CONNECTED = "RECEIVER_NOT_CONNECTED"

HANDOFF_PERSISTED_RU = "ПАКЕТ ПЕРЕДАН В КОНТУР ПРОИЗВОДСТВЕННОЙ ГОТОВНОСТИ И ДОПУСКА"
RECEIVER_NOT_CONNECTED_RU = "ещё не подключён"

CODE_HANDOFF_BLOCKER = "APPROVED_CANDIDATE_HANDOFF_BLOCKER"
CODE_HANDOFF_CONFLICT = "APPROVED_CANDIDATE_HANDOFF_CONFLICT"
CODE_HANDOFF_READBACK_MISMATCH = "APPROVED_CANDIDATE_HANDOFF_READBACK_MISMATCH"

_TABLE = "professional_handoffs"
_BOOTSTRAP_SQL = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
    handoff_id TEXT PRIMARY KEY,
    human_approved_package_id TEXT NOT NULL,
    target_role_code TEXT NOT NULL,
    artifact_content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_professional_handoff_artifact_target
ON {_TABLE} (human_approved_package_id, target_role_code);
"""


class CandidateHandoffError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class ApprovedCandidateHandoff:
    """Immutable reference to one human-approved candidate package."""

    schema_version: str
    handoff_id: str
    source_role_code: str
    target_role_code: str
    project_code: str
    month_key: str
    source_run_id: str
    source_candidate_package_id: str
    human_approved_package_id: str
    artifact_content_hash: str
    handoff_type: str
    handed_off_object: str
    created_at: str
    created_by: str
    professional_status: str
    receiver_status: str


@dataclass(frozen=True)
class CandidateHandoffResult:
    status: str
    handoff: ApprovedCandidateHandoff


def compute_handoff_id(
    *,
    human_approved_package_id: str,
    artifact_content_hash: str,
    target_role_code: str = TARGET_ROLE_CODE,
) -> str:
    """Deterministic identity — same artifact + same target → same handoff."""
    material = "|".join(
        (
            SCHEMA_VERSION,
            HANDOFF_TYPE,
            SOURCE_ROLE_CODE,
            target_role_code,
            human_approved_package_id,
            artifact_content_hash,
        )
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
    return f"eos-hof-{digest}"


def build_handoff(
    package: ApprovedMonthlyPackage,
    *,
    created_by: str,
    now: Optional[datetime] = None,
) -> ApprovedCandidateHandoff:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise CandidateHandoffError(
            CODE_HANDOFF_BLOCKER, "created_at must be timezone-aware"
        )
    stamp = stamp.astimezone(timezone.utc)
    actor = str(created_by or "").strip()
    if not actor:
        raise CandidateHandoffError(CODE_HANDOFF_BLOCKER, "created_by is required")
    approved_id = str(package.approved_package_id or "").strip()
    content_hash = str(package.content_hash or "").strip()
    if not approved_id or not content_hash:
        raise CandidateHandoffError(
            CODE_HANDOFF_BLOCKER,
            "approved package identity / content_hash is required",
        )
    return ApprovedCandidateHandoff(
        schema_version=SCHEMA_VERSION,
        handoff_id=compute_handoff_id(
            human_approved_package_id=approved_id,
            artifact_content_hash=content_hash,
        ),
        source_role_code=SOURCE_ROLE_CODE,
        target_role_code=TARGET_ROLE_CODE,
        project_code=str(package.project_code),
        month_key=str(package.month_key),
        source_run_id=str(package.source_run_id),
        source_candidate_package_id=str(package.source_candidate_package_id),
        human_approved_package_id=approved_id,
        artifact_content_hash=content_hash,
        handoff_type=HANDOFF_TYPE,
        handed_off_object=HANDOFF_OBJECT_KIND,
        created_at=stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        created_by=actor,
        professional_status=STATUS_HANDOFF_PERSISTED,
        receiver_status=RECEIVER_NOT_CONNECTED,
    )


def _payload(handoff: ApprovedCandidateHandoff) -> dict:
    return {
        "schema_version": handoff.schema_version,
        "handoff_id": handoff.handoff_id,
        "source_role_code": handoff.source_role_code,
        "target_role_code": handoff.target_role_code,
        "project_code": handoff.project_code,
        "month_key": handoff.month_key,
        "source_run_id": handoff.source_run_id,
        "source_candidate_package_id": handoff.source_candidate_package_id,
        "human_approved_package_id": handoff.human_approved_package_id,
        "artifact_content_hash": handoff.artifact_content_hash,
        "handoff_type": handoff.handoff_type,
        "handed_off_object": handoff.handed_off_object,
        "created_at": handoff.created_at,
        "created_by": handoff.created_by,
        "professional_status": handoff.professional_status,
        "receiver_status": handoff.receiver_status,
    }


def _from_payload(payload: dict) -> ApprovedCandidateHandoff:
    return ApprovedCandidateHandoff(
        schema_version=str(payload["schema_version"]),
        handoff_id=str(payload["handoff_id"]),
        source_role_code=str(payload["source_role_code"]),
        target_role_code=str(payload["target_role_code"]),
        project_code=str(payload["project_code"]),
        month_key=str(payload["month_key"]),
        source_run_id=str(payload["source_run_id"]),
        source_candidate_package_id=str(payload["source_candidate_package_id"]),
        human_approved_package_id=str(payload["human_approved_package_id"]),
        artifact_content_hash=str(payload["artifact_content_hash"]),
        handoff_type=str(payload["handoff_type"]),
        handed_off_object=str(payload["handed_off_object"]),
        created_at=str(payload["created_at"]),
        created_by=str(payload["created_by"]),
        professional_status=str(payload["professional_status"]),
        receiver_status=str(payload["receiver_status"]),
    )


class ApprovedCandidateHandoffStore:
    """SQLite put-if-absent store beside the Approved Monthly Package store."""

    def __init__(self, *, db_path: Path, connection: sqlite3.Connection) -> None:
        self._db_path = Path(db_path)
        self._connection = connection
        self._closed = False
        self._lock = threading.Lock()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._connection.close()

    def _table_exists(self) -> bool:
        row = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (_TABLE,),
        ).fetchone()
        return row is not None

    def get_by_id(self, handoff_id: str) -> Optional[ApprovedCandidateHandoff]:
        self._require_open()
        if not self._table_exists():
            return None
        with self._lock:
            row = self._connection.execute(
                f"SELECT payload_json FROM {_TABLE} WHERE handoff_id = ?",
                (str(handoff_id or "").strip(),),
            ).fetchone()
        return _from_payload(json.loads(row[0])) if row else None

    def find_by_approved_package(
        self,
        human_approved_package_id: str,
        *,
        target_role_code: str = TARGET_ROLE_CODE,
    ) -> Optional[ApprovedCandidateHandoff]:
        self._require_open()
        if not self._table_exists():
            return None
        with self._lock:
            row = self._connection.execute(
                f"""
                SELECT payload_json FROM {_TABLE}
                WHERE human_approved_package_id = ? AND target_role_code = ?
                """,
                (str(human_approved_package_id or "").strip(), target_role_code),
            ).fetchone()
        return _from_payload(json.loads(row[0])) if row else None

    def put_if_absent(
        self, handoff: ApprovedCandidateHandoff
    ) -> tuple[bool, ApprovedCandidateHandoff]:
        self._require_open()
        payload_json = canonical_json(_payload(handoff))
        with self._lock:
            try:
                self._connection.execute("BEGIN")
                existing = self._connection.execute(
                    f"""
                    SELECT artifact_content_hash, payload_json FROM {_TABLE}
                    WHERE human_approved_package_id = ? AND target_role_code = ?
                    """,
                    (handoff.human_approved_package_id, handoff.target_role_code),
                ).fetchone()
                if existing is not None:
                    if str(existing[0]) != handoff.artifact_content_hash:
                        raise CandidateHandoffError(
                            CODE_HANDOFF_CONFLICT,
                            "approved artifact already handed off with a different hash",
                        )
                    self._connection.execute("COMMIT")
                    return False, _from_payload(json.loads(existing[1]))
                self._connection.execute(
                    f"""
                    INSERT INTO {_TABLE} (
                        handoff_id,
                        human_approved_package_id,
                        target_role_code,
                        artifact_content_hash,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        handoff.handoff_id,
                        handoff.human_approved_package_id,
                        handoff.target_role_code,
                        handoff.artifact_content_hash,
                        payload_json,
                    ),
                )
                self._connection.execute("COMMIT")
                return True, handoff
            except CandidateHandoffError:
                self._connection.execute("ROLLBACK")
                raise
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise CandidateHandoffError(
                    CODE_HANDOFF_CONFLICT, "handoff identity collision"
                ) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def _require_open(self) -> None:
        if self._closed:
            raise CandidateHandoffError(CODE_HANDOFF_BLOCKER, "handoff store is closed")


def open_handoff_store(db_path: Path) -> ApprovedCandidateHandoffStore:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(_BOOTSTRAP_SQL)
    connection.commit()
    return ApprovedCandidateHandoffStore(db_path=path, connection=connection)


def open_existing_handoff_store(db_path: Path) -> Optional[ApprovedCandidateHandoffStore]:
    path = Path(db_path)
    if not path.is_file():
        return None
    return ApprovedCandidateHandoffStore(
        db_path=path, connection=sqlite3.connect(path)
    )


def production_handoff_db_path() -> Path:
    """Same immutable-artifact directory as the Approved Monthly Package store."""
    from agents.human_surface.final_confirm_command import _production_store_path

    return _production_store_path()


def submit_handoff_for_package(
    package: ApprovedMonthlyPackage,
    *,
    store: ApprovedCandidateHandoffStore,
    created_by: str = "human-surface-operator",
    now: Optional[datetime] = None,
) -> CandidateHandoffResult:
    """Persist handoff for one immutable approved package. Idempotent."""
    handoff = build_handoff(package, created_by=created_by, now=now)
    created, stored = store.put_if_absent(handoff)
    readback = store.get_by_id(stored.handoff_id)
    if (
        readback is None
        or readback.human_approved_package_id != handoff.human_approved_package_id
        or readback.artifact_content_hash != handoff.artifact_content_hash
        or readback.source_candidate_package_id != handoff.source_candidate_package_id
        or readback.source_run_id != handoff.source_run_id
    ):
        raise CandidateHandoffError(
            CODE_HANDOFF_READBACK_MISMATCH, "handoff read-back mismatch"
        )
    status = STATUS_HANDOFF_PERSISTED if created else STATUS_ALREADY_HANDED_OFF
    return CandidateHandoffResult(status=status, handoff=readback)


def submit_approved_candidate_handoff(
    run_id: str,
    *,
    created_by: str = "human-surface-operator",
    store: Optional[ApprovedCandidateHandoffStore] = None,
    now: Optional[datetime] = None,
) -> CandidateHandoffResult:
    """Production path: approved artifact must exist (durable read verified)."""
    package = find_current_approved_package(str(run_id))
    if package is None:
        raise CandidateHandoffError(
            CODE_HANDOFF_BLOCKER,
            "human-approved candidate package not found for run",
        )
    owned = store is None
    target = store if store is not None else open_handoff_store(production_handoff_db_path())
    try:
        return submit_handoff_for_package(
            package, store=target, created_by=created_by, now=now
        )
    finally:
        if owned:
            target.close()


def find_existing_approved_candidate_handoff(
    run_id: str,
    *,
    store: Optional[ApprovedCandidateHandoffStore] = None,
) -> Optional[ApprovedCandidateHandoff]:
    """Read-only lookup. Never creates a store file for a missing database."""
    package = find_current_approved_package(str(run_id))
    if package is None:
        return None
    owned = False
    target = store
    if target is None:
        target = open_existing_handoff_store(production_handoff_db_path())
        if target is None:
            return None
        owned = True
    try:
        return target.find_by_approved_package(package.approved_package_id)
    finally:
        if owned and target is not None:
            target.close()
