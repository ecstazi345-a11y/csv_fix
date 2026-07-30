-- =============================================================================
-- TECHNICAL DUPLICATES CLEANUP — monthly_plan_lines_v2 (transactional)
-- DELETE candidates: exactly 30 plan_line_id from audit
-- Backup table: monthly_plan_lines_v2_deleted_backup_20260728
-- App / Python / Streamlit: NOT modified
-- =============================================================================
-- Expected PRJ_001_БХК / июль-2026 (from pre-cleanup audit):
--   ROWS BEFORE   = 124
--   ROWS AFTER    = 95
--   VALUE BEFORE  = 41137527.5996
--   VALUE AFTER   = 29964515.4033
--   HOURS BEFORE  = 11117.50734023848  (column: labor_hours)
--   HOURS AFTER   = 8287.808006905147
-- =============================================================================
-- Note: table has labor_hours, not required_work_hours — use labor_hours in SELECTs
-- =============================================================================

begin;

-- 0) BEFORE metrics (PRJ / month)
do $$
declare
  v_rows int;
  v_value numeric;
  v_hours numeric;
begin
  select count(*), coalesce(sum(plan_value),0), coalesce(sum(labor_hours),0)
  into v_rows, v_value, v_hours
  from public.monthly_plan_lines_v2
  where project_code = 'PRJ_001_БХК' and month_key = 'июль-2026';

  perform set_config('app.techdup_rows_before', v_rows::text, true);
  perform set_config('app.techdup_value_before', v_value::text, true);
  perform set_config('app.techdup_hours_before', v_hours::text, true);

  if v_rows <> 124 then
    raise exception 'ABORT: rows before expected 124, found %', v_rows;
  end if;
end $$;

-- 1) Backup table + 30 rows
create table if not exists public.monthly_plan_lines_v2_deleted_backup_20260728 (
  backup_id uuid primary key default gen_random_uuid(),
  backed_up_at timestamptz not null default now(),
  cleanup_reason text not null,
  keep_plan_line_id uuid,
  group_id text,
  source_plan_line_id uuid not null,
  row_snapshot jsonb not null
);

