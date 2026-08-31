# Agent Run Control and Observability v0.1

**Status:** PROPOSED / NOT YET IMPLEMENTED. Architecture specification only.<br>
**Date:** 2026-08-31<br>
**Program:** Monthly Planning Agentic Orchestration<br>
**Increment:** 10 — Agent Control Room / Operational Observability / Run Control<br>
**Does not authorize:** product code, Streamlit page, SQL, Supabase DDL/RLS, Docker, requirements changes, tests, commit, or push.

**Parent law:** Constructor Agent Runtime v0.1 Increments 1–9 accepted on `main` (`c24708b3a40eb930f7879d3fd764784be057cc1e`). Discovery Phase 10.0 accepted.

**This document** is the normative implementation contract for the shared Execution OS **control plane**. Constructor is the **first tenant**. Later professional agents must reuse this plane without cloning Constructor-specific runtime or Control Room logic.

Related law (unchanged by this spec):

- [ARCHITECTURE_BASELINE.md](ARCHITECTURE_BASELINE.md)
- [AGENT_RUNTIME_V0_1_CONSTRUCTOR_MISSION.md](AGENT_RUNTIME_V0_1_CONSTRUCTOR_MISSION.md)
- [ORCHESTRATION_AND_HANDOFF.md](ORCHESTRATION_AND_HANDOFF.md)
- [DIGITAL_EMPLOYEE_ANATOMY.md](DIGITAL_EMPLOYEE_ANATOMY.md)
- [DECISION_LOG.md](DECISION_LOG.md)
- EOS-SEC (`security/*.md`)

`AGENT_RUNTIME_PROGRESS.md` is **not** updated by this specification.

---

## 0. Non-negotiable laws

```
AGENT ≠ CHATBOT
LLM ≠ AGENT
DASHBOARD ≠ AGENT
LANGGRAPH ≠ PROFESSIONAL ROLE

ONE MAJOR PROFESSIONAL ROLE = ONE SPECIALIZED AGENT.

AGENT DOES NOT START AGENT.
ORCHESTRATOR STARTS AGENTS.

HANDOFF ≠ DIRECT AGENT CALL.

TRIGGER ≠ AUTHORIZATION ≠ EXECUTION.

RESUME ≠ RETRY ≠ NEW RUN.

MODEL IS NOT A SECURITY BOUNDARY.
DATA ≠ INSTRUCTION.

CONTROL ROOM IS NOT THE RUNTIME.
STREAMLIT IS NOT THE SOURCE OF TRUTH.
BUSINESS TABLES ARE NOT THE SOURCE OF AGENT EXECUTION STATE.
```

The professional agent must continue independently if the browser or Streamlit session is closed.

Control Room visualizes **recorded runtime truth**. It does not fabricate state from BOQ / plan / constraint tables, from `st.session_state`, or from LangGraph internals.

---

## 1. System architecture

Target control flow:

```
TRIGGER
  ↓
RUN REQUEST
  ↓
RUN CONTROL
  ↓
AUTHORIZATION
  ↓
MISSION BINDING
  ↓
AGENT RUNTIME
  ↓
RUNTIME INSTRUMENTATION
  ↓
OBSERVABILITY EVENTS
  ↓
DURABLE OBSERVABILITY STORE
  ↓
QUERY / READ MODEL
  ↓
AGENT CONTROL ROOM
```

Parallel outputs from the professional runtime (Constructor today):

```
AGENT RUNTIME
  ├── business artifacts     (Candidate Package, exceptions, …)
  ├── HITL state             (interrupt + decision)
  ├── checkpoint             (LangGraph durable resume)
  └── structured handoff     (ConstructorHandoff)
```

The **Monthly Plan Orchestrator** consumes a persisted handoff and may start the **next** professional agent.

Constructor **MUST NOT** execute Admission. No hidden agent-to-agent chat. No direct agent call.

Constructor is the first tenant of this plane. The same contracts must later host:

- Admission Agent
- Constraint Agent
- Resource Capacity Agent
- Economic Evaluation Agent
- Management Decision Agent
- future physical-world agents

without cloning Constructor-specific control-plane or Control Room code.

---

## 2. Control plane vs business plane

### Business / professional plane

Owns professional truth for **one role**. For Constructor:

- `ConstructorLifecycleState`
- `ConstructorMissionScope`
- `CandidatePackage`
- labor-norm resolution set
- exception set
- HITL professional decision (`ConstructorHumanDecisionRequest` / `ConstructorResumeCommand`)
- `ConstructorHandoff`

This plane already exists (Increments 1–9). Increment 10 **must not** reimplement it.

### Control / operational plane

Owns operational truth that any professional agent can share:

- `RunRequest`
- `AgentRun`
- authorization facts
- operational status
- `ObservabilityEvent`
- stage projection
- trace / timing
- retries / resume counts
- audit / security events
- Control Room read model

### Law

```
AgentRun ≠ ConstructorLifecycleState
```

`AgentRun` must **not** become a second professional state machine.

The control plane **observes** professional execution and **controls** run identity, authorization, start, abort-of-run (operational), and durable visibility.

It does **not**:

- classify candidates
- resolve labor norms
- decide WAIT vs READY
- bind extra-scope rows
- authorize tools
- invent handoff payload
- start the next agent

`lifecycle_status` on `AgentRun` is a **projection** of the tenant’s professional status, not an independent Constructor engine.

---

## 3. RunRequest contract

Agent-neutral conceptual type: **`RunRequest`**.

A RunRequest is a structured ask to start a **new professional execution**. It does **not** grant authorization. It does **not** start the runtime by itself. It is **not** used for normal HITL resume or technical retry of an existing run.

### Required fields

