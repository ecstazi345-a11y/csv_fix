-- =============================================================================
-- Monthly Plan Labor Engine v1 — read-model views (Phase 0)
-- =============================================================================
-- Views:
--   monthly_plan_labor_lines_v1
--   monthly_plan_labor_summary_v1
--   monthly_plan_labor_admission_v1
--   monthly_plan_labor_admission_summary_v1
--   monthly_plan_capacity_v1
--   monthly_plan_passport_resource_v1
--
-- SoT planned hours: monthly_plan_lines_v2.labor_hours
-- NOT SoT: monthly_plan_constraints.required_hours
--
-- Deploy order:
--   1) monthly_plan_lines_v2_labor_meta.sql
--   2) planning_config_v1.sql
--   3) this file
--
-- Safe: CREATE OR REPLACE VIEW only (+ helper function)
-- UI:   not wired in Phase 0
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Helper: admission labor status from constraint checks (per plan line)
-- READY    = all checks PASS
-- WARNING  = has WARNING, no HOLD/FAIL, no pending ОЖИДАЕТ
-- BLOCKED  = any HOLD or FAIL
-- WAITING  = pending ОЖИДАЕТ (no blockers)
-- NO_CHECKS = no constraint rows for line
-- -----------------------------------------------------------------------------
create or replace function public.monthly_plan_admission_labor_status(
    p_pass_cnt integer,
    p_warning_cnt integer,
    p_blocked_cnt integer,
    p_waiting_cnt integer,
    p_check_total integer
)
returns text
language sql
immutable
as $$
    select case
        when coalesce(p_check_total, 0) = 0 then 'NO_CHECKS'
        when coalesce(p_blocked_cnt, 0) > 0 then 'BLOCKED'
        when coalesce(p_waiting_cnt, 0) > 0 then 'WAITING'
        when coalesce(p_warning_cnt, 0) > 0 then 'WARNING'
        when coalesce(p_pass_cnt, 0) = p_check_total then 'READY'
        else 'WAITING'
    end;
$$;

comment on function public.monthly_plan_admission_labor_status(integer, integer, integer, integer, integer) is
    'Admission labor bucket per line. Launch-eligible = READY + WARNING.';

-- -----------------------------------------------------------------------------
-- View 1: monthly_plan_labor_lines_v1
-- Grain: plan_line_id — enriched plan line for all planning stages
-- -----------------------------------------------------------------------------
create or replace view public.monthly_plan_labor_lines_v1 as
with cfg as (
    select public.planning_config_numeric('hours_per_person_month', 176)::numeric as hours_per_person_month
)
select
    l.plan_line_id,
    l.project_code,
    l.month_key,
    l.facility,
    l.discipline,
    l.system,
    l.iwp,
    l.boq_code,
    l.boq_name,
    l.unit,
    l.planned_qty,
    l.unit_price,
    l.plan_value,
    l.crew,
    l.crew_size,
    l.labor_hours,
    l.labor_cost,
    l.norm_scenario,
    l.norm_hours_per_unit,
    l.norm_source,
    l.labor_rate_per_hour,
    l.status,
    l.sent_to_constraints_at,
    l.created_at,
    l.updated_at,
    cfg.hours_per_person_month,
    case
        when coalesce(l.labor_hours, 0) > 0 and cfg.hours_per_person_month > 0
            then (l.labor_hours / cfg.hours_per_person_month)::numeric
        else 0::numeric
    end as fte_required,
    case
        when coalesce(l.planned_qty, 0) > 0
            then (l.labor_hours / nullif(l.planned_qty, 0))::numeric
        else null::numeric
    end as plan_intensity_hours_per_unit,
    coalesce(l.norm_hours_per_unit, (
        case
            when coalesce(l.planned_qty, 0) > 0
                then (l.labor_hours / nullif(l.planned_qty, 0))::numeric
            else null::numeric
        end
    )) as norm_hours_per_unit_effective,
    coalesce(
        l.norm_source,
        case
            when coalesce(l.planned_qty, 0) > 0 and coalesce(l.labor_hours, 0) > 0 then 'LEGACY_DERIVED'
            else 'NO_NORM'
        end
    ) as norm_source_effective
