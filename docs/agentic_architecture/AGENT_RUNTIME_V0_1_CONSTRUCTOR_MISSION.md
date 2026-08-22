# Agent Runtime v0.1 — Constructor Mission

**Status:** ARCHITECTURE DESIGN ONLY. Does not authorize implementation, LangGraph install, SQL, or product writes.

**Parent law:** commit `0e16e5fb9090eba77e159f27651ba528517a2959` (`docs/agentic_architecture/**`).

**This document** specifies the first real digital employee runtime: *Agent Runtime v0.1 — Constructor Mission*.

It does **not** replace Page52 (organizational description) or EOS-SEC (`security/*.md`).

**Architecture-review correction:** this revision fixes review comments (freshness after durable HITL, dual scope enforcement, no service bypass, durable HITL law, exception taxonomy). It does **not** authorize code.

---

## 1. Purpose

Спроектировать точный технический контур, в котором

**Агент формирования кандидатного состава месячного плана**

исполняет **миссию** (project + month + explicit business scope), а не кнопку Streamlit и не таблицу из 175 строк.

v0.1 должен уметь:

- принять `ConstructorMission`;
- читать реальность **только внутри mission scope** (read-time filter + post-read assertion);
- классифицировать BOQ существующим deterministic ядром MPCA-001;
- собрать **physical candidate package**;
- прикрепить labor-norm **metadata** (shared capability, не отдельный агент);
- не выбрасывать physical candidate из-за `UNRESOLVED` нормы;
- остановиться на Human Interrupt **только** при BLOCKING exceptions;
- после durable pause **обязательно** перечитать fresh reality;
- иначе зафиксировать structured handoff к роли Admission **только** из non-stale reality;
- **не** писать `monthly_plan_lines_v2` / NOT_SENT / SENT.

LangGraph **ещё не установлен**. Этот документ — закон для следующего implementation release.

---

## 2. Runtime boundary

### Engineering law

```
AGENT ≠ DASHBOARD
AGENT ≠ DATAFRAME
AGENT ≠ STREAMLIT CALLBACK
AGENT ≠ CHATBOT
NO SERVICE BYPASS
DURABLE HUMAN PAUSE INVALIDATES EXECUTION FRESHNESS
IN-PROCESS INTERRUPT ≠ DURABLE HITL
```

| Layer | Role in v0.1 |
|-------|----------------|
| **Python** | Deterministic business execution: domain, skills, validators, calculations, security adapters. **REUSE MPCA-001.** |
| **LangGraph** | Workflow / state machine: nodes, conditional edges, interrupt/resume, checkpoint. Orchestrates calls; does not reimplement remainder math as prompts. |
| **Supabase** | Shared operational reality + (later) business/audit run records. Agents re-read current data. No hidden prompt dump. |
| **EOS-SEC** | External security boundary. Context issuer, tool allowlist, trusted read executor, fail-closed. |
| **LLM adapter** | Not required for v0.1 happy path. Reserved for future semantic mapping (BOQ ↔ operation ↔ norm source). Never arithmetic. Never authoritative norms. Never freshness. |
| **Streamlit** | Agent Control Room / Human Decision Surface / evidence drill-down. Closing the page must not kill the run **once** a durable checkpoint exists. Streamlit is **not** HITL storage. |

### In v0.1 / out of v0.1

**In**

- Constructor mission runtime (READ-ONLY).
- Scope binding beyond project+month, enforced twice (read-time + assertion).
- Candidate package + exceptions + handoff object (in memory / designed persistence; not plan INSERT).
- LaborNormResolver as **stub shared capability** (attach metadata; no GESN connector).
- Freshness law after durable HITL and before handoff.

**Out**

- MPCA-002 live write (`create_not_sent_plan_lines`).
- Admission / Resource / Economic agents.
- Page10B workbench as runtime.
- `monthly_planning_orchestrator_service.py` as Constructor graph (это MPO feasibility runtime, другая роль).
- LLM provider choice.
- Production identity / RBAC.
- Claiming `HITL COMPLETE = YES` without durable checkpoint + interrupt persistence + fresh reread.

MPCA-002 / MPCA-003 dirty worktree files **must not** be modified to “start” this runtime.

---

## 3. Mission contract

`ConstructorMission` — цифровое задание сотруднику.

```python
# DESIGN ONLY — not a source file

from typing import NotRequired, TypedDict

ScopeValue = str | list[str]  # exact code(s); omit/None/empty/"ALL" => ALL

class ConstructorMission(TypedDict):
    schema_version: str          # "constructor_mission.v0.1"
    mission_id: str              # uuid
    project_code: str            # required, specific; never "Все"
    month_key: str               # stored product key, e.g. "сентябрь-2026"
    facility_scope: NotRequired[ScopeValue]
    discipline_scope: NotRequired[ScopeValue]
    system_scope: NotRequired[ScopeValue]
    iwp_scope: NotRequired[ScopeValue]
    queue_scope: NotRequired[ScopeValue]
    requested_by: str            # transitional actor; see §12 / §20
    requested_at: str            # ISO-8601 UTC
    orchestration_run_id: NotRequired[str]
```

Rules:

- `month_key` is the **stored** month. Canonical `2026-09` via existing `utils.month_key.normalize_month_key`. Agent must not use `date.today()`.
- Optional scope omitted / empty / `"ALL"` = **ALL inside this project+month**.
- Optional scope set = agent **MUST** restrict work to that set. Fail closed if a provided value cannot be bound (unknown discipline code with zero rows is valid empty result, not “fall back to whole project”).
- Presentation filters, search text, Streamlit widget selection, visor status (`ДОСТУПНО` / `ВЫПОЛНЕНО`) are **not** automatically mission scope.

Intake: Control Room or trusted local caller builds this object **explicitly**. Copying Page10B `render_scope_filters()` dict into the agent is forbidden (that is the 2026-08-22 deviation).

Mission scope is **immutable** for a run. It must pass unchanged through:

```
MISSION
  → TRUSTED READ
  → SCOPE ASSERTION
  → CLASSIFICATION
  → PACKAGE
  → EXCEPTION
  → HANDOFF
```

---

## 4. Scope contract

`MonthlyPlanningScope` is the **same** business object for UI display and for the agent.

```python
# DESIGN ONLY

class MonthlyPlanningScope(TypedDict):
    project_code: str
    month_key: str
    month_key_canonical: str
    facility_scope: list[str] | None   # None => ALL
    discipline_scope: list[str] | None
    system_scope: list[str] | None
    iwp_scope: list[str] | None
    queue_scope: list[str] | None
```

Normalization: mission → scope. Lists are exact codes after trim; comparison case policy = existing grain helpers (uppercase for candidate id; filter match must be defined once and reused).

### Dual enforcement (mandatory)

Scope is enforced **twice**. Neither layer replaces the other.

**1. READ-TIME SCOPE ENFORCEMENT**

Trusted read adapter must, **where technically possible**, read immediately:

- `project_code`
- `month_key` (for month-scoped sources such as existing plan lines)
- optional mission dimensions that exist on the allowlisted columns

It must **not** treat “load entire project, filter later” as the default architecture when the allowlist already contains facility / discipline / system / IWP columns.

