-- =============================================================================
-- Productivity Engine v2
-- =============================================================================
-- New views only — does NOT replace or alter:
--   boq_productivity_statistics
--   plan_diagnostics
--   plan_corrective_actions
--   existing Streamlit pages / working views
--
-- Deploy: Supabase SQL Editor (run as single script)
-- Depends: public.daily_progress_active
-- =============================================================================

-- -----------------------------------------------------------------------------
-- View 1: productive_fact_clean_v1
-- Clean productive rows for norm calculation (qty + hours + EV > 0)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.productive_fact_clean_v1 AS
SELECT
    dp.month_key,
    dp.project_code,
    dp.facility_building,
    dp.construction_discipline,
    dp.crew_id,
    dp.foreman,
    dp.iwp_id,
    dp.system_label,
    dp.boq_name,
    dp.unit_of_measure,
    dp.quantity_today,
    dp.direct_work_hours,
    dp.productive_work_hours,
    dp.idle_hours,
    dp.ev_day_value,
    upper(trim(dp.boq)) AS boq_code_norm,
    (dp.direct_work_hours / nullif(dp.quantity_today, 0))::numeric AS direct_hours_per_unit,
    (dp.productive_work_hours / nullif(dp.quantity_today, 0))::numeric AS productive_hours_per_unit
FROM public.daily_progress_active dp
WHERE nullif(trim(dp.boq), '') IS NOT NULL
  AND coalesce(dp.quantity_today, 0) > 0
  AND coalesce(dp.direct_work_hours, 0) > 0
  AND coalesce(dp.ev_day_value, 0) > 0;


-- -----------------------------------------------------------------------------
-- View 2: paid_hours_without_ev_v1
-- Paid direct hours with zero EV — losses / project conditions layer.
-- NOT for norm calculation.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.paid_hours_without_ev_v1 AS
SELECT
    dp.month_key,
    dp.project_code,
    dp.facility_building,
    dp.construction_discipline,
    dp.shift_type,
    dp.crew_id,
    dp.foreman,
    upper(trim(dp.boq)) AS boq_code_norm,
    dp.boq_name,
    dp.quantity_today,
    dp.direct_work_hours,
    dp.productive_work_hours,
    dp.idle_hours,
    dp.idle_reason,
    dp.comment_foreman
FROM public.daily_progress_active dp
WHERE nullif(trim(dp.boq), '') IS NOT NULL
  AND coalesce(dp.direct_work_hours, 0) > 0
  AND coalesce(dp.ev_day_value, 0) = 0;


-- -----------------------------------------------------------------------------
-- View 3: boq_productivity_norms_v2
-- BOQ norms from clean productive fact
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.boq_productivity_norms_v2 AS
WITH agg AS (
    SELECT
        p.project_code,
        p.facility_building,
        p.construction_discipline,
        p.boq_code_norm,

        count(*)::bigint AS records_count,
        count(DISTINCT p.month_key)::bigint AS active_months_count,
        count(DISTINCT p.crew_id)::bigint AS crews_count,

        coalesce(sum(p.quantity_today), 0)::numeric AS total_qty,
        coalesce(sum(p.direct_work_hours), 0)::numeric AS total_direct_hours,
        coalesce(sum(p.productive_work_hours), 0)::numeric AS total_productive_hours,
        coalesce(sum(p.ev_day_value), 0)::numeric AS total_ev,

        (sum(p.direct_work_hours) / nullif(sum(p.quantity_today), 0))::numeric
            AS weighted_avg_hours_per_unit,

        percentile_cont(0.5) WITHIN GROUP (
            ORDER BY p.direct_hours_per_unit
        )::numeric AS p50_hours_per_unit,

        percentile_cont(0.8) WITHIN GROUP (
            ORDER BY p.direct_hours_per_unit
        )::numeric AS p80_hours_per_unit,

        min(p.direct_hours_per_unit)::numeric AS best_hours_per_unit,
        max(p.direct_hours_per_unit)::numeric AS worst_hours_per_unit,
        stddev_pop(p.direct_hours_per_unit)::numeric AS stddev_hours_per_unit

    FROM public.productive_fact_clean_v1 p
    GROUP BY
        p.project_code,
        p.facility_building,
        p.construction_discipline,
        p.boq_code_norm
)
SELECT
    a.*,
    CASE
        WHEN a.records_count >= 15
         AND a.active_months_count >= 2
         AND a.total_qty > 100
            THEN 'HIGH'
        WHEN a.records_count >= 5
            THEN 'MEDIUM'
        ELSE 'LOW'
    END AS confidence_level
