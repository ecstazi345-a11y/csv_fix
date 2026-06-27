-- =============================================================================
-- Planning Config v1 — month planning parameters (Phase 0)
-- =============================================================================
-- Table:  public.planning_config
-- Purpose: shared constants for FTE and future planning knobs.
--
-- Deploy:  Supabase SQL Editor (before monthly_plan_labor_engine_v1.sql)
-- Safe:    new table + seed row only
-- =============================================================================

create table if not exists public.planning_config (
    config_key text primary key,
    config_value numeric not null,
    config_unit text,
    description text,
    updated_at timestamptz not null default now()
);

comment on table public.planning_config is
    'Key-value config for monthly planning read-models (FTE fund, default rates).';

comment on column public.planning_config.config_key is
    'Stable key, e.g. hours_per_person_month.';

insert into public.planning_config (
    config_key,
    config_value,
    config_unit,
    description
)
values (
    'hours_per_person_month',
    176,
    'hours',
    'Default FTE fund: available working hours per person per month.'
)
on conflict (config_key) do nothing;

create or replace function public.planning_config_numeric(
    p_key text,
    p_default numeric default null
)
returns numeric
language sql
stable
as $$
    select coalesce(
        (
            select pc.config_value
            from public.planning_config pc
            where pc.config_key = p_key
            limit 1
        ),
        p_default
    );
$$;

comment on function public.planning_config_numeric(text, numeric) is
    'Read planning config with SQL default fallback (used by labor read-model views).';
