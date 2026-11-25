# Профессиональный паспорт цифрового сотрудника
# Production Shift Auditor Agent (PSAA)

**Document:** PRODUCTION_SHIFT_AUDITOR_PROFESSIONAL_PASSPORT_V0_1
**Version:** v0.1 (S01 + local Audit History + S10 + S02 + S03 + S11 + S04 engines proven)
**Status:** S01 + PSAA-02 local history + S10 + S02 + S03 + S11 + S04 engines CURRENT / PROVEN · scenario direct labor cost PROVEN · actual incurred cost NOT PROVEN · full execution cost NOT COMPUTABLE · verified labor observations NOT PROVEN · approved labor norms NOT CREATED · production tech/physical knowledge NOT READY · inspection NOT PROVEN · full auditor NOT COMPLETE · production Supabase persistence NOT COMPLETE · S10/S02/S03/S11/S04 not in durable history
**Standard:** PROFESSIONAL_PASSPORT_TEMPLATE_V1_0
**Checkpoints:** [PSAA_01](PSAA_01_MATHEMATICAL_INTEGRITY_CHECKPOINT.md) · [PSAA_02](PSAA_02_AUDIT_HISTORY_CHECKPOINT.md) · [PSAA_03](PSAA_03_OPERATION_CLASSIFICATION_CHECKPOINT.md) · [PSAA_04](PSAA_04_TECHNOLOGICAL_INTEGRITY_CHECKPOINT.md) · [PSAA_05](PSAA_05_PHYSICAL_INTEGRITY_CHECKPOINT.md) · [PSAA_06](PSAA_06_LABOR_BENCHMARK_CHECKPOINT.md) · [PSAA_07](PSAA_07_EXECUTION_COST_CHECKPOINT.md)
**Latest code commit:** `e0d5179cea9c2f0653d559883a68d3d40de1ff07`
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
- Узкий trusted READ adapter (replaceable; legacy `daily_progress_active`)
- Структурированный профессиональный артефакт с provenance
- Append-only local Audit History (PSAA-02) — **DONE** (SQLite / in-memory; not production Supabase; S10/S02/S03/S11/S04 not persisted yet)

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

По входу `ShiftAuditInput` (fixture или trusted READ) выполнить **S01**, **S10**, **S02**, **S03**, **S11** и **S04** (joint `assess_shift`), вернуть математический, классификационный, технологический, physical-integrity, labor-benchmark и execution-cost артефакты; при необходимости сохранить append-only **S01** history record (PSAA-02). S10/S02/S03/S11/S04 пока не пишутся в durable history.

## 7. Skills

| Код | Навык | Статус |
|-----|-------|--------|
| S01 | Mathematical Integrity | **DONE / PROVEN** |
| S10 | Operation Classification & Normalization | **DONE / PROVEN** (deterministic; insulation working catalog) |
| S02 | Technological Integrity | **DONE / PROVEN** (engine; demo rules only — production knowledge NOT READY) |
| S03 | Physical Integrity | **DONE / PROVEN** (engine; demo measurability — production physical knowledge / inspection NOT READY) |
| S11 | Labor Benchmark & Observation Eligibility | **DONE / PROVEN** (engine; claimed metrics only — verified observations / approved norms NOT CREATED) |
| S04 | Execution Cost Analysis | **DONE / PROVEN** (engine; scenario direct labor only — actual incurred / full cost NOT PROVEN) |
| S05 | Temporal Integrity | **NEXT (PSAA-08)** |
| S06–S09, S12 | (см. Target) | TARGET / FUTURE |

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
| **CURRENT** | S01 DONE; PSAA-02 local durable history DONE (`ff40fb6`); S10 DONE (`a91161f`); S02 engine DONE (`74a528b`); S03 engine DONE (`eb9d9a0`); S11 engine DONE (`252af32`); S04 engine DONE (`e0d5179`); Overfund Diagnostic; EOS-SEC controlled persist |
| **TARGET** | Supabase history adapter + migration apply + live PG proof; S10/S02/S03/S11/S04 in durable history; production tech/physical knowledge; S05 (PSAA-08) / S06–S09/S12; Django Shift Acceptance; Human Gate acceptance |
| **NOT IN SCOPE (v0.1)** | LLM; UI; Constructor changes; Operation Registry; payroll; TCE replacement; auto accept/reject; auto norm/rate approval; margin/revenue |