| Field | Meaning |
|-------|---------|
| `schema_version` | Contract version. First implementation: `run_request.v0.1` |
| `request_id` | Minted by Run Control. Stable identity of this request |
| `requested_at` | Timezone-aware UTC |
| `agent_code` | Professional role, e.g. `MONTHLY_PLAN_CONSTRUCTOR` |
| `requested_agent_version` | Optional. If omitted, trusted registry version is used |
| `initiator_type` | Closed new-run enum — §4: `HUMAN` \| `ORCHESTRATOR` only |
| `initiator_id` | Safe initiator identity (not credentials) |
| `trigger_type` | Why this request exists (closed / bounded) |
| `trigger_reason` | Human-readable bounded reason |
| `project_code` | Required for Constructor; blank fails closed |
| `month_key` | Required for Constructor |
| `scope_request` | Explicit mission dimensions. Not Page10B leftover filters |
| `orchestration_run_id` | Optional; **required** when `initiator_type=ORCHESTRATOR` |
| `predecessor_run_id` | Optional; required for professional re-execution after COMPLETED |
| `requested_mission_id` | Mission identity supplied by authorized path |
| `idempotency_key` | Prevents duplicate starts of the same request |
| `metadata` | Bounded safe metadata only |

### Invariants

1. No credentials, tokens, DSN, clients, connections.
2. No arbitrary prompt / instruction payload.
3. No SQL.
4. No DataFrame / candidate rows.
5. `scope_request` is structured identifiers, not UI search leftovers.
6. `RunRequest` is not an `AgentExecutionContext`.
7. `idempotency_key` follows the canonical rule below. No silent duplicate professional run.
8. `SYSTEM_EVENT` is **not** a `RunRequest.initiator_type`. It requests orchestration; it must not name Constructor as a direct start target.

Exact field-length and key-count constants are implementation 10.1. This spec **requires** explicit hard limits; unbounded maps are forbidden.

### Idempotency (normative)

`idempotency_key` is scoped to a **canonical request digest**, not to wall-clock or UI chrome.

**IDEMPOTENCY_SCOPE** (fields that enter the digest):

- `agent_code`
- `initiator_type`
- `initiator_id`
- `project_code`
- `month_key`
- `scope_request` canonical representation
- `requested_mission_id`
- `orchestration_run_id`
- `predecessor_run_id`
- `trigger_type`

**Excluded** unless later declared semantic:

- `requested_at`
- presentation metadata
- UI labels
- `metadata` presentation-only keys

Canonical form: deterministic JSON (sorted keys, no NaN, stable null/omitted law) then SHA-256. Exact encoder is implementation 10.1 / 10.2. The digest algorithm must be identical for compare.

| Condition | Outcome |
|-----------|---------|
| Same `idempotency_key` **and** same canonical request digest | Reuse / return the existing `RunRequest` and its associated `run_id`. No second professional execution. |
| Same `idempotency_key` **and** different canonical request digest | `IDEMPOTENCY_CONFLICT`. Fail closed. No overwrite. No second run. No silent merge. |

Unknown / blank `idempotency_key` fails closed for managed Increment 10 starts.

---

## 4. Legal run initiators

Do **not** overload `RunRequest.initiator_type` with continuation commands.

### Legal NEW RUN `initiator_type` (on `RunRequest` only)

| Type | Semantics |
|------|-----------|
| `HUMAN` | New `RunRequest` from Agent Control Room. New `request_id`. New `run_id`. |
| `ORCHESTRATOR` | New `RunRequest` from orchestration state. New `request_id`. New `run_id`. `orchestration_run_id` required. |

### Not a new professional `RunRequest`

| Type | Semantics |
|------|-----------|
| `SYSTEM_EVENT` | Schedule or material reality-change **requests orchestration**. Must **not** directly start Constructor. Must **not** mint a Constructor `RunRequest`. |
| `RESUME` | Control action / HITL continuation of an **existing** run. Not a legal initiator of a new professional `RunRequest`. See §26. |
| `RETRY` | Technical attempt on an **existing** run. Not a legal initiator of a new professional `RunRequest`. See §27. |
| `REPLAY` | Audit reconstruction, crash-recovery observation, or idempotent persist (`IDEMPOTENT_REPLAY` on handoff). Not a new professional run. |

Re-execution after `COMPLETED`: **new** `RunRequest`, new `run_id`, `predecessor_run_id` = prior run, full authorization again.

`RESUME` / `RETRY` may appear as a control-action type, event family/type, or audit initiator of continuation. They **must not** appear as `RunRequest.initiator_type`.

### Forbidden

- Constructor starts Admission.
- Any agent starts an arbitrary agent.
- Streamlit callback invokes Constructor LangGraph / lifecycle **bypassing Run Control**.
- Agent self-start.
- Treating `RESUME` or `RETRY` as a new professional run or new `RunRequest`.
- Treating handoff persist `IDEMPOTENT_REPLAY` as Constructor re-execution.

---

## 5. Run identity model

### Ownership

**Run Control mints:**

- `request_id`
- `run_id`

**Mission identity** must exist **before** managed professional execution.

`mission_id` is supplied or bound by the authorized Run Control / Orchestrator path.

Managed Increment 10 runtime **must not** silently invent `mission_id`.

Legacy `run_constructor_langgraph(..., mission_id=None)` UUID fill may remain for **unmanaged** backward-compatible invoke. It is **not** canonical Increment 10 managed behavior.

### Relation graph

```
request_id          — one ask
  └── run_id        — one professional invocation (survives HITL)
        ├── mission_id
        ├── orchestration_run_id   (optional; required for ORCHESTRATOR)
        ├── authorization_id
        ├── thread_id
        ├── checkpoint_id          (current / last known)
        ├── attempt_n
        ├── resume_n
        ├── predecessor_run_id     (optional)
        ├── interrupt_id           (active / last)
        ├── decision_id            (last applied)
        ├── snapshot_id            (reality / provenance — not a generic artifact alias)
        ├── package_id             (Candidate Package typed id)
        └── handoff_id             (ConstructorHandoff typed id)
```

Event correlation may carry `artifact_type` + `artifact_id`. That pair **does not replace** typed domain ids. No ID synonymy.

| `artifact_type` (example) | `artifact_id` equals |
|---------------------------|----------------------|
| `CANDIDATE_PACKAGE` | `package_id` |
| `EXCEPTION_ANALYSIS` | exception-set id |
| `CONSTRUCTOR_HANDOFF` | `handoff_id` |

`snapshot_id` remains reality/provenance identity. It is not an alias of `artifact_id`.

### Frozen Constructor LangGraph law

```
thread_id == run_id
```

unless a later accepted version explicitly changes this law.

Issuer `AgentExecutionContext.run_id` for a managed run **must equal** the Run Control `run_id`. Run Control mints first; the issuer receives that id. The issuer still mints `authorization_id`. Callers must not supply `allowed_tools` / `write_allowed`.

