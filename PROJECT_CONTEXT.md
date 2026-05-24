# PROJECT_CONTEXT — csv_fix / AI Construction Control Center

> **Назначение файла:** стабильный «паспорт проекта». Обновлять при смене архитектуры, стека или ключевых решений.  
> **Аудитория:** владелец продукта (Architect / Orchestrator) + AI-агенты.  
> **Путь проекта на ПК:** `C:\csv_fix`

---

## 1. Что это за проект

**AI Construction Control Center** — AI-first execution OS для строительного субподрядчика инженерных систем (СМР).

Система связывает **план → допуск → исполнение → приёмку → деньги** в одной управленческой витрине, чтобы руководитель за 1–2 минуты видел, где проект идёт по плану, где заблокирован фронт, где факт не превращается в признанный объём и где формируются потери.

### Ключевая формула продукта

```
DATA → EXECUTABILITY → EXECUTION → ACCEPTANCE → CASH
```

| Этап | Смысл для бизнеса | Раздел Streamlit (целевой) |
|------|-------------------|----------------------------|
| **DATA** | Единые, чистые данные с площадки и из плана | Синк Airtable → Supabase, quality views |
| **EXECUTABILITY** | Можно ли физически выполнять работу сейчас | Допуск фронта |
| **EXECUTION** | План / факт / отклонения / звенья | Исполнение, Паспорт месяца |
| **ACCEPTANCE** | Инспекция, признание объёмов заказчиком | Приёмка и признание |
| **CASH** | Деньги, маржа, уведомления | Экономика, Уведомления заказчику |

---

## 2. Роль владельца и AI

| Роль | Кто | Ожидание |
|------|-----|----------|
| **Architect / Orchestrator** | Владелец проекта | Проектирует логику, процессы, витрины; не пишет код руками |
| **AI Agent** | Cursor / агенты | Пишет код, объясняет простыми словами, помнит контекст между сессиями |

**Правило для агента:** объяснять решения без жаргона; перед изменением кода — кратко сказать *что* и *зачем*; не ломать рабочую месячную логику СМР без явного запроса.

---

## Execution OS Architecture

Проект развивается от **витрины план-факт** к **Contractor Execution OS** — системе управления исполнением по цепочке:

```
Month → Week → Day → Crew → Worker
```

С двумя обязательными допусками перед исполнением и признанием:

| Допуск | Вопрос |
|--------|--------|
| **Execution Admittance** | Можно ли исполнять? (фронт, РД, IWP, МТР, люди, ОТ/ТБ, качество) |
| **Acceptance Admittance** | Можно ли признать и оплатить? (КС, QA/QC, расценка, commercial risk) |

Полное описание целевой архитектуры, engines, views и MVP: **`EXECUTION_OS_ARCHITECTURE.md`**.

---

## 3. Архитектура данных

```
┌─────────────┐     sync scripts      ┌──────────────┐     Streamlit      ┌─────────────┐
│  Airtable   │ ───────────────────►  │   Supabase   │ ────────────────►  │  Витрина    │
│ (ввод, CRM) │   Python upsert       │ tables+views │   pandas/read      │  для СМР    │
└─────────────┘                       └──────────────┘                    └─────────────┘
```

### Источники правды (Source of Truth)

| Слой | Таблица / объект | Назначение |
|------|------------------|------------|
| План месяца | `monthly_passport_plan` | Единственный источник месячного плана |
| Сырой факт | `daily_progress_raw` | Факт с площадки (смены) |
| BOQ | sync из Airtable | Справочник / объёмы |

### Рабочие витрины Supabase (CORE — опираться в Streamlit)

| View | Назначение |
|------|------------|
| `daily_progress_clean` | Очищенный факт |
| `daily_progress_monthly_agg_clean` | Агрегат факта по месяцу |
| `smr_plan_work_key` | Уникальный ключ работы (антидубль план×факт) |
| `smr_reconciliation` | План / факт / MATCHED / FACT_ONLY / PLAN_ONLY |
| `smr_month_summary` | KPI-карточки месяца |
| `smr_plan_line_control` | Строка плана vs суммарный факт |
| `smr_crew_control` | Контроль звеньев |
| `smr_data_quality_issues` | Ошибки классификации мастеров |
| `smr_problem_aggregation` | ТОП проблем |
| `smr_validation_work_key` | Сходимость RAW vs SMR |