**2. POST-READ SCOPE ASSERTION**

`bind_scope_to_mission(df, MonthlyPlanningScope)` remains a **mandatory deterministic hard gate**.

After every trusted read (initial `load_reality` and later `refresh_reality`):

- every returned row **must** belong to the mission scope;
- extra-scope rows → fail closed (`DATA_CONTRACT_BLOCKER` / `AMBIGUOUS_SCOPE`), not silent drop-and-continue as if the mission were ALL;
- empty in-scope result is valid (zero candidates), **not** a fallback to the rest of the project.

Query filtering does **not** replace this assertion. Post-filter does **not** justify an uncontrolled project-wide read.

### Adapter debt (implementation, not this design checkpoint)

Current `load_constructor_scope(project_code)` filters only `project_code`. Allowlist includes `facility_building`, `construction_discipline`, `system_label`, `iwp_id` — enough to bind facility/discipline/system/IWP after trusted read, still inside project. Runtime v0.1 **requires a secure adapter** so those dimensions can be applied at read time **and** re-asserted after read. Until that adapter exists, a scoped mission must not be executed as “whole-project MPCA-001 then hope bind happens”.

`construction_queue` is **not** on `SCOPE_SELECT_COLUMNS` today. `queue_scope` therefore requires a **narrow allowlist extension** (still READ, still trusted executor) before queue can be enforced. Until that column is allowlisted, a mission that **sets** `queue_scope` must **FAIL CLOSED** (`AMBIGUOUS_SCOPE` / `DATA_CONTRACT_BLOCKER`) — not silently ignore queue and scan the rest of the project.

Status / BOQ search stay UI-only.

### Scope regression law

For mission `PRJ_001_БХК` / `сентябрь-2026` / facility X / discipline `Вентиляция`, a runtime test **must** prove that returned/scanned **business** rows after the scope gate belong **only** to that mission. Regression to whole-project scan (historically 447 rows / 175 candidates) is **not** acceptable.

---

## 5. State model

Do **not** put full DataFrames, raw traces, or 175 candidate rows into LangGraph state.

Split four planes:

| Plane | What | Where |
|-------|------|--------|
| **Runtime state** | ids, lifecycle, current node, interrupt id, snapshot/package/handoff **references**, counts | LangGraph state + checkpoint |
| **Business result / package artifact** | compact candidate package | separate object (`package_id`), not graph bloat |
| **Audit / trace** | step events, redacted | `agent_run_events` (append-only) |
| **Persistent references** | snapshot/package/handoff/interrupt ids | runtime state points at them |

### Recommended graph state (small)

```python
# DESIGN ONLY — ConstructorMissionState (LangGraph)

class ConstructorMissionState(TypedDict):
    schema_version: str                 # "constructor_runtime_state.v0.1"
    run_id: str
    agent_code: str                     # MONTHLY_PLAN_CONSTRUCTOR
    agent_version: str                  # "0.1"
    mission_id: str
    orchestration_run_id: str | None

    project_code: str
    month_key: str
    scope: MonthlyPlanningScope         # immutable mission scope

    lifecycle_status: str               # see §6
    current_node: str | None
    started_at: str
    updated_at: str
    completed_at: str | None

    execution_context_ref: str          # authorization_id from AgentExecutionContext
    input_snapshot_id: str | None       # current reality snapshot
    snapshot_read_at: str | None        # ISO-8601 UTC of last successful read
    pre_interrupt_snapshot_id: str | None
    package_id: str | None              # candidate package artifact id
    handoff_id: str | None
    interrupt_id: str | None            # active HumanInterrupt, if any
    pending_human_decision_id: str | None

    scanned_count: int                  # AFTER scope gate, not whole-project
    candidate_count: int
    excluded_completed_count: int
    excluded_no_remainder_count: int
    already_planned_count: int
    exception_blocking_count: int
    exception_non_blocking_count: int
    exception_warning_count: int
    freshness_ok: bool | None

    labor_norm_summary: LaborNormSummary
    error_code: str | None
    error_message: str | None           # already redacted
```

Graph state holds **references + summaries**. It does **not** hold the full candidate table.

### Business result vs package artifact

Preferred graph/Control Room surface:

- `candidate_package_reference` (`package_id`)
- summary / counts
- bounded exception context

```python
class ConstructorBusinessResult(TypedDict):
    package_id: str
    run_id: str
    scope: MonthlyPlanningScope
    candidate_package_reference: str    # same as package_id; artifact lives separately
    candidate_ids: list[str]            # ids only; KEEP constructor_candidate_id
    exclusions_summary: dict[str, int]
    exceptions: list[ExceptionRecord]   # bounded; groups, not 175-row dump
    labor_norm_summary: LaborNormSummary
    snapshot_id: str
    generated_at: str
```

The **full** compact candidate package is a **separate business artifact** (object store / later `agent_packages` if needed). Control Room shows summary first. Large rows = evidence drill-down only.

```python
class CandidateRecord(TypedDict):
    candidate_id: str
    project_code: str
    month_key: str
    facility: str
    discipline: str
    system: str
    iwp: str
    boq_code: str
    boq_name: str
    unit: str
    remaining_qty: float
    already_planned_qty: float
    available_to_add_qty: float          # AVAILABLE PHYSICAL QUANTITY
    availability_status: str
    labor_norm_status: str               # VALIDATED | PROVISIONAL | UNRESOLVED | NOT_AVAILABLE
    labor_norm_resolution_ref: str | None
```

Do **not** store `normative_benchmark` / `observed_productivity` / `planning_norm` on `CandidateRecord`. Those live on the referenced `LaborNormResolution` (§10).

**Target change vs MPCA-001 `Candidate`:** do **not** treat `human_required_fields = ["crew", "planned_qty"]` as a condition for handoff. Crew is not Constructor routine. Physical available qty is analysis, not invented `planned_qty`. Final committed qty is later in the contour.

DataFrames from tools live only inside node execution, then discarded or summarized into `input_snapshot_id`.

---

## 6. Lifecycle

Canonical statuses (align names with parent Constructor spec; map MPCA-001 `STARTING` / `READING_DATA` / … internally):

### Happy path

```
MISSION_RECEIVED
  → LOAD_REALITY
  → CLASSIFY_SCOPE
  → BUILD_CANDIDATE_PACKAGE
  → RESOLVE_LABOR_NORM_METADATA
  → CHECK_EXCEPTIONS
  → PREPARE_HANDOFF
  → FRESHNESS_GATE
  → HANDOFF_READY
  → COMPLETED
```

### HITL path (durable pause)

```
CHECK_EXCEPTIONS
  → WAITING_FOR_HUMAN
  → APPLY_HUMAN_DECISION
  → REFRESH_REALITY
  → REVALIDATE
  → CLASSIFY_SCOPE / UPDATE PACKAGE
  → CHECK_EXCEPTIONS
  → PREPARE_HANDOFF
  → FRESHNESS_GATE
  → HANDOFF_READY
  → COMPLETED
```

`HumanDecision` itself does **not** make the pre-interrupt snapshot current. After durable resume, `REFRESH_REALITY` is mandatory before further business execution.

