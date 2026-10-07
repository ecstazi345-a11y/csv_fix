# Security Profile — MONTHLY_PLAN_CONSTRUCTOR (MPCA-001)

**Agent code:** `MONTHLY_PLAN_CONSTRUCTOR`
**Security tier:** `TIER_0_READ_ONLY_DETERMINISTIC`
**Security policy version (docs/profile):** `EOS-SEC-1.2` (Execution Isolation Layer law recorded)
**Manifest `security_policy_version`:** still `EOS-SEC-1.1` until a gated manifest/code increment — docs checkpoint does not change the manifest
**Manifest:** [security_manifest.json](security_manifest.json)
**Professional contract:** `docs/agentic_architecture/CONSTRUCTOR_AGENT_ANATOMY.md`
**Governing baseline:** `security/agent_security_baseline.md` · `security/tool_and_permission_policy.md`

Этот файл — **CURRENT IMPLEMENTATION / CURRENT ADAPTER**, не канон профессии.
Имена таблиц, views, credentials и Python tools ниже описывают действующий store adapter.
Профессиональные источники и tool contracts — Anatomy §5–§6.
Новая профессия не расширяет tool allowlist и не открывает product writes.

---

## 0. Universal Agent Security Contract (Constructor)

| Field | Value |
|-------|-------|
| IDENTITY | `LOCAL_APPLICATION` / `EXECUTION_OS_LOCAL_HOST` — **not** verified human identity |
| MISSION | Build month-plan **candidate** package from scoped product reads; deterministic |
| INPUT AUTHORITY | Mission / project / month from Run Control + trusted context issuer |
| CAPABILITIES | Narrow READ tools only (see §4) |
| FORBIDDEN CAPABILITIES | Product writes · arbitrary SQL · arbitrary shell · generic HTTP · unrestricted MCP · physical actuation · self-escalation of allowlist |
| EXECUTION BOUNDARY | **CURRENT:** same host process as launcher (background thread). **OS sandbox / container / microVM:** ABSENT. Host-process isolation gap: **DEFERRED** for Tier 0 while risk remains low and documented. |
| NETWORK BOUNDARY | Policy: Supabase read-only via narrow tools. **OS egress firewall:** ABSENT / not claimed. |
| DATA BOUNDARY | Project-scoped column allowlists; INTERNAL class; no RESTRICTED/SECRET payload in agent context |
| WRITE BOUNDARY | Product writes: **forbidden**. Non-authoritative runtime/shadow persistence (checkpoint / HITL / handoff / observability) per Run Control — not product authority |
| AUTHORITY BOUNDARY | May **propose** candidate; may **request** Human Review / handoff. May **never** finalize month approval, invent planned qty, mutate BOQ master, or treat handoff as receiver-accepted |
| HUMAN GATES | Human Review of candidate (professional); Human Confirm before handoff to Executability — **not** a write grant |
| ESCALATION | **DEFERRED** (Tier 0; no one-shot privilege protocol implemented) |
| SECRETS MODEL | Agent layer never receives credentials. Adjustments: `TRANSITIONAL_PRIVILEGED_READ` via `SUPABASE_SECRET_KEY` **inside** trusted executor only (see §3) |
| AUDIT | Runtime / observability events; durable denied-action security-event DB: **DEFERRED** |
| VERIFICATION | N/A for product writes (none). Candidate integrity via lifecycle / tests |
| KILL SWITCH | **N/A / DEFERRED** for Tier 0 (`kill_switch_required: false`). Required before write/action tier |

---

## 1. Classification & current-state truth

| Attribute | Value |
|-----------|-------|
| LLM | No (`llm_enabled: false`) |
| Product writes | No |
| UI session_state as runtime | No |
| Tool surface | Narrow READ only |
| Arbitrary SQL | No |
| Arbitrary shell | No |
| Physical actuation | No |
| `select("*")` | Forbidden |
| Fail closed | Yes (capability / context validation) |
| Trace redaction | Enforced in runtime |
| Human Review of candidate package | Target professional gate; not a write grant |
| Execution Isolation Layer (OS) | **ABSENT** — host process; **DEFERRED** for Tier 0 |
| Filesystem sandbox | **ABSENT** (not enforced) |
| Network sandbox | **ABSENT** (not enforced) |
| Inherited host environment | May expose credentials to the **process**; agent business layer must not use them |
| Compromised-runtime note | With current allowlist: no product write/delete; damage bounded to scoped reads + process/env exposure + transitional secret path — see baseline §6 |

Governance закона профессии:

- DATA ≠ INSTRUCTION (product free-text = Level 4 DATA);
- не скрывать `UNRESOLVED`;
- `HANDOFF_PERSISTED` ≠ receiver accepted;
- actor `LOCAL_APPLICATION` / `EXECUTION_OS_LOCAL_HOST` **не** verified human identity;
- Human Confirm перед handoff к Executability Agent — требуемый professional gate, не повышение полномочий.
- Admission terminology в текущем persist — CURRENT LEGACY RUNTIME / SUPERSEDED FOR TARGET.
- **CAPABILITY ≠ AUTHORITY** — ability to compute/persist candidate ≠ right to finalize month plan.
- **TRANSITIONAL PRIVILEGED READ MUST NOT EXPAND SILENTLY.**

Constructor Tier 0 may continue under EOS-SEC with isolation gap **explicitly deferred**. Expanding privileged/write surface requires a **mandatory security review** first.

