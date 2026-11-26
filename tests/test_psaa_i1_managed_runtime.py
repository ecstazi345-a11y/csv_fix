"""PSAA I1 — Managed Runtime Integration tests (Final Verification Gate)."""

from __future__ import annotations

import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from agents.control_room.query_port import AgentControlRoomQueryPort
from agents.observability.contracts import (
    EventType,
    InitiatorType,
    OperationalStatus,
    TriggerType,
    _unfreeze_jsonable,
)
from agents.observability.durable_recorder import StoreObservabilityRecorder
from agents.observability.sqlite_store import SqliteObservabilityStore
from agents.production_shift_auditor import AGENT_CODE
from agents.production_shift_auditor.fixtures import build_insulation_pipeline_fixture
from agents.production_shift_auditor.managed_launcher import (
    PsaaManagedRuntimeLauncher,
    fixed_audit_input_resolver,
)
from agents.production_shift_auditor.managed_run_contracts import (
    PSAA_MONTH_KEY_COMPATIBILITY_SENTINEL,
    PsaaManagedCompletionStatus,
    build_psaa_managed_start_input,
)
from agents.production_shift_auditor.runtime import audit_shift_from_input
from agents.run_control.contracts import (
    CODE_LAUNCH_OUTCOME_UNKNOWN,
    ManagedRunStartInput,
    StartOutcome,
)
from agents.run_control.registry import InMemoryRunControlRegistry
from agents.run_control.service import RunControlService
from agents.monthly_plan_constructor.managed_launcher import ConstructorManagedRuntimeLauncher
from security.agent_execution_context import issue_read_only_agent_context