### Stale path

```
FRESHNESS_GATE
  → STALE_REALITY          # BLOCKING for handoff
  → REFRESH_REALITY
  → REVALIDATE
  → CLASSIFY_SCOPE / UPDATE PACKAGE
  → CHECK_EXCEPTIONS
  → …
```

Any unrecoverable security / data-contract / tool failure:

```
FAILED
```

Fail closed. No silent empty package from a failed read.

`WAITING_FOR_HUMAN` is a **durable pause** only when §14 HITL law is met. Resume requires `HumanDecision` for the active interrupt, then fresh reality. Human must not be told to “press the Streamlit button again from scratch” as the resume protocol.

---

## 6.1 Freshness law

```
DURABLE HUMAN PAUSE INVALIDATES EXECUTION FRESHNESS
```

If a run entered `WAITING_FOR_HUMAN` **and** there was a durable interrupt / process pause / resume, then **before** continuing business execution a **fresh reality read is mandatory**.

Forbidden:

```
hours-later resume
  → reuse same input_snapshot_id
  → HANDOFF_READY
```

`HANDOFF_READY` **must not** be built from **knowingly stale** reality.

### Before `PREPARE_HANDOFF` / at `FRESHNESS_GATE`

Two legal paths:

**A.** After durable HITL a fresh reread already ran, and the current snapshot is still valid for this gate.

**B.** If since the last successful read a freshness TTL elapsed **or** relevant version/change signals exist — perform a fresh reread.

Exact TTL duration and database versioning strategy are **OPEN DESIGN**. The architectural law is independent of the chosen TTL: handoff cannot proceed on stale reality.

`STALE_REALITY` is a **working** exception. Default severity: **BLOCKING for handoff** until reality is refreshed and revalidated.

---

## 7. Graph nodes

All nodes: **deterministic Python** unless stated. LLM = none in v0.1 happy path. Freshness logic is **deterministic**, not LLM.

Security common to READ nodes: issued `AgentExecutionContext`; tools only from allowlist; project from context; no credentials in state; **no service bypass** (§9 / §16).

### 7.1 `receive_mission`

| | |
|--|--|
| **Purpose** | Validate mission, normalize month, materialize immutable `MonthlyPlanningScope`, issue READ context. |
| **Input** | `ConstructorMission` |
| **Tools** | `issue_read_only_agent_context` (existing). `normalize_month_key` (existing). |
| **Output** | `lifecycle_status=MISSION_RECEIVED` (then immediately next), filled `scope`, `run_id`. |
| **Next** | `load_reality` |
| **Failure** | blank project; month not canonical; `queue_scope` set but column not allowlisted; context issue → `DATA_CONTRACT_BLOCKER` / `SECURITY_DENIED`. |
| **Security** | Trusted instructions = this spec + issuer. Mission fields = untrusted data (validate types/length). |

### 7.2 `load_reality`

| | |
|--|--|
| **Purpose** | Read current BOQ remaining, adjustments, existing month plan lines **inside mission scope**: read-time filter where possible, then **post-read assertion**. |
| **Input** | context + immutable mission scope |
| **Tools** | APPROVED RUNTIME TOOLS only: `load_scope` / `load_adjustments` / `load_existing_month_plan_lines` → trusted read executor. New **small** adapters: read-time scope args where the column allowlist allows; `bind_scope_to_mission` assertion. Not a rewrite of classify. |
| **Output** | new `input_snapshot_id`, `snapshot_read_at`, `scanned_count` **after** scope gate. |
| **Next** | `classify_scope` |
| **Failure** | read error; unexpected credential env; extra-scope rows; bind would expand beyond mission. |
| **Security** | READ only. Column allowlists. Project from context, not from model. Month is operational argument already used by plan-lines read. No call to non-allowlisted services. |

**Must not:** load whole product then skip assertion. **Must not:** treat post-filter as license for uncontrolled project-wide read. **Must not:** use Page10B `apply_scope_filters` (UI search/status mixed in).

### 7.3 `classify_scope`

| | |
|--|--|
| **Purpose** | Normalize, apply not_required once, availability metrics, already planned, exclusions — **on the asserted mission slice only**. |
| **Input** | current snapshot (already scope-asserted) |
| **Tools** | **REUSE:** `skill_calculate_availability`, `skill_apply_existing_month_plan`, `build_constructor_proposal` / `classify_scope_rows` (`domain.py`). Also `normalize_scope_raw_df`, `filter_invalid_v2_boq_rows`, `_v2_apply_boq_availability_metrics`. These are deterministic domain functions over an already-authorized snapshot, not extra data-plane reads. |
| **Output** | classified candidates + exclusion counts (node memory / snapshot artifact). |
| **Next** | `build_candidate_package` |
| **Failure** | domain fail-closed already in MPCA-001 (invalid month already caught). |

### 7.4 `build_candidate_package`

| | |
|--|--|
| **Purpose** | Materialize the **package artifact** (compact `CandidateRecord` list + ids). Graph state stores `package_id` + counts only. Routine non-candidates stay in exclusion counts. |
| **Input** | classified proposal |
| **Tools** | **REUSE:** `skill_build_candidates`, `constructor_candidate_id`. Do **not** copy `human_required_fields` into runtime law. |
| **Output** | `package_id`, `candidate_count`, exclusion counters on graph state. |
| **Next** | `resolve_labor_norms` |
| **Failure** | `CANDIDATE_ID_COLLISION` → BLOCKING exception or FAILED per existing fail-closed (show, do not hide). |

### 7.5 `resolve_labor_norms`

| | |
|--|--|
| **Purpose** | Attach labor-norm **metadata** via shared capability. Never drop physical rows for `UNRESOLVED` / `NOT_AVAILABLE`. |
| **Input** | package artifact |
| **Tools** | v0.1 stub `LaborNormResolver.resolve_many` using **only currently allowlisted reads**. Default: do **not** call `load_constructor_line_economics` until it is a registered trusted tool. Do **not** call `monthly_plan_line_calculation` (write-path economics). |
| **Output** | `labor_norm_status` per candidate; `labor_norm_summary`. Unreadable economics → `UNRESOLVED` / `NOT_AVAILABLE`. |
| **Next** | `check_exceptions` |
| **Failure** | security/redaction failure → FAILED. Missing economics → NON_BLOCKING, package remains. |

### 7.6 `check_exceptions`

| | |
|--|--|
| **Purpose** | Map domain `HumanIssue` + runtime codes to taxonomy; split BLOCKING / NON_BLOCKING / WARNING. |
| **Input** | package + issues + freshness flags |
| **Tools** | **REUSE:** `skill_detect_conflicts`. **REPLACE law:** `skill_build_human_exceptions` must **not** treat missing crew/qty as the human workflow. **REPLACE law:** `skill_prepare_handoff` must **not** force `admission_handoff_ready=False` for lack of crew/qty. |
| **Output** | `exception_blocking_count`, `exception_non_blocking_count`, `exception_warning_count` |
| **Next** | `prepare_human_interrupt` if BLOCKING > 0 that requires human; else `prepare_handoff`. `SECURITY_DENIED` / unrecoverable `DATA_CONTRACT_BLOCKER` → `fail_run` (still BLOCKING for handoff; no human override). |
| **Failure** | mapping error → fail closed. |

