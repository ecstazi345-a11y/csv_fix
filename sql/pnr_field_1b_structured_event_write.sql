-- =============================================================================
-- FIELD-1B — Atomic structured field event write path
-- =============================================================================
-- File:    sql/pnr_field_1b_structured_event_write.sql
-- Status:  SQL DRAFT. Review before any database apply.
-- Deploy:  Supabase SQL Editor MANUALLY after explicit authorization.
--          This file is not executed by the application.
--          This increment does not apply the file.
--
-- One server-side function. One transaction. Parent event + 0..N
-- measurements + required BLOCKED or PARTIAL sidecar, or nothing.
--
-- Does:
--   INSERT public.pnr_execution_events
--   INSERT public.pnr_event_measurements (0..N)
--   INSERT public.pnr_event_blocked_details when execution_status = BLOCKED
--   INSERT public.pnr_event_partial_details when execution_status = PARTIAL
--
-- Does not:
--   mutate existing event rows
--   remove existing event rows
--   merge-write existing rows
--   backfill historical MVP-0 events
--   create triggers
--   execute assembled SQL strings
--   accept table names from payload
--   broaden table privileges
--   grant execute to anon / authenticated / PUBLIC
--   touch Agent Runtime, BHK, monthly planning
--
-- Privilege model:
--   SECURITY INVOKER — caller is service_role (existing table INSERT).
--   EXECUTE granted to service_role only.
-- =============================================================================

