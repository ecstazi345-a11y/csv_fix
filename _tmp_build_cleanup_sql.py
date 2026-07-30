import json, pathlib, uuid

ds=json.loads(pathlib.Path(r'c:\csv_fix\_tmp_legacy_cleanup_delete_set.json').read_text(encoding='utf-8'))
KEEP=ds['keep_line_id']
DRAFT=ds['draft_id']
batch=str(uuid.uuid4())
items=sorted(ds['delete_set'], key=lambda x: x['legacy_index'])
delete_ids=[d['line_id'] for d in items]
assert len(delete_ids)==34 and KEEP not in delete_ids

meta={}
for d in items:
    meta[d['line_id']]={
        'label': d['label'],
        'cleanup_action': 'DELETE_LEGACY_TAIL',
        'audit_classification': f"{d['group']}:{d['label']}:{d['reason'][:160]}",
        'related_plan_line_ids': d.get('related_plan_line_ids') or [],
    }
meta[KEEP]={
    'label': 'B35',
    'cleanup_action': 'KEEP_PENDING_MANUAL_DECISION',
    'audit_classification': 'B:B35:M4/M5 potential independent unfinished work; manual decision pending',
    'related_plan_line_ids': ['9a339a05-be64-4ea9-af5c-fd14a901f7c2'],
}

def sql_list(ids, indent='    '):
    return (',\n'+indent).join(f"'{i}'::uuid" for i in ids)

delete_sql=sql_list(delete_ids)
all_ids=delete_ids+[KEEP]
all_sql=sql_list(all_ids)
meta_json=json.dumps(meta, ensure_ascii=False)

