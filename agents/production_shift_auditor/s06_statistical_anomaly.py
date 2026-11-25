"""S06 — Statistical Anomaly Detection (deterministic).

Levels (must not be conflated):
  A. Descriptive statistical observation
  B. Configured threshold exceedance
  C. Statistical anomaly candidate from comparable history
  D. Inherited professional finding (reuse prior skills)
  E. Proven violation — NEVER assigned automatically by S06

Does not invent norms, remove observations, rank workers, or assign fraud.
"""

from __future__ import annotations

import statistics
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Optional, Sequence

from agents.production_shift_auditor.contracts import (
    LaborUnit,
    ShiftAuditArtifact,
    ShiftAuditInput,
)
from agents.production_shift_auditor.s02_contracts import ShiftTechnologicalIntegrityArtifact
from agents.production_shift_auditor.s03_contracts import ShiftPhysicalIntegrityArtifact
from agents.production_shift_auditor.s04_contracts import ShiftExecutionCostArtifact
from agents.production_shift_auditor.s05_contracts import (
    ShiftTemporalIntegrityArtifact,
    TemporalFindingStatus,
)
from agents.production_shift_auditor.s06_contracts import (
    S06_ARTIFACT_SCHEMA_VERSION,
    S06_RULES_VERSION,
    ConcentrationSummary,
    EvidenceAuthority,
    RepeatedValueSummary,
    ReportingPrecisionPolicy,
    ReviewPriority,
    RoundingSummary,
    ShiftStatisticalAnomalyArtifact,
    ShiftStatisticalSummary,
    SignalType,
    StatisticalAnomalySignal,
    StatisticalMethod,
    StatisticalReferenceObservation,
    StatisticalSignalStatus,
    StatisticalThresholdConfig,
)
from agents.production_shift_auditor.s10_contracts import ShiftOperationClassificationArtifact
from agents.production_shift_auditor.s11_contracts import (
    ComparabilityStatus,
    LaborCalculationStatus,
    ShiftLaborBenchmarkArtifact,
)

AGENT_CODE = "PRODUCTION_SHIFT_AUDITOR"
AGENT_VERSION = "0.1"

# Consistency factor for modified Z-score using MAD (Iglewicz & Hoaglin)
_MAD_Z_FACTOR = 0.6745


