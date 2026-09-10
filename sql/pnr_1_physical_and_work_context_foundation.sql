-- =============================================================================
-- PNR-1 — Physical identity + work-context foundation
-- =============================================================================
-- File:    sql/pnr_1_physical_and_work_context_foundation.sql
-- Status:  SQL DRAFT. Review before any database apply.
-- Deploy:  Supabase SQL Editor MANUALLY after explicit authorization.
--          This file is not executed by the application.
--          This increment does not apply the file.
--
-- Creates shared production-navigation catalogs and PNR physical graph.
-- Additive only. Existing MVP-0 tables stay in place.
--
-- User / production navigation (work context, not physical parent chain):
--   PROJECT → TITLE → DISCIPLINE → WORK TYPE → SYSTEM
--
-- Physical identity:
--   PROJECT → SYSTEM → FUNCTIONAL POSITION → ASSET INSTANCE
--   FUNCTIONAL POSITION → ENDPOINT ↔ ENDPOINT (connection)
--
-- Law: one physical system = one eos_systems.system_id.
-- Discipline / work type never duplicate П-1.
--
-- Does not:
--   - write product rows
--   - touch pnr_execution_events / pnr_objects / pnr_work_scopes /
--     pnr_operations structure
--   - add title_id on eos_systems
--   - create pnr_systems
--   - map facility_building or construction_discipline
--   - implement document / acceptance / evidence
--   - change MVP-0 event grants
--
-- UUID: default gen_random_uuid() — same convention as sql/pnr_mvp_0_1.sql.
-- No extra extension.
--
-- Security:
--   RLS on every new table. Zero policies.
--   anon / authenticated denied.
--   service_role: SELECT only after stripping default ALL.
--   Physical registry write is not a field path.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Shared provenance vocabulary (lightweight; not a provenance subsystem)
-- ---------------------------------------------------------------------------
-- PROJECT_DOCUMENT | RD | MANUFACTURER | FIELD_DISCOVERY | LEGACY_MVP |
-- IMPORT | ENGINEERING_DECISION

-- ###########################################################################
-- 1) eos_projects — shared Execution OS project registry
-- ###########################################################################
create table public.eos_projects (
    project_id uuid primary key default gen_random_uuid(),
    project_code text not null,
    project_name text not null,
    is_active boolean not null default true,
    source_type text not null default 'ENGINEERING_DECISION',
    source_reference text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint eos_projects_project_code_chk
        check (length(btrim(project_code)) > 0),
    constraint eos_projects_project_name_chk
        check (length(btrim(project_name)) > 0),
    constraint eos_projects_source_type_chk
        check (source_type in (
            'PROJECT_DOCUMENT',
            'RD',
            'MANUFACTURER',
            'FIELD_DISCOVERY',
            'LEGACY_MVP',
            'IMPORT',
            'ENGINEERING_DECISION'
        )),
    constraint eos_projects_project_code_key
        unique (project_code)
);

comment on table public.eos_projects is
    'PNR-1: shared Execution OS project registry. Not PNR-owned. '
    'Soft project_code on existing product tables is not rewritten here.';

-- ###########################################################################
-- 2) eos_titles — title inside a project
-- ###########################################################################
create table public.eos_titles (
    title_id uuid primary key default gen_random_uuid(),
    project_id uuid not null references public.eos_projects (project_id),
    title_code text not null,
    title_name text not null,
    is_active boolean not null default true,
    source_type text not null default 'ENGINEERING_DECISION',
    source_reference text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint eos_titles_title_code_chk
        check (length(btrim(title_code)) > 0),
    constraint eos_titles_title_name_chk
        check (length(btrim(title_name)) > 0),
    constraint eos_titles_source_type_chk
        check (source_type in (
            'PROJECT_DOCUMENT',
            'RD',
            'MANUFACTURER',
            'FIELD_DISCOVERY',
            'LEGACY_MVP',
            'IMPORT',
            'ENGINEERING_DECISION'
        )),
    constraint eos_titles_project_code_key
        unique (project_id, title_code)
);

