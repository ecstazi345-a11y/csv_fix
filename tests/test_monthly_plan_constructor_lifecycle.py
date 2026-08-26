"""
Increment 6 — Constructor Pure Python Lifecycle.

Pure domain tests. No Streamlit, Supabase, LLM, LangGraph, or product writes.
"""

from __future__ import annotations

import importlib
import inspect
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_PROVISIONAL,
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
    CandidatePackageError,
)
from agents.monthly_plan_constructor.exception_engine import (
    CODE_AMBIGUOUS_SCOPE,
    CODE_DATA_CONTRACT_BLOCKER,
    CODE_ENGINE_CONTRACT_BLOCKER,
    CODE_LABOR_NORM_UNRESOLVED,
    CODE_READ_FAILED,
    CODE_SECURITY_DENIED,
    ExceptionEngineError,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_NORMATIVE_BENCHMARK,
    BASIS_OBSERVED_PRODUCTIVITY,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    LaborNormEvidence,
    LaborNormResolverError,
    SOURCE_OFFICIAL_NORMATIVE,
    SOURCE_PROJECT_HISTORY,
)
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_CREATED,
    STATUS_FAILED,
    STATUS_LABOR_RESOLVED,
    STATUS_MISSION_BOUND,
    STATUS_PACKAGE_BUILT,
    STATUS_READY_FOR_HANDOFF,
    STATUS_REALITY_LOADED,
    STATUS_WAITING_FOR_HUMAN,
    CandidateAssemblyResult,
    ConstructorLifecycleState,
    LifecycleError,
    LifecycleTransition,
    _append_transition,
    advance_constructor_lifecycle,
    create_lifecycle_state,
    is_ready_for_handoff,
    run_constructor_lifecycle,
)
from agents.monthly_plan_constructor.mission_scope import (
    ConstructorMissionScope,
    build_constructor_mission_scope,
)
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
MISSION_ID = "mission-increment-6"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
OTHER_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-002"
FIXED_AT = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)


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
    """Injected port — does not calculate physical remainder."""

    def __init__(
        self,
        candidates: list[dict[str, object]] | None = None,
        *,
        scanned_count: int | None = None,
        fail: BaseException | None = None,
    ) -> None:
        self.candidates = candidates if candidates is not None else [_candidate_dict()]
        self.scanned_count = (
            scanned_count if scanned_count is not None else max(1, len(self.candidates))
        )
        self.fail = fail
        self.calls = 0

    def __call__(
        self,
        reality_read: ConstructorRealityRead,
        scope: ConstructorMissionScope,
    ) -> CandidateAssemblyResult:
        self.calls += 1
        if self.fail is not None:
            raise self.fail
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


def _run(
    *,
    assembler: StubAssembler | None = None,
    reader: RecordingReader | None = None,
    evidence: Sequence[LaborNormEvidence] = (),
    project_code: object = PROJECT,
    month_key: object = MONTH,
    facility_scope: object = None,
    discipline_scope: object = None,
    queue_scope: object = None,
    context: AgentExecutionContext | None = None,
) -> ConstructorLifecycleState:
    return run_constructor_lifecycle(
        context=context or _context(),
        project_code=project_code,
        month_key=month_key,
        facility_scope=facility_scope,  # type: ignore[arg-type]
        discipline_scope=discipline_scope,  # type: ignore[arg-type]
        queue_scope=queue_scope,  # type: ignore[arg-type]
        assemble_candidates=assembler or StubAssembler(),
        labor_evidence=evidence,
        scope_reader=reader or RecordingReader(),
        mission_id=MISSION_ID,
        now=FIXED_AT,
    )


