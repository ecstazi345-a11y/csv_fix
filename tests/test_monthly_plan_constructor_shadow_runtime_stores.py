"""
Increment 11C.1 — Shadow runtime path contract tests.

tmp_path only. Does not create C:\\csv_fix\\.runtime or any real Shadow DBs.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

import pytest

from agents.monthly_plan_constructor.shadow_runtime_stores import (
    CODE_SHADOW_RUNTIME_STORES_BLOCKER,
    ConstructorShadowRuntimePaths,
    ShadowRuntimeStoresError,
    resolve_constructor_shadow_runtime_paths,
)

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO / "agents" / "monthly_plan_constructor" / "shadow_runtime_stores.py"
)
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
    "langgraph.checkpoint.sqlite",
)
FORBIDDEN_TOKENS = PLAN_LINE_TOKENS + (
    "create_client",
    "issue_read_only_agent_context",
    "AGENT_OBSERVABILITY_DB_PATH",
    "SqliteSaver",
    "pickle",
)


def _resolve(tmp_path: Path) -> ConstructorShadowRuntimePaths:
    return resolve_constructor_shadow_runtime_paths(repository_root=tmp_path)


def test_explicit_repository_root_required() -> None:
    for invalid in (None, "", "   ", 123):
        with pytest.raises(ShadowRuntimeStoresError) as raised:
            resolve_constructor_shadow_runtime_paths(
                repository_root=invalid,  # type: ignore[arg-type]
            )
        assert raised.value.code == CODE_SHADOW_RUNTIME_STORES_BLOCKER
    with pytest.raises(ShadowRuntimeStoresError) as raised:
        resolve_constructor_shadow_runtime_paths(
            repository_root=Path("relative") / "repo",
        )
    assert raised.value.code == CODE_SHADOW_RUNTIME_STORES_BLOCKER


def test_canonical_root_is_absolute_and_deterministic(tmp_path: Path) -> None:
    paths = _resolve(tmp_path)
    expected = (tmp_path.resolve() / ".runtime" / "shadow" / "constructor")
    assert paths.runtime_root == expected
    assert paths.runtime_root.is_absolute()
    assert paths.runtime_root.parts[-3:] == (".runtime", "shadow", "constructor")


def test_exact_db_filenames_and_distinct_paths(tmp_path: Path) -> None:
    paths = _resolve(tmp_path)
    assert paths.observability_db_path.name == "observability.sqlite"
    assert paths.checkpoints_db_path.name == "checkpoints.sqlite"
    assert paths.hitl_db_path.name == "hitl.sqlite"
    assert paths.handoff_db_path.name == "handoff.sqlite"
    names = {
        paths.observability_db_path,
        paths.checkpoints_db_path,
        paths.hitl_db_path,
        paths.handoff_db_path,
    }
    assert len(names) == 4
    for db_path in names:
        assert db_path.parent == paths.runtime_root
        assert db_path.is_absolute()


def test_resolver_creates_no_directory_or_files(tmp_path: Path) -> None:
    before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}
    _resolve(tmp_path)
    after = {p.relative_to(tmp_path) for p in tmp_path.rglob("*")}
    assert after == before
    assert not (tmp_path / ".runtime").exists()


def test_two_calls_same_root_return_same_paths(tmp_path: Path) -> None:
    first = _resolve(tmp_path)
    second = _resolve(tmp_path)
    assert first == second
    assert first.runtime_root == second.runtime_root
    assert first.observability_db_path == second.observability_db_path


def test_different_repository_roots_are_isolated(
    tmp_path: Path, tmp_path_factory: Any
) -> None:
    other = tmp_path_factory.mktemp("other-repo")
    first = _resolve(tmp_path)
    second = resolve_constructor_shadow_runtime_paths(repository_root=other)
    assert first.runtime_root != second.runtime_root
    assert first.observability_db_path != second.observability_db_path
    assert first.runtime_root.is_relative_to(tmp_path.resolve())
    assert second.runtime_root.is_relative_to(other.resolve())


def test_no_environment_dependency(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    decoy = tmp_path / "control_room.sqlite"
    monkeypatch.setenv("AGENT_OBSERVABILITY_DB_PATH", str(decoy))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    paths = _resolve(tmp_path)
    assert paths.observability_db_path == (
        tmp_path.resolve() / ".runtime" / "shadow" / "constructor" / "observability.sqlite"
    )
    assert Path(os.environ["AGENT_OBSERVABILITY_DB_PATH"]) != paths.observability_db_path


def test_frozen_path_contract_cannot_be_mutated(tmp_path: Path) -> None:
    paths = _resolve(tmp_path)
    with pytest.raises(AttributeError):
        paths.runtime_root = tmp_path / "mutated"  # type: ignore[misc]


def test_no_product_or_saver_imports() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr.lower() == "mkdir":
                raise AssertionError("mkdir call is forbidden")
            if isinstance(node.func, ast.Name) and node.func.id.lower() == "mkdir":
                raise AssertionError("mkdir call is forbidden")
    for token in FORBIDDEN_IMPORTS:
        assert token not in imported
        assert token not in source
    for token in FORBIDDEN_TOKENS:
        assert token not in source
    assert "supabase" not in source.lower()
    assert "sqlite3" not in source


def test_does_not_write_real_canonical_runtime_root() -> None:
    real_root = REPO / ".runtime"
    assert not real_root.exists()
