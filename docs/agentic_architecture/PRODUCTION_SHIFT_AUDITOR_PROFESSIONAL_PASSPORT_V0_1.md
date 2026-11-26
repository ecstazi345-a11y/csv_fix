# Профессиональный паспорт цифрового сотрудника
# Production Shift Auditor Agent (PSAA)

**Document:** PRODUCTION_SHIFT_AUDITOR_PROFESSIONAL_PASSPORT_V0_1
**Version:** v0.1 (S01 + local Audit History + S10 + S02 + S03 + S11 + S04 + S05 + S06 + S07 + S08 + S09 + S12 engines proven · I1 managed runtime DONE)
**Status:** S01 + PSAA-02 local history + S10 + S02 + S03 + S11 + S04 + S05 + S06 + S07 + S08 + S09 + S12 engines CURRENT / PROVEN · **12 of 12 professional skill engines implemented** (engine count ≠ production readiness) · **I1 Managed Runtime Integration DONE** (`c5b5d3d`) · joint 12-skill managed execution PROVEN · headless / threaded managed execution PROVEN · process-local professional result PROVEN · production trusted source acquisition NOT PROVEN · durable runtime restart NOT PROVEN · structured observation generation PROVEN · knowledge candidate generation PROVEN · S11 reuse eligibility integration PROVEN · observation identity handling PROVEN · labor conservation PROVEN · verified production knowledge NOT PROVEN · approved production knowledge NOT CREATED · approved production labor norm NOT CREATED · production knowledge persistence NOT IMPLEMENTED · autonomous learning NOT IMPLEMENTED · operation/shift recommendation generation PROVEN · finding consolidation PROVEN · positive physical acceptance recommendation NOT PROVEN · production acceptance policy NOT READY · production acceptance recommendation NOT PROVEN · managerial acceptance NOT PERFORMED · contractual recognition NOT PERFORMED · evidence metadata validation PROVEN within tested scope · typed spatial reference compatibility PROVEN · multiple-representation identity handling PROVEN within tested scope · demonstration remaining-quantity check PROVEN · production evidence validation NOT PROVEN · evidence content validation NOT IMPLEMENTED · geometric overlap engine NOT IMPLEMENTED · physical execution NOT VERIFIED · demonstration hypothesis generation PROVEN · typed causal context PROVEN within tested scope · production root-cause proof NOT PROVEN · ESTABLISHED_CAUSE = NO · descriptive statistics PROVEN · historical anomaly-candidate method PROVEN within demo fixtures · production statistical anomaly NOT PROVEN · VIOLATION_NOT_PROVEN · mathematical time balance COMPUTABLE · conditional duration bounds PROVEN · actual chronology NOT VERIFIED · evidence-supported actual participation NOT PROVEN · scenario direct labor cost PROVEN · actual incurred cost NOT PROVEN · full execution cost NOT COMPUTABLE · COST_DEVIATION_BOUNDARIES_ONLY · verified labor observations NOT PROVEN · approved labor norms NOT CREATED · production tech/physical knowledge NOT READY · inspection NOT PROVEN · full auditor NOT COMPLETE · production Supabase persistence NOT COMPLETE · S10/S02/S03/S11/S04/S05/S06/S07/S08/S09/S12 not in durable history
**Standard:** PROFESSIONAL_PASSPORT_TEMPLATE_V1_0
**Checkpoints:** [PSAA_01](PSAA_01_MATHEMATICAL_INTEGRITY_CHECKPOINT.md) · [PSAA_02](PSAA_02_AUDIT_HISTORY_CHECKPOINT.md) · [PSAA_03](PSAA_03_OPERATION_CLASSIFICATION_CHECKPOINT.md) · [PSAA_04](PSAA_04_TECHNOLOGICAL_INTEGRITY_CHECKPOINT.md) · [PSAA_05](PSAA_05_PHYSICAL_INTEGRITY_CHECKPOINT.md) · [PSAA_06](PSAA_06_LABOR_BENCHMARK_CHECKPOINT.md) · [PSAA_07](PSAA_07_EXECUTION_COST_CHECKPOINT.md) · [PSAA_08](PSAA_08_TEMPORAL_INTEGRITY_CHECKPOINT.md) · [PSAA_09](PSAA_09_STATISTICAL_ANOMALY_CHECKPOINT.md) · [PSAA_10](PSAA_10_ROOT_CAUSE_CHECKPOINT.md) · [PSAA_11](PSAA_11_EVIDENCE_VALIDATION_CHECKPOINT.md) · [PSAA_12](PSAA_12_SHIFT_ACCEPTANCE_CHECKPOINT.md) · [PSAA_13](PSAA_13_PRODUCTION_INTELLIGENCE_CHECKPOINT.md) · [CORE_V0_1](PSAA_PROFESSIONAL_CORE_COMPLETION_V0_1.md) · [I1](PSAA_I1_MANAGED_RUNTIME_CHECKPOINT.md)
**Latest professional-core code commit:** `35dc6746ef2605f31a9cc13691d7505d955c99ac`
**Latest managed-runtime code commit:** `c5b5d3d8292048e62da23598fdc17827457b13b4`
**Core status:** `PSAA_PROFESSIONAL_CORE_V0_1 = FROZEN` · engines 12/12 · I1 managed runtime DONE · production readiness NOT_PROVEN
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
- S12 Production Intelligence (детерминированно) — **DONE** (`S12_ENGINE_IMPLEMENTED`; structured observations + knowledge candidates PROVEN; verified/approved knowledge NOT CREATED; persistence / autonomous learning NOT IMPLEMENTED)
- Узкий trusted READ adapter (replaceable; legacy `daily_progress_active`)
- Структурированный профессиональный артефакт с provenance
- Append-only local Audit History (PSAA-02) — **DONE** (SQLite / in-memory; not production Supabase; S10/S02/S03/S11/S04/S05/S06/S07/S08/S09/S12 not persisted yet)

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