**Устаревшие / вторичные** (не удалять, в UI не опираться):  
`monthly_plan_vs_fact`, `work_plan_fact_reconciliation`, `work_plan_fact_by_plan_line`, старые agg/sum views.

### Принятое решение: месяц vs неделя

- **Основа управления — месячное сопоставление** плана и факта.
- **Недельный фильтр** — только для просмотра факта за выбранную неделю.
- **Не считать сейчас:** «план недели», невыполненный план недели, жёсткий `JOIN` план×факт по `week_key` как управленческую истину.

Причина: в `Monthly_Passport_Plan` `week_key` от даты старта — не полноценный недельный план; JOIN по неделе даёт ложные `FACT_ONLY`.

Детали: `EXECUTION_PLAN_FACT_WEEKLY_MODEL.md`, `README_SMR_EXECUTION_LOGIC.md`.

---

## 4. Технический стек

| Компонент | Технология | Версия / примечание |
|-----------|------------|---------------------|
| UI | Streamlit (multipage) | `app.py` + `pages/` |
| Язык | Python | 3.12.x в `.venv` |
| Данные | Supabase (Postgres + API) | `services/supabase_client.py` |
| Внешний ввод | Airtable API | токены в `.env` |
| Аналитика в UI | pandas | |
| Конфиг | python-dotenv | файл `.env` в корне (в `.gitignore`) |
| IDE | Cursor / VS Code | ранее VS Code на этом ПК |
| Контейнер | devcontainer (опционально) | Python 3.11 image, порт 8501 |

### Зависимости (`requirements.txt`)

```
streamlit, pandas, requests, python-dotenv, supabase
```

### Структура репозитория

```
C:\csv_fix\
├── app.py                          # Landing / описание системы
├── pages/                          # Streamlit-разделы (01–10)
├── services/
│   ├── supabase_client.py          # Клиент Supabase (.env)
│   └── queries.py                  # Запросы (часть legacy tables)
├── daily_progress_sync_upsert.py   # Синк факта Airtable → Supabase
├── boq_sync_upsert.py              # Синк BOQ
├── monthly_passport_sync_airtable.py
├── monthly_labor_summary_sync_upsert.py  # Crew_Register → monthly_labor_summary
├── update_all_sync.py              # Запуск всех синков (4 потока)
├── ОБНОВИТЬ_ВСЕ_ДАННЫЕ.bat         # One-click синк для Windows
├── .venv/                          # Локальное окружение (не в git)
├── .env                            # Секреты (не в git)
├── PROJECT_CONTEXT.md              # Этот файл
├── AI_WORKLOG.md                   # Журнал сессий
├── AGENT_MEMORY.md                 # Краткая память для агента
└── NEXT_STEPS.md                   # Ближайшие задачи
```

---

## 5. Streamlit — разделы приложения

| # | Файл | Статус (2026-05) | Смысл |
|---|------|------------------|-------|
| — | `app.py` | ✅ | Вход, описание цепочки |
| 01 | Главная | 🟡 MVP | KPI из `smr_month_summary`, reconciliation |
| 02 | Допуск фронта | 🟠 Концепт | Executability Gate — текст/логика, мало данных |
| 03 | Допуск к оплате | 🟠 Концепт | Payment readiness |
| 04 | Паспорт месяца | 🟡 | Месячный план |
| 05 | Исполнение | ✅ **ядро** | План-факт, недельный факт, звенья, expanders, cache |
| 06 | Приёмка и признание | 🟡 | PTO registry, upsert |
| 07 | Контроль потерь | 🟠 Концепт | Потери / отклонения |
| 08 | Экономика | 🟠 Концепт | Деньги / маржа |
| 09 | Уведомления заказчику | 🟠 Концепт | События / уведомления |
| 10 | AI-Агенты | 🟡 v0 | Первый агент анализа исполнения (кнопка) |

Легенда: ✅ рабочий контур · 🟡 частично · 🟠 задумано / мало реализации

---

## 6. Workflow (как работать с проектом)

### Ежедневно / на площадке

1. Мастера и планировщики вносят данные в **Airtable**.
2. По необходимости запускается синхронизация в Supabase.

### Синхронизация данных

**Windows (рекомендуется):** двойной клик `ОБНОВИТЬ_ВСЕ_ДАННЫЕ.bat`  
или в терминале:

```powershell
cd C:\csv_fix
.\.venv\Scripts\activate
python update_all_sync.py
```

Порядок скриптов: `daily_progress` → `boq` → `monthly_passport` → `monthly_labor_summary` (Crew_Register).

### Запуск витрины

```powershell
cd C:\csv_fix
.\.venv\Scripts\streamlit.exe run app.py
```

Браузер: **http://localhost:8501**

### Разработка с AI

1. Открыть папку `C:\csv_fix` в Cursor.
2. Агент читает `AGENT_MEMORY.md` + `NEXT_STEPS.md` в начале сессии.
3. После значимой работы — запись в `AI_WORKLOG.md`, обновление `NEXT_STEPS.md`.

---

## 7. Переменные окружения (`.env`)

Файл **не коммитится**. Минимум для Streamlit:

| Переменная | Назначение |
|------------|------------|
| `SUPABASE_URL` | URL проекта Supabase |
| `SUPABASE_KEY` | Anon / service key для приложения |

Для синков Airtable также: `AIRTABLE_TOKEN`, `AIRTABLE_BASE_ID`, table IDs для daily progress, BOQ, monthly passport.

---

## 8. Принятые решения (ADR-lite)

| # | Решение | Почему |
|---|---------|--------|
| D1 | Airtable = ввод, Supabase = аналитика | Разделение UX ввода и SQL-витрин |
| D2 | Месячный plan-fact — основной | Недельный план в данных ещё не зрелый |
| D3 | Ключ работы: project + month + boq + iwp + system | Избежать размножения факта на план |
| D4 | Качество данных — отдельный контур | Ошибки Facility/Discipline ломали KPI |
| D5 | CSV-синк monthly passport удалён | Переход на Airtable sync (`08ffd46`) |
| D6 | Кэш `load_table` в Streamlit | Производительность дашборда (`f4cbb99`) |
| D7 | Persistent memory — 4 MD-файла в корне | Контекст между ПК и сессиями Cursor |

---

## 9. Roadmap (фазы)

### Фаза A — DATA & EXECUTION (текущая) ✅🟡

- [x] Синк Airtable → Supabase (3 потока)
- [x] SMR views и дашборд «Исполнение»
- [x] Главная с live KPI
- [x] Первый AI-агент (анализ исполнения)
- [ ] Стабилизация data quality на площадке
- [ ] Недельный план в данных (эксперимент — июнь, см. README)

### Фаза B — EXECUTABILITY

- [ ] Допуск фронта: чеклисты, HOLD, связь с планом
- [ ] Единые статусы «готов к работе»

### Фаза C — ACCEPTANCE

- [ ] Развитие PTO / признание объёмов
- [ ] Fact vs accepted vs cash gap

### Фаза D — CASH & GOVERNANCE

- [ ] Экономика, маржа, уведомления заказчику
- [ ] Автономные агенты: алерты, отчёты, эскалации

---

## 10. Текущая стадия проекта (snapshot)

| Параметр | Значение |
|----------|----------|
| **Дата snapshot** | 2026-05-15 |
| **Git branch** | `main` |
| **Последние коммиты** | Execution dashboard, cache, all-sync launcher, Airtable passport, PTO, AI agent |
| **Среда на ПК** | `C:\csv_fix`, `.venv` Python 3.12, Streamlit на `:8501` |
| **Зрелость** | **Execution OS v0.8** — сильное ядро план-факт; остальные разделы — продуктовый каркас |
| **Главный риск** | Качество классификации факта (Project / Facility / IWP / System / Discipline) |

---

## 11. Связанные документы в репо

| Файл | Содержание |
|------|------------|
| `README_SMR_EXECUTION_LOGIC.md` | Доменная логика СМР, views, контроль качества |
| `EXECUTION_PLAN_FACT_WEEKLY_MODEL.md` | Месяц vs неделя, ограничения JOIN |
| `AI_WORKLOG.md` | Хронология работ |
| `AGENT_MEMORY.md` | Сжатая память для агента |
| `NEXT_STEPS.md` | Очередь задач |

---

## 12. Как обновлять этот файл

Обновлять **редко**, только когда меняется:

- архитектура или стек;
- source of truth / список views;
- принятые решения (новая строка в §8);
- фаза roadmap или стадия (§9–10).

Мелкие задачи и сессии — в `AI_WORKLOG.md` и `NEXT_STEPS.md`.
