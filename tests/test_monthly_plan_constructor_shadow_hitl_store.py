"""
Increment 11C.3 — Persistent HITL store tests.

tmp_path only. Does not create C:\\csv_fix\\.runtime.
Does not start Shadow composition, resume a run, or touch product data.

Store durability only. Live runtime still records answers after resume apply;
this file does not prove pre-resume answer durability.
"""

from __future__ import annotations

import ast
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from agents.monthly_plan_constructor.hitl_contracts import (
    DECISION_ABORT_RUN,
    DECISION_CLARIFY_SCOPE,
    ScopeSummary,
    build_human_decision_request,
    build_resume_command,
    compute_eos_interrupt_id,
)
from agents.monthly_plan_constructor.shadow_hitl_store import (
    CODE_SHADOW_HITL_STORE_BLOCKER,
    ConstructorShadowHitlStore,
    ShadowHitlStoreError,
    bootstrap_constructor_shadow_hitl_store,
)
from agents.monthly_plan_constructor.shadow_runtime_stores import (
    resolve_constructor_shadow_runtime_paths,
)

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "agents" / "monthly_plan_constructor" / "shadow_hitl_store.py"
REAL_RUNTIME = REPO / ".runtime"
RUN_ID = "run-11c3-hitl"
MISSION_ID = "mission-11c3-hitl"
FIXED_AT = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)
PROJECT = "PRJ_001_БХК"

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
)


def _require_real_runtime_absent() -> None:
    if REAL_RUNTIME.exists():
        pytest.fail(
            "real C:\\csv_fix\\.runtime already exists; 11C.3 must stop "
            "rather than delete or reuse it"
        )


def _bootstrap(tmp_path: Path) -> ConstructorShadowHitlStore:
    return bootstrap_constructor_shadow_hitl_store(repository_root=tmp_path)


def _scope() -> ScopeSummary:
    return ScopeSummary(
        project_code=PROJECT,
        month_key="сентябрь-2026",
        facility_scope=None,
        discipline_scope=None,
        system_scope=None,
        iwp_scope=None,
        queue_scope=None,
    )


def _request(
    *,
    wait_ordinal: int = 1,
    created_at: datetime = FIXED_AT,
    run_id: str = RUN_ID,
    mission_id: str = MISSION_ID,
    interrupt_id: str | None = None,
    reason_code: str = "AMBIGUOUS_SCOPE",
    human_readable_reason: str = "ambiguous facility scope",
) -> ConstructorHumanDecisionRequest:
    kwargs: dict[str, Any] = dict(
        run_id=run_id,
        mission_id=mission_id,
        reason_code=reason_code,
        route="WAIT_HUMAN",
        severity="BLOCKING",
        human_readable_reason=human_readable_reason,
        wait_ordinal=wait_ordinal,
        current_scope_summary=_scope(),
        evidence_refs=("exc-1",),
        authorization_id_ref="auth-ref-11c3",
        project_code=PROJECT,
        created_at=created_at,
    )
    if interrupt_id is not None:
        kwargs["interrupt_id"] = interrupt_id
    return build_human_decision_request(**kwargs)


def _answer(
    request: ConstructorHumanDecisionRequest,
    *,
    decision_id: str = "dec-11c3-1",
    decision: str = DECISION_CLARIFY_SCOPE,
    run_id: str | None = None,
    mission_id: str | None = None,
    interrupt_id: str | None = None,
    submitted_at: datetime = FIXED_AT,
    expected_checkpoint_id: str | None = "ckpt-11c3-1",
) -> ConstructorResumeCommand:
    return build_resume_command(
        decision_id=decision_id,
        interrupt_id=interrupt_id or request.interrupt_id,
        run_id=run_id or request.run_id,
        mission_id=mission_id or request.mission_id,
        decision=decision,
        actor_id="human-11c3",
        parameters={"facility_scope": ["FACILITY_TARGET"]},
        comment="clarify facility",
        expected_checkpoint_id=expected_checkpoint_id,
        submitted_at=submitted_at,
        idempotency_key="idem-11c3-1",
    )