from public.monthly_plan_lines_v2 l
cross join cfg;

comment on view public.monthly_plan_labor_lines_v1 is
    'Plan line labor read-model. SoT hours = labor_hours. FTE uses planning_config hours_per_person_month (default 176).';

-- -----------------------------------------------------------------------------
-- View 2: monthly_plan_labor_summary_v1
-- Grain: project_code + month_key
-- -----------------------------------------------------------------------------
create or replace view public.monthly_plan_labor_summary_v1 as
select
    l.project_code,
    l.month_key,
    count(*)::bigint as plan_line_count,
    count(distinct l.boq_code)::bigint as boq_count,
    count(distinct nullif(trim(l.crew), ''))::bigint as crew_count,
    coalesce(sum(l.planned_qty), 0)::numeric as total_planned_qty,
    coalesce(sum(l.plan_value), 0)::numeric as total_plan_value,
    coalesce(sum(l.labor_hours), 0)::numeric as total_labor_hours,
    coalesce(sum(l.labor_cost), 0)::numeric as total_labor_cost,
    coalesce(sum(l.fte_required), 0)::numeric as total_fte_required,
    max(l.hours_per_person_month)::numeric as hours_per_person_month,
    count(*) filter (where l.norm_source_effective = 'HISTORICAL_P50')::bigint as lines_norm_p50,
    count(*) filter (where l.norm_source_effective = 'HISTORICAL_P80')::bigint as lines_norm_p80,
    count(*) filter (where l.norm_source_effective = 'MANUAL')::bigint as lines_norm_manual,
    count(*) filter (where l.norm_source_effective in ('NO_NORM', 'LEGACY_DERIVED') or l.norm_source_effective is null)::bigint as lines_norm_unknown,
    coalesce(sum(l.labor_hours) filter (where l.norm_source_effective = 'HISTORICAL_P50'), 0)::numeric as hours_norm_p50,
    coalesce(sum(l.labor_hours) filter (where l.norm_source_effective = 'HISTORICAL_P80'), 0)::numeric as hours_norm_p80,
    coalesce(sum(l.labor_hours) filter (where l.norm_source_effective = 'MANUAL'), 0)::numeric as hours_norm_manual,
    count(*) filter (where l.status = 'SENT_TO_ADMISSION')::bigint as lines_sent_to_admission,
    coalesce(sum(l.labor_hours) filter (where l.status = 'SENT_TO_ADMISSION'), 0)::numeric as hours_sent_to_admission
from public.monthly_plan_labor_lines_v1 l
group by
    l.project_code,
    l.month_key;

comment on view public.monthly_plan_labor_summary_v1 is
    'Monthly plan labor rollup by project+month. Used by Constructor and Economics read layers.';

-- -----------------------------------------------------------------------------
-- Constraint aggregation per plan line (admission scope)
-- -----------------------------------------------------------------------------
create or replace view public.monthly_plan_constraint_line_agg_v1 as
select
    c.line_id as plan_line_id,
    count(*)::integer as check_total,
    count(*) filter (where c.check_status = 'PASS')::integer as pass_cnt,
    count(*) filter (where c.check_status = 'WARNING')::integer as warning_cnt,
    count(*) filter (where c.check_status in ('HOLD', 'FAIL'))::integer as blocked_cnt,
    count(*) filter (where c.check_status = 'ОЖИДАЕТ')::integer as waiting_cnt
from public.monthly_plan_constraints c
where c.line_id is not null
group by
    c.line_id;

comment on view public.monthly_plan_constraint_line_agg_v1 is
    'Internal helper: constraint check counts per plan_line_id for admission labor views.';

