"""
Constructor Runtime v0.1 Increment 4 — LaborNormResolver capability.

Shared deterministic service. Not a professional agent.
Does not invent norms. Does not drop physical candidates.
Does not call economics tools, GESN, LLM, SQL, Streamlit, or writes.

Canonical numeric: labor hours per physical unit, finite and > 0.
Identity: CandidateRecord.candidate_id only — never BOQ-code join.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, replace
from typing import Any, Optional, Sequence

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_PROVISIONAL,
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
    CandidatePackage,
    CandidateRecord,
    LaborNormSummary,
)

SCHEMA_VERSION = "1.0"

SOURCE_PROJECT_HISTORY = "PROJECT_HISTORY"
SOURCE_COMPANY_HISTORY = "COMPANY_HISTORY"
SOURCE_OFFICIAL_NORMATIVE = "OFFICIAL_NORMATIVE"
SOURCE_TECHNOLOGICAL_STANDARD = "TECHNOLOGICAL_STANDARD"
SOURCE_VENDOR = "VENDOR"
SOURCE_INDUSTRY_BENCHMARK = "INDUSTRY_BENCHMARK"
SOURCE_EXPERT_APPROVED = "EXPERT_APPROVED"

SOURCE_TYPES = frozenset(
    {
        SOURCE_PROJECT_HISTORY,
        SOURCE_COMPANY_HISTORY,
        SOURCE_OFFICIAL_NORMATIVE,
        SOURCE_TECHNOLOGICAL_STANDARD,
        SOURCE_VENDOR,
        SOURCE_INDUSTRY_BENCHMARK,
        SOURCE_EXPERT_APPROVED,
    }
)

HISTORY_SOURCES = frozenset({SOURCE_PROJECT_HISTORY, SOURCE_COMPANY_HISTORY})
BENCHMARK_SOURCES = frozenset(
    {
        SOURCE_OFFICIAL_NORMATIVE,
        SOURCE_TECHNOLOGICAL_STANDARD,
        SOURCE_VENDOR,
        SOURCE_INDUSTRY_BENCHMARK,
    }
)

# Lower rank number = higher priority. TECHNOLOGICAL_STANDARD and VENDOR share level 4.
SOURCE_RANK = {
    SOURCE_PROJECT_HISTORY: 1,
    SOURCE_COMPANY_HISTORY: 2,
    SOURCE_OFFICIAL_NORMATIVE: 3,
    SOURCE_TECHNOLOGICAL_STANDARD: 4,
    SOURCE_VENDOR: 4,
    SOURCE_INDUSTRY_BENCHMARK: 5,
    SOURCE_EXPERT_APPROVED: 6,
}

BASIS_OBSERVED_PRODUCTIVITY = "OBSERVED_PRODUCTIVITY"
BASIS_NORMATIVE_BENCHMARK = "NORMATIVE_BENCHMARK"
BASIS_TECHNOLOGICAL_STANDARD = "TECHNOLOGICAL_STANDARD"
BASIS_INDUSTRY_BENCHMARK = "INDUSTRY_BENCHMARK"
BASIS_EXPERT_APPROVED = "EXPERT_APPROVED"

HOURS_VALIDATED_PRODUCTIVE_DIRECT = "VALIDATED_PRODUCTIVE_DIRECT"
HOURS_PAID_NONPRODUCTIVE = "PAID_NONPRODUCTIVE"
HOURS_PAID_WITHOUT_EXECUTED_QUANTITY = "PAID_WITHOUT_EXECUTED_QUANTITY"
HOURS_UNVALIDATED = "UNVALIDATED"
HOURS_NOT_APPLICABLE = "NOT_APPLICABLE"

NONPRODUCTIVE_HOURS = frozenset(
    {
        HOURS_PAID_NONPRODUCTIVE,
        HOURS_PAID_WITHOUT_EXECUTED_QUANTITY,
        HOURS_UNVALIDATED,
        "IDLE",
        "WAITING",
        "TRAINING",
        "NONPRODUCTIVE_PAID",
    }
)

PLANNING_STATUSES = frozenset({LABOR_VALIDATED, LABOR_PROVISIONAL})

REASON_NO_ADMISSIBLE_EVIDENCE = "NO_ADMISSIBLE_EVIDENCE"
REASON_AMBIGUOUS_LABOR_NORM_EVIDENCE = "AMBIGUOUS_LABOR_NORM_EVIDENCE"
REASON_SELECTED_BY_SOURCE_HIERARCHY = "SELECTED_BY_SOURCE_HIERARCHY"
REASON_DUPLICATE_EVIDENCE_DEDUPLICATED = "DUPLICATE_EVIDENCE_DEDUPLICATED"

CODE_DATA_CONTRACT_BLOCKER = "DATA_CONTRACT_BLOCKER"
CODE_REJECTED_MISSING_NORM = "REJECTED_MISSING_NORM"
CODE_REJECTED_ZERO_NORM = "REJECTED_ZERO_NORM"
CODE_REJECTED_NEGATIVE_NORM = "REJECTED_NEGATIVE_NORM"
CODE_REJECTED_NON_FINITE_NORM = "REJECTED_NON_FINITE_NORM"
CODE_REJECTED_INCOMPATIBLE_UNIT = "REJECTED_INCOMPATIBLE_UNIT"
CODE_REJECTED_MISSING_PROVENANCE = "REJECTED_MISSING_PROVENANCE"
CODE_REJECTED_NONPRODUCTIVE_HOURS = "REJECTED_NONPRODUCTIVE_HOURS"
CODE_REJECTED_HISTORY_WITHOUT_EXECUTED_QUANTITY = (
    "REJECTED_HISTORY_WITHOUT_EXECUTED_QUANTITY"
)
CODE_REJECTED_SEMANTIC_MISLABEL = "REJECTED_SEMANTIC_MISLABEL"
CODE_REJECTED_EXPERT_INCOMPLETE = "REJECTED_EXPERT_INCOMPLETE"
CODE_REJECTED_UNKNOWN_SOURCE = "REJECTED_UNKNOWN_SOURCE"
CODE_REJECTED_UNKNOWN_STATUS = "REJECTED_UNKNOWN_STATUS"
CODE_REJECTED_UNKNOWN_BASIS = "REJECTED_UNKNOWN_BASIS"

_COVERAGE_NOTE = "UNRESOLVED/NOT_AVAILABLE does not remove a physical candidate"


class LaborNormResolverError(ValueError):
    """Fail-closed LaborNormResolver contract violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class LaborNormEvidence:
    """Normalized labor-norm evidence for one CandidateRecord identity."""

    evidence_id: str
    candidate_id: str
    source_type: str
    labor_hours_per_unit: Any
    unit: str
    source_reference: str
    planning_use_status: str
    basis: str
    source_version: Optional[str] = None
    hours_quality: str = HOURS_NOT_APPLICABLE
    executed_quantity_validated: bool = False
    expert_author: str = ""
    expert_approved_at: str = ""
    expert_reason: str = ""