class TestStateContract(unittest.TestCase):
    def test_frozen_state(self) -> None:
        state = create_lifecycle_state(mission_id=MISSION_ID, created_at=FIXED_AT)
        with self.assertRaises(Exception):
            state.status = STATUS_FAILED  # type: ignore[misc]

    def test_frozen_transition(self) -> None:
        item = LifecycleTransition(
            from_status=STATUS_CREATED,
            to_status=STATUS_MISSION_BOUND,
            at=FIXED_AT,
        )
        with self.assertRaises(Exception):
            item.to_status = STATUS_FAILED  # type: ignore[misc]

    def test_created_optional_artifacts(self) -> None:
        state = create_lifecycle_state(mission_id=MISSION_ID, created_at=FIXED_AT)
        self.assertEqual(state.status, STATUS_CREATED)
        self.assertIsNone(state.scope)
        self.assertIsNone(state.reality_read)
        self.assertIsNone(state.package)
        self.assertIsNone(state.labor_resolutions)
        self.assertIsNone(state.exceptions)

    def test_timezone_aware_timestamps(self) -> None:
        state = _run()
        self.assertIsNotNone(state.created_at.tzinfo)
        self.assertIsNotNone(state.updated_at.tzinfo)
        for item in state.transitions:
            self.assertIsNotNone(item.at.tzinfo)

    def test_naive_now_rejected(self) -> None:
        with self.assertRaises(LifecycleError):
            run_constructor_lifecycle(
                context=_context(),
                project_code=PROJECT,
                month_key=MONTH,
                assemble_candidates=StubAssembler(),
                scope_reader=RecordingReader(),
                now=datetime(2026, 8, 26, 12, 0, 0),
            )

    def test_no_dataframe_in_public_contract(self) -> None:
        source = Path("agents/monthly_plan_constructor/lifecycle.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("import pandas", source)
        self.assertNotIn("DataFrame", inspect.signature(ConstructorLifecycleState).parameters)


class TestNormalPath(unittest.TestCase):
    def test_full_path_ready(self) -> None:
        state = _run(evidence=[_history()])
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        self.assertTrue(is_ready_for_handoff(state))
        statuses = [t.to_status for t in state.transitions]
        self.assertEqual(
            statuses,
            [
                STATUS_MISSION_BOUND,
                STATUS_REALITY_LOADED,
                STATUS_PACKAGE_BUILT,
                STATUS_LABOR_RESOLVED,
                STATUS_READY_FOR_HANDOFF,
            ],
        )

    def test_validated_labor(self) -> None:
        state = _run(evidence=[_history()])
        self.assertEqual(
            state.package.candidates[0].labor_norm_status, LABOR_VALIDATED  # type: ignore[union-attr]
        )
        self.assertEqual(state.exceptions.exceptions, ())  # type: ignore[union-attr]

    def test_provisional_labor(self) -> None:
        state = _run(evidence=[_normative()])
        self.assertEqual(
            state.package.candidates[0].labor_norm_status, LABOR_PROVISIONAL  # type: ignore[union-attr]
        )
        self.assertEqual(len(state.exceptions.exceptions), 0)  # type: ignore[union-attr]

    def test_mixed_unresolved_continues(self) -> None:
        assembler = StubAssembler(
            [
                _candidate_dict(candidate_id=CANDIDATE_ID, boq_code="BOQ-001"),
                _candidate_dict(candidate_id=OTHER_ID, boq_code="BOQ-002"),
            ],
            scanned_count=2,
        )
        state = _run(assembler=assembler, evidence=[_history()])
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        codes = {e.exception_code for e in state.exceptions.exceptions}  # type: ignore[union-attr]
        self.assertEqual(codes, {CODE_LABOR_NORM_UNRESOLVED})
        self.assertTrue(state.exceptions.handoff_allowed())  # type: ignore[union-attr]

    def test_all_unresolved_continues(self) -> None:
        state = _run(evidence=())
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        self.assertEqual(
            state.exceptions.exceptions[0].exception_code,  # type: ignore[union-attr]
            CODE_LABOR_NORM_UNRESOLVED,
        )
        self.assertEqual(len(state.package.candidates), 1)  # type: ignore[union-attr]


class TestZeroCandidate(unittest.TestCase):
    def test_empty_assembly_ready(self) -> None:
        reader = RecordingReader(rows=[])
        assembler = StubAssembler(candidates=[], scanned_count=0)
        state = _run(reader=reader, assembler=assembler, evidence=())
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        self.assertEqual(state.package.candidate_count, 0)  # type: ignore[union-attr]
        self.assertEqual(state.labor_resolutions.resolutions, ())  # type: ignore[union-attr]
        self.assertTrue(is_ready_for_handoff(state))


class TestScopeFailures(unittest.TestCase):
    def test_data_contract_blocker_failed(self) -> None:
        state = _run(project_code="")
        self.assertEqual(state.status, STATUS_FAILED)
        self.assertIsNone(state.scope)
        self.assertEqual(state.error_code, CODE_DATA_CONTRACT_BLOCKER)
        self.assertEqual(
            state.exceptions.exceptions[0].exception_code,  # type: ignore[union-attr]
            CODE_DATA_CONTRACT_BLOCKER,
        )

    def test_ambiguous_scope_wait_human(self) -> None:
        state = _run(facility_scope=["ALL", "FACILITY_TARGET"])
        self.assertEqual(state.status, STATUS_WAITING_FOR_HUMAN)
        self.assertEqual(state.error_code, CODE_AMBIGUOUS_SCOPE)
        self.assertEqual(
            state.exceptions.exceptions[0].route,  # type: ignore[union-attr]
            "WAIT_HUMAN",
        )


class TestSecureReadFailures(unittest.TestCase):
    def test_security_denied(self) -> None:
        ctx = _context(project_code="PRJ_OTHER")
        state = _run(context=ctx)
        self.assertEqual(state.status, STATUS_FAILED)
        self.assertEqual(state.error_code, CODE_SECURITY_DENIED)
        self.assertIsNotNone(state.scope)
        self.assertIsNone(state.reality_read)

    def test_tool_not_allowed_alias(self) -> None:
        def raising_reader(context, mission):
            raise SecureReadError("TOOL_NOT_ALLOWED", "tool denied")

        state = _run(reader=raising_reader)  # type: ignore[arg-type]        self.assertEqual(state.status, STATUS_FAILED)
        self.assertEqual(state.error_code, CODE_SECURITY_DENIED)
        self.assertEqual(
            state.exceptions.exceptions[0].details.original_failure_code,  # type: ignore[union-attr]
            "TOOL_NOT_ALLOWED",
        )

    def test_context_expired_alias(self) -> None:
        def raising_reader(context, mission):
            raise SecureReadError("CONTEXT_EXPIRED", "expired")

        state = _run(reader=raising_reader)  # type: ignore[arg-type]
        self.assertEqual(state.status, STATUS_FAILED)
        self.assertEqual(state.error_code, CODE_SECURITY_DENIED)

    def test_context_missing_alias(self) -> None:
        def raising_reader(context, mission):
            raise SecureReadError("CONTEXT_MISSING", "missing")

        state = _run(reader=raising_reader)  # type: ignore[arg-type]
        self.assertEqual(state.status, STATUS_FAILED)
        self.assertEqual(state.error_code, CODE_SECURITY_DENIED)

    def test_read_failed(self) -> None:
        def raising_reader(context, mission):
            raise SecureReadError(CODE_READ_FAILED, "read failed")

        state = _run(reader=raising_reader)  # type: ignore[arg-type]
        self.assertEqual(state.status, STATUS_FAILED)
        self.assertEqual(state.error_code, CODE_READ_FAILED)
        self.assertIsNone(state.package)


class TestPackageFailure(unittest.TestCase):
    def test_package_error_preserves_prior_artifacts(self) -> None:
        assembler = StubAssembler(
            fail=CandidatePackageError(CODE_DATA_CONTRACT_BLOCKER, "bad package")
        )
        state = _run(assembler=assembler)
        self.assertEqual(state.status, STATUS_FAILED)
        self.assertIsNotNone(state.scope)
        self.assertIsNotNone(state.reality_read)
        self.assertIsNone(state.package)


class TestLaborFailure(unittest.TestCase):
    def test_labor_contract_failure_preserves_package(self) -> None:
        def bad_evidence(package, state):
            raise LaborNormResolverError(CODE_DATA_CONTRACT_BLOCKER, "bad evidence")

        # resolve_labor_norms raises if evidence items wrong type — pass invalid sequence via wrapper
        state = run_constructor_lifecycle(
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            labor_evidence=["not-evidence"],  # type: ignore[arg-type]
            scope_reader=RecordingReader(),
            mission_id=MISSION_ID,
            now=FIXED_AT,
        )
        self.assertEqual(state.status, STATUS_FAILED)
        self.assertIsNotNone(state.package)
        self.assertIsNone(state.labor_resolutions)
        self.assertEqual(state.error_code, CODE_DATA_CONTRACT_BLOCKER)


class TestExceptionEngineFailure(unittest.TestCase):
    def test_engine_contract_failure_failed_safely(self) -> None:
        state = create_lifecycle_state(mission_id=MISSION_ID, created_at=FIXED_AT)
        scope = build_constructor_mission_scope(project_code=PROJECT, month_key=MONTH)
        state = _append_transition(
            state,
            to_status=STATUS_MISSION_BOUND,
            at=FIXED_AT,
            scope=scope,
        )
        # Force engine failure path via helper by mapping unknown through protected path
        from agents.monthly_plan_constructor.lifecycle import _fail_engine_contract

        failed = _fail_engine_contract(
            state,
            ExceptionEngineError(CODE_ENGINE_CONTRACT_BLOCKER, "broken"),
            at=FIXED_AT,
        )
        self.assertEqual(failed.status, STATUS_FAILED)
        self.assertEqual(failed.error_code, CODE_ENGINE_CONTRACT_BLOCKER)
        self.assertIsNone(failed.exceptions)


class TestReadiness(unittest.TestCase):
    def test_missing_package_not_ready(self) -> None:
        state = create_lifecycle_state(mission_id=MISSION_ID, created_at=FIXED_AT)
        self.assertFalse(is_ready_for_handoff(state))

    def test_labor_only_non_blocking_ready(self) -> None:
        state = _run(evidence=())
        self.assertTrue(is_ready_for_handoff(state))
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)

    def test_blocking_exception_not_ready(self) -> None:
        state = _run(project_code="")
        self.assertFalse(is_ready_for_handoff(state))
        self.assertEqual(state.status, STATUS_FAILED)


