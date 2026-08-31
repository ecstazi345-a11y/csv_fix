"""
Increment 9.1 — ConstructorHandoff contract and builder tests.

Pure domain tests. No Streamlit, Supabase, SQL, LangGraph, LLM, or product writes.
"""

from __future__ import annotations

import inspect
import re
import unittest
from dataclasses import fields, is_dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
    PackageExceptionSummary,
)
from agents.monthly_plan_constructor.exception_engine import (
    CODE_AMBIGUOUS_SCOPE,
    SOURCE_MISSION_SCOPE,
    ConstructorExceptionSet,
    exception_from_failure,
)
from agents.monthly_plan_constructor.handoff_contracts import (
    CODE_HANDOFF_CONTRACT_BLOCKER,
    DEFAULT_SECURITY_POLICY_VERSION,
    HANDOFF_TYPE,
    MAX_CANDIDATE_ID_LENGTH,
    MAX_CANDIDATE_IDS,
    SOURCE_AGENT,
    STATUS_HANDOFF_READY,
    TARGET_ROLE,
    ConstructorHandoffError,
    build_constructor_handoff,
    compute_constructor_handoff_id,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_OBSERVED_PRODUCTIVITY,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    LaborNormEvidence,
    SOURCE_PROJECT_HISTORY,
)
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_CREATED,
    STATUS_READY_FOR_HANDOFF,
    STATUS_WAITING_FOR_HUMAN,
    CandidateAssemblyResult,
    ConstructorLifecycleState,
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
MISSION_ID = "mission-increment-9-handoff"
RUN_ID = "run-increment-9-handoff"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
FIXED_AT = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)
LATER_AT = datetime(2026, 8, 31, 13, 0, 0, tzinfo=timezone.utc)

_FORBIDDEN = re.compile(
    r"(postgresql://|password|service_role|bearer\s+|supabase|"
    r"authorization:|secret_key|dataframe|prompt)",
    re.IGNORECASE,
)


