"""S02 — Technological Integrity (deterministic).

Checks classified operations against versioned technological rules.
Does NOT prove physical execution. Does NOT accept/reject the shift.
Does NOT invent approved technology when sources are absent.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence

from agents.production_shift_auditor.catalogs.insulation_tech_rules_v0_1 import (
    INSULATION_TECH_RULES,
    INSULATION_TECH_RULESET_VERSION,
    TechnologicalRule,
)
from agents.production_shift_auditor.contracts import (
    LaborUnit,
    OperationLaborClaim,
    ShiftAuditInput,
)
from agents.production_shift_auditor.s02_contracts import (
    S02_ARTIFACT_SCHEMA_VERSION,
    S02_RULES_VERSION,
    ApplicabilityVerdict,
    PriorOperationEvidence,
    SourceAuthority,
    TechCheckResult,
    TechCheckType,
    TechnologicalCheckFinding,
    ShiftTechnologicalIntegrityArtifact,
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

_TIME_RE = re.compile(
    r"execution_event_time\s*=\s*([0-9T:\-\+Zz\.]+)",
    re.IGNORECASE,
)


def _material_blob(claim: OperationLaborClaim, line: OperationClassificationLine) -> str:
    parts = [
        claim.material_hint or "",
        claim.boq_name or "",
        claim.comment or "",
        line.original_operation_text or "",
        " ".join(claim.notes),
    ]
    return normalize_operation_text(" ".join(p for p in parts if p))


def _discipline_blob(claim: OperationLaborClaim, audit_input: ShiftAuditInput) -> str:
    parts = [
        audit_input.construction_discipline or "",
        claim.work_kind_hint or "",
    ]
    return normalize_operation_text(" ".join(p for p in parts if p))


def _has_any_token(blob: str, tokens: tuple[str, ...]) -> bool:
    return any(t and t in blob for t in tokens)


def _execution_event_time(claim: OperationLaborClaim) -> Optional[str]:
    for note in claim.notes:
        m = _TIME_RE.search(note or "")
        if m:
            return m.group(1)
    if claim.comment:
        m = _TIME_RE.search(claim.comment)
        if m:
            return m.group(1)
    return None


def _parse_iso_sortable(value: str) -> Optional[str]:
    """Return a comparable string if parseable; else None (fail closed on compare)."""
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        # Allow trailing Z
        datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return raw
    except ValueError:
        return None


def _claim_for_line(
    audit_input: ShiftAuditInput, line: OperationClassificationLine
) -> Optional[OperationLaborClaim]:
    for claim in audit_input.operations:
        if claim.operation_name == line.original_operation_text:
            return claim
        if claim.source_record_ids and claim.source_record_ids[0] == line.source_operation_identity:
            return claim
    return None


def _base_finding(
    *,
    check_identity: str,
    line: OperationClassificationLine,
    claim: Optional[OperationLaborClaim],
    check_type: TechCheckType,
    rule: Optional[TechnologicalRule],
    applicability: ApplicabilityVerdict,
    check_result: TechCheckResult,
    supporting_evidence: tuple[str, ...],
    missing_evidence: tuple[str, ...],
    professional_explanation: str,
    clarification_request: Optional[str],
) -> TechnologicalCheckFinding:
    demo = bool(rule and rule.source_authority == SourceAuthority.DEMONSTRATION_RULE)
    return TechnologicalCheckFinding(
        check_identity=check_identity,
        source_operation_identity=line.source_operation_identity,
        original_operation_text=line.original_operation_text,
        classified_operation_code=line.operation_code_candidate,
        classified_operation_name=line.canonical_operation_candidate,
        check_type=check_type,
        applicable_rule_id=rule.rule_id if rule else None,
        rule_version=rule.revision if rule else None,
        source_authority=rule.source_authority if rule else None,
        source_provenance=(
            ((rule.source_citation,) if rule else ())
            + (("DEMONSTRATION_RULE",) if demo else ())
        ),
        applicability=applicability,
        check_result=check_result,
        supporting_evidence=supporting_evidence,
        missing_evidence=missing_evidence,
        professional_explanation=professional_explanation,
        clarification_request=clarification_request,
        demonstration_rule=demo,
        claimed_labor_quantity=(
            claim.claimed_labor_quantity if claim is not None else line.claimed_labor_quantity
        ),
        claimed_labor_unit=(
            claim.labor_unit.value if claim is not None else line.claimed_labor_unit
        ),
        physical_quantity=(
            claim.physical_quantity if claim is not None else line.physical_quantity
        ),
        physical_unit=claim.physical_unit if claim is not None else line.physical_unit,
    )


def _gate_from_classification(
    line: OperationClassificationLine,
    claim: Optional[OperationLaborClaim],
) -> Optional[TechnologicalCheckFinding]:
    st = line.classification_status
    if st == ClassificationStatus.COMPOSITE_OPERATION:
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:composite",
            line=line,
            claim=claim,
            check_type=TechCheckType.COMPOSITE_LIMITATION,
            rule=None,
            applicability=ApplicabilityVerdict.UNKNOWN,
            check_result=TechCheckResult.INSUFFICIENT_CONTEXT,
            supporting_evidence=("s10_status=COMPOSITE_OPERATION", "NO_AUTOMATIC_TIME_DISTRIBUTION"),
            missing_evidence=("separated_component_operations_with_labor",),
            professional_explanation=(
                "S10 вернул COMPOSITE_OPERATION: технологическая проверка ограничена; "
                "трудозатраты не распределяются между компонентами."
            ),
            clarification_request=(
                "Разделите составную запись на отдельные операции перед полной "
                "технологической проверкой."
            ),
        )
    if st == ClassificationStatus.UNKNOWN_OPERATION:
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:unknown",
            line=line,
            claim=claim,
            check_type=TechCheckType.CONTEXT_SUFFICIENCY,
            rule=None,
            applicability=ApplicabilityVerdict.UNKNOWN,
            check_result=TechCheckResult.NOT_EVALUATED,
            supporting_evidence=("s10_status=UNKNOWN_OPERATION",),
            missing_evidence=("classified_operation_in_working_catalog",),
            professional_explanation=(
                "Операция не классифицирована в рабочем каталоге — технологическая "
                "проверка не выполняется (CLASSIFICATION ≠ TECHNOLOGICAL VALIDATION)."
            ),
            clarification_request="Уточните каноническую технологическую операцию.",
        )
    if st == ClassificationStatus.INSUFFICIENT_CONTEXT:
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:s10_insufficient",
            line=line,
            claim=claim,
            check_type=TechCheckType.CONTEXT_SUFFICIENCY,
            rule=None,
            applicability=ApplicabilityVerdict.UNKNOWN,
            check_result=TechCheckResult.INSUFFICIENT_CONTEXT,
            supporting_evidence=("s10_status=INSUFFICIENT_CONTEXT",),
            missing_evidence=("specific_technological_operation_text",),
            professional_explanation=(
                "Недостаточно контекста классификации (часто work-type enum вместо "
                "конкретной операции) — технологическая проверка не обоснована."
            ),
            clarification_request="Укажите конкретную технологическую операцию.",
        )
    if st == ClassificationStatus.AMBIGUOUS:
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:ambiguous",
            line=line,
            claim=claim,
            check_type=TechCheckType.CONTEXT_SUFFICIENCY,
            rule=None,
            applicability=ApplicabilityVerdict.UNKNOWN,
            check_result=TechCheckResult.INSUFFICIENT_CONTEXT,
            supporting_evidence=("s10_status=AMBIGUOUS",),
            missing_evidence=("disambiguated_canonical_operation",),
            professional_explanation=(
                "Классификация неоднозначна — технологическая проверка отложена."
            ),
            clarification_request="Выберите каноническую операцию из кандидатов S10.",
        )
    return None


def _dummy_claim(name: str = "") -> OperationLaborClaim:
    return OperationLaborClaim(name, 0, LaborUnit.MAN_MINUTE)


def _eval_operation_applicability(
    rule: TechnologicalRule,
    line: OperationClassificationLine,
    claim: Optional[OperationLaborClaim],
    audit_input: ShiftAuditInput,
) -> TechnologicalCheckFinding:
    disc = _discipline_blob(claim or _dummy_claim(line.original_operation_text), audit_input)

    if not disc:
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
            line=line,
            claim=claim,
            check_type=rule.check_type,
            rule=rule,
            applicability=ApplicabilityVerdict.UNKNOWN,
            check_result=TechCheckResult.INSUFFICIENT_CONTEXT,
            supporting_evidence=(f"operation_code={line.operation_code_candidate}",),
            missing_evidence=("construction_discipline_or_work_kind",),
            professional_explanation=(
                "Вид работ / дисциплина не указаны — применимость операции к работе "
                "не доказана."
            ),
            clarification_request="Укажите вид работ / construction_discipline.",
        )
    if _has_any_token(disc, rule.discipline_exclude_tokens):
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
            line=line,
            claim=claim,
            check_type=rule.check_type,
            rule=rule,
            applicability=ApplicabilityVerdict.NOT_APPLICABLE,
            check_result=TechCheckResult.PROVEN_CONTRADICTION,
            supporting_evidence=(
                f"discipline_blob={disc[:80]}",
                "matched_exclude_token",
            ),
            missing_evidence=(),
            professional_explanation=(
                "Заявленная дисциплина/вид работ противоречит применимости "
                "теплоизоляционной операции (demonstration rule)."
            ),
            clarification_request="Проверьте соответствие операции и вида работ.",
        )
    if _has_any_token(disc, rule.discipline_include_tokens):
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
            line=line,
            claim=claim,
            check_type=rule.check_type,
            rule=rule,
            applicability=ApplicabilityVerdict.APPLICABLE,
            check_result=TechCheckResult.CONSISTENT_WITH_CHECKED_RULE,
            supporting_evidence=(
                f"discipline_blob={disc[:80]}",
                f"operation_code={line.operation_code_candidate}",
            ),
            missing_evidence=(),
            professional_explanation=(
                "Операция согласуется с заявленной дисциплиной изоляции "
                "в пределах проверенного demonstration rule."
            ),
            clarification_request=None,
        )
    return _base_finding(
        check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
        line=line,
        claim=claim,
        check_type=rule.check_type,
        rule=rule,
        applicability=ApplicabilityVerdict.UNKNOWN,
        check_result=TechCheckResult.INSUFFICIENT_CONTEXT,
        supporting_evidence=(f"discipline_blob={disc[:80]}",),
        missing_evidence=("discipline_tokens_matching_insulation_domain",),
        professional_explanation=(
            "Дисциплина указана, но не сопоставлена с доменом изоляции "
            "demonstration rule — вывод о применимости не сделан."
        ),
        clarification_request="Уточните вид работ относительно теплоизоляции.",
    )


def _eval_material_applicability(
    rule: TechnologicalRule,
    line: OperationClassificationLine,
    claim: Optional[OperationLaborClaim],
) -> TechnologicalCheckFinding:
    # Explicit material fields outweigh tokens that appear only in operation names
    # (e.g. «покров» in canonical cladding title must not hide a rockwool-only hint).
    explicit_mat = normalize_operation_text(
        " ".join(
            p
            for p in (
                (claim.material_hint if claim else None) or "",
                (claim.boq_name if claim else None) or "",
            )
            if p
        )
    )
    blob = _material_blob(claim or _dummy_claim(line.original_operation_text), line)
    mat_focus = explicit_mat or blob
    has_include = _has_any_token(mat_focus, rule.material_include_tokens)
    has_exclude = _has_any_token(mat_focus, rule.material_exclude_tokens)
    # When explicit material is present, judge include/exclude on it alone
    if explicit_mat:
        has_include = _has_any_token(explicit_mat, rule.material_include_tokens)
        has_exclude = _has_any_token(explicit_mat, rule.material_exclude_tokens)
    material_explicit = bool(explicit_mat)

    if rule.rule_id.endswith("CUTTING_ELASTOMER"):
        if has_exclude and not has_include:
            return _base_finding(
                check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
                line=line,
                claim=claim,
                check_type=rule.check_type,
                rule=rule,
                applicability=ApplicabilityVerdict.NOT_APPLICABLE,
                check_result=TechCheckResult.NOT_APPLICABLE,
                supporting_evidence=(f"material_blob={mat_focus[:100]}", "exclude_material_tokens"),
                missing_evidence=(),
                professional_explanation=(
                    "Правило раскроя эластомера неприменимо к заявленному "
                    "минераловатному / иному материалу (технологии не переносятся)."
                ),
                clarification_request=(
                    "Укажите применимое правило раскроя для данного материала "
                    "или уточните материал."
                ),
            )
        if has_include:
            return _base_finding(
                check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
                line=line,
                claim=claim,
                check_type=rule.check_type,
                rule=rule,
                applicability=ApplicabilityVerdict.APPLICABLE,
                check_result=TechCheckResult.CONSISTENT_WITH_CHECKED_RULE,
                supporting_evidence=(f"material_blob={mat_focus[:100]}", "elastomer_tokens"),
                missing_evidence=(),
                professional_explanation=(
                    "Материальный контекст согласуется с demonstration rule "
                    "раскроя эластомерной изоляции."
                ),
                clarification_request=None,
            )
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
            line=line,
            claim=claim,
            check_type=rule.check_type,
            rule=rule,
            applicability=ApplicabilityVerdict.UNKNOWN,
            check_result=TechCheckResult.INSUFFICIENT_CONTEXT,
            supporting_evidence=(f"material_blob={mat_focus[:100] or '∅'}",),
            missing_evidence=("material_hint_for_cutting_rule",),
            professional_explanation="Материал для проверки применимости раскроя неизвестен.",
            clarification_request="Укажите материал теплоизоляции (каучук/K-FLEX/минвата и т.п.).",
        )

    # Cladding system rule
    if has_exclude and not has_include:
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
            line=line,
            claim=claim,
            check_type=rule.check_type,
            rule=rule,
            applicability=ApplicabilityVerdict.APPLICABLE,
            check_result=TechCheckResult.PROVEN_CONTRADICTION,
            supporting_evidence=(
                f"material_blob={mat_focus[:100]}",
                "mineral_wool_without_cladding_tokens",
            ),
            missing_evidence=("cladding_system_material_evidence",),
            professional_explanation=(
                "Заявлено покрытие/cladding, но материальный контекст указывает "
                "минераловатную систему без покровного слоя — contradiction "
                "в пределах demonstration rule."
            ),
            clarification_request="Уточните систему покровного слоя / материал покрытия.",
        )
    if has_include:
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
            line=line,
            claim=claim,
            check_type=rule.check_type,
            rule=rule,
            applicability=ApplicabilityVerdict.APPLICABLE,
            check_result=TechCheckResult.CONSISTENT_WITH_CHECKED_RULE,
            supporting_evidence=(f"material_blob={mat_focus[:100]}", "cladding_tokens"),
            missing_evidence=(),
            professional_explanation=(
                "Материальный/покровный контекст согласуется с checked "
                "demonstration rule для cladding."
            ),
            clarification_request=None,
        )
    if not material_explicit and not has_include:
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
            line=line,
            claim=claim,
            check_type=rule.check_type,
            rule=rule,
            applicability=ApplicabilityVerdict.UNKNOWN,
            check_result=TechCheckResult.INSUFFICIENT_CONTEXT,
            supporting_evidence=(f"operation_text={line.original_operation_text[:80]}",),
            missing_evidence=("material_hint_or_covering_system",),
            professional_explanation=(
                "Для монтажа покровного слоя недостаточно явного материального "
                "контекста вне текста операции."
            ),
            clarification_request="Укажите материал / систему покрытия.",
        )
    # Operation text may still carry cladding product tokens (e.g. AL CLAD AD)
    if not material_explicit and _has_any_token(blob, rule.material_include_tokens):
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
            line=line,
            claim=claim,
            check_type=rule.check_type,
            rule=rule,
            applicability=ApplicabilityVerdict.APPLICABLE,
            check_result=TechCheckResult.CONSISTENT_WITH_CHECKED_RULE,
            supporting_evidence=(f"operation_text_tokens={blob[:100]}", "cladding_tokens"),
            missing_evidence=(),
            professional_explanation=(
                "Продукт/покрытие упомянуты в тексте операции; согласуется с "
                "demonstration rule (явный material_hint отсутствует)."
            ),
            clarification_request=None,
        )
    return _base_finding(
        check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
        line=line,
        claim=claim,
        check_type=rule.check_type,
        rule=rule,
        applicability=ApplicabilityVerdict.UNKNOWN,
        check_result=TechCheckResult.INSUFFICIENT_CONTEXT,
        supporting_evidence=(f"material_blob={mat_focus[:100]}",),
        missing_evidence=("clear_cladding_or_exclude_evidence",),
        professional_explanation="Материальный контекст cladding неоднозначен.",
        clarification_request="Уточните материал покровного слоя.",
    )


def _eval_prerequisite(
    rule: TechnologicalRule,
    line: OperationClassificationLine,
    claim: Optional[OperationLaborClaim],
    current_prereq_ops: Sequence[tuple[str, Optional[str]]],
    prior: Sequence[PriorOperationEvidence],
) -> TechnologicalCheckFinding:
    """Prerequisite CONSISTENT only with shared physical-object identity.

    Presence of adhesive/install somewhere in the same shift is NOT sufficient:
    those operations may belong to another pipe / segment / equipment item.
    """
    obj = ((claim.physical_object_hint if claim else None) or "").strip() or None
    same_shift_any = sorted(
        {
            code
            for code, _pobj in current_prereq_ops
            if code in rule.prerequisite_codes
        }
    )
    if not obj:
        missing = (
            "physical_object_hint_on_checked_operation",
            *tuple(f"prerequisite:{c}" for c in rule.prerequisite_codes),
        )
        evidence = (
            ("same_shift_prereq_codes_without_object_link:" + ",".join(same_shift_any),)
            if same_shift_any
            else ("no_object_identity_for_prerequisite_link",)
        )
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
            line=line,
            claim=claim,
            check_type=rule.check_type,
            rule=rule,
            applicability=ApplicabilityVerdict.APPLICABLE,
            check_result=TechCheckResult.INSUFFICIENT_CONTEXT,
            supporting_evidence=evidence,
            missing_evidence=missing,
            professional_explanation=(
                "Наличие предшествующих операций в смене не доказывает их выполнение "
                "для проверяемого объекта: идентичность физического объекта не "
                "подтверждена. MISSING EVIDENCE ≠ PROVEN VIOLATION."
            ),
            clarification_request=(
                "Укажите physical_object_hint на проверяемой и предшествующих "
                "операциях (тот же трубопровод / участок / оборудование)."
            ),
        )

    current_hits = sorted(
        {
            code
            for code, pobj in current_prereq_ops
            if code in rule.prerequisite_codes and (pobj or "").strip() == obj
        }
    )
    prior_hits = [
        p
        for p in prior
        if p.operation_code in rule.prerequisite_codes
        and (p.physical_object_hint or "").strip() == obj
    ]
    if current_hits or prior_hits:
        evidence = [f"shared_physical_object={obj}"]
        if current_hits:
            evidence.append("current_shift_prereq_same_object:" + ",".join(current_hits))
        for p in prior_hits[:3]:
            evidence.append(
                f"prior:{p.operation_code}@{p.work_date}"
                f"/object={p.physical_object_hint}"
                f"{'/crew=' + p.crew_id if p.crew_id else ''}"
            )
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
            line=line,
            claim=claim,
            check_type=rule.check_type,
            rule=rule,
            applicability=ApplicabilityVerdict.APPLICABLE,
            check_result=TechCheckResult.CONSISTENT_WITH_CHECKED_RULE,
            supporting_evidence=tuple(evidence),
            missing_evidence=(),
            professional_explanation=(
                "Предшествующий контекст подтверждён на том же физическом объекте "
                "(demonstration rule). Presence-in-shift alone was not used."
            ),
            clarification_request=None,
        )

    cross_object_or_unlinked = sorted(
        {
            f"{code}:{(pobj or '∅')}"
            for code, pobj in current_prereq_ops
            if code in rule.prerequisite_codes and (pobj or "").strip() != obj
        }
    )
    evidence = [f"checked_object={obj}", "no_same_object_prerequisite_evidence"]
    if cross_object_or_unlinked:
        evidence.append(
            "other_object_or_unlinked_prereq_in_shift:"
            + ",".join(cross_object_or_unlinked[:5])
        )
    return _base_finding(
        check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
        line=line,
        claim=claim,
        check_type=rule.check_type,
        rule=rule,
        applicability=ApplicabilityVerdict.APPLICABLE,
        check_result=TechCheckResult.INSUFFICIENT_CONTEXT,
        supporting_evidence=tuple(evidence),
        missing_evidence=tuple(
            f"prerequisite_same_object:{c}" for c in rule.prerequisite_codes
        ),
        professional_explanation=(
            "Предшествующие операции в смене/истории не связаны доказанно с тем же "
            "физическим объектом (другой трубопровод/участок/оборудование или "
            "объект не указан). Это НЕ доказательство нарушения технологии."
        ),
        clarification_request=(
            "Свяжите prerequisite и проверяемую операцию одним physical_object_hint "
            "или предоставьте prior-shift evidence с тем же объектом."
        ),
    )


def _eval_sequence(
    rule: TechnologicalRule,
    line: OperationClassificationLine,
    claim: Optional[OperationLaborClaim],
    audit_input: ShiftAuditInput,
    s10: ShiftOperationClassificationArtifact,
) -> TechnologicalCheckFinding:
    if claim is None or not claim.physical_object_hint:
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
            line=line,
            claim=claim,
            check_type=rule.check_type,
            rule=rule,
            applicability=ApplicabilityVerdict.NOT_APPLICABLE,
            check_result=TechCheckResult.NOT_EVALUATED,
            supporting_evidence=("row_order_is_not_chronology",),
            missing_evidence=("physical_object_hint", "execution_event_time"),
            professional_explanation=(
                "Sequence check не выполнен: нет идентичности физического объекта "
                "и/или подтверждённых временных маркеров. Порядок строк отчёта "
                "не используется как хронология."
            ),
            clarification_request=(
                "Укажите physical_object_hint и execution_event_time для связанных операций."
            ),
        )

    obj = claim.physical_object_hint
    before_code = rule.sequence_before_code
    after_code = rule.sequence_after_code
    before_claim: Optional[OperationLaborClaim] = None
    after_claim: Optional[OperationLaborClaim] = claim

    for other_line, other_claim in zip(s10.classifications, audit_input.operations):
        if other_line.operation_code_candidate != before_code:
            continue
        if other_claim.physical_object_hint != obj:
            continue
        before_claim = other_claim
        break

    if before_claim is None:
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
            line=line,
            claim=claim,
            check_type=rule.check_type,
            rule=rule,
            applicability=ApplicabilityVerdict.APPLICABLE,
            check_result=TechCheckResult.INSUFFICIENT_CONTEXT,
            supporting_evidence=(
                f"physical_object={obj}",
                "row_order_is_not_chronology",
            ),
            missing_evidence=(f"same_object_operation:{before_code}", "execution_event_time"),
            professional_explanation=(
                "На том же объекте нет подтверждённой предшествующей операции "
                f"{before_code} в текущей смене. Отсутствие ≠ нарушение; "
                "операция могла быть в другой смене."
            ),
            clarification_request="Добавьте prior-shift evidence или временные маркеры.",
        )

    t_before = _parse_iso_sortable(_execution_event_time(before_claim) or "")
    t_after = _parse_iso_sortable(_execution_event_time(after_claim) or "")
    if not t_before or not t_after:
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
            line=line,
            claim=claim,
            check_type=rule.check_type,
            rule=rule,
            applicability=ApplicabilityVerdict.APPLICABLE,
            check_result=TechCheckResult.INSUFFICIENT_CONTEXT,
            supporting_evidence=(
                f"physical_object={obj}",
                "same_object_pair_found",
                "row_order_is_not_chronology",
            ),
            missing_evidence=("execution_event_time_on_both_operations",),
            professional_explanation=(
                "Пара операций на одном объекте найдена, но нет подтверждённых "
                "временных маркеров исполнения — последовательность не оценивается "
                "по порядку строк."
            ),
            clarification_request="Добавьте execution_event_time=ISO-8601 в notes/comment.",
        )

    if t_before <= t_after:
        return _base_finding(
            check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
            line=line,
            claim=claim,
            check_type=rule.check_type,
            rule=rule,
            applicability=ApplicabilityVerdict.APPLICABLE,
            check_result=TechCheckResult.CONSISTENT_WITH_CHECKED_RULE,
            supporting_evidence=(
                f"object={obj}",
                f"before={before_code}@{t_before}",
                f"after={after_code}@{t_after}",
            ),
            missing_evidence=(),
            professional_explanation=(
                "Подтверждённая временная последовательность на одном объекте "
                "согласуется с demonstration rule."
            ),
            clarification_request=None,
        )
    return _base_finding(
        check_identity=f"s02:{line.source_operation_identity}:{rule.rule_id}",
        line=line,
        claim=claim,
        check_type=rule.check_type,
        rule=rule,
        applicability=ApplicabilityVerdict.APPLICABLE,
        check_result=TechCheckResult.PROVEN_CONTRADICTION,
        supporting_evidence=(
            f"object={obj}",
            f"before={before_code}@{t_before}",
            f"after={after_code}@{t_after}",
        ),
        missing_evidence=(),
        professional_explanation=(
            "Временные маркеры на одном физическом объекте противоречат "
            "требуемой последовательности (demonstration rule)."
        ),
        clarification_request="Проверьте фактический порядок исполнения на объекте.",
    )


def _rules_for_code(operation_code: Optional[str]) -> list[TechnologicalRule]:
    if not operation_code:
        return []
    return [r for r in INSULATION_TECH_RULES if operation_code in r.operation_codes]


def evaluate_s02(
    audit_input: ShiftAuditInput,
    s10: ShiftOperationClassificationArtifact,
    *,
    audit_id: Optional[str] = None,
    run_id: Optional[str] = None,
    prior_operation_evidence: Sequence[PriorOperationEvidence] = (),
    tech_rules_available: bool = True,
) -> ShiftTechnologicalIntegrityArtifact:
    findings: list[TechnologicalCheckFinding] = []
    current_prereq_ops: list[tuple[str, Optional[str]]] = []
    for c_line in s10.classifications:
        if c_line.classification_status not in {
            ClassificationStatus.EXACT_MATCH,
            ClassificationStatus.NORMALIZED_MATCH,
        }:
            continue
        if not c_line.operation_code_candidate:
            continue
        c_claim = _claim_for_line(audit_input, c_line)
        current_prereq_ops.append(
            (
                c_line.operation_code_candidate,
                (c_claim.physical_object_hint if c_claim else None),
            )
        )

    if not tech_rules_available:
        for line in s10.classifications:
            claim = _claim_for_line(audit_input, line)
            findings.append(
                _base_finding(
                    check_identity=f"s02:{line.source_operation_identity}:no_source",
                    line=line,
                    claim=claim,
                    check_type=TechCheckType.CONTEXT_SUFFICIENCY,
                    rule=None,
                    applicability=ApplicabilityVerdict.UNKNOWN,
                    check_result=TechCheckResult.INSUFFICIENT_CONTEXT,
                    supporting_evidence=("tech_rules_available=false",),
                    missing_evidence=("authoritative_or_demonstration_tech_ruleset",),
                    professional_explanation=(
                        "Технологический источник / ruleset отсутствует — "
                        "технологическая проверка не выполняется."
                    ),
                    clarification_request="Предоставьте технологические требования с provenance.",
                )
            )
    else:
        for line in s10.classifications:
            claim = _claim_for_line(audit_input, line)
            gated = _gate_from_classification(line, claim)
            if gated is not None:
                findings.append(gated)
                continue
            rules = _rules_for_code(line.operation_code_candidate)
            if not rules:
                findings.append(
                    _base_finding(
                        check_identity=f"s02:{line.source_operation_identity}:no_rule",
                        line=line,
                        claim=claim,
                        check_type=TechCheckType.CONTEXT_SUFFICIENCY,
                        rule=None,
                        applicability=ApplicabilityVerdict.UNKNOWN,
                        check_result=TechCheckResult.INSUFFICIENT_CONTEXT,
                        supporting_evidence=(
                            f"operation_code={line.operation_code_candidate}",
                        ),
                        missing_evidence=("applicable_technological_rule",),
                        professional_explanation=(
                            "Для классифицированной операции нет применимого "
                            "технологического правила в working ruleset."
                        ),
                        clarification_request="Добавьте правило с provenance или уточните операцию.",
                    )
                )
                continue
            for rule in rules:
                if rule.check_type == TechCheckType.OPERATION_APPLICABILITY:
                    findings.append(
                        _eval_operation_applicability(rule, line, claim, audit_input)
                    )
                elif rule.check_type == TechCheckType.MATERIAL_APPLICABILITY:
                    findings.append(_eval_material_applicability(rule, line, claim))
                elif rule.check_type == TechCheckType.PREREQUISITE:
                    findings.append(
                        _eval_prerequisite(
                            rule,
                            line,
                            claim,
                            current_prereq_ops,
                            prior_operation_evidence,
                        )
                    )
                elif rule.check_type == TechCheckType.SEQUENCE:
                    findings.append(
                        _eval_sequence(rule, line, claim, audit_input, s10)
                    )

    demo_count = sum(1 for f in findings if f.demonstration_rule)
    production_rule_findings = sum(
        1
        for f in findings
        if f.source_authority
        and f.source_authority != SourceAuthority.DEMONSTRATION_RULE
        and f.applicable_rule_id
    )
    observations = [
        "S02 = deterministic technological integrity skill (no LLM in this increment).",
        "TECHNOLOGICAL VALIDATION ≠ PHYSICAL EXECUTION PROOF.",
        "TECHNOLOGICAL VALIDATION ≠ SHIFT ACCEPTANCE.",
        "CLASSIFICATION ≠ TECHNOLOGICAL VALIDATION.",
        "MISSING EVIDENCE ≠ PROVEN VIOLATION.",
        "WORK ≠ OPERATION ≠ EXECUTION EVENT.",
        "Row order is never treated as execution chronology.",
        "Same-shift presence ≠ same-object prerequisite proof.",
        f"Ruleset: {INSULATION_TECH_RULESET_VERSION} — DEMONSTRATION rules unless revised.",
        f"Engine rules: {S02_RULES_VERSION}.",
        "S02_ENGINE_IMPLEMENTED · DEMONSTRATION_RULES_PROVEN · "
        "PRODUCTION_KNOWLEDGE_NOT_READY · PRODUCTION_VALIDATION_NOT_PROVEN.",
        "Passing one checked rule does NOT certify the whole technology of the shift.",
        "Demonstration findings are NOT production technological approval, "
        "NOT approved engineering requirements, and NOT a basis for shift rejection.",
        f"demonstration_findings={demo_count}; non_demo_rule_findings={production_rule_findings}.",
    ]
    if demo_count:
        observations.append(
            "One or more findings cite DEMONSTRATION_RULE — not approved production technology."
        )

    counts: dict[str, int] = {}
    for f in findings:
        counts[f.check_result.value] = counts.get(f.check_result.value, 0) + 1

    summary_lines = [
        "PSAA S02 — Technological Integrity (deterministic)",
        f"Проект: {audit_input.project_code} date={audit_input.work_date} crew={audit_input.crew_id}",
        "Managerial acceptance: NOT_IN_SCOPE",
        "Technological validation scope: CHECKED_RULES_ONLY",
        "Readiness: S02_ENGINE_IMPLEMENTED | DEMONSTRATION_RULES_PROVEN | "
        "PRODUCTION_KNOWLEDGE_NOT_READY | PRODUCTION_VALIDATION_NOT_PROVEN",
        "Status counts: "
        + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
    ]
    for f in findings:
        summary_lines.append(
            f"- «{f.original_operation_text}» | {f.applicable_rule_id or '—'} | "
            f"{f.check_result.value} | demo={f.demonstration_rule}"
        )

    return ShiftTechnologicalIntegrityArtifact(
        schema_version=S02_ARTIFACT_SCHEMA_VERSION,
        rules_version=S02_RULES_VERSION,
        tech_ruleset_version=INSULATION_TECH_RULESET_VERSION,
        audit_id=audit_id or s10.audit_id or str(uuid.uuid4()),
        agent_code=AGENT_CODE,
        agent_version=AGENT_VERSION,
        run_id=run_id,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        project_code=audit_input.project_code,
        work_date=audit_input.work_date,
        crew_id=audit_input.crew_id,
        evaluation_domain="insulation_demonstration_tech_rules",
        findings=tuple(findings),
        observations=tuple(observations),
        managerial_acceptance_status="NOT_IN_SCOPE",
        technological_validation_scope="CHECKED_RULES_ONLY_NOT_FULL_TECHNOLOGY",
        human_readable_summary="\n".join(summary_lines),
        s02_engine_status="S02_ENGINE_IMPLEMENTED",
        demonstration_rules_status="DEMONSTRATION_RULES_PROVEN",
        production_knowledge_status="PRODUCTION_KNOWLEDGE_NOT_READY",
        production_validation_status="PRODUCTION_VALIDATION_NOT_PROVEN",
    )
