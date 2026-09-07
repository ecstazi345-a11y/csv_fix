"""
Increment 11C.4 — Persistent handoff store tests.

tmp_path only. Does not create C:\\csv_fix\\.runtime.
Does not start Shadow composition, Admission, or a Digital Work Board.

Store durability only. Live runtime handoff wiring is unchanged;
this file does not prove live HANDOFF_PERSISTED / RUN_COMPLETED events.
"""

from __future__ import annotations

import ast
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from agents.monthly_plan_constructor.candidate_package import LABOR_UNRESOLVED, LABOR_VALIDATED
from agents.monthly_plan_constructor.handoff_contracts import (
    DEFAULT_SECURITY_POLICY_VERSION,
    TARGET_ROLE,
    ConstructorHandoff,
    build_constructor_handoff,
)
from agents.monthly_plan_constructor.handoff_store import (
    CODE_HANDOFF_IMMUTABILITY_CONFLICT,
    STATUS_CREATED,
    STATUS_IDEMPOTENT_REPLAY,
    ConstructorHandoffStoreError,
    compute_constructor_handoff_payload_digest,
    persist_constructor_handoff,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_OBSERVED_PRODUCTIVITY,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    LaborNormEvidence,
    SOURCE_PROJECT_HISTORY,
)
from agents.monthly_plan_constructor.lifecycle import (
    CandidateAssemblyResult,
    run_constructor_lifecycle,
)
from agents.monthly_plan_constructor.mission_scope import ConstructorMissionScope
from agents.monthly_plan_constructor.secure_read_tools import ConstructorRealityRead
from agents.monthly_plan_constructor.shadow_handoff_store import (
    CODE_SHADOW_HANDOFF_STORE_BLOCKER,
    ConstructorShadowHandoffStore,
    ShadowHandoffStoreError,
    bootstrap_constructor_shadow_handoff_store,
)
from agents.monthly_plan_constructor.shadow_runtime_stores import (
    resolve_constructor_shadow_runtime_paths,
)
from security.agent_execution_context import (
    AgentExecutionContext,
    issue_read_only_agent_context,
)

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "agents" / "monthly_plan_constructor" / "shadow_handoff_store.py"
REAL_RUNTIME = REPO / ".runtime"
PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"
MISSION_ID = "mission-11c4-handoff"
RUN_ID = "run-11c4-handoff"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
FIXED_AT = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
LATER_AT = datetime(2026, 8, 31, 13, 0, 0, tzinfo=timezone.utc)

FORBIDDEN_IMPORTS = (
    "supabase",
    "streamlit",
    "requests",
    "dotenv",
    "openai",
    "langgraph.checkpoint.sqlite",
)
FORBIDDEN_TOKENS = (
    "load_constructor_month_plan_lines",
    "execute_constructor_plan_lines_read",
    "monthly_plan_lines_v2",
    "create_client",
    "AGENT_OBSERVABILITY_DB_PATH",
    "SqliteSaver",
    "from_conn_string",
    "pickle",
    "SqliteObservabilityStore",
    "build_constructor_shadow_composition",
    "ConstructorShadowComposition",
    "issue_read_only_agent_context",
    "AgentExecutionContext",
    "receiver_ack",
    "target_run_id",
    "ownership_transferred",
    "datetime.now",
    "JsonPlusSerializer",
)


def _require_real_runtime_absent() -> None:
    if REAL_RUNTIME.exists():
        pytest.fail(
            "real C:\\csv_fix\\.runtime already exists; 11C.4 must stop "
            "rather than delete or reuse it"
        )


def _bootstrap(tmp_path: Path) -> ConstructorShadowHandoffStore:
    return bootstrap_constructor_shadow_handoff_store(repository_root=tmp_path)


