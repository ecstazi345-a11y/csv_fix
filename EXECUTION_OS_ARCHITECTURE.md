# ARCHITECTURE — Month → Week → Day → Crew → Worker Execution Planning System

> **Статус:** стратегическая архитектура (документация).  
> **Не является** текущей реализацией в коде. Streamlit, SQL и engine modules — отдельные этапы после проектирования views.  
> **Связанные файлы:** `PROJECT_CONTEXT.md`, `README_SMR_EXECUTION_LOGIC.md`, `NEXT_STEPS.md`

---

## 1. Назначение системы

Это **не просто планировщик**, а **Contractor Execution OS** — операционная система управления исполнением строительства субподрядчиком.

Система связывает планирование, допуски, исполнение на площадке, перепланирование, приёмку и деньги в одну управляемую цепочку:

```
Month → Week → Day → Crew → Worker → Daily Progress → Auto Replanning → Acceptance → Cash
```

**Задача для руководителя:** за минуты видеть не только «план vs факт», но и:

- что **реально исполнимо** на месяц / неделю / день;
- что **можно признать** заказчику и перевести в деньги;
- где **заблокирован** фронт, люди, МТР, РД, качество или коммерция;
- как **ежедневный факт** меняет остаток и план следующего дня.

**Отличие от классического план-факт дашборда:** план — это гипотеза; исполнение проходит через два допуска (Execution + Acceptance) и декомпозируется до задач звена и работника.

---

## 2. Текущий стек (as-is)

| Компонент | Роль в Execution OS |
|-----------|---------------------|
| **Airtable** | Ввод с площадки, Crew_Register, паспорт месяца, справочники |
| **Supabase** | Хранилище, агрегации, views для аналитики |
| **Streamlit** | Управленческий интерфейс (витрины, burn-down, качество данных) |
| **Monthly Passport Plan** | Месячный план работ (загрузка / утверждение) |
| **Daily Progress** | Факт смены: объёмы, часы, EV, операции |
| **monthly_labor_summary** | Мощность звеньев: люди, direct hours, мобилизация |
| **BOQ master** | Проектный объём, единицы, коды работ |
| **Historical productivity data** | Накопленная выработка по BOQ / операциям / звеньям (целевой слой) |

**Синхронизация (сегодня):** Python upsert Airtable → Supabase (`update_all_sync.py`, 4 потока).  
**Аналитика (сегодня):** views `smr_*`, `v_crew_burndown_with_fact`, Layer 1 / Layer 2 на странице «Счётчик звена».

---

## 3. Source of Truth

| Объект | Source of Truth для |
|--------|---------------------|
| **BOQ Master** | Проектный объём, единица измерения, идентификатор работы |
| **Daily Progress** | Факт выполнения на площадке (объём, часы, EV, операции, простой) |
| **Monthly Passport Plan** | План месяца (что хотим сделать) |
| **monthly_labor_summary** | Мощность звеньев: состав, direct hours, мобилизация, budget status |
| **Supabase Views** | Аналитика, агрегации, reconciliation, KPI |
| **Streamlit** | Управленческий интерфейс (чтение views, фильтры, диагностика рисков) |

**Правило:** витрина не создаёт истину — она отображает слои, прошедшие допуски и подтверждённые sync.

---

## 4. Основная цепочка (target flow)

```
BOQ / IWP / System
        ↓
Remaining Scope
        ↓
Historical Productivity Norm
        ↓
Labor Capacity
        ↓
Draft Month Plan
        ↓
Execution Admittance          ← можно ли исполнять?
        ↓
Acceptance Admittance         ← можно ли признать / оплатить?
        ↓
Final Executable Month Passport
        ↓
Weekly Plan
        ↓
Daily Plan
        ↓
Crew Task
        ↓
Worker Task
        ↓
Daily Progress (факт)
        ↓
Auto Replanning
```

Каждый уровень наследует ограничения верхнего и уточняет исполнимый объём / часы / EV.

---

## 5. Слой остатка (Balance Layer)

**Формула жизненного цикла BOQ:**

```
project qty − actual qty (all time) = remaining qty
```

| Понятие | Описание |
|---------|----------|
| **project qty** | Объём по BOQ master (контрактный / проектный) |
| **actual qty all time** | Суммарный признанный факт по BOQ из Daily Progress (и будущих слоёв приёмки) |
| **remaining qty** | Что ещё можно «сжечь» по этой позиции |

