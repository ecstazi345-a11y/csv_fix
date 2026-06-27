-- =============================================================================
-- Monthly Plan Lines v2 — labor metadata (Phase 0)
-- =============================================================================
-- Table:  public.monthly_plan_lines_v2
-- Purpose: persist norm provenance and labor rate at plan line grain.
--          Source of Truth for planned hours remains labor_hours (unchanged).
--
-- Deploy:  Supabase SQL Editor (after monthly_plan_lines_v2.sql)
-- Safe:    ADD COLUMN IF NOT EXISTS only — no drops, no renames.
-- UI:      not wired in Phase 0
-- =============================================================================

alter table public.monthly_plan_lines_v2
    add column if not exists norm_scenario text,
    add column if not exists norm_hours_per_unit numeric
        check (norm_hours_per_unit is null or norm_hours_per_unit >= 0),
    add column if not exists norm_source text,
    add column if not exists labor_rate_per_hour numeric
        check (labor_rate_per_hour is null or labor_rate_per_hour >= 0);

comment on column public.monthly_plan_lines_v2.norm_scenario is
    'UI scenario at save time: e.g. Реалистичная норма (P50), Осторожная норма (P80), Ручная норма.';

comment on column public.monthly_plan_lines_v2.norm_hours_per_unit is
    'Norm hours per unit frozen at planning time. Does not replace labor_hours SoT.';

comment on column public.monthly_plan_lines_v2.norm_source is
    'Norm provenance code: HISTORICAL_P50, HISTORICAL_P80, MANUAL, PROJECT_NORM, NO_NORM, LEGACY_DERIVED.';

comment on column public.monthly_plan_lines_v2.labor_rate_per_hour is
    'Labor rate (RUB/hour) used when labor_cost was calculated for this line.';

-- Optional gentle backfill for read-model only (does not change labor_hours).
update public.monthly_plan_lines_v2
set
    norm_hours_per_unit = (labor_hours / nullif(planned_qty, 0))::numeric,
    norm_source = coalesce(norm_source, 'LEGACY_DERIVED')
where norm_hours_per_unit is null
  and coalesce(planned_qty, 0) > 0
  and coalesce(labor_hours, 0) > 0;

update public.monthly_plan_lines_v2
set labor_rate_per_hour = (
    labor_cost / nullif(labor_hours, 0)
)::numeric
where labor_rate_per_hour is null
  and coalesce(labor_hours, 0) > 0
  and coalesce(labor_cost, 0) > 0;

create index if not exists idx_monthly_plan_lines_v2_norm_source
    on public.monthly_plan_lines_v2 (norm_source)
    where norm_source is not null;
