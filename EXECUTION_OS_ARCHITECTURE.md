# ARCHITECTURE — Month → Week → Day → Crew → Worker Execution Planning System

> **Статус:** стратегическая архитектура (документация).  
> **Не является** текущей реализацией в коде. Streamlit, SQL и engine modules — отдельные этапы после проектирования views.  
> **Связанные файлы:** `PROJECT_CONTEXT.md`, `README_SMR_EXECUTION_LOGIC.md`, `NEXT_STEPS.md`  
> **Контур месячного планирования (FROZEN):** `docs/MONTHLY_PLANNING_ARCHITECTURE_FREEZE.md`, `docs/MONTHLY_PLANNING_IMPLEMENTATION_PLAN.md`

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
- что **экономически оправдано** для подрядчика (не только исполнимо и признаваемо);
- где **заблокирован** фронт, люди, МТР, РД, качество, коммерция или экономика звена;
- как **ежедневный факт** меняет остаток и план следующего дня.

**Отличие от классического план-факт дашборда:** план — это гипотеза; перед финальным паспортом месяца проходят **три обязательных gate** (Three Admittance Model), затем декомпозиция до задач звена и работника.

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
PLAN
        ↓
Gate 1 — EXECUTION ADMITTANCE
        ↓
Gate 2 — ACCEPTANCE ADMITTANCE
        ↓
Gate 3 — ECONOMIC ADMITTANCE
        ↓
FINAL EXECUTABLE MONTH
        ↓
Month → Week → Day → Crew → Worker
        ↓
Execution
        ↓
Reality Capture (Daily Progress)
        ↓
Acceptance
        ↓
