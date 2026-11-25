# PSAA Skills

| Code | Name | Status (v0.1) |
|------|------|----------------|
| S01 | Mathematical Integrity | CURRENT / PROVEN |
| S02 | Technological Integrity | CURRENT / PROVEN (deterministic; insulation demonstration rules) |
| S03 | Physical Integrity | CURRENT / PROVEN (deterministic; insulation demonstration measurability) |
| S04 | Execution Cost Analysis | CURRENT / PROVEN (deterministic; claimed direct labor only) |
| S05 | Temporal Integrity | CURRENT / PROVEN (deterministic; claimed time only) |
| S06 | Statistical Anomaly Detection | CURRENT / PROVEN (deterministic; claimed signals only) |
| S07 | Causal Investigation | TARGET / FUTURE |
| S08 | Evidence Verification | TARGET / FUTURE |
| S09 | Shift Acceptance Conclusion | TARGET / FUTURE |
| S10 | Operation Classification & Normalization | CURRENT / PROVEN (deterministic, insulation working catalog) |
| S11 | Labor Benchmark & Observation Eligibility | CURRENT / PROVEN (deterministic; claimed metrics only) |
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

## S04 — Execution Cost Analysis (CURRENT)

Детерминированный расчёт **прямых трудовых затрат** по заявленным трудозатратам
операций при явно переданной typed ставке.

Вход: `ShiftAuditInput` + S01/S10/S02/S03/S11 (+ optional `LaborCostRateReference`).
Метод: **deterministic** Decimal. LLM не используется.

`labor_cost = labor_man_hours × applicable_rate`.
Production cost-rate READ adapter: **NOT IMPLEMENTED** — inject rate explicitly.

Статусы: SCENARIO_COST_COMPUTED · ESTIMATED_COST_COMPUTED ·
COST_RATE_NOT_AVAILABLE · COST_RATE_NOT_APPLICABLE · LABOR_SEMANTICS_UNPROVEN ·
UNIT_COST_NOT_COMPUTABLE · COMPOSITE_COST_UNALLOCATED · PARTIAL_COST_COVERAGE.

Законы: CLAIMED ≠ INCURRED ACTUAL · SCENARIO ≠ APPROVED ·
WAGE ≠ EMPLOYER COST · DIRECT ≠ FULL COST · PAID ≠ PRODUCTIVE ·
LABOR WITHOUT QUANTITY ≠ AUTOMATIC FINANCIAL LOSS ·
OPERATION COST ≠ CONTRACT PRICE · PHYSICAL ≠ REVENUE ·
COST ESTIMATION ≠ PAYROLL · UNKNOWN COST ≠ ZERO.

Readiness: `S04_ENGINE_IMPLEMENTED` · `ACTUAL_COST_NOT_PROVEN` ·
`FULL_EXECUTION_COST_NOT_COMPUTABLE`.

## S05 — Temporal Integrity (CURRENT)

Детерминированная оценка временной достоверности заявленного исполнения на трёх
уровнях: (A) математический баланс времени из S01; (B) условная feasibility при
явно обозначенных assumptions; (C) evidence-supported chronology.

Вход: `ShiftAuditInput` + S01/S10/S02/S03/S11/S04 (+ optional
`OperationTemporalClaim` / `ShiftTemporalContext`). Метод: **deterministic**.
LLM не используется. Timestamps и worker allocations не изобретаются.

Статусы: TIME_BALANCE_COMPUTABLE · TEMPORAL_CONTEXT_INSUFFICIENT ·
CONDITIONAL_DURATION_BOUND_COMPUTED · INVALID_TIME_INTERVAL ·
OUTSIDE_KNOWN_SHIFT_INTERVAL · CLAIMED_INTERVAL_OVERLAP ·
EXCLUSIVE_WORKER_ALLOCATION_CONFLICT · SCENARIO_CAPACITY_LIMIT_EXCEEDED ·
CAPACITY_CONFLICT · CHRONOLOGY_NOT_PROVEN · WORKER_ALLOCATION_NOT_PROVEN.

Capacity authority: SCENARIO_ASSUMPTION ≠ CONFIRMED_AVAILABLE_CREW_CAPACITY ≠
EVIDENCE_SUPPORTED_ACTUAL_PARTICIPATION. Half-open intervals `[start, end)`.

Законы: MAN-MINUTES ≠ ELAPSED MINUTES ·
CREW SIZE ≠ ACTUAL OPERATION WORKER ALLOCATION ·
REPORT ROW ORDER ≠ EXECUTION CHRONOLOGY ·
REGISTRATION TIMESTAMP ≠ EXECUTION TIMESTAMP ·
ARITHMETIC LABOR BALANCE ≠ VERIFIED TEMPORAL FEASIBILITY ·
TARGET PRODUCTIVE FUND ≠ ACTUAL ATTENDANCE ·
PARALLEL OPERATIONS ≠ AUTOMATIC TIME CONFLICT ·
OVERLAPPING INTERVALS ≠ AUTOMATIC FRAUD ·
UNALLOCATED TIME ≠ AUTOMATIC IDLE TIME ·
MISSING TIMESTAMPS ≠ PROVEN VIOLATION ·
CONDITIONAL DURATION BOUND ≠ ACTUAL OPERATION DURATION ·
CLAIMED CHRONOLOGY ≠ VERIFIED CHRONOLOGY.

