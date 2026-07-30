-- =============================================================================
-- BOQ Execution History v1
-- =============================================================================
-- View: public.boq_execution_history_v1
-- Purpose: read-only lifetime execution history per admission grain for page 21
--          («C. История исполнения BOQ»). One row per grain.
--
-- Grain (all parts upper(trim(...))):
--   project_code + boq_code + facility_building + construction_discipline
--
-- Nullable facility/discipline use join keys with sentinel '__NULL__' so FULL OUTER
-- JOIN can use plain equality (PostgreSQL rejects IS NOT DISTINCT FROM on FULL JOIN).
-- UI fields never expose the sentinel — they stay NULL when the key is '__NULL__'.
--
-- Architecture (mandatory):
--   master_normalized → master_agg
--   fact_normalized   → fact_agg
--   master_agg FULL OUTER JOIN fact_agg
-- Never join raw master rows to raw Daily Progress rows (fan-out risk).
--
-- Sources:
--   public.boq_master_api
--   public.daily_progress_active
--
-- Not used: daily_progress_raw, daily_progress_monthly_agg, plan/passport/labor views.
--
-- Deploy: Supabase SQL Editor (manual) — do NOT auto-deploy from app.
-- Grants: see footer notes (anon cannot SELECT boq_master_api directly).
-- =============================================================================