---

## 6. AgentRun contract

Agent-neutral conceptual type: **`AgentRun`**.

Operational envelope of one professional invocation. Not a second Constructor lifecycle.

### Identity

| Field | Meaning |
|-------|---------|
| `schema_version` | First implementation: `agent_run.v0.1` |
| `run_id` | Minted by Run Control |
| `request_id` | Originating request |
| `agent_code` | Professional role |
| `agent_version` | Effective version from trusted registry |
| `mission_id` | Bound before start |
| `orchestration_run_id` | Optional |

### Context

`project_code`, `month_key`, `scope_summary` (bounded identifiers — not full scope object dump if it contains large enumerations beyond the existing mission-scope contract).

### Initiator

`initiator_type`, `initiator_id`, `trigger_type`, `trigger_reason`

### Authorization

`authorization_id`, `authorized_by`, `security_policy_version`

### Operational fields

| Field | Meaning |
|-------|---------|
| `operational_status` | Closed enum — §7 |
| `lifecycle_status` | Projection of tenant professional status |
| `current_stage_id` | Constructor catalog §14 or future tenant catalog |
| `current_node` | Correlation only (e.g. LangGraph node name) |
| `attempt_n` | Technical attempt, 1-based |
| `resume_n` | Count of successful human resumes |
| `projection_version` | Monotonic version for optimistic concurrency / CAS |
| `started_at` / `updated_at` / `completed_at` | UTC |

### References only

`checkpoint_id`, `thread_id`, `snapshot_id`, `package_id`, `interrupt_id`, `decision_id`, `handoff_id`

Safe summaries / counts (scanned, candidates, exception buckets, labor-norm buckets, freshness flag).

`error_code` optional, `safe_error_summary` optional (already redacted).

### Forbidden on AgentRun

- full `CandidatePackage`
- full `ConstructorRealityRead`
- DataFrame
- `AgentExecutionContext` object
- client / connection / credentials
- prompt history / chain-of-thought

---

## 7. Operational status model

Closed `operational_status` enum:

| Status | Meaning |
|--------|---------|
| `REQUESTED` | RunRequest accepted; authorization not finished |
| `AUTHORIZING` | Issuer / policy check in progress |
| `AUTHORIZATION_DENIED` | Terminal for this request. No runtime start |
| `STARTING` | Authorized; runtime invoke not yet `RUNNING` |
| `RUNNING` | Professional runtime is advancing |
| `WAITING_FOR_HUMAN` | Durable HITL pause. Same `run_id` |
| `RETRYING` | Declared technical retry of the same `run_id` |
| `COMPLETED` | Managed operational completion — §8 |
| `FAILED` | Durable fail-closed professional or runtime failure **with** persisted `RUN_FAILED`. Not used for store outage |
| `ABORTED` | Controlled professional abort (HITL `ABORT_RUN` or equivalent) |

### Three different things (do not collapse)

| Token | Plane | Meaning |
|-------|--------|---------|
| `READY_FOR_HANDOFF` | Professional lifecycle | Constructor eligibility. Not “run finished”. Persist does not change it. |
| `HANDOFF_READY` | Handoff artifact | `ConstructorHandoff.status`. Not a lifecycle status. |
| `COMPLETED` (`RUN_COMPLETED` event) | Operational | Managed execution finished under §8. |

Control Room **primary** badge is durable `operational_status` when the observability store is reachable. Professional `lifecycle_status` is secondary / engineering.

Durable `FAILED` is allowed only when a Class A `RUN_FAILED` event was actually persisted (§17). Store unavailability is **not** durable `FAILED`. It is a local control-plane fail-safe (`OBSERVABILITY_UNAVAILABLE` / `CONTROL_PLANE_FAILURE`) that Control Room must present as **not durably confirmed** — never as invented `RUN_FAILED`.

---

## 8. Managed run completion law

For a **managed** Control Room / Orchestrator Constructor run:

`operational_status = COMPLETED` and event `RUN_COMPLETED` are allowed **only when all** of the following are true:

1. Professional lifecycle reached `READY_FOR_HANDOFF`.
2. Required `ConstructorHandoff` was successfully **built**.
3. Required handoff persistence returned `CREATED` or `IDEMPOTENT_REPLAY`.
4. The operational completion event was **durably recorded** (Class A — §17).

If required handoff persistence fails:

- `HANDOFF_PERSIST_FAILED` **must** be durably recorded (Class A — §17).
- `RUN_COMPLETED` is forbidden.
- Managed run may transition to durable operational `FAILED` **only if** `HANDOFF_PERSIST_FAILED` itself was durably persisted.
- If the observability persist of that Class A event also fails, apply §17 observability-unavailable semantics. Do **not** claim durable `FAILED` / `RUN_FAILED`.

Legacy invoke with `handoff_store=None` may still exist for Increment 7/9 compatibility. That path is **not** a fully managed Increment 10 run. Control Room must not present it as `COMPLETED` with a fake handoff.

---

## 9. Authorization model

```
RUN_REQUESTED
  → RUN_AUTHORIZATION_STARTED
  → RUN_AUTHORIZED | RUN_DENIED
  → MISSION_BOUND
  → RUN_STARTED
```

`RunRequest` ≠ authorization.

Reuse EOS-SEC trusted issuer / static registry / tool allowlist / project scope. Control Room and Orchestrator **must not** self-assign `allowed_tools`, `write_allowed`, service role, or permissions.

### Safe facts that may be stored / displayed

- `authorization_id`
- `actor_type`
- `policy_version` (`security_policy_version`)
- result (`PASS` / `DENIED`)
- safe denial code (`UNKNOWN_AGENT`, `BLANK_PROJECT`, `AUTHORIZATION_DENIED`, …)

### Never store

credentials, token, service_role, client, secret environment values, issuer internals beyond the safe dict fields already defined on `AgentExecutionContext.to_safe_dict()`.

Do **not** persist the `AgentExecutionContext` object. Persist only named safe fields.

Identity in v0.1 remains transitional (`LOCAL_APPLICATION` / recorded local operator). Verified human Auth is out of Increment 10.

---

## 10. ObservabilityEvent contract

Agent-neutral immutable type: **`ObservabilityEvent`**.

### Required

