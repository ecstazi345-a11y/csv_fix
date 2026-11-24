"""S03 — Physical Integrity (deterministic).

Checks claimed physical results: quantity, unit, object identity, result state,
duplicate risk, BOQ relationship. Does NOT prove physical execution.
Does NOT invent quantities. Does NOT convert units without geometry.
Does NOT create earned value / contract acceptance.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Optional, Sequence

from agents.production_shift_auditor.catalogs.insulation_physical_rules_v0_1 import (
    INSULATION_PHYSICAL_RULESET_VERSION,
    INSULATION_PHYSICAL_RULES,
    PhysicalIntegrityRule,
    rule_for_operation,
)
from agents.production_shift_auditor.contracts import OperationLaborClaim, ShiftAuditInput
from agents.production_shift_auditor.s03_contracts import (
    S03_ARTIFACT_SCHEMA_VERSION,
    S03_RULES_VERSION,
    BoqRelationshipStatus,
    ClaimedResultState,
    MeasurabilityClass,
    PhysicalCheckResult,
    PhysicalCheckType,
    PhysicalIntegrityFinding,
    PhysicalSourceAuthority,
    PriorPhysicalClaimEvidence,
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

AGENT_CODE = "PRODUCTION_SHIFT_AUDITOR"
AGENT_VERSION = "0.1"

_KNOWN_UNITS = {
    "шт": "шт",
    "шт.": "шт",
    "pcs": "шт",
    "pc": "шт",
    "м": "м",
    "м.": "м",
    "мп": "м",
    "м.п": "м",
    "м.п.": "м",
    "m": "м",
    "lm": "м",
    "м2": "м2",
    "м²": "м2",
    "m2": "м2",
    "sqm": "м2",
    "м3": "м3",
    "м³": "м3",
    "m3": "м3",
    "кг": "кг",
    "kg": "кг",
    "комплект": "комплект",
    "компл": "комплект",
    "участок": "участок",
}

_LENGTH_UNITS = {"м"}
_AREA_UNITS = {"м2"}
_COUNT_UNITS = {"шт"}


def _norm_unit(unit: Optional[str]) -> Optional[str]:
    if unit is None:
        return None
    raw = normalize_operation_text(unit).replace(" ", "")
    if not raw:
        return None
    return _KNOWN_UNITS.get(raw, raw)


def _claim_for_line(
    audit_input: ShiftAuditInput, line: OperationClassificationLine
) -> Optional[OperationLaborClaim]:
    for claim in audit_input.operations:
        if claim.operation_name == line.original_operation_text:
            return claim
        if claim.source_record_ids and claim.source_record_ids[0] == line.source_operation_identity:
            return claim
    return None


def _result_state_for(
    rule: Optional[PhysicalIntegrityRule], line: OperationClassificationLine
) -> ClaimedResultState:
    if rule is not None:
        return rule.expected_result_state
    if line.classification_status == ClassificationStatus.COMPOSITE_OPERATION:
        return ClaimedResultState.UNKNOWN
    return ClaimedResultState.UNKNOWN


def _boq_status(claim: Optional[OperationLaborClaim]) -> BoqRelationshipStatus:
    if claim is None or not (claim.boq_name or "").strip():
        return BoqRelationshipStatus.NO_BOQ_LINK
    # Link text may exist, but operation quantity is never auto contract/earned
    return BoqRelationshipStatus.OPERATION_NOT_AUTO_CONTRACT_QUANTITY


def _base_finding(
    *,
    check_identity: str,
    line: OperationClassificationLine,
    claim: Optional[OperationLaborClaim],
    check_type: PhysicalCheckType,
    rule: Optional[PhysicalIntegrityRule],
    check_result: PhysicalCheckResult,
    measurability: MeasurabilityClass,
    claimed_result_state: ClaimedResultState,
    supporting_evidence: tuple[str, ...],
    missing_information: tuple[str, ...],
    professional_explanation: str,
    clarification_request: Optional[str],
    duplicate_risk: Optional[str] = None,
    boq_relationship_status: Optional[BoqRelationshipStatus] = None,
) -> PhysicalIntegrityFinding:
    demo = bool(
        rule and rule.source_authority == PhysicalSourceAuthority.DEMONSTRATION_RULE
    )
    qty = claim.physical_quantity if claim is not None else line.physical_quantity
    unit = claim.physical_unit if claim is not None else line.physical_unit
    return PhysicalIntegrityFinding(
        check_identity=check_identity,
        source_operation_identity=line.source_operation_identity,
        original_operation_text=line.original_operation_text,
        classified_operation_code=line.operation_code_candidate,
        classified_operation_name=line.canonical_operation_candidate,
        check_type=check_type,
        original_claimed_quantity=qty,
        original_unit=unit,
        physical_object_reference=(
            (claim.physical_object_hint if claim else None) or None
        ),
        claimed_result_state=claimed_result_state,
        measurability=measurability,
        applicable_rule_id=rule.rule_id if rule else None,
        rule_version=rule.revision if rule else None,
        source_authority=rule.source_authority if rule else None,
        source_provenance=(
            ((rule.source_citation,) if rule else ())
            + (("DEMONSTRATION_RULE",) if demo else ())
            + (("UNIVERSAL_NUMERIC",) if rule and rule.source_authority == PhysicalSourceAuthority.UNIVERSAL_NUMERIC else ())
        ),
        check_result=check_result,
        supporting_evidence=supporting_evidence,
        missing_information=missing_information,
        duplicate_risk=duplicate_risk,
        boq_relationship_status=boq_relationship_status
        or _boq_status(claim),
        professional_explanation=professional_explanation,
        clarification_request=clarification_request,
        demonstration_rule=demo,
        claimed_labor_quantity=(
            claim.claimed_labor_quantity if claim is not None else line.claimed_labor_quantity
        ),
        claimed_labor_unit=(
            claim.labor_unit.value if claim is not None else line.claimed_labor_unit
        ),
    )


def _gate_from_classification(
    line: OperationClassificationLine, claim: Optional[OperationLaborClaim]
) -> Optional[PhysicalIntegrityFinding]:
    st = line.classification_status
    if st == ClassificationStatus.COMPOSITE_OPERATION:
        return _base_finding(
            check_identity=f"s03:{line.source_operation_identity}:composite",
            line=line,
            claim=claim,
            check_type=PhysicalCheckType.COMPOSITE_LIMITATION,
            rule=None,
            check_result=PhysicalCheckResult.INSUFFICIENT_CONTEXT,
            measurability=MeasurabilityClass.COMPOSITE_LIMITED,
            claimed_result_state=ClaimedResultState.UNKNOWN,
            supporting_evidence=(
                "s10_status=COMPOSITE_OPERATION",
                "NO_AUTOMATIC_QUANTITY_OR_TIME_DISTRIBUTION",
                f"preserved_quantity={claim.physical_quantity if claim else line.physical_quantity}",
                f"preserved_labor={claim.claimed_labor_quantity if claim else line.claimed_labor_quantity}",
            ),
            missing_information=("separated_component_operations_with_quantities",),
            professional_explanation=(
                "COMPOSITE_OPERATION: исходные объём и трудозатраты сохранены; "
                "распределение между компонентами без подтверждённых данных запрещено."
            ),
            clarification_request="Разделите составную запись перед полной physical integrity оценкой.",
        )
    if st in {
        ClassificationStatus.UNKNOWN_OPERATION,
        ClassificationStatus.AMBIGUOUS,
        ClassificationStatus.INSUFFICIENT_CONTEXT,
    }:
        return _base_finding(
            check_identity=f"s03:{line.source_operation_identity}:s10_gate",
            line=line,
            claim=claim,
            check_type=PhysicalCheckType.CONTEXT_SUFFICIENCY,
            rule=None,
            check_result=(
                PhysicalCheckResult.NOT_EVALUATED
                if st == ClassificationStatus.UNKNOWN_OPERATION
                else PhysicalCheckResult.INSUFFICIENT_CONTEXT
            ),
            measurability=MeasurabilityClass.MEASURABILITY_UNKNOWN,
            claimed_result_state=ClaimedResultState.UNKNOWN,
            supporting_evidence=(f"s10_status={st.value}",),
            missing_information=("classified_operation_for_physical_rules",),
            professional_explanation=(
                "Классификация недостаточна для применения physical integrity rules "
                "(CLASSIFICATION ≠ PHYSICAL VALIDATION)."
            ),
            clarification_request="Уточните каноническую операцию / контекст.",
        )
    return None


def _eval_quantity_and_unit(
    rule: PhysicalIntegrityRule,
    line: OperationClassificationLine,
    claim: Optional[OperationLaborClaim],
) -> PhysicalIntegrityFinding:
    qty = claim.physical_quantity if claim is not None else line.physical_quantity
    unit_raw = claim.physical_unit if claim is not None else line.physical_unit
    unit = _norm_unit(unit_raw)
    state = rule.expected_result_state
    meas = rule.measurability

    # Universal: negative quantity — ordinary execution claim scope only
    if qty is not None and qty < 0:
        univ = next(
            r for r in INSULATION_PHYSICAL_RULES if r.rule_id == "UNIV.QTY.NON_NEGATIVE"
        )
        return _base_finding(
            check_identity=f"s03:{line.source_operation_identity}:neg_qty",
            line=line,
            claim=claim,
            check_type=PhysicalCheckType.QUANTITY_INTEGRITY,
            rule=univ,
            check_result=PhysicalCheckResult.INVALID_QUANTITY,
            measurability=meas,
            claimed_result_state=state,
            supporting_evidence=(
                f"quantity={qty}",
                "ordinary_execution_claim_scope",
                "NOT_STORNO_OR_CORRECTION_WORKFLOW",
            ),
            missing_information=(),
            professional_explanation=(
                "Отрицательное количество недопустимо для обычного execution claim. "
                "Граница правила: не покрывает будущие storno/reversing/correction "
                "accounting events (correction workflow не реализован)."
            ),
            clarification_request=(
                "Исправьте заявленное количество либо оформите отдельное "
                "корректирующее событие (когда такой workflow появится)."
            ),
        )

    if not rule.requires_quantity:
        # Current rule does not require quantity — NOT the same as "not measurable"
        if qty is None:
            return _base_finding(
                check_identity=f"s03:{line.source_operation_identity}:{rule.rule_id}",
                line=line,
                claim=claim,
                check_type=PhysicalCheckType.QUANTITY_INTEGRITY,
                rule=rule,
                check_result=PhysicalCheckResult.NOT_APPLICABLE,
                measurability=MeasurabilityClass.QUANTITY_NOT_REQUIRED_BY_CURRENT_RULE,
                claimed_result_state=state,
                supporting_evidence=(
                    "quantity_not_required_by_current_rule",
                    "NOT_ONTOLOGICAL_NON_MEASURABILITY",
                    "LABOR_IS_NOT_PHYSICAL_VOLUME",
                    "future_approved_rules_may_add_units",
                ),
                missing_information=(),
                professional_explanation=(
                    "По текущему правилу количество не требуется "
                    "(quantity not required by current rule). Это не означает "
                    "принципиальную неизмеримость: подготовка поверхности может "
                    "в будущем измеряться в м², склеивание швов — в метрах, при "
                    "наличии утверждённого правила. Трудозатраты ≠ физический объём. "
                    "Отсутствие утверждённого правила не блокирует будущую "
                    "пооперационную экономику."
                ),
                clarification_request=None,
            )
        return _base_finding(
            check_identity=f"s03:{line.source_operation_identity}:{rule.rule_id}",
            line=line,
            claim=claim,
            check_type=PhysicalCheckType.QUANTITY_INTEGRITY,
            rule=rule,
            check_result=PhysicalCheckResult.CONSISTENT_WITH_CHECKED_RULE,
            measurability=MeasurabilityClass.QUANTITY_NOT_REQUIRED_BY_CURRENT_RULE,
            claimed_result_state=state,
            supporting_evidence=(
                f"optional_quantity={qty}",
                "quantity_not_required_by_current_rule",
            ),
            missing_information=(),
            professional_explanation=(
                "Количество указано опционально; текущий rule его не требует "
                "(не запрещает будущие контекстные единицы измерения)."
            ),
            clarification_request=None,
        )

    # Measurable: quantity expected
    if qty is None:
        return _base_finding(
            check_identity=f"s03:{line.source_operation_identity}:{rule.rule_id}:qty",
            line=line,
            claim=claim,
            check_type=PhysicalCheckType.QUANTITY_INTEGRITY,
            rule=rule,
            check_result=PhysicalCheckResult.INSUFFICIENT_CONTEXT,
            measurability=meas,
            claimed_result_state=state,
            supporting_evidence=("measurable_result_expected", "quantity_absent"),
            missing_information=("physical_quantity",),
            professional_explanation=(
                "Операция предполагает измеримый физический результат, но количество "
                "отсутствует. Отсутствие не заменяется нулём. "
                "MISSING EVIDENCE ≠ PROVEN VIOLATION."
            ),
            clarification_request="Укажите заявленное физическое количество и единицу.",
        )

    if qty == 0 and claim is not None and claim.claimed_labor_quantity > 0:
        # Zero volume with positive labor — not automatic violation
        zero_finding_ok = True
    else:
        zero_finding_ok = True

    if rule.discrete_integer_quantity:
        if not float(qty).is_integer() and abs(qty - round(qty)) > 1e-9:
            return _base_finding(
                check_identity=f"s03:{line.source_operation_identity}:{rule.rule_id}:disc",
                line=line,
                claim=claim,
                check_type=PhysicalCheckType.QUANTITY_INTEGRITY,
                rule=rule,
                check_result=PhysicalCheckResult.INVALID_QUANTITY,
                measurability=meas,
                claimed_result_state=state,
                supporting_evidence=(f"quantity={qty}", "discrete_integer_expected"),
                missing_information=(),
                professional_explanation=(
                    "Для дискретного результата (шт) заявлено нецелое количество "
                    "(demonstration discreteness rule)."
                ),
                clarification_request="Уточните целое количество изделий.",
            )

    allowed_norm = {_norm_unit(u) for u in rule.allowed_units}
    allowed_norm.discard(None)
    if not unit:
        return _base_finding(
            check_identity=f"s03:{line.source_operation_identity}:{rule.rule_id}:unit",
            line=line,
            claim=claim,
            check_type=PhysicalCheckType.UNIT_INTEGRITY,
            rule=rule,
            check_result=PhysicalCheckResult.INSUFFICIENT_CONTEXT,
            measurability=meas,
            claimed_result_state=state,
            supporting_evidence=(f"quantity={qty}", "unit_absent"),
            missing_information=("physical_unit",),
            professional_explanation="Единица измерения отсутствует при заявленном количестве.",
            clarification_request="Укажите единицу измерения физического результата.",
        )

    known_canonical = {"шт", "м", "м2", "м3", "кг", "комплект", "участок"}
    if unit not in known_canonical:
        return _base_finding(
            check_identity=f"s03:{line.source_operation_identity}:{rule.rule_id}:unk_unit",
            line=line,
            claim=claim,
            check_type=PhysicalCheckType.UNIT_INTEGRITY,
            rule=rule,
            check_result=PhysicalCheckResult.INSUFFICIENT_CONTEXT,
            measurability=meas,
            claimed_result_state=state,
            supporting_evidence=(f"unit={unit_raw}", "unknown_unit_semantics"),
            missing_information=("known_unit_semantics",),
            professional_explanation=(
                "Семантика единицы измерения неизвестна working catalog — "
                "неопределённость, не автоматическое нарушение."
            ),
            clarification_request="Укажите известную единицу (шт, м, м², …).",
        )

    if allowed_norm and unit not in allowed_norm:
        # Missing conversion params ≠ proven physical incompatibility of units.
        # Auto-conversion is never performed.
        conv_rule = next(
            (
                r
                for r in INSULATION_PHYSICAL_RULES
                if r.rule_id == "DEMO.INS.PHY.NO_UNIT_CONVERSION_WITHOUT_GEOMETRY"
            ),
            rule,
        )
        convertible_pair = (
            (unit in _AREA_UNITS and bool(allowed_norm & _LENGTH_UNITS))
            or (unit in _LENGTH_UNITS and bool(allowed_norm & _AREA_UNITS))
            or (unit in _COUNT_UNITS and bool(allowed_norm & (_LENGTH_UNITS | _AREA_UNITS)))
            or (unit in (_LENGTH_UNITS | _AREA_UNITS) and bool(allowed_norm & _COUNT_UNITS))
        )
        if convertible_pair or unit in _AREA_UNITS | _LENGTH_UNITS | _COUNT_UNITS:
            evidence = [
                f"unit={unit_raw}",
                "allowed=" + ",".join(sorted(u for u in allowed_norm if u)),
                "NO_AUTOMATIC_UNIT_CONVERSION",
                "missing_geometry_ne_proven_unit_incompatibility",
            ]
            if unit in _AREA_UNITS and allowed_norm & _LENGTH_UNITS:
                evidence.append("area_where_length_expected_conversion_unproven")
            if unit in _LENGTH_UNITS and allowed_norm & _AREA_UNITS:
                evidence.append("length_where_area_expected_conversion_unproven")
            if unit in _COUNT_UNITS:
                evidence.append("count_where_length_or_area_expected_conversion_unproven")
            return _base_finding(
                check_identity=f"s03:{line.source_operation_identity}:{rule.rule_id}:unit_ctx",
                line=line,
                claim=claim,
                check_type=PhysicalCheckType.UNIT_INTEGRITY,
                rule=conv_rule,
                check_result=PhysicalCheckResult.INSUFFICIENT_CONTEXT,
                measurability=meas,
                claimed_result_state=state,
                supporting_evidence=tuple(evidence),
                missing_information=(
                    "geometry_parameters_or_confirmed_conversion_formula",
                    "approved_measurement_rule_if_alternate_unit",
                ),
                professional_explanation=(
                    "Единица не совпадает с ожидаемой по текущему rule. "
                    "Отсутствие геометрии/формулы не доказывает физическую "
                    "несовместимость единиц (например м трубопровода могут стать "
                    "м² изоляции при подтверждённой формуле). Автоконверсия "
                    "не выполняется. Статус: неопределённость, не "
                    "UNIT_INCOMPATIBILITY."
                ),
                clarification_request=(
                    "Укажите ожидаемую единицу либо геометрию и утверждённую "
                    "формулу пересчёта."
                ),
            )
        return _base_finding(
            check_identity=f"s03:{line.source_operation_identity}:{rule.rule_id}:unit_mis",
            line=line,
            claim=claim,
            check_type=PhysicalCheckType.UNIT_INTEGRITY,
            rule=rule,
            check_result=PhysicalCheckResult.INSUFFICIENT_CONTEXT,
            measurability=meas,
            claimed_result_state=state,
            supporting_evidence=(
                f"unit={unit_raw}",
                "allowed=" + ",".join(sorted(u for u in allowed_norm if u)),
                "no_approved_measurement_rule_for_unit_pair",
                "NO_AUTOMATIC_UNIT_CONVERSION",
            ),
            missing_information=("approved_measurement_rule", "compatible_unit"),
            professional_explanation=(
                "Нет утверждённого правила измерения для данной пары "
                "единица/операция — неопределённость. Не объявляется доказанной "
                "физической несовместимостью без engineering authority."
            ),
            clarification_request="Укажите единицу по утверждённому правилу или само правило.",
        )

    evidence = [
        f"quantity={qty}",
        f"unit={unit_raw}",
        f"claimed_result_state={state.value}",
        "CLAIMED_RESULT_NE_VERIFIED_RESULT",
        "CONSISTENT_APPLIES_ONLY_TO_THIS_CHECKED_RULE",
        "DEMONSTRATION_RULE_NE_INDUSTRIAL_PHYSICAL_PROOF",
    ]
    if state == ClaimedResultState.MANUFACTURED:
        evidence.extend(
            [
                "CLAIMED_MANUFACTURED_NE_PROVEN_FABRICATION",
                "MANUFACTURED_NE_INSTALLED_NE_CONTRACT_ACCEPTED_NE_EARNED",
            ]
        )
    if state == ClaimedResultState.INSTALLED:
        evidence.extend(
            [
                "CLAIMED_INSTALLED_NE_INSPECTION_CONFIRMED",
                "INSTALLED_NE_CONTRACT_ACCEPTED_NE_EARNED",
            ]
        )
    if qty == 0 and claim is not None and claim.claimed_labor_quantity > 0:
        evidence.append("zero_quantity_with_positive_labor_not_auto_violation")

    expl = (
        f"Заявленный физический результат согласуется с конкретной checked rule "
        f"({qty} {unit_raw}). CONSISTENT ≠ physical execution proof и ≠ "
        f"промышленная физическая достоверность (demonstration rules). "
    )
    if state == ClaimedResultState.MANUFACTURED:
        expl += (
            "MANUFACTURED = claimed manufactured state, не доказанный факт "
            "изготовления; не installed, не accepted, не earned quantity. "
        )
    if state == ClaimedResultState.INSTALLED:
        expl += (
            "INSTALLED = claimed installed state, не инспекционно подтверждённый монтаж. "
        )
    if zero_finding_ok and qty == 0:
        expl += " Нулевой объём при положительных трудозатратах не объявлен нарушением."

    return _base_finding(
        check_identity=f"s03:{line.source_operation_identity}:{rule.rule_id}",
        line=line,
        claim=claim,
        check_type=PhysicalCheckType.QUANTITY_INTEGRITY,
        rule=rule,
        check_result=PhysicalCheckResult.CONSISTENT_WITH_CHECKED_RULE,
        measurability=meas,
        claimed_result_state=state,
        supporting_evidence=tuple(evidence),
        missing_information=(),
        professional_explanation=expl,
        clarification_request=None,
        boq_relationship_status=(
            BoqRelationshipStatus.OPERATION_NOT_AUTO_CONTRACT_QUANTITY
            if (claim and claim.boq_name)
            else BoqRelationshipStatus.NOT_CONTRACT_ACCEPTED
            if state == ClaimedResultState.MANUFACTURED
            else _boq_status(claim)
        ),
    )


def _eval_object_identity(
    line: OperationClassificationLine,
    claim: Optional[OperationLaborClaim],
    audit_input: ShiftAuditInput,
    rule: Optional[PhysicalIntegrityRule],
) -> PhysicalIntegrityFinding:
    state = _result_state_for(rule, line)
    meas = rule.measurability if rule else MeasurabilityClass.UNKNOWN
    obj = (claim.physical_object_hint if claim else None) or None
    bits = []
    if audit_input.project_code:
        bits.append(f"project={audit_input.project_code}")
    if audit_input.facility_building:
        bits.append(f"facility={audit_input.facility_building}")
    if claim and claim.boq_name:
        bits.append("boq_name_present")
    if obj:
        bits.append(f"physical_object_hint={obj}")
        return _base_finding(
            check_identity=f"s03:{line.source_operation_identity}:object",
            line=line,
            claim=claim,
            check_type=PhysicalCheckType.OBJECT_IDENTITY,
            rule=rule,
            check_result=PhysicalCheckResult.CONSISTENT_WITH_CHECKED_RULE,
            measurability=meas,
            claimed_result_state=state,
            supporting_evidence=tuple(bits)
            + ("SAME_DESCRIPTION_NE_SAME_PHYSICAL_OBJECT",),
            missing_information=(),
            professional_explanation=(
                "Указан physical_object_hint; свободный текст hint сам по себе не "
                "является полным доказательством идентичности объекта, но достаточный "
                "контекст для checked rule присутствует."
            ),
            clarification_request=None,
        )
    missing = ("physical_object_hint",)
    if not (claim and claim.boq_name) and not audit_input.facility_building:
        missing = ("physical_object_hint", "facility_or_system_or_boq_link")
    return _base_finding(
        check_identity=f"s03:{line.source_operation_identity}:object",
        line=line,
        claim=claim,
        check_type=PhysicalCheckType.OBJECT_IDENTITY,
        rule=rule,
        check_result=PhysicalCheckResult.INSUFFICIENT_CONTEXT,
        measurability=meas,
        claimed_result_state=state,
        supporting_evidence=tuple(bits) or ("no_object_identity_fields",),
        missing_information=missing,
        professional_explanation=(
            "Недостаточно идентификации физического объекта (система/участок/"
            "трубопровод/элемент). SAME DESCRIPTION ≠ SAME PHYSICAL OBJECT. "
            "Новые ID объектов не создаются."
        ),
        clarification_request="Укажите physical_object_hint / систему / участок.",
    )


def _eval_result_state_note(
    line: OperationClassificationLine,
    claim: Optional[OperationLaborClaim],
    rule: Optional[PhysicalIntegrityRule],
) -> PhysicalIntegrityFinding:
    state = _result_state_for(rule, line)
    meas = rule.measurability if rule else MeasurabilityClass.UNKNOWN
    evidence = [f"claimed_result_state={state.value}"]
    if state == ClaimedResultState.MANUFACTURED:
        evidence.extend(
            [
                "CLAIMED_MANUFACTURED_NE_PROVEN_FABRICATION",
                "MANUFACTURED_NE_INSTALLED",
                "INSTALLED_NE_CONTRACT_ACCEPTED",
                "OPERATION_QUANTITY_NE_CONTRACT_BOQ_QUANTITY",
                "PHYSICAL_PROGRESS_NE_EARNED_VALUE",
                "CONSISTENT_APPLIES_ONLY_TO_THIS_CHECKED_RULE",
            ]
        )
        expl = (
            "Claimed result state = MANUFACTURED (заявлено изготовление), не "
            "доказанный факт изготовления, не монтаж, не контрактная приёмка, "
            "не earned quantity."
        )
    elif state == ClaimedResultState.INSTALLED:
        evidence.extend(
            [
                "CLAIMED_INSTALLED_NE_INSPECTION_CONFIRMED",
                "INSTALLED_NE_CONTRACT_ACCEPTED",
                "PHYSICAL_PROGRESS_NE_EARNED_VALUE",
                "CONSISTENT_APPLIES_ONLY_TO_THIS_CHECKED_RULE",
            ]
        )
        expl = (
            "Claimed result state = INSTALLED (заявлен монтаж), не инспекционно "
            "подтверждённый монтаж и не contract accepted / earned value."
        )
    elif state == ClaimedResultState.PREPARED:
        expl = "Заявленное состояние — ПОДГОТОВЛЕНО; не самостоятельный договорной объём."
        evidence.append("prep_not_auto_contract_quantity")
    else:
        expl = "Состояние физического результата не выведено сверх checked rule."
    return _base_finding(
        check_identity=f"s03:{line.source_operation_identity}:state",
        line=line,
        claim=claim,
        check_type=PhysicalCheckType.RESULT_STATE,
        rule=rule,
        check_result=PhysicalCheckResult.CONSISTENT_WITH_CHECKED_RULE
        if rule
        else PhysicalCheckResult.NOT_EVALUATED,
        measurability=meas,
        claimed_result_state=state,
        supporting_evidence=tuple(evidence),
        missing_information=(),
        professional_explanation=expl,
        clarification_request=None,
        boq_relationship_status=(
            BoqRelationshipStatus.NOT_CONTRACT_ACCEPTED
            if state in {ClaimedResultState.MANUFACTURED, ClaimedResultState.INSTALLED}
            else _boq_status(claim)
        ),
    )


def _eval_duplicates(
    line: OperationClassificationLine,
    claim: Optional[OperationLaborClaim],
    audit_input: ShiftAuditInput,
    s10: ShiftOperationClassificationArtifact,
    prior: Sequence[PriorPhysicalClaimEvidence],
    rule: Optional[PhysicalIntegrityRule],
) -> PhysicalIntegrityFinding:
    state = _result_state_for(rule, line)
    meas = rule.measurability if rule else MeasurabilityClass.UNKNOWN
    ids = list(claim.source_record_ids) if claim else list(line.source_record_ids)
    # Proven: same source_record_id appears on multiple operations in this input
    id_counts: Counter[str] = Counter()
    for op in audit_input.operations:
        for rid in op.source_record_ids:
            if rid:
                id_counts[rid] += 1
    proven = [rid for rid in ids if id_counts.get(rid, 0) >= 2]
    if proven:
        return _base_finding(
            check_identity=f"s03:{line.source_operation_identity}:dup_record",
            line=line,
            claim=claim,
            check_type=PhysicalCheckType.DUPLICATE_CLAIM,
            rule=rule,
            check_result=PhysicalCheckResult.PROVEN_RECORD_DUPLICATE,
            measurability=meas,
            claimed_result_state=state,
            supporting_evidence=(
                "duplicate_source_record_ids:" + ",".join(proven),
                "within_single_audit_input_only",
                "NOT_CROSS_SNAPSHOT_DOUBLE_COUNTING_PROOF",
            ),
            missing_information=(),
            professional_explanation=(
                "Повтор идентичной source record identity внутри одного audit input. "
                "Тот же record ID в разных audit snapshots / повторный аудит "
                "неизменённой записи / новая версия записи НЕ являются автоматическим "
                "доказательством двойного учёта. Межсменное расследование не "
                "реализовано. Данные не изменяются."
            ),
            clarification_request="Проверьте дублирование исходной записи внутри текущего ввода.",
            duplicate_risk="PROVEN_SOURCE_RECORD_DUPLICATE_WITHIN_AUDIT_INPUT",
        )

    qty = claim.physical_quantity if claim else None
    unit = _norm_unit(claim.physical_unit if claim else None)
    obj = (claim.physical_object_hint if claim else None) or None
    code = line.operation_code_candidate
    # Possible duplicate: same code+qty+unit+object elsewhere (need object)
    if qty is None or unit is None or not code:
        return _base_finding(
            check_identity=f"s03:{line.source_operation_identity}:dup",
            line=line,
            claim=claim,
            check_type=PhysicalCheckType.DUPLICATE_CLAIM,
            rule=rule,
            check_result=PhysicalCheckResult.NOT_EVALUATED,
            measurability=meas,
            claimed_result_state=state,
            supporting_evidence=("insufficient_fields_for_duplicate_assessment",),
            missing_information=("quantity_unit_and_or_object_for_duplicate_check",),
            professional_explanation=(
                "Недостаточно данных для оценки дублирования физического результата. "
                "POSSIBLE DUPLICATE ≠ PROVEN DUPLICATE."
            ),
            clarification_request=None,
            duplicate_risk=None,
        )

    peers = []
    for other_line, other_claim in zip(s10.classifications, audit_input.operations):
        if other_line.source_operation_identity == line.source_operation_identity:
            continue
        if other_line.operation_code_candidate != code:
            continue
        if other_claim.physical_quantity != qty:
            continue
        if _norm_unit(other_claim.physical_unit) != unit:
            continue
        peers.append(other_claim)

    same_obj = [
        p for p in peers if obj and (p.physical_object_hint or "").strip() == obj
    ]
    diff_obj = [
        p
        for p in peers
        if (p.physical_object_hint or "").strip()
        and obj
        and (p.physical_object_hint or "").strip() != obj
    ]
    if diff_obj and not same_obj:
        return _base_finding(
            check_identity=f"s03:{line.source_operation_identity}:dup",
            line=line,
            claim=claim,
            check_type=PhysicalCheckType.DUPLICATE_CLAIM,
            rule=rule,
            check_result=PhysicalCheckResult.CONSISTENT_WITH_CHECKED_RULE,
            measurability=meas,
            claimed_result_state=state,
            supporting_evidence=(
                "same_quantity_on_different_objects_not_duplicate",
                f"object={obj}",
            ),
            missing_information=(),
            professional_explanation=(
                "Одинаковые объёмы на разных физических объектах не считаются дубликатами."
            ),
            clarification_request=None,
            duplicate_risk=None,
        )

    prior_hits = [
        p
        for p in prior
        if p.operation_code == code
        and p.physical_quantity == qty
        and _norm_unit(p.physical_unit) == unit
        and obj
        and (p.physical_object_hint or "").strip() == obj
    ]
    if same_obj or prior_hits:
        return _base_finding(
            check_identity=f"s03:{line.source_operation_identity}:dup",
            line=line,
            claim=claim,
            check_type=PhysicalCheckType.DUPLICATE_CLAIM,
            rule=rule,
            check_result=PhysicalCheckResult.POSSIBLE_DUPLICATE,
            measurability=meas,
            claimed_result_state=state,
            supporting_evidence=(
                f"matched_peers={len(same_obj)}",
                f"prior_hits={len(prior_hits)}",
                "POSSIBLE_DUPLICATE_NE_PROVEN_DUPLICATE",
            ),
            missing_information=("independent_verification_of_unique_physical_result",),
            professional_explanation=(
                "Возможен повторный учёт одного физического результата, но без "
                "достаточных данных это не объявляется доказанным дубликатом. "
                "Повтор операции может быть законным. Объёмы не корректируются."
            ),
            clarification_request="Подтвердите уникальность физического результата или законный повтор.",
            duplicate_risk="POSSIBLE_REPEATED_PHYSICAL_CLAIM",
        )

    return _base_finding(
        check_identity=f"s03:{line.source_operation_identity}:dup",
        line=line,
        claim=claim,
        check_type=PhysicalCheckType.DUPLICATE_CLAIM,
        rule=rule,
        check_result=PhysicalCheckResult.NOT_EVALUATED
        if not obj
        else PhysicalCheckResult.CONSISTENT_WITH_CHECKED_RULE,
        measurability=meas,
        claimed_result_state=state,
        supporting_evidence=(
            ("no_same_object_quantity_peer",)
            if obj
            else ("object_absent_duplicate_not_forced",)
        ),
        missing_information=(() if obj else ("physical_object_hint",)),
        professional_explanation=(
            "Признаков доказанного или вероятного дубликата при доступном контексте не выявлено."
            if obj
            else "Без идентичности объекта дубликат физического результата не выводится."
        ),
        clarification_request=None,
        duplicate_risk=None,
    )


def _eval_boq(
    line: OperationClassificationLine,
    claim: Optional[OperationLaborClaim],
    rule: Optional[PhysicalIntegrityRule],
) -> PhysicalIntegrityFinding:
    state = _result_state_for(rule, line)
    meas = rule.measurability if rule else MeasurabilityClass.UNKNOWN
    if claim and (claim.boq_name or "").strip():
        status = BoqRelationshipStatus.OPERATION_NOT_AUTO_CONTRACT_QUANTITY
        expl = (
            "Связь с договорной позицией заявлена текстом, но operation quantity "
            "не суммируется как contract BOQ / accepted / earned value автоматически. "
            "Промежуточные и конечные результаты не сливаются."
        )
        evidence = (
            f"boq_name={claim.boq_name[:80]}",
            "OPERATION_QUANTITY_NE_CONTRACT_BOQ_QUANTITY",
            "PHYSICAL_PROGRESS_NE_EARNED_VALUE",
            "NOT_AUTO_COMMERCIAL_RECOGNITION",
        )
        result = PhysicalCheckResult.CONSISTENT_WITH_CHECKED_RULE
    else:
        status = BoqRelationshipStatus.NO_BOQ_LINK
        expl = (
            "Подтверждённая связь с договорной позицией отсутствует; "
            "физический результат не объявляется договорным объёмом."
        )
        evidence = ("no_boq_link", "NOT_AUTO_CONTRACT_QUANTITY")
        result = PhysicalCheckResult.NOT_APPLICABLE
    if state == ClaimedResultState.MANUFACTURED:
        status = BoqRelationshipStatus.NOT_CONTRACT_ACCEPTED
        evidence = evidence + ("MANUFACTURED_NE_CONTRACT_ACCEPTED",)
        result = PhysicalCheckResult.CONSISTENT_WITH_CHECKED_RULE
        expl = (
            "Изготовленный результат не является автоматически договорным объёмом, "
            "earned quantity, earned value или выручкой."
        )
    return _base_finding(
        check_identity=f"s03:{line.source_operation_identity}:boq",
        line=line,
        claim=claim,
        check_type=PhysicalCheckType.BOQ_RELATIONSHIP,
        rule=rule,
        check_result=result,
        measurability=meas,
        claimed_result_state=state,
        supporting_evidence=evidence,
        missing_information=(() if claim and claim.boq_name else ("confirmed_boq_link",)),
        professional_explanation=expl,
        clarification_request=None,
        boq_relationship_status=status,
    )


def evaluate_s03(
    audit_input: ShiftAuditInput,
    s10: ShiftOperationClassificationArtifact,
    *,
    audit_id: Optional[str] = None,
    run_id: Optional[str] = None,
    prior_physical_claims: Sequence[PriorPhysicalClaimEvidence] = (),
) -> ShiftPhysicalIntegrityArtifact:
    findings: list[PhysicalIntegrityFinding] = []

    for line in s10.classifications:
        claim = _claim_for_line(audit_input, line)
        gated = _gate_from_classification(line, claim)
        if gated is not None:
            findings.append(gated)
            continue

        rule = rule_for_operation(line.operation_code_candidate)
        if rule is None:
            # Still run universal negative qty + object/dup/boq lightly
            qty = claim.physical_quantity if claim else line.physical_quantity
            if qty is not None and qty < 0:
                univ = next(
                    r
                    for r in INSULATION_PHYSICAL_RULES
                    if r.rule_id == "UNIV.QTY.NON_NEGATIVE"
                )
                findings.append(
                    _base_finding(
                        check_identity=f"s03:{line.source_operation_identity}:neg",
                        line=line,
                        claim=claim,
                        check_type=PhysicalCheckType.QUANTITY_INTEGRITY,
                        rule=univ,
                        check_result=PhysicalCheckResult.INVALID_QUANTITY,
                        measurability=MeasurabilityClass.UNKNOWN,
                        claimed_result_state=ClaimedResultState.UNKNOWN,
                        supporting_evidence=(f"quantity={qty}",),
                        missing_information=(),
                        professional_explanation="Отрицательное физическое количество недопустимо.",
                        clarification_request="Исправьте количество.",
                    )
                )
            findings.append(
                _base_finding(
                    check_identity=f"s03:{line.source_operation_identity}:no_rule",
                    line=line,
                    claim=claim,
                    check_type=PhysicalCheckType.CONTEXT_SUFFICIENCY,
                    rule=None,
                    check_result=PhysicalCheckResult.INSUFFICIENT_CONTEXT,
                    measurability=MeasurabilityClass.UNKNOWN,
                    claimed_result_state=ClaimedResultState.UNKNOWN,
                    supporting_evidence=(
                        f"operation_code={line.operation_code_candidate}",
                    ),
                    missing_information=("applicable_physical_integrity_rule",),
                    professional_explanation=(
                        "Нет применимого physical integrity rule в working pack "
                        "для этой операции (bonding/tape/cutting и т.п. могут не "
                        "требовать объёма — уточните правило)."
                    ),
                    clarification_request="Добавьте правило измеримости с provenance.",
                )
            )
            findings.append(_eval_object_identity(line, claim, audit_input, None))
            findings.append(_eval_duplicates(line, claim, audit_input, s10, prior_physical_claims, None))
            findings.append(_eval_boq(line, claim, None))
            continue

        findings.append(_eval_quantity_and_unit(rule, line, claim))
        findings.append(_eval_object_identity(line, claim, audit_input, rule))
        findings.append(_eval_result_state_note(line, claim, rule))
        findings.append(
            _eval_duplicates(line, claim, audit_input, s10, prior_physical_claims, rule)
        )
        findings.append(_eval_boq(line, claim, rule))

    demo_n = sum(1 for f in findings if f.demonstration_rule)
    observations = [
        "S03 = deterministic physical integrity skill (no LLM in this increment).",
        "LABOR ≠ PHYSICAL RESULT.",
        "CLAIMED RESULT ≠ VERIFIED RESULT.",
        "MANUFACTURED (claimed) ≠ proven fabrication ≠ INSTALLED ≠ CONTRACT ACCEPTED.",
        "INSTALLED (claimed) ≠ inspection-confirmed install.",
        "OPERATION QUANTITY ≠ CONTRACT BOQ QUANTITY.",
        "PHYSICAL PROGRESS ≠ EARNED VALUE.",
        "MISSING EVIDENCE ≠ PROVEN VIOLATION.",
        "SAME DESCRIPTION ≠ SAME PHYSICAL OBJECT.",
        "POSSIBLE DUPLICATE ≠ PROVEN DUPLICATE.",
        "quantity not required by current rule ≠ operation not quantitatively measurable.",
        "Missing geometry ≠ proven unit incompatibility; no automatic unit conversion.",
        "Non-negative quantity rule: ordinary execution claim only (not storno/correction).",
        "PROVEN_RECORD_DUPLICATE is within a single audit input only.",
        "CONSISTENT applies only to the specific checked rule.",
        "No automatic quantity correction / commercial recognition / payroll.",
        "S02/S03 demonstration rules do NOT prove industrial physical validity.",
        f"Ruleset: {INSULATION_PHYSICAL_RULESET_VERSION}.",
        f"Engine: {S03_RULES_VERSION}.",
        "S03_ENGINE_IMPLEMENTED · DEMONSTRATION_PHYSICAL_RULES_PROVEN · "
        "PRODUCTION_PHYSICAL_KNOWLEDGE_NOT_READY · PHYSICAL_INSPECTION_NOT_PROVEN.",
        f"demonstration_findings={demo_n}.",
    ]

    counts: dict[str, int] = {}
    for f in findings:
        counts[f.check_result.value] = counts.get(f.check_result.value, 0) + 1

    summary = [
        "PSAA S03 — Physical Integrity (deterministic)",
        f"Проект: {audit_input.project_code} date={audit_input.work_date} crew={audit_input.crew_id}",
        "Managerial acceptance: NOT_IN_SCOPE",
        "Physical validation scope: CLAIMED_RESULT_CHECKS_ONLY",
        "Readiness: S03_ENGINE_IMPLEMENTED | DEMONSTRATION_PHYSICAL_RULES_PROVEN | "
        "PRODUCTION_PHYSICAL_KNOWLEDGE_NOT_READY | PHYSICAL_INSPECTION_NOT_PROVEN",
        "Status counts: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
    ]
    for f in findings:
        if f.check_type in {
            PhysicalCheckType.QUANTITY_INTEGRITY,
            PhysicalCheckType.UNIT_INTEGRITY,
            PhysicalCheckType.COMPOSITE_LIMITATION,
            PhysicalCheckType.CONTEXT_SUFFICIENCY,
        }:
            summary.append(
                f"- «{f.original_operation_text}» | qty={f.original_claimed_quantity} "
                f"{f.original_unit or ''} | {f.claimed_result_state.value} | "
                f"{f.check_result.value} | demo={f.demonstration_rule}"
            )

    return ShiftPhysicalIntegrityArtifact(
        schema_version=S03_ARTIFACT_SCHEMA_VERSION,
        rules_version=S03_RULES_VERSION,
        physical_ruleset_version=INSULATION_PHYSICAL_RULESET_VERSION,
        audit_id=audit_id or s10.audit_id or str(uuid.uuid4()),
        agent_code=AGENT_CODE,
        agent_version=AGENT_VERSION,
        run_id=run_id,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        project_code=audit_input.project_code,
        work_date=audit_input.work_date,
        crew_id=audit_input.crew_id,
        evaluation_domain="insulation_demonstration_physical_rules",
        findings=tuple(findings),
        observations=tuple(observations),
        managerial_acceptance_status="NOT_IN_SCOPE",
        physical_validation_scope="CLAIMED_RESULT_CHECKS_ONLY_NOT_INSPECTION",
        human_readable_summary="\n".join(summary),
        s03_engine_status="S03_ENGINE_IMPLEMENTED",
        demonstration_rules_status="DEMONSTRATION_PHYSICAL_RULES_PROVEN",
        production_physical_knowledge_status="PRODUCTION_PHYSICAL_KNOWLEDGE_NOT_READY",
        physical_inspection_status="PHYSICAL_INSPECTION_NOT_PROVEN",
    )