Readiness: `S05_ENGINE_IMPLEMENTED` · `CHRONOLOGY_NOT_PROVEN` ·
`WORKER_ALLOCATION_NOT_PROVEN`.

## S06 — Statistical Anomaly Detection (CURRENT)

Детерминированные статистические сигналы по заявленным производственным
показателям: descriptive observation, configured threshold exceedance,
statistical anomaly candidate при сопоставимой истории.

Вход: joint S01–S05/S10/S11 (+ optional `StatisticalThresholdConfig`,
`ReportingPrecisionPolicy`, `StatisticalReferenceObservation`).
Метод: **deterministic** (median + MAD modified Z). LLM не используется.

Статусы: DESCRIPTIVE_OBSERVATION · THRESHOLD_EXCEEDANCE ·
STATISTICAL_ANOMALY_CANDIDATE · INSUFFICIENT_COMPARABLE_HISTORY ·
REFERENCE_NOT_AVAILABLE · REFERENCE_NOT_COMPARABLE · ZERO_DISPERSION ·
REPORTING_PRECISION_UNKNOWN · REVIEW_REQUIRED · VIOLATION_NOT_PROVEN ·
INHERITED_PROFESSIONAL_FINDING.

Законы: DESCRIPTIVE OBSERVATION ≠ STATISTICAL ANOMALY ·
STATISTICAL ANOMALY ≠ PROVEN VIOLATION ·
COST CONCENTRATION ≠ INEFFICIENCY · ROUNDING ≠ FABRICATION ·
REPEATED VALUE ≠ DUPLICATE EXECUTION ·
BENCHMARK DEVIATION ≠ PROVEN LOSS ·
SMALL SAMPLE ≠ RELIABLE PRODUCTION STANDARD ·
SAME OPERATION CODE ≠ AUTOMATIC COMPARABILITY ·
SCENARIO COST ≠ ACTUAL COST ·
HIGH REVIEW PRIORITY ≠ HIGH EVIDENCE AUTHORITY ·
NO DETECTED ANOMALY ≠ VERIFIED SHIFT ·
MISSING HISTORY ≠ NORMAL PERFORMANCE.

Readiness: `S06_ENGINE_IMPLEMENTED` · `VIOLATION_NOT_PROVEN`.
Production historical READ adapter: **NOT IMPLEMENTED** — typed references only.

## S11 — Labor Benchmark & Observation Eligibility (CURRENT)

Детерминированный расчёт заявленной удельной трудоёмкости / производительности
и пригодности наблюдения для последующего анализа.

Вход: `ShiftAuditInput` + артефакты S01/S10/S02/S03 (+ optional benchmarks /
historical observations). Метод: **deterministic**. LLM не используется.

Статусы расчёта: COMPUTABLE_CLAIMED_OBSERVATION · INSUFFICIENT_DATA ·
INVALID_INPUT · COMPOSITE_NOT_ALLOCATABLE · UNIT_LABOR_NOT_COMPUTABLE ·
LABOR_WITHOUT_POSITIVE_QUANTITY.

Eligibility: HISTORICAL_ANALYSIS_CANDIDATE · COMPUTABLE_BUT_CLAIMED_ONLY ·
NOT_ELIGIBLE_FOR_BENCHMARK.

Comparability: FULL_COMPARABILITY_NOT_PROVEN · COMPARABILITY_CONTEXT_INCOMPLETE ·
BUCKET_COMPARABLE_WITH_LIMITATIONS · NOT_COMPARABLE (code+unit ≠ full
comparability; geometry/physical/technology/conditions required).

Benchmark: BENCHMARK_NOT_AVAILABLE · BENCHMARK_COMPARISON_NOT_APPLICABLE ·
BENCHMARK_COMPARED_CLAIMED_ONLY · BENCHMARK_INCOMPATIBLE.
External inject ≠ approved production norm. Labor Norm READ adapter: not implemented.

Законы: CLAIMED ≠ VERIFIED ≠ APPROVED NORM ·
HISTORICAL AVERAGE ≠ PRODUCTION STANDARD ·
LABOR WITHOUT QUANTITY ≠ AUTOMATIC LOSS ·
PAID LABOR ≠ PRODUCTIVE LABOR ·
BENCHMARK DEVIATION ≠ PROVEN INEFFICIENCY ·
SAME OPERATION CODE ≠ AUTOMATIC COMPARABILITY ·
NO SILENT LABOR CONVERSION · NO COMPOSITE ALLOCATION ·
NO NORM MUTATION · NO INVENTED BENCHMARKS.

Средневзвешенная трудоёмкость = sum(eligible labor) / sum(quantity).
Демонстрационные S02/S03 findings не создают verified observation.
Readiness: `S11_ENGINE_IMPLEMENTED` · `CLAIMED_UNIT_LABOR_COMPUTABLE_WHEN_DATA_ALLOWS` ·
`VERIFIED_OBSERVATIONS_NOT_PROVEN` · `APPROVED_LABOR_NORMS_NOT_CREATED`.
