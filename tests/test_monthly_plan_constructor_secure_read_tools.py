"""
Increment 3 — Constructor secure read adapters.

Controlled stubs only. No live Supabase. No Streamlit. No writes.
"""

from __future__ import annotations

import ast
import dataclasses
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from agents.monthly_plan_constructor.candidate_package import (
    CandidatePackage,
    build_candidate_package,
)
from agents.monthly_plan_constructor.mission_scope import (
    CODE_AMBIGUOUS_SCOPE,
    ConstructorMissionScope,
    build_constructor_mission_scope,
)
from agents.monthly_plan_constructor.secure_read_tools import (
    CODE_SECURITY_DENIED,
    ConstructorRealityRead,
    ConstructorRealityRow,
    ScopeReadCapabilities,
    SecureReadError,
    read_constructor_reality,
)
from security.agent_execution_context import (
    MPCA_ALLOWED_TOOLS,
    TOOL_LOAD_SCOPE,
    AgentExecutionContext,
    issue_read_only_agent_context,
)

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
OTHER_PROJECT = "PRJ_OTHER"
OTHER_MONTH = "август-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"
REPO = Path(__file__).resolve().parents[1]


def _mission(**overrides: object) -> ConstructorMissionScope:
    payload: dict[str, object] = {"project_code": PROJECT, "month_key": MONTH}
    payload.update(overrides)
    return build_constructor_mission_scope(**payload)  # type: ignore[arg-type]


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
        self.calls: list[tuple[str, ConstructorMissionScope]] = []

    def __call__(
        self,
        context: AgentExecutionContext,
        mission: ConstructorMissionScope,
    ) -> list[dict[str, object]]:
        self.calls.append((context.authorization_id, mission))
        return list(self.rows)


def _read(
    mission: ConstructorMissionScope | None = None,
    *,
    context: AgentExecutionContext | None = None,
    reader: RecordingReader | None = None,
    capabilities: ScopeReadCapabilities | None = None,
    **kwargs: object,
) -> ConstructorRealityRead:
    return read_constructor_reality(
        context or _context(),
        mission or _mission(),
        scope_reader=reader or RecordingReader(),
        capabilities=capabilities or ScopeReadCapabilities(),
        **kwargs,  # type: ignore[arg-type]
    )