do $$
declare v_ins int; v_miss int;
begin
  select count(*) into v_miss
  from (
    select unnest(array[
      '86ad20c3-9be5-4642-8c96-b37c7636588c'::uuid,
      '0b74fceb-56b3-4732-9d98-e78c78c6c087'::uuid,
      '34c64e38-5889-4632-8573-0053e81b6dcc'::uuid,
      '204b572a-32df-4dee-bd1e-58f41a43e599'::uuid,
      '61b49da5-98b1-4c7b-8066-62321635ce4a'::uuid,
      '34fff00e-5b07-49ef-929f-2dcb5b539001'::uuid,
      '0a87d0bb-ee84-4a8c-a625-6bc4fd17b220'::uuid,
      'c79d3aa9-2fc0-408a-aab7-8ebbd14f1182'::uuid,
      '099cc188-0ac2-49db-a245-d5b129507808'::uuid,
      '4e7e0383-5659-4ba1-9dab-8208be1b1b68'::uuid,
      '65d4fd5b-867e-4170-85b2-31cad9b570ee'::uuid,
      'bf3ef19e-0eae-467f-aa4b-eda6219dd1d9'::uuid,
      '96dfa13f-44aa-4015-82ba-f2906a72463c'::uuid,
      '0efdeb0b-79b7-46cd-a10d-0c9d7b8e74e4'::uuid,
      'd168bf9c-c9f9-48ce-9ce1-9a56b8359013'::uuid,
      '43e38dfd-fd1b-4ece-bb07-b24b3b3a98c8'::uuid,
      'e67f779d-4699-41cd-ab6e-b6fa59461ada'::uuid,
      'd698e7e0-5219-4165-9894-13b86e8d2946'::uuid,
      'ecfbe872-3ddd-4530-9b5a-ccc8d77797fa'::uuid,
      '0d318268-196f-4603-94ef-7a4dedb64864'::uuid,
      '39f573b0-841a-4a04-996f-c972368a979a'::uuid,
      'f006114a-67ad-47e7-b8f6-44f07c44f7de'::uuid,
      'd53e1090-24c0-49ee-8f9f-3b815d228b50'::uuid,
      'f695054a-995c-4d96-9f27-8e04328cc74e'::uuid,
      '08958ad9-8858-4571-a805-3cf59c37e839'::uuid,
      '166b62c4-06e6-4223-a67e-c8c396f4e7e8'::uuid,
      'a5147534-0214-41bb-b7eb-dbb12b49ec87'::uuid,
      '53508c7d-7df2-413f-86ed-9272accd15bc'::uuid,
      '4b86facb-7ec1-4674-ab1b-12bd10223935'::uuid,
      'bbcbc584-b46b-426d-8093-a6e87d99c683'::uuid
    ]) as plan_line_id
  ) x
  left join public.monthly_plan_lines_v2 p on p.plan_line_id = x.plan_line_id
  where p.plan_line_id is null;

  if v_miss <> 0 then
    raise exception 'ABORT: % UUID(s) missing from live table', v_miss;
  end if;

  insert into public.monthly_plan_lines_v2_deleted_backup_20260728 (
    backed_up_at, cleanup_reason, keep_plan_line_id, group_id, source_plan_line_id, row_snapshot
  )
  select now(), 'technical_duplicate_cleanup_20260728', null, null, p.plan_line_id, to_jsonb(p)
  from public.monthly_plan_lines_v2 p
  where p.plan_line_id in (
    '86ad20c3-9be5-4642-8c96-b37c7636588c'::uuid,
    '0b74fceb-56b3-4732-9d98-e78c78c6c087'::uuid,
    '34c64e38-5889-4632-8573-0053e81b6dcc'::uuid,
    '204b572a-32df-4dee-bd1e-58f41a43e599'::uuid,
    '61b49da5-98b1-4c7b-8066-62321635ce4a'::uuid,
    '34fff00e-5b07-49ef-929f-2dcb5b539001'::uuid,
    '0a87d0bb-ee84-4a8c-a625-6bc4fd17b220'::uuid,
    'c79d3aa9-2fc0-408a-aab7-8ebbd14f1182'::uuid,
    '099cc188-0ac2-49db-a245-d5b129507808'::uuid,
    '4e7e0383-5659-4ba1-9dab-8208be1b1b68'::uuid,
    '65d4fd5b-867e-4170-85b2-31cad9b570ee'::uuid,
    'bf3ef19e-0eae-467f-aa4b-eda6219dd1d9'::uuid,
    '96dfa13f-44aa-4015-82ba-f2906a72463c'::uuid,
    '0efdeb0b-79b7-46cd-a10d-0c9d7b8e74e4'::uuid,
    'd168bf9c-c9f9-48ce-9ce1-9a56b8359013'::uuid,
    '43e38dfd-fd1b-4ece-bb07-b24b3b3a98c8'::uuid,
    'e67f779d-4699-41cd-ab6e-b6fa59461ada'::uuid,
    'd698e7e0-5219-4165-9894-13b86e8d2946'::uuid,
    'ecfbe872-3ddd-4530-9b5a-ccc8d77797fa'::uuid,
    '0d318268-196f-4603-94ef-7a4dedb64864'::uuid,
    '39f573b0-841a-4a04-996f-c972368a979a'::uuid,
    'f006114a-67ad-47e7-b8f6-44f07c44f7de'::uuid,
    'd53e1090-24c0-49ee-8f9f-3b815d228b50'::uuid,
    'f695054a-995c-4d96-9f27-8e04328cc74e'::uuid,
    '08958ad9-8858-4571-a805-3cf59c37e839'::uuid,
    '166b62c4-06e6-4223-a67e-c8c396f4e7e8'::uuid,
    'a5147534-0214-41bb-b7eb-dbb12b49ec87'::uuid,
    '53508c7d-7df2-413f-86ed-9272accd15bc'::uuid,
    '4b86facb-7ec1-4674-ab1b-12bd10223935'::uuid,
    'bbcbc584-b46b-426d-8093-a6e87d99c683'::uuid
  );

  get diagnostics v_ins = row_count;
  if v_ins <> 30 then
    raise exception 'ABORT: backup insert expected 30, got %', v_ins;
  end if;