comment on table public.eos_titles is
    'PNR-1: construction/organizational title under a project. '
    'Not facility_building. No automatic facility mapping.';

-- ###########################################################################
-- 3) eos_disciplines — shared work-context catalog
-- ###########################################################################
create table public.eos_disciplines (
    discipline_id uuid primary key default gen_random_uuid(),
    discipline_code text not null,
    discipline_name text not null,
    is_active boolean not null default true,
    source_type text not null default 'ENGINEERING_DECISION',
    source_reference text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint eos_disciplines_discipline_code_chk
        check (length(btrim(discipline_code)) > 0),
    constraint eos_disciplines_discipline_name_chk
        check (length(btrim(discipline_name)) > 0),
    constraint eos_disciplines_source_type_chk
        check (source_type in (
            'PROJECT_DOCUMENT',
            'RD',
            'MANUFACTURER',
            'FIELD_DISCOVERY',
            'LEGACY_MVP',
            'IMPORT',
            'ENGINEERING_DECISION'
        )),
    constraint eos_disciplines_discipline_code_key
        unique (discipline_code)
);

comment on table public.eos_disciplines is
    'PNR-1: shared discipline catalog (ОВ, КИПиА, ЭОМ, …). '
    'Work context only. Never a parent of eos_systems.';

-- ###########################################################################
-- 4) eos_work_types — shared execution-contour catalog
-- ###########################################################################
create table public.eos_work_types (
    work_type_id uuid primary key default gen_random_uuid(),
    work_type_code text not null,
    work_type_name text not null,
    is_active boolean not null default true,
    source_type text not null default 'ENGINEERING_DECISION',
    source_reference text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint eos_work_types_work_type_code_chk
        check (length(btrim(work_type_code)) > 0),
    constraint eos_work_types_work_type_name_chk
        check (length(btrim(work_type_name)) > 0),
    constraint eos_work_types_source_type_chk
        check (source_type in (
            'PROJECT_DOCUMENT',
            'RD',
            'MANUFACTURER',
            'FIELD_DISCOVERY',
            'LEGACY_MVP',
            'IMPORT',
            'ENGINEERING_DECISION'
        )),
    constraint eos_work_types_work_type_code_key
        unique (work_type_code)
);

comment on table public.eos_work_types is
    'PNR-1: shared work-type catalog (СМР, ПНР, future types). '
    'Not PNR work scope, not discipline, not operation, not stage.';

-- ###########################################################################
-- 5) eos_systems — additive nullable project_id only
--    Existing UNIQUE(project_code, system_code) kept.
--    No title_id. Physical system is not owned by one title.
-- ###########################################################################
alter table public.eos_systems
    add column project_id uuid references public.eos_projects (project_id);

comment on column public.eos_systems.project_id is
    'PNR-1 additive nullable FK to eos_projects. '
    'Existing project_code text remains. Live P1 row is not rewritten.';

-- ###########################################################################
-- 6) eos_system_aliases — labels for one physical system_id
--    No project-wide unique alias_code (two titles may both show П-1
--    as different system_id values).
-- ###########################################################################
create table public.eos_system_aliases (
    alias_id uuid primary key default gen_random_uuid(),
    system_id uuid not null references public.eos_systems (system_id),
    alias_code text not null,
    alias_kind text not null,
    source_type text not null default 'ENGINEERING_DECISION',
    source_reference text,
    created_at timestamptz not null default now(),
    constraint eos_system_aliases_alias_code_chk
        check (length(btrim(alias_code)) > 0),
    constraint eos_system_aliases_alias_kind_chk
        check (alias_kind in (
            'SOURCE',
            'CANONICAL',
            'SMR_LABEL',
            'VENDOR',
            'OTHER'
        )),
    constraint eos_system_aliases_source_type_chk
        check (source_type in (
            'PROJECT_DOCUMENT',
            'RD',
            'MANUFACTURER',
            'FIELD_DISCOVERY',
            'LEGACY_MVP',
            'IMPORT',
            'ENGINEERING_DECISION'
        )),
    constraint eos_system_aliases_system_code_key
        unique (system_id, alias_code)
);

