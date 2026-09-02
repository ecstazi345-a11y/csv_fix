"""
Increment 10.7 — Control Room factory tests.

Fail-closed path resolution. No ghost database auto-create.
"""

from __future__ import annotations

import inspect
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.control_room.factory import (
    AGENT_OBSERVABILITY_DB_PATH_ENV,
    ControlRoomConfigurationError,
    build_agent_control_room_query_port,
    resolve_observability_db_path,
)
from agents.control_room.query_port import AgentControlRoomQueryPort
from agents.observability.contracts import (
    InitiatorType,
    OperationalStatus,
    TriggerType,
    build_agent_run,
)
from agents.observability.sqlite_store import SqliteObservabilityStore

FIXED_AT = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)


def _build_run(**overrides: Any):
    payload = {
        "run_id": "run-factory-001",
        "request_id": "req-factory-001",
        "agent_code": "MONTHLY_PLAN_CONSTRUCTOR",
        "agent_version": "0.1",
        "mission_id": "mission-001",
        "project_code": "PRJ_001",
        "month_key": "2026-09",
        "initiator_type": InitiatorType.HUMAN,
        "initiator_id": "operator-local",
        "trigger_type": TriggerType.MANUAL,
        "trigger_reason": "manual-start",
        "operational_status": OperationalStatus.REQUESTED,
        "requested_at": FIXED_AT,
        "updated_at": FIXED_AT,
        "thread_id": "run-factory-001",
        "scope_summary": {"facility": "A"},
        "safe_summary": {"phase": "starting"},
        "safe_counts": {"candidates": 0},
        "projection_version": 0,
    }
    payload.update(overrides)
    return build_agent_run(**payload)


def _create_existing_observability_db() -> Path:
    handle = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    handle.close()
    path = Path(handle.name)
    store = SqliteObservabilityStore(path)
    store.create_run(_build_run())
    store.close()
    return path


def _close_port_store(port: AgentControlRoomQueryPort) -> None:
    store = getattr(port, "_store", None)
    close = getattr(store, "close", None)
    if callable(close):
        close()


class ControlRoomFactoryTests(unittest.TestCase):
    def test_missing_env_fail_closed(self) -> None:
        env = os.environ.pop(AGENT_OBSERVABILITY_DB_PATH_ENV, None)
        try:
            with self.assertRaises(ControlRoomConfigurationError):
                resolve_observability_db_path()
            with self.assertRaises(ControlRoomConfigurationError):
                build_agent_control_room_query_port()
        finally:
            if env is not None:
                os.environ[AGENT_OBSERVABILITY_DB_PATH_ENV] = env

    def test_nonexistent_path_fail_closed_no_ghost_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.sqlite"
            self.assertFalse(missing.exists())
            with self.assertRaises(ControlRoomConfigurationError):
                resolve_observability_db_path(override_path=missing)
            self.assertFalse(missing.exists())

    def test_existing_temp_sqlite_returns_query_port(self) -> None:
        db_path = _create_existing_observability_db()
        port: AgentControlRoomQueryPort | None = None
        try:
            port = build_agent_control_room_query_port(override_path=db_path)
            self.assertIsInstance(port, AgentControlRoomQueryPort)
            view = port.list_runs(limit=10)
            self.assertEqual(len(view.items), 1)
            self.assertEqual(view.items[0].run_id, "run-factory-001")
            snapshot = port.get_run_snapshot("run-factory-001")
            self.assertEqual(snapshot.run.run_id, "run-factory-001")
        finally:
            if port is not None:
                _close_port_store(port)
            db_path.unlink(missing_ok=True)

    def test_path_not_returned_or_exposed(self) -> None:
        db_path = _create_existing_observability_db()
        port = build_agent_control_room_query_port(override_path=db_path)
        try:
            self.assertIsInstance(port, AgentControlRoomQueryPort)
            self.assertNotIsInstance(port, Path)
            self.assertNotIsInstance(port, str)
            sig = inspect.signature(build_agent_control_room_query_port)
            self.assertEqual(str(sig.return_annotation), "AgentControlRoomQueryPort")
        finally:
            _close_port_store(port)
            db_path.unlink(missing_ok=True)

    def test_factory_has_no_streamlit_import(self) -> None:
        import agents.control_room.factory as factory_module

        source = inspect.getsource(factory_module)
        self.assertNotIn("streamlit", source)


if __name__ == "__main__":
    unittest.main()
