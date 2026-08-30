"""
Increment 7 — Constructor LangGraph Runtime.

Pure domain tests. No Streamlit, Supabase writes, LLM, durable checkpointer, or handoff.
"""

from __future__ import annotations

import importlib
import unittest
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Sequence
from unittest.mock import patch

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_PROVISIONAL,
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
)
from agents.monthly_plan_constructor.exception_engine import (
    CODE_AMBIGUOUS_SCOPE,
    CODE_DATA_CONTRACT_BLOCKER,
    CODE_LABOR_NORM_UNRESOLVED,
    CODE_READ_FAILED,
    CODE_SECURITY_DENIED,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_NORMATIVE_BENCHMARK,
    BASIS_OBSERVED_PRODUCTIVITY,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    LaborNormEvidence,
    SOURCE_OFFICIAL_NORMATIVE,
    SOURCE_PROJECT_HISTORY,
)
from agents.monthly_plan_constructor.langgraph_runtime import (
    ConstructorGraphState,
    build_constructor_langgraph,
    run_constructor_langgraph,
)
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_FAILED,
    STATUS_MISSION_BOUND,
    STATUS_PACKAGE_BUILT,
    STATUS_READY_FOR_HANDOFF,
    STATUS_REALITY_LOADED,
    STATUS_WAITING_FOR_HUMAN,
    CandidateAssemblyResult,
    ConstructorLifecycleState,
    LifecycleError,
    create_lifecycle_state,
    is_ready_for_handoff,
    run_constructor_lifecycle,
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
MISSION_ID = "mission-increment-7"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
FIXED_AT = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)
FIXED_RUN_ID = "run-increment-7-parity"


def _context(project_code: str = PROJECT) -> AgentExecutionContext:
    return issue_read_only_agent_context(
        agent_code="MONTHLY_PLAN_CONSTRUCTOR",
        project_code=project_code,
    )


