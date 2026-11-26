# PSAA I1 — Managed Runtime Integration Checkpoint

Compact documentation checkpoint for accepted I1 Managed Runtime Integration.
**Not** a new master architecture. **Not** a second progress journal.
**Not** a duplicate of Professional Core Completion. **Not** production readiness.

Canonical references:

- Profession: [`PRODUCTION_SHIFT_AUDITOR_PROFESSIONAL_PASSPORT_V0_1.md`](PRODUCTION_SHIFT_AUDITOR_PROFESSIONAL_PASSPORT_V0_1.md)
- Core freeze: [`PSAA_PROFESSIONAL_CORE_COMPLETION_V0_1.md`](PSAA_PROFESSIONAL_CORE_COMPLETION_V0_1.md)
- Prior skills: PSAA-01 … PSAA-13
- Agentic law: [`ARCHITECTURE_BASELINE.md`](ARCHITECTURE_BASELINE.md)
- Security: `security/*.md` (EOS-SEC)
- Methodology: Lessons_2 (external READ-ONLY)

Constructor journal [`AGENT_RUNTIME_PROGRESS.md`](AGENT_RUNTIME_PROGRESS.md) is **not** rewritten here.

---

## 1. AUTHORITATIVE GIT CHECKPOINT

| Field | Value |
|-------|--------|
| Branch | `wip/increment-11c-persistent-shadow-stores` |
| Code commit | `c5b5d3d8292048e62da23598fdc17827457b13b4` |
| Message | `feat(agents): integrate PSAA with managed runtime` |
| Final Verification Gate | **PASS** |
| Push | SUCCESS at acceptance |
| Local HEAD == upstream | **YES** at acceptance |
| Architecture Drift | **NO** |
| Professional Core v0.1 | **FROZEN** (unchanged by I1) |
| Skill engines | **12/12** |

I1 is managed execution integration only. It does **not** rewrite professional
skill engines, create a second runtime framework, PSAA-specific LangGraph,
Constructor HITL/handoff clone, Supabase adapter, durable 12-skill history,
Django/Streamlit UI, or S13+.

---

## 2. ACCEPTED EXECUTION PATH

```
Existing Run Control
  → PsaaManagedRuntimeLauncher
  → authorized project and shift scope validation
  → source resolution
  → assess_shift
  → joint execution of all 12 professional skills
  → process-local professional result
  → Observability
  → terminal managed run status
  → Query Port (status and supported references)
```

### Code scope

- `agents/production_shift_auditor/managed_run_contracts.py`
- `agents/production_shift_auditor/managed_launcher.py`
- `tests/test_psaa_i1_managed_runtime.py`

### Existing components reused

- `RunControlService`
- `ManagedRunStartInput`
- `ManagedRuntimeLauncher` Protocol
- `StoreObservabilityRecorder` / `SqliteObservabilityStore`
- `AgentControlRoomQueryPort`
- EOS-SEC execution context
- `assess_shift` professional core

Existing S01 path (`runtime.py`) preserved.
No second runtime framework. No PSAA-specific LangGraph graph.
No Constructor HITL/handoff clone. Professional core unchanged.

---

## 3. MANAGED EXECUTION AND SECURITY

Proven within tested scope:

- PSAA identity validation
- Run and execution context alignment
- Authorized project scope validation
- Resolved `ShiftAuditInput` scope validation (`project_code`, `work_date`, `crew_id`, optional `shift_type`)
- Synchronous execution
- Threaded execution
- Headless execution (no Django/Streamlit required)
- Controlled failure (no fabricated `RUN_COMPLETED`)
- Process-local result isolation
- Idempotent run replay within existing Run Control
- Observability events and terminal run status
- Query Port list/get status and supported references

Caller-supplied source resolver remains **untrusted**.
Fixture source resolution **PROVEN**.
Production trusted source acquisition **NOT PROVEN**.

