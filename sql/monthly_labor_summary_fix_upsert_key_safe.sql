-- monthly_labor_summary: безопасная смена upsert key
-- assignment_period_id (убрать unique) → airtable_record_id (unique)
--
-- Данные НЕ удаляются.
-- Если есть дубли по airtable_record_id — сначала выполните:
--   sql/monthly_labor_summary_cleanup_duplicates.sql
--
-- После этого скрипта запустите:
--   python monthly_labor_summary_sync_upsert.py

-- ============================================================
-- 1. ДИАГНОСТИКА (только чтение)
-- ============================================================

-- 1a. Constraints на monthly_labor_summary
SELECT
    c.conname AS constraint_name,
    CASE c.contype
        WHEN 'p' THEN 'PRIMARY KEY'
        WHEN 'u' THEN 'UNIQUE'
        WHEN 'f' THEN 'FOREIGN KEY'
        WHEN 'c' THEN 'CHECK'
        ELSE c.contype::text
    END AS constraint_type,
    pg_get_constraintdef(c.oid, true) AS definition
FROM pg_constraint c
JOIN pg_class t ON c.conrelid = t.oid
JOIN pg_namespace n ON t.relnamespace = n.oid
WHERE n.nspname = 'public'
  AND t.relname = 'monthly_labor_summary'
  AND (
      pg_get_constraintdef(c.oid) ILIKE '%assignment_period_id%'
      OR pg_get_constraintdef(c.oid) ILIKE '%airtable_record_id%'
  )
ORDER BY c.conname;

-- 1b. Indexes на monthly_labor_summary
SELECT
    i.relname AS index_name,
    ix.indisunique AS is_unique,
    ix.indisprimary AS is_primary,
    pg_get_indexdef(i.oid) AS index_definition
FROM pg_class t
JOIN pg_namespace n ON t.relnamespace = n.oid
JOIN pg_index ix ON t.oid = ix.indrelid
JOIN pg_class i ON ix.indexrelid = i.oid
WHERE n.nspname = 'public'
  AND t.relname = 'monthly_labor_summary'
  AND (
      pg_get_indexdef(i.oid) ILIKE '%assignment_period_id%'
      OR pg_get_indexdef(i.oid) ILIKE '%airtable_record_id%'
  )
ORDER BY i.relname;

-- 1c. Дубли по airtable_record_id (должно быть 0 перед NOT NULL / unique)
SELECT
    airtable_record_id,
    count(*) AS row_count
FROM public.monthly_labor_summary
WHERE airtable_record_id IS NOT NULL
GROUP BY airtable_record_id
HAVING count(*) > 1
ORDER BY row_count DESC, airtable_record_id;

-- 1d. Строки без airtable_record_id (если есть — NOT NULL пропустим)
SELECT count(*) AS rows_without_airtable_record_id
FROM public.monthly_labor_summary
WHERE airtable_record_id IS NULL;


-- ============================================================
-- 2. ИСПРАВЛЕНИЕ (без DELETE)
-- ============================================================

BEGIN;

-- 2a. Убрать known unique constraint/index по assignment_period_id
ALTER TABLE public.monthly_labor_summary
    DROP CONSTRAINT IF EXISTS monthly_labor_summary_assignment_period_id_key;

DROP INDEX IF EXISTS public.monthly_labor_summary_assignment_period_id_key;
DROP INDEX IF EXISTS public.idx_monthly_labor_summary_assignment_period_id;

-- 2b. Убрать любые оставшиеся UNIQUE constraints только на assignment_period_id
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT c.conname
        FROM pg_constraint c
        JOIN pg_class t ON c.conrelid = t.oid
        JOIN pg_namespace n ON t.relnamespace = n.oid
        WHERE n.nspname = 'public'
          AND t.relname = 'monthly_labor_summary'
          AND c.contype = 'u'
          AND pg_get_constraintdef(c.oid) ILIKE '%assignment_period_id%'
    LOOP
        EXECUTE format(
            'ALTER TABLE public.monthly_labor_summary DROP CONSTRAINT IF EXISTS %I',
            r.conname
        );
        RAISE NOTICE 'Dropped UNIQUE constraint: %', r.conname;
    END LOOP;
