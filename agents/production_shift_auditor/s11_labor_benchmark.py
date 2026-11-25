"""S11 — Labor Benchmark & Observation Eligibility (deterministic).

Computes claimed unit labor / productivity and eligibility for analysis.
Does NOT approve norms. Does NOT mutate Labor Norm Library.
Does NOT invent benchmarks. Does NOT allocate composite labor.
"""

from __future__ import annotations

import statistics
import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence

from agents.production_shift_auditor.contracts import (
    LaborSemanticsStatus,
    LaborUnit,
    OperationLaborClaim,
    ShiftAuditArtifact,
    ShiftAuditInput,
)
from agents.production_shift_auditor.s02_contracts import (
    SourceAuthority,
    ShiftTechnologicalIntegrityArtifact,
)
from agents.production_shift_auditor.s03_contracts import (
    MeasurabilityClass,
    PhysicalCheckResult,
    PhysicalCheckType,
    ShiftPhysicalIntegrityArtifact,
)
from agents.production_shift_auditor.s10_contracts import (
    ClassificationStatus,
    OperationClassificationLine,
    ShiftOperationClassificationArtifact,
)
from agents.production_shift_auditor.s10_operation_classification import (
    normalize_operation_text,
)
from agents.production_shift_auditor.s11_contracts import (
    S11_ARTIFACT_SCHEMA_VERSION,
    S11_RULES_VERSION,
    BenchmarkAuthorityStatus,
    BenchmarkComparisonStatus,
    BenchmarkReference,
    ComparabilityStatus,
    HistoricalAggregationSummary,
    HistoricalLaborObservation,
    LaborCalculationStatus,
    LaborConservationSummary,
    LaborObservationFinding,
    ObservationEligibility,
    ShiftLaborBenchmarkArtifact,
)

AGENT_CODE = "PRODUCTION_SHIFT_AUDITOR"
AGENT_VERSION = "0.1"


def _to_man_minutes(quantity: float, unit: LaborUnit) -> Optional[float]:
    if unit == LaborUnit.MAN_MINUTE:
        return float(quantity)
    if unit == LaborUnit.MAN_HOUR:
        return float(quantity) * 60.0
    return None  # HOUR_FIELD_UNPROVEN — no silent conversion


def _norm_unit(unit: Optional[str]) -> Optional[str]:
    if not unit:
        return None
    raw = normalize_operation_text(unit).replace(" ", "")
    mapping = {
        "шт": "шт",
        "шт.": "шт",
        "м": "м",
        "м2": "м2",
        "м²": "м2",
        "m2": "м2",
        "м3": "м3",
        "м³": "м3",
    }
    return mapping.get(raw, raw)