`get_result` is an **internal process-local accessor**, not a public authorized
Query API. Project mismatch with `project_code=` returns `None`.
`project_code` argument is **not** an independent authentication mechanism.
Future external result access must use authorized project-scoped security boundaries.

---

## 4. month_key COMPATIBILITY SEAM

Temporary seam (not a generalized agent-neutral business period contract):

`PSAA_MONTH_KEY_COMPATIBILITY_SENTINEL = "NOT_A_PLANNING_MONTH"`

Actual shift grain remains in `scope_request`:

- `grain=SHIFT`
- `work_date`
- `crew_id`
- optional `shift_type`
- explicit `month_key_semantics`

PSAA rejects calendar planning months.
Constructor calendar planning-month behavior preserved.
`ManagedRunStartInput` not generalized in I1.

---

## 5. OBSERVABILITY AND ARTIFACT SEMANTICS

Accepted artifact labels on `ARTIFACT_CREATED` detail:

- `storage_kind=PROCESS_LOCAL`
- `durable_persistence=false`
- `artifact_reference_kind=PROCESS_LOCAL_SUMMARY_ONLY`

`ARTIFACT_CREATED` does **not** establish durable production history.
Query Port exposes managed run status and supported references.
Full 12-skill professional result remains process-local.

Mandatory distinctions:

- `RUNTIME_COMPLETION ≠ PHYSICAL_EXECUTION_VERIFICATION`
- `RUNTIME_COMPLETION ≠ MANAGERIAL_ACCEPTANCE`
- `PROCESS_LOCAL_RESULT ≠ DURABLE_PROFESSIONAL_HISTORY`
- `HEADLESS_EXECUTION ≠ AUTONOMOUS_UNATTENDED_SCHEDULING`

---

## 6. PROFESSIONAL FIXTURE EVIDENCE

All 12 skills executed via managed runtime → `assess_shift`.

| Metric | Value |
|--------|-------|
| Original operations | 11 |
| Claimed labor | 1425 man-minutes |
| Target fund | 1440 man-minutes |
| Target − claimed | +15 |
| S04 scenario cost | 23750 RUB |
| Unit-labor observations | 2 |
| Knowledge candidates | 3 |
| Verified production knowledge | 0 |
| Approved production norms | 0 |
| Managerial acceptance | **NOT PERFORMED** |

Professional core semantics unchanged.
Fixture execution ≠ live production proof.

---

## 7. REGRESSION EVIDENCE (Final Verification Gate)

Suites reported **separately** (not summed):

| Suite | Result |
|-------|--------|
| I1 targeted | **22 PASS** |
| PSAA S01–S12 + history | **311 PASS** |
| Run Control + EOS-SEC | **71 PASS** (+2 subtests) |
| Observability + Query Port + handoff read | **152 PASS**, 1 confirmed pre-existing FAIL |
| Constructor managed launcher | **7 PASS** |
| Governance baseline string | **1 pre-existing FAIL** |
| `git diff --check` | **OK** |

No new I1 regressions reported.
Full repository regression **not** declared green.

### Confirmed pre-existing Query Port architecture failure

Proven on unchanged I1 baseline `e810effc50b5da1cdf2f59c89f70b62d819389b9`:

- Test: `test_no_constructor_or_streamlit_imports`
- Forbidden import: `agents.monthly_plan_constructor.shadow_runtime_stores`
- Classification: **PRE_EXISTING_NOT_I1_REGRESSION**
- Not fixed in I1

### Known Constructor defects retained

Baseline `2c038a3cf2ce7a403f24b299eb91d0b2b9168faa`:

- `handoff_store` — 17 ERROR (previously established; not re-run in full during I1)
- governance baseline string mismatch — FAIL

Constructor Agent not modified.

---

## 8. Lessons_2 AND EOS-SEC

| Field | Value |
|-------|--------|
| Lessons_2 path | `C:\Users\Андрей\LESSON_2` |
| Local HEAD == remote HEAD | `2c4445840cf68ff64cffecbe5a9a9dd21808be04` |
| Lessons_2 mutated | **NO** |
| EOS-SEC within tested scope | **PASS** |
| Architecture Drift | **NO** |

