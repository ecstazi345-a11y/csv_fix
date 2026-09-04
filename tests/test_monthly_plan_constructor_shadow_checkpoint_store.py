"""
Increment 11C.2 — Durable SQLite checkpointer tests.

tmp_path only. Does not create C:\\csv_fix\\.runtime.
Does not start Shadow composition, HITL, handoff, or product reads.

LangGraph proof: a tiny compiled StateGraph uses SqliteSaver through the
supported compile/invoke/get_state contract. That is sufficient for 11C.2
because the increment owns checkpoint durability + serializer injection +
thread identity, not Constructor professional graph behavior.
"""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path
from typing import Any, TypedDict

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.graph import END, START, StateGraph

from agents.monthly_plan_constructor.durable_checkpoint import (
    CONSTRUCTOR_MSGPACK_ALLOWLIST,
)
from agents.monthly_plan_constructor.shadow_checkpoint_store import (
    CODE_SHADOW_CHECKPOINT_STORE_BLOCKER,
    ConstructorShadowCheckpointStore,
    ShadowCheckpointStoreError,
    bootstrap_constructor_shadow_checkpoint_store,
)
from agents.monthly_plan_constructor.shadow_runtime_stores import (
    resolve_constructor_shadow_runtime_paths,
)
from security.agent_execution_context import (
    AgentExecutionContext,
    issue_read_only_agent_context,
)

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO / "agents" / "monthly_plan_constructor" / "shadow_checkpoint_store.py"
)
REAL_RUNTIME = REPO / ".runtime"
RUN_ID = "run-11c2-shadow-checkpoint"

PLAN_LINE_TOKENS = (
    "load_constructor_month_plan_lines",
    "execute_constructor_plan_lines_read",
    "monthly_plan_lines_v2",
)
FORBIDDEN_IMPORTS = (
    "supabase",
    "streamlit",
    "requests",
    "dotenv",
    "openai",
)
FORBIDDEN_TOKENS = PLAN_LINE_TOKENS + (
    "create_client",
    "AGENT_OBSERVABILITY_DB_PATH",
    "from_conn_string",
    "SqliteObservabilityStore",
    "build_constructor_shadow_composition",
    "ConstructorShadowComposition",
)


class _TinyCheckpointState(TypedDict):
    marker: str


def _require_real_runtime_absent() -> None:
    if REAL_RUNTIME.exists():
        pytest.fail(
            "real C:\\csv_fix\\.runtime already exists; 11C.2 must stop "
            "rather than delete or reuse it"
        )


def _bootstrap(tmp_path: Path) -> ConstructorShadowCheckpointStore:
    return bootstrap_constructor_shadow_checkpoint_store(
        repository_root=tmp_path,
    )


def _tiny_graph(checkpointer: Any) -> Any:
    def echo(state: _TinyCheckpointState) -> _TinyCheckpointState:
        return {"marker": f"{state['marker']}|persisted"}

    graph = StateGraph(_TinyCheckpointState)
    graph.add_node("echo", echo)
    graph.add_edge(START, "echo")
    graph.add_edge("echo", END)
    return graph.compile(checkpointer=checkpointer)


def _config(run_id: str = RUN_ID) -> dict[str, Any]:
    return {"configurable": {"thread_id": run_id}}


def _sidecar_sqlite_names(paths: Any) -> tuple[Path, Path, Path]:
    return (
        paths.observability_db_path,
        paths.hitl_db_path,
        paths.handoff_db_path,
    )


def test_real_runtime_root_absent_before_tests() -> None:
    _require_real_runtime_absent()


def test_import_creates_no_runtime_root() -> None:
    _require_real_runtime_absent()
    import agents.monthly_plan_constructor.shadow_checkpoint_store as module

    assert module.bootstrap_constructor_shadow_checkpoint_store is not None
    assert not REAL_RUNTIME.exists()


def test_bootstrap_creates_only_checkpoints_sqlite(tmp_path: Path) -> None:
    _require_real_runtime_absent()
    paths = resolve_constructor_shadow_runtime_paths(repository_root=tmp_path)
    assert not paths.runtime_root.exists()
    store = _bootstrap(tmp_path)
    try:
        assert paths.runtime_root.is_dir()
        assert store.db_path == paths.checkpoints_db_path
        assert store.db_path.is_file()
        assert store.db_path.name == "checkpoints.sqlite"
        for sidecar in _sidecar_sqlite_names(paths):
            assert not sidecar.exists()
    finally:
        store.close()
    assert not REAL_RUNTIME.exists()


def test_safe_serializer_is_attached(tmp_path: Path) -> None:
    store = _bootstrap(tmp_path)
    try:
        serde = store.checkpointer.serde
        assert serde is not None
        assert getattr(serde, "pickle_fallback", True) is False
        allowed = set(getattr(serde, "_allowed_msgpack_modules"))
        assert allowed == set(CONSTRUCTOR_MSGPACK_ALLOWLIST)
        assert (
            "security.agent_execution_context",
            "AgentExecutionContext",
        ) not in allowed
    finally:
        store.close()