end $$;

-- 2) DELETE 30 UUIDs only
do $$
declare v_del int;
begin
  delete from public.monthly_plan_lines_v2
  where plan_line_id in (
    '86ad20c3-9be5-4642-8c96-b37c7636588c'::uuid,
    '0b74fceb-56b3-4732-9d98-e78c78c6c087'::uuid,
    '34c64e38-5889-4632-8573-0053e81b6dcc'::uuid,
    '204b572a-32df-4dee-bd1e-58f41a43e599'::uuid,
    '61b49da5-98b1-4c7b-8066-62321635ce4a'::uuid,
    '34fff00e-5b07-49ef-929f-2dcb5b539001'::uuid,
    '0a87d0bb-ee84-4a8c-a625-6bc4fd17b220'::uuid,
    'c79d3aa9-2fc0-408a-aab7-8ebbd14f1182'::uuid,
    '099cc188-0ac2-49db-a245-d5b129507808'::uuid,
    '4e7e0383-5659-4ba1-9dab-8208be1b1b68'::uuid,
    '65d4fd5b-867e-4170-85b2-31cad9b570ee'::uuid,
    'bf3ef19e-0eae-467f-aa4b-eda6219dd1d9'::uuid,
    '96dfa13f-44aa-4015-82ba-f2906a72463c'::uuid,
    '0efdeb0b-79b7-46cd-a10d-0c9d7b8e74e4'::uuid,
    'd168bf9c-c9f9-48ce-9ce1-9a56b8359013'::uuid,
    '43e38dfd-fd1b-4ece-bb07-b24b3b3a98c8'::uuid,
    'e67f779d-4699-41cd-ab6e-b6fa59461ada'::uuid,
    'd698e7e0-5219-4165-9894-13b86e8d2946'::uuid,
    'ecfbe872-3ddd-4530-9b5a-ccc8d77797fa'::uuid,
    '0d318268-196f-4603-94ef-7a4dedb64864'::uuid,
    '39f573b0-841a-4a04-996f-c972368a979a'::uuid,
    'f006114a-67ad-47e7-b8f6-44f07c44f7de'::uuid,
    'd53e1090-24c0-49ee-8f9f-3b815d228b50'::uuid,
    'f695054a-995c-4d96-9f27-8e04328cc74e'::uuid,
    '08958ad9-8858-4571-a805-3cf59c37e839'::uuid,
    '166b62c4-06e6-4223-a67e-c8c396f4e7e8'::uuid,
    'a5147534-0214-41bb-b7eb-dbb12b49ec87'::uuid,
    '53508c7d-7df2-413f-86ed-9272accd15bc'::uuid,
    '4b86facb-7ec1-4674-ab1b-12bd10223935'::uuid,
    'bbcbc584-b46b-426d-8093-a6e87d99c683'::uuid
  );
  get diagnostics v_del = row_count;
  if v_del <> 30 then
    raise exception 'ABORT: delete expected 30, got %', v_del;
  end if;
end $$;