def test_real_runtime_root_absent_before_tests() -> None:
    _require_real_runtime_absent()


def test_import_creates_no_runtime_root() -> None:
    _require_real_runtime_absent()
    import agents.monthly_plan_constructor.shadow_hitl_store as module

    assert module.bootstrap_constructor_shadow_hitl_store is not None
    assert not REAL_RUNTIME.exists()


def test_implements_constructor_hitl_store_write_api(tmp_path: Path) -> None:
    store = _bootstrap(tmp_path)
    try:
        assert callable(store.upsert_open_request)
        assert callable(store.record_answer)
        assert callable(store.get_request)
        assert callable(store.get_answer_for_interrupt)
    finally:
        store.close()


def test_bootstrap_creates_only_hitl_sqlite(tmp_path: Path) -> None:
    _require_real_runtime_absent()
    paths = resolve_constructor_shadow_runtime_paths(repository_root=tmp_path)
    assert not paths.runtime_root.exists()
    store = _bootstrap(tmp_path)
    try:
        assert paths.runtime_root.is_dir()
        assert store.db_path == paths.hitl_db_path
        assert store.db_path.is_file()
        assert store.db_path.name == "hitl.sqlite"
        assert not paths.checkpoints_db_path.exists()
        assert not paths.handoff_db_path.exists()
        assert not paths.observability_db_path.exists()
    finally:
        store.close()
    assert not REAL_RUNTIME.exists()


def test_request_and_answer_survive_independent_reopen(tmp_path: Path) -> None:
    request = _request()
    answer = _answer(request)
    store_a = _bootstrap(tmp_path)
    connection_a = store_a.connection
    try:
        store_a.upsert_open_request(request)
        assert store_a.get_request(request.interrupt_id) == request
        assert store_a.get_answer_for_interrupt(request.interrupt_id) is None
    finally:
        store_a.close()

    store_b = _bootstrap(tmp_path)
    try:
        assert store_b is not store_a
        assert store_b.connection is not connection_a
        restored_request = store_b.get_request(request.interrupt_id)
        assert restored_request == request
        assert restored_request is not None
        assert restored_request.created_at == FIXED_AT
        assert restored_request.authorization_id_ref == "auth-ref-11c3"
        assert restored_request.wait_ordinal == 1
        replay = _request(created_at=FIXED_AT + timedelta(minutes=5))
        assert replay.interrupt_id == request.interrupt_id
        store_b.upsert_open_request(replay)
        assert store_b.get_request(request.interrupt_id) == request
        store_b.record_answer(interrupt_id=request.interrupt_id, command=answer)
        assert store_b.get_answer_for_interrupt(request.interrupt_id) == answer
    finally:
        store_b.close()

    store_c = _bootstrap(tmp_path)
    try:
        restored_request = store_c.get_request(request.interrupt_id)
        restored_answer = store_c.get_answer_for_interrupt(request.interrupt_id)
        assert restored_request == request
        assert restored_answer == answer
        assert restored_answer is not None
        assert restored_answer.expected_checkpoint_id == "ckpt-11c3-1"
        assert restored_answer.decision == DECISION_CLARIFY_SCOPE
        paths = resolve_constructor_shadow_runtime_paths(repository_root=tmp_path)
        sqlite_files = list(paths.runtime_root.glob("*.sqlite"))
        assert sqlite_files == [paths.hitl_db_path]
    finally:
        store_c.close()
    assert not REAL_RUNTIME.exists()


