-- =============================================================================
-- FIELD-1D.1C — Work scope ↔ canonical operation M:N bridge
-- =============================================================================
-- File:    sql/pnr_field_1d_1c_work_scope_operation_bridge.sql
-- Status:  SQL DRAFT. Review before any database apply.
-- Deploy:  Supabase SQL Editor MANUALLY after explicit authorization.
--          This file is not executed by the application.
--          This increment does not apply the file.
--
-- OPTION A (FIELD-1D.1B):
--   Keep public.pnr_operations.work_scope_id NOT NULL.
--   Keep the legacy FIELD-1C read path
--     list_active_operations(work_scope_id) → pnr_operations.work_scope_id.
--   Add public.pnr_work_scope_operations as the evolutionary M:N catalog
--   membership relation.
--
-- Additive catalog foundation only.
-- Backfill copies existing pnr_operations ownership into the bridge
-- (work_scope_id, operation_id, sequence_no, is_active) without naming
-- live UUIDs. Existing AUT_ALGORITHMS ↔ PNR-AUT-003 membership is
-- therefore included if those catalog rows exist.
--
-- Does not:
--   - ALTER / UPDATE / DELETE pnr_operations
--   - UPDATE / DELETE / INSERT pnr_execution_events
--   - add work_scope_id on events
--   - seed 9 professional scopes or 47 canonical operations
--   - seed P-1 physical objects / functional positions
--   - change FIELD-1A / FIELD-1B
--   - create RPC / functions / triggers / policies
--   - grant INSERT/UPDATE/DELETE on the new table
-- =============================================================================

-- ###########################################################################
-- 1) public.pnr_work_scope_operations
-- ###########################################################################
begin;

create table public.pnr_work_scope_operations (
    work_scope_id uuid not null,
    operation_id uuid not null,
    sequence_no integer,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pnr_work_scope_operations_pkey
        primary key (work_scope_id, operation_id),
    constraint pnr_work_scope_operations_work_scope_fk
        foreign key (work_scope_id)
        references public.pnr_work_scopes (work_scope_id)
        on delete no action,
    constraint pnr_work_scope_operations_operation_fk
        foreign key (operation_id)
        references public.pnr_operations (operation_id)
        on delete no action
);

comment on table public.pnr_work_scope_operations is
    'FIELD-1D.1C: M:N catalog membership of a canonical operation in a '
    'work scope. Not object applicability. Not execution context. '
    'pnr_operations.work_scope_id remains the legacy 1:1 owner.';

comment on column public.pnr_work_scope_operations.sequence_no is
    'Display order of the operation inside this work scope. Nullable. Not unique.';

comment on column public.pnr_work_scope_operations.is_active is
    'Membership active flag. Independent of later retiring one scope link '
    'without deleting the canonical operation.';

-- ###########################################################################
-- 2) Legacy ownership backfill — INSERT-only, no hardcoded catalog UUIDs
-- ###########################################################################
insert into public.pnr_work_scope_operations (
    work_scope_id,
    operation_id,
    sequence_no,
    is_active
)
select
    o.work_scope_id,
    o.operation_id,
    o.sequence_no,
    o.is_active
from public.pnr_operations o
where o.work_scope_id is not null
  and not exists (
      select 1
        from public.pnr_work_scope_operations m
       where m.work_scope_id = o.work_scope_id
         and m.operation_id = o.operation_id
  );

-- ###########################################################################
-- 3) RLS + grants — catalog SELECT-only, zero policies
-- ###########################################################################
alter table public.pnr_work_scope_operations enable row level security;

revoke all on table public.pnr_work_scope_operations from public;
revoke all on table public.pnr_work_scope_operations from anon, authenticated;
revoke all on table public.pnr_work_scope_operations from service_role;
grant select on table public.pnr_work_scope_operations to service_role;

commit;