class _FixtureHarness(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "obs.sqlite"
        self.fixture = build_insulation_pipeline_fixture()
        self.registry = InMemoryRunControlRegistry()
        self.store = SqliteObservabilityStore(self.db_path)
        self.recorder = StoreObservabilityRecorder(self.store)
        self.service = RunControlService(
            registry=self.registry,
            recorder=self.recorder,
            durable_store=self.store,
        )
        self.launcher = PsaaManagedRuntimeLauncher(
            audit_input_resolver=fixed_audit_input_resolver(self.fixture),
            observability_db_path=self.db_path,
            sync_execution=True,
        )

    def tearDown(self) -> None:
        self.store.close()
        self.tmp.cleanup()

    def _start(self, launcher=None, **overrides):
        start = build_psaa_managed_start_input(
            project_code=self.fixture.project_code,
            work_date=self.fixture.work_date,
            crew_id=self.fixture.crew_id,
            requested_mission_id=overrides.pop("requested_mission_id", "mission-psaa-1"),
            idempotency_key=overrides.pop("idempotency_key", "idem-psaa-1"),
            shift_type=self.fixture.shift_type,
        )
        if overrides:
            payload = start.__dict__.copy()
            payload.update(overrides)
            start = ManagedRunStartInput(**payload)
        return self.service.start(start, launcher=launcher or self.launcher)


class HappyPathTests(_FixtureHarness):
    def test_managed_fixture_joint_12_skills(self) -> None:
        result = self._start()
        self.assertEqual(result.outcome, StartOutcome.AUTHORIZED)
        self.assertEqual(result.agent_run.agent_code, AGENT_CODE)
        self.assertEqual(result.agent_run.project_code, self.fixture.project_code)
        self.assertEqual(result.run_request.month_key, PSAA_MONTH_KEY_COMPATIBILITY_SENTINEL)

        scope_raw = _unfreeze_jsonable(result.run_request.scope_request)
        scope = dict(scope_raw) if isinstance(scope_raw, dict) else {}
        self.assertEqual(scope.get("grain"), "SHIFT")
        self.assertEqual(scope.get("work_date"), self.fixture.work_date)
        self.assertEqual(scope.get("crew_id"), self.fixture.crew_id)
        self.assertEqual(scope.get("month_key_semantics"), "NOT_A_PLANNING_MONTH")

        managed = self.launcher.get_result(
            result.agent_run.run_id, project_code=self.fixture.project_code
        )
        self.assertIsNotNone(managed)
        assert managed is not None
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.COMPLETED)
        self.assertEqual(len(managed.professional_assessment.audit_input.operations), 11)
        self.assertEqual(managed.claimed_labor_man_minutes, 1425.0)
        self.assertEqual(managed.target_fund_man_minutes, 1440.0)
        self.assertEqual(
            managed.target_fund_man_minutes - managed.claimed_labor_man_minutes, 15.0
        )
        self.assertEqual(managed.scenario_direct_labor_cost_exact, "23750.0000")
        self.assertEqual(managed.unit_labor_observation_count, 2)
        self.assertEqual(managed.knowledge_candidate_count, 3)
        self.assertEqual(managed.verified_knowledge_count, 0)
        self.assertEqual(managed.approved_labor_norm_count, 0)
        self.assertEqual(managed.managerial_acceptance_status, "NOT_IN_SCOPE")
        self.assertIn("PHYSICAL_EXECUTION_VERIFIED_NO", managed.physical_execution_verified_status)
        self.assertTrue(managed.human_decision_required)

        pa = managed.professional_assessment
        self.assertIsNotNone(pa.s01)
        self.assertIsNotNone(pa.s10)
        self.assertIsNotNone(pa.s02)
        self.assertIsNotNone(pa.s03)
        self.assertIsNotNone(pa.s11)
        self.assertIsNotNone(pa.s04)
        self.assertIsNotNone(pa.s05)
        self.assertIsNotNone(pa.s06)
        self.assertIsNotNone(pa.s07)
        self.assertIsNotNone(pa.s08)
        self.assertIsNotNone(pa.s09)
        self.assertIsNotNone(pa.s12)
        self.assertEqual(pa.s12.shift_summary.total_claimed_labor_man_minutes, 1425.0)

        run = self.store.get_run(result.agent_run.run_id)
        self.assertEqual(run.operational_status, OperationalStatus.COMPLETED)
        events = self.store.list_events(result.agent_run.run_id, limit=50)
        types = {e.event_type for e in events}
        self.assertIn(EventType.RUN_COMPLETED, types)
        self.assertIn(EventType.ARTIFACT_CREATED, types)
        self.assertNotIn(EventType.RUN_FAILED, types)

        artifact_events = [e for e in events if e.event_type is EventType.ARTIFACT_CREATED]
        self.assertEqual(len(artifact_events), 1)
        detail_raw = _unfreeze_jsonable(artifact_events[0].detail)
        detail = dict(detail_raw) if isinstance(detail_raw, dict) else {}
        self.assertEqual(detail.get("storage_kind"), "PROCESS_LOCAL")
        self.assertEqual(detail.get("durable_persistence"), False)
        self.assertEqual(detail.get("artifact_reference_kind"), "PROCESS_LOCAL_SUMMARY_ONLY")
        self.assertEqual(detail.get("durable_professional_history"), False)
        self.assertEqual(detail.get("production_artifact_verified"), False)
        # Stage artifact collectors require stage_id — PSAA process-local
        # ARTIFACT_CREATED intentionally omits stage_id (not durable stage product).
        self.assertIsNone(artifact_events[0].stage_id)

        completed = [e for e in events if e.event_type is EventType.RUN_COMPLETED][0]
        cdetail_raw = _unfreeze_jsonable(completed.detail)
        cdetail = dict(cdetail_raw) if isinstance(cdetail_raw, dict) else {}
        self.assertEqual(cdetail.get("physical_execution_verified"), False)
        self.assertEqual(cdetail.get("managerial_acceptance_performed"), False)
        self.assertEqual(cdetail.get("durable_professional_history"), False)

    def test_query_port_sees_completed_run(self) -> None:
        result = self._start(idempotency_key="idem-psaa-qp")
        port = AgentControlRoomQueryPort(self.store)
        listed = port.list_runs(agent_code=AGENT_CODE, project_code=self.fixture.project_code)
        run_ids = {item.run_id for item in listed.items}
        self.assertIn(result.agent_run.run_id, run_ids)
        detail = port.get_run(result.agent_run.run_id)
        self.assertEqual(detail.agent_code, AGENT_CODE)
        self.assertEqual(detail.project_code, self.fixture.project_code)
        self.assertEqual(detail.operational_status, OperationalStatus.COMPLETED.value)

    def test_headless_no_ui_dependency(self) -> None:
        result = self._start(idempotency_key="idem-psaa-headless")
        self.assertEqual(result.outcome, StartOutcome.AUTHORIZED)
        self.assertEqual(
            self.launcher.get_result(result.agent_run.run_id).completion_status,
            PsaaManagedCompletionStatus.COMPLETED,
        )