@dataclass(frozen=True)
class LaborNormResolution:
    resolution_id: str
    schema_version: str
    package_id: str
    candidate_id: str
    status: str
    source_type: Optional[str]
    labor_hours_per_unit: Optional[float]
    unit: Optional[str]
    basis: Optional[str]
    source_reference: Optional[str]
    source_version: Optional[str]
    provenance: Optional[str]
    resolution_reason: str
    selected_evidence_id: Optional[str]
    rejection_codes: tuple[str, ...]
    ambiguity_evidence_ids: tuple[str, ...]
    observed_productivity: Optional[float]
    normative_benchmark: Optional[float]
    planning_norm: Optional[float]


@dataclass(frozen=True)
class LaborNormResolutionSet:
    schema_version: str
    package_id: str
    resolved_package: CandidatePackage
    resolutions: tuple[LaborNormResolution, ...]


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_positive_hours(value: Any) -> tuple[Optional[float], Optional[str]]:
    if value is None:
        return None, CODE_REJECTED_MISSING_NORM
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, CODE_REJECTED_NON_FINITE_NORM
    if math.isnan(number) or math.isinf(number):
        return None, CODE_REJECTED_NON_FINITE_NORM
    if number == 0:
        return None, CODE_REJECTED_ZERO_NORM
    if number < 0:
        return None, CODE_REJECTED_NEGATIVE_NORM
    return number, None


