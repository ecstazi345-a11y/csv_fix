-- =============================================================================
-- OBSOLETE — DO NOT EXECUTE
-- Replaced by business audit: most Group B rows were M3 technical tails.
-- Active cleanup script: sql/legacy_draft_cleanup_keep_b35_202607.sql
-- Marked obsolete: 2026-07-28
-- =============================================================================

-- =============================================================================
-- LEGACY GROUP B MIGRATION — draft identity backfill
-- Scope: monthly_plan_draft_lines ONLY
-- Does NOT touch: monthly_plan_lines_v2, Group A, Group D, B8 duplicate
-- Expected UPDATE count: 10
-- =============================================================================
-- B8/B9 precheck result:
--   exact duplicate on all business fields
--   differing only: line_id, planned_at
--   created_at identical -> keeper = min(line_id) = B9
--   keeper: 16486e86-d338-401c-9daf-ee7d7d17f933 (B9)
--   skip:   a72017cc-e9fd-4aad-ab1a-75c349d47f85 (B8) -> LEGACY_DRAFT_DUPLICATES
-- =============================================================================

begin;

-- -----------------------------------------------------------------------------
-- 0) Safety: refuse if any MIGRATE_B row already has client_line_uid
-- -----------------------------------------------------------------------------
do $$
declare
  already int;
begin
  select count(*) into already
  from public.monthly_plan_draft_lines
  where line_id in (
    '4280dbdc-aebb-4256-a731-098065edf19c', -- B1
    '49362e64-d137-4f95-b6eb-669ac68a45af', -- B5
    '5677541c-1e70-4431-9093-0d374ed58bf0', -- B6
    'f1bf6b49-e80a-4f84-9f55-614428106cd6', -- B7
    '16486e86-d338-401c-9daf-ee7d7d17f933', -- B9 keeper
    'c65de2cc-8fd7-466e-8494-c98c0c126a64', -- B10
    '5136b0f9-d585-4e84-b849-56b6c3bbcb52', -- B11
    'b148f69b-5375-4ccc-825c-5c0589b4300a', -- B33
    '366ba576-2b4f-43c0-9708-d24bf458c5d7', -- B34
    'c90c5f21-e9e5-45c8-93e2-940dbc4fe862'  -- B35
  )
  and client_line_uid is not null;

  if already <> 0 then
    raise exception 'ABORT: % MIGRATE_B row(s) already have client_line_uid', already;
  end if;
end $$;

-- -----------------------------------------------------------------------------
-- 1) Backup table (full row snapshot + migration metadata)
-- -----------------------------------------------------------------------------
create table if not exists public.monthly_plan_draft_lines_backup_legacy_202607 (
  backup_id uuid primary key default gen_random_uuid(),
  migration_batch_id uuid not null,
  migration_reason text not null,
  backed_up_at timestamptz not null default now(),
  source_draft_id uuid,
  source_line_id uuid not null,
  row_role text not null check (row_role in ('MIGRATE_B', 'LEGACY_DRAFT_DUPLICATE')),
  row_snapshot jsonb not null
);

create index if not exists monthly_plan_draft_lines_backup_legacy_202607_batch_idx
  on public.monthly_plan_draft_lines_backup_legacy_202607 (migration_batch_id);

-- Use a fixed batch id for this run (also recorded in local precheck JSON)
do $$
declare
  v_batch uuid := '6409a57e-fa8c-41ff-8edc-96e495caf348';
  v_reason text := 'legacy_group_b_client_line_uid_backfill';
  v_inserted int;
