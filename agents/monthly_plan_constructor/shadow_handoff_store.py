"""
Increment 11C.4 — Persistent SQLite handoff store for Shadow runtime.

Explicit infrastructure bootstrap only. Implements ConstructorHandoffStore:
get(handoff_id) and put_if_absent(handoff).

Creates only:
<repository_root>/.runtime/shadow/constructor/handoff.sqlite

Not LangGraph checkpoint memory. Not HITL memory. Not observability.
Not receiver acknowledgement. Not ownership transfer. Not a product database.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Mapping, Optional, Union

from agents.monthly_plan_constructor.candidate_package import (
    CandidatePackageReference,
    LaborNormSummary,
    PackageExceptionSummary,
)
from agents.monthly_plan_constructor.handoff_contracts import (
    STATUS_HANDOFF_READY,
    ConstructorHandoff,
    ConstructorHandoffProvenance,
)
from agents.monthly_plan_constructor.handoff_store import (
    CODE_HANDOFF_IMMUTABILITY_CONFLICT,
    CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
    ConstructorHandoffStoreError,
    HandoffStorePutResult,
    compute_constructor_handoff_payload_digest,
)
from agents.monthly_plan_constructor.mission_scope import ConstructorMissionScope
from agents.monthly_plan_constructor.shadow_runtime_stores import (
    resolve_constructor_shadow_runtime_paths,
)

CODE_SHADOW_HANDOFF_STORE_BLOCKER = "SHADOW_HANDOFF_STORE_BLOCKER"

_JSON_DUMP_KWARGS: dict[str, Any] = {
    "ensure_ascii": False,
    "sort_keys": True,
    "allow_nan": False,
    "separators": (",", ":"),
}

_SCOPE_KEYS = frozenset(
    {
        "project_code",
        "month_key",
        "month_key_canonical",
        "facility_scope",
        "discipline_scope",
        "system_scope",
        "iwp_scope",
        "queue_scope",
    }
)
_REFERENCE_KEYS = frozenset(
    {
        "package_id",
        "schema_version",
        "project_code",
        "month_key",
        "candidate_count",
        "created_at",
    }
)
_EXCEPTION_SUMMARY_KEYS = frozenset(
    {"blocking_count", "non_blocking_count", "warning_count"}
)
_LABOR_SUMMARY_KEYS = frozenset(
    {"validated", "provisional", "unresolved", "coverage_note"}
)
_PROVENANCE_KEYS = frozenset({"agent_version", "security_policy_version"})
_HANDOFF_KEYS = frozenset(
    {
        "schema_version",
        "handoff_id",
        "handoff_type",
        "source_agent",
        "source_run_id",
        "mission_id",
        "target_role",
        "orchestration_run_id",
        "project_code",
        "month_key",
        "scope",
        "candidate_package_reference",
        "snapshot_id",
        "candidate_ids",
        "candidate_count",
        "exceptions_summary",
        "labor_norm_summary",
        "created_at",
        "status",
        "provenance",
    }
)

_BOOTSTRAP_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS constructor_handoffs (
    handoff_id TEXT PRIMARY KEY,
    source_run_id TEXT NOT NULL,
    mission_id TEXT NOT NULL,
    handoff_type TEXT NOT NULL,
    target_role TEXT NOT NULL,
    package_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""


class ShadowHandoffStoreError(ValueError):
    """Fail-closed Shadow handoff store infrastructure / integrity violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ConstructorShadowHandoffStore:
    """
    Owned SQLite handoff resource implementing ConstructorHandoffStore.

    Durable rows are immutable ConstructorHandoff records.
    Presence of a row is transfer-record existence, not receiver acceptance.
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

    def __enter__(self) -> "ConstructorShadowHandoffStore":
        self._require_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def get(self, handoff_id: str) -> Optional[ConstructorHandoff]:
        self._require_open()
        key = str(handoff_id or "").strip()
        if not key:
            raise ShadowHandoffStoreError(
                CODE_SHADOW_HANDOFF_STORE_BLOCKER,
                "handoff_id is required",
            )
        with self._lock:
            row = self._connection.execute(
                """
                SELECT handoff_id, source_run_id, mission_id, handoff_type,
                       target_role, package_id, snapshot_id, schema_version,
                       status, created_at, payload_digest, payload_json
                FROM constructor_handoffs
                WHERE handoff_id = ?
                """,
                (key,),
            ).fetchone()
        if row is None:
            return None
        return _artifact_from_row(row)

    def put_if_absent(self, handoff: ConstructorHandoff) -> HandoffStorePutResult:
        self._require_open()
        artifact = _require_handoff(handoff)
        payload = _handoff_to_payload(artifact)
        payload_json = _json_dumps(payload)
        digest = compute_constructor_handoff_payload_digest(artifact)
        package_id = artifact.candidate_package_reference.package_id
        with self._lock:
            try:
                self._connection.execute("BEGIN")
                inserted = self._connection.execute(
                    """
                    INSERT INTO constructor_handoffs (
                        handoff_id, source_run_id, mission_id, handoff_type,
                        target_role, package_id, snapshot_id, schema_version,
                        status, created_at, payload_digest, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(handoff_id) DO NOTHING
                    """,
                    (
                        artifact.handoff_id,
                        artifact.source_run_id,
                        artifact.mission_id,
                        artifact.handoff_type,
                        artifact.target_role,
                        package_id,
                        artifact.snapshot_id,
                        artifact.schema_version,
                        artifact.status,
                        artifact.created_at,
                        digest,
                        payload_json,
                    ),
                )
                created = inserted.rowcount == 1
                row = self._connection.execute(
                    """
                    SELECT handoff_id, source_run_id, mission_id, handoff_type,
                           target_role, package_id, snapshot_id, schema_version,
                           status, created_at, payload_digest, payload_json
                    FROM constructor_handoffs
                    WHERE handoff_id = ?
                    """,
                    (artifact.handoff_id,),
                ).fetchone()
                if row is None:
                    raise ShadowHandoffStoreError(
                        CODE_SHADOW_HANDOFF_STORE_BLOCKER,
                        "put_if_absent did not leave a stored row",
                    )
                stored = _artifact_from_row(row)
                if not created:
                    stored_digest = compute_constructor_handoff_payload_digest(stored)
                    if stored_digest != digest:
                        raise ConstructorHandoffStoreError(
                            CODE_HANDOFF_IMMUTABILITY_CONFLICT,
                            "handoff_id already stored with a different payload",
                        )
                self._connection.execute("COMMIT")
                return HandoffStorePutResult(created=created, stored_handoff=stored)
            except sqlite3.IntegrityError as exc:
                self._connection.execute("ROLLBACK")
                raise ShadowHandoffStoreError(
                    CODE_SHADOW_HANDOFF_STORE_BLOCKER,
                    "handoff identity collision",
                ) from exc
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def _require_open(self) -> None:
        if self._closed:
            raise ShadowHandoffStoreError(
                CODE_SHADOW_HANDOFF_STORE_BLOCKER,
                "ConstructorShadowHandoffStore is closed",
            )


def bootstrap_constructor_shadow_handoff_store(
    *,
    repository_root: Union[str, Path],
) -> ConstructorShadowHandoffStore:
    """
    Explicit Shadow handoff infrastructure bootstrap.

    Resolves canonical paths, creates the runtime directory, opens only
    handoff.sqlite, and applies the handoff schema.
    """
    paths = resolve_constructor_shadow_runtime_paths(
        repository_root=repository_root,
    )
    try:
        paths.runtime_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ShadowHandoffStoreError(
            CODE_SHADOW_HANDOFF_STORE_BLOCKER,
            "canonical Shadow runtime directory could not be created",
        ) from exc

    try:
        connection = sqlite3.connect(
            str(paths.handoff_db_path),
            check_same_thread=False,
        )
    except sqlite3.Error as exc:
        raise ShadowHandoffStoreError(
            CODE_SHADOW_HANDOFF_STORE_BLOCKER,
            "handoff.sqlite could not be opened",
        ) from exc
    connection.row_factory = sqlite3.Row

    try:
        _apply_handoff_schema(connection)
        return ConstructorShadowHandoffStore(
            db_path=paths.handoff_db_path,
            connection=connection,
        )
    except BaseException:
        connection.close()
        raise


def _apply_handoff_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(_BOOTSTRAP_SQL)
    connection.commit()


def _require_handoff(handoff: Any) -> ConstructorHandoff:
    if handoff is None or not isinstance(handoff, ConstructorHandoff):
        raise ConstructorHandoffStoreError(
            CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
            "ConstructorHandoff is required",
        )
    handoff_id = str(handoff.handoff_id or "").strip()
    if not handoff_id:
        raise ConstructorHandoffStoreError(
            CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
            "handoff_id is required",
        )
    if handoff.status != STATUS_HANDOFF_READY:
        raise ConstructorHandoffStoreError(
            CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
            "handoff.status must be HANDOFF_READY",
        )
    return handoff


def _json_dumps(payload: Mapping[str, Any]) -> str:
    try:
        return json.dumps(payload, **_JSON_DUMP_KWARGS)
    except (TypeError, ValueError) as exc:
        raise ShadowHandoffStoreError(
            CODE_SHADOW_HANDOFF_STORE_BLOCKER,
            "handoff payload is not JSON-safe",
        ) from exc


def _json_loads(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ShadowHandoffStoreError(
            CODE_SHADOW_HANDOFF_STORE_BLOCKER,
            "handoff payload JSON is corrupt",
        ) from exc
    if not isinstance(payload, dict):
        raise ShadowHandoffStoreError(
            CODE_SHADOW_HANDOFF_STORE_BLOCKER,
            "handoff payload JSON must be an object",
        )
    return payload


def _store_integrity_error(message: str) -> ShadowHandoffStoreError:
    return ShadowHandoffStoreError(CODE_SHADOW_HANDOFF_STORE_BLOCKER, message)


def _require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _store_integrity_error(f"{field_name} must be an object")
    return value


def _require_exact_keys(
    payload: Mapping[str, Any],
    expected: frozenset[str],
    name: str,
) -> None:
    keys = frozenset(payload.keys())
    if keys != expected:
        raise _store_integrity_error(f"{name} has unknown or missing fields")


def _require_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise _store_integrity_error(f"{field_name} must be str")
    text = value.strip()
    if not text:
        raise _store_integrity_error(f"{field_name} is required")
    return text


def _optional_str(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _store_integrity_error(f"{field_name} must be str or null")
    text = value.strip()
    return text or None


def _require_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _store_integrity_error(f"{field_name} must be int")
    return value


def _require_str_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise _store_integrity_error(f"{field_name} must be a list of strings")
    items: list[str] = []
    for item in value:
        items.append(_require_str(item, field_name))
    return tuple(items)


def _optional_str_tuple(value: Any, field_name: str) -> Optional[tuple[str, ...]]:
    if value is None:
        return None
    return _require_str_tuple(value, field_name)


def _handoff_to_payload(handoff: ConstructorHandoff) -> dict[str, Any]:
    scope = handoff.scope
    reference = handoff.candidate_package_reference
    exceptions = handoff.exceptions_summary
    labor = handoff.labor_norm_summary
    provenance = handoff.provenance
    return {
        "schema_version": handoff.schema_version,
        "handoff_id": handoff.handoff_id,
        "handoff_type": handoff.handoff_type,
        "source_agent": handoff.source_agent,
        "source_run_id": handoff.source_run_id,
        "mission_id": handoff.mission_id,
        "target_role": handoff.target_role,
        "orchestration_run_id": handoff.orchestration_run_id,
        "project_code": handoff.project_code,
        "month_key": handoff.month_key,
        "scope": {
            "project_code": scope.project_code,
            "month_key": scope.month_key,
            "month_key_canonical": scope.month_key_canonical,
            "facility_scope": (
                None if scope.facility_scope is None else list(scope.facility_scope)
            ),
            "discipline_scope": (
                None
                if scope.discipline_scope is None
                else list(scope.discipline_scope)
            ),
            "system_scope": (
                None if scope.system_scope is None else list(scope.system_scope)
            ),
            "iwp_scope": None if scope.iwp_scope is None else list(scope.iwp_scope),
            "queue_scope": (
                None if scope.queue_scope is None else list(scope.queue_scope)
            ),
        },
        "candidate_package_reference": {
            "package_id": reference.package_id,
            "schema_version": reference.schema_version,
            "project_code": reference.project_code,
            "month_key": reference.month_key,
            "candidate_count": reference.candidate_count,
            "created_at": reference.created_at,
        },
        "snapshot_id": handoff.snapshot_id,
        "candidate_ids": list(handoff.candidate_ids),
        "candidate_count": handoff.candidate_count,
        "exceptions_summary": {
            "blocking_count": exceptions.blocking_count,
            "non_blocking_count": exceptions.non_blocking_count,
            "warning_count": exceptions.warning_count,
        },
        "labor_norm_summary": {
            "validated": labor.validated,
            "provisional": labor.provisional,
            "unresolved": labor.unresolved,
            "coverage_note": labor.coverage_note,
        },
        "created_at": handoff.created_at,
        "status": handoff.status,
        "provenance": {
            "agent_version": provenance.agent_version,
            "security_policy_version": provenance.security_policy_version,
        },
    }


def _scope_from_payload(raw: Any) -> ConstructorMissionScope:
    payload = _require_mapping(raw, "scope")
    _require_exact_keys(payload, _SCOPE_KEYS, "scope")
    return ConstructorMissionScope(
        project_code=_require_str(payload["project_code"], "scope.project_code"),
        month_key=_require_str(payload["month_key"], "scope.month_key"),
        month_key_canonical=_require_str(
            payload["month_key_canonical"], "scope.month_key_canonical"
        ),
        facility_scope=_optional_str_tuple(payload["facility_scope"], "scope.facility_scope"),
        discipline_scope=_optional_str_tuple(
            payload["discipline_scope"], "scope.discipline_scope"
        ),
        system_scope=_optional_str_tuple(payload["system_scope"], "scope.system_scope"),
        iwp_scope=_optional_str_tuple(payload["iwp_scope"], "scope.iwp_scope"),
        queue_scope=_optional_str_tuple(payload["queue_scope"], "scope.queue_scope"),
    )


def _reference_from_payload(raw: Any) -> CandidatePackageReference:
    payload = _require_mapping(raw, "candidate_package_reference")
    _require_exact_keys(payload, _REFERENCE_KEYS, "candidate_package_reference")
    return CandidatePackageReference(
        package_id=_require_str(payload["package_id"], "reference.package_id"),
        schema_version=_require_str(payload["schema_version"], "reference.schema_version"),
        project_code=_require_str(payload["project_code"], "reference.project_code"),
        month_key=_require_str(payload["month_key"], "reference.month_key"),
        candidate_count=_require_int(payload["candidate_count"], "reference.candidate_count"),
        created_at=_require_str(payload["created_at"], "reference.created_at"),
    )


def _exceptions_from_payload(raw: Any) -> PackageExceptionSummary:
    payload = _require_mapping(raw, "exceptions_summary")
    _require_exact_keys(payload, _EXCEPTION_SUMMARY_KEYS, "exceptions_summary")
    return PackageExceptionSummary(
        blocking_count=_require_int(payload["blocking_count"], "blocking_count"),
        non_blocking_count=_require_int(
            payload["non_blocking_count"], "non_blocking_count"
        ),
        warning_count=_require_int(payload["warning_count"], "warning_count"),
    )


def _labor_from_payload(raw: Any) -> LaborNormSummary:
    payload = _require_mapping(raw, "labor_norm_summary")
    _require_exact_keys(payload, _LABOR_SUMMARY_KEYS, "labor_norm_summary")
    return LaborNormSummary(
        validated=_require_int(payload["validated"], "validated"),
        provisional=_require_int(payload["provisional"], "provisional"),
        unresolved=_require_int(payload["unresolved"], "unresolved"),
        coverage_note=_require_str(payload["coverage_note"], "coverage_note"),
    )


def _provenance_from_payload(raw: Any) -> ConstructorHandoffProvenance:
    payload = _require_mapping(raw, "provenance")
    _require_exact_keys(payload, _PROVENANCE_KEYS, "provenance")
    return ConstructorHandoffProvenance(
        agent_version=_require_str(payload["agent_version"], "agent_version"),
        security_policy_version=_require_str(
            payload["security_policy_version"], "security_policy_version"
        ),
    )


def _handoff_from_payload(raw: Any) -> ConstructorHandoff:
    payload = _require_mapping(raw, "payload_json")
    _require_exact_keys(payload, _HANDOFF_KEYS, "ConstructorHandoff")
    candidate_ids = _require_str_tuple(payload["candidate_ids"], "candidate_ids")
    candidate_count = _require_int(payload["candidate_count"], "candidate_count")
    if candidate_count != len(candidate_ids):
        raise _store_integrity_error("candidate_count must equal len(candidate_ids)")
    return ConstructorHandoff(
        schema_version=_require_str(payload["schema_version"], "schema_version"),
        handoff_id=_require_str(payload["handoff_id"], "handoff_id"),
        handoff_type=_require_str(payload["handoff_type"], "handoff_type"),
        source_agent=_require_str(payload["source_agent"], "source_agent"),
        source_run_id=_require_str(payload["source_run_id"], "source_run_id"),
        mission_id=_require_str(payload["mission_id"], "mission_id"),
        target_role=_require_str(payload["target_role"], "target_role"),
        orchestration_run_id=_optional_str(
            payload["orchestration_run_id"], "orchestration_run_id"
        ),
        project_code=_require_str(payload["project_code"], "project_code"),
        month_key=_require_str(payload["month_key"], "month_key"),
        scope=_scope_from_payload(payload["scope"]),
        candidate_package_reference=_reference_from_payload(
            payload["candidate_package_reference"]
        ),
        snapshot_id=_require_str(payload["snapshot_id"], "snapshot_id"),
        candidate_ids=candidate_ids,
        candidate_count=candidate_count,
        exceptions_summary=_exceptions_from_payload(payload["exceptions_summary"]),
        labor_norm_summary=_labor_from_payload(payload["labor_norm_summary"]),
        created_at=_require_str(payload["created_at"], "created_at"),
        status=_require_str(payload["status"], "status"),
        provenance=_provenance_from_payload(payload["provenance"]),
    )


def _require_columns_match(handoff: ConstructorHandoff, row: sqlite3.Row) -> None:
    package_id = handoff.candidate_package_reference.package_id
    if (
        handoff.handoff_id != row["handoff_id"]
        or handoff.source_run_id != row["source_run_id"]
        or handoff.mission_id != row["mission_id"]
        or handoff.handoff_type != row["handoff_type"]
        or handoff.target_role != row["target_role"]
        or package_id != row["package_id"]
        or handoff.snapshot_id != row["snapshot_id"]
        or handoff.schema_version != row["schema_version"]
        or handoff.status != row["status"]
        or handoff.created_at != row["created_at"]
    ):
        raise ShadowHandoffStoreError(
            CODE_SHADOW_HANDOFF_STORE_BLOCKER,
            "handoff columns diverge from payload",
        )


def _artifact_from_row(row: sqlite3.Row) -> ConstructorHandoff:
    payload = _json_loads(row["payload_json"])
    artifact = _handoff_from_payload(payload)
    _require_columns_match(artifact, row)
    recomputed = compute_constructor_handoff_payload_digest(artifact)
    stored_digest = _require_str(row["payload_digest"], "payload_digest")
    if recomputed != stored_digest:
        raise ShadowHandoffStoreError(
            CODE_SHADOW_HANDOFF_STORE_BLOCKER,
            "handoff payload_digest does not match reconstructed artifact",
        )
    return artifact