class FailureTests(_FixtureHarness):
    def test_invalid_empty_operations(self) -> None:
        empty = replace(self.fixture, operations=())
        launcher = PsaaManagedRuntimeLauncher(
            audit_input_resolver=fixed_audit_input_resolver(empty),
            observability_db_path=self.db_path,
            sync_execution=True,
        )
        result = self.service.start(
            build_psaa_managed_start_input(
                project_code=self.fixture.project_code,
                work_date=self.fixture.work_date,
                crew_id=self.fixture.crew_id,
                requested_mission_id="mission-empty",
                idempotency_key="idem-empty",
            ),
            launcher=launcher,
        )
        self.assertEqual(result.outcome, StartOutcome.AUTHORIZED)
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.FAILED)
        self.assertEqual(managed.error_code, "PSAA_INVALID_INPUT")
        run = self.store.get_run(result.agent_run.run_id)
        self.assertEqual(run.operational_status, OperationalStatus.FAILED)

    def test_unauthorized_project_scope_mismatch(self) -> None:
        other = replace(self.fixture, project_code="OTHER_PROJECT")
        launcher = PsaaManagedRuntimeLauncher(
            audit_input_resolver=fixed_audit_input_resolver(other),
            observability_db_path=self.db_path,
            sync_execution=True,
        )
        result = self.service.start(
            build_psaa_managed_start_input(
                project_code=self.fixture.project_code,
                work_date=self.fixture.work_date,
                crew_id=self.fixture.crew_id,
                requested_mission_id="mission-xproj",
                idempotency_key="idem-xproj",
            ),
            launcher=launcher,
        )
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.FAILED)
        self.assertEqual(managed.error_code, "PSAA_SCOPE_MISMATCH")

    def test_work_date_grain_mismatch_rejected(self) -> None:
        mismatched = replace(self.fixture, work_date="1999-01-01")
        launcher = PsaaManagedRuntimeLauncher(
            audit_input_resolver=fixed_audit_input_resolver(mismatched),
            observability_db_path=self.db_path,
            sync_execution=True,
        )
        result = self._start(
            launcher=launcher,
            requested_mission_id="mission-grain-date",
            idempotency_key="idem-grain-date",
        )
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.FAILED)
        self.assertEqual(managed.error_code, "PSAA_SCOPE_MISMATCH")
        self.assertIn("work_date", managed.safe_error_summary or "")

    def test_crew_id_grain_mismatch_rejected(self) -> None:
        mismatched = replace(self.fixture, crew_id="CREW_OTHER")
        launcher = PsaaManagedRuntimeLauncher(
            audit_input_resolver=fixed_audit_input_resolver(mismatched),
            observability_db_path=self.db_path,
            sync_execution=True,
        )
        result = self._start(
            launcher=launcher,
            requested_mission_id="mission-grain-crew",
            idempotency_key="idem-grain-crew",
        )
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.FAILED)
        self.assertEqual(managed.error_code, "PSAA_SCOPE_MISMATCH")

    def test_incorrect_agent_identity_on_launcher(self) -> None:
        start = build_psaa_managed_start_input(
            project_code=self.fixture.project_code,
            work_date=self.fixture.work_date,
            crew_id=self.fixture.crew_id,
            requested_mission_id="mission-bad-agent",
            idempotency_key="idem-bad-agent",
        )
        payload = start.__dict__.copy()
        payload["agent_code"] = "MONTHLY_PLAN_CONSTRUCTOR"
        payload["month_key"] = "2026-09"
        bad = ManagedRunStartInput(**payload)
        with self.assertRaises(Exception) as ctx:
            self.service.start(bad, launcher=self.launcher)
        self.assertIn(
            ctx.exception.code if hasattr(ctx.exception, "code") else "",
            {CODE_LAUNCH_OUTCOME_UNKNOWN, "PSAA_AGENT_IDENTITY"},
        )

    def test_missing_source_resolver(self) -> None:
        def boom(*_a, **_k):
            raise RuntimeError("no source")

        launcher = PsaaManagedRuntimeLauncher(
            audit_input_resolver=boom,
            observability_db_path=self.db_path,
            sync_execution=True,
        )
        result = self.service.start(
            build_psaa_managed_start_input(
                project_code=self.fixture.project_code,
                work_date=self.fixture.work_date,
                crew_id=self.fixture.crew_id,
                requested_mission_id="mission-nosrc",
                idempotency_key="idem-nosrc",
            ),
            launcher=launcher,
        )
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.FAILED)
        self.assertEqual(managed.error_code, "PSAA_MISSING_SOURCE")
        run = self.store.get_run(result.agent_run.run_id)
        self.assertEqual(run.operational_status, OperationalStatus.FAILED)
        events = self.store.list_events(result.agent_run.run_id, limit=50)
        self.assertNotIn(EventType.RUN_COMPLETED, {e.event_type for e in events})

    def test_professional_assessment_failure(self) -> None:
        launcher = PsaaManagedRuntimeLauncher(
            audit_input_resolver=fixed_audit_input_resolver(self.fixture),
            observability_db_path=self.db_path,
            sync_execution=True,
        )
        with mock.patch(
            "agents.production_shift_auditor.managed_launcher.assess_shift",
            side_effect=RuntimeError("assess boom"),
        ):
            result = self._start(
                launcher=launcher,
                requested_mission_id="mission-assess-fail",
                idempotency_key="idem-assess-fail",
            )
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.FAILED)
        self.assertEqual(managed.error_code, "PSAA_EXECUTION_FAILED")
        run = self.store.get_run(result.agent_run.run_id)
        self.assertEqual(run.operational_status, OperationalStatus.FAILED)
        events = self.store.list_events(result.agent_run.run_id, limit=50)
        self.assertNotIn(EventType.RUN_COMPLETED, {e.event_type for e in events})

    def test_no_acceptance_escalation(self) -> None:
        result = self._start(idempotency_key="idem-no-accept")
        managed = self.launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.managerial_acceptance_status, "NOT_IN_SCOPE")
        self.assertEqual(
            managed.professional_assessment.s09.managerial_acceptance_status,
            "NOT_IN_SCOPE",
        )
        self.assertEqual(
            managed.professional_assessment.s09.managerial_acceptance_performed_status,
            "MANAGERIAL_ACCEPTANCE_PERFORMED_NO",
        )


