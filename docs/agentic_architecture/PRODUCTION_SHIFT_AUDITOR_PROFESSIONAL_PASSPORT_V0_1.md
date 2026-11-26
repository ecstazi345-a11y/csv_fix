# Профессиональный паспорт цифрового сотрудника
# Production Shift Auditor Agent (PSAA)

**Document:** PRODUCTION_SHIFT_AUDITOR_PROFESSIONAL_PASSPORT_V0_1
**Version:** v0.1 (S01 + local Audit History + S10 + S02 + S03 + S11 + S04 + S05 + S06 + S07 + S08 + S09 engines proven)
**Status:** S01 + PSAA-02 local history + S10 + S02 + S03 + S11 + S04 + S05 + S06 + S07 + S08 + S09 engines CURRENT / PROVEN · **11 of 12 professional skill engines implemented** (engine count ≠ production readiness) · operation/shift recommendation generation PROVEN · finding consolidation PROVEN · labor conservation PROVEN · positive physical acceptance recommendation NOT PROVEN · production acceptance policy NOT READY · production acceptance recommendation NOT PROVEN · managerial acceptance NOT PERFORMED · contractual recognition NOT PERFORMED · evidence metadata validation PROVEN within tested scope · typed spatial reference compatibility PROVEN · multiple-representation identity handling PROVEN within tested scope · demonstration remaining-quantity check PROVEN · production evidence validation NOT PROVEN · evidence content validation NOT IMPLEMENTED · geometric overlap engine NOT IMPLEMENTED · physical execution NOT VERIFIED · demonstration hypothesis generation PROVEN · typed causal context PROVEN within tested scope · production root-cause proof NOT PROVEN · ESTABLISHED_CAUSE = NO · descriptive statistics PROVEN · historical anomaly-candidate method PROVEN within demo fixtures · production statistical anomaly NOT PROVEN · VIOLATION_NOT_PROVEN · mathematical time balance COMPUTABLE · conditional duration bounds PROVEN · actual chronology NOT VERIFIED · evidence-supported actual participation NOT PROVEN · scenario direct labor cost PROVEN · actual incurred cost NOT PROVEN · full execution cost NOT COMPUTABLE · COST_DEVIATION_BOUNDARIES_ONLY · verified labor observations NOT PROVEN · approved labor norms NOT CREATED · production tech/physical knowledge NOT READY · inspection NOT PROVEN · full auditor NOT COMPLETE · production Supabase persistence NOT COMPLETE · S10/S02/S03/S11/S04/S05/S06/S07/S08/S09 not in durable history
**Standard:** PROFESSIONAL_PASSPORT_TEMPLATE_V1_0
**Checkpoints:** [PSAA_01](PSAA_01_MATHEMATICAL_INTEGRITY_CHECKPOINT.md) · [PSAA_02](PSAA_02_AUDIT_HISTORY_CHECKPOINT.md) · [PSAA_03](PSAA_03_OPERATION_CLASSIFICATION_CHECKPOINT.md) · [PSAA_04](PSAA_04_TECHNOLOGICAL_INTEGRITY_CHECKPOINT.md) · [PSAA_05](PSAA_05_PHYSICAL_INTEGRITY_CHECKPOINT.md) · [PSAA_06](PSAA_06_LABOR_BENCHMARK_CHECKPOINT.md) · [PSAA_07](PSAA_07_EXECUTION_COST_CHECKPOINT.md) · [PSAA_08](PSAA_08_TEMPORAL_INTEGRITY_CHECKPOINT.md) · [PSAA_09](PSAA_09_STATISTICAL_ANOMALY_CHECKPOINT.md) · [PSAA_10](PSAA_10_ROOT_CAUSE_CHECKPOINT.md) · [PSAA_11](PSAA_11_EVIDENCE_VALIDATION_CHECKPOINT.md) · [PSAA_12](PSAA_12_SHIFT_ACCEPTANCE_CHECKPOINT.md)
**Latest code commit:** `bdf17a19c7b7cb91ced06125c8df86129455480f`
**Branch:** `wip/increment-11c-persistent-shadow-stores`

---

## 1. Professional Identity