| Field | Meaning |
|-------|---------|
| `schema_version` | First implementation: `observability_event.v0.1` |
| `event_id` | Unique, never reused |
| `run_id` | Owning run |
| `agent_code` | Tenant role |
| `occurred_at` | Timezone-aware UTC |
| `family` | Closed family — §12 |
| `event_type` | Closed type within family |
| `status` | `OK` \| `DENIED` \| `FAILED` \| `INFO` |
| `title` | Short human line. Not a log dump |

### Optional correlation

`stage_id`, `span_id`, `request_id`, `mission_id`, `orchestration_run_id`, `authorization_id`, `checkpoint_id`, `interrupt_id`, `decision_id`, `artifact_type`, `artifact_id`, `handoff_id`, `tool_name`, `node_name`, `attempt_n`, `resume_n`

`artifact_type` + `artifact_id` is event correlation only. It does **not** replace typed `package_id` / `handoff_id` / exception-set id on `AgentRun`. `snapshot_id` is not an `artifact_id` alias.

### `detail`

Bounded + structured + redacted mapping — §11.

### Invariants

- Append-only. **No UPDATE** of an existing event.
- No secret values.
- No raw payload dumps.
- No one-event-per-BOQ-row.
- Every persist path must run structure validation, bounds, redaction, and secret scan (`assert_no_secrets_in_payload` or equivalent).

---

## 11. Event detail boundary

`detail` must be:

- structured
- bounded
- redacted
- JSON-compatible
- deterministic where applicable (canonical key order for digests if used)

### May contain

counts; safe status; error code; safe reason; safe identifiers; duration_ms; summary; decision code; persist outcome (`CREATED` / `IDEMPOTENT_REPLAY`); exception severity/code (not row dumps).

### Must not contain

DataFrame; candidate rows; full business records; credentials; `.env`; DSN; bearer; API key; service_role; DB connection; Supabase client; `AgentExecutionContext`; model chain-of-thought; raw prompts; arbitrary document contents; unredacted tool errors.

### Hard limits (required)

Implementation 10.1 **must** freeze explicit constants. Normative floor for this spec:

| Limit | Required |
|-------|----------|
| Maximum keys in `detail` | explicit integer |
| Maximum string length per value | explicit integer |
| Maximum nested depth | explicit integer (recommend 2) |
| Maximum list items | explicit integer |
| Maximum title length | explicit integer |
| Maximum event body encoding size | explicit integer |

Unspecified “reasonable” limits are **not** compliant. Overflow fails closed (`OBSERVABILITY_CONTRACT_BLOCKER` or equivalent) — do not truncate secrets into a still-leaking substring as a substitute for bounds.

---

## 12. Event taxonomy

Closed families and types. Unknown family/type fails closed.

### `RUN_CONTROL`

`RUN_REQUESTED` · `RUN_AUTHORIZATION_STARTED` · `RUN_AUTHORIZED` · `RUN_DENIED` · `RUN_STARTED` · `RUN_COMPLETED` · `RUN_FAILED` · `RUN_ABORTED`

### `MISSION`

`MISSION_BOUND`

### `STAGE`

`STAGE_STARTED` · `STAGE_COMPLETED` · `STAGE_FAILED`

Public business vocabulary is **STAGE_***, not LangGraph `NODE_*`. `node_name` may appear only as correlation metadata.

### `TOOL`

`TOOL_CALL_STARTED` · `TOOL_CALL_COMPLETED` · `TOOL_CALL_DENIED`

### `ARTIFACT`

`ARTIFACT_CREATED`

### `EXCEPTION`

`EXCEPTION_RAISED`

### `HITL`

`HUMAN_WAIT_STARTED` · `HUMAN_DECISION_RECEIVED` · `RUN_RESUMED`

### `REALITY`

`REALITY_REFRESH_STARTED` · `REALITY_REFRESH_COMPLETED`

### `RETRY`

`RETRY_REQUESTED` · `RETRY_STARTED` · `REPLAY_DETECTED`

### `HANDOFF`

`HANDOFF_CREATED` · `HANDOFF_PERSISTED` · `HANDOFF_PERSIST_FAILED`

### `SECURITY`

`SECURITY_EVENT`

Example `detail` security codes (safe facts only):

`AUTHORIZATION_PASS` · `AUTHORIZATION_DENIED` · `SCOPE_VALIDATION_PASS` · `SCOPE_EXPANSION_DENIED` · `CHECKPOINT_STALE` · `CHECKPOINT_MISMATCH` · `FRESHNESS_GATE_PASS` · `FRESHNESS_GATE_FAILED` · `HANDOFF_IMMUTABILITY_CONFLICT` · `OBSERVABILITY_WRITE_FAILED` · `OBSERVABILITY_RECOVERY_REQUIRED`

Do not attach secret evidence to security events.

`OBSERVABILITY_WRITE_FAILED` / `OBSERVABILITY_RECOVERY_REQUIRED` may be persisted **only when** the durable store is actually available (recovery/audit after outage). They must not be invented in-memory and later claimed as historical Class A truth if they were never appended.

---

## 13. Trace / stage / span model

Hierarchy:

```
AgentRun     = Trace boundary (one professional invocation)
  └── Stage  = professional observable execution step
        └── Event = point-in-time immutable fact
```

v0.1 **does not** create a second independently mutable Span truth store.

Stage / span **view** is projected from:

- `STAGE_STARTED`
- `STAGE_COMPLETED`
- `STAGE_FAILED`

**Events are the canonical observability history.**

Current `AgentRun` projection may be materialized for fast query. It **must** remain reconstructable from:

1. immutable run identity, plus
2. the append-only event log.

This is **observability event sourcing**, not business-domain event sourcing. Professional artifacts remain in the business plane (package, handoff, HITL contracts). Events **point at** those artifacts; they do not replace them.

---

## 14. Constructor professional stage catalog

Initial Constructor `stage_id` catalog (stable codes):

