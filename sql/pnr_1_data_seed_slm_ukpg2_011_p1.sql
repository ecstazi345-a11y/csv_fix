-- =============================================================================
-- PNR-1 DATA SEED — SLM / УКПГ2-011 / Вентиляция / ПНР / П-1
-- =============================================================================
-- File:    sql/pnr_1_data_seed_slm_ukpg2_011_p1.sql
-- STATUS:  REVIEW DRAFT — DO NOT EXECUTE
-- Deploy:  Supabase SQL Editor MANUALLY, and only after explicit human
--          authorization of this review draft. Not executed by the app.
--          PNR-1 catalog tables are service_role SELECT-only; this seed
--          is table-owner SQL, not PostgREST.
--
-- Project:          PRJ_001_SLM / Салмановское месторождение
-- Title:            УКПГ2-011 / УКПГ2-011
-- Discipline:       VENTILATION / Вентиляция
-- Work Type:        PNR / ПНР
-- Physical system:  existing system_id 4ab41ec1-f88e-4514-a07d-6c72f5ba212f
--                   legacy system_code P1 (not renamed)
-- Canonical alias:  П-1  (alias_kind = CANONICAL)
-- First FP:         ШСАУ-P1 / Шкаф системы автоматического управления P1
--                   position_type = PANEL
-- Legacy object:    object_id 1796501a-44a6-4d3a-855b-7ea16b9fdc2c
--                   bridged via pnr_object_position_map LEGACY_EQUIVALENT
--
-- Explicitly out of scope:
--   - PRJ_001_БХК is not touched
--   - historical pnr_execution_events are not touched
--   - no asset / endpoint / connection seed
--   - no schema changes
--   - no Agent Runtime changes
--   - no second physical system
--   - legacy system_code P1 is not rewritten
--
-- Expected effect:
--   +1 eos_projects
--   +1 eos_titles
--   +1 eos_disciplines
--   +1 eos_work_types
--   +1 eos_system_aliases
--   +1 eos_system_work_contexts
--   +1 pnr_functional_positions
--   +1 pnr_object_position_map
--   1 existing eos_systems row: project_id NULL → SLM project UUID
--   Total new rows: 8
--   Existing rows updated: 1
--
-- Provenance:
--   source_type      = ENGINEERING_DECISION
--   source_reference = PNR-1-SEED-SLM-UKPG2-011-P1-v1
--   Human-confirmed architectural mapping for the first PNR-1 production
--   navigation path. Not field discovery, not an import, not MVP catalog copy.
--
-- Idempotency / fail-closed:
--   One transaction. New UUIDs are never hardcoded; they are resolved by
--   stable business keys after a guarded write. Proven historical
--   system_id / object_id are identity guards only.
--   Pattern: INSERT ... SELECT ... WHERE NOT EXISTS (business key),
--   then reload the row and abort unless code+name (and kind/type where
--   applicable) match this contract exactly.
--   Broad ON CONFLICT DO NOTHING is not used: it could accept a
--   semantically incompatible pre-existing row.
--   Safe retry: the exact intended seed may already exist; the script
--   then no-ops those keys.
--   Conflict: same business key with a different name/kind/binding, or
--   the proven P1/object identity drifted, aborts the transaction.
--   Existing P1/ШСАУ-P1 FP is reused only when parent/active/valid_to
--   also match; otherwise abort. No FP rewrite.
--   Historical events are proven independently before writes and again
--   in the terminal post-write block. Events are not written.
-- =============================================================================

begin;

do $seed$
declare
    v_source_type text := 'ENGINEERING_DECISION';
    v_source_ref  text := 'PNR-1-SEED-SLM-UKPG2-011-P1-v1';

    v_system_id uuid := '4ab41ec1-f88e-4514-a07d-6c72f5ba212f';
    v_object_id uuid := '1796501a-44a6-4d3a-855b-7ea16b9fdc2c';

    v_project_id   uuid;
    v_title_id     uuid;
    v_discipline_id uuid;
    v_work_type_id uuid;
    v_position_id  uuid;

    v_project_name     text;
    v_title_name       text;
    v_discipline_code  text;
    v_discipline_name  text;
    v_work_type_code   text;
    v_work_type_name   text;
    v_sys_project_code text;
    v_sys_system_code  text;
    v_sys_system_name  text;
    v_sys_project_id   uuid;
    v_alias_code       text;
    v_alias_kind       text;
    v_context_code     text;
    v_context_system   uuid;
    v_fp_name          text;
    v_fp_type          text;
    v_fp_parent        uuid;
    v_fp_active        boolean;
    v_fp_valid_to      timestamptz;
    v_map_position_id  uuid;
    v_map_system_id    uuid;
    v_map_type         text;