CREATE OR REPLACE VIEW public.boq_execution_history_v1 AS
WITH
-- -----------------------------------------------------------------------------
-- 1) Master normalize
-- Narrow confirmed project fallback: only when project_code is empty AND
-- project_name is exactly 'БХК' → 'PRJ_001_БХК' (covers residual NULL rows).
-- No LIKE / partial match.
-- -----------------------------------------------------------------------------
master_normalized AS (
    SELECT
        coalesce(
            nullif(upper(trim(m.project_code)), ''),
            CASE
                WHEN upper(trim(m.project_name)) = 'БХК'
                    THEN 'PRJ_001_БХК'
                ELSE NULL
            END
        ) AS project_code_norm,
        upper(trim(m.boq_code)) AS boq_code_norm,
        -- Display / diagnostic (nullable); join key uses sentinel (never NULL).
        nullif(upper(trim(m.facility_building)), '') AS facility_building_norm,
        coalesce(
            nullif(upper(trim(m.facility_building)), ''),
            '__NULL__'
        ) AS facility_building_key,
        nullif(upper(trim(m.construction_discipline)), '') AS construction_discipline_norm,
        coalesce(
            nullif(upper(trim(m.construction_discipline)), ''),
            '__NULL__'
        ) AS construction_discipline_key,
        nullif(upper(trim(m.unit_of_measure)), '') AS unit_of_measure_norm,
        nullif(trim(m.project_code), '') AS project_code_raw,
        nullif(trim(m.project_name), '') AS project_name_raw,
        nullif(trim(m.boq_code), '') AS boq_code_raw,
        nullif(trim(m.facility_building), '') AS facility_building_raw,
        nullif(trim(m.construction_discipline), '') AS construction_discipline_raw,
        m.project_qty_num,
        m.total_value_num,
        m.unit_price_num
    FROM public.boq_master_api m
    WHERE coalesce(m.is_deleted, false) = false
      AND nullif(trim(m.boq_code), '') IS NOT NULL
),
master_normalized_keyed AS (
    SELECT *
    FROM master_normalized
    WHERE project_code_norm IS NOT NULL
),
-- -----------------------------------------------------------------------------
-- 2) Master aggregate (one row per grain)
-- -----------------------------------------------------------------------------
master_agg AS (
    SELECT
        mn.project_code_norm,
        mn.boq_code_norm,
        mn.facility_building_key,
        mn.construction_discipline_key,

        max(mn.project_code_raw) AS project_code,
        max(mn.boq_code_raw) AS boq_code,
        max(mn.facility_building_raw) AS facility_building,
        max(mn.construction_discipline_raw) AS construction_discipline,

        count(*)::bigint AS master_row_count,

        coalesce(sum(mn.project_qty_num), 0)::numeric AS project_qty_full,

        coalesce(sum(mn.total_value_num), 0)::numeric AS boq_total_value_total_value,

        coalesce(
            sum(
                CASE
                    WHEN mn.project_qty_num IS NOT NULL
                     AND mn.unit_price_num IS NOT NULL
                        THEN mn.project_qty_num * mn.unit_price_num
                    ELSE 0
                END
            ),
            0
        )::numeric AS boq_total_value_qty_price,

        CASE
            WHEN coalesce(sum(mn.total_value_num), 0) > 0
                THEN coalesce(sum(mn.total_value_num), 0)::numeric
            WHEN coalesce(
                sum(
                    CASE
                        WHEN mn.project_qty_num IS NOT NULL
                         AND mn.unit_price_num IS NOT NULL
                            THEN mn.project_qty_num * mn.unit_price_num
                        ELSE 0
                    END
                ),
                0
            ) > 0
                THEN coalesce(
                    sum(
                        CASE
                            WHEN mn.project_qty_num IS NOT NULL
                             AND mn.unit_price_num IS NOT NULL
                                THEN mn.project_qty_num * mn.unit_price_num
                            ELSE 0
                        END
                    ),
                    0
                )::numeric
            ELSE NULL::numeric
        END AS boq_total_value,

        CASE
            WHEN coalesce(sum(mn.total_value_num), 0) > 0
                THEN 'TOTAL_VALUE'
            WHEN coalesce(
                sum(
                    CASE
                        WHEN mn.project_qty_num IS NOT NULL
                         AND mn.unit_price_num IS NOT NULL
                            THEN mn.project_qty_num * mn.unit_price_num
                        ELSE 0
                    END
                ),
                0
            ) > 0
                THEN 'QTY_X_UNIT_PRICE'
            ELSE 'MISSING'
        END AS boq_value_source,

        count(DISTINCT mn.unit_of_measure_norm)::bigint AS master_uom_count,
        string_agg(
            DISTINCT mn.unit_of_measure_norm,
            ', '
            ORDER BY mn.unit_of_measure_norm
        ) AS master_uom_list,
        CASE
            WHEN count(DISTINCT mn.unit_of_measure_norm) = 1
                THEN max(mn.unit_of_measure_norm)
            ELSE NULL
        END AS master_unit_of_measure
    FROM master_normalized_keyed mn
    GROUP BY
        mn.project_code_norm,
        mn.boq_code_norm,
        mn.facility_building_key,
        mn.construction_discipline_key
),
-- -----------------------------------------------------------------------------
-- 3) Fact normalize
-- Keep rows with hours and zero quantity (prep / unpaid volume patterns).
-- Do NOT filter quantity_today > 0 at this layer.
-- -----------------------------------------------------------------------------
fact_normalized AS (
    SELECT
        upper(trim(dp.project_code)) AS project_code_norm,
        upper(trim(dp.boq)) AS boq_code_norm,
        nullif(upper(trim(dp.facility_building)), '') AS facility_building_norm,
        coalesce(
            nullif(upper(trim(dp.facility_building)), ''),
            '__NULL__'
        ) AS facility_building_key,
        nullif(upper(trim(dp.construction_discipline)), '') AS construction_discipline_norm,
        coalesce(
            nullif(upper(trim(dp.construction_discipline)), ''),
            '__NULL__'
        ) AS construction_discipline_key,
        nullif(upper(trim(dp.unit_of_measure)), '') AS unit_of_measure_norm,
        nullif(trim(dp.crew_id), '') AS crew_id_norm,
        nullif(trim(dp.shift_type), '') AS shift_type_norm,
        nullif(trim(dp.project_code), '') AS project_code_raw,
        nullif(trim(dp.boq), '') AS boq_code_raw,
        nullif(trim(dp.facility_building), '') AS facility_building_raw,
        nullif(trim(dp.construction_discipline), '') AS construction_discipline_raw,
        dp.work_date,
        dp.quantity_today,
        dp.direct_work_hours,
        dp.ac_day_value,
        dp.direct_rate_rub_per_hour
    FROM public.daily_progress_active dp
    WHERE coalesce(dp.is_deleted, false) = false
      AND nullif(trim(dp.project_code), '') IS NOT NULL
      AND nullif(trim(dp.boq), '') IS NOT NULL
),
-- -----------------------------------------------------------------------------
-- 4) Fact aggregate (one row per grain)
-- Labor cost is row-wise: prefer AC > 0, else hours × rate; never plan rate 3000.
-- -----------------------------------------------------------------------------
fact_agg AS (
    SELECT
        fn.project_code_norm,
        fn.boq_code_norm,
        fn.facility_building_key,
        fn.construction_discipline_key,

        max(fn.project_code_raw) AS project_code,
        max(fn.boq_code_raw) AS boq_code,
        max(fn.facility_building_raw) AS facility_building,
        max(fn.construction_discipline_raw) AS construction_discipline,

        count(*)::bigint AS fact_row_count,
        true AS has_history,

        coalesce(sum(coalesce(fn.quantity_today, 0)), 0)::numeric AS actual_qty,
        coalesce(sum(coalesce(fn.direct_work_hours, 0)), 0)::numeric AS direct_work_hours,

        coalesce(
            sum(
                CASE
                    WHEN fn.ac_day_value IS NOT NULL THEN fn.ac_day_value
                    ELSE 0
                END
            ),
            0
        )::numeric AS labor_cost_ac,

        coalesce(
            sum(
                CASE
                    WHEN coalesce(fn.ac_day_value, 0) = 0
                     AND coalesce(fn.direct_work_hours, 0) > 0
                     AND coalesce(fn.direct_rate_rub_per_hour, 0) > 0
                        THEN fn.direct_work_hours * fn.direct_rate_rub_per_hour
                    ELSE 0
                END
            ),
            0
        )::numeric AS labor_cost_rate_fallback,

        coalesce(
            sum(
                CASE
                    WHEN fn.ac_day_value IS NOT NULL
                     AND fn.ac_day_value > 0
                        THEN fn.ac_day_value
                    WHEN coalesce(fn.direct_work_hours, 0) > 0
                     AND coalesce(fn.direct_rate_rub_per_hour, 0) > 0
                        THEN fn.direct_work_hours * fn.direct_rate_rub_per_hour
                    ELSE 0
                END
            ),
            0
        )::numeric AS labor_cost_actual,

        count(*) FILTER (
            WHERE coalesce(fn.ac_day_value, 0) > 0
        )::bigint AS rows_with_ac,

        count(*) FILTER (
            WHERE coalesce(fn.direct_work_hours, 0) > 0
              AND coalesce(fn.ac_day_value, 0) = 0
        )::bigint AS rows_without_ac_with_hours,

        count(*) FILTER (
            WHERE coalesce(fn.direct_work_hours, 0) > 0
              AND coalesce(fn.ac_day_value, 0) = 0
              AND coalesce(fn.direct_rate_rub_per_hour, 0) > 0
        )::bigint AS rows_with_rate_fallback,

        count(*) FILTER (
            WHERE coalesce(fn.direct_work_hours, 0) > 0
              AND coalesce(fn.ac_day_value, 0) = 0
              AND coalesce(fn.direct_rate_rub_per_hour, 0) <= 0
        )::bigint AS rows_without_cost_source,

        count(DISTINCT
            CASE
                WHEN fn.work_date IS NULL THEN NULL
                WHEN fn.shift_type_norm IS NOT NULL
                 AND fn.crew_id_norm IS NOT NULL
                    THEN fn.work_date::text || '|' || fn.shift_type_norm || '|' || fn.crew_id_norm
                WHEN fn.shift_type_norm IS NOT NULL
                    THEN fn.work_date::text || '|' || fn.shift_type_norm
                ELSE fn.work_date::text
            END
        )::bigint AS shift_count,

        count(DISTINCT fn.crew_id_norm)::bigint AS crew_count,
        string_agg(
            DISTINCT fn.crew_id_norm,
            ', '
            ORDER BY fn.crew_id_norm
        ) AS crew_list,

        bool_or(fn.crew_id_norm IS NULL) AS missing_crew,
        bool_or(fn.shift_type_norm IS NULL) AS missing_shift_type,

        count(DISTINCT fn.unit_of_measure_norm)::bigint AS fact_uom_count,
        string_agg(
            DISTINCT fn.unit_of_measure_norm,
            ', '
            ORDER BY fn.unit_of_measure_norm
        ) AS fact_uom_list,
        CASE
            WHEN count(DISTINCT fn.unit_of_measure_norm) = 1
                THEN max(fn.unit_of_measure_norm)
            ELSE NULL
        END AS fact_unit_of_measure,

        min(fn.work_date) AS min_work_date,
        max(fn.work_date) AS max_work_date
    FROM fact_normalized fn
    GROUP BY
        fn.project_code_norm,
        fn.boq_code_norm,
        fn.facility_building_key,
        fn.construction_discipline_key
),
-- -----------------------------------------------------------------------------
-- 5) Join aggregates only (FULL OUTER JOIN on equality-safe keys)
-- -----------------------------------------------------------------------------
joined AS (
    SELECT
        coalesce(m.project_code_norm, f.project_code_norm) AS project_code_norm,
        coalesce(m.boq_code_norm, f.boq_code_norm) AS boq_code_norm,
        coalesce(m.facility_building_key, f.facility_building_key) AS facility_building_key,
        coalesce(m.construction_discipline_key, f.construction_discipline_key)
            AS construction_discipline_key,

        coalesce(m.project_code, f.project_code) AS project_code,
        coalesce(m.boq_code, f.boq_code) AS boq_code,
        -- Never expose join sentinel '__NULL__' to UI fields.
        CASE
            WHEN coalesce(m.facility_building_key, f.facility_building_key) = '__NULL__'
                THEN NULL
            ELSE coalesce(m.facility_building, f.facility_building)
        END AS facility_building,
        CASE
            WHEN coalesce(m.construction_discipline_key, f.construction_discipline_key) = '__NULL__'
                THEN NULL
            ELSE coalesce(m.construction_discipline, f.construction_discipline)
        END AS construction_discipline,

        (m.project_code_norm IS NOT NULL) AS has_master,
        coalesce(f.has_history, false) AS has_history,

        coalesce(m.master_row_count, 0)::bigint AS master_row_count,
        coalesce(f.fact_row_count, 0)::bigint AS fact_row_count,

        m.project_qty_full,
        coalesce(f.actual_qty, 0)::numeric AS actual_qty,
        coalesce(f.direct_work_hours, 0)::numeric AS direct_work_hours,

        coalesce(f.labor_cost_ac, 0)::numeric AS labor_cost_ac,
        coalesce(f.labor_cost_rate_fallback, 0)::numeric AS labor_cost_rate_fallback,
        coalesce(f.labor_cost_actual, 0)::numeric AS labor_cost_actual,

        coalesce(f.rows_with_ac, 0)::bigint AS rows_with_ac,
        coalesce(f.rows_without_ac_with_hours, 0)::bigint AS rows_without_ac_with_hours,
        coalesce(f.rows_with_rate_fallback, 0)::bigint AS rows_with_rate_fallback,
        coalesce(f.rows_without_cost_source, 0)::bigint AS rows_without_cost_source,

        m.boq_total_value,
        m.boq_value_source,

        coalesce(f.shift_count, 0)::bigint AS shift_count,
        coalesce(f.crew_count, 0)::bigint AS crew_count,
        f.crew_list,
        coalesce(f.missing_crew, false) AS missing_crew,
        coalesce(f.missing_shift_type, false) AS missing_shift_type,

        coalesce(m.master_uom_count, 0)::bigint AS master_uom_count,
        m.master_uom_list,
        m.master_unit_of_measure,

        coalesce(f.fact_uom_count, 0)::bigint AS fact_uom_count,
        f.fact_uom_list,
        f.fact_unit_of_measure,

        f.min_work_date,
        f.max_work_date
    FROM master_agg m
    FULL OUTER JOIN fact_agg f
        ON m.project_code_norm = f.project_code_norm
       AND m.boq_code_norm = f.boq_code_norm
       AND m.facility_building_key = f.facility_building_key
       AND m.construction_discipline_key = f.construction_discipline_key
),
-- -----------------------------------------------------------------------------
-- 6) Derived metrics + technical data_status
-- Forecast blocked when execution_percent < 10% (prep-heavy / unreliable linear EAC).
-- Economic labels (NORM/RISK/LOSS) intentionally deferred to Python.
-- -----------------------------------------------------------------------------
enriched AS (
    SELECT
        j.*,

        CASE
            WHEN coalesce(j.direct_work_hours, 0) <= 0
                THEN 'NO_LABOR_HOURS'
            WHEN coalesce(j.rows_without_cost_source, 0) > 0
                THEN 'MISSING'
            WHEN coalesce(j.rows_with_ac, 0) > 0
             AND coalesce(j.rows_with_rate_fallback, 0) > 0
                THEN 'MIXED_AC_AND_RATE'
            WHEN coalesce(j.rows_with_ac, 0) > 0
             AND coalesce(j.rows_without_ac_with_hours, 0) = 0
                THEN 'AC_DAY_VALUE'
            WHEN coalesce(j.rows_with_rate_fallback, 0) > 0
             AND coalesce(j.rows_with_ac, 0) = 0
                THEN 'RATE_FALLBACK'
            ELSE 'MISSING'
        END AS labor_cost_source,

        CASE
            WHEN coalesce(j.direct_work_hours, 0) <= 0 THEN true
            WHEN coalesce(j.rows_without_cost_source, 0) > 0 THEN false
            ELSE true
        END AS labor_cost_complete,

        CASE
            WHEN j.project_qty_full IS NOT NULL
             AND j.project_qty_full > 0
                THEN (j.actual_qty / j.project_qty_full) * 100
            ELSE NULL
        END AS execution_percent,

        CASE
            WHEN j.project_qty_full IS NOT NULL
             AND j.actual_qty > j.project_qty_full
                THEN true
            ELSE false
        END AS actual_qty_exceeds_full_qty,

        CASE
            WHEN j.boq_total_value IS NOT NULL
                THEN j.boq_total_value - j.labor_cost_actual
            ELSE NULL
        END AS current_balance,

        CASE
            WHEN j.master_uom_count > 1 OR j.fact_uom_count > 1
                THEN 'MULTIPLE'
            WHEN j.master_unit_of_measure IS NULL
              OR j.fact_unit_of_measure IS NULL
                THEN 'MISSING'
            WHEN j.master_unit_of_measure = j.fact_unit_of_measure
                THEN 'MATCH'
            ELSE 'MISMATCH'
        END AS uom_check_status
    FROM joined j
),
final AS (
    SELECT
        e.project_code,
        e.boq_code,
        e.facility_building,
        e.construction_discipline,

        e.has_master,
        e.has_history,

        e.master_row_count,
        e.fact_row_count,

        e.project_qty_full,
        e.actual_qty,
        e.execution_percent,
        e.actual_qty_exceeds_full_qty,

        e.direct_work_hours,

        e.labor_cost_ac,
        e.labor_cost_rate_fallback,
        e.labor_cost_actual,
        e.labor_cost_source,
        e.labor_cost_complete,

        e.rows_with_ac,
        e.rows_without_ac_with_hours,
        e.rows_with_rate_fallback,
        e.rows_without_cost_source,

        e.boq_total_value,
        e.boq_value_source,

        e.current_balance,

        CASE
            WHEN e.boq_total_value IS NOT NULL
             AND e.boq_total_value > 0
             AND e.labor_cost_complete
                THEN (e.labor_cost_actual / e.boq_total_value) * 100
            ELSE NULL
        END AS labor_budget_used_percent,

        CASE
            WHEN e.boq_total_value IS NOT NULL
             AND e.boq_total_value > 0
             AND e.project_qty_full IS NOT NULL
             AND e.project_qty_full > 0
             AND e.actual_qty > 0
             AND e.labor_cost_complete
             AND e.uom_check_status = 'MATCH'
                THEN (e.labor_cost_actual / e.boq_total_value)
                   / (e.actual_qty / e.project_qty_full)
            ELSE NULL
        END AS labor_consumption_index,

        e.shift_count,
        e.crew_count,
        e.crew_list,
        e.missing_crew,
        e.missing_shift_type,

        e.master_uom_count,
        e.master_uom_list,
        e.master_unit_of_measure,

        e.fact_uom_count,
        e.fact_uom_list,
        e.fact_unit_of_measure,

        e.uom_check_status,
        (e.uom_check_status IN ('MISMATCH', 'MULTIPLE')) AS uom_mismatch,

        (
            e.has_history
            AND e.has_master
            AND e.execution_percent IS NOT NULL
            AND e.execution_percent >= 10
            AND e.project_qty_full IS NOT NULL
            AND e.project_qty_full > 0
            AND e.actual_qty > 0
            AND e.boq_total_value IS NOT NULL
            AND e.boq_total_value > 0
            AND e.labor_cost_complete
            AND e.uom_check_status = 'MATCH'
        ) AS forecast_allowed,

        CASE
            WHEN (
                e.has_history
                AND e.has_master
                AND e.execution_percent IS NOT NULL
                AND e.execution_percent >= 10
                AND e.project_qty_full IS NOT NULL
                AND e.project_qty_full > 0
                AND e.actual_qty > 0
                AND e.boq_total_value IS NOT NULL
                AND e.boq_total_value > 0
                AND e.labor_cost_complete
                AND e.uom_check_status = 'MATCH'
            )
                THEN e.labor_cost_actual / (e.execution_percent / 100)
            ELSE NULL
        END AS forecast_labor_cost,

        CASE
            WHEN (
                e.has_history
                AND e.has_master
                AND e.execution_percent IS NOT NULL
                AND e.execution_percent >= 10
                AND e.project_qty_full IS NOT NULL
                AND e.project_qty_full > 0
                AND e.actual_qty > 0
                AND e.boq_total_value IS NOT NULL
                AND e.boq_total_value > 0
                AND e.labor_cost_complete
                AND e.uom_check_status = 'MATCH'
            )
                THEN e.boq_total_value
                   - (e.labor_cost_actual / (e.execution_percent / 100))
            ELSE NULL
        END AS forecast_result,

        CASE
            WHEN NOT e.has_history THEN 'NO_HISTORY'
            WHEN NOT e.has_master THEN 'MASTER_MISSING'
            WHEN e.project_qty_full IS NULL OR e.project_qty_full <= 0 THEN 'PROJECT_QTY_MISSING'
            WHEN NOT e.labor_cost_complete THEN 'LABOR_COST_MISSING'
            WHEN e.uom_check_status IN ('MISMATCH', 'MULTIPLE') THEN 'UOM_MISMATCH'
            WHEN e.uom_check_status = 'MISSING' THEN 'UOM_MISSING'
            WHEN e.actual_qty = 0 AND e.direct_work_hours > 0 THEN 'ACTUAL_QTY_ZERO_WITH_HOURS'
            WHEN e.execution_percent IS NULL OR e.execution_percent < 10 THEN 'INSUFFICIENT_PROGRESS'
            ELSE 'READY'
        END AS data_status,

        e.min_work_date,
        e.max_work_date
    FROM enriched e
)
SELECT *
FROM final;


