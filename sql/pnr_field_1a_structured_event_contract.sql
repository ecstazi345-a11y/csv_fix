-- =============================================================================
-- FIELD-1A — Structured physical event contract
-- =============================================================================
-- File:    sql/pnr_field_1a_structured_event_contract.sql
-- Status:  SQL DRAFT. Review before any database apply.
-- Deploy:  Supabase SQL Editor MANUALLY after explicit authorization.
--          This file is not executed by the application.
--          This increment does not apply the file.
--
-- Additive only. MVP-0 pnr_execution_events rows are not rewritten.
-- result remains NOT NULL with the existing PASS/FAIL/PARTIAL/BLOCKED CHECK.
-- New event columns are nullable with no defaults that reinterpret history.
--
-- Adds:
--   five nullable columns on public.pnr_execution_events
--   public.pnr_event_measurements
--   public.pnr_event_blocked_details
--   public.pnr_event_partial_details
--
-- Does not:
--   - INSERT / UPDATE / DELETE product rows
--   - backfill execution_status / evaluation_status
--   - rename or drop result
--   - create RPC / functions / triggers
--   - create evidence, pnr_constraints, deficiencies
--   - change Agent Runtime or BHK
--   - broaden existing pnr_execution_events grants
--   - ON DELETE CASCADE
--
-- Helper UNIQUE proof (PostgreSQL FK rule: referenced columns must be a
-- non-deferrable UNIQUE or PRIMARY KEY):
--   pnr_functional_positions already has unique (position_id, system_id)
--     = constraint pnr_fp_id_system_key in
--       sql/pnr_1_physical_and_work_context_foundation.sql
--     → no new UNIQUE on that table.
--   pnr_execution_events PK is event_id only.
--     Composite FKs onto (event_id, system_id), (event_id, object_id),
--     and (event_id, execution_status) therefore require those UNIQUE
--     keys here. They are implied by the PK semantically; PostgreSQL
--     still needs the explicit UNIQUE for the FK catalog.
--     Sidecars attach via execution_status, not legacy result.
-- =============================================================================

-- ###########################################################################
-- 1) Additive nullable columns on pnr_execution_events
-- ###########################################################################
alter table public.pnr_execution_events
    add column functional_position_id uuid,
    add column execution_status text,
    add column evaluation_status text,
    add column observation_text text,
    add column retry_of_event_id uuid;

comment on column public.pnr_execution_events.functional_position_id is
    'FIELD-1A: optional functional position. Same-system composite FK. '
    'Historical rows stay NULL. Not required to equal pnr_object_position_map.';

comment on column public.pnr_execution_events.execution_status is
    'FIELD-1A: execution attempt state. NULL = MVP-0 / historical row.';

comment on column public.pnr_execution_events.evaluation_status is
    'FIELD-1A: professional evaluation. NULL = MVP-0 / historical row.';

comment on column public.pnr_execution_events.observation_text is
    'FIELD-1A: observed fact. Not diagnosis, root cause, or comment replacement.';

comment on column public.pnr_execution_events.retry_of_event_id is
    'FIELD-1A: prior attempt. Same system and object. Not a graph engine.';

-- Enum CHECKs: NULL allowed.
alter table public.pnr_execution_events
    add constraint pnr_execution_events_execution_status_chk
        check (
            execution_status is null
            or execution_status in (
                'COMPLETED',
                'NOT_COMPLETED',
                'PARTIAL',
                'BLOCKED'
            )
        );

alter table public.pnr_execution_events
    add constraint pnr_execution_events_evaluation_status_chk
        check (
            evaluation_status is null
            or evaluation_status in (
                'CONFORMS',
                'DOES_NOT_CONFORM',
                'NOT_EVALUATED'
            )
        );

