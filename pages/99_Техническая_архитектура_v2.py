# ============================================================
# Техническая архитектура v2 — read-only паспорт реализации
# Production: pages/10B_Конструктор_месячного_плана_v2.py
# Без Supabase, без расчётов, без save/send
# ============================================================

from __future__ import annotations

import pandas as pd
import streamlit as st

PAGE_TITLE = "Техническая архитектура v2"
PAGE_SUBTITLE = (
    "Паспорт логики, данных, расчётов и потоков работы конструктора месячного плана."
)


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
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown(f'<h1 class="v2-doc-header">{PAGE_TITLE}</h1>', unsafe_allow_html=True)
    st.markdown(f'<p class="v2-doc-subtitle">{PAGE_SUBTITLE}</p>', unsafe_allow_html=True)


def section_01_purpose() -> None:
    with st.expander("1. Назначение конструктора месячного плана v2", expanded=False):
        st.markdown(
            """
**Зачем нужен v2**

Конструктор месячного плана v2 — модульная sandbox-версия инструмента планирования работ по BOQ.
Цель: отделить UI/UX и session-first поток от production v1, не ломая текущий контур допуска.

**Отличие от v1**

| Аспект | v1 | v2 |
| --- | --- | --- |
| Архитектура | монолитная страница | модульные expander-блоки |
| Черновик плана | Supabase drafts | session-only (`v2_month_plan_draft_items`) |
| Save / Send | подключено | **не подключено** |
| Корректировка остатка | production write | **write включён** (manual adjustments) |
| UI | legacy | enterprise redesign |

**Production-логика**

Страница `10_Planning_Конструктор_месячного_плана.py` (v1) продолжает работать параллельно.
v2 строится как поэтапная замена, а не hot-swap.

**Модульная архитектура**

Каждый блок страницы 10B — отдельный модуль с собственной ответственностью:
загрузка → scope → detail → корректировка → добавление в session plan → просмотр плана.

**Основной принцип потока**

```
read → select → adjust residual → add to session plan → review monthly plan → later save/send
```

На текущем этапе реализованы шаги до **review monthly plan** включительно (session-only).
Save/send — в roadmap.
            """
        )


def section_02_modules() -> None:
    with st.expander("2. Модули конструктора", expanded=False):
        modules_df = pd.DataFrame(
            [
                {
                    "Модуль": "0 — Загрузка исходных данных",
                    "Назначение": "Архитектурная заглушка для будущей загрузки Excel/Word",
                    "Статус": "Частично реализовано (UI-заглушка)",
                    "Supabase": "Не подключено",
                },
                {
                    "Модуль": "1 — Остатки и доступность к планированию",
                    "Назначение": "Фильтры, KPI, таблица BOQ, detail panel, корректировка остатка",
                    "Статус": "Реализовано",
                    "Supabase": "Read scope view + write manual adjustments",
                },
                {
                    "Модуль": "2 — Добавление BOQ (detail panel)",
                    "Назначение": "Expander «Добавить код / объём работ» внутри выбранного BOQ",
                    "Статус": "Реализовано (session-only)",
                    "Supabase": "Не пишется",
                },
                {
                    "Модуль": "3 — Единый месячный план",
                    "Назначение": "Read-only таблица session draft + KPI",
                    "Статус": "Реализовано (session-only)",
                    "Supabase": "Не пишется",
                },
                {
                    "Модуль": "4 — Действия с месячным планом",
                    "Назначение": "Save, Send, Edit, Delete — заглушки",
                    "Статус": "Не подключено",
                    "Supabase": "Не пишется",
                },
            ]
        )
        st.dataframe(modules_df, use_container_width=True, hide_index=True)
        st.markdown(
            """
<span class="v2-doc-badge ok">реализовано</span>
<span class="v2-doc-badge partial">частично реализовано</span>
<span class="v2-doc-badge session">session-only</span>
<span class="v2-doc-badge off">не подключено к Supabase</span>

**Production write в v2 включён только для:** `monthly_scope_manual_adjustments` (корректировка остатка).
            """,
            unsafe_allow_html=True,
        )