### 7.7 `prepare_human_interrupt`

| | |
|--|--|
| **Purpose** | Build `HumanInterrupt` for **BLOCKING** business exceptions only (grouped / bounded, not 175 rows). |
| **Input** | blocking exceptions |
| **Tools** | none external |
| **Output** | `interrupt_id`, `pre_interrupt_snapshot_id` = current snapshot, `lifecycle_status=WAITING_FOR_HUMAN` |
| **Next** | **pause**. Durable HITL only if §14 law is met; otherwise this is IN-PROCESS PROOF, not accepted HITL. Resume → `apply_human_decision` |
| **Failure** | empty `allowed_decisions` → FAILED (cannot ask a closed question). |

### 7.8 `apply_human_decision`

| | |
|--|--|
| **Purpose** | Record and stage the allowed decision. Does **not** certify the old snapshot as fresh. Does **not** write product tables. |
| **Input** | `HumanDecision` |
| **Tools** | deterministic appliers for **run-local intent** only (group/rule/bounded scope). **No** product write. Confirming physical qty does **not** write `monthly_scope_manual_adjustments`. |
| **Output** | `pending_human_decision_id`; interrupt closed or marked ANSWERED |
| **Next** | `refresh_reality` (**mandatory** after durable pause) |
| **Failure** | decision not in allowlist; stale interrupt; unknown actor type. |

If after refresh the decision is **no longer applicable** to the new reality, do **not** apply it blindly. Raise a new BLOCKING exception (typically `STALE_REALITY` or `DISPUTED_PHYSICAL_QUANTITY`) and return to HITL / fail-closed per type.

### 7.9 `refresh_reality`

| | |
|--|--|
| **Purpose** | Re-read **current** allowed mission scope and replace the execution snapshot. Mandatory after durable HITL; also used when `FRESHNESS_GATE` detects stale. |
| **Input** | immutable mission scope; `pre_interrupt_snapshot_id` (if any); pending decision |
| **Tools** | same APPROVED RUNTIME READ tools as `load_reality` (trusted executor + allowlist). Same dual scope enforcement. Deterministic. Not LLM. |
| **Output** | **new** `input_snapshot_id`, `snapshot_read_at`; material-change summary vs pre-interrupt snapshot |
| **Next** | `revalidate` |
| **Failure** | read error; extra-scope rows; context deny → FAILED. |
| **Security** | identical to `load_reality`. No economics bypass. No generic SQL. |

`refresh_reality` must:

1. re-read the actual allowed mission scope;
2. re-check physical remainder, completed status, existing monthly plan lines, duplicate/reservation context, and data touched by the human decision;
3. create a **new** snapshot/reference (must not reuse the pre-interrupt id as “current”);
4. compare material changes with the snapshot from before the interrupt;
5. if reality materially changed — rebuild affected candidate/result on the next nodes;
6. if the human decision no longer applies — emit a new BLOCKING exception instead of silent apply.

### 7.10 `revalidate`

| | |
|--|--|
| **Purpose** | Re-run classify / package / labor metadata on the **current** (just refreshed or still-valid) snapshot. |
| **Input** | current `input_snapshot_id` |
| **Tools** | same as classify + build + resolve (reuse). No extra data-plane reads except those already done by `refresh_reality`. |
| **Next** | `check_exceptions` |
| **Failure** | same as those nodes. |

`revalidate` does **not** substitute for `refresh_reality`. After durable HITL, `revalidate` runs **on the new snapshot**.

### 7.11 `prepare_handoff`

| | |
|--|--|
| **Purpose** | Build structured `ConstructorHandoff` (identifiers + summaries) from the current package. Does **not** yet set `HANDOFF_READY`. |
| **Input** | package with no BLOCKING exceptions |
| **Tools** | new builder; **do not** use current `admission_handoff_ready=False` crew/qty reason. |
| **Output** | draft `handoff_id` / handoff object |
| **Next** | `freshness_gate` |
| **Failure** | missing package; BLOCKING exceptions still present. |

### 7.12 `freshness_gate`

| | |
|--|--|
| **Purpose** | Deterministic gate: refuse `HANDOFF_READY` from stale reality. |
| **Input** | draft handoff; `input_snapshot_id`; `snapshot_read_at`; whether a durable pause occurred; optional TTL / version signals |
| **Tools** | none external except, if path B requires it, the same approved read tools via `refresh_reality`. Not LLM. |
| **Output** | `freshness_ok=true` and `lifecycle_status=HANDOFF_READY`; **or** `STALE_REALITY` BLOCKING |
| **Next** | `complete_run` if fresh; else `refresh_reality` then `revalidate` |
| **Failure** | cannot determine freshness → fail closed (`STALE_REALITY` BLOCKING, not silent pass). |
| **Security** | cannot mark handoff ready on a snapshot known to predate a durable pause without a subsequent successful `refresh_reality`. |

Path A: durable HITL already executed `refresh_reality` and the snapshot remains valid for this gate.

Path B: TTL elapsed or relevant version changes → must `refresh_reality` before handoff. Exact TTL **OPEN DESIGN**.

### 7.13 `complete_run`

| | |
|--|--|
| **Purpose** | Mark COMPLETED. Persist business result + handoff if persistence enabled. |
| **Next** | terminal |
| **Security** | still no product write. |

### 7.14 `fail_run`

| | |
|--|--|
| **Purpose** | Terminal FAILED. Redacted error. No partial write. |
| **Next** | terminal |

---

## 8. Conditional transitions

```
receive_mission --ok--> load_reality
receive_mission --fail--> fail_run

load_reality --ok--> classify_scope
load_reality --fail--> fail_run

classify_scope --ok--> build_candidate_package
classify_scope --fail--> fail_run

build_candidate_package --ok--> resolve_labor_norms
build_candidate_package --collision_policy--> check_exceptions
  (collision is a BLOCKING exception, not silent drop)

resolve_labor_norms --> check_exceptions
  (UNRESOLVED labor is NON_BLOCKING; does not skip check)

check_exceptions --blocking_human>0--> prepare_human_interrupt
check_exceptions --security/data_contract_unrecoverable--> fail_run
check_exceptions --blocking==0--> prepare_handoff

prepare_human_interrupt --> WAITING_FOR_HUMAN (graph interrupt)

apply_human_decision --ok--> refresh_reality
apply_human_decision --illegal--> fail_run

refresh_reality --ok--> revalidate
refresh_reality --fail--> fail_run

revalidate --> check_exceptions

prepare_handoff --ok--> freshness_gate
prepare_handoff --fail--> fail_run

freshness_gate --fresh--> complete_run          # HANDOFF_READY
freshness_gate --stale--> refresh_reality       # STALE_REALITY BLOCKING
```

Retries: READ tool failures may retry **once** with backoff **only** if error is classified transient. Unknown / security / schema errors: no retry, `fail_run`. Policy details OPEN; default fail-closed.

---

## 9. Tool mapping

### NO SERVICE BYPASS