class TestTransitions(unittest.TestCase):
    def test_prohibited_jump_rejected(self) -> None:
        state = create_lifecycle_state(mission_id=MISSION_ID, created_at=FIXED_AT)
        with self.assertRaises(LifecycleError) as raised:
            _append_transition(state, to_status=STATUS_PACKAGE_BUILT, at=FIXED_AT)
        self.assertIn("prohibited transition", str(raised.exception))

    def test_failed_is_terminal(self) -> None:
        state = _run(project_code="")
        with self.assertRaises(LifecycleError):
            _append_transition(state, to_status=STATUS_READY_FOR_HANDOFF, at=FIXED_AT)

    def test_waiting_is_terminal(self) -> None:
        state = _run(facility_scope=["ALL", "X"])
        with self.assertRaises(LifecycleError):
            _append_transition(state, to_status=STATUS_READY_FOR_HANDOFF, at=FIXED_AT)

    def test_append_only_trace(self) -> None:
        state = _run(evidence=[_history()])
        self.assertEqual(len(state.transitions), 5)
        self.assertEqual(state.transitions[0].from_status, STATUS_CREATED)


class TestAssemblerBoundary(unittest.TestCase):
    def test_injected_assembler_used(self) -> None:
        assembler = StubAssembler()
        state = _run(assembler=assembler, evidence=[_history()])
        self.assertEqual(assembler.calls, 1)
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)

    def test_no_mpca_domain_import(self) -> None:
        source = Path("agents/monthly_plan_constructor/lifecycle.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("agents.monthly_plan_constructor.domain", source)
        self.assertNotIn("agents.monthly_plan_constructor.runtime", source)
        self.assertNotIn("mpca_002", source.lower())
        self.assertNotIn("mpca_003", source.lower())
        self.assertNotIn("def calculate_remainder", source)
        self.assertNotIn("def classify", source)


class TestArchitectureIsolation(unittest.TestCase):
    def test_module_isolation(self) -> None:
        source = Path("agents/monthly_plan_constructor/lifecycle.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "import streamlit",
            "from streamlit",
            "import langgraph",
            "from langgraph",
            "import openai",
            "import supabase",
            "except Exception:",
            "except BaseException:",
        ):
            self.assertNotIn(forbidden, source)

    def test_import_clean(self) -> None:
        mod = importlib.import_module("agents.monthly_plan_constructor.lifecycle")
        self.assertTrue(hasattr(mod, "run_constructor_lifecycle"))
        self.assertTrue(hasattr(mod, "advance_constructor_lifecycle"))
        self.assertNotIn("streamlit", mod.__dict__)

    def test_authorization_id_recorded(self) -> None:
        ctx = _context()
        state = _run(context=ctx, evidence=[_history()])
        self.assertEqual(state.authorization_id, ctx.authorization_id)


def _advance(
    state: ConstructorLifecycleState,
    *,
    assembler: StubAssembler | None = None,
    reader: RecordingReader | None = None,
    evidence: Sequence[LaborNormEvidence] = (),
    project_code: object = PROJECT,
    month_key: object = MONTH,
    facility_scope: object = None,
    context: AgentExecutionContext | None = None,
) -> ConstructorLifecycleState:
    return advance_constructor_lifecycle(
        state,
        context=context or _context(),
        project_code=project_code,
        month_key=month_key,
        facility_scope=facility_scope,  # type: ignore[arg-type]
        assemble_candidates=assembler or StubAssembler(),
        labor_evidence=evidence,
        scope_reader=reader or RecordingReader(),
        now=FIXED_AT,
    )


class TestAdvanceOneStage(unittest.TestCase):
    def test_created_to_mission_bound(self) -> None:
        state = create_lifecycle_state(mission_id=MISSION_ID, created_at=FIXED_AT)
        state = _advance(state)
        self.assertEqual(state.status, STATUS_MISSION_BOUND)
        self.assertIsNotNone(state.scope)
        self.assertEqual([t.to_status for t in state.transitions], [STATUS_MISSION_BOUND])

    def test_exactly_one_professional_stage_per_advance(self) -> None:
        state = create_lifecycle_state(mission_id=MISSION_ID, created_at=FIXED_AT)
        state = _advance(state)
        self.assertEqual(state.status, STATUS_MISSION_BOUND)
        self.assertNotEqual(state.status, STATUS_REALITY_LOADED)
        self.assertEqual(len(state.transitions), 1)
        state = _advance(state)
        self.assertEqual(state.status, STATUS_REALITY_LOADED)
        self.assertNotEqual(state.status, STATUS_PACKAGE_BUILT)
        self.assertEqual(len(state.transitions), 2)

    def test_mission_bound_to_reality_loaded(self) -> None:
        state = create_lifecycle_state(mission_id=MISSION_ID, created_at=FIXED_AT)
        state = _advance(state)
        state = _advance(state)
        self.assertEqual(state.status, STATUS_REALITY_LOADED)
        self.assertIsNotNone(state.reality_read)

    def test_reality_to_package_built(self) -> None:
        state = create_lifecycle_state(mission_id=MISSION_ID, created_at=FIXED_AT)
        state = _advance(state)
        state = _advance(state)
        state = _advance(state)
        self.assertEqual(state.status, STATUS_PACKAGE_BUILT)
        self.assertIsNotNone(state.package)

    def test_package_to_labor_resolved(self) -> None:
        state = create_lifecycle_state(mission_id=MISSION_ID, created_at=FIXED_AT)
        for _ in range(3):
            state = _advance(state)
        state = _advance(state, evidence=[_history()])
        self.assertEqual(state.status, STATUS_LABOR_RESOLVED)
        self.assertIsNotNone(state.labor_resolutions)

    def test_labor_to_ready(self) -> None:
        state = create_lifecycle_state(mission_id=MISSION_ID, created_at=FIXED_AT)
        for _ in range(3):
            state = _advance(state)
        state = _advance(state, evidence=[_history()])
        state = _advance(state, evidence=[_history()])
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        self.assertTrue(is_ready_for_handoff(state))

    def test_terminal_cannot_advance_ready(self) -> None:
        state = _run(evidence=[_history()])
        with self.assertRaises(LifecycleError) as raised:
            _advance(state, evidence=[_history()])
        self.assertIn("cannot advance terminal", str(raised.exception))

    def test_terminal_cannot_advance_waiting(self) -> None:
        state = _run(facility_scope=["ALL", "FACILITY_TARGET"])
        with self.assertRaises(LifecycleError):
            _advance(state)

    def test_terminal_cannot_advance_failed(self) -> None:
        state = _run(project_code="")
        with self.assertRaises(LifecycleError):
            _advance(state)

    def test_advance_ambiguous_scope_wait(self) -> None:
        state = create_lifecycle_state(mission_id=MISSION_ID, created_at=FIXED_AT)
        state = _advance(state, facility_scope=["ALL", "FACILITY_TARGET"])
        self.assertEqual(state.status, STATUS_WAITING_FOR_HUMAN)
        self.assertEqual(state.error_code, CODE_AMBIGUOUS_SCOPE)

    def test_advance_secure_read_failed(self) -> None:
        state = create_lifecycle_state(mission_id=MISSION_ID, created_at=FIXED_AT)
        state = _advance(state)

        def raising_reader(context, mission):
            raise SecureReadError(CODE_READ_FAILED, "read failed")

        state = _advance(state, reader=raising_reader)  # type: ignore[arg-type]
        self.assertEqual(state.status, STATUS_FAILED)
        self.assertEqual(state.error_code, CODE_READ_FAILED)

    def test_advance_zero_candidate_path(self) -> None:
        reader = RecordingReader(rows=[])
        assembler = StubAssembler(candidates=[], scanned_count=0)
        state = create_lifecycle_state(mission_id=MISSION_ID, created_at=FIXED_AT)
        for _ in range(5):
            state = _advance(state, reader=reader, assembler=assembler, evidence=())
            if state.status in {STATUS_READY_FOR_HANDOFF, STATUS_FAILED, STATUS_WAITING_FOR_HUMAN}:
                break
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        self.assertEqual(state.package.candidate_count, 0)  # type: ignore[union-attr]

    def test_advance_all_unresolved_ready(self) -> None:
        state = create_lifecycle_state(mission_id=MISSION_ID, created_at=FIXED_AT)
        for _ in range(5):
            state = _advance(state, evidence=())
            if state.status in {STATUS_READY_FOR_HANDOFF, STATUS_FAILED, STATUS_WAITING_FOR_HUMAN}:
                break
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        self.assertEqual(
            state.exceptions.exceptions[0].exception_code,  # type: ignore[union-attr]
            CODE_LABOR_NORM_UNRESOLVED,
        )

    def test_advance_append_only(self) -> None:
        state = create_lifecycle_state(mission_id=MISSION_ID, created_at=FIXED_AT)
        prev_len = 0
        for _ in range(5):
            state = _advance(state, evidence=[_history()])
            self.assertGreaterEqual(len(state.transitions), prev_len)
            prev_len = len(state.transitions)
            if state.status == STATUS_READY_FOR_HANDOFF:
                break
        self.assertEqual(state.transitions[0].from_status, STATUS_CREATED)

    def test_run_matches_manual_advance_loop(self) -> None:
        via_run = _run(evidence=[_history()])
        state = create_lifecycle_state(
            mission_id=MISSION_ID,
            run_id=via_run.run_id,
            authorization_id=via_run.authorization_id,
            created_at=FIXED_AT,
        )
        assembler = StubAssembler()
        reader = RecordingReader()
        evidence = [_history()]
        while state.status not in {
            STATUS_READY_FOR_HANDOFF,
            STATUS_WAITING_FOR_HUMAN,
            STATUS_FAILED,
        }:
            state = _advance(
                state,
                assembler=assembler,
                reader=reader,
                evidence=evidence,
            )
        self.assertEqual(state.status, via_run.status)
        self.assertEqual(
            [t.to_status for t in state.transitions],
            [t.to_status for t in via_run.transitions],
        )
        self.assertEqual(
            state.package.candidate_count,  # type: ignore[union-attr]
            via_run.package.candidate_count,  # type: ignore[union-attr]
        )


if __name__ == "__main__":
    unittest.main()
