"""
Increment 8 — Constructor lifecycle serialization tests.

Local JsonPlusSerializer only. No Postgres/Supabase connection. No saver.setup().
"""

from __future__ import annotations

import re
import unittest
from datetime import datetime, timezone
from typing import Any

from agents.monthly_plan_constructor.candidate_package import LABOR_UNRESOLVED
from agents.monthly_plan_constructor.durable_checkpoint import (
    build_constructor_jsonplus_serializer,
)
from agents.monthly_plan_constructor.exception_engine import CODE_AMBIGUOUS_SCOPE
from agents.monthly_plan_constructor.hitl_contracts import (
    DECISION_CLARIFY_SCOPE,
    build_resume_command,
)
from agents.monthly_plan_constructor.hitl_resume import (
    apply_constructor_resume_command,
    build_decision_request_from_lifecycle,
)
from agents.monthly_plan_constructor.lifecycle import (
    STATUS_CREATED,
    STATUS_PACKAGE_BUILT,
    STATUS_READY_FOR_HANDOFF,
    STATUS_WAITING_FOR_HUMAN,
    CandidateAssemblyResult,
    ConstructorLifecycleState,
    create_lifecycle_state,
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
MISSION_ID = "mission-increment-8-serde"
RUN_ID = "run-increment-8-serde"
FIXED_AT = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"

_SENSITIVE = re.compile(
    r"(postgresql://|password|service_role|bearer\s+|supabase)",
    re.IGNORECASE,
)


def _context(run_id: str = RUN_ID) -> AgentExecutionContext:
    return issue_read_only_agent_context(
        agent_code="MONTHLY_PLAN_CONSTRUCTOR",
        project_code=PROJECT,
        run_id=run_id,
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
    def __call__(
        self,
        reality_read: ConstructorRealityRead,
        scope: ConstructorMissionScope,
    ) -> CandidateAssemblyResult:
        return CandidateAssemblyResult(
            candidates=(_candidate_dict(),),
            scanned_count=1,
        )


def _roundtrip(state: ConstructorLifecycleState) -> tuple[ConstructorLifecycleState, int]:
    serde = build_constructor_jsonplus_serializer()
    type_tag, payload = serde.dumps_typed(state)
    restored = serde.loads_typed((type_tag, payload))
    assert isinstance(restored, ConstructorLifecycleState)
    return restored, len(payload)


def _walk(obj: Any, path: str = "root") -> list[str]:
    findings: list[str] = []
    if callable(obj) and not isinstance(obj, type):
        findings.append(f"callable:{path}")
    if isinstance(obj, AgentExecutionContext):
        findings.append(f"context:{path}")
    if obj.__class__.__name__ in {"DataFrame", "Connection", "PostgresSaver"}:
        findings.append(f"unsafe:{path}:{obj.__class__.__name__}")
    if hasattr(obj, "__dict__") and not isinstance(obj, type):
        for key, value in getattr(obj, "__dict__", {}).items():
            findings.extend(_walk(value, f"{path}.{key}"))
    if isinstance(obj, (list, tuple, set, frozenset)):
        for idx, value in enumerate(obj):
            findings.extend(_walk(value, f"{path}[{idx}]"))
    if isinstance(obj, dict):
        for key, value in obj.items():
            findings.extend(_walk(value, f"{path}.{key}"))
    return findings


class TestSerializerConfig(unittest.TestCase):
    def test_pickle_fallback_disabled(self) -> None:
        serde = build_constructor_jsonplus_serializer()
        self.assertFalse(serde.pickle_fallback)

    def test_pickle_forbidden_flag(self) -> None:
        with self.assertRaises(ValueError):
            build_constructor_jsonplus_serializer(pickle_fallback=True)

    def test_explicit_allowlist_roundtrip(self) -> None:
        state = create_lifecycle_state(
            mission_id=MISSION_ID, run_id=RUN_ID, created_at=FIXED_AT
        )
        restored, size = _roundtrip(state)
        self.assertEqual(restored.status, STATUS_CREATED)
        self.assertEqual(restored.run_id, RUN_ID)
        self.assertGreater(size, 0)


class TestLifecycleRoundTrips(unittest.TestCase):
    def test_created(self) -> None:
        state = create_lifecycle_state(
            mission_id=MISSION_ID, run_id=RUN_ID, created_at=FIXED_AT
        )
        restored, size = _roundtrip(state)
        self.assertEqual(restored.status, STATUS_CREATED)
        print(f"CREATED_SIZE={size}")

    def test_wait(self) -> None:
        state = run_constructor_lifecycle(
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            facility_scope=["ALL", FACILITY_TARGET],
            assemble_candidates=StubAssembler(),
            scope_reader=RecordingReader(),
            mission_id=MISSION_ID,
            run_id=RUN_ID,
            now=FIXED_AT,
        )
        self.assertEqual(state.status, STATUS_WAITING_FOR_HUMAN)
        restored, size = _roundtrip(state)
        self.assertEqual(restored.status, STATUS_WAITING_FOR_HUMAN)
        self.assertEqual(restored.error_code, CODE_AMBIGUOUS_SCOPE)
        self.assertEqual(restored.run_id, RUN_ID)
        self.assertEqual(restored.mission_id, MISSION_ID)
        print(f"WAIT_SIZE={size}")

    def test_ready_with_package_labor(self) -> None:
        state = run_constructor_lifecycle(
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            scope_reader=RecordingReader(),
            mission_id=MISSION_ID,
            run_id=RUN_ID,
            now=FIXED_AT,
        )
        self.assertEqual(state.status, STATUS_READY_FOR_HANDOFF)
        restored, size = _roundtrip(state)
        self.assertEqual(restored.status, STATUS_READY_FOR_HANDOFF)
        self.assertIsNotNone(restored.package)
        self.assertIsNotNone(restored.labor_resolutions)
        print(f"READY_SIZE={size}")

    def test_no_unsafe_objects_in_state(self) -> None:
        state = run_constructor_lifecycle(
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            assemble_candidates=StubAssembler(),
            scope_reader=RecordingReader(),
            mission_id=MISSION_ID,
            run_id=RUN_ID,
            now=FIXED_AT,
        )
        findings = _walk(state)
        self.assertEqual(findings, [])

    def test_secret_scan(self) -> None:
        state = run_constructor_lifecycle(
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            facility_scope=["ALL", FACILITY_TARGET],
            assemble_candidates=StubAssembler(),
            scope_reader=RecordingReader(),
            mission_id=MISSION_ID,
            run_id=RUN_ID,
            now=FIXED_AT,
        )
        serde = build_constructor_jsonplus_serializer()
        _, payload = serde.dumps_typed(state)
        text = payload.decode("latin-1", errors="ignore")
        self.assertIsNone(_SENSITIVE.search(text))

    def test_stale_after_resume_classification(self) -> None:
        wait = run_constructor_lifecycle(
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            facility_scope=["ALL", FACILITY_TARGET],
            assemble_candidates=StubAssembler(),
            scope_reader=RecordingReader(),
            mission_id=MISSION_ID,
            run_id=RUN_ID,
            now=FIXED_AT,
        )
        _, wait_size = _roundtrip(wait)
        req = build_decision_request_from_lifecycle(wait)
        cmd = build_resume_command(
            decision_id="dec-1",
            interrupt_id=req.interrupt_id,
            run_id=RUN_ID,
            mission_id=MISSION_ID,
            decision=DECISION_CLARIFY_SCOPE,
            actor_id="human-1",
            parameters={"facility_scope": [FACILITY_TARGET]},
            submitted_at=FIXED_AT,
        )
        resumed = apply_constructor_resume_command(
            wait,
            cmd,
            context=_context(),
            project_code=PROJECT,
            month_key=MONTH,
            now=FIXED_AT,
        )
        restored, _ = _roundtrip(resumed)
        self.assertIsNone(restored.reality_read)
        self.assertIsNone(restored.package)
        self.assertIsNone(restored.labor_resolutions)
        self.assertGreater(wait_size, 0)
        # Ensure we did not accidentally keep PACKAGE_BUILT semantics.
        self.assertNotEqual(restored.status, STATUS_PACKAGE_BUILT)


if __name__ == "__main__":
    unittest.main()
