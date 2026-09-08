-- =============================================================================
-- PNR MVP-0.1 — Minimum physical schema
-- =============================================================================
-- File:    sql/pnr_mvp_0_1.sql
-- Deploy:  Supabase SQL Editor MANUALLY after review. Do NOT auto-run.
--          This file is not executed by the application.
--
-- Tables (exactly five):
--   public.eos_systems
--   public.pnr_objects
--   public.pnr_work_scopes
--   public.pnr_operations
--   public.pnr_execution_events
--
-- Purpose:
--   Smallest schema for FIELD USER → Streamlit → PNR event → journal.
--
-- Intentionally omitted (later increments / architecture):
--   pnr_normative_items, pnr_labor_baselines, mapping tables,
--   pnr_acceptance_*, pnr_event_labor, measurements, evidence,
--   defects, constraints, state engine, signed acceptance.
--
-- Does NOT:
--   - INSERT seed or product data (MVP-0.2)
--   - ALTER existing product tables
--   - reference BOQ / daily_progress / monthly planning
--   - touch Agent Runtime
--
-- Idempotency:
--   CREATE TABLE without IF NOT EXISTS on purpose.
--   Re-run against an incompatible existing object must FAIL visibly
--   rather than skip and hide schema drift.
--   Repository IF NOT EXISTS is used elsewhere for additive product
--   scripts; it is the wrong default for this first PNR cut.
--
-- UUID:
--   default gen_random_uuid() — established in this repository
--   (monthly_plan_lines_v2, daily_progress_form_submissions, …).
--   No extra extension.
--
-- updated_at:
--   Catalog tables: timestamptz not null default now().
--   No trigger functions. Smallest repo-compatible mechanism
--   (same as planning_config / several constraint tables).
--   Per-table updated_at triggers exist elsewhere; they are not
--   required for MVP-0 (catalog seed is INSERT; events are append-only
--   and have no updated_at).
--
-- Cross-system invariant:
--   Composite FK
--     pnr_execution_events(object_id, system_id)
--       → pnr_objects(object_id, system_id)
--   enforces event.system_id = object.system_id without a trigger.
--
-- Labor product:
--   Application (MVP-0.3) computes labor_hours = people_count × duration_hours.
--   No generated column.
--   When all three values are present, a CHECK requires exact numeric
--   equality (integer × numeric is exact; no float).
--   Partial labor (only some of the three columns) is allowed.
--
-- Security:
--   RLS enabled on all five. Zero policies.
--   In PostgreSQL, RLS with no policy denies anon/authenticated.
--   Supabase service_role bypasses RLS; do not invent a service_role
--   policy. Writes go through Streamlit server + SUPABASE_SECRET_KEY.
--   Do NOT copy daily_progress_form_submissions anon INSERT.
--   Catalog and event reads for the future form: server-side PNR
--   service only — no anon/authenticated SELECT grant.
--
--   MVP-0.1B: CREATE TABLE may GRANT ALL to service_role via Supabase
--   default privileges. GRANT SELECT/INSERT does not remove UPDATE/
--   DELETE/TRUNCATE. For pnr_execution_events only: REVOKE ALL FROM
--   service_role, then GRANT SELECT, INSERT. Catalog grants unchanged.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1) eos_systems — shared physical system identity (minimum contract)
--    project_code is a text attribute, not a Project master FK.
-- ---------------------------------------------------------------------------
create table public.eos_systems (
    system_id uuid primary key default gen_random_uuid(),
    project_code text not null,
    system_code text not null,
    system_name text not null,
    legacy_system_label text,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint eos_systems_project_code_chk
        check (length(btrim(project_code)) > 0),
    constraint eos_systems_system_code_chk
        check (length(btrim(system_code)) > 0),
    constraint eos_systems_system_name_chk
        check (length(btrim(system_name)) > 0),
    constraint eos_systems_project_system_code_key
        unique (project_code, system_code)
);

comment on table public.eos_systems is
    'PNR MVP-0.1: shared Execution OS system identity. Not a PNR-only registry. '
    'legacy_system_label is correlation to existing SMR text; not unique.';