create or replace function public.create_pnr_structured_execution_event(
    p_payload jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_event_id uuid;
    v_system_id uuid;
    v_object_id uuid;
    v_functional_position_id uuid;
    v_execution_status text;
    v_evaluation_status text;
    v_result text;
    v_observation_text text;
    v_retry_of_event_id uuid;
    v_occurred_at timestamptz;
    v_operation_id uuid;
    v_unmapped_operation_name text;
    v_people_count integer;
    v_duration_hours numeric;
    v_labor_hours numeric;
    v_reason text;
    v_comment text;
    v_source text;
    v_measurements jsonb;
    v_blocked_detail jsonb;
    v_partial_detail jsonb;
    v_item jsonb;
    v_category text;
    v_description text;
begin
    if p_payload is null or jsonb_typeof(p_payload) <> 'object' then
        raise exception 'FIELD-1B payload must be a JSON object';
    end if;

    v_event_id := nullif(p_payload->>'event_id', '')::uuid;
    if v_event_id is null then
        v_event_id := gen_random_uuid();
    end if;

    v_system_id := nullif(p_payload->>'system_id', '')::uuid;
    v_object_id := nullif(p_payload->>'object_id', '')::uuid;
    v_functional_position_id := nullif(p_payload->>'functional_position_id', '')::uuid;
    v_execution_status := nullif(btrim(p_payload->>'execution_status'), '');
    v_evaluation_status := nullif(btrim(p_payload->>'evaluation_status'), '');
    v_observation_text := nullif(btrim(p_payload->>'observation_text'), '');
    v_retry_of_event_id := nullif(p_payload->>'retry_of_event_id', '')::uuid;
    v_occurred_at := nullif(p_payload->>'occurred_at', '')::timestamptz;
    v_operation_id := nullif(p_payload->>'operation_id', '')::uuid;
    v_unmapped_operation_name := nullif(btrim(p_payload->>'unmapped_operation_name'), '');
    v_people_count := nullif(p_payload->>'people_count', '')::integer;
    v_duration_hours := nullif(p_payload->>'duration_hours', '')::numeric;
    v_labor_hours := nullif(p_payload->>'labor_hours', '')::numeric;
    v_reason := nullif(btrim(p_payload->>'reason'), '');
    v_comment := nullif(btrim(p_payload->>'comment'), '');
    v_source := coalesce(nullif(btrim(p_payload->>'source'), ''), 'STREAMLIT');

    v_measurements := p_payload->'measurements';
    if v_measurements is null or v_measurements = 'null'::jsonb then
        v_measurements := '[]'::jsonb;
    end if;

    v_blocked_detail := p_payload->'blocked_detail';
    if v_blocked_detail = 'null'::jsonb then
        v_blocked_detail := null;
    end if;

    v_partial_detail := p_payload->'partial_detail';
    if v_partial_detail = 'null'::jsonb then
        v_partial_detail := null;
    end if;

    if v_system_id is null or v_object_id is null then
        raise exception 'FIELD-1B system_id and object_id are required';
    end if;

    if v_occurred_at is null then
        raise exception 'FIELD-1B occurred_at is required';
    end if;

    if v_execution_status is null or v_evaluation_status is null then
        raise exception 'FIELD-1B execution_status and evaluation_status are required';
    end if;

    if v_retry_of_event_id is not null and v_retry_of_event_id = v_event_id then
        raise exception 'FIELD-1B retry cannot reference the same event';
    end if;

    v_result := case
        when v_execution_status = 'COMPLETED'
             and v_evaluation_status = 'CONFORMS'
            then 'PASS'
        when v_execution_status = 'COMPLETED'
             and v_evaluation_status = 'NOT_EVALUATED'
            then 'PASS'
        when v_execution_status = 'COMPLETED'
             and v_evaluation_status = 'DOES_NOT_CONFORM'
            then 'FAIL'
        when v_execution_status = 'NOT_COMPLETED'
             and v_evaluation_status = 'NOT_EVALUATED'
            then 'FAIL'
        when v_execution_status = 'PARTIAL'
             and v_evaluation_status = 'NOT_EVALUATED'
            then 'PARTIAL'
        when v_execution_status = 'PARTIAL'
             and v_evaluation_status = 'DOES_NOT_CONFORM'
            then 'PARTIAL'
        when v_execution_status = 'BLOCKED'
             and v_evaluation_status = 'NOT_EVALUATED'
            then 'BLOCKED'
        else null
    end;

    if v_result is null then
        raise exception 'FIELD-1B invalid execution/evaluation pair';
    end if;

    if jsonb_typeof(v_measurements) <> 'array' then
        raise exception 'FIELD-1B measurements must be a JSON array';
    end if;

    if v_execution_status = 'BLOCKED' then
        if v_blocked_detail is null or jsonb_typeof(v_blocked_detail) <> 'object' then
            raise exception 'FIELD-1B BLOCKED requires blocked_detail';
        end if;
        v_category := nullif(btrim(v_blocked_detail->>'constraint_category'), '');
        v_description := nullif(btrim(v_blocked_detail->>'constraint_description'), '');
        if v_category is null then
            raise exception 'FIELD-1B blocked_detail.constraint_category is required';
        end if;
        if v_category = 'OTHER' and v_description is null then
            raise exception 'FIELD-1B OTHER blocked_detail requires constraint_description';
        end if;
    elsif v_blocked_detail is not null then
        raise exception 'FIELD-1B blocked_detail is only allowed when BLOCKED';
    end if;

    if v_execution_status = 'PARTIAL' then
        if v_partial_detail is null or jsonb_typeof(v_partial_detail) <> 'object' then
            raise exception 'FIELD-1B PARTIAL requires partial_detail';
        end if;
        if nullif(btrim(v_partial_detail->>'completed_text'), '') is null then
            raise exception 'FIELD-1B partial_detail.completed_text is required';
        end if;
        if nullif(btrim(v_partial_detail->>'remaining_text'), '') is null then
            raise exception 'FIELD-1B partial_detail.remaining_text is required';
        end if;
    elsif v_partial_detail is not null then
        raise exception 'FIELD-1B partial_detail is only allowed when PARTIAL';
    end if;

    if v_people_count is not null and v_duration_hours is not null then
        v_labor_hours := v_people_count::numeric * v_duration_hours;
    end if;

    insert into public.pnr_execution_events (
        event_id,
        system_id,
        object_id,
        operation_id,
        unmapped_operation_name,
        result,
        occurred_at,
        people_count,
        duration_hours,
        labor_hours,
        reason,
        comment,
        source,
        functional_position_id,
        execution_status,
        evaluation_status,
        observation_text,
        retry_of_event_id
    ) values (
        v_event_id,
        v_system_id,
        v_object_id,
        v_operation_id,
        v_unmapped_operation_name,
        v_result,
        v_occurred_at,
        v_people_count,
        v_duration_hours,
        v_labor_hours,
        v_reason,
        v_comment,
        v_source,
        v_functional_position_id,
        v_execution_status,
        v_evaluation_status,
        v_observation_text,
        v_retry_of_event_id
    );

    for v_item in
        select jsonb_array_elements(v_measurements)
    loop
        if jsonb_typeof(v_item) <> 'object' then
            raise exception 'FIELD-1B each measurement must be a JSON object';
        end if;
        insert into public.pnr_event_measurements (
            event_id,
            parameter_code,
            parameter_name,
            value,
            unit,
            measurement_point,
            instrument_text,
            recorded_at
        ) values (
            v_event_id,
            nullif(btrim(v_item->>'parameter_code'), ''),
            nullif(btrim(v_item->>'parameter_name'), ''),
            (v_item->>'value')::numeric,
            nullif(btrim(v_item->>'unit'), ''),
            nullif(btrim(v_item->>'measurement_point'), ''),
            nullif(btrim(v_item->>'instrument_text'), ''),
            (v_item->>'recorded_at')::timestamptz
        );
    end loop;

    if v_execution_status = 'BLOCKED' then
        insert into public.pnr_event_blocked_details (
            event_id,
            execution_status,
            constraint_category,
            constraint_description,
            other_work_available
        ) values (
            v_event_id,
            'BLOCKED',
            v_category,
            v_description,
            case
                when v_blocked_detail->>'other_work_available' is null
                     or btrim(v_blocked_detail->>'other_work_available') = ''
                    then null
                else (v_blocked_detail->>'other_work_available')::boolean
            end
        );
    end if;

    if v_execution_status = 'PARTIAL' then
        insert into public.pnr_event_partial_details (
            event_id,
            execution_status,
            completed_text,
            remaining_text
        ) values (
            v_event_id,
            'PARTIAL',
            btrim(v_partial_detail->>'completed_text'),
            btrim(v_partial_detail->>'remaining_text')
        );
    end if;

    return jsonb_build_object(
        'event_id', v_event_id,
        'system_id', v_system_id,
        'object_id', v_object_id,
        'operation_id', v_operation_id,
        'unmapped_operation_name', v_unmapped_operation_name,
        'result', v_result,
        'occurred_at', v_occurred_at,
        'people_count', v_people_count,
        'duration_hours', v_duration_hours,
        'labor_hours', v_labor_hours,
        'reason', v_reason,
        'comment', v_comment,
        'source', v_source,
        'functional_position_id', v_functional_position_id,
        'execution_status', v_execution_status,
        'evaluation_status', v_evaluation_status,
        'observation_text', v_observation_text,
        'retry_of_event_id', v_retry_of_event_id
    );
end;
$$;

comment on function public.create_pnr_structured_execution_event(jsonb) is
    'FIELD-1B: atomic structured PNR event write. '
    'INVOKER service_role INSERT only. No execute for anon/authenticated/PUBLIC.';

revoke all on function public.create_pnr_structured_execution_event(jsonb) from public;
revoke all on function public.create_pnr_structured_execution_event(jsonb) from anon;
revoke all on function public.create_pnr_structured_execution_event(jsonb) from authenticated;

grant execute on function public.create_pnr_structured_execution_event(jsonb)
    to service_role;
