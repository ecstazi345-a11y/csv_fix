-- =============================================================================
-- FIELD-1A — POST-MIGRATION LIVE DATABASE PROOF (READ-ONLY)
-- =============================================================================
-- File:    sql/pnr_field_1a_post_migration_live_proof.sql
-- Run:     paste into Supabase SQL Editor MANUALLY.
-- Mode:    SELECT / catalog inspection ONLY.
--
-- Do NOT: INSERT, UPDATE, DELETE, ALTER, CREATE, DROP, GRANT, REVOKE,
--         TRUNCATE, NOTIFY, seed, or rerun the FIELD-1A migration.
--
-- Expected specification (source, not live proof):
--   sql/pnr_field_1a_structured_event_contract.sql
-- This script inspects live PostgreSQL metadata independently.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1) pnr_execution_events extension columns
-- ---------------------------------------------------------------------------
select
    '1_event_extension_columns' as proof_section,
    c.column_name,
    c.data_type,
    c.udt_name,
    c.is_nullable,
    c.column_default
from information_schema.columns c
where c.table_schema = 'public'
  and c.table_name = 'pnr_execution_events'
  and c.column_name in (
      'functional_position_id',
      'execution_status',
      'evaluation_status',
      'observation_text',
      'retry_of_event_id'
  )
order by c.ordinal_position;

-- ---------------------------------------------------------------------------
-- 2) STATUS CHECK CONTRACT — live pg_get_constraintdef
--    Expected name: pnr_execution_events_status_pair_chk
--    Also return every CHECK on the table so enum / observation / retry
--    CHECKs are visible. Semantic flags are derived from the LIVE definition.
-- ---------------------------------------------------------------------------
select
    '2_status_pair_check_definition' as proof_section,
    con.conname as constraint_name,
    pg_get_constraintdef(con.oid) as constraint_definition
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = rel.relnamespace
where nsp.nspname = 'public'
  and rel.relname = 'pnr_execution_events'
  and con.contype = 'c'
  and con.conname = 'pnr_execution_events_status_pair_chk';

select
    '2b_status_pair_semantic_flags' as proof_section,
    con.conname as constraint_name,
    def.definition,
    (
        def.definition ilike '%execution_status is null%'
        and def.definition ilike '%evaluation_status is null%'
    ) as has_both_null_historical,
    (
        def.definition ilike '%execution_status is not null%'
        and def.definition ilike '%evaluation_status is not null%'
    ) as has_both_nonnull_branch,
    (
        def.definition ilike '%execution_status%COMPLETED%'
        and def.definition ilike '%evaluation_status%CONFORMS%'
        and def.definition ilike '%result%PASS%'
    ) as has_completed_conforms_pass,
    (
        def.definition ilike '%execution_status%COMPLETED%'
        and def.definition ilike '%evaluation_status%NOT_EVALUATED%'
        and def.definition ilike '%result%PASS%'
    ) as has_completed_not_evaluated_pass,
    (
        def.definition ilike '%execution_status%COMPLETED%'
        and def.definition ilike '%evaluation_status%DOES_NOT_CONFORM%'
        and def.definition ilike '%result%FAIL%'
    ) as has_completed_does_not_conform_fail,
    (
        def.definition ilike '%execution_status%NOT_COMPLETED%'
        and def.definition ilike '%evaluation_status%NOT_EVALUATED%'
        and def.definition ilike '%result%FAIL%'
    ) as has_not_completed_not_evaluated_fail,
    (
        def.definition ilike '%execution_status%PARTIAL%'
        and def.definition ilike '%evaluation_status%NOT_EVALUATED%'
        and def.definition ilike '%result%PARTIAL%'
    ) as has_partial_not_evaluated_partial,
    (
        def.definition ilike '%execution_status%PARTIAL%'
        and def.definition ilike '%evaluation_status%DOES_NOT_CONFORM%'
        and def.definition ilike '%result%PARTIAL%'
    ) as has_partial_does_not_conform_partial,
    (
        def.definition ilike '%execution_status%BLOCKED%'
        and def.definition ilike '%evaluation_status%NOT_EVALUATED%'
        and def.definition ilike '%result%BLOCKED%'
    ) as has_blocked_not_evaluated_blocked
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = rel.relnamespace
cross join lateral (
    select pg_get_constraintdef(con.oid) as definition
) def
where nsp.nspname = 'public'
  and rel.relname = 'pnr_execution_events'
  and con.contype = 'c'
  and con.conname = 'pnr_execution_events_status_pair_chk';