FROM agg a;


-- =============================================================================
-- Verification SELECTs (4 BOQ codes)
-- Run after deploy.
-- =============================================================================

-- 1) productive_fact_clean_v1
SELECT
    'productive_fact_clean_v1' AS source_view,
    month_key,
    project_code,
    facility_building,
    construction_discipline,
    crew_id,
    foreman,
    iwp_id,
    system_label,
    boq_code_norm,
    boq_name,
    unit_of_measure,
    quantity_today,
    direct_work_hours,
    productive_work_hours,
    idle_hours,
    ev_day_value,
    direct_hours_per_unit,
    productive_hours_per_unit
FROM public.productive_fact_clean_v1
WHERE boq_code_norm IN (
    '2041-01-26-01',
    '2041-01-26-22',
    '1500-02-03-09',
    '1470-01-04-01'
)
ORDER BY boq_code_norm, month_key, crew_id;


-- 2) paid_hours_without_ev_v1
SELECT
    'paid_hours_without_ev_v1' AS source_view,
    month_key,
    project_code,
    facility_building,
    construction_discipline,
    shift_type,
    crew_id,
    foreman,
    boq_code_norm,
    boq_name,
    quantity_today,
    direct_work_hours,
    productive_work_hours,
    idle_hours,
    idle_reason,
    comment_foreman
FROM public.paid_hours_without_ev_v1
WHERE boq_code_norm IN (
    '2041-01-26-01',
    '2041-01-26-22',
    '1500-02-03-09',
    '1470-01-04-01'
)
ORDER BY boq_code_norm, month_key, crew_id;


-- 3) boq_productivity_norms_v2
SELECT
    'boq_productivity_norms_v2' AS source_view,
    project_code,
    facility_building,
    construction_discipline,
    boq_code_norm,
    records_count,
    active_months_count,
    crews_count,
    total_qty,
    total_direct_hours,
    total_productive_hours,
    total_ev,
    weighted_avg_hours_per_unit,
    p50_hours_per_unit,
    p80_hours_per_unit,
    best_hours_per_unit,
    worst_hours_per_unit,
    stddev_hours_per_unit,
    confidence_level
FROM public.boq_productivity_norms_v2
WHERE boq_code_norm IN (
    '2041-01-26-01',
    '2041-01-26-22',
    '1500-02-03-09',
    '1470-01-04-01'
)
ORDER BY boq_code_norm, project_code, facility_building, construction_discipline;


-- 4) Summary check across all three views
SELECT
    n.boq_code_norm,
    n.project_code,
    n.facility_building,
    n.construction_discipline,
    n.records_count,
    n.total_qty,
    n.weighted_avg_hours_per_unit,
    n.p50_hours_per_unit,
    n.p80_hours_per_unit,
    n.confidence_level,
    (
        SELECT count(*)
        FROM public.productive_fact_clean_v1 c
        WHERE c.boq_code_norm = n.boq_code_norm
          AND c.project_code = n.project_code
          AND c.facility_building IS NOT DISTINCT FROM n.facility_building
          AND c.construction_discipline IS NOT DISTINCT FROM n.construction_discipline
    ) AS clean_rows_check,
    (
        SELECT count(*)
        FROM public.paid_hours_without_ev_v1 p
        WHERE p.boq_code_norm = n.boq_code_norm
          AND p.project_code = n.project_code
          AND p.facility_building IS NOT DISTINCT FROM n.facility_building
          AND p.construction_discipline IS NOT DISTINCT FROM n.construction_discipline
    ) AS paid_no_ev_rows_check
FROM public.boq_productivity_norms_v2 n
WHERE n.boq_code_norm IN (
    '2041-01-26-01',
    '2041-01-26-22',
    '1500-02-03-09',
    '1470-01-04-01'
)
ORDER BY n.boq_code_norm, n.project_code, n.facility_building, n.construction_discipline;