def _norm_opt(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return normalize_operation_text(value) or None


def _claim_for_line(
    audit_input: ShiftAuditInput, line: OperationClassificationLine
) -> Optional[OperationLaborClaim]:
    for claim in audit_input.operations:
        if claim.source_record_ids and claim.source_record_ids[0] == line.source_operation_identity:
            return claim
        if claim.operation_name == line.original_operation_text:
            return claim
    return None


def _s03_qty_finding(
    s03: ShiftPhysicalIntegrityArtifact, source_identity: str, original: str
):
    for f in s03.findings:
        if f.source_operation_identity != source_identity and f.original_operation_text != original:
            continue
        if f.check_type in {
            PhysicalCheckType.QUANTITY_INTEGRITY,
            PhysicalCheckType.UNIT_INTEGRITY,
            PhysicalCheckType.COMPOSITE_LIMITATION,
            PhysicalCheckType.CONTEXT_SUFFICIENCY,
        }:
            return f
    return None


def _s03_state(
    s03: ShiftPhysicalIntegrityArtifact, source_identity: str, original: str
) -> Optional[str]:
    for f in s03.findings:
        if f.check_type != PhysicalCheckType.RESULT_STATE:
            continue
        if f.source_operation_identity == source_identity or f.original_operation_text == original:
            return f.claimed_result_state.value
    return None


def _s02_demo_only(
    s02: ShiftTechnologicalIntegrityArtifact, source_identity: str, original: str
) -> bool:
    related = [
        f
        for f in s02.findings
        if f.source_operation_identity == source_identity
        or f.original_operation_text == original
    ]
    if not related:
        return True
    return all(
        f.demonstration_rule
        or f.source_authority == SourceAuthority.DEMONSTRATION_RULE
        or f.applicable_rule_id is None
        for f in related
    )


def _median(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return float(statistics.median(values))


def _finding(
    *,
    check_identity: str,
    source_operation_identity: str,
    original_operation_text: str,
    canonical_operation_code: Optional[str],
    canonical_operation_name: Optional[str],
    labor_q: Optional[float],
    labor_u_s: Optional[str],
    semantics: Optional[str],
    eligible_mm: Optional[float],
    eligible_mh: Optional[float],
    qty: Optional[float],
    unit: Optional[str],
    state: Optional[str],
    unit_mm: Optional[float],
    unit_mh: Optional[float],
    productivity: Optional[float],
    calc: LaborCalculationStatus,
    eligibility: ObservationEligibility,
    eligibility_reasons: tuple[str, ...],
    comparability_status: ComparabilityStatus,
    comparability_limitations: tuple[str, ...],
    evidence_status: str,
    bench_status: BenchmarkComparisonStatus,
    bench_id: Optional[str],
    bench_ul: Optional[float],
    bench_dev: Optional[float],
    bench_authority: Optional[str],
    labor_wo_qty: Optional[str],
    provenance: tuple[str, ...],
    conclusion: str,
    clarification: Optional[str],
) -> LaborObservationFinding:
    return LaborObservationFinding(
        check_identity=check_identity,
        source_operation_identity=source_operation_identity,
        original_operation_text=original_operation_text,
        canonical_operation_code=canonical_operation_code,
        canonical_operation_name=canonical_operation_name,
        original_claimed_labor_quantity=labor_q,
        original_labor_unit=labor_u_s,
        labor_semantics=semantics,
        eligible_labor_man_minutes=eligible_mm,
        eligible_labor_man_hours=eligible_mh,
        original_claimed_physical_quantity=qty,
        original_measurement_unit=unit,
        claimed_result_state=state,
        unit_labor_man_minutes_per_physical=unit_mm,
        unit_labor_man_hours_per_physical=unit_mh,
        productivity_per_man_hour=productivity,
        calculation_status=calc,
        observation_eligibility=eligibility,
        eligibility_reasons=eligibility_reasons,
        comparability_status=comparability_status,
        comparability_limitations=comparability_limitations,
        evidence_status=evidence_status,
        benchmark_comparison_status=bench_status,
        benchmark_reference_id=bench_id,
        benchmark_unit_labor_man_hours=bench_ul,
        benchmark_deviation_pct=bench_dev,
        benchmark_authority_status=bench_authority,
        labor_without_quantity_category=labor_wo_qty,
        provenance=provenance,
        rules_version=S11_RULES_VERSION,
        professional_conclusion=conclusion,
        clarification_request=clarification,
        preserved_claimed_labor_quantity=labor_q,
        preserved_physical_quantity=qty,
    )


def _evaluate_observation(
    *,
    line: OperationClassificationLine,
    claim: Optional[OperationLaborClaim],
    audit_input: ShiftAuditInput,
    s01: ShiftAuditArtifact,
    s02: ShiftTechnologicalIntegrityArtifact,
    s03: ShiftPhysicalIntegrityArtifact,
    benchmarks: Sequence[BenchmarkReference],
) -> LaborObservationFinding:
    del s01  # joint chain identity only; S11 does not mutate S01
    labor_q = claim.claimed_labor_quantity if claim else line.claimed_labor_quantity
    labor_u = claim.labor_unit if claim else None
    labor_u_s = labor_u.value if labor_u else line.claimed_labor_unit
    qty = claim.physical_quantity if claim else line.physical_quantity
    unit = claim.physical_unit if claim else line.physical_unit
    unit_n = _norm_unit(unit)
    semantics = audit_input.labor_semantics_status.value
    state = _s03_state(s03, line.source_operation_identity, line.original_operation_text)
    s03_qty = _s03_qty_finding(s03, line.source_operation_identity, line.original_operation_text)
    demo_only = _s02_demo_only(s02, line.source_operation_identity, line.original_operation_text)

    provenance = (
        f"source_kind={audit_input.source_kind.value}",
        f"project={audit_input.project_code}",
        f"s10_status={line.classification_status.value}",
        f"labor_semantics={semantics}",
        f"s02_demo_only={demo_only}",
        f"rules={S11_RULES_VERSION}",
    )
    na = BenchmarkComparisonStatus.BENCHMARK_COMPARISON_NOT_APPLICABLE
    not_elig = ObservationEligibility.NOT_ELIGIBLE_FOR_BENCHMARK
    not_comp = ComparabilityStatus.NOT_APPLICABLE

    if line.classification_status == ClassificationStatus.COMPOSITE_OPERATION:
        elig_mm = (
            _to_man_minutes(labor_q, labor_u)
            if labor_u and labor_q is not None
            else None
        )
        return _finding(
            check_identity=f"s11:{line.source_operation_identity}:composite",
            source_operation_identity=line.source_operation_identity,
            original_operation_text=line.original_operation_text,
            canonical_operation_code=None,
            canonical_operation_name=None,
            labor_q=labor_q,
            labor_u_s=labor_u_s,
            semantics=semantics,
            eligible_mm=elig_mm,
            eligible_mh=(elig_mm / 60.0) if elig_mm is not None else None,
            qty=qty,
            unit=unit,
            state=state,
            unit_mm=None,
            unit_mh=None,
            productivity=None,
            calc=LaborCalculationStatus.COMPOSITE_NOT_ALLOCATABLE,
            eligibility=not_elig,
            eligibility_reasons=(
                "s10_COMPOSITE_OPERATION",
                "NO_AUTOMATIC_LABOR_OR_QUANTITY_ALLOCATION",
            ),
            comparability_status=ComparabilityStatus.NOT_COMPARABLE,
            comparability_limitations=("composite_requires_confirmed_decomposition",),
            evidence_status="CLAIMED_COMPOSITE_UNALLOCATED",
            bench_status=na,
            bench_id=None,
            bench_ul=None,
            bench_dev=None,
            bench_authority=None,
            labor_wo_qty=None,
            provenance=provenance,
            conclusion=(
                "COMPOSITE_OPERATION: исходные труд и объём сохранены; удельная "
                "норма отдельной операции не формируется без подтверждённой декомпозиции. "
                "Труд сохраняется для экономического анализа без unit indicator."
            ),
            clarification="Разделите составную запись с трудом и объёмом по компонентам.",
        )

    if line.classification_status in {
        ClassificationStatus.UNKNOWN_OPERATION,
        ClassificationStatus.AMBIGUOUS,
        ClassificationStatus.INSUFFICIENT_CONTEXT,
    }:
        return _finding(
            check_identity=f"s11:{line.source_operation_identity}:s10",
            source_operation_identity=line.source_operation_identity,
            original_operation_text=line.original_operation_text,
            canonical_operation_code=line.operation_code_candidate,
            canonical_operation_name=line.canonical_operation_candidate,
            labor_q=labor_q,
            labor_u_s=labor_u_s,
            semantics=semantics,
            eligible_mm=None,
            eligible_mh=None,
            qty=qty,
            unit=unit,
            state=state,
            unit_mm=None,
            unit_mh=None,
            productivity=None,
            calc=LaborCalculationStatus.INSUFFICIENT_DATA,
            eligibility=not_elig,
            eligibility_reasons=(f"s10_{line.classification_status.value}",),
            comparability_status=ComparabilityStatus.NOT_COMPARABLE,
            comparability_limitations=("canonical_operation_not_resolved",),
            evidence_status="CLASSIFICATION_INSUFFICIENT",
            bench_status=na,
            bench_id=None,
            bench_ul=None,
            bench_dev=None,
            bench_authority=None,
            labor_wo_qty=None,
            provenance=provenance,
            conclusion="Операция не классифицирована достаточно для unit labor / benchmark.",
            clarification="Уточните каноническую операцию.",
        )

    if labor_q is None:
        return _finding(
            check_identity=f"s11:{line.source_operation_identity}:no_labor",
            source_operation_identity=line.source_operation_identity,
            original_operation_text=line.original_operation_text,
            canonical_operation_code=line.operation_code_candidate,
            canonical_operation_name=line.canonical_operation_candidate,
            labor_q=None,
            labor_u_s=labor_u_s,
            semantics=semantics,
            eligible_mm=None,
            eligible_mh=None,
            qty=qty,
            unit=unit,
            state=state,
            unit_mm=None,
            unit_mh=None,
            productivity=None,
            calc=LaborCalculationStatus.INSUFFICIENT_DATA,
            eligibility=not_elig,
            eligibility_reasons=("claimed_labor_absent",),
            comparability_status=not_comp,
            comparability_limitations=("labor_missing",),
            evidence_status="LABOR_ABSENT",
            bench_status=na,
            bench_id=None,
            bench_ul=None,
            bench_dev=None,
            bench_authority=None,
            labor_wo_qty=None,
            provenance=provenance,
            conclusion="Трудозатраты отсутствуют — unit labor не вычислим.",
            clarification="Укажите трудозатраты с доказанной семантикой.",
        )

    if labor_q < 0 or (qty is not None and qty < 0):
        return _finding(
            check_identity=f"s11:{line.source_operation_identity}:invalid",
            source_operation_identity=line.source_operation_identity,
            original_operation_text=line.original_operation_text,
            canonical_operation_code=line.operation_code_candidate,
            canonical_operation_name=line.canonical_operation_candidate,
            labor_q=labor_q,
            labor_u_s=labor_u_s,
            semantics=semantics,
            eligible_mm=None,
            eligible_mh=None,
            qty=qty,
            unit=unit,
            state=state,
            unit_mm=None,
            unit_mh=None,
            productivity=None,
            calc=LaborCalculationStatus.INVALID_INPUT,
            eligibility=not_elig,
            eligibility_reasons=("negative_labor_or_quantity",),
            comparability_status=ComparabilityStatus.NOT_COMPARABLE,
            comparability_limitations=("invalid_numeric_input",),
            evidence_status="INVALID_INPUT",
            bench_status=na,
            bench_id=None,
            bench_ul=None,
            bench_dev=None,
            bench_authority=None,
            labor_wo_qty=None,
            provenance=provenance,
            conclusion=(
                "Отрицательные значения труда/объёма недопустимы для ordinary "
                "execution observation (correction workflow не реализован)."
            ),
            clarification="Исправьте входные значения.",
        )

    if labor_u is None or labor_u == LaborUnit.HOUR_FIELD_UNPROVEN:
        return _finding(
            check_identity=f"s11:{line.source_operation_identity}:unproven_labor",
            source_operation_identity=line.source_operation_identity,
            original_operation_text=line.original_operation_text,
            canonical_operation_code=line.operation_code_candidate,
            canonical_operation_name=line.canonical_operation_candidate,
            labor_q=labor_q,
            labor_u_s=labor_u_s,
            semantics=semantics,
            eligible_mm=None,
            eligible_mh=None,
            qty=qty,
            unit=unit,
            state=state,
            unit_mm=None,
            unit_mh=None,
            productivity=None,
            calc=LaborCalculationStatus.UNIT_LABOR_NOT_COMPUTABLE,
            eligibility=not_elig,
            eligibility_reasons=(
                "labor_semantics_unproven_or_hour_field_unproven",
                "NO_SILENT_CONVERSION_TO_MAN_HOURS",
            ),
            comparability_status=ComparabilityStatus.COMPARABILITY_CONTEXT_INCOMPLETE,
            comparability_limitations=("unproven_labor_semantics",),
            evidence_status="LABOR_SEMANTICS_UNPROVEN",
            bench_status=na,
            bench_id=None,
            bench_ul=None,
            bench_dev=None,
            bench_authority=None,
            labor_wo_qty=(
                "labor_with_unproven_semantics" if qty is None or qty == 0 else None
            ),
            provenance=provenance,
            conclusion=(
                "Семантика трудозатрат недоказана (например HOUR_FIELD_UNPROVEN) — "
                "silent conversion запрещён; unit labor не вычисляется. "
                "Claimed labor quantity preserved for economics where present."
            ),
            clarification="Подтвердите семантику man-minutes / man-hours.",
        )

    labor_mm = _to_man_minutes(labor_q, labor_u)
    assert labor_mm is not None
    labor_mh = labor_mm / 60.0

    if qty is None or qty == 0:
        category = (
            "zero_claimed_quantity" if qty == 0 else "absent_claimed_quantity"
        )
        if (
            s03_qty
            and s03_qty.measurability
            == MeasurabilityClass.QUANTITY_NOT_REQUIRED_BY_CURRENT_RULE
        ):
            category = "preparation_or_auxiliary_or_process_labor_without_required_quantity"
        return _finding(
            check_identity=f"s11:{line.source_operation_identity}:no_qty",
            source_operation_identity=line.source_operation_identity,
            original_operation_text=line.original_operation_text,
            canonical_operation_code=line.operation_code_candidate,
            canonical_operation_name=line.canonical_operation_candidate,
            labor_q=labor_q,
            labor_u_s=labor_u_s,
            semantics=semantics,
            eligible_mm=labor_mm,
            eligible_mh=labor_mh,
            qty=qty,
            unit=unit,
            state=state,
            unit_mm=None,
            unit_mh=None,
            productivity=None,
            calc=LaborCalculationStatus.LABOR_WITHOUT_POSITIVE_QUANTITY,
            eligibility=not_elig,
            eligibility_reasons=(
                category,
                "LABOR_WITHOUT_QUANTITY_NE_AUTOMATIC_LOSS",
                "NOT_AUTO_INCLUDED_IN_OTHER_OPERATION_NORM",
                "PRESERVED_FOR_FUTURE_ECONOMICS",
            ),
            comparability_status=ComparabilityStatus.NOT_COMPARABLE,
            comparability_limitations=("no_positive_physical_quantity",),
            evidence_status="CLAIMED_LABOR_WITHOUT_POSITIVE_QUANTITY",
            bench_status=na,
            bench_id=None,
            bench_ul=None,
            bench_dev=None,
            bench_authority=None,
            labor_wo_qty=category,
            provenance=provenance,
            conclusion=(
                "Труд без положительного физического объёма сохранён отдельно для "
                "экономики / анализа потерь. Не объявляется автоматической потерей; "
                "подготовительный/вспомогательный труд может быть технологически "
                "необходим. Не включается автоматически в прямую норму другой операции. "
                "Причина отсутствия объёма не придумывается. "
                "PAID LABOR ≠ PRODUCTIVE LABOR; LABOR WITHOUT QUANTITY ≠ AUTOMATIC LOSS."
            ),
            clarification=None,
        )

    if labor_mm == 0:
        return _finding(
            check_identity=f"s11:{line.source_operation_identity}:zero_labor",
            source_operation_identity=line.source_operation_identity,
            original_operation_text=line.original_operation_text,
            canonical_operation_code=line.operation_code_candidate,
            canonical_operation_name=line.canonical_operation_candidate,
            labor_q=labor_q,
            labor_u_s=labor_u_s,
            semantics=semantics,
            eligible_mm=0.0,
            eligible_mh=0.0,
            qty=qty,
            unit=unit,
            state=state,
            unit_mm=None,
            unit_mh=None,
            productivity=None,
            calc=LaborCalculationStatus.UNIT_LABOR_NOT_COMPUTABLE,
            eligibility=not_elig,
            eligibility_reasons=("zero_labor_with_positive_quantity", "NO_DIVISION_BY_ZERO"),
            comparability_status=ComparabilityStatus.NOT_COMPARABLE,
            comparability_limitations=("zero_eligible_labor",),
            evidence_status="ZERO_LABOR",
            bench_status=na,
            bench_id=None,
            bench_ul=None,
            bench_dev=None,
            bench_authority=None,
            labor_wo_qty=None,
            provenance=provenance,
            conclusion=(
                "Нулевой труд при положительном объёме — unit labor / productivity "
                "не вычислимы (деление на ноль запрещено)."
            ),
            clarification="Уточните трудозатраты.",
        )

    if not unit_n:
        return _finding(
            check_identity=f"s11:{line.source_operation_identity}:no_unit",
            source_operation_identity=line.source_operation_identity,
            original_operation_text=line.original_operation_text,
            canonical_operation_code=line.operation_code_candidate,
            canonical_operation_name=line.canonical_operation_candidate,
            labor_q=labor_q,
            labor_u_s=labor_u_s,
            semantics=semantics,
            eligible_mm=labor_mm,
            eligible_mh=labor_mh,
            qty=qty,
            unit=unit,
            state=state,
            unit_mm=None,
            unit_mh=None,
            productivity=None,
            calc=LaborCalculationStatus.INSUFFICIENT_DATA,
            eligibility=not_elig,
            eligibility_reasons=("measurement_unit_absent_or_unknown",),
            comparability_status=ComparabilityStatus.COMPARABILITY_CONTEXT_INCOMPLETE,
            comparability_limitations=("unit_missing",),
            evidence_status="UNIT_MISSING",
            bench_status=na,
            bench_id=None,
            bench_ul=None,
            bench_dev=None,
            bench_authority=None,
            labor_wo_qty=None,
            provenance=provenance,
            conclusion="Единица измерения отсутствует/неизвестна — unit labor не сопоставим.",
            clarification="Укажите единицу физического результата.",
        )

    unit_mm = labor_mm / qty
    unit_mh = labor_mh / qty
    productivity = qty / labor_mh

    eligibility_reasons = [
        "arithmetically_computable_claimed_observation",
        "CLAIMED_UNIT_LABOR_NE_VERIFIED_UNIT_LABOR",
        "VERIFIED_OBSERVATION_NE_APPROVED_LABOR_NORM",
    ]
    limitations = [
        "claimed_inputs_only",
        "SAME_OPERATION_CODE_NE_AUTOMATIC_COMPARABILITY",
        "geometry_context_absent_unless_caller_supplied",
        "physical_characteristics_absent_unless_caller_supplied",
        "technology_context_limited_to_s10_catalog_identity",
        "execution_conditions_absent_unless_caller_supplied",
        "FULL_COMPARABILITY_REQUIRES_ENGINEERING_CONTEXT",
    ]
    if demo_only:
        eligibility_reasons.append("s02_s03_demonstration_rules_do_not_verify_observation")
        limitations.append("demonstration_findings_ne_verified_observation")
    if audit_input.labor_semantics_status != LaborSemanticsStatus.EXPLICIT_CLAIM:
        limitations.append(f"labor_semantics={semantics}")
    else:
        limitations.append(f"labor_semantics={semantics}_explicit_but_claimed_only")
    if s03_qty and s03_qty.check_result not in {
        PhysicalCheckResult.CONSISTENT_WITH_CHECKED_RULE,
        PhysicalCheckResult.NOT_APPLICABLE,
    }:
        limitations.append(f"s03_qty_status={s03_qty.check_result.value}")
    if not (claim and claim.physical_object_hint):
        limitations.append("physical_object_identity_limited")
    if claim and claim.material_hint:
        limitations.append(f"material_context={claim.material_hint[:40]}")
    else:
        limitations.append("material_context_absent")
    if state:
        limitations.append(f"claimed_result_state={state}")
    else:
        limitations.append("result_state_limited")

    # Arithmetic computable + historical candidate ≠ full comparability proven
    comparability_status = ComparabilityStatus.COMPARABILITY_CONTEXT_INCOMPLETE
    if claim and claim.material_hint and state and claim.physical_object_hint:
        # Still not full — diameter/geometry/technology/conditions typically missing
        comparability_status = ComparabilityStatus.FULL_COMPARABILITY_NOT_PROVEN
        limitations.append(
            "code_unit_material_state_present_but_geometry_technology_conditions_incomplete"
        )
    else:
        limitations.append(
            "example_DN50_vs_DN500_fittings_not_auto_comparable_by_code_and_unit_alone"
        )

    if (
        audit_input.labor_semantics_status == LaborSemanticsStatus.EXPLICIT_CLAIM
        and line.classification_status
        in {ClassificationStatus.EXACT_MATCH, ClassificationStatus.NORMALIZED_MATCH}
        and qty > 0
        and labor_mm > 0
        and unit_n
    ):
        eligibility = ObservationEligibility.HISTORICAL_ANALYSIS_CANDIDATE
        eligibility_reasons.append(
            "arithmetically_usable_for_historical_analysis_candidate_queue"
        )
        eligibility_reasons.append("HISTORICAL_AVERAGE_NE_PRODUCTION_STANDARD")
        eligibility_reasons.append("COMPUTABLE_CLAIMED_OBSERVATION_NOT_APPROVED_NORM")
        eligibility_reasons.append(
            "HISTORICAL_CANDIDATE_NE_FULL_COMPARABILITY_PROVEN"
        )
        if demo_only:
            eligibility_reasons.append(
                "demonstration_s02_s03_do_not_create_verified_observation"
            )
    else:
        eligibility = ObservationEligibility.COMPUTABLE_BUT_CLAIMED_ONLY
        if audit_input.labor_semantics_status != LaborSemanticsStatus.EXPLICIT_CLAIM:
            eligibility = ObservationEligibility.NOT_ELIGIBLE_FOR_BENCHMARK
            eligibility_reasons.append("labor_semantics_not_explicit_claim")
        else:
            eligibility_reasons.append("computable_claimed_but_limited_for_benchmark_queue")

    bench_status = BenchmarkComparisonStatus.BENCHMARK_NOT_AVAILABLE
    bench_id = None
    bench_ul = None
    bench_dev = None
    bench_authority: Optional[str] = None
    code = line.operation_code_candidate
    matches = [
        b
        for b in benchmarks
        if code
        and b.operation_code == code
        and _norm_unit(b.physical_unit) == unit_n
    ]
    if not benchmarks:
        bench_status = BenchmarkComparisonStatus.BENCHMARK_NOT_AVAILABLE
    elif not matches:
        same_code = [b for b in benchmarks if code and b.operation_code == code]
        if same_code:
            bench_status = BenchmarkComparisonStatus.BENCHMARK_INCOMPATIBLE
            limitations.append("benchmark_unit_or_context_incompatible")
        else:
            bench_status = BenchmarkComparisonStatus.BENCHMARK_NOT_AVAILABLE
    else:
        compatible = []
        for b in matches:
            if b.project_scope and b.project_scope != audit_input.project_code:
                continue
            if b.material_hint and claim and claim.material_hint:
                bm = _norm_opt(b.material_hint) or ""
                cm = _norm_opt(claim.material_hint) or ""
                if bm not in cm and cm not in bm:
                    continue
            if b.result_state and state and b.result_state != state:
                continue
            if b.labor_semantics and b.labor_semantics != semantics:
                continue
            # If benchmark requires engineering context, observation must attest it
            # via claim.comment/notes (no universal parameter model invented here).
            blob = " ".join(
                [
                    (claim.comment or "") if claim else "",
                    " ".join(claim.notes) if claim and claim.notes else "",
                ]
            )
            blob_n = _norm_opt(blob) or ""
            context_ok = True
            for attr in (
                "geometry_hint",
                "physical_characteristic_hint",
                "technology_hint",
                "execution_conditions_hint",
            ):
                bval = getattr(b, attr)
                if bval and (_norm_opt(bval) or "") not in blob_n:
                    context_ok = False
                    break
            if context_ok:
                compatible.append(b)
        if not compatible:
            bench_status = BenchmarkComparisonStatus.BENCHMARK_INCOMPATIBLE
            limitations.append("benchmark_context_or_scope_mismatch")
        else:
            b = compatible[0]
            # Injected reference is NEVER auto-approved production norm by S11
            if b.authority_status == BenchmarkAuthorityStatus.APPROVED_PRODUCTION_NORM:
                # Still claimed-only comparison; S11 does not become approval authority
                limitations.append(
                    "caller_marked_approved_norm_but_S11_does_not_re_approve_or_mutate"
                )
            bench_status = BenchmarkComparisonStatus.BENCHMARK_COMPARED_CLAIMED_ONLY
            bench_id = f"{b.source_id}@{b.source_version}"
            bench_ul = b.unit_labor_man_hours_per_physical
            bench_authority = (
                f"{b.authority_status.value}|approval={b.approval_status}|"
                f"provenance={b.provenance_note}|scope={b.project_scope or 'unspecified'}"
            )
            if bench_ul and bench_ul != 0:
                bench_dev = ((unit_mh - bench_ul) / bench_ul) * 100.0
            eligibility_reasons.append("BENCHMARK_DEVIATION_NE_PROVEN_INEFFICIENCY")
            eligibility_reasons.append(
                "EXTERNAL_BENCHMARK_REFERENCE_NE_APPROVED_LABOR_NORM_BY_S11"
            )
            limitations.append("comparison_uses_claimed_observation_only")
            limitations.append(
                "production_labor_norm_read_adapter_NOT_IMPLEMENTED"
            )

    return _finding(
        check_identity=f"s11:{line.source_operation_identity}:unit_labor",
        source_operation_identity=line.source_operation_identity,
        original_operation_text=line.original_operation_text,
        canonical_operation_code=line.operation_code_candidate,
        canonical_operation_name=line.canonical_operation_candidate,
        labor_q=labor_q,
        labor_u_s=labor_u_s,
        semantics=semantics,
        eligible_mm=labor_mm,
        eligible_mh=labor_mh,
        qty=qty,
        unit=unit,
        state=state,
        unit_mm=unit_mm,
        unit_mh=unit_mh,
        productivity=productivity,
        calc=LaborCalculationStatus.COMPUTABLE_CLAIMED_OBSERVATION,
        eligibility=eligibility,
        eligibility_reasons=tuple(eligibility_reasons),
        comparability_status=comparability_status,
        comparability_limitations=tuple(limitations),
        evidence_status="CLAIMED_ONLY_NOT_VERIFIED_NOT_APPROVED_NORM",
        bench_status=bench_status,
        bench_id=bench_id,
        bench_ul=bench_ul,
        bench_dev=bench_dev,
        bench_authority=bench_authority,
        labor_wo_qty=None,
        provenance=provenance,
        conclusion=(
            f"Заявленная удельная трудоёмкость {unit_mm:.6g} чел·мин/{unit_n} "
            f"({unit_mh:.6g} чел·ч/{unit_n}); производительность "
            f"{productivity:.6g} {unit_n}/чел·ч. "
            "CLAIMED ≠ VERIFIED ≠ APPROVED NORM. "
            "Арифметическая вычислимость ≠ полная сопоставимость "
            "(геометрия/физ.характеристики/технология/условия могут отсутствовать). "
            f"Eligibility={eligibility.value}; comparability={comparability_status.value}; "
            f"benchmark={bench_status.value}."
        ),
        clarification=None,
    )


def _observation_dedupe_key(obs: HistoricalLaborObservation) -> str:
    if obs.observation_identity:
        return f"id:{obs.observation_identity}"
    # Same source record version → not independent physical observation
    if obs.source_record_version:
        return (
            f"ver:{obs.operation_code}|{obs.source_record_version}|"
            f"{obs.project_code or ''}|"
            f"{_norm_unit(obs.physical_unit)}"
        )
    # No identity: treat each supplied row as distinct caller observation
    return f"anon:{id(obs)}"


def aggregate_historical_observations(
    observations: Sequence[HistoricalLaborObservation],
    *,
    allowed_project_scope: Optional[str] = None,
) -> tuple[HistoricalAggregationSummary, ...]:
    """Quantity-weighted aggregation for caller-supplied comparable observations.

    Does not invent data. Does not drop inconvenient observations silently
    (they are counted as excluded/non-comparable). Does not auto-clean outliers.
    Does not approve norms. Does not auto-merge across projects.
    Dedupes identical observation_identity / source_record_version.
    Not a full cross-snapshot deduplication platform.
    """
    seen_keys: set[str] = set()
    deduped: list[HistoricalLaborObservation] = []
    excluded = 0
    unresolved: list[str] = []

    for obs in observations:
        key = _observation_dedupe_key(obs)
        if key in seen_keys and not key.startswith("anon:"):
            excluded += 1
            unresolved.append(
                f"duplicate_observation_identity_or_source_version_skipped:{key}"
            )
            continue
        seen_keys.add(key)
        if allowed_project_scope:
            if obs.project_code and obs.project_code != allowed_project_scope:
                excluded += 1
                unresolved.append(
                    f"cross_project_excluded_without_scope:{obs.project_code}"
                )
                continue
            if not obs.project_code:
                unresolved.append(
                    "project_code_absent_included_only_when_scope_filter_inactive_or_caller_attests"
                )
        elif obs.project_code:
            # No scope filter: still do not merge different projects into one bucket
            pass
        deduped.append(obs)

    # Bucket key includes engineering context dimensions (no universal param model)
    BucketKey = tuple[
        str,
        str,
        Optional[str],
        Optional[str],
        Optional[str],
        Optional[str],
        Optional[str],
        Optional[str],
        Optional[str],
        Optional[str],
    ]
    groups: dict[BucketKey, list[HistoricalLaborObservation]] = {}
    for obs in deduped:
        if allowed_project_scope is None and obs.project_code:
            # Separate buckets per project when codes differ
            proj = obs.project_code
        else:
            proj = allowed_project_scope or obs.project_code
        key: BucketKey = (
            obs.operation_code,
            _norm_unit(obs.physical_unit) or obs.physical_unit,
            _norm_opt(obs.material_hint),
            obs.claimed_result_state,
            _norm_opt(obs.geometry_hint),
            _norm_opt(obs.physical_characteristic_hint),
            _norm_opt(obs.technology_hint),
            _norm_opt(obs.labor_semantics),
            _norm_opt(obs.execution_conditions_hint),
            proj,
        )
        groups.setdefault(key, []).append(obs)

    summaries: list[HistoricalAggregationSummary] = []
    for key, bucket in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1] or "")):
        (
            code,
            unit,
            mat,
            st,
            geom,
            phys,
            tech,
            lab_sem,
            exec_c,
            proj,
        ) = key
        individuals: list[float] = []
        identities: list[str] = []
        total_q = 0.0
        total_l = 0.0
        local_excluded = 0
        for r in bucket:
            if r.physical_quantity <= 0 or r.eligible_labor_man_minutes <= 0:
                local_excluded += 1
                continue
            ul = r.eligible_labor_man_minutes / r.physical_quantity
            individuals.append(ul)
            total_q += r.physical_quantity
            total_l += r.eligible_labor_man_minutes
            identities.append(
                r.observation_identity
                or r.source_record_version
                or f"anon_row_{len(identities)}"
            )

        weighted = (total_l / total_q) if total_q > 0 else None
        context_present = all(
            x is not None for x in (mat, st, geom, phys, tech, lab_sem, exec_c)
        )
        if context_present and individuals:
            cstatus = ComparabilityStatus.BUCKET_COMPARABLE_WITH_LIMITATIONS
        elif individuals and (mat or st or geom or phys):
            cstatus = ComparabilityStatus.FULL_COMPARABILITY_NOT_PROVEN
        else:
            cstatus = ComparabilityStatus.COMPARABILITY_CONTEXT_INCOMPLETE

        limitations = [
            "caller_supplied_observations_only",
            "NO_AUTOMATIC_OUTLIER_REMOVAL",
            "HISTORICAL_AVERAGE_NE_PRODUCTION_STANDARD",
            "VERIFIED_OBSERVATION_NE_APPROVED_LABOR_NORM",
            "NO_CROSS_SNAPSHOT_DEDUPLICATION_PLATFORM",
            "SAME_OPERATION_CODE_NE_AUTOMATIC_COMPARABILITY",
            f"sample_size={len(individuals)}",
            f"project_bucket={proj or 'unspecified'}",
        ]
        if len(individuals) < 5:
            limitations.append("small_sample_not_an_approved_norm")
        if not geom:
            limitations.append("geometry_unspecified_DN50_vs_DN500_not_distinguished")
        if not phys:
            limitations.append("physical_characteristics_unspecified")
        if not tech:
            limitations.append("technology_unspecified")
        if not exec_c:
            limitations.append("execution_conditions_unspecified")
        if not lab_sem:
            limitations.append("labor_semantics_unspecified_in_bucket")
        if mat:
            limitations.append(f"material_bucket={mat[:40]}")
        else:
            limitations.append("material_unspecified_in_bucket")
        if st:
            limitations.append(f"result_state_bucket={st}")
        else:
            limitations.append("result_state_unspecified_in_bucket")

        summaries.append(
            HistoricalAggregationSummary(
                operation_code=code,
                physical_unit=unit or "",
                observation_count=len(individuals),
                total_quantity=total_q,
                total_eligible_labor_man_minutes=total_l,
                individual_unit_labor_man_minutes=tuple(individuals),
                quantity_weighted_unit_labor_man_minutes=weighted,
                quantity_weighted_unit_labor_man_hours=(
                    (weighted / 60.0) if weighted is not None else None
                ),
                minimum_unit_labor_man_minutes=min(individuals) if individuals else None,
                maximum_unit_labor_man_minutes=max(individuals) if individuals else None,
                median_unit_labor_man_minutes=_median(individuals),
                included_observation_identities=tuple(identities),
                excluded_or_non_comparable_count=excluded + local_excluded,
                unresolved_eligibility_notes=tuple(unresolved),
                comparability_status=cstatus,
                sample_limitations=tuple(limitations),
                approved_norm_status="NOT_AN_APPROVED_NORM",
                benchmark_authority_note="AGGREGATE_IS_NOT_BENCHMARK_AUTHORITY",
            )
        )
    return tuple(summaries)