comment on table public.eos_system_aliases is
    'PNR-1: multiple labels for one eos_systems.system_id. '
    'CANONICAL is the user-facing code (e.g. П-1). '
    'MVP system_code (e.g. P1) is not renamed by this file.';

create unique index eos_system_aliases_one_canonical_uidx
    on public.eos_system_aliases (system_id)
    where alias_kind = 'CANONICAL';

-- ###########################################################################
-- 7) eos_system_work_contexts — production contour of a physical system
--    Project is derived: context → title → project.
-- ###########################################################################
create table public.eos_system_work_contexts (
    system_work_context_id uuid primary key default gen_random_uuid(),
    title_id uuid not null references public.eos_titles (title_id),
    discipline_id uuid not null references public.eos_disciplines (discipline_id),
    work_type_id uuid not null references public.eos_work_types (work_type_id),
    system_id uuid not null references public.eos_systems (system_id),
    context_system_code text not null,
    is_active boolean not null default true,
    source_type text not null default 'ENGINEERING_DECISION',
    source_reference text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint eos_system_work_contexts_code_chk
        check (length(btrim(context_system_code)) > 0),
    constraint eos_system_work_contexts_source_type_chk
        check (source_type in (
            'PROJECT_DOCUMENT',
            'RD',
            'MANUFACTURER',
            'FIELD_DISCOVERY',
            'LEGACY_MVP',
            'IMPORT',
            'ENGINEERING_DECISION'
        )),
    constraint eos_system_work_contexts_contour_system_key
        unique (title_id, discipline_id, work_type_id, system_id),
    constraint eos_system_work_contexts_contour_code_key
        unique (title_id, discipline_id, work_type_id, context_system_code)
);

comment on table public.eos_system_work_contexts is
    'PNR-1: one physical system in one title + discipline + work type. '
    'Navigation path, not a second physical system. '
    'Same context_system_code in different titles may be different system_id.';

create index eos_system_work_contexts_system_id_idx
    on public.eos_system_work_contexts (system_id);

create index eos_system_work_contexts_title_id_idx
    on public.eos_system_work_contexts (title_id);

-- ###########################################################################
-- 8) pnr_functional_positions
-- ###########################################################################
create table public.pnr_functional_positions (
    position_id uuid primary key default gen_random_uuid(),
    system_id uuid not null references public.eos_systems (system_id),
    parent_position_id uuid,
    position_code text not null,
    position_name text not null,
    position_type text not null,
    is_active boolean not null default true,
    valid_from timestamptz not null default now(),
    valid_to timestamptz,
    source_type text not null default 'ENGINEERING_DECISION',
    source_reference text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pnr_fp_position_code_chk
        check (length(btrim(position_code)) > 0),
    constraint pnr_fp_position_name_chk
        check (length(btrim(position_name)) > 0),
    constraint pnr_fp_position_type_chk
        check (position_type in (
            'PANEL',
            'EQUIPMENT_SLOT',
            'INSTRUMENT',
            'ACTUATOR',
            'ASSEMBLY',
            'NETWORK_NODE',
            'OTHER'
        )),
    constraint pnr_fp_source_type_chk
        check (source_type in (
            'PROJECT_DOCUMENT',
            'RD',
            'MANUFACTURER',
            'FIELD_DISCOVERY',
            'LEGACY_MVP',
            'IMPORT',
            'ENGINEERING_DECISION'
        )),
    constraint pnr_fp_valid_range_chk
        check (valid_to is null or valid_to > valid_from),
    constraint pnr_fp_parent_not_self_chk
        check (parent_position_id is null or parent_position_id <> position_id),
    constraint pnr_fp_system_code_key
        unique (system_id, position_code),
    constraint pnr_fp_id_system_key
        unique (position_id, system_id),
    constraint pnr_fp_parent_same_system_fk
        foreign key (parent_position_id, system_id) references public.pnr_functional_positions (position_id, system_id)
);

