-- =============================================================================
-- Monthly Plan Lines v2 — единый месячный план конструктора
-- =============================================================================
-- Таблица:  public.monthly_plan_lines_v2
-- Назначение: persistence для конструктора v2 (pages/10B_Конструктор_месячного_плана_v2.py).
--             Один project + один month = один план (много строк).
--             Без header/draft/saved-draft сущностей.
--
-- Deploy:   Supabase SQL Editor (выполнить один раз вручную)
-- v1:       monthly_plan_drafts / monthly_plan_draft_lines — не трогаем
-- =============================================================================

create table if not exists public.monthly_plan_lines_v2 (
    plan_line_id uuid primary key default gen_random_uuid(),

    project_code text not null,
    month_key text not null,

    facility text,
    discipline text,
    system text,
    iwp text,

    boq_code text not null,
    boq_name text,
    unit text,

    planned_qty numeric not null default 0
        check (planned_qty >= 0),

    crew text,
    crew_size integer
        check (crew_size is null or crew_size > 0),

    labor_hours numeric not null default 0
        check (labor_hours >= 0),
    labor_cost numeric not null default 0
        check (labor_cost >= 0),

    unit_price numeric,
    plan_value numeric,

    status text not null default 'NOT_SENT'
        check (status in ('NOT_SENT', 'SENT_TO_ADMISSION')),

    sent_to_constraints_at timestamptz,

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- Список плана по project+month (основной query конструктора)
create index if not exists idx_monthly_plan_lines_v2_project_month
    on public.monthly_plan_lines_v2 (project_code, month_key);

create index if not exists idx_monthly_plan_lines_v2_status
    on public.monthly_plan_lines_v2 (status);

create index if not exists idx_monthly_plan_lines_v2_boq_code
    on public.monthly_plan_lines_v2 (boq_code);

-- Hint-index для поиска по scope+boq (не unique — BOQ может повторяться в месяце)
create index if not exists idx_monthly_plan_lines_v2_scope_boq
    on public.monthly_plan_lines_v2 (project_code, month_key, boq_code);

comment on table public.monthly_plan_lines_v2 is
    'Единый месячный план v2: persistence для конструктора. Один project+month = один план (много строк).';

comment on column public.monthly_plan_lines_v2.plan_line_id is
    'Технический PK. Не business key — один BOQ может иметь несколько строк в месяце.';

comment on column public.monthly_plan_lines_v2.status is
    'NOT_SENT = Не отправлен; SENT_TO_ADMISSION = Отправлен в допуск. Статусы допуска — в review_queue/constraints.';

-- Миграция для уже развёрнутых БД (выполнить в Supabase SQL Editor)
alter table public.monthly_plan_lines_v2
    add column if not exists system text,
    add column if not exists iwp text;

-- Trigger updated_at
create or replace function public.monthly_plan_lines_v2_set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_monthly_plan_lines_v2_updated_at on public.monthly_plan_lines_v2;

create trigger trg_monthly_plan_lines_v2_updated_at
    before update on public.monthly_plan_lines_v2
    for each row execute function public.monthly_plan_lines_v2_set_updated_at();
