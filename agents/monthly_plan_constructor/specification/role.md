# Агент формирования кандидатного состава месячного плана

**Код:** `MONTHLY_PLAN_CONSTRUCTOR`
**Версия:** v1.0 target professional contract (2026-10-02)
**Контур:** месячное планирование (Constructor)
**Канон:** `docs/agentic_architecture/CONSTRUCTOR_AGENT_ANATOMY.md`
**Authority:** 3 of 5 — specification. Не конкурирует с Anatomy.

## Роль

Цифровой сотрудник формирования кандидатного состава месячного плана.

Работа начинается с формализованного намерения планирования (Constructor Mission),
не с заранее собранной человеком таблицы BOQ.

После получения Mission агент самостоятельно читает весь scope, считает remainder,
учитывает текущий месяц, предлагает labor norm, выявляет конфликты и формирует
полный Candidate Package с рекомендациями (target).

Человек не собирает BOQ-коды вручную до старта.
Человек выполняет Human Review готового пакета: Добавить / Убрать / Требует уточнения.

Следующий целевой сотрудник после Human Confirm — Executability Agent.
Admission terminology — CURRENT LEGACY RUNTIME / SUPERSEDED FOR TARGET.

## Это не

- чат-бот;
- dashboard;
- LLM-обёртка;
- writer в product tables;
- Executability / Resource / Economic / Orchestrator.

## Граница текущей реализации (v0.1 code)

**READ → ANALYZE → PROPOSE → TRACE**

Без product writes. Без LLM. UI не является runtime.
Human Review, Reviewed Candidate Package, labor final gate, Human Confirm, Executability Agent — target, не proven.