No agent node may call an existing Python service around:

- trusted executor
- tool registry / allowlist
- `AgentExecutionContext`
- scope validation

Existence of a function/service is **not** permission for the agent runtime to call it.

### A. APPROVED RUNTIME TOOL

| Existing | Used by |
|----------|---------|
| `security.agent_execution_context.issue_read_only_agent_context` | receive_mission |
| `agents.monthly_plan_constructor.tools.load_scope` | load_reality / refresh_reality |
| `tools.load_adjustments` | load_reality / refresh_reality |
| `tools.load_existing_month_plan_lines` | load_reality / refresh_reality |
| `security.trusted_read_executor.execute_constructor_*` | behind tools |
| `services.monthly_plan_constructor_read_service.load_constructor_scope` | **only** behind executor + allowlist |
| `services.monthly_plan_constructor_read_service.load_constructor_adjustments` | **only** behind executor + allowlist |
| `services.monthly_plan_constructor_read_service.load_constructor_month_plan_lines` | **only** behind executor + allowlist |
| `utils.month_key.normalize_month_key` | receive_mission (pure function, no I/O) |
| `services.monthly_planning_scope_read_service.normalize_scope_raw_df` | classify (pure transform of authorized snapshot) |
| `services.monthly_planning_boq_service` metrics / invalid filter | classify (already used by skills; snapshot-local) |
| `domain.build_constructor_proposal`, `classify_scope_rows`, grain helpers | classify / package |
| `skills.skill_*` except handoff/human_required law | classify / package / conflicts |

### B. EXISTING SERVICE — REQUIRES SECURE ADAPTER

| Asset | Status |
|-------|--------|
| `load_constructor_line_economics` | **Not** an approved runtime tool. Exists in the read service and workbench, **absent** from current `MPCA_ALLOWED_TOOLS`. Must not be called from any Constructor Runtime node until a **narrow trusted read tool** is registered (allowlist + executor + column allowlist + context). Until then: labor/economic metadata = `UNRESOLVED` / `NOT_AVAILABLE`. Does **not** block physical candidates. |
| read-time mission-scope filtering on `load_constructor_scope` | Current API is project-only. Requires a secure adapter to pass optional facility/discipline/system/IWP **without** bypassing executor. |
| `construction_queue` column | Not on `SCOPE_SELECT_COLUMNS`. Mission that **sets** `queue_scope` fails closed until allowlisted. |

### C. UI-ONLY / NOT FOR RUNTIME

| Asset | Why |
|-------|-----|
| Page10B `apply_scope_filters`, session_state, workbench dataframe | UI-specific. Mixes search/status into “filters”. |
| `services.monthly_plan_constructor_workbench.execute_constructor_workbench` | MPCA-003 experiment; project+month only; renders 175 rows. |
| Page51 MPO cockpit / Page52 docs | Other surfaces. |
| LLM for remainder / already_planned / freshness | Deterministic. |

### D. WRITE PATH — FORBIDDEN IN v0.1

| Asset | Why |
|-------|-----|
| `tools.create_not_sent_plan_lines` / `trusted_write_executor` | Write release, not this runtime. |
| `write_authorization.py` issuers | Not needed for READ run. Keep for later. |
| `services.monthly_plan_line_calculation` as Constructor output | Write-line economics; Resource/write path. |
| Generic SQL / HTTP / shell / filesystem write | EOS-SEC forbid. |

### Needs a thin adapter (new, small, deterministic)

| Adapter | Why |
|---------|-----|
| read-time scope on trusted load tools | Dual enforcement layer 1. |
| `mission_to_scope` / `bind_scope_to_mission` | Dual enforcement layer 2. Hard gate. |
| `package_from_mpca_candidates` | Drop crew/qty-as-human-required; add `labor_norm_status`. |
| `map_human_issues_to_exceptions` | Align codes with §11. |
| `LaborNormResolver` stub | Shared capability; v0.1 default UNRESOLVED until economics tool is registered. |
| `handoff_from_package` | Replace `skill_prepare_handoff` admission_ready=False law. |
| freshness comparator | Deterministic snapshot/material-change check. |

### UI stays outside runtime

- Page10B manual constructor (BOQ list, draft, «В ДОПУСК»).
- MPCA-003 candidate table as primary surface.
- Page51 MPO cockpit.
- Page52 docs.

Control Room may **display** run status by reading persisted run + package **reference**. Summary first; large rows only as evidence.

---

## 10. Labor norm integration

`LaborNormResolver` = **shared capability**, not an agent. Constructor does **not** become Resource Agent or Economic Agent.

v0.1 behaviour:

1. Use **only** allowlisted reads. **Default: do not call** `load_constructor_line_economics`.
2. If a future registered economics tool returns a finite P50: `labor_norm_status=PROVISIONAL`, `source_type=PROJECT_HISTORY` (observed productivity **candidate**). Confidence not HIGH: **HISTORY EXISTS ≠ HISTORY IS TRUSTWORTHY**. No productive-hours quality pipeline in v0.1.
3. If missing / non-finite / tool not registered: `UNRESOLVED` or `NOT_AVAILABLE`. Severity: **NON_BLOCKING**.
4. Do **not** call GESN, scrape, or LLM “typical hours”.
5. **Never** set hours to 0 as a fake norm.
6. **Never** remove the candidate from the physical package because of UNRESOLVED.
7. `labor_cost` Page10B constant 3000 is **not** Constructor output in v0.1.

Candidate stores only:

- `labor_norm_status`
- `labor_norm_resolution_ref`

Detailed structure lives separately (exact storage **OPEN DESIGN**):

```python
# DESIGN ONLY — not stored on CandidateRecord

class LaborNormResolution(TypedDict):
    resolution_id: str
    candidate_id: str
    status: str                          # VALIDATED | PROVISIONAL | UNRESOLVED | NOT_AVAILABLE
    normative_benchmark: float | None    # optional; official/GESN-class benchmark
    observed_productivity: float | None  # optional; e.g. project P50 candidate
    planning_norm: float | None          # optional; Constructor v0.1 does not invent this
    source_type: str | None
    confidence: str | None
```

These three values **must not be mixed**. LLM cannot invent an authoritative labor norm. Constructor v0.1 does not fill `planning_norm`.

```python
class LaborNormSummary(TypedDict):
    validated: int      # 0 in v0.1 stub unless later quality gate exists
    provisional: int
    unresolved: int
    coverage_note: str
```

Constructor does not decide crew size, capacity, or month economics.

Write-path law **unchanged for later**: MPCA-002 missing P50 → no INSERT with invented `labor_hours`. Physical package ≠ written plan line.

---

## 11. Exception model

One contract, used everywhere in this document:

| Severity | Effect |
|----------|--------|
| **BLOCKING** | Cannot proceed to `HANDOFF_READY`. Business BLOCKING that is recoverable by a human → `WAITING_FOR_HUMAN`. Security / unrecoverable data-contract → `FAILED` (still BLOCKING for handoff; no human override in v0.1). |
| **NON_BLOCKING** | Business uncertainty exists; physical package **may** continue. Shown in Control Room / handoff summary. |
| **WARNING** | Technical / quality / completeness signal. Does **not** change lifecycle by itself. |