Остаток — вход для Draft Month Engine и для Auto Replanning после каждого дня.

**Целевой объект:** `boq_lifetime_balance` (view / table).

---

## 6. Слой исторической нормы (Productivity Layer)

Норма выработки строится из истории факта, а не из «желания» планировщика.

| Тип нормы | Назначение |
|-----------|------------|
| **Management Norm** | Фактическая средняя норма — для руководства и реализма |
| **Crew Target Norm** | Улучшенная целевая норма — для постановки задач звену |

**Статистики по BOQ / операции / звену:**

- average  
- median  
- P50  
- P80  

**data confidence** — насколько надёжна норма (кол-во смен, давность, однородность звена, полнота DP).

**Целевой объект:** `boq_productivity_history` (view).

---

## 7. Draft Month Engine

Черновик месяца — **реалистичный**, а не «скопированный из Excel».

**Входы:**

- загруженный план месяца (Monthly Passport Plan);
- labor plan (`monthly_labor_summary`);
- remaining scope по BOQ;
- historical productivity norm;
- доступные direct hours по звеньям.

**Логика (концепт):**

1. Сопоставить плановые строки с остатком BOQ.  
2. Оценить требуемые чел-ч по норме (management vs target — два сценария).  
3. Сверить с labor capacity (люди × доступные direct hours).  
4. Выявить перегруз / недогруз / нулевой остаток.  
5. Сформировать **draft_month_plan** с пометками риска.

**Выход:** draft месяца до допусков (не финальный паспорт).

**Целевой объект:** `draft_month_plan`.

---

## 8. Execution Admittance

**Вопрос:** можно ли **физически и организационно** выполнить работу в периоде?

| Проверка | Примеры блокеров |
|----------|------------------|
| Фронт | Нет доступа, не готов участок |
| РД | Нет рабочей документации |
| IWP | Пакет не выпущен / не согласован |
| МТР | Нет материалов, нет списания |
| Техника | Нет крана, нет доступа |
| Люди | Нет мобилизации, нет звена |
| ОТ / ТБ | Stop work |
| Качество | HOLD, rework zone |
| Конфликты работ | Пересечение с другими подрядчиками / системами |

**Результат по строке / пакету:** допущено к исполнению / с риском / заблокировано.

**Целевой объект:** `execution_admittance_register`.

---

## 9. Acceptance Admittance

**Вопрос:** можно ли **признать** выполненное и довести до **денег**?

| Проверка | Примеры |
|----------|---------|
| approved basis | Утверждённое основание оплаты |
| КС | Комплект закрытия |
| Исполнительная документация | As-built, акты |
| Схемы | Исполнительные схемы |
| QA / QC | Инспекции, протоколы |
| Списание МТР | Материалы учтены |
| Расценка | Rate approved |
| commercial risk | Спор, claim, hold payment |
| engineering holds | Замечания проектировщика |

**Результат:** допущено к признанию / с риском / заблокировано к cash.

**Целевой объект:** `acceptance_admittance_register`.

---

## 10. Constraint Register

Единый реестр ограничений, питающий оба допуска и перепланирование.

| Поле | Описание |
|------|----------|
| код | Идентификатор ограничения |
| система | System / discipline |
| IWP | Пакет работ |
| причина | Текст / класс причины |
| владелец | Кто снимает |
| срок снятия | Target date |
| заблокированный объём | qty / EV |
| заблокированные чел-ч | Labor impact |
| заблокированный EV | Financial impact |
| заблокированные деньги | Cash impact |

**Целевой объект:** `constraint_register`.

---

## 11. Final Executable Month Passport

Финальный месяц после **Execution Admittance** и **Acceptance Admittance**.

| Статус строки / пакета | Смысл |
|------------------------|--------|
| **approved executable** | Можно исполнять и признавать |
| **approved with risk** | Исполняемо / признаваемо с оговорками |
| **blocked execution** | Нельзя исполнять (Execution) |
| **blocked acceptance** | Исполнили, но нельзя признать / оплатить |

Только **approved executable** (и controlled **approved with risk**) идут в Weekly / Daily breakdown.

**Целевой объект:** `final_month_passport`.

---

## 12. Auto Breakdown (Scheduling)

Декомпозиция утверждённого месяца:

```
Month  →  Week   (weekly_execution_plan)
Week   →  Day    (daily_execution_plan)
Day    →  Crew   (crew_task_plan)
Crew   →  Worker (worker_task_plan)
```

