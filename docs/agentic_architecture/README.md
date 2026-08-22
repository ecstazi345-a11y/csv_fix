# Agentic Architecture — Execution OS

**Status:** canonical ENGINEERING SOURCE OF TRUTH<br>
**Version:** v0.1<br>
**Date:** 2026-08-22<br>
**Scope:** агентная архитектура контура месячного планирования и связанных цифровых сотрудников

Это не пользовательская справка и не история чата.<br>
Это инженерный закон, по которому через месяцы можно восстановить систему **без** Cursor / ChatGPT transcripts.

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

1. [RECOVERY_CONTEXT.md](RECOVERY_CONTEXT.md) — если сессия новая: вставить как контекст и **не** проектировать систему заново.
2. [ARCHITECTURE_BASELINE.md](ARCHITECTURE_BASELINE.md) — общий закон системы.
3. [MONTHLY_PLAN_CONSTRUCTOR_AGENT.md](MONTHLY_PLAN_CONSTRUCTOR_AGENT.md) — первый цифровой сотрудник.
4. [ORCHESTRATION_AND_HANDOFF.md](ORCHESTRATION_AND_HANDOFF.md) — жизненный цикл, оркестратор, передача работы, Human Interrupt.
5. [LABOR_NORM_RESOLUTION.md](LABOR_NORM_RESOLUTION.md) — нормативы трудоёмкости, provenance, отсутствие своей истории.
6. [DECISION_LOG.md](DECISION_LOG.md) — что уже решено и что отвергнуто.

Не начинать новый агент, таблицу или LangGraph runtime, не прочитав baseline + decision log.

---

## Документы

| Файл | Назначение |
|------|------------|
| [ARCHITECTURE_BASELINE.md](ARCHITECTURE_BASELINE.md) | Общий закон: stack, AGENT ≠ dashboard, организация цифровых сотрудников, EOS-SEC, LLM boundary, anti-patterns, next release. |
| [MONTHLY_PLAN_CONSTRUCTOR_AGENT.md](MONTHLY_PLAN_CONSTRUCTOR_AGENT.md) | Спецификация Агента формирования кандидатного состава: mission, scope, lifecycle, human role, quantity, missing labor norm. |
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

Следующий инженерный релиз после этого checkpoint:

**AGENT RUNTIME v0.1 — CONSTRUCTOR MISSION**<br>
(не MPCA-004 table).

См. [ARCHITECTURE_BASELINE.md](ARCHITECTURE_BASELINE.md) § Next engineering release.