select
    '2c_all_event_check_constraints' as proof_section,
    con.conname as constraint_name,
    pg_get_constraintdef(con.oid) as constraint_definition
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = rel.relnamespace
where nsp.nspname = 'public'
  and rel.relname = 'pnr_execution_events'
  and con.contype = 'c'
order by con.conname;

-- ---------------------------------------------------------------------------
-- 3) HELPER UNIQUES
--    Expected live UNIQUE:
--      (event_id, system_id)
--      (event_id, object_id)
--      (event_id, execution_status)
--    Must NOT exist as FIELD-1A helper UNIQUE (event_id, result).
-- ---------------------------------------------------------------------------
select
    '3_event_unique_constraints' as proof_section,
    con.conname as constraint_name,
    pg_get_constraintdef(con.oid) as constraint_definition,
    regexp_replace(
        pg_get_constraintdef(con.oid),
        '\s+',
        ' ',
        'g'
    ) ~* 'unique \(event_id, system_id\)'
        as is_event_id_system_id,
    regexp_replace(
        pg_get_constraintdef(con.oid),
        '\s+',
        ' ',
        'g'
    ) ~* 'unique \(event_id, object_id\)'
        as is_event_id_object_id,
    regexp_replace(
        pg_get_constraintdef(con.oid),
        '\s+',
        ' ',
        'g'
    ) ~* 'unique \(event_id, execution_status\)'
        as is_event_id_execution_status,
    regexp_replace(
        pg_get_constraintdef(con.oid),
        '\s+',
        ' ',
        'g'
    ) ~* 'unique \(event_id, result\)'
        as is_event_id_result_unique
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = rel.relnamespace
where nsp.nspname = 'public'
  and rel.relname = 'pnr_execution_events'
  and con.contype = 'u'
order by con.conname;

select
    '3b_helper_unique_presence' as proof_section,
    exists (
        select 1
        from pg_constraint con
        join pg_class rel on rel.oid = con.conrelid
        join pg_namespace nsp on nsp.oid = rel.relnamespace
        where nsp.nspname = 'public'
          and rel.relname = 'pnr_execution_events'
          and con.contype = 'u'
          and regexp_replace(pg_get_constraintdef(con.oid), '\s+', ' ', 'g')
              ~* 'unique \(event_id, system_id\)'
    ) as has_unique_event_id_system_id,
    exists (
        select 1
        from pg_constraint con
        join pg_class rel on rel.oid = con.conrelid
        join pg_namespace nsp on nsp.oid = rel.relnamespace
        where nsp.nspname = 'public'
          and rel.relname = 'pnr_execution_events'
          and con.contype = 'u'
          and regexp_replace(pg_get_constraintdef(con.oid), '\s+', ' ', 'g')
              ~* 'unique \(event_id, object_id\)'
    ) as has_unique_event_id_object_id,
    exists (
        select 1
        from pg_constraint con
        join pg_class rel on rel.oid = con.conrelid
        join pg_namespace nsp on nsp.oid = rel.relnamespace
        where nsp.nspname = 'public'
          and rel.relname = 'pnr_execution_events'
          and con.contype = 'u'
          and regexp_replace(pg_get_constraintdef(con.oid), '\s+', ' ', 'g')
              ~* 'unique \(event_id, execution_status\)'
    ) as has_unique_event_id_execution_status,
    exists (
        select 1
        from pg_constraint con
        join pg_class rel on rel.oid = con.conrelid
        join pg_namespace nsp on nsp.oid = rel.relnamespace
        where nsp.nspname = 'public'
          and rel.relname = 'pnr_execution_events'
          and con.contype = 'u'
          and regexp_replace(pg_get_constraintdef(con.oid), '\s+', ' ', 'g')
              ~* 'unique \(event_id, result\)'
    ) as has_unique_event_id_result;