sql=f'''-- =============================================================================
-- LEGACY DRAFT CLEANUP — KEEP B35 ONLY
-- Active draft: {DRAFT}
-- cleanup_batch_id: {batch}
-- DELETE SET: 34 line_id (exact PK list)
-- KEEP / DO NOT DELETE / DO NOT UPDATE: {KEEP} (B35)
-- DOES NOT TOUCH: public.monthly_plan_lines_v2
-- =============================================================================
-- Expected:
--   legacy rows before          = 35
--   backup rows for batch       = 35
--   delete candidates           = 34
--   deleted rows                = 34
--   legacy rows after           = 1 (B35)
--   monthly_plan_lines_v2 count = 124 before and after
-- =============================================================================
-- DO NOT RUN: sql/legacy_group_b_migration_202607.sql (OBSOLETE)
-- =============================================================================

begin;

-- -----------------------------------------------------------------------------
-- 0) Capture plan row count BEFORE any draft changes (must stay 124)
-- -----------------------------------------------------------------------------
do $$
declare
  v_plan_before int;
begin
  select count(*) into v_plan_before
  from public.monthly_plan_lines_v2
  where project_code = 'PRJ_001_БХК'
    and month_key = 'июль-2026';

  if v_plan_before <> 124 then
    raise exception
      'ABORT: monthly_plan_lines_v2 expected 124 rows for PRJ_001_БХК/июль-2026, found %',
      v_plan_before;
  end if;

  perform set_config('app.legacy_cleanup_plan_before', v_plan_before::text, true);
end $$;

-- -----------------------------------------------------------------------------
-- 1) Preflight: draft has exactly 35 target rows; B35 valid; 34 delete candidates
-- -----------------------------------------------------------------------------
do $$
declare
  v_draft_total int;
  v_target_total int;
  v_keep int;
  v_del int;
begin
  select count(*) into v_draft_total
  from public.monthly_plan_draft_lines
  where draft_id = '{DRAFT}'::uuid;

  if v_draft_total <> 35 then
    raise exception 'ABORT: legacy rows before expected 35, found %', v_draft_total;
  end if;

  select count(*) into v_target_total
  from public.monthly_plan_draft_lines
  where line_id in (
    {all_sql}
  );

  if v_target_total <> 35 then
    raise exception 'ABORT: expected all 35 audited line_id present, found %', v_target_total;
  end if;

  select count(*) into v_keep
  from public.monthly_plan_draft_lines
  where line_id = '{KEEP}'::uuid
    and draft_id = '{DRAFT}'::uuid
    and client_line_uid is null
    and plan_line_id is null
    and coalesce(line_status, '') = 'DRAFT'
    and coalesce(boq_code, '') = '1470-01-04-03'
    and planned_qty = 132.6
    and coalesce(crew_id, '') = 'АСИ-10'
    and coalesce(facility_building, '') = '16160-13'
    and coalesce(project_code, '') = 'PRJ_001_БХК'
    and coalesce(month_key, '') = 'июль-2026';

  if v_keep <> 1 then
    raise exception 'ABORT: B35 precheck failed (missing or fields changed)';
  end if;

  select count(*) into v_del
  from public.monthly_plan_draft_lines
  where line_id in (
    {delete_sql}
  );

  if v_del <> 34 then
    raise exception 'ABORT: delete candidates expected 34, found %', v_del;
  end if;
end $$;

-- -----------------------------------------------------------------------------
-- 2) Backup table + insert full snapshots for all 35 rows
-- -----------------------------------------------------------------------------
create table if not exists public.monthly_plan_draft_lines_backup_legacy_202607 (
  backup_id uuid primary key default gen_random_uuid(),
  cleanup_batch_id uuid not null,
  cleanup_reason text not null,
  backed_up_at timestamptz not null default now(),
  cleanup_action text not null
    check (cleanup_action in ('DELETE_LEGACY_TAIL', 'KEEP_PENDING_MANUAL_DECISION')),
  related_plan_line_ids jsonb,
  audit_classification text,
  source_draft_id uuid,
  source_line_id uuid not null,
  row_snapshot jsonb not null
);

create index if not exists monthly_plan_draft_lines_backup_legacy_202607_batch_idx
  on public.monthly_plan_draft_lines_backup_legacy_202607 (cleanup_batch_id);

do $$
declare
  v_batch uuid := '{batch}'::uuid;
  v_reason text := 'legacy_draft_cleanup_keep_b35_only';
  v_meta jsonb := $meta${meta_json}$meta$::jsonb;
  v_inserted int;
begin
  if exists (
    select 1
    from public.monthly_plan_draft_lines_backup_legacy_202607
    where cleanup_batch_id = v_batch
  ) then
    raise exception 'ABORT: cleanup_batch_id % already exists in backup', v_batch;
  end if;

  insert into public.monthly_plan_draft_lines_backup_legacy_202607 (
    cleanup_batch_id,
    cleanup_reason,
    backed_up_at,
    cleanup_action,
    related_plan_line_ids,
    audit_classification,
    source_draft_id,
    source_line_id,
    row_snapshot
  )
  select
    v_batch,
    v_reason,
    now(),
    (v_meta -> d.line_id::text ->> 'cleanup_action'),
    coalesce(v_meta -> d.line_id::text -> 'related_plan_line_ids', '[]'::jsonb),
    (v_meta -> d.line_id::text ->> 'audit_classification'),
    d.draft_id,
    d.line_id,
    to_jsonb(d)
  from public.monthly_plan_draft_lines d
  where d.line_id in (
    {all_sql}
  );

  get diagnostics v_inserted = row_count;

  if v_inserted <> 35 then
    raise exception 'ABORT: backup rows expected 35, got %', v_inserted;
  end if;

  if (
    select count(*)
    from public.monthly_plan_draft_lines_backup_legacy_202607
    where cleanup_batch_id = v_batch
      and cleanup_action = 'KEEP_PENDING_MANUAL_DECISION'
      and source_line_id = '{KEEP}'::uuid
  ) <> 1 then
    raise exception 'ABORT: B35 KEEP backup row missing';
  end if;

  if (
    select count(*)
    from public.monthly_plan_draft_lines_backup_legacy_202607
    where cleanup_batch_id = v_batch
      and cleanup_action = 'DELETE_LEGACY_TAIL'
  ) <> 34 then
    raise exception 'ABORT: expected 34 DELETE_LEGACY_TAIL backup rows';
  end if;
end $$;

-- -----------------------------------------------------------------------------
-- 3) DELETE only the approved 34 primary keys
-- -----------------------------------------------------------------------------
do $$
declare
  v_deleted int;
begin
  delete from public.monthly_plan_draft_lines d
  where d.line_id in (
    {delete_sql}
  );

  get diagnostics v_deleted = row_count;

  if v_deleted <> 34 then
    raise exception 'ABORT: deleted rows expected 34, got %', v_deleted;
  end if;
end $$;

-- -----------------------------------------------------------------------------
-- 4) Post-delete validations
-- -----------------------------------------------------------------------------
do $$
declare
  v_left int;
  v_keep int;
  v_gone int;
  v_backup int;
  v_plan_after int;
  v_plan_before int;
begin
  select count(*) into v_left
  from public.monthly_plan_draft_lines
  where draft_id = '{DRAFT}'::uuid;

  if v_left <> 1 then
    raise exception 'ABORT: legacy rows after expected 1, found %', v_left;
  end if;

  select count(*) into v_keep
  from public.monthly_plan_draft_lines
  where line_id = '{KEEP}'::uuid
    and draft_id = '{DRAFT}'::uuid
    and client_line_uid is null
    and plan_line_id is null
    and coalesce(line_status, '') = 'DRAFT'
    and coalesce(boq_code, '') = '1470-01-04-03'
    and planned_qty = 132.6
    and coalesce(crew_id, '') = 'АСИ-10'
    and coalesce(facility_building, '') = '16160-13';

  if v_keep <> 1 then
    raise exception 'ABORT: remaining row is not intact B35';
  end if;

  select count(*) into v_gone
  from public.monthly_plan_draft_lines
  where line_id in (
    {delete_sql}
  );

  if v_gone <> 0 then
    raise exception 'ABORT: % delete-set rows still present after DELETE', v_gone;
  end if;

  select count(*) into v_backup
  from public.monthly_plan_draft_lines_backup_legacy_202607
  where cleanup_batch_id = '{batch}'::uuid;

  if v_backup <> 35 then
    raise exception 'ABORT: backup rows for batch expected 35, found %', v_backup;
  end if;

  select count(*) into v_plan_after
  from public.monthly_plan_lines_v2
  where project_code = 'PRJ_001_БХК'
    and month_key = 'июль-2026';

  v_plan_before := nullif(current_setting('app.legacy_cleanup_plan_before', true), '')::int;

  if v_plan_before is distinct from 124 or v_plan_after is distinct from 124 then
    raise exception
      'ABORT: monthly_plan_lines_v2 count changed (before=%, after=%); expected 124/124',
      v_plan_before, v_plan_after;
  end if;
end $$;

commit;

-- =============================================================================
-- Optional post-commit SELECTs (safe; run after successful COMMIT):
-- =============================================================================
-- select count(*) as legacy_rows_after
-- from public.monthly_plan_draft_lines
-- where draft_id = '{DRAFT}'::uuid;
--
-- select line_id, boq_code, planned_qty, crew_id, facility_building,
--        client_line_uid, plan_line_id, line_status
-- from public.monthly_plan_draft_lines
-- where line_id = '{KEEP}'::uuid;
--
-- select cleanup_action, count(*)
-- from public.monthly_plan_draft_lines_backup_legacy_202607
-- where cleanup_batch_id = '{batch}'::uuid
-- group by cleanup_action;
--
-- select count(*) as plan_rows
-- from public.monthly_plan_lines_v2
-- where project_code = 'PRJ_001_БХК'
--   and month_key = 'июль-2026';
'''

