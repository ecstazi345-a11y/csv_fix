# AGENT_MEMORY — быстрая память для AI-агента

> **Читать в начале каждой сессии** (30 секунд). Полный контекст: `PROJECT_CONTEXT.md`. Задачи: `NEXT_STEPS.md`. История: `AI_WORKLOG.md`.

---

## Identity

| Поле | Значение |
|------|----------|
| Проект | csv_fix / AI Construction Control Center |
| Путь | `C:\csv_fix` |
| Владелец | **Не программист.** Роль: **Architect / Orchestrator** |
| Язык общения | Русский, простые объяснения |
| Формула | `DATA → EXECUTABILITY → EXECUTION → ACCEPTANCE → CASH` |

---

## One-liner

Строительный **AI-first execution OS**: данные из Airtable → аналитика в Supabase → витрина Streamlit для управления СМР (план, факт, приёмка, деньги).

---

## Architecture (не ломать без запроса)

```
Airtable → [Python sync] → Supabase (tables + views) → Streamlit
```

**Source of truth:** `monthly_passport_plan` (план), `daily_progress_raw` (факт).  
**UI опирается на views:** `smr_*` (см. список в PROJECT_CONTEXT §3).  
**Не опираться на legacy views** в новом UI.

**Критическое правило plan-fact:** месячное сопоставление — основа; неделя — только фильтр факта; **не делать** жёсткий weekly JOIN план×факт как истину.

---

## Stack & run commands

```powershell
cd C:\csv_fix
.\.venv\Scripts\streamlit.exe run app.py    # UI → http://localhost:8501
.\.venv\Scripts\python.exe update_all_sync.py   # 4 синка (факт, BOQ, план, Crew_Register)
# или: ОБНОВИТЬ_ВСЕ_ДАННЫЕ.bat
```

- `.env` обязателен для страниц с Supabase (`SUPABASE_URL`, `SUPABASE_KEY` + Airtable для синков).
- `.venv` и `.env` в `.gitignore` — не коммитить.

---

## Code map (куда смотреть)

| Задача | Файл |
|--------|------|
| Landing | `app.py` |
| План-факт (главный дашборд) | `pages/05_Исполнение.py` |
| KPI главная | `pages/01_Главная.py` |
| AI агент v0 | `pages/11_AI_Агенты.py` |
| PTO / приёмка | `pages/07_Приемка_и_признание.py` |
| Качество данных | `pages/06_Качество_данных.py` |
| Supabase client | `services/supabase_client.py` |
| Синки | `*_sync*.py`, `update_all_sync.py` |
| Доменная логика | `README_SMR_EXECUTION_LOGIC.md` |

---

## Maturity snapshot (2026-05-15)

- **Сильно:** Исполнение (05), синки, SMR views, Главная KPI, AI agent v0.
- **Слабо / каркас:** Допуск фронта (02), Оплата (03), Потери (07), Экономика (08), Уведомления (09).
- **Стадия:** Execution OS **v0.8**
- **Главный риск:** ошибки классификации факта (Facility, Discipline, IWP, System).

---

## Agent behavior rules

1. **Объяснять просто** — что делает изменение для стройки и денег.
2. **Минимальный diff** — не рефакторить без запроса.
3. **Не коммитить** без явной просьбы; не трогать `.env`.
4. **Перед правкой SQL/views** — свериться с `README_SMR_EXECUTION_LOGIC.md`.
5. **После сессии** — предложить обновить `AI_WORKLOG.md` и `NEXT_STEPS.md`.
6. **Коммиты на русском или английском** — как в истории репо (кратко, по делу).

---

## Owner preferences

- Пошаговые инструкции и готовые команды PowerShell.
- Работа между компьютерами: клонировать git + скопировать `.env` вручную + `pip install -r requirements.txt`.
- VS Code / Cursor — оба OK; путь проекта тот же.

---

## Do NOT

- Удалять legacy views/tables без явного согласования.
- Внедрять weekly plan-fact JOIN как production-логику без зрелых данных.
- Писать секреты в markdown или в git.
- Создавать лишние markdown-файлы без запроса.

---

## Last session pointer

**2026-05-15:** среда восстановлена, Streamlit работает, memory layer создан.  
→ Актуальные задачи: **`NEXT_STEPS.md`**
