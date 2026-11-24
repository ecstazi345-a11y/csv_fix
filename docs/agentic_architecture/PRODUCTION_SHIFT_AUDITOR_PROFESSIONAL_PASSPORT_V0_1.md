# Профессиональный паспорт цифрового сотрудника
# Production Shift Auditor Agent (PSAA)

**Document:** PRODUCTION_SHIFT_AUDITOR_PROFESSIONAL_PASSPORT_V0_1
**Version:** v0.1 (Initial Passport + S01 proven)
**Status:** S01 CURRENT / PROVEN · full auditor NOT COMPLETE
**Standard:** PROFESSIONAL_PASSPORT_TEMPLATE_V1_0
**Checkpoint:** [PSAA_01_MATHEMATICAL_INTEGRITY_CHECKPOINT.md](PSAA_01_MATHEMATICAL_INTEGRITY_CHECKPOINT.md)
**Implementation commit:** `291233564d646d16977f3d5ed8989f55123c772c`
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
- S01 Mathematical Integrity (детерминированно) — **DONE**
- Узкий trusted READ adapter (replaceable; legacy `daily_progress_active`)
- Структурированный профессиональный артефакт с provenance

### SHARED
- EOS-SEC AgentExecutionContext / trusted READ executor
- Observability event contracts (Class-A lifecycle, best-effort)
- Целевой производительный фонд 8 чел·ч/чел (как в планировании) — не табельный фонд

### NOT OWNED
- Constructor Agent / месячное планирование
- Accept/reject смены · Audit History persistence
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
| APPEND-ONLY HISTORY | TARGET principle (PSAA-02); not implemented in v0.1 |
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

По входу `ShiftAuditInput` (fixture или trusted READ) выполнить **S01** и вернуть `ShiftAuditArtifact`.

## 7. Skills

| Код | Навык | Статус |
|-----|-------|--------|
| S01 | Mathematical Integrity | **DONE / PROVEN** |
| S02–S12 | (см. Target) | TARGET / FUTURE |

## 8. Tools

| Tool | Политика | Статус |
|------|----------|--------|
| `load_shift_daily_progress` | PUBLISHABLE_READ, allowlisted | CURRENT (legacy adapter) |

Write tools: **запрещены**.

## 9. Business Artifact

`ShiftAuditArtifact` — показатели, пооперационная детализация, наблюдения, missing data, questions, раздельные статусы:

- math integrity (`COHERENT` = arithmetic coherence only)
- data completeness
- professional credibility (NOT_EVALUATED в v0.1)
- managerial acceptance (NOT_IN_SCOPE)

**Не** ACCEPTED/REJECTED.

## 10. Security / EOS-SEC

- Registry: `PRODUCTION_SHIFT_AUDITOR` в `security/agent_execution_context.py`
- Manifest: `agents/production_shift_auditor/specification/security_manifest.json`
- Credentials только в infrastructure trusted executor
- Master free text = untrusted data
- Observability ≠ product write

## 11. Runtime

Тонкий модуль `agents/production_shift_auditor/runtime.py`.
LangGraph / Django / durable audit history — **NOT IMPLEMENTED** для PSAA v0.1.

## 12. Current / Proven vs Target

| | |
|--|--|
| **CURRENT** | S01 DONE; source-neutral contracts; trusted READ; live uncertainty handling; EOS-SEC registration; commit `2912335` |
| **TARGET** | PSAA-02 Audit History; S02–S12; Django Shift Acceptance surface; append-only history; Human Gate acceptance |
| **NOT IN SCOPE (v0.1)** | LLM; UI; Constructor changes; Operation Registry; payroll; auto accept/reject |

### Limits (mandatory)

- Live labor semantics — **PARTIALLY_PROVEN**
- Legacy `crew_size` may denote allocated resource, not headcount (**PASS with LIMIT**)
- Full autonomous auditor — **not created**

## 13. Failure Conditions

- Смешение project/crew/date/shift → fail-closed
- Конфликт `crew_size` → diagnostic, без суммирования по строкам
- `direct_work_hours` без доказанной семантики → `HOUR_FIELD_UNPROVEN`

## 14. Next increment

**PSAA-02 — Production Shift Audit History** (design later; not started).

## 15. Passport status

**Initial Passport v0.1** + S01 implementation evidence (fixture + live uncertainty proof).
Final Passport — после Audit History и расширенного professional proof.