По входу `ShiftAuditInput` (fixture или trusted READ) выполнить **S01**, **S10**, **S02**, **S03**, **S11**, **S04**, **S05**, **S06**, **S07**, **S08**, **S09** и **S12** (joint `assess_shift`), вернуть математический, классификационный, технологический, physical-integrity, labor-benchmark, execution-cost, temporal-integrity, statistical-anomaly, root-cause, evidence-validation, acceptance-recommendation и production-intelligence артефакты; при необходимости сохранить append-only **S01** history record (PSAA-02). S10/S02/S03/S11/S04/S05/S06/S07/S08/S09/S12 пока не пишутся в durable history.

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
| S12 | Production Intelligence | **DONE / PROVEN** (engine; structured observations + knowledge candidates — verified/approved knowledge NOT CREATED; persistence / autonomous learning NOT IMPLEMENTED) |

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

Тонкий модуль `agents/production_shift_auditor/runtime.py` + history store (S01 path preserved).
**I1 Managed Runtime:** `PsaaManagedRuntimeLauncher` + existing Run Control /
Observability / Query Port — **DONE** (`c5b5d3d`; see
[`PSAA_I1_MANAGED_RUNTIME_CHECKPOINT.md`](PSAA_I1_MANAGED_RUNTIME_CHECKPOINT.md)).
Joint assess_shift S01–S12 via managed path — **PROVEN** (fixture).
Process-local professional result — **YES**; durable 12-skill history — **NO**.
PSAA-specific LangGraph / Django UI — **NOT IMPLEMENTED**.
Local SQLite history (PSAA-02) — **DONE**. Production Supabase persist — **NOT COMPLETE**.

## 12. Current / Proven vs Target

