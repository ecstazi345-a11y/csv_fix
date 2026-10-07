"""
Constructor Recommendation Layer V1 — pure deterministic capability.

Consumes already-computed CandidateRecord facts (qty + labor status).
Does not recompute remainder / already_planned / exclusions.
Does not call tools, network, SQL, shell, LLM, or product writes.

V1 returns only:
  RECOMMEND_ADD
  HUMAN_REVIEW_REQUIRED

RECOMMEND_REMOVE is reserved/deferred and never returned by the V1 mapper.
Recommendation is applied only after authoritative labor resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from agents.monthly_plan_constructor.candidate_package import (
    LABOR_NOT_AVAILABLE,
    LABOR_PROVISIONAL,
    LABOR_UNRESOLVED,
    LABOR_VALIDATED,
    CandidateRecord,
)

RECOMMEND_ADD = "RECOMMEND_ADD"
HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
RECOMMEND_REMOVE = "RECOMMEND_REMOVE"  # reserved / DEFERRED — V1 mapper never returns

V1_ACTIVE_RECOMMENDATIONS = frozenset({RECOMMEND_ADD, HUMAN_REVIEW_REQUIRED})

REASON_AVAILABLE_TO_ADD = "AVAILABLE_TO_ADD"
REASON_LABOR_VALIDATED = "LABOR_VALIDATED"
REASON_LABOR_PROVISIONAL = "LABOR_PROVISIONAL"
REASON_LABOR_NORM_UNRESOLVED = "LABOR_NORM_UNRESOLVED"
REASON_LABOR_NOT_AVAILABLE = "LABOR_NOT_AVAILABLE"

CODE_RECOMMENDATION_CONTRACT_BLOCKER = "RECOMMENDATION_CONTRACT_BLOCKER"


class RecommendationError(ValueError):
    """Fail-closed recommendation contract violation."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class RecommendationResult:
    recommendation: str
    recommendation_reason_codes: tuple[str, ...]


def _require_candidate(candidate: Any) -> CandidateRecord:
    if not isinstance(candidate, CandidateRecord):
        raise RecommendationError(
            CODE_RECOMMENDATION_CONTRACT_BLOCKER,
            "candidate must be CandidateRecord",
        )
    return candidate


def recommend_for_candidate(candidate: CandidateRecord) -> RecommendationResult:
    """
    Map labor-enriched candidate facts to a V1 professional recommendation.

    Same input → same output. Never returns RECOMMEND_REMOVE.
    """
    item = _require_candidate(candidate)
    status = str(item.labor_norm_status or "").strip().upper()
    available = float(item.available_to_add_qty)

    if status in {LABOR_UNRESOLVED, LABOR_NOT_AVAILABLE}:
        reason = (
            REASON_LABOR_NORM_UNRESOLVED
            if status == LABOR_UNRESOLVED
            else REASON_LABOR_NOT_AVAILABLE
        )
        return RecommendationResult(
            recommendation=HUMAN_REVIEW_REQUIRED,
            recommendation_reason_codes=(reason,),
        )

    if status == LABOR_VALIDATED:
        if available <= 0:
            raise RecommendationError(
                CODE_RECOMMENDATION_CONTRACT_BLOCKER,
                "VALIDATED candidate with available_to_add_qty <= 0 is unsupported in V1",
            )
        return RecommendationResult(
            recommendation=RECOMMEND_ADD,
            recommendation_reason_codes=(
                REASON_AVAILABLE_TO_ADD,
                REASON_LABOR_VALIDATED,
            ),
        )

    if status == LABOR_PROVISIONAL:
        if available <= 0:
            raise RecommendationError(
                CODE_RECOMMENDATION_CONTRACT_BLOCKER,
                "PROVISIONAL candidate with available_to_add_qty <= 0 is unsupported in V1",
            )
        return RecommendationResult(
            recommendation=RECOMMEND_ADD,
            recommendation_reason_codes=(
                REASON_AVAILABLE_TO_ADD,
                REASON_LABOR_PROVISIONAL,
            ),
        )

    raise RecommendationError(
        CODE_RECOMMENDATION_CONTRACT_BLOCKER,
        f"unsupported labor_norm_status for recommendation V1: {status!r}",
    )


def apply_recommendation(candidate: CandidateRecord) -> CandidateRecord:
    """Immutable rebuild: attach V1 recommendation after labor enrichment."""
    result = recommend_for_candidate(candidate)
    if result.recommendation == RECOMMEND_REMOVE:
        raise RecommendationError(
            CODE_RECOMMENDATION_CONTRACT_BLOCKER,
            "RECOMMEND_REMOVE is deferred and must not be emitted by V1",
        )
    if result.recommendation not in V1_ACTIVE_RECOMMENDATIONS:
        raise RecommendationError(
            CODE_RECOMMENDATION_CONTRACT_BLOCKER,
            f"unsupported recommendation value {result.recommendation!r}",
        )
    return replace(
        candidate,
        recommendation=result.recommendation,
        recommendation_reason_codes=result.recommendation_reason_codes,
    )
