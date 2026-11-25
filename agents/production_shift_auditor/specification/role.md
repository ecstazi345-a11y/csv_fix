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

Реализованы навыки: **S01**, **S10**, **S02**, **S03**, **S11** (deterministic).
S04–S09, S12 — TARGET / FUTURE.
S11 считает заявленную удельную трудоёмкость и eligibility; не утверждает нормы.
LLM не используется.
Product writes запрещены. Нормы труда не мутируются.