COMMENT ON VIEW public.boq_execution_history_v1 IS
'Lifetime BOQ execution history per project+boq+facility+discipline. '
'Pre-aggregates boq_master_api and daily_progress_active separately, then FULL OUTER JOIN. '
'Explicit BHK project_code fallback only for empty master.project_code. '
'Linear forecast allowed only when execution_percent >= 10 and UoM/labor cost complete.';


-- =============================================================================
-- Deploy notes (manual — do not auto-apply grants from app)
-- =============================================================================
-- RLS: anon/authenticated cannot SELECT boq_master_api (0 rows observed),
-- but can SELECT monthly_scope_picker_view. After CREATE VIEW, verify:
--
--   select * from public.boq_execution_history_v1
--   where project_code = 'PRJ_001_БХК'
--     and boq_code = '1500-03-01-01'
--     and trim(facility_building) = '16160-13'
--   limit 5;
--
-- If the view returns empty under the Streamlit key while SECRET sees rows,
-- grant SELECT on the view to the same roles that can read monthly_scope_picker_view
-- (typically authenticated / anon), WITHOUT SECURITY DEFINER and WITHOUT changing
-- table RLS. Example (only if confirmed needed):
--
--   grant select on public.boq_execution_history_v1 to authenticated, anon;
--
-- Prefer invoker rights (default). Do not add SECURITY DEFINER unless explicitly
-- approved after security review.
-- =============================================================================

-- =============================================================================
-- Verification SELECT (run after manual deploy)
-- =============================================================================
-- SELECT *
-- FROM public.boq_execution_history_v1
-- WHERE upper(trim(project_code)) = 'PRJ_001_БХК'
--   AND upper(trim(boq_code)) = '1500-03-01-01'
--   AND upper(trim(facility_building)) = '16160-13'
--   AND upper(trim(construction_discipline)) = upper(trim('Автоматизация'));