-- Pair law: both NULL (legacy) OR both set to one valid combination
-- with matching legacy result. Existing result CHECK is unchanged.
alter table public.pnr_execution_events
    add constraint pnr_execution_events_status_pair_chk
        check (
            (
                execution_status is null
                and evaluation_status is null
            )
            or (
                execution_status is not null
                and evaluation_status is not null
                and (
                    (
                        execution_status = 'COMPLETED'
                        and evaluation_status = 'CONFORMS'
                        and result = 'PASS'
                    )
                    or (
                        execution_status = 'COMPLETED'
                        and evaluation_status = 'NOT_EVALUATED'
                        and result = 'PASS'
                    )
                    or (
                        execution_status = 'COMPLETED'
                        and evaluation_status = 'DOES_NOT_CONFORM'
                        and result = 'FAIL'
                    )
                    or (
                        execution_status = 'NOT_COMPLETED'
                        and evaluation_status = 'NOT_EVALUATED'
                        and result = 'FAIL'
                    )
                    or (
                        execution_status = 'PARTIAL'
                        and evaluation_status = 'NOT_EVALUATED'
                        and result = 'PARTIAL'
                    )
                    or (
                        execution_status = 'PARTIAL'
                        and evaluation_status = 'DOES_NOT_CONFORM'
                        and result = 'PARTIAL'
                    )
                    or (
                        execution_status = 'BLOCKED'
                        and evaluation_status = 'NOT_EVALUATED'
                        and result = 'BLOCKED'
                    )
                )
            )
        );

alter table public.pnr_execution_events
    add constraint pnr_execution_events_observation_text_chk
        check (
            observation_text is null
            or length(btrim(observation_text)) > 0
        );

alter table public.pnr_execution_events
    add constraint pnr_execution_events_retry_not_self_chk
        check (
            retry_of_event_id is null
            or retry_of_event_id <> event_id
        );

-- Helper UNIQUE keys required for composite FKs (see header proof).
alter table public.pnr_execution_events
    add constraint pnr_execution_events_id_system_key
        unique (event_id, system_id);

alter table public.pnr_execution_events
    add constraint pnr_execution_events_id_object_key
        unique (event_id, object_id);

alter table public.pnr_execution_events
    add constraint pnr_execution_events_id_execution_status_key
        unique (event_id, execution_status);

-- Same-system FP. Referenced unique already exists: pnr_fp_id_system_key.
-- MATCH SIMPLE: (NULL, system_id) is not required to match.
alter table public.pnr_execution_events
    add constraint pnr_execution_events_fp_system_fk
        foreign key (functional_position_id, system_id)
        references public.pnr_functional_positions (position_id, system_id)
        on delete no action;

alter table public.pnr_execution_events
    add constraint pnr_execution_events_retry_of_fk
        foreign key (retry_of_event_id)
        references public.pnr_execution_events (event_id)
        on delete no action;

alter table public.pnr_execution_events
    add constraint pnr_execution_events_retry_system_fk
        foreign key (retry_of_event_id, system_id)
        references public.pnr_execution_events (event_id, system_id)
        on delete no action;

alter table public.pnr_execution_events
    add constraint pnr_execution_events_retry_object_fk
        foreign key (retry_of_event_id, object_id)
        references public.pnr_execution_events (event_id, object_id)
        on delete no action;

create index idx_pnr_execution_events_functional_position_id
    on public.pnr_execution_events (functional_position_id);

create index idx_pnr_execution_events_retry_of_event_id
    on public.pnr_execution_events (retry_of_event_id);

-- ###########################################################################
-- 2) pnr_event_measurements — raw physical readings, 0..N per event
-- ###########################################################################
create table public.pnr_event_measurements (
    measurement_id uuid primary key default gen_random_uuid(),
    event_id uuid not null,
    parameter_code text,
    parameter_name text not null,
    value numeric not null,
    unit text not null,
    measurement_point text,
    instrument_text text,
    recorded_at timestamptz not null,
    created_at timestamptz not null default now(),
    constraint pnr_event_measurements_event_fk
        foreign key (event_id)
        references public.pnr_execution_events (event_id)
        on delete no action,
    constraint pnr_event_measurements_parameter_code_chk
        check (
            parameter_code is null
            or length(btrim(parameter_code)) > 0
        ),
    constraint pnr_event_measurements_parameter_name_chk
        check (length(btrim(parameter_name)) > 0),
    constraint pnr_event_measurements_unit_chk
        check (length(btrim(unit)) > 0),
    constraint pnr_event_measurements_point_chk
        check (
            measurement_point is null
            or length(btrim(measurement_point)) > 0
        ),
    constraint pnr_event_measurements_instrument_chk
        check (
            instrument_text is null
            or length(btrim(instrument_text)) > 0
        )
);

