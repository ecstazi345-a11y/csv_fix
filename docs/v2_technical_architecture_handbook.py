# ============================================================
# Техническая архитектура v2 — enterprise technical handbook (library)
# Рендерится из: pages/10B_Конструктор_месячного_плана.py → модуль 4
# Read-only документация. Без Supabase write, без расчётов runtime.
# Архив standalone: archive/_archive_99_Техническая_архитектура_v2.py
# ============================================================

from __future__ import annotations

import pandas as pd
import streamlit as st

PAGE_TITLE = "Техническая архитектура v2"
PAGE_SUBTITLE = (
    "Полный паспорт логики, данных, расчётов, session-модели и потоков "
    "конструктора месячного плана v2 (EPC / enterprise system handbook)."
)
PRODUCTION_PAGE = "pages/10B_Конструктор_месячного_плана.py"
SQL_SCHEMA = "sql/monthly_plan_lines_v2.sql"


def inject_doc_styles() -> None:
    st.markdown(
        """
        <style>
        .v2-doc-header {
            font-size: 1.65rem;
            font-weight: 700;
            color: #0f172a;
            letter-spacing: -0.02em;
            margin-bottom: 0.35rem;
        }
        .v2-doc-subtitle {
            color: #64748b;
            font-size: 0.92rem;
            line-height: 1.45;
            margin-bottom: 1.25rem;
        }
        .v2-doc-note {
            color: #475569;
            font-size: 0.88rem;
            line-height: 1.5;
            margin: 0.35rem 0 0.65rem 0;
        }
        .v2-doc-pipeline {
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.82rem;
            line-height: 1.55;
            color: #334155;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 0.75rem 1rem;
            margin: 0.5rem 0 0.75rem 0;
            white-space: pre-wrap;
        }
        .v2-doc-badge {
            display: inline-block;
            padding: 0.12rem 0.45rem;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 600;
            margin-right: 0.35rem;
            margin-bottom: 0.25rem;
            border: 1px solid #e2e8f0;
            background: #f8fafc;
            color: #475569;
        }
        .v2-doc-badge.ok { background: #ecfdf3; border-color: #bbf7d0; color: #166534; }
        .v2-doc-badge.partial { background: #eff6ff; border-color: #dbeafe; color: #1e40af; }
        .v2-doc-badge.session { background: #f5f3ff; border-color: #ddd6fe; color: #5b21b6; }
        .v2-doc-badge.off { background: #f1f5f9; border-color: #e2e8f0; color: #64748b; }
        .v2-doc-badge.legacy { background: #fff7ed; border-color: #fed7aa; color: #9a3412; }
        .v2-doc-badge.warn { background: #fffbeb; border-color: #fde68a; color: #92400e; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown(f'<h1 class="v2-doc-header">{PAGE_TITLE}</h1>', unsafe_allow_html=True)
    st.markdown(f'<p class="v2-doc-subtitle">{PAGE_SUBTITLE}</p>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="v2-doc-note">Реализация: <code>{PRODUCTION_PAGE}</code> · '
        f'SQL: <code>{SQL_SCHEMA}</code> · v1: '
        f'<code>pages/10_Planning_Конструктор_месячного_плана.py</code> (параллельно, не заменён)</p>',
        unsafe_allow_html=True,
    )


def section_01_purpose() -> None:
    with st.expander("1. Назначение конструктора месячного плана v2", expanded=False):
        st.markdown(
            """
**Зачем нужен v2**

Конструктор месячного плана v2 — модульная enterprise-версия инструмента планирования работ по BOQ
для EPC-проекта. Цель: поэтапная замена v1 с чистой архитектурой данных, без hot-swap production.

**Отличие от v1 (актуально)**

| Аспект | v1 | v2 |
| --- | --- | --- |
| Архитектура страницы | монолит | модульные expander-блоки |
| Persistence плана | `monthly_plan_drafts` + `monthly_plan_draft_lines` | **`monthly_plan_lines_v2`** (single-table) |
| UX загрузки плана | кнопка load draft, draft_id | **auto-load** по `project_code` + `month_key` |
| Save / Send | production flow | **подключено** (фаза 1.2) |
| Статусы строк плана | draft / review queue | `NOT_SENT` / `SENT_TO_ADMISSION` |
| Корректировка остатка | production write | **write включён** (`monthly_scope_manual_adjustments`) |
| UI | legacy | enterprise redesign |

**Модульная архитектура страницы 10B**

Каждый expander — отдельный operational module:

1. Загрузка исходных данных (заглушка)
2. Остатки и доступность к планированию (BOQ scope)
3. Единый месячный план (persistence + actions)
4. Техническая архитектура v2 (этот handbook)

**Основной business flow (актуальный)**

```
read BOQ scope → select row → adjust residual (optional)
→ add to month plan (session pending)
→ review unified month plan → save → send to admission
→ (roadmap) review_queue → constraints → passport month
```

**Принцип co-existence с v1**

`10_Planning_…` продолжает работать. v2 строится как замена по этапам roadmap, не как единовременный cutover.
            """
        )


def section_02_pipeline() -> None:
    with st.expander("2. Pipeline данных", expanded=False):
        st.markdown("#### Macro pipeline (business)")
        st.markdown(
            """
<div class="v2-doc-pipeline">monthly_scope_picker_view (BOQ / остатки / нормы)
↓
Конструктор v2 — Единый месячный план (session + UI)
↓
monthly_plan_lines_v2 (Supabase persistence)
↓
Контур допуска (roadmap: review_queue + constraints)
↓
Чистый паспорт месяца (roadmap)</div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("#### Micro pipeline (Модуль 1 — BOQ scope)")
        st.markdown(
            """
<div class="v2-doc-pipeline">monthly_scope_picker_view
↓
load_v2_boq_scope_from_supabase()
↓
normalize_v2_scope_df()
↓
calculate_v2_basic_scope_metrics()
↓
apply_v2_session_draft_reservation()   ← только is_pending, не DB-план
↓
apply_scope_filters()
↓
render_scope_kpi_cards() / render_scope_table()
↓
render_selected_boq_card() → корректировка / добавление в план</div>
            """,
            unsafe_allow_html=True,
        )

        steps_df = pd.DataFrame(
            [
                {"Шаг": "monthly_scope_picker_view", "Описание": "Source of truth остатков BOQ (read-only view)"},
                {"Шаг": "normalize_v2_scope_df()", "Описание": "Нормализация колонок, типов, ключей BOQ"},
                {"Шаг": "calculate_v2_basic_scope_metrics()", "Описание": "remaining, available, status, стоимости"},
                {
                    "Шаг": "apply_v2_session_draft_reservation()",
                    "Описание": "Уменьшение available только по несохранённым is_pending строкам",
                },
                {"Шаг": "apply_scope_filters()", "Описание": "Фильтрация среза по UI"},
                {"Шаг": "render_selected_boq_card()", "Описание": "Detail panel: метрики, корректировка, add to plan"},
            ]
        )
        st.dataframe(steps_df, use_container_width=True, hide_index=True)

        st.markdown("#### Micro pipeline (Модуль 3 — Единый месячный план)")
        st.markdown(
            """
<div class="v2-doc-pipeline">_v2_resolve_draft_scope() → project + month
↓
hydrate_v2_month_plan_if_needed()   ← auto-load при смене scope
↓
_v2_filter_items_for_scope() → session items текущего месяца
↓
map_v2_session_draft_to_display_df() → таблица UI
↓
multi-row selection → render_v2_plan_action_bar()
↓
save / edit / delete / send / clear pending</div>
            """,
            unsafe_allow_html=True,
        )


def section_03_supabase() -> None:
    with st.expander("3. Таблицы и view Supabase", expanded=False):
        supabase_df = pd.DataFrame(
            [
                {
                    "Объект": "monthly_plan_lines_v2",
                    "Тип": "table",
                    "Назначение": "Единый месячный план v2 — persistence строк плана",
                    "Используется в v2": "да — primary write",
                    "Write?": "insert / update / delete / status",
                },
                {
                    "Объект": "monthly_scope_picker_view",
                    "Тип": "view",
                    "Назначение": "BOQ scope: total, executed, planning_remaining, нормы",
                    "Используется в v2": "да",
                    "Write?": "read-only",
                },
                {
                    "Объект": "monthly_scope_manual_adjustments",
                    "Тип": "table",
                    "Назначение": "Ручные корректировки выполненного до Daily Progress",
                    "Используется в v2": "да",
                    "Write?": "save / delete adjustment",
                },
                {
                    "Объект": "monthly_labor_summary",
                    "Тип": "table",
                    "Назначение": "Источник crew_code / звеньев",
                    "Используется в v2": "да",
                    "Write?": "read-only",
                },
                {
                    "Объект": "monthly_plan_drafts",
                    "Тип": "table (legacy v1)",
                    "Назначение": "Заголовки черновиков планов",
                    "Используется в v2": "нет (UX-модель v2 отказалась)",
                    "Write?": "код legacy в 10B, UI недоступен",
                },
                {
                    "Объект": "monthly_plan_draft_lines",
                    "Тип": "table (legacy v1)",
                    "Назначение": "Строки черновика v1",
                    "Используется в v2": "нет",
                    "Write?": "код legacy в 10B, UI недоступен",
                },
                {
                    "Объект": "monthly_plan_review_queue",
                    "Тип": "table",
                    "Назначение": "Очередь допуска",
                    "Используется в v2": "roadmap",
                    "Write?": "send v2 пока не пишет сюда",
                },
                {
                    "Объект": "monthly_plan_constraints",
                    "Тип": "table",
                    "Назначение": "Ограничения допуска",
                    "Используется в v2": "roadmap",
                    "Write?": "не подключено",
                },
                {
                    "Объект": "daily_progress_active",
                    "Тип": "table",
                    "Назначение": "Факт выполнения (через view)",
                    "Используется в v2": "косвенно через picker view",
                    "Write?": "read-only",
                },
            ]
        )
        st.dataframe(supabase_df, use_container_width=True, hide_index=True)
        st.markdown(
            """
<span class="v2-doc-badge ok">production write v2</span>
<span class="v2-doc-badge session">session overlay</span>
<span class="v2-doc-badge legacy">legacy v1 tables</span>
<span class="v2-doc-badge off">roadmap</span>

**Production write в v2 сейчас:** `monthly_scope_manual_adjustments`, `monthly_plan_lines_v2`.
            """,
            unsafe_allow_html=True,
        )


def section_04_monthly_plan_lines_v2() -> None:
    with st.expander("4. Модель данных monthly_plan_lines_v2", expanded=False):
        st.markdown(
            """
**Single-table philosophy**

Один `project_code` + один `month_key` = один логический месячный план (много строк).
Нет отдельной header-таблицы, нет `draft_id`, нет кнопки «загрузить черновик».

**Почему ушли от draft/header UX**

| Проблема draft/header | Решение v2 |
| --- | --- |
| Два шага: создать draft → load draft | Auto-hydrate при выборе project/month |
| Потеря continuity после restart | Строки всегда в `monthly_plan_lines_v2` |
| Дублирование сущностей header/lines | Одна таблица = одна правда |
| Сложный merge session ↔ saved draft | Session = overlay; DB = persisted truth |

**Persistence logic**

- Новая строка: `is_pending=True`, `plan_line_id=None` → save → insert
- Редактирование NOT_SENT: `is_pending=True` → save → update по `plan_line_id`
- Send: update `status` + `sent_to_constraints_at` (без delete/recreate)
- Delete: только NOT_SENT (DB delete или session remove)

**Month continuity**

Пользователь может вернуться через неделю, выбрать тот же project + month →
`hydrate_v2_month_plan_if_needed` подтянет все строки из Supabase автоматически.
Несохранённые pending строки текущего scope сохраняются при hydrate (если не force).
            """
        )

        fields_df = pd.DataFrame(
            [
                {
                    "Поле": "plan_line_id",
                    "Тип": "uuid PK",
                    "Назначение": "Технический первичный ключ строки. Не business key — один BOQ может иметь несколько строк в месяце.",
                },
                {
                    "Поле": "project_code",
                    "Тип": "text",
                    "Назначение": "Код проекта. Часть scope-ключа плана вместе с month_key.",
                },
                {
                    "Поле": "month_key",
                    "Тип": "text",
                    "Назначение": "Месяц планирования (например 2026-06). Часть scope-ключа.",
                },
                {
                    "Поле": "facility",
                    "Тип": "text",
                    "Назначение": "Титул / объект (facility_building). В UI — колонка «Титул».",
                },
                {
                    "Поле": "discipline",
                    "Тип": "text",
                    "Назначение": "Строительная дисциплина (СМР, ЭМ, …). В UI — «Дисциплина».",
                },
                {
                    "Поле": "boq_code",
                    "Тип": "text",
                    "Назначение": "Код BOQ. Business identifier работы.",
                },
                {
                    "Поле": "boq_name",
                    "Тип": "text",
                    "Назначение": "Наименование работ по BOQ.",
                },
                {
                    "Поле": "unit",
                    "Тип": "text",
                    "Назначение": "Единица измерения объёма.",
                },
                {
                    "Поле": "planned_qty",
                    "Тип": "numeric",
                    "Назначение": "Плановый объём работ на месяц. ≥ 0.",
                },
                {
                    "Поле": "crew",
                    "Тип": "text",
                    "Назначение": "Код звена (crew_code в session).",
                },
                {
                    "Поле": "crew_size",
                    "Тип": "integer",
                    "Назначение": "Численность звена. Влияет на duration_shifts в UI.",
                },
                {
                    "Поле": "labor_hours",
                    "Тип": "numeric",
                    "Назначение": "Трудозатраты (чел-ч) = planned_qty × norm_hours_per_unit.",
                },
                {
                    "Поле": "labor_cost",
                    "Тип": "numeric",
                    "Назначение": "Стоимость труда = labor_hours × ставка (3000 ₽/ч по умолчанию).",
                },
                {
                    "Поле": "unit_price",
                    "Тип": "numeric",
                    "Назначение": "Цена за единицу объёма из BOQ scope.",
                },
                {
                    "Поле": "plan_value",
                    "Тип": "numeric",
                    "Назначение": "Плановая стоимость объёма = planned_qty × unit_price.",
                },
                {
                    "Поле": "status",
                    "Тип": "text",
                    "Назначение": "NOT_SENT или SENT_TO_ADMISSION. Check constraint в SQL.",
                },
                {
                    "Поле": "sent_to_constraints_at",
                    "Тип": "timestamptz",
                    "Назначение": "Момент отправки в контур допуска (UTC). NULL до send.",
                },
                {
                    "Поле": "created_at",
                    "Тип": "timestamptz",
                    "Назначение": "Время создания строки. Используется для сортировки и UI «Дата/время».",
                },
                {
                    "Поле": "updated_at",
                    "Тип": "timestamptz",
                    "Назначение": "Автообновление trigger при любом update.",
                },
            ]
        )
        st.dataframe(fields_df, use_container_width=True, hide_index=True, height=480)

        st.markdown("#### Поля session-only (не в monthly_plan_lines_v2)")
        session_only_df = pd.DataFrame(
            [
                {"Поле session": "system", "UI колонка": "Система", "Поведение": "Заполняется при add из detail panel; после DB reload — пусто"},
                {"Поле session": "iwp", "UI колонка": "IWP", "Поведение": "Аналогично system — session overlay"},
                {"Поле session": "is_pending", "UI колонка": "—", "Поведение": "True = несохранённая строка; влияет на reservation и save"},
                {"Поле session": "line_uid", "UI колонка": "—", "Поведение": "Временный id до появления plan_line_id"},
                {"Поле session": "read_only", "UI колонка": "—", "Поведение": "True для SENT_TO_ADMISSION — блокирует edit/delete"},
                {"Поле session": "construction_queue", "UI колонка": "Очередь", "Поведение": "Derived из facility или scope row"},
            ]
        )
        st.dataframe(session_only_df, use_container_width=True, hide_index=True)

        st.markdown(
            """
**Индексы (SQL)**

- `(project_code, month_key)` — основной list query
- `(status)` — фильтрация по статусу
- `(boq_code)` — поиск по коду
- `(project_code, month_key, boq_code)` — hint-index (не unique: BOQ может повторяться)
            """
        )


def section_05_remaining() -> None:
    with st.expander("5. Расчёт остатка BOQ", expanded=False):
        st.markdown(
            """
**Source of truth: `monthly_scope_picker_view`**

v2 **не пересчитывает** production-остаток вручную. View агрегирует BOQ total, manual adjustments
и Daily Progress fact.

**Формула остатка (концептуально)**

<div class="v2-doc-pipeline">BOQ total (total_project_qty)
− manual adjustments (manual_executed_before_system / manual_verified_remaining)
− Daily Progress fact (executed_qty_all_time через view)
= planning_remaining_qty</div>

**Логика в view (упрощённо)**

```
Если manual_verified_remaining_qty задан:
    remaining = manual_verified_remaining_qty
Иначе:
    remaining = total_project_qty − executed_qty_all_time − manual_executed_before_system
```

**Ключевая философия v2 (критично для июля и следующих месяцев)**

<span class="v2-doc-badge warn">важно</span>

`monthly_plan_lines_v2` **НЕ уменьшает** `planning_remaining_qty` как факт выполнения.

| Что | Влияет на остаток BOQ? |
| --- | --- |
| Daily Progress fact | **Да** — через view |
| Manual adjustment | **Да** — через view |
| Сохранённый месячный план (DB) | **Нет** |
| Отправленный в допуск план | **Нет** |
| Несохранённое добавление (is_pending) | **Да, временно** — только session reservation |

**Почему сохранённый план ≠ факт выполнения**

Месячный план — это **намерение** (plan), а не **факт** (execution).
Если бы save уменьшал остаток как DP-fact:
- в июле остатки «съелись бы» планом июня, хотя работы ещё не выполнены;
- перенос плана между месяцами сломал бы continuity;
- BOQ scope перестал бы отражать реальную доступность к планированию.

**Session reservation (локальный overlay)**

```
available_to_add_qty = planning_remaining_qty − session_planned_qty(is_pending only)
```

`build_v2_session_planned_qty_map()` суммирует **только** строки с `is_pending=True`.
Сохранённые и отправленные строки **не** участвуют в reservation.

**Статусы BOQ scope (UI)**

| Статус | Условие |
| --- | --- |
| Доступно | remaining > 0, session reservation = 0 |
| Частично запланировано | session reservation > 0, available > 0 |
| Запланировано полностью | available ≤ 0, reservation > 0 |
| Перепланировано | available < 0 |
| Выполнено | remaining ≤ 0 |
            """,
            unsafe_allow_html=True,
        )


def section_06_session() -> None:
    with st.expander("6. Session architecture", expanded=False):
        session_df = pd.DataFrame(
            [
                {
                    "Ключ": "v2_month_plan_items",
                    "Константа": "V2_PLAN_ITEMS_KEY",
                    "Тип": "list[dict]",
                    "Назначение": "Все строки месячных планов в session (все scope). Единый массив items.",
                },
                {
                    "Ключ": "v2_month_plan_scope",
                    "Константа": "V2_PLAN_SCOPE_KEY",
                    "Тип": "str",
                    "Назначение": "Текущий hydrated scope: PROJECT|month_key. Предотвращает повторный load.",
                },
                {
                    "Ключ": "v2_month_plan_dirty",
                    "Константа": "V2_PLAN_DIRTY_KEY",
                    "Тип": "bool",
                    "Назначение": "True если есть несохранённые pending строки в текущем scope.",
                },
                {
                    "Ключ": "v2_plan_selected_row_keys",
                    "Константа": "V2_PLAN_SELECTED_KEYS",
                    "Тип": "list[str]",
                    "Назначение": "Ключи выделенных строк таблицы (multi-row selection).",
                },
                {
                    "Ключ": "v2_plan_edit_row_key",
                    "Константа": "V2_PLAN_EDIT_ROW_KEY",
                    "Тип": "str",
                    "Назначение": "Ключ строки в режиме edit panel (ровно одна NOT_SENT).",
                },
                {
                    "Ключ": "v2_scope_project / v2_scope_planning_month",
                    "Константа": "—",
                    "Тип": "str",
                    "Назначение": "Фильтры Модуля 1; определяют scope для hydrate.",
                },
            ]
        )
        st.dataframe(session_df, use_container_width=True, hide_index=True)

        st.markdown(
            """
**Session item — ключевые флаги**

| Флаг | Значение |
| --- | --- |
| `is_pending=True` | Строка ещё не в DB или изменена после load → требует save |
| `plan_line_id` | UUID после save; обязателен для send |
| `read_only=True` | SENT_TO_ADMISSION — edit/delete заблокированы |
| `status` | NOT_SENT или SENT_TO_ADMISSION (зеркало DB) |

**Миграция legacy ключа**

`v2_month_plan_draft_items` → автоматически переносится в `v2_month_plan_items` при init.

**Row key (`_v2_plan_row_key`)**

Стабильный идентификатор строки в UI selection:
`plan_line_id` если есть, иначе `line_uid` для pending.
            """
        )


def section_07_save_hydrate() -> None:
    with st.expander("7. Save / hydrate lifecycle", expanded=False):
        st.markdown(
            """
**Auto-load model**

При каждом rerun, если выбран конкретный project (не «Все») и month_key:

```
main() → hydrate_v2_month_plan_if_needed(project, month)
```

Hydrate **не выполняется повторно** для того же scope_key, если не `force=True`.

**scope_key**

```
scope_key = f"{project_code.upper()}|{month_key.lower()}"
```

**Алгоритм hydrate (упрощённо)**

```
1. Если scope_key не изменился и не force → return
2. При смене scope → сброс V2_PLAN_SELECTED_KEYS, V2_PLAN_EDIT_ROW_KEY
3. kept = items других scope (не текущий project/month)
4. pending_new = is_pending без plan_line_id в текущем scope
5. loaded = load_v2_month_plan_lines(project, month) из Supabase
6. session items = kept + loaded + pending_new
7. V2_PLAN_DIRTY_KEY = bool(pending_new)
```

**Save flow**

```
Пользователь → «Сохранить план»
→ save_v2_month_plan()
   → validate pending / NOT_SENT items
   → insert (новые) или update (plan_line_id + NOT_SENT)
   → hydrate(force=True) — перезагрузка из DB
→ success message → st.rerun()
```

**Save → refresh → restart → auto-load**

| Событие | Поведение |
| --- | --- |
| Save в той же сессии | hydrate(force=True), pending сбрасывается |
| Browser refresh (F5) | session items теряются → hydrate загружает из DB |
| Streamlit restart | то же — DB = source of persisted truth |
| Возврат через неделю | выбор project+month → hydrate → все строки месяца |

**Send flow (фаза 1.2)**

```
send_v2_plan_lines_to_admission()
→ для выбранных NOT_SENT с plan_line_id:
   status → SENT_TO_ADMISSION, sent_to_constraints_at → now()
→ без записи в monthly_plan_review_queue (roadmap)
→ hydrate(force=True)
```

**Clear pending**

`clear_v2_pending_plan_lines_for_scope()` удаляет только `is_pending` строки текущего scope из session.
            """
        )

        lifecycle_df = pd.DataFrame(
            [
                {"Событие": "Add BOQ", "is_pending": True, "plan_line_id": "null", "DB": "—"},
                {"Событие": "Save", "is_pending": False, "plan_line_id": "uuid", "DB": "insert/update"},
                {"Событие": "Edit NOT_SENT", "is_pending": True, "plan_line_id": "uuid", "DB": "update on save"},
                {"Событие": "Send", "is_pending": False, "plan_line_id": "uuid", "DB": "status update"},
                {"Событие": "Delete NOT_SENT", "is_pending": "—", "plan_line_id": "—", "DB": "delete row"},
                {"Событие": "Delete SENT", "is_pending": "—", "plan_line_id": "uuid", "DB": "blocked"},
            ]
        )
        st.dataframe(lifecycle_df, use_container_width=True, hide_index=True)


def section_08_statuses() -> None:
    with st.expander("8. Статусы строк и lifecycle", expanded=False):
        plan_status_df = pd.DataFrame(
            [
                {
                    "DB status": "NOT_SENT",
                    "UI label": "В допуск не отправлен",
                    "Описание": "Строка в monthly_plan_lines_v2 или pending в session. Доступны edit/delete/send (после save).",
                    "read_only": False,
                },
                {
                    "DB status": "SENT_TO_ADMISSION",
                    "UI label": "Отправлен в допуск",
                    "Описание": "Status update в DB. Edit/delete недоступны. Review queue — roadmap.",
                    "read_only": True,
                },
            ]
        )
        st.markdown("**Статусы строк месячного плана (v2)**")
        st.dataframe(plan_status_df, use_container_width=True, hide_index=True)

        st.markdown(
            """
**Lifecycle строки плана**

<div class="v2-doc-pipeline">[Add BOQ] → pending (session)
↓ save
NOT_SENT (monthly_plan_lines_v2)
↓ send to admission
SENT_TO_ADMISSION (read-only)
↓ (roadmap) review_queue → constraints → passport</div>

**Правила переходов**

- `NOT_SENT → SENT_TO_ADMISSION`: только через send, только с `plan_line_id`
- `SENT_TO_ADMISSION → NOT_SENT`: **не поддерживается** в v2 (rollback — roadmap)
- Pending без save: send **блокируется** с ошибкой «Сначала сохраните»

**Статусы BOQ scope (отдельно от статусов плана)**

Статусы в таблице остатков (Доступно / Частично запланировано / …) описывают **BOQ availability**,
не статус строки месячного плана.
            """,
            unsafe_allow_html=True,
        )


def section_09_ui_logic() -> None:
    with st.expander("9. UI logic — command center", expanded=False):
        st.markdown(
            """
**Расположение**

Action bar встроен в модуль «Единый месячный план» (`render_v2_plan_action_bar`).
Отдельный expander «Действия» — legacy stub.

**Layout панели**

```
[metric cards: Выбрано | К допуску] | [vertical button stack]
```

**Metric cards**

| Карточка | Источник | Смысл |
| --- | --- | --- |
| Выбрано | `_v2_plan_selection_stats["selected"]` | Число выделенных строк в таблице |
| К допуску | `_v2_plan_selection_stats["sent_to_admission"]` | Все строки scope со статусом SENT_TO_ADMISSION (не selected!) |

**Кнопки и disabled states**

| Кнопка | enabled когда | handler |
| --- | --- | --- |
| В ДОПУСК | `sendable > 0` | `send_v2_plan_lines_to_admission` |
| Сохранить план | `has_pending` | `save_v2_month_plan` |
| Изменить строку | `editable == 1` | открывает `render_v2_plan_edit_panel` |
| Удалить строки | `deletable > 0` | `delete_v2_plan_lines` |
| Очистить несохранённые | `has_pending` | `clear_v2_pending_plan_lines_for_scope` |

**sendable / editable / deletable (для выбранных строк)**

```
selected → строки в selected_keys
NOT_SENT only → editable, deletable
NOT_SENT + plan_line_id → sendable (+1)
SENT_TO_ADMISSION → skipped для edit/delete/send
```

**Почему edit/delete недоступны после admission**

`status == SENT_TO_ADMISSION` → `read_only=True`.
Строка зафиксирована в контуре допуска (фаза 1.2 — только status в DB).
Изменение потребовало бы rollback flow и audit trail (roadmap).

**Multi-select**

`st.dataframe(selection_mode="multi-row")` → `V2_PLAN_SELECTED_KEYS`.
Edit требует **ровно одну** выбранную NOT_SENT строку.
            """
        )

        keys_df = pd.DataFrame(
            [
                {"Кнопка": "В ДОПУСК", "key": "v2_plan_send_main"},
                {"Кнопка": "Сохранить план", "key": "v2_plan_save_main"},
                {"Кнопка": "Изменить строку", "key": "v2_plan_edit_main"},
                {"Кнопка": "Удалить строки", "key": "v2_plan_delete_main"},
                {"Кнопка": "Очистить несохранённые", "key": "v2_plan_clear_main"},
            ]
        )
        st.dataframe(keys_df, use_container_width=True, hide_index=True)


def section_10_capabilities() -> None:
    with st.expander("10. Current capabilities (что работает)", expanded=False):
        caps_df = pd.DataFrame(
            [
                {"Возможность": "Загрузка BOQ scope из view", "Статус": "✅", "Детали": "load_v2_boq_scope_from_supabase"},
                {"Возможность": "Фильтры и KPI среза", "Статус": "✅", "Детали": "render_module_boq_scope"},
                {"Возможность": "Manual adjustment остатка", "Статус": "✅", "Детали": "write в monthly_scope_manual_adjustments"},
                {"Возможность": "Add BOQ в месячный план", "Статус": "✅", "Детали": "session pending + reservation"},
                {"Возможность": "Auto-load плана по project/month", "Статус": "✅", "Детали": "hydrate_v2_month_plan_if_needed"},
                {"Возможность": "Save плана в Supabase", "Статус": "✅", "Детали": "monthly_plan_lines_v2 insert/update"},
                {"Возможность": "Edit NOT_SENT строки", "Статус": "✅", "Детали": "single-row edit panel"},
                {"Возможность": "Delete NOT_SENT строки", "Статус": "✅", "Детали": "DB delete + session remove"},
                {"Возможность": "Multi-select в таблице плана", "Статус": "✅", "Детали": "multi-row selection"},
                {"Возможность": "Send to admission", "Статус": "✅", "Детали": "status update only, без review_queue"},
                {"Возможность": "Reload после restart", "Статус": "✅", "Детали": "hydrate из DB"},
                {"Возможность": "Продолжение плана через неделю", "Статус": "✅", "Детали": "month continuity через auto-load"},
                {"Возможность": "Частичное продолжение месяца", "Статус": "✅", "Детали": "добавление новых строк к существующим"},
                {"Возможность": "review_queue integration", "Статус": "⏳", "Детали": "roadmap"},
                {"Возможность": "Constraints auto-generation", "Статус": "⏳", "Детали": "roadmap"},
                {"Возможность": "Паспорт месяца", "Статус": "⏳", "Детали": "roadmap"},
            ]
        )
        st.dataframe(caps_df, use_container_width=True, hide_index=True)

        st.markdown("#### Расчёты плановой строки (формулы)")
        st.markdown(
            """
```
plan_value = planned_qty × unit_price
norm_hours_per_unit ← P50 / P80 / manual
required_hours = planned_qty × norm_hours_per_unit
crew_day_capacity_hours = crew_size × 8
duration_shifts = required_hours / crew_day_capacity_hours
labor_cost = required_hours × 3000
```

`labor_cost` **не умножается** повторно на `crew_size`.
            """
        )


def section_11_limitations() -> None:
    with st.expander("11. Ограничения и что не подключено", expanded=False):
        limits_df = pd.DataFrame(
            [
                {"Ограничение": "Send не пишет в monthly_plan_review_queue", "Причина": "Фаза 1.2 — только status в plan lines"},
                {"Ограничение": "system / iwp не persist в DB", "Причина": "Колонки отсутствуют в monthly_plan_lines_v2"},
                {"Ограничение": "Rollback SENT → NOT_SENT", "Причина": "Не реализован — нужен audit flow"},
                {"Ограничение": "Saved plan не резервирует BOQ остаток", "Причина": "By design — план ≠ факт"},
                {"Ограничение": "draft/header UX v1 в 10B", "Причина": "Код legacy остался, UI недоступен"},
                {"Ограничение": "Загрузка Excel/Word", "Причина": "Модуль 0 — UI-заглушка"},
                {"Ограничение": "War Room / Passport integration", "Причина": "Roadmap"},
                {"Ограничение": "SUPABASE_SECRET_KEY required для save/send", "Причина": "Write client через service role"},
            ]
        )
        st.dataframe(limits_df, use_container_width=True, hide_index=True)

        not_connected = [
            "monthly_plan_review_queue write from v2 send",
            "monthly_plan_constraints auto-create",
            "previously sent lines from v1 drafts",
            "passport month aggregation",
            "acceptance / cash logic",
            "DB-level planned qty reservation",
        ]
        st.markdown("**Не подключено (explicit list)**")
        for item in not_connected:
            st.markdown(f"- {item}")


def section_12_roadmap() -> None:
    with st.expander("12. Roadmap v2", expanded=False):
        roadmap_df = pd.DataFrame(
            [
                {
                    "Этап": 1,
                    "Контур": "Monthly constructor v2",
                    "Задача": "Стабилизация UI, action bar, edit/delete/send, month continuity",
                    "Статус": "в работе",
                },
                {
                    "Этап": 2,
                    "Контур": "Admission v2",
                    "Задача": "Связать SENT_TO_ADMISSION с monthly_plan_review_queue",
                    "Статус": "planned",
                },
                {
                    "Этап": 3,
                    "Контур": "Constraints",
                    "Задача": "Автогенерация ограничений допуска из отправленных строк",
                    "Статус": "planned",
                },
                {
                    "Этап": 4,
                    "Контур": "Passport month",
                    "Задача": "Чистый паспорт месяца из утверждённого плана",
                    "Статус": "planned",
                },
                {
                    "Этап": 5,
                    "Контур": "Acceptance / Cash",
                    "Задача": "Логика приёмки и cash-flow после паспорта",
                    "Статус": "planned",
                },
                {
                    "Этап": 6,
                    "Контур": "v1 sunset",
                    "Задача": "Архивировать 10_Planning как legacy fallback",
                    "Статус": "planned",
                },
            ]
        )
        st.dataframe(roadmap_df, use_container_width=True, hide_index=True)


def section_13_functions() -> None:
    with st.expander("13. Ключевые функции и эксплуатационные заметки", expanded=False):
        funcs_df = pd.DataFrame(
            [
                {"Функция": "load_v2_boq_scope_from_supabase", "Модуль": "1", "Назначение": "Загрузка BOQ scope из view"},
                {"Функция": "apply_v2_session_draft_reservation", "Модуль": "1", "Назначение": "Session reservation (is_pending only)"},
                {"Функция": "save_v2_manual_adjustment", "Модуль": "1", "Назначение": "Write корректировки остатка"},
                {"Функция": "append_v2_month_plan_draft_item", "Модуль": "1→3", "Назначение": "Add BOQ в session plan"},
                {"Функция": "load_v2_month_plan_lines", "Модуль": "3", "Назначение": "Read из monthly_plan_lines_v2"},
                {"Функция": "hydrate_v2_month_plan_if_needed", "Модуль": "3", "Назначение": "Auto-load / merge session + DB"},
                {"Функция": "save_v2_month_plan", "Модуль": "3", "Назначение": "Upsert pending → DB"},
                {"Функция": "apply_v2_plan_line_edit", "Модуль": "3", "Назначение": "Пересчёт editable полей"},
                {"Функция": "send_v2_plan_lines_to_admission", "Модуль": "3", "Назначение": "Status → SENT_TO_ADMISSION"},
                {"Функция": "delete_v2_plan_lines", "Модуль": "3", "Назначение": "Delete NOT_SENT"},
                {"Функция": "clear_v2_pending_plan_lines_for_scope", "Модуль": "3", "Назначение": "Clear pending only"},
                {"Функция": "render_v2_plan_action_bar", "Модуль": "3", "Назначение": "Command center UI"},
                {"Функция": "map_v2_plan_db_row_to_session_item", "Модуль": "3", "Назначение": "DB row → session item"},
                {"Функция": "map_v2_session_item_to_plan_db_row", "Модуль": "3", "Назначение": "Session item → DB payload"},
            ]
        )
        st.dataframe(funcs_df, use_container_width=True, hide_index=True, height=420)

        st.markdown(
            """
**Эксплуатационные заметки**

- **Selected BOQ** после refresh может сбрасываться — session-only selection в Модуле 1.
- **Несохранённые pending** теряются при clear или смене scope без save.
- **Сохранённые строки** переживают restart — загружаются hydrate из DB.
- **`added_at`** в session: UTC ISO; в UI «Дата/время» — Europe/Moscow.
- **`SUPABASE_SECRET_KEY`** в `.env` обязателен для save/send/delete DB rows.
- **v1** (`10_Planning_…`) — production fallback, не модифицировать при работе над v2.
- **Документация** — модуль 4 в `10B` (expander «Техническая архитектура v2»); исходник: `docs/v2_technical_architecture_handbook.py`.
            """
        )
        st.caption(f"Файл реализации: `{PRODUCTION_PAGE}`")


def render_v2_technical_architecture_handbook(*, embedded: bool = True) -> None:
    """Полный enterprise handbook — 13 expander-секций."""
    inject_doc_styles()
    if embedded:
        st.markdown(
            '<p class="constructor-v2-module-hint">'
            "Полный технический паспорт конструктора v2: данные, session, lifecycle, "
            "остатки BOQ, UI logic, roadmap. Read-only — без влияния на runtime."
            "</p>",
            unsafe_allow_html=True,
        )
    else:
        render_header()
    section_01_purpose()
    section_02_pipeline()
    section_03_supabase()
    section_04_monthly_plan_lines_v2()
    section_05_remaining()
    section_06_session()
    section_07_save_hydrate()
    section_08_statuses()
    section_09_ui_logic()
    section_10_capabilities()
    section_11_limitations()
    section_12_roadmap()
    section_13_functions()