comment on column public.eos_systems.project_code is
    'Text project code on the system row. No Project master table.';

comment on column public.eos_systems.legacy_system_label is
    'Optional correlation to existing system / system_label text. Not identity.';

-- ---------------------------------------------------------------------------
-- 2) pnr_objects — commissioning object, one system
-- ---------------------------------------------------------------------------
create table public.pnr_objects (
    object_id uuid primary key default gen_random_uuid(),
    system_id uuid not null
        references public.eos_systems (system_id),
    object_code text not null,
    object_name text not null,
    object_kind text not null,
    parent_object_id uuid
        references public.pnr_objects (object_id),
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pnr_objects_object_code_chk
        check (length(btrim(object_code)) > 0),
    constraint pnr_objects_object_name_chk
        check (length(btrim(object_name)) > 0),
    constraint pnr_objects_object_kind_chk
        check (object_kind in (
            'SYSTEM_COMPONENT',
            'EQUIPMENT',
            'PANEL',
            'DEVICE',
            'NETWORK',
            'LOOP',
            'OTHER'
        )),
    constraint pnr_objects_parent_not_self_chk
        check (parent_object_id is null or parent_object_id <> object_id),
    constraint pnr_objects_system_code_key
        unique (system_id, object_code),
    -- Target for event composite FK (same-system invariant).
    constraint pnr_objects_id_system_key
        unique (object_id, system_id)
);

comment on table public.pnr_objects is
    'PNR MVP-0.1: commissioning object belonging to one system. '
    'parent_object_id is optional; not a hierarchy engine.';

comment on column public.pnr_objects.object_kind is
    'v0.1: SYSTEM_COMPONENT | EQUIPMENT | PANEL | DEVICE | NETWORK | LOOP | OTHER.';

-- ---------------------------------------------------------------------------
-- 3) pnr_work_scopes — reusable catalog vocabulary (not per-system)
-- ---------------------------------------------------------------------------
create table public.pnr_work_scopes (
    work_scope_id uuid primary key default gen_random_uuid(),
    scope_code text not null,
    scope_name text not null,
    sequence_no integer,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pnr_work_scopes_scope_code_chk
        check (length(btrim(scope_code)) > 0),
    constraint pnr_work_scopes_scope_name_chk
        check (length(btrim(scope_name)) > 0),
    constraint pnr_work_scopes_scope_code_key
        unique (scope_code)
);

comment on table public.pnr_work_scopes is
    'PNR MVP-0.1: reusable work-scope catalog. No system_id.';

-- ---------------------------------------------------------------------------
-- 4) pnr_operations — reusable operation catalog
-- ---------------------------------------------------------------------------
create table public.pnr_operations (
    operation_id uuid primary key default gen_random_uuid(),
    operation_code text not null,
    work_scope_id uuid not null
        references public.pnr_work_scopes (work_scope_id),
    operation_name text not null,
    sequence_no integer,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pnr_operations_operation_code_chk
        check (length(btrim(operation_code)) > 0),
    constraint pnr_operations_operation_name_chk
        check (length(btrim(operation_name)) > 0),
    constraint pnr_operations_operation_code_key
        unique (operation_code)
);

comment on table public.pnr_operations is
    'PNR MVP-0.1: reusable operation catalog. No normative / BOQ / actual / acceptance fields.';

