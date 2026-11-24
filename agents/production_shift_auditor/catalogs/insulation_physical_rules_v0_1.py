"""Working physical integrity rules for PSAA S03 — insulation domain.

Universal numeric checks are marked UNIVERSAL_NUMERIC.
Measurability / unit expectations for insulation ops are DEMONSTRATION_RULE
unless a future revision cites approved engineering sources.

NOT a production metrology standard. NOT an Operation Registry.
NOT physical inspection proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agents.production_shift_auditor.s03_contracts import (
    ClaimedResultState,
    MeasurabilityClass,
    PhysicalCheckType,
    PhysicalSourceAuthority,
)

INSULATION_PHYSICAL_RULESET_VERSION = "psaa.s03.insulation_physical_rules.v0.1"

_DEMO = PhysicalSourceAuthority.DEMONSTRATION_RULE
_UNIV = PhysicalSourceAuthority.UNIVERSAL_NUMERIC
_DEMO_SRC = (
    "DEMONSTRATION / working example for PSAA-05 skill mechanism — "
    "not an approved production metrology standard."
)
_UNIV_SRC = "Universal numeric sanity check (negative quantity, etc.)."


@dataclass(frozen=True)
class PhysicalIntegrityRule:
    rule_id: str
    check_type: PhysicalCheckType
    operation_codes: tuple[str, ...]
    requirement_text: str
    measurability: MeasurabilityClass
    expected_result_state: ClaimedResultState
    allowed_units: tuple[str, ...]
    source_citation: str
    source_authority: PhysicalSourceAuthority
    revision: str
    application_limits: tuple[str, ...]
    requires_quantity: bool = False
    allows_zero_quantity: bool = True
    discrete_integer_quantity: bool = False


_LIMITS = (
    "CLAIMED RESULT ≠ VERIFIED RESULT.",
    "MANUFACTURED ≠ INSTALLED ≠ CONTRACT ACCEPTED.",
    "OPERATION QUANTITY ≠ CONTRACT BOQ QUANTITY ≠ EARNED VALUE.",
    "CONSISTENT_WITH_CHECKED_RULE ≠ physical execution proof.",
)


INSULATION_PHYSICAL_RULES: tuple[PhysicalIntegrityRule, ...] = (
    PhysicalIntegrityRule(
        rule_id="UNIV.QTY.NON_NEGATIVE",
        check_type=PhysicalCheckType.QUANTITY_INTEGRITY,
        operation_codes=(),  # applies to any measurable claim with a quantity
        requirement_text="Заявленное физическое количество не может быть отрицательным.",
        measurability=MeasurabilityClass.MEASURABILITY_UNKNOWN,
        expected_result_state=ClaimedResultState.UNKNOWN,
        allowed_units=(),
        source_citation=_UNIV_SRC,
        source_authority=_UNIV,
        revision="v0.1",
        application_limits=(
            "Applies to ordinary execution claims only.",
            "Does NOT cover storno / reversing / correction accounting events "
            "(future correction workflow — not implemented).",
            "Universal numeric only — not a technology standard.",
        ),
        requires_quantity=False,
        allows_zero_quantity=True,
    ),
    PhysicalIntegrityRule(
        rule_id="DEMO.INS.PHY.FITTING_FABRICATION_PCS",
        check_type=PhysicalCheckType.QUANTITY_INTEGRITY,
        operation_codes=("INS.FITTING_FABRICATION",),
        requirement_text=(
            "Изготовление фасонных изделий — измеримый заявленный результат в шт.; "
            "заявленное изготовление ≠ монтаж ≠ договорная приёмка."
        ),
        measurability=MeasurabilityClass.MEASURABLE_RESULT_EXPECTED,
        expected_result_state=ClaimedResultState.MANUFACTURED,
        allowed_units=("шт", "шт.", "pcs", "pc"),
        source_citation=_DEMO_SRC,
        source_authority=_DEMO,
        revision="v0.1",
        application_limits=_LIMITS,
        requires_quantity=True,
        allows_zero_quantity=True,
        discrete_integer_quantity=True,
    ),
    PhysicalIntegrityRule(
        rule_id="DEMO.INS.PHY.STRAIGHT_INSTALL_LENGTH",
        check_type=PhysicalCheckType.UNIT_INTEGRITY,
        operation_codes=("INS.STRAIGHT_INSTALL",),
        requirement_text=(
            "Монтаж прямых участков — ожидаемая единица длины (м / м.п.); "
            "перевод в м² без геометрии запрещён."
        ),
        measurability=MeasurabilityClass.MEASURABLE_RESULT_EXPECTED,
        expected_result_state=ClaimedResultState.INSTALLED,
        allowed_units=("м", "м.", "мп", "м.п", "м.п.", "m", "lm"),
        source_citation=_DEMO_SRC,
        source_authority=_DEMO,
        revision="v0.1",
        application_limits=_LIMITS + ("No automatic m→m² conversion.",),
        requires_quantity=True,
        allows_zero_quantity=True,
    ),
    PhysicalIntegrityRule(
        rule_id="DEMO.INS.PHY.CLADDING_AREA",
        check_type=PhysicalCheckType.UNIT_INTEGRITY,
        operation_codes=("INS.CLADDING",),
        requirement_text=(
            "Монтаж защитного покровного слоя — ожидаемая единица площади (м²); "
            "штуки/погонные метры не подставляются без инженерного основания."
        ),
        measurability=MeasurabilityClass.MEASURABLE_RESULT_EXPECTED,
        expected_result_state=ClaimedResultState.INSTALLED,
        allowed_units=("м2", "м²", "m2", "sqm"),
        source_citation=_DEMO_SRC,
        source_authority=_DEMO,
        revision="v0.1",
        application_limits=_LIMITS,
        requires_quantity=True,
        allows_zero_quantity=True,
    ),
    PhysicalIntegrityRule(
        rule_id="DEMO.INS.PHY.PREP_NO_VOLUME_REQUIRED",
        check_type=PhysicalCheckType.QUANTITY_INTEGRITY,
        operation_codes=(
            "INS.SURFACE_PREP",
            "INS.MARKING",
            "INS.ADHESIVE_PREP",
            "INS.ADHESIVE_APPLY",
        ),
        requirement_text=(
            "Подготовительные операции не требуют обязательного физического объёма; "
            "отсутствие количества ≠ автоматическое нарушение."
        ),
        measurability=MeasurabilityClass.QUANTITY_NOT_REQUIRED_BY_CURRENT_RULE,
        expected_result_state=ClaimedResultState.PREPARED,
        allowed_units=(),
        source_citation=_DEMO_SRC,
        source_authority=_DEMO,
        revision="v0.1",
        application_limits=_LIMITS
        + (
            "Labor minutes are not physical volume.",
            "quantity not required by CURRENT rule ≠ operation not quantitatively measurable.",
            "Future approved rules may measure surface prep in m², etc.",
        ),
        requires_quantity=False,
    ),
    PhysicalIntegrityRule(
        rule_id="DEMO.INS.PHY.AUX_NO_VOLUME_REQUIRED",
        check_type=PhysicalCheckType.QUANTITY_INTEGRITY,
        operation_codes=("INS.AUX_TAPE_FIX", "INS.AUX_CLEANUP", "INS.QA"),
        requirement_text=(
            "Вспомогательные / QA операции не требуют обязательного физического объёма "
            "по текущему demonstration rule."
        ),
        measurability=MeasurabilityClass.QUANTITY_NOT_REQUIRED_BY_CURRENT_RULE,
        expected_result_state=ClaimedResultState.PROCESSED,
        allowed_units=(),
        source_citation=_DEMO_SRC,
        source_authority=_DEMO,
        revision="v0.1",
        application_limits=_LIMITS
        + (
            "quantity not required by CURRENT rule ≠ permanently non-measurable.",
        ),
        requires_quantity=False,
    ),
    PhysicalIntegrityRule(
        rule_id="DEMO.INS.PHY.PROCESS_NO_VOLUME_REQUIRED",
        check_type=PhysicalCheckType.QUANTITY_INTEGRITY,
        operation_codes=(
            "INS.CUTTING",
            "INS.SEAM_BONDING",
            "INS.TAPE",
            "INS.FITTING_INSTALL",
        ),
        requirement_text=(
            "Отдельные технологические процессные операции могут не нести "
            "самостоятельный договорной объём по текущему rule; "
            "склеивание швов в будущем может измеряться в метрах при наличии "
            "утверждённого правила."
        ),
        measurability=MeasurabilityClass.QUANTITY_NOT_REQUIRED_BY_CURRENT_RULE,
        expected_result_state=ClaimedResultState.PROCESSED,
        allowed_units=(),
        source_citation=_DEMO_SRC,
        source_authority=_DEMO,
        revision="v0.1",
        application_limits=_LIMITS
        + (
            "Not every technological operation is a contract BOQ quantity.",
            "Absence of approved measurement rule does not block future per-op economics.",
        ),
        requires_quantity=False,
    ),
    PhysicalIntegrityRule(
        rule_id="DEMO.INS.PHY.NO_UNIT_CONVERSION_WITHOUT_GEOMETRY",
        check_type=PhysicalCheckType.UNIT_INTEGRITY,
        operation_codes=(),
        requirement_text=(
            "Запрещено преобразовывать погонные метры в м² (и шт в м/м²) без "
            "подтверждённых геометрических параметров и формулы."
        ),
        measurability=MeasurabilityClass.UNKNOWN,
        expected_result_state=ClaimedResultState.UNKNOWN,
        allowed_units=(),
        source_citation=_DEMO_SRC,
        source_authority=_DEMO,
        revision="v0.1",
        application_limits=_LIMITS,
    ),
)


def rule_for_operation(operation_code: Optional[str]) -> Optional[PhysicalIntegrityRule]:
    if not operation_code:
        return None
    for rule in INSULATION_PHYSICAL_RULES:
        if operation_code in rule.operation_codes and rule.rule_id.startswith("DEMO.INS.PHY."):
            if rule.rule_id.endswith("NO_UNIT_CONVERSION_WITHOUT_GEOMETRY"):
                continue
            return rule
    return None
