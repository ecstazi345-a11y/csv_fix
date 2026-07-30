-- =============================================================================
-- LEGACY DRAFT CLEANUP — KEEP B35 ONLY
-- Active draft: 661d5ffe-5851-4a27-8b4b-e01d16929798
-- cleanup_batch_id: 8775a015-6847-492c-b5cb-2e8f21ac192f
-- DELETE SET: 34 line_id (exact PK list)
-- KEEP / DO NOT DELETE / DO NOT UPDATE: c90c5f21-e9e5-45c8-93e2-940dbc4fe862 (B35)
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
  where draft_id = '661d5ffe-5851-4a27-8b4b-e01d16929798'::uuid;

  if v_draft_total <> 35 then
    raise exception 'ABORT: legacy rows before expected 35, found %', v_draft_total;
  end if;

  select count(*) into v_target_total
  from public.monthly_plan_draft_lines
  where line_id in (
    '4280dbdc-aebb-4256-a731-098065edf19c'::uuid,
    '481363ed-955f-46ff-8969-475c1c3deecc'::uuid,
    '8898f66f-7f55-4ae4-b146-57a1ac998f6a'::uuid,
    '9c548492-628a-4179-a644-62ac420b65a3'::uuid,
    '49362e64-d137-4f95-b6eb-669ac68a45af'::uuid,
    '5677541c-1e70-4431-9093-0d374ed58bf0'::uuid,
    'f1bf6b49-e80a-4f84-9f55-614428106cd6'::uuid,
    'a72017cc-e9fd-4aad-ab1a-75c349d47f85'::uuid,
    '16486e86-d338-401c-9daf-ee7d7d17f933'::uuid,
    'c65de2cc-8fd7-466e-8494-c98c0c126a64'::uuid,
    '5136b0f9-d585-4e84-b849-56b6c3bbcb52'::uuid,
    '347c03a2-08ad-4f42-b50f-8181de569b86'::uuid,
    '1c82d05b-5d7b-4783-b110-a9bfce6eb62f'::uuid,
    '560015f8-dac8-4722-a155-a684ae5fe484'::uuid,
    '4d06523c-b440-417e-b3fc-86ed0a77170c'::uuid,
    '4df3ec69-fb65-4d5a-a3c4-b8a4d5c2561c'::uuid,
    'eda4baa9-786b-409e-a89c-ba9fdb495dd9'::uuid,
    '668f12ff-4983-49b9-9bb0-9528079fbf43'::uuid,
    '6e2db03b-1a2f-45a6-83ee-46247db1affa'::uuid,
    '07f40fa8-5ac8-4c22-a19f-1d37ee7c6448'::uuid,
    'ac775cb4-70f8-4d3a-94cb-f0c0abe55c4c'::uuid,
    'ad554cc7-eb4d-4c39-b56d-ef78235e0c7c'::uuid,
    '9854d163-4a79-45d8-ac79-eb50ab81cc7a'::uuid,
    '767909e7-e358-4cba-b7b0-b6723b715b30'::uuid,
    '4d98829f-b027-48a0-a858-01a634eaba5c'::uuid,
    '46f439bb-a829-4d4f-be2e-af630be55cc9'::uuid,
    '8c17d045-30bf-4930-98e9-b9189952fbf0'::uuid,
    'f75774ee-b54d-4213-a07e-0b98c61155d5'::uuid,
    '5b0496b7-126d-412f-b052-44e2751648a2'::uuid,
    'f856d039-5bc3-4f1d-92dd-6d11eb1b1c06'::uuid,
    '0d0bf5c0-a5c1-4c9a-bdd2-ffbe655c3568'::uuid,
    '1eb63335-91e0-4b5d-a933-cb42046a62a5'::uuid,
    'b148f69b-5375-4ccc-825c-5c0589b4300a'::uuid,
    '366ba576-2b4f-43c0-9708-d24bf458c5d7'::uuid,
    'c90c5f21-e9e5-45c8-93e2-940dbc4fe862'::uuid
  );

  if v_target_total <> 35 then
    raise exception 'ABORT: expected all 35 audited line_id present, found %', v_target_total;
  end if;

  select count(*) into v_keep
  from public.monthly_plan_draft_lines
  where line_id = 'c90c5f21-e9e5-45c8-93e2-940dbc4fe862'::uuid
    and draft_id = '661d5ffe-5851-4a27-8b4b-e01d16929798'::uuid
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
    '4280dbdc-aebb-4256-a731-098065edf19c'::uuid,
    '481363ed-955f-46ff-8969-475c1c3deecc'::uuid,
    '8898f66f-7f55-4ae4-b146-57a1ac998f6a'::uuid,
    '9c548492-628a-4179-a644-62ac420b65a3'::uuid,
    '49362e64-d137-4f95-b6eb-669ac68a45af'::uuid,
    '5677541c-1e70-4431-9093-0d374ed58bf0'::uuid,
    'f1bf6b49-e80a-4f84-9f55-614428106cd6'::uuid,
    'a72017cc-e9fd-4aad-ab1a-75c349d47f85'::uuid,
    '16486e86-d338-401c-9daf-ee7d7d17f933'::uuid,
    'c65de2cc-8fd7-466e-8494-c98c0c126a64'::uuid,
    '5136b0f9-d585-4e84-b849-56b6c3bbcb52'::uuid,
    '347c03a2-08ad-4f42-b50f-8181de569b86'::uuid,
    '1c82d05b-5d7b-4783-b110-a9bfce6eb62f'::uuid,
    '560015f8-dac8-4722-a155-a684ae5fe484'::uuid,
    '4d06523c-b440-417e-b3fc-86ed0a77170c'::uuid,
    '4df3ec69-fb65-4d5a-a3c4-b8a4d5c2561c'::uuid,
    'eda4baa9-786b-409e-a89c-ba9fdb495dd9'::uuid,
    '668f12ff-4983-49b9-9bb0-9528079fbf43'::uuid,
    '6e2db03b-1a2f-45a6-83ee-46247db1affa'::uuid,
    '07f40fa8-5ac8-4c22-a19f-1d37ee7c6448'::uuid,
    'ac775cb4-70f8-4d3a-94cb-f0c0abe55c4c'::uuid,
    'ad554cc7-eb4d-4c39-b56d-ef78235e0c7c'::uuid,
    '9854d163-4a79-45d8-ac79-eb50ab81cc7a'::uuid,
    '767909e7-e358-4cba-b7b0-b6723b715b30'::uuid,
    '4d98829f-b027-48a0-a858-01a634eaba5c'::uuid,
    '46f439bb-a829-4d4f-be2e-af630be55cc9'::uuid,
    '8c17d045-30bf-4930-98e9-b9189952fbf0'::uuid,
    'f75774ee-b54d-4213-a07e-0b98c61155d5'::uuid,
    '5b0496b7-126d-412f-b052-44e2751648a2'::uuid,
    'f856d039-5bc3-4f1d-92dd-6d11eb1b1c06'::uuid,
    '0d0bf5c0-a5c1-4c9a-bdd2-ffbe655c3568'::uuid,
    '1eb63335-91e0-4b5d-a933-cb42046a62a5'::uuid,
    'b148f69b-5375-4ccc-825c-5c0589b4300a'::uuid,
    '366ba576-2b4f-43c0-9708-d24bf458c5d7'::uuid
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
  v_batch uuid := '8775a015-6847-492c-b5cb-2e8f21ac192f'::uuid;
  v_reason text := 'legacy_draft_cleanup_keep_b35_only';
  v_meta jsonb := $meta${"4280dbdc-aebb-4256-a731-098065edf19c": {"label": "B1", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "B:B1:Group B business audit M3: exact/near match already SENT in plan; save/restore technical tail", "related_plan_line_ids": ["21088d49-f180-4623-8e8d-1247489356e6", "376fa0ec-dd52-4087-9656-a5f8d3acba6e", "ddd4584e-c9da-47ce-83d5-13a00cf26164", "5c982a12-5cac-4aa1-96bf-ac6d93fff6dc"]}, "481363ed-955f-46ff-8969-475c1c3deecc": {"label": "A2", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A2:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["b6471349-e0d3-4285-9328-e8ead01cee4b"]}, "8898f66f-7f55-4ae4-b146-57a1ac998f6a": {"label": "A3", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A3:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["2ac41948-3913-4dbb-931a-447e23c87b5f"]}, "9c548492-628a-4179-a644-62ac420b65a3": {"label": "D4", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "D:D4:Group D: ambiguous multi-match plan duplicates; legacy tail, do not restore", "related_plan_line_ids": ["9eb2ed48-ecb4-4033-b095-3a646d4c2402", "6937aa11-8a42-46eb-ae6c-d730e57a91d5"]}, "49362e64-d137-4f95-b6eb-669ac68a45af": {"label": "B5", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "B:B5:Group B business audit M3: exact/near match already SENT in plan; save/restore technical tail", "related_plan_line_ids": ["8ac44357-9683-4aa5-be34-ef4322b3cb3a"]}, "5677541c-1e70-4431-9093-0d374ed58bf0": {"label": "B6", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "B:B6:Group B business audit M3: exact/near match already SENT in plan; save/restore technical tail", "related_plan_line_ids": ["d4618bf2-611a-43bc-b7ce-2b49da54647a"]}, "f1bf6b49-e80a-4f84-9f55-614428106cd6": {"label": "B7", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "B:B7:Group B business audit M3: exact/near match already SENT in plan; save/restore technical tail", "related_plan_line_ids": ["9170760c-c15c-46fd-9974-7da7a1ad57c8"]}, "a72017cc-e9fd-4aad-ab1a-75c349d47f85": {"label": "B8", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "B:B8:Group B exact-duplicate draft twin of B9; technical legacy tail; related plan already SENT (same scope as B9)", "related_plan_line_ids": ["63b2a399-3278-4fe3-8633-7e6ae106b871", "c79d3aa9-2fc0-408a-aab7-8ebbd14f1182"]}, "16486e86-d338-401c-9daf-ee7d7d17f933": {"label": "B9", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "B:B9:Group B business audit M3: exact/near match already SENT in plan; save/restore technical tail", "related_plan_line_ids": ["63b2a399-3278-4fe3-8633-7e6ae106b871", "c79d3aa9-2fc0-408a-aab7-8ebbd14f1182"]}, "c65de2cc-8fd7-466e-8494-c98c0c126a64": {"label": "B10", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "B:B10:Group B business audit M3: exact/near match already SENT in plan; save/restore technical tail", "related_plan_line_ids": ["cfde5650-c99d-4c6d-89f6-3ca4ea54cfeb"]}, "5136b0f9-d585-4e84-b849-56b6c3bbcb52": {"label": "B11", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "B:B11:Group B business audit M3: exact/near match already SENT in plan; save/restore technical tail", "related_plan_line_ids": ["5f880e8a-34cf-4406-863e-bc9647491d19", "2ac41948-3913-4dbb-931a-447e23c87b5f"]}, "347c03a2-08ad-4f42-b50f-8181de569b86": {"label": "A12", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A12:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["5f0e6c1a-359f-497a-addc-7d9c1f8563fd"]}, "1c82d05b-5d7b-4783-b110-a9bfce6eb62f": {"label": "A13", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A13:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["1edee268-7f33-4876-9f2f-52e50c960dd2"]}, "560015f8-dac8-4722-a155-a684ae5fe484": {"label": "A14", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A14:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["8d9a0313-cbb2-475a-bcab-1df9af4400c9"]}, "4d06523c-b440-417e-b3fc-86ed0a77170c": {"label": "A15", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A15:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["cc3720d4-c449-49d4-a5b3-f394cf256c0f"]}, "4df3ec69-fb65-4d5a-a3c4-b8a4d5c2561c": {"label": "A16", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A16:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["f2e56ad0-5a34-411c-bb43-edeb808cd293"]}, "eda4baa9-786b-409e-a89c-ba9fdb495dd9": {"label": "A17", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A17:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["39f7e231-3938-44a5-9cc2-cb80e293db60"]}, "668f12ff-4983-49b9-9bb0-9528079fbf43": {"label": "A18", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A18:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["def621cf-2662-4d91-8c49-803690e3e0ec"]}, "6e2db03b-1a2f-45a6-83ee-46247db1affa": {"label": "A19", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A19:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["c70ee054-78c3-4c31-b8f5-4f2c03e56e98"]}, "07f40fa8-5ac8-4c22-a19f-1d37ee7c6448": {"label": "A20", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A20:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["2e0cc716-ddc5-4c36-af64-6debda7fec7c"]}, "ac775cb4-70f8-4d3a-94cb-f0c0abe55c4c": {"label": "A21", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A21:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["37b409ce-ff39-41be-a312-6b7593669f10"]}, "ad554cc7-eb4d-4c39-b56d-ef78235e0c7c": {"label": "D22", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "D:D22:Group D: ambiguous multi-match plan duplicates; legacy tail, do not restore", "related_plan_line_ids": ["9eb2ed48-ecb4-4033-b095-3a646d4c2402", "6937aa11-8a42-46eb-ae6c-d730e57a91d5"]}, "9854d163-4a79-45d8-ac79-eb50ab81cc7a": {"label": "A23", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A23:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["05d5b267-75d6-48df-a7d0-8465382c4b70"]}, "767909e7-e358-4cba-b7b0-b6723b715b30": {"label": "A24", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A24:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["f458adab-4f77-4426-8072-73a64562b65e"]}, "4d98829f-b027-48a0-a858-01a634eaba5c": {"label": "A25", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A25:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["0bec2868-c24a-4988-98eb-257f874da52e"]}, "46f439bb-a829-4d4f-be2e-af630be55cc9": {"label": "A26", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A26:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["2ce1de69-83af-4377-a8d2-8a78da4323dd"]}, "8c17d045-30bf-4930-98e9-b9189952fbf0": {"label": "A27", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A27:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["41330c13-be9e-43ec-9bdd-cb25a04c6d28"]}, "f75774ee-b54d-4213-a07e-0b98c61155d5": {"label": "A28", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A28:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["89bc4103-41d5-47e3-a5c0-578daf4aa562"]}, "5b0496b7-126d-412f-b052-44e2751648a2": {"label": "A29", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A29:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["10cdd80e-8016-41f2-9064-3f691900fef1"]}, "f856d039-5bc3-4f1d-92dd-6d11eb1b1c06": {"label": "A30", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A30:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["be70e576-854b-46ce-8503-88375eaca3da"]}, "0d0bf5c0-a5c1-4c9a-bdd2-ffbe655c3568": {"label": "A31", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A31:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["05eef51d-6238-4710-95fa-9fe28b831b43"]}, "1eb63335-91e0-4b5d-a933-cb42046a62a5": {"label": "A32", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "A:A32:Group A: already saved in monthly_plan_lines_v2 (exact match); legacy restore tail", "related_plan_line_ids": ["81c0902a-0d95-49d3-9f68-6f4c50bdf23e"]}, "b148f69b-5375-4ccc-825c-5c0589b4300a": {"label": "B33", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "B:B33:Group B business audit M3: exact/near match already SENT in plan; save/restore technical tail", "related_plan_line_ids": ["21088d49-f180-4623-8e8d-1247489356e6", "376fa0ec-dd52-4087-9656-a5f8d3acba6e", "ddd4584e-c9da-47ce-83d5-13a00cf26164", "5c982a12-5cac-4aa1-96bf-ac6d93fff6dc"]}, "366ba576-2b4f-43c0-9708-d24bf458c5d7": {"label": "B34", "cleanup_action": "DELETE_LEGACY_TAIL", "audit_classification": "B:B34:Group B business audit M3: exact/near match already SENT in plan; save/restore technical tail", "related_plan_line_ids": ["b5805f25-f3e9-4bbe-8812-b7a9de99b25c", "d168bf9c-c9f9-48ce-9ce1-9a56b8359013"]}, "c90c5f21-e9e5-45c8-93e2-940dbc4fe862": {"label": "B35", "cleanup_action": "KEEP_PENDING_MANUAL_DECISION", "audit_classification": "B:B35:M4/M5 potential independent unfinished work; manual decision pending", "related_plan_line_ids": ["9a339a05-be64-4ea9-af5c-fd14a901f7c2"]}}$meta$::jsonb;
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
    '4280dbdc-aebb-4256-a731-098065edf19c'::uuid,
    '481363ed-955f-46ff-8969-475c1c3deecc'::uuid,
    '8898f66f-7f55-4ae4-b146-57a1ac998f6a'::uuid,
    '9c548492-628a-4179-a644-62ac420b65a3'::uuid,
    '49362e64-d137-4f95-b6eb-669ac68a45af'::uuid,
    '5677541c-1e70-4431-9093-0d374ed58bf0'::uuid,
    'f1bf6b49-e80a-4f84-9f55-614428106cd6'::uuid,
    'a72017cc-e9fd-4aad-ab1a-75c349d47f85'::uuid,
    '16486e86-d338-401c-9daf-ee7d7d17f933'::uuid,
    'c65de2cc-8fd7-466e-8494-c98c0c126a64'::uuid,
    '5136b0f9-d585-4e84-b849-56b6c3bbcb52'::uuid,
    '347c03a2-08ad-4f42-b50f-8181de569b86'::uuid,
    '1c82d05b-5d7b-4783-b110-a9bfce6eb62f'::uuid,
    '560015f8-dac8-4722-a155-a684ae5fe484'::uuid,
    '4d06523c-b440-417e-b3fc-86ed0a77170c'::uuid,
    '4df3ec69-fb65-4d5a-a3c4-b8a4d5c2561c'::uuid,
    'eda4baa9-786b-409e-a89c-ba9fdb495dd9'::uuid,
    '668f12ff-4983-49b9-9bb0-9528079fbf43'::uuid,
    '6e2db03b-1a2f-45a6-83ee-46247db1affa'::uuid,
    '07f40fa8-5ac8-4c22-a19f-1d37ee7c6448'::uuid,
    'ac775cb4-70f8-4d3a-94cb-f0c0abe55c4c'::uuid,
    'ad554cc7-eb4d-4c39-b56d-ef78235e0c7c'::uuid,
    '9854d163-4a79-45d8-ac79-eb50ab81cc7a'::uuid,
    '767909e7-e358-4cba-b7b0-b6723b715b30'::uuid,
    '4d98829f-b027-48a0-a858-01a634eaba5c'::uuid,
    '46f439bb-a829-4d4f-be2e-af630be55cc9'::uuid,
    '8c17d045-30bf-4930-98e9-b9189952fbf0'::uuid,
    'f75774ee-b54d-4213-a07e-0b98c61155d5'::uuid,
    '5b0496b7-126d-412f-b052-44e2751648a2'::uuid,
    'f856d039-5bc3-4f1d-92dd-6d11eb1b1c06'::uuid,
    '0d0bf5c0-a5c1-4c9a-bdd2-ffbe655c3568'::uuid,
    '1eb63335-91e0-4b5d-a933-cb42046a62a5'::uuid,
    'b148f69b-5375-4ccc-825c-5c0589b4300a'::uuid,
    '366ba576-2b4f-43c0-9708-d24bf458c5d7'::uuid,
    'c90c5f21-e9e5-45c8-93e2-940dbc4fe862'::uuid
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
      and source_line_id = 'c90c5f21-e9e5-45c8-93e2-940dbc4fe862'::uuid
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
    '4280dbdc-aebb-4256-a731-098065edf19c'::uuid,
    '481363ed-955f-46ff-8969-475c1c3deecc'::uuid,
    '8898f66f-7f55-4ae4-b146-57a1ac998f6a'::uuid,
    '9c548492-628a-4179-a644-62ac420b65a3'::uuid,
    '49362e64-d137-4f95-b6eb-669ac68a45af'::uuid,
    '5677541c-1e70-4431-9093-0d374ed58bf0'::uuid,
    'f1bf6b49-e80a-4f84-9f55-614428106cd6'::uuid,
    'a72017cc-e9fd-4aad-ab1a-75c349d47f85'::uuid,
    '16486e86-d338-401c-9daf-ee7d7d17f933'::uuid,
    'c65de2cc-8fd7-466e-8494-c98c0c126a64'::uuid,
    '5136b0f9-d585-4e84-b849-56b6c3bbcb52'::uuid,
    '347c03a2-08ad-4f42-b50f-8181de569b86'::uuid,
    '1c82d05b-5d7b-4783-b110-a9bfce6eb62f'::uuid,
    '560015f8-dac8-4722-a155-a684ae5fe484'::uuid,
    '4d06523c-b440-417e-b3fc-86ed0a77170c'::uuid,
    '4df3ec69-fb65-4d5a-a3c4-b8a4d5c2561c'::uuid,
    'eda4baa9-786b-409e-a89c-ba9fdb495dd9'::uuid,
    '668f12ff-4983-49b9-9bb0-9528079fbf43'::uuid,
    '6e2db03b-1a2f-45a6-83ee-46247db1affa'::uuid,
    '07f40fa8-5ac8-4c22-a19f-1d37ee7c6448'::uuid,
    'ac775cb4-70f8-4d3a-94cb-f0c0abe55c4c'::uuid,
    'ad554cc7-eb4d-4c39-b56d-ef78235e0c7c'::uuid,
    '9854d163-4a79-45d8-ac79-eb50ab81cc7a'::uuid,
    '767909e7-e358-4cba-b7b0-b6723b715b30'::uuid,
    '4d98829f-b027-48a0-a858-01a634eaba5c'::uuid,
    '46f439bb-a829-4d4f-be2e-af630be55cc9'::uuid,
    '8c17d045-30bf-4930-98e9-b9189952fbf0'::uuid,
    'f75774ee-b54d-4213-a07e-0b98c61155d5'::uuid,
    '5b0496b7-126d-412f-b052-44e2751648a2'::uuid,
    'f856d039-5bc3-4f1d-92dd-6d11eb1b1c06'::uuid,
    '0d0bf5c0-a5c1-4c9a-bdd2-ffbe655c3568'::uuid,
    '1eb63335-91e0-4b5d-a933-cb42046a62a5'::uuid,
    'b148f69b-5375-4ccc-825c-5c0589b4300a'::uuid,
    '366ba576-2b4f-43c0-9708-d24bf458c5d7'::uuid
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
  where draft_id = '661d5ffe-5851-4a27-8b4b-e01d16929798'::uuid;

  if v_left <> 1 then
    raise exception 'ABORT: legacy rows after expected 1, found %', v_left;
  end if;

  select count(*) into v_keep
  from public.monthly_plan_draft_lines
  where line_id = 'c90c5f21-e9e5-45c8-93e2-940dbc4fe862'::uuid
    and draft_id = '661d5ffe-5851-4a27-8b4b-e01d16929798'::uuid
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
    '4280dbdc-aebb-4256-a731-098065edf19c'::uuid,
    '481363ed-955f-46ff-8969-475c1c3deecc'::uuid,
    '8898f66f-7f55-4ae4-b146-57a1ac998f6a'::uuid,
    '9c548492-628a-4179-a644-62ac420b65a3'::uuid,
    '49362e64-d137-4f95-b6eb-669ac68a45af'::uuid,
    '5677541c-1e70-4431-9093-0d374ed58bf0'::uuid,
    'f1bf6b49-e80a-4f84-9f55-614428106cd6'::uuid,
    'a72017cc-e9fd-4aad-ab1a-75c349d47f85'::uuid,
    '16486e86-d338-401c-9daf-ee7d7d17f933'::uuid,
    'c65de2cc-8fd7-466e-8494-c98c0c126a64'::uuid,
    '5136b0f9-d585-4e84-b849-56b6c3bbcb52'::uuid,
    '347c03a2-08ad-4f42-b50f-8181de569b86'::uuid,
    '1c82d05b-5d7b-4783-b110-a9bfce6eb62f'::uuid,
    '560015f8-dac8-4722-a155-a684ae5fe484'::uuid,
    '4d06523c-b440-417e-b3fc-86ed0a77170c'::uuid,
    '4df3ec69-fb65-4d5a-a3c4-b8a4d5c2561c'::uuid,
    'eda4baa9-786b-409e-a89c-ba9fdb495dd9'::uuid,
    '668f12ff-4983-49b9-9bb0-9528079fbf43'::uuid,
    '6e2db03b-1a2f-45a6-83ee-46247db1affa'::uuid,
    '07f40fa8-5ac8-4c22-a19f-1d37ee7c6448'::uuid,
    'ac775cb4-70f8-4d3a-94cb-f0c0abe55c4c'::uuid,
    'ad554cc7-eb4d-4c39-b56d-ef78235e0c7c'::uuid,
    '9854d163-4a79-45d8-ac79-eb50ab81cc7a'::uuid,
    '767909e7-e358-4cba-b7b0-b6723b715b30'::uuid,
    '4d98829f-b027-48a0-a858-01a634eaba5c'::uuid,
    '46f439bb-a829-4d4f-be2e-af630be55cc9'::uuid,
    '8c17d045-30bf-4930-98e9-b9189952fbf0'::uuid,
    'f75774ee-b54d-4213-a07e-0b98c61155d5'::uuid,
    '5b0496b7-126d-412f-b052-44e2751648a2'::uuid,
    'f856d039-5bc3-4f1d-92dd-6d11eb1b1c06'::uuid,
    '0d0bf5c0-a5c1-4c9a-bdd2-ffbe655c3568'::uuid,
    '1eb63335-91e0-4b5d-a933-cb42046a62a5'::uuid,
    'b148f69b-5375-4ccc-825c-5c0589b4300a'::uuid,
    '366ba576-2b4f-43c0-9708-d24bf458c5d7'::uuid
  );

  if v_gone <> 0 then
    raise exception 'ABORT: % delete-set rows still present after DELETE', v_gone;
  end if;

  select count(*) into v_backup
  from public.monthly_plan_draft_lines_backup_legacy_202607
  where cleanup_batch_id = '8775a015-6847-492c-b5cb-2e8f21ac192f'::uuid;

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
-- where draft_id = '661d5ffe-5851-4a27-8b4b-e01d16929798'::uuid;
--
-- select line_id, boq_code, planned_qty, crew_id, facility_building,
--        client_line_uid, plan_line_id, line_status
-- from public.monthly_plan_draft_lines
-- where line_id = 'c90c5f21-e9e5-45c8-93e2-940dbc4fe862'::uuid;
--
-- select cleanup_action, count(*)
-- from public.monthly_plan_draft_lines_backup_legacy_202607
-- where cleanup_batch_id = '8775a015-6847-492c-b5cb-2e8f21ac192f'::uuid
-- group by cleanup_action;
--
-- select count(*) as plan_rows
-- from public.monthly_plan_lines_v2
-- where project_code = 'PRJ_001_БХК'
--   and month_key = 'июль-2026';