-- ---------------------------------------------------------------------------
-- 4) FUNCTIONAL POSITION FK
--    (functional_position_id, system_id)
--      -> pnr_functional_positions(position_id, system_id)
-- ---------------------------------------------------------------------------
select
    '4_functional_position_fk' as proof_section,
    con.conname as constraint_name,
    pg_get_constraintdef(con.oid) as constraint_definition,
    nsp_ref.nspname as referenced_schema,
    rel_ref.relname as referenced_table
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = rel.relnamespace
left join pg_class rel_ref on rel_ref.oid = con.confrelid
left join pg_namespace nsp_ref on nsp_ref.oid = rel_ref.relnamespace
where nsp.nspname = 'public'
  and rel.relname = 'pnr_execution_events'
  and con.contype = 'f'
  and (
      con.conname = 'pnr_execution_events_fp_system_fk'
      or pg_get_constraintdef(con.oid) ilike
         '%(functional_position_id, system_id)%pnr_functional_positions%(position_id, system_id)%'
  )
order by con.conname;

-- ---------------------------------------------------------------------------
-- 5) RETRY FKs + no-self CHECK
--    same-system, same-object, no self-retry.
--    Do NOT expect same-operation at DB level.
-- ---------------------------------------------------------------------------
select
    '5_retry_fk_and_check' as proof_section,
    con.conname as constraint_name,
    case con.contype
        when 'f' then 'FOREIGN KEY'
        when 'c' then 'CHECK'
        else con.contype::text
    end as constraint_type,
    pg_get_constraintdef(con.oid) as constraint_definition
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = rel.relnamespace
where nsp.nspname = 'public'
  and rel.relname = 'pnr_execution_events'
  and (
      con.conname in (
          'pnr_execution_events_retry_of_fk',
          'pnr_execution_events_retry_system_fk',
          'pnr_execution_events_retry_object_fk',
          'pnr_execution_events_retry_not_self_chk'
      )
      or (
          con.contype = 'f'
          and pg_get_constraintdef(con.oid) ilike '%retry_of_event_id%'
      )
      or (
          con.contype = 'c'
          and pg_get_constraintdef(con.oid) ilike '%retry_of_event_id%event_id%'
      )
  )
order by con.contype, con.conname;

-- ---------------------------------------------------------------------------
-- 6) pnr_event_measurements
-- ---------------------------------------------------------------------------
select
    '6_measurements_table_exists' as proof_section,
    to_regclass('public.pnr_event_measurements') as table_regclass,
    c.relrowsecurity as rls_enabled,
    c.relforcerowsecurity as rls_forced
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname = 'pnr_event_measurements';

select
    '6b_measurements_columns' as proof_section,
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default
from information_schema.columns
where table_schema = 'public'
  and table_name = 'pnr_event_measurements'
order by ordinal_position;

select
    '6c_measurements_constraints' as proof_section,
    con.conname as constraint_name,
    case con.contype
        when 'p' then 'PRIMARY KEY'
        when 'f' then 'FOREIGN KEY'
        when 'c' then 'CHECK'
        when 'u' then 'UNIQUE'
        else con.contype::text
    end as constraint_type,
    pg_get_constraintdef(con.oid) as constraint_definition
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = rel.relnamespace
where nsp.nspname = 'public'
  and rel.relname = 'pnr_event_measurements'
order by con.contype, con.conname;

select
    '6d_measurements_indexes' as proof_section,
    i.relname as index_name,
    ix.indisunique as is_unique,
    ix.indisprimary as is_primary,
    pg_get_indexdef(ix.indexrelid) as index_definition
