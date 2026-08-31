"""
Increment 9.4 — disposable PostgreSQL ConstructorHandoff durability proof.

Tests only. Not a product adapter. Synthetic local credentials only.
Process A / Process B are genuine subprocesses of this file (--role process-a / process-b).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import traceback
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ROOT_STR = str(_REPO_ROOT)
if _ROOT_STR not in sys.path:
    sys.path.insert(0, _ROOT_STR)

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
    CandidatePackageReference,
    LaborNormSummary,
    PackageExceptionSummary,
)
from agents.monthly_plan_constructor.handoff_contracts import (
    DEFAULT_SECURITY_POLICY_VERSION,
    ConstructorHandoff,
    ConstructorHandoffProvenance,
    build_constructor_handoff,
)
from agents.monthly_plan_constructor.handoff_store import (
    CODE_HANDOFF_IMMUTABILITY_CONFLICT,
    CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
    STATUS_CREATED,
    STATUS_IDEMPOTENT_REPLAY,
    ConstructorHandoffStoreError,
    HandoffStorePutResult,
    compute_constructor_handoff_payload_digest,
    persist_constructor_handoff,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_OBSERVED_PRODUCTIVITY,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    LaborNormEvidence,
    SOURCE_PROJECT_HISTORY,
)
from agents.monthly_plan_constructor.langgraph_runtime import run_constructor_langgraph
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_READY_FOR_HANDOFF,
    CandidateAssemblyResult,
    ConstructorLifecycleState,
    run_constructor_lifecycle,
)
from agents.monthly_plan_constructor.mission_scope import ConstructorMissionScope
from agents.monthly_plan_constructor.secure_read_tools import ConstructorRealityRead
from security.agent_execution_context import (
    AgentExecutionContext,
    issue_read_only_agent_context,
)

# Synthetic disposable DSN authorized for this test file only.
_SYNTHETIC_DSN = "postgresql://eos_test:eos_test@127.0.0.1:55432/eos_test"
TABLE_NAME = "constructor_handoffs_test"

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"
MISSION_ID = "mission-increment-9-4"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
FIXED_AT = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)

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


def _redact(text: str) -> str:
    if not text:
        return text
    out = text.replace(_SYNTHETIC_DSN, "<redacted-dsn>")
    return out.replace("eos_test", "<redacted>")


def _connect() -> Any:
    import psycopg

    try:
        return psycopg.connect(_SYNTHETIC_DSN, autocommit=True)
    except Exception:
        raise RuntimeError("disposable postgres unreachable") from None


def _scalar(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    if isinstance(row, Mapping):
        return next(iter(row.values()))
    return row[0]


def _ensure_schema(conn: Any) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            handoff_id TEXT PRIMARY KEY,
            payload_json JSONB NOT NULL,
            payload_digest TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _row_count(conn: Any, handoff_id: Optional[str] = None) -> int:
    if handoff_id is None:
        value = _scalar(conn, f"SELECT COUNT(*) FROM {TABLE_NAME}")
    else:
        value = _scalar(
            conn,
            f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE handoff_id = %s",
            (handoff_id,),
        )
    return int(value or 0)


def _store_error(message: str) -> ConstructorHandoffStoreError:
    return ConstructorHandoffStoreError(CODE_HANDOFF_STORE_CONTRACT_BLOCKER, message)


def _require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _store_error(f"{field_name} must be an object")
    return value


def _require_exact_keys(payload: Mapping[str, Any], expected: frozenset[str], name: str) -> None:
    keys = frozenset(payload.keys())
    if keys != expected:
        raise _store_error(f"{name} has unknown or missing fields")


def _require_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise _store_error(f"{field_name} must be str")
    text = value.strip()
    if not text:
        raise _store_error(f"{field_name} is required")
    return text


def _optional_str(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _store_error(f"{field_name} must be str or null")
    text = value.strip()
    return text or None


def _require_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _store_error(f"{field_name} must be int")
    return value


def _require_str_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise _store_error(f"{field_name} must be a list of strings")
    items: list[str] = []
    for item in value:
        items.append(_require_str(item, field_name))
    return tuple(items)


def _optional_str_tuple(value: Any, field_name: str) -> Optional[tuple[str, ...]]:
    if value is None:
        return None
    return _require_str_tuple(value, field_name)


def _payload_from_handoff(handoff: ConstructorHandoff) -> dict[str, Any]:
    if not isinstance(handoff, ConstructorHandoff):
        raise _store_error("ConstructorHandoff is required")
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
            "facility_scope": None if scope.facility_scope is None else list(scope.facility_scope),
            "discipline_scope": None
            if scope.discipline_scope is None
            else list(scope.discipline_scope),
            "system_scope": None if scope.system_scope is None else list(scope.system_scope),
            "iwp_scope": None if scope.iwp_scope is None else list(scope.iwp_scope),
            "queue_scope": None if scope.queue_scope is None else list(scope.queue_scope),
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
        raise _store_error("candidate_count must equal len(candidate_ids)")
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


def _reconstruct_and_verify(raw: Any, expected_digest: str, *, handoff_id: str) -> ConstructorHandoff:
    artifact = _handoff_from_payload(raw)
    if artifact.handoff_id != handoff_id:
        raise _store_error("stored payload handoff_id does not match primary key")
    digest = compute_constructor_handoff_payload_digest(artifact)
    if digest != expected_digest:
        raise _store_error("stored payload_digest does not match reconstructed artifact")
    return artifact


class PostgresConstructorHandoffStore:
    """Test-only ConstructorHandoffStore against disposable Postgres. Not a product adapter."""

    def __init__(self, conn: Any) -> None:
        if conn is None:
            raise _store_error("psycopg connection is required")
        self.conn = conn

    def get(self, handoff_id: str) -> Optional[ConstructorHandoff]:
        key = _require_str(handoff_id, "handoff_id")
        row = self.conn.execute(
            f"""
            SELECT handoff_id, payload_json, payload_digest
            FROM {TABLE_NAME}
            WHERE handoff_id = %s
            """,
            (key,),
        ).fetchone()
        if row is None:
            return None
        return self._artifact_from_row(row, requested_id=key)

    def put_if_absent(self, handoff: ConstructorHandoff) -> HandoffStorePutResult:
        if not isinstance(handoff, ConstructorHandoff):
            raise _store_error("ConstructorHandoff is required")
        key = _require_str(handoff.handoff_id, "handoff_id")
        payload = _payload_from_handoff(handoff)
        digest = compute_constructor_handoff_payload_digest(handoff)
        inserted = self.conn.execute(
            f"""
            INSERT INTO {TABLE_NAME} (handoff_id, payload_json, payload_digest)
            VALUES (%s, %s::jsonb, %s)
            ON CONFLICT (handoff_id) DO NOTHING
            RETURNING handoff_id
            """,
            (
                key,
                json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                digest,
            ),
        ).fetchone()
        created = inserted is not None
        row = self.conn.execute(
            f"""
            SELECT handoff_id, payload_json, payload_digest
            FROM {TABLE_NAME}
            WHERE handoff_id = %s
            """,
            (key,),
        ).fetchone()
        if row is None:
            raise _store_error("put_if_absent did not leave a stored row")
        stored = self._artifact_from_row(row, requested_id=key)
        return HandoffStorePutResult(created=created, stored_handoff=stored)

    def _artifact_from_row(self, row: Any, *, requested_id: str) -> ConstructorHandoff:
        if isinstance(row, Mapping):
            stored_id = row["handoff_id"]
            payload = row["payload_json"]
            digest = row["payload_digest"]
        else:
            stored_id, payload, digest = row[0], row[1], row[2]
        if stored_id != requested_id:
            raise _store_error("store returned incompatible handoff_id")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise _store_error("payload_json is not valid JSON") from exc
        return _reconstruct_and_verify(
            payload,
            _require_str(digest, "payload_digest"),
            handoff_id=requested_id,
        )


class RecordingHandoffStore:
    """Captures put_if_absent outcomes without changing store semantics."""

    def __init__(self, inner: PostgresConstructorHandoffStore) -> None:
        self.inner = inner
        self.put_calls = 0
        self.last_put: Optional[HandoffStorePutResult] = None

    def get(self, handoff_id: str) -> Optional[ConstructorHandoff]:
        return self.inner.get(handoff_id)

    def put_if_absent(self, handoff: ConstructorHandoff) -> HandoffStorePutResult:
        self.put_calls += 1
        self.last_put = self.inner.put_if_absent(handoff)
        return self.last_put


class RecordingReader:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows if rows is not None else [_raw()]
        self.calls = 0

    def __call__(
        self,
        context: AgentExecutionContext,
        mission: ConstructorMissionScope,
    ) -> list[dict[str, object]]:
        self.calls += 1
        return list(self.rows)


class StubAssembler:
    def __init__(
        self,
        candidates: list[dict[str, object]] | None = None,
        *,
        scanned_count: int | None = None,
    ) -> None:
        self.candidates = candidates if candidates is not None else [_candidate_dict()]
        self.scanned_count = (
            scanned_count if scanned_count is not None else max(1, len(self.candidates))
        )

    def __call__(
        self,
        reality_read: ConstructorRealityRead,
        scope: ConstructorMissionScope,
    ) -> CandidateAssemblyResult:
        return CandidateAssemblyResult(
            candidates=tuple(self.candidates),
            scanned_count=self.scanned_count,
        )


def _raw() -> dict[str, object]:
    return {
        "project_code": PROJECT,
        "month_key": MONTH,
        "facility": FACILITY_TARGET,
        "facility_building": FACILITY_TARGET,
        "discipline": DISCIPLINE_VENT,
        "construction_discipline": DISCIPLINE_VENT,
        "system": "SYS-1",
        "system_label": "SYS-1",
        "iwp": "IWP-1",
        "iwp_id": "IWP-1",
        "boq_code": "BOQ-001",
        "boq_name": "Воздуховод",
        "unit_of_measure": "м2",
    }


def _candidate_dict() -> dict[str, object]:
    return {
        "candidate_id": CANDIDATE_ID,
        "project_code": PROJECT,
        "month_key": MONTH,
        "facility": FACILITY_TARGET,
        "discipline": DISCIPLINE_VENT,
        "system": "SYS-1",
        "iwp": "IWP-1",
        "queue": "Q1",
        "boq_code": "BOQ-001",
        "boq_name": "Воздуховод",
        "unit": "м2",
        "remaining_qty": 10.0,
        "already_planned_qty": 0.0,
        "available_to_add_qty": 10.0,
        "availability_status": "Доступно",
        "labor_norm_status": LABOR_UNRESOLVED,
    }


def _history() -> LaborNormEvidence:
    return LaborNormEvidence(
        evidence_id="ev-project",
        candidate_id=CANDIDATE_ID,
        source_type=SOURCE_PROJECT_HISTORY,
        labor_hours_per_unit=1.42,
        unit="м2",
        source_reference="project-history-run",
        source_version="2026-08",
        planning_use_status=LABOR_VALIDATED,
        basis=BASIS_OBSERVED_PRODUCTIVITY,
        hours_quality=HOURS_VALIDATED_PRODUCTIVE_DIRECT,
        executed_quantity_validated=True,
    )


def _context(run_id: str) -> AgentExecutionContext:
    return issue_read_only_agent_context(
        agent_code="MONTHLY_PLAN_CONSTRUCTOR",
        project_code=PROJECT,
        run_id=run_id,
    )


def _ready_state(*, run_id: str) -> ConstructorLifecycleState:
    return run_constructor_lifecycle(
        context=_context(run_id),
        project_code=PROJECT,
        month_key=MONTH,
        assemble_candidates=StubAssembler(),
        labor_evidence=(_history(),),
        scope_reader=RecordingReader(),
        mission_id=MISSION_ID,
        run_id=run_id,
        now=FIXED_AT,
    )


def _handoff_from_state(state: ConstructorLifecycleState) -> ConstructorHandoff:
    return build_constructor_handoff(
        state,
        security_policy_version=DEFAULT_SECURITY_POLICY_VERSION,
        created_at=state.updated_at,
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _identifiers(artifact: ConstructorHandoff) -> dict[str, Any]:
    return {
        "handoff_id": artifact.handoff_id,
        "payload_digest": compute_constructor_handoff_payload_digest(artifact),
        "source_run_id": artifact.source_run_id,
        "snapshot_id": artifact.snapshot_id,
    }


def role_process_a(handshake: Path, result: Path, run_id: str) -> int:
    conn = _connect()
    try:
        _ensure_schema(conn)
        store = RecordingHandoffStore(PostgresConstructorHandoffStore(conn))
        lifecycle = run_constructor_langgraph(
            context=_context(run_id),
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            labor_evidence=(_history(),),
            scope_reader=RecordingReader(),
            mission_id=MISSION_ID,
            run_id=run_id,
            now=FIXED_AT,
            handoff_store=store,
        )
        if lifecycle.status != STATUS_READY_FOR_HANDOFF:
            raise RuntimeError(f"expected READY_FOR_HANDOFF, got {lifecycle.status}")
        if store.put_calls != 1 or store.last_put is None or store.last_put.created is not True:
            raise RuntimeError("expected first persist to insert a row")
        artifact = store.last_put.stored_handoff
        if _row_count(conn, artifact.handoff_id) != 1:
            raise RuntimeError("row count after process A persist is not 1")
        loaded = store.get(artifact.handoff_id)
        if loaded is None:
            raise RuntimeError("inserted handoff is not readable")
        ids = _identifiers(loaded)
        handshake_payload = {
            **ids,
            "pid": os.getpid(),
        }
        _write_json(handshake, handshake_payload)
        _write_json(
            result,
            {
                "outcome": "created",
                "status": STATUS_CREATED,
                "lifecycle_status": lifecycle.status,
                "row_count": _row_count(conn, artifact.handoff_id),
                "pid": os.getpid(),
                **ids,
            },
        )
        return 0
    finally:
        conn.close()


def role_process_b(handshake: Path, result: Path) -> int:
    ids = _read_json(handshake)
    handoff_id = str(ids["handoff_id"])
    expected_digest = str(ids["payload_digest"])
    conn = _connect()
    try:
        _ensure_schema(conn)
        store = PostgresConstructorHandoffStore(conn)
        loaded = store.get(handoff_id)
        if loaded is None:
            raise RuntimeError("process B did not find stored handoff")
        digest = compute_constructor_handoff_payload_digest(loaded)
        if digest != expected_digest:
            raise RuntimeError("process B digest mismatch")
        if loaded.source_run_id != ids["source_run_id"]:
            raise RuntimeError("process B source_run_id mismatch")
        if loaded.snapshot_id != ids["snapshot_id"]:
            raise RuntimeError("process B snapshot_id mismatch")
        persist_status = persist_constructor_handoff(store=store, handoff=loaded)
        if persist_status.status != STATUS_IDEMPOTENT_REPLAY:
            raise RuntimeError(f"expected IDEMPOTENT_REPLAY, got {persist_status.status}")
        count = _row_count(conn, handoff_id)
        if count != 1:
            raise RuntimeError(f"row count after replay is {count}, expected 1")
        _write_json(
            result,
            {
                "outcome": "replay",
                "status": persist_status.status,
                "row_count": count,
                "pid": os.getpid(),
                "handoff_id": loaded.handoff_id,
                "payload_digest": digest,
                "source_run_id": loaded.source_run_id,
                "snapshot_id": loaded.snapshot_id,
            },
        )
        return 0
    finally:
        conn.close()


def _spawn(
    role: str,
    handshake: Path,
    result: Path,
    *,
    run_id: Optional[str] = None,
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--role",
        role,
        "--handshake",
        str(handshake),
        "--result",
        str(result),
    ]
    if run_id:
        cmd.extend(["--run-id", run_id])
    return subprocess.run(
        cmd,
        cwd=_ROOT_STR,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        shell=False,
    )


def _assert_proc(proc: subprocess.CompletedProcess[str], label: str) -> None:
    if proc.returncode != 0:
        raise AssertionError(
            f"{label} exited {proc.returncode}: {_redact(proc.stderr or proc.stdout or '')}"
        )


class TestSerializationFailClosed(unittest.TestCase):
    def test_roundtrip_digest_stable(self) -> None:
        artifact = _handoff_from_state(_ready_state(run_id="run-9-4-ser"))
        payload = _payload_from_handoff(artifact)
        reconstructed = _reconstruct_and_verify(
            payload,
            compute_constructor_handoff_payload_digest(artifact),
            handoff_id=artifact.handoff_id,
        )
        self.assertEqual(reconstructed, artifact)
        self.assertIsInstance(reconstructed.candidate_ids, tuple)
        self.assertEqual(
            compute_constructor_handoff_payload_digest(reconstructed),
            compute_constructor_handoff_payload_digest(artifact),
        )

    def test_missing_nested_field_fail_closed(self) -> None:
        artifact = _handoff_from_state(_ready_state(run_id="run-9-4-missing"))
        payload = _payload_from_handoff(artifact)
        del payload["provenance"]["security_policy_version"]
        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            _handoff_from_payload(payload)
        self.assertEqual(caught.exception.code, CODE_HANDOFF_STORE_CONTRACT_BLOCKER)

    def test_malformed_shape_fail_closed(self) -> None:
        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            _handoff_from_payload(["not", "an", "object"])
        self.assertEqual(caught.exception.code, CODE_HANDOFF_STORE_CONTRACT_BLOCKER)

    def test_unknown_field_fail_closed(self) -> None:
        artifact = _handoff_from_state(_ready_state(run_id="run-9-4-extra"))
        payload = _payload_from_handoff(artifact)
        payload["unexpected"] = "nope"
        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            _handoff_from_payload(payload)
        self.assertEqual(caught.exception.code, CODE_HANDOFF_STORE_CONTRACT_BLOCKER)

    def test_wrong_digest_fail_closed(self) -> None:
        artifact = _handoff_from_state(_ready_state(run_id="run-9-4-digest"))
        payload = _payload_from_handoff(artifact)
        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            _reconstruct_and_verify(
                payload,
                "0" * 64,
                handoff_id=artifact.handoff_id,
            )
        self.assertEqual(caught.exception.code, CODE_HANDOFF_STORE_CONTRACT_BLOCKER)

    def test_wrong_handoff_id_fail_closed(self) -> None:
        artifact = _handoff_from_state(_ready_state(run_id="run-9-4-id"))
        payload = _payload_from_handoff(artifact)
        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            _reconstruct_and_verify(
                payload,
                compute_constructor_handoff_payload_digest(artifact),
                handoff_id="eos-hof-other",
            )
        self.assertEqual(caught.exception.code, CODE_HANDOFF_STORE_CONTRACT_BLOCKER)

    def test_source_boundaries(self) -> None:
        source = Path(__file__).read_text(encoding="utf-8")
        helper = source.split("class TestSerializationFailClosed", 1)[0]
        lowered = helper.lower()
        self.assertIn("class PostgresConstructorHandoffStore", helper)
        self.assertIn("ON CONFLICT (handoff_id) DO NOTHING", helper)
        self.assertIn("RETURNING handoff_id", helper)
        self.assertIn("shell=False", helper)
        self.assertNotIn("_canonical_jsonable", helper)
        self.assertNotIn("import pickle", helper)
        self.assertNotIn("pickle.loads", helper)
        self.assertNotIn("eval(", helper)
        self.assertNotIn("shell=True", helper)
        self.assertNotIn("supabase", lowered)
        self.assertNotIn("dotenv", lowered)
        self.assertNotIn("os.environ", helper)
        self.assertNotIn("os.getenv", helper)
        self.assertNotIn("service_role", lowered)
        self.assertNotIn("DO UPDATE", helper)
        self.assertNotIn("\nUPDATE ", helper)
        self.assertNotIn("MERGE ", helper)


class PostgresProofTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = _connect()
        _ensure_schema(self.conn)
        self.conn.execute(f"TRUNCATE {TABLE_NAME}")

    def tearDown(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


class TestDurableRestart(PostgresProofTestCase):
    def test_fresh_interpreter_process_a_then_b(self) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="ctor-hof-"))
        handshake = tmp / "handshake.json"
        result_a = tmp / "a.json"
        result_b = tmp / "b.json"
        run_id = f"run-9-4-restart-{uuid.uuid4().hex[:12]}"
        proc_a = _spawn("process-a", handshake, result_a, run_id=run_id)
        _assert_proc(proc_a, "process-a")
        payload_a = _read_json(result_a)
        ids = _read_json(handshake)
        self.assertEqual(payload_a["status"], STATUS_CREATED)
        self.assertEqual(payload_a["lifecycle_status"], STATUS_READY_FOR_HANDOFF)
        self.assertEqual(payload_a["row_count"], 1)
        self.assertEqual(ids["handoff_id"], payload_a["handoff_id"])
        self.assertNotIn("password", json.dumps(ids))
        self.assertNotIn("service_role", json.dumps(ids))
        self.assertNotIn(_SYNTHETIC_DSN, json.dumps(ids))

        proc_b = _spawn("process-b", handshake, result_b)
        _assert_proc(proc_b, "process-b")
        payload_b = _read_json(result_b)
        self.assertEqual(payload_b["status"], STATUS_IDEMPOTENT_REPLAY)
        self.assertEqual(payload_b["row_count"], 1)
        self.assertEqual(payload_b["handoff_id"], ids["handoff_id"])
        self.assertEqual(payload_b["payload_digest"], ids["payload_digest"])
        self.assertNotEqual(payload_a["pid"], payload_b["pid"])
        self.assertNotEqual(payload_a["pid"], os.getpid())
        self.assertNotEqual(payload_b["pid"], os.getpid())
        self.assertEqual(_row_count(self.conn, ids["handoff_id"]), 1)


class TestPostgresStoreSemantics(PostgresProofTestCase):
    def test_immutability_conflict_keeps_one_row(self) -> None:
        run_id = f"run-9-4-immut-{uuid.uuid4().hex[:12]}"
        artifact = _handoff_from_state(_ready_state(run_id=run_id))
        store = PostgresConstructorHandoffStore(self.conn)
        first = persist_constructor_handoff(store=store, handoff=artifact)
        self.assertEqual(first.status, STATUS_CREATED)
        from dataclasses import replace

        mutated = replace(artifact, created_at="2099-01-01T00:00:00Z")
        self.assertEqual(mutated.handoff_id, artifact.handoff_id)
        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            persist_constructor_handoff(store=store, handoff=mutated)
        self.assertEqual(caught.exception.code, CODE_HANDOFF_IMMUTABILITY_CONFLICT)
        self.assertEqual(_row_count(self.conn, artifact.handoff_id), 1)
        stored = store.get(artifact.handoff_id)
        self.assertEqual(stored.created_at, artifact.created_at)

    def test_two_connections_one_created_one_replay(self) -> None:
        run_id = f"run-9-4-race-{uuid.uuid4().hex[:12]}"
        artifact = _handoff_from_state(_ready_state(run_id=run_id))
        other = _connect()
        try:
            store_a = PostgresConstructorHandoffStore(self.conn)
            store_b = PostgresConstructorHandoffStore(other)
            first = persist_constructor_handoff(store=store_a, handoff=artifact)
            second = persist_constructor_handoff(store=store_b, handoff=artifact)
            self.assertEqual(first.status, STATUS_CREATED)
            self.assertEqual(second.status, STATUS_IDEMPOTENT_REPLAY)
            self.assertEqual(_row_count(self.conn, artifact.handoff_id), 1)
        finally:
            other.close()

    def test_wrong_stored_digest_fail_closed(self) -> None:
        run_id = f"run-9-4-baddigest-{uuid.uuid4().hex[:12]}"
        artifact = _handoff_from_state(_ready_state(run_id=run_id))
        payload = _payload_from_handoff(artifact)
        self.conn.execute(
            f"""
            INSERT INTO {TABLE_NAME} (handoff_id, payload_json, payload_digest)
            VALUES (%s, %s::jsonb, %s)
            """,
            (
                artifact.handoff_id,
                json.dumps(payload, ensure_ascii=False),
                "0" * 64,
            ),
        )
        store = PostgresConstructorHandoffStore(self.conn)
        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            store.get(artifact.handoff_id)
        self.assertEqual(caught.exception.code, CODE_HANDOFF_STORE_CONTRACT_BLOCKER)
        self.assertEqual(_row_count(self.conn, artifact.handoff_id), 1)

    def test_malformed_stored_payload_fail_closed(self) -> None:
        handoff_id = "eos-hof-malformed-shape"
        self.conn.execute(
            f"""
            INSERT INTO {TABLE_NAME} (handoff_id, payload_json, payload_digest)
            VALUES (%s, %s::jsonb, %s)
            """,
            (handoff_id, json.dumps({"not": "a-handoff"}), "0" * 64),
        )
        store = PostgresConstructorHandoffStore(self.conn)
        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            store.get(handoff_id)
        self.assertEqual(caught.exception.code, CODE_HANDOFF_STORE_CONTRACT_BLOCKER)

    def test_langgraph_slice_persists_one_row(self) -> None:
        run_id = f"run-9-4-graph-{uuid.uuid4().hex[:12]}"
        store = RecordingHandoffStore(PostgresConstructorHandoffStore(self.conn))
        lifecycle = run_constructor_langgraph(
            context=_context(run_id),
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            labor_evidence=(_history(),),
            scope_reader=RecordingReader(),
            mission_id=MISSION_ID,
            run_id=run_id,
            now=FIXED_AT,
            handoff_store=store,
        )
        self.assertEqual(lifecycle.status, STATUS_READY_FOR_HANDOFF)
        self.assertEqual(store.put_calls, 1)
        self.assertTrue(store.last_put.created)  # type: ignore[union-attr]
        artifact = store.last_put.stored_handoff  # type: ignore[union-attr]
        self.assertEqual(artifact.source_run_id, lifecycle.run_id)
        self.assertEqual(artifact.snapshot_id, lifecycle.reality_read.snapshot_id)  # type: ignore[union-attr]
        self.assertEqual(_row_count(self.conn, artifact.handoff_id), 1)


def _main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Constructor handoff postgres proof harness")
    parser.add_argument("--role", required=True, choices=("process-a", "process-b"))
    parser.add_argument("--handshake", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)
    handshake = Path(args.handshake)
    result = Path(args.result)
    try:
        if args.role == "process-a":
            run_id = args.run_id.strip() or f"run-9-4-cli-{uuid.uuid4().hex[:12]}"
            return role_process_a(handshake, result, run_id)
        return role_process_b(handshake, result)
    except Exception as exc:
        sanitized = {
            "outcome": "harness_error",
            "error_class": type(exc).__name__,
            "error": _redact(str(exc)),
            "trace": _redact(traceback.format_exc()),
            "pid": os.getpid(),
        }
        try:
            _write_json(result, sanitized)
        except Exception:
            pass
        print(_redact(str(exc)), file=sys.stderr)
        return 1


if __name__ == "__main__":
    if any(arg == "--role" for arg in sys.argv[1:]):
        raise SystemExit(_main())
    unittest.main()