-- ---------------------------------------------------------------------------
-- 5) pnr_execution_events — append-oriented attempts
--    No business UNIQUE on (object, operation, time).
--    FAIL then PASS = two rows.
--    service_role: SELECT+INSERT only (REVOKE ALL then GRANT; no UPDATE/DELETE/TRUNCATE).
-- ---------------------------------------------------------------------------
create table public.pnr_execution_events (
    event_id uuid primary key default gen_random_uuid(),
    system_id uuid not null
        references public.eos_systems (system_id),
    object_id uuid not null,
    operation_id uuid
        references public.pnr_operations (operation_id),
    unmapped_operation_name text,
    result text not null,
    occurred_at timestamptz not null,
    people_count integer,
    duration_hours numeric,
    labor_hours numeric,
    reason text,
    comment text,
    source text not null default 'STREAMLIT',
    created_at timestamptz not null default now(),
    constraint pnr_execution_events_object_system_fk
        foreign key (object_id, system_id)
        references public.pnr_objects (object_id, system_id),
    constraint pnr_execution_events_result_chk
        check (result in ('PASS', 'FAIL', 'PARTIAL', 'BLOCKED')),
    constraint pnr_execution_events_operation_xor_chk
        check (
            (
                operation_id is not null
                and unmapped_operation_name is null
            )
            or (
                operation_id is null
                and unmapped_operation_name is not null
                and length(btrim(unmapped_operation_name)) > 0
            )
        ),
    constraint pnr_execution_events_people_count_chk
        check (people_count is null or people_count > 0),
    constraint pnr_execution_events_duration_hours_chk
        check (duration_hours is null or duration_hours >= 0),
    constraint pnr_execution_events_labor_hours_chk
        check (labor_hours is null or labor_hours >= 0),
    -- When people and duration are both set, labor_hours must be their
    -- exact numeric product. No generated column; app still computes
    -- the value. Partial triples remain allowed.
    constraint pnr_execution_events_labor_product_chk
        check (
            people_count is null
            or duration_hours is null
            or (
                labor_hours is not null
                and labor_hours = (people_count::numeric * duration_hours)
            )
        ),
    constraint pnr_execution_events_source_chk
        check (length(btrim(source)) > 0)
);

comment on table public.pnr_execution_events is
    'PNR MVP-0.1: append-only commissioning attempt. '
    'No upsert key. Catalogued XOR unmapped operation. '
    'labor_hours is a total, not pnr_event_labor.';

comment on column public.pnr_execution_events.unmapped_operation_name is
    'Required when operation_id is null. Blank/whitespace rejected. No UNKNOWN catalog row.';

comment on column public.pnr_execution_events.source is
    'Capture path. Default STREAMLIT. Server-side form only.';

-- ---------------------------------------------------------------------------
-- Indexes (MVP read/write path only)
-- unique (system_id, object_code) already supports objects-by-system.
-- ---------------------------------------------------------------------------
create index idx_pnr_operations_work_scope_id
    on public.pnr_operations (work_scope_id);

create index idx_pnr_execution_events_occurred_at
    on public.pnr_execution_events (occurred_at desc);

create index idx_pnr_execution_events_system_id
    on public.pnr_execution_events (system_id);

create index idx_pnr_execution_events_object_id
    on public.pnr_execution_events (object_id);

-- ---------------------------------------------------------------------------
-- RLS + grants
-- No CREATE POLICY — anon/authenticated denied by empty RLS.
-- service_role bypasses RLS (Supabase); table DML is grant-based.
-- ---------------------------------------------------------------------------
alter table public.eos_systems enable row level security;
alter table public.pnr_objects enable row level security;
alter table public.pnr_work_scopes enable row level security;
alter table public.pnr_operations enable row level security;
alter table public.pnr_execution_events enable row level security;

revoke all on table public.eos_systems from public;
revoke all on table public.pnr_objects from public;
revoke all on table public.pnr_work_scopes from public;
revoke all on table public.pnr_operations from public;
revoke all on table public.pnr_execution_events from public;

revoke all on table public.eos_systems from anon, authenticated;
revoke all on table public.pnr_objects from anon, authenticated;
revoke all on table public.pnr_work_scopes from anon, authenticated;
revoke all on table public.pnr_operations from anon, authenticated;
revoke all on table public.pnr_execution_events from anon, authenticated;

grant select on table public.eos_systems to service_role;
grant select on table public.pnr_objects to service_role;
grant select on table public.pnr_work_scopes to service_role;
grant select on table public.pnr_operations to service_role;

-- Events: strip CREATE TABLE default ALL (incl. UPDATE/DELETE/TRUNCATE),
-- then grant append-only. Catalog service_role grants are not touched.
revoke all on table public.pnr_execution_events from service_role;
grant select, insert on table public.pnr_execution_events to service_role;