class SecureReadAdapterTests(unittest.TestCase):
    def test_1_valid_authorized_project_month_read(self) -> None:
        result = _read()
        self.assertIsInstance(result, ConstructorRealityRead)
        self.assertEqual(result.project_code, PROJECT.upper())
        self.assertEqual(result.month_key, MONTH)
        self.assertEqual(result.row_count, 1)
        self.assertEqual(result.tool_name, TOOL_LOAD_SCOPE)

    def test_2_facility_scope_reaches_trusted_read(self) -> None:
        reader = RecordingReader([_raw()])
        mission = _mission(facility_scope=FACILITY_TARGET)
        _read(mission, reader=reader)
        self.assertEqual(len(reader.calls), 1)
        self.assertEqual(reader.calls[0][1].facility_scope, ("FACILITY_TARGET",))

    def test_3_discipline_scope_reaches_trusted_read(self) -> None:
        reader = RecordingReader([_raw()])
        mission = _mission(discipline_scope=DISCIPLINE_VENT)
        _read(mission, reader=reader)
        self.assertEqual(reader.calls[0][1].discipline_scope, ("ВЕНТИЛЯЦИЯ",))

    def test_4_facility_and_discipline_intersection(self) -> None:
        reader = RecordingReader(
            [
                _raw(boq_code="HIT"),
                _raw(
                    facility="OTHER",
                    facility_building="OTHER",
                    boq_code="MISS",
                ),
            ]
        )
        with self.assertRaises(SecureReadError):
            _read(
                _mission(
                    facility_scope=FACILITY_TARGET,
                    discipline_scope=DISCIPLINE_VENT,
                ),
                reader=reader,
            )
        ok = RecordingReader([_raw(boq_code="HIT")])
        result = _read(
            _mission(
                facility_scope=FACILITY_TARGET,
                discipline_scope=DISCIPLINE_VENT,
            ),
            reader=ok,
        )
        self.assertEqual(result.row_count, 1)
        self.assertEqual(result.rows[0].boq_code, "HIT")

    def test_5_system_scope_propagated(self) -> None:
        reader = RecordingReader([_raw(system="SYS-2", system_label="SYS-2")])
        mission = _mission(system_scope="SYS-2")
        result = _read(mission, reader=reader)
        self.assertEqual(reader.calls[0][1].system_scope, ("SYS-2",))
        self.assertEqual(result.rows[0].system, "SYS-2")

    def test_6_iwp_scope_propagated(self) -> None:
        reader = RecordingReader([_raw(iwp="IWP-9", iwp_id="IWP-9")])
        mission = _mission(iwp_scope="IWP-9")
        result = _read(mission, reader=reader)
        self.assertEqual(reader.calls[0][1].iwp_scope, ("IWP-9",))
        self.assertEqual(result.rows[0].iwp, "IWP-9")

    def test_7_queue_scope_propagated_when_supported(self) -> None:
        reader = RecordingReader(
            [_raw(queue="Q2", construction_queue="Q2")]
        )
        mission = _mission(queue_scope="Q2")
        result = _read(
            mission,
            reader=reader,
            capabilities=ScopeReadCapabilities(queue=True),
        )
        self.assertEqual(reader.calls[0][1].queue_scope, ("Q2",))
        self.assertEqual(result.rows[0].queue, "Q2")

    def test_8_mission_project_mismatch_fails_closed(self) -> None:
        with self.assertRaises(SecureReadError) as raised:
            _read(_mission(), context=_context(OTHER_PROJECT))
        self.assertEqual(raised.exception.code, CODE_SECURITY_DENIED)

    def test_9_unknown_facility_returns_zero_not_whole_project(self) -> None:
        reader = RecordingReader([])
        result = _read(_mission(facility_scope="UNKNOWN_FACILITY"), reader=reader)
        self.assertEqual(result.row_count, 0)
        self.assertEqual(result.rows, ())
        self.assertNotEqual(result.row_count, 447)

    def test_10_unsupported_queue_capability_fails_closed(self) -> None:
        reader = RecordingReader([_raw()])
        with self.assertRaises(SecureReadError) as raised:
            _read(
                _mission(queue_scope="Q1"),
                reader=reader,
                capabilities=ScopeReadCapabilities(queue=False),
            )
        self.assertEqual(raised.exception.code, CODE_AMBIGUOUS_SCOPE)
        self.assertEqual(reader.calls, [])

    def test_11_out_of_scope_row_from_executor_fails_closed(self) -> None:
        reader = RecordingReader(
            [
                _raw(),
                _raw(
                    facility="LEAK",
                    facility_building="LEAK",
                    boq_code="OUT",
                ),
            ]
        )
        with self.assertRaises(SecureReadError) as raised:
            _read(_mission(facility_scope=FACILITY_TARGET), reader=reader)
        self.assertIn("outside mission scope", str(raised.exception))

    def test_12_wrong_project_row_rejected(self) -> None:
        reader = RecordingReader([_raw(project_code=OTHER_PROJECT)])
        with self.assertRaises(SecureReadError):
            _read(reader=reader)

    def test_13_wrong_month_row_rejected(self) -> None:
        reader = RecordingReader([_raw(month_key=OTHER_MONTH)])
        with self.assertRaises(SecureReadError):
            _read(reader=reader)

    def test_14_tool_not_allowlisted_cannot_be_invoked(self) -> None:
        base = _context()
        denied = AgentExecutionContext(
            actor_id=base.actor_id,
            actor_type=base.actor_type,
            agent_code=base.agent_code,
            agent_version=base.agent_version,
            run_id=base.run_id,
            project_code=base.project_code,
            allowed_tools=tuple(
                tool for tool in MPCA_ALLOWED_TOOLS if tool != TOOL_LOAD_SCOPE
            ),
            permission_tier=base.permission_tier,
            authorization_id=base.authorization_id,
            issued_at=base.issued_at,
            expires_at=base.expires_at,
            security_policy_version=base.security_policy_version,
            write_allowed=False,
        )
        reader = RecordingReader()
        with self.assertRaises(SecureReadError) as raised:
            _read(context=denied, reader=reader)
        self.assertEqual(raised.exception.code, "TOOL_NOT_ALLOWED")
        self.assertEqual(reader.calls, [])

    def test_15_no_direct_service_bypass_path(self) -> None:
        source = (
            REPO / "agents" / "monthly_plan_constructor" / "secure_read_tools.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                for alias in node.names:
                    imported.add(f"{node.module}.{alias.name}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
        self.assertNotIn("services.monthly_plan_constructor_read_service", imported)
        self.assertNotIn(
            "services.monthly_plan_constructor_read_service.load_constructor_scope",
            imported,
        )
        self.assertNotIn(
            "services.monthly_plan_constructor_read_service.load_constructor_line_economics",
            imported,
        )
        self.assertNotIn("agents.monthly_plan_constructor.tools", imported)
        self.assertIn("load_constructor_line_economics", source)
        self.assertIn("NOT_AVAILABLE", source)

    def test_16_zero_row_valid_read(self) -> None:
        result = _read(reader=RecordingReader([]))
        self.assertEqual(result.row_count, 0)
        self.assertEqual(result.rows, ())

    def test_17_input_mission_not_mutated(self) -> None:
        mission = _mission(facility_scope=FACILITY_TARGET)
        before = dataclasses.asdict(mission)
        _read(mission, reader=RecordingReader([_raw()]))
        self.assertEqual(dataclasses.asdict(mission), before)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            mission.project_code = "HACK"  # type: ignore[misc]

    def test_18_read_provenance_present(self) -> None:
        context = _context()
        result = _read(
            context=context,
            reader=RecordingReader([_raw()]),
            read_at="2026-09-01T00:00:00Z",
        )
        self.assertTrue(result.read_id)
        self.assertEqual(result.read_at, "2026-09-01T00:00:00Z")
        self.assertEqual(result.provenance.tool_name, TOOL_LOAD_SCOPE)
        self.assertEqual(result.provenance.authorization_id, context.authorization_id)
        self.assertEqual(result.provenance.row_count, 1)
        self.assertEqual(result.snapshot_id, result.read_id)

    def test_19_public_result_is_not_dataframe(self) -> None:
        result = _read()
        self.assertNotIsInstance(result, pd.DataFrame)
        self.assertIsInstance(result.rows, tuple)
        self.assertIsInstance(result.rows[0], ConstructorRealityRow)
        for item in dataclasses.fields(result):
            self.assertFalse(isinstance(getattr(result, item.name), pd.DataFrame))

    def test_20_read_result_separate_from_candidate_package(self) -> None:
        result = _read()
        self.assertNotIsInstance(result, CandidatePackage)
        self.assertFalse(hasattr(result, "candidates"))
        package = build_candidate_package(
            _mission(),
            [
                {
                    "candidate_id": "C1",
                    "project_code": PROJECT,
                    "month_key": MONTH,
                    "facility": FACILITY_TARGET,
                    "discipline": DISCIPLINE_VENT,
                    "boq_code": "BOQ-001",
                    "available_to_add_qty": 1.0,
                }
            ],
            mission_id="m1",
            scanned_count=1,
        )
        self.assertIsInstance(package, CandidatePackage)
        self.assertNotEqual(type(result), type(package))

    def test_expired_context_fails_closed(self) -> None:
        base = _context()
        expired = AgentExecutionContext(
            actor_id=base.actor_id,
            actor_type=base.actor_type,
            agent_code=base.agent_code,
            agent_version=base.agent_version,
            run_id=base.run_id,
            project_code=base.project_code,
            allowed_tools=base.allowed_tools,
            permission_tier=base.permission_tier,
            authorization_id=base.authorization_id,
            issued_at=base.issued_at,
            expires_at=(datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
            security_policy_version=base.security_policy_version,
            write_allowed=False,
        )
        with self.assertRaises(SecureReadError) as raised:
            _read(context=expired, reader=RecordingReader())
        self.assertEqual(raised.exception.code, "CONTEXT_EXPIRED")


class Mpca003ReadRegressionTests(unittest.TestCase):
    def test_scoped_trusted_read_returns_17_not_447(self) -> None:
        target_n = 17
        rows: list[dict[str, object]] = []
        for i in range(target_n):
            rows.append(_raw(boq_code=f"T{i:03d}"))
        reader = RecordingReader(rows)
        mission = _mission(
            facility_scope=FACILITY_TARGET,
            discipline_scope=DISCIPLINE_VENT,
        )
        result = _read(mission, reader=reader)
        self.assertEqual(reader.calls[0][1].facility_scope, ("FACILITY_TARGET",))
        self.assertEqual(reader.calls[0][1].discipline_scope, ("ВЕНТИЛЯЦИЯ",))
        self.assertEqual(result.row_count, 17)
        self.assertNotEqual(result.row_count, 447)
        self.assertTrue(all(row.facility == FACILITY_TARGET for row in result.rows))
        self.assertTrue(all(row.discipline == DISCIPLINE_VENT for row in result.rows))


if __name__ == "__main__":
    unittest.main()