from pg_index ix
join pg_class t on t.oid = ix.indrelid
join pg_class i on i.oid = ix.indexrelid
join pg_namespace nsp on nsp.oid = t.relnamespace
where nsp.nspname = 'public'
  and t.relname = 'pnr_event_measurements'
order by i.relname;

-- ---------------------------------------------------------------------------
-- 7) pnr_event_blocked_details
-- ---------------------------------------------------------------------------
select
    '7_blocked_table_exists' as proof_section,
    to_regclass('public.pnr_event_blocked_details') as table_regclass,
    c.relrowsecurity as rls_enabled,
    c.relforcerowsecurity as rls_forced
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname = 'pnr_event_blocked_details';

select
    '7b_blocked_columns' as proof_section,
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default
from information_schema.columns
where table_schema = 'public'
  and table_name = 'pnr_event_blocked_details'
order by ordinal_position;

select
    '7c_blocked_constraints' as proof_section,
    con.conname as constraint_name,
    case con.contype
        when 'p' then 'PRIMARY KEY'
        when 'f' then 'FOREIGN KEY'
        when 'c' then 'CHECK'
        when 'u' then 'UNIQUE'
        else con.contype::text
    end as constraint_type,
    pg_get_constraintdef(con.oid) as constraint_definition
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = rel.relnamespace
where nsp.nspname = 'public'
  and rel.relname = 'pnr_event_blocked_details'
order by con.contype, con.conname;

-- ---------------------------------------------------------------------------
-- 8) pnr_event_partial_details
-- ---------------------------------------------------------------------------
select
    '8_partial_table_exists' as proof_section,
    to_regclass('public.pnr_event_partial_details') as table_regclass,
    c.relrowsecurity as rls_enabled,
    c.relforcerowsecurity as rls_forced
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname = 'pnr_event_partial_details';

select
    '8b_partial_columns' as proof_section,
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default
from information_schema.columns
where table_schema = 'public'
  and table_name = 'pnr_event_partial_details'
order by ordinal_position;

select
    '8c_partial_constraints' as proof_section,
    con.conname as constraint_name,
    case con.contype
        when 'p' then 'PRIMARY KEY'
        when 'f' then 'FOREIGN KEY'
        when 'c' then 'CHECK'
        when 'u' then 'UNIQUE'
        else con.contype::text
    end as constraint_type,
    pg_get_constraintdef(con.oid) as constraint_definition
from pg_constraint con
join pg_class rel on rel.oid = con.conrelid
join pg_namespace nsp on nsp.oid = rel.relnamespace
where nsp.nspname = 'public'
  and rel.relname = 'pnr_event_partial_details'
order by con.contype, con.conname;

-- ---------------------------------------------------------------------------
-- 9) SECURITY — live RLS + privileges for the three new tables
--    Expected:
--      RLS enabled = YES
--      PUBLIC / anon / authenticated = NONE
--      service_role = SELECT + INSERT only
--    Owner (postgres) privileges may still appear; inspect all grantees.
-- ---------------------------------------------------------------------------
select
    '9_rls_state' as proof_section,
    n.nspname as table_schema,
    c.relname as table_name,
    c.relrowsecurity as rls_enabled,
    c.relforcerowsecurity as rls_forced,
    (
        select count(*)
        from pg_policy p
        where p.polrelid = c.oid
    ) as policy_count
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname in (
      'pnr_event_measurements',
      'pnr_event_blocked_details',
      'pnr_event_partial_details'
  )
order by c.relname;

select
    '9b_all_grantees' as proof_section,
    g.table_name,
    g.grantee,
    g.privilege_type,
    g.is_grantable
from information_schema.role_table_grants g
where g.table_schema = 'public'
  and g.table_name in (
      'pnr_event_measurements',
      'pnr_event_blocked_details',
      'pnr_event_partial_details'
  )
order by g.table_name, g.grantee, g.privilege_type;

