"""S04 — Execution Cost Analysis (deterministic; direct labor only).

labor_cost = labor_man_hours × applicable_labor_cost_rate
Does NOT invent rates. Does NOT compute payroll/revenue/margin/full cost.
Does NOT mutate rates or product state. Decimal monetary arithmetic.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Sequence

from agents.production_shift_auditor.contracts import (
    LaborUnit,
    OperationLaborClaim,
    ShiftAuditArtifact,
    ShiftAuditInput,
)
from agents.production_shift_auditor.s02_contracts import ShiftTechnologicalIntegrityArtifact
from agents.production_shift_auditor.s03_contracts import ShiftPhysicalIntegrityArtifact
from agents.production_shift_auditor.s04_contracts import (
    S04_ARTIFACT_SCHEMA_VERSION,
    S04_EXACT_QUANTUM,
    S04_MONEY_QUANTUM,
    S04_ROUNDING,
    S04_RULES_VERSION,
    ActualCostVerificationStatus,
    CostCalculationStatus,
    CostCompleteness,
    CostRateAuthority,
    CostRateEconomicType,
    CostRateUnit,
    CostConservationSummary,
    LaborCostRateReference,
    OperationCostFinding,
    ShiftExecutionCostArtifact,
)
from agents.production_shift_auditor.s10_contracts import (
    ShiftOperationClassificationArtifact,
)
from agents.production_shift_auditor.s11_contracts import (
    LaborCalculationStatus,
    ShiftLaborBenchmarkArtifact,
)

AGENT_CODE = "PRODUCTION_SHIFT_AUDITOR"
AGENT_VERSION = "0.1"

_EXACT_Q = Decimal(S04_EXACT_QUANTUM)
_MONEY_Q = Decimal(S04_MONEY_QUANTUM)


def _d(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _exact(value: Decimal) -> Decimal:
    return value.quantize(_EXACT_Q, rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_Q, rounding=ROUND_HALF_UP)


def _s(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return format(value, "f")


def _rate_to_per_man_hour(rate: LaborCostRateReference) -> Optional[Decimal]:
    try:
        raw = _d(rate.rate_value)
    except (InvalidOperation, ValueError):
        return None
    if raw < 0:
        return None
    # Zero allowed only with explicit confirmation (checked in selector)
    if rate.rate_unit == CostRateUnit.PER_MAN_HOUR:
        return raw
    if rate.rate_unit == CostRateUnit.PER_MAN_MINUTE:
        return raw * Decimal("60")
    return None


def _zero_rate_explicitly_confirmed(rate: LaborCostRateReference) -> bool:
    note = (rate.applicability_note or "").upper()
    return "ZERO_RATE_EXPLICITLY_CONFIRMED" in note


def _date_in_range(work_date: str, valid_from: Optional[str], valid_to: Optional[str]) -> bool:
    if valid_from and work_date < valid_from:
        return False
    if valid_to and work_date > valid_to:
        return False
    return True


def _normalize_category(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return " ".join(value.strip().lower().split()) or None


def _select_applicable_rate(
    rates: Sequence[LaborCostRateReference],
    *,
    project_code: str,
    work_date: str,
    labor_category: Optional[str] = None,
) -> tuple[Optional[LaborCostRateReference], Optional[CostCalculationStatus], tuple[str, ...]]:
    """Select one rate for one operation context.

    Supports shift-wide rates and optional per-category selection.
    Does NOT allocate labor across workers. Not a multi-rate allocation engine.
    """
    if not rates:
        return None, CostCalculationStatus.COST_RATE_NOT_AVAILABLE, ("no_cost_rate_supplied",)

    limitations: list[str] = []
    currencies = {r.currency for r in rates}
    if len(currencies) > 1:
        return (
            None,
            CostCalculationStatus.COST_RATE_NOT_APPLICABLE,
            ("multiple_currencies_without_fx_conversion_out_of_scope",),
        )

    op_cat = _normalize_category(labor_category)
    category_matched: list[LaborCostRateReference] = []
    shift_wide: list[LaborCostRateReference] = []

    for r in rates:
        if r.applicable_project_scope and r.applicable_project_scope != project_code:
            limitations.append(f"scope_mismatch:{r.rate_identity}")
            continue
        if not _date_in_range(work_date, r.valid_from, r.valid_to):
            limitations.append(f"validity_window_mismatch:{r.rate_identity}")
            continue
        if r.economic_type == CostRateEconomicType.CONTRACT_UNIT_PRICE:
            limitations.append(f"contract_unit_price_not_labor_cost:{r.rate_identity}")
            continue
        if r.economic_type == CostRateEconomicType.WAGE_RATE:
            limitations.append(f"wage_rate_ne_employer_labor_cost:{r.rate_identity}")
            continue
        if r.economic_type == CostRateEconomicType.UNKNOWN_RATE_TYPE:
            limitations.append(f"unknown_rate_type:{r.rate_identity}")
            continue
        if r.rate_unit == CostRateUnit.UNKNOWN:
            limitations.append(f"unknown_rate_unit:{r.rate_identity}")
            continue
        per_mh = _rate_to_per_man_hour(r)
        if per_mh is None:
            limitations.append(f"invalid_rate_value:{r.rate_identity}")
            continue
        if per_mh == 0 and not _zero_rate_explicitly_confirmed(r):
            limitations.append(
                f"zero_rate_without_explicit_confirmation:{r.rate_identity}"
            )
            continue
        if r.rate_authority == CostRateAuthority.UNKNOWN_RATE_AUTHORITY:
            limitations.append(f"unknown_authority:{r.rate_identity}")
            continue

        rate_cat = _normalize_category(r.applicable_labor_category)
        if rate_cat is None:
            shift_wide.append(r)
            continue
        if op_cat is None:
            # Categorized rate without operation category: usable as shift-wide
            # fallback with explicit limitation (not worker allocation).
            shift_wide.append(r)
            limitations.append(
                f"rate_category_present_operation_category_absent:{r.rate_identity}"
            )
            continue
        if op_cat != rate_cat:
            limitations.append(
                f"labor_category_mismatch:{r.rate_identity}:{rate_cat}!={op_cat}"
            )
            continue
        category_matched.append(r)

    # Prefer category-matched rates over shift-wide when op category is known
    pool = category_matched if category_matched else shift_wide
    if not pool:
        return (
            None,
            CostCalculationStatus.COST_RATE_NOT_APPLICABLE,
            tuple(limitations) or ("no_applicable_rate",),
        )

    priority = {
        CostRateAuthority.SCENARIO_RATE: 1,
        CostRateAuthority.BUDGET_RATE: 2,
        CostRateAuthority.APPROVED_COST_RATE: 3,
        CostRateAuthority.OBSERVED_COST_RATE: 4,
    }
    pool.sort(key=lambda x: (priority.get(x.rate_authority, 99), x.rate_identity))
    chosen = pool[0]
    lim = list(limitations)
    lim.append(f"selected_rate={chosen.rate_identity}@{chosen.version}")
    lim.append(f"authority={chosen.rate_authority.value}")
    lim.append(f"economic_type={chosen.economic_type.value}")
    lim.append("AUTHORITY_NE_ECONOMIC_TYPE")
    lim.append("SCENARIO_RATE_NE_APPROVED_COST_RATE")
    lim.append("APPROVED_RATE_NE_PROOF_OF_INCURRED_ACTUAL_COST")
    lim.append("CLAIMED_LABOR_COST_NE_INCURRED_ACTUAL_COST")
    lim.append("NO_CROSS_WORKER_LABOR_ALLOCATION")
    lim.append("production_cost_rate_read_adapter_NOT_IMPLEMENTED")
    if chosen.economic_type == CostRateEconomicType.FULLY_BURDENED_LABOR_COST_RATE:
        lim.append("FULLY_BURDENED_NE_PURE_DIRECT_LABOR_COST")
        lim.append("DO_NOT_DOUBLE_COUNT_COMPONENTS_ALREADY_IN_RATE")
    if not chosen.included_cost_components or any(
        "unknown" in c.lower() for c in chosen.included_cost_components
    ):
        lim.append("COST_COMPONENT_UNCERTAINTY")
    if chosen.economic_type == CostRateEconomicType.EMPLOYER_DIRECT_LABOR_COST_RATE:
        extras = [
            c
            for c in chosen.included_cost_components
            if c not in ("direct_labor",)
            and "overhead" in c.lower()
        ]
        if extras:
            lim.append("INCLUDED_COMPONENTS_EXCEED_PURE_DIRECT_LABOR")
    return chosen, None, tuple(lim)


def _s11_by_identity(
    s11: ShiftLaborBenchmarkArtifact,
) -> dict[str, object]:
    return {f.source_operation_identity: f for f in s11.findings}


def _claim_for_identity(
    audit_input: ShiftAuditInput, source_operation_identity: str, original: str
) -> Optional[OperationLaborClaim]:
    for claim in audit_input.operations:
        if claim.source_record_ids and claim.source_record_ids[0] == source_operation_identity:
            return claim
        if claim.operation_name == original:
            return claim
    return None


def _man_hours_from_s11(f11) -> Optional[Decimal]:
    if f11.eligible_labor_man_hours is not None:
        return _d(f11.eligible_labor_man_hours)
    if f11.eligible_labor_man_minutes is not None:
        return _d(f11.eligible_labor_man_minutes) / Decimal("60")
    return None


def _evaluate_operation(
    *,
    f11,
    line,
    rate: Optional[LaborCostRateReference],
    rate_status: Optional[CostCalculationStatus],
    rate_limitations: tuple[str, ...],
    rate_per_mh: Optional[Decimal],
) -> OperationCostFinding:
    labor_q = f11.original_claimed_labor_quantity
    labor_u = f11.original_labor_unit
    qty = f11.original_claimed_physical_quantity
    unit = f11.original_measurement_unit
    semantics = f11.labor_semantics
    mh = _man_hours_from_s11(f11)
    mm = (
        _d(f11.eligible_labor_man_minutes)
        if f11.eligible_labor_man_minutes is not None
        else None
    )

    provenance = tuple(f11.provenance) + (
        f"s04_rules={S04_RULES_VERSION}",
        f"s11_calc={f11.calculation_status.value}",
    )
    included = rate.included_cost_components if rate else ()

    # Labor semantics / conversion already blocked in S11 for HOUR_FIELD_UNPROVEN
    if f11.calculation_status == LaborCalculationStatus.UNIT_LABOR_NOT_COMPUTABLE and (
        labor_u == LaborUnit.HOUR_FIELD_UNPROVEN.value
        or (semantics and "UNPROVEN" in semantics)
    ) and mh is None:
        return OperationCostFinding(
            check_identity=f"s04:{f11.source_operation_identity}:unproven",
            source_operation_identity=f11.source_operation_identity,
            original_operation_text=f11.original_operation_text,
            canonical_operation_code=f11.canonical_operation_code,
            canonical_operation_name=f11.canonical_operation_name,
            original_claimed_labor_quantity=labor_q,
            original_labor_unit=labor_u,
            labor_semantics=semantics,
            labor_man_minutes=_s(mm),
            labor_man_hours=None,
            original_physical_quantity=qty,
            measurement_unit=unit,
            applied_rate_identity=None,
            cost_rate_authority=None,
            cost_rate_economic_type=None,
            included_cost_components=(),
            computed_direct_labor_cost_exact=None,
            computed_direct_labor_cost_rounded=None,
            computed_unit_labor_cost_exact=None,
            computed_unit_labor_cost_rounded=None,
            currency=None,
            calculation_status=CostCalculationStatus.LABOR_SEMANTICS_UNPROVEN,
            cost_completeness=CostCompleteness.NONE_MONETIZED,
            has_computable_unit_cost=False,
            authority_limitations=("HOUR_FIELD_UNPROVEN_OR_UNPROVEN_LABOR_SEMANTICS",)
            + rate_limitations,
            evidence_status="LABOR_SEMANTICS_UNPROVEN_COST_NOT_COMPUTABLE",
            labor_category_note="claimed_labor_semantics_unproven; UNKNOWN_COST_NE_ZERO_COST",
            provenance=provenance,
            rules_version=S04_RULES_VERSION,
            professional_conclusion=(
                "Семантика трудозатрат недоказана — прямая трудовая стоимость "
                "не вычислима. UNKNOWN COST ≠ ZERO COST."
            ),
            clarification_request="Подтвердите семантику man-hours / man-minutes.",
            preserved_claimed_labor_quantity=labor_q,
            preserved_physical_quantity=qty,
        )

    if (
        f11.calculation_status == LaborCalculationStatus.INVALID_INPUT
        or (labor_q is not None and labor_q < 0)
    ):
        return OperationCostFinding(
            check_identity=f"s04:{f11.source_operation_identity}:invalid",
            source_operation_identity=f11.source_operation_identity,
            original_operation_text=f11.original_operation_text,
            canonical_operation_code=f11.canonical_operation_code,
            canonical_operation_name=f11.canonical_operation_name,
            original_claimed_labor_quantity=labor_q,
            original_labor_unit=labor_u,
            labor_semantics=semantics,
            labor_man_minutes=None,
            labor_man_hours=None,
            original_physical_quantity=qty,
            measurement_unit=unit,
            applied_rate_identity=None,
            cost_rate_authority=None,
            cost_rate_economic_type=None,
            included_cost_components=(),
            computed_direct_labor_cost_exact=None,
            computed_direct_labor_cost_rounded=None,
            computed_unit_labor_cost_exact=None,
            computed_unit_labor_cost_rounded=None,
            currency=None,
            calculation_status=CostCalculationStatus.INVALID_INPUT,
            cost_completeness=CostCompleteness.NONE_MONETIZED,
            has_computable_unit_cost=False,
            authority_limitations=("negative_labor",),
            evidence_status="INVALID_INPUT",
            labor_category_note="invalid_claimed_labor",
            provenance=provenance,
            rules_version=S04_RULES_VERSION,
            professional_conclusion="Отрицательный труд — cost not computable.",
            clarification_request="Исправьте входные трудозатраты.",
            preserved_claimed_labor_quantity=labor_q,
            preserved_physical_quantity=qty,
        )

    if rate is None or rate_per_mh is None:
        status = rate_status or CostCalculationStatus.COST_RATE_NOT_AVAILABLE
        return OperationCostFinding(
            check_identity=f"s04:{f11.source_operation_identity}:no_rate",
            source_operation_identity=f11.source_operation_identity,
            original_operation_text=f11.original_operation_text,
            canonical_operation_code=f11.canonical_operation_code,
            canonical_operation_name=f11.canonical_operation_name,
            original_claimed_labor_quantity=labor_q,
            original_labor_unit=labor_u,
            labor_semantics=semantics,
            labor_man_minutes=_s(mm),
            labor_man_hours=_s(_exact(mh) if mh is not None else None),
            original_physical_quantity=qty,
            measurement_unit=unit,
            applied_rate_identity=None,
            cost_rate_authority=None,
            cost_rate_economic_type=None,
            included_cost_components=(),
            computed_direct_labor_cost_exact=None,
            computed_direct_labor_cost_rounded=None,
            computed_unit_labor_cost_exact=None,
            computed_unit_labor_cost_rounded=None,
            currency=None,
            calculation_status=status,
            cost_completeness=CostCompleteness.NONE_MONETIZED,
            has_computable_unit_cost=False,
            authority_limitations=rate_limitations,
            evidence_status="COST_NOT_COMPUTABLE_RATE_GAP",
            labor_category_note=(
                "claimed_labor_preserved; UNKNOWN_COST_NE_ZERO_COST; "
                "not automatic financial loss"
            ),
            provenance=provenance,
            rules_version=S04_RULES_VERSION,
            professional_conclusion=(
                "Применимая ставка прямых трудовых затрат отсутствует/неприменима. "
                "Трудозатраты сохранены. UNKNOWN COST ≠ ZERO COST. "
                "Не объявляется автоматической финансовой потерей."
            ),
            clarification_request="Передайте typed LaborCostRateReference с authority и scope.",
            preserved_claimed_labor_quantity=labor_q,
            preserved_physical_quantity=qty,
        )

    if mh is None:
        # Labor present but not convertible — still preserve claim
        return OperationCostFinding(
            check_identity=f"s04:{f11.source_operation_identity}:no_mh",
            source_operation_identity=f11.source_operation_identity,
            original_operation_text=f11.original_operation_text,
            canonical_operation_code=f11.canonical_operation_code,
            canonical_operation_name=f11.canonical_operation_name,
            original_claimed_labor_quantity=labor_q,
            original_labor_unit=labor_u,
            labor_semantics=semantics,
            labor_man_minutes=None,
            labor_man_hours=None,
            original_physical_quantity=qty,
            measurement_unit=unit,
            applied_rate_identity=None,
            cost_rate_authority=None,
            cost_rate_economic_type=None,
            included_cost_components=(),
            computed_direct_labor_cost_exact=None,
            computed_direct_labor_cost_rounded=None,
            computed_unit_labor_cost_exact=None,
            computed_unit_labor_cost_rounded=None,
            currency=None,
            calculation_status=CostCalculationStatus.INSUFFICIENT_DATA,
            cost_completeness=CostCompleteness.NONE_MONETIZED,
            has_computable_unit_cost=False,
            authority_limitations=("labor_hours_not_convertible",) + rate_limitations,
            evidence_status="LABOR_HOURS_ABSENT",
            labor_category_note="claimed_labor_not_monetizable; UNKNOWN_COST_NE_ZERO_COST",
            provenance=provenance,
            rules_version=S04_RULES_VERSION,
            professional_conclusion=(
                "Трудозатраты не приведены к man-hours — cost not computable. "
                "UNKNOWN COST ≠ ZERO COST."
            ),
            clarification_request=None,
            preserved_claimed_labor_quantity=labor_q,
            preserved_physical_quantity=qty,
        )

    # Compute direct labor cost
    cost_exact = _exact(mh * rate_per_mh)
    cost_rounded = _money(cost_exact)

    has_unit = (
        qty is not None
        and qty > 0
        and unit
        and f11.calculation_status
        == LaborCalculationStatus.COMPUTABLE_CLAIMED_OBSERVATION
        and f11.unit_labor_man_minutes_per_physical is not None
    )
    unit_exact = None
    unit_rounded = None
    if has_unit:
        unit_exact = _exact(cost_exact / _d(qty))
        unit_rounded = _money(unit_exact)
        calc_status = (
            CostCalculationStatus.SCENARIO_COST_COMPUTED
            if rate.rate_authority == CostRateAuthority.SCENARIO_RATE
            else CostCalculationStatus.ESTIMATED_COST_COMPUTED
        )
    else:
        # Cost computable without unit indicator (incl. zero qty, prep, composite)
        if f11.calculation_status == LaborCalculationStatus.COMPOSITE_NOT_ALLOCATABLE:
            calc_status = CostCalculationStatus.COMPOSITE_COST_UNALLOCATED
        elif has_unit is False and qty is not None and qty > 0 and not unit:
            calc_status = CostCalculationStatus.UNIT_COST_NOT_COMPUTABLE
        else:
            calc_status = (
                CostCalculationStatus.SCENARIO_COST_COMPUTED
                if rate.rate_authority == CostRateAuthority.SCENARIO_RATE
                else CostCalculationStatus.ESTIMATED_COST_COMPUTED
            )

    composite_note = ""
    if f11.calculation_status == LaborCalculationStatus.COMPOSITE_NOT_ALLOCATABLE:
        composite_note = (
            " COMPOSITE: общая стоимость сохранена без произвольного распределения."
        )

    authority = rate.rate_authority.value
    if rate.rate_authority == CostRateAuthority.SCENARIO_RATE:
        evidence = "SCENARIO_CLAIMED_DIRECT_LABOR_COST_NOT_ACTUAL"
    elif rate.rate_authority == CostRateAuthority.APPROVED_COST_RATE:
        evidence = "APPROVED_RATE_USED_BUT_ACTUAL_INCURRED_COST_NOT_PROVEN"
    else:
        evidence = "ESTIMATED_CLAIMED_DIRECT_LABOR_COST_NOT_ACTUAL"

    extra_lim: list[str] = []
    if rate.economic_type == CostRateEconomicType.FULLY_BURDENED_LABOR_COST_RATE:
        extra_lim.append("FULLY_BURDENED_NE_PURE_DIRECT_LABOR_COST")
        evidence = evidence + "|FULLY_BURDENED_USED_WITH_DIRECT_LABOR_SCOPE_LIMITATION"
    if "COST_COMPONENT_UNCERTAINTY" in rate_limitations:
        extra_lim.append("COST_COMPONENT_UNCERTAINTY")
    if rate_per_mh == 0:
        extra_lim.append("ZERO_RATE_EXPLICITLY_CONFIRMED_APPLIED")

    return OperationCostFinding(
        check_identity=f"s04:{f11.source_operation_identity}:cost",
        source_operation_identity=f11.source_operation_identity,
        original_operation_text=f11.original_operation_text,
        canonical_operation_code=f11.canonical_operation_code,
        canonical_operation_name=f11.canonical_operation_name,
        original_claimed_labor_quantity=labor_q,
        original_labor_unit=labor_u,
        labor_semantics=semantics,
        labor_man_minutes=_s(_exact(mm) if mm is not None else _exact(mh * 60)),
        labor_man_hours=_s(_exact(mh)),
        original_physical_quantity=qty,
        measurement_unit=unit,
        applied_rate_identity=f"{rate.rate_identity}@{rate.version}",
        cost_rate_authority=authority,
        cost_rate_economic_type=rate.economic_type.value,
        included_cost_components=included,
        computed_direct_labor_cost_exact=_s(cost_exact),
        computed_direct_labor_cost_rounded=_s(cost_rounded),
        computed_unit_labor_cost_exact=_s(unit_exact),
        computed_unit_labor_cost_rounded=_s(unit_rounded),
        currency=rate.currency,
        calculation_status=calc_status,
        cost_completeness=CostCompleteness.FULL_MONETIZED,
        has_computable_unit_cost=bool(has_unit),
        authority_limitations=rate_limitations
        + tuple(extra_lim)
        + (
            "DIRECT_LABOR_COST_NE_FULL_EXECUTION_COST",
            "PAID_LABOR_NE_PRODUCTIVE_LABOR",
            "LABOR_WITHOUT_QUANTITY_NE_AUTOMATIC_FINANCIAL_LOSS",
            "OPERATION_COST_NE_CONTRACT_PRICE",
            "PHYSICAL_RESULT_NE_REVENUE",
            "COST_ESTIMATION_NE_PAYROLL",
            "COST_CONCENTRATION_NE_INEFFICIENCY",
            "TARGET_FUND_DEVIATION_NE_PROVEN_FINANCIAL_LOSS",
            "WORKING_QUANTUM_0_0001_NE_EXACT_PERIODIC_FRACTION",
        ),
        evidence_status=evidence,
        labor_category_note=(
            "claimed_labor_monetized_as_scenario_or_estimated_direct_labor; "
            "not proven productive/paid/idle/loss classification; "
            "not automatic financial loss; "
            "no cross-worker labor allocation"
        ),
        provenance=provenance,
        rules_version=S04_RULES_VERSION,
        professional_conclusion=(
            f"Расчётные прямые трудовые затраты: {_s(cost_exact)} {rate.currency} "
            f"(money-rounded {_s(cost_rounded)}; working quantum={S04_EXACT_QUANTUM}, "
            f"not exact periodic fraction; rate={rate.rate_identity} "
            f"{rate.rate_value}/{rate.rate_unit.value}). "
            f"Authority={authority} (≠ economic_type={rate.economic_type.value}). "
            f"CLAIMED ≠ INCURRED ACTUAL. "
            f"Unit cost={'%s %s/%s' % (_s(unit_exact), rate.currency, unit) if unit_exact is not None else 'NOT_COMPUTABLE'}. "
            f"DIRECT ≠ FULL COST. No payroll / revenue / margin."
            f"{composite_note}"
        ),
        clarification_request=None,
        preserved_claimed_labor_quantity=labor_q,
        preserved_physical_quantity=qty,
    )


def _build_conservation(
    findings: Sequence[OperationCostFinding],
    *,
    s01_total_mm: Optional[float],
) -> CostConservationSummary:
    monetized_mm = Decimal("0")
    non_mon_mm = Decimal("0")
    total_exact = Decimal("0")
    with_unit = Decimal("0")
    without_unit = Decimal("0")
    line_sum_rounded = Decimal("0")
    any_monetized = False
    any_non = False
    currency = None
    currencies: set[str] = set()

    for f in findings:
        mm = _d(f.labor_man_minutes) if f.labor_man_minutes is not None else None
        if f.computed_direct_labor_cost_exact is not None:
            any_monetized = True
            c = _d(f.computed_direct_labor_cost_exact)
            total_exact += c
            if f.has_computable_unit_cost:
                with_unit += c
            else:
                without_unit += c
            if f.computed_direct_labor_cost_rounded is not None:
                line_sum_rounded += _d(f.computed_direct_labor_cost_rounded)
            if mm is not None:
                monetized_mm += mm
            if f.currency:
                currencies.add(f.currency)
                currency = f.currency
        else:
            any_non = True
            if mm is not None:
                non_mon_mm += mm
            elif f.preserved_claimed_labor_quantity is not None and f.original_labor_unit == LaborUnit.MAN_MINUTE.value:
                non_mon_mm += _d(f.preserved_claimed_labor_quantity)

    if len(currencies) > 1:
        # Should not happen after rate selection; fail closed totals
        return CostConservationSummary(
            total_claimed_labor_man_minutes=_s(_exact(_d(s01_total_mm or 0))) or "0",
            monetized_labor_man_minutes=_s(_exact(monetized_mm)) or "0",
            non_monetized_labor_man_minutes=_s(_exact(non_mon_mm)) or "0",
            total_calculated_direct_labor_cost_exact=None,
            total_calculated_direct_labor_cost_rounded=None,
            cost_with_computable_unit_indicators_exact=None,
            cost_without_computable_unit_indicators_exact=None,
            currency=None,
            conservation_holds=False,
            categories_mutually_exclusive=True,
            calculation_completeness=CostCompleteness.PARTIAL_COST_COVERAGE,
            line_sum_rounded=None,
            total_vs_line_sum_residual_rounded=None,
            reconciliation_note="MULTI_CURRENCY_SUM_FORBIDDEN",
            notes=("different_currencies_not_summed",),
        )

    total_claimed = _exact(_d(s01_total_mm)) if s01_total_mm is not None else _exact(
        monetized_mm + non_mon_mm
    )
    preserved_labor = _exact(monetized_mm + non_mon_mm)

    if any_monetized and any_non:
        completeness = CostCompleteness.PARTIAL_COST_COVERAGE
    elif any_monetized:
        completeness = CostCompleteness.FULL_MONETIZED
    else:
        completeness = CostCompleteness.NONE_MONETIZED

    total_rounded = _money(total_exact) if any_monetized else None
    residual = None
    if total_rounded is not None:
        residual = _money(line_sum_rounded - total_rounded)

    conservation_holds = abs(preserved_labor - total_claimed) < Decimal("0.0001")
    if any_monetized:
        # Cost partition conservation: with_unit + without_unit == total_exact
        conservation_holds = conservation_holds and abs(
            (with_unit + without_unit) - total_exact
        ) < Decimal("0.0001")

    notes = (
        "Cost categories mutually exclusive: with unit indicator vs without.",
        "Labor without quantity still monetized when rate+hours allow.",
        "LABOR_WITHOUT_QUANTITY_NE_AUTOMATIC_FINANCIAL_LOSS",
        "UNKNOWN_COST_NE_ZERO_COST",
        "ZERO_RUB_IS_NOT_PROVEN_SHIFT_COST_WHEN_NONE_MONETIZED",
        "DIRECT_LABOR_COST_NE_FULL_EXECUTION_COST",
        "CLAIMED_LABOR_COST_NE_INCURRED_ACTUAL_COST",
        "WORKING_QUANTUM_0_0001_IS_LIMITED_PRECISION_NOT_EXACT_PERIODIC",
        "ROUNDING_RESIDUAL_NOT_HIDDEN_OR_REDISTRIBUTED",
        f"rounding={S04_ROUNDING} money_quantum={S04_MONEY_QUANTUM}",
    )
    if completeness == CostCompleteness.NONE_MONETIZED:
        notes = notes + (
            "no_monetized_lines_total_cost_is_None_not_zero_RUB_as_proven_cost",
        )
    return CostConservationSummary(
        total_claimed_labor_man_minutes=_s(total_claimed) or "0",
        monetized_labor_man_minutes=_s(_exact(monetized_mm)) or "0",
        non_monetized_labor_man_minutes=_s(_exact(non_mon_mm)) or "0",
        total_calculated_direct_labor_cost_exact=_s(_exact(total_exact)) if any_monetized else None,
        total_calculated_direct_labor_cost_rounded=_s(total_rounded),
        cost_with_computable_unit_indicators_exact=_s(_exact(with_unit)) if any_monetized else None,
        cost_without_computable_unit_indicators_exact=_s(_exact(without_unit))
        if any_monetized
        else None,
        currency=currency,
        conservation_holds=conservation_holds,
        categories_mutually_exclusive=True,
        calculation_completeness=completeness,
        line_sum_rounded=_s(_money(line_sum_rounded)) if any_monetized else None,
        total_vs_line_sum_residual_rounded=_s(residual),
        reconciliation_note=(
            "sum(line_rounded) - round(sum(exact)); residual from display rounding only"
            if any_monetized
            else "no_monetized_lines"
        ),
        notes=notes,
    )


def evaluate_s04(
    audit_input: ShiftAuditInput,
    s01: ShiftAuditArtifact,
    s10: ShiftOperationClassificationArtifact,
    s02: ShiftTechnologicalIntegrityArtifact,
    s03: ShiftPhysicalIntegrityArtifact,
    s11: ShiftLaborBenchmarkArtifact,
    *,
    audit_id: Optional[str] = None,
    run_id: Optional[str] = None,
    cost_rates: Sequence[LaborCostRateReference] = (),
) -> ShiftExecutionCostArtifact:
    del s02, s03  # available for future authority gates; unused in v0.1 calculations

    by_id = _s11_by_identity(s11)
    findings: list[OperationCostFinding] = []
    applied_ids: list[str] = []
    for line in s10.classifications:
        f11 = by_id.get(line.source_operation_identity)
        if f11 is None:
            continue
        claim = _claim_for_identity(
            audit_input, line.source_operation_identity, line.original_operation_text
        )
        labor_cat = claim.work_kind_hint if claim else None
        rate, rate_status, rate_lim = _select_applicable_rate(
            cost_rates,
            project_code=audit_input.project_code,
            work_date=audit_input.work_date,
            labor_category=labor_cat,
        )
        rate_per_mh = _rate_to_per_man_hour(rate) if rate else None
        if rate:
            applied_ids.append(f"{rate.rate_identity}@{rate.version}")
        findings.append(
            _evaluate_operation(
                f11=f11,
                line=line,
                rate=rate,
                rate_status=rate_status,
                rate_limitations=rate_lim,
                rate_per_mh=rate_per_mh,
            )
        )

    s01_total = None
    if s01.s01_metrics and s01.s01_metrics.claimed_total_man_minutes is not None:
        s01_total = float(s01.s01_metrics.claimed_total_man_minutes)
    conservation = _build_conservation(findings, s01_total_mm=s01_total)

    money_policy = (
        "Monetary policy: working_quantum="
        + S04_EXACT_QUANTUM
        + " (limited precision, not exact periodic fractions); money="
        + S04_MONEY_QUANTUM
        + "; "
        + S04_ROUNDING
        + "."
    )
    observations = [
        "S04 = deterministic direct labor execution cost skill.",
        "CLAIMED LABOR COST != INCURRED ACTUAL COST.",
        "SCENARIO RATE != APPROVED COST RATE.",
        "WAGE RATE != EMPLOYER LABOR COST RATE.",
        "DIRECT LABOR COST != FULL EXECUTION COST.",
        "PAID LABOR != PRODUCTIVE LABOR.",
        "LABOR WITHOUT QUANTITY != AUTOMATIC FINANCIAL LOSS.",
        "OPERATION COST != CONTRACT PRICE.",
        "PHYSICAL RESULT != REVENUE.",
        "COST ESTIMATION != PAYROLL.",
        "UNKNOWN COST != ZERO COST.",
        "ZERO RUB when none monetized != proven shift cost.",
        "COST CONCENTRATION != INEFFICIENCY.",
        "TARGET FUND DEVIATION != PROVEN FINANCIAL LOSS.",
        "AUTHORITY != ECONOMIC TYPE.",
        "FULLY BURDENED != PURE DIRECT LABOR COST.",
        "No FX conversion. No margin. No revenue. No payroll.",
        "Per-operation category or shift-wide rate selection; no cross-worker labor allocation; not a full multi-rate engine.",
        "Production cost rate READ adapter: NOT_IMPLEMENTED_LIMITATION.",
        money_policy,
        "Rules: " + S04_RULES_VERSION + ".",
        "S04_ENGINE_IMPLEMENTED; ACTUAL_COST_NOT_PROVEN; FULL_EXECUTION_COST_NOT_COMPUTABLE.",
    ]

    unique_applied = sorted(set(applied_ids))
    if unique_applied:
        applied = (
            "rates_used=["
            + ", ".join(unique_applied)
            + "]; PER_OPERATION_OR_SHIFT_WIDE; NO_CROSS_WORKER_ALLOCATION"
        )
    else:
        applied = None

    summary = [
        "PSAA S04 — Execution Cost Analysis (direct labor only)",
        f"Проект: {audit_input.project_code} date={audit_input.work_date} crew={audit_input.crew_id}",
        f"Applied rate: {applied or 'NONE'}",
        (
            f"Conservation: claimed_mm={conservation.total_claimed_labor_man_minutes} "
            f"total_cost={conservation.total_calculated_direct_labor_cost_exact} "
            f"with_unit={conservation.cost_with_computable_unit_indicators_exact} "
            f"without_unit={conservation.cost_without_computable_unit_indicators_exact} "
            f"completeness={conservation.calculation_completeness.value} "
            f"holds={conservation.conservation_holds}"
        ),
        "Managerial acceptance: NOT_IN_SCOPE | Payroll: NOT_PERFORMED | "
        "Commercial recognition: NOT_PERFORMED | Rate mutation: NOT_PERFORMED",
        "Actual cost: ACTUAL_COST_NOT_PROVEN | Full execution cost: NOT_COMPUTABLE | "
        "Margin/Revenue: NOT_COMPUTED",
    ]
    for f in findings:
        summary.append(
            f"- «{f.original_operation_text}» | qty={f.original_physical_quantity} "
            f"{f.measurement_unit or ''} | labor_h={f.labor_man_hours} | "
            f"rate={f.applied_rate_identity or '-'} | "
            f"cost={f.computed_direct_labor_cost_exact or 'N/A'} | "
            f"unit={f.computed_unit_labor_cost_exact or '-'} | "
            f"{f.calculation_status.value}"
        )

    return ShiftExecutionCostArtifact(
        schema_version=S04_ARTIFACT_SCHEMA_VERSION,
        rules_version=S04_RULES_VERSION,
        audit_id=audit_id or s01.audit_id or str(uuid.uuid4()),
        agent_code=AGENT_CODE,
        agent_version=AGENT_VERSION,
        run_id=run_id,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        project_code=audit_input.project_code,
        work_date=audit_input.work_date,
        crew_id=audit_input.crew_id,
        evaluation_domain="claimed_direct_labor_execution_cost",
        findings=tuple(findings),
        cost_conservation=conservation,
        applied_rate_summary=applied,
        observations=tuple(observations),
        managerial_acceptance_status="NOT_IN_SCOPE",
        payroll_decision_status="NOT_PERFORMED",
        commercial_recognition_status="NOT_PERFORMED",
        cost_rate_mutation_status="NOT_PERFORMED",
        contract_price_mutation_status="NOT_PERFORMED",
        actual_cost_verification_status=ActualCostVerificationStatus.ACTUAL_COST_NOT_PROVEN,
        full_execution_cost_status="FULL_EXECUTION_COST_NOT_COMPUTABLE",
        margin_status="NOT_COMPUTED",
        revenue_status="NOT_COMPUTED",
        human_readable_summary="\n".join(summary),
        s04_engine_status="S04_ENGINE_IMPLEMENTED",
        claimed_cost_status="CLAIMED_DIRECT_LABOR_COST_COMPUTABLE_WHEN_RATE_AND_LABOR_ALLOW",
        verified_actual_cost_status="ACTUAL_COST_NOT_PROVEN",
        durable_history_schema_status="UNCHANGED_IN_THIS_INCREMENT",
        production_cost_rate_read_adapter_status="NOT_IMPLEMENTED_LIMITATION",
    )


def scenario_rate_1000_rub_per_man_hour(
    *,
    project_code: str = "FIXTURE_INSULATION_DEMO",
) -> LaborCostRateReference:
    """Explicit demonstration scenario rate — NOT a project/worker actual rate."""
    return LaborCostRateReference(
        rate_identity="PSAA_S04_SCENARIO_RUB_1000_MH",
        rate_value="1000",
        currency="RUB",
        rate_unit=CostRateUnit.PER_MAN_HOUR,
        rate_authority=CostRateAuthority.SCENARIO_RATE,
        economic_type=CostRateEconomicType.EMPLOYER_DIRECT_LABOR_COST_RATE,
        provenance="explicit_caller_scenario_for_fixture_demonstration_only",
        version="demo-v0.1",
        applicable_project_scope=project_code,
        applicable_labor_category="insulation_crew_direct_labor_scenario",
        valid_from="2020-01-01",
        valid_to="2099-12-31",
        applicability_note=(
            "SCENARIO ONLY — not an approved project rate, not wage, not actual incurred cost."
        ),
    )