def _context(run_id: str = RUN_ID) -> AgentExecutionContext:
    return issue_read_only_agent_context(
        agent_code="MONTHLY_PLAN_CONSTRUCTOR",
        project_code=PROJECT,
        run_id=run_id,
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


class RecordingReader:
    def __call__(
        self,
        context: AgentExecutionContext,
        mission: ConstructorMissionScope,
    ) -> list[dict[str, object]]:
        return [_raw()]


class StubAssembler:
    def __call__(
        self,
        reality_read: ConstructorRealityRead,
        scope: ConstructorMissionScope,
    ) -> CandidateAssemblyResult:
        return CandidateAssemblyResult(
            candidates=(
                {
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
                },
            ),
            scanned_count=1,
        )


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


def _ready_state(*, run_id: str = RUN_ID):
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


def _handoff_from_state(state, *, created_at: datetime = FIXED_AT) -> ConstructorHandoff:
    return build_constructor_handoff(
        state,
        security_policy_version=DEFAULT_SECURITY_POLICY_VERSION,
        created_at=created_at,
    )


def _handoff(*, run_id: str = RUN_ID, created_at: datetime = FIXED_AT) -> ConstructorHandoff:
    return _handoff_from_state(_ready_state(run_id=run_id), created_at=created_at)


def test_real_runtime_root_absent_before_tests() -> None:
    _require_real_runtime_absent()


def test_import_creates_no_runtime_root() -> None:
    _require_real_runtime_absent()
    import agents.monthly_plan_constructor.shadow_handoff_store as module

    assert module.bootstrap_constructor_shadow_handoff_store is not None
    assert not REAL_RUNTIME.exists()


def test_implements_constructor_handoff_store_api(tmp_path: Path) -> None:
    store = _bootstrap(tmp_path)
    try:
        assert callable(store.get)
        assert callable(store.put_if_absent)
        assert not hasattr(store, "persist") or store.persist is not getattr(
            type(store), "persist", None
        )
        assert "persist" not in type(store).__dict__
    finally:
        store.close()


def test_bootstrap_creates_only_handoff_sqlite(tmp_path: Path) -> None:
    _require_real_runtime_absent()
    paths = resolve_constructor_shadow_runtime_paths(repository_root=tmp_path)
    assert not paths.runtime_root.exists()
    store = _bootstrap(tmp_path)
    try:
        assert paths.runtime_root.is_dir()
        assert store.db_path == paths.handoff_db_path
        assert store.db_path.is_file()
        assert store.db_path.name == "handoff.sqlite"
        assert not paths.checkpoints_db_path.exists()
        assert not paths.hitl_db_path.exists()
        assert not paths.observability_db_path.exists()
    finally:
        store.close()
    assert not REAL_RUNTIME.exists()


def test_request_and_replay_survive_independent_reopen(tmp_path: Path) -> None:
    artifact = _handoff()
    original_digest = compute_constructor_handoff_payload_digest(artifact)
    store_a = _bootstrap(tmp_path)
    connection_a = store_a.connection
    try:
        result = persist_constructor_handoff(store=store_a, handoff=artifact)
        assert result.status == STATUS_CREATED
        assert result.handoff_id == artifact.handoff_id
        assert result.payload_digest == original_digest
        restored = store_a.get(artifact.handoff_id)
        assert restored == artifact
        assert restored is not None
        assert restored.target_role == TARGET_ROLE
        assert restored.candidate_package_reference.package_id == (
            artifact.candidate_package_reference.package_id
        )
        assert restored.snapshot_id == artifact.snapshot_id
    finally:
        store_a.close()

    store_b = _bootstrap(tmp_path)
    try:
        assert store_b is not store_a
        assert store_b.connection is not connection_a
        restored = store_b.get(artifact.handoff_id)
        assert restored == artifact
        assert restored is not None
        assert restored.target_role == TARGET_ROLE
        assert restored.candidate_package_reference.package_id == (
            artifact.candidate_package_reference.package_id
        )
        assert restored.snapshot_id == artifact.snapshot_id
        assert compute_constructor_handoff_payload_digest(restored) == original_digest
        replay = persist_constructor_handoff(store=store_b, handoff=artifact)
        assert replay.status == STATUS_IDEMPOTENT_REPLAY
        count = store_b.connection.execute(
            "SELECT COUNT(*) AS n FROM constructor_handoffs"
        ).fetchone()["n"]
        assert count == 1
    finally:
        store_b.close()

    store_c = _bootstrap(tmp_path)
    try:
        restored = store_c.get(artifact.handoff_id)
        assert restored == artifact
        assert restored is not None
        assert compute_constructor_handoff_payload_digest(restored) == original_digest
        paths = resolve_constructor_shadow_runtime_paths(repository_root=tmp_path)
        sqlite_files = list(paths.runtime_root.glob("*.sqlite"))
        assert sqlite_files == [paths.handoff_db_path]
    finally:
        store_c.close()
    assert not REAL_RUNTIME.exists()


def test_created_at_drift_fails_closed_and_original_survives_reopen(
    tmp_path: Path,
) -> None:
    state = _ready_state()
    original = _handoff_from_state(state, created_at=FIXED_AT)
    drifted = _handoff_from_state(state, created_at=LATER_AT)
    assert original.handoff_id == drifted.handoff_id
    assert original.created_at != drifted.created_at
    store = _bootstrap(tmp_path)
    try:
        persist_constructor_handoff(store=store, handoff=original)
        with pytest.raises(ConstructorHandoffStoreError) as raised:
            persist_constructor_handoff(store=store, handoff=drifted)
        assert raised.value.code == CODE_HANDOFF_IMMUTABILITY_CONFLICT
        assert store.get(original.handoff_id) == original
    finally:
        store.close()
    reopened = _bootstrap(tmp_path)
    try:
        assert reopened.get(original.handoff_id) == original
        assert reopened.get(original.handoff_id).created_at == original.created_at
    finally:
        reopened.close()


def test_conflicting_target_role_and_artifact_fail_closed(tmp_path: Path) -> None:
    original = _handoff()
    store = _bootstrap(tmp_path)
    try:
        persist_constructor_handoff(store=store, handoff=original)
        role_conflict = replace(original, target_role="SOME_OTHER_ROLE")
        with pytest.raises(ConstructorHandoffStoreError) as raised:
            persist_constructor_handoff(store=store, handoff=role_conflict)
        assert raised.value.code == CODE_HANDOFF_IMMUTABILITY_CONFLICT
        payload_conflict = replace(
            original,
            candidate_ids=("other-candidate-id",),
            candidate_count=1,
        )
        with pytest.raises(ConstructorHandoffStoreError) as raised:
            persist_constructor_handoff(store=store, handoff=payload_conflict)
        assert raised.value.code == CODE_HANDOFF_IMMUTABILITY_CONFLICT
        assert store.get(original.handoff_id) == original
    finally:
        store.close()
    reopened = _bootstrap(tmp_path)
    try:
        assert reopened.get(original.handoff_id) == original
    finally:
        reopened.close()


def test_distinct_source_runs_coexist(tmp_path: Path) -> None:
    first = _handoff(run_id="run-11c4-a")
    second = _handoff(run_id="run-11c4-b")
    assert first.handoff_id != second.handoff_id
    store = _bootstrap(tmp_path)
    try:
        assert persist_constructor_handoff(store=store, handoff=first).status == STATUS_CREATED
        assert persist_constructor_handoff(store=store, handoff=second).status == STATUS_CREATED
        assert store.get(first.handoff_id) == first
        assert store.get(second.handoff_id) == second
        count = store.connection.execute(
            "SELECT COUNT(*) AS n FROM constructor_handoffs"
        ).fetchone()["n"]
        assert count == 2
    finally:
        store.close()


def test_unknown_handoff_get_returns_none(tmp_path: Path) -> None:
    store = _bootstrap(tmp_path)
    try:
        assert store.get("eos-hof-missing") is None
    finally:
        store.close()


def test_column_payload_mismatch_fails_closed(tmp_path: Path) -> None:
    artifact = _handoff()
    store = _bootstrap(tmp_path)
    try:
        persist_constructor_handoff(store=store, handoff=artifact)
        store.connection.execute(
            """
            UPDATE constructor_handoffs
            SET target_role = ?
            WHERE handoff_id = ?
            """,
            ("TAMPERED_ROLE", artifact.handoff_id),
        )
        store.connection.commit()
        with pytest.raises(ShadowHandoffStoreError) as raised:
            store.get(artifact.handoff_id)
        assert raised.value.code == CODE_SHADOW_HANDOFF_STORE_BLOCKER
    finally:
        store.close()


def test_corrupt_digest_fails_closed(tmp_path: Path) -> None:
    artifact = _handoff()
    store = _bootstrap(tmp_path)
    try:
        persist_constructor_handoff(store=store, handoff=artifact)
        store.connection.execute(
            """
            UPDATE constructor_handoffs
            SET payload_digest = ?
            WHERE handoff_id = ?
            """,
            ("0" * 64, artifact.handoff_id),
        )
        store.connection.commit()
        with pytest.raises(ShadowHandoffStoreError) as raised:
            store.get(artifact.handoff_id)
        assert raised.value.code == CODE_SHADOW_HANDOFF_STORE_BLOCKER
    finally:
        store.close()


def test_malformed_json_fails_closed(tmp_path: Path) -> None:
    artifact = _handoff()
    store = _bootstrap(tmp_path)
    try:
        persist_constructor_handoff(store=store, handoff=artifact)
        store.connection.execute(
            """
            UPDATE constructor_handoffs
            SET payload_json = ?
            WHERE handoff_id = ?
            """,
            ("{not-json", artifact.handoff_id),
        )
        store.connection.commit()
        with pytest.raises(ShadowHandoffStoreError) as raised:
            store.get(artifact.handoff_id)
        assert raised.value.code == CODE_SHADOW_HANDOFF_STORE_BLOCKER
    finally:
        store.close()


def test_close_is_idempotent_and_access_fails_closed(tmp_path: Path) -> None:
    artifact = _handoff()
    store = _bootstrap(tmp_path)
    connection = store.connection
    store.close()
    store.close()
    assert store.closed
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    with pytest.raises(ShadowHandoffStoreError) as raised:
        store.get(artifact.handoff_id)
    assert raised.value.code == CODE_SHADOW_HANDOFF_STORE_BLOCKER
    with pytest.raises(ShadowHandoffStoreError) as raised:
        store.put_if_absent(artifact)
    assert raised.value.code == CODE_SHADOW_HANDOFF_STORE_BLOCKER


def test_bootstrap_closes_connection_if_schema_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def tracking_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn = real_connect(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(
        "agents.monthly_plan_constructor.shadow_handoff_store.sqlite3.connect",
        tracking_connect,
    )

    def boom(connection: Any) -> None:
        raise RuntimeError("schema failed")

    monkeypatch.setattr(
        "agents.monthly_plan_constructor.shadow_handoff_store._apply_handoff_schema",
        boom,
    )
    with pytest.raises(RuntimeError, match="schema failed"):
        bootstrap_constructor_shadow_handoff_store(repository_root=tmp_path)
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")


def test_context_manager_closes_store(tmp_path: Path) -> None:
    with _bootstrap(tmp_path) as store:
        assert not store.closed
        connection = store.connection
    assert store.closed
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_no_product_or_forbidden_factories() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for token in FORBIDDEN_IMPORTS:
        assert token not in imported
        if token != "requests":
            assert token not in source
    for token in FORBIDDEN_TOKENS:
        assert token not in source
    assert "pickle" not in source
    assert "JsonPlusSerializer" not in source
    assert "datetime.now" not in source
    assert "check_same_thread=False" in source
    assert "PRAGMA foreign_keys = ON" in source
    assert "supabase" not in source.lower()
    assert "def persist(" not in source


def test_does_not_write_real_canonical_runtime_root(tmp_path: Path) -> None:
    _require_real_runtime_absent()
    store = _bootstrap(tmp_path)
    store.close()
    assert not REAL_RUNTIME.exists()
    assert (tmp_path / ".runtime").exists()
    assert not (REPO / ".runtime").exists()
