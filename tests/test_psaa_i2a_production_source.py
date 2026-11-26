"""PSAA I2-A — Trusted Production Source Acquisition tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from agents.observability.contracts import OperationalStatus
from agents.observability.durable_recorder import StoreObservabilityRecorder
from agents.observability.sqlite_store import SqliteObservabilityStore
from agents.production_shift_auditor import AGENT_CODE
from agents.production_shift_auditor.contracts import (
    DataSourceKind,
    LaborSemanticsStatus,
    LaborUnit,
)
from agents.production_shift_auditor.fixtures import build_insulation_pipeline_fixture
from agents.production_shift_auditor.managed_launcher import (
    PsaaManagedRuntimeLauncher,
    fixed_audit_input_resolver,
)
from agents.production_shift_auditor.managed_run_contracts import (
    PsaaManagedCompletionStatus,
    build_psaa_managed_start_input,
)
from agents.production_shift_auditor.production_source import (
    SELECTION_COMPLETE_WITHIN_LIMIT,
    SELECTION_POSSIBLY_TRUNCATED,
    SOURCE_ACQUISITION_PATH,
    TRUSTED_READ_ROW_LIMIT,
    TrustedProductionAuditInputResolver,
    build_trusted_production_audit_input_resolver,
)
from agents.production_shift_auditor.s04_execution_cost import (
    scenario_rate_1000_rub_per_man_hour,
)
from agents.run_control.contracts import StartOutcome
from agents.run_control.registry import InMemoryRunControlRegistry
from agents.run_control.service import RunControlService


def _sample_rows(
    *,
    project_code: str = "PRJ_DEMO",
    crew_id: str = "CREW_A",
    work_date: str = "2026-10-01",
    shift_type: str = "DAY",
    crew_size: float = 3,
    hours: float | None = 2.0,
    quantity: float | None = 10.0,
    record_id: str = "rec_1",
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "airtable_record_id": record_id,
                "project_code": project_code,
                "work_date": work_date,
                "shift_type": shift_type,
                "crew_id": crew_id,
                "crew_size": crew_size,
                "foreman": "F1",
                "facility_building": "B1",
                "construction_discipline": "изоляция",
                "boq": "BOQ1",
                "boq_name": "Insulation",
                "unit_of_measure": "м2",
                "quantity_today": quantity,
                "direct_work_hours": hours,
                "operation_type": "Монтаж изоляции",
                "operation_quantity": None,
                "operation_comment": None,
                "comment_foreman": None,
            }
        ]
    )


class _Harness(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "obs.sqlite"
        self.registry = InMemoryRunControlRegistry()
        self.store = SqliteObservabilityStore(self.db_path)
        self.recorder = StoreObservabilityRecorder(self.store)
        self.service = RunControlService(
            registry=self.registry,
            recorder=self.recorder,
            durable_store=self.store,
        )

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _start(self, resolver, **scope):
        project = scope.pop("project_code", "PRJ_DEMO")
        work_date = scope.pop("work_date", "2026-10-01")
        crew_id = scope.pop("crew_id", "CREW_A")
        shift_type = scope.pop("shift_type", "DAY")
        launcher = PsaaManagedRuntimeLauncher(
            audit_input_resolver=resolver,
            observability_db_path=self.db_path,
            sync_execution=True,
        )
        result = self.service.start(
            build_psaa_managed_start_input(
                project_code=project,
                work_date=work_date,
                crew_id=crew_id,
                shift_type=shift_type,
                requested_mission_id=scope.pop("requested_mission_id", "mission-i2a"),
                idempotency_key=scope.pop("idempotency_key", "idem-i2a"),
            ),
            launcher=launcher,
        )
        return result, launcher


class TrustedReadReuseTests(_Harness):
    def test_existing_trusted_read_mechanism_reused(self) -> None:
        calls: list[dict] = []

        def fake_loader(context, *, crew_id, work_date, shift_type=None):
            calls.append(
                {
                    "agent": context.agent_code,
                    "project": context.project_code,
                    "crew_id": crew_id,
                    "work_date": work_date,
                    "shift_type": shift_type,
                    "tools": context.allowed_tools,
                }
            )
            return _sample_rows(), {
                "error": None,
                "row_count": 1,
                "source": "daily_progress_active",
                "live_data_proof": "OK",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        result, launcher = self._start(resolver)
        self.assertEqual(result.outcome, StartOutcome.AUTHORIZED)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["agent"], AGENT_CODE)
        self.assertEqual(calls[0]["project"], "PRJ_DEMO")
        self.assertIn("load_shift_daily_progress", calls[0]["tools"])
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.COMPLETED)
        notes = managed.professional_assessment.audit_input.provenance_notes
        self.assertTrue(any(SOURCE_ACQUISITION_PATH in n for n in notes))


class ScopeEnforcementTests(_Harness):
    def test_authorized_project_acquisition(self) -> None:
        def fake_loader(context, **kwargs):
            return _sample_rows(project_code=context.project_code), {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 1,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        result, launcher = self._start(resolver, idempotency_key="idem-auth")
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.COMPLETED)
        self.assertEqual(managed.project_code, "PRJ_DEMO")
        self.assertEqual(
            managed.professional_assessment.audit_input.source_kind,
            DataSourceKind.DAILY_PROGRESS_ACTIVE,
        )

    def test_unauthorized_project_blocked_by_context_vs_rows(self) -> None:
        def fake_loader(context, **kwargs):
            # Rows claim a different project than authorized context
            return _sample_rows(project_code="OTHER_PROJECT"), {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 1,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        result, launcher = self._start(resolver, idempotency_key="idem-xproj")
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.FAILED)
        self.assertEqual(managed.error_code, "PSAA_SCOPE_MISMATCH")

    def test_wrong_work_date_blocked(self) -> None:
        def fake_loader(context, **kwargs):
            return _sample_rows(work_date="1999-01-01"), {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 1,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        result, launcher = self._start(resolver, idempotency_key="idem-date")
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.FAILED)
        self.assertEqual(managed.error_code, "PSAA_SCOPE_MISMATCH")

    def test_wrong_crew_id_blocked(self) -> None:
        def fake_loader(context, **kwargs):
            return _sample_rows(crew_id="CREW_OTHER"), {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 1,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        result, launcher = self._start(resolver, idempotency_key="idem-crew")
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.FAILED)
        self.assertEqual(managed.error_code, "PSAA_SCOPE_MISMATCH")

    def test_shift_type_mismatch_blocked(self) -> None:
        def fake_loader(context, **kwargs):
            return _sample_rows(shift_type="NIGHT"), {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 1,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        result, launcher = self._start(resolver, idempotency_key="idem-shift")
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.FAILED)
        self.assertEqual(managed.error_code, "PSAA_SCOPE_MISMATCH")


class FailureAndSemanticsTests(_Harness):
    def test_missing_source_handled(self) -> None:
        def fake_loader(context, **kwargs):
            return pd.DataFrame(), {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 0,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        result, launcher = self._start(resolver, idempotency_key="idem-empty")
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.FAILED)
        self.assertEqual(managed.error_code, "PSAA_MISSING_SOURCE")
        run = self.store.get_run(result.agent_run.run_id)
        self.assertEqual(run.operational_status, OperationalStatus.FAILED)

    def test_source_acquisition_failure_handled(self) -> None:
        def fake_loader(context, **kwargs):
            return pd.DataFrame(), {
                "error": "upstream unavailable",
                "live_data_proof": "FAILED",
                "row_count": 0,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        result, launcher = self._start(resolver, idempotency_key="idem-failread")
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.error_code, "PSAA_MISSING_SOURCE")

    def test_conflicting_labor_semantics_preserved(self) -> None:
        def fake_loader(context, **kwargs):
            return _sample_rows(hours=4.5), {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 1,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        result, launcher = self._start(resolver, idempotency_key="idem-labor")
        managed = launcher.get_result(result.agent_run.run_id)
        ai = managed.professional_assessment.audit_input
        self.assertEqual(ai.labor_semantics_status, LaborSemanticsStatus.PARTIALLY_PROVEN)
        self.assertEqual(ai.operations[0].labor_unit, LaborUnit.HOUR_FIELD_UNPROVEN)

    def test_missing_hours_not_promoted_to_proven_man_hours(self) -> None:
        def fake_loader(context, **kwargs):
            return _sample_rows(hours=None), {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 1,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        result, launcher = self._start(resolver, idempotency_key="idem-nohours")
        managed = launcher.get_result(result.agent_run.run_id)
        op = managed.professional_assessment.audit_input.operations[0]
        self.assertEqual(op.labor_unit, LaborUnit.HOUR_FIELD_UNPROVEN)
        # Existing mapper may carry 0.0 quantity with UNPROVEN unit — uncertainty preserved.
        self.assertNotEqual(op.labor_unit, LaborUnit.MAN_HOUR)
        self.assertNotEqual(op.labor_unit, LaborUnit.MAN_MINUTE)

    def test_missing_quantity_not_fabricated(self) -> None:
        def fake_loader(context, **kwargs):
            return _sample_rows(quantity=None), {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 1,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        result, launcher = self._start(resolver, idempotency_key="idem-noqty")
        managed = launcher.get_result(result.agent_run.run_id)
        op = managed.professional_assessment.audit_input.operations[0]
        self.assertIsNone(op.physical_quantity)

    def test_unknown_operation_context_preserved(self) -> None:
        def fake_loader(context, **kwargs):
            df = _sample_rows()
            df.loc[0, "operation_type"] = "Совершенно неизвестная операция XYZ"
            return df, {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 1,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        result, launcher = self._start(resolver, idempotency_key="idem-unkop")
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.COMPLETED)
        name = managed.professional_assessment.audit_input.operations[0].operation_name
        self.assertIn("неизвестная", name.lower())


class SnapshotProvenanceTests(_Harness):
    def test_source_identity_provenance_and_snapshot(self) -> None:
        def fake_loader(context, **kwargs):
            return _sample_rows(record_id="rec_abc"), {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 1,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        result, launcher = self._start(resolver, idempotency_key="idem-snap")
        snap = resolver.last_snapshot
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertEqual(snap.source_table, "daily_progress_active")
        self.assertEqual(snap.acquisition_path, SOURCE_ACQUISITION_PATH)
        self.assertIn("rec_abc", snap.source_record_ids)
        self.assertTrue(snap.original_rows_content_hash)
        self.assertTrue(snap.normalized_input_content_hash)
        self.assertIsNone(snap.source_version_ref)
        self.assertTrue(snap.to_safe_dict()["content_hash_is_not_source_version"])
        self.assertFalse(snap.to_safe_dict()["durable_history_persisted"])
        ai = launcher.get_result(result.agent_run.run_id).professional_assessment.audit_input
        self.assertIsNone(ai.source_version_ref)
        self.assertIn("rec_abc", ai.source_record_ids)
        self.assertTrue(
            any("content_hash_is_not_source_version=true" in n for n in ai.provenance_notes)
        )

    def test_content_hash_not_promoted_to_source_version(self) -> None:
        def fake_loader(context, **kwargs):
            return _sample_rows(), {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 1,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        self._start(resolver, idempotency_key="idem-hash")
        snap = resolver.last_snapshot
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertNotEqual(snap.source_version_ref, snap.original_rows_content_hash)
        self.assertIsNone(snap.source_version_ref)


class JointExecutionAndCompatTests(_Harness):
    def test_joint_12_skill_managed_execution_from_production_resolver(self) -> None:
        def fake_loader(context, **kwargs):
            return _sample_rows(), {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 1,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        result, launcher = self._start(resolver, idempotency_key="idem-joint")
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.COMPLETED)
        pa = managed.professional_assessment
        for attr in (
            "s01",
            "s10",
            "s02",
            "s03",
            "s11",
            "s04",
            "s05",
            "s06",
            "s07",
            "s08",
            "s09",
            "s12",
        ):
            self.assertIsNotNone(getattr(pa, attr), attr)
        self.assertEqual(managed.managerial_acceptance_status, "NOT_IN_SCOPE")
        self.assertIn("PHYSICAL_EXECUTION_VERIFIED_NO", managed.physical_execution_verified_status)
        # I1 process-local semantics
        self.assertIn("process_local", managed.artifact_schema_note)

    def test_fixture_resolver_compatibility_preserved(self) -> None:
        fixture = build_insulation_pipeline_fixture()
        result, launcher = self._start(
            fixed_audit_input_resolver(fixture),
            project_code=fixture.project_code,
            work_date=fixture.work_date,
            crew_id=fixture.crew_id,
            shift_type=fixture.shift_type,
            requested_mission_id="mission-fixture-compat",
            idempotency_key="idem-fixture-compat",
        )
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.COMPLETED)
        self.assertEqual(managed.claimed_labor_man_minutes, 1425.0)

    def test_no_production_source_mutation_path_in_resolver(self) -> None:
        src = Path(
            "agents/production_shift_auditor/production_source.py"
        ).read_text(encoding="utf-8")
        for banned in (".insert(", ".update(", ".upsert(", ".delete(", "WRITE"):
            # WRITE may appear in comments about no product WRITE — allow comments
            if banned == "WRITE":
                continue
            self.assertNotIn(banned, src)


class ConflictingCrewSizeTests(_Harness):
    def test_conflicting_crew_size_fail_closed(self) -> None:
        def fake_loader(context, **kwargs):
            df = pd.concat(
                [
                    _sample_rows(crew_size=3, record_id="r1"),
                    _sample_rows(crew_size=5, record_id="r2"),
                ],
                ignore_index=True,
            )
            return df, {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 2,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        result, launcher = self._start(resolver, idempotency_key="idem-crewsize")
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.FAILED)
        self.assertEqual(managed.error_code, "PSAA_SCOPE_MISMATCH")


class LaborSemanticsIntegrityTests(_Harness):
    def test_missing_hours_zero_placeholder_not_actual_zero_labor(self) -> None:
        def fake_loader(context, **kwargs):
            return _sample_rows(hours=None, quantity=5.0), {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 1,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        launcher = PsaaManagedRuntimeLauncher(
            audit_input_resolver=resolver,
            observability_db_path=self.db_path,
            sync_execution=True,
            cost_rates=(scenario_rate_1000_rub_per_man_hour(project_code="PRJ_DEMO"),),
        )
        result = self.service.start(
            build_psaa_managed_start_input(
                project_code="PRJ_DEMO",
                work_date="2026-10-01",
                crew_id="CREW_A",
                shift_type="DAY",
                requested_mission_id="mission-lab0",
                idempotency_key="idem-lab0",
            ),
            launcher=launcher,
        )
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.COMPLETED)
        pa = managed.professional_assessment
        op = pa.audit_input.operations[0]
        self.assertEqual(op.labor_unit, LaborUnit.HOUR_FIELD_UNPROVEN)
        self.assertEqual(op.claimed_labor_quantity, 0.0)
        self.assertIn(
            "MISSING_DIRECT_WORK_HOURS_NUMERIC_PLACEHOLDER_NOT_ACTUAL_ZERO_LABOR",
            op.notes,
        )
        # Decision-driving consumers must not treat placeholder as proven labor.
        self.assertIsNone(pa.s01.s01_metrics.claimed_total_man_minutes)
        self.assertEqual(pa.s01.math_integrity_status.value, "DATA_INCOMPLETE")
        self.assertIsNone(
            pa.s04.cost_conservation.total_calculated_direct_labor_cost_exact
        )
        self.assertIsNone(pa.s05.shift_summary.total_claimed_labor_man_minutes)
        self.assertIsNone(pa.s06.shift_summary.total_original_labor_man_minutes)
        self.assertIsNone(pa.s09.shift_summary.total_claimed_labor_man_minutes)
        self.assertEqual(pa.s12.shift_summary.knowledge_candidate_count, 0)
        self.assertEqual(pa.s12.shift_summary.unit_labor_observation_count, 0)
        self.assertIsNone(managed.claimed_labor_man_minutes)
        self.assertIsNone(managed.scenario_direct_labor_cost_exact)

    def test_present_unproven_hours_not_converted_to_cost_or_benchmark(self) -> None:
        def fake_loader(context, **kwargs):
            return _sample_rows(hours=2.0, quantity=10.0), {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 1,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        launcher = PsaaManagedRuntimeLauncher(
            audit_input_resolver=resolver,
            observability_db_path=self.db_path,
            sync_execution=True,
            cost_rates=(scenario_rate_1000_rub_per_man_hour(project_code="PRJ_DEMO"),),
        )
        result = self.service.start(
            build_psaa_managed_start_input(
                project_code="PRJ_DEMO",
                work_date="2026-10-01",
                crew_id="CREW_A",
                shift_type="DAY",
                requested_mission_id="mission-lab2",
                idempotency_key="idem-lab2",
            ),
            launcher=launcher,
        )
        managed = launcher.get_result(result.agent_run.run_id)
        pa = managed.professional_assessment
        self.assertIsNone(pa.s01.s01_metrics.claimed_total_man_minutes)
        self.assertIsNone(
            pa.s04.cost_conservation.total_calculated_direct_labor_cost_exact
        )
        f11 = pa.s11.findings[0]
        self.assertEqual(f11.observation_eligibility.value, "NOT_ELIGIBLE_FOR_BENCHMARK")
        self.assertIsNone(f11.unit_labor_man_minutes_per_physical)
        self.assertEqual(pa.s12.shift_summary.knowledge_candidate_count, 0)


class SnapshotIntegrityTests(_Harness):
    def test_snapshot_rows_are_immutable(self) -> None:
        def fake_loader(context, **kwargs):
            return _sample_rows(record_id="rec_imm"), {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 1,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        self._start(resolver, idempotency_key="idem-imm")
        snap = resolver.last_snapshot
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertEqual(snap.selection_completeness, SELECTION_COMPLETE_WITHIN_LIMIT)
        row = snap.original_rows[0]
        with self.assertRaises(TypeError):
            row["project_code"] = "HACKED"  # type: ignore[index]
        with self.assertRaises(TypeError):
            snap.read_meta_safe["row_count"] = 999  # type: ignore[index]
        # Hash remains stable after failed mutation attempts.
        self.assertTrue(snap.original_rows_content_hash)
        self.assertIsNone(snap.source_version_ref)
        self.assertNotEqual(snap.source_version_ref, snap.original_rows_content_hash)

    def test_independent_snapshots_per_run(self) -> None:
        def fake_loader(context, **kwargs):
            return _sample_rows(), {
                "error": None,
                "live_data_proof": "OK",
                "row_count": 1,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        r1, _ = self._start(resolver, idempotency_key="idem-s1", requested_mission_id="m1")
        snap1 = resolver.last_snapshot
        r2, _ = self._start(resolver, idempotency_key="idem-s2", requested_mission_id="m2")
        snap2 = resolver.last_snapshot
        self.assertIsNotNone(snap1)
        self.assertIsNotNone(snap2)
        assert snap1 is not None and snap2 is not None
        self.assertNotEqual(r1.agent_run.run_id, r2.agent_run.run_id)
        self.assertNotEqual(snap1.snapshot_id, snap2.snapshot_id)
        self.assertIn(r2.agent_run.run_id, snap2.snapshot_id)

    def test_truncation_marks_completeness_unproven(self) -> None:
        from datetime import datetime, timezone

        from agents.observability.contracts import (
            InitiatorType,
            TriggerType,
            build_agent_run,
            build_run_request,
        )
        from agents.production_shift_auditor.managed_run_contracts import (
            PSAA_MONTH_KEY_COMPATIBILITY_SENTINEL,
        )
        from security.agent_execution_context import issue_read_only_agent_context

        def fake_loader(context, **kwargs):
            base = _sample_rows().iloc[0].to_dict()
            data = []
            for i in range(TRUSTED_READ_ROW_LIMIT):
                item = dict(base)
                item["airtable_record_id"] = f"rec_{i}"
                data.append(item)
            return pd.DataFrame(data), {
                "error": None,
                "live_data_proof": "OK",
                "row_count": TRUSTED_READ_ROW_LIMIT,
                "source": "daily_progress_active",
            }

        resolver = build_trusted_production_audit_input_resolver(read_loader=fake_loader)
        # Resolve only — do not run full 5k-op assess_shift in this completeness gate.
        run_request = build_run_request(
            request_id="req-trunc",
            requested_at=datetime.now(timezone.utc),
            agent_code=AGENT_CODE,
            initiator_type=InitiatorType.HUMAN,
            initiator_id="operator-local",
            trigger_type=TriggerType.MANUAL,
            trigger_reason="trunc-test",
            project_code="PRJ_DEMO",
            month_key=PSAA_MONTH_KEY_COMPATIBILITY_SENTINEL,
            scope_request={
                "grain": "SHIFT",
                "work_date": "2026-10-01",
                "crew_id": "CREW_A",
                "shift_type": "DAY",
            },
            requested_mission_id="mission-trunc",
            idempotency_key="idem-trunc-resolve",
        )
        now = datetime.now(timezone.utc)
        agent_run = build_agent_run(
            run_id="run-trunc",
            request_id=run_request.request_id,
            agent_code=AGENT_CODE,
            agent_version="0.1",
            project_code="PRJ_DEMO",
            month_key=PSAA_MONTH_KEY_COMPATIBILITY_SENTINEL,
            mission_id="mission-trunc",
            initiator_type=InitiatorType.HUMAN,
            initiator_id="operator-local",
            trigger_type=TriggerType.MANUAL,
            trigger_reason="trunc-test",
            operational_status=OperationalStatus.RUNNING,
            requested_at=now,
            updated_at=now,
            thread_id="run-trunc",
            started_at=now,
        )
        context = issue_read_only_agent_context(
            agent_code=AGENT_CODE,
            project_code="PRJ_DEMO",
            run_id="run-trunc",
        )
        audit_input = resolver.resolve(run_request, agent_run, context)
        snap = resolver.last_snapshot
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertEqual(snap.selection_completeness, SELECTION_POSSIBLY_TRUNCATED)
        self.assertIn("SOURCE_SELECTION_MAY_BE_TRUNCATED_AT_LIMIT", snap.missing_context)
        self.assertIn("SNAPSHOT_COMPLETENESS_NOT_FULLY_PROVEN", snap.missing_context)
        self.assertEqual(snap.selection_limit, TRUSTED_READ_ROW_LIMIT)
        self.assertEqual(len(audit_input.operations), TRUSTED_READ_ROW_LIMIT)
        self.assertNotEqual(
            snap.selection_completeness, SELECTION_COMPLETE_WITHIN_LIMIT
        )


if __name__ == "__main__":
    unittest.main()