END $$;

-- 2c. Убрать любые оставшиеся UNIQUE indexes только на assignment_period_id
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT i.relname AS index_name
        FROM pg_class t
        JOIN pg_namespace n ON t.relnamespace = n.oid
        JOIN pg_index ix ON t.oid = ix.indrelid
        JOIN pg_class i ON ix.indexrelid = i.oid
        WHERE n.nspname = 'public'
          AND t.relname = 'monthly_labor_summary'
          AND ix.indisunique
          AND NOT ix.indisprimary
          AND pg_get_indexdef(i.oid) ILIKE '%assignment_period_id%'
    LOOP
        EXECUTE format('DROP INDEX IF EXISTS public.%I', r.index_name);
        RAISE NOTICE 'Dropped UNIQUE index: %', r.index_name;
    END LOOP;
END $$;

COMMENT ON COLUMN public.monthly_labor_summary.assignment_period_id IS
    'Справочный ключ периода из Airtable; не использовать как upsert key';

-- 2d. Unique index по airtable_record_id (upsert key для sync)
CREATE UNIQUE INDEX IF NOT EXISTS monthly_labor_summary_airtable_record_id_key
    ON public.monthly_labor_summary (airtable_record_id);

COMMENT ON INDEX public.monthly_labor_summary_airtable_record_id_key IS
    'Upsert key для monthly_labor_summary_sync_upsert.py';

-- 2e. NOT NULL только если нет пустых airtable_record_id
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.monthly_labor_summary
        WHERE airtable_record_id IS NULL
    ) THEN
        RAISE NOTICE
            'Skipped NOT NULL on airtable_record_id: есть строки с NULL';
    ELSE
        ALTER TABLE public.monthly_labor_summary
            ALTER COLUMN airtable_record_id SET NOT NULL;
        RAISE NOTICE 'Set NOT NULL on airtable_record_id';
    END IF;
END $$;

COMMIT;


-- ============================================================
-- 3. ПРОВЕРКА ПОСЛЕ ИСПРАВЛЕНИЯ
-- ============================================================

-- 3a. Constraints / indexes (повтор)
SELECT
    c.conname AS constraint_name,
    CASE c.contype
        WHEN 'u' THEN 'UNIQUE'
        WHEN 'p' THEN 'PRIMARY KEY'
        ELSE c.contype::text
    END AS constraint_type,
    pg_get_constraintdef(c.oid, true) AS definition
FROM pg_constraint c
JOIN pg_class t ON c.conrelid = t.oid
JOIN pg_namespace n ON t.relnamespace = n.oid
WHERE n.nspname = 'public'
  AND t.relname = 'monthly_labor_summary'
  AND (
      pg_get_constraintdef(c.oid) ILIKE '%assignment_period_id%'
      OR pg_get_constraintdef(c.oid) ILIKE '%airtable_record_id%'
  )
ORDER BY c.conname;

SELECT
    i.relname AS index_name,
    ix.indisunique AS is_unique,
    pg_get_indexdef(i.oid) AS index_definition
FROM pg_class t
JOIN pg_namespace n ON t.relnamespace = n.oid
JOIN pg_index ix ON t.oid = ix.indrelid
JOIN pg_class i ON ix.indexrelid = i.oid
WHERE n.nspname = 'public'
  AND t.relname = 'monthly_labor_summary'
  AND (
      pg_get_indexdef(i.oid) ILIKE '%assignment_period_id%'
      OR pg_get_indexdef(i.oid) ILIKE '%airtable_record_id%'
  )
ORDER BY i.relname;

-- 3b. Ожидаем:
--   - нет UNIQUE на assignment_period_id
--   - есть UNIQUE index monthly_labor_summary_airtable_record_id_key