def test_unsafe_agent_execution_context_fails_closed(tmp_path: Path) -> None:
    store = _bootstrap(tmp_path)
    try:
        context = issue_read_only_agent_context(
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            project_code="PRJ_001_БХК",
            run_id=RUN_ID,
        )
        assert isinstance(context, AgentExecutionContext)
        checkpoint = empty_checkpoint()
        checkpoint["channel_values"] = {"context": context}
        config = {
            "configurable": {
                "thread_id": RUN_ID,
                "checkpoint_ns": "",
            }
        }
        store.checkpointer.put(config, checkpoint, {"source": "input", "step": 0}, {})
        restored = store.checkpointer.get_tuple(config)
        assert restored is not None
        payload = restored.checkpoint["channel_values"]["context"]
        assert not isinstance(payload, AgentExecutionContext)
        assert isinstance(payload, dict)
        allowed = set(store.checkpointer.serde._allowed_msgpack_modules)
        assert allowed == set(CONSTRUCTOR_MSGPACK_ALLOWLIST)
    finally:
        store.close()


def test_reopen_new_connection_reads_langgraph_checkpoint(tmp_path: Path) -> None:
    """
    Sufficiency: compile/invoke/get_state is the public LangGraph checkpointer
    contract. 11C.2 does not re-prove Constructor professional lifecycle.
    """
    store_a = _bootstrap(tmp_path)
    connection_a = store_a.connection
    try:
        app_a = _tiny_graph(store_a.checkpointer)
        result = app_a.invoke({"marker": "shadow"}, _config())
        assert result["marker"] == "shadow|persisted"
        tuple_a = store_a.checkpointer.get_tuple(_config())
        assert tuple_a is not None
        assert tuple_a.config["configurable"]["thread_id"] == RUN_ID
        checkpoint_id = tuple_a.config["configurable"]["checkpoint_id"]
        assert checkpoint_id
    finally:
        store_a.close()

    assert store_a.closed
    with pytest.raises(ShadowCheckpointStoreError) as raised:
        store_a.checkpointer
    assert raised.value.code == CODE_SHADOW_CHECKPOINT_STORE_BLOCKER

    store_b = _bootstrap(tmp_path)
    try:
        assert store_b is not store_a
        assert store_b.connection is not connection_a
        assert store_b.db_path == store_a.db_path
        app_b = _tiny_graph(store_b.checkpointer)
        snapshot = app_b.get_state(_config())
        assert snapshot.values["marker"] == "shadow|persisted"
        assert snapshot.config["configurable"]["thread_id"] == RUN_ID
        tuple_b = store_b.checkpointer.get_tuple(_config())
        assert tuple_b is not None
        assert tuple_b.config["configurable"]["checkpoint_id"] == checkpoint_id
        paths = resolve_constructor_shadow_runtime_paths(repository_root=tmp_path)
        for sidecar in _sidecar_sqlite_names(paths):
            assert not sidecar.exists()
    finally:
        store_b.close()
    assert not REAL_RUNTIME.exists()


def test_wrong_thread_id_does_not_return_other_run(tmp_path: Path) -> None:
    store = _bootstrap(tmp_path)
    try:
        app = _tiny_graph(store.checkpointer)
        app.invoke({"marker": "shadow"}, _config(RUN_ID))
        missing = store.checkpointer.get_tuple(_config("run-other-thread"))
        assert missing is None
        found = store.checkpointer.get_tuple(_config(RUN_ID))
        assert found is not None
        assert found.config["configurable"]["thread_id"] == RUN_ID
    finally:
        store.close()


def test_bootstrap_closes_connection_if_setup_fails(
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
        "agents.monthly_plan_constructor.shadow_checkpoint_store.sqlite3.connect",
        tracking_connect,
    )

    def boom(self: Any) -> None:
        raise RuntimeError("setup failed")

    monkeypatch.setattr(
        "agents.monthly_plan_constructor.shadow_checkpoint_store.SqliteSaver.setup",
        boom,
    )
    with pytest.raises(RuntimeError, match="setup failed"):
        bootstrap_constructor_shadow_checkpoint_store(repository_root=tmp_path)
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")


def test_close_is_idempotent_and_releases_connection(tmp_path: Path) -> None:
    store = _bootstrap(tmp_path)
    connection = store.connection
    store.close()
    store.close()
    assert store.closed
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    with pytest.raises(ShadowCheckpointStoreError) as raised:
        store.connection
    assert raised.value.code == CODE_SHADOW_CHECKPOINT_STORE_BLOCKER


def test_repeated_bootstrap_against_existing_db(tmp_path: Path) -> None:
    first = _bootstrap(tmp_path)
    try:
        app = _tiny_graph(first.checkpointer)
        app.invoke({"marker": "shadow"}, _config())
    finally:
        first.close()
    second = _bootstrap(tmp_path)
    try:
        snapshot = _tiny_graph(second.checkpointer).get_state(_config())
        assert snapshot.values["marker"] == "shadow|persisted"
        paths = resolve_constructor_shadow_runtime_paths(repository_root=tmp_path)
        sqlite_files = list(paths.runtime_root.glob("*.sqlite"))
        assert sqlite_files == [paths.checkpoints_db_path]
    finally:
        second.close()


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
        assert token not in source
    for token in FORBIDDEN_TOKENS:
        assert token not in source
    assert "from_conn_string" not in source
    assert "pickle" not in source
    assert "SqliteSaver(connection)" not in source
    assert "SqliteSaver(conn)" not in source
    assert "serde=serializer" in source
    assert "checkpointer.setup()" in source
    assert "check_same_thread=False" in source
    assert "supabase" not in source.lower()


def test_does_not_write_real_canonical_runtime_root(tmp_path: Path) -> None:
    _require_real_runtime_absent()
    store = _bootstrap(tmp_path)
    store.close()
    assert not REAL_RUNTIME.exists()
    assert (tmp_path / ".runtime").exists()
    assert not (REPO / ".runtime").exists()
