# MONTHLY PLANNING — Architecture Freeze

> **Проект:** csv_fix / Execution OS  
> **Статус:** FROZEN — утверждённая архитектура перед реализацией  
> **Дата фиксации:** 2026-05-29  
> **Scope:** только контур месячного планирования (Planning Layer)

---

## 1. Общий принцип

- **Не создавать новые страницы.** Развивать существующий контур.
- **Каждый этап — одна функция.** Страницы не дублируют роли друг друга.
- **Один Source of Truth для плановых трудозатрат:** `monthly_plan_lines_v2.labor_hours`.

### Жизненный цикл данных

```
Конструктор → Экономика → Допуск → Управленческие решения → Паспорт
  (create)     (analyze)   (gate)        (decide)              (commit)
```

### Маппинг страниц Streamlit

| Этап | Файл | Меню |
|------|------|------|
| 1. Конструктор | `pages/10B_Конструктор_месячного_плана.py` | Конструктор месячного плана |
| 2. Экономика | `pages/22_Admission_AI_Action_Engine.py` | Экономика месячного плана |
| 3. Допуск | `pages/21_Admission_Управление_ограничениями_месячного_плана.py` | Допуск месячного плана |
| 4. Управленческие решения | `pages/23_Admission_War_Room_ограничений.py` | Управление решениями по месячному плану |
| 5. Паспорт | `pages/12_Planning_Паспорт_месяца.py` | Паспорт месячного плана |

---

## 2. Этап 1 — Конструктор месячного плана

**Назначение:** создание `Monthly Plan Line`. Единственное место расчёта и записи.

**Главный вопрос:** *Что мы собираемся выполнить и каким трудом?*

### Обязательные поля строки

| Поле | Тип | SoT |
|------|-----|-----|
| BOQ | `boq_code`, `boq_name` | v2 |
| Объём | `planned_qty`, `unit` | v2 |
| Стоимость работ | `plan_value` | v2 |
| Источник нормы | `norm_source` | v2 (persist) |
| Норма (ч/ед.) | `norm_hours_per_unit` | v2 (persist) |
| Сценарий нормы | `norm_scenario` | v2 (persist) |
| Плановые трудозатраты | `labor_hours` | v2 |
| Стоимость труда | `labor_cost` | v2 |
| Требуемое кол-во людей (FTE) | computed | `labor_hours / hours_per_person_month` |

### KPI страницы (сводка)

- BOQ в плане · плановый объём · стоимость работ
- **Плановые чел-ч** · **стоимость труда** · **требуется FTE**
- **Разбивка по источнику норм** (P50 / P80 / manual / no norm)
- Таблица разрезов: титул · дисциплина · BOQ · система · очередь · IWP · звено

### Запрещено на этапе

- Статусы допуска, outcome War Room, frozen-паспорт
- Анализ дефицита мощности (это Экономика)

---

## 3. Этап 2 — Экономика месячного плана

**Назначение:** read-only анализ ресурсов сформированного плана.

**Главный вопрос:** *Хватит ли нам ресурсов выполнить этот месячный план?*

### KPI страницы

| KPI | Источник |
|-----|----------|
| Общая стоимость работ | sum `plan_value` |
| Общие плановые трудозатраты | sum `labor_hours` |
| Общая стоимость труда | sum `labor_cost` |
| Требуемое кол-во людей (FTE) | computed |
| Имеющееся кол-во людей (FTE) | `monthly_labor_summary` |
| Дефицит / профицит ресурсов | capacity − demand |

### Запрещено на этапе

- Пересчёт норм и часов
- Изменение plan lines
- Статусы допуска и управленческие решения

---

## 4. Этап 3 — Допуск месячного плана

**Назначение:** статус исполнимости. Не рассчитывает часы, не меняет нормы.

**Главный вопрос:** *Какая часть месячного плана реально может быть запущена в производство?*

### Статусы строки (допуск)

- `READY` (допущено)
- `WARNING` (под риском)
- `BLOCKED` / `FAIL` (заблокировано)

### KPI страницы (труд, агрегат)

