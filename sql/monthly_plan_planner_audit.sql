-- =============================================================================
-- Monthly plan planner audit — ФИО и момент планирования строки
-- =============================================================================
-- Deploy: Supabase SQL Editor (выполнить один раз вручную)
-- Используется: pages/10B_Конструктор_месячного_плана.py
-- =============================================================================

alter table public.monthly_plan_lines_v2
    add column if not exists planned_by text,
    add column if not exists planned_at timestamptz;

alter table public.monthly_plan_draft_lines
    add column if not exists planned_by text,
    add column if not exists planned_at timestamptz;

comment on column public.monthly_plan_lines_v2.planned_by is
    'ФИО планировщика на момент добавления строки в месячный план (v2 конструктор).';

comment on column public.monthly_plan_lines_v2.planned_at is
    'UTC timestamp добавления строки в план; в UI отображается как Europe/Moscow.';

comment on column public.monthly_plan_draft_lines.planned_by is
    'ФИО планировщика (legacy draft lines, опционально).';

comment on column public.monthly_plan_draft_lines.planned_at is
    'UTC timestamp планирования (legacy draft lines, опционально).';
