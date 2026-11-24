# PSAA Skills

| Code | Name | Status (v0.1) |
|------|------|----------------|
| S01 | Mathematical Integrity | CURRENT / PROVEN |
| S02 | Technological Integrity | CURRENT / PROVEN (deterministic; insulation demonstration rules) |
| S03 | Physical Integrity | CURRENT / PROVEN (deterministic; insulation demonstration measurability) |
| S04 | Operation Cost Analysis | TARGET / FUTURE |
| S05 | Temporal Integrity | TARGET / FUTURE |
| S06 | Statistical Anomalies | TARGET / FUTURE |
| S07 | Causal Investigation | TARGET / FUTURE |
| S08 | Evidence Verification | TARGET / FUTURE |
| S09 | Shift Acceptance Conclusion | TARGET / FUTURE |
| S10 | Operation Classification & Normalization | CURRENT / PROVEN (deterministic, insulation working catalog) |
| S11 | Labor Benchmark Comparison | TARGET / FUTURE |
| S12 | Labor Intelligence Preparation | TARGET / FUTURE |

## S01 — Mathematical Integrity (CURRENT)

Детерминированная проверка математической целостности заявленных трудозатрат смены
относительно целевого производительного фонда звена.

Не сравнивает с нормативами. Не выдаёт ACCEPTED/REJECTED.
`COHERENT` ≠ отсутствие отклонений.

## S02 — Technological Integrity (CURRENT)

Детерминированная проверка технологической обоснованности классифицированных
операций относительно версионируемых правил с provenance.

Вход: `ShiftAuditInput` + артефакт S10 (+ optional prior-shift evidence).
Метод: **deterministic** rule evaluation. LLM не используется.

Статусы: CONSISTENT_WITH_CHECKED_RULE · PROVEN_CONTRADICTION ·
INSUFFICIENT_CONTEXT · NOT_APPLICABLE · NOT_EVALUATED.

Законы: WORK ≠ OPERATION ≠ EXECUTION EVENT ·
CLASSIFICATION ≠ TECHNOLOGICAL VALIDATION ·
TECHNOLOGICAL VALIDATION ≠ PHYSICAL EXECUTION PROOF ·
TECHNOLOGICAL VALIDATION ≠ SHIFT ACCEPTANCE ·
MISSING EVIDENCE ≠ PROVEN VIOLATION ·
alias/catalog match ≠ approved technology ·
row order ≠ chronology ·
demonstration rule ≠ production requirement.

Working ruleset `psaa.s02.insulation_tech_rules.v0.1` — **DEMONSTRATION**
(утверждённые техкарты/инструкции производителя в репозитории отсутствовали).
Одна пройденная проверка ≠ достоверность всей технологии смены.
Prerequisite CONSISTENT только при shared `physical_object_hint`
(наличие операции в смене ≠ доказательство для проверяемого объекта).

Readiness: `S02_ENGINE_IMPLEMENTED` · `DEMONSTRATION_RULES_PROVEN` ·
`PRODUCTION_KNOWLEDGE_NOT_READY` · `PRODUCTION_VALIDATION_NOT_PROVEN`.

## S03 — Physical Integrity (CURRENT)

Детерминированная проверка заявленных физических результатов: количество, единица,
идентичность объекта, состояние результата, риск дубликата, связь с BOQ.

Вход: `ShiftAuditInput` + артефакт S10. Метод: **deterministic**. LLM не используется.

Статусы: CONSISTENT_WITH_CHECKED_RULE · INVALID_QUANTITY · UNIT_INCOMPATIBILITY ·
INSUFFICIENT_CONTEXT · POSSIBLE_DUPLICATE · PROVEN_RECORD_DUPLICATE ·
NOT_APPLICABLE · NOT_EVALUATED.

Законы: LABOR ≠ PHYSICAL RESULT · CLAIMED ≠ VERIFIED · MANUFACTURED ≠ INSTALLED ·
INSTALLED ≠ CONTRACT ACCEPTED · OPERATION QTY ≠ BOQ QTY · PROGRESS ≠ EARNED VALUE ·
MISSING EVIDENCE ≠ PROVEN VIOLATION · SAME DESCRIPTION ≠ SAME OBJECT ·
POSSIBLE DUPLICATE ≠ PROVEN DUPLICATE · no unit conversion without geometry.

Readiness: `S03_ENGINE_IMPLEMENTED` · `DEMONSTRATION_PHYSICAL_RULES_PROVEN` ·
`PRODUCTION_PHYSICAL_KNOWLEDGE_NOT_READY` · `PHYSICAL_INSPECTION_NOT_PROVEN`.

Семантика: quantity not required by current rule ≠ not measurable;
missing geometry ≠ proven unit incompatibility; negative qty rule =
ordinary execution claim only; PROVEN_RECORD_DUPLICATE = within one audit input.

## S10 — Operation Classification & Normalization (CURRENT)

Детерминированная классификация исходных наименований операций на рабочий каталог
теплоизоляционных кандидатов (`psaa.s10.insulation_catalog.v0.1`).

Метод: **deterministic** (aliases + normalization + context tokens). LLM не используется.

Статусы: EXACT_MATCH · NORMALIZED_MATCH · AMBIGUOUS · COMPOSITE_OPERATION ·
UNKNOWN_OPERATION · INSUFFICIENT_CONTEXT.

Законы: ORIGINAL TEXT PRESERVATION · CLASSIFICATION ≠ ACCEPTANCE ·
CLASSIFICATION ≠ TECHNOLOGICAL VALIDATION · NO FABRICATION ·
NO AUTOMATIC TIME DISTRIBUTION · NO AUTOMATIC UNIT CONVERSION ·
NO AUTOMATIC REGISTRY APPROVAL.

Каталог — working example, не утверждённый Operation Registry.
