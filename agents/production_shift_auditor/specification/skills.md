# PSAA Skills

| Code | Name | Status (v0.1) |
|------|------|----------------|
| S01 | Mathematical Integrity | CURRENT / PROVEN |
| S02 | Technological Integrity | TARGET / FUTURE |
| S03 | Physical Integrity | TARGET / FUTURE |
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