def section_03_supabase() -> None:
    with st.expander("3. Таблицы и view Supabase", expanded=False):
        supabase_df = pd.DataFrame(
            [
                {
                    "Объект": "monthly_scope_picker_view",
                    "Тип": "view",
                    "Назначение": "Главный источник BOQ scope: total, executed, planning_remaining, нормы",
                    "Используется в v2": "да",
                    "Write?": "read-only",
                },
                {
                    "Объект": "monthly_scope_manual_adjustments",
                    "Тип": "table",
                    "Назначение": "Ручные корректировки ранее выполненного объёма",
                    "Используется в v2": "да",
                    "Write?": "write: correction save/delete",
                },
                {
                    "Объект": "monthly_labor_summary",
                    "Тип": "table",
                    "Назначение": "Источник звеньев / crew_code",
                    "Используется в v2": "да",
                    "Write?": "read-only",
                },
                {
                    "Объект": "monthly_plan_drafts",
                    "Тип": "table",
                    "Назначение": "Заголовки черновиков планов",
                    "Используется в v2": "пока нет",
                    "Write?": "не пишется",
                },
                {
                    "Объект": "monthly_plan_draft_lines",
                    "Тип": "table",
                    "Назначение": "Строки месячного плана",
                    "Используется в v2": "пока нет",
                    "Write?": "не пишется",
                },
                {
                    "Объект": "monthly_plan_review_queue",
                    "Тип": "table",
                    "Назначение": "Очередь допуска",
                    "Используется в v2": "пока нет",
                    "Write?": "не пишется",
                },
                {
                    "Объект": "monthly_plan_constraints",
                    "Тип": "table",
                    "Назначение": "Ограничения допуска",
                    "Используется в v2": "пока нет",
                    "Write?": "не пишется",
                },
                {
                    "Объект": "daily_progress_active",
                    "Тип": "table",
                    "Назначение": "Факт выполнения (через view)",
                    "Используется в v2": "косвенно",
                    "Write?": "read-only",
                },
                {
                    "Объект": "boq_master_api",
                    "Тип": "table/view",
                    "Назначение": "Исходный BOQ через view",
                    "Используется в v2": "косвенно",
                    "Write?": "read-only",
                },
            ]
        )
        st.dataframe(supabase_df, use_container_width=True, hide_index=True)


def section_04_pipeline() -> None:
    with st.expander("4. Pipeline данных", expanded=False):
        st.markdown(
            """
<div class="v2-doc-pipeline">monthly_scope_picker_view
↓
normalize_v2_scope_df()
↓
calculate_v2_basic_scope_metrics()
↓
apply_v2_session_draft_reservation()
↓
apply_scope_filters()
↓
render_scope_kpi_cards()
↓
render_scope_table()
↓
render_selected_boq_card()</div>
            """,
            unsafe_allow_html=True,
        )
        steps_df = pd.DataFrame(
            [
                {"Шаг": "monthly_scope_picker_view", "Описание": "Read-only загрузка BOQ scope из Supabase view"},
                {"Шаг": "normalize_v2_scope_df()", "Описание": "Нормализация колонок, типов, ключей BOQ"},
                {"Шаг": "calculate_v2_basic_scope_metrics()", "Описание": "Расчёт remaining, available, status, стоимостей"},
                {"Шаг": "apply_v2_session_draft_reservation()", "Описание": "Уменьшение available по session draft текущего месяца"},
                {"Шаг": "apply_scope_filters()", "Описание": "Фильтрация среза по UI-фильтрам и поискам"},
                {"Шаг": "render_scope_kpi_cards()", "Описание": "KPI-карточки агрегатов среза"},
                {"Шаг": "render_scope_table()", "Описание": "Рабочий список BOQ с выбором строки"},
                {"Шаг": "render_selected_boq_card()", "Описание": "Detail panel: метрики, корректировка, добавление в план"},
            ]
        )
        st.dataframe(steps_df, use_container_width=True, hide_index=True)


def section_05_remaining() -> None:
    with st.expander("5. Расчёт остатка BOQ", expanded=False):
        st.markdown(
            """
**Источник production-остатка (view)**

- `planning_remaining_qty`
- `planning_remaining_value`
- `remaining_qty_source`

**Логика в view**

```
Если manual_verified_remaining_qty задан:
    remaining = manual_verified_remaining_qty
Иначе:
    remaining = total_project_qty - executed_qty_all_time - manual_executed_before_system
```

**В v2**

`remaining_qty` берётся из `planning_remaining_qty`.

**Важно**

v2 **не пересчитывает** production-остаток вручную — view является **source of truth**.
Локально v2 только вычисляет `available_to_add_qty` с учётом session reservation.
            """
        )


def section_06_manual_adjustment() -> None:
    with st.expander("6. Ручная корректировка остатка", expanded=False):
        st.markdown(
            """
**Назначение**

Учесть объём, выполненный до запуска Daily Progress.

**UI**

Detail panel → expander **«Корректировка остатка»**

**Write в Supabase**

Таблица: `monthly_scope_manual_adjustments`

**Ключ записи**

- `project_code`
- `facility_building`
- `construction_discipline`
- `boq_code`

**Поля**

- `manual_executed_before_system`
- `manual_verified_remaining_qty = None`
- `reason`
- `comment`
- `updated_at`

**После save/delete**

1. Clear cache
2. Rerun
3. `monthly_scope_picker_view` подтягивает новые данные
4. `planning_remaining_qty` пересчитывается в view
            """
        )


