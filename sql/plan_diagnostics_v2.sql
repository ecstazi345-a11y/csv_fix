-- =============================================================================
-- E.3.1 — Plan Diagnostics Engine v2
-- =============================================================================
-- View:     public.plan_diagnostics
-- Source:   public.draft_month_plan
-- Purpose:  AI explanation layer — «Почему план плохой?» / «Что изменить?»
--
-- Deploy:   Supabase SQL Editor (run as single script)
-- Depends:  public.draft_month_plan must exist
-- =============================================================================

CREATE OR REPLACE VIEW public.plan_diagnostics AS
WITH line_agg AS (
    SELECT
        d.month_key,
        d.project_code,
        d.crew_code,

        COUNT(*)::bigint AS plan_lines_count,

        COALESCE(SUM(d.planned_ev_line), 0)::numeric AS planned_ev_total,
        COALESCE(MAX(d.crew_total_labor_cost_month), 0)::numeric AS crew_cost_total,
        COALESCE(MAX(d.crew_direct_hours_month), 0)::numeric AS crew_available_hours,
        COALESCE(SUM(d.required_hours_management_line), 0)::numeric AS required_hours_management,
        COALESCE(SUM(d.required_hours_risk_p80_line), 0)::numeric AS required_hours_risk_p80,

        COUNT(*) FILTER (WHERE d.capacity_status = 'OVER_REMAINING')::bigint AS over_remaining_lines,
        COUNT(*) FILTER (WHERE d.capacity_status = 'LABOR_CAPACITY_FAIL')::bigint AS labor_capacity_fail_lines,
        COUNT(*) FILTER (WHERE d.capacity_status = 'NO_LABOR_PLAN')::bigint AS no_labor_plan_lines,
        COUNT(*) FILTER (WHERE d.capacity_status = 'NO_BALANCE_DATA')::bigint AS no_balance_data_lines,

        COUNT(*) FILTER (WHERE d.economic_status = 'ECONOMIC_FAIL')::bigint AS economic_fail_lines,
        COUNT(*) FILTER (WHERE d.economic_status = 'ECONOMIC_BREAK_EVEN')::bigint AS economic_break_even_lines,
        COUNT(*) FILTER (WHERE d.economic_status = 'ECONOMIC_LOW_MARGIN')::bigint AS economic_low_margin_lines,
        COUNT(*) FILTER (WHERE d.economic_status = 'NO_LABOR_COST')::bigint AS no_labor_cost_lines,
        COUNT(*) FILTER (WHERE d.economic_status = 'NO_PLANNED_EV')::bigint AS no_planned_ev_lines,

        COUNT(*) FILTER (WHERE d.norm_quality_status = 'MANUAL_NORM_REQUIRED')::bigint AS manual_norm_required_lines,
        COUNT(*) FILTER (WHERE d.norm_quality_status = 'LOW_CONFIDENCE_NORM')::bigint AS low_confidence_norm_lines,
        COUNT(*) FILTER (WHERE d.norm_quality_status = 'PRODUCTIVITY_UNSTABLE')::bigint AS productivity_unstable_lines,

        NULLIF(
            string_agg(DISTINCT d.boq_code, ', ' ORDER BY d.boq_code)
                FILTER (WHERE d.economic_status = 'ECONOMIC_FAIL'),
            ''
        ) AS economic_fail_codes,

        NULLIF(
            string_agg(DISTINCT d.boq_code, ', ' ORDER BY d.boq_code)
                FILTER (WHERE d.norm_quality_status = 'MANUAL_NORM_REQUIRED'),
            ''
        ) AS manual_norm_required_codes,

        NULLIF(
            string_agg(DISTINCT d.boq_code, ', ' ORDER BY d.boq_code)
                FILTER (WHERE d.norm_quality_status = 'PRODUCTIVITY_UNSTABLE'),
            ''
        ) AS productivity_unstable_codes,

        NULLIF(
            string_agg(DISTINCT d.boq_code, ', ' ORDER BY d.boq_code)
                FILTER (WHERE d.capacity_status = 'OVER_REMAINING'),
            ''
        ) AS over_remaining_codes

    FROM public.draft_month_plan d
    GROUP BY
        d.month_key,
        d.project_code,
        d.crew_code
),
metrics AS (
    SELECT
        a.*,

        (a.planned_ev_total - a.crew_cost_total)::numeric AS gross_margin,

        CASE
            WHEN a.crew_cost_total > 0
                THEN ROUND(a.planned_ev_total / a.crew_cost_total, 4)
            ELSE NULL
        END AS ev_to_cost_ratio,

        CASE
            WHEN a.planned_ev_total > 0
                THEN ROUND(a.crew_cost_total / a.planned_ev_total, 4)
            ELSE 0::numeric
        END AS cost_to_ev_ratio,

        GREATEST(a.crew_cost_total - a.planned_ev_total, 0)::numeric AS required_additional_ev,

        (a.crew_available_hours - a.required_hours_management)::numeric AS hours_gap_management,
        (a.crew_available_hours - a.required_hours_risk_p80)::numeric AS hours_gap_risk_p80

    FROM line_agg a
),
classified AS (
    SELECT
        m.*,

        CASE
            WHEN m.gross_margin < 0 AND m.hours_gap_management > 0
                THEN 'ECONOMIC_FAIL_LOW_VALUE_SCOPE'
            WHEN m.gross_margin < 0
                THEN 'ECONOMIC_FAIL'
            WHEN m.labor_capacity_fail_lines > 0
                THEN 'LABOR_CAPACITY_FAIL'
            WHEN m.over_remaining_lines > 0
                THEN 'OVER_REMAINING_SCOPE'
            WHEN m.no_labor_plan_lines > 0
                THEN 'NO_LABOR_PLAN'
            WHEN m.productivity_unstable_lines > 0
                THEN 'PRODUCTIVITY_UNSTABLE'
            WHEN m.manual_norm_required_lines > 0
                THEN 'NO_HISTORY_NORM'
            ELSE 'PLAN_OK'
        END AS primary_problem_code

    FROM metrics m
),
explained AS (
    SELECT
        c.*,

        CASE c.primary_problem_code
            WHEN 'ECONOMIC_FAIL_LOW_VALUE_SCOPE' THEN 'LOW_VALUE_SCOPE'
            WHEN 'ECONOMIC_FAIL' THEN 'ECONOMIC_DEFICIT'
            WHEN 'LABOR_CAPACITY_FAIL' THEN 'LABOR_CAPACITY_SHORTAGE'
            WHEN 'OVER_REMAINING_SCOPE' THEN 'SCOPE_OVERFLOW'
            WHEN 'NO_LABOR_PLAN' THEN 'NO_LABOR_DATA'
            WHEN 'PRODUCTIVITY_UNSTABLE' THEN 'PRODUCTIVITY_RISK'
            WHEN 'NO_HISTORY_NORM' THEN 'NO_HISTORY'
            ELSE 'OK'
        END AS root_cause,

        CASE
            WHEN c.gross_margin < 0 THEN 'RED'
            WHEN c.productivity_unstable_lines > 0 THEN 'ORANGE'
            ELSE 'YELLOW'
        END AS diagnostic_status

    FROM classified c
)
SELECT
    e.month_key,
    e.project_code,
    e.crew_code,

    e.plan_lines_count,
    e.planned_ev_total,
    e.crew_cost_total,
    e.gross_margin,
    e.ev_to_cost_ratio,
    e.cost_to_ev_ratio,
    e.required_additional_ev,

    e.crew_available_hours,
    e.required_hours_management,
    e.required_hours_risk_p80,
    e.hours_gap_management,
    e.hours_gap_risk_p80,

    e.over_remaining_lines,
    e.labor_capacity_fail_lines,
    e.no_labor_plan_lines,
    e.no_balance_data_lines,

    e.economic_fail_lines,
    e.economic_break_even_lines,
    e.economic_low_margin_lines,
    e.no_labor_cost_lines,
    e.no_planned_ev_lines,

    e.manual_norm_required_lines,
    e.low_confidence_norm_lines,
    e.productivity_unstable_lines,

    e.economic_fail_codes,
    e.manual_norm_required_codes,
    e.productivity_unstable_codes,
    e.over_remaining_codes,

    e.diagnostic_status,
    e.primary_problem_code,
    e.root_cause,

    -- -------------------------------------------------------------------------
    -- executive_summary (русский)
    -- -------------------------------------------------------------------------
    CASE e.primary_problem_code
        WHEN 'ECONOMIC_FAIL_LOW_VALUE_SCOPE' THEN
            'Проблема не в мощности звена, а в низкой стоимости запланированных работ. '
            || 'Звено имеет достаточный запас часов, но плановый EV не покрывает стоимость людей.'
        WHEN 'ECONOMIC_FAIL' THEN
            'План звена экономически убыточен: плановый EV не покрывает стоимость звена.'
        WHEN 'LABOR_CAPACITY_FAIL' THEN
            'План звена не укладывается в доступную мощность: не хватает чел-ч по базовому плану.'
        WHEN 'OVER_REMAINING_SCOPE' THEN
            'Часть плановых строк превышает остаток BOQ — план завышен относительно остатка.'
        WHEN 'NO_LABOR_PLAN' THEN
            'Для звена нет labor plan: не заданы люди / direct hours в monthly_labor_summary.'
        WHEN 'PRODUCTIVITY_UNSTABLE' THEN
            'По части кодов высокая нестабильность производительности. '
            || 'Есть риск, что фактические трудозатраты будут выше базового плана.'
        WHEN 'NO_HISTORY_NORM' THEN
            'По части кодов нет исторической нормы. Требуется ручной benchmark или накопление факта.'
        ELSE
            'План звена в пределах допустимых диагностических рамок.'
    END AS executive_summary,

    -- -------------------------------------------------------------------------
    -- management_action (русский)
    -- -------------------------------------------------------------------------
    CASE e.primary_problem_code
        WHEN 'ECONOMIC_FAIL_LOW_VALUE_SCOPE' THEN
            'Добавить более денежный фронт работ, укрупнить объём, перераспределить часть людей, '
            || 'сократить состав звена или объединить работы со смежным фронтом.'
        WHEN 'ECONOMIC_FAIL' THEN
            'Увеличить плановый EV, добавить высокодоходные работы, снизить стоимость звена '
            || 'или перенести часть людей на другой фронт.'
        WHEN 'LABOR_CAPACITY_FAIL' THEN
            'Сократить объём плана, перенести работы на другой месяц / звено, добавить людей '
            || 'или пересмотреть нормы и календарь.'
        WHEN 'OVER_REMAINING_SCOPE' THEN
            'Сверить план с остатком BOQ, убрать строки сверх остатка, перенести объём или уточнить факт.'
        WHEN 'NO_LABOR_PLAN' THEN
            'Заполнить Crew_Register / monthly_labor_summary: мобилизация, direct hours, стоимость звена.'
        WHEN 'PRODUCTIVITY_UNSTABLE' THEN
            'Для риск-плана использовать P80, проверить фронт, высотность, стеснённость, МТР '
            || 'и причины разброса производительности.'
        WHEN 'NO_HISTORY_NORM' THEN
            'Задать ручную норму, взять аналогичный код или дождаться накопления факта.'
        ELSE
            'Продолжить исполнение; контролировать факт и остаток BOQ.'
    END AS management_action,

    -- -------------------------------------------------------------------------
    -- detailed_explanation (русский, AI explanation layer)
    -- -------------------------------------------------------------------------
    CASE e.primary_problem_code
        WHEN 'ECONOMIC_FAIL_LOW_VALUE_SCOPE' THEN
            E'🔴 КРИТИЧЕСКОЕ ОТКЛОНЕНИЕ — ЭКОНОМИЧЕСКИ НЕЭФФЕКТИВНЫЙ ФРОНТ\n\n'
            || 'Звено: ' || e.crew_code || E'\n\n'
            || 'Плановый объём работ: '
            || to_char(ROUND(e.planned_ev_total)::bigint, 'FM999999990') || E' ₽\n'
            || 'Стоимость звена за месяц: '
            || to_char(ROUND(e.crew_cost_total)::bigint, 'FM999999990') || E' ₽\n'
            || 'Дефицит покрытия: '
            || to_char(ROUND(e.gross_margin)::bigint, 'FM999999990') || E' ₽\n\n'
            || E'МОЩНОСТЬ ЗВЕНА:\n'
            || 'Доступно: ' || to_char(ROUND(e.crew_available_hours)::bigint, 'FM999999990') || E' чел-ч\n'
            || 'Требуется: ' || to_char(ROUND(e.required_hours_management)::bigint, 'FM999999990')
            || E' чел-ч по базовому плану\n'
            || 'Риск-план P80: ' || to_char(ROUND(e.required_hours_risk_p80)::bigint, 'FM999999990')
            || E' чел-ч\n\n'
            || E'ВЫВОД:\n'
            || E'Проблема НЕ в нехватке мощности звена.\n'
            || E'У звена есть резерв по времени.\n'
            || E'Проблема в том, что запланированные работы имеют слишком низкую стоимость '
            || E'и не покрывают затраты на содержание звена.\n'
            || E'Звено загружено дешёвым фронтом.\n\n'
            || E'РЕКОМЕНДАЦИЯ:\n'
            || E'• добавить более денежный фронт работ;\n'
            || E'• укрупнить объём;\n'
            || E'• перераспределить часть людей;\n'
            || E'• сократить состав звена;\n'
            || E'• объединить со смежным фронтом.'

        WHEN 'ECONOMIC_FAIL' THEN
            E'🔴 КРИТИЧЕСКОЕ ОТКЛОНЕНИЕ — ЭКОНОМИЧЕСКИЙ ПРОВАЛ ПЛАНА\n'
            || E'Плановый EV не покрывает стоимость звена. Нужно пересобрать состав работ или состав звена.'

        WHEN 'LABOR_CAPACITY_FAIL' THEN
            E'🔴 КРИТИЧЕСКОЕ ОТКЛОНЕНИЕ — НЕХВАТКА МОЩНОСТИ ЗВЕНА\n\n'
            || 'Звено: ' || e.crew_code || E'\n\n'
            || E'МОЩНОСТЬ ЗВЕНА:\n'
            || 'Доступно: ' || to_char(ROUND(e.crew_available_hours)::bigint, 'FM999999990') || E' чел-ч\n'
            || 'Требуется: ' || to_char(ROUND(e.required_hours_management)::bigint, 'FM999999990')
            || E' чел-ч по базовому плану\n'
            || 'Риск-план P80: ' || to_char(ROUND(e.required_hours_risk_p80)::bigint, 'FM999999990')
            || E' чел-ч\n'
            || 'Дефицит часов: '
            || to_char(ROUND(ABS(LEAST(e.hours_gap_management, 0)))::bigint, 'FM999999990') || E' чел-ч\n\n'
            || E'ВЫВОД:\n'
            || E'Проблема в нехватке мощности звена — план не помещается в доступные direct hours.\n\n'
            || E'РЕКОМЕНДАЦИЯ:\n'
            || E'• сократить объём плана;\n'
            || E'• добавить людей / часы;\n'
            || E'• перенести работы на другое звено или месяц.'

        WHEN 'OVER_REMAINING_SCOPE' THEN
            E'🔴 КРИТИЧЕСКОЕ ОТКЛОНЕНИЕ — ПЛАН ПРЕВЫШАЕТ ОСТАТОК\n'
            || E'Часть строк плана превышает remaining scope по BOQ.\n'
            || COALESCE(E'\nКоды: ' || e.over_remaining_codes, '')

        WHEN 'NO_LABOR_PLAN' THEN
            E'🟡 ВНИМАНИЕ — НЕТ LABOR PLAN\n'
            || E'Для звена не заданы direct hours / стоимость в monthly_labor_summary.\n'
            || E'Без labor plan невозможна экономическая и ёмкостная диагностика.'

        WHEN 'PRODUCTIVITY_UNSTABLE' THEN
            E'🟠 РИСК — НЕСТАБИЛЬНАЯ ПРОИЗВОДИТЕЛЬНОСТЬ\n'
            || E'Для части кодов производительность нестабильна. Для риск-плана использовать P80.'

        WHEN 'NO_HISTORY_NORM' THEN
            E'🟡 ВНИМАНИЕ — НЕТ ИСТОРИЧЕСКОЙ НОРМЫ\n'
            || E'По части кодов нет статистики. Требуется ручная норма или аналог.'

        ELSE
            E'🟢 План звена без критических диагностических отклонений.'
    END AS detailed_explanation

FROM explained e;

COMMENT ON VIEW public.plan_diagnostics IS
    'E.3.1 Plan Diagnostics Engine v2 — crew/month diagnostics and Russian AI explanations from draft_month_plan';