Preserved: project isolation · least privilege · DATA ≠ INSTRUCTION ·
authorized run scope · no product WRITE · no source mutation ·
no acceptance / contractual recognition · no payroll or norm mutation ·
no unauthorized external result access · no hidden handoff ·
no autonomous learning.

Runtime state transitions ≠ product WRITE authority.

---

## 9. I1 READINESS FLAGS

### YES within tested scope

- `PSAA_MANAGED_RUNTIME_LAUNCHER_IMPLEMENTED`
- `EXISTING_RUN_CONTROL_REUSED`
- `MANAGED_PSAA_RUN_PROVEN`
- `JOINT_12_SKILL_MANAGED_EXECUTION_PROVEN`
- `HEADLESS_EXECUTION_PROVEN`
- `PROJECT_SCOPE_ENFORCEMENT_PROVEN`
- `PROCESS_LOCAL_RESULT_ISOLATION_PROVEN`
- `THREADED_EXECUTION_PROVEN`
- `OBSERVABILITY_INTEGRATION_PROVEN`
- `ARTIFACT_DURABILITY_SEMANTICS_PRESERVED`
- `QUERY_PORT_COMPATIBILITY_PROVEN`
- `CONTROLLED_FAILURE_PROVEN`
- `CONSTRUCTOR_COMPATIBILITY_PROVEN`
- `PROFESSIONAL_CORE_SEMANTICS_PRESERVED`

### Remain NO

- `PRODUCTION_TRUSTED_SOURCE_ACQUISITION_PROVEN`
- `DURABLE_RUNTIME_RESTART_PROVEN`
- `PRODUCTION_SUPABASE_INTEGRATION_PROVEN`
- `PRODUCTION_READINESS_PROVEN`

---

## 10. REMAINING TECHNICAL DEBT

Professional Core technical debt register remains in force
([`PSAA_PROFESSIONAL_CORE_COMPLETION_V0_1.md`](PSAA_PROFESSIONAL_CORE_COMPLETION_V0_1.md)).

Additional I1 debt (not remediated here):

- Caller-supplied source resolver is not trusted production acquisition
- Full managed professional result is process-local
- No complete durable 12-skill audit history
- No production PostgreSQL persistence proof
- No durable runtime restart/recovery proof
- No automatic agent-type dispatch registry beyond caller-supplied launcher
- Internal `get_result` is not a public authorized Query API
- `month_key` remains compatibility seam
- Confirmed pre-existing Query Port architecture failure
- Existing Constructor defects retained

---

## 11. NEXT — I2 Supabase & Durable History

Proposed split (research before implementation):

- **I2-A** — Trusted Production Source Acquisition
- **I2-B** — Full Professional Audit Durable History

Before I2 implementation, compact reuse research of existing:

- PSAA read adapter / trusted read tools
- PSAA-02 history contracts and stores
- Trusted audit history executor
- `sql/psaa_shift_audit_history_v1.sql`
- Existing Supabase adapters / durable shared-state mechanisms

Target path:

```
SUPABASE SOURCE
  → AUTHORIZED TRUSTED READ
  → IMMUTABLE SOURCE SNAPSHOT
  → PSAA MANAGED EXECUTION
  → JOINT 12-SKILL ARTIFACT
  → AUTHORIZED DURABLE PERSISTENCE
  → READ-BACK AFTER PROCESS RESTART
```

Distinguish durable professional result persistence from interrupted runtime
execution recovery. Distinguish legacy BHK data from target SINTARK production
data. Legacy labor semantics remain partially proven.

No fabricated source values. No automatic acceptance. No approved norm
generation. No new knowledge platform.

**I2 is not started in this checkpoint.**

---

## 12. CHECKPOINT STATUS

**I1 Managed Runtime Integration — DONE.**
**I1 Documentation Checkpoint — DONE** (this document).
**I2 Supabase & Durable History — NEXT.**