| Order | `stage_id` | Professional meaning |
|------:|------------|----------------------|
| 01 | `AUTHORIZATION` | Issuer / policy / project bound |
| 02 | `MISSION_BINDING` | Scope bound; extra-scope fail-closed |
| 03 | `REALITY_READ` | Trusted scoped read |
| 04 | `CANDIDATE_ASSEMBLY` | Physical package build |
| 05 | `LABOR_NORM_RESOLUTION` | Metadata attach; unresolved does not drop candidates |
| 06 | `EXCEPTION_ANALYSIS` | WAIT / READY / FAIL routing |
| 07 | `HUMAN_GATE` | Durable interrupt |
| 08 | `REALITY_REVALIDATION` | Fresh read after resume |
| 09 | `HANDOFF_PREPARATION` | Build `ConstructorHandoff` |
| 10 | `HANDOFF_PERSISTENCE` | Store `CREATED` / `IDEMPOTENT_REPLAY` |
| 11 | `RUN_COMPLETION` | Operational completion under §8 |

Admission and later agents get **their own** catalogs under the same stage-view contract. They must not reuse Constructor stage codes for different professional work.

### Stage view states

`NOT_STARTED` · `RUNNING` · `WAITING` · `BLOCKED` · `FAILED` · `COMPLETED`

Plus: `started_at`, `ended_at`, `duration`, current message, last safe event.

No decorative / fake progression. A stage is `RUNNING` only after `STAGE_STARTED` without a terminal stage event. `WAITING` is driven by HITL events + operational status, not CSS animation.

Presentation colors (green / blue / yellow / orange / red / gray) belong to the UI adapter, **not** this runtime contract.

---

## 15. ObservabilityRecorder

Shared agent-neutral port: **`ObservabilityRecorder`**.

This protocol is part of **Increment 10.1**, together with a safe **in-memory test implementation**. That double is contract proof only. It is not production durability.

Responsibility: record immutable safe events. For authoritative transitions the recorder must use the store’s atomic append+project operation (§18), including in the in-memory double.

Conceptual API:

- `record_event(...)`
- optional helpers: `start_stage(...)`, `complete_stage(...)`, `fail_stage(...)`

Helpers **only create canonical events**. They must not maintain a competing span store.

Run Control (10.2) and runtime instrumentation (10.3) **inject** this port. They must not create a private event sink.

### Recorder must not

- decide professional status
- calculate exceptions
- change scope
- authorize tools
- build `CandidatePackage`
- make human decisions
- start the next agent
- hold credentials

---

## 16. Event emission locations

**Combination with one recorder abstraction.**

Emit from:

- Run Control (request, identity, start)
- Authorization boundary
- LangGraph **node wrapper** (not inside remainder math)
- Trusted tool boundary (allow / deny / complete)
- HITL wait / resume
- Fresh-reality path
- Artifact creation (package / exception-set references)
- Handoff persistence
- Security denial paths
- Run completion / failure / abort

Do **not**:

- add UI copy into core professional functions
- instrument every Python function
- couple events to Streamlit
- make LangGraph the only possible wrapper (if the graph is replaced, wrappers change; contracts / store / query / Control Room stay)

---

## 17. Observability write failure policy

### Class A — critical control / audit events

Required Class A set:

`RUN_REQUESTED` · `RUN_AUTHORIZATION_STARTED` · `RUN_AUTHORIZED` / `RUN_DENIED` · `MISSION_BOUND` · `RUN_STARTED` · `HUMAN_WAIT_STARTED` · `HUMAN_DECISION_RECEIVED` · `RUN_RESUMED` · `HANDOFF_CREATED` · `HANDOFF_PERSISTED` · `HANDOFF_PERSIST_FAILED` · `RUN_COMPLETED` · `RUN_FAILED` · `RUN_ABORTED` · `SECURITY_EVENT` for denied / critical security actions

`RUN_FAILED` is Class A **only** when professional/runtime failure occurred **while the observability store was available** and the event can actually be appended.

### Law: no durable event → no claim of durable state

```
NO DURABLE EVENT → NO CLAIM OF DURABLE STATE.
```

### Class A write failure (store unavailable or append rejected)

A. Critical Class A observability write failure **immediately forbids** further managed execution.

B. Runtime / Run Control enters a **local** fail-safe: `CONTROL_PLANE_FAILURE` / `OBSERVABILITY_UNAVAILABLE` (or equivalent process outcome). This is **not** a durable `AgentRun.operational_status`. It does **not** mean a durable `RUN_FAILED` event exists.

C. The system **MUST NOT**:

- continue professional execution;
- create a handoff;
- emit `RUN_COMPLETED`;
- show the user a false durable `FAILED` / `RUN_FAILED` state.

D. When the durable store is available again, recovery/audit **MAY** persist a recovery fact (`OBSERVABILITY_WRITE_FAILED`, `OBSERVABILITY_RECOVERY_REQUIRED`) **only if** that event is actually durably appended.

E. Control Room, if the store is unreachable or the run is not durably confirmed, **MUST** show:

`OBSERVABILITY UNAVAILABLE / RUN STATE NOT DURABLY CONFIRMED`

It must **not** invent `RUN_FAILED`.

F. A managed run that cannot persist a required Class A event must stop invisibility: no further nodes, no handoff, no fake completion.

### Class B — non-critical telemetry

Optional performance counters, diagnostic timing enrichments, non-essential UI hints.

May be best-effort later. Class B must **never** be used as authoritative run truth.

---

## 18. Observability store boundary

Agent-neutral protocol. No arbitrary SQL. No generic `update_run()`. No generic UPDATE/DELETE of events.

Minimum operations:

| Operation | Law |
|-----------|-----|
| `create_run(run)` | Insert run identity. Fail if `run_id` exists with different identity |
| `get_run(run_id)` | Read current projection |
| `append_event_and_project_run(event, expected_projection_version, projection_change)` | **MUST**: atomically append the event and apply the constrained projection change, or commit neither |
| `list_events(run_id, filters)` | Bounded |
| `list_runs(filters)` | Bounded |

A standalone `append_event` without projection update is **not** sufficient for authoritative operational transitions.

Exact API names are implementation detail. **Atomicity and version checking are normative.**

### Atomicity MUST

Any authoritative operational transition that changes:

- `operational_status`
- `current_stage_id`
- WAIT / interrupt state
- completion
- failure
- abort
- retry state

**MUST** persist the canonical event **and** the corresponding current `AgentRun` projection **atomically**, or through an equivalent concurrency-safe transactional mechanism.

Invariant:

```
EVENT_ACCEPTED  ⇔  RUN_PROJECTION_UPDATED_TO_MATCH
```