| Поле | Значение |
|------|----------|
| **Код** | `PRODUCTION_SHIFT_AUDITOR` |
| **Имя** | Production Shift Auditor Agent / Цифровой аудитор производственного исполнения |
| **Версия** | 0.1 |
| **Бизнес-контур** | **EXECUTION** |
| **Security tier** | TIER_0_READ_ONLY_DETERMINISTIC |

**Кто:** цифровой аудитор достоверности сменной производственной отчётности.

Будущая рабочая поверхность (TARGET, not built): **Django → Execution → Shift Acceptance** — компактная очередь приёмки, реестр смен, исключения, раскрываемая детализация до звена / работников / договорной позиции / операций / доказательств. Не отдельная карточка на каждую операцию.

## 2. Why / Business Problem

Сменная отчётность содержит заявленные трудозатраты и объёмы. Нужна профессиональная проверка и честная фиксация ограничений данных **до** управленческой приёмки.

## 3. Responsibility

Исследовать достоверность сменной отчётности в пределах реализованных навыков; формировать `ShiftAuditArtifact`; передавать человеку вопросы, требующие решения.

### OWNED (v0.1)
- S01 Mathematical Integrity (детерминированно) — **DONE** (включая Overfund Diagnostic)
- S10 Operation Classification & Normalization (детерминированно) — **DONE** (insulation working catalog; not Operation Registry)
- S02 Technological Integrity engine (детерминированно) — **DONE** (`S02_ENGINE_IMPLEMENTED` · `DEMONSTRATION_RULES_PROVEN`; production knowledge NOT READY)
- S03 Physical Integrity engine (детерминированно) — **DONE** (`S03_ENGINE_IMPLEMENTED` · `DEMONSTRATION_PHYSICAL_RULES_PROVEN`; production physical knowledge NOT READY; inspection NOT PROVEN)
- S11 Labor Benchmark & Observation Eligibility (детерминированно) — **DONE** (`S11_ENGINE_IMPLEMENTED`; verified observations NOT PROVEN; approved norms NOT CREATED)
- S04 Execution Cost Analysis (детерминированно) — **DONE** (`S04_ENGINE_IMPLEMENTED`; scenario direct labor PROVEN; actual incurred / full cost NOT PROVEN)
- S05 Temporal Integrity (детерминированно) — **DONE** (`S05_ENGINE_IMPLEMENTED`; time balance COMPUTABLE; conditional bounds PROVEN; actual chronology / evidence-supported participation NOT PROVEN)
- S06 Statistical Anomaly Detection (детерминированно) — **DONE** (`S06_ENGINE_IMPLEMENTED`; descriptive statistics PROVEN; demo historical anomaly-candidate method PROVEN; production statistical anomaly NOT PROVEN; VIOLATION_NOT_PROVEN)
- S07 Root Cause Analysis (детерминированно) — **DONE** (`S07_ENGINE_IMPLEMENTED`; demonstration hypothesis generation PROVEN; typed causal context PROVEN within tested scope; production root-cause proof NOT PROVEN; ESTABLISHED_CAUSE = NO)
- S08 Evidence Validation (детерминированно) — **DONE** (`S08_ENGINE_IMPLEMENTED`; evidence metadata validation PROVEN within tested scope; typed spatial compatibility PROVEN; production evidence / content / geometric overlap / physical execution NOT PROVEN)
- S09 Shift Acceptance Recommendation (детерминированно) — **DONE** (`S09_ENGINE_IMPLEMENTED`; operation/shift recommendation + finding consolidation PROVEN; positive physical / production acceptance / managerial acceptance NOT PROVEN)
- Узкий trusted READ adapter (replaceable; legacy `daily_progress_active`)
- Структурированный профессиональный артефакт с provenance
- Append-only local Audit History (PSAA-02) — **DONE** (SQLite / in-memory; not production Supabase; S10/S02/S03/S11/S04/S05/S06/S07/S08/S09 not persisted yet)

### SHARED
- EOS-SEC AgentExecutionContext / trusted READ + controlled artifact persist
- Observability event contracts (Class-A lifecycle, best-effort)
- Целевой производительный фонд 8 чел·ч/чел (как в планировании) — не табельный фонд

### NOT OWNED
- Constructor Agent / месячное планирование
- Accept/reject смены
- Operation Registry / Labor Intelligence / TCE / зарплата
- Product WRITE в производственные таблицы / Airtable
- LLM reasoning · Django UI

