-- monthly_labor_summary: upsert key → airtable_record_id
-- ВАЖНО: сначала выполнить sql/monthly_labor_summary_cleanup_duplicates.sql

-- 1. Убрать unique на assignment_period_id (если был создан ранее)
ALTER TABLE public.monthly_labor_summary
    DROP CONSTRAINT IF EXISTS monthly_labor_summary_assignment_period_id_key;

DROP INDEX IF EXISTS public.monthly_labor_summary_assignment_period_id_key;
DROP INDEX IF EXISTS public.idx_monthly_labor_summary_assignment_period_id;

-- assignment_period_id остаётся справочным полем (не unique)
COMMENT ON COLUMN public.monthly_labor_summary.assignment_period_id IS
    'Справочный ключ периода из Airtable; не использовать как upsert key';

-- 2. airtable_record_id обязателен и уникален
ALTER TABLE public.monthly_labor_summary
    ALTER COLUMN airtable_record_id SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS monthly_labor_summary_airtable_record_id_key
    ON public.monthly_labor_summary (airtable_record_id);

COMMENT ON INDEX public.monthly_labor_summary_airtable_record_id_key IS
    'Upsert key для monthly_labor_summary_sync_upsert.py';