No window where Control Room permanently sees a projection without its event, or an event without the corresponding projection.

If the atomic transaction fails: **neither** authoritative change is committed. Apply §17 if the failed write was Class A.

Concurrency control is required. Conceptually one of:

- `projection_version` optimistic concurrency;
- compare-and-set;
- database transaction with expected version.

Caller supplies `expected_projection_version`. Mismatch fails closed (conflict). Do not last-write-wins.

Events remain immutable. Projection updates are **constrained** (allowed fields only).

Implementations (in-memory, local file/SQLite, disposable test Postgres) hide behind this protocol. Product Supabase is **not** an Increment 10 implementation target.

---

## 19. Run projection

`AgentRun` current fields may be materialized for Control Room queries. `projection_version` starts at create and increments on every accepted atomic projection change.

Every authoritative change to:

- operational status
- current stage
- wait / interrupt identity
- completion
- failure / abort
- retry state

**must** correspond to a durable event **and** an atomic projection update (§18).

```
NO DURABLE EVENT → NO CLAIM OF DURABLE STATE.
```

Control Room must never show a durable status that has no corresponding recorded runtime fact.

If the observability store is unavailable, Control Room shows `OBSERVABILITY UNAVAILABLE / RUN STATE NOT DURABLY CONFIRMED` — not a guessed badge.

If projection and event log disagree after the store is available, **event log wins** after reconstruction. A projection that cannot be rebuilt is a defect. Reconstruction must not invent events.

---

## 20. Local durability vs production storage

Increment 10 **may** prove durability locally (same discipline as Increment 8 / 9.4 test Postgres: isolated, no product DDL).

**No** production Supabase DDL/RLS in Increment 10 implementation slices 10.1–10.10 unless a later **separate** security review explicitly authorizes it.

Architecture must remain compatible with future tables:

- `agent_runs`
- `agent_run_events`
- `agent_interrupts`
- `agent_handoffs`

Future production schema requires separate: DDL review, RLS review, service-role isolation, retention/privacy review, indexes, rate limits, audit review.

Do not implement those in this increment.

LangGraph checkpoint remains the **resume** plane. Observability store is the **Control Room** plane. Handoff store is the **next-agent** plane. HITL store is the **interrupt/decision** plane. Do not collapse these four planes into one table “because they all have run_id”.

---

## 21. Query / read model

Shared agent-neutral port: **`AgentControlRoomQueryPort`**.

Conceptual operations (all **bounded**; no arbitrary DB access from UI):

- `get_run(run_id)`
- `list_runs(agent_code?, project_code?, month_key?, status?, orchestration_run_id?)`
- `list_events(run_id, after?, family?, limit?)`
- `get_stage_map(run_id)`
- `get_human_gate(run_id)`
- `list_artifacts(run_id)`
- `get_handoff_view(run_id)`
- `get_security_summary(run_id)`
- `get_fleet_snapshot(...)`
- `get_next_expected_action(run_id)` — deterministic projection or `NULL` / `NOT_AVAILABLE`; never UI-invented

Query port returns **read models** (DTOs), not LangGraph checkpoint blobs, not full packages, not `AgentExecutionContext`.

`next_expected_action` is **not** free text from Streamlit. v0.1 **must** use deterministic stage-catalog projection from:

- `agent_code`
- durable `operational_status` (only if store-confirmed)
- `current_stage_id`
- stage catalog
- open HITL state
- handoff state

If any required input is missing or the store is unavailable: return `NULL` / `NOT_AVAILABLE`. Presentation adapter maps codes to labels; it **MUST NEVER** invent the next action.

Examples (codes, not UI copy):

| Authoritative condition | `next_expected_action` |
|-------------------------|------------------------|
| `REALITY_READ` completed, not waiting | `CANDIDATE_ASSEMBLY` |
| `operational_status = WAITING_FOR_HUMAN` | `HUMAN_DECISION_REQUIRED` |
| lifecycle `READY_FOR_HANDOFF`, handoff not persisted | `HANDOFF_PREPARATION` or `HANDOFF_PERSISTENCE` per catalog |
| `operational_status = COMPLETED` | `NONE` |

Streamlit and any future web UI call **only**:

1. Run Control API / port (start, resume decision submit)
2. this Query Port

---

## 22. Control Room role

Streamlit is **one presentation adapter**.

It does **not**:

- read LangGraph memory directly
- inspect checkpoint internals as UX truth
- infer execution from BOQ / plan / constraint tables
- calculate lifecycle itself
- hold durable run state in `st.session_state`
- start subprocess agents directly
- use arbitrary Supabase SQL

Closing the browser must **not** stop a run.

Reopening the page must reconstruct history from the **durable observability store** (and artifact/handoff/HITL references). Checkpoint may still be required to **resume**; it is not the human-readable trace.

Live updates in Streamlit v0.1: **bounded polling / refresh** against the Query Port. Not an event bus requirement. Not websocket vendor lock-in.

---

## 23. Control Room information architecture

Professional visual hierarchy. Constructor labels may appear; layout and query shapes must stay agent-neutral.

### Surface 1 — Command header / Run Passport

Agent name (Constructor: «Агент формирования кандидатного состава»); operational status; project; month; mission; `run_id`; `orchestration_run_id`; initiator; authorized_by; trigger reason; requested_at; started_at; elapsed time; current stage; last action; `next_expected_action` from Query Port only; human decision required yes/no.

If the Query Port returns `NOT_AVAILABLE` or the store is down, show no next-action guess — use the observability-unavailable presentation (§17).

### Surface 2 — Live Process Map

Central visual. Constructor stages §14, presented as:

```
Authorization
  → Mission binding
  → Reality read
  → Candidate assembly
  → Labor norms
  → Exception analysis
  → Human gate
  → Fresh reality
  → Handoff preparation
  → Handoff persistence
  → Completed
```

Every node driven by recorded stage events. Presentation colors are adapter-only.

### Surface 3 — Live Timeline

Human-readable: time, event title, stage, status, short safe explanation.

Example:

```
17:34:12  Mission scope bound.
17:34:13  126 candidates assembled.
17:34:14  3 unresolved labor norms detected.
```

Technical detail only via drill-down. Raw system logs are **not** the primary UX.

### Surface 4 — Human Decision

