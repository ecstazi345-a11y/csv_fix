# Профессиональный паспорт цифрового сотрудника
# Production Shift Auditor Agent (PSAA)

**Document:** PRODUCTION_SHIFT_AUDITOR_PROFESSIONAL_PASSPORT_V0_1
**Version:** v0.1 (S01 + local Audit History proven)
**Status:** S01 + PSAA-02 local history CURRENT / PROVEN · full auditor NOT COMPLETE · production Supabase persistence NOT COMPLETE
**Standard:** PROFESSIONAL_PASSPORT_TEMPLATE_V1_0
**Checkpoints:** [PSAA_01](PSAA_01_MATHEMATICAL_INTEGRITY_CHECKPOINT.md) · [PSAA_02](PSAA_02_AUDIT_HISTORY_CHECKPOINT.md)
**Latest code commit:** `ff40fb6f04759a11a5a2f556dc97574c9daac445`
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
- Узкий trusted READ adapter (replaceable; legacy `daily_progress_active`)
- Структурированный профессиональный артефакт с provenance
- Append-only local Audit History (PSAA-02) — **DONE** (SQLite / in-memory; not production Supabase)

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

По входу `ShiftAuditInput` (fixture или trusted READ) выполнить **S01**, вернуть `ShiftAuditArtifact` и при необходимости сохранить append-only history record (PSAA-02).

## 7. Skills

| Код | Навык | Статус |
|-----|-------|--------|
| S01 | Mathematical Integrity | **DONE / PROVEN** |
| S10 | Operation Classification & Normalization | **NEXT (PSAA-03)** |
| S02–S09, S11–S12 | (см. Target) | TARGET / FUTURE |

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

History record stores immutable input + artifact snapshots (append-only by `audit_id`).

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
| **CURRENT** | S01 DONE; PSAA-02 local durable history DONE (`ff40fb6`); Overfund Diagnostic; EOS-SEC controlled persist |
| **TARGET** | Supabase history adapter + migration apply + live PG proof; S10 (PSAA-03); S02–S09/S11–S12; Django Shift Acceptance; Human Gate acceptance |
| **NOT IN SCOPE (v0.1)** | LLM; UI; Constructor changes; Operation Registry; payroll; auto accept/reject |

### Limits (mandatory)

- Live labor semantics — **PARTIALLY_PROVEN**
- Legacy `crew_size` may denote allocated resource, not headcount (**PASS with LIMIT**)
- SQL_SCHEMA_READY = YES; SUPABASE_STORAGE_ADAPTER_READY = NO; MIGRATION_APPLIED = NO; LIVE_POSTGRESQL_PERSISTENCE_PROVEN = NO
- SQLite ≠ multi-node production durability
- `absolute_deviation_*` signed semantics — technical debt (version-aware contract correction required)
- Full autonomous auditor — **not created**

## 13. Failure Conditions

- Смешение project/crew/date/shift → fail-closed
- Конфликт `crew_size` → diagnostic, без суммирования по строкам
- `direct_work_hours` без доказанной семантики → `HOUR_FIELD_UNPROVEN`
- History: same `audit_id` + different content → CONFLICT; cross-project → DENIED; write failure → fail-closed

## 14. Next increment

**PSAA-03 — S10 Operation Classification & Normalization** (not started).

Recognize / classify / normalize operation descriptions while preserving original text, provenance, and uncertainty — foundation for Operation Registry, technological integrity, labor accumulation, and per-operation economics.

## 15. Passport status

**Initial Passport v0.1** + S01 evidence + PSAA-02 local history evidence.
Final Passport — после production-grade history и расширенного professional proof.
