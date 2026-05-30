-- =============================================================================
-- Monthly Plan Passport v1 — утверждённый месячный план (Approved Monthly Plan)
-- =============================================================================
-- Таблицы:  public.monthly_plan_passports
--           public.monthly_plan_passport_lines
-- View:     public.monthly_plan_passport_dashboard_v1
--
-- Назначение: финальный результат месячного планирования после конструктора,
--             контура допуска, снятия ограничений и утверждения.
--
-- Поток: Draft → Review Queue → Constraints → War Room → Passport → Week → Day
--
-- Deploy:   Supabase SQL Editor (выполнить один раз вручную)
-- Страница: pages/10_Planning_Паспорт_месяца.py
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Шапка утверждённого месячного паспорта
-- -----------------------------------------------------------------------------

create table if not exists public.monthly_plan_passports (
    passport_id uuid primary key default gen_random_uuid(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    draft_id uuid,
    project_code text,
    month_key text,
    passport_status text not null default 'DRAFT',

    passport_name text,
    created_by text,
    approved_by text,
    approved_at timestamptz,

    total_plan_value numeric not null default 0,
    total_required_hours numeric not null default 0,
    total_labor_cost numeric not null default 0,
    rows_count integer not null default 0,

    admission_summary jsonb,
    comment text,

    constraint monthly_plan_passports_status_chk
        check (passport_status in (
            'DRAFT',
            'UNDER_REVIEW',
            'APPROVED',
            'SUPERSEDED',
            'CANCELLED'
        ))
);

create index if not exists idx_monthly_plan_passports_draft_id
    on public.monthly_plan_passports (draft_id);

create index if not exists idx_monthly_plan_passports_project_code
    on public.monthly_plan_passports (project_code);

create index if not exists idx_monthly_plan_passports_month_key
    on public.monthly_plan_passports (month_key);

create index if not exists idx_monthly_plan_passports_status
    on public.monthly_plan_passports (passport_status);

comment on table public.monthly_plan_passports is
    'Шапка утверждённого месячного плана (Approved Monthly Plan Passport) после контура допуска.';

comment on column public.monthly_plan_passports.passport_id is
    'Уникальный идентификатор паспорта месяца';
comment on column public.monthly_plan_passports.draft_id is
    'Ссылка на исходный черновик (monthly_plan_drafts)';
comment on column public.monthly_plan_passports.passport_status is
    'Статус: DRAFT, UNDER_REVIEW, APPROVED, SUPERSEDED, CANCELLED';
comment on column public.monthly_plan_passports.admission_summary is
    'Сводка по допуску: итоги проверок EXECUTABILITY / ACCEPTABILITY / CREW_ECONOMICS';

-- -----------------------------------------------------------------------------
-- Строки утверждённого месячного паспорта
-- -----------------------------------------------------------------------------

create table if not exists public.monthly_plan_passport_lines (
    passport_line_id uuid primary key default gen_random_uuid(),
    passport_id uuid not null references public.monthly_plan_passports (passport_id)
        on delete cascade,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    draft_id uuid,
    line_id uuid,
    review_id uuid,

    project_code text,
    month_key text,
    facility_building text,
    construction_discipline text,
    boq_code text,
    boq_name text,
    unit_of_measure text,

    crew_id text,
    planned_qty numeric,
    unit_price numeric,
    plan_value numeric,

    required_hours numeric,
    labor_rate_per_hour numeric,
    labor_cost numeric,

    admission_status text,
    constraints_total integer not null default 0,
    constraints_pass integer not null default 0,
    constraints_warning integer not null default 0,
    constraints_hold integer not null default 0,
    constraints_fail integer not null default 0,

    week_plan_status text not null default 'NOT_DECOMPOSED',
    comment text
);

create index if not exists idx_monthly_plan_passport_lines_passport_id
    on public.monthly_plan_passport_lines (passport_id);

create index if not exists idx_monthly_plan_passport_lines_draft_id
    on public.monthly_plan_passport_lines (draft_id);

create index if not exists idx_monthly_plan_passport_lines_line_id
    on public.monthly_plan_passport_lines (line_id);

create index if not exists idx_monthly_plan_passport_lines_review_id
    on public.monthly_plan_passport_lines (review_id);

create index if not exists idx_monthly_plan_passport_lines_project_code
    on public.monthly_plan_passport_lines (project_code);

create index if not exists idx_monthly_plan_passport_lines_month_key
    on public.monthly_plan_passport_lines (month_key);

create index if not exists idx_monthly_plan_passport_lines_boq_code
    on public.monthly_plan_passport_lines (boq_code);

create index if not exists idx_monthly_plan_passport_lines_crew_id
    on public.monthly_plan_passport_lines (crew_id);

comment on table public.monthly_plan_passport_lines is
    'Строки утверждённого месячного плана: BOQ, звенья, трудозатраты, статус допуска.';

comment on column public.monthly_plan_passport_lines.week_plan_status is
    'Статус декомпозиции в недели; по умолчанию NOT_DECOMPOSED';

-- -----------------------------------------------------------------------------
-- Dashboard v1: паспорт + строки
-- -----------------------------------------------------------------------------

create or replace view public.monthly_plan_passport_dashboard_v1 as
select
    p.passport_id,
    p.passport_status,
    p.project_code,
    p.month_key,
    p.passport_name,
    p.approved_by,
    p.approved_at,
    l.boq_code,
    l.boq_name,
    l.facility_building,
    l.construction_discipline,
    l.crew_id,
    l.planned_qty,
    l.plan_value,
    l.required_hours,
    l.labor_cost,
    l.admission_status,
    l.week_plan_status
from public.monthly_plan_passports p
inner join public.monthly_plan_passport_lines l
    on l.passport_id = p.passport_id;

comment on view public.monthly_plan_passport_dashboard_v1 is
    'Дашборд паспорта месяца v1: шапка утверждённого плана + строки BOQ/звенья/допуск.';
