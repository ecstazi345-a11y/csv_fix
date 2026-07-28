-- =============================================================================
-- monthly_plan_lines_v2 — client_line_uid hardening
-- =============================================================================
-- Purpose:
--   1) backfill NULL client_line_uid
--   2) add UNIQUE INDEX on client_line_uid
--   3) enable DB-level idempotent upsert from app save-path
--
-- Safe scope:
--   - does NOT delete rows
--   - does NOT change plan_line_id
--   - does NOT create UNIQUE on BOQ / facility / crew / production scope
--
-- Deploy: Supabase SQL Editor after explicit GO
-- =============================================================================

begin;

-- -----------------------------------------------------------------------------
-- 0) Pre-checks
-- -----------------------------------------------------------------------------
do $$
declare
  v_total int;
  v_null_uid int;
  v_dup_groups int;
begin
  select count(*) into v_total
  from public.monthly_plan_lines_v2;

  select count(*) into v_null_uid
  from public.monthly_plan_lines_v2
  where client_line_uid is null;

  select count(*) into v_dup_groups
  from (
    select client_line_uid
    from public.monthly_plan_lines_v2
    where client_line_uid is not null
    group by client_line_uid
    having count(*) > 1
  ) d;

  raise notice 'PRECHECK total_rows=%', v_total;
  raise notice 'PRECHECK null_client_line_uid=%', v_null_uid;
  raise notice 'PRECHECK duplicate_uid_groups=%', v_dup_groups;

  if v_dup_groups <> 0 then
    raise exception
      'ABORT: found % duplicate non-null client_line_uid group(s); resolve before UNIQUE',
      v_dup_groups;
  end if;

  perform set_config('app.uid_hard_total_before', v_total::text, true);
  perform set_config('app.uid_hard_null_before', v_null_uid::text, true);
end $$;

-- -----------------------------------------------------------------------------
-- 1) Backfill NULL client_line_uid only
-- -----------------------------------------------------------------------------
update public.monthly_plan_lines_v2
set client_line_uid = gen_random_uuid()
where client_line_uid is null;

-- -----------------------------------------------------------------------------
-- 2) UNIQUE INDEX on client_line_uid (does not touch plan_line_id PK)
-- -----------------------------------------------------------------------------
create unique index if not exists monthly_plan_lines_v2_client_line_uid_uidx
  on public.monthly_plan_lines_v2 (client_line_uid);

-- -----------------------------------------------------------------------------
-- 3) Post-checks (must match expectations or ROLLBACK)
-- -----------------------------------------------------------------------------
do $$
declare
  v_total int;
  v_null_uid int;
  v_unique_uid int;
  v_dup_groups int;
  v_total_before int;
begin
  select count(*) into v_total
  from public.monthly_plan_lines_v2;

  select count(*) into v_null_uid
  from public.monthly_plan_lines_v2
  where client_line_uid is null;

  select count(distinct client_line_uid) into v_unique_uid
  from public.monthly_plan_lines_v2;

  select count(*) into v_dup_groups
  from (
    select client_line_uid
    from public.monthly_plan_lines_v2
    where client_line_uid is not null
    group by client_line_uid
    having count(*) > 1
  ) d;

  v_total_before := nullif(current_setting('app.uid_hard_total_before', true), '')::int;

  raise notice 'POSTCHECK total_rows=%', v_total;
  raise notice 'POSTCHECK null_client_line_uid=%', v_null_uid;
  raise notice 'POSTCHECK unique_client_line_uid=%', v_unique_uid;
  raise notice 'POSTCHECK duplicate_uid_groups=%', v_dup_groups;

  if v_total_before is distinct from v_total then
    raise exception
      'ABORT: row count changed (before=%, after=%)',
      v_total_before, v_total;
  end if;

  if v_null_uid <> 0 then
    raise exception 'ABORT: null client_line_uid remain: %', v_null_uid;
  end if;

  if v_dup_groups <> 0 then
    raise exception 'ABORT: duplicate client_line_uid groups remain: %', v_dup_groups;
  end if;

  if v_unique_uid <> v_total then
    raise exception
      'ABORT: unique client_line_uid (%) != total rows (%)',
      v_unique_uid, v_total;
  end if;
end $$;

commit;

-- Optional verification SELECTs after COMMIT:
-- select count(*) as rows_total,
--        count(*) filter (where client_line_uid is null) as null_uid,
--        count(distinct client_line_uid) as unique_uid
-- from public.monthly_plan_lines_v2;
--
-- select indexname, indexdef
-- from pg_indexes
-- where tablename = 'monthly_plan_lines_v2'
--   and indexname = 'monthly_plan_lines_v2_client_line_uid_uidx';
