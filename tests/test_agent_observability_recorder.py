"""
Increment 10.1B — ObservabilityRecorder Protocol + in-memory test recorder tests.

No Streamlit, LangGraph, Supabase, SQL, Docker, LLM, or product writes.
"""

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from agents.observability.contracts import (
    EventStatus,
    EventType,
    ObservabilityContractError,
    ObservabilityEvent,
    build_observability_event,
)
from agents.observability.recorder import (
    InMemoryObservabilityRecorder,
    ObservabilityEventConflictError,
    ObservabilityRecorder,
    RecordOutcome,
    RecordResult,
    compute_observability_event_fingerprint,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RECORDER_PATH = REPO_ROOT / "agents" / "observability" / "recorder.py"
PACKAGE_INIT_PATH = REPO_ROOT / "agents" / "observability" / "__init__.py"

FIXED_AT = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)

_FORBIDDEN_IMPORTS = frozenset(
    {
        "streamlit",
        "langgraph",
        "supabase",
        "pandas",
        "agents.monthly_plan_constructor",
        "psycopg",
        "sqlite3",
    }
)


def _event_kwargs(**overrides: Any) -> dict[str, Any]:
    payload = {
        "event_id": "evt-001",
        "run_id": "run-001",
        "agent_code": "MONTHLY_PLAN_CONSTRUCTOR",
        "occurred_at": FIXED_AT,
        "event_type": EventType.RUN_STARTED,
        "status": EventStatus.OK,
        "title": "Run started",
        "detail": {"node": "start"},
    }
    payload.update(overrides)
    return payload


def _build_event(**overrides: Any) -> ObservabilityEvent:
    return build_observability_event(**_event_kwargs(**overrides))


