"""
Increment 9.2 — ConstructorHandoff store protocol and persist tests.

In-memory Fake store only. No SQL, Supabase, Postgres, LangGraph, or product writes.
"""

from __future__ import annotations

import hashlib
import inspect
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agents.monthly_plan_constructor.candidate_package import LABOR_UNRESOLVED, LABOR_VALIDATED
from agents.monthly_plan_constructor.handoff_contracts import (
    DEFAULT_SECURITY_POLICY_VERSION,
    STATUS_HANDOFF_READY,
    ConstructorHandoff,
    build_constructor_handoff,
)
from agents.monthly_plan_constructor.handoff_store import (
    CODE_HANDOFF_IMMUTABILITY_CONFLICT,
    CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
    STATUS_CREATED,
    STATUS_IDEMPOTENT_REPLAY,
    ConstructorHandoffStoreError,
    HandoffStorePutResult,
    compute_constructor_handoff_payload_digest,
    persist_constructor_handoff,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_OBSERVED_PRODUCTIVITY,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    LaborNormEvidence,
    SOURCE_PROJECT_HISTORY,
)
from agents.monthly_plan_constructor.lifecycle import (
    CandidateAssemblyResult,
    run_constructor_lifecycle,
)
from agents.monthly_plan_constructor.mission_scope import ConstructorMissionScope
from agents.monthly_plan_constructor.secure_read_tools import ConstructorRealityRead
from security.agent_execution_context import (
    AgentExecutionContext,
    issue_read_only_agent_context,
)

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"
MISSION_ID = "mission-increment-9-store"
RUN_ID = "run-increment-9-store"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
FIXED_AT = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
LATER_AT = datetime(2026, 8, 31, 13, 0, 0, tzinfo=timezone.utc)


def _context(run_id: str = RUN_ID) -> AgentExecutionContext:
    return issue_read_only_agent_context(
        agent_code="MONTHLY_PLAN_CONSTRUCTOR",
        project_code=PROJECT,
        run_id=run_id,
    )


def _raw() -> dict[str, object]:
    return {
        "project_code": PROJECT,
        "month_key": MONTH,
        "facility": FACILITY_TARGET,
        "facility_building": FACILITY_TARGET,
        "discipline": DISCIPLINE_VENT,
        "construction_discipline": DISCIPLINE_VENT,
        "system": "SYS-1",
        "system_label": "SYS-1",
        "iwp": "IWP-1",
        "iwp_id": "IWP-1",
        "boq_code": "BOQ-001",
        "boq_name": "Воздуховод",
        "unit_of_measure": "м2",
    }


class RecordingReader:
    def __call__(
        self,
        context: AgentExecutionContext,
        mission: ConstructorMissionScope,
    ) -> list[dict[str, object]]:
        return [_raw()]


class StubAssembler:
    def __call__(
        self,
        reality_read: ConstructorRealityRead,
        scope: ConstructorMissionScope,
    ) -> CandidateAssemblyResult:
        return CandidateAssemblyResult(
            candidates=(
                {
                    "candidate_id": CANDIDATE_ID,
                    "project_code": PROJECT,
                    "month_key": MONTH,
                    "facility": FACILITY_TARGET,
                    "discipline": DISCIPLINE_VENT,
                    "system": "SYS-1",
                    "iwp": "IWP-1",
                    "queue": "Q1",
                    "boq_code": "BOQ-001",
                    "boq_name": "Воздуховод",
                    "unit": "м2",
                    "remaining_qty": 10.0,
                    "already_planned_qty": 0.0,
                    "available_to_add_qty": 10.0,
                    "availability_status": "Доступно",
                    "labor_norm_status": LABOR_UNRESOLVED,
                },
            ),
            scanned_count=1,
        )