def section_07_add_to_plan() -> None:
    with st.expander("7. Добавление BOQ в месячный план", expanded=False):
        st.markdown(
            """
**Текущий режим:** session-only

**Пишет только в:**

`st.session_state["v2_month_plan_draft_items"]`

**Не пишет в Supabase.**

**Поля draft_item**
            """
        )
        fields_df = pd.DataFrame(
            {
                "Поле": [
                    "line_uid",
                    "project_code",
                    "facility",
                    "discipline",
                    "system",
                    "iwp",
                    "boq_code",
                    "boq_name",
                    "unit",
                    "month_key",
                    "crew_code",
                    "crew_size",
                    "productive_hours_per_person_shift",
                    "crew_day_capacity_hours",
                    "planned_qty",
                    "unit_price",
                    "plan_value",
                    "norm_scenario",
                    "manual_norm_value",
                    "norm_hours_per_unit",
                    "required_hours",
                    "duration_shifts",
                    "labor_rate_per_hour",
                    "labor_cost",
                    "comment",
                    "added_at",
                    "line_source_ui",
                    "read_only",
                ]
            }
        )
        st.dataframe(fields_df, use_container_width=True, hide_index=True, height=320)


def section_08_calculations() -> None:
    with st.expander("8. Расчёты плановой строки", expanded=False):
        st.markdown(
            """
**Формулы**

```
plan_value = planned_qty × unit_price
```

**norm_hours_per_unit**

| Сценарий | Источник |
| --- | --- |
| Реалистичная норма | P50 |
| Осторожная норма | P80 |
| Ручная норма | manual input |

```
required_hours = planned_qty × norm_hours_per_unit
crew_day_capacity_hours = crew_size × 8
duration_shifts = required_hours / crew_day_capacity_hours
labor_cost = required_hours × 3000
```

**Важно:** `labor_cost` **не умножается** повторно на `crew_size`.
            """
        )


def section_09_reservation() -> None:
    with st.expander("9. Резервирование объёма в текущей сессии", expanded=False):
        st.markdown(
            """
После добавления строки в session draft:

**`build_v2_session_planned_qty_map()`** суммирует `planned_qty` по ключу:

- `project_code`
- `facility`
- `discipline`
- `boq_code`
- `month_key`

```
available_to_add_qty = remaining_qty - session_planned_qty
```

**Эффект в UI**

- Статус → «Частично запланировано»
- `available_to_add_qty` уменьшается
- В таблице появляются **Месяц планирования** и **Дата планирования** (МСК)
            """
        )


def section_10_monthly_plan() -> None:
    with st.expander("10. Единый месячный план", expanded=False):
        st.markdown(
            """
**Сейчас читает только:**

`st.session_state["v2_month_plan_draft_items"]`

**Показывает**

- Новые строки (статус «Новая строка»)
- KPI: строки, стоимость, трудозатраты, стоимость труда
- Таблицу 15 колонок через `map_v2_session_draft_to_display_df()`

**Пока не читает**

- Previously sent lines
- Saved drafts из Supabase
- Supabase plan lines
            """
        )


def section_11_statuses() -> None:
    with st.expander("11. Статусы строк и жизненный цикл", expanded=False):
        current_df = pd.DataFrame(
            [
                {"Статус": "Доступно", "Описание": "Есть остаток, session reservation = 0"},
                {"Статус": "Частично запланировано", "Описание": "Часть остатка зарезервирована в session draft"},
                {"Статус": "Выполнено", "Описание": "Остаток = 0 или полностью освоено"},
                {"Статус": "Перепланировано", "Описание": "Запланировано больше остатка — требует проверки"},
                {"Статус": "Требует проверки", "Описание": "Аномалия данных или корректировок"},
            ]
        )
        st.markdown("**Текущие статусы BOQ scope**")
        st.dataframe(current_df, use_container_width=True, hide_index=True)

        future_df = pd.DataFrame(
            [
                {"Lifecycle": "NEW_SESSION", "Описание": "Добавлено в session draft (реализовано)"},
                {"Lifecycle": "SAVED_DRAFT", "Описание": "Сохранено в Supabase draft (roadmap)"},
                {"Lifecycle": "SENT_TO_REVIEW", "Описание": "Отправлено в контур допуска (roadmap)"},
                {"Lifecycle": "APPROVED", "Описание": "Утверждено (roadmap)"},
                {"Lifecycle": "BLOCKED", "Описание": "Заблокировано ограничениями (roadmap)"},
            ]
        )
        st.markdown("**Будущие lifecycle статусы строк плана**")
        st.dataframe(future_df, use_container_width=True, hide_index=True)
        st.caption("Сейчас реализован только **NEW_SESSION** для добавления в месячный план.")


