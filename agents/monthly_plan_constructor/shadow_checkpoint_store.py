"""
Increment 11C.2 — Durable SQLite LangGraph checkpointer for Shadow runtime.

Explicit infrastructure bootstrap only. Not Constructor profession logic.
Not HITL persistence. Not handoff persistence. Not observability. Not Run Control.

Creates only:
<repository_root>/.runtime/shadow/constructor/checkpoints.sqlite

Path arithmetic stays in shadow_runtime_stores.
Serializer / allowlist stays in durable_checkpoint.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Union

from langgraph.checkpoint.sqlite import SqliteSaver

from agents.monthly_plan_constructor.durable_checkpoint import (
    build_constructor_jsonplus_serializer,
)
from agents.monthly_plan_constructor.shadow_runtime_stores import (
    resolve_constructor_shadow_runtime_paths,
)

CODE_SHADOW_CHECKPOINT_STORE_BLOCKER = "SHADOW_CHECKPOINT_STORE_BLOCKER"


class ShadowCheckpointStoreError(ValueError):
    """Fail-closed Shadow SQLite checkpointer infrastructure violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ConstructorShadowCheckpointStore:
    """
    Owned SQLite checkpoint resource.

    Holds the connection, the SqliteSaver, and the canonical db path.
    close() is idempotent. After close, accessors fail closed.
    """

    def __init__(
        self,
        *,
        db_path: Path,
        connection: sqlite3.Connection,
        checkpointer: SqliteSaver,
    ) -> None:
        self._db_path = db_path
        self._connection = connection
        self._checkpointer = checkpointer
        self._closed = False

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def connection(self) -> sqlite3.Connection:
        self._require_open()
        return self._connection

    @property
    def checkpointer(self) -> SqliteSaver:
        self._require_open()
        return self._checkpointer

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._connection.close()

    def __enter__(self) -> "ConstructorShadowCheckpointStore":
        self._require_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def _require_open(self) -> None:
        if self._closed:
            raise ShadowCheckpointStoreError(
                CODE_SHADOW_CHECKPOINT_STORE_BLOCKER,
                "ConstructorShadowCheckpointStore is closed",
            )


def bootstrap_constructor_shadow_checkpoint_store(
    *,
    repository_root: Union[str, Path],
) -> ConstructorShadowCheckpointStore:
    """
    Explicit Shadow checkpoint infrastructure bootstrap.

    Resolves canonical paths, creates the runtime directory, opens only
    checkpoints.sqlite, injects the Constructor serializer, and calls setup().
    """
    paths = resolve_constructor_shadow_runtime_paths(
        repository_root=repository_root,
    )
    try:
        paths.runtime_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ShadowCheckpointStoreError(
            CODE_SHADOW_CHECKPOINT_STORE_BLOCKER,
            "canonical Shadow runtime directory could not be created",
        ) from exc

    try:
        connection = sqlite3.connect(
            str(paths.checkpoints_db_path),
            check_same_thread=False,
        )
    except sqlite3.Error as exc:
        raise ShadowCheckpointStoreError(
            CODE_SHADOW_CHECKPOINT_STORE_BLOCKER,
            "checkpoints.sqlite could not be opened",
        ) from exc

    try:
        serializer = build_constructor_jsonplus_serializer()
        checkpointer = SqliteSaver(connection, serde=serializer)
        checkpointer.setup()
        return ConstructorShadowCheckpointStore(
            db_path=paths.checkpoints_db_path,
            connection=connection,
            checkpointer=checkpointer,
        )
    except BaseException:
        connection.close()
        raise
