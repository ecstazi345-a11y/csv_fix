"""S05 — Temporal Integrity (deterministic).

Three levels (must not be conflated):
  A. Mathematical time balance (from S01)
  B. Temporal feasibility under stated assumptions
  C. Evidence-supported actual chronology

Does not invent timestamps or worker allocations.
Does not classify fraud, idle, or payroll outcomes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence

from agents.production_shift_auditor.contracts import (
    LaborUnit,
    ShiftAuditArtifact,
    ShiftAuditInput,
)
from agents.production_shift_auditor.s02_contracts import (
    SourceAuthority,
    ShiftTechnologicalIntegrityArtifact,
)
from agents.production_shift_auditor.s03_contracts import ShiftPhysicalIntegrityArtifact
from agents.production_shift_auditor.s04_contracts import ShiftExecutionCostArtifact
from agents.production_shift_auditor.s05_contracts import (
    S05_ARTIFACT_SCHEMA_VERSION,
    S05_RULES_VERSION,
    CapacityAuthority,
    ChronologyVerificationStatus,
    OperationTemporalClaim,
    ShiftTemporalContext,
    ShiftTemporalIntegrityArtifact,
    ShiftTemporalSummary,
    TemporalFeasibilityStatus,
    TemporalFindingStatus,
    TemporalOperationFinding,
    TimestampAuthority,
)
from agents.production_shift_auditor.s10_contracts import (
    ShiftOperationClassificationArtifact,
)
from agents.production_shift_auditor.s11_contracts import ShiftLaborBenchmarkArtifact

AGENT_CODE = "PRODUCTION_SHIFT_AUDITOR"
AGENT_VERSION = "0.1"


def _parse_iso(value: Optional[str]) -> tuple[Optional[datetime], Optional[str]]:
    if not value:
        return None, None
    raw = value.strip()
    if not raw:
        return None, None
    try:
        if raw.endswith("Z"):
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(raw)
    except ValueError:
        return None, "unparseable_timestamp"
    if dt.tzinfo is None:
        return dt, "timezone_absent_ambiguous"
    return dt, None


def _match_temporal_claim(
    claims: Sequence[OperationTemporalClaim],
    *,
    source_identity: str,
    original: str,
) -> Optional[OperationTemporalClaim]:
    for c in claims:
        if c.source_operation_identity and c.source_operation_identity == source_identity:
            return c
        if c.original_operation_text and c.original_operation_text == original:
            return c
    return None


def _s11_mm(f11) -> Optional[float]:
    if f11.eligible_labor_man_minutes is not None:
        return float(f11.eligible_labor_man_minutes)
    if f11.preserved_claimed_labor_quantity is not None and f11.original_labor_unit == LaborUnit.MAN_MINUTE.value:
        return float(f11.preserved_claimed_labor_quantity)
    if f11.preserved_claimed_labor_quantity is not None and f11.original_labor_unit == LaborUnit.MAN_HOUR.value:
        return float(f11.preserved_claimed_labor_quantity) * 60.0
    return None


def _intervals_overlap(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> bool:
    """Half-open [start, end): touching endpoints do not overlap."""
    return a0 < b1 and b0 < a1


def _active_half_open(start: datetime, end: datetime, t: datetime) -> bool:
    return start <= t < end


def _dedupe_intervals_by_source(
    intervals: list[tuple],
) -> list[tuple]:
    """Repeat source identity must not inflate simultaneous occupancy."""
    seen: dict[str, tuple] = {}
    for item in intervals:
        finding = item[0]
        sid = finding.source_operation_identity
        if sid not in seen:
            seen[sid] = item
    return list(seen.values())


def _peak_simultaneous_claimed_workers(intervals: list[tuple]) -> tuple[int, tuple[str, ...]]:
    """Peak claimed workers under half-open semantics; not a scheduling engine.

    Evaluates occupancy at each unique interval start (points where count can rise).
    Pairwise overlap graphs are intentionally not summed into a false concurrent total.
    """
    uniq = _dedupe_intervals_by_source(intervals)
    peak = 0
    peak_ops: tuple[str, ...] = ()
    for _, t0, _, _ in uniq:
        active = [
            (fj, cj)
            for fj, b0, b1, cj in uniq
            if _active_half_open(b0, b1, t0)
        ]
        count = sum(len(cj.worker_identities) for _, cj in active)
        if count > peak:
            peak = count
            peak_ops = tuple(fj.source_operation_identity for fj, _ in active)
    return peak, peak_ops


def evaluate_s05(
    audit_input: ShiftAuditInput,
    s01: ShiftAuditArtifact,
    s10: ShiftOperationClassificationArtifact,
    s02: ShiftTechnologicalIntegrityArtifact,
    s03: ShiftPhysicalIntegrityArtifact,
    s11: ShiftLaborBenchmarkArtifact,
    s04: ShiftExecutionCostArtifact,
    *,
    audit_id: Optional[str] = None,
    run_id: Optional[str] = None,
    temporal_claims: Sequence[OperationTemporalClaim] = (),
    shift_temporal_context: Optional[ShiftTemporalContext] = None,
) -> ShiftTemporalIntegrityArtifact:
    del s03, s04  # joint chain; S05 does not mutate prior artifacts
    ctx = shift_temporal_context or ShiftTemporalContext()
    s11_by_id = {f.source_operation_identity: f for f in s11.findings}

    # --- A. Mathematical time balance from S01 (do not recompute engine) ---
    m = s01.s01_metrics
    target = m.target_fund_man_minutes
    claimed = m.claimed_total_man_minutes
    signed_dev = m.absolute_deviation_man_minutes  # S01: target - claimed
    coverage = m.fund_coverage_pct
    unallocated = None
    if target is not None and claimed is not None:
        unallocated = float(target) - float(claimed)

    time_balance = TemporalFindingStatus.TIME_BALANCE_COMPUTABLE
    if target is None or claimed is None:
        time_balance = TemporalFindingStatus.TEMPORAL_CONTEXT_INSUFFICIENT

    # --- Per-operation evaluation ---
    findings: list[TemporalOperationFinding] = []
    parsed_intervals: list[tuple[TemporalOperationFinding, datetime, datetime, OperationTemporalClaim]] = []
    unresolved: list[str] = []
    any_conflict = False
    any_interval = False

    for line in s10.classifications:
        f11 = s11_by_id.get(line.source_operation_identity)
        labor_mm = _s11_mm(f11) if f11 else (
            float(line.claimed_labor_quantity)
            if line.claimed_labor_quantity is not None
            and line.claimed_labor_unit == LaborUnit.MAN_MINUTE.value
            else None
        )
        tclaim = _match_temporal_claim(
            temporal_claims,
            source_identity=line.source_operation_identity,
            original=line.original_operation_text,
        )
        statuses: list[TemporalFindingStatus] = []
        temporal_notes: list[str] = []
        overlap_notes: list[str] = []
        clarification = None

        if time_balance == TemporalFindingStatus.TIME_BALANCE_COMPUTABLE:
            statuses.append(TemporalFindingStatus.TIME_BALANCE_COMPUTABLE)

        # Default: chronology / allocation not proven
        statuses.append(TemporalFindingStatus.CHRONOLOGY_NOT_PROVEN)
        statuses.append(TemporalFindingStatus.WORKER_ALLOCATION_NOT_PROVEN)
        temporal_notes.append("REPORT_ROW_ORDER_NE_EXECUTION_CHRONOLOGY")
        temporal_notes.append("REGISTRATION_TIMESTAMP_NE_EXECUTION_TIMESTAMP")
        temporal_notes.append("MAN_MINUTES_NE_ELAPSED_MINUTES")
        temporal_notes.append("CREW_SIZE_NE_ACTUAL_OPERATION_WORKER_ALLOCATION")

        ts_auth = TimestampAuthority.ABSENT
        start_s = end_s = None
        elapsed = None
        workers: tuple[str, ...] = ()
        alloc_status = "WORKER_ALLOCATION_NOT_PROVEN"
        cond_bound = None
        cond_assumption = None
        capacity_status = "CAPACITY_NOT_EVALUATED_INSUFFICIENT_ALLOCATION"
        chronology_auth = "CHRONOLOGY_NOT_PROVEN"

        # Conditional duration bound (scenario capacity only)
        max_workers = None
        if tclaim and tclaim.maximum_simultaneous_workers_scenario is not None:
            max_workers = tclaim.maximum_simultaneous_workers_scenario
        elif ctx.maximum_simultaneous_workers_scenario is not None:
            max_workers = ctx.maximum_simultaneous_workers_scenario
        # crew_size alone is NOT automatic operation allocation — only when
        # explicitly provided as scenario maximum simultaneous workers.
        if labor_mm is not None and max_workers is not None and max_workers > 0:
            cond_bound = float(labor_mm) / float(max_workers)
            cond_assumption = (
                f"labor_effort/{max_workers}_simultaneous_workers_SCENARIO_ONLY; "
                "CONDITIONAL_DURATION_BOUND_NE_ACTUAL_OPERATION_DURATION; "
                "CREW_SIZE_NOT_USED_AS_AUTOMATIC_ALLOCATION"
            )
            statuses.append(TemporalFindingStatus.CONDITIONAL_DURATION_BOUND_COMPUTED)
            temporal_notes.append(cond_assumption)
        elif labor_mm is not None and audit_input.crew_size > 0:
            temporal_notes.append(
                "crew_size_present_but_not_used_as_automatic_operation_allocation; "
                "provide maximum_simultaneous_workers_scenario for conditional bound"
            )
            statuses.append(TemporalFindingStatus.TEMPORAL_CONTEXT_INSUFFICIENT)

        if tclaim:
            workers = tclaim.worker_identities
            if workers:
                alloc_status = "WORKER_IDENTITIES_CLAIMED_NOT_VERIFIED"
            if tclaim.participation_semantics:
                temporal_notes.append(
                    f"participation_semantics_claimed={tclaim.participation_semantics}; "
                    "not evidence-supported actual participation"
                )
            if tclaim.exclusive_active_work is None and workers:
                temporal_notes.append(
                    "unknown_participation_semantics; overlap_not_automatic_double_count"
                )
            ts_auth = tclaim.timestamp_authority
            if tclaim.registration_timestamp_utc and not (
                tclaim.claimed_start_utc or tclaim.claimed_end_utc
            ):
                temporal_notes.append(
                    "registration_timestamp_present_but_not_execution_interval"
                )
                statuses.append(TemporalFindingStatus.TEMPORAL_CONTEXT_INSUFFICIENT)

            start_s = tclaim.claimed_start_utc
            end_s = tclaim.claimed_end_utc
            if start_s or end_s:
                any_interval = True
                start_dt, start_err = _parse_iso(start_s)
                end_dt, end_err = _parse_iso(end_s)
                tz_ok = tclaim.timezone_explicit or (
                    start_dt is not None
                    and start_dt.tzinfo is not None
                    and end_dt is not None
                    and end_dt.tzinfo is not None
                )
                if not tz_ok or start_err == "timezone_absent_ambiguous" or end_err == "timezone_absent_ambiguous":
                    statuses.append(TemporalFindingStatus.AMBIGUOUS_TIMEZONE_OR_DATE)
                    temporal_notes.append("ambiguous_timezone_or_date_semantics")
                    clarification = "Укажите явный timezone и ISO-8601 start/end."
                if start_err == "unparseable_timestamp" or end_err == "unparseable_timestamp":
                    statuses.append(TemporalFindingStatus.INVALID_TIME_INTERVAL)
                    temporal_notes.append("unparseable_claimed_interval")
                elif start_dt is not None and end_dt is not None:
                    interval_usable = False
                    if end_dt < start_dt:
                        # Explicit end datetime earlier than start is INVALID.
                        # Overnight flag must NOT invent a corrected end date.
                        # Valid midnight crossing requires end >= start with
                        # sufficient explicit date basis (e.g. next calendar day).
                        statuses.append(TemporalFindingStatus.INVALID_TIME_INTERVAL)
                        temporal_notes.append(
                            "end_before_start_INVALID; "
                            "overnight_flag_does_not_auto_correct_dates"
                        )
                        if ctx.overnight_shift_explicit:
                            temporal_notes.append(
                                "overnight_declared_but_end_datetime_still_before_start"
                            )
                        clarification = (
                            "Укажите корректные даты start/end "
                            "(переход через полночь — end на следующий календарный день)."
                        )
                    else:
                        elapsed = (end_dt - start_dt).total_seconds() / 60.0
                        if elapsed == 0:
                            temporal_notes.append(
                                "zero_duration_interval_semantics_require_clarification"
                            )
                        if (
                            ctx.overnight_shift_explicit
                            and start_dt.date() != end_dt.date()
                        ):
                            temporal_notes.append(
                                "overnight_shift_explicitly_declared_with_date_rollover"
                            )
                        statuses.append(TemporalFindingStatus.INTERVAL_VALID_CLAIMED_ONLY)
                        chronology_auth = "CLAIMED_INTERVAL_PRESENT_NOT_VERIFIED"
                        temporal_notes.append("CLAIMED_CHRONOLOGY_NE_VERIFIED_CHRONOLOGY")
                        interval_usable = True

                    # Shift bounds check (claimed-only; not verified chronology)
                    shift_start, _ = _parse_iso(ctx.shift_start_utc)
                    shift_end, _ = _parse_iso(ctx.shift_end_utc)
                    if interval_usable and shift_start and shift_end:
                        if start_dt < shift_start or end_dt > shift_end:
                            statuses.append(
                                TemporalFindingStatus.OUTSIDE_KNOWN_SHIFT_INTERVAL
                            )
                            temporal_notes.append(
                                "claimed_interval_outside_known_shift_bounds"
                            )

                    # Labor vs interval capacity (requires workers or scenario max)
                    if (
                        interval_usable
                        and elapsed is not None
                        and elapsed > 0
                        and labor_mm is not None
                    ):
                        capacity_workers = max_workers
                        if capacity_workers is None and workers:
                            capacity_workers = len(workers)
                        if capacity_workers and capacity_workers > 0:
                            max_labor = elapsed * float(capacity_workers)
                            if labor_mm > max_labor + 1e-9:
                                statuses.append(
                                    TemporalFindingStatus.LABOR_EXCEEDS_INTERVAL_CAPACITY
                                )
                                capacity_status = (
                                    "CLAIMED_LABOR_EXCEEDS_INTERVAL_CAPACITY_UNDER_ASSUMPTIONS"
                                )
                                temporal_notes.append(
                                    f"labor_mm={labor_mm} > elapsed={elapsed}*{capacity_workers}"
                                )
                                any_conflict = True
                            else:
                                capacity_status = (
                                    "LABOR_WITHIN_INTERVAL_CAPACITY_UNDER_ASSUMPTIONS"
                                )
                        else:
                            capacity_status = (
                                "CAPACITY_NOT_EVALUATED_INSUFFICIENT_ALLOCATION"
                            )
                            temporal_notes.append(
                                "cannot_test_labor_vs_elapsed_without_worker_count_or_scenario_max"
                            )
                elif (start_s and not end_s) or (end_s and not start_s):
                    statuses.append(TemporalFindingStatus.TEMPORAL_CONTEXT_INSUFFICIENT)
                    temporal_notes.append("incomplete_start_or_end")
            else:
                statuses.append(TemporalFindingStatus.TEMPORAL_CONTEXT_INSUFFICIENT)
                temporal_notes.append("no_explicit_operation_interval")
        else:
            statuses.append(TemporalFindingStatus.TEMPORAL_CONTEXT_INSUFFICIENT)
            temporal_notes.append("no_temporal_claim_supplied")

        # Demo S02 does not create confirmed chronology violation
        demo_s02 = True
        for sf in s02.findings:
            if (
                sf.source_operation_identity == line.source_operation_identity
                or sf.original_operation_text == line.original_operation_text
            ):
                if not (
                    sf.demonstration_rule
                    or sf.source_authority == SourceAuthority.DEMONSTRATION_RULE
                    or sf.applicable_rule_id is None
                ):
                    demo_s02 = False
        if demo_s02:
            temporal_notes.append(
                "demonstration_s02_findings_do_not_create_confirmed_chronology_violation"
            )

        conclusion_parts = [
            f"Labor effort={labor_mm} man-minutes (≠ elapsed)."
            if labor_mm is not None
            else "Labor effort unavailable.",
            "Actual interval: "
            + ("present claimed-only" if (start_s and end_s) else "ABSENT → chronology NOT_PROVEN")
            + ".",
            f"Conditional duration bound: {cond_bound} min under stated assumptions."
            if cond_bound is not None
            else "Conditional duration bound: not computed (no scenario max simultaneous workers).",
            (
                "WORKER_ALLOCATION_NOT_PROVEN."
                if not workers
                else f"Workers claimed_count={len(workers)} (identities not logged; not verified)."
            ),
            "No fraud/idle/payroll classification.",
        ]

        finding = TemporalOperationFinding(
            check_identity=f"s05:{line.source_operation_identity}:temporal",
            source_operation_identity=line.source_operation_identity,
            original_operation_text=line.original_operation_text,
            canonical_operation_code=line.operation_code_candidate,
            canonical_operation_name=line.canonical_operation_candidate,
            original_claimed_labor_quantity=f11.original_claimed_labor_quantity if f11 else line.claimed_labor_quantity,
            original_labor_unit=f11.original_labor_unit if f11 else line.claimed_labor_unit,
            labor_semantics=f11.labor_semantics if f11 else audit_input.labor_semantics_status.value,
            labor_man_minutes=labor_mm,
            claimed_start_utc=start_s,
            claimed_end_utc=end_s,
            timestamp_authority=ts_auth if tclaim else TimestampAuthority.ABSENT,
            elapsed_duration_minutes=elapsed,
            worker_identities=workers,
            allocation_evidence_status=alloc_status,
            conditional_duration_bound_minutes=cond_bound,
            conditional_bound_assumption=cond_assumption,
            temporal_findings=tuple(dict.fromkeys(temporal_notes)),
            overlap_findings=(),
            temporal_capacity_status=capacity_status,
            chronology_authority=chronology_auth,
            finding_statuses=tuple(dict.fromkeys(statuses)),
            provenance=(
                f"project={audit_input.project_code}",
                f"crew={audit_input.crew_id}",
                f"s01_time_balance={time_balance.value}",
                f"rules={S05_RULES_VERSION}",
            ),
            rules_version=S05_RULES_VERSION,
            professional_conclusion=" ".join(conclusion_parts),
            clarification_request=clarification,
            preserved_claimed_labor_quantity=f11.preserved_claimed_labor_quantity if f11 else line.claimed_labor_quantity,
        )
        findings.append(finding)

        if tclaim and start_s and end_s:
            sdt, serr = _parse_iso(start_s)
            edt, eerr = _parse_iso(end_s)
            # Only chronologically valid intervals enter overlap/capacity passes.
            # Overnight is never synthesized by adding a day.
            if (
                sdt
                and edt
                and serr is None
                and eerr is None
                and edt >= sdt
            ):
                parsed_intervals.append((finding, sdt, edt, tclaim))

    # --- Overlap / capacity passes ---
    updated: list[TemporalOperationFinding] = []
    finding_overlaps: dict[str, list[str]] = {f.source_operation_identity: [] for f in findings}
    finding_status_extra: dict[str, list[TemporalFindingStatus]] = {
        f.source_operation_identity: [] for f in findings
    }
    finding_capacity_authority: dict[str, CapacityAuthority] = {}

    for i, (fi, a0, a1, ci) in enumerate(parsed_intervals):
        for j, (fj, b0, b1, cj) in enumerate(parsed_intervals):
            if j <= i:
                continue
            if not _intervals_overlap(a0, a1, b0, b1):
                continue
            workers_i = set(ci.worker_identities)
            workers_j = set(cj.worker_identities)
            shared = workers_i & workers_j
            note = (
                f"claimed_interval_overlap_with:{fj.source_operation_identity}"
            )
            finding_overlaps[fi.source_operation_identity].append(note)
            finding_overlaps[fj.source_operation_identity].append(
                f"claimed_interval_overlap_with:{fi.source_operation_identity}"
            )
            finding_status_extra[fi.source_operation_identity].append(
                TemporalFindingStatus.CLAIMED_INTERVAL_OVERLAP
            )
            finding_status_extra[fj.source_operation_identity].append(
                TemporalFindingStatus.CLAIMED_INTERVAL_OVERLAP
            )

            if shared:
                # Same worker overlap
                excl_i = ci.exclusive_active_work is True
                excl_j = cj.exclusive_active_work is True
                if excl_i and excl_j:
                    msg = (
                        f"EXCLUSIVE_WORKER_ALLOCATION_CONFLICT "
                        f"shared_worker_count={len(shared)} "
                        f"ops=({fi.source_operation_identity},{fj.source_operation_identity}); "
                        "claimed conflict; not automatic fraud classification"
                    )
                    finding_overlaps[fi.source_operation_identity].append(msg)
                    finding_overlaps[fj.source_operation_identity].append(msg)
                    finding_status_extra[fi.source_operation_identity].append(
                        TemporalFindingStatus.EXCLUSIVE_WORKER_ALLOCATION_CONFLICT
                    )
                    finding_status_extra[fj.source_operation_identity].append(
                        TemporalFindingStatus.EXCLUSIVE_WORKER_ALLOCATION_CONFLICT
                    )
                    any_conflict = True
                else:
                    msg = (
                        f"same_worker_overlap_without_proven_exclusive_semantics "
                        f"shared_worker_count={len(shared)}; uncertainty; "
                        "not proven double-count; not automatic fraud"
                    )
                    finding_overlaps[fi.source_operation_identity].append(msg)
                    finding_overlaps[fj.source_operation_identity].append(msg)
                    finding_status_extra[fi.source_operation_identity].append(
                        TemporalFindingStatus.TEMPORAL_CONTEXT_INSUFFICIENT
                    )
                    finding_status_extra[fj.source_operation_identity].append(
                        TemporalFindingStatus.TEMPORAL_CONTEXT_INSUFFICIENT
                    )
            else:
                if workers_i or workers_j:
                    msg = (
                        "different_workers_overlapping_intervals_not_automatic_conflict"
                    )
                    finding_overlaps[fi.source_operation_identity].append(msg)
                    finding_overlaps[fj.source_operation_identity].append(msg)
                else:
                    # Same crew possible parallel without worker allocation
                    msg = (
                        "same_crew_parallel_operations_without_worker_allocation_"
                        "INSUFFICIENT_CONTEXT; PARALLEL_OPERATIONS_NE_AUTOMATIC_TIME_CONFLICT"
                    )
                    finding_overlaps[fi.source_operation_identity].append(msg)
                    finding_overlaps[fj.source_operation_identity].append(msg)
                    finding_status_extra[fi.source_operation_identity].append(
                        TemporalFindingStatus.TEMPORAL_CONTEXT_INSUFFICIENT
                    )
                    finding_status_extra[fj.source_operation_identity].append(
                        TemporalFindingStatus.TEMPORAL_CONTEXT_INSUFFICIENT
                    )
                    unresolved.append(msg)

    # Simultaneous capacity under half-open intervals; authority-tagged.
    # Prefer confirmed available capacity over scenario assumption when both set.
    capacity_limit: Optional[int] = None
    capacity_auth: Optional[CapacityAuthority] = None
    if ctx.confirmed_available_crew_capacity is not None:
        capacity_limit = ctx.confirmed_available_crew_capacity
        capacity_auth = CapacityAuthority.CONFIRMED_AVAILABLE_CREW_CAPACITY
    elif ctx.maximum_simultaneous_workers_scenario is not None:
        capacity_limit = ctx.maximum_simultaneous_workers_scenario
        capacity_auth = CapacityAuthority.SCENARIO_ASSUMPTION

    if capacity_limit is not None and parsed_intervals:
        peak, peak_ops = _peak_simultaneous_claimed_workers(parsed_intervals)
        if peak > capacity_limit:
            if capacity_auth == CapacityAuthority.SCENARIO_ASSUMPTION:
                status = TemporalFindingStatus.SCENARIO_CAPACITY_LIMIT_EXCEEDED
                msg = (
                    f"SCENARIO_CAPACITY_LIMIT_EXCEEDED peak_claimed_workers={peak} "
                    f"> scenario_max={capacity_limit}; "
                    f"authority={capacity_auth.value}; "
                    "scenario condition violation ≠ proven physical capacity conflict; "
                    "not fraud"
                )
            else:
                status = TemporalFindingStatus.CAPACITY_CONFLICT
                msg = (
                    f"CAPACITY_CONFLICT peak_claimed_workers={peak} "
                    f"> confirmed_available={capacity_limit}; "
                    f"authority={capacity_auth.value}; "
                    "claimed-allocation conflict within available authority; "
                    "≠ evidence-supported actual participation conflict; not fraud"
                )
            for sid in peak_ops or {
                fi.source_operation_identity for fi, _, _, _ in parsed_intervals
            }:
                finding_overlaps[sid].append(msg)
                finding_status_extra[sid].append(status)
                finding_capacity_authority[sid] = capacity_auth  # type: ignore[assignment]
            any_conflict = True
            unresolved.append(msg)

    for f in findings:
        extra_ov = tuple(finding_overlaps.get(f.source_operation_identity, []))
        extra_st = tuple(finding_status_extra.get(f.source_operation_identity, []))
        cap_auth = finding_capacity_authority.get(f.source_operation_identity)
        updated.append(
            TemporalOperationFinding(
                check_identity=f.check_identity,
                source_operation_identity=f.source_operation_identity,
                original_operation_text=f.original_operation_text,
                canonical_operation_code=f.canonical_operation_code,
                canonical_operation_name=f.canonical_operation_name,
                original_claimed_labor_quantity=f.original_claimed_labor_quantity,
                original_labor_unit=f.original_labor_unit,
                labor_semantics=f.labor_semantics,
                labor_man_minutes=f.labor_man_minutes,
                claimed_start_utc=f.claimed_start_utc,
                claimed_end_utc=f.claimed_end_utc,
                timestamp_authority=f.timestamp_authority,
                elapsed_duration_minutes=f.elapsed_duration_minutes,
                worker_identities=f.worker_identities,
                allocation_evidence_status=f.allocation_evidence_status,
                conditional_duration_bound_minutes=f.conditional_duration_bound_minutes,
                conditional_bound_assumption=f.conditional_bound_assumption,
                temporal_findings=f.temporal_findings,
                overlap_findings=extra_ov,
                temporal_capacity_status=f.temporal_capacity_status,
                chronology_authority=f.chronology_authority,
                finding_statuses=tuple(dict.fromkeys(f.finding_statuses + extra_st)),
                provenance=f.provenance,
                rules_version=f.rules_version,
                professional_conclusion=f.professional_conclusion
                + ((" Overlaps: " + "; ".join(extra_ov)) if extra_ov else ""),
                clarification_request=f.clarification_request,
                preserved_claimed_labor_quantity=f.preserved_claimed_labor_quantity,
                capacity_conflict_authority=cap_auth,
            )
        )
    findings = updated

    # Dedup observation identities (repeat audit ≠ new event)
    seen_ids: set[str] = set()
    for f in findings:
        if f.source_operation_identity in seen_ids:
            unresolved.append(
                f"duplicate_source_operation_identity_in_audit:{f.source_operation_identity}"
            )
        seen_ids.add(f.source_operation_identity)

    if any_conflict:
        feasibility = TemporalFeasibilityStatus.CONFLICT_IN_CLAIMED_DATA
    elif any_interval:
        feasibility = TemporalFeasibilityStatus.FEASIBLE_UNDER_STATED_ASSUMPTIONS
        # still may be insufficient for full feasibility
        if any(
            TemporalFindingStatus.TEMPORAL_CONTEXT_INSUFFICIENT in f.finding_statuses
            for f in findings
        ):
            # mix: keep assumptions label if no hard conflict
            pass
    else:
        feasibility = TemporalFeasibilityStatus.INSUFFICIENT_CONTEXT

    chrono = ChronologyVerificationStatus.CHRONOLOGY_NOT_PROVEN
    if any_interval:
        chrono = ChronologyVerificationStatus.CLAIMED_INTERVALS_PRESENT_NOT_VERIFIED

    interval_coverage = (
        "SOME_CLAIMED_INTERVALS_PRESENT"
        if any_interval
        else "NO_EXPLICIT_OPERATION_INTERVALS"
    )

    summary = ShiftTemporalSummary(
        target_productive_fund_man_minutes=target,
        total_claimed_labor_man_minutes=claimed,
        signed_deviation_man_minutes=signed_dev,
        coverage_pct=coverage,
        time_balance_status=time_balance,
        unallocated_relative_to_target_man_minutes=unallocated,
        unallocated_classification=(
            "UNALLOCATED_RELATIVE_TO_TARGET_NE_AUTOMATIC_IDLE_OR_LOSS_OR_UNPAID"
        ),
        individual_allocation_readiness="WORKER_ALLOCATION_NOT_PROVEN",
        operation_interval_coverage=interval_coverage,
        temporal_feasibility_status=feasibility,
        chronology_verification_status=chrono,
        unresolved_temporal_findings=tuple(dict.fromkeys(unresolved)),
        notes=(
            "Level A: mathematical time balance from S01.",
            "Level B: feasibility only under stated assumptions.",
            "Level C: evidence-supported chronology NOT_PROVEN without verified intervals.",
            "UNALLOCATED_TIME_NE_AUTOMATIC_IDLE_TIME",
            "TARGET_PRODUCTIVE_FUND_NE_ACTUAL_ATTENDANCE",
            "PARALLEL_OPERATIONS_NE_AUTOMATIC_TIME_CONFLICT",
            "OVERLAPPING_INTERVALS_NE_AUTOMATIC_FRAUD",
            "MISSING_TIMESTAMPS_NE_PROVEN_VIOLATION",
            "GAPS_BETWEEN_INTERVALS_NE_AUTOMATIC_IDLE",
            "NO_CPM_OR_SCHEDULING_ENGINE",
            "ABSENCE_OF_DETECTED_CONFLICTS_NE_VERIFIED_SHIFT",
            "SCENARIO_CAPACITY_LIMIT_NE_PROVEN_PHYSICAL_CAPACITY_CONFLICT",
            "HALF_OPEN_INTERVALS_TOUCHING_ENDPOINTS_NE_OVERLAP",
        ),
    )

    observations = [
        "S05 = deterministic temporal integrity skill.",
        "MAN-MINUTES != ELAPSED MINUTES.",
        "CREW SIZE != ACTUAL OPERATION WORKER ALLOCATION.",
        "REPORT ROW ORDER != EXECUTION CHRONOLOGY.",
        "REGISTRATION TIMESTAMP != EXECUTION TIMESTAMP.",
        "ARITHMETIC LABOR BALANCE != VERIFIED TEMPORAL FEASIBILITY.",
        "TARGET PRODUCTIVE FUND != ACTUAL ATTENDANCE.",
        "PARALLEL OPERATIONS != AUTOMATIC TIME CONFLICT.",
        "OVERLAPPING INTERVALS != AUTOMATIC FRAUD.",
        "UNALLOCATED TIME != AUTOMATIC IDLE TIME.",
        "MISSING TIMESTAMPS != PROVEN VIOLATION.",
        "CONDITIONAL DURATION BOUND != ACTUAL OPERATION DURATION.",
        "CLAIMED CHRONOLOGY != VERIFIED CHRONOLOGY.",
        "ABSENCE OF DETECTED CONFLICTS != VERIFIED SHIFT.",
        "SCENARIO CAPACITY LIMIT EXCEEDED != PROVEN PHYSICAL CONFLICT.",
        f"Rules: {S05_RULES_VERSION}.",
        "S05_ENGINE_IMPLEMENTED; CHRONOLOGY_NOT_PROVEN; WORKER_ALLOCATION_NOT_PROVEN.",
    ]

    summary_lines = [
        "PSAA S05 — Temporal Integrity",
        f"Проект: {audit_input.project_code} date={audit_input.work_date} crew={audit_input.crew_id}",
        (
            f"Time balance: target={target} claimed={claimed} "
            f"signed_dev={signed_dev} coverage={coverage} "
            f"unallocated={unallocated} [{summary.unallocated_classification}]"
        ),
        f"Feasibility={feasibility.value}; Chronology={chrono.value}",
        "Managerial acceptance: NOT_IN_SCOPE | Payroll/Disciplinary/Fraud: NOT_PERFORMED",
    ]
    for f in findings:
        summary_lines.append(
            f"- «{f.original_operation_text}» | labor={f.labor_man_minutes} | "
            f"interval={'yes' if f.claimed_start_utc and f.claimed_end_utc else 'no'} | "
            f"cond_bound={f.conditional_duration_bound_minutes} | "
            f"statuses={[s.value for s in f.finding_statuses]}"
        )

    return ShiftTemporalIntegrityArtifact(
        schema_version=S05_ARTIFACT_SCHEMA_VERSION,
        rules_version=S05_RULES_VERSION,
        audit_id=audit_id or s01.audit_id or str(uuid.uuid4()),
        agent_code=AGENT_CODE,
        agent_version=AGENT_VERSION,
        run_id=run_id,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        project_code=audit_input.project_code,
        work_date=audit_input.work_date,
        crew_id=audit_input.crew_id,
        evaluation_domain="temporal_integrity_claimed_time",
        findings=tuple(findings),
        shift_summary=summary,
        observations=tuple(observations),
        managerial_acceptance_status="NOT_IN_SCOPE",
        payroll_decision_status="NOT_PERFORMED",
        disciplinary_decision_status="NOT_PERFORMED",
        fraud_classification_status="NOT_PERFORMED",
        human_readable_summary="\n".join(summary_lines),
        s05_engine_status="S05_ENGINE_IMPLEMENTED",
        mathematical_time_balance_status="COMPUTABLE_WHEN_S01_ALLOWS",
        temporal_feasibility_status_label="ONLY_UNDER_STATED_ASSUMPTIONS",
        chronology_status="CHRONOLOGY_NOT_PROVEN",
        durable_history_schema_status="UNCHANGED_IN_THIS_INCREMENT",
    )