comment on table public.pnr_functional_positions is
    'PNR-1: stable functional position inside one system. '
    'Not an asset instance. Not pnr_objects. No discipline/work_type.';

create index pnr_fp_system_id_idx
    on public.pnr_functional_positions (system_id);

create index pnr_fp_parent_position_id_idx
    on public.pnr_functional_positions (parent_position_id);

-- ###########################################################################
-- 9) pnr_object_position_map — legacy object → FP
--    PK object_id: at most one production interpretation per legacy object.
--    position_id is not unique: many objects may point at one FP.
-- ###########################################################################
create table public.pnr_object_position_map (
    object_id uuid primary key,
    position_id uuid not null,
    system_id uuid not null,
    mapping_type text not null,
    source_type text not null default 'LEGACY_MVP',
    source_reference text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pnr_object_position_map_mapping_type_chk
        check (mapping_type = 'LEGACY_EQUIVALENT'),
    constraint pnr_object_position_map_source_type_chk
        check (source_type in (
            'PROJECT_DOCUMENT',
            'RD',
            'MANUFACTURER',
            'FIELD_DISCOVERY',
            'LEGACY_MVP',
            'IMPORT',
            'ENGINEERING_DECISION'
        )),
    constraint pnr_object_position_map_object_system_fk
        foreign key (object_id, system_id) references public.pnr_objects (object_id, system_id),
    constraint pnr_object_position_map_position_system_fk
        foreign key (position_id, system_id) references public.pnr_functional_positions (position_id, system_id)
);

comment on table public.pnr_object_position_map is
    'PNR-1: legacy pnr_objects.object_id → one functional position. '
    'Historical execution events keep object_id. No event rewrite.';

create index pnr_object_position_map_position_id_idx
    on public.pnr_object_position_map (position_id);

-- ###########################################################################
-- 10) pnr_asset_instances
--     Elementary FP: at most one currently installed instance
--     (removed_at is null). Assemblies use child positions.
-- ###########################################################################
create table public.pnr_asset_instances (
    asset_id uuid primary key default gen_random_uuid(),
    position_id uuid not null,
    system_id uuid not null,
    asset_type text not null,
    manufacturer text,
    model text,
    serial_number text,
    installed_at timestamptz not null,
    removed_at timestamptz,
    configuration_data jsonb,
    source_type text not null default 'ENGINEERING_DECISION',
    source_reference text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pnr_asset_instances_asset_type_chk
        check (length(btrim(asset_type)) > 0),
    constraint pnr_asset_instances_source_type_chk
        check (source_type in (
            'PROJECT_DOCUMENT',
            'RD',
            'MANUFACTURER',
            'FIELD_DISCOVERY',
            'LEGACY_MVP',
            'IMPORT',
            'ENGINEERING_DECISION'
        )),
    constraint pnr_asset_instances_removed_after_installed_chk
        check (removed_at is null or removed_at > installed_at),
    constraint pnr_asset_instances_configuration_data_chk
        check (
            configuration_data is null
            or jsonb_typeof(configuration_data) = 'object'
        ),
    constraint pnr_asset_instances_position_system_fk
        foreign key (position_id, system_id) references public.pnr_functional_positions (position_id, system_id)
);

comment on table public.pnr_asset_instances is
    'PNR-1: installed physical instance occupying a functional position. '
    'Current occupancy truth is removed_at IS NULL. serial_number is not identity. '
    'Historical events are not backfilled.';

create index pnr_asset_instances_position_installed_idx
    on public.pnr_asset_instances (position_id, installed_at);

create unique index pnr_asset_instances_one_current_uidx
    on public.pnr_asset_instances (position_id)
    where removed_at is null;

