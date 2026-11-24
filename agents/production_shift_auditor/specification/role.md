# Production Shift Auditor Agent

**Код:** `PRODUCTION_SHIFT_AUDITOR`
**Версия:** v0.1 (Initial / DESIGN + S01 CURRENT)
**Контур:** производственное исполнение (смена)
**Authority:** specification pack. Не конкурирует с Constructor Anatomy.

## Роль

Цифровой аудитор производственного исполнения.

Исследует достоверность сменной производственной отчётности, выявляет отклонения,
формирует профессиональное заключение и передаёт человеку вопросы, требующие решения.

## Это не

- чат-бот;
- dashboard / Streamlit page;
- LLM-обёртка;
- writer в `daily_progress_*` / Airtable;
- Constructor / планировщик;
- зарплатный / TCE калькулятор;
- Operation Registry;
- система accept/reject смены (TARGET).

## Граница текущей реализации (v0.1)

**READ (узкий) → ANALYZE (детерминированно) → ARTIFACT → TRACE**

Реализован только навык **S01 — Mathematical Integrity**.
Skills S02–S12 — TARGET / FUTURE, не реализованы.
LLM не используется.
Product writes запрещены.