def _units_compatible(candidate_unit: str, evidence_unit: str) -> bool:
    left = _text(candidate_unit)
    right = _text(evidence_unit)
    if not left or not right:
        return False
    return left.casefold() == right.casefold()


def _assess_evidence(
    candidate: CandidateRecord,
    evidence: LaborNormEvidence,
) -> tuple[Optional[float], Optional[str]]:
    if _text(evidence.candidate_id) != candidate.candidate_id:
        return None, CODE_REJECTED_UNKNOWN_SOURCE

    source = _text(evidence.source_type).upper()
    if source not in SOURCE_TYPES:
        return None, CODE_REJECTED_UNKNOWN_SOURCE

    status = _text(evidence.planning_use_status).upper()
    if status not in PLANNING_STATUSES:
        return None, CODE_REJECTED_UNKNOWN_STATUS

    basis = _text(evidence.basis).upper()
    if not basis:
        return None, CODE_REJECTED_UNKNOWN_BASIS

    if source in HISTORY_SOURCES and basis != BASIS_OBSERVED_PRODUCTIVITY:
        return None, CODE_REJECTED_SEMANTIC_MISLABEL
    if source == SOURCE_OFFICIAL_NORMATIVE and basis != BASIS_NORMATIVE_BENCHMARK:
        return None, CODE_REJECTED_SEMANTIC_MISLABEL
    if source in BENCHMARK_SOURCES and basis == BASIS_OBSERVED_PRODUCTIVITY:
        return None, CODE_REJECTED_SEMANTIC_MISLABEL

    hours, hours_code = _parse_positive_hours(evidence.labor_hours_per_unit)
    if hours_code is not None:
        return None, hours_code

    if not _units_compatible(candidate.unit, evidence.unit):
        return None, CODE_REJECTED_INCOMPATIBLE_UNIT

    if not _text(evidence.source_reference):
        return None, CODE_REJECTED_MISSING_PROVENANCE

    if source in HISTORY_SOURCES:
        quality = _text(evidence.hours_quality).upper() or HOURS_UNVALIDATED
        if quality in NONPRODUCTIVE_HOURS or quality != HOURS_VALIDATED_PRODUCTIVE_DIRECT:
            return None, CODE_REJECTED_NONPRODUCTIVE_HOURS
        if evidence.executed_quantity_validated is not True:
            return None, CODE_REJECTED_HISTORY_WITHOUT_EXECUTED_QUANTITY

    if source == SOURCE_EXPERT_APPROVED:
        if not (
            _text(evidence.expert_author)
            and _text(evidence.expert_approved_at)
            and _text(evidence.expert_reason)
        ):
            return None, CODE_REJECTED_EXPERT_INCOMPLETE

    return hours, None


def _identity_key(evidence: LaborNormEvidence, hours: float) -> tuple[Any, ...]:
    return (
        hours,
        _text(evidence.unit).casefold(),
        _text(evidence.source_type).upper(),
        _text(evidence.planning_use_status).upper(),
        _text(evidence.basis).upper(),
    )