def _median(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return float(statistics.median(values))


def _mad(values: Sequence[float], med: Optional[float] = None) -> Optional[float]:
    if not values:
        return None
    m = med if med is not None else _median(values)
    if m is None:
        return None
    return float(statistics.median([abs(v - m) for v in values]))


def _modified_z(value: float, med: float, mad: float) -> Optional[float]:
    if mad == 0:
        return None
    return (_MAD_Z_FACTOR * (value - med)) / mad


def _labor_mm_from_claim(qty: Optional[float], unit) -> Optional[float]:
    if qty is None:
        return None
    u = unit.value if hasattr(unit, "value") else unit
    if u == LaborUnit.MAN_MINUTE.value or u == LaborUnit.MAN_MINUTE:
        return float(qty)
    if u == LaborUnit.MAN_HOUR.value or u == LaborUnit.MAN_HOUR:
        return float(qty) * 60.0
    return None


def _top_n_with_ties(
    items: list[tuple[str, float]],
    n: int,
) -> tuple[list[tuple[str, float]], Optional[str]]:
    """Select top-N by value descending; preserve tie transparency at the cutoff.

    Stable name order among equal values is for deterministic reporting only —
    it does not assign professional priority among tied operations.
    """
    if not items or n <= 0:
        return [], None
    ranked = sorted(items, key=lambda x: (-x[1], x[0]))
    if len(ranked) <= n:
        return ranked, None
    cutoff_val = ranked[n - 1][1]
    selected: list[tuple[str, float]] = []
    for name, val in ranked:
        if len(selected) < n:
            selected.append((name, val))
        else:
            break
    note = None
    same_at_cutoff = [name for name, val in ranked if abs(val - cutoff_val) < 1e-12]
    if len(same_at_cutoff) > 1:
        note = (
            f"tie_at_{cutoff_val}_man_minutes among={same_at_cutoff}; "
            f"top{n}_descriptive_slot_fill={ [n for n, _ in selected] }; "
            "tie_selection_non_preferential_deterministic_only; "
            "NO_FALSE_PRIORITY_AMONG_TIED_OPERATIONS; "
            "COST_CONCENTRATION_NE_INEFFICIENCY; "
            "DESCRIPTIVE_OBSERVATION_NE_STATISTICAL_ANOMALY"
        )
    return selected, note


def _validate_threshold_config(
    cfg: StatisticalThresholdConfig,
) -> tuple[bool, tuple[str, ...]]:
    problems: list[str] = []
    if cfg.min_sample_size is None or cfg.min_sample_size < 1:
        problems.append("invalid_min_sample_size_requires_positive_integer")
    if (
        cfg.mad_modified_z_threshold is None
        or cfg.mad_modified_z_threshold <= 0
    ):
        problems.append("invalid_mad_modified_z_threshold_requires_positive")
    if (
        cfg.zero_dispersion_absolute_deviation_threshold is not None
        and cfg.zero_dispersion_absolute_deviation_threshold <= 0
    ):
        problems.append("invalid_zero_dispersion_absolute_deviation_threshold")
    for name, val in (
        ("top1_share_review_pct", cfg.top1_share_review_pct),
        ("top3_share_review_pct", cfg.top3_share_review_pct),
    ):
        if val is not None and val <= 0:
            problems.append(f"invalid_{name}_requires_positive")
    return (len(problems) == 0), tuple(problems)


def _context_fields(ref: StatisticalReferenceObservation) -> tuple[str, ...]:
    fields = []
    if ref.material_hint:
        fields.append(f"material={ref.material_hint}")
    if ref.geometry_hint:
        fields.append(f"geometry={ref.geometry_hint}")
    if ref.technology_hint:
        fields.append(f"technology={ref.technology_hint}")
    if ref.result_state:
        fields.append(f"result_state={ref.result_state}")
    if ref.labor_semantics:
        fields.append(f"labor_semantics={ref.labor_semantics}")
    if ref.execution_conditions_hint:
        fields.append(f"execution_conditions={ref.execution_conditions_hint}")
    return tuple(fields)


def _rich_comparability_ready(
    *,
    material: Optional[str],
    result_state: Optional[str],
    labor_semantics: Optional[str],
    ref: StatisticalReferenceObservation,
) -> tuple[bool, str]:
    """Code+unit alone is insufficient for statistical population membership."""
    matched: list[str] = []
    if material and ref.material_hint:
        if material != ref.material_hint:
            return False, "material_mismatch"
        matched.append("material")
    elif material or ref.material_hint:
        return False, "material_context_incomplete"

    if result_state and ref.result_state:
        if result_state != ref.result_state:
            return False, "result_state_mismatch"
        matched.append("result_state")
    elif ref.result_state and not result_state:
        return False, "result_state_context_incomplete"

    if labor_semantics and ref.labor_semantics:
        if labor_semantics != ref.labor_semantics:
            return False, "labor_semantics_mismatch"
        matched.append("labor_semantics")

    if ref.geometry_hint:
        return False, "geometry_context_incomplete"
    if ref.technology_hint and "technology" not in matched and "material" not in matched:
        return False, "technology_context_incomplete"
    if ref.execution_conditions_hint:
        return False, "execution_conditions_context_incomplete"

    if not matched:
        return False, "comparability_context_incomplete_code_unit_only"
    return True, "bucket_comparable_with_limitations_claimed_sample"


def _refs_comparable(
    ref: StatisticalReferenceObservation,
    *,
    op_code: Optional[str],
    physical_unit: Optional[str],
    material: Optional[str],
    geometry: Optional[str],
    technology: Optional[str],
    result_state: Optional[str],
    labor_semantics: Optional[str],
    project_code: str,
    authorized_project_scopes: Sequence[str],
) -> tuple[bool, str]:
    if not op_code or ref.operation_code != op_code:
        return False, "operation_code_mismatch"
    if not physical_unit or ref.physical_unit != physical_unit:
        return False, "physical_unit_mismatch"
    if material and ref.material_hint and ref.material_hint != material:
        return False, "material_mismatch"
    if geometry and ref.geometry_hint and ref.geometry_hint != geometry:
        return False, "geometry_mismatch"
    if technology and ref.technology_hint and ref.technology_hint != technology:
        return False, "technology_mismatch"
    if result_state and ref.result_state and ref.result_state != result_state:
        return False, "result_state_mismatch"
    if labor_semantics and ref.labor_semantics and ref.labor_semantics != labor_semantics:
        return False, "labor_semantics_mismatch"
    if ref.project_code and ref.project_code != project_code:
        if ref.project_code not in authorized_project_scopes and project_code not in authorized_project_scopes:
            # cross-project requires authorized scope containing the foreign project
            if "*" not in authorized_project_scopes and ref.project_code not in authorized_project_scopes:
                return False, "cross_project_scope_not_authorized"
    return True, "bucket_comparable_with_limitations"


def evaluate_s06(
    audit_input: ShiftAuditInput,
    s01: ShiftAuditArtifact,
    s10: ShiftOperationClassificationArtifact,
    s02: ShiftTechnologicalIntegrityArtifact,
    s03: ShiftPhysicalIntegrityArtifact,
    s11: ShiftLaborBenchmarkArtifact,
    s04: ShiftExecutionCostArtifact,
    s05: ShiftTemporalIntegrityArtifact,
    *,
    audit_id: Optional[str] = None,
    run_id: Optional[str] = None,
    threshold_config: Optional[StatisticalThresholdConfig] = None,
    reporting_precision: Optional[ReportingPrecisionPolicy] = None,
    statistical_references: Sequence[StatisticalReferenceObservation] = (),
    authorized_project_scopes: Sequence[str] = (),
    allow_future_reference_dates: bool = False,
    evaluation_as_of_date: Optional[str] = None,
) -> ShiftStatisticalAnomalyArtifact:
    del s02, s03  # available for inheritance via artifacts already passed where needed
    cfg = threshold_config or StatisticalThresholdConfig()
    precision = reporting_precision or ReportingPrecisionPolicy()
    as_of = evaluation_as_of_date or audit_input.work_date

    signals: list[StatisticalAnomalySignal] = []
    unresolved: list[str] = []
    cfg_ok, cfg_problems = _validate_threshold_config(cfg)
    mad_threshold_usable = cfg_ok
    if not cfg_ok:
        unresolved.extend(cfg_problems)
        signals.append(
            StatisticalAnomalySignal(
                signal_identity="s06:invalid_threshold_config",
                signal_type=SignalType.SAMPLE_INTEGRITY,
                status=StatisticalSignalStatus.REVIEW_REQUIRED,
                source_observation_identities=(),
                canonical_operation_code=None,
                canonical_operation_name=None,
                metric="threshold_config_validity",
                observed_value=None,
                reference_value=None,
                sample_size=None,
                statistical_method=StatisticalMethod.NOT_APPLICABLE,
                threshold_reference=f"{cfg.config_identity}/{cfg.version}",
                threshold_authority=cfg.authority,
                comparability_status="NOT_APPLICABLE",
                evidence_authority=EvidenceAuthority.CONFIGURED_THRESHOLD,
                deviation_value=None,
                review_priority=ReviewPriority.CLARIFICATION_REQUIRED,
                limitations=cfg_problems
                + (
                    "invalid_threshold_blocks_mad_anomaly_path",
                    "VIOLATION_NOT_PROVEN",
                ),
                provenance=(f"rules={S06_RULES_VERSION}",),
                rules_version=S06_RULES_VERSION,
                professional_conclusion=(
                    "Threshold configuration invalid; MAD anomaly path not applied. "
                    "VIOLATION_NOT_PROVEN."
                ),
                clarification_question=(
                    "Исправьте threshold config: положительные MAD threshold "
                    "и min_sample_size."
                ),
            )
        )

    # --- Labor values from S11 / S10 (preserve missing ≠ zero) ---
    s11_by_id = {f.source_operation_identity: f for f in s11.findings}
    labor_items: list[tuple[str, str, Optional[float]]] = []  # sid, name, mm
    for line in s10.classifications:
        f11 = s11_by_id.get(line.source_operation_identity)
        mm = None
        if f11 is not None and f11.eligible_labor_man_minutes is not None:
            mm = float(f11.eligible_labor_man_minutes)
        elif f11 is not None and f11.preserved_claimed_labor_quantity is not None:
            mm = _labor_mm_from_claim(
                f11.preserved_claimed_labor_quantity, f11.original_labor_unit
            )
        elif line.claimed_labor_quantity is not None:
            mm = _labor_mm_from_claim(line.claimed_labor_quantity, line.claimed_labor_unit)
        labor_items.append(
            (line.source_operation_identity, line.original_operation_text, mm)
        )

    present = [(sid, name, float(mm)) for sid, name, mm in labor_items if mm is not None]
    missing_count = sum(1 for _, _, mm in labor_items if mm is None)
    if missing_count:
        unresolved.append(
            f"missing_labor_observations={missing_count}; MISSING_NE_ZERO"
        )
        signals.append(
            StatisticalAnomalySignal(
                signal_identity="s06:missing_labor",
                signal_type=SignalType.SAMPLE_INTEGRITY,
                status=StatisticalSignalStatus.VIOLATION_NOT_PROVEN,
                source_observation_identities=tuple(
                    sid for sid, _, mm in labor_items if mm is None
                ),
                canonical_operation_code=None,
                canonical_operation_name=None,
                metric="missing_labor_count",
                observed_value=float(missing_count),
                reference_value=None,
                sample_size=len(labor_items),
                statistical_method=StatisticalMethod.NOT_APPLICABLE,
                threshold_reference=None,
                threshold_authority=None,
                comparability_status="NOT_APPLICABLE",
                evidence_authority=EvidenceAuthority.DESCRIPTIVE_ONLY,
                deviation_value=None,
                review_priority=ReviewPriority.CLARIFICATION_REQUIRED,
                limitations=("missing_labor_not_converted_to_zero",),
                provenance=(f"rules={S06_RULES_VERSION}",),
                rules_version=S06_RULES_VERSION,
                professional_conclusion=(
                    "Missing labor values preserved as missing; not zero-filled; "
                    "VIOLATION_NOT_PROVEN."
                ),
                clarification_question="Уточните отсутствующие трудозатраты операций.",
            )
        )

    total = sum(mm for _, _, mm in present) if present else None
    s01_total = (
        float(s01.s01_metrics.claimed_total_man_minutes)
        if s01.s01_metrics and s01.s01_metrics.claimed_total_man_minutes is not None
        else total
    )
    if s01_total is not None and total is not None and abs(s01_total - total) > 1e-6:
        unresolved.append(
            f"labor_conservation_check s01={s01_total} s06_sum={total}"
        )

    # Empty / zero-total safety
    if not present or total is None or total == 0:
        conc = ConcentrationSummary(
            total_claimed_labor_man_minutes=total if present else None,
            maximum_man_minutes=None,
            minimum_man_minutes=None,
            maximum_operation_names=(),
            minimum_operation_names=(),
            top1_share_pct=None,
            top3_share_pct=None,
            top4_share_pct=None,
            top1_operation_names=(),
            top3_operation_names=(),
            top4_operation_names=(),
            top3_tie_note=None,
            remaining_after_top3_man_minutes=None,
            notes=("empty_or_zero_total_sample; shares_not_computed",),
        )
        signals.append(
            StatisticalAnomalySignal(
                signal_identity="s06:empty_or_zero_sample",
                signal_type=SignalType.SAMPLE_INTEGRITY,
                status=StatisticalSignalStatus.INSUFFICIENT_COMPARABLE_HISTORY,
                source_observation_identities=(),
                canonical_operation_code=None,
                canonical_operation_name=None,
                metric="total_claimed_labor_man_minutes",
                observed_value=total,
                reference_value=None,
                sample_size=len(present),
                statistical_method=StatisticalMethod.NOT_APPLICABLE,
                threshold_reference=None,
                threshold_authority=None,
                comparability_status="NOT_APPLICABLE",
                evidence_authority=EvidenceAuthority.DESCRIPTIVE_ONLY,
                deviation_value=None,
                review_priority=ReviewPriority.CLARIFICATION_REQUIRED,
                limitations=("empty_or_zero_total_handled_safely",),
                provenance=(f"rules={S06_RULES_VERSION}",),
                rules_version=S06_RULES_VERSION,
                professional_conclusion=(
                    "Empty or zero-total labor sample; concentration shares not computed; "
                    "VIOLATION_NOT_PROVEN."
                ),
                clarification_question=None,
            )
        )
    else:
        by_name = [(name, mm) for _, name, mm in present]
        max_mm = max(mm for _, mm in by_name)
        min_mm = min(mm for _, mm in by_name)
        max_names = tuple(n for n, v in by_name if abs(v - max_mm) < 1e-12)
        min_names = tuple(n for n, v in by_name if abs(v - min_mm) < 1e-12)

        top1, tie1 = _top_n_with_ties(by_name, 1)
        top3, tie3 = _top_n_with_ties(by_name, 3)
        top4, tie4 = _top_n_with_ties(by_name, 4)
        top1_sum = sum(v for _, v in top1)
        top3_sum = sum(v for _, v in top3)
        top4_sum = sum(v for _, v in top4)
        top1_pct = (top1_sum / total) * 100.0
        top3_pct = (top3_sum / total) * 100.0
        top4_pct = (top4_sum / total) * 100.0
        remaining_top3 = total - top3_sum

        conc = ConcentrationSummary(
            total_claimed_labor_man_minutes=total,
            maximum_man_minutes=max_mm,
            minimum_man_minutes=min_mm,
            maximum_operation_names=max_names,
            minimum_operation_names=min_names,
            top1_share_pct=top1_pct,
            top3_share_pct=top3_pct,
            top4_share_pct=top4_pct,
            top1_operation_names=tuple(n for n, _ in top1),
            top3_operation_names=tuple(n for n, _ in top3),
            top4_operation_names=tuple(n for n, _ in top4),
            top3_tie_note=tie3,
            remaining_after_top3_man_minutes=remaining_top3,
            notes=(
                "shares_vs_claimed_total_not_target_fund",
                "COST_CONCENTRATION_NE_INEFFICIENCY",
                "DESCRIPTIVE_OBSERVATION_NE_STATISTICAL_ANOMALY",
                *(x for x in (tie1, tie3, tie4) if x),
            ),
        )

        # Descriptive concentration signals
        for label, pct, names, thr in (
            ("top1_share_pct", top1_pct, tuple(n for n, _ in top1), cfg.top1_share_review_pct),
            ("top3_share_pct", top3_pct, tuple(n for n, _ in top3), cfg.top3_share_review_pct),
            ("top4_share_pct", top4_pct, tuple(n for n, _ in top4), None),
        ):
            status = StatisticalSignalStatus.DESCRIPTIVE_OBSERVATION
            evidence = EvidenceAuthority.DESCRIPTIVE_ONLY
            priority = ReviewPriority.INFORMATION
            if thr is not None and pct > thr:
                status = StatisticalSignalStatus.THRESHOLD_EXCEEDANCE
                evidence = EvidenceAuthority.CONFIGURED_THRESHOLD
                priority = ReviewPriority.REVIEW_CANDIDATE
            signals.append(
                StatisticalAnomalySignal(
                    signal_identity=f"s06:concentration:{label}",
                    signal_type=SignalType.LABOR_CONCENTRATION,
                    status=status,
                    source_observation_identities=tuple(
                        sid for sid, name, _ in present if name in names
                    ),
                    canonical_operation_code=None,
                    canonical_operation_name=", ".join(names) if names else None,
                    metric=label,
                    observed_value=pct,
                    reference_value=thr,
                    sample_size=len(present),
                    statistical_method=(
                        StatisticalMethod.EXPLICIT_THRESHOLD_COMPARISON
                        if thr is not None
                        else StatisticalMethod.DESCRIPTIVE_SHARE
                    ),
                    threshold_reference=(
                        f"{cfg.config_identity}:{label}>{thr}" if thr is not None else None
                    ),
                    threshold_authority=cfg.authority if thr is not None else None,
                    comparability_status="NOT_APPLICABLE_WITHIN_SHIFT_MIX",
                    evidence_authority=evidence,
                    deviation_value=(pct - thr) if thr is not None else None,
                    review_priority=priority,
                    limitations=(
                        "COST_CONCENTRATION_NE_INEFFICIENCY",
                        "HIGH_REVIEW_PRIORITY_NE_HIGH_EVIDENCE_AUTHORITY",
                        "mixed_operations_in_shift_not_one_statistical_population",
                        "VIOLATION_NOT_PROVEN",
                        f"threshold_authority={cfg.authority}",
                    ),
                    provenance=(
                        f"project={audit_input.project_code}",
                        f"rules={S06_RULES_VERSION}",
                        f"threshold_config={cfg.config_identity}/{cfg.version}",
                    ),
                    rules_version=S06_RULES_VERSION,
                    professional_conclusion=(
                        f"{label}={pct:.4f}% of claimed labor among {names}. "
                        "Descriptive unless configured threshold exceeded. "
                        "Not inefficiency or proven violation."
                    ),
                    clarification_question=None,
                )
            )

    # --- Rounding / repetition ---
    vals = [mm for _, _, mm in present]
    div5 = sum(1 for v in vals if abs(v % 5.0) < 1e-9)
    div10 = sum(1 for v in vals if abs(v % 10.0) < 1e-9)
    freq = Counter(vals)
    repeated = tuple(sorted(((v, c) for v, c in freq.items() if c >= 2), key=lambda x: -x[1]))

    if precision.step_minutes is None:
        round_status = StatisticalSignalStatus.REPORTING_PRECISION_UNKNOWN
        round_notes = (
            "REPORTING_PRECISION_UNKNOWN; ROUNDING_NE_FABRICATION; "
            "no_unsupported_violation_from_divisibility_alone",
        )
    else:
        # Official precision makes matching divisibility descriptive, not violation
        round_status = StatisticalSignalStatus.DESCRIPTIVE_OBSERVATION
        round_notes = (
            f"reporting_precision_step={precision.step_minutes}",
            f"authority={precision.authority}",
            "ROUNDING_NE_FABRICATION",
            "explicit_policy_prevents_unsupported_violation_conclusion",
        )

    rounding = RoundingSummary(
        observation_count=len(vals),
        divisible_by_5_count=div5,
        divisible_by_10_count=div10,
        reporting_precision_step_minutes=precision.step_minutes,
        reporting_precision_authority=precision.authority,
        pattern_status=round_status,
        notes=round_notes,
    )
    signals.append(
        StatisticalAnomalySignal(
            signal_identity="s06:rounding:div5",
            signal_type=SignalType.ROUNDING_PATTERN,
            status=round_status,
            source_observation_identities=tuple(sid for sid, _, _ in present),
            canonical_operation_code=None,
            canonical_operation_name=None,
            metric="divisible_by_5_count",
            observed_value=float(div5),
            reference_value=float(len(vals)) if vals else None,
            sample_size=len(vals),
            statistical_method=StatisticalMethod.DIVISIBILITY_COUNT,
            threshold_reference=None,
            threshold_authority=precision.authority,
            comparability_status="NOT_APPLICABLE",
            evidence_authority=EvidenceAuthority.DESCRIPTIVE_ONLY,
            deviation_value=None,
            review_priority=ReviewPriority.INFORMATION,
            limitations=round_notes,
            provenance=(f"rules={S06_RULES_VERSION}",),
            rules_version=S06_RULES_VERSION,
            professional_conclusion=(
                f"{div5}/{len(vals)} labor values divisible by 5. "
                "ROUNDING ≠ FABRICATION. VIOLATION_NOT_PROVEN."
            ),
            clarification_question=(
                None
                if precision.step_minutes is not None
                else "Укажите официальную точность отчётности (шаг минут)."
            ),
        )
    )
    signals.append(
        StatisticalAnomalySignal(
            signal_identity="s06:rounding:div10",
            signal_type=SignalType.ROUNDING_PATTERN,
            status=round_status,
            source_observation_identities=tuple(sid for sid, _, _ in present),
            canonical_operation_code=None,
            canonical_operation_name=None,
            metric="divisible_by_10_count",
            observed_value=float(div10),
            reference_value=float(len(vals)) if vals else None,
            sample_size=len(vals),
            statistical_method=StatisticalMethod.DIVISIBILITY_COUNT,
            threshold_reference=None,
            threshold_authority=precision.authority,
            comparability_status="NOT_APPLICABLE",
            evidence_authority=EvidenceAuthority.DESCRIPTIVE_ONLY,
            deviation_value=None,
            review_priority=ReviewPriority.INFORMATION,
            limitations=round_notes,
            provenance=(f"rules={S06_RULES_VERSION}",),
            rules_version=S06_RULES_VERSION,
            professional_conclusion=(
                f"{div10}/{len(vals)} labor values divisible by 10. "
                "ROUNDING ≠ FABRICATION. VIOLATION_NOT_PROVEN."
            ),
            clarification_question=None,
        )
    )

    rep_status = StatisticalSignalStatus.DESCRIPTIVE_OBSERVATION
    repeated_summary = RepeatedValueSummary(
        distinct_values=len(freq),
        repeated_values=repeated,
        status=rep_status,
        notes=(
            "REPEATED_VALUE_NE_DUPLICATE_EXECUTION",
            "VIOLATION_NOT_PROVEN",
        ),
    )
    if repeated:
        signals.append(
            StatisticalAnomalySignal(
                signal_identity="s06:repeated_values",
                signal_type=SignalType.REPEATED_VALUE,
                status=rep_status,
                source_observation_identities=tuple(sid for sid, _, _ in present),
                canonical_operation_code=None,
                canonical_operation_name=None,
                metric="repeated_labor_values",
                observed_value=float(len(repeated)),
                reference_value=None,
                sample_size=len(vals),
                statistical_method=StatisticalMethod.VALUE_FREQUENCY,
                threshold_reference=None,
                threshold_authority=None,
                comparability_status="NOT_APPLICABLE",
                evidence_authority=EvidenceAuthority.DESCRIPTIVE_ONLY,
                deviation_value=None,
                review_priority=ReviewPriority.INFORMATION,
                limitations=(
                    "REPEATED_VALUE_NE_DUPLICATE_EXECUTION",
                    "VIOLATION_NOT_PROVEN",
                ),
                provenance=(f"rules={S06_RULES_VERSION}",),
                rules_version=S06_RULES_VERSION,
                professional_conclusion=(
                    f"Repeated labor values observed: {repeated}. "
                    "Not proven duplicate execution."
                ),
                clarification_question=None,
            )
        )

    # --- Unit labor deviation vs typed statistical references ---
    ref_coverage_parts: list[str] = []
    seen_ref_ids: set[str] = set()
    seen_source_records: set[str] = set()
    deduped_refs: list[StatisticalReferenceObservation] = []
    for ref in statistical_references:
        if ref.observation_identity in seen_ref_ids:
            unresolved.append(
                f"duplicate_reference_identity_excluded:{ref.observation_identity}"
            )
            continue
        # Two versions of one source record ≠ two independent observations
        if ref.source_record_identity:
            if ref.source_record_identity in seen_source_records:
                unresolved.append(
                    f"duplicate_source_record_version_excluded:"
                    f"{ref.source_record_identity}:{ref.source_record_version or 'unversioned'}:"
                    f"{ref.observation_identity}"
                )
                continue
            seen_source_records.add(ref.source_record_identity)
        seen_ref_ids.add(ref.observation_identity)
        # Future dates / chronological cutoff
        if (
            not allow_future_reference_dates
            and ref.observation_date
            and as_of
            and ref.observation_date > as_of
        ):
            unresolved.append(
                f"future_reference_excluded:{ref.observation_identity}"
            )
            continue
        deduped_refs.append(ref)

    for line in s10.classifications:
        f11 = s11_by_id.get(line.source_operation_identity)
        if not f11 or f11.unit_labor_man_minutes_per_physical is None:
            continue
        if f11.calculation_status != LaborCalculationStatus.COMPUTABLE_CLAIMED_OBSERVATION:
            continue
        observed_ul = float(f11.unit_labor_man_minutes_per_physical)
        claim = next(
            (
                c
                for c in audit_input.operations
                if c.operation_name == line.original_operation_text
            ),
            None,
        )
        material = claim.material_hint if claim else None

        comparable_vals: list[float] = []
        comparable_ids: list[str] = []
        incomparable_reasons: list[str] = []
        for ref in deduped_refs:
            # Never silently include current observation in own reference population
            if ref.observation_identity in (
                line.source_operation_identity,
                f"current:{line.source_operation_identity}",
            ):
                unresolved.append(
                    f"current_observation_excluded_from_own_reference:{ref.observation_identity}"
                )
                continue
            # Geometry on claim is not available as typed class; only compare
            # when caller places geometry_hint on StatisticalReferenceObservation
            # against an explicit current geometry via material/tech context.
            current_geometry = None
            ok, reason = _refs_comparable(
                ref,
                op_code=line.operation_code_candidate,
                physical_unit=f11.original_measurement_unit,
                material=material,
                geometry=current_geometry,
                technology=None,
                result_state=f11.claimed_result_state,
                labor_semantics=f11.labor_semantics,
                project_code=audit_input.project_code,
                authorized_project_scopes=authorized_project_scopes,
            )
            # If reference declares geometry but current has none → incomplete
            if ok and ref.geometry_hint and current_geometry is None:
                ok = False
                reason = "geometry_context_incomplete"
            if ok:
                rich_ok, rich_reason = _rich_comparability_ready(
                    material=material,
                    result_state=f11.claimed_result_state,
                    labor_semantics=f11.labor_semantics,
                    ref=ref,
                )
                if not rich_ok:
                    ok = False
                    reason = rich_reason

            if not ok:
                incomparable_reasons.append(reason)
                continue
            comparable_vals.append(float(ref.unit_labor_man_minutes_per_physical))
            comparable_ids.append(ref.observation_identity)

        n = len(comparable_vals)
        ref_coverage_parts.append(
            f"{line.source_operation_identity}:comparable_n={n}"
        )
        if n == 0:
            status = (
                StatisticalSignalStatus.REFERENCE_NOT_AVAILABLE
                if not statistical_references
                else StatisticalSignalStatus.INSUFFICIENT_COMPARABLE_HISTORY
                if not incomparable_reasons
                else StatisticalSignalStatus.REFERENCE_NOT_COMPARABLE
                if incomparable_reasons and n == 0
                else StatisticalSignalStatus.INSUFFICIENT_COMPARABLE_HISTORY
            )
            if statistical_references and incomparable_reasons:
                status = StatisticalSignalStatus.REFERENCE_NOT_COMPARABLE
            elif statistical_references:
                status = StatisticalSignalStatus.INSUFFICIENT_COMPARABLE_HISTORY
            else:
                status = StatisticalSignalStatus.REFERENCE_NOT_AVAILABLE
            signals.append(
                StatisticalAnomalySignal(
                    signal_identity=f"s06:unit_labor:{line.source_operation_identity}",
                    signal_type=SignalType.UNIT_LABOR_DEVIATION,
                    status=status,
                    source_observation_identities=(line.source_operation_identity,),
                    canonical_operation_code=line.operation_code_candidate,
                    canonical_operation_name=line.canonical_operation_candidate,
                    metric="unit_labor_man_minutes",
                    observed_value=observed_ul,
                    reference_value=None,
                    sample_size=0,
                    statistical_method=StatisticalMethod.MEDIAN_MAD_MODIFIED_Z,
                    threshold_reference=None,
                    threshold_authority=cfg.authority,
                    comparability_status=status.value,
                    evidence_authority=EvidenceAuthority.DESCRIPTIVE_ONLY,
                    deviation_value=None,
                    review_priority=ReviewPriority.CLARIFICATION_REQUIRED,
                    limitations=(
                        "INSUFFICIENT_COMPARABLE_HISTORY_OR_NOT_COMPARABLE",
                        "SMALL_SAMPLE_NE_RELIABLE_PRODUCTION_STANDARD",
                        "MISSING_HISTORY_NE_NORMAL_PERFORMANCE",
                        "VIOLATION_NOT_PROVEN",
                        *tuple(sorted(set(incomparable_reasons)))[:5],
                    ),
                    provenance=(f"rules={S06_RULES_VERSION}",),
                    rules_version=S06_RULES_VERSION,
                    professional_conclusion=(
                        "No usable comparable historical unit-labor sample for this "
                        "operation under stated comparability constraints. "
                        "Uncertainty preserved. VIOLATION_NOT_PROVEN."
                    ),
                    clarification_question=(
                        "Предоставьте сопоставимые исторические наблюдения "
                        "с достаточным контекстом."
                    ),
                )
            )
            continue

        if not mad_threshold_usable:
            continue

        if n < cfg.min_sample_size:
            signals.append(
                StatisticalAnomalySignal(
                    signal_identity=f"s06:unit_labor:{line.source_operation_identity}",
                    signal_type=SignalType.UNIT_LABOR_DEVIATION,
                    status=StatisticalSignalStatus.INSUFFICIENT_COMPARABLE_HISTORY,
                    source_observation_identities=(
                        line.source_operation_identity,
                        *comparable_ids,
                    ),
                    canonical_operation_code=line.operation_code_candidate,
                    canonical_operation_name=line.canonical_operation_candidate,
                    metric="unit_labor_man_minutes",
                    observed_value=observed_ul,
                    reference_value=_median(comparable_vals),
                    sample_size=n,
                    statistical_method=StatisticalMethod.MEDIAN_MAD_MODIFIED_Z,
                    threshold_reference=(
                        f"{cfg.config_identity}:min_sample_size={cfg.min_sample_size}"
                    ),
                    threshold_authority=cfg.authority,
                    comparability_status=ComparabilityStatus.BUCKET_COMPARABLE_WITH_LIMITATIONS.value,
                    evidence_authority=EvidenceAuthority.DESCRIPTIVE_ONLY,
                    deviation_value=None,
                    review_priority=ReviewPriority.CLARIFICATION_REQUIRED,
                    limitations=(
                        "INSUFFICIENT_COMPARABLE_HISTORY",
                        "SMALL_SAMPLE_NE_RELIABLE_PRODUCTION_STANDARD",
                        "SMALL_SAMPLE_NE_APPROVED_BENCHMARK",
                        "CLAIMED_HISTORICAL_SAMPLE_NE_VERIFIED_HISTORICAL_SAMPLE",
                        f"demonstration_threshold_authority={cfg.authority}",
                        "VIOLATION_NOT_PROVEN",
                        "min_sample_checked_after_dedupe_and_comparability_filters",
                    ),
                    provenance=(
                        f"threshold_config={cfg.config_identity}/{cfg.version}",
                        f"rules={S06_RULES_VERSION}",
                    ),
                    rules_version=S06_RULES_VERSION,
                    professional_conclusion=(
                        f"Comparable n={n} < min_sample_size={cfg.min_sample_size} "
                        "(after dedupe/filters). "
                        "Not an approved benchmark. VIOLATION_NOT_PROVEN."
                    ),
                    clarification_question=None,
                )
            )
            continue

        med = _median(comparable_vals)
        mad = _mad(comparable_vals, med)
        assert med is not None and mad is not None
        if mad == 0.0:
            delta = observed_ul - med
            abs_delta = abs(delta)
            matches_median = abs_delta < 1e-12
            zd_thr = cfg.zero_dispersion_absolute_deviation_threshold
            if (
                not matches_median
                and zd_thr is not None
                and abs_delta > zd_thr
            ):
                zd_status = StatisticalSignalStatus.THRESHOLD_EXCEEDANCE
                zd_priority = ReviewPriority.REVIEW_CANDIDATE
                zd_evidence = EvidenceAuthority.CONFIGURED_THRESHOLD
                zd_thr_ref = (
                    f"{cfg.config_identity}:MAD=0;"
                    f"|observed-median|>{zd_thr}"
                )
                zd_conclusion = (
                    f"MAD=0; observed={observed_ul} differs from historical "
                    f"median={med} by {delta}. Explicit zero-dispersion absolute "
                    f"threshold {zd_thr} exceeded (authority={cfg.authority}). "
                    "Not automatic normal performance. "
                    "Not proven violation. Z-score not computed (no ÷0)."
                )
            elif matches_median:
                zd_status = StatisticalSignalStatus.ZERO_DISPERSION
                zd_priority = ReviewPriority.INFORMATION
                zd_evidence = EvidenceAuthority.COMPARABLE_HISTORICAL_SAMPLE
                zd_thr_ref = f"{cfg.config_identity}:MAD=0;observed=median"
                zd_conclusion = (
                    f"MAD=0; observed={observed_ul} equals historical median={med}. "
                    "Modified Z not computed. Match to zero-dispersion history is "
                    "not proof of verified normal performance. VIOLATION_NOT_PROVEN."
                )
            else:
                zd_status = StatisticalSignalStatus.ZERO_DISPERSION
                zd_priority = ReviewPriority.REVIEW_CANDIDATE
                zd_evidence = EvidenceAuthority.COMPARABLE_HISTORICAL_SAMPLE
                zd_thr_ref = f"{cfg.config_identity}:MAD=0;observed≠median"
                zd_conclusion = (
                    f"MAD=0; observed={observed_ul} differs from historical "
                    f"median={med} by {delta}. Modified Z not computed "
                    "(no division by zero; no infinite score). "
                    "Difference from median is NOT automatically normal just "
                    "because MAD cannot score it. "
                    "No alternate threshold invented. VIOLATION_NOT_PROVEN."
                )
            signals.append(
                StatisticalAnomalySignal(
                    signal_identity=f"s06:unit_labor:{line.source_operation_identity}",
                    signal_type=SignalType.UNIT_LABOR_DEVIATION,
                    status=zd_status,
                    source_observation_identities=(
                        line.source_operation_identity,
                        *comparable_ids,
                    ),
                    canonical_operation_code=line.operation_code_candidate,
                    canonical_operation_name=line.canonical_operation_candidate,
                    metric="unit_labor_man_minutes",
                    observed_value=observed_ul,
                    reference_value=med,
                    sample_size=n,
                    statistical_method=StatisticalMethod.MEDIAN_MAD_MODIFIED_Z,
                    threshold_reference=zd_thr_ref,
                    threshold_authority=cfg.authority,
                    comparability_status=ComparabilityStatus.BUCKET_COMPARABLE_WITH_LIMITATIONS.value,
                    evidence_authority=zd_evidence,
                    deviation_value=delta,
                    review_priority=zd_priority,
                    limitations=(
                        "ZERO_DISPERSION; no_division_by_zero; no_infinite_score",
                        "observed_ne_median_not_auto_normal_when_MAD_zero"
                        if not matches_median
                        else "observed_equals_median_not_verified_normal",
                        "CLAIMED_HISTORICAL_SAMPLE_NE_VERIFIED_HISTORICAL_SAMPLE",
                        "low_unit_labor_ne_automatic_good_result",
                        "VIOLATION_NOT_PROVEN",
                        "STATISTICAL_ANOMALY_NE_PROVEN_VIOLATION",
                    ),
                    provenance=(
                        f"threshold_config={cfg.config_identity}/{cfg.version}",
                        f"rules={S06_RULES_VERSION}",
                    ),
                    rules_version=S06_RULES_VERSION,
                    professional_conclusion=zd_conclusion,
                    clarification_question=(
                        None
                        if matches_median
                        else (
                            "Уточните нулевую дисперсию истории и отличие "
                            "наблюдения от медианы; не интерпретировать как норму."
                        )
                    ),
                )
            )
            continue

        z = _modified_z(observed_ul, med, mad)
        assert z is not None
        abs_z = abs(z)
        thr = cfg.mad_modified_z_threshold
        if abs_z > thr:
            status = StatisticalSignalStatus.STATISTICAL_ANOMALY_CANDIDATE
            priority = ReviewPriority.REVIEW_CANDIDATE
            # High cost can raise review priority without raising evidence authority
            cost_f = next(
                (
                    c
                    for c in s04.findings
                    if c.source_operation_identity == line.source_operation_identity
                ),
                None,
            )
            if (
                cost_f
                and cost_f.computed_direct_labor_cost_exact is not None
                and float(cost_f.computed_direct_labor_cost_exact) >= 5000
            ):
                # Urgency ≠ evidence authority (authority stays COMPARABLE_HISTORICAL_SAMPLE)
                priority = ReviewPriority.HIGH_REVIEW_PRIORITY
            signals.append(
                StatisticalAnomalySignal(
                    signal_identity=f"s06:unit_labor:{line.source_operation_identity}",
                    signal_type=SignalType.UNIT_LABOR_DEVIATION,
                    status=status,
                    source_observation_identities=(
                        line.source_operation_identity,
                        *comparable_ids,
                    ),
                    canonical_operation_code=line.operation_code_candidate,
                    canonical_operation_name=line.canonical_operation_candidate,
                    metric="unit_labor_modified_z_mad",
                    observed_value=observed_ul,
                    reference_value=med,
                    sample_size=n,
                    statistical_method=StatisticalMethod.MEDIAN_MAD_MODIFIED_Z,
                    threshold_reference=(
                        f"{cfg.config_identity}:|modified_z|>{thr}"
                    ),
                    threshold_authority=cfg.authority,
                    comparability_status=ComparabilityStatus.BUCKET_COMPARABLE_WITH_LIMITATIONS.value,
                    evidence_authority=EvidenceAuthority.COMPARABLE_HISTORICAL_SAMPLE,
                    deviation_value=z,
                    review_priority=priority,
                    limitations=(
                        "STATISTICAL_ANOMALY_NE_PROVEN_VIOLATION",
                        "BENCHMARK_DEVIATION_NE_PROVEN_LOSS",
                        "HIGH_REVIEW_PRIORITY_NE_HIGH_EVIDENCE_AUTHORITY",
                        "FULL_COMPARABILITY_NOT_PROVEN",
                        "CLAIMED_HISTORICAL_SAMPLE_NE_VERIFIED_HISTORICAL_SAMPLE",
                        "COMPARABLE_HISTORICAL_SAMPLE_NE_VERIFIED_EXECUTION_ANOMALY",
                        "low_or_high_unit_labor_ne_automatic_good_or_bad_result",
                        f"demonstration_threshold_authority={cfg.authority}",
                        "VIOLATION_NOT_PROVEN",
                        "original_observations_not_removed",
                    ),
                    provenance=(
                        f"threshold_config={cfg.config_identity}/{cfg.version}",
                        f"MAD={mad}",
                        f"rules={S06_RULES_VERSION}",
                    ),
                    rules_version=S06_RULES_VERSION,
                    professional_conclusion=(
                        f"Modified Z={z:.4f} vs median={med} MAD={mad} "
                        f"(threshold {thr}, authority={cfg.authority}). "
                        "Statistical anomaly candidate only. "
                        "Not proven violation, loss, or fraud."
                    ),
                    clarification_question=(
                        "Требуется профессиональное исследование (S07), "
                        "не автоматическая санкция."
                    ),
                )
            )
        else:
            signals.append(
                StatisticalAnomalySignal(
                    signal_identity=f"s06:unit_labor:{line.source_operation_identity}",
                    signal_type=SignalType.UNIT_LABOR_DEVIATION,
                    status=StatisticalSignalStatus.DESCRIPTIVE_OBSERVATION,
                    source_observation_identities=(
                        line.source_operation_identity,
                        *comparable_ids,
                    ),
                    canonical_operation_code=line.operation_code_candidate,
                    canonical_operation_name=line.canonical_operation_candidate,
                    metric="unit_labor_modified_z_mad",
                    observed_value=observed_ul,
                    reference_value=med,
                    sample_size=n,
                    statistical_method=StatisticalMethod.MEDIAN_MAD_MODIFIED_Z,
                    threshold_reference=(
                        f"{cfg.config_identity}:|modified_z|>{thr}"
                    ),
                    threshold_authority=cfg.authority,
                    comparability_status=ComparabilityStatus.BUCKET_COMPARABLE_WITH_LIMITATIONS.value,
                    evidence_authority=EvidenceAuthority.COMPARABLE_HISTORICAL_SAMPLE,
                    deviation_value=z,
                    review_priority=ReviewPriority.INFORMATION,
                    limitations=(
                        "NO_DETECTED_ANOMALY_NE_VERIFIED_SHIFT",
                        "VIOLATION_NOT_PROVEN",
                    ),
                    provenance=(f"rules={S06_RULES_VERSION}",),
                    rules_version=S06_RULES_VERSION,
                    professional_conclusion=(
                        f"Modified Z={z:.4f} within threshold {thr}. "
                        "Descriptive only. Absence of anomaly ≠ verified shift."
                    ),
                    clarification_question=None,
                )
            )

    # --- Cost deviation boundaries (reuse S04; do not promote scenario→actual) ---
    if s04.cost_conservation.total_calculated_direct_labor_cost_exact is not None:
        signals.append(
            StatisticalAnomalySignal(
                signal_identity="s06:cost:scenario_boundary",
                signal_type=SignalType.COST_DEVIATION,
                status=StatisticalSignalStatus.DESCRIPTIVE_OBSERVATION,
                source_observation_identities=tuple(
                    f.source_operation_identity for f in s04.findings
                ),
                canonical_operation_code=None,
                canonical_operation_name=None,
                metric="scenario_direct_labor_cost",
                observed_value=float(
                    s04.cost_conservation.total_calculated_direct_labor_cost_exact
                ),
                reference_value=None,
                sample_size=len(s04.findings),
                statistical_method=StatisticalMethod.DESCRIPTIVE_SHARE,
                threshold_reference=None,
                threshold_authority=None,
                comparability_status="SCENARIO_COST_ONLY",
                evidence_authority=EvidenceAuthority.DESCRIPTIVE_ONLY,
                deviation_value=None,
                review_priority=ReviewPriority.INFORMATION,
                limitations=(
                    "SCENARIO_COST_NE_ACTUAL_COST",
                    "no_revenue_margin_payroll",
                    "VIOLATION_NOT_PROVEN",
                ),
                provenance=(
                    f"s04_actual_status={s04.actual_cost_verification_status}",
                    f"rules={S06_RULES_VERSION}",
                ),
                rules_version=S06_RULES_VERSION,
                professional_conclusion=(
                    "S04 scenario/estimated direct labor cost retained as scenario. "
                    "Not promoted to actual incurred cost. VIOLATION_NOT_PROVEN."
                ),
                clarification_question=None,
            )
        )

    econ_types = {
        f.cost_rate_economic_type
        for f in s04.findings
        if f.cost_rate_economic_type is not None
    }
    if len(econ_types) > 1:
        signals.append(
            StatisticalAnomalySignal(
                signal_identity="s06:cost:incompatible_rate_types",
                signal_type=SignalType.COST_DEVIATION,
                status=StatisticalSignalStatus.REFERENCE_NOT_COMPARABLE,
                source_observation_identities=(),
                canonical_operation_code=None,
                canonical_operation_name=None,
                metric="cost_rate_economic_types",
                observed_value=float(len(econ_types)),
                reference_value=1.0,
                sample_size=len(s04.findings),
                statistical_method=StatisticalMethod.NOT_APPLICABLE,
                threshold_reference=None,
                threshold_authority=None,
                comparability_status="RATE_TYPES_NOT_COMPARABLE",
                evidence_authority=EvidenceAuthority.DESCRIPTIVE_ONLY,
                deviation_value=None,
                review_priority=ReviewPriority.CLARIFICATION_REQUIRED,
                limitations=(
                    "incompatible_rate_types_not_aggregated",
                    "currency_and_component_boundaries_required",
                    "VIOLATION_NOT_PROVEN",
                ),
                provenance=(f"rules={S06_RULES_VERSION}",),
                rules_version=S06_RULES_VERSION,
                professional_conclusion=(
                    "Mixed economic rate types present; monetary figures not treated "
                    "as one comparable population. VIOLATION_NOT_PROVEN."
                ),
                clarification_question=None,
            )
        )

    # Currency / component boundary note from S04 conservation
    if s04.cost_conservation.currency:
        unresolved.append(
            f"cost_currency={s04.cost_conservation.currency}; "
            "cross_currency_comparison_not_performed"
        )

    # --- Temporal signals inherited from S05 (not promoted to physical proof) ---
    inherited = 0
    inherited_keys: set[str] = set()
    for f in s05.findings:
        inherited_statuses = [
            s
            for s in f.finding_statuses
            if s
            in (
                TemporalFindingStatus.SCENARIO_CAPACITY_LIMIT_EXCEEDED,
                TemporalFindingStatus.CAPACITY_CONFLICT,
                TemporalFindingStatus.EXCLUSIVE_WORKER_ALLOCATION_CONFLICT,
                TemporalFindingStatus.CLAIMED_INTERVAL_OVERLAP,
            )
        ]
        if not inherited_statuses:
            continue
        key = (
            f"{f.source_operation_identity}:"
            + ",".join(sorted(s.value for s in inherited_statuses))
        )
        if key in inherited_keys:
            continue
        inherited_keys.add(key)
        inherited += 1
        signals.append(
            StatisticalAnomalySignal(
                signal_identity=f"s06:temporal_inherited:{f.source_operation_identity}",
                signal_type=SignalType.TEMPORAL_SIGNAL,
                status=StatisticalSignalStatus.INHERITED_PROFESSIONAL_FINDING,
                source_observation_identities=(f.source_operation_identity,),
                canonical_operation_code=f.canonical_operation_code,
                canonical_operation_name=f.canonical_operation_name,
                metric="s05_finding_statuses",
                observed_value=float(len(inherited_statuses)),
                reference_value=None,
                sample_size=None,
                statistical_method=StatisticalMethod.INHERITED,
                threshold_reference=None,
                threshold_authority=None,
                comparability_status="INHERITED",
                evidence_authority=EvidenceAuthority.INHERITED_FROM_PRIOR_SKILL,
                deviation_value=None,
                review_priority=ReviewPriority.REVIEW_CANDIDATE,
                limitations=(
                    "S05_scenario_or_claimed_conflict_NE_physical_proof",
                    "CHRONOLOGY_NOT_PROVEN",
                    "INHERITED_FINDING_NOT_DUPLICATED_AS_INDEPENDENT_PROOF",
                    "VIOLATION_NOT_PROVEN",
                    *(s.value for s in inherited_statuses),
                ),
                provenance=(
                    f"s05_chronology={s05.chronology_status}",
                    f"rules={S06_RULES_VERSION}",
                ),
                rules_version=S06_RULES_VERSION,
                professional_conclusion=(
                    "Inherited S05 temporal finding for review. "
                    "Scenario/claimed temporal conflict not promoted to proven "
                    "physical conflict. VIOLATION_NOT_PROVEN."
                ),
                clarification_question=None,
            )
        )

    # Always stamp chronology insufficiency as informational context
    if s05.chronology_status == "CHRONOLOGY_NOT_PROVEN":
        unresolved.append("S05_CHRONOLOGY_NOT_PROVEN")

    remaining_no_unit = float(
        s11.labor_conservation.labor_without_computable_unit_indicators_man_minutes
    )

    comparable_reference_coverage = (
        "; ".join(ref_coverage_parts)
        if ref_coverage_parts
        else "NO_UNIT_LABOR_REFERENCE_EVALUATIONS"
    )
    if not statistical_references:
        comparable_reference_coverage = (
            "PRODUCTION_HISTORY_ADAPTER_NOT_IMPLEMENTED; "
            "NO_TYPED_REFERENCES_SUPPLIED"
        )
        unresolved.append("MISSING_HISTORY_NE_NORMAL_PERFORMANCE")

    conclusion = (
        f"S06 descriptive concentration/rounding complete for claimed labor="
        f"{s01_total}. Statistical anomaly candidates require comparable history. "
        f"Inherited temporal findings={inherited}. "
        "NO DETECTED ANOMALY ≠ VERIFIED SHIFT. VIOLATION_NOT_PROVEN. "
        "Managerial acceptance NOT_IN_SCOPE."
    )

    summary = ShiftStatisticalSummary(
        concentration=conc,
        rounding=rounding,
        repeated_values=repeated_summary,
        comparable_reference_coverage=comparable_reference_coverage,
        unresolved_context=tuple(dict.fromkeys(unresolved)),
        inherited_finding_count=inherited,
        total_original_labor_man_minutes=s01_total,
        professional_conclusion=conclusion,
        notes=(
            "DESCRIPTIVE_OBSERVATION_NE_STATISTICAL_ANOMALY",
            "STATISTICAL_ANOMALY_NE_PROVEN_VIOLATION",
            "COST_CONCENTRATION_NE_INEFFICIENCY",
            "ROUNDING_NE_FABRICATION",
            "REPEATED_VALUE_NE_DUPLICATE_EXECUTION",
            "BENCHMARK_DEVIATION_NE_PROVEN_LOSS",
            "SMALL_SAMPLE_NE_RELIABLE_PRODUCTION_STANDARD",
            "SAME_OPERATION_CODE_NE_AUTOMATIC_COMPARABILITY",
            "SCENARIO_COST_NE_ACTUAL_COST",
            "HIGH_REVIEW_PRIORITY_NE_HIGH_EVIDENCE_AUTHORITY",
            "NO_DETECTED_ANOMALY_NE_VERIFIED_SHIFT",
            "MISSING_HISTORY_NE_NORMAL_PERFORMANCE",
            "S06_does_not_assign_root_cause_S07",
            f"remaining_labor_without_computable_unit_indicators_mm={remaining_no_unit}",
            f"threshold_config={cfg.config_identity}/{cfg.version}/{cfg.authority}",
        ),
    )

    observations = (
        "S06 = deterministic statistical anomaly signal skill.",
        "DESCRIPTIVE OBSERVATION != STATISTICAL ANOMALY.",
        "STATISTICAL ANOMALY != PROVEN VIOLATION.",
        "COST CONCENTRATION != INEFFICIENCY.",
        "ROUNDING != FABRICATION.",
        "REPEATED VALUE != DUPLICATE EXECUTION.",
        "BENCHMARK DEVIATION != PROVEN LOSS.",
        "SMALL SAMPLE != RELIABLE PRODUCTION STANDARD.",
        "SAME OPERATION CODE != AUTOMATIC COMPARABILITY.",
        "SCENARIO COST != ACTUAL COST.",
        "HIGH REVIEW PRIORITY != HIGH EVIDENCE AUTHORITY.",
        "NO DETECTED ANOMALY != VERIFIED SHIFT.",
        "MISSING HISTORY != NORMAL PERFORMANCE.",
        "Method: median + MAD modified Z when comparable n>=min_sample_size.",
        f"Rules: {S06_RULES_VERSION}.",
        "S06_ENGINE_IMPLEMENTED; VIOLATION_NOT_PROVEN.",
    )

    lines = [
        "PSAA S06 — Statistical Anomaly Detection",
        f"Проект: {audit_input.project_code} date={audit_input.work_date} crew={audit_input.crew_id}",
        f"Claimed labor={s01_total}; signals={len(signals)}; inherited={inherited}",
        f"Concentration top1={conc.top1_share_pct} top3={conc.top3_share_pct} top4={conc.top4_share_pct}",
        f"Rounding div5={rounding.divisible_by_5_count}/{rounding.observation_count} "
        f"div10={rounding.divisible_by_10_count}/{rounding.observation_count}",
        "Managerial acceptance: NOT_IN_SCOPE | Fraud/Payroll/Disciplinary: NOT_PERFORMED",
    ]
    for s in signals:
        lines.append(
            f"- [{s.status.value}] {s.signal_type.value} | {s.metric}="
            f"{s.observed_value} | auth={s.evidence_authority.value} | "
            f"prio={s.review_priority.value}"
        )

    return ShiftStatisticalAnomalyArtifact(
        schema_version=S06_ARTIFACT_SCHEMA_VERSION,
        rules_version=S06_RULES_VERSION,
        audit_id=audit_id or s01.audit_id or str(uuid.uuid4()),
        agent_code=AGENT_CODE,
        agent_version=AGENT_VERSION,
        run_id=run_id,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        project_code=audit_input.project_code,
        work_date=audit_input.work_date,
        crew_id=audit_input.crew_id,
        evaluation_domain="statistical_anomaly_signals_claimed_data",
        signals=tuple(signals),
        shift_summary=summary,
        observations=observations,
        managerial_acceptance_status="NOT_IN_SCOPE",
        payroll_decision_status="NOT_PERFORMED",
        disciplinary_decision_status="NOT_PERFORMED",
        fraud_classification_status="NOT_PERFORMED",
        human_readable_summary="\n".join(lines),
        s06_engine_status="S06_ENGINE_IMPLEMENTED",
        durable_history_schema_status="UNCHANGED_IN_THIS_INCREMENT",
        production_history_adapter_status="NOT_IMPLEMENTED_USE_TYPED_REFERENCES",
        cost_deviation_readiness="COST_DEVIATION_BOUNDARIES_ONLY",
        production_cost_deviation_status="PRODUCTION_COST_DEVIATION_NOT_PROVEN",
    )