## 4. Fundamental principles

| Principle | Meaning |
|-----------|---------|
| SOURCE-NEUTRAL | Core = `ShiftAuditInput` / `ShiftAuditArtifact`; adapters replaceable |
| EXECUTOR-NEUTRAL | Professional logic ≠ UI ≠ specific runtime host |
| MULTI-SHIFT / MULTI-CREW / MULTI-WORK | One audit grain ≠ assumption of single work type; no silent cross-grain mix |
| EXCEPTION-DRIVEN MANAGEMENT | Compact exceptions + drill-down; not one card per operation |
| APPEND-ONLY HISTORY | CURRENT for local durable store; production Supabase path NOT COMPLETE |
| HUMAN GATE | Managerial acceptance is human; not automatic |

**Separately model (never collapse into one status):**

1. проверка / целостность данных
2. достоверность физического исполнения
3. управленческая приёмка
4. контрактная приёмка
5. себестоимость
6. начисление вознаграждения

Проверка смены **не** является автоматическим решением по заработной плате.

## 5. Organizational Position

Отдельная профессиональная роль в контуре **EXECUTION**. Не tenant Constructor. Не клонирует Constructor packages, planning state, handoff.

## 6. Mission (v0.1)

По входу `ShiftAuditInput` (fixture или trusted READ) выполнить **S01**, **S10**, **S02**, **S03**, **S11**, **S04**, **S05**, **S06**, **S07**, **S08** и **S09** (joint `assess_shift`), вернуть математический, классификационный, технологический, physical-integrity, labor-benchmark, execution-cost, temporal-integrity, statistical-anomaly, root-cause, evidence-validation и acceptance-recommendation артефакты; при необходимости сохранить append-only **S01** history record (PSAA-02). S10/S02/S03/S11/S04/S05/S06/S07/S08/S09 пока не пишутся в durable history.

## 7. Skills

| Код | Навык | Статус |
|-----|-------|--------|
| S01 | Mathematical Integrity | **DONE / PROVEN** |
| S10 | Operation Classification & Normalization | **DONE / PROVEN** (deterministic; insulation working catalog) |
| S02 | Technological Integrity | **DONE / PROVEN** (engine; demo rules only — production knowledge NOT READY) |
| S03 | Physical Integrity | **DONE / PROVEN** (engine; demo measurability — production physical knowledge / inspection NOT READY) |
| S11 | Labor Benchmark & Observation Eligibility | **DONE / PROVEN** (engine; claimed metrics only — verified observations / approved norms NOT CREATED) |
| S04 | Execution Cost Analysis | **DONE / PROVEN** (engine; scenario direct labor only — actual incurred / full cost NOT PROVEN) |
| S05 | Temporal Integrity | **DONE / PROVEN** (engine; claimed time only — actual chronology / evidence-supported participation NOT PROVEN) |
| S06 | Statistical Anomaly Detection | **DONE / PROVEN** (engine; descriptive + demo historical candidate method — production anomaly NOT PROVEN; VIOLATION_NOT_PROVEN) |
| S07 | Root Cause Analysis | **DONE / PROVEN** (engine; demo hypotheses + typed context — production root cause NOT PROVEN; ESTABLISHED_CAUSE = NO) |
| S08 | Evidence Validation (+ Spatial Execution Evidence direction) | **DONE / PROVEN** (engine; metadata validation + typed spatial compatibility — production evidence / content / geometry / physical execution NOT PROVEN) |
| S09 | Shift Acceptance Recommendation | **DONE / PROVEN** (engine; professional recommendation + exception-driven shared context — positive physical / production acceptance / managerial acceptance NOT PROVEN) |
| S12 | Production Intelligence | **NEXT (PSAA-13)** |

## 8. Tools

| Tool | Политика | Статус |
|------|----------|--------|
| `load_shift_daily_progress` | PUBLISHABLE_READ, allowlisted | CURRENT (legacy adapter) |
| `persist_shift_audit_history` | CONTROLLED_ARTIFACT_PERSIST | CURRENT (local store; Supabase adapter NO) |
| `load_shift_audit_history` | PUBLISHABLE_READ, project-scoped | CURRENT |

