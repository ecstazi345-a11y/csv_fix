-- Удаление исторических дублей monthly_labor_summary
-- Правило: один airtable_record_id → одна строка (самая свежая по last_synced_at)
-- Выполнить ДО sql/monthly_labor_summary_fix_key.sql

DELETE FROM public.monthly_labor_summary
WHERE id IN (
    SELECT id
    FROM (
        SELECT
            id,
            row_number() OVER (
                PARTITION BY airtable_record_id
                ORDER BY last_synced_at DESC NULLS LAST, id DESC
            ) AS rn
        FROM public.monthly_labor_summary
        WHERE airtable_record_id IS NOT NULL
    ) ranked
    WHERE rn > 1
);

-- Проверка: не должно остаться дублей по airtable_record_id
-- SELECT airtable_record_id, count(*) FROM monthly_labor_summary
-- GROUP BY airtable_record_id HAVING count(*) > 1;
