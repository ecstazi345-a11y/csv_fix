"""
Increment 5 — Constructor Exception Engine capability.

Pure domain tests. No Streamlit, Supabase, LLM, SQL, or product writes.
"""

from __future__ import annotations

import importlib
import inspect
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_PROVISIONAL,
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
    CandidatePackage,
    build_candidate_package,
)
from agents.monthly_plan_constructor.exception_engine import (
    CODE_AMBIGUOUS_SCOPE,
    CODE_DATA_CONTRACT_BLOCKER,
    CODE_ENGINE_CONTRACT_BLOCKER,
    CODE_LABOR_NORM_UNRESOLVED,
    CODE_READ_FAILED,
    CODE_SECURITY_DENIED,
    ROUTE_CONTINUE,
    ROUTE_FAIL_RUN,
    ROUTE_WAIT_HUMAN,
    SCHEMA_VERSION,
    SEVERITY_BLOCKING,
    SEVERITY_NON_BLOCKING,
    SOURCE_CANDIDATE_PACKAGE,
    SOURCE_LABOR_NORM,
    SOURCE_MISSION_SCOPE,
    SOURCE_SECURE_READ,
    ConstructorException,
    ConstructorExceptionDetails,
    ConstructorExceptionSet,
    ExceptionEngineError,
    build_constructor_exception,
    build_exception_set,
    exception_from_failure,
    exceptions_from_labor_resolutions,
)
from agents.monthly_plan_constructor.labor_norm_resolver import (
    BASIS_NORMATIVE_BENCHMARK,
    BASIS_OBSERVED_PRODUCTIVITY,
    CODE_REJECTED_INCOMPATIBLE_UNIT,
    CODE_REJECTED_ZERO_NORM,
    HOURS_VALIDATED_PRODUCTIVE_DIRECT,
    LaborNormEvidence,
    REASON_AMBIGUOUS_LABOR_NORM_EVIDENCE,
    REASON_NO_ADMISSIBLE_EVIDENCE,
    SOURCE_OFFICIAL_NORMATIVE,
    SOURCE_PROJECT_HISTORY,
    resolve_labor_norms,
)
from agents.monthly_plan_constructor.mission_scope import (
    build_constructor_mission_scope,
)

PROJECT = "PRJ_001_БХК"
MONTH = "сентябрь-2026"
FACILITY_TARGET = "FACILITY_TARGET"
DISCIPLINE_VENT = "Вентиляция"
MISSION_ID = "mission-increment-5"
CANDIDATE_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-001"
OTHER_ID = "PRJ_001_БХК|СЕНТЯБРЬ-2026|FACILITY_TARGET|ВЕНТИЛЯЦИЯ|BOQ-002"
FIXED_AT = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)


def _mission():
    return build_constructor_mission_scope(project_code=PROJECT, month_key=MONTH)


def _candidate(**overrides: object) -> dict[str, object]:
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