def section_12_not_connected() -> None:
    with st.expander("12. Что пока не подключено", expanded=False):
        not_connected = [
            "save monthly plan to Supabase",
            "send to review queue",
            "auto constraints generation",
            "previously sent lines",
            "editing saved lines",
            "deleting individual saved lines",
            "DB planned qty reservation",
            "passport integration",
            "War Room integration",
        ]
        for item in not_connected:
            st.markdown(f"- {item}")


def section_13_functions() -> None:
    with st.expander("13. Ключевые функции v2", expanded=False):
        funcs_df = pd.DataFrame(
            [
                {"Функция": "load_v2_boq_scope_from_supabase", "Назначение": "Загрузка BOQ scope из view"},
                {"Функция": "normalize_v2_scope_df", "Назначение": "Нормализация колонок и типов"},
                {"Функция": "calculate_v2_basic_scope_metrics", "Назначение": "Расчёт remaining, available, status"},
                {"Функция": "apply_v2_session_draft_reservation", "Назначение": "Session reservation по month_key"},
                {"Функция": "render_module_boq_scope", "Назначение": "Оркестрация Модуля 1"},
                {"Функция": "render_scope_filters", "Назначение": "UI фильтров среза"},
                {"Функция": "render_scope_kpi_cards", "Назначение": "KPI-карточки среза"},
                {"Функция": "render_scope_table", "Назначение": "Рабочий список BOQ"},
                {"Функция": "render_selected_boq_card", "Назначение": "Detail panel выбранного BOQ"},
                {"Функция": "save_v2_manual_adjustment", "Назначение": "Save корректировки остатка"},
                {"Функция": "delete_v2_manual_adjustment", "Назначение": "Delete корректировки остатка"},
                {"Функция": "load_v2_manual_adjustments_history", "Назначение": "История корректировок BOQ"},
                {"Функция": "append_v2_month_plan_draft_item", "Назначение": "Добавление строки в session draft"},
                {"Функция": "build_v2_session_planned_qty_map", "Назначение": "Карта зарезервированных объёмов"},
                {"Функция": "render_module_month_plan", "Назначение": "Модуль «Единый месячный план»"},
                {"Функция": "map_v2_session_draft_to_display_df", "Назначение": "Session draft → display DataFrame"},
                {"Функция": "format_v2_added_at_moscow", "Назначение": "UTC → Europe/Moscow для UI"},
            ]
        )
        st.dataframe(funcs_df, use_container_width=True, hide_index=True, height=420)
        st.caption("Файл реализации: `pages/10B_Конструктор_месячного_плана_v2.py`")


def section_14_ops() -> None:
    with st.expander("14. Эксплуатационные заметки", expanded=False):
        st.markdown(
            """
- **Selected BOQ** после refresh может сбрасываться — пока нормально (session-only selection).
- **Session draft** пропадает после restart Streamlit / browser reset — пока нормально.
- **`added_at`** хранится в UTC (ISO), отображается в **Europe/Moscow** (`DD.MM.YYYY HH:MM`).
- **`crew_size`** вводится вручную в UI (колонка может отсутствовать в `monthly_labor_summary`).
- **`crew_code`** читается из `monthly_labor_summary` (read-only).
- **v2** сейчас **sandbox / session-first**, кроме **manual adjustments** (единственный production write).
            """
        )


def section_15_roadmap() -> None:
    with st.expander("15. Roadmap перехода v1 → v2", expanded=False):
        roadmap_df = pd.DataFrame(
            [
                {"Этап": 1, "Задача": "Stabilize v2 UI + session flow", "Статус": "в работе"},
                {"Этап": 2, "Задача": "Add saved draft persistence", "Статус": "planned"},
                {"Этап": 3, "Задача": "Add previously sent lines read-only", "Статус": "planned"},
                {"Этап": 4, "Задача": "Add delete/edit only for NEW_SESSION / SAVED_DRAFT", "Статус": "planned"},
                {"Этап": 5, "Задача": "Add send to review queue", "Статус": "planned"},
                {"Этап": 6, "Задача": "Auto create constraints", "Статус": "planned"},
                {"Этап": 7, "Задача": "Replace v1 constructor", "Статус": "planned"},
                {"Этап": 8, "Задача": "Archive v1 as legacy fallback", "Статус": "planned"},
            ]
        )
        st.dataframe(roadmap_df, use_container_width=True, hide_index=True)


def main() -> None:
    inject_doc_styles()
    render_header()
    section_01_purpose()
    section_02_modules()
    section_03_supabase()
    section_04_pipeline()
    section_05_remaining()
    section_06_manual_adjustment()
    section_07_add_to_plan()
    section_08_calculations()
    section_09_reservation()
    section_10_monthly_plan()
    section_11_statuses()
    section_12_not_connected()
    section_13_functions()
    section_14_ops()
    section_15_roadmap()


st.set_page_config(
    page_title="Техническая архитектура v2",
    layout="wide",
    initial_sidebar_state="expanded",
)

main()