- Чел-ч в допуске (scope: `SENT_TO_ADMISSION`)
- Чел-ч допущенные · заблокированные · под риском
- Чел-ч к запуску (политика: READY + WARNING)

### Запрещено на этапе

- Пересчёт `labor_hours`
- FTE gap / roster analysis (это Экономика)
- Состав паспорта (это War Room)

---

## 5. Этап 4 — Управленческие решения

**Назначение:** governance. Не пересчитывает и не агрегирует заново — **фильтрует pre-aggregated read-model** по решению.

**Главный вопрос:** *Что станет обязательством компании на следующий месяц?*

### Решения

| Решение | Смысл |
|---------|-------|
| `INCLUDE` | Включить в обязательство месяца |
| `EXCLUDE` | Исключить из обязательства |
| `DEFER` | Отложить |
| `RISK_ACCEPTED` | Принять риск, включить с оговоркой |

### KPI страницы

Отображение **уже посчитанных** часов/стоимости по группам решений (не новый расчёт в UI).

### Запрещено на этапе

- Изменение норм и `labor_hours`
- Capacity analysis
- Детальные checks отделов (это Допуск)

---

## 6. Этап 5 — Итоговый паспорт месяца

**Назначение:** frozen snapshot официального обязательства. Не расчётная страница.

**Главный вопрос:** *Какой объём, за какие деньги, каким трудом и какими ресурсами компания официально обязалась выполнить в этом месяце?*

### Агрегаты паспорта

- BOQ count · общий объём · стоимость работ
- Требуемые чел-ч · стоимость труда
- Требуемое FTE · доступное FTE · дефицит/профицит (snapshot на момент утверждения)

### Разрезы (официальный отчёт)

- По дисциплинам · титулам · системам · звеньям

### SoT

`monthly_plan_passports` + `monthly_plan_passport_lines` + view `monthly_plan_passport_dashboard_v1`

---

## 7. Data architecture

### Source of Truth

| Слой | Объект | Grain |
|------|--------|-------|
| Plan lines | `monthly_plan_lines_v2` | `plan_line_id` |
| Norm reference | `boq_productivity_norms_v2` | project + facility + discipline + boq |
| Crew capacity | `monthly_labor_summary` | project + month + crew |
| Admission status | `monthly_plan_constraints` | line / package |
| Passport | `monthly_plan_passport_lines` | `passport_line_id` |

### Read-model views (Phase 0 — SQL in `sql/monthly_plan_labor_engine_v1.sql`)

| View | Consumers |
|------|-----------|
| `monthly_plan_labor_lines_v1` | все этапы |
| `monthly_plan_labor_summary_v1` | Конструктор, Экономика |
| `monthly_plan_capacity_v1` | Экономика |
| `monthly_plan_labor_admission_v1` | Допуск |
| `monthly_plan_labor_admission_summary_v1` | Допуск |
| `monthly_plan_passport_resource_v1` | Паспорт |

**Admission launch policy:** `launch_hours` = READY + WARNING.

### Anti double-count rules

1. Агрегация только по `plan_line_id`.
2. Каждая страница — свой lifecycle scope (см. этапы 1–5).
3. Паспорт читает только passport tables, не v2.
4. `monthly_plan_constraints.required_hours` — копия для checks, не SoT KPI.

### Config (`sql/planning_config_v1.sql`)

| Параметр | Default |
|----------|---------|
| `hours_per_person_month` | 176 |
| `labor_rate_per_hour` | 3000 (до persist в v2, Phase 2) |

### Labor metadata columns (`sql/monthly_plan_lines_v2_labor_meta.sql`)

`norm_scenario`, `norm_hours_per_unit`, `norm_source`, `labor_rate_per_hour`

---

## 8. Реализация — порядок этапов

См. `docs/MONTHLY_PLANNING_IMPLEMENTATION_PLAN.md` (генерируется вместе с аудитом).

---

## Связанные документы

- `EXECUTION_OS_ARCHITECTURE.md` — стратегическая архитектура Execution OS
- `docs/v2_technical_architecture_handbook.py` — технический handbook v2
- `sql/monthly_plan_lines_v2.sql` — DDL plan lines
