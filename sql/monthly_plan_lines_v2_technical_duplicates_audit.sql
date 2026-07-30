-- =============================================================================
-- TECHNICAL DUPLICATES AUDIT — monthly_plan_lines_v2
-- DIAGNOSTIC ONLY. No DELETE / UPDATE / INSERT.
-- =============================================================================
-- Business twin key (NULL-safe):
--   project_code
--   month_key
--   facility            (= facility_building in product language)
--   discipline          (= construction_discipline)
--   crew
--   boq_code
--   planned_qty         (= plan_qty)
--   plan_value
--   labor_hours         (= required_work_hours)
--   unit_price
--   system              (= system_label; NULL = NULL)
--   iwp                 (= iwp_id; NULL = NULL)
--
-- KEEP  = earliest created_at within group (tie-break: min plan_line_id)
-- DELETE candidates = all other rows in the same group
-- =============================================================================

-- -----------------------------------------------------------------------------
-- A) Full candidate list
-- -----------------------------------------------------------------------------
with base as (
  select
    p.plan_line_id,
    p.project_code,
    p.month_key,
    p.facility,
    p.discipline,
    p.crew,
    p.boq_code,
    p.planned_qty,
    p.plan_value,
    p.labor_hours,
    p.unit_price,
    p.system,
    p.iwp,
    p.created_at,
    p.status,
    md5(
      concat_ws(
        '||',
        coalesce(p.project_code, ''),
        coalesce(p.month_key, ''),
        coalesce(p.facility, ''),
        coalesce(p.discipline, ''),
        coalesce(p.crew, ''),
        coalesce(p.boq_code, ''),
        coalesce(p.planned_qty::text, ''),
        coalesce(p.plan_value::text, ''),
        coalesce(p.labor_hours::text, ''),
        coalesce(p.unit_price::text, ''),
        coalesce(p.system, ''),
        coalesce(p.iwp, '')
      )
    ) as group_id
  from public.monthly_plan_lines_v2 p
),
ranked as (
  select
    b.*,
    count(*) over (partition by b.group_id) as group_size,
    first_value(b.plan_line_id) over (
      partition by b.group_id
      order by b.created_at asc nulls last, b.plan_line_id asc
    ) as keep_plan_line_id,
    row_number() over (
      partition by b.group_id
      order by b.created_at asc nulls last, b.plan_line_id asc
    ) as rn
  from base b
),
delete_candidates as (
  select
    r.group_id as "GROUP_ID",
    r.keep_plan_line_id as "KEEP_PLAN_LINE_ID",
    r.plan_line_id as "DELETE_PLAN_LINE_ID",
    r.boq_code as "BOQ_CODE",
    r.facility as "FACILITY",
    r.crew as "CREW",
    r.planned_qty as "QTY",
    r.plan_value as "VALUE",
    r.labor_hours as "HOURS",
    r.created_at as "CREATED_AT",
    format(
      'technical duplicate of %s (same project/month/facility/discipline/crew/boq/qty/value/hours/unit_price/system/iwp); keep earliest created_at',
      r.keep_plan_line_id
    ) as "DELETE_REASON",
    r.project_code,
    r.month_key,
    r.status,
    r.group_size
  from ranked r
  where r.group_size > 1
    and r.rn > 1
)
select
  "GROUP_ID",
  "KEEP_PLAN_LINE_ID",
  "DELETE_PLAN_LINE_ID",
  "BOQ_CODE",
  "FACILITY",
  "CREW",
  "QTY",
  "VALUE",
  "HOURS",
  "CREATED_AT",
  "DELETE_REASON"
from delete_candidates
order by
  "BOQ_CODE",
  "FACILITY",
  "CREW",
  "CREATED_AT",
  "DELETE_PLAN_LINE_ID";


-- -----------------------------------------------------------------------------
-- B) Impact summary (run separately)
-- -----------------------------------------------------------------------------
/*
with base as (
  select
    p.plan_line_id,
    p.plan_value,
    p.labor_hours,
    md5(
      concat_ws(
        '||',
        coalesce(p.project_code, ''),
        coalesce(p.month_key, ''),
        coalesce(p.facility, ''),
        coalesce(p.discipline, ''),
        coalesce(p.crew, ''),
        coalesce(p.boq_code, ''),
        coalesce(p.planned_qty::text, ''),
        coalesce(p.plan_value::text, ''),
        coalesce(p.labor_hours::text, ''),
        coalesce(p.unit_price::text, ''),
        coalesce(p.system, ''),
        coalesce(p.iwp, '')
      )
    ) as group_id,
    p.created_at
  from public.monthly_plan_lines_v2 p
),
ranked as (
  select
    b.*,
    count(*) over (partition by b.group_id) as group_size,
    row_number() over (
      partition by b.group_id
      order by b.created_at asc nulls last, b.plan_line_id asc
    ) as rn
  from base b
),
marked as (
  select
    *,
    (group_size > 1 and rn > 1) as is_delete_candidate
  from ranked
)
select
  count(*) filter (where is_delete_candidate)                         as rows_to_delete,
  count(*) filter (where not is_delete_candidate)                     as rows_remaining,
  count(*)                                                            as rows_before,
  coalesce(sum(plan_value) filter (where is_delete_candidate), 0)     as plan_value_removed,
  coalesce(sum(labor_hours) filter (where is_delete_candidate), 0)    as labor_hours_removed,
  coalesce(sum(plan_value), 0)                                        as plan_value_before,
  coalesce(sum(plan_value) filter (where not is_delete_candidate), 0) as plan_value_after,
  coalesce(sum(labor_hours), 0)                                       as labor_hours_before,
  coalesce(sum(labor_hours) filter (where not is_delete_candidate), 0) as labor_hours_after
from marked;
*/