There is **no** separate `INFO` severity in v0.1. Trace-only notes belong in audit events, not this taxonomy.

### Taxonomy v0.1

| Code | Default severity | Notes |
|------|------------------|-------|
| `AMBIGUOUS_SCOPE` | BLOCKING | Incomplete grain; `queue_scope` set but not enforceable; extra-scope rows after assertion. Maps existing `AMBIGUOUS_SCOPE` / `AMBIGUOUS_PLAN_LINE_SCOPE`. |
| `DUPLICATE_CONTEXT` | BLOCKING | `CANDIDATE_ID_COLLISION`; conflicting plan-line grain (`CONFLICTING_PLAN_LINES`). |
| `DISPUTED_PHYSICAL_QUANTITY` | BLOCKING | `INCONSISTENT_QUANTITIES`, `CANDIDATE_EXCEEDS_AVAILABLE`, `INVALID_PLANNED_QTY` when they mean reality is unsafe to package. Also: human decision no longer applicable after refresh. |
| `DATA_QUALITY_BLOCKER` | BLOCKING | Invalid keys; adjustments read failed if it would silently zero not_required. Existing `ADJUSTMENTS_READ_FAILED`. |
| `DATA_CONTRACT_BLOCKER` | BLOCKING | Month/project invalid; mission schema fail. Existing `BLANK_PROJECT` / bad month. Unrecoverable → FAILED, not HITL. |
| `SECURITY_DENIED` | BLOCKING | Context/tool deny. FAILED, not interrupt. No human “override” in v0.1. |
| `STALE_REALITY` | **BLOCKING** | Working status. Blocks handoff until fresh read + revalidation. After durable pause, reuse of the old snapshot is this exception. |
| `LABOR_NORM_UNRESOLVED` | **NON_BLOCKING** | **Does not block** physical package. Includes `NOT_AVAILABLE` when economics tool is unregistered. |
| `TOOL_FAILURE` | BLOCKING or FAILED | Prefer FAILED for unknown; BLOCKING HITL only if a defined recovery decision exists. |
| `HANDOFF_NOT_READY` | BLOCKING | Blocking exceptions remain; should not reach prepare_handoff. |

Routine exclusions (`EXCLUDED_COMPLETED`, `EXCLUDED_NO_REMAINDER`, `EXCLUDED_ALREADY_PLANNED`, `EXCLUDED_NOT_REQUIRED`) are **not** human exceptions. They are package accounting.

Missing crew / missing planned_qty are **not** v0.1 BLOCKING exceptions.

---

## 12. Human interrupt model

Human does **not** confirm every routine candidate.

Allowed human interaction in this runtime:

- mission/scope (before or as receive_mission — usually **outside** the graph: the mission **is** the assignment);
- exception;
- ambiguous reality;
- disputed physical quantity;
- (later, not v0.1) critical write authorization;
- (later) management decision / passport.

### HumanInterruptContract

```python
class HumanInterrupt(TypedDict):
    interrupt_id: str
    run_id: str
    type: str                 # matches taxonomy code or group key
    severity: str             # BLOCKING
    reason: str               # human-readable, no secrets
    business_context: dict    # project, month, scope (redacted/minimized)
    affected_entities: list[str]  # bounded group keys / representative ids — NOT a mass editor
    allowed_decisions: list[str]
    requested_at: str
    status: str               # OPEN | ANSWERED | EXPIRED | CANCELLED
```

Suggested `allowed_decisions` (closed set, per type):

- `CONFIRM_PHYSICAL_QUANTITY`
- `EXCLUDE_FROM_PACKAGE`
- `SPLIT_GRAIN` (may be UNSUPPORTED → not listed)
- `ABORT_RUN`

`REREAD_REALITY` is **not** an optional human shortcut around the freshness law. After durable HITL the runtime **always** runs `refresh_reality`. Listing it as a human decision is unnecessary for v0.1.

Do not list `APPROVE_ALL_CANDIDATES` as a way to skip exceptions.

### HumanDecisionContract

```python
class HumanDecision(TypedDict):
    decision_id: str
    interrupt_id: str
    actor_type: str
    actor_id: str
    display_name: str | None
    identity_note: str
    decision: str
    parameters: dict          # group/rule/bounded scope — NOT a 175-row patch list
    comment: str
    decided_at: str
```

### Human contract bounds

`affected_entities` and `HumanDecision.parameters` **must not** become a hidden mass row editor.

For routine bulk cases the decision applies to:

- an **exception group**, or
- a **bounded mission/rule scope**, or
- a **single disputed grain**

not to a requirement that the human confirm every candidate row.

Example of allowed parameters: `{"available_to_add_qty": 12.0, "grain": "…"}` or `{"exclude_rule": "DUPLICATE_CONTEXT"}`. Forbidden: a payload that is effectively `approved_items[]` for all 175 candidates.

### Transitional identity debt

There is **no** verified human identity / Auth / project membership.

Reuse EOS-SEC transitional actor:

- `actor_type = LOCAL_APPLICATION`
- `actor_id = EXECUTION_OS_LOCAL_HOST`
- `identity_note` MUST remain: this is **not** verified human identity.

Control Room in v0.1 records **that a local operator answered**, not a legally identified person. Production identity is architectural debt (§20).

Do not mint `HumanApproval` / `WriteAuthorization` for this READ runtime.

---

## 13. Handoff contract

No hidden agent-to-agent chat.

```python
class ConstructorHandoff(TypedDict):
    schema_version: str                 # "constructor_handoff.v0.1"
    handoff_id: str
    handoff_type: str                   # CONSTRUCTOR_TO_ADMISSION
    source_agent: str                   # MONTHLY_PLAN_CONSTRUCTOR
    source_run_id: str
    target_role: str                    # MONTHLY_PLAN_ADMISSION_AGENT
    orchestration_run_id: str | None
    project_code: str
    month_key: str
    scope: MonthlyPlanningScope
    candidate_package_reference: str    # package_id
    snapshot_id: str                    # reality snapshot that passed freshness_gate
    candidate_ids: list[str]
    candidate_count: int
    exceptions_summary: dict            # NON_BLOCKING / WARNING only if handoff ready
    labor_norm_summary: LaborNormSummary
    created_at: str
    status: str                         # HANDOFF_READY
    provenance: dict                    # agent_version, security_policy_version
```

Admission Agent **is not implemented**. Handoff is a structured object for the orchestrator / future Admission to **read identifiers and then re-read live reality**.

Do not embed full BOQ tables in the handoff. Do not emit `HANDOFF_READY` until `freshness_gate` passes.

---

## 14. Persistence model and HITL law

No SQL in this checkpoint. Minimal model:

**Need between processes** (page closed, interrupt hours later):

- run lifecycle + mission/scope;
- active interrupt + decisions;
- package **reference**;
- current and pre-interrupt snapshot references;
- handoff;
- redacted events.

**Transient (checkpoint or memory only):**

- DataFrames;
- raw tool payloads;
- executor internals.

### Recommended tables (conceptual, not created)

Prefer **four**, not one table per class:

