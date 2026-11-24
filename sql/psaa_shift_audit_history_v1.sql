-- =============================================================================
-- PSAA Shift Audit History V1 — append-only professional audit store
-- =============================================================================
-- File:    sql/psaa_shift_audit_history_v1.sql
-- Deploy:  Supabase SQL Editor MANUALLY after explicit human approval.
--          Do NOT auto-run on production from the app / agent.
--
-- Scope:   PSAA-02 durable history ONLY.
--          Does NOT change daily_progress_*, Airtable sync, Constructor,
--          norms, payroll, or acceptance tables.
--
-- Semantics:
--   APPEND-ONLY by audit_id PRIMARY KEY
--   Technical retry of same audit_id + same content hash = idempotent
--   Different content for same audit_id must fail (application-enforced)
--   SOURCE-NEUTRAL payload (ShiftAuditInput + ShiftAuditArtifact snapshots)
--
-- RLS: project isolation via project_code; publishable key policies are
--      intentionally narrow. Agent writes go through trusted executor only.
-- =============================================================================

create table if not exists public.psaa_shift_audit_history (
    audit_id text primary key,
    project_code text not null,
    work_date text not null,
    shift_type text,
    crew_id text not null,
    source_kind text not null,
    input_schema_version text not null,
    rules_version text not null,
    agent_code text not null,
    agent_version text not null,
    run_id text,
    audited_at_utc timestamptz not null,
    persisted_at_utc timestamptz not null default now(),
    math_integrity_status text not null,
    data_completeness_status text not null,
    professional_credibility_status text not null,
    managerial_acceptance_status text not null,
    input_content_hash text not null,
    artifact_content_hash text not null,
    record_content_hash text not null,
    source_record_ids jsonb not null default '[]'::jsonb,
    uncertainties jsonb not null default '[]'::jsonb,
    input_snapshot jsonb not null,
    artifact_snapshot jsonb not null,
    schema_version text not null default 'psaa_shift_audit_history.v0.1',
    created_at timestamptz not null default now(),

    constraint psaa_shift_audit_history_agent_chk
        check (agent_code = 'PRODUCTION_SHIFT_AUDITOR')
);

create index if not exists ix_psaa_shift_audit_history_grain
    on public.psaa_shift_audit_history (project_code, work_date, crew_id, shift_type);

create index if not exists ix_psaa_shift_audit_history_project_time
    on public.psaa_shift_audit_history (project_code, audited_at_utc);

alter table public.psaa_shift_audit_history enable row level security;

-- No broad anon policies. Access is via trusted server path / future RLS grants.
-- Intentionally no UPDATE/DELETE policies for append-only discipline.

comment on table public.psaa_shift_audit_history is
    'PSAA-02 append-only shift audit history. Not managerial acceptance. Not product fact.';