def build_labor_conservation(
    findings: Sequence[LaborObservationFinding],
    *,
    s01_claimed_total_man_minutes: Optional[float],
) -> LaborConservationSummary:
    """Mutually exclusive partition of claimed labor for economics continuity."""
    computable = 0.0
    without = 0.0
    for f in findings:
        # Prefer preserved claimed labor in man-minutes when convertible
        mm = f.eligible_labor_man_minutes
        if mm is None and f.preserved_claimed_labor_quantity is not None:
            # Only count when unit was man-minute/hour already reflected in eligible;
            # if ineligible conversion, use original when labor_unit is known man-minute
            if f.original_labor_unit == LaborUnit.MAN_MINUTE.value:
                mm = float(f.preserved_claimed_labor_quantity)
            elif f.original_labor_unit == LaborUnit.MAN_HOUR.value:
                mm = float(f.preserved_claimed_labor_quantity) * 60.0
        if mm is None:
            continue
        if (
            f.calculation_status
            == LaborCalculationStatus.COMPUTABLE_CLAIMED_OBSERVATION
            and f.unit_labor_man_minutes_per_physical is not None
        ):
            computable += mm
        else:
            # Composite, labor-without-qty, insufficient, etc. — still preserved
            without += mm

    preserved = computable + without
    s01_total = (
        float(s01_claimed_total_man_minutes)
        if s01_claimed_total_man_minutes is not None
        else preserved
    )
    notes = (
        "Categories mutually exclusive: computable unit indicators vs remaining.",
        "Remaining includes absent qty, zero qty, composite, prep/aux, non-allocatable.",
        "825 (fixture remaining) ≠ automatic losses.",
        "LABOR_WITHOUT_QUANTITY_NE_AUTOMATIC_LOSS",
        "No double-counting between analytical categories.",
        "All preserved labor remains available for future economic analysis.",
    )
    return LaborConservationSummary(
        total_claimed_labor_man_minutes=s01_total,
        labor_with_computable_unit_indicators_man_minutes=computable,
        labor_without_computable_unit_indicators_man_minutes=without,
        preserved_total_man_minutes=preserved,
        conservation_holds=abs(preserved - s01_total) < 1e-6,
        categories_mutually_exclusive=True,
        labor_without_unit_ne_automatic_losses=True,
        notes=notes,
    )


