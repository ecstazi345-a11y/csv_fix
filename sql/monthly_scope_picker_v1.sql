-- =============================================================================
-- Monthly Scope Picker v1
-- =============================================================================
-- View: public.monthly_scope_picker_view
-- Purpose: data layer for page "Конструктор месячного плана"
--
-- New view only — does NOT replace or alter existing SQL/views/pages.
--
-- Deploy: Supabase SQL Editor (run as single script)
-- Depends:
--   public.boq_master_api
--   public.daily_progress_active
--   public.boq_productivity_norms_v2
--   public.monthly_scope_manual_adjustments
-- =============================================================================

CREATE OR REPLACE VIEW public.monthly_scope_picker_view AS
WITH boq_master_clean AS (
    SELECT
        coalesce(nullif(trim(m.project_code), ''), trim(m.project_name)) AS project_code,
        m.facility_building,
        m.construction_discipline,
        upper(trim(m.boq_code)) AS boq_code,
        upper(trim(coalesce(nullif(trim(m.project_code), ''), trim(m.project_name), ''))) AS project_code_norm,
        upper(trim(coalesce(m.facility_building, ''))) AS facility_building_norm,
        upper(trim(coalesce(m.construction_discipline, ''))) AS construction_discipline_norm,
        upper(trim(m.boq_code)) AS boq_code_norm,
        coalesce(nullif(trim(m.description), ''), nullif(trim(m.name), '')) AS boq_name,
        m.unit_of_measure,
        coalesce(m.project_qty_num, 0)::numeric AS project_qty_row,
        coalesce(m.total_value_num, 0)::numeric AS total_value_row,
        m.unit_price_num::numeric AS unit_price_num
    FROM public.boq_master_api m
    WHERE coalesce(m.is_deleted, false) = false
      AND nullif(trim(m.boq_code), '') IS NOT NULL
),
boq_master_agg AS (
    SELECT
        b.project_code_norm,
        b.facility_building_norm,
        b.construction_discipline_norm,
        b.boq_code_norm,
        max(b.project_code) AS project_code,
        max(b.facility_building) AS facility_building,
        max(b.construction_discipline) AS construction_discipline,
        max(b.boq_code) AS boq_code,
        max(b.boq_name) AS boq_name,
        max(b.unit_of_measure) AS unit_of_measure,
        sum(b.project_qty_row)::numeric AS total_project_qty,
        sum(b.total_value_row)::numeric AS total_project_value_raw,
        CASE
            WHEN sum(b.project_qty_row) > 0
                THEN (sum(b.total_value_row) / sum(b.project_qty_row))::numeric
            ELSE NULL::numeric
        END AS implied_unit_price,
        max(b.unit_price_num) AS max_unit_price_num
    FROM boq_master_clean b
    GROUP BY
        b.project_code_norm,
        b.facility_building_norm,
        b.construction_discipline_norm,
        b.boq_code_norm
),
boq_master_priced AS (
    SELECT
        a.*,
        coalesce(a.max_unit_price_num, a.implied_unit_price, 0)::numeric AS unit_price,
        coalesce(
            a.total_project_value_raw,
            coalesce(a.max_unit_price_num, a.implied_unit_price, 0) * a.total_project_qty,
            0
        )::numeric AS total_project_value
    FROM boq_master_agg a
),
executed_all_time AS (
    SELECT
        upper(trim(coalesce(dp.project_code, ''))) AS project_code_norm,
        upper(trim(coalesce(dp.facility_building, ''))) AS facility_building_norm,
        upper(trim(coalesce(dp.construction_discipline, ''))) AS construction_discipline_norm,
        upper(trim(dp.boq)) AS boq_code_norm,
        coalesce(sum(dp.quantity_today), 0)::numeric AS executed_qty_all_time
    FROM public.daily_progress_active dp
    WHERE nullif(trim(dp.boq), '') IS NOT NULL
      AND coalesce(dp.quantity_today, 0) > 0
    GROUP BY
        upper(trim(coalesce(dp.project_code, ''))),
        upper(trim(coalesce(dp.facility_building, ''))),
        upper(trim(coalesce(dp.construction_discipline, ''))),
        upper(trim(dp.boq))
),
norms_clean AS (
    SELECT
        upper(trim(coalesce(n.project_code, ''))) AS project_code_norm,
        upper(trim(coalesce(n.facility_building, ''))) AS facility_building_norm,
        upper(trim(coalesce(n.construction_discipline, ''))) AS construction_discipline_norm,
        upper(trim(coalesce(n.boq_code_norm, ''))) AS boq_code_norm,
        n.p50_hours_per_unit,
        n.p80_hours_per_unit,
        n.weighted_avg_hours_per_unit,
        n.confidence_level
    FROM public.boq_productivity_norms_v2 n
    WHERE nullif(trim(coalesce(n.boq_code_norm, '')), '') IS NOT NULL
),
adjustments_latest AS (
    SELECT DISTINCT ON (
        upper(trim(coalesce(a.project_code, ''))),
        upper(trim(coalesce(a.facility_building, ''))),
        upper(trim(coalesce(a.construction_discipline, ''))),
        upper(trim(coalesce(a.boq_code, '')))
    )
        upper(trim(coalesce(a.project_code, ''))) AS project_code_norm,
        upper(trim(coalesce(a.facility_building, ''))) AS facility_building_norm,
        upper(trim(coalesce(a.construction_discipline, ''))) AS construction_discipline_norm,
        upper(trim(coalesce(a.boq_code, ''))) AS boq_code_norm,
        a.manual_executed_before_system,
        a.manual_verified_remaining_qty,
        a.reason AS manual_adjustment_reason,
        a.comment AS manual_adjustment_comment
    FROM public.monthly_scope_manual_adjustments a
    ORDER BY
        upper(trim(coalesce(a.project_code, ''))),
        upper(trim(coalesce(a.facility_building, ''))),
        upper(trim(coalesce(a.construction_discipline, ''))),
        upper(trim(coalesce(a.boq_code, ''))),
        a.updated_at DESC NULLS LAST
),
base_scoped AS (
    SELECT
        b.project_code,
        b.facility_building,
        b.construction_discipline,
        b.boq_code,
        b.boq_name,
        b.unit_of_measure,
        b.total_project_qty,
        coalesce(e.executed_qty_all_time, 0)::numeric AS executed_qty_all_time,
        (
            b.total_project_qty - coalesce(e.executed_qty_all_time, 0)
        )::numeric AS system_remaining_qty,
        b.unit_price,
        b.total_project_value,
        (coalesce(e.executed_qty_all_time, 0) * b.unit_price)::numeric AS executed_value_all_time,
        n.p50_hours_per_unit,
        n.p80_hours_per_unit,
        n.weighted_avg_hours_per_unit,
        n.confidence_level,
        coalesce(adj.manual_executed_before_system, 0)::numeric AS manual_executed_before_system,
        adj.manual_verified_remaining_qty,
        adj.manual_adjustment_reason,
        adj.manual_adjustment_comment
    FROM boq_master_priced b
    LEFT JOIN executed_all_time e
        ON e.project_code_norm = b.project_code_norm
       AND e.facility_building_norm = b.facility_building_norm
       AND e.construction_discipline_norm = b.construction_discipline_norm
       AND e.boq_code_norm = b.boq_code_norm
    LEFT JOIN norms_clean n
        ON n.project_code_norm = b.project_code_norm
       AND n.facility_building_norm = b.facility_building_norm
       AND n.construction_discipline_norm = b.construction_discipline_norm
       AND n.boq_code_norm = b.boq_code_norm
    LEFT JOIN adjustments_latest adj
        ON adj.project_code_norm = b.project_code_norm
       AND adj.facility_building_norm = b.facility_building_norm
       AND adj.construction_discipline_norm = b.construction_discipline_norm
       AND adj.boq_code_norm = b.boq_code_norm
),
scoped AS (
    SELECT
        b.*,
        CASE
            WHEN b.manual_verified_remaining_qty IS NOT NULL
                THEN b.manual_verified_remaining_qty
            ELSE greatest(
                b.total_project_qty
                    - b.executed_qty_all_time
                    - coalesce(b.manual_executed_before_system, 0),
                0
            )
        END AS planning_remaining_qty,
        CASE
            WHEN b.manual_verified_remaining_qty IS NOT NULL
                THEN 'MANUAL_VERIFIED'
            WHEN coalesce(b.manual_executed_before_system, 0) > 0
                THEN 'MANUAL_EXECUTED_BEFORE_SYSTEM'
            ELSE 'SYSTEM_CALCULATED'
        END AS remaining_qty_source
    FROM base_scoped b
)
SELECT
    s.project_code,
    s.facility_building,
    s.construction_discipline,
    s.boq_code,
    s.boq_name,
    s.unit_of_measure,
    s.total_project_qty,
    s.executed_qty_all_time,
    s.manual_executed_before_system,
    s.system_remaining_qty,
    s.manual_verified_remaining_qty,
    s.planning_remaining_qty,
    s.remaining_qty_source,
    s.unit_price,
    s.total_project_value,
    s.executed_value_all_time,
    (s.planning_remaining_qty * s.unit_price)::numeric AS planning_remaining_value,
    s.p50_hours_per_unit,
    s.p80_hours_per_unit,
    s.weighted_avg_hours_per_unit,
    s.confidence_level,
    s.manual_adjustment_reason,
    s.manual_adjustment_comment,
    CASE
        WHEN s.p50_hours_per_unit IS NULL THEN 'НЕТ ИСТОРИИ'
        ELSE 'ИСТОРИЯ ЕСТЬ'
    END AS norm_status,
    (s.planning_remaining_qty * s.p50_hours_per_unit)::numeric AS estimated_hours_p50_remaining,
    (s.planning_remaining_qty * s.p80_hours_per_unit)::numeric AS estimated_hours_p80_remaining
FROM scoped s;


-- =============================================================================
-- Verification SELECT
-- =============================================================================
SELECT *
FROM public.monthly_scope_picker_view
WHERE boq_code IN (
    '2041-01-26-01',
    '2041-01-26-22',
    '1500-02-03-09',
    '1470-01-04-01'
)
ORDER BY facility_building, construction_discipline, boq_code;
