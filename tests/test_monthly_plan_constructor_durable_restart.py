"""
Increment 8 — durable HITL restart-survival proofs.

Tests only. Disposable localhost Postgres. No product DDL/migrations.
No Streamlit, Supabase, .env, or production credentials.

Process A / Process B are genuine subprocesses of this file
(`--role process-a` / `process-b` / `inspect`).
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

from agents.monthly_plan_constructor.candidate_package import LABOR_UNRESOLVED
from agents.monthly_plan_constructor.durable_checkpoint import (
    build_constructor_jsonplus_serializer,
    build_postgres_checkpointer,
    resolve_current_checkpoint_id,
)
from agents.monthly_plan_constructor.exception_engine import CODE_AMBIGUOUS_SCOPE
from agents.monthly_plan_constructor.hitl_contracts import (
    CODE_HITL_CONTRACT_BLOCKER,
    CODE_RUN_ABORTED_BY_HUMAN,
    DECISION_ABORT_RUN,
    DECISION_CLARIFY_SCOPE,
    ConstructorHumanDecisionRequest,
    ConstructorResumeCommand,
    HitlContractError,
    build_resume_command,
    compute_eos_interrupt_id,
    count_wait_ordinal,
)
from agents.monthly_plan_constructor.hitl_resume import (
    build_decision_request_from_lifecycle,
    stale_artifacts_cleared,
)
from agents.monthly_plan_constructor.langgraph_runtime import build_constructor_langgraph
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_FAILED,
    STATUS_READY_FOR_HANDOFF,
    STATUS_WAITING_FOR_HUMAN,
    CandidateAssemblyResult,
    ConstructorLifecycleState,
    LifecycleError,
    create_lifecycle_state,
)
from agents.monthly_plan_constructor.mission_scope import ConstructorMissionScope
from agents.monthly_plan_constructor.secure_read_tools import (
    ConstructorRealityRead,
    SecureReadError,
)
from langgraph.types import Command
from security.agent_execution_context import (
    AgentExecutionContext,
    issue_read_only_agent_context,
)

# Synthetic disposable DSN authorized for this test file only.
_SYNTHETIC_DSN = "postgresql://eos_test:eos_test@127.0.0.1:55432/eos_test"

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY_TARGET = "FACILITY_TARGET"
FACILITY_OTHER = "FACILITY_OTHER"
DISCIPLINE_VENT = "Вентиляция"
MISSION_ID = "mission-durable-restart"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
FIXED_AT = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)

REALITY_ENV = "TEST_REALITY_VERSION"
MARKER_V1 = "V1_REALITY_MARKER"
MARKER_V2 = "V2_REALITY_MARKER"
SENTINEL_SERVICE_ROLE = "SYNTHETIC_CKPT_SENTINEL_SERVICE_ROLE"
SENTINEL_BEARER = "SYNTHETIC_CKPT_SENTINEL_BEARER"
SENTINEL_DSN_SHAPE = "postgresql://"

HITL_OPEN_TABLE = "ctor_dur_hitl_open"
HITL_ANSWER_TABLE = "ctor_dur_hitl_answer"

_FORBIDDEN_TYPE_NAMES = frozenset(
    {
        "AgentExecutionContext",
        "DataFrame",
        "Connection",
        "PostgresSaver",
        "MemorySaver",
        "InMemorySaver",
        "PooledConnection",
        "ConnectionPool",
    }
)
_FORBIDDEN_CHANNEL_KEYS = frozenset(
    {
        "context",
        "scope_reader",
        "assemble_candidates",
        "labor_evidence",
        "hitl_store",
        "checkpointer",
        "conn",
        "client",
        "supabase",
        "password",
        "secret",
        "service_role",
    }
)


def _redact(text: str) -> str:
    if not text:
        return text
    out = text.replace(_SYNTHETIC_DSN, "<redacted-dsn>")
    return out.replace("eos_test", "<redacted>")


def _connect(*, for_saver: bool = False) -> Any:
    import psycopg
    from psycopg.rows import dict_row

    try:
        if for_saver:
            return psycopg.connect(
                _SYNTHETIC_DSN,
                autocommit=True,
                prepare_threshold=0,
                row_factory=dict_row,
            )
        return psycopg.connect(_SYNTHETIC_DSN, autocommit=True)
    except Exception:
        raise RuntimeError("disposable postgres unreachable") from None


class _ConnPair:
    def __init__(self) -> None:
        self.saver_conn = _connect(for_saver=True)
        self.hitl_conn = _connect(for_saver=False)

    def close(self) -> None:
        for conn in (self.hitl_conn, self.saver_conn):
            try:
                conn.close()
            except Exception:
                pass


def _scalar(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    if isinstance(row, Mapping):
        return next(iter(row.values()))
    return row[0]


def _ensure_hitl_schema(conn: Any) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {HITL_OPEN_TABLE} (
            interrupt_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            mission_id TEXT NOT NULL,
            status TEXT NOT NULL,
            wait_ordinal INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {HITL_ANSWER_TABLE} (
            decision_id TEXT PRIMARY KEY,
            interrupt_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            mission_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS ctor_dur_hitl_answer_interrupt_uidx
        ON {HITL_ANSWER_TABLE} (interrupt_id)
        """
    )


def _prepare_saver(conn: Any) -> Any:
    saver = build_postgres_checkpointer(
        conn,
        serde=build_constructor_jsonplus_serializer(pickle_fallback=False),
    )
    saver.setup()
    return saver


