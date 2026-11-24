# Agentic Architecture — Execution OS

**Status:** canonical ENGINEERING SOURCE OF TRUTH<br>
**Version:** v0.1<br>
**Date:** 2026-08-22<br>
**Scope:** агентная архитектура контура месячного планирования и связанных цифровых сотрудников

Это не пользовательская справка и не история чата.<br>
Это инженерный закон, по которому через месяцы можно восстановить систему **без** Cursor / ChatGPT transcripts.

---

## Навигация

| Сначала | Зачем |
|---------|--------|
| [AGENT_RUNTIME_PROGRESS.md](AGENT_RUNTIME_PROGRESS.md) | Где мы сейчас (журнал программы, append-only checkpoints). |
| [DIGITAL_EMPLOYEE_ANATOMY.md](DIGITAL_EMPLOYEE_ANATOMY.md) | Как профессионально устроен цифровой сотрудник. |
| [DIGITAL_WORKER_BLUEPRINT.md](DIGITAL_WORKER_BLUEPRINT.md) | Навигационный стандарт проектирования цифрового сотрудника. Не заменяет источники истины. |
| [ARCHITECTURE_BASELINE.md](ARCHITECTURE_BASELINE.md) | Как устроена целевая архитектура (в т.ч. компактная карта DYNAMIS / СИНТАРК / PSAA). |
| [PRODUCTION_SHIFT_AUDITOR_PROFESSIONAL_PASSPORT_V0_1.md](PRODUCTION_SHIFT_AUDITOR_PROFESSIONAL_PASSPORT_V0_1.md) | Паспорт Production Shift Auditor (EXECUTION). |
| [PSAA_01_MATHEMATICAL_INTEGRITY_CHECKPOINT.md](PSAA_01_MATHEMATICAL_INTEGRITY_CHECKPOINT.md) | Checkpoint завершения PSAA-01. |
| [PSAA_02_AUDIT_HISTORY_CHECKPOINT.md](PSAA_02_AUDIT_HISTORY_CHECKPOINT.md) | Checkpoint завершения PSAA-02 (local durable history). |
| [PSAA_03_OPERATION_CLASSIFICATION_CHECKPOINT.md](PSAA_03_OPERATION_CLASSIFICATION_CHECKPOINT.md) | Checkpoint завершения PSAA-03 (S10 classification). |
| [RECOVERY_CONTEXT.md](RECOVERY_CONTEXT.md) | Как восстановить контекст после паузы. |

---

## Что это

**Execution OS** — операционная система физического исполнения строительных работ: план → допуск → исполнение → приёмка → деньги.

**Agentic Architecture** — способ организовать внутри Execution OS **цифровых сотрудников**: независимых исполнителей с миссией, scope, lifecycle, skills, tools, permissions, exceptions, human gates и handoff.

Эта директория — **технический source of truth** для разработки цифровых сотрудников.

---

## Зачем существует эта директория

Архитектура должна быть восстановима, когда:

- нет истории предыдущих сессий Cursor / ChatGPT;
- новый инженер или новый агент-ассистент открывает репозиторий;
- реализация MPCA-001/002/003 уже частично существует и легко принять её UI за целевой закон.

Без этого документа система снова проектируется «с нуля» и повторяет уже отвергнутые ошибки.

---

## Page52 vs эта директория

| Источник | Роль |
|----------|------|
| `pages/52_Архитектура_агентной_оркестрации_месячного_плана.py` | Организационное / пользовательское описание: кто какие роли выполняет, какую рутину забирает, какой эффект для ИТР. |
| `docs/agentic_architecture/` | Техническая инженерная архитектура реализации: runtime, contracts, scope, security, handoff, labor norms, anti-patterns, next release. |

Page52 **не отменяется**. Она остаётся каноном **зачем и кто**.<br>
Эта директория — канон **как строить**.

При конфликте UI-эксперимента (например таблица 175 кандидатов на Page10B) с документами этой директории побеждает **эта директория**, пока ADR явно не изменит закон.

Связанный security law живёт отдельно и тоже обязателен:

- `security/README.md`
- `security/agent_security_baseline.md` (EOS-SEC-1.0 / EOS-SEC-1.1)
- остальные файлы `security/*.md`

---

## Порядок чтения

