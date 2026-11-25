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

Реализованы навыки: **S01**, **S10**, **S02**, **S03**, **S11**, **S04**, **S05**, **S06**, **S07** (deterministic).
S08–S09, S12 — TARGET / FUTURE.
S11 — удельная трудоёмкость / eligibility (не нормы).
S04 — расчётные прямые трудовые затраты (не payroll / не full cost / не actual).
S05 — временная достоверность заявленного исполнения (не timesheet / не scheduling).
S06 — статистические сигналы по заявленным данным (не proven violation).
S07 — причинные гипотезы и уточняющие вопросы (не established cause / не S08).
LLM не используется.
Product writes запрещены. Нормы и ставки не мутируются. Не назначает виновных.
