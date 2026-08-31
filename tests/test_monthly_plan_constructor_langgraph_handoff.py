"""
Increment 9.3 — LangGraph persist_handoff orchestration.

In-memory Fake store only. No SQL, Supabase, Postgres, Streamlit, or product writes.
"""

from __future__ import annotations

import inspect
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import patch

from agents.monthly_plan_constructor.candidate_package import LABOR_UNRESOLVED, LABOR_VALIDATED
from agents.monthly_plan_constructor.exception_engine import (
    CODE_AMBIGUOUS_SCOPE,
    CODE_READ_FAILED,
)
from agents.monthly_plan_constructor.handoff_contracts import (
    DEFAULT_SECURITY_POLICY_VERSION,
    ConstructorHandoff,
)
from agents.monthly_plan_constructor.handoff_store import (
    CODE_HANDOFF_IMMUTABILITY_CONFLICT,
    CODE_HANDOFF_STORE_CONTRACT_BLOCKER,
    ConstructorHandoffStoreError,
    HandoffStorePutResult,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_OBSERVED_PRODUCTIVITY,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    LaborNormEvidence,
    SOURCE_PROJECT_HISTORY,
)
from agents.monthly_plan_constructor.langgraph_runtime import (
    NODE_PERSIST_HANDOFF,
    ConstructorGraphState,
    build_constructor_langgraph,
    run_constructor_langgraph,
)
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_FAILED,
    STATUS_READY_FOR_HANDOFF,
    STATUS_WAITING_FOR_HUMAN,
    CandidateAssemblyResult,
    ConstructorLifecycleState,
    create_lifecycle_state,
)
from agents.monthly_plan_constructor.mission_scope import ConstructorMissionScope
from agents.monthly_plan_constructor.secure_read_tools import (
    ConstructorRealityRead,
    SecureReadError,
)
from security.agent_execution_context import (
    AgentExecutionContext,
    issue_read_only_agent_context,
)

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"
MISSION_ID = "mission-increment-9-3"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
FIXED_AT = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
RUNTIME_SOURCE = Path("agents/monthly_plan_constructor/langgraph_runtime.py")


def _context(run_id: str = "run-increment-9-3") -> AgentExecutionContext:
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
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows if rows is not None else [_raw()]
        self.calls = 0

    def __call__(
        self,
        context: AgentExecutionContext,
        mission: ConstructorMissionScope,
    ) -> list[dict[str, object]]:
        self.calls += 1
        return list(self.rows)


class StubAssembler:
    def __init__(
        self,
        candidates: list[dict[str, object]] | None = None,
        *,
        scanned_count: int | None = None,
    ) -> None:
        self.candidates = candidates if candidates is not None else [_candidate_dict()]
        self.scanned_count = (
            scanned_count if scanned_count is not None else max(1, len(self.candidates))
        )

    def __call__(
        self,
        reality_read: ConstructorRealityRead,
        scope: ConstructorMissionScope,
    ) -> CandidateAssemblyResult:
        return CandidateAssemblyResult(
            candidates=tuple(self.candidates),
            scanned_count=self.scanned_count,
        )


def _candidate_dict(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
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
    }
    base.update(overrides)
    return base


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


class InMemoryHandoffStore:
    """Test-only atomic put_if_absent. Not a product persistence backend."""

    def __init__(self) -> None:
        self._records: dict[str, ConstructorHandoff] = {}
        self.put_calls = 0

    def get(self, handoff_id: str) -> Optional[ConstructorHandoff]:
        return self._records.get(handoff_id)

    def put_if_absent(self, handoff: ConstructorHandoff) -> HandoffStorePutResult:
        self.put_calls += 1
        existing = self._records.get(handoff.handoff_id)
        if existing is None:
            self._records[handoff.handoff_id] = handoff
            return HandoffStorePutResult(created=True, stored_handoff=handoff)
        return HandoffStorePutResult(created=False, stored_handoff=existing)

    def artifacts(self) -> list[ConstructorHandoff]:
        return list(self._records.values())

    def __len__(self) -> int:
        return len(self._records)