def _history() -> LaborNormEvidence:
    return LaborNormEvidence(
        evidence_id="ev-project",
        candidate_id=CANDIDATE_ID,
        source_type=SOURCE_PROJECT_HISTORY,
        labor_hours_per_unit=1.42,
        unit="м2",
        source_reference="project-history-run",
        source_version="2026-08",
        planning_use_status=LABOR_VALIDATED,
        basis=BASIS_OBSERVED_PRODUCTIVITY,
        hours_quality=HOURS_VALIDATED_PRODUCTIVE_DIRECT,
        executed_quantity_validated=True,
    )


def _ready_state(*, run_id: str = RUN_ID):
    return run_constructor_lifecycle(
        context=_context(run_id),
        project_code=PROJECT,
        month_key=MONTH,
        assemble_candidates=StubAssembler(),
        labor_evidence=(_history(),),
        scope_reader=RecordingReader(),
        mission_id=MISSION_ID,
        run_id=run_id,
        now=FIXED_AT,
    )


def _handoff_from_state(state, *, created_at: datetime = FIXED_AT) -> ConstructorHandoff:
    return build_constructor_handoff(
        state,
        security_policy_version=DEFAULT_SECURITY_POLICY_VERSION,
        created_at=created_at,
    )


def _handoff(*, run_id: str = RUN_ID, created_at: datetime = FIXED_AT) -> ConstructorHandoff:
    return _handoff_from_state(_ready_state(run_id=run_id), created_at=created_at)


class InMemoryHandoffStore:
    """Test-only atomic put_if_absent. Not a product persistence backend."""

    def __init__(self) -> None:
        self._records: dict[str, ConstructorHandoff] = {}

    def get(self, handoff_id: str) -> Optional[ConstructorHandoff]:
        return self._records.get(handoff_id)

    def put_if_absent(self, handoff: ConstructorHandoff) -> HandoffStorePutResult:
        existing = self._records.get(handoff.handoff_id)
        if existing is None:
            self._records[handoff.handoff_id] = handoff
            return HandoffStorePutResult(created=True, stored_handoff=handoff)
        return HandoffStorePutResult(created=False, stored_handoff=existing)

    def __len__(self) -> int:
        return len(self._records)


class RaceHandoffStore:
    """get() always None; put_if_absent returns a pre-existing row (lost race)."""

    def __init__(self, existing: ConstructorHandoff) -> None:
        self.existing = existing
        self.get_calls = 0
        self.put_calls = 0

    def get(self, handoff_id: str) -> Optional[ConstructorHandoff]:
        self.get_calls += 1
        return None

    def put_if_absent(self, handoff: ConstructorHandoff) -> HandoffStorePutResult:
        self.put_calls += 1
        return HandoffStorePutResult(created=False, stored_handoff=self.existing)


class TestPersistCreatedAndReplay(unittest.TestCase):
    def test_first_persist_created(self) -> None:
        store = InMemoryHandoffStore()
        artifact = _handoff()
        result = persist_constructor_handoff(store=store, handoff=artifact)
        self.assertEqual(result.status, STATUS_CREATED)
        self.assertEqual(result.handoff_id, artifact.handoff_id)
        self.assertEqual(len(store), 1)
        self.assertEqual(store.get(artifact.handoff_id), artifact)

    def test_same_handoff_replay(self) -> None:
        store = InMemoryHandoffStore()
        artifact = _handoff()
        persist_constructor_handoff(store=store, handoff=artifact)
        result = persist_constructor_handoff(store=store, handoff=artifact)
        self.assertEqual(result.status, STATUS_IDEMPOTENT_REPLAY)
        self.assertEqual(len(store), 1)

    def test_many_replays_one_record(self) -> None:
        store = InMemoryHandoffStore()
        artifact = _handoff()
        statuses = [
            persist_constructor_handoff(store=store, handoff=artifact).status
            for _ in range(5)
        ]
        self.assertEqual(statuses[0], STATUS_CREATED)
        self.assertEqual(statuses[1:], [STATUS_IDEMPOTENT_REPLAY] * 4)
        self.assertEqual(len(store), 1)

    def test_different_handoff_id_separate_created(self) -> None:
        store = InMemoryHandoffStore()
        first = persist_constructor_handoff(store=store, handoff=_handoff(run_id="run-a"))
        second = persist_constructor_handoff(store=store, handoff=_handoff(run_id="run-b"))
        self.assertEqual(first.status, STATUS_CREATED)
        self.assertEqual(second.status, STATUS_CREATED)
        self.assertNotEqual(first.handoff_id, second.handoff_id)
        self.assertEqual(len(store), 2)


