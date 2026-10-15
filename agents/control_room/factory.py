"""
Increment 10.7 — headless Control Room Query Port composition.

Resolves AGENT_OBSERVABILITY_DB_PATH (required in production).
Does NOT auto-create observability databases.

10.7 establishes AGENT_OBSERVABILITY_DB_PATH as the Control Room configuration
convention. ConstructorManagedRuntimeLauncher still receives observability_db_path
explicitly — full production wiring (Run Control + Launcher + Control Room on the
same file) is proven in Increment 10.10, not here.

When the env var is unset, an existing Constructor shadow observability.sqlite
beside this repository is accepted as the same durable truth the live launcher
writes — never created here, never copied.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

from agents.control_room.constructor_professional_result_reader import (
    ConstructorProfessionalResultReader,
    sibling_checkpoint_path,
)
from agents.control_room.query_port import AgentControlRoomQueryPort
from agents.observability.sqlite_store import SqliteObservabilityStore

AGENT_OBSERVABILITY_DB_PATH_ENV = "AGENT_OBSERVABILITY_DB_PATH"

CODE_CONTROL_ROOM_CONFIGURATION = "CONTROL_ROOM_CONFIGURATION"


class ControlRoomConfigurationError(ValueError):
    """Fail-closed Control Room infrastructure configuration error."""

    def __init__(self, message: str) -> None:
        self.code = CODE_CONTROL_ROOM_CONFIGURATION
        super().__init__(message)


def _repository_root() -> Path:
    # agents/control_room/factory.py → repository root
    return Path(__file__).resolve().parents[2]


def _existing_constructor_shadow_observability_path() -> Optional[Path]:
    """Return existing shadow observability.sqlite, or None. Never creates files."""
    try:
        from agents.monthly_plan_constructor.shadow_runtime_stores import (
            resolve_constructor_shadow_runtime_paths,
        )

        paths = resolve_constructor_shadow_runtime_paths(
            repository_root=_repository_root(),
        )
    except Exception:
        return None
    candidate = paths.observability_db_path
    if candidate.is_file():
        return candidate.resolve()
    return None


def resolve_observability_db_path(
    *,
    override_path: Optional[Union[str, Path]] = None,
) -> Path:
    """
    Resolve an existing observability SQLite file path.

    Prefer AGENT_OBSERVABILITY_DB_PATH. When unset, use an already-present
    Constructor shadow observability store for this repository.
    Tests may pass override_path pointing to a pre-created database file.
    Does not create databases.
    """
    if override_path is not None:
        path = Path(override_path)
    else:
        configured = os.environ.get(AGENT_OBSERVABILITY_DB_PATH_ENV)
        if configured is not None and str(configured).strip():
            path = Path(str(configured).strip())
        else:
            shadow = _existing_constructor_shadow_observability_path()
            if shadow is None:
                raise ControlRoomConfigurationError(
                    f"{AGENT_OBSERVABILITY_DB_PATH_ENV} is required",
                )
            path = shadow

    if not path.is_file():
        raise ControlRoomConfigurationError(
            "configured observability database does not exist",
        )
    return path.resolve()


def build_agent_control_room_query_port(
    *,
    override_path: Optional[Union[str, Path]] = None,
) -> AgentControlRoomQueryPort:
    """Construct SqliteObservabilityStore + AgentControlRoomQueryPort. Read-only."""
    db_path = resolve_observability_db_path(override_path=override_path)
    store = SqliteObservabilityStore(db_path)
    reader = ConstructorProfessionalResultReader(sibling_checkpoint_path(db_path))
    return AgentControlRoomQueryPort(store, professional_result_reader=reader)