class ReplaySameStore:
    """put_if_absent always reports an existing identical artifact."""

    def __init__(self) -> None:
        self.put_calls = 0
        self.last: Optional[ConstructorHandoff] = None

    def get(self, handoff_id: str) -> Optional[ConstructorHandoff]:
        return self.last if self.last is not None and self.last.handoff_id == handoff_id else None

    def put_if_absent(self, handoff: ConstructorHandoff) -> HandoffStorePutResult:
        self.put_calls += 1
        self.last = handoff
        return HandoffStorePutResult(created=False, stored_handoff=handoff)


class ConflictStore:
    """put_if_absent returns same id with a different payload."""

    def __init__(self) -> None:
        self.put_calls = 0

    def get(self, handoff_id: str) -> Optional[ConstructorHandoff]:
        return None

    def put_if_absent(self, handoff: ConstructorHandoff) -> HandoffStorePutResult:
        self.put_calls += 1
        mutated = replace(handoff, created_at="2099-01-01T00:00:00Z")
        return HandoffStorePutResult(created=False, stored_handoff=mutated)


class BoomStore:
    def get(self, handoff_id: str) -> Optional[ConstructorHandoff]:
        return None

    def put_if_absent(self, handoff: ConstructorHandoff) -> HandoffStorePutResult:
        raise RuntimeError("store exploded")


class FakeHitlStore:
    def __init__(self) -> None:
        self.open_calls = 0
        self.answer_calls = 0
        self.open_ids: list[str] = []

    def upsert_open_request(self, request) -> None:
        self.open_calls += 1
        if request.interrupt_id not in self.open_ids:
            self.open_ids.append(request.interrupt_id)

    def record_answer(self, *, interrupt_id: str, command) -> None:
        self.answer_calls += 1


def _persist_handoff_source() -> str:
    source = RUNTIME_SOURCE.read_text(encoding="utf-8")
    body = source.split("def persist_handoff", 1)[1].split("\n    def route", 1)[0]
    return body


def _run(
    *,
    handoff_store: Optional[object] = None,
    assembler: StubAssembler | None = None,
    reader: RecordingReader | None = None,
    evidence=(_history(),),
    facility_scope: object = None,
    run_id: str = "run-increment-9-3",
    **kwargs,
) -> ConstructorLifecycleState:
    return run_constructor_langgraph(
        context=_context(run_id=run_id),
        project_code=PROJECT,
        month_key=MONTH,
        facility_scope=facility_scope,  # type: ignore[arg-type]
        assemble_candidates=assembler or StubAssembler(),
        labor_evidence=evidence,
        scope_reader=reader or RecordingReader(),
        mission_id=MISSION_ID,
        run_id=run_id,
        now=FIXED_AT,
        handoff_store=handoff_store,  # type: ignore[arg-type]
        **kwargs,
    )


class TestNoStoreBackwardCompat(unittest.TestCase):
    def test_ready_without_store_does_not_persist(self) -> None:
        from agents.monthly_plan_constructor import langgraph_runtime as lg

        with patch.object(
            lg, "persist_constructor_handoff", wraps=lg.persist_constructor_handoff
        ) as spy:
            state = _run(handoff_store=None)
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        self.assertEqual(spy.call_count, 0)
        self.assertIsInstance(state, ConstructorLifecycleState)
        self.assertNotIsInstance(state, tuple)

    def test_default_graph_has_no_persist_node(self) -> None:
        app = build_constructor_langgraph(
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            scope_reader=RecordingReader(),
            now=FIXED_AT,
        )
        nodes = set(app.get_graph().nodes)
        self.assertNotIn(NODE_PERSIST_HANDOFF, nodes)


