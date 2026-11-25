"""PSAA-08 / S05 — Temporal Integrity tests."""

from __future__ import annotations

import unittest
from dataclasses import replace

from agents.production_shift_auditor.contracts import (
    LaborUnit,
    ManagerialAcceptanceStatus,
    OperationLaborClaim,
)
from agents.production_shift_auditor.fixtures import build_insulation_pipeline_fixture
from agents.production_shift_auditor.professional_assessment import assess_shift
from agents.production_shift_auditor.s04_execution_cost import (
    scenario_rate_1000_rub_per_man_hour,
)
from agents.production_shift_auditor.s05_contracts import (
    CapacityAuthority,
    ChronologyVerificationStatus,
    OperationTemporalClaim,
    ShiftTemporalContext,
    TemporalFeasibilityStatus,
    TemporalFindingStatus,
    TimestampAuthority,
)


def _by_name(art, name: str):
    hits = [f for f in art.findings if f.original_operation_text == name]
    assert hits, f"no S05 finding for {name!r}"
    return hits[0]


def _statuses(f) -> set[str]:
    return {s.value for s in f.finding_statuses}


class FixtureTimeBalanceTests(unittest.TestCase):
    def test_target_claimed_remaining_coverage(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s05_bal")
        s = joint.s05.shift_summary
        self.assertEqual(s.target_productive_fund_man_minutes, 1440.0)
        self.assertEqual(s.total_claimed_labor_man_minutes, 1425.0)
        self.assertEqual(s.signed_deviation_man_minutes, 15.0)
        self.assertAlmostEqual(s.coverage_pct, 98.958333, places=5)
        self.assertEqual(s.unallocated_relative_to_target_man_minutes, 15.0)
        self.assertEqual(s.time_balance_status, TemporalFindingStatus.TIME_BALANCE_COMPUTABLE)
        self.assertEqual(joint.s01.s01_metrics.claimed_total_man_minutes, 1425.0)

    def test_unallocated_not_idle(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s05_idle")
        s = joint.s05.shift_summary
        self.assertIn("NE_AUTOMATIC_IDLE", s.unallocated_classification)
        blob = " ".join(s.notes) + joint.s05.human_readable_summary
        self.assertIn("UNALLOCATED_TIME_NE_AUTOMATIC_IDLE_TIME", blob)
        self.assertNotIn("CONFIRMED_IDLE", s.unallocated_classification)

    def test_conditional_bound_400_over_3(self) -> None:
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_bound",
            shift_temporal_context=ShiftTemporalContext(
                maximum_simultaneous_workers_scenario=3,
                source_note="scenario_only",
            ),
        )
        fit = _by_name(joint.s05, "Изготовление фасонных изделий")
        self.assertAlmostEqual(fit.conditional_duration_bound_minutes, 400.0 / 3.0, places=6)
        self.assertIn(
            TemporalFindingStatus.CONDITIONAL_DURATION_BOUND_COMPUTED,
            fit.finding_statuses,
        )
        self.assertIn("SCENARIO_ONLY", fit.conditional_bound_assumption or "")
        self.assertIn("CONDITIONAL_DURATION_BOUND_NE_ACTUAL", fit.conditional_bound_assumption or "")

    def test_crew_size_not_automatic_allocation(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s05_crew")
        fit = _by_name(joint.s05, "Изготовление фасонных изделий")
        self.assertIsNone(fit.conditional_duration_bound_minutes)
        note = " ".join(fit.temporal_findings)
        self.assertIn("crew_size_present_but_not_used_as_automatic_operation_allocation", note)
        self.assertIn(
            TemporalFindingStatus.WORKER_ALLOCATION_NOT_PROVEN, fit.finding_statuses
        )
        self.assertEqual(
            joint.s05.shift_summary.individual_allocation_readiness,
            "WORKER_ALLOCATION_NOT_PROVEN",
        )

    def test_missing_timestamps_chronology_not_proven(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s05_chr")
        self.assertEqual(
            joint.s05.shift_summary.chronology_verification_status,
            ChronologyVerificationStatus.CHRONOLOGY_NOT_PROVEN,
        )
        self.assertEqual(joint.s05.chronology_status, "CHRONOLOGY_NOT_PROVEN")
        for f in joint.s05.findings:
            self.assertIn(TemporalFindingStatus.CHRONOLOGY_NOT_PROVEN, f.finding_statuses)
            self.assertIsNone(f.claimed_start_utc)
            self.assertIsNone(f.claimed_end_utc)

    def test_row_order_not_chronology(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s05_row")
        for f in joint.s05.findings:
            self.assertIn("REPORT_ROW_ORDER_NE_EXECUTION_CHRONOLOGY", f.temporal_findings)

    def test_registration_timestamp_not_execution(self) -> None:
        base = build_insulation_pipeline_fixture()
        # Identify first op via matching original text
        claim = OperationTemporalClaim(
            original_operation_text="Подготовка поверхности",
            registration_timestamp_utc="2026-01-01T10:00:00+00:00",
            timestamp_authority=TimestampAuthority.REGISTRATION_TIMESTAMP_ONLY,
        )
        joint = assess_shift(
            base, audit_id="s05_reg", temporal_claims=(claim,)
        )
        f = _by_name(joint.s05, "Подготовка поверхности")
        self.assertIsNone(f.elapsed_duration_minutes)
        self.assertIn(
            "registration_timestamp_present_but_not_execution_interval",
            f.temporal_findings,
        )
        self.assertIn("REGISTRATION_TIMESTAMP_NE_EXECUTION_TIMESTAMP", f.temporal_findings)

    def test_target_fund_ne_paid_attendance(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s05_att")
        self.assertIn(
            "TARGET_PRODUCTIVE_FUND_NE_ACTUAL_ATTENDANCE",
            joint.s05.shift_summary.notes,
        )


class IntervalValidationTests(unittest.TestCase):
    def test_valid_explicit_interval(self) -> None:
        claim = OperationTemporalClaim(
            original_operation_text="Подготовка поверхности",
            claimed_start_utc="2026-01-01T08:00:00+00:00",
            claimed_end_utc="2026-01-01T08:30:00+00:00",
            timezone_explicit=True,
            timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
            maximum_simultaneous_workers_scenario=1,
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_ok",
            temporal_claims=(claim,),
        )
        f = _by_name(joint.s05, "Подготовка поверхности")
        self.assertEqual(f.elapsed_duration_minutes, 30.0)
        self.assertIn(TemporalFindingStatus.INTERVAL_VALID_CLAIMED_ONLY, f.finding_statuses)
        self.assertEqual(
            joint.s05.shift_summary.chronology_verification_status,
            ChronologyVerificationStatus.CLAIMED_INTERVALS_PRESENT_NOT_VERIFIED,
        )
        self.assertNotEqual(
            joint.s05.shift_summary.chronology_verification_status,
            ChronologyVerificationStatus.VERIFIED_CHRONOLOGY,
        )

    def test_invalid_end_before_start(self) -> None:
        claim = OperationTemporalClaim(
            original_operation_text="Подготовка поверхности",
            claimed_start_utc="2026-01-01T10:00:00+00:00",
            claimed_end_utc="2026-01-01T09:00:00+00:00",
            timezone_explicit=True,
            timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_inv",
            temporal_claims=(claim,),
            shift_temporal_context=ShiftTemporalContext(overnight_shift_explicit=False),
        )
        f = _by_name(joint.s05, "Подготовка поверхности")
        self.assertIn(TemporalFindingStatus.INVALID_TIME_INTERVAL, f.finding_statuses)
        self.assertIsNone(f.elapsed_duration_minutes)

    def test_explicit_overnight_with_date_rollover(self) -> None:
        claim = OperationTemporalClaim(
            original_operation_text="Подготовка поверхности",
            claimed_start_utc="2026-01-01T22:00:00+00:00",
            claimed_end_utc="2026-01-02T06:00:00+00:00",
            timezone_explicit=True,
            timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_on",
            temporal_claims=(claim,),
            shift_temporal_context=ShiftTemporalContext(overnight_shift_explicit=True),
        )
        f = _by_name(joint.s05, "Подготовка поверхности")
        self.assertIn(TemporalFindingStatus.INTERVAL_VALID_CLAIMED_ONLY, f.finding_statuses)
        self.assertAlmostEqual(f.elapsed_duration_minutes or 0, 8 * 60, places=3)
        self.assertIn(
            "overnight_shift_explicitly_declared_with_date_rollover", f.temporal_findings
        )

    def test_overnight_flag_does_not_auto_correct_end_before_start(self) -> None:
        claim = OperationTemporalClaim(
            original_operation_text="Подготовка поверхности",
            claimed_start_utc="2026-01-01T22:00:00+00:00",
            claimed_end_utc="2026-01-01T06:00:00+00:00",
            timezone_explicit=True,
            timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_on_bad",
            temporal_claims=(claim,),
            shift_temporal_context=ShiftTemporalContext(overnight_shift_explicit=True),
        )
        f = _by_name(joint.s05, "Подготовка поверхности")
        self.assertIn(TemporalFindingStatus.INVALID_TIME_INTERVAL, f.finding_statuses)
        self.assertIsNone(f.elapsed_duration_minutes)
        self.assertTrue(
            any("does_not_auto_correct" in x for x in f.temporal_findings)
        )

    def test_ambiguous_timezone(self) -> None:
        claim = OperationTemporalClaim(
            original_operation_text="Подготовка поверхности",
            claimed_start_utc="2026-01-01T08:00:00",
            claimed_end_utc="2026-01-01T09:00:00",
            timezone_explicit=False,
            timestamp_authority=TimestampAuthority.AMBIGUOUS,
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_tz",
            temporal_claims=(claim,),
        )
        f = _by_name(joint.s05, "Подготовка поверхности")
        self.assertIn(TemporalFindingStatus.AMBIGUOUS_TIMEZONE_OR_DATE, f.finding_statuses)

    def test_labor_exceeds_interval_capacity(self) -> None:
        # 30 man-min labor, 10 elapsed min, 1 worker → capacity 10 < 30
        claim = OperationTemporalClaim(
            original_operation_text="Подготовка поверхности",
            claimed_start_utc="2026-01-01T08:00:00+00:00",
            claimed_end_utc="2026-01-01T08:10:00+00:00",
            timezone_explicit=True,
            timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
            worker_identities=("W1",),
            maximum_simultaneous_workers_scenario=1,
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_cap",
            temporal_claims=(claim,),
        )
        f = _by_name(joint.s05, "Подготовка поверхности")
        self.assertIn(
            TemporalFindingStatus.LABOR_EXCEEDS_INTERVAL_CAPACITY, f.finding_statuses
        )


class OverlapAndCapacityTests(unittest.TestCase):
    def test_same_worker_exclusive_overlap_conflict(self) -> None:
        claims = (
            OperationTemporalClaim(
                original_operation_text="Подготовка поверхности",
                claimed_start_utc="2026-01-01T08:00:00+00:00",
                claimed_end_utc="2026-01-01T09:00:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("W1",),
                exclusive_active_work=True,
            ),
            OperationTemporalClaim(
                original_operation_text="Замеры и разметка",
                claimed_start_utc="2026-01-01T08:30:00+00:00",
                claimed_end_utc="2026-01-01T09:30:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("W1",),
                exclusive_active_work=True,
            ),
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_excl",
            temporal_claims=claims,
        )
        f1 = _by_name(joint.s05, "Подготовка поверхности")
        self.assertIn(
            TemporalFindingStatus.EXCLUSIVE_WORKER_ALLOCATION_CONFLICT, f1.finding_statuses
        )
        self.assertIn(
            TemporalFindingStatus.CLAIMED_INTERVAL_OVERLAP, f1.finding_statuses
        )
        blob = " ".join(f1.overlap_findings).lower()
        self.assertIn("not automatic fraud", blob)
        self.assertEqual(joint.s05.fraud_classification_status, "NOT_PERFORMED")
        self.assertEqual(
            joint.s05.shift_summary.temporal_feasibility_status,
            TemporalFeasibilityStatus.CONFLICT_IN_CLAIMED_DATA,
        )

    def test_same_worker_overlap_without_exclusive_semantics_uncertainty(self) -> None:
        claims = (
            OperationTemporalClaim(
                original_operation_text="Подготовка поверхности",
                claimed_start_utc="2026-01-01T08:00:00+00:00",
                claimed_end_utc="2026-01-01T09:00:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("W1",),
                exclusive_active_work=None,
            ),
            OperationTemporalClaim(
                original_operation_text="Замеры и разметка",
                claimed_start_utc="2026-01-01T08:30:00+00:00",
                claimed_end_utc="2026-01-01T09:30:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("W1",),
                exclusive_active_work=None,
            ),
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_unc",
            temporal_claims=claims,
        )
        f1 = _by_name(joint.s05, "Подготовка поверхности")
        self.assertIn(TemporalFindingStatus.CLAIMED_INTERVAL_OVERLAP, f1.finding_statuses)
        self.assertNotIn(
            TemporalFindingStatus.EXCLUSIVE_WORKER_ALLOCATION_CONFLICT, f1.finding_statuses
        )
        self.assertTrue(
            any("without_proven_exclusive_semantics" in x for x in f1.overlap_findings)
        )

    def test_different_workers_overlap_not_automatic_conflict(self) -> None:
        claims = (
            OperationTemporalClaim(
                original_operation_text="Подготовка поверхности",
                claimed_start_utc="2026-01-01T08:00:00+00:00",
                claimed_end_utc="2026-01-01T09:00:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("W1",),
            ),
            OperationTemporalClaim(
                original_operation_text="Замеры и разметка",
                claimed_start_utc="2026-01-01T08:30:00+00:00",
                claimed_end_utc="2026-01-01T09:30:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("W2",),
            ),
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_diff",
            temporal_claims=claims,
        )
        f1 = _by_name(joint.s05, "Подготовка поверхности")
        self.assertIn(TemporalFindingStatus.CLAIMED_INTERVAL_OVERLAP, f1.finding_statuses)
        self.assertNotIn(
            TemporalFindingStatus.EXCLUSIVE_WORKER_ALLOCATION_CONFLICT, f1.finding_statuses
        )
        self.assertTrue(
            any("not_automatic_conflict" in x for x in f1.overlap_findings)
        )
        self.assertNotEqual(
            joint.s05.shift_summary.temporal_feasibility_status,
            TemporalFeasibilityStatus.CONFLICT_IN_CLAIMED_DATA,
        )

    def test_same_crew_parallel_without_allocation_insufficient(self) -> None:
        claims = (
            OperationTemporalClaim(
                original_operation_text="Подготовка поверхности",
                claimed_start_utc="2026-01-01T08:00:00+00:00",
                claimed_end_utc="2026-01-01T09:00:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
            ),
            OperationTemporalClaim(
                original_operation_text="Замеры и разметка",
                claimed_start_utc="2026-01-01T08:30:00+00:00",
                claimed_end_utc="2026-01-01T09:30:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
            ),
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_par",
            temporal_claims=claims,
        )
        f1 = _by_name(joint.s05, "Подготовка поверхности")
        self.assertTrue(
            any("INSUFFICIENT_CONTEXT" in x for x in f1.overlap_findings)
        )
        self.assertTrue(
            any("PARALLEL_OPERATIONS_NE_AUTOMATIC" in x for x in f1.overlap_findings)
        )

    def test_scenario_capacity_limit_exceeded_not_physical_proof(self) -> None:
        claims = (
            OperationTemporalClaim(
                original_operation_text="Подготовка поверхности",
                claimed_start_utc="2026-01-01T08:00:00+00:00",
                claimed_end_utc="2026-01-01T09:00:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("W1", "W2"),
            ),
            OperationTemporalClaim(
                original_operation_text="Замеры и разметка",
                claimed_start_utc="2026-01-01T08:30:00+00:00",
                claimed_end_utc="2026-01-01T09:30:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("W3", "W4"),
            ),
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_cc",
            temporal_claims=claims,
            shift_temporal_context=ShiftTemporalContext(
                maximum_simultaneous_workers_scenario=3,
            ),
        )
        statuses = set()
        authorities = set()
        for f in joint.s05.findings:
            statuses |= _statuses(f)
            if f.capacity_conflict_authority:
                authorities.add(f.capacity_conflict_authority)
        self.assertIn(
            TemporalFindingStatus.SCENARIO_CAPACITY_LIMIT_EXCEEDED.value, statuses
        )
        self.assertNotIn(TemporalFindingStatus.CAPACITY_CONFLICT.value, statuses)
        self.assertIn(CapacityAuthority.SCENARIO_ASSUMPTION, authorities)

    def test_half_open_staggered_peak_is_two_not_three(self) -> None:
        # A 08-10, B 09-11, C 10-12 — pairwise overlaps exist, peak concurrent = 2
        claims = (
            OperationTemporalClaim(
                original_operation_text="Подготовка поверхности",
                claimed_start_utc="2026-01-01T08:00:00+00:00",
                claimed_end_utc="2026-01-01T10:00:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("WA",),
            ),
            OperationTemporalClaim(
                original_operation_text="Замеры и разметка",
                claimed_start_utc="2026-01-01T09:00:00+00:00",
                claimed_end_utc="2026-01-01T11:00:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("WB",),
            ),
            OperationTemporalClaim(
                original_operation_text="Подготовка клея",
                claimed_start_utc="2026-01-01T10:00:00+00:00",
                claimed_end_utc="2026-01-01T12:00:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("WC",),
            ),
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_half",
            temporal_claims=claims,
            shift_temporal_context=ShiftTemporalContext(
                maximum_simultaneous_workers_scenario=2,
            ),
        )
        statuses = set()
        for f in joint.s05.findings:
            statuses |= _statuses(f)
        self.assertNotIn(
            TemporalFindingStatus.SCENARIO_CAPACITY_LIMIT_EXCEEDED.value, statuses
        )
        self.assertNotIn(TemporalFindingStatus.CAPACITY_CONFLICT.value, statuses)

    def test_three_simultaneous_vs_confirmed_capacity_two(self) -> None:
        claims = (
            OperationTemporalClaim(
                original_operation_text="Подготовка поверхности",
                claimed_start_utc="2026-01-01T08:00:00+00:00",
                claimed_end_utc="2026-01-01T10:00:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("WA",),
            ),
            OperationTemporalClaim(
                original_operation_text="Замеры и разметка",
                claimed_start_utc="2026-01-01T08:00:00+00:00",
                claimed_end_utc="2026-01-01T10:00:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("WB",),
            ),
            OperationTemporalClaim(
                original_operation_text="Подготовка клея",
                claimed_start_utc="2026-01-01T08:00:00+00:00",
                claimed_end_utc="2026-01-01T10:00:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("WC",),
            ),
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_conf_cap",
            temporal_claims=claims,
            shift_temporal_context=ShiftTemporalContext(
                confirmed_available_crew_capacity=2,
            ),
        )
        statuses = set()
        authorities = set()
        for f in joint.s05.findings:
            statuses |= _statuses(f)
            if f.capacity_conflict_authority:
                authorities.add(f.capacity_conflict_authority)
        self.assertIn(TemporalFindingStatus.CAPACITY_CONFLICT.value, statuses)
        self.assertNotIn(
            TemporalFindingStatus.SCENARIO_CAPACITY_LIMIT_EXCEEDED.value, statuses
        )
        self.assertIn(CapacityAuthority.CONFIRMED_AVAILABLE_CREW_CAPACITY, authorities)
        blob = " ".join(
            " ".join(f.overlap_findings) for f in joint.s05.findings
        )
        self.assertIn("not fraud", blob.lower())

    def test_touching_intervals_not_overlap(self) -> None:
        claims = (
            OperationTemporalClaim(
                original_operation_text="Подготовка поверхности",
                claimed_start_utc="2026-01-01T08:00:00+00:00",
                claimed_end_utc="2026-01-01T10:00:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("W1",),
                exclusive_active_work=True,
            ),
            OperationTemporalClaim(
                original_operation_text="Замеры и разметка",
                claimed_start_utc="2026-01-01T10:00:00+00:00",
                claimed_end_utc="2026-01-01T12:00:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("W1",),
                exclusive_active_work=True,
            ),
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_touch",
            temporal_claims=claims,
        )
        f1 = _by_name(joint.s05, "Подготовка поверхности")
        self.assertNotIn(TemporalFindingStatus.CLAIMED_INTERVAL_OVERLAP, f1.finding_statuses)
        self.assertNotIn(
            TemporalFindingStatus.EXCLUSIVE_WORKER_ALLOCATION_CONFLICT, f1.finding_statuses
        )

    def test_zero_duration_requires_clarification(self) -> None:
        claim = OperationTemporalClaim(
            original_operation_text="Подготовка поверхности",
            claimed_start_utc="2026-01-01T08:00:00+00:00",
            claimed_end_utc="2026-01-01T08:00:00+00:00",
            timezone_explicit=True,
            timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_zero",
            temporal_claims=(claim,),
        )
        f = _by_name(joint.s05, "Подготовка поверхности")
        self.assertIn(TemporalFindingStatus.INTERVAL_VALID_CLAIMED_ONLY, f.finding_statuses)
        self.assertTrue(
            any("zero_duration" in x for x in f.temporal_findings)
        )

    def test_duplicate_source_identity_not_inflating_capacity(self) -> None:
        # Same source identity repeated in temporal claims must not double occupancy
        base = build_insulation_pipeline_fixture()
        probe = assess_shift(base, audit_id="s05_dup_probe")
        sid = probe.s10.classifications[0].source_operation_identity
        claims = (
            OperationTemporalClaim(
                source_operation_identity=sid,
                original_operation_text="Подготовка поверхности",
                claimed_start_utc="2026-01-01T08:00:00+00:00",
                claimed_end_utc="2026-01-01T10:00:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("W1",),
            ),
            OperationTemporalClaim(
                source_operation_identity=sid,
                original_operation_text="Подготовка поверхности",
                claimed_start_utc="2026-01-01T08:00:00+00:00",
                claimed_end_utc="2026-01-01T10:00:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
                worker_identities=("W1",),
            ),
        )
        joint = assess_shift(
            base,
            audit_id="s05_dup",
            temporal_claims=claims,
            shift_temporal_context=ShiftTemporalContext(
                maximum_simultaneous_workers_scenario=1,
            ),
        )
        statuses = set()
        for f in joint.s05.findings:
            statuses |= _statuses(f)
        self.assertNotIn(
            TemporalFindingStatus.SCENARIO_CAPACITY_LIMIT_EXCEEDED.value, statuses
        )


class DependencyAndGapTests(unittest.TestCase):
    def test_different_objects_no_artificial_dependency(self) -> None:
        # Different physical_object hints on temporal claims must not force dependency
        claims = (
            OperationTemporalClaim(
                original_operation_text="Монтаж прямых участков",
                physical_object_hint="PIPE_A",
            ),
            OperationTemporalClaim(
                original_operation_text="Монтаж AL CLAD AD",
                physical_object_hint="PIPE_B",
            ),
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_obj",
            temporal_claims=claims,
        )
        blob = joint.s05.human_readable_summary + " ".join(
            " ".join(f.temporal_findings) for f in joint.s05.findings
        )
        self.assertNotIn("CONFIRMED_CHRONOLOGY_VIOLATION", blob)
        self.assertEqual(
            joint.s05.shift_summary.chronology_verification_status,
            ChronologyVerificationStatus.CHRONOLOGY_NOT_PROVEN,
        )

    def test_demo_s02_not_confirmed_chronology_violation(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s05_s02")
        for f in joint.s05.findings:
            self.assertIn(
                "demonstration_s02_findings_do_not_create_confirmed_chronology_violation",
                f.temporal_findings,
            )
            self.assertNotIn(
                TemporalFindingStatus.CAPACITY_CONFLICT, f.finding_statuses
            )

    def test_gaps_not_automatic_idle(self) -> None:
        claims = (
            OperationTemporalClaim(
                original_operation_text="Подготовка поверхности",
                claimed_start_utc="2026-01-01T08:00:00+00:00",
                claimed_end_utc="2026-01-01T08:30:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
            ),
            OperationTemporalClaim(
                original_operation_text="Замеры и разметка",
                claimed_start_utc="2026-01-01T10:00:00+00:00",
                claimed_end_utc="2026-01-01T11:00:00+00:00",
                timezone_explicit=True,
                timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
            ),
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_gap",
            temporal_claims=claims,
        )
        self.assertIn(
            "GAPS_BETWEEN_INTERVALS_NE_AUTOMATIC_IDLE",
            joint.s05.shift_summary.notes,
        )
        blob = " ".join(
            " ".join(f.overlap_findings) + " ".join(f.temporal_findings)
            for f in joint.s05.findings
        )
        self.assertNotIn("CONFIRMED_IDLE", blob)

    def test_repeat_audit_same_source_not_new_event(self) -> None:
        # Same fixture assessed twice → same identities; second call not a new physical event
        a1 = assess_shift(build_insulation_pipeline_fixture(), audit_id="s05_r1")
        a2 = assess_shift(build_insulation_pipeline_fixture(), audit_id="s05_r2")
        ids1 = [f.source_operation_identity for f in a1.s05.findings]
        ids2 = [f.source_operation_identity for f in a2.s05.findings]
        self.assertEqual(ids1, ids2)
        self.assertEqual(len(ids1), len(set(ids1)))
        note = " ".join(a1.s05.observations)
        self.assertIn("CLAIMED CHRONOLOGY != VERIFIED CHRONOLOGY", note)


class IntegrationRegressionTests(unittest.TestCase):
    def test_claimed_labor_and_s04_cost_preserved(self) -> None:
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_int",
            cost_rates=(scenario_rate_1000_rub_per_man_hour(),),
        )
        self.assertEqual(joint.s01.s01_metrics.claimed_total_man_minutes, 1425.0)
        self.assertEqual(
            joint.s04.cost_conservation.total_calculated_direct_labor_cost_exact,
            "23750.0000",
        )
        self.assertEqual(len(joint.s05.findings), 11)
        self.assertEqual(joint.s05.managerial_acceptance_status, "NOT_IN_SCOPE")
        self.assertEqual(joint.s05.fraud_classification_status, "NOT_PERFORMED")
        self.assertEqual(joint.s05.payroll_decision_status, "NOT_PERFORMED")
        self.assertEqual(
            joint.s01.managerial_acceptance_status, ManagerialAcceptanceStatus.NOT_IN_SCOPE
        )
        self.assertEqual(joint.s05.durable_history_schema_status, "UNCHANGED_IN_THIS_INCREMENT")
        # Prior skills unchanged shapes
        self.assertEqual(len(joint.s10.classifications), 11)
        self.assertEqual(len(joint.s11.findings), 11)
        self.assertEqual(len(joint.s04.findings), 11)

    def test_no_acception_reject_in_s05(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s05_acc")
        blob = joint.s05.to_dict()
        text = str(blob)
        self.assertNotIn("ACCEPTED", text)
        self.assertNotIn("REJECTED", text)

    def test_serializable(self) -> None:
        joint = assess_shift(build_insulation_pipeline_fixture(), audit_id="s05_ser")
        d = joint.s05.to_dict()
        self.assertEqual(d["schema_version"], "shift_temporal_integrity.v0.1")
        self.assertEqual(len(d["findings"]), 11)

    def test_outside_shift_bounds(self) -> None:
        claim = OperationTemporalClaim(
            original_operation_text="Подготовка поверхности",
            claimed_start_utc="2026-01-01T06:00:00+00:00",
            claimed_end_utc="2026-01-01T07:00:00+00:00",
            timezone_explicit=True,
            timestamp_authority=TimestampAuthority.EXPLICIT_CLAIMED_INTERVAL,
        )
        joint = assess_shift(
            build_insulation_pipeline_fixture(),
            audit_id="s05_out",
            temporal_claims=(claim,),
            shift_temporal_context=ShiftTemporalContext(
                shift_start_utc="2026-01-01T08:00:00+00:00",
                shift_end_utc="2026-01-01T16:00:00+00:00",
                timezone_explicit=True,
            ),
        )
        f = _by_name(joint.s05, "Подготовка поверхности")
        self.assertIn(TemporalFindingStatus.OUTSIDE_KNOWN_SHIFT_INTERVAL, f.finding_statuses)

    def test_minimal_ops_with_source_ids(self) -> None:
        # Minimal two-op fixture for interval tests — base fixture unchanged
        base = build_insulation_pipeline_fixture()
        ops = (
            replace(
                base.operations[0],
                source_record_ids=("SRC_A",),
            ),
            replace(
                base.operations[1],
                source_record_ids=("SRC_B",),
            ),
        )
        inp = replace(base, operations=ops)
        joint = assess_shift(inp, audit_id="s05_src")
        ids = {f.source_operation_identity for f in joint.s05.findings}
        self.assertEqual(ids, {"SRC_A", "SRC_B"})


if __name__ == "__main__":
    unittest.main()