| Store | Plane | Contents |
|-------|--------|----------|
| `agent_runs` | BUSINESS + RUNTIME pointer | run_id, agent, mission/scope JSON, lifecycle_status, counts, package_id, snapshot ids, error, timestamps |
| `agent_interrupts` | BUSINESS HITL | interrupt + decision columns or child rows |
| `agent_handoffs` | BUSINESS | ConstructorHandoff JSON |
| `agent_run_events` | AUDIT | append-only redacted trace (step, counts, no secrets) |

Optional later: `agent_packages` if the package artifact should not live on `agent_runs`. Do not create it until size is proven.

Exact DDL, indexes, RLS — **OPEN DESIGN**.

### LangGraph checkpoint vs Supabase

| | LangGraph checkpoint | Supabase |
|--|----------------------|----------|
| **Role** | Resume graph (current node, small state, retry) | Operational/business/audit **truth** other agents and Control Room can read |
| **Backend** | **OPEN DESIGN** (not chosen) | Existing project DB; new tables later |
| **Must not** | Be the only copy of handoff | Store credentials, raw secrets, unredacted tool errors |

### HITL acceptance law

```
IN-PROCESS INTERRUPT ≠ DURABLE HITL
```

If **any** of the following is missing:

- persistent LangGraph checkpoint **or equivalent durable checkpoint**;
- persistent agent interrupt record;
- a way to restore the run after the process has exited;

then this is **not** implemented Human-in-the-Loop runtime. It may be called only:

- `IN-PROCESS PROOF`, or
- `DEVELOPMENT INTERRUPT PROOF`.

It must **not** be reported as `HITL COMPLETE = YES`.

Production-grade / **accepted v0.1 HITL** requires **all** of:

1. persistent run identity;
2. durable checkpoint;
3. persistent interrupt record;
4. human decision record;
5. resume by `run_id` / checkpoint;
6. **fresh reality read** after durable pause;
7. audit trail.

Agent Runtime v0.1 **may** be implemented incrementally:

- scope/package runtime proof can be **PASS** while durable HITL is **NOT IMPLEMENTED**;
- `HITL COMPLETE = YES` is allowed **only** after the seven conditions above.

A demo that pauses in RAM / Streamlit session is **not** the HITL success scenario.

---

## 15. LangGraph responsibility

Current `run_monthly_plan_constructor_agent` is a **single synchronous procedure**. Current `monthly_planning_orchestrator_service` is a **different** one-shot MPO analyzer.

LangGraph is introduced **after** Python contracts are proven. It is a **runtime orchestration layer**, not a rewrite of deterministic business logic.

LangGraph adds what those do **not**:

- persistent lifecycle independent of Streamlit;
- named nodes + conditional edges;
- interrupt / resume (`WAITING_FOR_HUMAN`);
- checkpoint / recovery after process death;
- explicit handoff node vs “return a dict to the page”;
- retry policy at the edge, not inside a 500-line function;
- long-running execution without a browser session;
- `refresh_reality` / `freshness_gate` as first-class nodes.

LangGraph does **not**:

- replace `classify_scope_rows`;
- hold Supabase credentials;
- invent norms;
- decide freshness via LLM;
- become a super-agent;
- authorize service bypass.

Pattern: **node = validate + call existing skill/tool + write small state**.

---

## 16. Security boundaries (EOS-SEC)

Constructor Runtime v0.1 = **TIER_0_READ_ONLY_DETERMINISTIC** (existing registry). `write_allowed=False`.

**MODEL IS NOT A SECURITY BOUNDARY.**

| Boundary | Rule |
|----------|------|
| Trusted instructions | This spec, issuer, static tool registry. Not UI text, not BOQ names. |
| Untrusted data | Mission strings, view rows, plan lines, adjustments, economics. DATA ≠ INSTRUCTION. |
| Tool allowlist | Current approved reads: `load_constructor_scope`, `load_constructor_adjustments`, `load_constructor_month_plan_lines`. Economics read is **not** approved until registered. |
| No service bypass | Nodes must not call Python services that skip executor + registry + context + scope validation. |
| Project / mission scope | `AgentExecutionContext.project_code` plus dual mission-scope enforcement. |
| Read permission | Trusted read executor + column allowlists. |
| Write permission | **None** in this runtime. |
| Human gate | Interrupt for BLOCKING business exceptions only. Not 175-row approval. Not write approval. |
| Freshness | Deterministic. Durable pause invalidates snapshot. |
| Validation | Mission schema, month_key, dual scope, proposal validators (reuse). |
| Audit | Redacted events. `assert_no_secrets_in_payload`. |
| Fail closed | Unknown tool, missing context, unenforceable queue_scope, extra-scope rows, read failure, undetermined freshness → FAILED/DENY/`STALE_REALITY`. |
| Secret isolation | No clients in graph state. No env in traces. |

Forbidden: generic SQL, shell, exec, HTTP, filesystem writes.

---

## 17. Control Room contract

Minimal fields from runtime (no large UI design):

| Field | Example |
|-------|---------|
| agent | MONTHLY_PLAN_CONSTRUCTOR 0.1 |
| mission | PRJ_001_БХК / сентябрь-2026 / facility X / Вентиляция |
| status | LOAD_REALITY / WAITING_FOR_HUMAN / HANDOFF_READY / FAILED |
| current_node | `check_exceptions` / `freshness_gate` |
| started_at / duration | ISO + ms |
| processed (`scanned_count`) | after scope gate, e.g. 127 — **not** 447 if mission is scoped |
| candidates | 54 (count; not the table) |
| exceptions | 2 BLOCKING / n NON_BLOCKING / n WARNING |
| labor_norm_summary | 0 / 0 / 54 if economics unregistered |
| human action required | interrupt_id + grouped reason |
| last event | redacted step summary |
| handoff status | none / HANDOFF_READY |
| freshness | ok / STALE_REALITY |

Actions: `[Открыть решения]` `[Показать доказательства]`.

Large dataframe = evidence drill-down only. Not the success path. Control Room is not the runtime.

---

## 18. Success scenario

```
PROJECT:     PRJ_001_БХК
MONTH:       сентябрь-2026
FACILITY:    one explicit facility/title
DISCIPLINE:  Вентиляция
SYSTEM:      ALL
IWP:         ALL
QUEUE:       ALL (omitted)
```

The agent **must**:

1. Receive this mission as `ConstructorMission` (not Page10B leftover filters).
2. Enforce scope at trusted read **and** assert after read.
3. **Not** process or report the whole project (2026-08-22 anti-pattern: 447/175). Runtime test must prove scanned/returned business rows belong **only** to this mission.
4. Build physical candidate package from remaining/available in that slice.
5. Attach labor-norm metadata only from allowlisted tools; otherwise `UNRESOLVED` / `NOT_AVAILABLE`.
6. **Not** drop candidates solely for missing P50.
7. Create interrupt **only** if BLOCKING business exceptions exist in that slice.
8. After any durable HITL: `APPLY_HUMAN_DECISION` → `REFRESH_REALITY` → `REVALIDATE` — never reuse the old snapshot.
9. Else (or after resolved exceptions) pass `FRESHNESS_GATE` then `HANDOFF_READY` with identifiers + summaries.
10. **Not** require a human to review 175 routine rows.
11. **Not** INSERT/UPDATE plan lines, NOT_SENT, SENT, constraints, or schema.
12. **Not** depend on Streamlit remaining open.

