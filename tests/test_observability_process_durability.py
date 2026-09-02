"""
Increment 10.5 — separate-process SqliteObservabilityStore durability proof.

Process A writes durable state and exits. Process B opens the same SQLite file
in a fresh Python interpreter and reconstructs identical operational truth.

No production code. No Supabase. No Control Room. No shared in-memory store.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
_ROOT_STR = str(REPO_ROOT)
if _ROOT_STR not in sys.path:
    sys.path.insert(0, _ROOT_STR)

from agents.observability.contracts import (
    EventStatus,
    EventType,
    InitiatorType,
    OperationalStatus,
    TriggerType,
    build_agent_run,
    build_observability_event,
)
from agents.observability.durable_recorder import StoreObservabilityRecorder
from agents.observability.recorder import RecordOutcome, compute_observability_event_fingerprint
from agents.observability.store import CreateRunOutcome, DEFAULT_LIST_EVENTS_LIMIT
from agents.observability.sqlite_store import SqliteObservabilityStore

TEST_FILE = Path(__file__).resolve()
SUBPROCESS_TIMEOUT_SECONDS = 60

RUN_ID = "run-10-5-dur"
REQUEST_ID = "req-10-5-dur"
MISSION_ID = "mission-10-5-dur"
INTERRUPT_ID = "intr-10-5-dur"
HANDOFF_ID = "hof-10-5-dur"
AGENT_CODE = "GENERIC_TEST_AGENT"

T0 = datetime(2026, 9, 2, 14, 0, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 9, 2, 14, 0, 1, tzinfo=timezone.utc)
T2 = datetime(2026, 9, 2, 14, 0, 2, tzinfo=timezone.utc)
T3 = datetime(2026, 9, 2, 14, 0, 3, tzinfo=timezone.utc)
T4 = datetime(2026, 9, 2, 14, 0, 4, tzinfo=timezone.utc)
T5 = datetime(2026, 9, 2, 14, 0, 5, tzinfo=timezone.utc)
T6 = datetime(2026, 9, 2, 14, 0, 6, tzinfo=timezone.utc)

EXPECTED_EVENT_COUNT = 7
EXPECTED_PROJECTION_VERSION = 7


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _build_run() -> Any:
    return build_agent_run(
        run_id=RUN_ID,
        request_id=REQUEST_ID,
        agent_code=AGENT_CODE,
        agent_version="0.1",
        mission_id=MISSION_ID,
        project_code="PRJ_10_5",
        month_key="2026-09",
        initiator_type=InitiatorType.HUMAN,
        initiator_id="operator-10-5",
        trigger_type=TriggerType.MANUAL,
        trigger_reason="process-durability-proof",
        operational_status=OperationalStatus.REQUESTED,
        requested_at=T0,
        updated_at=T0,
        thread_id=RUN_ID,
        scope_summary={"proof": "10.5"},
        safe_summary={"phase": "starting"},
        safe_counts={"events": 0},
        projection_version=0,
    )


def _event_sequence() -> list[Any]:
    return [
        build_observability_event(
            event_id="evt-10-5-01",
            run_id=RUN_ID,
            agent_code=AGENT_CODE,
            occurred_at=T0,
            event_type=EventType.RUN_REQUESTED,
            status=EventStatus.OK,
            title="Run requested",
            detail={"phase": "request"},
        ),
        build_observability_event(
            event_id="evt-10-5-02",
            run_id=RUN_ID,
            agent_code=AGENT_CODE,
            occurred_at=T1,
            event_type=EventType.RUN_AUTHORIZATION_STARTED,
            status=EventStatus.OK,
            title="Authorization started",
            detail={"phase": "auth"},
        ),
        build_observability_event(
            event_id="evt-10-5-03",
            run_id=RUN_ID,
            agent_code=AGENT_CODE,
            occurred_at=T2,
            event_type=EventType.MISSION_BOUND,
            status=EventStatus.OK,
            title="Mission bound",
            mission_id=MISSION_ID,
            detail={"phase": "mission"},
        ),
        build_observability_event(
            event_id="evt-10-5-04",
            run_id=RUN_ID,
            agent_code=AGENT_CODE,
            occurred_at=T3,
            event_type=EventType.RUN_ADVANCING,
            status=EventStatus.OK,
            title="Run advancing",
            detail={"phase": "runtime"},
        ),
        build_observability_event(
            event_id="evt-10-5-05",
            run_id=RUN_ID,
            agent_code=AGENT_CODE,
            occurred_at=T4,
            event_type=EventType.HUMAN_WAIT_STARTED,
            status=EventStatus.OK,
            title="Human wait started",
            interrupt_id=INTERRUPT_ID,
            detail={"phase": "hitl"},
        ),
        build_observability_event(
            event_id="evt-10-5-06",
            run_id=RUN_ID,
            agent_code=AGENT_CODE,
            occurred_at=T5,
            event_type=EventType.RUN_RESUMED,
            status=EventStatus.OK,
            title="Run resumed",
            resume_n=1,
            detail={"phase": "resume"},
        ),
        build_observability_event(
            event_id="evt-10-5-07",
            run_id=RUN_ID,
            agent_code=AGENT_CODE,
            occurred_at=T6,
            event_type=EventType.RUN_COMPLETED,
            status=EventStatus.OK,
            title="Run completed",
            handoff_id=HANDOFF_ID,
            detail={"phase": "complete"},
        ),
    ]


def _first_event_for_replay() -> Any:
    return build_observability_event(
        event_id="evt-10-5-01",
        run_id=RUN_ID,
        agent_code=AGENT_CODE,
        occurred_at=T0,
        event_type=EventType.RUN_REQUESTED,
        status=EventStatus.OK,
        title="Run requested",
        detail={"phase": "request"},
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fingerprints_for_events(events: list[Any]) -> list[str]:
    return [compute_observability_event_fingerprint(event) for event in events]


def role_process_a(db_path: Path, handshake_path: Path, result_path: Path) -> int:
    events = _event_sequence()
    store = SqliteObservabilityStore(db_path)
    try:
        created = store.create_run(_build_run())
        if created.outcome not in {CreateRunOutcome.CREATED, CreateRunOutcome.IDEMPOTENT_REPLAY}:
            raise RuntimeError(f"unexpected create_run outcome: {created.outcome}")

        recorder = StoreObservabilityRecorder(store)
        for event in events:
            outcome = recorder.record_event(event)
            if outcome.outcome is not RecordOutcome.CREATED:
                raise RuntimeError(
                    f"expected CREATED for {event.event_id}, got {outcome.outcome}",
                )

        stored_run = store.get_run(RUN_ID)
        listed_events = store.list_events(RUN_ID, limit=DEFAULT_LIST_EVENTS_LIMIT)
        event_ids = [event.event_id for event in listed_events]
        fingerprints = _fingerprints_for_events(list(listed_events))

        if stored_run.operational_status is not OperationalStatus.COMPLETED:
            raise RuntimeError(
                f"expected COMPLETED, got {stored_run.operational_status}",
            )
        if stored_run.projection_version != EXPECTED_PROJECTION_VERSION:
            raise RuntimeError(
                f"expected projection_version {EXPECTED_PROJECTION_VERSION}, "
                f"got {stored_run.projection_version}",
            )
        if stored_run.started_at != T3:
            raise RuntimeError(f"started_at mismatch: {stored_run.started_at!r} != {T3!r}")
        if stored_run.completed_at != T6:
            raise RuntimeError(f"completed_at mismatch: {stored_run.completed_at!r} != {T6!r}")
        if len(listed_events) != EXPECTED_EVENT_COUNT:
            raise RuntimeError(f"expected {EXPECTED_EVENT_COUNT} events, got {len(listed_events)}")
        expected_ids = [event.event_id for event in events]
        if event_ids != expected_ids:
            raise RuntimeError(f"event order mismatch: {event_ids} != {expected_ids}")

        handshake = {
            "phase": "process-a",
            "pid": os.getpid(),
            "run_id": RUN_ID,
            "operational_status": stored_run.operational_status.value,
            "projection_version": stored_run.projection_version,
            "started_at": _iso(stored_run.started_at),
            "completed_at": _iso(stored_run.completed_at),
            "interrupt_id": stored_run.interrupt_id,
            "handoff_id": stored_run.handoff_id,
            "event_ids": event_ids,
            "fingerprints": fingerprints,
        }
        _write_json(handshake_path, handshake)
        _write_json(
            result_path,
            {
                "phase": "process-a",
                "pid": os.getpid(),
                "verified": True,
                "event_count": len(listed_events),
            },
        )
        return 0
    finally:
        store.close()


def role_process_b(db_path: Path, handshake_path: Path, result_path: Path) -> int:
    handshake = _read_json(handshake_path)
    run_id = str(handshake["run_id"])
    store = SqliteObservabilityStore(db_path)
    try:
        recovered_run = store.get_run(run_id)
        listed_events = store.list_events(run_id, limit=DEFAULT_LIST_EVENTS_LIMIT)
        event_ids = [event.event_id for event in listed_events]
        fingerprints = _fingerprints_for_events(list(listed_events))

        if recovered_run.run_id != handshake["run_id"]:
            raise RuntimeError("run_id mismatch")
        if recovered_run.operational_status.value != handshake["operational_status"]:
            raise RuntimeError("operational_status mismatch")
        if recovered_run.projection_version != handshake["projection_version"]:
            raise RuntimeError("projection_version mismatch")
        if _iso(recovered_run.started_at) != handshake["started_at"]:
            raise RuntimeError("started_at mismatch")
        if _iso(recovered_run.completed_at) != handshake["completed_at"]:
            raise RuntimeError("completed_at mismatch")
        if handshake.get("interrupt_id") is not None:
            if recovered_run.interrupt_id != handshake["interrupt_id"]:
                raise RuntimeError("interrupt_id mismatch")
        if handshake.get("handoff_id") is not None:
            if recovered_run.handoff_id != handshake["handoff_id"]:
                raise RuntimeError("handoff_id mismatch")
        if event_ids != handshake["event_ids"]:
            raise RuntimeError("event_ids order mismatch")
        if fingerprints != handshake["fingerprints"]:
            raise RuntimeError("fingerprints mismatch")

        replay_event = _first_event_for_replay()
        replay_result = StoreObservabilityRecorder(store).record_event(replay_event)
        if replay_result.outcome is not RecordOutcome.IDEMPOTENT_REPLAY:
            raise RuntimeError(f"expected IDEMPOTENT_REPLAY, got {replay_result.outcome}")

        after_replay_run = store.get_run(run_id)
        after_replay_events = store.list_events(run_id, limit=DEFAULT_LIST_EVENTS_LIMIT)
        if after_replay_run.projection_version != handshake["projection_version"]:
            raise RuntimeError("projection_version changed after replay")
        if after_replay_run.operational_status.value != handshake["operational_status"]:
            raise RuntimeError("operational_status changed after replay")
        if len(after_replay_events) != len(handshake["event_ids"]):
            raise RuntimeError("event count changed after replay")
        if [event.event_id for event in after_replay_events] != handshake["event_ids"]:
            raise RuntimeError("event order changed after replay")

        _write_json(
            result_path,
            {
                "phase": "process-b",
                "pid": os.getpid(),
                "run_id": run_id,
                "operational_status": after_replay_run.operational_status.value,
                "projection_version": after_replay_run.projection_version,
                "event_count": len(after_replay_events),
                "replay_outcome": replay_result.outcome.value,
                "verified": True,
            },
        )
        return 0
    finally:
        store.close()


def _spawn(role: str, db_path: Path, handshake_path: Path, result_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(TEST_FILE),
            "--role",
            role,
            "--db",
            str(db_path),
            "--handshake",
            str(handshake_path),
            "--result",
            str(result_path),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        shell=False,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
        check=False,
    )


def _assert_proc(proc: subprocess.CompletedProcess[str], label: str) -> None:
    if proc.returncode != 0:
        raise AssertionError(
            f"{label} exited {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}",
        )


def test_process_a_writes_process_b_recovers_same_sqlite_file(tmp_path: Path) -> None:
    db_path = tmp_path / "observability.sqlite"
    handshake_path = tmp_path / "handshake.json"
    result_path = tmp_path / "result.json"

    proc_a = _spawn("process-a", db_path, handshake_path, result_path)
    _assert_proc(proc_a, "process-a")
    assert handshake_path.is_file(), "handshake.json missing after process-a"

    handshake = _read_json(handshake_path)
    proc_b = _spawn("process-b", db_path, handshake_path, result_path)
    _assert_proc(proc_b, "process-b")
    assert result_path.is_file(), "result.json missing after process-b"

    result = _read_json(result_path)
    assert handshake["pid"] != result["pid"], "process PIDs must differ"
    assert result["verified"] is True
    assert result["operational_status"] == OperationalStatus.COMPLETED.value
    assert result["projection_version"] == EXPECTED_PROJECTION_VERSION
    assert result["event_count"] == EXPECTED_EVENT_COUNT
    assert result["replay_outcome"] == RecordOutcome.IDEMPOTENT_REPLAY.value

    parent_store = SqliteObservabilityStore(db_path)
    try:
        parent_run = parent_store.get_run(RUN_ID)
        parent_events = parent_store.list_events(RUN_ID, limit=DEFAULT_LIST_EVENTS_LIMIT)
        assert parent_run.operational_status == OperationalStatus.COMPLETED
        assert parent_run.projection_version == EXPECTED_PROJECTION_VERSION
        assert len(parent_events) == EXPECTED_EVENT_COUNT
        assert [event.event_id for event in parent_events] == handshake["event_ids"]
    finally:
        parent_store.close()


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Increment 10.5 observability process durability probe")
    parser.add_argument("--role", required=True, choices=("process-a", "process-b"))
    parser.add_argument("--db", required=True)
    parser.add_argument("--handshake", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args(argv)
    db_path = Path(args.db)
    handshake_path = Path(args.handshake)
    result_path = Path(args.result)
    if args.role == "process-a":
        return role_process_a(db_path, handshake_path, result_path)
    return role_process_b(db_path, handshake_path, result_path)


if __name__ == "__main__":
    if any(arg == "--role" for arg in sys.argv[1:]):
        raise SystemExit(_main())
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q", str(TEST_FILE)]))