out=pathlib.Path(r'c:\csv_fix\sql\legacy_draft_cleanup_keep_b35_202607.sql')
out.write_text(sql, encoding='utf-8')

# mark obsolete
obs_path=pathlib.Path(r'c:\csv_fix\sql\legacy_group_b_migration_202607.sql')
cur=obs_path.read_text(encoding='utf-8')
banner='''-- =============================================================================
-- OBSOLETE — DO NOT EXECUTE
-- Replaced by business audit: most Group B rows were M3 technical tails.
-- Active cleanup script: sql/legacy_draft_cleanup_keep_b35_202607.sql
-- Marked obsolete: 2026-07-28
-- =============================================================================

'''
if 'OBSOLETE — DO NOT EXECUTE' not in cur:
    obs_path.write_text(banner+cur, encoding='utf-8')

meta_out={
  'cleanup_batch_id': batch,
  'draft_id': DRAFT,
  'keep_line_id': KEEP,
  'delete_count': 34,
  'delete_ids': delete_ids,
  'sql_file': str(out),
  'backup_table': 'public.monthly_plan_draft_lines_backup_legacy_202607',
  'executed': False,
}
pathlib.Path(r'c:\csv_fix\_tmp_legacy_cleanup_batch.json').write_text(
    json.dumps(meta_out, ensure_ascii=False, indent=2), encoding='utf-8'
)
print(json.dumps({'batch': batch, 'sql_bytes': out.stat().st_size, 'delete': len(delete_ids)}, ensure_ascii=False))