begin
  -- avoid double-backup of same batch
  if exists (
    select 1
    from public.monthly_plan_draft_lines_backup_legacy_202607
    where migration_batch_id = v_batch
  ) then
    raise exception 'ABORT: backup for migration_batch_id % already exists', v_batch;
  end if;

  insert into public.monthly_plan_draft_lines_backup_legacy_202607 (
    migration_batch_id,
    migration_reason,
    backed_up_at,
    source_draft_id,
    source_line_id,
    row_role,
    row_snapshot
  )
  select
    v_batch,
    v_reason,
    now(),
    d.draft_id,
    d.line_id,
    case
      when d.line_id = 'a72017cc-e9fd-4aad-ab1a-75c349d47f85' then 'LEGACY_DRAFT_DUPLICATE'
      else 'MIGRATE_B'
    end,
    to_jsonb(d)
  from public.monthly_plan_draft_lines d
  where d.line_id in (
    '4280dbdc-aebb-4256-a731-098065edf19c', -- B1
    '49362e64-d137-4f95-b6eb-669ac68a45af', -- B5
    '5677541c-1e70-4431-9093-0d374ed58bf0', -- B6
    'f1bf6b49-e80a-4f84-9f55-614428106cd6', -- B7
    '16486e86-d338-401c-9daf-ee7d7d17f933', -- B9 keeper
    'c65de2cc-8fd7-466e-8494-c98c0c126a64', -- B10
    '5136b0f9-d585-4e84-b849-56b6c3bbcb52', -- B11
    'b148f69b-5375-4ccc-825c-5c0589b4300a', -- B33
    '366ba576-2b4f-43c0-9708-d24bf458c5d7', -- B34
    'c90c5f21-e9e5-45c8-93e2-940dbc4fe862', -- B35
    'a72017cc-e9fd-4aad-ab1a-75c349d47f85'  -- B8 duplicate (backup only, no UPDATE)
  );

  get diagnostics v_inserted = row_count;
  if v_inserted <> 11 then
    raise exception 'ABORT: backup expected 11 rows (10 MIGRATE_B + 1 duplicate), got %', v_inserted;
  end if;
end $$;

-- -----------------------------------------------------------------------------
-- 2) Targeted UPDATE — only MIGRATE_B PKs, only where client_line_uid IS NULL
-- -----------------------------------------------------------------------------
with updated as (
  update public.monthly_plan_draft_lines d
  set
    client_line_uid = gen_random_uuid(),
    line_origin = 'INITIAL',
    parent_plan_line_id = null,
    plan_line_id = null
  where d.line_id in (
    '4280dbdc-aebb-4256-a731-098065edf19c', -- B1
    '49362e64-d137-4f95-b6eb-669ac68a45af', -- B5
    '5677541c-1e70-4431-9093-0d374ed58bf0', -- B6
    'f1bf6b49-e80a-4f84-9f55-614428106cd6', -- B7
    '16486e86-d338-401c-9daf-ee7d7d17f933', -- B9 keeper
    'c65de2cc-8fd7-466e-8494-c98c0c126a64', -- B10
    '5136b0f9-d585-4e84-b849-56b6c3bbcb52', -- B11
    'b148f69b-5375-4ccc-825c-5c0589b4300a', -- B33
    '366ba576-2b4f-43c0-9708-d24bf458c5d7', -- B34
    'c90c5f21-e9e5-45c8-93e2-940dbc4fe862'  -- B35
  )
  and d.client_line_uid is null
  returning d.line_id, d.client_line_uid
)
select
  case
    when (select count(*) from updated) = 10 then 'OK: updated 10'
    else format('ABORT: expected 10 updates, got %s', (select count(*) from updated))
  end as update_check;

-- Hard stop if count mismatch
do $$
declare
  v_cnt int;
  v_uid_null int;
  v_uid_dup int;
  v_bad_origin int;
  v_bad_parent int;
  v_bad_plan int;
  v_bad_status int;
  v_dup_changed int;
  v_d_changed int;
  v_a_changed int;