def test_same_wait_replay_keeps_first_created_at(tmp_path: Path) -> None:
    first = _request(created_at=FIXED_AT)
    later = _request(created_at=FIXED_AT + timedelta(hours=1))
    assert first.interrupt_id == later.interrupt_id
    store = _bootstrap(tmp_path)
    try:
        store.upsert_open_request(first)
        store.upsert_open_request(later)
        stored = store.get_request(first.interrupt_id)
        assert stored == first
        assert stored is not None
        assert stored.created_at == FIXED_AT
        count = store.connection.execute(
            "SELECT COUNT(*) AS n FROM hitl_open_requests"
        ).fetchone()["n"]
        assert count == 1
    finally:
        store.close()


def test_conflicting_request_same_interrupt_fails_closed(tmp_path: Path) -> None:
    first = _request()
    colliding = _request(run_id="run-other", interrupt_id=first.interrupt_id)
    store = _bootstrap(tmp_path)
    try:
        store.upsert_open_request(first)
        with pytest.raises(ShadowHitlStoreError) as raised:
            store.upsert_open_request(colliding)
        assert raised.value.code == CODE_SHADOW_HITL_STORE_BLOCKER
        assert store.get_request(first.interrupt_id) == first
    finally:
        store.close()


def test_multi_wait_distinct_after_reopen(tmp_path: Path) -> None:
    wait_one = _request(wait_ordinal=1)
    wait_two = _request(wait_ordinal=2)
    assert wait_one.interrupt_id != wait_two.interrupt_id
    assert wait_one.interrupt_id == compute_eos_interrupt_id(
        run_id=RUN_ID, wait_ordinal=1, reason_code="AMBIGUOUS_SCOPE"
    )
    store = _bootstrap(tmp_path)
    try:
        store.upsert_open_request(wait_one)
        store.upsert_open_request(wait_two)
    finally:
        store.close()
    reopened = _bootstrap(tmp_path)
    try:
        assert reopened.get_request(wait_one.interrupt_id) == wait_one
        assert reopened.get_request(wait_two.interrupt_id) == wait_two
        count = reopened.connection.execute(
            "SELECT COUNT(*) AS n FROM hitl_open_requests"
        ).fetchone()["n"]
        assert count == 2
    finally:
        reopened.close()


def test_unknown_interrupt_answer_fails_closed(tmp_path: Path) -> None:
    request = _request()
    answer = _answer(request)
    store = _bootstrap(tmp_path)
    try:
        with pytest.raises(ShadowHitlStoreError) as raised:
            store.record_answer(interrupt_id=request.interrupt_id, command=answer)
        assert raised.value.code == CODE_SHADOW_HITL_STORE_BLOCKER
        assert store.get_answer_for_interrupt(request.interrupt_id) is None
    finally:
        store.close()


def test_wrong_interrupt_binding_fails_closed(tmp_path: Path) -> None:
    request = _request()
    other = _request(wait_ordinal=2)
    answer = _answer(request, interrupt_id=other.interrupt_id)
    store = _bootstrap(tmp_path)
    try:
        store.upsert_open_request(request)
        with pytest.raises(ShadowHitlStoreError) as raised:
            store.record_answer(interrupt_id=request.interrupt_id, command=answer)
        assert raised.value.code == CODE_SHADOW_HITL_STORE_BLOCKER
        assert store.get_answer_for_interrupt(request.interrupt_id) is None
    finally:
        store.close()


def test_wrong_run_and_mission_fail_closed(tmp_path: Path) -> None:
    request = _request()
    store = _bootstrap(tmp_path)
    try:
        store.upsert_open_request(request)
        wrong_run = _answer(request, run_id="run-other")
        with pytest.raises(ShadowHitlStoreError) as raised:
            store.record_answer(interrupt_id=request.interrupt_id, command=wrong_run)
        assert raised.value.code == CODE_SHADOW_HITL_STORE_BLOCKER
        wrong_mission = _answer(request, mission_id="mission-other")
        with pytest.raises(ShadowHitlStoreError) as raised:
            store.record_answer(
                interrupt_id=request.interrupt_id,
                command=wrong_mission,
            )
        assert raised.value.code == CODE_SHADOW_HITL_STORE_BLOCKER
        assert store.get_answer_for_interrupt(request.interrupt_id) is None
    finally:
        store.close()


