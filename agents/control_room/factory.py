"""
Increment 10.7 — headless Control Room Query Port composition.

Resolves AGENT_OBSERVABILITY_DB_PATH (required in production).
Does NOT auto-create observability databases.

10.7 establishes AGENT_OBSERVABILITY_DB_PATH as the Control Room configuration
convention. ConstructorManagedRuntimeLauncher still receives observability_db_path
explicitly — full production wiring (Run Control + Launcher + Control Room on the
same file) is proven in Increment 10.10, not here.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

from agents.control_room.query_port import AgentControlRoomQueryPort
from agents.observability.sqlite_store import SqliteObservabilityStore

AGENT_OBSERVABILITY_DB_PATH_ENV = "AGENT_OBSERVABILITY_DB_PATH"

CODE_CONTROL_ROOM_CONFIGURATION = "CONTROL_ROOM_CONFIGURATION"


class ControlRoomConfigurationError(ValueError):
    """Fail-closed Control Room infrastructure configuration error."""

    def __init__(self, message: str) -> None:
        self.code = CODE_CONTROL_ROOM_CONFIGURATION
        super().__init__(message)


def resolve_observability_db_path(
    *,
    override_path: Optional[Union[str, Path]] = None,
) -> Path:
    """
    Resolve an existing observability SQLite file path.

    Production requires AGENT_OBSERVABILITY_DB_PATH.
    Tests may pass override_path pointing to a pre-created database file.
    """
    if override_path is not None:
        path = Path(override_path)
    else:
        configured = os.environ.get(AGENT_OBSERVABILITY_DB_PATH_ENV)
        if configured is None or not str(configured).strip():
            raise ControlRoomConfigurationError(
                f"{AGENT_OBSERVABILITY_DB_PATH_ENV} is required",
            )
        path = Path(str(configured).strip())

    if not path.is_file():
        raise ControlRoomConfigurationError(
            "configured observability database does not exist",
        )
    return path


def build_agent_control_room_query_port(
    *,
    override_path: Optional[Union[str, Path]] = None,
) -> AgentControlRoomQueryPort:
    """Construct SqliteObservabilityStore + AgentControlRoomQueryPort. Read-only."""
    db_path = resolve_observability_db_path(override_path=override_path)
    store = SqliteObservabilityStore(db_path)
    return AgentControlRoomQueryPort(store)