Правила распределения (будущий Scheduling Engine):

- учёт labor capacity и календаря;
- приоритет по остатку и срокам;
- не превышать crew target norm без явного риска;
- резерв на простой / перепланирование.

---

## 13. Daily Progress → Auto Replanning

Каждый день факт из Daily Progress пересчитывает:

| Метрика | Действие |
|---------|----------|
| Остаток дня | plan day − fact day |
| Остаток недели | rolling week |
| Остаток месяца | rolling month |
| Производительность звена | actual vs norm |
| Риск недоосвоения | alert / status |
| План следующего дня | proposed replan |

**Целевой объект:** `replanning_log` (история решений и автопредложений).

**Связь с текущим UI:** страница «Счётчик звена» (Layer 1 burn-down, мобилизация без DP) — ранний индикатор разрыва план ↔ факт; полный Replanning Engine — следующий этап.

---

## 14. Минимальный набор будущих таблиц / views

| Объект | Назначение |
|--------|------------|
| `boq_lifetime_balance` | Остаток BOQ за весь период |
| `boq_productivity_history` | Историческая выработка по BOQ |
| `draft_month_plan` | Черновик месяца до допусков |
| `execution_admittance_register` | Допуск к исполнению |
| `acceptance_admittance_register` | Допуск к признанию |
| `constraint_register` | Реестр ограничений |
| `final_month_passport` | Исполняемый месяц после допусков |
| `weekly_execution_plan` | План недели |
| `daily_execution_plan` | План дня |
| `crew_task_plan` | Задачи звена |
| `worker_task_plan` | Задачи работника |
| `replanning_log` | Лог перепланирования |

На первом этапе MVP — **только views и документация**, без Streamlit-страниц под каждый engine.

---

## 15. Engine modules (логические модули)

| Engine | Ответственность |
|--------|-----------------|
| **Balance Engine** | project qty − actual = remaining |
| **Productivity Engine** | norms, P50/P80, confidence |
| **Capacity Engine** | labor plan, mobilization, direct hours |
| **Draft Month Engine** | реалистичный draft месяца |
| **Execution Admittance Engine** | исполнимость |
| **Acceptance Engine** | признание / cash readiness |
| **Scheduling Engine** | Month → Week → Day → Crew → Worker |
| **Replanning Engine** | факт дня → новый план |

Модули не обязаны быть отдельными Python-пакетами на MVP; достаточно views + чётких контрактов данных.

---

## 16. Главный принцип (три истины)

```
Не всё, что запланировано, является исполнимым.
Не всё, что исполнимо, является признаваемым.
Не всё, что выполнено, становится деньгами.
```

| Этап | Типичная ошибка без допуска |
|------|----------------------------|
| План | «В паспорте 100% — значит сделаем» |
| Исполнение | «Люди на площадке — значит работа идёт» |
| Приёмка | «Сделали — значит оплатят» |

Execution OS вводит **явные gates** между этими этапами.

---

## 17. MVP — границы первого этапа

**В scope MVP (архитектура + аналитика):**

1. Зафиксировать эту архитектуру в репозитории.  
2. Спроектировать Supabase views для остатка BOQ и productivity.  
3. Спроектировать контракты `draft_month_plan`, `constraint_register`, `final_month_passport`.  
4. Согласовать с существующими `smr_*` и `monthly_passport_plan` — без дублирования истины.

**Вне scope MVP (отдельные этапы):**

- новые Streamlit-страницы под каждый engine;
- запись задач Worker Task в Airtable;
- автоматический Scheduling Engine в production;
- замена текущих синков.

**Порядок работ:** см. `NEXT_STEPS.md` → блок «Execution OS — следующие шаги».

---

## Связь с текущим репозиторием csv_fix

| Уже есть | Роль в Execution OS |
|----------|---------------------|
| `pages/05_Исполнение.py` | План-факт месяца (SMR views) |
| `pages/07_Счётчик_звена.py` | Burn-down звена, мобилизация, Layer 2 |
| `pages/06_Качество_данных.py` | Качество факта (вход для Productivity confidence) |
| `monthly_labor_summary` | Capacity Engine (as-is) |
| `monthly_passport_sync_airtable.py` | План месяца (as-is) |
| `daily_progress_sync_upsert.py` | Факт (as-is) |

---

*Документ создан: 2026-05-24 · Владелец: Architect / Orchestrator · Статус: strategic architecture only*