Cash
```

**Подготовка плана (до gates):** BOQ / IWP / System → Remaining Scope → Historical Productivity Norm → Labor Capacity → **Draft Month Plan**.

Каждый gate отвечает на отдельный вопрос. Только после прохождения всех трёх формируется **Final Executable Month** и допускается breakdown на неделю / день / звено / работника.

Полная модель gates: раздел **THREE ADMITTANCE MODEL** ниже.

---

# THREE ADMITTANCE MODEL

Три обязательных gate перед **Final Passport Month**. Обнаружено при проектировании **Draft Month Engine**: план может быть физически исполним и коммерчески признаваем, но **экономически убыточен** для подрядчика.

**Кейс:** звено **АСИ-16** — плановый EV ≈ 476 466 ₽, стоимость звена ≈ 1 872 000 ₽. Физически выполнимо, признание закрываемо, **экономически — убыток**.

```
Исполнимо ≠ выгодно
Признаваемо ≠ выгодно
```

---

## Gate 1 — EXECUTION ADMITTANCE

**Назначение:** допуск **физической исполнимости**.

**Ключевой вопрос:** «Можно ли физически выполнить?»

**Участники:** MTO, PTO, Construction, HSE, QA/QC.

**Проверяет:**

- RD readiness  
- IWP readiness  
- Front availability  
- Materials availability  
- Crew availability  
- Equipment availability  
- Permit / HSE readiness  
- Workface conflicts  

**Статусы:**

| Статус | Смысл |
|--------|--------|
| **EXECUTABLE** | Можно выходить на фронт |
| **PARTIALLY_EXECUTABLE** | Частично, с ограничениями |
| **BLOCKED** | Физически нельзя |

**Принцип:** **Запланировано ≠ Исполнимо**

**Целевой объект:** `execution_admittance_register`

---

## Gate 2 — ACCEPTANCE ADMITTANCE

**Назначение:** допуск **коммерческого признания**.

**Ключевой вопрос:** «Можно ли довести до признания и денег?»

**Участники:** PTO, QA/QC, Contracts, MTO, Owner / EPC constraints.

**Проверяет:**

- Approved basis  
- Engineering holds  
- QA/QC acceptance  
- Исполнительная документация  
- КС closure readiness  
- Approved rate  
- MTR write-off feasibility  
- Recognition feasibility  

**Статусы:**

| Статус | Смысл |
|--------|--------|
| **ACCEPTABLE** | Можно признавать и вести к оплате |
| **HIGH_COMMERCIAL_RISK** | Признание возможно с риском |
| **BLOCKED_FOR_ACCEPTANCE** | Нельзя довести до признания / cash |

**Принцип:** **Исполнимо ≠ Признаваемо**

**Целевой объект:** `acceptance_admittance_register`

---

## Gate 3 — ECONOMIC ADMITTANCE

**Назначение:** допуск **экономической целесообразности** (обязательный слой с 2026-05).

**Ключевой вопрос:** «Имеет ли смысл выполнять этот scope этим звеном?»

**Проверяет:**

- Planned EV  
- Crew Cost  
- Direct Hours  
- Loaded Labor Cost  
- Productivity Norm  
- Break-even volume  
- Margin feasibility  

**Базовая формула:**

```
Crew EV − Crew Cost = Crew Margin
```

**Дополнительные показатели:**

- EV / Cost Ratio  
- Break-even Volume  
- Required Additional EV  
- Low Value Scope flag  

**Статусы:**

| Статус | Смысл |
|--------|--------|
| **ECONOMIC_OK** | Маржа в норме |
| **ECONOMIC_LOW_MARGIN** | Низкая, но допустимая маржа |
| **ECONOMIC_BREAK_EVEN** | На грани безубыточности |
| **ECONOMIC_FAIL** | Подрядчик теряет деньги |
| **LOW_VALUE_SCOPE** | Scope с низкой ценностью относительно cost |

**Пример — АСИ-16:**

| Показатель | Значение |
|------------|----------|
| Planned EV | ≈ 476 466 ₽ |
| Crew Cost | ≈ 1 872 000 ₽ |
| **Result** | **ECONOMIC_FAIL** |

**Комментарий:** план физически возможен; план коммерчески признаваем; **подрядчик теряет деньги**.

**Принцип:** **Признаваемо ≠ выгодно**

**Целевой объект:** `economic_admittance_register`

---

## Сводка Three Admittance Model

| Gate | Вопрос | Типичная ошибка |
|------|--------|-----------------|
| 1 Execution | Можно ли сделать? | «В паспорте есть — значит сделаем» |
| 2 Acceptance | Можно ли признать? | «Сделали — значит закроем КС» |
| 3 Economic | Имеет ли смысл? | «Признаваемо — значит выгодно» |

**Final Executable Month** допускается только когда три gate согласованы (допустимы controlled risk-статусы, не BLOCKED / ECONOMIC_FAIL без решения).

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

## 8. Execution Admittance (Gate 1)

> **Полная спецификация:** раздел **THREE ADMITTANCE MODEL → Gate 1**.

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

**Статусы:** `EXECUTABLE` · `PARTIALLY_EXECUTABLE` · `BLOCKED`

**Целевой объект:** `execution_admittance_register`.

---

## 9. Acceptance Admittance (Gate 2)

> **Полная спецификация:** раздел **THREE ADMITTANCE MODEL → Gate 2**.

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

**Статусы:** `ACCEPTABLE` · `HIGH_COMMERCIAL_RISK` · `BLOCKED_FOR_ACCEPTANCE`

**Целевой объект:** `acceptance_admittance_register`.

---

## 9a. Economic Admittance (Gate 3)

> **Полная спецификация:** раздел **THREE ADMITTANCE MODEL → Gate 3**.

**Вопрос:** имеет ли смысл выполнять scope **этим звеном** с точки зрения маржи?

**Статусы:** `ECONOMIC_OK` · `ECONOMIC_LOW_MARGIN` · `ECONOMIC_BREAK_EVEN` · `ECONOMIC_FAIL` · `LOW_VALUE_SCOPE`

**Целевой объект:** `economic_admittance_register`.

**Связь с UI:** burn-down звена — ранний индикатор; **Plan Diagnostics Engine** — объяснение причин плохого плана.

---

## 10. Constraint Register

Единый реестр ограничений, питающий **все три gate** и перепланирование.

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

Финальный месяц после прохождения **трёх gate** (Execution + Acceptance + **Economic**).

| Статус строки / пакета | Смысл |
|------------------------|--------|
| **approved executable** | Все три gate пройдены (допустим controlled risk) |
| **approved with risk** | Исполняемо / признаваемо / экономика — с оговорками |
| **blocked execution** | Gate 1 — нельзя исполнять |
| **blocked acceptance** | Gate 2 — нельзя признать / оплатить |
| **blocked economic** | Gate 3 — экономически нецелесообразно (`ECONOMIC_FAIL`, `LOW_VALUE_SCOPE`) |

Только строки с **approved executable** (и controlled **approved with risk** без `ECONOMIC_FAIL`) идут в Weekly / Daily breakdown.

**Правило:** прохождение Gate 1 и Gate 2 **без** Gate 3 — типичная ловушка (пример АСИ-16).

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
| `execution_admittance_register` | Gate 1 — допуск к исполнению |
| `acceptance_admittance_register` | Gate 2 — допуск к признанию |
| `economic_admittance_register` | Gate 3 — экономический допуск |
| `constraint_register` | Реестр ограничений |
| `final_month_passport` | Исполняемый месяц после трёх gate |
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
| **Execution Admittance Engine** | Gate 1 — исполнимость |
| **Acceptance Engine** | Gate 2 — признание / cash readiness |
| **Economic Admittance Engine** | Gate 3 — маржа, break-even, ECONOMIC_FAIL |
| **Plan Diagnostics Engine** | «Почему план плохой?» — коды диагностики |
| **Scheduling Engine** | Month → Week → Day → Crew → Worker |
| **Replanning Engine** | факт дня → новый план |

Модули не обязаны быть отдельными Python-пакетами на MVP; достаточно views + чётких контрактов данных.

---

## 16. Главный принцип (четыре истины)

```
Не всё, что запланировано, является исполнимым.
Не всё, что исполнимо, является признаваемым.
Не всё, что признаваемо, является выгодным.
Не всё, что выполнено, становится деньгами.
```

| Этап | Типичная ошибка без gate |
|------|---------------------------|
| План | «В паспорте 100% — значит сделаем» |
| Исполнение (Gate 1) | «Люди на площадке — значит работа идёт» |
| Приёмка (Gate 2) | «Сделали — значит закроем КС» |
| Экономика (Gate 3) | «Признаваемо — значит маржа OK» (кейс АСИ-16) |
| Cash | «Выполнили — значит оплатят» |

Execution OS вводит **три явных gate** (Three Admittance Model) перед финальным паспортом месяца.

---

## 17. MVP — границы первого этапа

**В scope MVP (архитектура + аналитика):**

1. Зафиксировать эту архитектуру в репозитории.  
2. Спроектировать Supabase views для остатка BOQ и productivity.  
3. Спроектировать контракты `draft_month_plan`, `constraint_register`, `final_month_passport`, `economic_admittance_register`.  
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

*Документ создан: 2026-05-24 · Обновлено: 2026-05-24 (Three Admittance Model) · Владелец: Architect / Orchestrator · Статус: strategic architecture only*