def _context() -> AgentExecutionContext:
    return issue_read_only_agent_context(
        agent_code="MONTHLY_PLAN_CONSTRUCTOR",
        project_code=PROJECT,
        run_id=RUN_ID,
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

    def __call__(
        self,
        context: AgentExecutionContext,
        mission: ConstructorMissionScope,
    ) -> list[dict[str, object]]:
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

    def __call__(
        self,
        reality_read: ConstructorRealityRead,
        scope: ConstructorMissionScope,
    ) -> CandidateAssemblyResult:
        return CandidateAssemblyResult(
            candidates=tuple(self.candidates),
            scanned_count=self.scanned_count,
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


def _ready(**overrides: object) -> ConstructorLifecycleState:
    kwargs: dict[str, object] = {
        "context": _context(),
        "project_code": PROJECT,
        "month_key": MONTH,
        "assemble_candidates": StubAssembler(),
        "labor_evidence": (_history(),),
        "scope_reader": RecordingReader(),
        "mission_id": MISSION_ID,
        "run_id": RUN_ID,
        "now": FIXED_AT,
    }
    kwargs.update(overrides)
    return run_constructor_lifecycle(**kwargs)  # type: ignore[arg-type]


def _build(state: ConstructorLifecycleState, **kwargs: object):
    payload = {
        "security_policy_version": DEFAULT_SECURITY_POLICY_VERSION,
        "created_at": FIXED_AT,
    }
    payload.update(kwargs)
    return build_constructor_handoff(state, **payload)  # type: ignore[arg-type]


def _walk(value: Any, bag: list[Any]) -> None:
    bag.append(value)
    if is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            _walk(getattr(value, item.name), bag)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _walk(item, bag)
    elif isinstance(value, dict):
        for item in value.values():
            _walk(item, bag)


class TestValidHandoff(unittest.TestCase):
    def test_ready_fresh_snapshot(self) -> None:
        state = _ready()
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        handoff = _build(state)
        self.assertEqual(handoff.status, STATUS_HANDOFF_READY)
        self.assertEqual(handoff.handoff_type, HANDOFF_TYPE)
        self.assertEqual(handoff.source_agent, SOURCE_AGENT)
        self.assertEqual(handoff.target_role, TARGET_ROLE)
        self.assertEqual(handoff.source_run_id, RUN_ID)
        self.assertEqual(handoff.mission_id, MISSION_ID)
        self.assertEqual(handoff.candidate_count, 1)
        self.assertEqual(handoff.candidate_ids, (CANDIDATE_ID,))
        self.assertEqual(handoff.snapshot_id, state.reality_read.snapshot_id)  # type: ignore[union-attr]
        self.assertEqual(
            handoff.snapshot_id,
            state.package.provenance.snapshot_id,  # type: ignore[union-attr]
        )
        self.assertTrue(handoff.handoff_id.startswith("eos-hof-"))
        self.assertEqual(handoff.exceptions_summary.blocking_count, 0)
        self.assertIsNone(handoff.orchestration_run_id)

    def test_deterministic_id(self) -> None:
        state = _ready()
        a = _build(state)
        b = _build(state)
        self.assertEqual(a.handoff_id, b.handoff_id)
        expected = compute_constructor_handoff_id(
            source_run_id=RUN_ID,
            package_id=state.package.package_id,  # type: ignore[union-attr]
            snapshot_id=state.reality_read.snapshot_id,  # type: ignore[union-attr]
        )
        self.assertEqual(a.handoff_id, expected)

    def test_package_changed_new_id(self) -> None:
        state = _ready()
        original = _build(state)
        mutated = replace(
            state,
            package=replace(state.package, package_id="pkg-changed"),  # type: ignore[arg-type]
        )
        changed = _build(mutated)
        self.assertNotEqual(original.handoff_id, changed.handoff_id)

    def test_snapshot_changed_new_id(self) -> None:
        state = _ready()
        original = _build(state)
        new_snap = "snap-v2"
        package = replace(
            state.package,  # type: ignore[arg-type]
            provenance=replace(state.package.provenance, snapshot_id=new_snap),  # type: ignore[union-attr]
        )
        reality = replace(
            state.reality_read,  # type: ignore[arg-type]
            read_id=new_snap,
            provenance=replace(state.reality_read.provenance, read_id=new_snap),  # type: ignore[union-attr]
        )
        mutated = replace(state, package=package, reality_read=reality)
        changed = _build(mutated)
        self.assertNotEqual(original.handoff_id, changed.handoff_id)
        self.assertEqual(changed.snapshot_id, new_snap)

    def test_created_at_does_not_affect_id(self) -> None:
        state = _ready()
        a = _build(state, created_at=FIXED_AT)
        b = _build(state, created_at=LATER_AT)
        self.assertEqual(a.handoff_id, b.handoff_id)
        self.assertNotEqual(a.created_at, b.created_at)

    def test_empty_package_valid(self) -> None:
        state = _ready(
            assemble_candidates=StubAssembler(candidates=[], scanned_count=0),
            scope_reader=RecordingReader(rows=[]),
            labor_evidence=(),
        )
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        handoff = _build(state)
        self.assertEqual(handoff.candidate_count, 0)
        self.assertEqual(handoff.candidate_ids, ())
        self.assertEqual(handoff.status, STATUS_HANDOFF_READY)


class TestFailClosed(unittest.TestCase):
    def test_not_ready(self) -> None:
        state = _ready(facility_scope=["ALL", FACILITY_TARGET])
        self.assertEqual(state.status, STATUS_WAITING_FOR_HUMAN)
        with self.assertRaises(ConstructorHandoffError) as caught:
            _build(state)
        self.assertEqual(caught.exception.code, CODE_HANDOFF_CONTRACT_BLOCKER)

    def test_package_missing(self) -> None:
        state = replace(_ready(), package=None)
        with self.assertRaises(ConstructorHandoffError) as caught:
            _build(state)
        self.assertEqual(caught.exception.code, CODE_HANDOFF_CONTRACT_BLOCKER)

    def test_reality_missing(self) -> None:
        state = replace(_ready(), reality_read=None)
        with self.assertRaises(ConstructorHandoffError) as caught:
            _build(state)
        self.assertEqual(caught.exception.code, CODE_HANDOFF_CONTRACT_BLOCKER)

    def test_missing_snapshot(self) -> None:
        state = _ready()
        package = replace(
            state.package,  # type: ignore[arg-type]
            provenance=replace(state.package.provenance, snapshot_id=None),  # type: ignore[union-attr]
        )
        with self.assertRaises(ConstructorHandoffError) as caught:
            _build(replace(state, package=package))
        self.assertEqual(caught.exception.code, CODE_HANDOFF_CONTRACT_BLOCKER)

    def test_stale_snapshot_mismatch(self) -> None:
        state = _ready()
        reality = replace(
            state.reality_read,  # type: ignore[arg-type]
            read_id="stale-other",
            provenance=replace(state.reality_read.provenance, read_id="stale-other"),  # type: ignore[union-attr]
        )
        with self.assertRaises(ConstructorHandoffError) as caught:
            _build(replace(state, reality_read=reality))
        self.assertIn("stale snapshot", str(caught.exception))

    def test_blocking_exception(self) -> None:
        state = _ready()
        blocking = exception_from_failure(
            CODE_AMBIGUOUS_SCOPE,
            source_capability=SOURCE_MISSION_SCOPE,
            reason="blocking",
            observed_at=FIXED_AT,
        )
        exceptions = ConstructorExceptionSet(
            schema_version="1.0",
            exceptions=(blocking,),
            summary=PackageExceptionSummary(
                blocking_count=1,
                non_blocking_count=0,
                warning_count=0,
            ),
            package_id=state.package.package_id,  # type: ignore[union-attr]
        )
        with self.assertRaises(ConstructorHandoffError) as caught:
            _build(replace(state, exceptions=exceptions))
        self.assertEqual(caught.exception.code, CODE_HANDOFF_CONTRACT_BLOCKER)

    def test_wrong_project(self) -> None:
        state = _ready()
        scope = replace(state.scope, project_code="PRJ_OTHER")  # type: ignore[arg-type]
        with self.assertRaises(ConstructorHandoffError):
            _build(replace(state, scope=scope))

    def test_wrong_month(self) -> None:
        state = _ready()
        scope = replace(state.scope, month_key="октябрь-2026")  # type: ignore[arg-type]
        with self.assertRaises(ConstructorHandoffError):
            _build(replace(state, scope=scope))

    def test_wrong_mission(self) -> None:
        state = _ready()
        with self.assertRaises(ConstructorHandoffError):
            _build(replace(state, mission_id="mission-other"))

    def test_wrong_run(self) -> None:
        state = _ready()
        with self.assertRaises(ConstructorHandoffError):
            _build(replace(state, run_id="run-other"))

    def test_wrong_scope(self) -> None:
        state = _ready()
        scope = replace(state.scope, facility_scope=("OTHER",))  # type: ignore[arg-type]
        with self.assertRaises(ConstructorHandoffError):
            _build(replace(state, scope=scope))

    def test_created_status_rejected(self) -> None:
        state = replace(_ready(), status=STATUS_CREATED)
        with self.assertRaises(ConstructorHandoffError):
            _build(state)


class TestCandidateIdLimits(unittest.TestCase):
    def test_duplicate_candidate_id(self) -> None:
        state = _ready()
        first = state.package.candidates[0]  # type: ignore[union-attr]
        package = replace(
            state.package,  # type: ignore[arg-type]
            candidates=(first, first),
            summary=replace(state.package.summary, candidate_count=2),  # type: ignore[union-attr]
        )
        with self.assertRaises(ConstructorHandoffError) as caught:
            _build(replace(state, package=package))
        self.assertIn("duplicate candidate_id", str(caught.exception))

    def test_too_many_candidate_ids(self) -> None:
        state = _ready()
        first = state.package.candidates[0]  # type: ignore[union-attr]
        extra = tuple(
            replace(first, candidate_id=f"cid-{index:04d}")
            for index in range(MAX_CANDIDATE_IDS + 1)
        )
        package = replace(
            state.package,  # type: ignore[arg-type]
            candidates=extra,
            summary=replace(
                state.package.summary,  # type: ignore[union-attr]
                candidate_count=MAX_CANDIDATE_IDS + 1,
            ),
        )
        with self.assertRaises(ConstructorHandoffError) as caught:
            _build(replace(state, package=package))
        self.assertIn("exceed", str(caught.exception))

    def test_candidate_id_too_long(self) -> None:
        state = _ready()
        first = state.package.candidates[0]  # type: ignore[union-attr]
        package = replace(
            state.package,  # type: ignore[arg-type]
            candidates=(replace(first, candidate_id="x" * (MAX_CANDIDATE_ID_LENGTH + 1)),),
        )
        with self.assertRaises(ConstructorHandoffError) as caught:
            _build(replace(state, package=package))
        self.assertIn("128", str(caught.exception))


class TestSecurity(unittest.TestCase):
    def test_artifact_secret_free(self) -> None:
        handoff = _build(_ready())
        seen: list[Any] = []
        _walk(handoff, seen)
        forbidden_types = {
            "DataFrame",
            "AgentExecutionContext",
            "Connection",
            "Client",
        }
        for item in seen:
            name = type(item).__name__
            self.assertNotIn(name, forbidden_types)
            self.assertFalse(callable(item) and not isinstance(item, type))
            if isinstance(item, str):
                self.assertIsNone(_FORBIDDEN.search(item), item)

    def test_no_admission_execution_or_chat(self) -> None:
        handoff = _build(_ready())
        self.assertEqual(handoff.target_role, TARGET_ROLE)
        self.assertNotIn("SENT_TO_ADMISSION", handoff.status)
        blob = " ".join(
            str(getattr(handoff, item.name)) for item in fields(handoff)
        )
        self.assertNotIn("chat", blob.lower())
        self.assertNotIn("prompt", blob.lower())
        source = Path(
            "agents/monthly_plan_constructor/handoff_contracts.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("supabase", source.lower())
        self.assertNotIn("import pandas", source)
        self.assertNotIn("http", source.lower())
        self.assertNotIn("psycopg", source)
        self.assertNotIn("streamlit", source.lower())
        signature = inspect.signature(build_constructor_handoff)
        self.assertNotIn("dataframe", str(signature).lower())


if __name__ == "__main__":
    unittest.main()