begin
    -- ------------------------------------------------------------------
    -- Identity guards on proven historical rows (read, then lock)
    -- ------------------------------------------------------------------
    select s.project_code, s.system_code, s.system_name, s.project_id
      into v_sys_project_code, v_sys_system_code, v_sys_system_name, v_sys_project_id
      from public.eos_systems s
     where s.system_id = v_system_id
     for update;

    if not found then
        raise exception
            'PNR-1 seed aborted: expected physical system_id % is missing',
            v_system_id;
    end if;

    if v_sys_project_code is distinct from 'PRJ_001_SLM'
       or v_sys_system_code is distinct from 'P1'
       or v_sys_system_name is distinct from 'Система вентиляции P1' then
        raise exception
            'PNR-1 seed aborted: system_id % no longer matches expected P1 identity (project_code=%, system_code=%, system_name=%)',
            v_system_id, v_sys_project_code, v_sys_system_code, v_sys_system_name;
    end if;

    if exists (
        select 1
          from public.eos_systems s
         where s.system_id is distinct from v_system_id
           and s.project_code = 'PRJ_001_SLM'
           and s.system_code = 'P1'
    ) then
        raise exception
            'PNR-1 seed aborted: a second SLM P1 physical system row exists';
    end if;

    perform 1
       from public.pnr_objects o
      where o.object_id = v_object_id
        and o.system_id = v_system_id
        and o.object_code = 'ШСАУ-P1'
        and o.object_name = 'Шкаф системы автоматического управления P1'
        and o.object_kind = 'PANEL'
      for update;

    if not found then
        raise exception
            'PNR-1 seed aborted: expected legacy object ШСАУ-P1 is missing or no longer matches system_id %',
            v_system_id;
    end if;

    perform 1
       from public.pnr_execution_events e
      where e.event_id = '41bd0c13-7eaa-43bd-a7e5-23bb74e58ae9'
        and e.system_id = v_system_id
        and e.object_id = v_object_id
        and e.result = 'FAIL'
        and e.people_count is not distinct from 2
        and e.duration_hours is not distinct from 1.5
        and e.labor_hours is not distinct from 3
      for share;

    if not found then
        raise exception
            'PNR-1 seed aborted: historical FAIL event 41bd0c13-7eaa-43bd-a7e5-23bb74e58ae9 is missing or no longer matches expected identity';
    end if;

    perform 1
       from public.pnr_execution_events e
      where e.event_id = '51f7935e-785a-4f66-9877-af19f821b772'
        and e.system_id = v_system_id
        and e.object_id = v_object_id
        and e.result = 'PASS'
        and e.people_count is not distinct from 2
        and e.duration_hours is not distinct from 0.5
        and e.labor_hours is not distinct from 1
      for share;

    if not found then
        raise exception
            'PNR-1 seed aborted: historical PASS event 51f7935e-785a-4f66-9877-af19f821b772 is missing or no longer matches expected identity';
    end if;

    -- ------------------------------------------------------------------
    -- A. eos_projects
    -- ------------------------------------------------------------------
    insert into public.eos_projects (
        project_code,
        project_name,
        is_active,
        source_type,
        source_reference
    )
    select
        'PRJ_001_SLM',
        'Салмановское месторождение',
        true,
        v_source_type,
        v_source_ref
    where not exists (
        select 1
          from public.eos_projects p
         where p.project_code = 'PRJ_001_SLM'
    );

    select p.project_id, p.project_name
      into v_project_id, v_project_name
      from public.eos_projects p
     where p.project_code = 'PRJ_001_SLM';

    if v_project_id is null then
        raise exception
            'PNR-1 seed aborted: project_code PRJ_001_SLM was not resolved';
    end if;

    if v_project_name is distinct from 'Салмановское месторождение' then
        raise exception
            'PNR-1 seed aborted: project_code PRJ_001_SLM exists with incompatible project_name %',
            v_project_name;
    end if;

    -- ------------------------------------------------------------------
    -- B. eos_titles
    -- ------------------------------------------------------------------
    insert into public.eos_titles (
        project_id,
        title_code,
        title_name,
        is_active,
        source_type,
        source_reference
    )
    select
        v_project_id,
        'УКПГ2-011',
        'УКПГ2-011',
        true,
        v_source_type,
        v_source_ref
    where not exists (
        select 1
          from public.eos_titles t
         where t.project_id = v_project_id
           and t.title_code = 'УКПГ2-011'
    );

    select t.title_id, t.title_name
      into v_title_id, v_title_name
      from public.eos_titles t
     where t.project_id = v_project_id
       and t.title_code = 'УКПГ2-011';

    if v_title_id is null then
        raise exception
            'PNR-1 seed aborted: title УКПГ2-011 under PRJ_001_SLM was not resolved';
    end if;

    if v_title_name is distinct from 'УКПГ2-011' then
        raise exception
            'PNR-1 seed aborted: title_code УКПГ2-011 exists with incompatible title_name %',
            v_title_name;
    end if;

    -- ------------------------------------------------------------------
    -- C. eos_disciplines  (machine code VENTILATION; display Вентиляция)
    -- ------------------------------------------------------------------
    if exists (
        select 1
          from public.eos_disciplines d
         where d.discipline_name = 'Вентиляция'
           and d.discipline_code is distinct from 'VENTILATION'
    ) then
        raise exception
            'PNR-1 seed aborted: discipline Вентиляция already exists under a different discipline_code';
    end if;

    insert into public.eos_disciplines (
        discipline_code,
        discipline_name,
        is_active,
        source_type,
        source_reference
    )
    select
        'VENTILATION',
        'Вентиляция',
        true,
        v_source_type,
        v_source_ref
    where not exists (
        select 1
          from public.eos_disciplines d
         where d.discipline_code = 'VENTILATION'
    );

    select d.discipline_id, d.discipline_code, d.discipline_name
      into v_discipline_id, v_discipline_code, v_discipline_name
      from public.eos_disciplines d
     where d.discipline_code = 'VENTILATION';

    if v_discipline_id is null then
        raise exception
            'PNR-1 seed aborted: discipline_code VENTILATION was not resolved';
    end if;

    if v_discipline_name is distinct from 'Вентиляция' then
        raise exception
            'PNR-1 seed aborted: discipline_code VENTILATION exists with incompatible discipline_name %',
            v_discipline_name;
    end if;

    -- ------------------------------------------------------------------
    -- D. eos_work_types
    -- ------------------------------------------------------------------
    if exists (
        select 1
          from public.eos_work_types w
         where w.work_type_name = 'ПНР'
           and w.work_type_code is distinct from 'PNR'
    ) then
        raise exception
            'PNR-1 seed aborted: work type ПНР already exists under a different work_type_code';
    end if;

    insert into public.eos_work_types (
        work_type_code,
        work_type_name,
        is_active,
        source_type,
        source_reference
    )
    select
        'PNR',
        'ПНР',
        true,
        v_source_type,
        v_source_ref
    where not exists (
        select 1
          from public.eos_work_types w
         where w.work_type_code = 'PNR'
    );

    select w.work_type_id, w.work_type_code, w.work_type_name
      into v_work_type_id, v_work_type_code, v_work_type_name
      from public.eos_work_types w
     where w.work_type_code = 'PNR';

    if v_work_type_id is null then
        raise exception
            'PNR-1 seed aborted: work_type_code PNR was not resolved';
    end if;

    if v_work_type_name is distinct from 'ПНР' then
        raise exception
            'PNR-1 seed aborted: work_type_code PNR exists with incompatible work_type_name %',
            v_work_type_name;
    end if;

    -- ------------------------------------------------------------------
    -- E. eos_systems — backfill project_id only on the proven P1 row
    -- ------------------------------------------------------------------
    if v_sys_project_id is null then
        update public.eos_systems s
           set project_id = v_project_id
         where s.system_id = v_system_id
           and s.project_code = 'PRJ_001_SLM'
           and s.system_code = 'P1'
           and s.project_id is null;

        if not found then
            raise exception
                'PNR-1 seed aborted: P1 project_id backfill did not match the expected identity row';
        end if;
    elsif v_sys_project_id is distinct from v_project_id then
        raise exception
            'PNR-1 seed aborted: P1 system_id % is already bound to a different project_id %',
            v_system_id, v_sys_project_id;
    end if;

    -- ------------------------------------------------------------------
    -- F. eos_system_aliases — canonical П-1 on the existing physical system
    -- ------------------------------------------------------------------
    if exists (
        select 1
          from public.eos_system_aliases a
         where a.system_id = v_system_id
           and a.alias_kind = 'CANONICAL'
           and a.alias_code is distinct from 'П-1'
    ) then
        raise exception
            'PNR-1 seed aborted: P1 already has a different CANONICAL alias';
    end if;

    insert into public.eos_system_aliases (
        system_id,
        alias_code,
        alias_kind,
        source_type,
        source_reference
    )
    select
        v_system_id,
        'П-1',
        'CANONICAL',
        v_source_type,
        v_source_ref
    where not exists (
        select 1
          from public.eos_system_aliases a
         where a.system_id = v_system_id
           and a.alias_code = 'П-1'
    );

    select a.alias_code, a.alias_kind
      into v_alias_code, v_alias_kind
      from public.eos_system_aliases a
     where a.system_id = v_system_id
       and a.alias_code = 'П-1';

    if v_alias_code is null then
        raise exception
            'PNR-1 seed aborted: canonical alias П-1 was not resolved for P1';
    end if;

    if v_alias_kind is distinct from 'CANONICAL' then
        raise exception
            'PNR-1 seed aborted: alias П-1 on P1 exists with incompatible alias_kind %',
            v_alias_kind;
    end if;

    -- ------------------------------------------------------------------
    -- G. eos_system_work_contexts
    -- ------------------------------------------------------------------
    if exists (
        select 1
          from public.eos_system_work_contexts c
         where c.title_id = v_title_id
           and c.discipline_id = v_discipline_id
           and c.work_type_id = v_work_type_id
           and c.context_system_code = 'П-1'
           and c.system_id is distinct from v_system_id
    ) then
        raise exception
            'PNR-1 seed aborted: work-context code П-1 is already bound to a different system_id';
    end if;

    insert into public.eos_system_work_contexts (
        title_id,
        discipline_id,
        work_type_id,
        system_id,
        context_system_code,
        is_active,
        source_type,
        source_reference
    )
    select
        v_title_id,
        v_discipline_id,
        v_work_type_id,
        v_system_id,
        'П-1',
        true,
        v_source_type,
        v_source_ref
    where not exists (
        select 1
          from public.eos_system_work_contexts c
         where c.title_id = v_title_id
           and c.discipline_id = v_discipline_id
           and c.work_type_id = v_work_type_id
           and c.system_id = v_system_id
    );

    select c.context_system_code, c.system_id
      into v_context_code, v_context_system
      from public.eos_system_work_contexts c
     where c.title_id = v_title_id
       and c.discipline_id = v_discipline_id
       and c.work_type_id = v_work_type_id
       and c.system_id = v_system_id;

    if v_context_code is null then
        raise exception
            'PNR-1 seed aborted: work context for УКПГ2-011 / Вентиляция / ПНР / P1 was not resolved';
    end if;

    if v_context_code is distinct from 'П-1'
       or v_context_system is distinct from v_system_id then
        raise exception
            'PNR-1 seed aborted: existing work context is incompatible (context_system_code=%, system_id=%)',
            v_context_code, v_context_system;
    end if;

    -- ------------------------------------------------------------------
    -- H. pnr_functional_positions — preserve legacy ШСАУ-P1 codes
    -- ------------------------------------------------------------------
    insert into public.pnr_functional_positions (
        system_id,
        parent_position_id,
        position_code,
        position_name,
        position_type,
        is_active,
        source_type,
        source_reference
    )
    select
        v_system_id,
        null,
        'ШСАУ-P1',
        'Шкаф системы автоматического управления P1',
        'PANEL',
        true,
        v_source_type,
        v_source_ref
    where not exists (
        select 1
          from public.pnr_functional_positions fp
         where fp.system_id = v_system_id
           and fp.position_code = 'ШСАУ-P1'
    );

    select fp.position_id,
           fp.position_name,
           fp.position_type,
           fp.parent_position_id,
           fp.is_active,
           fp.valid_to
      into v_position_id,
           v_fp_name,
           v_fp_type,
           v_fp_parent,
           v_fp_active,
           v_fp_valid_to
      from public.pnr_functional_positions fp
     where fp.system_id = v_system_id
       and fp.position_code = 'ШСАУ-P1';

    if v_position_id is null then
        raise exception
            'PNR-1 seed aborted: functional position ШСАУ-P1 was not resolved';
    end if;

    if v_fp_name is distinct from 'Шкаф системы автоматического управления P1'
       or v_fp_type is distinct from 'PANEL'
       or v_fp_parent is not null
       or v_fp_active is not true
       or v_fp_valid_to is not null then
        raise exception
            'PNR-1 seed aborted: functional position ШСАУ-P1 exists with incompatible identity (name/type/parent/active/valid_to)';
    end if;

    -- ------------------------------------------------------------------
    -- I. pnr_object_position_map — one legacy bridge, same system_id
    -- ------------------------------------------------------------------
    insert into public.pnr_object_position_map (
        object_id,
        position_id,
        system_id,
        mapping_type,
        source_type,
        source_reference
    )
    select
        v_object_id,
        v_position_id,
        v_system_id,
        'LEGACY_EQUIVALENT',
        v_source_type,
        v_source_ref
    where not exists (
        select 1
          from public.pnr_object_position_map m
         where m.object_id = v_object_id
    );

    select m.position_id, m.system_id, m.mapping_type
      into v_map_position_id, v_map_system_id, v_map_type
      from public.pnr_object_position_map m
     where m.object_id = v_object_id;

    if v_map_position_id is null then
        raise exception
            'PNR-1 seed aborted: object-position map for ШСАУ-P1 was not resolved';
    end if;

    if v_map_position_id is distinct from v_position_id
       or v_map_system_id is distinct from v_system_id
       or v_map_type is distinct from 'LEGACY_EQUIVALENT' then
        raise exception
            'PNR-1 seed aborted: existing object-position map is incompatible';
    end if;

    -- ------------------------------------------------------------------
    -- Terminal post-write proof — fail closed before COMMIT
    -- ------------------------------------------------------------------
    if (
        select count(*)
          from public.eos_projects p
         where p.project_code = 'PRJ_001_SLM'
           and p.project_name = 'Салмановское месторождение'
    ) is distinct from 1 then
        raise exception
            'PNR-1 seed aborted: expected exactly one SLM project row';
    end if;

    if (
        select count(*)
          from public.eos_titles t
         where t.project_id = v_project_id
           and t.title_code = 'УКПГ2-011'
           and t.title_name = 'УКПГ2-011'
    ) is distinct from 1 then
        raise exception
            'PNR-1 seed aborted: expected exactly one УКПГ2-011 title under SLM';
    end if;

    if (
        select count(*)
          from public.eos_disciplines d
         where d.discipline_code = 'VENTILATION'
           and d.discipline_name = 'Вентиляция'
    ) is distinct from 1 then
        raise exception
            'PNR-1 seed aborted: expected exactly one VENTILATION discipline';
    end if;

    if (
        select count(*)
          from public.eos_work_types w
         where w.work_type_code = 'PNR'
           and w.work_type_name = 'ПНР'
    ) is distinct from 1 then
        raise exception
            'PNR-1 seed aborted: expected exactly one PNR work type';
    end if;

    if (
        select count(*)
          from public.eos_systems s
         where s.system_id = v_system_id
           and s.project_code = 'PRJ_001_SLM'
           and s.system_code = 'P1'
           and s.system_name = 'Система вентиляции P1'
           and s.legacy_system_label is null
           and s.project_id = v_project_id
    ) is distinct from 1 then
        raise exception
            'PNR-1 seed aborted: proven P1 identity or project_id binding is not the intended final state';
    end if;

    if (
        select count(*)
          from public.eos_system_aliases a
         where a.system_id = v_system_id
           and a.alias_code = 'П-1'
           and a.alias_kind = 'CANONICAL'
    ) is distinct from 1 then
        raise exception
            'PNR-1 seed aborted: expected exactly one canonical alias П-1 on proven P1';
    end if;

    if (
        select count(*)
          from public.eos_system_work_contexts c
          join public.eos_titles t
            on t.title_id = c.title_id
          join public.eos_projects p
            on p.project_id = t.project_id
          join public.eos_disciplines d
            on d.discipline_id = c.discipline_id
          join public.eos_work_types w
            on w.work_type_id = c.work_type_id
         where p.project_code = 'PRJ_001_SLM'
           and t.title_code = 'УКПГ2-011'
           and d.discipline_code = 'VENTILATION'
           and w.work_type_code = 'PNR'
           and c.system_id = v_system_id
           and c.context_system_code = 'П-1'
    ) is distinct from 1 then
        raise exception
            'PNR-1 seed aborted: expected exactly one SLM / УКПГ2-011 / VENTILATION / PNR / П-1 work context';
    end if;

    if (
        select count(*)
          from public.pnr_functional_positions fp
         where fp.system_id = v_system_id
           and fp.position_code = 'ШСАУ-P1'
           and fp.position_name = 'Шкаф системы автоматического управления P1'
           and fp.position_type = 'PANEL'
           and fp.parent_position_id is null
           and fp.is_active is true
           and fp.valid_to is null
           and fp.position_id = v_position_id
    ) is distinct from 1 then
        raise exception
            'PNR-1 seed aborted: expected exactly one intended ШСАУ-P1 functional position on proven P1';
    end if;

    if (
        select count(*)
          from public.pnr_objects o
         where o.object_id = v_object_id
           and o.system_id = v_system_id
           and o.object_code = 'ШСАУ-P1'
           and o.object_name = 'Шкаф системы автоматического управления P1'
           and o.object_kind = 'PANEL'
    ) is distinct from 1 then
        raise exception
            'PNR-1 seed aborted: historical legacy object ШСАУ-P1 is not the expected final identity';
    end if;

    if (
        select count(*)
          from public.pnr_object_position_map m
         where m.object_id = v_object_id
           and m.system_id = v_system_id
           and m.position_id = v_position_id
           and m.mapping_type = 'LEGACY_EQUIVALENT'
    ) is distinct from 1 then
        raise exception
            'PNR-1 seed aborted: expected exactly one LEGACY_EQUIVALENT bridge from ШСАУ-P1 object to intended FP';
    end if;

    if not exists (
        select 1
          from public.pnr_execution_events e
         where e.event_id = '41bd0c13-7eaa-43bd-a7e5-23bb74e58ae9'
           and e.system_id = v_system_id
           and e.object_id = v_object_id
           and e.result = 'FAIL'
           and e.people_count is not distinct from 2
           and e.duration_hours is not distinct from 1.5
           and e.labor_hours is not distinct from 3
    ) then
        raise exception
            'PNR-1 seed aborted: historical FAIL event identity is not intact after seed writes';
    end if;

    if not exists (
        select 1
          from public.pnr_execution_events e
         where e.event_id = '51f7935e-785a-4f66-9877-af19f821b772'
           and e.system_id = v_system_id
           and e.object_id = v_object_id
           and e.result = 'PASS'
           and e.people_count is not distinct from 2
           and e.duration_hours is not distinct from 0.5
           and e.labor_hours is not distinct from 1
    ) then
        raise exception
            'PNR-1 seed aborted: historical PASS event identity is not intact after seed writes';
    end if;

    raise notice
        'PNR-1 seed contract resolved project_id=% title_id=% discipline_id=% work_type_id=% system_id=% position_id=% object_id=%',
        v_project_id, v_title_id, v_discipline_id, v_work_type_id,
        v_system_id, v_position_id, v_object_id;
end;
$seed$;

commit;