class TestHappyPathPersist(unittest.TestCase):
    def test_persist_called_once_and_lifecycle_stays_ready(self) -> None:
        from agents.monthly_plan_constructor import langgraph_runtime as lg

        store = InMemoryHandoffStore()
        with patch.object(
            lg, "persist_constructor_handoff", wraps=lg.persist_constructor_handoff
        ) as spy:
            state = _run(handoff_store=store)
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(len(store), 1)
        self.assertEqual(store.put_calls, 1)
        artifact = store.artifacts()[0]
        self.assertEqual(artifact.source_run_id, state.run_id)
        self.assertEqual(artifact.mission_id, state.mission_id)
        self.assertEqual(artifact.project_code, state.scope.project_code)  # type: ignore[union-attr]
        self.assertEqual(artifact.month_key, state.scope.month_key)  # type: ignore[union-attr]
        self.assertEqual(artifact.scope, state.scope)
        self.assertEqual(
            artifact.candidate_package_reference,
            state.package.as_reference(),  # type: ignore[union-attr]
        )
        self.assertEqual(artifact.snapshot_id, state.reality_read.snapshot_id)  # type: ignore[union-attr]
        self.assertEqual(artifact.snapshot_id, state.package.provenance.snapshot_id)  # type: ignore[union-attr]

    def test_empty_package_ready_persists(self) -> None:
        store = InMemoryHandoffStore()
        state = _run(
            handoff_store=store,
            reader=RecordingReader(rows=[]),
            assembler=StubAssembler(candidates=[], scanned_count=0),
            evidence=(),
        )
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        self.assertEqual(state.package.candidate_count, 0)  # type: ignore[union-attr]
        self.assertEqual(len(store), 1)
        artifact = store.artifacts()[0]
        self.assertEqual(artifact.candidate_count, 0)
        self.assertEqual(artifact.candidate_ids, ())
        self.assertEqual(artifact.snapshot_id, state.reality_read.snapshot_id)  # type: ignore[union-attr]

    def test_graph_state_schema_unchanged(self) -> None:
        from typing import get_type_hints

        hints = get_type_hints(ConstructorGraphState)
        self.assertEqual(set(hints.keys()), {"lifecycle"})
        self.assertIs(hints["lifecycle"], ConstructorLifecycleState)
        for banned in ("handoff", "persist_result", "handoff_id", "payload_digest"):
            self.assertNotIn(banned, ConstructorGraphState.__annotations__)


class TestWaitAndFailedDoNotPersist(unittest.TestCase):
    def test_waiting_for_human_does_not_persist(self) -> None:
        store = InMemoryHandoffStore()
        state = _run(
            handoff_store=store,
            facility_scope=["ALL", FACILITY_TARGET],
            evidence=(),
        )
        self.assertEqual(state.status, STATUS_WAITING_FOR_HUMAN)
        self.assertEqual(state.error_code, CODE_AMBIGUOUS_SCOPE)
        self.assertEqual(len(store), 0)
        self.assertEqual(store.put_calls, 0)

    def test_failed_read_does_not_persist(self) -> None:
        store = InMemoryHandoffStore()

        def raising_reader(context, mission):
            raise SecureReadError(CODE_READ_FAILED, "read failed")

        state = _run(
            handoff_store=store,
            reader=raising_reader,  # type: ignore[arg-type]
        )
        self.assertEqual(state.status, STATUS_FAILED)
        self.assertEqual(state.error_code, CODE_READ_FAILED)
        self.assertEqual(len(store), 0)
        self.assertEqual(store.put_calls, 0)