def evaluate_s11(
    audit_input: ShiftAuditInput,
    s01: ShiftAuditArtifact,
    s10: ShiftOperationClassificationArtifact,
    s02: ShiftTechnologicalIntegrityArtifact,
    s03: ShiftPhysicalIntegrityArtifact,
    *,
    audit_id: Optional[str] = None,
    run_id: Optional[str] = None,
    benchmarks: Sequence[BenchmarkReference] = (),
    historical_observations: Sequence[HistoricalLaborObservation] = (),
    historical_project_scope: Optional[str] = None,
) -> ShiftLaborBenchmarkArtifact:
    findings: list[LaborObservationFinding] = []
    for line in s10.classifications:
        claim = _claim_for_line(audit_input, line)
        findings.append(
            _evaluate_observation(
                line=line,
                claim=claim,
                audit_input=audit_input,
                s01=s01,
                s02=s02,
                s03=s03,
                benchmarks=benchmarks,
            )
        )

    scope = historical_project_scope  # None → no cross-project merge via project bucket
    aggregations = aggregate_historical_observations(
        historical_observations, allowed_project_scope=scope
    )
    s01_total = None
    if s01.s01_metrics and s01.s01_metrics.claimed_total_man_minutes is not None:
        s01_total = float(s01.s01_metrics.claimed_total_man_minutes)
    conservation = build_labor_conservation(findings, s01_claimed_total_man_minutes=s01_total)

    observations = [
        "S11 = deterministic labor benchmark & observation eligibility skill.",
        "CLAIMED UNIT LABOR ≠ VERIFIED UNIT LABOR.",
        "VERIFIED OBSERVATION ≠ APPROVED LABOR NORM.",
        "HISTORICAL AVERAGE ≠ PRODUCTION STANDARD.",
        "LABOR WITHOUT QUANTITY ≠ AUTOMATIC LOSS.",
        "PAID LABOR ≠ PRODUCTIVE LABOR.",
        "BENCHMARK DEVIATION ≠ PROVEN INEFFICIENCY.",
        "SAME OPERATION CODE ≠ AUTOMATIC COMPARABILITY.",
        "EXTERNAL BENCHMARK REFERENCE ≠ APPROVED LABOR NORM BY S11.",
        "Arithmetic computability ≠ full engineering comparability.",
        "Geometry/physical characteristics/technology/conditions required for full comparability.",
        "S02/S03 demonstration findings do NOT create verified observations.",
        "No Labor Norm Library mutation. No invented benchmarks.",
        "No automatic composite labor allocation.",
        "Quantity-weighted unit labor = sum(labor)/sum(quantity); not mean of ratios as substitute.",
        "Observation identity / source_record_version deduped; no cross-snapshot platform.",
        "Cross-project observations not merged without scope.",
        "Production Labor Norm READ adapter: NOT_IMPLEMENTED_LIMITATION.",
        f"Rules: {S11_RULES_VERSION}.",
        "S11_ENGINE_IMPLEMENTED · CLAIMED_UNIT_LABOR_COMPUTABLE_WHEN_DATA_ALLOWS · "
        "VERIFIED_OBSERVATIONS_NOT_PROVEN · APPROVED_LABOR_NORMS_NOT_CREATED.",
    ]

    counts: dict[str, int] = {}
    for f in findings:
        counts[f.calculation_status.value] = counts.get(f.calculation_status.value, 0) + 1

    summary = [
        "PSAA S11 — Labor Benchmark & Observation Eligibility",
        f"Проект: {audit_input.project_code} date={audit_input.work_date} crew={audit_input.crew_id}",
        "Managerial acceptance: NOT_IN_SCOPE | Payroll: NOT_PERFORMED | "
        "Commercial recognition: NOT_PERFORMED | Norm mutation: NOT_PERFORMED",
        (
            f"Labor conservation: total={conservation.total_claimed_labor_man_minutes} "
            f"computable_UL={conservation.labor_with_computable_unit_indicators_man_minutes} "
            f"remaining={conservation.labor_without_computable_unit_indicators_man_minutes} "
            f"preserved={conservation.preserved_total_man_minutes} "
            f"holds={conservation.conservation_holds}"
        ),
        "Readiness: S11_ENGINE_IMPLEMENTED | VERIFIED_OBSERVATIONS_NOT_PROVEN | "
        "APPROVED_LABOR_NORMS_NOT_CREATED | LABOR_NORM_READ_ADAPTER_NOT_IMPLEMENTED",
        "Status counts: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
    ]
    for f in findings:
        summary.append(
            f"- «{f.original_operation_text}» | qty={f.original_claimed_physical_quantity} "
            f"{f.original_measurement_unit or ''} | labor={f.eligible_labor_man_minutes} "
            f"чел·мин | UL={f.unit_labor_man_minutes_per_physical} | "
            f"prod={f.productivity_per_man_hour} | {f.calculation_status.value} | "
            f"{f.observation_eligibility.value} | {f.comparability_status.value}"
        )
    for agg in aggregations:
        summary.append(
            f"- AGG {agg.operation_code}/{agg.physical_unit}: n={agg.observation_count} "
            f"weighted_UL_mm={agg.quantity_weighted_unit_labor_man_minutes} "
            f"excl={agg.excluded_or_non_comparable_count} "
            f"[{agg.approved_norm_status}] {agg.comparability_status.value}"
        )

    return ShiftLaborBenchmarkArtifact(
        schema_version=S11_ARTIFACT_SCHEMA_VERSION,
        rules_version=S11_RULES_VERSION,
        audit_id=audit_id or s01.audit_id or str(uuid.uuid4()),
        agent_code=AGENT_CODE,
        agent_version=AGENT_VERSION,
        run_id=run_id,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        project_code=audit_input.project_code,
        work_date=audit_input.work_date,
        crew_id=audit_input.crew_id,
        evaluation_domain="claimed_labor_observation_eligibility",
        findings=tuple(findings),
        aggregations=aggregations,
        labor_conservation=conservation,
        observations=tuple(observations),
        managerial_acceptance_status="NOT_IN_SCOPE",
        norm_mutation_status="NOT_PERFORMED",
        payroll_decision_status="NOT_PERFORMED",
        commercial_recognition_status="NOT_PERFORMED",
        human_readable_summary="\n".join(summary),
        s11_engine_status="S11_ENGINE_IMPLEMENTED",
        claimed_metrics_status="CLAIMED_UNIT_LABOR_COMPUTABLE_WHEN_DATA_ALLOWS",
        verified_observation_status="VERIFIED_OBSERVATIONS_NOT_PROVEN",
        approved_norm_status="APPROVED_LABOR_NORMS_NOT_CREATED",
        durable_history_schema_status="UNCHANGED_IN_THIS_INCREMENT",
        production_labor_norm_read_adapter_status="NOT_IMPLEMENTED_LIMITATION",
    )
