"""
Increment 11C.1 — Shadow runtime path / infrastructure contract.

Pure path resolution only. Does not create directories, files, SQLite
connections, schemas, or store implementations.

Canonical topology (not created here):
<repository_root>/.runtime/shadow/constructor/
    observability.sqlite
    checkpoints.sqlite
    hitl.sqlite
    handoff.sqlite

No environment fallback. No cwd default. No home-directory default.
No product database. Persistent store implementations belong to later 11C.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

CODE_SHADOW_RUNTIME_STORES_BLOCKER = "SHADOW_RUNTIME_STORES_BLOCKER"

SHADOW_RUNTIME_ROOT_SEGMENTS: tuple[str, ...] = (".runtime", "shadow", "constructor")
OBSERVABILITY_DB_FILENAME = "observability.sqlite"
CHECKPOINTS_DB_FILENAME = "checkpoints.sqlite"
HITL_DB_FILENAME = "hitl.sqlite"
HANDOFF_DB_FILENAME = "handoff.sqlite"


class ShadowRuntimeStoresError(ValueError):
    """Fail-closed Shadow runtime path / infrastructure violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ConstructorShadowRuntimePaths:
    """Deterministic absolute Shadow runtime file paths. Not a store."""

    runtime_root: Path
    observability_db_path: Path
    checkpoints_db_path: Path
    hitl_db_path: Path
    handoff_db_path: Path


def resolve_constructor_shadow_runtime_paths(
    *,
    repository_root: Union[str, Path],
) -> ConstructorShadowRuntimePaths:
    """
    Derive canonical Shadow runtime paths from an explicit repository root.

    Pure: no directory creation, no file create, no SQLite open, no environment read.
    """
    root = _require_repository_root(repository_root)
    runtime_root = root.joinpath(*SHADOW_RUNTIME_ROOT_SEGMENTS)
    return ConstructorShadowRuntimePaths(
        runtime_root=runtime_root,
        observability_db_path=runtime_root / OBSERVABILITY_DB_FILENAME,
        checkpoints_db_path=runtime_root / CHECKPOINTS_DB_FILENAME,
        hitl_db_path=runtime_root / HITL_DB_FILENAME,
        handoff_db_path=runtime_root / HANDOFF_DB_FILENAME,
    )


def _require_repository_root(value: Any) -> Path:
    if value is None:
        raise ShadowRuntimeStoresError(
            CODE_SHADOW_RUNTIME_STORES_BLOCKER,
            "repository_root is required",
        )
    if not isinstance(value, (str, Path)):
        raise ShadowRuntimeStoresError(
            CODE_SHADOW_RUNTIME_STORES_BLOCKER,
            "repository_root must be a filesystem path",
        )
    text = str(value).strip()
    if not text:
        raise ShadowRuntimeStoresError(
            CODE_SHADOW_RUNTIME_STORES_BLOCKER,
            "repository_root is required",
        )
    path = Path(text)
    if not path.is_absolute():
        raise ShadowRuntimeStoresError(
            CODE_SHADOW_RUNTIME_STORES_BLOCKER,
            "repository_root must be an absolute path",
        )
    resolved = path.resolve()
    if resolved.exists() and resolved.is_file():
        raise ShadowRuntimeStoresError(
            CODE_SHADOW_RUNTIME_STORES_BLOCKER,
            "repository_root must not be a file",
        )
    return resolved