When `WAITING_FOR_HUMAN`: large explicit panel from real `ConstructorHumanDecisionRequest`:

- why the agent stopped
- exception code
- evidence references
- allowed decisions
- `interrupt_id`
- waiting since / duration
- authorized decision actor (transitional identity noted)
- what happens after each allowed decision

Submission calls the **existing controlled HITL path**. UI must not mutate lifecycle/checkpoint directly.

### Surface 5 — Artifacts

Candidate Package, Exception Analysis, Constructor Handoff: `artifact_type` + typed id (`package_id` / exception-set id / `handoff_id`), created_at, status, snapshot/reference, safe counts, provenance. Read-only drill-down. **No** giant DataFrame by default. `artifact_id` on events is correlation only — not a replacement for those typed ids.

### Surface 6 — Handoff / digital organization

Constructor status + handoff arrow + target role `MONTHLY_PLAN_ADMISSION_AGENT`.

Future chain (placeholders allowed):

```
Orchestrator
  → Constructor
  → Admission
  → Constraint
  → Resource
  → Economic
  → Management Decision
```

Increment 10 **must not** implement those agents. Not-started roles are schema placeholders, not fake RUNNING states.

### Surface 7 — Engineering trace

`run_id`, `request_id`, `mission_id`, `thread_id`, `checkpoint_id`, `authorization_id`, `interrupt_id`, `decision_id`, `snapshot_id`, `package_id`, `handoff_id`, `attempt_n`, `resume_n`, stage timings, tool calls, retries, replay events, security events, errors.

Never credentials.

### Surface 8 — Fleet / Agents Now

Agent-neutral cards/columns: agent role, state, project, month, mission, current stage, elapsed time, human wait?, last event, orchestration run.

Constructor may be the only live agent. Adding Admission must not require a Control Room rewrite.

---

## 24. Run start UX

Button «Запустить агента» **must not** call Constructor directly.

```
Human fills allowed mission inputs
  → Control Room creates RunRequest
  → Run Control validates request
  → Run Control mints request_id / run_id
  → Authorization executes
  → Mission is bound
  → Only after authorization: runtime starts
  → Control Room reads truth from observability events
```

Visible sequence:

```
Запрос на запуск
  → Проверка полномочий
  → Разрешение
  → Формирование миссии
  → Запуск агента
```

---

## 25. Manual vs Orchestrator start

**Same Run Control path.** Difference only in initiator / trigger metadata.

| | HUMAN | ORCHESTRATOR |
|--|--------|--------------|
| `initiator_type` | `HUMAN` | `ORCHESTRATOR` |
| `orchestration_run_id` | optional | **required** |
| Runtime | same Constructor managed start | same |

No separate hidden runtime path.

`SYSTEM_EVENT` does not skip the orchestrator. It does not create a Constructor `RunRequest`.

---

## 26. Resume UX

Normal HITL resume is **not** a new agent launch and **not** a new `RunRequest`.

It **MUST NOT**:

- create a new `RunRequest`;
- mint a new `request_id`;
- mint a new `run_id`;
- mint a new `mission_id`;
- change `thread_id`.

It uses: same `request_id`, same `run_id`, same `mission_id`, same `thread_id`. `resume_n` increments by 1 after a successful human resume.

Human decision **must** be persisted before runtime continuation.

Order:

1. Human decision persisted first (HITL store / existing resume command).
2. Events: `HUMAN_DECISION_RECEIVED` → `RUN_RESUMED` → `REALITY_REFRESH_STARTED` → `REALITY_REFRESH_COMPLETED`.
3. Package rebuilt; exceptions re-evaluated; continue.

Control Room must show this sequence from events. Do not claim “fresh read happened” without `REALITY_REFRESH_*`.

`RESUME` is a control action / event / audit initiator of continuation. It is **not** `RunRequest.initiator_type`.

---

## 27. Retry / Replay

### RETRY

Same `run_id`. `attempt_n` increments. Reason **mandatory**. Not a new `RunRequest`. Not a new `mission_id`. Not a new `thread_id`.

Allowed **only** for a **declared retryable TECHNICAL** failure.

Retry **MUST NOT** bypass or reset:

- authorization
- mission scope
- scope validation
- human gate
- freshness gate
- checkpoint validation
- security denial
- professional exception classification
- handoff immutability
- data contract blocker
- professional `FAILED` outcome

If authorization expired: re-authorize through the EOS-SEC policy boundary **before** retry continuation. Do not invent permissions.

If mission/scope changed: retry **cannot** widen scope. A materially changed mission requires a **NEW RUN** (`RunRequest` + new `run_id` + `predecessor_run_id` if replacing a completed run).

If a human decision is required: `RETRY` cannot substitute for HITL.

If freshness failed: `RETRY` must re-run the freshness path, not skip it.

### REPLAY

Idempotent persistence, crash-recovery observation, or audit fact (`REPLAY_DETECTED`). Not a new professional run. Not a `RunRequest`.

### Completed professional rerun

New `RunRequest`. New `run_id`. `predecessor_run_id` = old run. Full authorization again.

---

## 28. Abort / stop semantics

Do **not** define a generic “kill Python process” button.

Distinguish:

| Kind | Increment 10 |
|------|----------------|
| Professional ABORT decision | Existing HITL `ABORT_RUN` (or equivalent allowed decision) |
| Controlled run abort | Operational `ABORTED` + `RUN_ABORTED` after the professional abort is applied |
| Emergency kill switch | **Out of Increment 10.** Separate EOS-SEC / runtime capability |

UI must not invent unsafe general process-kill behavior.

---

## 29. Security / privacy

Mandatory:

- No `.env` reads into observability.
- No credential values, service role, bearer tokens.
- No raw exception dumps that may contain secrets.
- No `AgentExecutionContext` persistence (safe named fields only).
- No DB clients / connections.
- No unrestricted tool payloads.
- No hidden model thoughts / chain-of-thought.
- No arbitrary prompt history.

Every event, before persistence:

1. structure validation
2. payload bounds
3. redaction
4. secret scan

Fail closed on violation. Control Room displays the same safe facts; it is not a second, weaker filter.

---

## 30. World-class visualization principles

**Adopt (concepts, not vendors):**