-- -----------------------------------------------------------------------------
-- View 3: monthly_plan_labor_admission_v1
-- Grain: plan_line_id — SENT_TO_ADMISSION lines + admission labor status
-- Hours SoT: labor_hours from v2 (not constraints.required_hours)
-- Launch-eligible: READY + WARNING
-- -----------------------------------------------------------------------------
create or replace view public.monthly_plan_labor_admission_v1 as
select
    l.plan_line_id,
    l.project_code,
    l.month_key,
    l.facility,
    l.discipline,
    l.system,
    l.iwp,
    l.boq_code,
    l.boq_name,
    l.crew,
    l.planned_qty,
    l.plan_value,
    l.labor_hours,
    l.labor_cost,
    l.fte_required,
    l.hours_per_person_month,
    l.status as plan_line_status,
    l.sent_to_constraints_at,
    coalesce(a.check_total, 0) as check_total,
    coalesce(a.pass_cnt, 0) as pass_cnt,
    coalesce(a.warning_cnt, 0) as warning_cnt,
    coalesce(a.blocked_cnt, 0) as blocked_cnt,
    coalesce(a.waiting_cnt, 0) as waiting_cnt,
    public.monthly_plan_admission_labor_status(
        coalesce(a.pass_cnt, 0),
        coalesce(a.warning_cnt, 0),
        coalesce(a.blocked_cnt, 0),
        coalesce(a.waiting_cnt, 0),
        coalesce(a.check_total, 0)
    ) as admission_labor_status,
    public.monthly_plan_admission_labor_status(
        coalesce(a.pass_cnt, 0),
        coalesce(a.warning_cnt, 0),
        coalesce(a.blocked_cnt, 0),
        coalesce(a.waiting_cnt, 0),
        coalesce(a.check_total, 0)
    ) in ('READY', 'WARNING') as is_launch_eligible
from public.monthly_plan_labor_lines_v1 l
left join public.monthly_plan_constraint_line_agg_v1 a
    on a.plan_line_id = l.plan_line_id
where l.status = 'SENT_TO_ADMISSION';

comment on view public.monthly_plan_labor_admission_v1 is
    'Admission labor lines. Launch hours = READY + WARNING. Does not use constraints.required_hours as SoT.';

-- -----------------------------------------------------------------------------
-- View 4: monthly_plan_labor_admission_summary_v1
-- Grain: project_code + month_key
-- -----------------------------------------------------------------------------
create or replace view public.monthly_plan_labor_admission_summary_v1 as
select
    a.project_code,
    a.month_key,
    count(*)::bigint as admission_line_count,
    count(distinct a.boq_code)::bigint as admission_boq_count,
    coalesce(sum(a.plan_value), 0)::numeric as total_plan_value,
    coalesce(sum(a.labor_hours), 0)::numeric as total_labor_hours,
    coalesce(sum(a.labor_cost), 0)::numeric as total_labor_cost,
    coalesce(sum(a.fte_required), 0)::numeric as total_fte_required,
    max(a.hours_per_person_month)::numeric as hours_per_person_month,
    coalesce(sum(a.labor_hours) filter (where a.admission_labor_status = 'READY'), 0)::numeric as ready_hours,
    coalesce(sum(a.labor_hours) filter (where a.admission_labor_status = 'WARNING'), 0)::numeric as warning_hours,
    coalesce(sum(a.labor_hours) filter (where a.admission_labor_status = 'BLOCKED'), 0)::numeric as blocked_hours,
    coalesce(sum(a.labor_hours) filter (where a.admission_labor_status = 'WAITING'), 0)::numeric as waiting_hours,
    coalesce(sum(a.labor_hours) filter (where a.admission_labor_status = 'NO_CHECKS'), 0)::numeric as no_checks_hours,
    coalesce(sum(a.labor_hours) filter (where a.is_launch_eligible), 0)::numeric as launch_hours,
    coalesce(sum(a.fte_required) filter (where a.is_launch_eligible), 0)::numeric as launch_fte,
    count(*) filter (where a.admission_labor_status = 'READY')::bigint as ready_line_count,
    count(*) filter (where a.admission_labor_status = 'WARNING')::bigint as warning_line_count,
    count(*) filter (where a.admission_labor_status = 'BLOCKED')::bigint as blocked_line_count,
    count(*) filter (where a.admission_labor_status = 'WAITING')::bigint as waiting_line_count,
    count(*) filter (where a.is_launch_eligible)::bigint as launch_line_count