-- ###########################################################################
-- 11) pnr_connection_endpoints
--     Cable/core are attributes on connections, not endpoint kinds in v1.
-- ###########################################################################
create table public.pnr_connection_endpoints (
    endpoint_id uuid primary key default gen_random_uuid(),
    system_id uuid not null references public.eos_systems (system_id),
    position_id uuid,
    endpoint_code text not null,
    endpoint_name text,
    endpoint_kind text not null,
    is_active boolean not null default true,
    valid_from timestamptz not null default now(),
    valid_to timestamptz,
    source_type text not null default 'ENGINEERING_DECISION',
    source_reference text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pnr_ce_endpoint_code_chk
        check (length(btrim(endpoint_code)) > 0),
    constraint pnr_ce_endpoint_kind_chk
        check (endpoint_kind in (
            'DEVICE_PORT',
            'TERMINAL',
            'IO_CHANNEL',
            'CONNECTOR',
            'NETWORK_PORT',
            'OTHER'
        )),
    constraint pnr_ce_source_type_chk
        check (source_type in (
            'PROJECT_DOCUMENT',
            'RD',
            'MANUFACTURER',
            'FIELD_DISCOVERY',
            'LEGACY_MVP',
            'IMPORT',
            'ENGINEERING_DECISION'
        )),
    constraint pnr_ce_valid_range_chk
        check (valid_to is null or valid_to > valid_from),
    constraint pnr_ce_id_system_key
        unique (endpoint_id, system_id),
    constraint pnr_ce_position_system_fk
        foreign key (position_id, system_id) references public.pnr_functional_positions (position_id, system_id)
);

comment on table public.pnr_connection_endpoints is
    'PNR-1: reusable connection-graph node. Usually owned by a position. '
    'position_id null = system-level node. No CABLE_CORE kind in v1.';

create unique index pnr_ce_position_code_uidx
    on public.pnr_connection_endpoints (system_id, position_id, endpoint_code)
    where position_id is not null;

create unique index pnr_ce_system_code_uidx
    on public.pnr_connection_endpoints (system_id, endpoint_code)
    where position_id is null;

create index pnr_ce_system_id_idx
    on public.pnr_connection_endpoints (system_id);

create index pnr_ce_position_id_idx
    on public.pnr_connection_endpoints (position_id);

-- ###########################################################################
-- 12) pnr_connections — versioned directed edge, same system
-- ###########################################################################
create table public.pnr_connections (
    connection_id uuid primary key default gen_random_uuid(),
    system_id uuid not null references public.eos_systems (system_id),
    source_endpoint_id uuid not null,
    destination_endpoint_id uuid not null,
    connection_type text not null,
    cable_reference text,
    core_reference text,
    signal_type text,
    design_reference text,
    design_revision text,
    supersedes_connection_id uuid,
    valid_from timestamptz not null default now(),
    valid_to timestamptz,
    source_type text not null default 'ENGINEERING_DECISION',
    source_reference text,
    created_at timestamptz not null default now(),
    constraint pnr_connections_type_chk
        check (connection_type in (
            'PHYSICAL',
            'SIGNAL',
            'CONTROL',
            'NETWORK',
            'PROCESS',
            'OTHER'
        )),
    constraint pnr_connections_source_type_chk
        check (source_type in (
            'PROJECT_DOCUMENT',
            'RD',
            'MANUFACTURER',
            'FIELD_DISCOVERY',
            'LEGACY_MVP',
            'IMPORT',
            'ENGINEERING_DECISION'
        )),
    constraint pnr_connections_not_loop_chk
        check (source_endpoint_id <> destination_endpoint_id),
    constraint pnr_connections_valid_range_chk
        check (valid_to is null or valid_to > valid_from),
    constraint pnr_connections_not_self_supersede_chk
        check (
            supersedes_connection_id is null
            or supersedes_connection_id <> connection_id
        ),
    constraint pnr_connections_id_system_key
        unique (connection_id, system_id),
    constraint pnr_connections_source_endpoint_fk
        foreign key (source_endpoint_id, system_id) references public.pnr_connection_endpoints (endpoint_id, system_id),
    constraint pnr_connections_dest_endpoint_fk
        foreign key (destination_endpoint_id, system_id) references public.pnr_connection_endpoints (endpoint_id, system_id),
    constraint pnr_connections_supersedes_same_system_fk
        foreign key (supersedes_connection_id, system_id) references public.pnr_connections (connection_id, system_id)
);