class PostgresHitlStore:
    """Test-only HITL adapter against disposable Postgres. Not a product store."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def upsert_open_request(self, request: ConstructorHumanDecisionRequest) -> None:
        self.conn.execute(
            f"""
            INSERT INTO {HITL_OPEN_TABLE}
                (interrupt_id, run_id, mission_id, status, wait_ordinal)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (interrupt_id) DO NOTHING
            """,
            (
                request.interrupt_id,
                request.run_id,
                request.mission_id,
                request.status,
                request.wait_ordinal,
            ),
        )

    def record_answer(
        self,
        *,
        interrupt_id: str,
        command: ConstructorResumeCommand,
    ) -> None:
        self.conn.execute(
            f"""
            INSERT INTO {HITL_ANSWER_TABLE}
                (decision_id, interrupt_id, run_id, mission_id, decision)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (decision_id) DO NOTHING
            """,
            (
                command.decision_id,
                interrupt_id,
                command.run_id,
                command.mission_id,
                command.decision,
            ),
        )


def _context(run_id: str, project_code: str = PROJECT) -> AgentExecutionContext:
    return issue_read_only_agent_context(
        agent_code="MONTHLY_PLAN_CONSTRUCTOR",
        project_code=project_code,
        run_id=run_id,
    )


def _raw(*, marker: str) -> dict[str, object]:
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
        "boq_name": marker,
        "unit_of_measure": "м2",
    }


class VersionedReader:
    """Deterministic fake scope_reader. Version comes from env, not checkpoint."""

    sentinel_service_role = SENTINEL_SERVICE_ROLE
    sentinel_bearer = SENTINEL_BEARER

    def __init__(self, *, raise_ambiguous: bool = False) -> None:
        self.calls = 0
        self.raise_ambiguous = raise_ambiguous
        self.last_mission: ConstructorMissionScope | None = None
        self.observed_markers: list[str] = []

    def __call__(
        self,
        context: AgentExecutionContext,
        mission: ConstructorMissionScope,
    ) -> list[dict[str, object]]:
        self.calls += 1
        self.last_mission = mission
        version = (os.environ.get(REALITY_ENV) or "v1").strip().lower()
        if version not in {"v1", "v2"}:
            raise SecureReadError("READ_FAILED", "unknown synthetic reality version")
        if self.raise_ambiguous:
            raise SecureReadError(CODE_AMBIGUOUS_SCOPE, "synthetic re-WAIT")
        marker = MARKER_V2 if version == "v2" else MARKER_V1
        self.observed_markers.append(marker)
        return [_raw(marker=marker)]


class VersionedAssembler:
    """Builds candidates from reality rows so v1 reuse cannot hide behind stubs."""

    sentinel_service_role = SENTINEL_SERVICE_ROLE
    sentinel_bearer = SENTINEL_BEARER

    def __init__(self) -> None:
        self.calls = 0
        self.markers: list[str] = []

    def __call__(
        self,
        reality_read: ConstructorRealityRead,
        scope: ConstructorMissionScope,
    ) -> CandidateAssemblyResult:
        self.calls += 1
        candidates: list[dict[str, object]] = []
        for row in reality_read.rows:
            marker = str(row.boq_name)
            self.markers.append(marker)
            qty = 77.0 if marker == MARKER_V2 else 10.0
            candidates.append(
                {
                    "candidate_id": CANDIDATE_ID,
                    "project_code": PROJECT,
                    "month_key": MONTH,
                    "facility": FACILITY_TARGET,
                    "discipline": DISCIPLINE_VENT,
                    "system": row.system or "SYS-1",
                    "iwp": row.iwp or "IWP-1",
                    "queue": "Q1",
                    "boq_code": row.boq_code or "BOQ-001",
                    "boq_name": marker,
                    "unit": row.unit or "м2",
                    "remaining_qty": qty,
                    "already_planned_qty": 0.0,
                    "available_to_add_qty": qty,
                    "availability_status": "Доступно",
                    "labor_norm_status": LABOR_UNRESOLVED,
                }
            )
        scanned = max(1, len(candidates))
        return CandidateAssemblyResult(
            candidates=tuple(candidates),
            scanned_count=scanned,
        )


def _thread_config(run_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": run_id}}


def _build_app(
    *,
    context: AgentExecutionContext,
    saver: Any,
    store: PostgresHitlStore,
    reader: VersionedReader,
    assembler: VersionedAssembler,
) -> Any:
    return build_constructor_langgraph(
        context=context,
        project_code=PROJECT,
        month_key=MONTH,
        facility_scope=["ALL", FACILITY_TARGET],
        assemble_candidates=assembler,
        scope_reader=reader,
        now=FIXED_AT,
        checkpointer=saver,
        hitl_store=store,
    )


def _interrupt_bits(payload: Any) -> tuple[Optional[str], Optional[str]]:
    if not payload:
        return None, None
    first = payload[0]
    native_id = getattr(first, "id", None)
    value = getattr(first, "value", first)
    eos_id = getattr(value, "interrupt_id", None)
    return (
        str(native_id).strip() if native_id else None,
        str(eos_id).strip() if eos_id else None,
    )


def _lifecycle_from_state(
    app: Any,
    config: dict[str, Any],
    *,
    saver: Any | None = None,
    run_id: str | None = None,
) -> ConstructorLifecycleState:
    try:
        snap = app.get_state(config)
        values = getattr(snap, "values", None) or {}
        lifecycle = values.get("lifecycle")
        if isinstance(lifecycle, ConstructorLifecycleState):
            return lifecycle
    except Exception:
        lifecycle = None
    if saver is not None and run_id is not None:
        tup = saver.get_tuple(_thread_config(run_id))
        if tup is not None:
            ckpt = getattr(tup, "checkpoint", None)
            values = ckpt.get("channel_values") if isinstance(ckpt, Mapping) else None
            if isinstance(values, Mapping):
                restored = values.get("lifecycle")
                if isinstance(restored, ConstructorLifecycleState):
                    return restored
    raise RuntimeError("restored graph state missing ConstructorLifecycleState")


def _checkpoint_id_from_app(app: Any, config: dict[str, Any]) -> str:
    snap = app.get_state(config)
    cfg = getattr(snap, "config", None) or {}
    found = (cfg.get("configurable") or {}).get("checkpoint_id")
    if not found:
        raise RuntimeError("checkpoint_id missing from restored graph state")
    return str(found).strip()


def _walk_security(obj: Any, path: str = "root") -> list[str]:
    findings: list[str] = []
    if obj is None:
        return findings
    if callable(obj) and not isinstance(obj, type):
        findings.append(f"callable:{path}")
    if isinstance(obj, AgentExecutionContext):
        findings.append(f"context:{path}")
    name = obj.__class__.__name__
    if name in _FORBIDDEN_TYPE_NAMES:
        findings.append(f"unsafe:{path}:{name}")
    if isinstance(obj, (bytes, bytearray, memoryview)):
        text = bytes(obj).decode("latin-1", errors="ignore")
        findings.extend(_sentinel_hits(text, path))
        return findings
    if isinstance(obj, str):
        findings.extend(_sentinel_hits(obj, path))
        return findings
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            key_text = str(key)
            if key_text in _FORBIDDEN_CHANNEL_KEYS:
                findings.append(f"forbidden-key:{path}.{key_text}")
            findings.extend(_walk_security(value, f"{path}.{key_text}"))
        return findings
    if isinstance(obj, (list, tuple, set, frozenset)):
        for idx, value in enumerate(obj):
            findings.extend(_walk_security(value, f"{path}[{idx}]"))
        return findings
    if hasattr(obj, "__dict__") and not isinstance(obj, type):
        for key, value in getattr(obj, "__dict__", {}).items():
            findings.extend(_walk_security(value, f"{path}.{key}"))
    return findings


def _sentinel_hits(text: str, path: str) -> list[str]:
    hits: list[str] = []
    lowered = text.lower()
    if SENTINEL_SERVICE_ROLE in text:
        hits.append(f"sentinel-service-role:{path}")
    if SENTINEL_BEARER in text:
        hits.append(f"sentinel-bearer:{path}")
    if SENTINEL_DSN_SHAPE in lowered or "service_role" in lowered:
        hits.append(f"secret-shape:{path}")
    if "bearer " in lowered:
        hits.append(f"secret-shape:{path}")
    return hits


def _scan_checkpoint(saver: Any, run_id: str) -> dict[str, Any]:
    tup = saver.get_tuple(_thread_config(run_id))
    if tup is None:
        return {"found": False, "findings": ["missing-checkpoint"]}
    findings: list[str] = []
    ckpt = getattr(tup, "checkpoint", None)
    channel_values: Any = None
    if isinstance(ckpt, Mapping):
        channel_values = ckpt.get("channel_values")
        findings.extend(_walk_security(channel_values, "channel_values"))
        for key in (channel_values or {}):
            if str(key) in _FORBIDDEN_CHANNEL_KEYS:
                findings.append(f"forbidden-key:channel_values.{key}")
    metadata = getattr(tup, "metadata", None)
    findings.extend(_walk_security(metadata, "metadata"))
    lifecycle = None
    if isinstance(channel_values, Mapping):
        lifecycle = channel_values.get("lifecycle")
    if isinstance(lifecycle, ConstructorLifecycleState):
        findings.extend(_walk_security(lifecycle, "lifecycle"))
        serde = build_constructor_jsonplus_serializer(pickle_fallback=False)
        _tag, payload = serde.dumps_typed(lifecycle)
        findings.extend(_sentinel_hits(payload.decode("latin-1", errors="ignore"), "lifecycle-bytes"))
    pickle_fallback = bool(getattr(getattr(saver, "serde", None), "pickle_fallback", True))
    if pickle_fallback:
        findings.append("pickle-fallback-enabled")
    return {
        "found": True,
        "findings": findings,
        "pickle_fallback": pickle_fallback,
        "has_lifecycle": isinstance(lifecycle, ConstructorLifecycleState),
        "status": getattr(lifecycle, "status", None),
        "reality_marker": _reality_marker(lifecycle) if lifecycle is not None else None,
        "package_marker": _package_marker(lifecycle) if lifecycle is not None else None,
    }


def _reality_marker(lifecycle: ConstructorLifecycleState | None) -> Optional[str]:
    if lifecycle is None or lifecycle.reality_read is None:
        return None
    rows = lifecycle.reality_read.rows
    if not rows:
        return None
    return str(rows[0].boq_name)


def _package_marker(lifecycle: ConstructorLifecycleState | None) -> Optional[str]:
    if lifecycle is None or lifecycle.package is None or not lifecycle.package.candidates:
        return None
    return str(lifecycle.package.candidates[0].boq_name)


def _package_qty(lifecycle: ConstructorLifecycleState | None) -> Optional[float]:
    if lifecycle is None or lifecycle.package is None or not lifecycle.package.candidates:
        return None
    return float(lifecycle.package.candidates[0].remaining_qty)


def _hitl_counts(conn: Any, run_id: str) -> dict[str, Any]:
    open_count = int(
        _scalar(
            conn,
            f"SELECT COUNT(*) AS n FROM {HITL_OPEN_TABLE} WHERE run_id = %s",
            (run_id,),
        )
        or 0
    )
    answer_count = int(
        _scalar(
            conn,
            f"SELECT COUNT(*) AS n FROM {HITL_ANSWER_TABLE} WHERE run_id = %s",
            (run_id,),
        )
        or 0
    )
    open_ids = [
        row["interrupt_id"] if isinstance(row, Mapping) else row[0]
        for row in conn.execute(
            f"SELECT interrupt_id FROM {HITL_OPEN_TABLE} WHERE run_id = %s ORDER BY created_at",
            (run_id,),
        ).fetchall()
    ]
    answer_ids = [
        (row["decision_id"], row["interrupt_id"])
        if isinstance(row, Mapping)
        else (row[0], row[1])
        for row in conn.execute(
            f"SELECT decision_id, interrupt_id FROM {HITL_ANSWER_TABLE} WHERE run_id = %s",
            (run_id,),
        ).fetchall()
    ]
    return {
        "open_count": open_count,
        "answer_count": answer_count,
        "open_ids": open_ids,
        "answer_ids": answer_ids,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, default=str), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resume_command(handshake: Mapping[str, Any], mode: str) -> ConstructorResumeCommand:
    run_id = str(handshake["run_id"])
    mission_id = str(handshake["mission_id"])
    interrupt_id = str(handshake["eos_interrupt_id"])
    checkpoint_id = str(handshake["checkpoint_id"])
    decision_id = str(handshake["decision_id_seed"])
    decision = DECISION_CLARIFY_SCOPE
    parameters: dict[str, Any] = {"facility_scope": [FACILITY_TARGET]}
    expected: Optional[str] = checkpoint_id
    if mode == "missing-ckpt":
        expected = None
    elif mode == "stale-ckpt":
        expected = "00000000-0000-0000-0000-000000000001"
    elif mode == "wrong-run-id":
        run_id = "run-other-wrong-id"
    elif mode == "wrong-mission-id":
        mission_id = "mission-other-wrong"
    elif mode == "wrong-interrupt-id":
        interrupt_id = "eos-int-deadbeefdeadbeefdeadbeefdeadbe"
    elif mode == "mutate-project":
        parameters = {
            "facility_scope": [FACILITY_TARGET],
            "project_code": "PRJ_OTHER",
        }
    elif mode == "mutate-month":
        parameters = {
            "facility_scope": [FACILITY_TARGET],
            "month_key": "октябрь-2026",
        }
    elif mode == "expand-scope":
        parameters = {"facility_scope": None}
    elif mode == "abort":
        decision = DECISION_ABORT_RUN
        parameters = {}
    elif mode == "expand-other-facility":
        parameters = {"facility_scope": [FACILITY_TARGET, FACILITY_OTHER]}
    return build_resume_command(
        decision_id=decision_id,
        interrupt_id=interrupt_id,
        run_id=run_id,
        mission_id=mission_id,
        decision=decision,
        actor_id="human-durable-1",
        parameters=parameters,
        expected_checkpoint_id=expected,
        submitted_at=FIXED_AT,
        comment="stop" if decision == DECISION_ABORT_RUN else None,
    )


def _lifecycle_snapshot(lifecycle: ConstructorLifecycleState) -> dict[str, Any]:
    return {
        "status": lifecycle.status,
        "error_code": lifecycle.error_code,
        "run_id": lifecycle.run_id,
        "mission_id": lifecycle.mission_id,
        "authorization_id": lifecycle.authorization_id,
        "wait_ordinal": count_wait_ordinal(lifecycle.transitions),
        "stale_cleared": stale_artifacts_cleared(lifecycle),
        "reality_marker": _reality_marker(lifecycle),
        "package_marker": _package_marker(lifecycle),
        "package_qty": _package_qty(lifecycle),
        "has_reality": lifecycle.reality_read is not None,
        "has_package": lifecycle.package is not None,
        "has_labor": lifecycle.labor_resolutions is not None,
        "transition_to": [t.to_status for t in lifecycle.transitions],
    }


def role_process_a(handshake_path: Path, result_path: Path, run_id: str) -> int:
    os.environ[REALITY_ENV] = "v1"
    pair = _ConnPair()
    try:
        saver = _prepare_saver(pair.saver_conn)
        _ensure_hitl_schema(pair.hitl_conn)
        store = PostgresHitlStore(pair.hitl_conn)
        ctx = _context(run_id)
        reader = VersionedReader()
        assembler = VersionedAssembler()
        app = _build_app(
            context=ctx,
            saver=saver,
            store=store,
            reader=reader,
            assembler=assembler,
        )
        serde = getattr(app.checkpointer, "serde", None) or saver.serde
        if getattr(serde, "pickle_fallback", True):
            raise RuntimeError("pickle_fallback must stay False")
        initial = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id=run_id,
            authorization_id=ctx.authorization_id,
            created_at=FIXED_AT,
        )
        config = _thread_config(run_id)
        out = app.invoke({"lifecycle": initial}, config)
        lifecycle = out["lifecycle"]
        if lifecycle.status != STATUS_WAITING_FOR_HUMAN:
            raise RuntimeError(f"process A expected WAIT, got {lifecycle.status}")
        native_id, eos_from_interrupt = _interrupt_bits(out.get("__interrupt__"))
        req = build_decision_request_from_lifecycle(lifecycle)
        eos_id = eos_from_interrupt or req.interrupt_id
        checkpoint_id = _checkpoint_id_from_app(app, config)
        resolved = resolve_current_checkpoint_id(saver, thread_id=run_id)
        if resolved != checkpoint_id:
            raise RuntimeError("checkpoint_id mismatch between get_state and saver")
        counts = _hitl_counts(pair.hitl_conn, run_id)
        scan = _scan_checkpoint(saver, run_id)
        handshake = {
            "run_id": run_id,
            "mission_id": lifecycle.mission_id,
            "checkpoint_id": checkpoint_id,
            "eos_interrupt_id": eos_id,
            "native_interrupt_id": native_id,
            "decision_id_seed": f"dec-{run_id}",
            "project_code": PROJECT,
            "month_key": MONTH,
            "reality_version": "v1",
            "authorization_id": ctx.authorization_id,
            "status": lifecycle.status,
            "error_code": lifecycle.error_code,
            "wait_ordinal": count_wait_ordinal(lifecycle.transitions),
            "reader_calls": reader.calls,
            "assembler_calls": assembler.calls,
            "open_count": counts["open_count"],
            "answer_count": counts["answer_count"],
            "pickle_fallback": bool(getattr(serde, "pickle_fallback", True)),
            "scan_findings": scan["findings"],
        }
        _write_json(handshake_path, handshake)
        _write_json(
            result_path,
            {
                "outcome": "wait",
                **_lifecycle_snapshot(lifecycle),
                **counts,
                "checkpoint_id": checkpoint_id,
                "eos_interrupt_id": eos_id,
                "native_interrupt_id": native_id,
                "scan_findings": scan["findings"],
                "pickle_fallback": handshake["pickle_fallback"],
                "authorization_id": ctx.authorization_id,
                "reader_calls": reader.calls,
            },
        )
        return 0
    finally:
        pair.close()


def role_inspect(handshake_path: Path, result_path: Path) -> int:
    handshake = _read_json(handshake_path)
    run_id = str(handshake["run_id"])
    pair = _ConnPair()
    try:
        saver = _prepare_saver(pair.saver_conn)
        _ensure_hitl_schema(pair.hitl_conn)
        scan = _scan_checkpoint(saver, run_id)
        counts = _hitl_counts(pair.hitl_conn, run_id)
        resolved = None
        resolve_error = None
        try:
            resolved = resolve_current_checkpoint_id(saver, thread_id=run_id)
        except HitlContractError as exc:
            resolve_error = exc.code
        _write_json(
            result_path,
            {
                "outcome": "inspect",
                "found": scan["found"],
                "status": scan.get("status"),
                "checkpoint_id": resolved,
                "resolve_error": resolve_error,
                "reality_marker": scan.get("reality_marker"),
                "package_marker": scan.get("package_marker"),
                "scan_findings": scan["findings"],
                "pickle_fallback": scan.get("pickle_fallback"),
                **counts,
            },
        )
        return 0
    finally:
        pair.close()


def _invoke_resume(app: Any, cmd: ConstructorResumeCommand, config: dict[str, Any]) -> dict[str, Any]:
    try:
        out = app.invoke(Command(resume=cmd), config)
        lifecycle = out["lifecycle"]
        native_id, eos_id = _interrupt_bits(out.get("__interrupt__"))
        return {
            "outcome": "resumed",
            "lifecycle": lifecycle,
            "native_interrupt_id": native_id,
            "eos_interrupt_id": eos_id,
            "error_code": None,
            "error_class": None,
        }
    except HitlContractError as exc:
        return {
            "outcome": "fail_closed",
            "lifecycle": None,
            "error_code": exc.code,
            "error_class": "HitlContractError",
        }
    except LifecycleError as exc:
        return {
            "outcome": "fail_closed",
            "lifecycle": None,
            "error_code": exc.code,
            "error_class": "LifecycleError",
        }
    except Exception as exc:
        return {
            "outcome": "invoke_error",
            "lifecycle": None,
            "error_code": getattr(exc, "code", None),
            "error_class": type(exc).__name__,
        }


def role_process_b(
    handshake_path: Path,
    result_path: Path,
    *,
    mode: str,
) -> int:
    handshake = _read_json(handshake_path)
    run_id = str(handshake["run_id"])
    raise_ambiguous = mode in {"rewait", "expand-after-rewait"}
    pair = _ConnPair()
    try:
        saver = _prepare_saver(pair.saver_conn)
        _ensure_hitl_schema(pair.hitl_conn)
        store = PostgresHitlStore(pair.hitl_conn)
        ctx = _context(run_id)
        reader = VersionedReader(raise_ambiguous=raise_ambiguous)
        assembler = VersionedAssembler()
        app = _build_app(
            context=ctx,
            saver=saver,
            store=store,
            reader=reader,
            assembler=assembler,
        )
        config = _thread_config(run_id)
        restored = _lifecycle_from_state(app, config, saver=saver, run_id=run_id)
        if restored.status != STATUS_WAITING_FOR_HUMAN:
            raise RuntimeError(f"process B restore expected WAIT, got {restored.status}")
        if restored.run_id != run_id:
            raise RuntimeError("restored run_id mismatch")
        cmd = _resume_command(handshake, mode)
        first = _invoke_resume(app, cmd, config)
        lifecycle = first.get("lifecycle")
        if lifecycle is None:
            lifecycle = _lifecycle_from_state(app, config, saver=saver, run_id=run_id)
        # Duplicate resume in the same Process B after a successful first resume.
        duplicate_outcome = None
        if mode == "duplicate" and first["outcome"] == "resumed":
            second = _invoke_resume(app, cmd, config)
            duplicate_outcome = {
                "outcome": second["outcome"],
                "error_code": second.get("error_code"),
                "error_class": second.get("error_class"),
            }
            if second.get("lifecycle") is not None:
                lifecycle = second["lifecycle"]
            else:
                lifecycle = _lifecycle_from_state(app, config, saver=saver, run_id=run_id)
        # After re-WAIT, optionally attempt scope expansion against the new interrupt.
        expand_outcome = None
        if mode == "expand-after-rewait" and first["outcome"] == "resumed":
            if lifecycle.status != STATUS_WAITING_FOR_HUMAN:
                raise RuntimeError(
                    f"re-WAIT expected WAIT, got {lifecycle.status}"
                )
            req2 = build_decision_request_from_lifecycle(lifecycle)
            ckpt2 = _checkpoint_id_from_app(app, config)
            expand_cmd = build_resume_command(
                decision_id=f"dec-expand-{run_id}",
                interrupt_id=req2.interrupt_id,
                run_id=run_id,
                mission_id=str(handshake["mission_id"]),
                decision=DECISION_CLARIFY_SCOPE,
                actor_id="human-durable-1",
                parameters={"facility_scope": None},
                expected_checkpoint_id=ckpt2,
                submitted_at=FIXED_AT,
            )
            expanded = _invoke_resume(app, expand_cmd, config)
            expand_outcome = {
                "outcome": expanded["outcome"],
                "error_code": expanded.get("error_code"),
                "error_class": expanded.get("error_class"),
                "interrupt_id": req2.interrupt_id,
                "checkpoint_id": ckpt2,
            }
            if expanded.get("lifecycle") is not None:
                lifecycle = expanded["lifecycle"]
            else:
                lifecycle = _lifecycle_from_state(app, config, saver=saver, run_id=run_id)
        counts = _hitl_counts(pair.hitl_conn, run_id)
        scan = _scan_checkpoint(saver, run_id)
        current_ckpt = None
        try:
            current_ckpt = _checkpoint_id_from_app(app, config)
        except Exception:
            try:
                current_ckpt = resolve_current_checkpoint_id(saver, thread_id=run_id)
            except HitlContractError:
                current_ckpt = handshake.get("checkpoint_id")
        req_now = None
        if lifecycle.status == STATUS_WAITING_FOR_HUMAN:
            req_now = build_decision_request_from_lifecycle(lifecycle)
        snap = _lifecycle_snapshot(lifecycle)
        payload = {
            **snap,
            **counts,
            "outcome": first["outcome"],
            "error_code": first.get("error_code") or snap.get("error_code"),
            "lifecycle_error_code": snap.get("error_code"),
            "error_class": first.get("error_class"),
            "authorization_id_a": handshake.get("authorization_id"),
            "authorization_id_b": ctx.authorization_id,
            "reader_calls": reader.calls,
            "assembler_calls": assembler.calls,
            "reader_markers": reader.observed_markers,
            "assembler_markers": assembler.markers,
            "checkpoint_id": current_ckpt,
            "handshake_checkpoint_id": handshake.get("checkpoint_id"),
            "handshake_interrupt_id": handshake.get("eos_interrupt_id"),
            "current_interrupt_id": None if req_now is None else req_now.interrupt_id,
            "duplicate": duplicate_outcome,
            "expand": expand_outcome,
            "scan_findings": scan["findings"],
            "pickle_fallback": scan.get("pickle_fallback"),
            "reality_env": os.environ.get(REALITY_ENV),
        }
        _write_json(result_path, payload)
        return 0
    finally:
        pair.close()


def _spawn(
    role: str,
    handshake: Path,
    result: Path,
    *,
    run_id: Optional[str] = None,
    mode: Optional[str] = None,
    reality: Optional[str] = None,
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
    if mode:
        cmd.extend(["--resume-mode", mode])
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _ROOT_STR + (os.pathsep + existing if existing else "")
    if reality:
        env[REALITY_ENV] = reality
    return subprocess.run(
        cmd,
        cwd=_ROOT_STR,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _assert_proc(proc: subprocess.CompletedProcess[str], label: str) -> None:
    if proc.returncode != 0:
        raise AssertionError(
            f"{label} exited {proc.returncode}: {_redact(proc.stderr or proc.stdout or '')}"
        )


def _new_run_id(label: str) -> str:
    return f"run-dur-{label}-{uuid.uuid4().hex[:12]}"


def _run_a(label: str) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    tmp = tempfile.mkdtemp(prefix="ctor-dur-")
    handshake = Path(tmp) / "handshake.json"
    result_a = Path(tmp) / "a.json"
    run_id = _new_run_id(label)
    proc = _spawn(
        "process-a",
        handshake,
        result_a,
        run_id=run_id,
        reality="v1",
    )
    _assert_proc(proc, "process-a")
    return _read_json(handshake), _read_json(result_a), handshake, Path(tmp)


def _run_inspect(handshake: Path, tmp: Path) -> dict[str, Any]:
    result = tmp / "inspect.json"
    proc = _spawn("inspect", handshake, result)
    _assert_proc(proc, "inspect")
    return _read_json(result)


def _run_b(
    handshake: Path,
    tmp: Path,
    *,
    mode: str,
    reality: str = "v2",
    stem: str = "b",
) -> dict[str, Any]:
    result = tmp / f"{stem}.json"
    proc = _spawn(
        "process-b",
        handshake,
        result,
        mode=mode,
        reality=reality,
    )
    _assert_proc(proc, f"process-b:{mode}")
    return _read_json(result)


def _assert_fail_closed(b: Mapping[str, Any], handshake: Mapping[str, Any]) -> None:
    assert b["outcome"] == "fail_closed"
    assert b["error_code"] == CODE_HITL_CONTRACT_BLOCKER
    assert b["status"] == STATUS_WAITING_FOR_HUMAN
    assert b["run_id"] == handshake["run_id"]
    assert b["answer_count"] == 0
    assert b["has_reality"] is False
    assert b["has_package"] is False
    assert b["package_marker"] is None
    assert b["reality_marker"] is None
    assert MARKER_V2 not in (b.get("reader_markers") or [])
    assert b["reader_calls"] == 0
    assert STATUS_READY_FOR_HANDOFF not in (b.get("transition_to") or [])
    assert b["error_class"] == "HitlContractError"
    assert b.get("lifecycle_error_code") == CODE_AMBIGUOUS_SCOPE


class TestDurableRestart(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pair = _ConnPair()
        try:
            _prepare_saver(pair.saver_conn)
            _ensure_hitl_schema(pair.hitl_conn)
        finally:
            pair.close()

    def test_process_a_wait_checkpoint_survives_exit(self) -> None:
        handshake, result_a, path, tmp = _run_a("persist")
        inspect = _run_inspect(path, tmp)
        self.assertEqual(result_a["status"], STATUS_WAITING_FOR_HUMAN)
        self.assertEqual(result_a["error_code"], CODE_AMBIGUOUS_SCOPE)
        self.assertTrue(inspect["found"])
        self.assertEqual(inspect["status"], STATUS_WAITING_FOR_HUMAN)
        self.assertEqual(inspect["checkpoint_id"], handshake["checkpoint_id"])
        self.assertEqual(inspect["open_count"], 1)
        self.assertEqual(inspect["answer_count"], 0)
        self.assertEqual(inspect["scan_findings"], [])
        self.assertFalse(inspect["pickle_fallback"])
        self.assertIsNone(inspect["reality_marker"])
        self.assertEqual(handshake["wait_ordinal"], 1)
        self.assertTrue(str(handshake["eos_interrupt_id"]).startswith("eos-int-"))
        self.assertEqual(
            handshake["eos_interrupt_id"],
            compute_eos_interrupt_id(
                run_id=handshake["run_id"],
                wait_ordinal=1,
                reason_code=CODE_AMBIGUOUS_SCOPE,
            ),
        )

    def test_process_b_resume_fresh_context_v2_ready(self) -> None:
        handshake, result_a, path, tmp = _run_a("happy")
        inspect_a = _run_inspect(path, tmp)
        self.assertEqual(inspect_a["status"], STATUS_WAITING_FOR_HUMAN)
        b = _run_b(path, tmp, mode="clarify-happy", reality="v2")
        self.assertEqual(b["outcome"], "resumed")
        self.assertEqual(b["status"], STATUS_READY_FOR_HANDOFF)
        self.assertEqual(b["run_id"], handshake["run_id"])
        self.assertEqual(b["mission_id"], handshake["mission_id"])
        self.assertNotEqual(b["authorization_id_b"], handshake["authorization_id"])
        self.assertGreaterEqual(b["reader_calls"], 1)
        self.assertGreaterEqual(b["assembler_calls"], 1)
        self.assertEqual(b["reality_env"], "v2")
        self.assertEqual(b["reality_marker"], MARKER_V2)
        self.assertEqual(b["package_marker"], MARKER_V2)
        self.assertEqual(b["package_qty"], 77.0)
        self.assertNotEqual(b["reality_marker"], MARKER_V1)
        self.assertNotIn(MARKER_V1, b["reader_markers"])
        self.assertNotIn(MARKER_V1, b["assembler_markers"])
        self.assertEqual(b["open_count"], 1)
        self.assertEqual(b["answer_count"], 1)
        self.assertEqual(b["open_ids"], [handshake["eos_interrupt_id"]])
        self.assertFalse(b["pickle_fallback"])
        self.assertEqual(b["scan_findings"], [])
        self.assertGreaterEqual(result_a["open_count"], 1)

    def test_missing_expected_checkpoint_id_fail_closed(self) -> None:
        handshake, _, path, tmp = _run_a("missckpt")
        b = _run_b(path, tmp, mode="missing-ckpt", reality="v2")
        _assert_fail_closed(b, handshake)
        inspect = _run_inspect(path, tmp)
        self.assertEqual(inspect["status"], STATUS_WAITING_FOR_HUMAN)
        self.assertEqual(inspect["answer_count"], 0)

    def test_stale_expected_checkpoint_id_fail_closed(self) -> None:
        handshake, _, path, tmp = _run_a("staleckpt")
        b = _run_b(path, tmp, mode="stale-ckpt", reality="v2")
        _assert_fail_closed(b, handshake)
        inspect = _run_inspect(path, tmp)
        self.assertEqual(inspect["status"], STATUS_WAITING_FOR_HUMAN)
        self.assertEqual(inspect["checkpoint_id"], handshake["checkpoint_id"])
        self.assertEqual(inspect["answer_count"], 0)

    def test_wrong_run_id_fail_closed(self) -> None:
        handshake, _, path, tmp = _run_a("wrongrun")
        b = _run_b(path, tmp, mode="wrong-run-id", reality="v2")
        _assert_fail_closed(b, handshake)

    def test_wrong_mission_id_fail_closed(self) -> None:
        handshake, _, path, tmp = _run_a("wrongmission")
        b = _run_b(path, tmp, mode="wrong-mission-id", reality="v2")
        _assert_fail_closed(b, handshake)

    def test_wrong_eos_interrupt_id_fail_closed(self) -> None:
        handshake, _, path, tmp = _run_a("wrongint")
        b = _run_b(path, tmp, mode="wrong-interrupt-id", reality="v2")
        _assert_fail_closed(b, handshake)

    def test_project_code_mutation_fail_closed(self) -> None:
        handshake, _, path, tmp = _run_a("mutproject")
        b = _run_b(path, tmp, mode="mutate-project", reality="v2")
        _assert_fail_closed(b, handshake)

    def test_month_key_mutation_fail_closed(self) -> None:
        handshake, _, path, tmp = _run_a("mutmonth")
        b = _run_b(path, tmp, mode="mutate-month", reality="v2")
        _assert_fail_closed(b, handshake)

    def test_scope_expansion_fail_closed_after_rewait(self) -> None:
        handshake, _, path, tmp = _run_a("expand")
        b = _run_b(path, tmp, mode="expand-after-rewait", reality="v2")
        self.assertEqual(b["outcome"], "resumed")
        self.assertIsNotNone(b.get("expand"))
        self.assertEqual(b["expand"]["outcome"], "fail_closed")
        self.assertEqual(b["expand"]["error_code"], CODE_HITL_CONTRACT_BLOCKER)
        self.assertEqual(b["status"], STATUS_WAITING_FOR_HUMAN)
        self.assertNotEqual(b["current_interrupt_id"], handshake["eos_interrupt_id"])
        self.assertEqual(b["answer_count"], 1)
        self.assertEqual(b["open_count"], 2)
        self.assertIsNone(b["package_marker"])
        self.assertIsNone(b["reality_marker"])
        inspect = _run_inspect(path, tmp)
        self.assertEqual(inspect["status"], STATUS_WAITING_FOR_HUMAN)
        self.assertEqual(inspect["answer_count"], 1)

    def test_open_answer_idempotent_duplicate_resume_safe(self) -> None:
        handshake, result_a, path, tmp = _run_a("idem")
        self.assertEqual(result_a["open_count"], 1)
        b = _run_b(path, tmp, mode="duplicate", reality="v2")
        self.assertEqual(b["status"], STATUS_READY_FOR_HANDOFF)
        self.assertEqual(b["open_count"], 1)
        self.assertEqual(b["answer_count"], 1)
        self.assertEqual(b["open_ids"], [handshake["eos_interrupt_id"]])
        self.assertEqual(len(b["answer_ids"]), 1)
        self.assertEqual(b["package_marker"], MARKER_V2)
        inspect = _run_inspect(path, tmp)
        self.assertEqual(inspect["open_count"], 1)
        self.assertEqual(inspect["answer_count"], 1)

    def test_rewait_new_interrupt_identity(self) -> None:
        handshake, _, path, tmp = _run_a("rewait")
        b = _run_b(path, tmp, mode="rewait", reality="v2")
        self.assertEqual(b["outcome"], "resumed")
        self.assertEqual(b["status"], STATUS_WAITING_FOR_HUMAN)
        self.assertEqual(b["error_code"], CODE_AMBIGUOUS_SCOPE)
        self.assertNotEqual(b["current_interrupt_id"], handshake["eos_interrupt_id"])
        self.assertEqual(
            b["current_interrupt_id"],
            compute_eos_interrupt_id(
                run_id=handshake["run_id"],
                wait_ordinal=2,
                reason_code=CODE_AMBIGUOUS_SCOPE,
            ),
        )
        self.assertEqual(b["wait_ordinal"], 2)
        self.assertEqual(b["open_count"], 2)
        self.assertEqual(b["answer_count"], 1)
        self.assertIn(handshake["eos_interrupt_id"], b["open_ids"])
        self.assertIn(b["current_interrupt_id"], b["open_ids"])

    def test_abort_run_failed(self) -> None:
        handshake, _, path, tmp = _run_a("abort")
        b = _run_b(path, tmp, mode="abort", reality="v2")
        self.assertEqual(b["outcome"], "resumed")
        self.assertEqual(b["status"], STATUS_FAILED)
        self.assertEqual(b["error_code"], CODE_RUN_ABORTED_BY_HUMAN)
        self.assertTrue(b["stale_cleared"])
        self.assertEqual(b["answer_count"], 1)
        self.assertEqual(b["reader_calls"], 0)
        self.assertIsNone(b["reality_marker"])
        self.assertIsNone(b["package_marker"])
        self.assertEqual(b["run_id"], handshake["run_id"])
        inspect = _run_inspect(path, tmp)
        self.assertEqual(inspect["status"], STATUS_FAILED)
        self.assertEqual(inspect["answer_count"], 1)

    def test_checkpoint_structurally_secret_free(self) -> None:
        handshake, result_a, path, tmp = _run_a("secure")
        inspect_a = _run_inspect(path, tmp)
        self.assertEqual(inspect_a["scan_findings"], [])
        self.assertFalse(inspect_a["pickle_fallback"])
        self.assertFalse(result_a["pickle_fallback"])
        self.assertEqual(result_a["scan_findings"], [])
        b = _run_b(path, tmp, mode="clarify-happy", reality="v2")
        self.assertEqual(b["scan_findings"], [])
        self.assertFalse(b["pickle_fallback"])
        self.assertEqual(b["status"], STATUS_READY_FOR_HANDOFF)
        inspect_b = _run_inspect(path, tmp)
        self.assertEqual(inspect_b["scan_findings"], [])
        self.assertEqual(inspect_b["package_marker"], MARKER_V2)
        self.assertNotIn("context", json.dumps(handshake))


def _main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Constructor durable restart harness")
    parser.add_argument("--role", required=True, choices=("process-a", "process-b", "inspect"))
    parser.add_argument("--handshake", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--resume-mode", default="clarify-happy")
    args = parser.parse_args(argv)
    handshake = Path(args.handshake)
    result = Path(args.result)
    try:
        if args.role == "process-a":
            run_id = args.run_id.strip() or _new_run_id("cli")
            return role_process_a(handshake, result, run_id)
        if args.role == "inspect":
            return role_inspect(handshake, result)
        return role_process_b(handshake, result, mode=args.resume_mode)
    except Exception as exc:
        sanitized = {
            "outcome": "harness_error",
            "error_class": type(exc).__name__,
            "error": _redact(str(exc)),
            "trace": _redact(traceback.format_exc()),
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