-- 3) Post-delete checks
do $$
declare v_rows int; v_value numeric; v_hours numeric;
begin
  if exists (
    select 1 from public.monthly_plan_lines_v2 where plan_line_id in (
      '86ad20c3-9be5-4642-8c96-b37c7636588c'::uuid,
      '0b74fceb-56b3-4732-9d98-e78c78c6c087'::uuid,
      '34c64e38-5889-4632-8573-0053e81b6dcc'::uuid,
      '204b572a-32df-4dee-bd1e-58f41a43e599'::uuid,
      '61b49da5-98b1-4c7b-8066-62321635ce4a'::uuid,
      '34fff00e-5b07-49ef-929f-2dcb5b539001'::uuid,
      '0a87d0bb-ee84-4a8c-a625-6bc4fd17b220'::uuid,
      'c79d3aa9-2fc0-408a-aab7-8ebbd14f1182'::uuid,
      '099cc188-0ac2-49db-a245-d5b129507808'::uuid,
      '4e7e0383-5659-4ba1-9dab-8208be1b1b68'::uuid,
      '65d4fd5b-867e-4170-85b2-31cad9b570ee'::uuid,
      'bf3ef19e-0eae-467f-aa4b-eda6219dd1d9'::uuid,
      '96dfa13f-44aa-4015-82ba-f2906a72463c'::uuid,
      '0efdeb0b-79b7-46cd-a10d-0c9d7b8e74e4'::uuid,
      'd168bf9c-c9f9-48ce-9ce1-9a56b8359013'::uuid,
      '43e38dfd-fd1b-4ece-bb07-b24b3b3a98c8'::uuid,
      'e67f779d-4699-41cd-ab6e-b6fa59461ada'::uuid,
      'd698e7e0-5219-4165-9894-13b86e8d2946'::uuid,
      'ecfbe872-3ddd-4530-9b5a-ccc8d77797fa'::uuid,
      '0d318268-196f-4603-94ef-7a4dedb64864'::uuid,
      '39f573b0-841a-4a04-996f-c972368a979a'::uuid,
      'f006114a-67ad-47e7-b8f6-44f07c44f7de'::uuid,
      'd53e1090-24c0-49ee-8f9f-3b815d228b50'::uuid,
      'f695054a-995c-4d96-9f27-8e04328cc74e'::uuid,
      '08958ad9-8858-4571-a805-3cf59c37e839'::uuid,
      '166b62c4-06e6-4223-a67e-c8c396f4e7e8'::uuid,
      'a5147534-0214-41bb-b7eb-dbb12b49ec87'::uuid,
      '53508c7d-7df2-413f-86ed-9272accd15bc'::uuid,
      '4b86facb-7ec1-4674-ab1b-12bd10223935'::uuid,
      'bbcbc584-b46b-426d-8093-a6e87d99c683'::uuid
    )
  ) then
    raise exception 'ABORT: deleted UUID still present';
  end if;

  select count(*), coalesce(sum(plan_value),0), coalesce(sum(labor_hours),0)
  into v_rows, v_value, v_hours
  from public.monthly_plan_lines_v2
  where project_code = 'PRJ_001_БХК' and month_key = 'июль-2026';

  if v_rows <> 95 then
    raise exception 'ABORT: rows after expected 95, found %', v_rows;
  end if;

  perform set_config('app.techdup_rows_after', v_rows::text, true);
  perform set_config('app.techdup_value_after', v_value::text, true);
  perform set_config('app.techdup_hours_after', v_hours::text, true);
end $$;

commit;

-- 4) Post-commit verification (as requested)
-- If your schema has no required_work_hours, use labor_hours (shown here):
select
  count(*) as rows,
  coalesce(sum(plan_value), 0) as total_value,
  coalesce(sum(labor_hours), 0) as total_hours
from public.monthly_plan_lines_v2
where project_code = 'PRJ_001_БХК'
  and month_key = 'июль-2026';

select count(*) as backup_rows
from public.monthly_plan_lines_v2_deleted_backup_20260728;

-- Optional report template after successful run:
-- BACKUP CREATED: YES (expect backup_rows = 30)
-- ROWS BEFORE: 124
-- ROWS AFTER: 95
-- VALUE BEFORE: 41137527.5996
-- VALUE AFTER: 29964515.4033
-- HOURS BEFORE: 11117.50734023848
-- HOURS AFTER: 8287.808006905147