class TestImmutabilityConflict(unittest.TestCase):
    def test_same_id_different_created_at(self) -> None:
        store = InMemoryHandoffStore()
        state = _ready_state()
        first = _handoff_from_state(state, created_at=FIXED_AT)
        second = _handoff_from_state(state, created_at=LATER_AT)
        self.assertEqual(first.handoff_id, second.handoff_id)
        self.assertNotEqual(first.created_at, second.created_at)
        persist_constructor_handoff(store=store, handoff=first)
        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            persist_constructor_handoff(store=store, handoff=second)
        self.assertEqual(caught.exception.code, CODE_HANDOFF_IMMUTABILITY_CONFLICT)
        self.assertEqual(len(store), 1)
        self.assertEqual(store.get(first.handoff_id), first)

    def test_same_id_changed_provenance(self) -> None:
        store = InMemoryHandoffStore()
        first = _handoff()
        persist_constructor_handoff(store=store, handoff=first)
        mutated = replace(
            first,
            provenance=replace(
                first.provenance,
                security_policy_version="EOS-SEC-OTHER",
            ),
        )
        self.assertEqual(mutated.handoff_id, first.handoff_id)
        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            persist_constructor_handoff(store=store, handoff=mutated)
        self.assertEqual(caught.exception.code, CODE_HANDOFF_IMMUTABILITY_CONFLICT)
        self.assertEqual(store.get(first.handoff_id).provenance, first.provenance)

    def test_same_id_changed_candidate_payload(self) -> None:
        store = InMemoryHandoffStore()
        first = _handoff()
        persist_constructor_handoff(store=store, handoff=first)
        mutated = replace(first, candidate_ids=("other-candidate-id",), candidate_count=1)
        self.assertEqual(mutated.handoff_id, first.handoff_id)
        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            persist_constructor_handoff(store=store, handoff=mutated)
        self.assertEqual(caught.exception.code, CODE_HANDOFF_IMMUTABILITY_CONFLICT)
        self.assertEqual(store.get(first.handoff_id).candidate_ids, first.candidate_ids)

    def test_no_overwrite(self) -> None:
        store = InMemoryHandoffStore()
        first = _handoff()
        persist_constructor_handoff(store=store, handoff=first)
        try:
            persist_constructor_handoff(
                store=store,
                handoff=replace(first, created_at="2099-01-01T00:00:00Z"),
            )
        except ConstructorHandoffStoreError:
            pass
        self.assertEqual(store.get(first.handoff_id).created_at, first.created_at)