class TestStoreOutcomes(unittest.TestCase):
    def test_idempotent_replay_completes_ready(self) -> None:
        store = ReplaySameStore()
        state = _run(handoff_store=store)
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        self.assertEqual(store.put_calls, 1)
        self.assertIsInstance(store.last, ConstructorHandoff)
        self.assertEqual(store.last.source_run_id, state.run_id)  # type: ignore[union-attr]

    def test_immutability_conflict_propagates(self) -> None:
        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            _run(handoff_store=ConflictStore())
        self.assertEqual(caught.exception.code, CODE_HANDOFF_IMMUTABILITY_CONFLICT)

    def test_malformed_store_response_fail_closed(self) -> None:
        class BadStore:
            def get(self, handoff_id: str) -> None:
                return None

            def put_if_absent(self, handoff: ConstructorHandoff):
                return {"created": True, "stored_handoff": handoff}

        with self.assertRaises(ConstructorHandoffStoreError) as caught:
            _run(handoff_store=BadStore())
        self.assertEqual(caught.exception.code, CODE_HANDOFF_STORE_CONTRACT_BLOCKER)

    def test_persistence_exception_not_swallowed(self) -> None:
        with self.assertRaises(RuntimeError) as caught:
            _run(handoff_store=BoomStore())
        self.assertEqual(str(caught.exception), "store exploded")


class TestBoundaries(unittest.TestCase):
    def test_product_source_boundaries(self) -> None:
        source = RUNTIME_SOURCE.read_text(encoding="utf-8")
        lowered = source.lower()
        self.assertIn("NODE_PERSIST_HANDOFF", source)
        self.assertIn("persist_constructor_handoff", source)
        self.assertIn("build_constructor_handoff", source)
        self.assertIn("created_at=lifecycle.updated_at", source)
        self.assertIn("graph.add_edge(NODE_PERSIST_HANDOFF, END)", source)
        self.assertNotIn("add_conditional_edges(NODE_PERSIST_HANDOFF", source)
        persist_body = _persist_handoff_source()
        self.assertNotIn("datetime.now", persist_body)
        self.assertNotIn("utcnow", persist_body)
        self.assertNotIn("store.get", persist_body)
        for needle in (
            "supabase",
            "psycopg",
            "sqlalchemy",
            "postgresql",
            "streamlit",
            "openai",
            "requests",
            "httpx",
            "subprocess",
            "os.environ",
            "os.system",
        ):
            self.assertNotIn(needle, lowered)
        self.assertNotIn("Admission", source)
        self.assertNotIn("SENT_TO_ADMISSION", source)
        self.assertNotIn("STATUS_HANDOFF_READY", source)
        self.assertNotIn("chat", lowered)
        lifecycle_source = Path("agents/monthly_plan_constructor/lifecycle.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("HANDOFF_READY", lifecycle_source.split("STATUS_READY_FOR_HANDOFF", 1)[0])
        self.assertNotIn('STATUS_HANDOFF_READY', lifecycle_source)

    def test_run_api_unchanged(self) -> None:
        from typing import get_type_hints

        signature = inspect.signature(run_constructor_langgraph)
        self.assertIn("handoff_store", signature.parameters)
        hints = get_type_hints(run_constructor_langgraph)
        self.assertIs(hints["return"], ConstructorLifecycleState)
        store = InMemoryHandoffStore()
        result = _run(handoff_store=store)
        self.assertIsInstance(result, ConstructorLifecycleState)
        self.assertNotIsInstance(result, tuple)

    def test_checkpoint_values_are_lifecycle_only(self) -> None:
        from langgraph.checkpoint.memory import InMemorySaver

        from agents.monthly_plan_constructor.durable_checkpoint import (
            build_constructor_jsonplus_serializer,
        )

        store = InMemoryHandoffStore()
        run_id = "run-increment-9-3-ckpt"
        ctx = _context(run_id=run_id)
        app = build_constructor_langgraph(
            context=ctx,
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            labor_evidence=(_history(),),
            scope_reader=RecordingReader(),
            now=FIXED_AT,
            checkpointer=InMemorySaver(serde=build_constructor_jsonplus_serializer()),
            handoff_store=store,
        )
        initial = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id=run_id,
            authorization_id=ctx.authorization_id,
            created_at=FIXED_AT,
        )
        config = {"configurable": {"thread_id": run_id}}
        out = app.invoke({"lifecycle": initial}, config)
        self.assertEqual(out["lifecycle"].status, STATUS_READY_FOR_HANDOFF)
        self.assertEqual(len(store), 1)
        snap = app.get_state(config)
        self.assertIn("lifecycle", snap.values)
        for key in snap.values:
            self.assertNotIn("handoff", str(key).lower())
        self.assertNotIn("handoff", snap.values)
        self.assertNotIn("persist_result", snap.values)
        self.assertIsInstance(snap.values["lifecycle"], ConstructorLifecycleState)
        self.assertEqual(snap.values["lifecycle"].status, STATUS_READY_FOR_HANDOFF)


