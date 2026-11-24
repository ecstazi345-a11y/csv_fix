"""S10 — Operation Classification & Normalization (deterministic).

No LLM. No labor redistribution. No unit conversion. No registry approval.
Untrusted master text is data, never instructions.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from agents.production_shift_auditor.catalogs.insulation_operations_v0_1 import (
    INSULATION_CATALOG_VERSION,
    INSULATION_OPERATION_CANDIDATES,
    RULES_VERSION as CATALOG_RULES,
    CanonicalOperationCandidate,
)
from agents.production_shift_auditor.contracts import OperationLaborClaim, ShiftAuditInput
from agents.production_shift_auditor.s10_contracts import (
    S10_ARTIFACT_SCHEMA_VERSION,
    S10_RULES_VERSION,
    ClassificationCandidate,
    ClassificationMethod,
    ClassificationStatus,
    OperationClassificationLine,
    ShiftOperationClassificationArtifact,
)

AGENT_CODE = "PRODUCTION_SHIFT_AUDITOR"
AGENT_VERSION = "0.1"

_PUNCT_RE = re.compile(r"[^\w\s\-]+", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")
_COMPOSITE_SPLIT_RE = re.compile(
    r"\s+(?:и|/|\+| затем | потом | а также )\s+",
    re.IGNORECASE,
)


def normalize_operation_text(text: str) -> str:
    raw = (text or "").strip().lower().replace("ё", "е")
    raw = raw.replace("«", " ").replace("»", " ")
    raw = _PUNCT_RE.sub(" ", raw)
    raw = raw.replace("_", " ")
    raw = _SPACE_RE.sub(" ", raw).strip()
    return raw


def _context_blob(claim: OperationLaborClaim, audit_input: ShiftAuditInput) -> str:
    parts = [
        claim.operation_name,
        audit_input.construction_discipline or "",
        claim.material_hint or "",
        claim.boq_name or "",
        claim.work_kind_hint or "",
        claim.physical_object_hint or "",
        claim.comment or "",
        " ".join(claim.notes),
        claim.physical_unit or "",
    ]
    return normalize_operation_text(" ".join(p for p in parts if p))


def _score_candidate(
    norm_text: str,
    context: str,
    cand: CanonicalOperationCandidate,
) -> tuple[int, list[str]]:
    evidence: list[str] = []
    score = 0
    if norm_text in cand.aliases or norm_text == normalize_operation_text(cand.canonical_name):
        return 100, [f"exact_alias_or_canonical:{cand.operation_code}"]

    for alias in cand.aliases:
        if alias and alias in norm_text:
            score = max(score, 80)
            evidence.append(f"alias_substring:{alias}")
        elif alias and norm_text in alias and len(norm_text) >= 8:
            score = max(score, 70)
            evidence.append(f"text_substring_of_alias:{alias}")

    strong_hits = [t for t in cand.strong_tokens if t and t in norm_text]
    if strong_hits:
        score = max(score, 40 + 10 * min(len(strong_hits), 3))
        evidence.append("strong_tokens:" + ",".join(strong_hits))

    ctx_hits = [t for t in cand.context_tokens if t and t in context]
    if ctx_hits and strong_hits:
        score += 15
        evidence.append("context_tokens:" + ",".join(ctx_hits))
    elif ctx_hits and score >= 40:
        score += 8
        evidence.append("context_tokens:" + ",".join(ctx_hits))

    return score, evidence


def _best_matches(
    norm_text: str, context: str
) -> list[tuple[CanonicalOperationCandidate, int, list[str]]]:
    scored: list[tuple[CanonicalOperationCandidate, int, list[str]]] = []
    for cand in INSULATION_OPERATION_CANDIDATES:
        score, evidence = _score_candidate(norm_text, context, cand)
        if score > 0:
            scored.append((cand, score, evidence))
    scored.sort(key=lambda x: (-x[1], x[0].operation_code))
    return scored


_WORK_TYPE_ENUM_RE = re.compile(
    r"(?i)^\s*\d+\.\d+\.|thermal_insulation|working_shift|day_off|единица по описанию"
)


def _is_general_work_type_label(norm_text: str, original: str) -> bool:
    """Airtable/discipline enums are not specific technological operations."""
    if _WORK_TYPE_ENUM_RE.search(original or "") or _WORK_TYPE_ENUM_RE.search(norm_text):
        return True
    # Broad labels without specific action detail
    broad = {
        "монтаж теплоизоляции трубопроводов",
        "монтаж теплоизоляции",
        "теплоизоляция трубопроводов",
    }
    return norm_text in broad


def _looks_composite(norm_text: str) -> list[str]:
    """Split into fragments that indicate multiple technological actions.

    Composite if:
    - ≥2 fragments each match different catalog codes, OR
    - ≥1 fragment matches catalog and another fragment is a distinct non-empty
      technical phrase (even if not yet in catalog).
    Exact alias equality must not hide such joins.
    """
    if not norm_text:
        return []
    parts = [p.strip() for p in _COMPOSITE_SPLIT_RE.split(norm_text) if p and p.strip()]
    if len(parts) < 2:
        return []

    matched: list[tuple[str, Optional[str], int]] = []
    for part in parts:
        hits = _best_matches(part, part)
        if hits and hits[0][1] >= 70:
            matched.append((part, hits[0][0].operation_code, hits[0][1]))
        elif len(part) >= 4:
            matched.append((part, None, 0))

    codes = {c for _, c, _ in matched if c}
    known = [p for p, c, s in matched if c and s >= 70]
    unknown = [p for p, c, _ in matched if c is None]
    if len(codes) >= 2 and len(known) >= 2:
        return [p for p, _, _ in matched]
    if known and unknown:
        # One known op joined with another uncatalogued action phrase
        return [p for p, _, _ in matched]
    return []

def classify_operation_claim(
    claim: OperationLaborClaim,
    audit_input: ShiftAuditInput,
    *,
    source_operation_identity: str,
) -> OperationClassificationLine:
    original = claim.operation_name
    norm = normalize_operation_text(original)
    context = _context_blob(claim, audit_input)
    provenance = (
        f"source_kind={audit_input.source_kind.value}",
        f"project_code={audit_input.project_code}",
        f"discipline={audit_input.construction_discipline or ''}",
        *tuple(f"record:{rid}" for rid in claim.source_record_ids[:5]),
        *audit_input.provenance_notes[:3],
    )

    labor_q = claim.claimed_labor_quantity
    labor_u = claim.labor_unit.value if claim.labor_unit else None

    if not norm:
        return OperationClassificationLine(
            source_operation_identity=source_operation_identity,
            original_operation_text=original,
            canonical_operation_candidate=None,
            operation_code_candidate=None,
            work_category=None,
            classification_status=ClassificationStatus.INSUFFICIENT_CONTEXT,
            classification_method=ClassificationMethod.DETERMINISTIC_INSUFFICIENT,
            matching_evidence=("empty_or_whitespace_operation_text",),
            uncertainty_reason="Отсутствует исходное описание операции.",
            clarification_request="Укажите технологическую операцию текстом.",
            classification_rules_version=S10_RULES_VERSION,
            catalog_version=INSULATION_CATALOG_VERSION,
            provenance=provenance,
            claimed_labor_quantity=labor_q,
            claimed_labor_unit=labor_u,
            physical_quantity=claim.physical_quantity,
            physical_unit=claim.physical_unit,
            source_record_ids=claim.source_record_ids,
        )

    if _is_general_work_type_label(norm, original):
        return OperationClassificationLine(
            source_operation_identity=source_operation_identity,
            original_operation_text=original,
            canonical_operation_candidate=None,
            operation_code_candidate=None,
            work_category=None,
            classification_status=ClassificationStatus.INSUFFICIENT_CONTEXT,
            classification_method=ClassificationMethod.DETERMINISTIC_INSUFFICIENT,
            matching_evidence=("general_work_type_or_enum_label",),
            uncertainty_reason=(
                "Текст похож на общий вид работ / enum дисциплины, а не на "
                "конкретную технологическую операцию."
            ),
            clarification_request=(
                "Укажите конкретную технологическую операцию (раскрой, монтаж "
                "прямых участков, проклейка лентой и т.п.), а не только вид работ."
            ),
            classification_rules_version=S10_RULES_VERSION,
            catalog_version=INSULATION_CATALOG_VERSION,
            provenance=provenance,
            claimed_labor_quantity=labor_q,
            claimed_labor_unit=labor_u,
            physical_quantity=claim.physical_quantity,
            physical_unit=claim.physical_unit,
            source_record_ids=claim.source_record_ids,
        )

    # Full-string exact catalog hit first: catalog names may themselves contain
    # "и" (e.g. «Замеры и разметка») and must not be split as COMPOSITE.
    exact_hits = [
        c
        for c in INSULATION_OPERATION_CANDIDATES
        if norm in c.aliases or norm == normalize_operation_text(c.canonical_name)
    ]
    if len(exact_hits) == 1:
        cand = exact_hits[0]
        canon_norm = normalize_operation_text(cand.canonical_name)
        status = (
            ClassificationStatus.EXACT_MATCH
            if norm == canon_norm
            else ClassificationStatus.NORMALIZED_MATCH
        )
        method = (
            ClassificationMethod.DETERMINISTIC_ALIAS
            if status == ClassificationStatus.EXACT_MATCH
            else ClassificationMethod.DETERMINISTIC_NORMALIZED
        )
        evidence = (
            f"exact_alias_or_canonical:{cand.operation_code}",
            "score:100",
        )
        return OperationClassificationLine(
            source_operation_identity=source_operation_identity,
            original_operation_text=original,
            canonical_operation_candidate=cand.canonical_name,
            operation_code_candidate=cand.operation_code,
            work_category=cand.work_category,
            classification_status=status,
            classification_method=method,
            matching_evidence=evidence,
            uncertainty_reason=None,
            clarification_request=None,
            classification_rules_version=S10_RULES_VERSION,
            catalog_version=INSULATION_CATALOG_VERSION,
            candidates=(
                ClassificationCandidate(
                    cand.operation_code,
                    cand.canonical_name,
                    cand.work_category,
                    evidence,
                ),
            ),
            provenance=provenance,
            claimed_labor_quantity=labor_q,
            claimed_labor_unit=labor_u,
            physical_quantity=claim.physical_quantity,
            physical_unit=claim.physical_unit,
            source_record_ids=claim.source_record_ids,
        )
    if len(exact_hits) >= 2:
        cand_rows = tuple(
            ClassificationCandidate(
                operation_code=c.operation_code,
                canonical_name=c.canonical_name,
                work_category=c.work_category,
                matching_evidence=(f"exact_alias_or_canonical:{c.operation_code}",),
            )
            for c in exact_hits[:5]
        )
        return OperationClassificationLine(
            source_operation_identity=source_operation_identity,
            original_operation_text=original,
            canonical_operation_candidate=None,
            operation_code_candidate=None,
            work_category=None,
            classification_status=ClassificationStatus.AMBIGUOUS,
            classification_method=ClassificationMethod.DETERMINISTIC_ALIAS,
            matching_evidence=("multiple_exact_alias_hits",),
            uncertainty_reason="Одна формулировка точно совпадает с несколькими кандидатами каталога.",
            clarification_request="Выберите каноническую операцию из предложенных кандидатов.",
            classification_rules_version=S10_RULES_VERSION,
            catalog_version=INSULATION_CATALOG_VERSION,
            candidates=cand_rows,
            provenance=provenance,
            claimed_labor_quantity=labor_q,
            claimed_labor_unit=labor_u,
            physical_quantity=claim.physical_quantity,
            physical_unit=claim.physical_unit,
            source_record_ids=claim.source_record_ids,
        )

    composite_parts = _looks_composite(norm)
    if composite_parts:
        cand_rows: list[ClassificationCandidate] = []
        for part in composite_parts:
            hits = _best_matches(part, context)
            if hits:
                c, score, ev = hits[0]
                cand_rows.append(
                    ClassificationCandidate(
                        operation_code=c.operation_code,
                        canonical_name=c.canonical_name,
                        work_category=c.work_category,
                        matching_evidence=tuple(ev + [f"fragment:{part}", f"score:{score}"]),
                    )
                )
        return OperationClassificationLine(
            source_operation_identity=source_operation_identity,
            original_operation_text=original,
            canonical_operation_candidate=None,
            operation_code_candidate=None,
            work_category=None,
            classification_status=ClassificationStatus.COMPOSITE_OPERATION,
            classification_method=ClassificationMethod.DETERMINISTIC_COMPOSITE,
            matching_evidence=(
                "composite_fragments:" + "|".join(composite_parts),
                "NO_AUTOMATIC_TIME_DISTRIBUTION",
            ),
            uncertainty_reason=(
                "Одна исходная запись содержит несколько распознаваемых операций; "
                "трудозатраты не распределяются автоматически."
            ),
            clarification_request=(
                "Разделите составную запись на отдельные операции с трудозатратами "
                "по каждой, либо подтвердите ведущую операцию."
            ),
            classification_rules_version=S10_RULES_VERSION,
            catalog_version=INSULATION_CATALOG_VERSION,
            candidates=tuple(cand_rows),
            provenance=provenance,
            claimed_labor_quantity=labor_q,
            claimed_labor_unit=labor_u,
            physical_quantity=claim.physical_quantity,
            physical_unit=claim.physical_unit,
            source_record_ids=claim.source_record_ids,
        )

    hits = _best_matches(norm, context)
    if not hits or hits[0][1] < 40:
        return OperationClassificationLine(
            source_operation_identity=source_operation_identity,
            original_operation_text=original,
            canonical_operation_candidate=None,
            operation_code_candidate=None,
            work_category=None,
            classification_status=ClassificationStatus.UNKNOWN_OPERATION,
            classification_method=ClassificationMethod.DETERMINISTIC_UNKNOWN,
            matching_evidence=("no_catalog_match_above_threshold",),
            uncertainty_reason="Операция не сопоставлена с рабочим каталогом изоляции.",
            clarification_request=(
                "Уточните каноническое наименование операции или технологический контекст."
            ),
            classification_rules_version=S10_RULES_VERSION,
            catalog_version=INSULATION_CATALOG_VERSION,
            candidates=(),
            provenance=provenance,
            claimed_labor_quantity=labor_q,
            claimed_labor_unit=labor_u,
            physical_quantity=claim.physical_quantity,
            physical_unit=claim.physical_unit,
            source_record_ids=claim.source_record_ids,
        )

    top = hits[0]
    close = [h for h in hits if h[1] >= 70 and (top[1] - h[1]) <= 15]
    # Distinct codes near the top → AMBIGUOUS
    close_codes = {h[0].operation_code for h in close}
    if len(close_codes) >= 2:
        cand_rows = tuple(
            ClassificationCandidate(
                operation_code=h[0].operation_code,
                canonical_name=h[0].canonical_name,
                work_category=h[0].work_category,
                matching_evidence=tuple(h[2] + [f"score:{h[1]}"]),
            )
            for h in close[:5]
        )
        return OperationClassificationLine(
            source_operation_identity=source_operation_identity,
            original_operation_text=original,
            canonical_operation_candidate=None,
            operation_code_candidate=None,
            work_category=None,
            classification_status=ClassificationStatus.AMBIGUOUS,
            classification_method=ClassificationMethod.DETERMINISTIC_CONTEXT,
            matching_evidence=("multiple_near_equal_candidates",),
            uncertainty_reason="Несколько канонических кандидатов совместимы с описанием.",
            clarification_request="Выберите каноническую операцию из предложенных кандидатов.",
            classification_rules_version=S10_RULES_VERSION,
            catalog_version=INSULATION_CATALOG_VERSION,
            candidates=cand_rows,
            provenance=provenance,
            claimed_labor_quantity=labor_q,
            claimed_labor_unit=labor_u,
            physical_quantity=claim.physical_quantity,
            physical_unit=claim.physical_unit,
            source_record_ids=claim.source_record_ids,
        )

    cand, score, evidence = top
    canon_norm = normalize_operation_text(cand.canonical_name)
    # EXACT_MATCH only when the source text equals the canonical name itself.
    # Alias hit alone is NORMALIZED_MATCH — string equality of an alias is not
    # proof of full professional equivalence to the canonical operation.
    if norm == canon_norm:
        status = ClassificationStatus.EXACT_MATCH
        method = ClassificationMethod.DETERMINISTIC_ALIAS
    elif score >= 70:
        status = ClassificationStatus.NORMALIZED_MATCH
        method = (
            ClassificationMethod.DETERMINISTIC_CONTEXT
            if any(e.startswith("context_tokens") for e in evidence)
            else ClassificationMethod.DETERMINISTIC_NORMALIZED
        )
    elif score >= 40:
        # Weak single match — treat as insufficient rather than inventing certainty
        return OperationClassificationLine(
            source_operation_identity=source_operation_identity,
            original_operation_text=original,
            canonical_operation_candidate=cand.canonical_name,
            operation_code_candidate=cand.operation_code,
            work_category=cand.work_category,
            classification_status=ClassificationStatus.INSUFFICIENT_CONTEXT,
            classification_method=ClassificationMethod.DETERMINISTIC_INSUFFICIENT,
            matching_evidence=tuple(evidence + [f"weak_score:{score}"]),
            uncertainty_reason="Слабое совпадение без достаточного контекста для NORMALIZED_MATCH.",
            clarification_request="Добавьте материал / вид работ / уточните формулировку операции.",
            classification_rules_version=S10_RULES_VERSION,
            catalog_version=INSULATION_CATALOG_VERSION,
            candidates=(
                ClassificationCandidate(
                    cand.operation_code,
                    cand.canonical_name,
                    cand.work_category,
                    tuple(evidence),
                ),
            ),
            provenance=provenance,
            claimed_labor_quantity=labor_q,
            claimed_labor_unit=labor_u,
            physical_quantity=claim.physical_quantity,
            physical_unit=claim.physical_unit,
            source_record_ids=claim.source_record_ids,
        )
    else:
        status = ClassificationStatus.UNKNOWN_OPERATION
        method = ClassificationMethod.DETERMINISTIC_UNKNOWN

    return OperationClassificationLine(
        source_operation_identity=source_operation_identity,
        original_operation_text=original,
        canonical_operation_candidate=cand.canonical_name,
        operation_code_candidate=cand.operation_code,
        work_category=cand.work_category,
        classification_status=status,
        classification_method=method,
        matching_evidence=tuple(evidence + [f"score:{score}"]),
        uncertainty_reason=None,
        clarification_request=None,
        classification_rules_version=S10_RULES_VERSION,
        catalog_version=INSULATION_CATALOG_VERSION,
        candidates=(
            ClassificationCandidate(
                cand.operation_code,
                cand.canonical_name,
                cand.work_category,
                tuple(evidence),
            ),
        ),
        provenance=provenance,
        claimed_labor_quantity=labor_q,
        claimed_labor_unit=labor_u,
        physical_quantity=claim.physical_quantity,
        physical_unit=claim.physical_unit,
        source_record_ids=claim.source_record_ids,
    )


def evaluate_s10(
    audit_input: ShiftAuditInput,
    *,
    audit_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> ShiftOperationClassificationArtifact:
    lines: list[OperationClassificationLine] = []
    for idx, claim in enumerate(audit_input.operations):
        identity = (
            claim.source_record_ids[0]
            if claim.source_record_ids
            else f"op:{idx}:{normalize_operation_text(claim.operation_name)[:40]}"
        )
        lines.append(
            classify_operation_claim(
                claim,
                audit_input,
                source_operation_identity=identity,
            )
        )

    observations = [
        "S10 = deterministic classification skill (no LLM in this increment).",
        "CLASSIFICATION ≠ ACCEPTANCE; CLASSIFICATION ≠ TECHNOLOGICAL VALIDATION.",
        "ORIGINAL TEXT PRESERVATION: исходный текст мастера сохранён.",
        "NO AUTOMATIC TIME DISTRIBUTION / UNIT CONVERSION / REGISTRY APPROVAL.",
        f"Working catalog: {INSULATION_CATALOG_VERSION} (not approved Operation Registry).",
        f"Rules: {S10_RULES_VERSION} / catalog_rules={CATALOG_RULES}.",
    ]
    counts: dict[str, int] = {}
    for line in lines:
        counts[line.classification_status.value] = (
            counts.get(line.classification_status.value, 0) + 1
        )
    summary_lines = [
        "PSAA S10 — Operation Classification (deterministic)",
        f"Проект: {audit_input.project_code} date={audit_input.work_date} crew={audit_input.crew_id}",
        "Managerial acceptance: NOT_IN_SCOPE",
        "Registry approval: NOT_APPROVED_BY_AGENT",
        "Status counts: "
        + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
    ]
    for line in lines:
        summary_lines.append(
            f"- «{line.original_operation_text}» → "
            f"{line.canonical_operation_candidate or '—'} "
            f"[{line.classification_status.value}]"
        )

    return ShiftOperationClassificationArtifact(
        schema_version=S10_ARTIFACT_SCHEMA_VERSION,
        rules_version=S10_RULES_VERSION,
        catalog_version=INSULATION_CATALOG_VERSION,
        audit_id=audit_id or str(uuid.uuid4()),
        agent_code=AGENT_CODE,
        agent_version=AGENT_VERSION,
        run_id=run_id,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        project_code=audit_input.project_code,
        work_date=audit_input.work_date,
        crew_id=audit_input.crew_id,
        classification_domain="insulation_working_catalog",
        classifications=tuple(lines),
        observations=tuple(observations),
        managerial_acceptance_status="NOT_IN_SCOPE",
        registry_approval_status="NOT_APPROVED_BY_AGENT",
        human_readable_summary="\n".join(summary_lines),
    )
