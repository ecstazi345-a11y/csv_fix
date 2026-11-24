"""Working technological rules for PSAA S02 — insulation domain only.

ALL rules in this pack are DEMONSTRATION_RULE unless a future revision
explicitly cites an approved tech card / manufacturer instruction / project
requirement with provenance.

NOT an approved technology of production.
NOT a MEP-wide Engineering Knowledge Graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from agents.production_shift_auditor.s02_contracts import (
    SourceAuthority,
    TechCheckType,
)

INSULATION_TECH_RULESET_VERSION = "psaa.s02.insulation_tech_rules.v0.1"


@dataclass(frozen=True)
class TechnologicalRule:
    rule_id: str
    work_category: str
    operation_codes: tuple[str, ...]
    requirement_text: str
    applicability_conditions: tuple[str, ...]
    required_inputs: tuple[str, ...]
    check_type: TechCheckType
    source_citation: str
    source_authority: SourceAuthority
    revision: str
    application_limits: tuple[str, ...]
    # Optional structured helpers for deterministic evaluator
    prerequisite_codes: tuple[str, ...] = ()
    material_include_tokens: tuple[str, ...] = ()
    material_exclude_tokens: tuple[str, ...] = ()
    discipline_include_tokens: tuple[str, ...] = ()
    discipline_exclude_tokens: tuple[str, ...] = ()
    sequence_before_code: Optional[str] = None
    sequence_after_code: Optional[str] = None


# Explicit: every rule below is demonstration-only for skill-mechanism proof.
_DEMO = SourceAuthority.DEMONSTRATION_RULE
_DEMO_SOURCE = (
    "DEMONSTRATION ONLY — no approved insulation tech card / manufacturer "
    "instruction was available in-repo at PSAA-04 implementation; rule exists "
    "solely to exercise S02 deterministic checks."
)
_LIMITS = (
    "Not production technology.",
    "Not approved Operation Registry content.",
    "Do not treat CONSISTENT_WITH_CHECKED_RULE as full technological validation of the shift.",
)


INSULATION_TECH_RULES: tuple[TechnologicalRule, ...] = (
    TechnologicalRule(
        rule_id="DEMO.INS.OP_APP.PIPING_INSULATION",
        work_category="insulation",
        operation_codes=(
            "INS.SURFACE_PREP",
            "INS.MARKING",
            "INS.CUTTING",
            "INS.FITTING_FABRICATION",
            "INS.STRAIGHT_INSTALL",
            "INS.FITTING_INSTALL",
            "INS.ADHESIVE_PREP",
            "INS.ADHESIVE_APPLY",
            "INS.SEAM_BONDING",
            "INS.TAPE",
            "INS.CLADDING",
            "INS.AUX_TAPE_FIX",
            "INS.AUX_CLEANUP",
            "INS.QA",
        ),
        requirement_text=(
            "Классифицированная операция теплоизоляции применима к заявленному "
            "виду работ / дисциплине изоляции трубопроводов или оборудования."
        ),
        applicability_conditions=(
            "operation_code in insulation working catalog",
            "discipline or work_kind available for comparison",
        ),
        required_inputs=("classified_operation_code", "construction_discipline|work_kind_hint"),
        check_type=TechCheckType.OPERATION_APPLICABILITY,
        source_citation=_DEMO_SOURCE,
        source_authority=_DEMO,
        revision="v0.1",
        application_limits=_LIMITS,
        discipline_include_tokens=("изоляц", "теплоизоляц", "insulation"),
        discipline_exclude_tokens=("сварк", "бетон", "опалубк", "welding"),
    ),
    TechnologicalRule(
        rule_id="DEMO.INS.MAT.CLADDING_SYSTEM",
        work_category="cladding",
        operation_codes=("INS.CLADDING",),
        requirement_text=(
            "Монтаж защитного покровного слоя (в т.ч. AL CLAD AD) требует "
            "указания покровной / cladding-системы; технология минераловатной "
            "изоляции без покровного слоя не переносится автоматически."
        ),
        applicability_conditions=(
            "classified_operation_code=INS.CLADDING",
            "material or covering context should be inspected",
        ),
        required_inputs=("material_hint|boq_name|physical_volume_label|operation_text",),
        check_type=TechCheckType.MATERIAL_APPLICABILITY,
        source_citation=_DEMO_SOURCE,
        source_authority=_DEMO,
        revision="v0.1",
        application_limits=_LIMITS
        + ("Does not prove correct cladding product selection.",),
        # Avoid short stem «покрыт» — matches «без покрытия» falsely.
        material_include_tokens=("al clad", "alclad", "покровн", "покровного", "clad"),
        material_exclude_tokens=("rockwool", "минват", "минераловат", "цилиндры"),
    ),
    TechnologicalRule(
        rule_id="DEMO.INS.MAT.CUTTING_ELASTOMER",
        work_category="fabrication",
        operation_codes=("INS.CUTTING",),
        requirement_text=(
            "Правило раскроя эластомерной теплоизоляции (каучук / K-FLEX и аналоги) "
            "не переносится на минераловатные системы без отдельного источника."
        ),
        applicability_conditions=(
            "classified_operation_code=INS.CUTTING",
            "material context determines applicability of elastomer cutting rule",
        ),
        required_inputs=("material_hint|boq_name|operation_text",),
        check_type=TechCheckType.MATERIAL_APPLICABILITY,
        source_citation=_DEMO_SOURCE,
        source_authority=_DEMO,
        revision="v0.1",
        application_limits=_LIMITS,
        material_include_tokens=("каучук", "k-flex", "kflex", "эластомер", "elastomer"),
        material_exclude_tokens=("rockwool", "минват", "минераловат", "цилиндры"),
    ),
    TechnologicalRule(
        rule_id="DEMO.INS.PREREQ.SEAM_AFTER_BONDING_CONTEXT",
        work_category="bonding",
        operation_codes=("INS.SEAM_BONDING",),
        requirement_text=(
            "Для проверки склеивания швов желателен подтверждённый контекст "
            "предшествующего монтажа изоляции и/или подготовки/нанесения клея. "
            "Отсутствие записи ≠ доказательство невыполнения."
        ),
        applicability_conditions=(
            "classified_operation_code=INS.SEAM_BONDING",
            "prior evidence may come from current or prior shifts / other crews",
        ),
        required_inputs=("classified_operation_code", "current_or_prior_operation_evidence"),
        check_type=TechCheckType.PREREQUISITE,
        source_citation=_DEMO_SOURCE,
        source_authority=_DEMO,
        revision="v0.1",
        application_limits=_LIMITS
        + (
            "Absence of prerequisite evidence → INSUFFICIENT_CONTEXT, never PROVEN_CONTRADICTION.",
            "Prerequisites may be satisfied in another shift or by another crew.",
            "Same-shift presence without shared physical_object_hint is NOT sufficient.",
            "Adhesive/install on another pipe/segment/equipment does not satisfy this check.",
        ),
        prerequisite_codes=(
            "INS.STRAIGHT_INSTALL",
            "INS.FITTING_INSTALL",
            "INS.ADHESIVE_PREP",
            "INS.ADHESIVE_APPLY",
        ),
    ),
    TechnologicalRule(
        rule_id="DEMO.INS.SEQ.SURFACE_BEFORE_STRAIGHT_SAME_OBJECT",
        work_category="installation",
        operation_codes=("INS.STRAIGHT_INSTALL",),
        requirement_text=(
            "При идентичности физического объекта и наличии подтверждённых "
            "временных маркеров исполнения подготовка поверхности должна "
            "предшествовать монтажу прямых участков. Порядок строк отчёта "
            "не является хронологией."
        ),
        applicability_conditions=(
            "same non-empty physical_object_hint on both operations",
            "explicit execution_event_time markers required",
            "row order must not be used as chronology",
        ),
        required_inputs=(
            "physical_object_hint",
            "execution_event_time on both related claims",
        ),
        check_type=TechCheckType.SEQUENCE,
        source_citation=_DEMO_SOURCE,
        source_authority=_DEMO,
        revision="v0.1",
        application_limits=_LIMITS
        + (
            "Without object identity and temporal markers → NOT_EVALUATED / INSUFFICIENT_CONTEXT.",
            "Parallel routes and multi-object work remain allowed.",
        ),
        sequence_before_code="INS.SURFACE_PREP",
        sequence_after_code="INS.STRAIGHT_INSTALL",
    ),
)