Product WRITE tools: **запрещены** (`write_allowed=False`).

## 9. Business Artifact

`ShiftAuditArtifact` — показатели, пооперационная детализация, наблюдения, missing data, questions, раздельные статусы:

- math integrity (`COHERENT` = arithmetic coherence only; **not** absence of deviations; **not** acceptance)
- data completeness
- professional credibility (NOT_EVALUATED в v0.1)
- managerial acceptance (NOT_IN_SCOPE)

History record stores immutable input + S01 artifact snapshots (append-only by `audit_id`).
S10 produces a separate `ShiftOperationClassificationArtifact` (classification ≠ acceptance; catalog ≠ registry).
S02 produces `ShiftTechnologicalIntegrityArtifact` (checked-rule consistency ≠ physical proof ≠ acceptance; demo ≠ approved engineering requirement).
S03 produces `ShiftPhysicalIntegrityArtifact` (claimed quantity/unit/state checks ≠ verified result ≠ inspection; LABOR ≠ PHYSICAL RESULT; MANUFACTURED ≠ INSTALLED ≠ CONTRACT ACCEPTED).
S11 produces `ShiftLaborBenchmarkArtifact` (claimed unit labor / productivity / eligibility / conservation; CLAIMED ≠ VERIFIED ≠ APPROVED NORM; labor without quantity ≠ automatic loss).
S04 produces `ShiftExecutionCostArtifact` (claimed direct labor cost from typed rate; SCENARIO ≠ ACTUAL; DIRECT ≠ FULL COST; UNKNOWN ≠ ZERO; no payroll / margin / revenue).
S05 produces `ShiftTemporalIntegrityArtifact` (S01 time balance reuse; conditional duration bounds under stated assumptions; claimed intervals half-open; chronology NOT_PROVEN; scenario capacity ≠ proven physical conflict; no timesheet / scheduling / fraud).
S06 produces `ShiftStatisticalAnomalyArtifact` (descriptive concentration/rounding; median+MAD modified Z on typed claimed historical refs; ZERO_DISPERSION without ÷0; COST_DEVIATION_BOUNDARIES_ONLY; VIOLATION_NOT_PROVEN; no worker ranking / root cause).
S07 produces `ShiftRootCauseArtifact` (relevant hypotheses from prior findings; typed supporting/contradicting context; evidence requirements; clarification questions/roles; CAUSE_NOT_ESTABLISHED; no autonomous investigation / blame / causal cost allocation).
S08 produces `ShiftEvidenceValidationArtifact` (claimed execution + evidence reference + metadata validation; typed spatial refs; multiple-representation identity; demonstration remaining-quantity; authority ceiling METADATA_VALIDATED; CLAIMED ≠ VERIFIED; METADATA ≠ CONTENT; no geometric overlap / physical verification / acceptance).
S09 produces `ShiftAcceptanceRecommendationArtifact` (operation-level + shift-level professional recommendations; shared context requirements; operation-specific exceptions; finding consolidation with underlying identity / representation_kind / counts_as_independent_proof; status_reason_codes; human decision required; PROFESSIONAL RECOMMENDATION ≠ MANAGERIAL ACCEPTANCE; PARTIAL RECOMMENDATION ≠ PARTIAL ACCEPTANCE; no ACCEPTED/REJECTED quantities).

**Не** ACCEPTED/REJECTED.

## 10. Security / EOS-SEC

- Registry: `PRODUCTION_SHIFT_AUDITOR` в `security/agent_execution_context.py`
- Manifest: `agents/production_shift_auditor/specification/security_manifest.json`
- Credentials только в infrastructure trusted executor
- Master free text = untrusted data
- Observability ≠ product write
- Artifact persist ≠ product write; project isolation; no UPDATE/DELETE via allowlisted API

## 11. Runtime

Тонкий модуль `agents/production_shift_auditor/runtime.py` + history store.
LangGraph / Django — **NOT IMPLEMENTED**.
Local SQLite history — **DONE**. Production Supabase persist — **NOT COMPLETE**.

## 12. Current / Proven vs Target