def _raw(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
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
    base.update(overrides)
    return base


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
        self.calls = 0

    def __call__(
        self,
        reality_read: ConstructorRealityRead,
        scope: ConstructorMissionScope,
    ) -> CandidateAssemblyResult:
        self.calls += 1
        return CandidateAssemblyResult(
            candidates=tuple(self.candidates),
            scanned_count=self.scanned_count,
        )


def _history(**overrides: object) -> LaborNormEvidence:
    payload: dict[str, object] = {
        "evidence_id": "ev-project",
        "candidate_id": CANDIDATE_ID,
        "source_type": SOURCE_PROJECT_HISTORY,
        "labor_hours_per_unit": 1.42,
        "unit": "м2",
        "source_reference": "project-history-run",
        "source_version": "2026-08",
        "planning_use_status": LABOR_VALIDATED,
        "basis": BASIS_OBSERVED_PRODUCTIVITY,
        "hours_quality": HOURS_VALIDATED_PRODUCTIVE_DIRECT,
        "executed_quantity_validated": True,
    }
    payload.update(overrides)
    return LaborNormEvidence(**payload)  # type: ignore[arg-type]


def _normative(**overrides: object) -> LaborNormEvidence:
    payload: dict[str, object] = {
        "evidence_id": "ev-official",
        "candidate_id": CANDIDATE_ID,
        "source_type": SOURCE_OFFICIAL_NORMATIVE,
        "labor_hours_per_unit": 2.0,
        "unit": "м2",
        "source_reference": "gesn-table",
        "planning_use_status": LABOR_PROVISIONAL,
        "basis": BASIS_NORMATIVE_BENCHMARK,
    }
    payload.update(overrides)
    return LaborNormEvidence(**payload)  # type: ignore[arg-type]


def _run_pure(
    *,
    assembler: StubAssembler | None = None,
    reader: RecordingReader | None = None,
    evidence: Sequence[LaborNormEvidence] = (),
    project_code: object = PROJECT,
    month_key: object = MONTH,
    facility_scope: object = None,
    context: AgentExecutionContext | None = None,
    run_id: str = FIXED_RUN_ID,
) -> ConstructorLifecycleState:
    return run_constructor_lifecycle(
        context=context or _context(),
        project_code=project_code,
        month_key=month_key,
        facility_scope=facility_scope,  # type: ignore[arg-type]
        assemble_candidates=assembler or StubAssembler(),
        labor_evidence=evidence,
        scope_reader=reader or RecordingReader(),
        mission_id=MISSION_ID,
        run_id=run_id,
        now=FIXED_AT,
    )


def _run_graph(
    *,
    assembler: StubAssembler | None = None,
    reader: RecordingReader | None = None,
    evidence: Sequence[LaborNormEvidence] = (),
    project_code: object = PROJECT,
    month_key: object = MONTH,
    facility_scope: object = None,
    context: AgentExecutionContext | None = None,
    run_id: str = FIXED_RUN_ID,
) -> ConstructorLifecycleState:
    return run_constructor_langgraph(
        context=context or _context(),
        project_code=project_code,
        month_key=month_key,
        facility_scope=facility_scope,  # type: ignore[arg-type]
        assemble_candidates=assembler or StubAssembler(),
        labor_evidence=evidence,
        scope_reader=reader or RecordingReader(),
        mission_id=MISSION_ID,
        run_id=run_id,
        now=FIXED_AT,
    )


def _semantic_parity(
    left: ConstructorLifecycleState,
    right: ConstructorLifecycleState,
) -> None:
    assert left.status == right.status
    assert left.error_code == right.error_code
    assert left.mission_id == right.mission_id
    assert left.run_id == right.run_id
    assert left.authorization_id == right.authorization_id
    assert [t.to_status for t in left.transitions] == [
        t.to_status for t in right.transitions
    ]
    assert [t.from_status for t in left.transitions] == [
        t.from_status for t in right.transitions
    ]
    assert (left.scope is None) == (right.scope is None)
    assert (left.reality_read is None) == (right.reality_read is None)
    assert (left.package is None) == (right.package is None)
    assert (left.labor_resolutions is None) == (right.labor_resolutions is None)
    assert (left.exceptions is None) == (right.exceptions is None)
    if left.package is not None and right.package is not None:
        assert left.package.candidate_count == right.package.candidate_count
        assert [c.candidate_id for c in left.package.candidates] == [
            c.candidate_id for c in right.package.candidates
        ]
        assert [c.labor_norm_status for c in left.package.candidates] == [
            c.labor_norm_status for c in right.package.candidates
        ]
    if left.exceptions is not None and right.exceptions is not None:
        assert [e.exception_code for e in left.exceptions.exceptions] == [
            e.exception_code for e in right.exceptions.exceptions
        ]
        assert [e.route for e in left.exceptions.exceptions] == [
            e.route for e in right.exceptions.exceptions
        ]
        assert left.exceptions.handoff_allowed() == right.exceptions.handoff_allowed()


class TestLangGraphVersion(unittest.TestCase):
    def test_langgraph_version(self) -> None:
        self.assertEqual(version("langgraph"), "1.2.11")


class TestNormalPath(unittest.TestCase):
    def test_full_path_ready(self) -> None:
        state = _run_graph(evidence=[_history()])
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        self.assertTrue(is_ready_for_handoff(state))
        self.assertEqual(
            [t.to_status for t in state.transitions],
            [
                STATUS_MISSION_BOUND,
                STATUS_REALITY_LOADED,
                STATUS_PACKAGE_BUILT,
                "LABOR_RESOLVED",
                STATUS_READY_FOR_HANDOFF,
            ],
        )

    def test_stages_execute_in_order(self) -> None:
        source = Path(
            "agents/monthly_plan_constructor/langgraph_runtime.py"
        ).read_text(encoding="utf-8")
        markers = [
            "add_node(NODE_BIND_MISSION",
            "add_node(NODE_LOAD_REALITY",
            "add_node(NODE_BUILD_PACKAGE",
            "add_node(NODE_RESOLVE_LABOR",
            "add_node(NODE_EVALUATE_EXCEPTIONS",
        ]
        positions = [source.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions))

    def test_transition_sequence_valid(self) -> None:
        state = _run_graph(evidence=[_history()])
        expected_from = [
            "CREATED",
            STATUS_MISSION_BOUND,
            STATUS_REALITY_LOADED,
            STATUS_PACKAGE_BUILT,
            "LABOR_RESOLVED",
        ]
        self.assertEqual([t.from_status for t in state.transitions], expected_from)