If the slice is empty: COMPLETED with `candidate_count=0`, handoff empty-but-valid, not a fallback to all disciplines.

---

## 19. Failure scenarios

| Scenario | Expected |
|----------|----------|
| Mission project `Все` or blank | FAILED `DATA_CONTRACT_BLOCKER` before read |
| Invalid month_key | FAILED `DATA_CONTRACT_BLOCKER` (existing validator) |
| `queue_scope` set, queue column not allowlisted | FAILED / BLOCKING `AMBIGUOUS_SCOPE` — no silent ALL |
| Extra-scope rows after assertion | FAILED / BLOCKING — no silent ALL |
| Scope read error | FAILED; no fake zero package |
| Context issuer deny | FAILED `SECURITY_DENIED` |
| Candidate id collision | BLOCKING interrupt or fail-closed show-all-collision (KEEP MPCA-001: do not hide) |
| Economics service called without allowlist | Must be impossible (no service bypass) |
| Economics tool unregistered | NON_BLOCKING `LABOR_NORM_UNRESOLVED` / `NOT_AVAILABLE`; package remains |
| Hours-later resume reuses old snapshot | Forbidden; `STALE_REALITY` BLOCKING until `refresh_reality` |
| Handoff from stale snapshot | Forbidden; `freshness_gate` fails closed |
| Illegal human decision | FAILED or reject decision, interrupt stays OPEN |
| Human decision inapplicable after refresh | New BLOCKING exception; do not apply blindly |
| Write tool invoked | Must be impossible (not on allowlist; write_allowed false) |
| Process crash during WAITING_FOR_HUMAN without durable checkpoint | **Not** accepted HITL (`HITL COMPLETE = NO`); IN-PROCESS PROOF only |

---

## 20. Open design items (consciously unsolved in v0.1)

Do **not** invent these now:

- exact LangGraph checkpoint backend;
- exact Supabase DDL / RLS for `agent_*`;
- exact freshness TTL duration;
- database versioning strategy for “relevant version changes”;
- exact labor-norm storage schema;
- production Auth / RBAC / verified human identity;
- GESN / official normative connector and licensing;
- Admission Agent implementation;
- Resource Agent / Economic Agent;
- LLM provider;
- operation taxonomy and BOQ → operation → norm mapping;
- advanced adjustment factors;
- history quality pipeline for HIGH confidence P50;
- `construction_queue` on scope allowlist (until then `queue_scope` fail-closed);
- registering `load_constructor_line_economics` as a trusted tool;
- frontend migration off Streamlit;
- replacing MPO Page51 with this graph;
- production write path (MPCA-002 remains design KEEP, live write off).

---

## 21. Implementation sequence

Do **not** start by installing LangGraph.

LangGraph is wrapped around **already proven** Python nodes/services. It does **not** replace deterministic business logic.

| Increment | What | HITL claim |
|-----------|------|------------|
| **1** | Mission Scope Contract + deterministic scope binder + **scope regression tests** (facility X + Вентиляция ≠ 447). | n/a |
| **2** | Candidate package artifact + package references + bounded graph state. | n/a |
| **3** | Secure read-tool adapters + runtime tool registry consistency (no service bypass). | n/a |
| **4** | LaborNormResolver stub/interface without invented norms (default UNRESOLVED until economics registered). | n/a |
| **5** | Exception engine + BLOCKING / NON_BLOCKING / WARNING. | n/a |
| **6** | Pure Python lifecycle proof **without Streamlit coupling**. May include in-process interrupt as DEVELOPMENT PROOF only. | `HITL COMPLETE = NO` |
| **7** | LangGraph runtime wrapper over proven nodes/services. | still NO unless §14 met |
| **8** | Durable checkpoint + persistent interrupt + resume + **fresh reality reread**. | HITL may become YES only here |
| **9** | Structured handoff persistence. | — |
| **10** | Minimal Agent Control Room integration (summary first). | Control Room is not the runtime |

Do not: MPCA-004 table; modify dirty MPCA-002/003 as a shortcut; enable writes; call unregistered economics; skip freshness after pause.

---

## 22. Acceptance criteria

Release **Agent Runtime v0.1 — Constructor Mission** is accepted only if:

**A.** Scoped mission never expands to the whole project. Regression test: `PRJ_001_БХК` / `сентябрь-2026` / facility X / `Вентиляция` → scanned/returned business rows belong only to that mission (not 447 whole-project).

**B.** Durable resume always performs a fresh reality read (`refresh_reality` after `WAITING_FOR_HUMAN`).

**C.** `HANDOFF_READY` is never created from stale reality (`freshness_gate`).

**D.** No service bypass outside tool allowlist / trusted executor / context / scope validation.

**E.** Missing P50 / labor norm does not remove a physical candidate (`LABOR_NORM_UNRESOLVED` = NON_BLOCKING).

**F.** Human does not confirm routine rows. Decisions apply to exception groups / bounded rules.

**G.** No product write.

**H.** No Streamlit dependency for the run to exist or resume.

**I.** For **accepted HITL** implementation: the run can be restored by persistent identity/checkpoint (all seven conditions in §14). Until then `HITL COMPLETE = NO`.

**J.** Admission handoff is structured identifiers/references, not prompt chat. Admission re-reads live reality.

Also required:

- [ ] Mission requires project + stored month; optional scopes bind or fail-closed.
- [ ] UI search/status are not implicit mission fields.
- [ ] Trusted read + existing classify/remainder/already-planned **reused** (no prompt rewrite).
- [ ] Dual scope: read-time enforcement where possible + post-read assertion always.
- [ ] EOS-SEC: allowlist, no secrets in state, fail-closed, MODEL IS NOT SECURITY BOUNDARY.
- [ ] Control Room can show status **without** making the dataframe the work.
- [ ] LangGraph is used as orchestrator, not as a rewrite of `domain.py`.
- [ ] `STALE_REALITY` is a working BLOCKING exception, not unused.

Until those are proven, MPCA-003 remains an **experiment**, not the employee.

Incremental truth: Increments 1–6 may PASS as scope/package proofs while **durable HITL is NOT IMPLEMENTED**. That is allowed. Claiming a finished digital-worker HITL without Increment 8 is **not** allowed.

---

## Related

- [ARCHITECTURE_BASELINE.md](ARCHITECTURE_BASELINE.md)
- [MONTHLY_PLAN_CONSTRUCTOR_AGENT.md](MONTHLY_PLAN_CONSTRUCTOR_AGENT.md)
- [ORCHESTRATION_AND_HANDOFF.md](ORCHESTRATION_AND_HANDOFF.md)
- [LABOR_NORM_RESOLUTION.md](LABOR_NORM_RESOLUTION.md)
- [DECISION_LOG.md](DECISION_LOG.md)
- [RECOVERY_CONTEXT.md](RECOVERY_CONTEXT.md)
- `security/agent_security_baseline.md`