| | |
|--|--|
| **CURRENT** | S01 DONE; PSAA-02 local durable history DONE (`ff40fb6`); S10 DONE (`a91161f`); S02 engine DONE (`74a528b`); S03 engine DONE (`eb9d9a0`); S11 engine DONE (`252af32`); S04 engine DONE (`e0d5179`); S05 engine DONE (`e7c475c`); S06 engine DONE (`66fb64a`); S07 engine DONE (`aa53122`); S08 engine DONE (`1b092d1`); S09 engine DONE (`bdf17a1`); **11/12 skill engines**; Overfund Diagnostic; EOS-SEC controlled persist |
| **TARGET** | Supabase history adapter + migration apply + live PG proof; S10/S02/S03/S11/S04/S05/S06/S07/S08/S09 in durable history; production tech/physical knowledge; S12 (PSAA-13); Spatial Execution Evidence industrial integration (editor / geometry / BIM / CV); Django Shift Acceptance; Human Gate acceptance; integrate PSAA with existing Agent Runtime, Supabase and live production processes (**no new agent architecture**) |
| **NOT IN SCOPE (v0.1)** | LLM; UI; Constructor changes; Operation Registry; payroll; TCE replacement; auto accept/reject; auto norm/rate approval; margin/revenue; timesheet/scheduling engine; ML anomaly platform; worker ranking; autonomous investigation; causal cost allocation; evidence content validation; geometric overlap engine; physical execution verification; automatic managerial acceptance |

### Limits (mandatory)

