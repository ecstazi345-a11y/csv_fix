-- =============================================================================
-- Professional П-1 Foundation Seed v1.0 — REVIEW DRAFT
-- =============================================================================
-- File:    sql/pnr_professional_p1_foundation_seed_v1.sql
-- Status:  SQL DRAFT. DO NOT EXECUTE until explicit human authorization.
-- Deploy:  Supabase SQL Editor MANUALLY after review.
--          Not executed by the application.
--          Catalog tables are service_role SELECT-only; this seed is
--          table-owner SQL, not PostgREST.
--
-- Seeds exactly:
--   8 professional Work Scopes
--   15 canonical commissioning operations
--   42 approved M:N memberships (pnr_work_scope_operations)
--
-- Does NOT:
--   - UPDATE / DELETE / ALTER / DROP / TRUNCATE
--   - INSERT pnr_execution_events
--   - create Section 09 / acceptance / commercial / payment
--   - create П-1.1 / П-1.2 / assets / endpoints / scenarios / Required Work
--   - rename, deactivate, or remap AUT_ALGORITHMS / PNR-AUT-003
--   - add PNR-AUT-003 to scope 03
--   - use ON CONFLICT DO NOTHING (semantic collisions must fail closed)
--
-- Idempotency:
--   INSERT ... SELECT WHERE NOT EXISTS on stable business codes.
--   After write, the row must match this contract's name / owner / sequence
--   / is_active exactly. Same code + different semantics => RAISE EXCEPTION.
--
-- Legacy owner pnr_operations.work_scope_id is compatibility only.
-- Authoritative applicability is pnr_work_scope_operations.
-- =============================================================================

begin;

do $seed$
declare
    v_scope_count integer;
    v_op_count integer;
    v_map_count integer;
    v_present integer;
    v_extra integer;
    rec record;