from public.monthly_plan_labor_admission_v1 a
group by
    a.project_code,
    a.month_key;

comment on view public.monthly_plan_labor_admission_summary_v1 is
    'Admission labor KPI rollup. launch_hours = READY + WARNING per approved policy.';

-- -----------------------------------------------------------------------------
-- View 5: monthly_plan_capacity_v1
-- Grain: project_code + month_key + crew
-- Plan demand from v2; available capacity from monthly_labor_summary
-- -----------------------------------------------------------------------------
create or replace view public.monthly_plan_capacity_v1 as
with cfg as (
    select public.planning_config_numeric('hours_per_person_month', 176)::numeric as hours_per_person_month
),
plan_by_crew as (
    select
        l.project_code,
        l.month_key,
        nullif(trim(l.crew), '') as crew_code,
        coalesce(sum(l.labor_hours), 0)::numeric as plan_labor_hours,
        coalesce(sum(l.labor_cost), 0)::numeric as plan_labor_cost,
        coalesce(sum(l.fte_required), 0)::numeric as plan_fte_required,
        count(*)::bigint as plan_line_count
    from public.monthly_plan_labor_lines_v1 l
    where nullif(trim(l.crew), '') is not null
    group by
        l.project_code,
        l.month_key,
        nullif(trim(l.crew), '')
),
capacity_by_crew as (
    select
        nullif(trim(mls.project_code), '') as project_code,
        nullif(trim(mls.month_key), '') as month_key,
        nullif(trim(mls.crew_code), '') as crew_code,
        coalesce(sum(mls.direct_hours_month), 0)::numeric as available_labor_hours,
        coalesce(sum(mls.direct_cost_rub_month), 0)::numeric as available_labor_cost,
        count(*)::bigint as roster_row_count
    from public.monthly_labor_summary mls
    where nullif(trim(mls.crew_code), '') is not null
    group by
        nullif(trim(mls.project_code), ''),
        nullif(trim(mls.month_key), ''),
        nullif(trim(mls.crew_code), '')
)
select
    coalesce(p.project_code, c.project_code) as project_code,
    coalesce(p.month_key, c.month_key) as month_key,
    coalesce(p.crew_code, c.crew_code) as crew_code,
    cfg.hours_per_person_month,
    coalesce(p.plan_labor_hours, 0)::numeric as plan_labor_hours,
    coalesce(p.plan_labor_cost, 0)::numeric as plan_labor_cost,
    coalesce(p.plan_fte_required, 0)::numeric as plan_fte_required,
    coalesce(p.plan_line_count, 0)::bigint as plan_line_count,
    coalesce(c.available_labor_hours, 0)::numeric as available_labor_hours,
    coalesce(c.available_labor_cost, 0)::numeric as available_labor_cost,
    coalesce(c.roster_row_count, 0)::bigint as roster_row_count,
    case
        when cfg.hours_per_person_month > 0
            then (coalesce(c.available_labor_hours, 0) / cfg.hours_per_person_month)::numeric
        else 0::numeric
    end as available_fte,
    (coalesce(c.available_labor_hours, 0) - coalesce(p.plan_labor_hours, 0))::numeric as hours_gap,
    (
        case
            when cfg.hours_per_person_month > 0
                then (coalesce(c.available_labor_hours, 0) / cfg.hours_per_person_month)::numeric
            else 0::numeric
        end
        - coalesce(p.plan_fte_required, 0)
    )::numeric as fte_gap