comment on table public.pnr_connections is
    'PNR-1: directed versioned edge between endpoints of one system. '
    'Current truth is valid_to IS NULL. Revision = close valid_to on the old row '
    'and add a new row that supersedes only a same-system connection. '
    'cable_reference / core_reference are attributes, not a cable BOM.';

create unique index pnr_connections_current_edge_uidx
    on public.pnr_connections (
        source_endpoint_id,
        destination_endpoint_id,
        connection_type
    )
    where valid_to is null;

create index pnr_connections_system_id_idx
    on public.pnr_connections (system_id);

create index pnr_connections_source_endpoint_id_idx
    on public.pnr_connections (source_endpoint_id);

create index pnr_connections_dest_endpoint_id_idx
    on public.pnr_connections (destination_endpoint_id);

-- ###########################################################################
-- RLS + grants — new tables only
-- Zero policies. Strip CREATE TABLE default ALL on service_role, then SELECT.
-- Existing pnr_execution_events grants are not changed.
-- ###########################################################################
alter table public.eos_projects enable row level security;
alter table public.eos_titles enable row level security;
alter table public.eos_disciplines enable row level security;
alter table public.eos_work_types enable row level security;
alter table public.eos_system_aliases enable row level security;
alter table public.eos_system_work_contexts enable row level security;
alter table public.pnr_functional_positions enable row level security;
alter table public.pnr_object_position_map enable row level security;
alter table public.pnr_asset_instances enable row level security;
alter table public.pnr_connection_endpoints enable row level security;
alter table public.pnr_connections enable row level security;

revoke all on table public.eos_projects from public;
revoke all on table public.eos_titles from public;
revoke all on table public.eos_disciplines from public;
revoke all on table public.eos_work_types from public;
revoke all on table public.eos_system_aliases from public;
revoke all on table public.eos_system_work_contexts from public;
revoke all on table public.pnr_functional_positions from public;
revoke all on table public.pnr_object_position_map from public;
revoke all on table public.pnr_asset_instances from public;
revoke all on table public.pnr_connection_endpoints from public;
revoke all on table public.pnr_connections from public;

revoke all on table public.eos_projects from anon, authenticated;
revoke all on table public.eos_titles from anon, authenticated;
revoke all on table public.eos_disciplines from anon, authenticated;
revoke all on table public.eos_work_types from anon, authenticated;
revoke all on table public.eos_system_aliases from anon, authenticated;
revoke all on table public.eos_system_work_contexts from anon, authenticated;
revoke all on table public.pnr_functional_positions from anon, authenticated;
revoke all on table public.pnr_object_position_map from anon, authenticated;
revoke all on table public.pnr_asset_instances from anon, authenticated;
revoke all on table public.pnr_connection_endpoints from anon, authenticated;
revoke all on table public.pnr_connections from anon, authenticated;

revoke all on table public.eos_projects from service_role;
revoke all on table public.eos_titles from service_role;
revoke all on table public.eos_disciplines from service_role;
revoke all on table public.eos_work_types from service_role;
revoke all on table public.eos_system_aliases from service_role;
revoke all on table public.eos_system_work_contexts from service_role;
revoke all on table public.pnr_functional_positions from service_role;
revoke all on table public.pnr_object_position_map from service_role;
revoke all on table public.pnr_asset_instances from service_role;
revoke all on table public.pnr_connection_endpoints from service_role;
revoke all on table public.pnr_connections from service_role;

grant select on table public.eos_projects to service_role;
grant select on table public.eos_titles to service_role;
grant select on table public.eos_disciplines to service_role;
grant select on table public.eos_work_types to service_role;
grant select on table public.eos_system_aliases to service_role;
grant select on table public.eos_system_work_contexts to service_role;
grant select on table public.pnr_functional_positions to service_role;
grant select on table public.pnr_object_position_map to service_role;
grant select on table public.pnr_asset_instances to service_role;
grant select on table public.pnr_connection_endpoints to service_role;
grant select on table public.pnr_connections to service_role;