begin
    create temporary table tmp_scopes (
        scope_code text primary key,
        scope_name text not null,
        sequence_no integer not null
    ) on commit drop;

    create temporary table tmp_operations (
        operation_code text primary key,
        operation_name text not null,
        owner_scope_code text not null,
        sequence_no integer not null
    ) on commit drop;

    create temporary table tmp_memberships (
        scope_code text not null,
        operation_code text not null,
        sequence_no integer not null,
        primary key (scope_code, operation_code)
    ) on commit drop;

    insert into tmp_scopes (scope_code, scope_name, sequence_no) values
        ('PNR-WS-01-PRESTART',  'Предпусковая готовность', 10),
        ('PNR-WS-02-VENT-DRIVE','Вентиляционные установки и электропривод', 20),
        ('PNR-WS-03-AUTOMATION','Автоматизация и управление', 30),
        ('PNR-WS-04-PROTECTION','Защиты, блокировки, аварийные режимы и межсистемное взаимодействие', 40),
        ('PNR-WS-05-PTI',       'ПТИ — теплотехнический и гидравлический контур', 50),
        ('PNR-WS-06-AIR-PATH',  'Воздушный тракт и регулирующие устройства', 60),
        ('PNR-WS-07-AERO',      'Аэродинамические измерения и регулирование', 70),
        ('PNR-WS-08-COMPLEX-P1','Комплексные функциональные испытания П-1', 80);

    insert into tmp_operations (
        operation_code, operation_name, owner_scope_code, sequence_no
    ) values
        ('COM-ID-001',   'Идентификация объекта и его функционального состава', 'PNR-WS-01-PRESTART', 10),
        ('COM-INSP-001', 'Проверка соответствия установленного оборудования проектному составу', 'PNR-WS-01-PRESTART', 20),
        ('COM-INSP-002', 'Проверка механической готовности объекта', 'PNR-WS-01-PRESTART', 30),
        ('COM-INSP-003', 'Проверка электрической готовности объекта', 'PNR-WS-01-PRESTART', 40),
        ('COM-INSP-004', 'Проверка готовности КИПиА и цепей управления', 'PNR-WS-01-PRESTART', 50),
        ('COM-MECH-001', 'Проверка механического перемещения исполнительного устройства', 'PNR-WS-02-VENT-DRIVE', 60),
        ('COM-ELEC-001', 'Проверка параметров электропитания', 'PNR-WS-02-VENT-DRIVE', 70),
        ('COM-ELEC-002', 'Измерение сопротивления изоляции электрооборудования', 'PNR-WS-02-VENT-DRIVE', 80),
        ('COM-ELEC-003', 'Проверка направления вращения электропривода', 'PNR-WS-02-VENT-DRIVE', 90),
        ('COM-ELEC-004', 'Выполнение пробного пуска электропривода', 'PNR-WS-02-VENT-DRIVE', 100),
        ('COM-CMD-001',  'Проверка выполнения команды управления', 'PNR-WS-03-AUTOMATION', 110),
        ('COM-SIG-001',  'Проверка прохождения и корректности сигнала', 'PNR-WS-03-AUTOMATION', 120),
        ('COM-MEAS-001', 'Выполнение измерения контролируемого параметра', 'PNR-WS-07-AERO', 130),
        ('COM-ADJ-001',  'Выполнение регулирования или настройки физического параметра', 'PNR-WS-07-AERO', 140),
        ('COM-TEST-001', 'Выполнение функционального испытания сценария', 'PNR-WS-08-COMPLEX-P1', 150);

    -- 01 Предпусковая готовность
    insert into tmp_memberships (scope_code, operation_code, sequence_no) values
        ('PNR-WS-01-PRESTART', 'COM-ID-001', 10),
        ('PNR-WS-01-PRESTART', 'COM-INSP-001', 20),
        ('PNR-WS-01-PRESTART', 'COM-INSP-002', 30),
        ('PNR-WS-01-PRESTART', 'COM-INSP-003', 40),
        ('PNR-WS-01-PRESTART', 'COM-INSP-004', 50);
    -- 02 Вентиляционные установки и электропривод
    insert into tmp_memberships (scope_code, operation_code, sequence_no) values
        ('PNR-WS-02-VENT-DRIVE', 'COM-INSP-002', 10),
        ('PNR-WS-02-VENT-DRIVE', 'COM-INSP-003', 20),
        ('PNR-WS-02-VENT-DRIVE', 'COM-MECH-001', 30),
        ('PNR-WS-02-VENT-DRIVE', 'COM-ELEC-001', 40),
        ('PNR-WS-02-VENT-DRIVE', 'COM-ELEC-002', 50),
        ('PNR-WS-02-VENT-DRIVE', 'COM-ELEC-003', 60),
        ('PNR-WS-02-VENT-DRIVE', 'COM-ELEC-004', 70),
        ('PNR-WS-02-VENT-DRIVE', 'COM-CMD-001', 80),
        ('PNR-WS-02-VENT-DRIVE', 'COM-MEAS-001', 90);
    -- 03 Автоматизация и управление
    insert into tmp_memberships (scope_code, operation_code, sequence_no) values
        ('PNR-WS-03-AUTOMATION', 'COM-INSP-004', 10),
        ('PNR-WS-03-AUTOMATION', 'COM-CMD-001', 20),
        ('PNR-WS-03-AUTOMATION', 'COM-SIG-001', 30);
    -- 04 Защиты, блокировки, аварийные режимы и межсистемное взаимодействие
    insert into tmp_memberships (scope_code, operation_code, sequence_no) values
        ('PNR-WS-04-PROTECTION', 'COM-CMD-001', 10),
        ('PNR-WS-04-PROTECTION', 'COM-SIG-001', 20),
        ('PNR-WS-04-PROTECTION', 'COM-TEST-001', 30);
    -- 05 ПТИ — теплотехнический и гидравлический контур
    insert into tmp_memberships (scope_code, operation_code, sequence_no) values
        ('PNR-WS-05-PTI', 'COM-INSP-001', 10),
        ('PNR-WS-05-PTI', 'COM-INSP-002', 20),
        ('PNR-WS-05-PTI', 'COM-INSP-003', 30),
        ('PNR-WS-05-PTI', 'COM-INSP-004', 40),
        ('PNR-WS-05-PTI', 'COM-MECH-001', 50),
        ('PNR-WS-05-PTI', 'COM-ELEC-001', 60),
        ('PNR-WS-05-PTI', 'COM-CMD-001', 70),
        ('PNR-WS-05-PTI', 'COM-SIG-001', 80),
        ('PNR-WS-05-PTI', 'COM-MEAS-001', 90),
        ('PNR-WS-05-PTI', 'COM-ADJ-001', 100),
        ('PNR-WS-05-PTI', 'COM-TEST-001', 110);
    -- 06 Воздушный тракт и регулирующие устройства
    insert into tmp_memberships (scope_code, operation_code, sequence_no) values
        ('PNR-WS-06-AIR-PATH', 'COM-INSP-001', 10),
        ('PNR-WS-06-AIR-PATH', 'COM-INSP-002', 20),
        ('PNR-WS-06-AIR-PATH', 'COM-MECH-001', 30),
        ('PNR-WS-06-AIR-PATH', 'COM-MEAS-001', 40),
        ('PNR-WS-06-AIR-PATH', 'COM-ADJ-001', 50);
    -- 07 Аэродинамические измерения и регулирование
    insert into tmp_memberships (scope_code, operation_code, sequence_no) values
        ('PNR-WS-07-AERO', 'COM-MEAS-001', 10),
        ('PNR-WS-07-AERO', 'COM-ADJ-001', 20);
    -- 08 Комплексные функциональные испытания П-1
    insert into tmp_memberships (scope_code, operation_code, sequence_no) values
        ('PNR-WS-08-COMPLEX-P1', 'COM-CMD-001', 10),
        ('PNR-WS-08-COMPLEX-P1', 'COM-SIG-001', 20),
        ('PNR-WS-08-COMPLEX-P1', 'COM-MEAS-001', 30),
        ('PNR-WS-08-COMPLEX-P1', 'COM-TEST-001', 40);

    select count(*) into v_scope_count from tmp_scopes;
    select count(*) into v_op_count from tmp_operations;
    select count(*) into v_map_count from tmp_memberships;

    if v_scope_count <> 8 then
        raise exception
            'PNR professional P-1 seed aborted: scope manifest count % is not 8',
            v_scope_count;
    end if;
    if v_op_count <> 15 then
        raise exception
            'PNR professional P-1 seed aborted: operation manifest count % is not 15',
            v_op_count;
    end if;
    if v_map_count <> 42 then
        raise exception
            'PNR professional P-1 seed aborted: membership manifest count % is not 42',
            v_map_count;
    end if;

    if exists (select 1 from tmp_scopes where scope_code like 'PNR-WS-09%') then
        raise exception
            'PNR professional P-1 seed aborted: Section 09 is not part of this foundation';
    end if;

    if exists (
        select 1 from tmp_operations
         where operation_code not like 'COM-%'
    ) then
        raise exception
            'PNR professional P-1 seed aborted: operation manifest contains a non-COM code';
    end if;

    -- ------------------------------------------------------------------
    -- Work scopes — INSERT missing codes only, then fail-closed identity
    -- ------------------------------------------------------------------
    insert into public.pnr_work_scopes (
        scope_code,
        scope_name,
        sequence_no,
        is_active
    )
    select
        t.scope_code,
        t.scope_name,
        t.sequence_no,
        true
    from tmp_scopes t
    where not exists (
        select 1
          from public.pnr_work_scopes s
         where s.scope_code = t.scope_code
    );

    for rec in
        select
            t.scope_code,
            t.scope_name as expected_name,
            t.sequence_no as expected_seq,
            s.work_scope_id,
            s.scope_name as live_name,
            s.sequence_no as live_seq,
            s.is_active
        from tmp_scopes t
        left join public.pnr_work_scopes s
          on s.scope_code = t.scope_code
    loop
        if rec.work_scope_id is null then
            raise exception
                'PNR professional P-1 seed aborted: work scope % was not resolved',
                rec.scope_code;
        end if;
        if rec.live_name is distinct from rec.expected_name then
            raise exception
                'PNR professional P-1 seed aborted: scope_code % exists with incompatible scope_name % (expected %)',
                rec.scope_code, rec.live_name, rec.expected_name;
        end if;
        if rec.is_active is not true then
            raise exception
                'PNR professional P-1 seed aborted: scope_code % exists but is_active is not true',
                rec.scope_code;
        end if;
        if rec.live_seq is distinct from rec.expected_seq then
            raise exception
                'PNR professional P-1 seed aborted: scope_code % exists with incompatible sequence_no % (expected %)',
                rec.scope_code, rec.live_seq, rec.expected_seq;
        end if;
    end loop;

    -- ------------------------------------------------------------------
    -- Canonical operations — INSERT missing codes only
    -- Legacy owner is compatibility; do not rewrite existing owners.
    -- ------------------------------------------------------------------
    insert into public.pnr_operations (
        operation_code,
        operation_name,
        work_scope_id,
        sequence_no,
        is_active
    )
    select
        t.operation_code,
        t.operation_name,
        s.work_scope_id,
        t.sequence_no,
        true
    from tmp_operations t
    join public.pnr_work_scopes s
      on s.scope_code = t.owner_scope_code
    where not exists (
        select 1
          from public.pnr_operations o
         where o.operation_code = t.operation_code
    );

    for rec in
        select
            t.operation_code,
            t.operation_name as expected_name,
            t.owner_scope_code as expected_owner,
            t.sequence_no as expected_seq,
            o.operation_id,
            o.operation_name as live_name,
            o.sequence_no as live_seq,
            o.is_active,
            os.scope_code as live_owner
        from tmp_operations t
        left join public.pnr_operations o
          on o.operation_code = t.operation_code
        left join public.pnr_work_scopes os
          on os.work_scope_id = o.work_scope_id
    loop
        if rec.operation_id is null then
            raise exception
                'PNR professional P-1 seed aborted: operation % was not resolved',
                rec.operation_code;
        end if;
        if rec.live_name is distinct from rec.expected_name then
            raise exception
                'PNR professional P-1 seed aborted: operation_code % exists with incompatible operation_name % (expected %)',
                rec.operation_code, rec.live_name, rec.expected_name;
        end if;
        if rec.is_active is not true then
            raise exception
                'PNR professional P-1 seed aborted: operation_code % exists but is_active is not true',
                rec.operation_code;
        end if;
        if rec.live_seq is distinct from rec.expected_seq then
            raise exception
                'PNR professional P-1 seed aborted: operation_code % exists with incompatible sequence_no % (expected %)',
                rec.operation_code, rec.live_seq, rec.expected_seq;
        end if;
        if rec.live_owner is distinct from rec.expected_owner then
            raise exception
                'PNR professional P-1 seed aborted: operation_code % exists with incompatible legacy owner % (expected %)',
                rec.operation_code, rec.live_owner, rec.expected_owner;
        end if;
    end loop;

    -- ------------------------------------------------------------------
    -- M:N memberships — INSERT missing pairs only
    -- ------------------------------------------------------------------
    insert into public.pnr_work_scope_operations (
        work_scope_id,
        operation_id,
        sequence_no,
        is_active
    )
    select
        s.work_scope_id,
        o.operation_id,
        t.sequence_no,
        true
    from tmp_memberships t
    join public.pnr_work_scopes s
      on s.scope_code = t.scope_code
    join public.pnr_operations o
      on o.operation_code = t.operation_code
    where not exists (
        select 1
          from public.pnr_work_scope_operations m
         where m.work_scope_id = s.work_scope_id
           and m.operation_id = o.operation_id
    );

    for rec in
        select
            t.scope_code,
            t.operation_code,
            t.sequence_no as expected_seq,
            m.is_active,
            m.sequence_no as live_seq,
            s.work_scope_id,
            o.operation_id
        from tmp_memberships t
        join public.pnr_work_scopes s
          on s.scope_code = t.scope_code
        join public.pnr_operations o
          on o.operation_code = t.operation_code
        left join public.pnr_work_scope_operations m
          on m.work_scope_id = s.work_scope_id
         and m.operation_id = o.operation_id
    loop
        if rec.work_scope_id is null or rec.operation_id is null then
            raise exception
                'PNR professional P-1 seed aborted: membership % ↔ % could not resolve catalog ids',
                rec.scope_code, rec.operation_code;
        end if;
        if rec.is_active is null then
            raise exception
                'PNR professional P-1 seed aborted: required membership % ↔ % is missing',
                rec.scope_code, rec.operation_code;
        end if;
        if rec.is_active is not true then
            raise exception
                'PNR professional P-1 seed aborted: required membership % ↔ % exists but is_active is not true',
                rec.scope_code, rec.operation_code;
        end if;
        if rec.live_seq is distinct from rec.expected_seq then
            raise exception
                'PNR professional P-1 seed aborted: membership % ↔ % exists with incompatible sequence_no % (expected %)',
                rec.scope_code, rec.operation_code, rec.live_seq, rec.expected_seq;
        end if;
    end loop;

    select count(*)
      into v_present
      from tmp_memberships t
      join public.pnr_work_scopes s
        on s.scope_code = t.scope_code
      join public.pnr_operations o
        on o.operation_code = t.operation_code
      join public.pnr_work_scope_operations m
        on m.work_scope_id = s.work_scope_id
       and m.operation_id = o.operation_id
       and m.is_active is true;

    if v_present <> 42 then
        raise exception
            'PNR professional P-1 seed aborted: active target memberships present = %, expected 42',
            v_present;
    end if;

    -- Extra memberships involving target scopes/operations: report, do not delete.
    select count(*)
      into v_extra
      from public.pnr_work_scope_operations m
      join public.pnr_work_scopes s
        on s.work_scope_id = m.work_scope_id
      join public.pnr_operations o
        on o.operation_id = m.operation_id
     where (
            s.scope_code in (select scope_code from tmp_scopes)
            or o.operation_code in (select operation_code from tmp_operations)
           )
       and not exists (
            select 1
              from tmp_memberships t
             where t.scope_code = s.scope_code
               and t.operation_code = o.operation_code
       );

    if v_extra > 0 then
        raise notice
            'PNR professional P-1 seed: % extra membership(s) involve target scopes/operations and were left untouched for human review',
            v_extra;
        for rec in
            select s.scope_code, o.operation_code, m.is_active, m.sequence_no
              from public.pnr_work_scope_operations m
              join public.pnr_work_scopes s
                on s.work_scope_id = m.work_scope_id
              join public.pnr_operations o
                on o.operation_id = m.operation_id
             where (
                    s.scope_code in (select scope_code from tmp_scopes)
                    or o.operation_code in (select operation_code from tmp_operations)
                   )
               and not exists (
                    select 1
                      from tmp_memberships t
                     where t.scope_code = s.scope_code
                       and t.operation_code = o.operation_code
               )
             order by s.scope_code, o.operation_code
        loop
            raise notice
                'extra membership (not deleted): % ↔ % is_active=% sequence_no=%',
                rec.scope_code, rec.operation_code, rec.is_active, rec.sequence_no;
        end loop;
    end if;

    -- Fail closed if this seed's target set somehow includes Section 09
    -- or a non-COM operation. Do not assert global table counts.
    if exists (
        select 1
          from public.pnr_work_scopes s
         where s.scope_code in (select scope_code from tmp_scopes)
           and s.scope_code like 'PNR-WS-09%'
    ) then
        raise exception
            'PNR professional P-1 seed aborted: Section 09 scope appeared in the target set';
    end if;
end
$seed$;

commit;