- Live labor semantics — **PARTIALLY_PROVEN**
- Legacy `crew_size` may denote allocated resource, not headcount (**PASS with LIMIT**)
- SQL_SCHEMA_READY = YES; SUPABASE_STORAGE_ADAPTER_READY = NO; MIGRATION_APPLIED = NO; LIVE_POSTGRESQL_PERSISTENCE_PROVEN = NO
- SQLite ≠ multi-node production durability
- `absolute_deviation_*` signed semantics — technical debt (version-aware contract correction required)
- S10/S02/S03/S11/S04/S05/S06/S07/S08/S09 not in durable audit history; insulation-only working catalogs; no industrial classification/inspection accuracy proof
- Alias string equality ≠ professional equivalence; catalog candidate ≠ approved Operation Registry
- S02: `PRODUCTION_KNOWLEDGE_NOT_READY` · `PRODUCTION_VALIDATION_NOT_PROVEN`
- S03: `PRODUCTION_PHYSICAL_KNOWLEDGE_NOT_READY` · `PHYSICAL_INSPECTION_NOT_PROVEN`
- S11: `VERIFIED_OBSERVATIONS_NOT_PROVEN` · `APPROVED_LABOR_NORMS_NOT_CREATED` · production Labor Norm READ adapter NOT IMPLEMENTED
- S04: `ACTUAL_COST_NOT_PROVEN` · `FULL_EXECUTION_COST_NOT_COMPUTABLE` · production cost-rate READ adapter NOT IMPLEMENTED · full multi-rate/worker allocation NOT IMPLEMENTED
- S05: `CHRONOLOGY_NOT_PROVEN` · `WORKER_ALLOCATION_NOT_PROVEN` · evidence-supported actual participation NOT PROVEN · live BHK temporal context insufficient · no timesheet/scheduling engine
- S06: `PRODUCTION_STATISTICAL_ANOMALY_NOT_PROVEN` · `COST_DEVIATION_BOUNDARIES_ONLY` · no production historical READ adapter · demonstration thresholds ≠ approved norms · live BHK comparable history insufficient
- S07: `PRODUCTION_ROOT_CAUSE_PROOF_NOT_PROVEN` · `CAUSE_NOT_ESTABLISHED` · no production causal-context READ adapter · demonstration cause catalog ≠ approved KB · live BHK causal context insufficient · autonomous investigation NOT IMPLEMENTED
- S08: `PRODUCTION_EVIDENCE_VALIDATION_NOT_PROVEN` · `EVIDENCE_CONTENT_VALIDATION_NOT_IMPLEMENTED` · `GEOMETRIC_OVERLAP_ENGINE_NOT_IMPLEMENTED` · `PHYSICAL_EXECUTION_NOT_VERIFIED` · no production evidence READ adapter · demonstration requirements ≠ approved production requirements · interactive engineering map NOT IMPLEMENTED · no PDF.js / CAD / BIM / CV integration
- S09: `POSITIVE_PHYSICAL_ACCEPTANCE_RECOMMENDATION_NOT_PROVEN` · `PRODUCTION_ACCEPTANCE_POLICY_NOT_READY` · `PRODUCTION_ACCEPTANCE_RECOMMENDATION_NOT_PROVEN` · `MANAGERIAL_ACCEPTANCE_PERFORMED_NO` · `CONTRACTUAL_RECOGNITION_PERFORMED_NO` · demonstration recommendation policy ≠ approved production policy · RECOMMEND_ACCEPTANCE_WITHIN_VALIDATED_SCOPE reserved · no Django/HITL/Control Room integration
- Quantity not required by current rule ≠ non-measurability; missing geometry ≠ proven unit incompatibility; claimed MANUFACTURED/INSTALLED ≠ verified fact
- Same shift ≠ same physical object; missing evidence ≠ proven violation; demo rule ≠ approved engineering requirement
- CLAIMED UNIT LABOR ≠ VERIFIED ≠ APPROVED NORM; labor without quantity ≠ automatic loss; same operation code ≠ automatic comparability
- CLAIMED LABOR COST ≠ ACTUAL; SCENARIO ≠ APPROVED; DIRECT ≠ FULL; UNKNOWN ≠ ZERO; estimate ≠ payroll
- MAN-MINUTES ≠ ELAPSED; CREW SIZE ≠ ALLOCATION; CLAIMED CHRONOLOGY ≠ VERIFIED; SCENARIO CAPACITY EXCEEDANCE ≠ PROVEN PHYSICAL CONFLICT; UNALLOCATED ≠ IDLE; NO DETECTED CONFLICT ≠ VERIFIED SHIFT
- DESCRIPTIVE ≠ ANOMALY ≠ PROVEN VIOLATION; ROUNDING ≠ FABRICATION; CLAIMED HISTORICAL ≠ VERIFIED; HIGH REVIEW PRIORITY ≠ HIGH EVIDENCE AUTHORITY; ANOMALY SIGNAL ≠ ROOT CAUSE
- ANOMALY ≠ ROOT CAUSE; CORRELATION ≠ CAUSATION; POSSIBLE ≠ ESTABLISHED; SUPPORTING CONTEXT ≠ PROVEN CAUSAL RELATIONSHIP; SUGGESTED ROLE ≠ RESPONSIBLE PARTY
- CLAIMED EXECUTION ≠ VERIFIED EXECUTION; EVIDENCE REFERENCE ≠ VERIFIED CONTENT; METADATA VALIDATION ≠ CONTENT VALIDATION; ATTACHED PHOTO ≠ VERIFIED QUANTITY; ONE PHYSICAL OBJECT ≠ ONE DRAWING REPRESENTATION; SAME OBJECT ≠ DUPLICATE EXECUTION; NO QUANTITY EXCEEDANCE ≠ SPATIAL UNIQUENESS; CONFIRMED PHYSICAL QUANTITY ≠ CONTRACTUALLY ACCEPTED QUANTITY; MISSING HISTORY ≠ ZERO HISTORY; POTENTIAL QUANTITY EXCESS ≠ PAYMENT REJECTION; EVIDENCE VALIDATION ≠ MANAGERIAL ACCEPTANCE
- PROFESSIONAL RECOMMENDATION ≠ MANAGERIAL ACCEPTANCE; PARTIAL RECOMMENDATION ≠ PARTIAL ACCEPTANCE; MANAGERIAL ACCEPTANCE ≠ CONTRACTUAL RECOGNITION; CONTRACTUAL RECOGNITION ≠ PAYROLL AUTHORIZATION; DEMONSTRATION FINDING ≠ APPROVED PRODUCTION BLOCKER; INHERITED REPRESENTATION ≠ INDEPENDENT PROOF; CAUSAL HYPOTHESIS ≠ ESTABLISHED CAUSE; SOFTWARE ENGINE PASS ≠ PRODUCTION VALIDATION; NO DETECTED ISSUE ≠ VERIFIED SHIFT
- Constructor handoff_store / governance baseline string — PRE_EXISTING defects (baseline `2c038a3`)
- Full autonomous auditor — **not created**; 11/12 engines ≠ production readiness

## 13. Failure Conditions