class TestWaitPath(unittest.TestCase):
    def test_ambiguous_scope_wait(self) -> None:
        state = _run_graph(facility_scope=["ALL", "FACILITY_TARGET"])
        self.assertEqual(state.status, STATUS_WAITING_FOR_HUMAN)
        self.assertEqual(state.error_code, CODE_AMBIGUOUS_SCOPE)

    def test_wait_ends_without_resume(self) -> None:
        # Default graph (no checkpointer) still stops on WAIT without auto-resume.
        source = Path(
            "agents/monthly_plan_constructor/langgraph_runtime.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "MemorySaver(",
            "InMemorySaver(",
            "PostgresSaver(",
            "saver.setup",
        ):
            self.assertNotIn(forbidden, source)
        state = _run_graph(facility_scope=["ALL", "X"])
        self.assertEqual(state.status, STATUS_WAITING_FOR_HUMAN)


class TestFailurePath(unittest.TestCase):
    def test_secure_read_failed(self) -> None:
        def raising_reader(context, mission):
            raise SecureReadError(CODE_READ_FAILED, "read failed")

        state = _run_graph(reader=raising_reader)  # type: ignore[arg-type]
        self.assertEqual(state.status, STATUS_FAILED)
        self.assertEqual(state.error_code, CODE_READ_FAILED)

    def test_data_contract_failed(self) -> None:
        state = _run_graph(project_code="")
        self.assertEqual(state.status, STATUS_FAILED)
        self.assertEqual(state.error_code, CODE_DATA_CONTRACT_BLOCKER)

    def test_security_denied(self) -> None:
        state = _run_graph(context=_context(project_code="PRJ_OTHER"))
        self.assertEqual(state.status, STATUS_FAILED)
        self.assertEqual(state.error_code, CODE_SECURITY_DENIED)


class TestEdgeCases(unittest.TestCase):
    def test_zero_candidates_ready(self) -> None:
        state = _run_graph(
            reader=RecordingReader(rows=[]),
            assembler=StubAssembler(candidates=[], scanned_count=0),
            evidence=(),
        )
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        self.assertEqual(state.package.candidate_count, 0)  # type: ignore[union-attr]

    def test_all_labor_unresolved_ready(self) -> None:
        state = _run_graph(evidence=())
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        self.assertEqual(
            state.exceptions.exceptions[0].exception_code,  # type: ignore[union-attr]
            CODE_LABOR_NORM_UNRESOLVED,
        )


class TestArchitecture(unittest.TestCase):
    def test_output_is_lifecycle_state(self) -> None:
        state = _run_graph(evidence=[_history()])
        self.assertIsInstance(state, ConstructorLifecycleState)

    def test_graph_state_contract(self) -> None:
        from typing import get_type_hints

        hints = get_type_hints(ConstructorGraphState)
        self.assertEqual(set(hints.keys()), {"lifecycle"})
        self.assertIs(hints["lifecycle"], ConstructorLifecycleState)

    def test_no_supabase_llm_handoff_checkpointer(self) -> None:
        source = Path(
            "agents/monthly_plan_constructor/langgraph_runtime.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "import streamlit",
            "from streamlit",
            "import openai",
            "import supabase",
            "from langgraph.checkpoint",
            "MemorySaver(",
            "InMemorySaver(",
            "Admission",
            "handoff_artifact",
            "create_handoff",
            "service_role",
            "except Exception:",
        ):
            self.assertNotIn(forbidden, source)

    def test_deps_not_in_graph_state_type(self) -> None:
        fields = set(ConstructorGraphState.__annotations__)
        for banned in (
            "context",
            "assemble_candidates",
            "scope_reader",
            "labor_evidence",
            "supabase",
            "client",
            "secret",
            "authorization",
        ):
            self.assertNotIn(banned, fields)

    def test_wrong_node_status_fail_closed(self) -> None:
        app = build_constructor_langgraph(
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            scope_reader=RecordingReader(),
            now=FIXED_AT,
        )
        # Start graph expects CREATED; feeding MISSION_BOUND into invoke still starts at bind_mission
        bad = create_lifecycle_state(mission_id=MISSION_ID, created_at=FIXED_AT)
        # Force wrong status by advancing once outside graph then invoking — bind_mission rejects
        from agents.monthly_plan_constructor.lifecycle import advance_constructor_lifecycle

        mid = advance_constructor_lifecycle(
            bad,
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            scope_reader=RecordingReader(),
            now=FIXED_AT,
        )
        self.assertEqual(mid.status, STATUS_MISSION_BOUND)
        with self.assertRaises(LifecycleError):
            app.invoke({"lifecycle": mid})

    def test_compiled_graph_has_no_checkpointer(self) -> None:
        app = build_constructor_langgraph(
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            scope_reader=RecordingReader(),
            now=FIXED_AT,
        )
        self.assertIsNone(getattr(app, "checkpointer", None))

    def test_routing_uses_lifecycle_status_only(self) -> None:
        source = Path(
            "agents/monthly_plan_constructor/langgraph_runtime.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def _route_by_status", source)
        self.assertIn("lifecycle.status", source)
        route_fn = source.split("def _route_by_status", 1)[1].split(
            "\ndef build_constructor_langgraph", 1
        )[0]
        for banned in (
            "exception_code",
            "candidate_count",
            "package.",
            "labor_resolutions",
            "handoff_allowed",
            "is_ready_for_handoff",
        ):
            self.assertNotIn(banned, route_fn)


class TestParity(unittest.TestCase):
    def test_parity_ready(self) -> None:
        ctx = _context()
        pure = _run_pure(evidence=[_history()], context=ctx)
        graph = _run_graph(evidence=[_history()], context=ctx)
        _semantic_parity(pure, graph)

    def test_parity_wait(self) -> None:
        ctx = _context()
        pure = _run_pure(facility_scope=["ALL", "FACILITY_TARGET"], context=ctx)
        graph = _run_graph(facility_scope=["ALL", "FACILITY_TARGET"], context=ctx)
        _semantic_parity(pure, graph)

    def test_parity_failed_read(self) -> None:
        def raising_reader(context, mission):
            raise SecureReadError(CODE_READ_FAILED, "read failed")

        ctx = _context()
        pure = _run_pure(reader=raising_reader, context=ctx)  # type: ignore[arg-type]
        graph = _run_graph(reader=raising_reader, context=ctx)  # type: ignore[arg-type]
        _semantic_parity(pure, graph)

    def test_parity_data_contract(self) -> None:
        ctx = _context()
        pure = _run_pure(project_code="", context=ctx)
        graph = _run_graph(project_code="", context=ctx)
        _semantic_parity(pure, graph)

    def test_parity_zero_candidates(self) -> None:
        ctx = _context()
        reader = RecordingReader(rows=[])
        assembler = StubAssembler(candidates=[], scanned_count=0)
        pure = _run_pure(reader=reader, assembler=assembler, evidence=(), context=ctx)
        graph = _run_graph(reader=reader, assembler=assembler, evidence=(), context=ctx)
        _semantic_parity(pure, graph)

    def test_parity_all_unresolved(self) -> None:
        ctx = _context()
        pure = _run_pure(evidence=(), context=ctx)
        graph = _run_graph(evidence=(), context=ctx)
        _semantic_parity(pure, graph)


class TestIsolation(unittest.TestCase):
    def test_import_clean(self) -> None:
        mod = importlib.import_module(
            "agents.monthly_plan_constructor.langgraph_runtime"
        )
        self.assertTrue(hasattr(mod, "run_constructor_langgraph"))
        self.assertTrue(hasattr(mod, "build_constructor_langgraph"))
        self.assertNotIn("streamlit", mod.__dict__)
        self.assertNotIn("openai", mod.__dict__)

    def test_no_candidate_math(self) -> None:
        source = Path(
            "agents/monthly_plan_constructor/langgraph_runtime.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("remaining_qty", source)
        self.assertNotIn("classify_scope", source)
        self.assertNotIn("calculate_remainder", source)
        self.assertNotIn("build_constructor_mission_scope", source)
        self.assertNotIn("read_constructor_reality", source)
        self.assertNotIn("build_candidate_package", source)
        self.assertNotIn("resolve_labor_norms", source)
        self.assertNotIn("exceptions_from_labor", source)


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


class TestIncrement8HitlLangGraph(unittest.TestCase):
    def test_wait_surfaces_interrupt_and_resume(self) -> None:
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
        from agents.monthly_plan_constructor.lifecycle import (
            STATUS_READY_FOR_HANDOFF,
        )

        run_id = "run-inc8-hitl-graph"
        ctx = issue_read_only_agent_context(
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            project_code=PROJECT,
            run_id=run_id,
        )
        store = FakeHitlStore()
        reader = RecordingReader()
        app = build_constructor_langgraph(
            context=ctx,
            project_code=PROJECT,
            month_key=MONTH,
            facility_scope=["ALL", FACILITY_TARGET],
            assemble_candidates=StubAssembler(),
            scope_reader=reader,
            now=FIXED_AT,
            checkpointer=InMemorySaver(serde=build_constructor_jsonplus_serializer()),
            hitl_store=store,
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
        self.assertIn("__interrupt__", out1)
        interrupt_value = out1["__interrupt__"][0].value
        self.assertEqual(interrupt_value.reason_code, CODE_AMBIGUOUS_SCOPE)
        self.assertEqual(store.open_calls, 1)
        self.assertEqual(len(store.open_ids), 1)

        req = build_decision_request_from_lifecycle(out1["lifecycle"])
        self.assertEqual(req.interrupt_id, interrupt_value.interrupt_id)
        snap = app.get_state(config)
        checkpoint_id = snap.config["configurable"]["checkpoint_id"]
        cmd = build_resume_command(
            decision_id="dec-graph-1",
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
        self.assertGreaterEqual(reader.calls, 1)
        # Replay before interrupt causes a second upsert call, same id.
        self.assertGreaterEqual(store.open_calls, 2)
        self.assertEqual(len(store.open_ids), 1)
        self.assertEqual(store.answer_calls, 1)
        self.assertNotIn("resume_command", ConstructorGraphState.__annotations__)

    def test_wrong_thread_id_fail_closed(self) -> None:
        """Resume into human_wait with configurable.thread_id != lifecycle.run_id.

        LangGraph keys checkpoints by thread_id, so both the WAIT invoke and
        the Command resume must share that mismatched thread_id; otherwise
        interrupt() never returns and the product gate is not reached.
        """
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.types import Command

        from agents.monthly_plan_constructor import langgraph_runtime as lg_runtime
        from agents.monthly_plan_constructor.durable_checkpoint import (
            build_constructor_jsonplus_serializer,
        )
        from agents.monthly_plan_constructor.hitl_contracts import (
            CODE_HITL_CONTRACT_BLOCKER,
            DECISION_CLARIFY_SCOPE,
            HitlContractError,
            build_resume_command,
        )
        from agents.monthly_plan_constructor.hitl_resume import (
            build_decision_request_from_lifecycle,
        )

        run_id = "run-inc8-wrong-thread"
        wrong_thread = "thread-not-the-run-id"
        ctx = issue_read_only_agent_context(
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            project_code=PROJECT,
            run_id=run_id,
        )
        store = FakeHitlStore()
        reader = RecordingReader()
        app = build_constructor_langgraph(
            context=ctx,
            project_code=PROJECT,
            month_key=MONTH,
            facility_scope=["ALL", FACILITY_TARGET],
            assemble_candidates=StubAssembler(),
            scope_reader=reader,
            now=FIXED_AT,
            checkpointer=InMemorySaver(serde=build_constructor_jsonplus_serializer()),
            hitl_store=store,
        )
        initial = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id=run_id,
            authorization_id=ctx.authorization_id,
            created_at=FIXED_AT,
        )
        config = {"configurable": {"thread_id": wrong_thread}}
        out1 = app.invoke({"lifecycle": initial}, config)
        self.assertEqual(out1["lifecycle"].status, STATUS_WAITING_FOR_HUMAN)
        reads_after_wait = reader.calls
        answers_after_wait = store.answer_calls

        req = build_decision_request_from_lifecycle(out1["lifecycle"])
        snap = app.get_state(config)
        checkpoint_id = snap.config["configurable"]["checkpoint_id"]
        cmd = build_resume_command(
            decision_id="dec-wrong-thread",
            interrupt_id=req.interrupt_id,
            run_id=run_id,
            mission_id=MISSION_ID,
            decision=DECISION_CLARIFY_SCOPE,
            actor_id="human-1",
            parameters={"facility_scope": [FACILITY_TARGET]},
            expected_checkpoint_id=checkpoint_id,
            submitted_at=FIXED_AT,
        )
        with patch.object(
            lg_runtime,
            "apply_constructor_resume_command",
            wraps=lg_runtime.apply_constructor_resume_command,
        ) as apply_spy:
            with self.assertRaises(HitlContractError) as raised:
                app.invoke(Command(resume=cmd), config)
        self.assertEqual(raised.exception.code, CODE_HITL_CONTRACT_BLOCKER)
        self.assertIn("thread_id must equal run_id", str(raised.exception))
        self.assertEqual(apply_spy.call_count, 0)
        self.assertEqual(store.answer_calls, answers_after_wait)
        self.assertEqual(reader.calls, reads_after_wait)
        held = app.get_state(config)
        self.assertEqual(held.values["lifecycle"].status, STATUS_WAITING_FOR_HUMAN)

    def test_expired_context_fail_closed_on_resume(self) -> None:
        """Expired context can reach WAIT (bind_mission AMBIGUOUS_SCOPE).

        AgentExecutionContext is frozen. Secure-read expiry is not consulted
        until load_reality, so an already-expired context still interrupts.
        Resume must fail closed at require_durable_resume_checkpoint.
        """
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.types import Command

        from agents.monthly_plan_constructor import langgraph_runtime as lg_runtime
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
        from agents.monthly_plan_constructor.lifecycle import (
            CODE_LIFECYCLE_CONTRACT_BLOCKER,
        )

        run_id = "run-inc8-expired-ctx"
        live = issue_read_only_agent_context(
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            project_code=PROJECT,
            run_id=run_id,
        )
        expired = AgentExecutionContext(
            actor_id=live.actor_id,
            actor_type=live.actor_type,
            agent_code=live.agent_code,
            agent_version=live.agent_version,
            run_id=live.run_id,
            project_code=live.project_code,
            allowed_tools=live.allowed_tools,
            permission_tier=live.permission_tier,
            authorization_id=live.authorization_id,
            issued_at=live.issued_at,
            expires_at=(
                datetime.now(timezone.utc) - timedelta(seconds=5)
            ).isoformat(),
            security_policy_version=live.security_policy_version,
            write_allowed=False,
        )
        self.assertTrue(expired.is_expired())
        store = FakeHitlStore()
        reader = RecordingReader()
        app = build_constructor_langgraph(
            context=expired,
            project_code=PROJECT,
            month_key=MONTH,
            facility_scope=["ALL", FACILITY_TARGET],
            assemble_candidates=StubAssembler(),
            scope_reader=reader,
            now=FIXED_AT,
            checkpointer=InMemorySaver(serde=build_constructor_jsonplus_serializer()),
            hitl_store=store,
        )
        initial = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id=run_id,
            authorization_id=expired.authorization_id,
            created_at=FIXED_AT,
        )
        config = {"configurable": {"thread_id": run_id}}
        out1 = app.invoke({"lifecycle": initial}, config)
        self.assertEqual(out1["lifecycle"].status, STATUS_WAITING_FOR_HUMAN)
        reads_after_wait = reader.calls
        answers_after_wait = store.answer_calls

        req = build_decision_request_from_lifecycle(out1["lifecycle"])
        snap = app.get_state(config)
        checkpoint_id = snap.config["configurable"]["checkpoint_id"]
        cmd = build_resume_command(
            decision_id="dec-expired-ctx",
            interrupt_id=req.interrupt_id,
            run_id=run_id,
            mission_id=MISSION_ID,
            decision=DECISION_CLARIFY_SCOPE,
            actor_id="human-1",
            parameters={"facility_scope": [FACILITY_TARGET]},
            expected_checkpoint_id=checkpoint_id,
            submitted_at=FIXED_AT,
        )
        with patch.object(
            lg_runtime,
            "apply_constructor_resume_command",
            wraps=lg_runtime.apply_constructor_resume_command,
        ) as apply_spy:
            with self.assertRaises(LifecycleError) as raised:
                app.invoke(Command(resume=cmd), config)
        self.assertEqual(raised.exception.code, CODE_LIFECYCLE_CONTRACT_BLOCKER)
        self.assertIn("expired", str(raised.exception).lower())
        self.assertEqual(apply_spy.call_count, 0)
        self.assertEqual(store.answer_calls, answers_after_wait)
        self.assertEqual(reader.calls, reads_after_wait)
        held = app.get_state(config)
        self.assertEqual(held.values["lifecycle"].status, STATUS_WAITING_FOR_HUMAN)

    def test_no_apply_human_decision_node(self) -> None:
        source = Path(
            "agents/monthly_plan_constructor/langgraph_runtime.py"
        ).read_text(encoding="utf-8")
        self.assertIn("NODE_HUMAN_WAIT", source)
        self.assertNotIn("apply_human_decision", source)
        self.assertIn("apply_constructor_resume_command", source)
        self.assertIn("interrupt(", source)


if __name__ == "__main__":
    unittest.main()
