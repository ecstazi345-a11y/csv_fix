-- =============================================================================
-- Monthly Plan Lines v2 — identity columns (Release A)
-- =============================================================================
-- Tables:  public.monthly_plan_lines_v2
--          public.monthly_plan_draft_lines
-- Purpose: prepare nullable schema for future idempotent save/restore.
--          Does NOT change application behaviour by itself.
--
-- Deploy:  Supabase SQL Editor (manual, after explicit approval)
-- Safe:    ADD COLUMN IF NOT EXISTS only — no UNIQUE, no backfill, no DELETE.
--
-- Notes:
--   client_line_uid     — stable line identity UI → draft → plan
--   idempotency_key     — one save-operation id (retry protection)
--   parent_plan_line_id — ADDITIONAL volume link to original commitment
--   line_origin         — INITIAL / ADDITIONAL / CORRECTION
--   UNIQUE indexes will be added only after backfill + duplicate cleanup
-- =============================================================================

-- ---------------------------------------------------------------------------
-- monthly_plan_lines_v2
-- ---------------------------------------------------------------------------
alter table public.monthly_plan_lines_v2
    add column if not exists client_line_uid uuid,
    add column if not exists idempotency_key uuid,
    add column if not exists parent_plan_line_id uuid,
    add column if not exists line_origin text not null default 'INITIAL';

comment on column public.monthly_plan_lines_v2.client_line_uid is
    'Stable line identity from first UI Add through draft autosave/restore and plan save. Not regenerated on restore.';

comment on column public.monthly_plan_lines_v2.idempotency_key is
    'Identifies one save write operation; protects against retry/timeout duplicate INSERT.';

comment on column public.monthly_plan_lines_v2.parent_plan_line_id is
    'For ADDITIONAL lines: references the original SENT commitment plan_line_id.';

comment on column public.monthly_plan_lines_v2.line_origin is
    'INITIAL = first commitment; ADDITIONAL = extra volume after SENT; CORRECTION = reserved.';

alter table public.monthly_plan_lines_v2
    drop constraint if exists monthly_plan_lines_v2_line_origin_check;

alter table public.monthly_plan_lines_v2
    add constraint monthly_plan_lines_v2_line_origin_check
    check (line_origin in ('INITIAL', 'ADDITIONAL', 'CORRECTION'));

alter table public.monthly_plan_lines_v2
    drop constraint if exists monthly_plan_lines_v2_parent_plan_line_id_fkey;

alter table public.monthly_plan_lines_v2
    add constraint monthly_plan_lines_v2_parent_plan_line_id_fkey
    foreign key (parent_plan_line_id)
    references public.monthly_plan_lines_v2 (plan_line_id)
    on delete restrict;

-- ---------------------------------------------------------------------------
-- monthly_plan_draft_lines
-- ---------------------------------------------------------------------------
alter table public.monthly_plan_draft_lines
    add column if not exists client_line_uid uuid,
    add column if not exists plan_line_id uuid,
    add column if not exists parent_plan_line_id uuid,
    add column if not exists line_origin text not null default 'INITIAL';

comment on column public.monthly_plan_draft_lines.client_line_uid is
    'Stable line identity mirrored from session; must survive autosave and restore.';

comment on column public.monthly_plan_draft_lines.plan_line_id is
    'Optional link to monthly_plan_lines_v2.plan_line_id after save; nullable until linked.';

comment on column public.monthly_plan_draft_lines.parent_plan_line_id is
    'Draft-side parent link for ADDITIONAL portion (same semantics as plan lines).';

comment on column public.monthly_plan_draft_lines.line_origin is
    'INITIAL / ADDITIONAL / CORRECTION — same vocabulary as monthly_plan_lines_v2.';

alter table public.monthly_plan_draft_lines
    drop constraint if exists monthly_plan_draft_lines_line_origin_check;

alter table public.monthly_plan_draft_lines
    add constraint monthly_plan_draft_lines_line_origin_check
    check (line_origin in ('INITIAL', 'ADDITIONAL', 'CORRECTION'));

-- Release A intentionally omits:
--   UNIQUE (client_line_uid)
--   UNIQUE (idempotency_key)
--   NOT NULL on client_line_uid
--   backfill / UPDATE of existing business data
--   FK from draft.plan_line_id / draft.parent_plan_line_id