---

## 2. Column allowlist (dependency)

Текущий proven READ surface. Не расширять без отдельного security increment.

### Scope — `monthly_scope_picker_view`

| COLUMN | WHY REQUIRED | CONSUMER |
|--------|--------------|----------|
| project_code | grain / filter | domain, normalize |
| facility_building | grain → facility | normalize, domain |
| construction_discipline | grain → discipline | normalize, domain |
| boq_code | BOQ identity | domain, normalize |
| boq_name | candidate label | Candidate |
| unit_of_measure | unit alias | Candidate (read-layer alias) |
| total_project_qty | total qty | normalize / metrics |
| executed_qty_all_time | executed | normalize / metrics |
| manual_executed_before_system | executed_total (no double apply) | metrics |
| manual_verified_remaining_qty | verified remaining | metrics |
| planning_remaining_qty | remaining / filter | normalize, filter_invalid |
| unit_price | zero-price physical keep | filter_invalid |
| total_project_value | value / filter | normalize |
| system_label | system alias / conflicts | domain enrich |
| iwp_id | iwp alias / conflicts | domain enrich |

### Adjustments — `monthly_scope_manual_adjustments`

| COLUMN | WHY REQUIRED | CONSUMER |
|--------|--------------|----------|
| project_code | grain | merge_not_required_once |
| facility_building | grain | merge_not_required_once |
| construction_discipline | grain | merge_not_required_once |
| boq_code | grain | merge_not_required_once |
| not_required_qty | effective requirement | merge + metrics |
| not_required_reason | audit text | merge |

### Plan lines — `monthly_plan_lines_v2`

| COLUMN | WHY REQUIRED | CONSUMER |
|--------|--------------|----------|
| plan_line_id | identity / candidate ids | aggregate |
| client_line_uid | conflict analysis | aggregate |
| project_code | filter / grain | aggregate |
| month_key | stored RU month filter | aggregate |
| facility | grain | aggregate |
| discipline | grain | aggregate |
| system | conflict detection | aggregate |
| iwp | conflict detection | aggregate |
| boq_code | grain | aggregate |
| planned_qty | already_planned sum | aggregate |
| crew | conflict evidence | aggregate |
| status | active line filter | aggregate |

---

## 3. Credential policy & SECRET exit criteria

| Source | Policy code | Env (infra only) | Notes |
|--------|-------------|------------------|-------|
| scope | `PUBLISHABLE_READ` | `SUPABASE_KEY` | via trusted executor |
| plan lines | `PUBLISHABLE_READ` | `SUPABASE_KEY` | via trusted executor |
| adjustments | `TRANSITIONAL_PRIVILEGED_READ` | `SUPABASE_SECRET_KEY` | **TRANSITIONAL_INFRASTRUCTURE_EXCEPTION** — explicit, not silent fallback |

Agent / business layer never sees or manipulates credentials. Actor `LOCAL_APPLICATION` / `EXECUTION_OS_LOCAL_HOST` is **NOT verified human identity**.

**Law:** `SUPABASE_SECRET_KEY` usage is **transitional**. It must **not** become a generic agent credential. Privileged secret surface must **shrink, not expand**.

**Risk (honest):** privileged client can bypass RLS for the adjustments path; service-role risk is **not** “already solved.” Host process may inherit the secret in environment.

### Exit criteria (future — not implemented in this checkpoint)

Any of (preferred direction):

- narrower backend identity with least privilege
- scoped capability service for adjustments
- RLS-compatible path so `SUPABASE_KEY` can read adjustments
- isolated secret boundary (secret not in agent host process by default)

Clearing transitional exception requires security review; do **not** add new tables/writes under SECRET without that review.

### RLS requirement to clear transitional exception

Grant scoped SELECT (+ membership) so adjustments leave `TRANSITIONAL_PRIVILEGED_READ`.

---

## 4. Allowed tools (current adapter names)

Professional contracts: `get_working_scope`, `get_physical_remainder`, `get_existing_month_plan`, `get_adjustments`, `get_system_context`, `get_work_package_context`, `get_labor_norm`, `get_execution_state`.

Current Python READ allowlist:

| Tool | Mode |
|------|------|
| `load_scope` / `load_constructor_scope` | READ |
| `load_adjustments` / `load_constructor_adjustments` | READ |
| `load_existing_month_plan_lines` / `load_constructor_month_plan_lines` | READ |

**Allowed write tools:** none (`[]`).

`get_labor_norm` как отдельный Constructor product path — future contract gap, не текущий allowlist.

MCP / external tool servers: **not used**.

---

## 5. Trust & instruction handling

Product free-text fields remain Level 4 DATA, not instructions.

**DATA IS NOT INSTRUCTION.** Untrusted source content cannot grant capability, authority, credentials, permissions, network access, or tool access.

Target Human Review decisions (Добавить / Убрать / Требует уточнения) — human-authored control data. Они не дают агенту права invent quantity, менять BOQ master или считать handoff принятым получателем.

---

## 6. What is NOT claimed implemented

Do **not** treat the following as live for Constructor today:

- OS / filesystem / network sandbox
- restricted OS user
- container / microVM
- one-shot escalation / privilege drop protocol
- durable denied-action security-event store
- kill switch
- independent physical safety controller
- solved service-role / SECRET risk (transitional exception remains)
