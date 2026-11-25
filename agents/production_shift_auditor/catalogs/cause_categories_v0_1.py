"""Demonstration cause-category catalog for PSAA S07.

NOT an approved production causality knowledge base.
Select only professionally relevant hypotheses — do not emit all categories
for every signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


CAUSE_CATALOG_VERSION = "psaa.s07.cause_categories.v0.1"
CAUSE_CATALOG_AUTHORITY = "DEMONSTRATION_CAUSE_CATALOG"


class CauseCategory(str, Enum):
    ENGINEERING_PHYSICAL_COMPLEXITY = "A_ENGINEERING_PHYSICAL_COMPLEXITY"
    TECHNOLOGY_AND_MATERIAL = "B_TECHNOLOGY_AND_MATERIAL"
    FRONT_READINESS_ORGANIZATIONAL = "C_FRONT_READINESS_ORGANIZATIONAL"
    MATERIAL_AND_TOOL_AVAILABILITY = "D_MATERIAL_AND_TOOL_AVAILABILITY"
    REWORK_AND_QUALITY = "E_REWORK_AND_QUALITY"
    LABOR_AND_EXECUTION_CONDITIONS = "F_LABOR_AND_EXECUTION_CONDITIONS"
    SOURCE_DATA_AND_REPORTING_QUALITY = "G_SOURCE_DATA_AND_REPORTING_QUALITY"
    REFERENCE_AND_COMPARISON_LIMITATIONS = "H_REFERENCE_AND_COMPARISON_LIMITATIONS"


@dataclass(frozen=True)
class CauseCategoryEntry:
    category: CauseCategory
    title: str
    example_causes: tuple[str, ...]
    typical_clarification_role: str
    notes: tuple[str, ...]


CAUSE_CATEGORY_CATALOG: tuple[CauseCategoryEntry, ...] = (
    CauseCategoryEntry(
        category=CauseCategory.ENGINEERING_PHYSICAL_COMPLEXITY,
        title="Engineering and physical complexity",
        example_causes=(
            "geometry",
            "dimensions",
            "elevation",
            "non_standard_components",
            "physical_accessibility",
            "system_complexity",
        ),
        typical_clarification_role="PTO",
        notes=("demonstration_only", "not_approved_production_causality_kb"),
    ),
    CauseCategoryEntry(
        category=CauseCategory.TECHNOLOGY_AND_MATERIAL,
        title="Technology and material",
        example_causes=(
            "different_material",
            "thickness",
            "fabrication_method",
            "installation_technology",
            "technological_sequence",
        ),
        typical_clarification_role="PTO",
        notes=("demonstration_only",),
    ),
    CauseCategoryEntry(
        category=CauseCategory.FRONT_READINESS_ORGANIZATIONAL,
        title="Front readiness and organizational constraints",
        example_causes=(
            "unavailable_work_front",
            "missing_admission",
            "restricted_access",
            "interference_with_other_contractors",
            "incomplete_predecessor_works",
        ),
        typical_clarification_role="SITE_SUPERVISOR",
        notes=("demonstration_only", "not_auto_emitted_without_relevance"),
    ),
    CauseCategoryEntry(
        category=CauseCategory.MATERIAL_AND_TOOL_AVAILABILITY,
        title="Material and tool availability",
        example_causes=(
            "material_shortage",
            "incorrect_material",
            "delayed_issue",
            "unavailable_tool",
            "equipment_limitations",
        ),
        typical_clarification_role="MTO",
        notes=("demonstration_only", "delay_ne_full_causal_attribution"),
    ),
    CauseCategoryEntry(
        category=CauseCategory.REWORK_AND_QUALITY,
        title="Rework and quality",
        example_causes=(
            "defect_correction",
            "repeated_fabrication",
            "repeated_installation",
            "damage",
            "rd_revision_related_rework",
        ),
        typical_clarification_role="FOREMAN",
        notes=("demonstration_only", "rework_hypothesis_ne_proven_rework"),
    ),
    CauseCategoryEntry(
        category=CauseCategory.LABOR_AND_EXECUTION_CONDITIONS,
        title="Labor and execution conditions",
        example_causes=(
            "allocation_differences",
            "crew_composition",
            "working_conditions",
            "interruptions",
            "productive_vs_elapsed_uncertainty",
        ),
        typical_clarification_role="SITE_SUPERVISOR",
        notes=("demonstration_only",),
    ),
    CauseCategoryEntry(
        category=CauseCategory.SOURCE_DATA_AND_REPORTING_QUALITY,
        title="Source data and reporting quality",
        example_causes=(
            "operation_aggregation",
            "missing_quantity",
            "incorrect_unit",
            "labor_semantics_ambiguity",
            "repeated_source_versions",
            "reporting_precision",
            "incomplete_physical_context",
        ),
        typical_clarification_role="FOREMAN",
        notes=(
            "demonstration_only",
            "DATA_QUALITY_PROBLEM_NE_PRODUCTION_INEFFICIENCY",
        ),
    ),
    CauseCategoryEntry(
        category=CauseCategory.REFERENCE_AND_COMPARISON_LIMITATIONS,
        title="Reference and comparison limitations",
        example_causes=(
            "incompatible_historical_observations",
            "unsuitable_benchmark",
            "insufficient_reference_population",
            "different_technological_conditions",
            "incompatible_cost_rates",
        ),
        typical_clarification_role="PTO",
        notes=(
            "demonstration_only",
            "MISSING_HISTORY_NE_NORMAL_PERFORMANCE",
        ),
    ),
)


def catalog_entry(category: CauseCategory) -> CauseCategoryEntry:
    for e in CAUSE_CATEGORY_CATALOG:
        if e.category == category:
            return e
    raise KeyError(category)