from plan_by_crew p
full outer join capacity_by_crew c
    on c.project_code = p.project_code
   and c.month_key = p.month_key
   and c.crew_code = p.crew_code
cross join cfg;

comment on view public.monthly_plan_capacity_v1 is
    'Plan demand vs roster capacity by crew. Economics layer read-model.';

-- -----------------------------------------------------------------------------
-- View 6: monthly_plan_passport_resource_v1
-- Grain: passport_id — frozen resource commitment snapshot
-- -----------------------------------------------------------------------------
create or replace view public.monthly_plan_passport_resource_v1 as
with cfg as (
    select public.planning_config_numeric('hours_per_person_month', 176)::numeric as hours_per_person_month
),
passport_lines as (
    select
        l.passport_id,
        count(*)::bigint as line_count,
        count(distinct l.boq_code)::bigint as boq_count,
        count(distinct nullif(trim(l.crew_id), ''))::bigint as crew_count,
        coalesce(sum(l.planned_qty), 0)::numeric as total_planned_qty,
        coalesce(sum(l.plan_value), 0)::numeric as total_plan_value,
        coalesce(sum(l.required_hours), 0)::numeric as total_required_hours,
        coalesce(sum(l.labor_cost), 0)::numeric as total_labor_cost
    from public.monthly_plan_passport_lines l
    group by
        l.passport_id
),
project_capacity as (
    select
        nullif(trim(mls.project_code), '') as project_code,
        nullif(trim(mls.month_key), '') as month_key,
        coalesce(sum(mls.direct_hours_month), 0)::numeric as available_labor_hours
    from public.monthly_labor_summary mls
    group by
        nullif(trim(mls.project_code), ''),
        nullif(trim(mls.month_key), '')
)
select
    p.passport_id,
    p.passport_status,
    p.project_code,
    p.month_key,
    p.passport_name,
    p.approved_by,
    p.approved_at,
    p.total_plan_value as header_total_plan_value,
    p.total_required_hours as header_total_required_hours,
    p.total_labor_cost as header_total_labor_cost,
    p.rows_count as header_rows_count,
    pl.line_count,
    pl.boq_count,
    pl.crew_count,
    pl.total_planned_qty,
    pl.total_plan_value,
    pl.total_required_hours,
    pl.total_labor_cost,
    cfg.hours_per_person_month,
    case
        when cfg.hours_per_person_month > 0
            then (pl.total_required_hours / cfg.hours_per_person_month)::numeric
        else 0::numeric
    end as fte_required,
    coalesce(pc.available_labor_hours, 0)::numeric as available_labor_hours,
    case
        when cfg.hours_per_person_month > 0
            then (coalesce(pc.available_labor_hours, 0) / cfg.hours_per_person_month)::numeric
        else 0::numeric
    end as fte_available,
    (coalesce(pc.available_labor_hours, 0) - pl.total_required_hours)::numeric as hours_gap,
    (
        case
            when cfg.hours_per_person_month > 0
                then (coalesce(pc.available_labor_hours, 0) / cfg.hours_per_person_month)::numeric
            else 0::numeric
        end
        - case
            when cfg.hours_per_person_month > 0
                then (pl.total_required_hours / cfg.hours_per_person_month)::numeric
            else 0::numeric
        end
    )::numeric as fte_gap
from public.monthly_plan_passports p
inner join passport_lines pl
    on pl.passport_id = p.passport_id
left join project_capacity pc
    on pc.project_code = nullif(trim(p.project_code), '')
   and pc.month_key = nullif(trim(p.month_key), '')
cross join cfg;

comment on view public.monthly_plan_passport_resource_v1 is
    'Passport resource commitment rollup. Uses passport line required_hours (frozen), not live v2 lines.';