class IsolationAndThreadingTests(_FixtureHarness):
    def test_get_result_before_completion_is_none(self) -> None:
        gate = threading.Event()

        def slow_resolver(run_request, agent_run, context):
            gate.wait(timeout=5.0)
            return fixed_audit_input_resolver(self.fixture)(run_request, agent_run, context)

        launcher = PsaaManagedRuntimeLauncher(
            audit_input_resolver=slow_resolver,
            observability_db_path=self.db_path,
            sync_execution=False,
        )
        result = self._start(
            launcher=launcher,
            requested_mission_id="mission-before",
            idempotency_key="idem-before",
        )
        self.assertIsNone(launcher.get_result(result.agent_run.run_id))
        gate.set()
        launcher.wait(timeout=30.0)
        managed = launcher.get_result(
            result.agent_run.run_id, project_code=self.fixture.project_code
        )
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.COMPLETED)

    def test_threaded_execution_completes(self) -> None:
        launcher = PsaaManagedRuntimeLauncher(
            audit_input_resolver=fixed_audit_input_resolver(self.fixture),
            observability_db_path=self.db_path,
            sync_execution=False,
        )
        result = self._start(
            launcher=launcher,
            requested_mission_id="mission-threaded",
            idempotency_key="idem-threaded",
        )
        launcher.wait(timeout=30.0)
        managed = launcher.get_result(result.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.COMPLETED)
        self.assertEqual(managed.claimed_labor_man_minutes, 1425.0)
        run = self.store.get_run(result.agent_run.run_id)
        self.assertEqual(run.operational_status, OperationalStatus.COMPLETED)

    def test_two_sequential_runs_isolated(self) -> None:
        r1 = self._start(requested_mission_id="mission-seq-1", idempotency_key="idem-seq-1")
        r2 = self._start(requested_mission_id="mission-seq-2", idempotency_key="idem-seq-2")
        m1 = self.launcher.get_result(r1.agent_run.run_id)
        m2 = self.launcher.get_result(r2.agent_run.run_id)
        self.assertNotEqual(r1.agent_run.run_id, r2.agent_run.run_id)
        self.assertEqual(m1.run_id, r1.agent_run.run_id)
        self.assertEqual(m2.run_id, r2.agent_run.run_id)
        self.assertEqual(m1.completion_status, PsaaManagedCompletionStatus.COMPLETED)
        self.assertEqual(m2.completion_status, PsaaManagedCompletionStatus.COMPLETED)

    def test_two_concurrent_runs_isolated(self) -> None:
        launcher = PsaaManagedRuntimeLauncher(
            audit_input_resolver=fixed_audit_input_resolver(self.fixture),
            observability_db_path=self.db_path,
            sync_execution=False,
        )
        r1 = self._start(
            launcher=launcher,
            requested_mission_id="mission-c1",
            idempotency_key="idem-c1",
        )
        r2 = self._start(
            launcher=launcher,
            requested_mission_id="mission-c2",
            idempotency_key="idem-c2",
        )
        launcher.wait(timeout=60.0)
        m1 = launcher.get_result(r1.agent_run.run_id)
        m2 = launcher.get_result(r2.agent_run.run_id)
        self.assertNotEqual(r1.agent_run.run_id, r2.agent_run.run_id)
        self.assertEqual(m1.run_id, r1.agent_run.run_id)
        self.assertEqual(m2.run_id, r2.agent_run.run_id)
        self.assertEqual(m1.claimed_labor_man_minutes, 1425.0)
        self.assertEqual(m2.claimed_labor_man_minutes, 1425.0)

    def test_get_result_cross_project_denied(self) -> None:
        result = self._start(idempotency_key="idem-xaccess")
        # Knowledge of run_id alone must not authorize cross-project access
        # when caller supplies a project_code gate.
        denied = self.launcher.get_result(
            result.agent_run.run_id, project_code="OTHER_PROJECT"
        )
        self.assertIsNone(denied)
        allowed = self.launcher.get_result(
            result.agent_run.run_id, project_code=self.fixture.project_code
        )
        self.assertIsNotNone(allowed)

    def test_failed_result_accessible_and_not_completed(self) -> None:
        empty = replace(self.fixture, operations=())
        launcher = PsaaManagedRuntimeLauncher(
            audit_input_resolver=fixed_audit_input_resolver(empty),
            observability_db_path=self.db_path,
            sync_execution=True,
        )
        result = self._start(
            launcher=launcher,
            requested_mission_id="mission-fail-res",
            idempotency_key="idem-fail-res",
        )
        managed = launcher.get_result(
            result.agent_run.run_id, project_code=self.fixture.project_code
        )
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.FAILED)
        self.assertIsNone(managed.professional_assessment)

    def test_idempotent_replay_per_run_control(self) -> None:
        start = build_psaa_managed_start_input(
            project_code=self.fixture.project_code,
            work_date=self.fixture.work_date,
            crew_id=self.fixture.crew_id,
            requested_mission_id="mission-idem",
            idempotency_key="idem-same-key",
            shift_type=self.fixture.shift_type,
        )
        first = self.service.start(start, launcher=self.launcher)
        second = self.service.start(start, launcher=self.launcher)
        # Existing Run Control contract: same idempotency key returns same run
        self.assertEqual(first.agent_run.run_id, second.agent_run.run_id)
        managed = self.launcher.get_result(first.agent_run.run_id)
        self.assertEqual(managed.completion_status, PsaaManagedCompletionStatus.COMPLETED)