class ObservabilityRecorderTests(unittest.TestCase):
    def test_01_protocol_shape(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        self.assertIsInstance(recorder, ObservabilityRecorder)
        self.assertTrue(callable(recorder.record_event))

    def test_02_first_event_created(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        event = _build_event()
        result = recorder.record_event(event)
        self.assertEqual(result.outcome, RecordOutcome.CREATED)
        self.assertEqual(result.event_id, "evt-001")
        self.assertEqual(result.run_id, "run-001")
        self.assertIsInstance(result, RecordResult)

    def test_03_same_event_idempotent_replay(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        event = _build_event()
        first = recorder.record_event(event)
        second = recorder.record_event(event)
        self.assertEqual(first.outcome, RecordOutcome.CREATED)
        self.assertEqual(second.outcome, RecordOutcome.IDEMPOTENT_REPLAY)
        self.assertEqual(len(recorder.snapshot_events()), 1)

    def test_04_same_event_id_different_title_conflict(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        recorder.record_event(_build_event())
        with self.assertRaises(ObservabilityEventConflictError) as ctx:
            recorder.record_event(_build_event(title="Different title"))
        self.assertEqual(ctx.exception.code, "OBSERVABILITY_EVENT_CONFLICT")
        self.assertEqual(len(recorder.snapshot_events()), 1)

    def test_05_same_event_id_different_detail_conflict(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        recorder.record_event(_build_event())
        with self.assertRaises(ObservabilityEventConflictError):
            recorder.record_event(_build_event(detail={"node": "other"}))

    def test_06_same_event_id_different_run_id_conflict(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        recorder.record_event(_build_event())
        with self.assertRaises(ObservabilityEventConflictError):
            recorder.record_event(_build_event(run_id="run-other"))

    def test_07_two_event_ids_append_independently(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        recorder.record_event(_build_event(event_id="evt-a"))
        recorder.record_event(_build_event(event_id="evt-b", title="Second"))
        self.assertEqual(len(recorder.snapshot_events()), 2)

    def test_08_insertion_order_preserved(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        recorder.record_event(_build_event(event_id="evt-a", title="A"))
        recorder.record_event(_build_event(event_id="evt-b", title="B"))
        titles = [item.title for item in recorder.snapshot_events()]
        self.assertEqual(titles, ["A", "B"])

    def test_09_multiple_runs_supported(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        recorder.record_event(_build_event(event_id="evt-a", run_id="run-a"))
        recorder.record_event(_build_event(event_id="evt-b", run_id="run-b"))
        self.assertEqual(len(recorder.events_for_run("run-a")), 1)
        self.assertEqual(len(recorder.events_for_run("run-b")), 1)

    def test_10_events_for_run_filters_correctly(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        recorder.record_event(_build_event(event_id="evt-a", run_id="run-a"))
        recorder.record_event(_build_event(event_id="evt-b", run_id="run-b"))
        recorder.record_event(_build_event(event_id="evt-c", run_id="run-a", title="C"))
        run_a = recorder.events_for_run("run-a")
        self.assertEqual([item.event_id for item in run_a], ["evt-a", "evt-c"])

    def test_11_snapshot_cannot_mutate_recorder_internals(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        recorder.record_event(_build_event())
        snapshot = list(recorder.snapshot_events())
        snapshot.clear()
        self.assertEqual(len(recorder.snapshot_events()), 1)

    def test_12_event_not_mutated(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        event = _build_event()
        title = event.title
        recorder.record_event(event)
        self.assertEqual(event.title, title)

    def test_13_non_event_rejected(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        with self.assertRaises(ObservabilityContractError):
            recorder.record_event({"event_id": "evt-001"})  # type: ignore[arg-type]

    def test_14_secret_rejection_propagates(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        with self.assertRaises(ObservabilityContractError):
            recorder.record_event(
                _build_event(detail={"access_token": "secret-value"})
            )

    def test_15_invalid_serialization_fails_closed(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        event = _build_event()
        with patch.object(
            ObservabilityEvent,
            "to_dict",
            return_value={"bad": object()},
        ):
            with self.assertRaises(ObservabilityContractError):
                recorder.record_event(event)

    def test_16_fingerprint_deterministic(self) -> None:
        event = _build_event()
        a = compute_observability_event_fingerprint(event)
        b = compute_observability_event_fingerprint(event)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)

    def test_17_detail_order_does_not_change_fingerprint(self) -> None:
        event_a = _build_event(detail={"a": 1, "b": 2})
        event_b = _build_event(detail={"b": 2, "a": 1})
        self.assertEqual(
            compute_observability_event_fingerprint(event_a),
            compute_observability_event_fingerprint(event_b),
        )

    def test_18_replay_after_inspection_still_idempotent(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        event = _build_event()
        recorder.record_event(event)
        _ = recorder.snapshot_events()
        result = recorder.record_event(event)
        self.assertEqual(result.outcome, RecordOutcome.IDEMPOTENT_REPLAY)

    def test_19_conflict_does_not_overwrite_original(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        recorder.record_event(_build_event(title="Original"))
        with self.assertRaises(ObservabilityEventConflictError):
            recorder.record_event(_build_event(title="Replacement"))
        stored = recorder.snapshot_events()[0]
        self.assertEqual(stored.title, "Original")

    def test_20_conflict_leaves_count_unchanged(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        recorder.record_event(_build_event())
        with self.assertRaises(ObservabilityEventConflictError):
            recorder.record_event(_build_event(title="Other"))
        self.assertEqual(len(recorder.snapshot_events()), 1)

    def test_21_no_delete_clear_on_protocol(self) -> None:
        public = {
            name
            for name in dir(ObservabilityRecorder)
            if not name.startswith("_")
        }
        self.assertNotIn("clear", public)
        self.assertNotIn("delete", public)
        recorder_public = {
            name
            for name in dir(InMemoryObservabilityRecorder)
            if not name.startswith("_")
        }
        self.assertNotIn("clear_run", recorder_public)
        self.assertNotIn("delete_event", recorder_public)
        self.assertNotIn("delete_all", recorder_public)

    def test_22_different_agent_codes_supported(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        recorder.record_event(
            _build_event(event_id="evt-a", agent_code="MONTHLY_PLAN_CONSTRUCTOR")
        )
        recorder.record_event(
            _build_event(
                event_id="evt-b",
                agent_code="ADMISSION_AGENT",
                title="Admission",
            )
        )
        self.assertEqual(len(recorder.snapshot_events()), 2)

    def test_23_no_constructor_dependency(self) -> None:
        source = RECORDER_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
            for alias in node.names
        )
        self.assertNotIn("agents", imports)

    def test_24_no_forbidden_imports(self) -> None:
        source = RECORDER_PATH.read_text(encoding="utf-8")
        for forbidden in _FORBIDDEN_IMPORTS:
            self.assertNotIn(forbidden, source)

    def test_25_record_result_immutable(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        result = recorder.record_event(_build_event())
        with self.assertRaises(Exception):
            result.outcome = RecordOutcome.IDEMPOTENT_REPLAY  # type: ignore[misc]

    def test_26_recorder_does_not_invent_events(self) -> None:
        source = RECORDER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("build_observability_event", source)
        self.assertNotIn("EventType.", source)

    def test_27_public_exports_present(self) -> None:
        from agents import observability

        for symbol in (
            "ObservabilityRecorder",
            "InMemoryObservabilityRecorder",
            "RecordOutcome",
            "RecordResult",
            "ObservabilityEventConflictError",
        ):
            self.assertTrue(hasattr(observability, symbol))

    def test_28_events_for_run_rejects_blank_run_id(self) -> None:
        recorder = InMemoryObservabilityRecorder()
        with self.assertRaises(ObservabilityContractError):
            recorder.events_for_run("   ")

    def test_29_fingerprint_requires_event(self) -> None:
        with self.assertRaises(ObservabilityContractError):
            compute_observability_event_fingerprint(object())  # type: ignore[arg-type]

    def test_30_record_result_fields(self) -> None:
        result = RecordResult(
            outcome=RecordOutcome.CREATED,
            event_id="evt-001",
            run_id="run-001",
        )
        self.assertEqual(result.event_id, "evt-001")
        self.assertEqual(result.run_id, "run-001")


class ObservabilityRecorderIsolationTests(unittest.TestCase):
    def test_py_compile_recorder_module(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", str(RECORDER_PATH)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)

    def test_package_init_exports_only_recorder_symbols(self) -> None:
        source = PACKAGE_INIT_PATH.read_text(encoding="utf-8")
        self.assertIn("InMemoryObservabilityRecorder", source)
        self.assertIn("ObservabilityRecorder", source)
        self.assertNotIn("compute_observability_event_fingerprint", source)


if __name__ == "__main__":
    unittest.main()