class TestHitlFreshSnapshotHandoff(unittest.TestCase):
    def test_wait_resume_fresh_reality_then_persist(self) -> None:
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.types import Command

        from agents.monthly_plan_constructor.durable_checkpoint import (
            build_constructor_jsonplus_serializer,
        )
        from agents.monthly_plan_constructor.hitl_contracts import (
            DECISION_CLARIFY_SCOPE,
            build_resume_command,
        )
        from agents.monthly_plan_constructor.hitl_resume import (
            build_decision_request_from_lifecycle,
        )

        run_id = "run-increment-9-3-hitl"
        ctx = _context(run_id=run_id)
        hitl_store = FakeHitlStore()
        handoff_store = InMemoryHandoffStore()
        reader = RecordingReader()
        app = build_constructor_langgraph(
            context=ctx,
            project_code=PROJECT,
            month_key=MONTH,
            facility_scope=["ALL", FACILITY_TARGET],
            assemble_candidates=StubAssembler(),
            labor_evidence=(_history(),),
            scope_reader=reader,
            now=FIXED_AT,
            checkpointer=InMemorySaver(serde=build_constructor_jsonplus_serializer()),
            hitl_store=hitl_store,
            handoff_store=handoff_store,
        )
        initial = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id=run_id,
            authorization_id=ctx.authorization_id,
            created_at=FIXED_AT,
        )
        config = {"configurable": {"thread_id": run_id}}
        out1 = app.invoke({"lifecycle": initial}, config)
        self.assertEqual(out1["lifecycle"].status, STATUS_WAITING_FOR_HUMAN)
        self.assertEqual(len(handoff_store), 0)
        reads_at_wait = reader.calls

        req = build_decision_request_from_lifecycle(out1["lifecycle"])
        snap = app.get_state(config)
        checkpoint_id = snap.config["configurable"]["checkpoint_id"]
        cmd = build_resume_command(
            decision_id="dec-9-3-hitl",
            interrupt_id=req.interrupt_id,
            run_id=run_id,
            mission_id=MISSION_ID,
            decision=DECISION_CLARIFY_SCOPE,
            actor_id="human-1",
            parameters={"facility_scope": [FACILITY_TARGET]},
            expected_checkpoint_id=checkpoint_id,
            submitted_at=FIXED_AT,
        )
        out2 = app.invoke(Command(resume=cmd), config)
        lifecycle = out2["lifecycle"]
        self.assertEqual(lifecycle.status, STATUS_READY_FOR_HANDOFF)
        self.assertGreater(reader.calls, reads_at_wait)
        self.assertEqual(len(handoff_store), 1)
        artifact = handoff_store.artifacts()[0]
        self.assertEqual(artifact.snapshot_id, lifecycle.reality_read.snapshot_id)
        self.assertEqual(artifact.snapshot_id, lifecycle.package.provenance.snapshot_id)
        self.assertEqual(artifact.source_run_id, lifecycle.run_id)
        self.assertEqual(hitl_store.answer_calls, 1)
        held = app.get_state(config)
        self.assertNotIn("handoff", held.values)
        self.assertEqual(held.values["lifecycle"].status, STATUS_READY_FOR_HANDOFF)


if __name__ == "__main__":
    unittest.main()
