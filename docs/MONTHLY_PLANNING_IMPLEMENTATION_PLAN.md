# MONTHLY PLANNING — Implementation Plan

> **Статус:** план реализации после Architecture Freeze  
> **Предусловие:** `docs/MONTHLY_PLANNING_ARCHITECTURE_FREEZE.md`  
> **Принцип:** этапы независимы, каждый даёт проверяемый результат в UI

---

## Phase 0 — Data foundation (Supabase) ✅ SQL prepared

**Deploy order (Supabase SQL Editor):**

1. `sql/monthly_plan_lines_v2_labor_meta.sql`
2. `sql/planning_config_v1.sql`
3. `sql/monthly_plan_labor_engine_v1.sql`

| # | Задача | Артефакт | Статус |
|---|--------|----------|--------|
| 0.1 | Labor metadata columns on v2 | `sql/monthly_plan_lines_v2_labor_meta.sql` | ✅ |
| 0.2 | `planning_config` + `hours_per_person_month = 176` | `sql/planning_config_v1.sql` | ✅ |
| 0.3 | `monthly_plan_labor_lines_v1` | `sql/monthly_plan_labor_engine_v1.sql` | ✅ |
| 0.4 | `monthly_plan_labor_summary_v1` | same | ✅ |
| 0.5 | `monthly_plan_labor_admission_v1` + `_summary_v1` | same | ✅ |
| 0.6 | `monthly_plan_capacity_v1` | same | ✅ |
| 0.7 | `monthly_plan_passport_resource_v1` | same | ✅ |

**Helper (internal):** `monthly_plan_constraint_line_agg_v1`, `monthly_plan_admission_labor_status()`, `planning_config_numeric()`

**Критерий готовности:** SQL deploy в Supabase; select по project+month возвращает hours, cost, fte.

---

## Phase 1 — Shared read service ✅

**Цель:** единая точка чтения для всех страниц.

| # | Задача | Артефакт | Статус |
|---|--------|----------|--------|
| 1.1 | `services/monthly_plan_labor_service.py` | load_* + format helpers | ✅ |
| 1.2 | Фильтры: project, month, passport_id | query-level `.eq()` | ✅ |
| 1.3 | Unit smoke: import + Supabase read | manual | ✅ |

**Критерий готовности:** service импортируется без дублирования формул FTE; views читаются read-only.

**Не начинать Phase 2** без отдельной команды.

---

## Phase 2 — Конструктор (10B)

**Цель:** полный lifecycle create + persist norm metadata.

| # | Задача |
|---|--------|
| 2.1 | `map_v2_session_item_to_plan_db_row` — писать norm_* и labor_rate |
| 2.2 | `map_v2_plan_db_row_to_session_item` — восстанавливать norm_scenario из БД (не default P50) |
| 2.3 | KPI-полоса: + FTE, + breakdown norm source |
| 2.4 | Таблица разрезов (discipline / title / crew / …) |
| 2.5 | Построчно: FTE line = labor_hours / 176 |

**Критерий готовности:** save → reload → norm source сохранён; сводка FTE видна.

**Не трогать:** admission send flow, passport service.

---

## Phase 3 — Экономика (Page 22)

**Цель:** страница отвечает на вопрос «хватит ли ресурсов».

| # | Задача |
|---|--------|
| 3.1 | Верхний блок «Трудовая экономика месяца» (6 KPI) |
| 3.2 | Таблица capacity по звеньям (`monthly_plan_capacity_v1`) |
| 3.3 | AI Action Engine — collapsible secondary (не primary) |
| 3.4 | Заголовок/caption страницы — соответствие роли |

**Критерий готовности:** при открытии Page 22 видны demand vs capacity без входа в 10B.

---

## Phase 4 — Допуск (Page 21)

**Цель:** труд в контуре допуска.

| # | Задача |
|---|--------|
| 4.1 | KPI-полоса «Труд в допуске» (часы по READY / WARNING / BLOCKED) |
| 4.2 | Маппинг package_status + check_status → READY / WARNING / BLOCKED |
| 4.3 | Сохранить существующую KPI-полосу в ₽ (ворота) |

**Критерий готовности:** допущенные/заблокированные часы видны в сводке.

---

## Phase 5 — Управленческие решения (Page 23)

**Цель:** governance без пересчёта.

| # | Задача |
|---|--------|
| 5.1 | Маппинг UI → INCLUDE / EXCLUDE / DEFER / RISK_ACCEPTED |
| 5.2 | Сводка: часы/₽ по группам решений из read-model + session composition |
| 5.3 | Убрать misleading «Норма выработки» → «Интенсивность плана, ч/ед» |
| 5.4 | Не дублировать admission checks (ссылка на Page 21) |

**Критерий готовности:** composition change → KPI hours update без пересчёта labor_hours.

---

## Phase 6 — Паспорт (Page 12)

**Цель:** официальное обязательство с resource snapshot.

| # | Задача |
|---|--------|
| 6.1 | Header KPI: FTE required / available / gap |
| 6.2 | Разрезы: discipline, title, system, crew |
| 6.3 | `monthly_passport_service`: snapshot FTE metrics в header при formation |
| 6.4 | DDL: `total_fte_required`, `total_fte_available`, `fte_gap` в passports (optional columns) |

**Критерий готовности:** утверждённый паспорт показывает полный resource commitment.

---

## Phase 7 — Handbook & QA

| # | Задача |
|---|--------|
| 7.1 | Обновить `docs/v2_technical_architecture_handbook.py` |
| 7.2 | Сверка KPI между страницами на тестовом project+month |
| 7.3 | Checklist anti double-count |

---

## Зависимости

```
Phase 0 → Phase 1 → Phase 2
                 → Phase 3
                 → Phase 4
                 → Phase 5
                 → Phase 6 (depends on passport service + Phase 0 views)
```

## Рекомендуемый порядок UI delivery

1. **Phase 0 + 1 + 2** — Конструктор (MVP: «что и каким трудом»)
2. **Phase 3** — Экономика («хватит ли людей»)
3. **Phase 4** — Допуск
4. **Phase 5 + 6** — Решения + Паспорт

## Out of scope (этот контур)

- Daily Progress / Fact Hours
- Execution / Shift Acceptance
- Commercial / Payroll
- Новые Streamlit-страницы
