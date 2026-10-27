-- Additive only: expose Airtable Elevation_Mark on Daily Progress raw fact.
-- Safe: ADD COLUMN IF NOT EXISTS. No DROP / DELETE / TRUNCATE / rewrite.
--
-- Target table: public.daily_progress_raw
--   (Airtable sync upsert target: daily_progress_sync_upsert.py)
--
-- Apply BEFORE the next daily_progress sync that includes elevation_mark.
--
-- VIEW BLOCKER (do not auto-rewrite here):
--   public.daily_progress_active currently does NOT expose elevation_mark.
--   Live definition could not be read safely via PostgREST (no pg_get_viewdef /
--   information_schema access). Do NOT CREATE OR REPLACE the view until the
--   exact current definition is obtained from the DB admin / SQL editor.
--   After this ALTER + sync, elevation_mark will land in daily_progress_raw.
--   PTO export reads daily_progress_active — Elevation_Mark stays empty until
--   the active view/table is additively updated to pass elevation_mark through
--   while preserving existing filters (is_deleted = false) and column set
--   (currently all raw columns except week_key).

ALTER TABLE public.daily_progress_raw
    ADD COLUMN IF NOT EXISTS elevation_mark text;

COMMENT ON COLUMN public.daily_progress_raw.elevation_mark IS
    'Airtable Elevation_Mark. Text: may contain engineering notation/signs.';