select
    '9c_privilege_matrix' as proof_section,
    e.table_name,
    e.role_name,
    e.privilege_type,
    e.expected_allowed,
    (a.privilege_type is not null) as actually_granted,
    case
        when e.expected_allowed and a.privilege_type is not null then 'OK'
        when (not e.expected_allowed) and a.privilege_type is null then 'OK'
        else 'MISMATCH'
    end as check_result
from (
    select t.table_name, r.role_name, p.privilege_type, x.expected_allowed
    from (
        values
            ('pnr_event_measurements'),
            ('pnr_event_blocked_details'),
            ('pnr_event_partial_details')
    ) as t(table_name)
    cross join (
        values
            ('PUBLIC'),
            ('anon'),
            ('authenticated'),
            ('service_role')
    ) as r(role_name)
    cross join (
        values
            ('SELECT'),
            ('INSERT'),
            ('UPDATE'),
            ('DELETE'),
            ('TRUNCATE'),
            ('REFERENCES'),
            ('TRIGGER')
    ) as p(privilege_type)
    cross join lateral (
        select
            (
                r.role_name = 'service_role'
                and p.privilege_type in ('SELECT', 'INSERT')
            ) as expected_allowed
    ) as x
) e
left join information_schema.role_table_grants a
  on a.table_schema = 'public'
 and a.table_name = e.table_name
 and a.grantee = e.role_name
 and a.privilege_type = e.privilege_type
order by e.table_name, e.role_name, e.privilege_type;

-- ---------------------------------------------------------------------------
-- 10) HISTORICAL MVP-0 EVENTS — safe fields only
-- ---------------------------------------------------------------------------
select
    '10_historical_events_presence' as proof_section,
    v.expected_event_id,
    (e.event_id is not null) as present
from (
    values
        ('41bd0c13-7eaa-43bd-a7e5-23bb74e58ae9'::uuid),
        ('51f7935e-785a-4f66-9877-af19f821b772'::uuid)
) as v(expected_event_id)
left join public.pnr_execution_events e
  on e.event_id = v.expected_event_id
order by v.expected_event_id;

select
    '10b_historical_events_safe_fields' as proof_section,
    e.event_id,
    e.system_id,
    e.object_id,
    e.operation_id,
    e.result,
    e.execution_status,
    e.evaluation_status,
    e.functional_position_id,
    e.retry_of_event_id,
    e.people_count,
    e.duration_hours,
    e.labor_hours,
    e.source
from public.pnr_execution_events e
where e.event_id in (
    '41bd0c13-7eaa-43bd-a7e5-23bb74e58ae9'::uuid,
    '51f7935e-785a-4f66-9877-af19f821b772'::uuid
)
order by e.event_id;

-- ---------------------------------------------------------------------------
-- 11) EVENT COUNT SAFETY
--     Known MVP-0 baseline before FIELD-1A = 2.
--     If count <> 2, do not auto-declare corruption; review required.
-- ---------------------------------------------------------------------------
select
    '11_event_count' as proof_section,
    count(*) as pnr_execution_events_count,
    count(*) filter (
        where event_id in (
            '41bd0c13-7eaa-43bd-a7e5-23bb74e58ae9'::uuid,
            '51f7935e-785a-4f66-9877-af19f821b772'::uuid
        )
    ) as known_mvp0_event_count,
    case
        when count(*) = 2 then 'MATCHES_MVP0_BASELINE_2'
        else 'REVIEW_REQUIRED_COUNT_NOT_2'
    end as count_review_flag
from public.pnr_execution_events;

-- ---------------------------------------------------------------------------
-- 12) NO FIELD-1A PRODUCT DATA in new sidecar tables
--     Expected immediately after schema-only migration: 0 / 0 / 0
-- ---------------------------------------------------------------------------
select
    '12_sidecar_row_counts' as proof_section,
    (select count(*) from public.pnr_event_measurements) as pnr_event_measurements_count,
    (select count(*) from public.pnr_event_blocked_details) as pnr_event_blocked_details_count,
    (select count(*) from public.pnr_event_partial_details) as pnr_event_partial_details_count;