class TestPayloadDigest(unittest.TestCase):
    def test_digest_deterministic_and_stable(self) -> None:
        artifact = _handoff()
        a = compute_constructor_handoff_payload_digest(artifact)
        b = compute_constructor_handoff_payload_digest(artifact)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)
        self.assertRegex(a, r"^[0-9a-f]{64}$")

    def test_different_payload_different_digest(self) -> None:
        state = _ready_state()
        a = compute_constructor_handoff_payload_digest(
            _handoff_from_state(state, created_at=FIXED_AT)
        )
        b = compute_constructor_handoff_payload_digest(
            _handoff_from_state(state, created_at=LATER_AT)
        )
        self.assertNotEqual(a, b)

    def test_digest_is_sha256_not_python_hash(self) -> None:
        source = Path("agents/monthly_plan_constructor/handoff_store.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("hashlib.sha256", source)
        self.assertNotIn("pickle", source)
        self.assertNotIn("hash(handoff", source)
        artifact = _handoff()
        digest = compute_constructor_handoff_payload_digest(artifact)
        self.assertNotEqual(digest, str(hash(artifact)))


class TestRaceAndMalformed(unittest.TestCase):
    def test_race_same_payload_replay(self) -> None:
        existing = _handoff()
        store = RaceHandoffStore(existing)
        result = persist_constructor_handoff(store=store, handoff=existing)
        self.assertEqual(store.get_calls, 1)
        self.assertEqual(store.put_calls, 1)
        self.assertEqual(result.status, STATUS_IDEMPOTENT_REPLAY)

    def test_race_different_payload_conflict(self) -> None:
        state = _ready_state()
        existing = _handoff_from_state(state, created_at=FIXED_AT)
        incoming = _handoff_from_state(state, created_at=LATER_AT)
        self.assertEqual(existing.handoff_id, incoming.handoff_id)
        store = RaceHandoffStore(existing)
        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            persist_constructor_handoff(store=store, handoff=incoming)
        self.assertEqual(caught.exception.code, CODE_HANDOFF_IMMUTABILITY_CONFLICT)
        self.assertGreaterEqual(store.put_calls, 1)

    def test_malformed_store_response(self) -> None:
        artifact = _handoff()

        class BadStore:
            def get(self, handoff_id: str) -> None:
                return None

            def put_if_absent(self, handoff: ConstructorHandoff):
                return {"created": True, "stored_handoff": handoff}

        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            persist_constructor_handoff(store=BadStore(), handoff=artifact)
        self.assertEqual(caught.exception.code, CODE_HANDOFF_STORE_CONTRACT_BLOCKER)

    def test_store_returns_wrong_handoff_id(self) -> None:
        artifact = _handoff()
        other = replace(artifact, handoff_id="eos-hof-other")

        class WrongIdStore:
            def get(self, handoff_id: str) -> None:
                return None

            def put_if_absent(self, handoff: ConstructorHandoff) -> HandoffStorePutResult:
                return HandoffStorePutResult(created=True, stored_handoff=other)

        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            persist_constructor_handoff(store=WrongIdStore(), handoff=artifact)
        self.assertEqual(caught.exception.code, CODE_HANDOFF_STORE_CONTRACT_BLOCKER)

    def test_status_not_handoff_ready(self) -> None:
        artifact = replace(_handoff(), status="READY_FOR_HANDOFF")
        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            persist_constructor_handoff(store=InMemoryHandoffStore(), handoff=artifact)
        self.assertEqual(caught.exception.code, CODE_HANDOFF_STORE_CONTRACT_BLOCKER)

    def test_none_and_invalid_handoff(self) -> None:
        store = InMemoryHandoffStore()
        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            persist_constructor_handoff(store=store, handoff=None)  # type: ignore[arg-type]
        self.assertEqual(caught.exception.code, CODE_HANDOFF_STORE_CONTRACT_BLOCKER)
        with self.assertRaises(ConstructorHandoffStoreError):
            persist_constructor_handoff(store=store, handoff=object())  # type: ignore[arg-type]


class TestBoundaries(unittest.TestCase):
    def test_product_imports_and_surface(self) -> None:
        source = Path("agents/monthly_plan_constructor/handoff_store.py").read_text(
            encoding="utf-8"
        )
        lowered = source.lower()
        for needle in (
            "supabase",
            "psycopg",
            "sqlalchemy",
            "pandas",
            "streamlit",
            "langgraph",
            "requests",
            "httpx",
            "subprocess",
            "os.system",
            "pickle",
            "openai",
        ):
            self.assertNotIn(needle, lowered)
        self.assertNotIn("SENT_TO_ADMISSION", source)
        self.assertNotIn("chat", lowered)
        signature = inspect.signature(persist_constructor_handoff)
        self.assertEqual(set(signature.parameters), {"store", "handoff"})
        result = persist_constructor_handoff(store=InMemoryHandoffStore(), handoff=_handoff())
        self.assertEqual(result.status, STATUS_CREATED)
        self.assertNotIn("password", result.payload_digest)
        self.assertNotIn("service_role", result.payload_digest)


if __name__ == "__main__":
    unittest.main()