- Run → stages → events hierarchy
- Current-state view separate from history
- Live stage map
- Timeline
- Tool visibility
- Handoff visibility
- Latency per stage
- First-class human intervention
- History after browser close
- Filter by run / agent / project / status
- Fleet view
- Security visibility
- Artifact provenance
- Drill-down technical trace
- Redaction as a gate

**Do not copy and do not depend on:** Langfuse, LangSmith, OpenTelemetry collector, OpenAI Agents SDK, or another SaaS dashboard.

Execution OS remains sovereign and vendor-neutral. LLM-token dashboards and prompt playgrounds are **not** the Control Room.

---

## 31. What not to build

- Control Room inside Page10B
- MPCA-003 resurrection / 175-row agent workbench as primary UX
- Page51 inferred runtime
- Agent state inferred from BOQ / business tables
- `st.session_state` as durable truth
- Giant agent DataFrame as primary UX
- Hidden agent-to-agent prompt chat
- Direct Constructor → Admission invocation
- Production Supabase schema in this increment
- New LLM dependency
- Observability logic that reimplements lifecycle / exceptions / remainder
- Vendor observability product as runtime
- `RUN_COMPLETED` without §8
- Silent `mission_id` mint in managed runs
- Generic process-kill button
- Streamlit-invented `next_expected_action`
- Durable `RUN_FAILED` claimed when the observability store was unavailable
- `RESUME` / `RETRY` as `RunRequest.initiator_type`

---

## 32. Increment 10 implementation roadmap

Frozen sequence. Do not skip query before UI. Do not start 10.1 in this documentation phase.

| Slice | What |
|------:|------|
| **10.1** | Contracts + **ObservabilityRecorder Protocol** + **in-memory test recorder** + payload validation / bounds: `RunRequest`, `AgentRun`, `ObservabilityEvent`, enums, stage catalog |
| **10.2** | Run Control: request, identity, authorization, mission binding, managed start. **Injects** `ObservabilityRecorder`. No private event sink |
| **10.3** | Runtime instrumentation on the **same** Recorder Protocol: node wrappers, HITL, fresh reality, artifact, handoff, security |
| **10.4** | Durable `ObservabilityStore` / durable recorder **behind the accepted interface**; constrained atomic projection |
| **10.5** | Durable local persistence proof: separate-process recovery; **no** product Supabase DDL |
| **10.6** | Query / read model: headless Control Room queries including deterministic `next_expected_action` |
| **10.7** | Professional Streamlit Control Room: Run Passport, Live Process Map, Timeline, Engineering Trace, Fleet base |
| **10.8** | HITL visual: WAIT, decision, resume, fresh-reality visualization |
| **10.9** | Artifact / Handoff / Digital Organization visualization |
| **10.10** | Full live-run proof + regression + EOS-SEC + docs checkpoint |

### Recorder dependency law

10.1 **must** include `ObservabilityRecorder` and a safe **in-memory test implementation**. That recorder is **TEST / CONTRACT PROOF only**. It does **not** make a run production-durable.

10.2 Run Control **must** receive `ObservabilityRecorder` by injection. It may prove `RUN_REQUESTED`, `RUN_AUTHORIZATION_STARTED`, `RUN_AUTHORIZED` / `RUN_DENIED`, `MISSION_BOUND`, `RUN_STARTED` through that recorder. It **must not** invent a private log/event sink.

10.3 uses the **same** Recorder Protocol.

10.4 implements durable store / durable recorder behind that interface.

10.5 proves separate-process durability.

A fully managed durable run requires 10.4 / 10.5. In-memory 10.1/10.2 proofs are not Increment 10 Done.

---

## 33. Definition of Done

Increment 10 is DONE only when **all** hold:

1. Approved initiator creates a real `RunRequest`.
2. Authorization is durably visible.
3. Mission binding is visible.
4. Constructor starts **outside** UI lifecycle.
5. Control Room shows `RUNNING`.
6. Real stages progress `NOT_STARTED → RUNNING → COMPLETED`.
7. Timeline shows real structured events.
8. Constructor reaches `WAITING_FOR_HUMAN` in the proof scenario.
9. Control Room displays Human Gate from **real** interrupt data.
10. Human submits an allowed decision.
11. **Same** `run_id` resumes.
12. Fresh reality read is visibly recorded.
13. Candidate package is rebuilt.
14. Exceptions are re-evaluated.
15. `READY_FOR_HANDOFF` occurs.
16. `ConstructorHandoff` is created.
17. Handoff persistence succeeds (`CREATED` or `IDEMPOTENT_REPLAY`).
18. `RUN_COMPLETED` is durably recorded.
19. Browser / Streamlit can close.
20. Reopening reconstructs the complete trace.
21. No secret-bearing event/state is persisted or displayed.
22. All Constructor Increments 1–9 regressions PASS.
23. EOS-SEC release gate PASS.
24. Architecture can host Admission Agent without cloning Constructor-specific control plane.

A page that “opens” is **not** Done.

---

## 34. Out of scope for Increment 10

- Admission / Constraint / Resource / Economic / Management agent implementation
- Full Monthly Plan Orchestrator runtime
- Production `agent_runs` / `agent_run_events` Supabase DDL/RLS
- Generic autonomous agent-to-agent communication
- Robots / drones / Physical AI execution
- Agent Runtime Reference v1.0 extraction
- Verified production Auth / RBAC
- Kill-switch process termination UX

Those occur later.

---

## 35. Recovery / release law

Increment 10 follows the same disciplined lifecycle:

```
architecture
  → implementation increment
  → focused tests
  → regression
  → semantic review
  → Lessons_2 gate
  → EOS-SEC gate
  → exact-file commit
  → push WIP
  → docs checkpoint
  → release to main
```

`AGENT_RUNTIME_PROGRESS.md` remains unchanged until an **accepted** increment checkpoint is ready.

This specification **does not** authorize implementation. Slice 10.1 starts only after explicit authorization.

---

## 36. Spec status

```
SPEC STATUS:
PROPOSED / NOT YET IMPLEMENTED

IMPLEMENTATION AUTHORIZATION:
NONE

CURRENT PRODUCT PROGRESS:
9 / 10

NEXT IMPLEMENTATION:
Increment 10.1 — Agent-neutral contracts + ObservabilityRecorder Protocol
```

Do **not** claim 10/10.