begin
  select count(*) into v_cnt
  from public.monthly_plan_draft_lines
  where line_id in (
    '4280dbdc-aebb-4256-a731-098065edf19c',
    '49362e64-d137-4f95-b6eb-669ac68a45af',
    '5677541c-1e70-4431-9093-0d374ed58bf0',
    'f1bf6b49-e80a-4f84-9f55-614428106cd6',
    '16486e86-d338-401c-9daf-ee7d7d17f933',
    'c65de2cc-8fd7-466e-8494-c98c0c126a64',
    '5136b0f9-d585-4e84-b849-56b6c3bbcb52',
    'b148f69b-5375-4ccc-825c-5c0589b4300a',
    '366ba576-2b4f-43c0-9708-d24bf458c5d7',
    'c90c5f21-e9e5-45c8-93e2-940dbc4fe862'
  )
  and client_line_uid is not null;

  if v_cnt <> 10 then
    raise exception 'ROLLBACK trigger: expected 10 rows with client_line_uid, got %', v_cnt;
  end if;

  select count(*) into v_uid_null
  from public.monthly_plan_draft_lines
  where line_id in (
    '4280dbdc-aebb-4256-a731-098065edf19c',
    '49362e64-d137-4f95-b6eb-669ac68a45af',
    '5677541c-1e70-4431-9093-0d374ed58bf0',
    'f1bf6b49-e80a-4f84-9f55-614428106cd6',
    '16486e86-d338-401c-9daf-ee7d7d17f933',
    'c65de2cc-8fd7-466e-8494-c98c0c126a64',
    '5136b0f9-d585-4e84-b849-56b6c3bbcb52',
    'b148f69b-5375-4ccc-825c-5c0589b4300a',
    '366ba576-2b4f-43c0-9708-d24bf458c5d7',
    'c90c5f21-e9e5-45c8-93e2-940dbc4fe862'
  )
  and (
    client_line_uid is null
    or client_line_uid::text !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
  );

  if v_uid_null <> 0 then
    raise exception 'ROLLBACK trigger: invalid/null client_line_uid on % rows', v_uid_null;
  end if;

  select count(*) into v_uid_dup
  from (
    select client_line_uid
    from public.monthly_plan_draft_lines
    where line_id in (
      '4280dbdc-aebb-4256-a731-098065edf19c',
      '49362e64-d137-4f95-b6eb-669ac68a45af',
      '5677541c-1e70-4431-9093-0d374ed58bf0',
      'f1bf6b49-e80a-4f84-9f55-614428106cd6',
      '16486e86-d338-401c-9daf-ee7d7d17f933',
      'c65de2cc-8fd7-466e-8494-c98c0c126a64',
      '5136b0f9-d585-4e84-b849-56b6c3bbcb52',
      'b148f69b-5375-4ccc-825c-5c0589b4300a',
      '366ba576-2b4f-43c0-9708-d24bf458c5d7',
      'c90c5f21-e9e5-45c8-93e2-940dbc4fe862'
    )
    group by client_line_uid
    having count(*) > 1
  ) t;

  if v_uid_dup <> 0 then
    raise exception 'ROLLBACK trigger: duplicate client_line_uid values found';
  end if;

  select count(*) into v_bad_origin
  from public.monthly_plan_draft_lines
  where line_id in (
    '4280dbdc-aebb-4256-a731-098065edf19c',
    '49362e64-d137-4f95-b6eb-669ac68a45af',
    '5677541c-1e70-4431-9093-0d374ed58bf0',
    'f1bf6b49-e80a-4f84-9f55-614428106cd6',
    '16486e86-d338-401c-9daf-ee7d7d17f933',
    'c65de2cc-8fd7-466e-8494-c98c0c126a64',
    '5136b0f9-d585-4e84-b849-56b6c3bbcb52',
    'b148f69b-5375-4ccc-825c-5c0589b4300a',
    '366ba576-2b4f-43c0-9708-d24bf458c5d7',
    'c90c5f21-e9e5-45c8-93e2-940dbc4fe862'
  )
  and coalesce(line_origin, '') <> 'INITIAL';

  select count(*) into v_bad_parent
  from public.monthly_plan_draft_lines
  where line_id in (
    '4280dbdc-aebb-4256-a731-098065edf19c',
    '49362e64-d137-4f95-b6eb-669ac68a45af',
    '5677541c-1e70-4431-9093-0d374ed58bf0',
    'f1bf6b49-e80a-4f84-9f55-614428106cd6',
    '16486e86-d338-401c-9daf-ee7d7d17f933',
    'c65de2cc-8fd7-466e-8494-c98c0c126a64',
    '5136b0f9-d585-4e84-b849-56b6c3bbcb52',
    'b148f69b-5375-4ccc-825c-5c0589b4300a',
    '366ba576-2b4f-43c0-9708-d24bf458c5d7',
    'c90c5f21-e9e5-45c8-93e2-940dbc4fe862'
  )
  and parent_plan_line_id is not null;

  select count(*) into v_bad_plan
  from public.monthly_plan_draft_lines
  where line_id in (
    '4280dbdc-aebb-4256-a731-098065edf19c',
    '49362e64-d137-4f95-b6eb-669ac68a45af',
    '5677541c-1e70-4431-9093-0d374ed58bf0',
    'f1bf6b49-e80a-4f84-9f55-614428106cd6',
    '16486e86-d338-401c-9daf-ee7d7d17f933',
    'c65de2cc-8fd7-466e-8494-c98c0c126a64',
    '5136b0f9-d585-4e84-b849-56b6c3bbcb52',
    'b148f69b-5375-4ccc-825c-5c0589b4300a',
    '366ba576-2b4f-43c0-9708-d24bf458c5d7',
    'c90c5f21-e9e5-45c8-93e2-940dbc4fe862'
  )
  and plan_line_id is not null;

  select count(*) into v_bad_status
  from public.monthly_plan_draft_lines
  where line_id in (
    '4280dbdc-aebb-4256-a731-098065edf19c',
    '49362e64-d137-4f95-b6eb-669ac68a45af',
    '5677541c-1e70-4431-9093-0d374ed58bf0',
    'f1bf6b49-e80a-4f84-9f55-614428106cd6',
    '16486e86-d338-401c-9daf-ee7d7d17f933',
    'c65de2cc-8fd7-466e-8494-c98c0c126a64',
    '5136b0f9-d585-4e84-b849-56b6c3bbcb52',
    'b148f69b-5375-4ccc-825c-5c0589b4300a',
    '366ba576-2b4f-43c0-9708-d24bf458c5d7',
    'c90c5f21-e9e5-45c8-93e2-940dbc4fe862'
  )
  and coalesce(line_status, '') <> 'DRAFT';

  if v_bad_origin <> 0 or v_bad_parent <> 0 or v_bad_plan <> 0 or v_bad_status <> 0 then
    raise exception
      'ROLLBACK trigger: identity/status checks failed (origin=%, parent=%, plan=%, status=%)',
      v_bad_origin, v_bad_parent, v_bad_plan, v_bad_status;
  end if;

  -- B8 duplicate must remain without client_line_uid
  select count(*) into v_dup_changed
  from public.monthly_plan_draft_lines
  where line_id = 'a72017cc-e9fd-4aad-ab1a-75c349d47f85'
    and client_line_uid is not null;

  if v_dup_changed <> 0 then
    raise exception 'ROLLBACK trigger: B8 duplicate was modified';
  end if;

  -- Group D must remain without client_line_uid
  select count(*) into v_d_changed
  from public.monthly_plan_draft_lines
  where line_id in (
    '9c548492-628a-4179-a644-62ac420b65a3',
    'ad554cc7-eb4d-4c39-b56d-ef78235e0c7c'
  )
  and client_line_uid is not null;

  if v_d_changed <> 0 then
    raise exception 'ROLLBACK trigger: Group D was modified';
  end if;

  -- Group A must remain without client_line_uid (legacy state)
  select count(*) into v_a_changed
  from public.monthly_plan_draft_lines
  where line_id in (
    '481363ed-955f-46ff-8969-475c1c3deecc',
    '8898f66f-7f55-4ae4-b146-57a1ac998f6a',
    '347c03a2-08ad-4f42-b50f-8181de569b86',
    '1c82d05b-5d7b-4783-b110-a9bfce6eb62f',
    '560015f8-dac8-4722-a155-a684ae5fe484',
    '4d06523c-b440-417e-b3fc-86ed0a77170c',
    '4df3ec69-fb65-4d5a-a3c4-b8a4d5c2561c',
    'eda4baa9-786b-409e-a89c-ba9fdb495dd9',
    '668f12ff-4983-49b9-9bb0-9528079fbf43',
    '6e2db03b-1a2f-45a6-83ee-46247db1affa',
    '07f40fa8-5ac8-4c22-a19f-1d37ee7c6448',
    'ac775cb4-70f8-4d3a-94cb-f0c0abe55c4c',
    '9854d163-4a79-45d8-ac79-eb50ab81cc7a',
    '767909e7-e358-4cba-b7b0-b6723b715b30',
    '4d98829f-b027-48a0-a858-01a634eaba5c',
    '46f439bb-a829-4d4f-be2e-af630be55cc9',
    '8c17d045-30bf-4930-98e9-b9189952fbf0',
    'f75774ee-b54d-4213-a07e-0b98c61155d5',
    '5b0496b7-126d-412f-b052-44e2751648a2',
    'f856d039-5bc3-4f1d-92dd-6d11eb1b1c06',
    '0d0bf5c0-a5c1-4c9a-bdd2-ffbe655c3568',
    '1eb63335-91e0-4b5d-a933-cb42046a62a5'
  )
  and client_line_uid is not null;

  if v_a_changed <> 0 then
    raise exception 'ROLLBACK trigger: Group A was modified';
  end if;