1. [AGENT_RUNTIME_PROGRESS.md](AGENT_RUNTIME_PROGRESS.md) — где мы сейчас.
2. [DIGITAL_EMPLOYEE_ANATOMY.md](DIGITAL_EMPLOYEE_ANATOMY.md) — базовые понятия и устройство цифрового сотрудника.
3. [ARCHITECTURE_BASELINE.md](ARCHITECTURE_BASELINE.md) — целевая архитектура системы.
4. [AGENT_RUNTIME_V0_1_CONSTRUCTOR_MISSION.md](AGENT_RUNTIME_V0_1_CONSTRUCTOR_MISSION.md) — runtime specification Constructor Agent.
5. [RECOVERY_CONTEXT.md](RECOVERY_CONTEXT.md) — быстрое восстановление после длинной паузы / другого компьютера.

Остальные файлы каталога (спецификация роли, orchestration, labor norms, decision log) читать по задаче. Не начинать новый агент, таблицу или LangGraph runtime, не прочитав baseline + decision log.

---

## Документы

| Файл | Назначение |
|------|------------|
| [AGENT_RUNTIME_PROGRESS.md](AGENT_RUNTIME_PROGRESS.md) | Журнал программы: что доказано, где мы, что дальше. |
| [DIGITAL_EMPLOYEE_ANATOMY.md](DIGITAL_EMPLOYEE_ANATOMY.md) | Учебная анатомия профессионального цифрового сотрудника. |
| [ARCHITECTURE_BASELINE.md](ARCHITECTURE_BASELINE.md) | Общий закон: stack, AGENT ≠ dashboard, организация цифровых сотрудников, EOS-SEC, LLM boundary, anti-patterns, DYNAMIS/СИНТАРК map, next release. |
| [MONTHLY_PLAN_CONSTRUCTOR_AGENT.md](MONTHLY_PLAN_CONSTRUCTOR_AGENT.md) | Спецификация Агента формирования кандидатного состава: mission, scope, lifecycle, human role, quantity, missing labor norm. |
| [PRODUCTION_SHIFT_AUDITOR_PROFESSIONAL_PASSPORT_V0_1.md](PRODUCTION_SHIFT_AUDITOR_PROFESSIONAL_PASSPORT_V0_1.md) | Паспорт аудитора сменного исполнения (PSAA). |
| [PSAA_01_MATHEMATICAL_INTEGRITY_CHECKPOINT.md](PSAA_01_MATHEMATICAL_INTEGRITY_CHECKPOINT.md) | Зафиксированное завершение PSAA-01 (S01). |
| [PSAA_02_AUDIT_HISTORY_CHECKPOINT.md](PSAA_02_AUDIT_HISTORY_CHECKPOINT.md) | Зафиксированное завершение PSAA-02 (append-only history). |
| [PSAA_03_OPERATION_CLASSIFICATION_CHECKPOINT.md](PSAA_03_OPERATION_CLASSIFICATION_CHECKPOINT.md) | Зафиксированное завершение PSAA-03 (S10 classification). |
| [ORCHESTRATION_AND_HANDOFF.md](ORCHESTRATION_AND_HANDOFF.md) | Оркестратор, shared state, structured handoff, pause/resume, Control Room, KPI routine removal. |
| [LABOR_NORM_RESOLUTION.md](LABOR_NORM_RESOLUTION.md) | LaborNormResolver: иерархия источников, provenance, benchmark vs P50 vs planning norm, continuous learning. |
| [DECISION_LOG.md](DECISION_LOG.md) | Принятые и отклонённые решения (ADR-like). |
| [RECOVERY_CONTEXT.md](RECOVERY_CONTEXT.md) | Компактный контекст для новой сессии. |

---

## Что здесь не делается

Документы этой директории **не**:

- не являются разрешением писать product code;
- не создают таблицы Supabase и не меняют schema;
- не подключают ГЭСН / внешние нормативные API;
- не отменяют EOS-SEC;
- не делают Page10B runtime агента.

Актуальное состояние программ смотреть в:

- Constructor / control plane: [AGENT_RUNTIME_PROGRESS.md](AGENT_RUNTIME_PROGRESS.md)
- PSAA-01 completion: [PSAA_01_MATHEMATICAL_INTEGRITY_CHECKPOINT.md](PSAA_01_MATHEMATICAL_INTEGRITY_CHECKPOINT.md)
- PSAA-02 completion: [PSAA_02_AUDIT_HISTORY_CHECKPOINT.md](PSAA_02_AUDIT_HISTORY_CHECKPOINT.md)
- PSAA-03 completion: [PSAA_03_OPERATION_CLASSIFICATION_CHECKPOINT.md](PSAA_03_OPERATION_CLASSIFICATION_CHECKPOINT.md)

Этот README не является журналом программы.