comment on table public.pnr_event_measurements is
    'FIELD-1A: raw measurements for one execution attempt. '
    'Not a catalog, instrument registry, or criteria engine. Duplicates allowed.';

create index idx_pnr_event_measurements_event_id
    on public.pnr_event_measurements (event_id);

-- ###########################################################################
-- 3) pnr_event_blocked_details — 1:1 capture, not pnr_constraints
-- ###########################################################################
create table public.pnr_event_blocked_details (
    event_id uuid primary key,
    execution_status text not null,
    constraint_category text not null,
    constraint_description text,
    other_work_available boolean,
    created_at timestamptz not null default now(),
    constraint pnr_event_blocked_details_execution_status_chk
        check (execution_status = 'BLOCKED'),
    constraint pnr_event_blocked_details_event_execution_status_fk
        foreign key (event_id, execution_status)
        references public.pnr_execution_events (event_id, execution_status)
        on delete no action,
    constraint pnr_event_blocked_details_category_chk
        check (constraint_category in (
            'DOCUMENTATION',
            'CONSTRUCTION_READINESS',
            'ADJACENT_WORK',
            'MATERIALS',
            'EQUIPMENT',
            'POWER_SUPPLY',
            'WORKING_MEDIUM',
            'OBJECT_ACCESS',
            'PERMIT_SAFETY',
            'PERSONNEL',
            'INSTRUMENT',
            'AUTOMATION_SOFTWARE',
            'THIRD_PARTY_DECISION',
            'WEATHER_EXTERNAL',
            'OTHER'
        )),
    constraint pnr_event_blocked_details_description_chk
        check (
            (
                constraint_description is null
                or length(btrim(constraint_description)) > 0
            )
            and (
                constraint_category <> 'OTHER'
                or (
                    constraint_description is not null
                    and length(btrim(constraint_description)) > 0
                )
            )
        )
);

comment on table public.pnr_event_blocked_details is
    'FIELD-1A: field capture of a BLOCKED attempt. Not a constraint lifecycle. '
    'Parent must have execution_status = BLOCKED (composite FK). No trigger.';

-- ###########################################################################
-- 4) pnr_event_partial_details — 1:1 capture, not a quantity engine
-- ###########################################################################
create table public.pnr_event_partial_details (
    event_id uuid primary key,
    execution_status text not null,
    completed_text text not null,
    remaining_text text not null,
    created_at timestamptz not null default now(),
    constraint pnr_event_partial_details_execution_status_chk
        check (execution_status = 'PARTIAL'),
    constraint pnr_event_partial_details_event_execution_status_fk
        foreign key (event_id, execution_status)
        references public.pnr_execution_events (event_id, execution_status)
        on delete no action,
    constraint pnr_event_partial_details_completed_chk
        check (length(btrim(completed_text)) > 0),
    constraint pnr_event_partial_details_remaining_chk
        check (length(btrim(remaining_text)) > 0)
);

comment on table public.pnr_event_partial_details is
    'FIELD-1A: completed / remaining text for a PARTIAL attempt. '
    'Parent must have execution_status = PARTIAL (composite FK). No trigger.';

-- ###########################################################################
-- 5) RLS + grants — new tables only
--    Existing pnr_execution_events grants are not broadened.
-- ###########################################################################
alter table public.pnr_event_measurements enable row level security;
alter table public.pnr_event_blocked_details enable row level security;
alter table public.pnr_event_partial_details enable row level security;

revoke all on table public.pnr_event_measurements from public;
revoke all on table public.pnr_event_blocked_details from public;
revoke all on table public.pnr_event_partial_details from public;

revoke all on table public.pnr_event_measurements from anon, authenticated;
revoke all on table public.pnr_event_blocked_details from anon, authenticated;
revoke all on table public.pnr_event_partial_details from anon, authenticated;

revoke all on table public.pnr_event_measurements from service_role;
revoke all on table public.pnr_event_blocked_details from service_role;
revoke all on table public.pnr_event_partial_details from service_role;

grant select, insert on table public.pnr_event_measurements to service_role;
grant select, insert on table public.pnr_event_blocked_details to service_role;
grant select, insert on table public.pnr_event_partial_details to service_role;