class CompatibilityTests(_FixtureHarness):
    def test_s01_runtime_path_still_works(self) -> None:
        s01 = audit_shift_from_input(self.fixture, run_id="run_s01_compat")
        self.assertEqual(s01.artifact.s01_metrics.claimed_total_man_minutes, 1425.0)

    def test_month_key_sentinel_rejected_if_fake_calendar(self) -> None:
        _ = issue_read_only_agent_context(
            agent_code=AGENT_CODE,
            project_code=self.fixture.project_code,
            run_id="run-sentinel",
        )
        start = build_psaa_managed_start_input(
            project_code=self.fixture.project_code,
            work_date=self.fixture.work_date,
            crew_id=self.fixture.crew_id,
            requested_mission_id="mission-fake-month",
            idempotency_key="idem-fake-month",
        )
        payload = start.__dict__.copy()
        payload["month_key"] = "2026-01"
        fake = ManagedRunStartInput(**payload)
        with self.assertRaises(Exception):
            self.service.start(fake, launcher=self.launcher)

    def test_constructor_launcher_still_rejects_psaa_identity(self) -> None:
        ctor = ConstructorManagedRuntimeLauncher(
            observability_db_path=self.db_path,
            assemble_candidates=lambda **_k: [],
            scope_reader=lambda *_a, **_k: [],
        )
        start = build_psaa_managed_start_input(
            project_code=self.fixture.project_code,
            work_date=self.fixture.work_date,
            crew_id=self.fixture.crew_id,
            requested_mission_id="mission-ctor-compat",
            idempotency_key="idem-ctor-compat",
        )
        with self.assertRaises(Exception) as ctx:
            self.service.start(start, launcher=ctor)
        self.assertEqual(getattr(ctx.exception, "code", None), CODE_LAUNCH_OUTCOME_UNKNOWN)

    def test_constructor_planning_month_still_accepted_by_contract(self) -> None:
        # Sentinel is PSAA-only; Constructor calendar month remains valid text
        # for ManagedRunStartInput validation (non-empty).
        start = ManagedRunStartInput(
            agent_code="MONTHLY_PLAN_CONSTRUCTOR",
            initiator_type=InitiatorType.HUMAN,
            initiator_id="operator-local",
            trigger_type=TriggerType.MANUAL,
            trigger_reason="ctor-month-check",
            project_code=self.fixture.project_code,
            month_key="2026-09",
            requested_mission_id="mission-ctor-month-ok",
            idempotency_key="idem-ctor-month-ok",
        )
        self.assertEqual(start.month_key, "2026-09")
        self.assertNotEqual(start.month_key, PSAA_MONTH_KEY_COMPATIBILITY_SENTINEL)


if __name__ == "__main__":
    unittest.main()