- Смешение project/crew/date/shift → fail-closed
- Конфликт `crew_size` → diagnostic, без суммирования по строкам
- `direct_work_hours` без доказанной семантики → `HOUR_FIELD_UNPROVEN`
- History: same `audit_id` + different content → CONFLICT; cross-project → DENIED; write failure → fail-closed

## 14. Spatial Execution Evidence (S08 direction — product boundary)

**Spatial Execution Evidence** — пространственная фиксация и проверка доказательств
физического исполнения. Составная часть профессии PSAA / навыка **S08 Evidence
Validation**, не отдельный проект и не новый агент РД.

Целевая полевая поверхность мастера (TARGET): интерактивная инженерная карта
вместо обычной постфактум заполняемой таблицы. Мастер фиксирует изменение
состояния физического мира непосредственно на РД.

Multiple representations: PLAN · AXONOMETRY · SECTION · future BIM_MODEL.

Spatial reference types: POINT · LINE · AREA · OBJECT_REFERENCE.

Профессиональные требования (сохранены):

- единый physical object identity;
- лист и ревизия РД;
- геометрическая привязка;
- высотная отметка и её инженерное основание;
- отдельные слои технологических операций;
- история исполнения;
- заявленные и подтверждённые объёмы;
- трудозатраты;
- доказательства;
- предотвращение повторного учёта одного физического результата.

Один физический объект может иметь несколько представлений на РД.
Оригинальная РД остаётся неизменной.
Из execution events в перспективе: сменный отчёт · история исполнения ·
трудозатраты · доказательства · данные для цифровых сотрудников.

**Текущий S08** обеспечивает typed compatibility и limited deterministic
metadata validation (layers A/B/C). Authority ceiling: METADATA_VALIDATED.

**Не объявлено реализованным:** interactive engineering map editor · automated
RD recognition · geometric overlap calculations · cross-revision geometry
mapping · BIM/CAD integration · computer vision · production evidence content
validation. Эти возможности — последующая промышленная интеграция.

Candidate implementation approach (**NOT APPROVED / NOT VERIFIED**):
PDF.js + SVG/Canvas overlay + Django/Supabase.

## 15. Next increment

**PSAA-13 / S12 — Production Intelligence** (not started).

Последний профессиональный навык программы PSAA.

Профессиональная цель: преобразование результатов производственного исполнения
и профессионального аудита в структурированные наблюдения, пригодные для
контролируемого повторного использования.

Предусмотреть: production observation identity · operation-specific labor
observations · observation eligibility · comparable execution conditions ·
physical/technological context · evidence authority · provenance/source
version · historical human decision references · recurring production
constraints · unresolved deviations · reusable knowledge candidates ·
explicit knowledge reuse limitations.

Переиспользовать S11 Labor Benchmark. Не создавать второй механизм расчёта
удельной трудоёмкости.

Различать: claimed observation · audited observation · verified physical
observation · managerial acceptance · reusable knowledge candidate ·
approved production knowledge · approved production labor norm.

CLAIMED OBSERVATION ≠ VERIFIED KNOWLEDGE ·
REPEATED OBSERVATION ≠ APPROVED NORM ·
PROFESSIONAL RECOMMENDATION ≠ HUMAN DECISION ·
ACCEPTED QUANTITY ≠ AUTOMATICALLY VALID BENCHMARK.

Не допускать автоматического превращения непроверенных смен, демонстрационных
правил и причинных гипотез в нормативную базу компании.
Не создавать новую learning architecture, knowledge platform, vector database
или autonomous learning system.

Remaining skill engine after S09: **S12**. После S12 — Professional Core
Completion Checkpoint, затем отдельный прагматичный integration preflight
(existing Agent Runtime, security, Supabase, production data contracts, human
decision boundary, Django Human Surface). **Не** создавать общую агентную
архитектуру заново. **Не** объявлять PSAA промышленно готовым только после
завершения 12 skill engines.

## 16. Passport status

**Initial Passport v0.1** + S01 + PSAA-02 local history + S10 + S02 + S03 + S11 + S04 + S05 + S06 + S07 + S08 + S09 engine evidence (**11 of 12 skill engines**; not production readiness).
Final Passport — после production-grade history, production tech/physical knowledge и расширенного professional proof.