### Limits (mandatory)

- Live labor semantics — **PARTIALLY_PROVEN**
- Legacy `crew_size` may denote allocated resource, not headcount (**PASS with LIMIT**)
- SQL_SCHEMA_READY = YES; SUPABASE_STORAGE_ADAPTER_READY = NO; MIGRATION_APPLIED = NO; LIVE_POSTGRESQL_PERSISTENCE_PROVEN = NO
- SQLite ≠ multi-node production durability
- `absolute_deviation_*` signed semantics — technical debt (version-aware contract correction required)
- S10/S02/S03/S11/S04 not in durable audit history; insulation-only working catalogs; no industrial classification/inspection accuracy proof
- Alias string equality ≠ professional equivalence; catalog candidate ≠ approved Operation Registry
- S02: `PRODUCTION_KNOWLEDGE_NOT_READY` · `PRODUCTION_VALIDATION_NOT_PROVEN`
- S03: `PRODUCTION_PHYSICAL_KNOWLEDGE_NOT_READY` · `PHYSICAL_INSPECTION_NOT_PROVEN`
- S11: `VERIFIED_OBSERVATIONS_NOT_PROVEN` · `APPROVED_LABOR_NORMS_NOT_CREATED` · production Labor Norm READ adapter NOT IMPLEMENTED
- S04: `ACTUAL_COST_NOT_PROVEN` · `FULL_EXECUTION_COST_NOT_COMPUTABLE` · production cost-rate READ adapter NOT IMPLEMENTED · full multi-rate/worker allocation NOT IMPLEMENTED
- Quantity not required by current rule ≠ non-measurability; missing geometry ≠ proven unit incompatibility; claimed MANUFACTURED/INSTALLED ≠ verified fact
- Same shift ≠ same physical object; missing evidence ≠ proven violation; demo rule ≠ approved engineering requirement
- CLAIMED UNIT LABOR ≠ VERIFIED ≠ APPROVED NORM; labor without quantity ≠ automatic loss; same operation code ≠ automatic comparability
- CLAIMED LABOR COST ≠ ACTUAL; SCENARIO ≠ APPROVED; DIRECT ≠ FULL; UNKNOWN ≠ ZERO; estimate ≠ payroll
- Constructor handoff_store / governance baseline string — PRE_EXISTING defects (baseline `2c038a3`)
- Full autonomous auditor — **not created**

## 13. Failure Conditions

- Смешение project/crew/date/shift → fail-closed
- Конфликт `crew_size` → diagnostic, без суммирования по строкам
- `direct_work_hours` без доказанной семантики → `HOUR_FIELD_UNPROVEN`
- History: same `audit_id` + different content → CONFLICT; cross-project → DENIED; write failure → fail-closed

## 14. Next increment

**PSAA-08 / S05 — Temporal Integrity** (not started).

Assess temporal credibility of claimed production execution: elapsed vs labor effort, crew vs worker time, sequential/parallel/overlap, target fund vs paid/idle/unallocated time, claimed vs verified chronology.
Man-minutes ≠ elapsed minutes; row order ≠ chronology; arithmetic balance ≠ temporal feasibility; parallel ≠ automatic conflict; missing timestamps ≠ violation; unallocated ≠ automatic idle; no invented timestamps/worker allocation; no automatic fraud/loss classification.

## 15. Passport status

**Initial Passport v0.1** + S01 + PSAA-02 local history + S10 + S02 + S03 + S11 + S04 engine evidence.
Final Passport — после production-grade history, production tech/physical knowledge и расширенного professional proof.