| | |
|--|--|
| **CURRENT** | S01 DONE; PSAA-02 local durable history DONE (`ff40fb6`); S10 DONE (`a91161f`); S02 engine DONE (`74a528b`); S03 engine DONE (`eb9d9a0`); S11 engine DONE (`252af32`); S04 engine DONE (`e0d5179`); S05 engine DONE (`e7c475c`); S06 engine DONE (`66fb64a`); S07 engine DONE (`aa53122`); S08 engine DONE (`1b092d1`); S09 engine DONE (`bdf17a1`); S12 engine DONE (`35dc674`); **12/12 skill engines FROZEN as Professional Core v0.1**; joint fixture execution PROVEN; **I1 managed runtime DONE** (`c5b5d3d`); Overfund Diagnostic; EOS-SEC controlled persist |
| **TARGET** | I2 Supabase & Durable History (trusted production source acquisition + full professional audit durable history / read-back after restart); production tech/physical knowledge; Spatial Execution Evidence industrial integration; Django Shift Acceptance; controlled knowledge reuse after validation/approval (**no new agent architecture**) |
| **NOT IN SCOPE (v0.1)** | LLM; UI; Constructor changes; Operation Registry; payroll; TCE replacement; auto accept/reject; auto norm/rate approval; margin/revenue; timesheet/scheduling engine; ML anomaly platform; vector DB / RAG; worker ranking; autonomous investigation / learning; causal cost allocation; evidence content validation; geometric overlap engine; physical execution verification; automatic managerial acceptance; automatic knowledge approval |

### Limits (mandatory)

- Live labor semantics — **PARTIALLY_PROVEN**
- Legacy `crew_size` may denote allocated resource, not headcount (**PASS with LIMIT**)
- SQL_SCHEMA_READY = YES; SUPABASE_STORAGE_ADAPTER_READY = NO; MIGRATION_APPLIED = NO; LIVE_POSTGRESQL_PERSISTENCE_PROVEN = NO
- SQLite ≠ multi-node production durability
- `absolute_deviation_*` signed semantics — technical debt (version-aware contract correction required)
- S10/S02/S03/S11/S04/S05/S06/S07/S08/S09/S12 not in durable audit history; insulation-only working catalogs; no industrial classification/inspection accuracy proof
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
- S12: `VERIFIED_PRODUCTION_KNOWLEDGE_GENERATION_NOT_PROVEN` · `APPROVED_PRODUCTION_KNOWLEDGE_CREATED_NO` · `APPROVED_PRODUCTION_LABOR_NORM_CREATED_NO` · `PRODUCTION_KNOWLEDGE_PERSISTENCE_IMPLEMENTED_NO` · `AUTONOMOUS_LEARNING_IMPLEMENTED_NO` · knowledge candidate ≠ approved knowledge · suggested reuse ≠ authorized reuse · no second UL engine over S11
- Quantity not required by current rule ≠ non-measurability; missing geometry ≠ proven unit incompatibility; claimed MANUFACTURED/INSTALLED ≠ verified fact
- Same shift ≠ same physical object; missing evidence ≠ proven violation; demo rule ≠ approved engineering requirement
- CLAIMED UNIT LABOR ≠ VERIFIED ≠ APPROVED NORM; labor without quantity ≠ automatic loss; same operation code ≠ automatic comparability
- CLAIMED LABOR COST ≠ ACTUAL; SCENARIO ≠ APPROVED; DIRECT ≠ FULL; UNKNOWN ≠ ZERO; estimate ≠ payroll
- MAN-MINUTES ≠ ELAPSED; CREW SIZE ≠ ALLOCATION; CLAIMED CHRONOLOGY ≠ VERIFIED; SCENARIO CAPACITY EXCEEDANCE ≠ PROVEN PHYSICAL CONFLICT; UNALLOCATED ≠ IDLE; NO DETECTED CONFLICT ≠ VERIFIED SHIFT
- DESCRIPTIVE ≠ ANOMALY ≠ PROVEN VIOLATION; ROUNDING ≠ FABRICATION; CLAIMED HISTORICAL ≠ VERIFIED; HIGH REVIEW PRIORITY ≠ HIGH EVIDENCE AUTHORITY; ANOMALY SIGNAL ≠ ROOT CAUSE
- ANOMALY ≠ ROOT CAUSE; CORRELATION ≠ CAUSATION; POSSIBLE ≠ ESTABLISHED; SUPPORTING CONTEXT ≠ PROVEN CAUSAL RELATIONSHIP; SUGGESTED ROLE ≠ RESPONSIBLE PARTY
- CLAIMED EXECUTION ≠ VERIFIED EXECUTION; EVIDENCE REFERENCE ≠ VERIFIED CONTENT; METADATA VALIDATION ≠ CONTENT VALIDATION; ATTACHED PHOTO ≠ VERIFIED QUANTITY; ONE PHYSICAL OBJECT ≠ ONE DRAWING REPRESENTATION; SAME OBJECT ≠ DUPLICATE EXECUTION; NO QUANTITY EXCEEDANCE ≠ SPATIAL UNIQUENESS; CONFIRMED PHYSICAL QUANTITY ≠ CONTRACTUALLY ACCEPTED QUANTITY; MISSING HISTORY ≠ ZERO HISTORY; POTENTIAL QUANTITY EXCESS ≠ PAYMENT REJECTION; EVIDENCE VALIDATION ≠ MANAGERIAL ACCEPTANCE
- PROFESSIONAL RECOMMENDATION ≠ MANAGERIAL ACCEPTANCE; PARTIAL RECOMMENDATION ≠ PARTIAL ACCEPTANCE; MANAGERIAL ACCEPTANCE ≠ CONTRACTUAL RECOGNITION; CONTRACTUAL RECOGNITION ≠ PAYROLL AUTHORIZATION; DEMONSTRATION FINDING ≠ APPROVED PRODUCTION BLOCKER; INHERITED REPRESENTATION ≠ INDEPENDENT PROOF; CAUSAL HYPOTHESIS ≠ ESTABLISHED CAUSE; SOFTWARE ENGINE PASS ≠ PRODUCTION VALIDATION; NO DETECTED ISSUE ≠ VERIFIED SHIFT
- CLAIMED OBSERVATION ≠ VERIFIED KNOWLEDGE; AUDITED ≠ VERIFIED PHYSICAL; REPEATED ≠ APPROVED NORM; KNOWLEDGE CANDIDATE ≠ APPROVED PRODUCTION KNOWLEDGE; SUGGESTED REUSE ≠ AUTHORIZED REUSE; SCENARIO COST ≠ ACTUAL COST KNOWLEDGE; MULTIPLE AUDITS ≠ MULTIPLE PHYSICAL OBSERVATIONS
- Constructor handoff_store / governance baseline string — PRE_EXISTING defects (baseline `2c038a3`)
- Query Port architecture `shadow_runtime_stores` import FAIL — PRE_EXISTING_NOT_I1_REGRESSION (baseline `e810eff`)
- I1: caller-supplied resolver untrusted; process-local result ≠ durable history; `month_key` compatibility seam; `get_result` internal-only
- Full autonomous auditor — **not created**; 12/12 engines ≠ production readiness; I1 ≠ production readiness

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