def _package(candidates: list[dict[str, object]] | None = None) -> CandidatePackage:
    items = candidates if candidates is not None else [_candidate()]
    return build_candidate_package(
        _mission(),
        items,
        mission_id=MISSION_ID,
        scanned_count=len(items),
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


class TestArtifactContract(unittest.TestCase):
    def test_frozen_exception(self) -> None:
        item = exception_from_failure(
            CODE_DATA_CONTRACT_BLOCKER,
            source_capability=SOURCE_MISSION_SCOPE,
            reason="bad mission",
            observed_at=FIXED_AT,
        )
        with self.assertRaises(Exception):
            item.exception_code = "X"  # type: ignore[misc]

    def test_schema_version(self) -> None:
        item = exception_from_failure(
            CODE_READ_FAILED,
            source_capability=SOURCE_SECURE_READ,
            reason="read failed",
            observed_at=FIXED_AT,
        )
        self.assertEqual(item.schema_version, SCHEMA_VERSION)

    def test_observed_at_timezone_aware(self) -> None:
        item = exception_from_failure(
            CODE_AMBIGUOUS_SCOPE,
            source_capability=SOURCE_MISSION_SCOPE,
            reason="ambiguous",
            observed_at=FIXED_AT,
        )
        self.assertIsNotNone(item.observed_at.tzinfo)
        self.assertEqual(item.observed_at.utcoffset(), timezone.utc.utcoffset(None))

    def test_naive_observed_at_rejected(self) -> None:
        with self.assertRaises(ExceptionEngineError) as raised:
            build_constructor_exception(
                exception_code=CODE_DATA_CONTRACT_BLOCKER,
                reason="x",
                source_capability=SOURCE_MISSION_SCOPE,
                observed_at=datetime(2026, 8, 25, 12, 0, 0),
            )
        self.assertEqual(raised.exception.code, CODE_ENGINE_CONTRACT_BLOCKER)

    def test_closed_severity_route_source(self) -> None:
        item = exception_from_failure(
            CODE_AMBIGUOUS_SCOPE,
            source_capability=SOURCE_SECURE_READ,
            reason="queue not enforceable",
            observed_at=FIXED_AT,
        )
        self.assertEqual(item.severity, SEVERITY_BLOCKING)
        self.assertEqual(item.route, ROUTE_WAIT_HUMAN)
        self.assertEqual(item.source_capability, SOURCE_SECURE_READ)

    def test_no_dataframe_in_public_contract(self) -> None:
        source = Path(
            "agents/monthly_plan_constructor/exception_engine.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("import pandas", source)
        self.assertNotIn("DataFrame", inspect.signature(ConstructorException).parameters)
        self.assertNotIn("DataFrame", inspect.signature(ConstructorExceptionSet).parameters)


class TestNormalLaborPath(unittest.TestCase):
    def test_validated_no_exception(self) -> None:
        package = _package()
        result = resolve_labor_norms(package, [_history()])
        exc_set = exceptions_from_labor_resolutions(result, observed_at=FIXED_AT)
        self.assertEqual(exc_set.exceptions, ())
        self.assertEqual(exc_set.summary.blocking_count, 0)
        self.assertEqual(exc_set.summary.non_blocking_count, 0)
        self.assertTrue(exc_set.handoff_allowed())

    def test_provisional_no_exception(self) -> None:
        package = _package()
        result = resolve_labor_norms(package, [_normative()])
        exc_set = exceptions_from_labor_resolutions(result, observed_at=FIXED_AT)
        self.assertEqual(len(exc_set.exceptions), 0)
        self.assertEqual(result.resolutions[0].status, LABOR_PROVISIONAL)


class TestLaborUnresolved(unittest.TestCase):
    def test_unresolved_emits_labor_exception(self) -> None:
        package = _package()
        before_ids = [c.candidate_id for c in package.candidates]
        result = resolve_labor_norms(package, [])
        self.assertEqual(result.resolutions[0].status, LABOR_UNRESOLVED)
        exc_set = exceptions_from_labor_resolutions(result, observed_at=FIXED_AT)
        self.assertEqual(len(exc_set.exceptions), 1)
        item = exc_set.exceptions[0]
        self.assertEqual(item.exception_code, CODE_LABOR_NORM_UNRESOLVED)
        self.assertEqual(item.severity, SEVERITY_NON_BLOCKING)
        self.assertEqual(item.route, ROUTE_CONTINUE)
        self.assertEqual(item.candidate_id, CANDIDATE_ID)
        self.assertEqual(item.resolution_id, result.resolutions[0].resolution_id)
        self.assertEqual(item.package_id, package.package_id)
        self.assertEqual(
            item.details.resolution_reason, REASON_NO_ADMISSIBLE_EVIDENCE
        )
        self.assertEqual(item.details.resolution_status, LABOR_UNRESOLVED)
        # Candidate not deleted/mutated by exception engine
        self.assertEqual(
            [c.candidate_id for c in result.resolved_package.candidates],
            before_ids,
        )
        self.assertEqual(len(result.resolved_package.candidates), 1)

    def test_rejection_codes_preserved(self) -> None:
        package = _package()
        bad = _history(labor_hours_per_unit=0.0, evidence_id="ev-zero")
        result = resolve_labor_norms(package, [bad])
        exc_set = exceptions_from_labor_resolutions(result, observed_at=FIXED_AT)
        self.assertIn(
            CODE_REJECTED_ZERO_NORM,
            exc_set.exceptions[0].details.rejection_codes,
        )

    def test_ambiguity_ids_preserved(self) -> None:
        package = _package()
        a = _history(evidence_id="ev-a", labor_hours_per_unit=1.0)
        b = _history(evidence_id="ev-b", labor_hours_per_unit=9.0)
        result = resolve_labor_norms(package, [a, b])
        self.assertEqual(
            result.resolutions[0].resolution_reason,
            REASON_AMBIGUOUS_LABOR_NORM_EVIDENCE,
        )
        exc_set = exceptions_from_labor_resolutions(result, observed_at=FIXED_AT)
        self.assertEqual(
            set(exc_set.exceptions[0].details.ambiguity_evidence_ids),
            {"ev-a", "ev-b"},
        )

    def test_incompatible_unit_rejection_preserved(self) -> None:
        package = _package()
        bad = _history(unit="шт", evidence_id="ev-unit")
        result = resolve_labor_norms(package, [bad])
        exc_set = exceptions_from_labor_resolutions(result, observed_at=FIXED_AT)
        self.assertIn(
            CODE_REJECTED_INCOMPATIBLE_UNIT,
            exc_set.exceptions[0].details.rejection_codes,
        )


class TestHardFailureMapping(unittest.TestCase):
    def test_data_contract_blocker(self) -> None:
        item = exception_from_failure(
            CODE_DATA_CONTRACT_BLOCKER,
            source_capability=SOURCE_CANDIDATE_PACKAGE,
            reason="duplicate candidate_id",
            observed_at=FIXED_AT,
        )
        self.assertEqual(item.exception_code, CODE_DATA_CONTRACT_BLOCKER)
        self.assertEqual(item.severity, SEVERITY_BLOCKING)
        self.assertEqual(item.route, ROUTE_FAIL_RUN)

    def test_ambiguous_scope(self) -> None:
        item = exception_from_failure(
            CODE_AMBIGUOUS_SCOPE,
            source_capability=SOURCE_MISSION_SCOPE,
            reason="ALL mixed with values",
            observed_at=FIXED_AT,
        )
        self.assertEqual(item.severity, SEVERITY_BLOCKING)
        self.assertEqual(item.route, ROUTE_WAIT_HUMAN)

    def test_security_denied(self) -> None:
        item = exception_from_failure(
            CODE_SECURITY_DENIED,
            source_capability=SOURCE_SECURE_READ,
            reason="project mismatch",
            observed_at=FIXED_AT,
        )
        self.assertEqual(item.severity, SEVERITY_BLOCKING)
        self.assertEqual(item.route, ROUTE_FAIL_RUN)

    def test_read_failed(self) -> None:
        item = exception_from_failure(
            CODE_READ_FAILED,
            source_capability=SOURCE_SECURE_READ,
            reason="executor error",
            observed_at=FIXED_AT,
        )
        self.assertEqual(item.exception_code, CODE_READ_FAILED)
        self.assertEqual(item.severity, SEVERITY_BLOCKING)
        self.assertEqual(item.route, ROUTE_FAIL_RUN)


class TestSecurityNormalization(unittest.TestCase):
    def test_tool_not_allowed(self) -> None:
        item = exception_from_failure(
            "TOOL_NOT_ALLOWED",
            source_capability=SOURCE_SECURE_READ,
            reason="tool denied",
            observed_at=FIXED_AT,
        )
        self.assertEqual(item.exception_code, CODE_SECURITY_DENIED)
        self.assertEqual(item.details.original_failure_code, "TOOL_NOT_ALLOWED")
        self.assertEqual(item.severity, SEVERITY_BLOCKING)
        self.assertEqual(item.route, ROUTE_FAIL_RUN)

    def test_context_expired(self) -> None:
        item = exception_from_failure(
            "CONTEXT_EXPIRED",
            source_capability=SOURCE_SECURE_READ,
            reason="expired",
            observed_at=FIXED_AT,
        )
        self.assertEqual(item.exception_code, CODE_SECURITY_DENIED)
        self.assertEqual(item.details.original_failure_code, "CONTEXT_EXPIRED")
        self.assertEqual(item.route, ROUTE_FAIL_RUN)

    def test_context_missing(self) -> None:
        item = exception_from_failure(
            "CONTEXT_MISSING",
            source_capability=SOURCE_SECURE_READ,
            reason="missing",
            observed_at=FIXED_AT,
        )
        self.assertEqual(item.exception_code, CODE_SECURITY_DENIED)
        self.assertEqual(item.details.original_failure_code, "CONTEXT_MISSING")
        self.assertEqual(item.severity, SEVERITY_BLOCKING)

    def test_security_cannot_downgrade(self) -> None:
        with self.assertRaises(ExceptionEngineError):
            build_constructor_exception(
                exception_code=CODE_SECURITY_DENIED,
                reason="x",
                source_capability=SOURCE_SECURE_READ,
                severity=SEVERITY_NON_BLOCKING,
                route=ROUTE_CONTINUE,
                observed_at=FIXED_AT,
            )


class TestUnknownFailureCode(unittest.TestCase):
    def test_unknown_fails_closed(self) -> None:
        with self.assertRaises(ExceptionEngineError) as raised:
            exception_from_failure(
                "STALE_REALITY",
                source_capability=SOURCE_SECURE_READ,
                reason="not active in increment 5",
                observed_at=FIXED_AT,
            )
        self.assertEqual(raised.exception.code, CODE_ENGINE_CONTRACT_BLOCKER)

    def test_unknown_never_warning_continue(self) -> None:
        with self.assertRaises(ExceptionEngineError):
            exception_from_failure(
                "SOME_RANDOM_CODE",
                source_capability=SOURCE_MISSION_SCOPE,
                reason="nope",
                observed_at=FIXED_AT,
            )


class TestExceptionSet(unittest.TestCase):
    def test_empty_handoff_allowed(self) -> None:
        empty = build_exception_set(())
        self.assertTrue(empty.handoff_allowed())
        self.assertEqual(empty.codes(), ())
        self.assertEqual(empty.blocking(), ())
        self.assertEqual(empty.summary.blocking_count, 0)

    def test_labor_only_handoff_allowed(self) -> None:
        package = _package()
        result = resolve_labor_norms(package, [])
        exc_set = exceptions_from_labor_resolutions(result, observed_at=FIXED_AT)
        self.assertTrue(exc_set.handoff_allowed())
        self.assertEqual(exc_set.summary.non_blocking_count, 1)
        self.assertEqual(exc_set.summary.blocking_count, 0)

    def test_blocking_blocks_handoff(self) -> None:
        item = exception_from_failure(
            CODE_SECURITY_DENIED,
            source_capability=SOURCE_SECURE_READ,
            reason="denied",
            observed_at=FIXED_AT,
        )
        exc_set = build_exception_set([item])
        self.assertFalse(exc_set.handoff_allowed())
        self.assertEqual(len(exc_set.blocking()), 1)
        self.assertEqual(exc_set.codes(), (CODE_SECURITY_DENIED,))

    def test_duplicate_collapse(self) -> None:
        a = exception_from_failure(
            CODE_DATA_CONTRACT_BLOCKER,
            source_capability=SOURCE_MISSION_SCOPE,
            reason="first",
            package_id="pkg-1",
            candidate_id="c1",
            observed_at=FIXED_AT,
        )
        b = exception_from_failure(
            CODE_DATA_CONTRACT_BLOCKER,
            source_capability=SOURCE_MISSION_SCOPE,
            reason="second duplicate",
            package_id="pkg-1",
            candidate_id="c1",
            observed_at=FIXED_AT,
        )
        exc_set = build_exception_set([a, b])
        self.assertEqual(len(exc_set.exceptions), 1)
        self.assertEqual(exc_set.exceptions[0].reason, "first")

    def test_distinct_candidates_remain_distinct(self) -> None:
        package = _package(
            [
                _candidate(candidate_id=CANDIDATE_ID, boq_code="BOQ-001"),
                _candidate(candidate_id=OTHER_ID, boq_code="BOQ-002"),
            ]
        )
        result = resolve_labor_norms(package, [])
        exc_set = exceptions_from_labor_resolutions(result, observed_at=FIXED_AT)
        self.assertEqual(len(exc_set.exceptions), 2)
        ids = {item.candidate_id for item in exc_set.exceptions}
        self.assertEqual(ids, {CANDIDATE_ID, OTHER_ID})

    def test_mixed_counts(self) -> None:
        labor = exceptions_from_labor_resolutions(
            resolve_labor_norms(_package(), []),
            observed_at=FIXED_AT,
        ).exceptions[0]
        blocking = exception_from_failure(
            CODE_AMBIGUOUS_SCOPE,
            source_capability=SOURCE_MISSION_SCOPE,
            reason="ambiguous",
            observed_at=FIXED_AT,
        )
        exc_set = build_exception_set([labor, blocking])
        self.assertEqual(exc_set.summary.blocking_count, 1)
        self.assertEqual(exc_set.summary.non_blocking_count, 1)
        self.assertFalse(exc_set.handoff_allowed())


class TestArchitectureIsolation(unittest.TestCase):
    def test_module_source_isolation(self) -> None:
        source = Path(
            "agents/monthly_plan_constructor/exception_engine.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "import streamlit",
            "from streamlit",
            "import langgraph",
            "from langgraph",
            "import openai",
            "from openai",
            "import supabase",
            "from supabase",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("mpca_002", source.lower())
        self.assertNotIn("mpca_003", source.lower())
        self.assertNotIn("from agents.monthly_plan_constructor.domain", source)
        self.assertNotIn("from agents.monthly_plan_constructor.runtime", source)

    def test_import_does_not_pull_streamlit(self) -> None:
        mod = importlib.import_module(
            "agents.monthly_plan_constructor.exception_engine"
        )
        self.assertTrue(hasattr(mod, "exceptions_from_labor_resolutions"))
        self.assertNotIn("streamlit", mod.__dict__)

    def test_details_are_data_only(self) -> None:
        details = ConstructorExceptionDetails(
            original_failure_code="TOOL_NOT_ALLOWED",
            rejection_codes=("REJECTED_ZERO_NORM",),
            ambiguity_evidence_ids=("ev-a",),
            resolution_reason=REASON_NO_ADMISSIBLE_EVIDENCE,
            resolution_status=LABOR_UNRESOLVED,
        )
        item = build_constructor_exception(
            exception_code=CODE_LABOR_NORM_UNRESOLVED,
            reason="unresolved",
            source_capability=SOURCE_LABOR_NORM,
            observed_at=FIXED_AT,
            details=details,
        )
        self.assertIsInstance(item.details.rejection_codes, tuple)
        self.assertNotIn("prompt", item.reason.lower())


if __name__ == "__main__":
    unittest.main()