end $$;

-- Business-field integrity vs backup snapshot for MIGRATE_B
do $$
declare
  v_batch uuid := '6409a57e-fa8c-41ff-8edc-96e495caf348';
  v_mismatch int;
begin
  select count(*) into v_mismatch
  from public.monthly_plan_draft_lines_backup_legacy_202607 b
  join public.monthly_plan_draft_lines d
    on d.line_id = b.source_line_id
  where b.migration_batch_id = v_batch
    and b.row_role = 'MIGRATE_B'
    and (
         d.boq_code is distinct from (b.row_snapshot->>'boq_code')
      or d.planned_qty::text is distinct from (b.row_snapshot->>'planned_qty')
      or d.crew_id is distinct from (b.row_snapshot->>'crew_id')
      or d.project_code is distinct from (b.row_snapshot->>'project_code')
      or d.month_key is distinct from (b.row_snapshot->>'month_key')
      or d.facility_building is distinct from (b.row_snapshot->>'facility_building')
      or d.construction_discipline is distinct from (b.row_snapshot->>'construction_discipline')
      or d.plan_value::text is distinct from (b.row_snapshot->>'plan_value')
      or d.required_hours::text is distinct from (b.row_snapshot->>'required_hours')
      or d.labor_cost::text is distinct from (b.row_snapshot->>'labor_cost')
      or d.boq_name is distinct from (b.row_snapshot->>'boq_name')
      or d.unit_of_measure is distinct from (b.row_snapshot->>'unit_of_measure')
      or d.unit_price::text is distinct from (b.row_snapshot->>'unit_price')
      or d.line_status is distinct from (b.row_snapshot->>'line_status')
    );

  if v_mismatch <> 0 then
    raise exception 'ROLLBACK trigger: business fields changed on % MIGRATE_B rows', v_mismatch;
  end if;
end $$;

-- If all checks passed:
commit;

-- =============================================================================
-- Optional post-commit verification SELECTs (run after COMMIT):
-- =============================================================================
-- select line_id, client_line_uid, line_origin, parent_plan_line_id, plan_line_id, line_status
-- from public.monthly_plan_draft_lines
-- where line_id in (...10 migrate ids...);
--
-- select line_id, client_line_uid
-- from public.monthly_plan_draft_lines
-- where line_id = 'a72017cc-e9fd-4aad-ab1a-75c349d47f85'; -- B8 must be NULL uid
--
-- select count(*) from public.monthly_plan_lines_v2
-- where project_code = 'PRJ_001_БХК' and month_key = 'июль-2026'; -- expect 124