**I2 Supabase & Durable History** (NEXT; separate stage after compact reuse research).

Proposed split: **I2-A** Trusted Production Source Acquisition · **I2-B** Full
Professional Audit Durable History. See
[`PSAA_I1_MANAGED_RUNTIME_CHECKPOINT.md`](PSAA_I1_MANAGED_RUNTIME_CHECKPOINT.md) §11.

Professional Core v0.1 remains **FROZEN** — see
[`PSAA_PROFESSIONAL_CORE_COMPLETION_V0_1.md`](PSAA_PROFESSIONAL_CORE_COMPLETION_V0_1.md).
I1 Managed Runtime Integration is **DONE**.

Do **not** start S13+.
Do **not** create new runtime framework, knowledge platform, or parallel PSAA architecture.
Do **not** start I2 without separate authorization and reuse research of existing
PSAA read/history/Supabase mechanisms.

## 16. Passport status

**Professional Core v0.1 FROZEN** — S01 + PSAA-02 local history + S10 + S02 + S03 + S11 + S04 + S05 + S06 + S07 + S08 + S09 + S12 (**12 of 12 skill engines**; joint fixture PROVEN; production readiness NOT_PROVEN).
**I1 Managed Runtime Integration DONE** — existing Run Control + `PsaaManagedRuntimeLauncher` + joint assess_shift; process-local result; production trusted source / durable history / production readiness NOT_PROVEN.
Final industrial Passport — после production-grade history, production tech/physical knowledge и расширенного professional proof.