def _semantic_slots(
    source: str,
    hours: float,
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    observed: Optional[float] = None
    normative: Optional[float] = None
    planning: Optional[float] = None
    if source in HISTORY_SOURCES:
        observed = hours
    elif source in BENCHMARK_SOURCES:
        normative = hours
    # EXPERT_APPROVED is not Constructor-invented planning_norm.
    return observed, normative, planning


def _unresolved(
    *,
    package_id: str,
    candidate_id: str,
    reason: str,
    rejection_codes: tuple[str, ...],
    ambiguity_evidence_ids: tuple[str, ...] = (),
) -> LaborNormResolution:
    return LaborNormResolution(
        resolution_id=str(uuid.uuid4()),
        schema_version=SCHEMA_VERSION,
        package_id=package_id,
        candidate_id=candidate_id,
        status=LABOR_UNRESOLVED,
        source_type=None,
        labor_hours_per_unit=None,
        unit=None,
        basis=None,
        source_reference=None,
        source_version=None,
        provenance=None,
        resolution_reason=reason,
        selected_evidence_id=None,
        rejection_codes=rejection_codes,
        ambiguity_evidence_ids=ambiguity_evidence_ids,
        observed_productivity=None,
        normative_benchmark=None,
        planning_norm=None,
    )


def _selected(
    *,
    package_id: str,
    candidate: CandidateRecord,
    evidence: LaborNormEvidence,
    hours: float,
    reason: str,
    rejection_codes: tuple[str, ...],
) -> LaborNormResolution:
    source = _text(evidence.source_type).upper()
    reference = _text(evidence.source_reference)
    version = _text(evidence.source_version) or None
    provenance = f"{source}:{reference}"
    if version:
        provenance = f"{provenance}:{version}"
    observed, normative, planning = _semantic_slots(source, hours)
    status = _text(evidence.planning_use_status).upper()
    return LaborNormResolution(
        resolution_id=str(uuid.uuid4()),
        schema_version=SCHEMA_VERSION,
        package_id=package_id,
        candidate_id=candidate.candidate_id,
        status=status,
        source_type=source,
        labor_hours_per_unit=hours,
        unit=_text(evidence.unit),
        basis=_text(evidence.basis).upper(),
        source_reference=reference,
        source_version=version,
        provenance=provenance,
        resolution_reason=reason,
        selected_evidence_id=_text(evidence.evidence_id),
        rejection_codes=rejection_codes,
        ambiguity_evidence_ids=(),
        observed_productivity=observed,
        normative_benchmark=normative,
        planning_norm=planning,
    )


def _resolve_candidate(
    package_id: str,
    candidate: CandidateRecord,
    evidence_items: Sequence[LaborNormEvidence],
) -> LaborNormResolution:
    related = [
        item
        for item in evidence_items
        if _text(item.candidate_id) == candidate.candidate_id
    ]
    if not related:
        return _unresolved(
            package_id=package_id,
            candidate_id=candidate.candidate_id,
            reason=REASON_NO_ADMISSIBLE_EVIDENCE,
            rejection_codes=(),
        )

    admissible: list[tuple[LaborNormEvidence, float]] = []
    rejection_codes: list[str] = []
    for item in related:
        hours, code = _assess_evidence(candidate, item)
        if code is not None:
            rejection_codes.append(code)
            continue
        assert hours is not None
        admissible.append((item, hours))

    if not admissible:
        unique_codes = tuple(dict.fromkeys(rejection_codes))
        return _unresolved(
            package_id=package_id,
            candidate_id=candidate.candidate_id,
            reason=REASON_NO_ADMISSIBLE_EVIDENCE,
            rejection_codes=unique_codes,
        )

    by_rank: dict[int, list[tuple[LaborNormEvidence, float]]] = {}
    for item, hours in admissible:
        rank = SOURCE_RANK[_text(item.source_type).upper()]
        by_rank.setdefault(rank, []).append((item, hours))

    codes = tuple(dict.fromkeys(rejection_codes))
    for rank in sorted(by_rank):
        pool = by_rank[rank]
        validated = [
            pair
            for pair in pool
            if _text(pair[0].planning_use_status).upper() == LABOR_VALIDATED
        ]
        chosen_pool = validated if validated else pool

        groups: dict[tuple[Any, ...], list[tuple[LaborNormEvidence, float]]] = {}
        for item, hours in chosen_pool:
            groups.setdefault(_identity_key(item, hours), []).append((item, hours))

        if len(groups) > 1:
            ambiguous_ids = tuple(
                sorted(_text(item.evidence_id) for item, _hours in chosen_pool)
            )
            return _unresolved(
                package_id=package_id,
                candidate_id=candidate.candidate_id,
                reason=REASON_AMBIGUOUS_LABOR_NORM_EVIDENCE,
                rejection_codes=codes,
                ambiguity_evidence_ids=ambiguous_ids,
            )

        group = next(iter(groups.values()))
        group_sorted = sorted(group, key=lambda pair: _text(pair[0].evidence_id))
        winner, hours = group_sorted[0]
        reason = REASON_SELECTED_BY_SOURCE_HIERARCHY
        if len(group) > 1:
            reason = REASON_DUPLICATE_EVIDENCE_DEDUPLICATED
        return _selected(
            package_id=package_id,
            candidate=candidate,
            evidence=winner,
            hours=hours,
            reason=reason,
            rejection_codes=codes,
        )

    return _unresolved(
        package_id=package_id,
        candidate_id=candidate.candidate_id,
        reason=REASON_NO_ADMISSIBLE_EVIDENCE,
        rejection_codes=codes,
    )


def _summary(candidates: Sequence[CandidateRecord]) -> LaborNormSummary:
    validated = 0
    provisional = 0
    unresolved = 0
    for item in candidates:
        if item.labor_norm_status == LABOR_VALIDATED:
            validated += 1
        elif item.labor_norm_status == LABOR_PROVISIONAL:
            provisional += 1
        else:
            unresolved += 1
    return LaborNormSummary(
        validated=validated,
        provisional=provisional,
        unresolved=unresolved,
        coverage_note=_COVERAGE_NOTE,
    )


def resolve_labor_norms(
    package: CandidatePackage,
    evidence: Sequence[LaborNormEvidence],
) -> LaborNormResolutionSet:
    """
    Attach labor-norm metadata to every candidate.

    Returns a new package via immutable replace. Original package is unchanged.
    Input candidate count equals output resolution count.
    """
    if not isinstance(package, CandidatePackage):
        raise LaborNormResolverError(
            CODE_DATA_CONTRACT_BLOCKER,
            "package must be CandidatePackage",
        )
    if evidence is None or isinstance(evidence, (str, bytes)):
        raise LaborNormResolverError(
            CODE_DATA_CONTRACT_BLOCKER,
            "evidence must be a sequence of LaborNormEvidence",
        )

    evidence_items = tuple(evidence)
    for item in evidence_items:
        if not isinstance(item, LaborNormEvidence):
            raise LaborNormResolverError(
                CODE_DATA_CONTRACT_BLOCKER,
                "evidence items must be LaborNormEvidence",
            )

    resolutions: list[LaborNormResolution] = []
    new_candidates: list[CandidateRecord] = []
    for candidate in package.candidates:
        resolution = _resolve_candidate(package.package_id, candidate, evidence_items)
        resolutions.append(resolution)
        new_candidates.append(
            replace(
                candidate,
                labor_norm_status=resolution.status,
                labor_norm_resolution_ref=resolution.resolution_id,
            )
        )

    if len(resolutions) != len(package.candidates):
        raise LaborNormResolverError(
            CODE_DATA_CONTRACT_BLOCKER,
            "resolution count must equal candidate count",
        )

    frozen_candidates = tuple(new_candidates)
    resolved_package = replace(
        package,
        candidates=frozen_candidates,
        labor_norm_summary=_summary(frozen_candidates),
    )
    return LaborNormResolutionSet(
        schema_version=SCHEMA_VERSION,
        package_id=package.package_id,
        resolved_package=resolved_package,
        resolutions=tuple(resolutions),
    )