def test_identical_answer_replay_is_idempotent(tmp_path: Path) -> None:
    request = _request()
    answer = _answer(request)
    store = _bootstrap(tmp_path)
    try:
        store.upsert_open_request(request)
        store.record_answer(interrupt_id=request.interrupt_id, command=answer)
        store.record_answer(interrupt_id=request.interrupt_id, command=answer)
        count = store.connection.execute(
            "SELECT COUNT(*) AS n FROM hitl_answers"
        ).fetchone()["n"]
        assert count == 1
        assert store.get_answer_for_interrupt(request.interrupt_id) == answer
    finally:
        store.close()


def test_conflicting_answer_fails_closed_and_original_survives_reopen(
    tmp_path: Path,
) -> None:
    request = _request()
    original = _answer(request, decision_id="dec-original")
    conflicting_id = _answer(request, decision_id="dec-other")
    conflicting_payload = _answer(
        request,
        decision_id="dec-original",
        decision=DECISION_ABORT_RUN,
        expected_checkpoint_id=None,
    )
    store = _bootstrap(tmp_path)
    try:
        store.upsert_open_request(request)
        store.record_answer(interrupt_id=request.interrupt_id, command=original)
        with pytest.raises(ShadowHitlStoreError) as raised:
            store.record_answer(
                interrupt_id=request.interrupt_id,
                command=conflicting_id,
            )
        assert raised.value.code == CODE_SHADOW_HITL_STORE_BLOCKER
        with pytest.raises(ShadowHitlStoreError) as raised:
            store.record_answer(
                interrupt_id=request.interrupt_id,
                command=conflicting_payload,
            )
        assert raised.value.code == CODE_SHADOW_HITL_STORE_BLOCKER
        assert store.get_answer_for_interrupt(request.interrupt_id) == original
    finally:
        store.close()
    reopened = _bootstrap(tmp_path)
    try:
        assert reopened.get_answer_for_interrupt(request.interrupt_id) == original
        assert reopened.get_request(request.interrupt_id) == request
    finally:
        reopened.close()


def test_close_is_idempotent_and_access_fails_closed(tmp_path: Path) -> None:
    request = _request()
    store = _bootstrap(tmp_path)
    connection = store.connection
    store.close()
    store.close()
    assert store.closed
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    with pytest.raises(ShadowHitlStoreError) as raised:
        store.get_request(request.interrupt_id)
    assert raised.value.code == CODE_SHADOW_HITL_STORE_BLOCKER
    with pytest.raises(ShadowHitlStoreError) as raised:
        store.upsert_open_request(request)
    assert raised.value.code == CODE_SHADOW_HITL_STORE_BLOCKER
    with pytest.raises(ShadowHitlStoreError) as raised:
        store.record_answer(interrupt_id=request.interrupt_id, command=_answer(request))
    assert raised.value.code == CODE_SHADOW_HITL_STORE_BLOCKER


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
        "agents.monthly_plan_constructor.shadow_hitl_store.sqlite3.connect",
        tracking_connect,
    )

    def boom(connection: Any) -> None:
        raise RuntimeError("schema failed")

    monkeypatch.setattr(
        "agents.monthly_plan_constructor.shadow_hitl_store._apply_hitl_schema",
        boom,
    )
    with pytest.raises(RuntimeError, match="schema failed"):
        bootstrap_constructor_shadow_hitl_store(repository_root=tmp_path)
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


def test_does_not_write_real_canonical_runtime_root(tmp_path: Path) -> None:
    _require_real_runtime_absent()
    store = _bootstrap(tmp_path)
    store.close()
    assert not REAL_RUNTIME.exists()
    assert (tmp_path / ".runtime").exists()
    assert not (REPO / ".runtime").exists()
