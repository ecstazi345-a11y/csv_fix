# Agent Runtime Progress — Execution OS

**Purpose:** долговечная инженерная память агентной программы. Не история чата.

Checkpoints **append-only**. Не переписывать предыдущие записи.

**Program:** Monthly Planning Agentic Orchestration<br>
**Stack law:** Python + LangGraph + Supabase shared state + EOS-SEC + replaceable LLM adapter + Streamlit Control Room<br>
**Decomposition law:** one major professional role = one specialized agent. Shared capabilities are not agents.

## Current snapshot (not a checkpoint)

- **Program:** Monthly Planning Agentic Orchestration
- **Current agent:** MONTHLY_PLAN_CONSTRUCTOR
- **Progress:** **9 / 10**
- **DONE:** [1] Mission Scope Contract · [2] Candidate Package Artifact · [3] Secure Read Tool Adapters · [4] Labor Norm Resolver · [5] Exception Engine · [6] Pure Python Lifecycle · [7] LangGraph Runtime · [8] Durable HITL / Resume · [9] Structured Handoff · [10.1] Agent-Neutral Observability Foundation · [10.2] Run Control · [10.3A] Runtime Instrumentation Foundation · [10.3B] Core LangGraph Stage Wiring · [10.3C] Tool / Artifact Runtime Instrumentation · [10.3D] HITL / Resume / Reality Refresh Runtime Instrumentation · [10.3E] Handoff / Completion Runtime Instrumentation · **Operational Truth Fix** · **10.4 Durable Observability Store** · **10.5 Separate-Process Durability Proof** · **ConstructorManagedRuntimeLauncher** (Local Managed Runtime Backend v0.1) · **10.6 AgentControlRoomQueryPort** · **10.7 Control Room Core**
- **NEXT:** Increment **10.8** State-of-the-Art HITL Architecture Gate → HITL visualization preflight — do **not** start before this checkpoint is committed
- **Recovery code HEAD:** `9a7eeed931a40dc6dd8fa615979c40675a057b6c` (10.7 Control Room Core on `wip/increment-10-agent-control-room`)
- **Increment 10 status:** 10.0 DONE · 10.A0 DONE · 10.A1 DONE · 10.1 DONE · 10.2 DONE · 10.3A DONE · 10.3B DONE · 10.3C DONE · 10.3D DONE · 10.3E DONE · **10.3A–E Runtime Instrumentation DONE** · **Operational Truth Fix DONE** · **10.4 Durable Observability Store DONE** · **10.5 Separate-Process Durability Proof DONE** · **ConstructorManagedRuntimeLauncher DONE** · **10.6 AgentControlRoomQueryPort DONE** · **10.7 Control Room Core DONE** · Increment 10 overall **NOT COMPLETE**

Historical checkpoints below are append-only and are **not** rewritten.

---

============================================================
CHECKPOINT — 2026-08-24 — CONSTRUCTOR AGENT — INCREMENT 2
============================================================

PROGRAM:
Monthly Planning Agentic Orchestration

CURRENT AGENT:
MONTHLY_PLAN_CONSTRUCTOR<br>
Агент формирования кандидатного состава месячного плана

CURRENT INCREMENT:
[2] Candidate Package Artifact

STATUS:
DONE

------------------------------------------------------------
WHAT WE BUILT
------------------------------------------------------------

- Runtime specification committed: `docs/agentic_architecture/AGENT_RUNTIME_V0_1_CONSTRUCTOR_MISSION.md` (`d8eeff3`). Design law only; does not install LangGraph.
- Increment 1 committed: `ConstructorMissionScope` + deterministic `bind_scope_to_mission` + post-bind assertion + 447-row MPCA-003 regression (`775993f`).
- Increment 2 committed: immutable `CandidatePackage` / `CandidateRecord` + `build_candidate_package` (`862279b`).
- Package is a structured Python artifact: UUID `package_id`, `schema_version=1.0`, provenance, summary counts, labor-norm status. Not a DataFrame, not a Streamlit table, not a plan write.
- Out-of-scope candidates fail closed. Physical qty ≠ feasible qty ≠ commitment qty. Missing price / `UNRESOLVED` labor does not drop a candidate.
- Increments 1–2 are isolated modules. They are **not** wired to Page10B, `runtime.py`, read services, or LangGraph.

------------------------------------------------------------
WHAT THIS GIVES THE SYSTEM
------------------------------------------------------------

Цифровой сотрудник Constructor теперь имеет две доказанные способности ядра:

1. Он знает **где** имеет право работать (mission scope: project + month + optional facility/discipline/system/IWP/queue; scope never expands).
2. Он умеет оформить **формальный бизнес-артефакт** своей работы (Candidate Package) для будущего handoff в Admission — а не таблицу на экране и не текст модели.

Это ещё не автономный runtime. Это доказанный contract core.

------------------------------------------------------------
WHERE WE ARE IN THE AGENT ROADMAP
------------------------------------------------------------

Constructor Agent Runtime v0.1 (одна роль, десять инкрементов — не десять агентов):

[1] Mission Scope Contract — **DONE**
[2] Candidate Package Artifact — **DONE** (this checkpoint)
[3] Secure Read Tool Adapters — **NEXT**
[4] Labor Norm Resolver integration — **NOT STARTED**
[5] Exception Engine — **NOT STARTED**
[6] Pure Python Lifecycle — **NOT STARTED**
[7] LangGraph Runtime — **NOT STARTED**
[8] Durable HITL / Resume — **NOT STARTED**
[9] Structured Handoff — **NOT STARTED**
[10] Agent Control Room Integration — **NOT STARTED**

Progress: **2 / 10**

------------------------------------------------------------
WHERE WE ARE IN THE MONTHLY PLANNING PROGRAM
------------------------------------------------------------

MONTHLY PLAN ORCHESTRATOR<br>
→ **1. CONSTRUCTOR AGENT — CURRENT (increments 1–2 of 10)**<br>
→ 2. ADMISSION AGENT — not started<br>
→ 3. CONSTRAINT AGENT — not started<br>
→ 4. RESOURCE CAPACITY AGENT — not started<br>
→ 5. ECONOMIC EVALUATION AGENT — not started<br>
→ 6. MANAGEMENT DECISION AGENT — not started<br>
→ HUMAN DECISION GATE<br>
→ ПАСПОРТ МЕСЯЧНОГО ПРОИЗВОДСТВЕННОГО ОБЯЗАТЕЛЬСТВА

Существующий `monthly_planning_orchestrator_service.py` / Page51 — MPO feasibility cockpit продукта, **не** Constructor Runtime.

------------------------------------------------------------
CURRENT AGENT CAPABILITIES
------------------------------------------------------------

Разделение статуса:

| Capability | Status |
|------------|--------|
| Architecture baseline docs | DESIGNED + COMMITTED + PUSHED (`0e16e5f`) |
| Constructor Runtime v0.1 spec | DESIGNED + COMMITTED + PUSHED (`d8eeff3`). Not an implementation grant. |
| Mission scope contract + binder | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`775993f`) |
| Candidate Package artifact | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`862279b`) |
| MPCA-001 predecessor: `runtime.py` / `domain.py` / `skills.py` / `tools.py` / validators | EXISTS (committed earlier `4d7d21b`). Synchronous READ/CLASSIFY/PROPOSE. Not the increment graph. Not wired to Increments 1–2. |
| EOS-SEC issuer + trusted read executor + `MPCA_ALLOWED_TOOLS` | EXISTS (MPCA-001). New runtime does not call them yet. |
| MPCA-002 write stack / MPCA-003 Page10B workbench | DIRTY worktree experiment. **Not** accepted Constructor Runtime. Live write not approved. |

**MISSION CONTRACTS (implemented):** `ConstructorMissionScope`, `build_constructor_mission_scope`

**BUSINESS ARTIFACTS (implemented):** `CandidatePackage`, `CandidateRecord`, `CandidatePackageReference` (`as_reference()`)

**VALIDATORS (implemented):** post-bind assertion; package fail-closed if any candidate outside mission; `candidate_count == len(candidates)`

**SKILLS / NODES / LANGGRAPH:** not in Increments 1–2

**TESTS (this program slice):**<br>
`tests/test_monthly_plan_constructor_mission_scope.py` — 20 PASS<br>
`tests/test_monthly_plan_constructor_candidate_package.py` — 20 PASS

**SPECS:** `docs/agentic_architecture/*` including `AGENT_RUNTIME_V0_1_CONSTRUCTOR_MISSION.md`

------------------------------------------------------------
WHAT IS NOT BUILT YET
------------------------------------------------------------

- Read-time trusted scope adapter (Increment 3)
- LaborNormResolver as registered capability; economics tool still not on `MPCA_ALLOWED_TOOLS`
- Exception engine (BLOCKING / NON_BLOCKING / WARNING)
- Pure Python lifecycle (`WAITING_FOR_HUMAN`, `REFRESH_REALITY`, `FRESHNESS_GATE`)
- LangGraph not installed / not implemented
- Durable checkpoint / persistent interrupt / resume
- `ConstructorHandoff` persistence
- Agent Control Room as runtime surface
- Admission / Constraint / Resource / Economic / Management Decision agents
- Production writes to `monthly_plan_lines_v2`
- Integration of Increments 1–2 into `runtime.py` or Page10B

Constructor is **not** yet an autonomous digital worker runtime.

------------------------------------------------------------
ARCHITECTURE QUALITY CHECK
------------------------------------------------------------

AGENT != DASHBOARD: **PASS** (Increments 1–2 are Streamlit-free)<br>
STRUCTURED BUSINESS ARTIFACT: **PASS** (`CandidatePackage`)<br>
STATEFUL DESIGN: **FUTURE** (immutable package exists; run lifecycle not implemented)<br>
STRUCTURED HANDOFF: **FUTURE** (package is the intended payload; `ConstructorHandoff` not built)<br>
DURABLE HITL: **FUTURE** (law in spec; `HITL COMPLETE` remains NO)<br>
DETERMINISTIC FIRST: **PASS**<br>
REPLACEABLE LLM: **PASS** (no LLM in Increments 1–2; spec keeps adapter replaceable)<br>
EOS-SEC: **PASS** for this slice (no model-as-boundary; no service bypass in new modules). Tool-adapter wiring = Increment 3.<br>
NO AGENT ZOO: **PASS** (LaborNormResolver remains a shared capability in spec; not an agent)<br>
NO HIDDEN AGENT CHAT: **PASS**<br>
FRESH REALITY LAW: **FUTURE** (specified; no lifecycle node yet)<br>
OBSERVABILITY READY: **FUTURE**

ARCHITECTURE DRIFT: **NO**

Residual (not counted as drift of this increment): MPCA-003 dirty Page10B table experiment remains in the worktree and is **not** the target UX. It was not modified, staged, or promoted.

------------------------------------------------------------
FILES
------------------------------------------------------------

CREATED (Increment 2, this checkpoint commit):

- `agents/monthly_plan_constructor/candidate_package.py`
- `tests/test_monthly_plan_constructor_candidate_package.py`

MODIFIED:
- none for Increment 2

Already on `main` from earlier steps of the same program (not rewritten here):

- `docs/agentic_architecture/AGENT_RUNTIME_V0_1_CONSTRUCTOR_MISSION.md`
- `agents/monthly_plan_constructor/mission_scope.py`
- `tests/test_monthly_plan_constructor_mission_scope.py`

------------------------------------------------------------
TESTS
------------------------------------------------------------

NEW TESTS (Increment 2): 20 passed / 0 failed<br>
INCREMENT 1 REGRESSION: 20 passed / 0 failed

------------------------------------------------------------
GIT CHECKPOINT
------------------------------------------------------------

COMMIT: `862279b07234d3172d39b270ed49eca7535095ab`

MESSAGE: `feat(agents): add constructor candidate package artifact`

PUSH: YES

LOCAL HEAD: `862279b07234d3172d39b270ed49eca7535095ab`

REMOTE HEAD: `862279b07234d3172d39b270ed49eca7535095ab`

LOCAL == REMOTE: YES

Recovery point for this stage: **`862279b`**.<br>
Architecture parent: `0e16e5f`. Runtime spec: `d8eeff3`. Increment 1: `775993f`.

Worktree remains dirty with preserved MPCA-002/003 files (not part of this checkpoint).

------------------------------------------------------------
ONE-LINE SUMMARY
------------------------------------------------------------

На этом этапе мы дали агенту формальный бизнес-артефакт его работы — Candidate Package — внутри уже доказанного mission scope.

------------------------------------------------------------
NEXT
------------------------------------------------------------

Increment 3 — Secure Read Tool Adapters.

Должен дать агенту право читать операционную реальность **только** через trusted executor + tool allowlist + mission scope (no service bypass), ещё без LangGraph, SQL schema и production writes.

---

============================================================
CHECKPOINT — 2026-08-24 — CONSTRUCTOR AGENT — INCREMENT 3
============================================================

PROGRAM:
Monthly Planning Agentic Orchestration

CURRENT AGENT:
MONTHLY_PLAN_CONSTRUCTOR<br>
Агент формирования кандидатного состава месячного плана

CURRENT INCREMENT:
[3] Secure Read Tool Adapters

STATUS:
DONE

------------------------------------------------------------
WHAT WE BUILT
------------------------------------------------------------

- Isolated `read_constructor_reality` adapter (`af2e9af`).
- `AgentExecutionContext` participates in authorization; expired / missing context fail closed.
- Mission project must equal authorized project (`SECURITY_DENIED` otherwise).
- Read-time mission scope is passed into the trusted-read port (LAYER 1).
- Post-read assertion reuses Increment 1 (LAYER 2). Extra-scope rows fail closed.
- Double scope defence: no silent widen to whole project.
- Only allowlisted tool `load_constructor_scope` via `validate_context_for_tool`.
- No service bypass: adapter does not import dirty `read_service` / `tools.py` / economics.
- Bounded `ConstructorRealityRead` with provenance (`read_id`, `read_at`, tool, authorization).
- Zero-row result is valid. Public contract is not a DataFrame. Read result ≠ CandidatePackage.
- Regression: scoped mission FACILITY_TARGET + Вентиляция → 17 rows, not 447.
- 22 new tests PASS; Increment 1 (20) and Increment 2 (20) regressions PASS.
- Query-side SQL filter in dirty `monthly_plan_constructor_read_service.py` was **not** added. `queue_scope` without capability fail closed.

------------------------------------------------------------
WHAT THIS GIVES THE SYSTEM
------------------------------------------------------------

Теперь Constructor Agent получил **безопасные глаза**: он может получать необходимую операционную реальность через разрешённый trusted read boundary и **только** в пределах своей Mission Scope. Он не ходит в базу напрямую и не вызывает существующие services в обход allowlist.

Это ещё не полный runtime. Это доказанный secure-read contract.

------------------------------------------------------------
WHERE WE ARE IN THE AGENT ROADMAP
------------------------------------------------------------

Constructor Agent Runtime v0.1 (одна роль, десять инкрементов — не десять агентов):

[1] Mission Scope Contract — **DONE**
[2] Candidate Package Artifact — **DONE**
[3] Secure Read Tool Adapters — **DONE** (this checkpoint)
[4] Labor Norm Resolver integration — **NEXT**
[5] Exception Engine — **NOT STARTED**
[6] Pure Python Lifecycle — **NOT STARTED**
[7] LangGraph Runtime — **NOT STARTED**
[8] Durable HITL / Resume — **NOT STARTED**
[9] Structured Handoff — **NOT STARTED**
[10] Agent Control Room Integration — **NOT STARTED**

Progress: **3 / 10**

------------------------------------------------------------
WHERE WE ARE IN THE MONTHLY PLANNING PROGRAM
------------------------------------------------------------

MONTHLY PLAN ORCHESTRATOR<br>
→ **1. CONSTRUCTOR AGENT — CURRENT (increments 1–3 of 10)**<br>
→ 2. ADMISSION AGENT — not started<br>
→ 3. CONSTRAINT AGENT — not started<br>
→ 4. RESOURCE CAPACITY AGENT — not started<br>
→ 5. ECONOMIC EVALUATION AGENT — not started<br>
→ 6. MANAGEMENT DECISION AGENT — not started<br>
→ HUMAN DECISION GATE<br>
→ ПАСПОРТ МЕСЯЧНОГО ПРОИЗВОДСТВЕННОГО ОБЯЗАТЕЛЬСТВА

------------------------------------------------------------
CURRENT AGENT CAPABILITIES
------------------------------------------------------------

| Capability | Status |
|------------|--------|
| Mission scope contract + binder | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`775993f`) |
| Candidate Package artifact | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`862279b`) |
| Secure read adapter | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`af2e9af`) |
| EOS-SEC issuer + trusted read executor | EXISTS (MPCA-001). Increment 3 calls `validate_context_for_tool` / optional executor wrapper. |
| LaborNormResolver | NEXT (Increment 4). Economics tool not on `MPCA_ALLOWED_TOOLS`. |
| Exception / lifecycle / LangGraph / HITL / handoff / Control Room | NOT IMPLEMENTED |
| MPCA-001 predecessor runtime | EXISTS, not wired to Increments 1–3 |
| MPCA-002/003 dirty worktree | PRESERVED experiment, not this runtime |

**TOOLS (implemented increment):** `read_constructor_reality` → allowlisted `load_constructor_scope`

**READ ARTIFACT:** `ConstructorRealityRead` / `ConstructorRealityRow` / `ConstructorReadProvenance`

**TESTS:**<br>
`tests/test_monthly_plan_constructor_secure_read_tools.py` — 22 PASS<br>
Increment 1 — 20 PASS<br>
Increment 2 — 20 PASS

------------------------------------------------------------
WHAT IS NOT BUILT YET
------------------------------------------------------------

- LaborNormResolver as registered capability (Increment 4)
- Exception engine
- Pure Python lifecycle / freshness gate
- LangGraph
- Durable checkpoint / HITL
- Structured ConstructorHandoff
- Agent Control Room
- Admission and later professional agents
- Query-side SQL filters in the existing (dirty) read service
- Integration of Increments 1–3 into `runtime.py` or Page10B
- Production writes

------------------------------------------------------------
ARCHITECTURE QUALITY CHECK
------------------------------------------------------------

AGENT != DASHBOARD: **PASS**<br>
STRUCTURED BUSINESS ARTIFACT: **PASS** (package still Increment 2; read result is a separate artifact)<br>
STATEFUL DESIGN: **FUTURE**<br>
STRUCTURED HANDOFF: **FUTURE**<br>
DURABLE HITL: **FUTURE**<br>
DETERMINISTIC FIRST: **PASS**<br>
REPLACEABLE LLM: **PASS**<br>
EOS-SEC: **PASS** (context, allowlist, no service bypass, fail closed)<br>
NO AGENT ZOO: **PASS**<br>
NO HIDDEN AGENT CHAT: **PASS**<br>
FRESH REALITY LAW: **FUTURE**<br>
OBSERVABILITY READY: **FUTURE**

ARCHITECTURE DRIFT: **NO**

------------------------------------------------------------
FILES
------------------------------------------------------------

CREATED:

- `agents/monthly_plan_constructor/secure_read_tools.py`
- `tests/test_monthly_plan_constructor_secure_read_tools.py`

MODIFIED:
- none for Increment 3 product/docs in that commit

------------------------------------------------------------
TESTS
------------------------------------------------------------

NEW TESTS (Increment 3): 22 passed / 0 failed<br>
INCREMENT 1 REGRESSION: 20 passed / 0 failed<br>
INCREMENT 2 REGRESSION: 20 passed / 0 failed

------------------------------------------------------------
GIT CHECKPOINT
------------------------------------------------------------

COMMIT: `af2e9afc169093fa2cead1953e8396d011b5417c`

MESSAGE: `feat(agents): add constructor secure read adapters`

PUSH: YES

LOCAL HEAD: `af2e9afc169093fa2cead1953e8396d011b5417c`

REMOTE HEAD: `af2e9afc169093fa2cead1953e8396d011b5417c`

LOCAL == REMOTE: YES

Recovery point for this stage: **`af2e9af`**.

Worktree remains dirty with preserved MPCA-002/003 files (not part of this checkpoint).

------------------------------------------------------------
ONE-LINE SUMMARY
------------------------------------------------------------

На этом этапе мы дали агенту безопасные глаза: trusted read только внутри Mission Scope, без обхода allowlist.

------------------------------------------------------------
NEXT
------------------------------------------------------------

Increment 4 — Labor Norm Resolver integration.

Должен дать Constructor возможность прикреплять labor-norm **metadata** (VALIDATED / PROVISIONAL / UNRESOLVED) без выдуманных норм, без блокировки physical candidate отсутствием P50, и без вызова незарегистрированного economics tool.

---

============================================================
CHECKPOINT — 2026-08-24 — CONSTRUCTOR AGENT — INCREMENT 4 — LABOR NORM RESOLVER
============================================================

PROGRAM:
Monthly Planning Agentic Orchestration

CURRENT AGENT:
MONTHLY_PLAN_CONSTRUCTOR<br>
Агент формирования кандидатного состава месячного плана

CURRENT INCREMENT:
[4] Labor Norm Resolver integration

STATUS:
DONE

------------------------------------------------------------
WHAT WE BUILT
------------------------------------------------------------

- Isolated capability `resolve_labor_norms` (`f0062e7`).
- Typed evidence contract `LaborNormEvidence` (not a DataFrame, not a free-form dict as public API).
- Structured artifact `LaborNormResolution` / `LaborNormResolutionSet` linked to `package_id` and `candidate_id`.
- Immutable enrichment of `CandidateRecord` via `dataclasses.replace`. Original `CandidatePackage` unchanged. Schema of Increment 2 **not** modified.
- One resolution per input candidate. Count invariant: input candidates = output resolutions.
- Status model: `VALIDATED` / `PROVISIONAL` / `UNRESOLVED`.
- Deterministic source hierarchy from `LABOR_NORM_RESOLUTION.md`: PROJECT_HISTORY → COMPANY_HISTORY → OFFICIAL_NORMATIVE → TECHNOLOGICAL_STANDARD/VENDOR → INDUSTRY_BENCHMARK → EXPERT_APPROVED → UNRESOLVED.
- Invalid higher-priority evidence falls through. Conflicting same-rank evidence fails closed (`AMBIGUOUS_LABOR_NORM_EVIDENCE`). Identical duplicates are deterministically deduplicated.
- Numeric fail-closed: None / NaN / inf / 0 / negative rejected. Canonical unit: labor hours per physical unit.
- Unit mismatch rejected. No implicit engineering conversion.
- Provenance/source reference mandatory for resolved evidence.
- Historical quality: paid/nonproductive hours and history without validated executed quantity are inadmissible.
- Official normative remains `NORMATIVE_BENCHMARK`; not relabeled as observed crew productivity.
- No LLM. No SQL. No Supabase write. No Streamlit. No economics-tool call.
- Lessons_2 methodology gate: **PASS** (`2c4445840cf68ff64cffecbe5a9a9dd21808be04`).

------------------------------------------------------------
WHAT THIS GIVES THE SYSTEM
------------------------------------------------------------

Constructor Agent получил детерминированную способность разрешать трудовую норму для каждого физического кандидата: понимать источник нормы, её статус доверия, единицу измерения, provenance и причину выбора.

Если безопасно определить норму нельзя, кандидат не исчезает: он остаётся физическим кандидатом со статусом `UNRESOLVED`.

`LaborNormResolver` — **CAPABILITY / SERVICE** внутри Constructor Agent, **не** отдельный агент.

------------------------------------------------------------
WHERE WE ARE IN THE AGENT ROADMAP
------------------------------------------------------------

Constructor Agent Runtime v0.1 (одна роль, десять инкрементов — не десять агентов):

[1] Mission Scope Contract — **DONE**<br>
[2] Candidate Package Artifact — **DONE**<br>
[3] Secure Read Tool Adapters — **DONE**<br>
[4] Labor Norm Resolver integration — **DONE** (this checkpoint)<br>
[5] Exception Engine — **NEXT**<br>
[6] Pure Python Lifecycle — **NOT STARTED**<br>
[7] LangGraph Runtime — **NOT STARTED**<br>
[8] Durable HITL / Resume — **NOT STARTED**<br>
[9] Structured Handoff — **NOT STARTED**<br>
[10] Agent Control Room Integration — **NOT STARTED**

Progress: **4 / 10**

------------------------------------------------------------
WHERE WE ARE IN THE MONTHLY PLANNING PROGRAM
------------------------------------------------------------

MONTHLY PLAN ORCHESTRATOR<br>
→ **1. CONSTRUCTOR AGENT — CURRENT (increments 1–4 of 10)**<br>
→ 2. ADMISSION AGENT — not started<br>
→ 3. CONSTRAINT AGENT — not started<br>
→ 4. RESOURCE CAPACITY AGENT — not started<br>
→ 5. ECONOMIC EVALUATION AGENT — not started<br>
→ 6. MANAGEMENT DECISION AGENT — not started<br>
→ HUMAN DECISION GATE<br>
→ ПАСПОРТ МЕСЯЧНОГО ПРОИЗВОДСТВЕННОГО ОБЯЗАТЕЛЬСТВА

------------------------------------------------------------
CURRENT AGENT CAPABILITIES
------------------------------------------------------------

| Capability | Status |
|------------|--------|
| Mission scope contract + binder | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`775993f`) |
| Candidate Package artifact | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`862279b`) |
| Secure read adapter | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`af2e9af`) |
| LaborNormResolver | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`f0062e7`) |
| Exception / lifecycle / LangGraph / HITL / handoff / Control Room | NOT IMPLEMENTED |
| MPCA-001 predecessor runtime | EXISTS, not wired to Increments 1–4 |
| MPCA-002/003 dirty worktree | PRESERVED experiment, not this runtime |

**CAPABILITY (this increment):** `resolve_labor_norms` — shared service, not an agent.

**RESOLUTION ARTIFACT:** `LaborNormResolution` / `LaborNormResolutionSet`

**TESTS:**<br>
`tests/test_monthly_plan_constructor_labor_norm_resolver.py` — 26 PASS<br>
Increment 1 — 20 PASS<br>
Increment 2 — 20 PASS<br>
Increment 3 — 22 PASS<br>
py_compile — PASS

------------------------------------------------------------
WHAT IS NOT BUILT YET
------------------------------------------------------------

- Exception engine (Increment 5)
- Pure Python lifecycle / freshness gate
- LangGraph
- Durable checkpoint / HITL
- Structured ConstructorHandoff
- Agent Control Room
- Admission and later professional agents
- GESN/FSNB live connectors and P50/P80 analytics engine
- Integration of Increments 1–4 into `runtime.py` or Page10B
- Production writes

------------------------------------------------------------
ARCHITECTURE QUALITY CHECK
------------------------------------------------------------

AGENT != CHATBOT: **PASS**<br>
AGENT != DATAFRAME: **PASS**<br>
ONE PROFESSIONAL ROLE = ONE AGENT: **PASS**<br>
LaborNormResolver = capability, not agent: **PASS**<br>
DETERMINISTIC-FIRST: **PASS**<br>
LLM NOT REQUIRED: **PASS**<br>
STRUCTURED OUTPUT: **PASS**<br>
PROVENANCE: **PASS**<br>
FAIL-CLOSED AMBIGUITY: **PASS**<br>
CANDIDATE PRESERVATION: **PASS** (physical candidate ≠ labor norm availability)<br>
EOS-SEC: **PASS** (tier 0 deterministic/read-only domain; no writes, no secrets, MODEL IS NOT A SECURITY BOUNDARY)<br>
CANDIDATE_PACKAGE SCHEMA CHANGED: **NO**<br>
NO AGENT ZOO: **PASS**

ARCHITECTURE DRIFT: **NO**

Verified business laws: missing norm does not delete physical work; VALIDATED outranks PROVISIONAL at the same source rank; unit mismatch rejected; no implicit unit conversion; official normative is not observed productivity; historical source keeps historical semantics; paid/nonproductive hours are not productive norm data; history without validated executed quantity is inadmissible; price absence does not affect physical candidacy.

------------------------------------------------------------
SECURITY / EOS-SEC
------------------------------------------------------------

SECURITY TIER: 0 — deterministic/read-only domain capability.

No writes. No SQL. No Supabase mutation. No arbitrary HTTP. No shell tool. No model-generated authoritative norm. No secret handling.

------------------------------------------------------------
FILES
------------------------------------------------------------

CREATED:

- `agents/monthly_plan_constructor/labor_norm_resolver.py`
- `tests/test_monthly_plan_constructor_labor_norm_resolver.py`

MODIFIED:
- none for Increment 4 product/docs in that commit

------------------------------------------------------------
TESTS
------------------------------------------------------------

NEW TESTS (Increment 4): 26 passed / 0 failed<br>
INCREMENT 1 REGRESSION: 20 passed / 0 failed<br>
INCREMENT 2 REGRESSION: 20 passed / 0 failed<br>
INCREMENT 3 REGRESSION: 22 passed / 0 failed<br>
PY_COMPILE: PASS

------------------------------------------------------------
GIT CHECKPOINT
------------------------------------------------------------

COMMIT: `f0062e7d38cdae40342d04e2453069aec931489c`

MESSAGE: `feat(agents): add constructor labor norm resolver`

PUSH: YES

LOCAL HEAD: `f0062e7d38cdae40342d04e2453069aec931489c`

REMOTE HEAD: `f0062e7d38cdae40342d04e2453069aec931489c`

LOCAL == REMOTE: YES

Recovery point for this stage: **`f0062e7`**.

LESSONS_2 GATE: PASS<br>
LESSONS_2 HEAD: `2c4445840cf68ff64cffecbe5a9a9dd21808be04`

Worktree remains dirty with preserved MPCA-002/003 files (not part of this checkpoint).

------------------------------------------------------------
ONE-LINE SUMMARY
------------------------------------------------------------

На этом этапе Constructor получил детерминированный LaborNormResolver: норма с provenance и статусом доверия, без удаления физического кандидата при UNRESOLVED.

------------------------------------------------------------
NEXT
------------------------------------------------------------

Increment 5 — Exception Engine.

Превратит unresolved/ambiguous условия в формальные machine-readable exceptions и решит, какие случаи могут продолжаться автоматически, а какие требуют human/professional attention. Increment 5 **не** реализован.

---

============================================================
CHECKPOINT — 2026-08-25 — CONSTRUCTOR AGENT — INCREMENT 5 — EXCEPTION ENGINE
============================================================

PROGRAM:
Monthly Planning Agentic Orchestration

CURRENT AGENT:
MONTHLY_PLAN_CONSTRUCTOR<br>
Агент формирования кандидатного состава месячного плана

CURRENT INCREMENT:
[5] Exception Engine

STATUS:
DONE

------------------------------------------------------------
WHAT WE BUILT
------------------------------------------------------------

- Isolated capability `Exception Engine` (`38cd42f`).
- Public immutable artifacts: `ConstructorException`, `ConstructorExceptionSet`.
- Deterministic hard-failure mapper: `exception_from_failure` (machine-readable failure codes only; does not execute Increment 1–4 capabilities).
- Labor adapter: `exceptions_from_labor_resolutions` (consumes `LaborNormResolutionSet`; does not recompute norms).
- Set builder with semantic dedup + `PackageExceptionSummary` reuse (schema of Increment 2 **not** mutated).
- Declarative helpers for future lifecycle: `codes()`, `blocking()`, `handoff_allowed()`.
- Exception Engine is a **CAPABILITY / SERVICE** inside Constructor Agent. It is **not** a separate agent, not LLM, not LangGraph, not a workflow/retry engine, not a generic logging framework, not a Python traceback wrapper, not Streamlit UI.
- Increments 1–4 product files unchanged. Engine may import their public types/constants only.

------------------------------------------------------------
WHAT THIS GIVES THE SYSTEM
------------------------------------------------------------

До Increment 5 разные способности Constructor сталкивались с проблемами в разных формах: hard fail-closed codes, Secure Read failures, soft `UNRESOLVED` labor outcomes.

После Increment 5 у Constructor Agent есть **единый structured machine-readable professional language** исключений:

- что произошло (`exception_code`);
- что затронуто (`package_id` / `candidate_id` / `resolution_id` + bounded details);
- блокируется ли нормальный путь (`severity`);
- разрешено ли автоматическое продолжение (`route` / derived continuation flags);
- какой future resolution route применяется (`FAIL_RUN` / `WAIT_HUMAN` / `CONTINUE`).

Это **вход для решений Increment 6 lifecycle**. Exception Engine **не** выполняет lifecycle transitions сам.

------------------------------------------------------------
ACTIVE TAXONOMY (v0.1)
------------------------------------------------------------

Canonical active codes only:

| Code | Severity | Route |
|------|----------|-------|
| `DATA_CONTRACT_BLOCKER` | BLOCKING | FAIL_RUN |
| `AMBIGUOUS_SCOPE` | BLOCKING | WAIT_HUMAN |
| `SECURITY_DENIED` | BLOCKING | FAIL_RUN |
| `READ_FAILED` | BLOCKING | FAIL_RUN |
| `LABOR_NORM_UNRESOLVED` | NON_BLOCKING | CONTINUE |

Security aliases normalize to `SECURITY_DENIED` with original lower-level code preserved in structured details:

- `TOOL_NOT_ALLOWED`
- `CONTEXT_EXPIRED`
- `CONTEXT_MISSING`

Speculative lifecycle codes (`STALE_REALITY`, `HANDOFF_NOT_READY`, …) are **not** active taxonomy in Increment 5.

`EXCEPTION_ENGINE_CONTRACT_BLOCKER` is an **engine programming/contract** fail-closed error — not a professional Constructor taxonomy item.

------------------------------------------------------------
CRITICAL BUSINESS LAW
------------------------------------------------------------

**PHYSICAL CANDIDATE ≠ LABOR NORM AVAILABILITY**

Therefore `LABOR_NORM_UNRESOLVED` does **not**:

- delete the physical candidate;
- zero physical quantity;
- manufacture a labor norm;
- block candidate/package merely because labor is unresolved.

Physical candidate survives. Labor-only NON_BLOCKING exceptions do **not** make `handoff_allowed()` false.

------------------------------------------------------------
SECURITY LAW
------------------------------------------------------------

Security failures cannot downgrade.

Security denial always means: **BLOCKING + FAIL_RUN**.

No:

- WARNING downgrade;
- NON_BLOCKING downgrade;
- CONTINUE;
- human override inside Exception Engine.

Unknown / unapproved failure codes fail closed via Exception Engine contract protection.

------------------------------------------------------------
WHERE WE ARE IN THE AGENT ROADMAP
------------------------------------------------------------

Constructor Agent Runtime v0.1 (одна роль, десять инкрементов — не десять агентов):

[1] Mission Scope Contract — **DONE**<br>
[2] Candidate Package Artifact — **DONE**<br>
[3] Secure Read Tool Adapters — **DONE**<br>
[4] Labor Norm Resolver — **DONE**<br>
[5] Exception Engine — **DONE** (this checkpoint)<br>
[6] Pure Python Lifecycle — **NEXT**<br>
[7] LangGraph Runtime — **NOT STARTED**<br>
[8] Durable HITL / Resume — **NOT STARTED**<br>
[9] Structured Handoff — **NOT STARTED**<br>
[10] Agent Control Room Integration — **NOT STARTED**

Progress: **5 / 10**

------------------------------------------------------------
WHERE WE ARE IN THE MONTHLY PLANNING PROGRAM
------------------------------------------------------------

MONTHLY PLAN ORCHESTRATOR<br>
→ **1. CONSTRUCTOR AGENT — CURRENT (increments 1–5 of 10)**<br>
→ 2. ADMISSION AGENT — not started<br>
→ 3. CONSTRAINT AGENT — not started<br>
→ 4. RESOURCE CAPACITY AGENT — not started<br>
→ 5. ECONOMIC EVALUATION AGENT — not started<br>
→ 6. MANAGEMENT DECISION AGENT — not started<br>
→ HUMAN DECISION GATE<br>
→ ПАСПОРТ МЕСЯЧНОГО ПРОИЗВОДСТВЕННОГО ОБЯЗАТЕЛЬСТВА

------------------------------------------------------------
CURRENT AGENT CAPABILITIES
------------------------------------------------------------

| Capability | Status |
|------------|--------|
| Mission scope contract + binder | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`775993f`) |
| Candidate Package artifact | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`862279b`) |
| Secure read adapter | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`af2e9af`) |
| LaborNormResolver | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`f0062e7`) |
| Exception Engine | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`38cd42f`) |
| Lifecycle / LangGraph / HITL / handoff / Control Room | NOT IMPLEMENTED |
| MPCA-001 predecessor runtime | EXISTS, not wired to Increments 1–5 |
| MPCA-002/003 | NOT REQUIRED on this computer; not part of Constructor Runtime |

**CAPABILITY (this increment):** Exception Engine — shared service, not an agent.

**EXCEPTION ARTIFACTS:** `ConstructorException` / `ConstructorExceptionSet`

**PUBLIC MAPPERS:** `exception_from_failure`, `exceptions_from_labor_resolutions`, `build_exception_set`

------------------------------------------------------------
INCREMENT BOUNDARY
------------------------------------------------------------

Increment 5 does **NOT**:

- catch existing Increment 1–4 capability failures automatically;
- run lifecycle / state transitions;
- pause / resume;
- perform HITL;
- retry reads;
- persist exceptions to Supabase;
- execute handoff;
- implement freshness detection;
- start LangGraph.

Existing Increment 1–4 fail-closed behavior remains intact.

`AMBIGUOUS_SCOPE → WAIT_HUMAN` is **future resolution semantics** only; it does not weaken Mission Scope / Secure Read fail-closed throws.

Secure Read economics/tool string warnings are **not** converted into `LABOR_NORM_UNRESOLVED`.

Future Increment 6 will consume Exception Engine outputs and decide deterministic lifecycle transitions.

------------------------------------------------------------
ARCHITECTURE QUALITY CHECK
------------------------------------------------------------

AGENT != CHATBOT: **PASS**<br>
AGENT != DATAFRAME: **PASS**<br>
ONE PROFESSIONAL ROLE = ONE AGENT: **PASS**<br>
Exception Engine = capability, not agent: **PASS**<br>
DETERMINISTIC-FIRST: **PASS**<br>
LLM NOT REQUIRED: **PASS**<br>
LANGGRAPH NOT USED: **PASS**<br>
STREAMLIT NOT USED: **PASS**<br>
SUPABASE WRITES: **NO**<br>
NO DATAFRAME PUBLIC CONTRACT: **PASS**<br>
NO MPCA-001/002/003 DEPENDENCY: **PASS**<br>
INCREMENT 1–4 FILES UNCHANGED: **YES**<br>
CANDIDATE_PACKAGE SCHEMA CHANGED: **NO**<br>
PackageExceptionSummary reused without schema mutation: **YES**<br>
PHYSICAL CANDIDATE PRESERVATION: **PASS**<br>
SECURITY NON-DOWNGRADE: **PASS**<br>
UNKNOWN CODE FAIL-CLOSED: **PASS**<br>
INCREMENT 6 BOUNDARY PRESERVED: **PASS**<br>
EOS-SEC: **PASS**<br>
SEMANTIC ARCHITECTURE REVIEW: **PASS**<br>
CODE QUALITY REVIEW: **PASS**<br>
NO AGENT ZOO: **PASS**

ARCHITECTURE DRIFT: **NO**

------------------------------------------------------------
SECURITY / EOS-SEC
------------------------------------------------------------

MODEL IS NOT A SECURITY BOUNDARY.<br>
DATA != INSTRUCTION.<br>
Fail closed. Mandatory machine-readable provenance.<br>
Security cannot downgrade to WARNING / NON_BLOCKING / CONTINUE / WAIT_HUMAN.<br>
No arbitrary SQL. No shell/exec. No Supabase writes. No secrets in exception reason/details by design of callers.

------------------------------------------------------------
FILES
------------------------------------------------------------

CREATED:

- `agents/monthly_plan_constructor/exception_engine.py`
- `tests/test_monthly_plan_constructor_exception_engine.py`

MODIFIED (product Increment 5 commit):
- none — exactly those two files

------------------------------------------------------------
TESTS
------------------------------------------------------------

NEW TESTS (Increment 5): 31 passed / 0 failed<br>
INCREMENT 1 REGRESSION: 20 passed / 0 failed<br>
INCREMENT 2 REGRESSION: 20 passed / 0 failed<br>
INCREMENT 3 REGRESSION: 22 passed / 0 failed<br>
INCREMENT 4 REGRESSION: 26 passed / 0 failed<br>
PY_COMPILE: PASS<br>
GIT DIFF CHECK: PASS<br>
SEMANTIC ARCHITECTURE: PASS<br>
CODE QUALITY: PASS<br>
EOS-SEC: PASS

------------------------------------------------------------
GIT CHECKPOINT
------------------------------------------------------------

PRODUCT COMMIT: `38cd42ff7fa256500a602614bf22e854ab763eff`

MESSAGE: `feat(agents): add constructor exception engine`

PUSH: YES

LOCAL HEAD: `38cd42ff7fa256500a602614bf22e854ab763eff`

REMOTE HEAD: `38cd42ff7fa256500a602614bf22e854ab763eff`

LOCAL == REMOTE: YES

FILE COUNT IN PRODUCT COMMIT: 2

Files:

- `agents/monthly_plan_constructor/exception_engine.py`
- `tests/test_monthly_plan_constructor_exception_engine.py`

Recovery point for this stage: **`38cd42f`**.

LESSONS_2 GATE: PASS (READ-ONLY; unchanged)<br>
LESSONS_2 PATH: `C:\Users\Андрей\lesson_2`<br>
LESSONS_2 HEAD: `2c4445840cf68ff64cffecbe5a9a9dd21808be04`

Worktree after product push: CLEAN.

------------------------------------------------------------
WHAT IS NOT BUILT YET
------------------------------------------------------------

- Pure Python Lifecycle (Increment 6) — **NEXT / NOT YET BUILT**
- LangGraph Runtime (Increment 7)
- Durable HITL / Resume (Increment 8)
- Structured Handoff (Increment 9)
- Agent Control Room Integration (Increment 10)
- Wiring Increments 1–5 into `runtime.py` / Page10B
- Admission and later professional agents
- Production writes

------------------------------------------------------------
ONE-LINE SUMMARY
------------------------------------------------------------

На этом этапе Constructor получил детерминированный Exception Engine: единый machine-readable язык исключений (severity + route + refs), без lifecycle и без удаления физического кандидата при UNRESOLVED labor.

------------------------------------------------------------
NEXT
------------------------------------------------------------

Increment 6 — Pure Python Lifecycle.

Свяжет уже построенные способности Constructor в детерминированный профессиональный lifecycle и по structured outputs / Exception Engine semantics решит: продолжать нормально, fail closed, ждать human resolution, позже требовать refreshed reality, или стать eligible for handoff.

Increment 6 **не** реализован в этом checkpoint.

---

============================================================
CHECKPOINT — 2026-08-26 — CONSTRUCTOR AGENT — INCREMENT 6 — PURE PYTHON LIFECYCLE
============================================================

PROGRAM:
Monthly Planning Agentic Orchestration

CURRENT AGENT:
MONTHLY_PLAN_CONSTRUCTOR<br>
Агент формирования кандидатного состава месячного плана

CURRENT INCREMENT:
[6] Pure Python Lifecycle

STATUS:
DONE

------------------------------------------------------------
WHAT WE BUILT
------------------------------------------------------------

- Isolated Pure Python Lifecycle (`c35957f`).
- Public immutable artifacts: `ConstructorLifecycleState`, `LifecycleTransition`.
- Public entry point: `run_constructor_lifecycle(...)` — one Constructor mission run to a terminal status.
- Progressive optional artifacts: CREATED may have `scope=None`; later statuses enforce required artifacts via invariants.
- Deterministic transition law + append-only transition trace (not an observability platform).
- Injected `CandidateAssembler` / `CandidateAssemblyResult` port — lifecycle does **not** invent physical remainder / classification.
- Reuses Increments 1–5 public capabilities; does not duplicate their professional logic.
- Increments 1–5 product files unchanged.

Before Increment 6 Constructor was a set of separate capabilities. Increment 6 connects them into one controlled mission runtime:

MISSION
→ TRUSTED REALITY
→ CANDIDATE ASSEMBLY PORT
→ CANDIDATE PACKAGE
→ LABOR RESOLUTION
→ EXCEPTION EVALUATION
→ READY / WAIT / FAIL

------------------------------------------------------------
WHAT THIS GIVES THE DIGITAL EMPLOYEE
------------------------------------------------------------

Constructor Agent больше не только набор отдельных модулей.

Он умеет исполнить одну профессиональную mission как controlled lifecycle:

- где сейчас находится run;
- какие бизнес-артефакты уже созданы;
- какая capability идёт дальше;
- когда нормальная обработка может продолжаться;
- когда execution must fail closed;
- когда требуется human resolution (логически);
- когда текущая работа Constructor завершена и run eligible for future handoff.

Это **первый реальный runtime** цифрового сотрудника Constructor.

Важно: Increment 6 — still an **in-memory deterministic Python** runtime. Это ещё не final production orchestration infrastructure (LangGraph / durable HITL / handoff persistence).

------------------------------------------------------------
LIFECYCLE GRAIN
------------------------------------------------------------

One lifecycle execution = **one Constructor mission run**.

Runtime identity: `run_id`<br>
Professional boundary: `ConstructorMissionScope` (project + month + optional dimensions)

Not: BOQ row · individual candidate · Streamlit session · whole project without mission scope.

------------------------------------------------------------
ACTIVE LIFECYCLE STATES
------------------------------------------------------------

Active statuses:

`CREATED` → `MISSION_BOUND` → `REALITY_LOADED` → `PACKAGE_BUILT` → `LABOR_RESOLVED`

Terminal:

`READY_FOR_HANDOFF` · `WAITING_FOR_HUMAN` · `FAILED`

Normal path:

CREATED
→ MISSION_BOUND
→ REALITY_LOADED
→ PACKAGE_BUILT
→ LABOR_RESOLVED
→ READY_FOR_HANDOFF

------------------------------------------------------------
READY_FOR_HANDOFF LAW
------------------------------------------------------------

In Increment 6, `READY_FOR_HANDOFF` means:

Constructor completed its deterministic professional work for this run and is **eligible for future structured handoff**.

It does **NOT** mean:

- handoff artifact already exists;
- Admission Agent called;
- Supabase write performed;
- freshness gate executed;
- the whole Monthly Planning process is complete.

Structured Handoff = Increment 9.

Predicate is fact-based (`is_ready_for_handoff`), not status-string alone: scope + reality + package + labor resolutions + exceptions; resolution cardinality matches candidates; no BLOCKING; `handoff_allowed()`.

------------------------------------------------------------
WAITING_FOR_HUMAN LAW
------------------------------------------------------------

`AMBIGUOUS_SCOPE` → BLOCKING + WAIT_HUMAN → lifecycle `WAITING_FOR_HUMAN`.

Increment 6 implements the **logical** terminal only.

It does **NOT** yet implement: durable pause · persisted checkpoint · human decision contract · resume · fresh reality reload · stale-decision prevention.

Those belong primarily to Increment 8.

------------------------------------------------------------
FAIL-CLOSED LAW
------------------------------------------------------------

Known professional failures map deterministically to terminal behavior:

| Code | Terminal |
|------|----------|
| `DATA_CONTRACT_BLOCKER` | FAILED |
| `SECURITY_DENIED` (+ aliases) | FAILED |
| `READ_FAILED` | FAILED |
| `AMBIGUOUS_SCOPE` | WAITING_FOR_HUMAN |

Security cannot downgrade into CONTINUE / WARNING / WAIT_HUMAN override / READY_FOR_HANDOFF.

Typed catches only (`MissionScopeError`, `CandidatePackageError`, `SecureReadError`, `LaborNormResolverError`, `ExceptionEngineError`). Broad `except Exception` is **not** used as lifecycle business control flow.

`ExceptionEngineError` → FAILED safely; no recursive remapping; no fabricated successful ExceptionSet.

Partial valid artifacts are preserved on late failures.

------------------------------------------------------------
PHYSICAL CANDIDATE / LABOR LAW
------------------------------------------------------------

**PHYSICAL CANDIDATE ≠ LABOR NORM AVAILABILITY**

`LABOR_NORM_UNRESOLVED` remains NON_BLOCKING + CONTINUE and does **not** by itself prevent `READY_FOR_HANDOFF`.

Even an all-UNRESOLVED package may finish the Constructor lifecycle if no other blocking exception exists.

------------------------------------------------------------
ZERO-CANDIDATE LAW
------------------------------------------------------------

Successful trusted read + valid empty candidate assembly is a valid professional result.

Zero candidates does **not** automatically mean FAILED or WAITING_FOR_HUMAN.

An empty valid package may reach `READY_FOR_HANDOFF` when contracts are satisfied and there are no blocking exceptions.

------------------------------------------------------------
CANDIDATE ASSEMBLY BOUNDARY
------------------------------------------------------------

Increment 6 does **NOT** implement physical remainder / candidate classification business logic.

Lifecycle uses injected `CandidateAssembler` → `CandidateAssemblyResult`.

This prevents lifecycle from absorbing BOQ remainder math, classification, feasible/commitment quantities, or old MPCA-001 workbench/domain logic.

Lifecycle coordinates capabilities. It does not become a second business-domain engine.

------------------------------------------------------------
STATE / TRACE
------------------------------------------------------------

`ConstructorLifecycleState` — immutable/frozen; professional artifacts appear progressively; CREATED does not fabricate scope/package/labor.

`LifecycleTransition` — minimal append-only deterministic stage trace.

Not yet: observability platform · audit database · LangGraph checkpoint system.

Authorization safety: stores `authorization_id` only from `AgentExecutionContext`; never full context/secrets. Secure Read remains the authorization authority for tools.

------------------------------------------------------------
WHERE WE ARE IN THE AGENT ROADMAP
------------------------------------------------------------

Constructor Agent Runtime v0.1 (одна роль, десять инкрементов — не десять агентов):

[1] Mission Scope Contract — **DONE**<br>
[2] Candidate Package Artifact — **DONE**<br>
[3] Secure Read Tool Adapters — **DONE**<br>
[4] Labor Norm Resolver — **DONE**<br>
[5] Exception Engine — **DONE**<br>
[6] Pure Python Lifecycle — **DONE** (this checkpoint)<br>
[7] LangGraph Runtime — **NEXT**<br>
[8] Durable HITL / Resume — **NOT STARTED**<br>
[9] Structured Handoff — **NOT STARTED**<br>
[10] Agent Control Room Integration — **NOT STARTED**

Progress: **6 / 10**

------------------------------------------------------------
WHERE WE ARE IN THE MONTHLY PLANNING PROGRAM
------------------------------------------------------------

MONTHLY PLAN ORCHESTRATOR<br>
→ **1. CONSTRUCTOR AGENT — CURRENT (increments 1–6 of 10)**<br>
→ 2. ADMISSION AGENT — not started<br>
→ 3. CONSTRAINT AGENT — not started<br>
→ 4. RESOURCE CAPACITY AGENT — not started<br>
→ 5. ECONOMIC EVALUATION AGENT — not started<br>
→ 6. MANAGEMENT DECISION AGENT — not started<br>
→ HUMAN DECISION GATE<br>
→ ПАСПОРТ МЕСЯЧНОГО ПРОИЗВОДСТВЕННОГО ОБЯЗАТЕЛЬСТВА

------------------------------------------------------------
CURRENT AGENT CAPABILITIES
------------------------------------------------------------

| Capability | Status |
|------------|--------|
| Mission scope contract + binder | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`775993f`) |
| Candidate Package artifact | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`862279b`) |
| Secure read adapter | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`af2e9af`) |
| LaborNormResolver | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`f0062e7`) |
| Exception Engine | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`38cd42f`) |
| Pure Python Lifecycle | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`c35957f`) |
| LangGraph / durable HITL / handoff / Control Room | NOT IMPLEMENTED |
| MPCA-001 predecessor runtime | EXISTS, not wired as Increment runtime |
| MPCA-002/003 | NOT REQUIRED on this computer; not Constructor Runtime |

**CAPABILITY (this increment):** Pure Python Lifecycle — internal coordination, not an agent.

**STATE ARTIFACTS:** `ConstructorLifecycleState` / `LifecycleTransition`

**PUBLIC ENTRY:** `run_constructor_lifecycle`

------------------------------------------------------------
INCREMENT BOUNDARY
------------------------------------------------------------

Increment 6 does **NOT** yet provide:

- LangGraph Runtime;
- durable checkpoint persistence;
- durable HITL / resume;
- fresh-reality loop;
- structured Constructor → Admission handoff;
- Supabase lifecycle persistence;
- Agent Control Room.

------------------------------------------------------------
ARCHITECTURE QUALITY CHECK
------------------------------------------------------------

AGENT != CHATBOT: **PASS**<br>
ONE PROFESSIONAL ROLE = ONE AGENT: **PASS**<br>
Lifecycle = capability coordination, not Lifecycle Agent: **PASS**<br>
DETERMINISTIC-FIRST: **PASS**<br>
LLM NOT REQUIRED: **PASS**<br>
LANGGRAPH NOT USED: **PASS**<br>
STREAMLIT NOT USED: **PASS**<br>
SUPABASE WRITES: **NO**<br>
NO MPCA-001/002/003 DEPENDENCY: **PASS**<br>
NO BROAD `except Exception` BUSINESS ROUTING: **PASS**<br>
INCREMENT 1–5 FILES UNCHANGED: **YES**<br>
CAPABILITY REUSE (no duplicated professional calc): **PASS**<br>
CANDIDATE ASSEMBLY BOUNDARY: **PASS**<br>
PHYSICAL CANDIDATE PRESERVATION: **PASS**<br>
ZERO-CANDIDATE VALID: **PASS**<br>
SECURITY NON-DOWNGRADE: **PASS**<br>
PARTIAL ARTIFACT PRESERVATION: **PASS**<br>
INCREMENT 8 HITL BOUNDARY PRESERVED: **YES**<br>
INCREMENT 9 HANDOFF BOUNDARY PRESERVED: **YES**<br>
READY FOR LANGGRAPH WRAPPING LATER: **YES**<br>
EOS-SEC: **PASS**<br>
SEMANTIC ARCHITECTURE REVIEW: **PASS**<br>
CODE QUALITY REVIEW: **PASS**

ARCHITECTURE DRIFT: **NO**

------------------------------------------------------------
SECURITY / EOS-SEC
------------------------------------------------------------

MODEL IS NOT A SECURITY BOUNDARY.<br>
DATA != INSTRUCTION.<br>
Fail closed. Security denial → FAILED only.<br>
No arbitrary SQL / shell / Supabase writes / LLM lifecycle decisions.<br>
Tool allowlist + context remain enforced by Secure Read.

------------------------------------------------------------
FILES
------------------------------------------------------------

CREATED:

- `agents/monthly_plan_constructor/lifecycle.py`
- `tests/test_monthly_plan_constructor_lifecycle.py`

MODIFIED (product Increment 6 commit):
- none — exactly those two files

------------------------------------------------------------
TESTS
------------------------------------------------------------

NEW TESTS (Increment 6): 34 passed / 0 failed<br>
INCREMENT 1 REGRESSION: 20 passed / 0 failed<br>
INCREMENT 2 REGRESSION: 20 passed / 0 failed<br>
INCREMENT 3 REGRESSION: 22 passed / 0 failed<br>
INCREMENT 4 REGRESSION: 26 passed / 0 failed<br>
INCREMENT 5 REGRESSION: 31 passed / 0 failed<br>
PY_COMPILE: PASS<br>
GIT DIFF CHECK: PASS<br>
SEMANTIC ARCHITECTURE: PASS<br>
CODE QUALITY: PASS<br>
EOS-SEC: PASS

------------------------------------------------------------
GIT CHECKPOINT
------------------------------------------------------------

PRODUCT COMMIT: `c35957fd3caeeb4c5c82909a35972248dc8707ea`

MESSAGE: `feat(agents): add constructor pure python lifecycle`

PUSH: YES

LOCAL HEAD: `c35957fd3caeeb4c5c82909a35972248dc8707ea`

REMOTE HEAD: `c35957fd3caeeb4c5c82909a35972248dc8707ea`

LOCAL == REMOTE: YES

FILE COUNT IN PRODUCT COMMIT: 2

Files:

- `agents/monthly_plan_constructor/lifecycle.py`
- `tests/test_monthly_plan_constructor_lifecycle.py`

Recovery point for this stage: **`c35957f`**.

LESSONS_2 GATE: PASS (READ-ONLY; unchanged)<br>
LESSONS_2 PATH: `C:\Users\Андрей\lesson_2`<br>
LESSONS_2 HEAD: `2c4445840cf68ff64cffecbe5a9a9dd21808be04`

Worktree after product push: CLEAN.

------------------------------------------------------------
WHAT IS NOT BUILT YET
------------------------------------------------------------

- LangGraph Runtime (Increment 7) — **NEXT / NOT YET BUILT**
- Durable HITL / Resume (Increment 8)
- Structured Handoff (Increment 9)
- Agent Control Room Integration (Increment 10)
- Production candidate classification capability (outside injected assembly port)
- Wiring into Page10B / production writes
- Admission and later professional agents

------------------------------------------------------------
ONE-LINE SUMMARY
------------------------------------------------------------

На этом этапе Constructor получил первый complete deterministic Pure Python Lifecycle: одна mission run с controlled stages READY / WAIT / FAIL, без LangGraph и без поглощения remainder/classification logic.

------------------------------------------------------------
NEXT
------------------------------------------------------------

Increment 7 — LangGraph Runtime.

Обернёт уже доказанный Pure Python Lifecycle LangGraph-инфраструктурой (graph execution / routing).

Критические business rules, exception policies и readiness laws остаются owned by Pure Python lifecycle и существующими capabilities.

LangGraph **не** должен стать заменой профессиональной логики Constructor.

Increment 7 **не** реализован в этом checkpoint.

============================================================
CHECKPOINT — 2026-08-26 — CONSTRUCTOR AGENT — INCREMENT 7
============================================================

PROGRAM:
Monthly Planning Agentic Orchestration

CURRENT AGENT:
MONTHLY_PLAN_CONSTRUCTOR<br>
Агент формирования кандидатного состава месячного плана

CURRENT INCREMENT:
[7] LangGraph Runtime

STATUS:
DONE

------------------------------------------------------------
WHAT WE BUILT
------------------------------------------------------------

- Dependency gate closed first: `langgraph==1.2.11` declared in `requirements.txt` (`f4ae6fa`). No runtime files in that commit.
- Architecture gate selected **OPTION C**: deterministic one-step lifecycle advancer + thin named LangGraph nodes.
- Pure Python Lifecycle gained public `advance_constructor_lifecycle(...)`: advances authoritative `ConstructorLifecycleState` by **exactly one** professional stage per call.
- `run_constructor_lifecycle(...)` remains backward-compatible and now loops the same stepper until a terminal status.
- New module `langgraph_runtime.py`: thin Constructor LangGraph orchestration over the same stepper.
- Graph business state is a thin envelope only: `ConstructorGraphState = { lifecycle: ConstructorLifecycleState }`.
- No parallel LangGraph business truth. Authoritative state remains `ConstructorLifecycleState`.

------------------------------------------------------------
GRAPH TOPOLOGY
------------------------------------------------------------

```text
START
  ↓
bind_mission
  ↓
load_reality
  ↓
build_package
  ↓
resolve_labor
  ↓
evaluate_exceptions
  ↓
READY_FOR_HANDOFF / WAITING_FOR_HUMAN / FAILED
  ↓
END
```

Each named node calls `advance_constructor_lifecycle(...)` **exactly once**.

Routing reads `lifecycle.status` only.

LangGraph does **not** independently inspect exception codes, package contents, candidate counts, labor values, or readiness predicates to make professional decisions.

Business rules convert reality into lifecycle status; the graph only routes on that status.

Wrong-node / unexpected status → fail closed (`LifecycleError`). No skip / repair / rewind.

------------------------------------------------------------
ARCHITECTURE BOUNDARIES
------------------------------------------------------------

| Layer | Ownership |
|-------|-----------|
| Deterministic Python (Inc 1–6 + advancer) | professional/business rules + deterministic capabilities |
| LangGraph (Inc 7) | runtime / lifecycle orchestration only |
| Supabase | shared operational/business state (unchanged; no Inc 7 writes) |
| Streamlit | Agent Control Room / Human Decision Surface — **not** the agent runtime |

Constructor Agent remains **ONE** professional digital employee.

Mission binding, secure read, candidate assembly, labor norm resolution, and exception evaluation remain internal capabilities/stages/nodes — **not** microagents.

`CandidateAssembler` remains an injected capability boundary.

Preserved quantity law:

```text
Candidate Physical Quantity
!=
Feasible Quantity
!=
Approved Commitment Quantity
```

No remainder / classification math inside `lifecycle.py` or `langgraph_runtime.py`.

Public LangGraph API (Constructor-only; not a generic framework):

- `build_constructor_langgraph(...)`
- `run_constructor_langgraph(...)` → returns `ConstructorLifecycleState`

Dependencies (context, assembler, scope_reader, evidence) are closed over at build/invoke time — **not** stored in graph business state.

------------------------------------------------------------
WHAT THIS GIVES THE SYSTEM
------------------------------------------------------------

Constructor is no longer only a deterministic Python function chain.

It now has an explicit graph-based runtime with named professional lifecycle stages and status-driven routing, while retaining **one** deterministic business truth (`ConstructorLifecycleState`).

This prepares persistent interruption, human decision gates, resume, traceability, and Control Room visualization **without** transferring ownership of construction business logic to LangGraph.

`READY_FOR_HANDOFF` remains eligibility only — not handoff execution.

------------------------------------------------------------
WHERE WE ARE IN THE AGENT ROADMAP
------------------------------------------------------------

Constructor Agent Runtime v0.1 (одна роль, десять инкрементов — не десять агентов):

[1] Mission Scope Contract — **DONE**<br>
[2] Candidate Package Artifact — **DONE**<br>
[3] Secure Read Tool Adapters — **DONE**<br>
[4] Labor Norm Resolver — **DONE**<br>
[5] Exception Engine — **DONE**<br>
[6] Pure Python Lifecycle — **DONE**<br>
[7] LangGraph Runtime — **DONE** (this checkpoint)<br>
[8] Durable HITL / Resume — **NEXT**<br>
[9] Structured Handoff — **NOT STARTED**<br>
[10] Agent Control Room Integration — **NOT STARTED**

Progress after this documentation checkpoint is committed and pushed: **7 / 10**

------------------------------------------------------------
WHERE WE ARE IN THE MONTHLY PLANNING PROGRAM
------------------------------------------------------------

MONTHLY PLAN ORCHESTRATOR<br>
→ **1. CONSTRUCTOR AGENT — CURRENT (increments 1–7 of 10)**<br>
→ 2. ADMISSION AGENT — not started<br>
→ 3. CONSTRAINT AGENT — not started<br>
→ 4. RESOURCE CAPACITY AGENT — not started<br>
→ 5. ECONOMIC EVALUATION AGENT — not started<br>
→ 6. MANAGEMENT DECISION AGENT — not started<br>
→ HUMAN DECISION GATE<br>
→ ПАСПОРТ МЕСЯЧНОГО ПРОИЗВОДСТВЕННОГО ОБЯЗАТЕЛЬСТВА

------------------------------------------------------------
CURRENT AGENT CAPABILITIES
------------------------------------------------------------

| Capability | Status |
|------------|--------|
| Mission scope contract + binder | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`775993f`) |
| Candidate Package artifact | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`862279b`) |
| Secure read adapter | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`af2e9af`) |
| LaborNormResolver | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`f0062e7`) |
| Exception Engine | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`38cd42f`) |
| Pure Python Lifecycle + one-step advancer | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`14945a1`) |
| LangGraph Runtime (thin wrap) | IMPLEMENTED + TESTED + COMMITTED + PUSHED (`14945a1`) |
| Durable HITL / checkpointer / resume | NOT IMPLEMENTED |
| Structured handoff | NOT IMPLEMENTED |
| Agent Control Room | NOT IMPLEMENTED |
| MPCA-001 predecessor runtime | EXISTS, not wired as Increment runtime |
| MPCA-002/003 | NOT REQUIRED on this computer; not Constructor Runtime |

**STATE ARTIFACTS:** `ConstructorLifecycleState` / `LifecycleTransition` / `ConstructorGraphState` (envelope only)

**PUBLIC ENTRIES:** `run_constructor_lifecycle` · `advance_constructor_lifecycle` · `run_constructor_langgraph` · `build_constructor_langgraph`

------------------------------------------------------------
INCREMENT BOUNDARY — WHAT INCREMENT 7 DELIBERATELY DOES NOT DO
------------------------------------------------------------

Increment 7 does **NOT** implement durable HITL.

Absent by design:

- checkpointer / MemorySaver / durable pause;
- `interrupt` / resume;
- restart recovery;
- fresh-reality validation after resume;
- `thread_id` durable runtime requirement.

`WAITING_FOR_HUMAN` remains a **logical terminal** result in Increment 7 (routes to END). Durable pause/resume belongs to:

**Increment 8 — Durable HITL / Resume**

Also deferred:

- structured agent-to-agent handoff / Admission invocation → **Increment 9 — Structured Handoff**
- Streamlit Agent Control Room integration → **Increment 10 — Agent Control Room Integration**

------------------------------------------------------------
ARCHITECTURE QUALITY CHECK
------------------------------------------------------------

AGENT != CHATBOT: **PASS**<br>
ONE PROFESSIONAL ROLE = ONE AGENT: **PASS**<br>
LANGGRAPH != BUSINESS LOGIC: **PASS**<br>
ONE AUTHORITATIVE BUSINESS STATE (`ConstructorLifecycleState`): **PASS**<br>
NO PARALLEL GRAPH BUSINESS TRUTH: **PASS**<br>
ADVANCE EXACTLY ONE STAGE PER CALL: **PASS**<br>
EACH GRAPH NODE CALLS ADVANCE ONCE: **PASS**<br>
ROUTING BY `lifecycle.status` ONLY: **PASS**<br>
DETERMINISTIC-FIRST: **PASS**<br>
LLM NOT REQUIRED / NOT USED: **PASS**<br>
STREAMLIT NOT USED: **PASS**<br>
SUPABASE WRITES: **NO**<br>
NO HANDOFF EXECUTION: **PASS**<br>
NO CHECKPOINTER: **PASS**<br>
CANDIDATE ASSEMBLY BOUNDARY PRESERVED: **PASS**<br>
NO NEW EXCEPTION TAXONOMY: **PASS**<br>
INCREMENT 8 / 9 / 10 SCOPE NOT LEAKED: **YES**<br>
EOS-SEC: **PASS**<br>
IMPLEMENTATION REVIEW GATE: **PASS**<br>
LESSONS_2 ALIGNMENT: **PASS**

ARCHITECTURE DRIFT: **NO**

------------------------------------------------------------
SECURITY / EOS-SEC
------------------------------------------------------------

EOS-SEC: **PASS**

MODEL IS NOT A SECURITY BOUNDARY.<br>
LangGraph is **NOT** a security boundary.

Increment 7 does **not** introduce: LLM decision authority · Supabase writes · arbitrary SQL · shell/exec · service-role / secrets in graph state · automatic critical writes · hidden agent-to-agent chat · handoff execution · authorization bypass.

Existing Mission Scope + `AgentExecutionContext` + Secure Read + fail-closed mapping remain authoritative.

------------------------------------------------------------
FILES
------------------------------------------------------------

DEPENDENCY (separate prior commit):

- `requirements.txt` → `langgraph==1.2.11`
- commit: `f4ae6fa114ec859c2be3fb6de0297c1d1a6c7c89`
- message: `build(agents): add langgraph runtime dependency`

PRODUCT (Increment 7 code commit):

MODIFIED:

- `agents/monthly_plan_constructor/lifecycle.py`
- `tests/test_monthly_plan_constructor_lifecycle.py`

NEW:

- `agents/monthly_plan_constructor/langgraph_runtime.py`
- `tests/test_monthly_plan_constructor_langgraph_runtime.py`

FILE COUNT IN PRODUCT COMMIT: 4

------------------------------------------------------------
TESTS
------------------------------------------------------------

Increment 1: 20 PASS<br>
Increment 2: 20 PASS<br>
Increment 3: 22 PASS<br>
Increment 4: 26 PASS<br>
Increment 5: 31 PASS<br>
Increment 6: 49 PASS<br>
Increment 7: 26 PASS<br>
TOTAL: **194 PASS**

PARITY TESTS: **PASS**<br>
Law: for equivalent deterministic inputs, Pure Python lifecycle business result == LangGraph runtime business result (semantic outcomes; not incidental UUID/timestamp identity).

PY_COMPILE: PASS<br>
IMPLEMENTATION REVIEW GATE: PASS<br>
EOS-SEC REVIEW: PASS<br>
LESSONS_2 ALIGNMENT: PASS

------------------------------------------------------------
GIT CHECKPOINT
------------------------------------------------------------

DEPENDENCY COMMIT: `f4ae6fa114ec859c2be3fb6de0297c1d1a6c7c89`<br>
MESSAGE: `build(agents): add langgraph runtime dependency`

PRODUCT COMMIT: `14945a14e14a700f9bd2080bada2168e4d55f3c3`<br>
MESSAGE: `feat(agents): add constructor langgraph runtime`

PUSH (product): YES / SUCCESS

LOCAL HEAD: `14945a14e14a700f9bd2080bada2168e4d55f3c3`

REMOTE HEAD: `14945a14e14a700f9bd2080bada2168e4d55f3c3`

LOCAL == REMOTE: YES

Recovery point for product code: **`14945a1`**.

LESSONS_2 GATE: PASS (READ-ONLY; unchanged)<br>
LESSONS_2 PATH: `C:\Users\Андрей\lesson_2`

Worktree after product push: CLEAN (before this documentation edit).

------------------------------------------------------------
WHAT IS NOT BUILT YET
------------------------------------------------------------

- Durable HITL / Resume (Increment 8) — **NEXT / NOT YET BUILT**
- Structured Handoff (Increment 9)
- Agent Control Room Integration (Increment 10)
- Production candidate classification capability (outside injected assembly port)
- Wiring into Page10B / production writes
- Admission and later professional agents

------------------------------------------------------------
ONE-LINE SUMMARY
------------------------------------------------------------

На этом этапе Constructor получил thin LangGraph runtime поверх доказанного Pure Python Lifecycle: named nodes + status routing, один authoritative business state, без checkpointer/HITL/handoff и без передачи профессиональной логики в граф.

------------------------------------------------------------
NEXT
------------------------------------------------------------

Increment 8 — Durable HITL / Resume.

Добавит durable pause/resume вокруг уже существующих named nodes и `WAITING_FOR_HUMAN`, без переписывания business laws Increments 1–7.

Increment 8 **не** реализован в этом checkpoint.

============================================================
CHECKPOINT — 2026-08-30 — CONSTRUCTOR AGENT — INCREMENT 8
============================================================

PROGRAM:
Monthly Planning Agentic Orchestration

CURRENT AGENT:
MONTHLY_PLAN_CONSTRUCTOR<br>
Агент формирования кандидатного состава месячного плана

CURRENT INCREMENT:
[8] Durable HITL / Resume

STATUS:
DONE

------------------------------------------------------------
WHAT WE BUILT
------------------------------------------------------------

- Durable Human-in-the-Loop / Resume for Constructor Agent.
- LangGraph `PostgresSaver` is the runtime checkpoint plane (not InMemorySaver as the durability proof).
- Law: `thread_id == run_id`.
- Mandatory `expected_checkpoint_id` gate at the durable resume boundary.
- Missing or stale `expected_checkpoint_id` → fail closed.
- Live `AgentExecutionContext` is required on resume; expired context → fail closed.
- Stale `reality_read` / package / labor are invalidated on clarify resume.
- After resume, Constructor performs a **fresh** secure reality read. Checkpoint is not treated as current project reality.
- Process A / Process B restart-survival is proven with a real PostgreSQL subprocess boundary.
- Human answer is recorded only after the durable security gate.
- Duplicate resume / OPEN request / answer idempotency verified.
- Re-WAIT receives a new deterministic EOS interrupt identity.
- Serializer: `pickle_fallback=False`.
- Checkpoint payload does not contain secrets, `AgentExecutionContext`, DB clients, callables, or DataFrame.

------------------------------------------------------------
WHAT THIS GIVES THE SYSTEM
------------------------------------------------------------

Constructor Agent can now safely stop at `WAITING_FOR_HUMAN`, survive termination of the Python process, and continue in a new process from a durable PostgreSQL checkpoint — without trusting stale pre-WAIT project reality.

Authorization is reconstructed with a fresh trusted `AgentExecutionContext`. Resume may clarify or narrow authorized scope; it must not expand it.

------------------------------------------------------------
WHERE WE ARE IN THE AGENT ROADMAP
------------------------------------------------------------

Constructor Agent Runtime v0.1 (одна роль, десять инкрементов — не десять агентов):

[1] Mission Scope Contract — **DONE**<br>
[2] Candidate Package Artifact — **DONE**<br>
[3] Secure Read Tool Adapters — **DONE**<br>
[4] Labor Norm Resolver — **DONE**<br>
[5] Exception Engine — **DONE**<br>
[6] Pure Python Lifecycle — **DONE**<br>
[7] LangGraph Runtime — **DONE**<br>
[8] Durable HITL / Resume — **DONE** (this checkpoint)<br>
[9] Structured Handoff — **NEXT**<br>
[10] Agent Control Room / Observability — **NOT STARTED**

Progress after this documentation checkpoint is committed: **8 / 10**

------------------------------------------------------------
WHERE WE ARE IN THE MONTHLY PLANNING PROGRAM
------------------------------------------------------------

MONTHLY PLAN ORCHESTRATOR<br>
→ **1. CONSTRUCTOR AGENT — CURRENT (increments 1–8 of 10)**<br>
→ 2. ADMISSION AGENT — not started<br>
→ 3. CONSTRAINT AGENT — not started<br>
→ 4. RESOURCE CAPACITY AGENT — not started<br>
→ 5. ECONOMIC EVALUATION AGENT — not started<br>
→ 6. MANAGEMENT DECISION AGENT — not started<br>
→ HUMAN DECISION GATE<br>
→ ПАСПОРТ МЕСЯЧНОГО ПРОИЗВОДСТВЕННОГО ОБЯЗАТЕЛЬСТВА

------------------------------------------------------------
TEST EVIDENCE
------------------------------------------------------------

FULL CONSTRUCTOR SUITE: **287 PASS**<br>
FAILED: 0<br>
ERRORS: 0<br>
SKIPPED: 0

Durable restart (genuine subprocess + PostgreSQL): **14 PASS**

PY_COMPILE: PASS<br>
PIP CHECK: PASS<br>
SUPABASE USED: NO<br>
PRODUCT DATA CHANGED: NO<br>
REAL SECRETS READ: NO

------------------------------------------------------------
TEST INFRASTRUCTURE
------------------------------------------------------------

A disposable local PostgreSQL Docker container (`execution-os-hitl-test-pg`, localhost bind, tmpfs, synthetic `eos_test` credentials) was used only for the durability gate and was removed after tests.

No production database. No project `.env`. No Supabase.

------------------------------------------------------------
RELEASE
------------------------------------------------------------

CODE COMMIT: `78ff86d546e53c12a60c8f5955fb5291c964aa27`<br>
MESSAGE: `feat(agents): complete constructor durable hitl resume`

origin/main: `78ff86d546e53c12a60c8f5955fb5291c964aa27`

------------------------------------------------------------
FILES (CODE RELEASE — already on origin/main)
------------------------------------------------------------

MODIFIED:

- `agents/monthly_plan_constructor/durable_checkpoint.py`
- `agents/monthly_plan_constructor/langgraph_runtime.py`
- `tests/test_monthly_plan_constructor_langgraph_runtime.py`

NEW:

- `tests/test_monthly_plan_constructor_durable_checkpoint.py`
- `tests/test_monthly_plan_constructor_durable_restart.py`

FILE COUNT IN PRODUCT COMMIT: 5

This documentation file is **not** part of `78ff86d`.

------------------------------------------------------------
WHAT IS NOT BUILT YET
------------------------------------------------------------

- Structured Handoff (Increment 9) — **NEXT / NOT YET BUILT**
- Agent Control Room / Observability (Increment 10)
- Production HITL/audit tables / RLS / product Postgres migrations
- Wiring into Page10B / production writes
- Admission and later professional agents

------------------------------------------------------------
ONE-LINE SUMMARY
------------------------------------------------------------

На этом этапе Constructor получил durable HITL/resume: WAIT переживает гибель Python-процесса, checkpoint живёт в PostgreSQL, resume требует живой authorization и свежей reality, а не восстановленной памяти процесса.

------------------------------------------------------------
NEXT
------------------------------------------------------------

Increment 9 — Structured Handoff.

Increment 9 **не** реализован в этом checkpoint.

============================================================
CHECKPOINT — 2026-08-31 — CONSTRUCTOR AGENT — INCREMENT 9
============================================================

PROGRAM:
Monthly Planning Agentic Orchestration

CURRENT AGENT:
MONTHLY_PLAN_CONSTRUCTOR<br>
Агент формирования кандидатного состава месячного плана

CURRENT INCREMENT:
[9] Structured Handoff

STATUS:
DONE

------------------------------------------------------------
WHAT WE BUILT
------------------------------------------------------------

Increment 9.1 — Structured Handoff Contract<br>
Commit: `4007fee6730cd07c2c1fc80b2965dff84e96636d`

- frozen `ConstructorHandoff`
- deterministic `handoff_id` (`sha256` of schema|type|run|package_id|snapshot_id; `created_at` is not in the id)
- explicit source/target role (`MONTHLY_PLAN_CONSTRUCTOR` → `MONTHLY_PLAN_ADMISSION_AGENT`)
- `CandidatePackageReference`
- `snapshot_id`
- bounded `candidate_ids` (`MAX_CANDIDATE_IDS=1024`, `MAX_CANDIDATE_ID_LENGTH=128`, fail closed, no truncate)
- exceptions / labor summaries
- provenance (`agent_version`, `security_policy_version`)
- fail-closed consistency gates (READY status, package/reality/scope equality, blocking forbid)

Increment 9.2 — Store Protocol + Idempotency<br>
Commit: `91fe1bdc9200bce5ccdeabdf0ae4c93bf57f23cd`

- `ConstructorHandoffStore`
- `get` + atomic `put_if_absent`
- `CREATED`
- `IDEMPOTENT_REPLAY`
- immutable payload
- same id + different payload → `HANDOFF_IMMUTABILITY_CONFLICT`
- deterministic SHA-256 payload digest (canonical JSON; not Python `hash()`, not pickle)

Increment 9.3 — LangGraph Integration<br>
Commit: `b86254d3452d16cdc9ae58ae4893d991c48bd636`

- `READY_FOR_HANDOFF` → `persist_handoff` → `END`
- persistence only after professional READY (no new lifecycle status)
- graph state remains `{lifecycle}` only
- store / context / policy dependencies closed over at build time
- backward compatible when `handoff_store=None` (READY → END)
- no Admission execution
- no hidden agent-to-agent chat

Increment 9.4 — Durable PostgreSQL Proof<br>
Commit: `2cfde3a0c4bc8afdf3e0781833e8f5e254a07448`

- test-only PostgreSQL adapter (`PostgresConstructorHandoffStore` inside the proof test)
- real disposable PostgreSQL 16 (`execution-os-handoff-test-pg`, localhost `127.0.0.1:55432`, tmpfs, synthetic `eos_test`)
- Process A → persist → exit
- Process B fresh interpreter → read / replay
- persistence survives Python process death
- atomic `INSERT … ON CONFLICT DO NOTHING`
- immutability conflict proof
- malformed payload / digest / id fail closed
- two-connection idempotency proof
- production PostgreSQL handoff adapter **NOT** created

------------------------------------------------------------
WHAT THIS GIVES THE SYSTEM
------------------------------------------------------------

Constructor Agent теперь не просто достигает `READY_FOR_HANDOFF`, а формирует и сохраняет структурированный, детерминированный, идемпотентный и неизменяемый handoff-артефакт для следующей профессиональной роли.

Передача между агентами происходит **не** через скрытый prompt/chat, а через formal artifact + identifiers/references.

Admission Agent в Increment 9 **не** реализован и **не** вызывается. Следующий агент должен читать свежую операционную реальность самостоятельно.

`READY_FOR_HANDOFF` остаётся профессиональной готовностью Constructor.<br>
`HANDOFF_READY` — статус отдельного handoff artifact, не новый lifecycle status.

------------------------------------------------------------
ARCHITECTURE LAWS CONFIRMED
------------------------------------------------------------

AGENT ≠ CHATBOT: **PASS**<br>
LLM ≠ AGENT: **PASS**<br>
ONE MAJOR PROFESSIONAL ROLE = ONE SPECIALIZED AGENT: **PASS**<br>
NO HIDDEN AGENT-TO-AGENT CHAT: **PASS**<br>
STRUCTURED HANDOFF: **PASS**<br>
MISSION SCOPE FAIL CLOSED: **PASS**<br>
FRESH REALITY AFTER HITL: **PASS**<br>
BOUNDED PAYLOAD: **PASS**<br>
IDEMPOTENCY: **PASS**<br>
IMMUTABILITY: **PASS**<br>
LEAST PRIVILEGE: **PASS**<br>
MODEL IS NOT SECURITY BOUNDARY: **PASS**<br>
DATA ≠ INSTRUCTION: **PASS**<br>
NO PRODUCT DB WRITE: **PASS**<br>
NO ARBITRARY SQL/SHELL: **PASS**<br>
NO ADMISSION EXECUTION: **PASS**

------------------------------------------------------------
RELEASE TESTS
------------------------------------------------------------

GATE A:<br>
36 Python files `py_compile` **PASS** (19 product + 17 tests)

GATE B:<br>
15 non-PostgreSQL modules<br>
**329 passed / 0 failed / 0 errors / 0 skipped**

GATE D:<br>
27 PostgreSQL durability tests<br>
**27 passed / 0 failed / 0 errors**

GATE E:<br>
FULL Constructor regression<br>
**356 passed / 0 failed / 0 errors / 0 skipped**

GATE F:<br>
`pip check` **PASS**<br>
No broken requirements found

GATE G:<br>
`tests/test_agent_security_governance.py`<br>
**19 passed / 0 failed / 0 errors / 0 skipped**<br>
EOS-SEC Gate **PASS**

GATE H:<br>
disposable PostgreSQL removed<br>
cleanup **PASS**

------------------------------------------------------------
LESSONS_2 GATE
------------------------------------------------------------

LESSON_2 local: `2c4445840cf68ff64cffecbe5a9a9dd21808be04`<br>
remote: `2c4445840cf68ff64cffecbe5a9a9dd21808be04`<br>
local == remote: **YES**<br>
Methodology gate: **PASS**

------------------------------------------------------------
FILES
------------------------------------------------------------

Increment 9 product:

- `agents/monthly_plan_constructor/handoff_contracts.py`
- `agents/monthly_plan_constructor/handoff_store.py`
- `agents/monthly_plan_constructor/langgraph_runtime.py`

Increment 9 test files:

- `tests/test_monthly_plan_constructor_handoff_contracts.py`
- `tests/test_monthly_plan_constructor_handoff_store.py`
- `tests/test_monthly_plan_constructor_langgraph_handoff.py`
- `tests/test_monthly_plan_constructor_handoff_postgres.py`

Production PostgreSQL handoff adapter: **NOT BUILT**

Product Supabase `agent_handoffs` DDL/RLS: **NOT BUILT** / separate future persistence security gate

This documentation file is **not** part of `2cfde3a`.

------------------------------------------------------------
WHAT IS CONSCIOUSLY NOT DONE
------------------------------------------------------------

- Admission Agent
- product Supabase handoff persistence
- production `agent_handoffs` DDL/RLS
- Agent Control Room / Observability (Increment 10)
- visual tracing UI
- system-wide E2E across multiple agents

------------------------------------------------------------
WHERE WE ARE IN THE AGENT ROADMAP
------------------------------------------------------------

Constructor Agent Runtime v0.1 (одна роль, десять инкрементов — не десять агентов):

[1] Mission Scope Contract — **DONE**<br>
[2] Candidate Package Artifact — **DONE**<br>
[3] Secure Read Tool Adapters — **DONE**<br>
[4] Labor Norm Resolver — **DONE**<br>
[5] Exception Engine — **DONE**<br>
[6] Pure Python Lifecycle — **DONE**<br>
[7] LangGraph Runtime — **DONE**<br>
[8] Durable HITL / Resume — **DONE**<br>
[9] Structured Handoff — **DONE** (this checkpoint)<br>
[10] Agent Control Room / Observability — **NEXT**

Progress after this documentation checkpoint is committed: **9 / 10**

------------------------------------------------------------
CONTOUR (unchanged)
------------------------------------------------------------

MONTHLY PLAN ORCHESTRATOR<br>
→ **1. CONSTRUCTOR AGENT — CURRENT (increments 1–9 of 10)**<br>
→ 2. ADMISSION AGENT — not started<br>
→ 3. CONSTRAINT AGENT — not started<br>
→ 4. RESOURCE CAPACITY AGENT — not started<br>
→ 5. ECONOMIC EVALUATION AGENT — not started<br>
→ 6. MANAGEMENT DECISION AGENT — not started<br>
→ HUMAN DECISION GATE<br>
→ ПАСПОРТ МЕСЯЧНОГО ПРОИЗВОДСТВЕННОГО ОБЯЗАТЕЛЬСТВА

------------------------------------------------------------
GIT CHECKPOINT
------------------------------------------------------------

CODE RECOVERY HEAD: `2cfde3a0c4bc8afdf3e0781833e8f5e254a07448`<br>
BRANCH AT CODE RELEASE: `wip/increment-9-structured-handoff`

DOCS COMMIT: **PENDING** — будет заполнен после отдельного commit.

------------------------------------------------------------
WHAT IS NOT BUILT YET
------------------------------------------------------------

- Agent Control Room / Observability (Increment 10) — **NEXT / NOT YET BUILT**
- Production HITL/audit tables / RLS / product Postgres migrations
- Product `agent_handoffs` persistence / Supabase DDL
- Wiring into Page10B / production writes
- Admission and later professional agents

------------------------------------------------------------
ONE-LINE SUMMARY
------------------------------------------------------------

На этом этапе Constructor формирует structured handoff: формальный неизменяемый артефакт с identifiers/references, идемпотентным persist и fail-closed immutability — без скрытого agent chat и без вызова Admission.

------------------------------------------------------------
NEXT
------------------------------------------------------------

Increment 10 — Agent Control Room / Observability.

После Increment 10: System Test & Hardening Week.

============================================================
CHECKPOINT — 2026-09-01 — INCREMENT 10.1 — AGENT-NEUTRAL OBSERVABILITY FOUNDATION
============================================================

PROGRAM:
Monthly Planning Agentic Orchestration

CURRENT AGENT:
MONTHLY_PLAN_CONSTRUCTOR (first tenant of shared observability foundation)

CURRENT INCREMENT:
[10.1] Agent-Neutral Observability Foundation

STATUS:
DONE / ACCEPTED / RELEASE-GATE PASS

------------------------------------------------------------
WHAT WE BUILT
------------------------------------------------------------

10.1A — Core Contracts (`15b0480`):

- `RunRequest`
- `AgentRun`
- `ObservabilityEvent`
- `StageDefinition`
- closed enums / event taxonomy
- Constructor stage catalog as first tenant
- deterministic `RunRequest` idempotency digest
- bounded JSON payload validation
- canonical UTC
- nested copy-safe immutable payloads
- safe serialization
- EOS-SEC secret-safety integration

10.1B — Observability Recorder (`ffacba7`):

- `ObservabilityRecorder` Protocol
- `RecordOutcome`
- `RecordResult`
- `InMemoryObservabilityRecorder`
- `event_id` idempotency:
  - `CREATED`
  - `IDEMPOTENT_REPLAY`
  - conflict fail-closed
- canonical event fingerprint
- append-only semantics
- `RLock` same-process race protection
- test-only snapshot inspection

Architecture specification (10.A1): `bbfa2c6` — `docs/agentic_architecture/AGENT_RUN_CONTROL_AND_OBSERVABILITY_V0_1.md`

------------------------------------------------------------
WHAT THIS GIVES THE SYSTEM
------------------------------------------------------------

Execution OS now has the first shared agent-neutral operational observability foundation.

Future agents can use the same:

- `RunRequest`
- `AgentRun`
- `ObservabilityEvent`
- `StageDefinition`
- `ObservabilityRecorder`

without cloning Constructor-specific control-plane code.

This foundation is required before Run Control, runtime instrumentation, durable store, Query Port, and Agent Control Room.

------------------------------------------------------------
ARCHITECTURE LAWS PRESERVED
------------------------------------------------------------

- `RunRequest` != Authorization
- `AgentRun` != professional lifecycle
- `ObservabilityRecorder` != `ObservabilityStore`
- `InMemoryObservabilityRecorder` != durable truth
- Recorder does not create events
- Recorder does not authorize execution
- Recorder does not update `AgentRun`
- Agent does not start agent
- Control Room != runtime
- Streamlit != source of truth

------------------------------------------------------------
TEST / RELEASE GATES
------------------------------------------------------------

10.1 contract tests: **53 / 53 PASS**<br>
10.1 recorder tests: **32 / 32 PASS**<br>
Combined observability: **85 / 85 PASS**<br>
Constructor pure/local regression: **329 / 329 PASS**<br>
EOS-SEC: **19 / 19 PASS**<br>
py_compile: **PASS**<br>
pip check: **PASS**

Lessons_2: local == remote == `2c4445840cf68ff64cffecbe5a9a9dd21808be04`

------------------------------------------------------------
COMMITS
------------------------------------------------------------

Architecture specification:

- `bbfa2c61cf80440428bd1b470eddbf378a61e102`
- message: `docs(agents): define run control observability architecture`

10.1A:

- `15b048055a80e40abebd65e07820ae75a718cb81`
- message: `feat(agents): add observability core contracts`

10.1B:

- `ffacba71ee47032a8f285e3cd01243a3bd665754`
- message: `feat(agents): add observability recorder protocol`

BRANCH: `wip/increment-10-agent-control-room`

------------------------------------------------------------
FILES
------------------------------------------------------------

Product:

- `agents/observability/__init__.py`
- `agents/observability/contracts.py`
- `agents/observability/recorder.py`

Tests:

- `tests/test_agent_observability_contracts.py`
- `tests/test_agent_observability_recorder.py`

Architecture (10.A1, prior commit):

- `docs/agentic_architecture/AGENT_RUN_CONTROL_AND_OBSERVABILITY_V0_1.md`

------------------------------------------------------------
WHAT IS NOT DONE
------------------------------------------------------------

- NO Run Control yet
- NO runtime instrumentation yet
- NO durable `ObservabilityStore` yet
- NO `AgentRun` durable projection yet
- NO Query Port yet
- NO Agent Control Room yet
- NO production Supabase DDL/RLS
- NO Admission Agent implementation
- Increment 10 overall is **NOT COMPLETE**

No separate product-code 10.1C is required — 10.1A + 10.1B fully satisfy accepted Increment 10.1 scope.

------------------------------------------------------------
WHERE WE ARE IN THE AGENT ROADMAP
------------------------------------------------------------

Constructor Agent Runtime v0.1 (одна роль, десять инкрементов — не десять агентов):

[1] Mission Scope Contract — **DONE**<br>
[2] Candidate Package Artifact — **DONE**<br>
[3] Secure Read Tool Adapters — **DONE**<br>
[4] Labor Norm Resolver — **DONE**<br>
[5] Exception Engine — **DONE**<br>
[6] Pure Python Lifecycle — **DONE**<br>
[7] LangGraph Runtime — **DONE**<br>
[8] Durable HITL / Resume — **DONE**<br>
[9] Structured Handoff — **DONE**<br>
[10] Agent Control Room / Observability — **IN PROGRESS**

Increment 10 decomposition:

- 10.0 — Architecture Discovery — **DONE**
- 10.A0 — WIP branch prep — **DONE**
- 10.A1 — Formal Architecture Spec — **DONE**
- 10.1 — Agent-Neutral Observability Foundation — **DONE** (this checkpoint)
- 10.2 — Run Control — **NEXT / NOT STARTED**
- 10.4 — Durable Observability Store — **NOT STARTED**

Progress: **9 / 10** (Increment 10 overall not complete; do not claim 10 / 10)

------------------------------------------------------------
ONE-LINE SUMMARY
------------------------------------------------------------

На этом этапе Execution OS получил первый shared agent-neutral observability foundation: contracts + recorder protocol, без Run Control, без durable store и без Control Room.

------------------------------------------------------------
NEXT
------------------------------------------------------------

Increment 10.2 — Run Control.

Expected scope:

- `RunRequest` → idempotent run creation
- `run_id` / `request_id` ownership
- authorization boundary
- mission binding
- `AgentRun` operational envelope
- Class A observability events through injected `ObservabilityRecorder`
- managed runtime start boundary

Durable store remains later Increment 10.4.

Increment 10.2 **не** реализован в этом checkpoint.

============================================================
CHECKPOINT — 2026-09-01 — INCREMENT 10.2 — RUN CONTROL
============================================================

PROGRAM:
Monthly Planning Agentic Orchestration

CURRENT AGENT:
MONTHLY_PLAN_CONSTRUCTOR (first consumer of shared Run Control; Run Control itself is agent-neutral)

CURRENT INCREMENT:
[10.2] Run Control

STATUS:
DONE / ACCEPTED / COMMITTED / PUSHED / RELEASE-GATE PASS

------------------------------------------------------------
WHAT WE BUILT
------------------------------------------------------------

- agent-neutral `ManagedRunStartInput`
- `RunControlService`
- `RunControlRegistry` Protocol
- `InMemoryRunControlRegistry`
- Run Control-owned `request_id`
- Run Control-owned `run_id`
- `thread_id == run_id`
- requested `mission_id` binding (never minted by Run Control)
- existing EOS-SEC authorization reuse through `issue_read_only_agent_context`
- `ManagedRuntimeLauncher` Protocol (interface boundary only)
- Class A observability events through injected `ObservabilityRecorder`
- idempotency handling via frozen 10.1 `compute_run_request_digest`
- concurrent duplicate-start protection (same key + same digest)
- explicit process-local reservation state:
  - `IN_PROGRESS`
  - `RESULT_AVAILABLE`
  - `TERMINAL_FAILURE`
- terminal control-plane failure semantics (`CONTROL_PLANE_FAILURE`)
- launch ambiguity semantics (`LAUNCH_OUTCOME_UNKNOWN`)
- generic `SYSTEM_EVENT` direct-start rejection (all agents)
- transient `AgentExecutionContext` (launcher receives context on first authorized start only)
- no cached authorization authority (`authorization_id` safe evidence only)

------------------------------------------------------------
WHAT THIS GIVES THE SYSTEM
------------------------------------------------------------

Run Control now establishes a controlled managed-start boundary.

A start request can no longer directly imply execution.

The system separates:

TRIGGER<br>
→ RUN REQUEST<br>
→ IDEMPOTENCY<br>
→ AUTHORIZATION<br>
→ MISSION BINDING<br>
→ CONTROL-PLANE EVENTS<br>
→ MANAGED RUNTIME LAUNCH BOUNDARY

It prevents accidental duplicate starts inside the same process and prevents idempotent replay from becoming hidden retry.

`RunRequest` != Authorization.<br>
Trigger != Authorization != Execution.<br>
`AgentRun` operational status != Constructor professional lifecycle state.<br>
Run Control != Orchestrator.<br>
Run Control != agent business logic.<br>
`SYSTEM_EVENT` = orchestration ingress, not direct specialized-agent execution.

------------------------------------------------------------
PLACE IN OVERALL ARCHITECTURE
------------------------------------------------------------

Increment 10.2 sits between:

- **10.1** Agent-Neutral Observability Foundation
- **10.3** Runtime Instrumentation

It prepares the generic managed control plane but does **NOT** yet execute Constructor LangGraph directly.

`ManagedRuntimeLauncher` in 10.2 is an interface boundary only. Real Constructor runtime integration belongs to **10.3**.

------------------------------------------------------------
ARCHITECTURE LAWS CONFIRMED
------------------------------------------------------------

- MODEL IS NOT SECURITY BOUNDARY
- DATA != INSTRUCTION
- no second authorization system
- authorization before launcher
- `SYSTEM_EVENT` cannot directly invoke managed agent
- `AgentExecutionContext` is transient
- replay cannot reauthorize
- replay cannot relaunch
- launch ambiguity becomes `LAUNCH_OUTCOME_UNKNOWN`
- control-plane evidence failure stops managed start
- no secrets / SQL / shell / Streamlit authority in Run Control

Authorized Class A event order:

`RUN_REQUESTED` → `RUN_AUTHORIZATION_STARTED` → `RUN_AUTHORIZED` → `MISSION_BOUND` → `RUN_STARTED`

Denied path:

`RUN_REQUESTED` → `RUN_AUTHORIZATION_STARTED` → `RUN_DENIED`

------------------------------------------------------------
TEST / RELEASE GATES
------------------------------------------------------------

Focused Run Control: **51 / 51 PASS**<br>
Observability contracts: **53 / 53 PASS**<br>
Observability recorder: **32 / 32 PASS**<br>
Constructor pure/local regression: **329 / 329 PASS**<br>
EOS-SEC: **36 / 36 PASS**<br>
py_compile: **PASS**<br>
pip check: **PASS**

Release gates: Git/Scope · Lessons_2 · Functional · Observability · Constructor · EOS-SEC architecture — **ALL PASS**

Lessons_2: local == remote == `2c4445840cf68ff64cffecbe5a9a9dd21808be04`

------------------------------------------------------------
COMMITS
------------------------------------------------------------

CODE COMMIT:

- `300696bebc3604d3da189b5aef9af9cb1af1710b`
- message: `feat(agents): add managed run control`

BRANCH: `wip/increment-10-agent-control-room`

LOCAL WIP HEAD: `300696bebc3604d3da189b5aef9af9cb1af1710b`<br>
REMOTE WIP HEAD: `300696bebc3604d3da189b5aef9af9cb1af1710b`<br>
LOCAL == REMOTE: **YES**

origin/main unchanged: `c24708b3a40eb930f7879d3fd764784be057cc1e`

------------------------------------------------------------
FILES
------------------------------------------------------------

Product:

- `agents/run_control/__init__.py`
- `agents/run_control/contracts.py`
- `agents/run_control/registry.py`
- `agents/run_control/service.py`

Tests:

- `tests/test_run_control_contracts.py`
- `tests/test_run_control_registry.py`
- `tests/test_run_control_service.py`
- `tests/test_run_control_failure_state.py`

FILE COUNT IN CODE COMMIT: 8

NEW DEPENDENCIES: **NONE**

------------------------------------------------------------
WHAT IS NOT DONE
------------------------------------------------------------

- NO durable Run Control store (Increment 10.4)
- NO distributed idempotency
- NO exactly-once across processes
- NO Supabase observability persistence
- NO real Constructor launcher adapter
- NO LangGraph runtime instrumentation
- NO HITL visual control
- NO Query Port
- NO Control Room UI
- NO Orchestrator runtime
- NO Admission Agent
- Increment 10 overall is **NOT COMPLETE**

NON-DURABLE · PROCESS-LOCAL: restart loses idempotency registry state and process-local cached result/failure state. Durable truth remains Increment 10.4.

------------------------------------------------------------
WHERE WE ARE IN THE AGENT ROADMAP
------------------------------------------------------------

Constructor Agent Runtime v0.1 (одна роль, десять инкрементов — не десять агентов):

[1] Mission Scope Contract — **DONE**<br>
[2] Candidate Package Artifact — **DONE**<br>
[3] Secure Read Tool Adapters — **DONE**<br>
[4] Labor Norm Resolver — **DONE**<br>
[5] Exception Engine — **DONE**<br>
[6] Pure Python Lifecycle — **DONE**<br>
[7] LangGraph Runtime — **DONE**<br>
[8] Durable HITL / Resume — **DONE**<br>
[9] Structured Handoff — **DONE**<br>
[10] Agent Control Room / Observability — **IN PROGRESS**

Increment 10 decomposition:

- 10.0 — Architecture Discovery — **DONE**
- 10.A0 — WIP branch prep — **DONE**
- 10.A1 — Formal Architecture Spec — **DONE**
- 10.1 — Agent-Neutral Observability Foundation — **DONE**
- 10.2 — Run Control — **DONE** (this checkpoint)
- 10.3 — Runtime Instrumentation — **NEXT / NOT STARTED**
- 10.4 — Durable Observability Store — **NOT STARTED**

Progress: **9 / 10** (Increment 10 overall not complete; do not claim 10 / 10)

------------------------------------------------------------
ONE-LINE SUMMARY
------------------------------------------------------------

На этом этапе Execution OS получил agent-neutral Run Control: managed start с idempotency, EOS-SEC authorization, mission binding, Class A events и launcher boundary — без durable store и без прямого запуска Constructor LangGraph.

------------------------------------------------------------
NEXT
------------------------------------------------------------

Increment 10.3 — Runtime Instrumentation.

Expected scope:

- real `ManagedRuntimeLauncher` adapter for Constructor LangGraph
- runtime node instrumentation
- synchronization between control-plane events and Constructor professional runtime

Increment 10.3 **не** реализован в этом checkpoint.

============================================================
CHECKPOINT — 2026-09-01 — INCREMENT 10.3A — RUNTIME INSTRUMENTATION FOUNDATION
============================================================

PROGRAM:
Monthly Planning Agentic Orchestration

CURRENT AGENT:
MONTHLY_PLAN_CONSTRUCTOR (first consumer of Constructor runtime instrumentation helpers)

CURRENT INCREMENT:
[10.3A] Runtime Instrumentation Foundation

STATUS:
DONE / ACCEPTED / COMMITTED / PUSHED / RELEASE-GATED

------------------------------------------------------------
WHAT WE BUILT
------------------------------------------------------------

Product:

- `agents/monthly_plan_constructor/runtime_instrumentation.py`

Tests:

- `tests/test_constructor_runtime_instrumentation.py`

Main contracts:

- `ConstructorRuntimeEventKey`
- `compute_constructor_runtime_event_id(...)`
- `ConstructorRuntimeInstrumentation`
- `validate_constructor_stage_id(...)`
- `is_constructor_stage_id(...)`

Core architecture:

- deterministic event identity for Constructor runtime facts
- namespace `constructor_runtime_event.v0.1`
- canonical JSON + SHA-256 → `crt-evt-{digest}`
- no timestamp / uuid / randomness in event identity
- existing frozen `CONSTRUCTOR_STAGE_CATALOG` reused (no second catalog)
- existing `build_observability_event(...)` reused (no second event model)
- injected `ObservabilityRecorder` write Protocol only
- `RecordResult` preserved (`CREATED` / `IDEMPOTENT_REPLAY`)
- no Recorder read dependency (`snapshot_events`, fingerprint maps, internal dicts forbidden in production path)
- no `InMemoryObservabilityRecorder` production dependency
- no second state machine (no stage store, span store, dedup cache, runtime status registry)

------------------------------------------------------------
EVENT OWNERSHIP
------------------------------------------------------------

Constructor runtime instrumentation **MUST NOT** emit Run Control-owned events:

- `RUN_REQUESTED`
- `RUN_AUTHORIZATION_STARTED`
- `RUN_AUTHORIZED`
- `RUN_DENIED`
- `MISSION_BOUND`
- `RUN_STARTED`

Blocked fail-closed in `ConstructorRuntimeEventKey`.

The runtime helper only validates, builds, and emits **caller-specified** runtime-owned facts.

`RUNTIME_OWNED_EVENT_TYPES` is documentary only — not a second authority system.

**Advisory (non-blocker):** `RETRY_REQUESTED` / `RETRY_STARTED` ownership must be resolved before or during **10.3B** runtime wiring. Not resolved in 10.3A. No `EventType` enum changes.

------------------------------------------------------------
REPLAY / IDEMPOTENCY SEMANTICS
------------------------------------------------------------

- same deterministic `event_id` + identical payload → `IDEMPOTENT_REPLAY`
- same `event_id` + changed payload or `occurred_at` → recorder conflict, fail closed
- no automatic `REPLAY_DETECTED` (recorder replay ≠ LangGraph semantic replay)
- replay detection requires actual runtime knowledge in later slices
- `semantic_occurrence_key` + `resume_n` + `attempt_n` support multiple stage occurrences within one run

Caller owns `occurred_at` semantics.

------------------------------------------------------------
SECURITY
------------------------------------------------------------

- no `AgentExecutionContext` stored or accepted in payloads
- no authority cache
- no SQL / shell / Supabase / Streamlit
- no LangGraph dependency inside 10.3A helper module
- no secrets / raw rows / DataFrames / documents in events
- observability payload bounds from Increment 10.1 reused (not Handoff contract limits)
- instrumentation cannot authorize, change mission, expand scope, or start agents

------------------------------------------------------------
WHAT THIS GIVES THE SYSTEM
------------------------------------------------------------

10.3A defines **HOW** Constructor runtime operational facts are represented and safely recorded.

It does **NOT** yet define **WHERE** LangGraph nodes emit them.

Conceptual chain:

Run Control<br>
→ authorized runtime start boundary<br>
→ **Runtime Instrumentation Foundation (10.3A)**<br>
→ real LangGraph stage wiring (**10.3B**)

Observability RECORDS execution truth. It does NOT become execution truth.

------------------------------------------------------------
PLACE IN OVERALL ARCHITECTURE
------------------------------------------------------------

Increment 10.3A sits between:

- **10.2** Run Control
- **10.3B** Core LangGraph Stage Wiring

10.3A is foundation only. No actual node instrumentation yet.

------------------------------------------------------------
WHAT IS NOT DONE
------------------------------------------------------------

- NO actual LangGraph node instrumentation
- NO `ConstructorManagedRuntimeLauncher`
- NO stage wiring
- NO HITL wiring
- NO handoff / completion wiring
- NO durable observability store (Increment 10.4)
- NO Query Port
- NO Control Room UI
- NO Supabase observability persistence
- Increment 10.3 overall is **NOT COMPLETE**
- Increment 10 overall is **NOT COMPLETE**

------------------------------------------------------------
TEST / RELEASE GATES
------------------------------------------------------------

10.3A focused: **37 / 37 PASS**<br>
Observability contracts: **53 / 53 PASS**<br>
Observability recorder: **32 / 32 PASS**<br>
Run Control: **51 / 51 PASS**<br>
Constructor standard gate: **329 / 329 PASS**<br>
EOS-SEC: **36 / 36 PASS**<br>
py_compile: **PASS**<br>
pip check: **PASS**

**FULL POSTGRES INTEGRATION SUITE:** **ENVIRONMENT_BLOCKED**<br>
Reason: disposable PostgreSQL unavailable at `127.0.0.1:55432`<br>
This is **NOT** classified as code regression. Do **not** claim full `unittest discover` PASS.

Release gates: Git/Scope · Lessons_2 · Environment · Functional · Observability · Constructor standard · EOS-SEC architecture — **ALL PASS**

Lessons_2: local == remote == `2c4445840cf68ff64cffecbe5a9a9dd21808be04`

------------------------------------------------------------
ENVIRONMENT RULE
------------------------------------------------------------

All Execution OS release tests on this computer use:

`C:\csv_fix\.venv\Scripts\python.exe`

Do **not** use system Python for release gates.

LangGraph installed in project venv: **1.2.11**

------------------------------------------------------------
COMMITS
------------------------------------------------------------

CODE COMMIT:

- `c4baaecf4ad17af7c31c0533da76056e8a26e74a`
- message: `feat(agents): add constructor runtime instrumentation foundation`

BRANCH: `wip/increment-10-agent-control-room`

LOCAL WIP HEAD: `c4baaecf4ad17af7c31c0533da76056e8a26e74a`<br>
REMOTE WIP HEAD: `c4baaecf4ad17af7c31c0533da76056e8a26e74a`<br>
LOCAL == REMOTE: **YES**

origin/main unchanged: `c24708b3a40eb930f7879d3fd764784be057cc1e`

------------------------------------------------------------
FILES
------------------------------------------------------------

Product:

- `agents/monthly_plan_constructor/runtime_instrumentation.py`

Tests:

- `tests/test_constructor_runtime_instrumentation.py`

FILE COUNT IN CODE COMMIT: 2

NEW DEPENDENCIES: **NONE**

------------------------------------------------------------
WHERE WE ARE IN THE AGENT ROADMAP
------------------------------------------------------------

Constructor Agent Runtime v0.1:

[1]–[9] — **DONE**<br>
[10] Agent Control Room / Observability — **IN PROGRESS**

Increment 10 decomposition:

- 10.0 — Architecture Discovery — **DONE**
- 10.A0 — WIP branch prep — **DONE**
- 10.A1 — Formal Architecture Spec — **DONE**
- 10.1 — Agent-Neutral Observability Foundation — **DONE**
- 10.2 — Run Control — **DONE**
- 10.3A — Runtime Instrumentation Foundation — **DONE** (this checkpoint)
- 10.3B — Core LangGraph Stage Wiring — **NEXT / NOT STARTED**
- 10.4 — Durable Observability Store — **NOT STARTED**

Progress: **9 / 10** (Increment 10 overall not complete; do not claim 10 / 10)

------------------------------------------------------------
ONE-LINE SUMMARY
------------------------------------------------------------

На этом этапе Execution OS получил Constructor runtime instrumentation foundation: deterministic event identity, stage validation, safe Recorder emission и Run Control event ownership — без LangGraph wiring, без launcher и без durable store.

------------------------------------------------------------
NEXT
------------------------------------------------------------

Increment 10.3B — Core LangGraph Stage Wiring.

Expected scope:

- inject `ObservabilityRecorder` into Constructor LangGraph runtime
- thin stage/node event wiring around existing lifecycle advance
- preserve professional lifecycle vs operational event separation

Increment 10.3B **не** реализован в этом checkpoint.

---

============================================================
CHECKPOINT — 2026-09-02 — CONSTRUCTOR AGENT — INCREMENT 10.3B
============================================================

PROGRAM:
Monthly Planning Agentic Orchestration

CURRENT AGENT:
MONTHLY_PLAN_CONSTRUCTOR

CURRENT INCREMENT:
[10.3B] Core LangGraph Stage Wiring

STATUS:
DONE

------------------------------------------------------------
WHAT WE BUILT
------------------------------------------------------------

Increment 10.3B wired the existing observability runtime foundation (10.3A) into the **real** Constructor LangGraph professional execution path.

Four core LangGraph nodes now emit structured runtime stage events through optional `ObservabilityRecorder` injection:

| LangGraph node | Professional stage | Events |
|----------------|-------------------|--------|
| `load_reality` | `REALITY_READ` | `STAGE_STARTED` → `STAGE_COMPLETED` or `STAGE_FAILED` |
| `build_package` | `CANDIDATE_ASSEMBLY` | `STAGE_STARTED` → `STAGE_COMPLETED` or `STAGE_FAILED` |
| `resolve_labor` | `LABOR_NORM_RESOLUTION` | `STAGE_STARTED` → `STAGE_COMPLETED` or `STAGE_FAILED` |
| `evaluate_exceptions` | `EXCEPTION_ANALYSIS` | `STAGE_STARTED` → `STAGE_COMPLETED` or `STAGE_FAILED` |

Terminal event type follows **actual professional lifecycle outcome** — not merely function return.

**Not instrumented in 10.3B** (deferred to later 10.3 slices):

- `bind_mission` (AUTHORIZATION / MISSION_BINDING)
- `human_wait` (HITL — 10.3D)
- `revalidate_reality` (REALITY_REVALIDATION — 10.3D)
- `persist_handoff` (HANDOFF — 10.3E)

Injection seam (backward-compatible):

- `build_constructor_langgraph(..., recorder: ObservabilityRecorder | None = None)`
- `run_constructor_langgraph(..., recorder: ObservabilityRecorder | None = None)`
- `recorder=None` preserves Increment 7–9 runtime behavior unchanged

------------------------------------------------------------
IMPORTANT SEMANTICS
------------------------------------------------------------

**WAITING_FOR_HUMAN is NOT STAGE_FAILED.**

It means the professional stage **completed** with a human-routed result. HITL wait events belong to 10.3D, not 10.3B.

| Professional outcome | Stage event |
|---------------------|-------------|
| Expected success progression | `STAGE_COMPLETED` |
| `WAITING_FOR_HUMAN` | `STAGE_COMPLETED` (not failure) |
| `FAILED` | `STAGE_FAILED` |

**Recorder failure policy:** propagate fail-closed. Do **not** mutate professional lifecycle to encode recorder outage. Do **not** invent `RUN_FAILED` in 10.3B.

**Architecture boundaries preserved:**

- recorder optional; `recorder=None` → no instrumentation overhead path
- recorder is **NOT** stored in graph state
- recorder is **NOT** stored in lifecycle state
- no global / singleton recorder
- no Streamlit dependency
- no Supabase dependency
- no Postgres dependency for 10.3B
- no Run Control event duplication (`RUN_REQUESTED`, `RUN_AUTHORIZED`, `MISSION_BOUND`, etc.)

**Lifecycle error law:** if `LifecycleError` / orchestration contract error raises before professional result, propagate exception. Do **not** invent false `STAGE_COMPLETED` / `STAGE_FAILED`.

------------------------------------------------------------
REPLAY / IDEMPOTENCY
------------------------------------------------------------

LangGraph checkpoint replay may re-execute node code before interrupt/resume.

10.3B uses deterministic semantic occurrence identity from **existing lifecycle artifacts** (no invented counters, timestamps, UUIDs, or globals):

| Stage | `semantic_occurrence_key` | `resume_n` |
|-------|---------------------------|------------|
| `REALITY_READ` | `"initial"` | `0` |
| `CANDIDATE_ASSEMBLY` | `snapshot-{read_id}` | derived from REALITY_LOADED transition count |
| `LABOR_NORM_RESOLUTION` | `package-{package_id}` | derived from REALITY_LOADED transition count |
| `EXCEPTION_ANALYSIS` | `package-{package_id}` | derived from REALITY_LOADED transition count |

Same semantic coordinates → same deterministic `event_id` → recorder returns **`IDEMPOTENT_REPLAY`**.

Do **not** claim exactly-once delivery. Do **not** emit `REPLAY_DETECTED` without explicit runtime proof (not in 10.3B).

------------------------------------------------------------
WHAT THIS GIVES THE SYSTEM
------------------------------------------------------------

До 10.3B observability-инфраструктура уже существовала, но теперь сам живой LangGraph Constructor Agent во время реальной профессиональной работы оставляет структурированный цифровой след по своим основным стадиям.

Это означает, что будущий Agent Control Room сможет показывать не придуманный UI-статус, а фактические runtime-события цифрового сотрудника.

Conceptual chain now:

Run Control<br>
→ authorized runtime start boundary<br>
→ Runtime Instrumentation Foundation (10.3A)<br>
→ **Core LangGraph Stage Wiring (10.3B)** ← this checkpoint<br>
→ Tool / Artifact instrumentation (10.3C)

Observability RECORDS execution truth. It does NOT become execution truth.

------------------------------------------------------------
PLACE IN OVERALL ARCHITECTURE
------------------------------------------------------------

Increment 10.3B sits between:

- **10.3A** Runtime Instrumentation Foundation (HOW events are built)
- **10.3C** Tool / Artifact Runtime Instrumentation (WHERE tool calls and artifacts emit)

10.3B is thin runtime-boundary wiring only. No changes to `lifecycle.py`, domain modules, or Run Control.

------------------------------------------------------------
WHAT IS NOT DONE
------------------------------------------------------------

- NO `TOOL_CALL_*` / `ARTIFACT_CREATED` events (10.3C)
- NO `HUMAN_WAIT_STARTED` / `HUMAN_DECISION_RECEIVED` / `RUN_RESUMED` / `REALITY_REFRESH_*` (10.3D)
- NO `HANDOFF_CREATED` / `HANDOFF_PERSISTED` / `RUN_COMPLETED` terminal wiring (10.3E)
- NO `ConstructorManagedRuntimeLauncher`
- NO durable observability store (Increment 10.4)
- NO Query Port
- NO Control Room UI
- NO Supabase observability persistence
- Increment 10.3 overall is **NOT COMPLETE**
- Increment 10 overall is **NOT COMPLETE**

------------------------------------------------------------
TEST / RELEASE GATES
------------------------------------------------------------

10.3B focused: **16 / 16 PASS**<br>
LangGraph runtime + handoff + 10.3A combined: **98 / 98 PASS**<br>
Observability contracts + recorder: **85 / 85 PASS** (within combined gate)<br>
Run Control: **51 / 51 PASS** (within combined gate)<br>
Constructor standard gate: **382 / 382 PASS**<br>
Observability + Run Control + EOS-SEC combined: **155 / 155 PASS**<br>
EOS-SEC: **36 / 36 PASS** (within combined gate)<br>
py_compile: **PASS**<br>
pip check: **PASS**

**FULL POSTGRES DURABLE RESTART SUITE:** **ENVIRONMENT_BLOCKED**<br>
Reason: disposable PostgreSQL unavailable at `127.0.0.1:55432`<br>
This is **NOT** classified as a 10.3B regression. Do **not** claim full postgres integration PASS.

Release gates: Git/Scope · Lessons_2 · Environment · Functional · Observability · Constructor standard · EOS-SEC architecture — **ALL PASS**

Lessons_2: local == remote == `2c4445840cf68ff64cffecbe5a9a9dd21808be04`

Project test Python: `C:\csv_fix\.venv\Scripts\python.exe`<br>
LangGraph in project venv: **1.2.11**

------------------------------------------------------------
COMMITS
------------------------------------------------------------

CODE COMMIT:

- `08a061a216f2ccc5d8daf7906e0b155882f40b9d`
- message: `feat(agents): wire constructor core stage observability`

BRANCH: `wip/increment-10-agent-control-room`

LOCAL WIP HEAD: `08a061a216f2ccc5d8daf7906e0b155882f40b9d`<br>
REMOTE WIP HEAD: `08a061a216f2ccc5d8daf7906e0b155882f40b9d`<br>
LOCAL == REMOTE: **YES**

origin/main unchanged: `c24708b3a40eb930f7879d3fd764784be057cc1e`

------------------------------------------------------------
FILES
------------------------------------------------------------

Product:

- `agents/monthly_plan_constructor/langgraph_runtime.py`

Tests:

- `tests/test_constructor_langgraph_stage_instrumentation.py`

FILE COUNT IN CODE COMMIT: 2

NON-10.3B FILES IN COMMIT: **NO**

NEW DEPENDENCIES: **NONE**

**Not modified:** `runtime_instrumentation.py`, `lifecycle.py`, Run Control, observability contracts, domain modules.

------------------------------------------------------------
WHERE WE ARE IN THE AGENT ROADMAP
------------------------------------------------------------

Constructor Agent Runtime v0.1:

[1]–[9] — **DONE**<br>
[10] Agent Control Room / Observability — **IN PROGRESS**

Increment 10 decomposition:

- 10.0 — Architecture Discovery — **DONE**
- 10.A0 — WIP branch prep — **DONE**
- 10.A1 — Formal Architecture Spec — **DONE**
- 10.1 — Agent-Neutral Observability Foundation — **DONE**
- 10.2 — Run Control — **DONE**
- 10.3A — Runtime Instrumentation Foundation — **DONE**
- 10.3B — Core LangGraph Stage Wiring — **DONE** (this checkpoint)
- 10.3C — Tool / Artifact Runtime Instrumentation — **NEXT / NOT STARTED**
- 10.3D — HITL / Revalidation Runtime Instrumentation — **NOT STARTED**
- 10.3E — Handoff / Completion Runtime Instrumentation — **NOT STARTED**
- 10.4 — Durable Observability Store — **NOT STARTED**

Progress: **9 / 10** (Increment 10 overall not complete; do not claim 10 / 10)

------------------------------------------------------------
ONE-LINE SUMMARY
------------------------------------------------------------

На этом этапе Execution OS подключил observability runtime к четырём core LangGraph стадиям Constructor Agent: REALITY_READ, CANDIDATE_ASSEMBLY, LABOR_NORM_RESOLUTION и EXCEPTION_ANALYSIS теперь оставляют детерминированный STAGE_STARTED / STAGE_COMPLETED / STAGE_FAILED след во время реальной профессиональной работы.

------------------------------------------------------------
NEXT
------------------------------------------------------------

Increment 10.3C — Tool / Artifact Runtime Instrumentation.

Expected scope:

- structured observability around actual secure-read / domain tool usage
- `TOOL_CALL_STARTED` / `TOOL_CALL_COMPLETED` / `TOOL_CALL_DENIED`
- `ARTIFACT_CREATED` for business artifacts (reality read, package, etc.)
- still no Control Room UI, no durable store, no Supabase observability persistence

Increment 10.3C **не** реализован в этом checkpoint.

---

============================================================
CHECKPOINT — 2026-09-02 — CONSTRUCTOR AGENT — INCREMENT 10.3C
TOOL / ARTIFACT RUNTIME INSTRUMENTATION
============================================================

PROGRAM:
Monthly Planning Agentic Orchestration

CURRENT AGENT:
MONTHLY_PLAN_CONSTRUCTOR

CURRENT INCREMENT:
[10.3C] Tool / Artifact Runtime Instrumentation

STATUS:
DONE

------------------------------------------------------------
WHAT WE BUILT
------------------------------------------------------------

Increment 10.3C extended the live Constructor runtime observability hierarchy from:

```
RUN
→ STAGE
```

to:

```
RUN
→ STAGE
    → TOOL
    → ARTIFACT
```

Architecture law preserved: **Python function call ≠ tool call** · **Skill ≠ tool**.

Not every Python function in the Constructor graph is classified as a tool. Only the current core professional EOS-SEC tool seam is instrumented in 10.3C.

**REALITY_READ chronology (10.3C):**

```
STAGE_STARTED
→ TOOL_CALL_STARTED
→ professional secure read (single-source lifecycle step)
→ TOOL_CALL_COMPLETED or TOOL_CALL_DENIED
→ ARTIFACT_CREATED (if new ConstructorRealityRead)
→ STAGE_COMPLETED or STAGE_FAILED   (10.3B ownership unchanged)
```

**CANDIDATE_ASSEMBLY chronology (10.3C addition):**

```
STAGE_STARTED
→ professional advance (10.3B unchanged)
→ ARTIFACT_CREATED (if new CandidatePackage)
→ STAGE_COMPLETED or STAGE_FAILED
```

------------------------------------------------------------
TOOL OBSERVABILITY
------------------------------------------------------------

Current 10.3C tool scope is intentionally narrow.

The only core professional EOS-SEC tool instrumented in 10.3C:

| Constant | Tool name | Node | Stage |
|----------|-----------|------|-------|
| `TOOL_LOAD_SCOPE` | `load_constructor_scope` | `load_reality` | `REALITY_READ` |

Structured events:

- `TOOL_CALL_STARTED`
- `TOOL_CALL_COMPLETED`
- `TOOL_CALL_DENIED`

Existing contract does **NOT** use `TOOL_CALL_FAILED`.

Failure distinction within `TOOL_CALL_DENIED`:

| Failure class | Event | EventStatus |
|---------------|-------|-------------|
| Security denial | `TOOL_CALL_DENIED` | `DENIED` |
| Controlled read / contract / tool failure | `TOOL_CALL_DENIED` | `FAILED` |

No observability contract changes were required (`agents/observability/contracts.py` untouched).

**Not classified as tools in 10.3C:** `assemble_candidates`, `build_candidate_package`, `resolve_labor_norms`, `exceptions_from_labor_resolutions`, scope reader internal port, checkpointer, HITL store, handoff persistence.

------------------------------------------------------------
BUSINESS ARTIFACT OBSERVABILITY
------------------------------------------------------------

Exactly two accepted artifact types in 10.3C:

| Artifact | `artifact_id` | Event |
|----------|---------------|-------|
| `ConstructorRealityRead` | `read_id` | `ARTIFACT_CREATED` |
| `CandidatePackage` | `package_id` | `ARTIFACT_CREATED` |

Observability stores only safe metadata and correlation references.

Safe metadata (examples): `row_count`, `schema_version`, `tool_name`, `candidate_count`, `snapshot_id` reference.

Observability does **NOT** store:

- raw rows
- DataFrames
- candidate arrays
- raw evidence
- `AgentExecutionContext`
- credentials
- tokens
- full business payloads

**CandidatePackage detection:** post-hoc before/after lifecycle comparison. Emit only when `before.package` absent/different and `after.package` represents a newly created package. No artifact event on replay of existing package identity.

------------------------------------------------------------
IMPORTANT ARTIFACT BOUNDARY
------------------------------------------------------------

10.3C did **NOT** instrument:

- `LaborNormResolutionSet`
- `ConstructorExceptionSet`

Reason: they currently do not have accepted independent stable business artifact identity. No synthetic artifact IDs were invented (e.g. no `{package_id}-exceptions`).

Architecture law:

**OBSERVABILITY MUST NOT INVENT BUSINESS ENTITIES OR BUSINESS IDENTITY FOR UI CONVENIENCE.**

`ConstructorHandoff` also remains out of scope and belongs to **10.3E**.

------------------------------------------------------------
SINGLE-SOURCE REALITY READ
------------------------------------------------------------

Lifecycle refactor (mechanical extraction only):

- `advance_constructor_reality_read_step(...)` extracted from `lifecycle.py`
- Purpose: allow LangGraph runtime instrumentation to wrap the real professional reality-read step without duplicating business transition logic

Architecture law:

**ONE PROFESSIONAL LOGIC = ONE SOURCE OF TRUTH**

- `advance_constructor_lifecycle()` delegates the `MISSION_BOUND` reality-read branch to the extracted function
- LangGraph `_instrumented_reality_read_advance()` calls the same function

Verified:

- no lifecycle semantic change
- no new status
- no new state field
- no routing change
- no failure mapping change
- transition history preserved

------------------------------------------------------------
TEST COMPATIBILITY FIX (10.3B REGRESSION)
------------------------------------------------------------

`tests/test_constructor_langgraph_stage_instrumentation.py` received a justified compatibility correction.

Reason: before 10.3C only `STAGE_*` events carried the relevant core `stage_id` in those tests. After nested TOOL / ARTIFACT observability, tool/artifact events legitimately share `stage_id`.

The `_stage_events()` helper now filters actual stage event types:

- `STAGE_STARTED`
- `STAGE_COMPLETED`
- `STAGE_FAILED`

This does **NOT** weaken 10.3B regression protection:

| Check | Result |
|-------|--------|
| Assertions removed | **NO** |
| Tests disabled | **NO** |
| Expected stage semantics weakened | **NO** |

------------------------------------------------------------
REPLAY / IDEMPOTENCY
------------------------------------------------------------

Deterministic semantic occurrence identity continues to use existing runtime coordinates.

Examples:

| Kind | `semantic_occurrence_key` concept |
|------|-----------------------------------|
| Tool | `{stage_key}/tool-{TOOL_LOAD_SCOPE}` |
| Reality artifact | `{stage_key}/artifact-snapshot-{read_id}` |
| Package artifact | `{stage_key}/artifact-package-{package_id}` |

No random observability UUID/counters were introduced.

Same semantic replay → **`IDEMPOTENT_REPLAY`**.

Do **not** claim exactly-once delivery. Do **not** emit `REPLAY_DETECTED` without explicit runtime proof.

Post-HITL fresh reality instrumentation belongs to **10.3D** — not solved in 10.3C.

------------------------------------------------------------
DATA MINIMIZATION / EOS-SEC
------------------------------------------------------------

Observability is **NOT** a second business database.

Events contain safe references and metadata only.

**Recorder failure policy (unchanged from 10.3B):** fail-closed propagation:

- propagates
- does not silently disappear
- does not rewrite professional lifecycle to `FAILED`
- does not invent `RUN_FAILED`
- does not remove already-created business artifacts

If `TOOL_CALL_STARTED` emission fails → tool is not executed. If `ARTIFACT_CREATED` emission fails after professional artifact creation → business artifact is not rewritten/removed.

------------------------------------------------------------
OUT-OF-SCOPE PRESERVED
------------------------------------------------------------

10.3C did **NOT** implement:

- `HUMAN_WAIT_STARTED`
- `HUMAN_DECISION_RECEIVED`
- `RUN_RESUMED`
- `REALITY_REFRESH_*`

→ belong to **10.3D**

10.3C did **NOT** implement:

- `HANDOFF_CREATED`
- `HANDOFF_PERSISTED`
- `HANDOFF_PERSIST_FAILED`
- `RUN_COMPLETED`

→ belong to **10.3E**

Also preserved: no Run Control duplication · no duplicate `STAGE_*` events beyond 10.3B ownership · no `revalidate_reality` instrumentation.

------------------------------------------------------------
WHAT THIS GIVES THE SYSTEM
------------------------------------------------------------

После 10.3C цифровой сотрудник оставляет структурированный след уже не только о том, какую профессиональную стадию он выполнял, но и каким разрешённым инструментом пользовался и какой структурированный бизнес-артефакт создал.

Control Room в будущем сможет показывать фактическую цепочку:

```
работа агента → стадия → инструмент → результат
```

…а не декоративные UI-статусы.

Conceptual chain now:

Run Control<br>
→ authorized runtime start boundary<br>
→ Runtime Instrumentation Foundation (10.3A)<br>
→ Core LangGraph Stage Wiring (10.3B)<br>
→ **Tool / Artifact Runtime Instrumentation (10.3C)** ← this checkpoint<br>
→ HITL / Resume / Reality Refresh instrumentation (10.3D)

Observability RECORDS execution truth. It does NOT become execution truth.

------------------------------------------------------------
PLACE IN OVERALL ARCHITECTURE
------------------------------------------------------------

Increment 10.3C sits between:

- **10.3B** Core LangGraph Stage Wiring (STAGE events)
- **10.3D** HITL / Resume / Reality Refresh Runtime Instrumentation

10.3C is thin runtime-boundary instrumentation only. Minimal mechanical lifecycle extraction for single-source reality read. No observability contract changes. No domain module changes.

------------------------------------------------------------
WHAT IS NOT DONE
------------------------------------------------------------

- NO `HUMAN_WAIT_STARTED` / `HUMAN_DECISION_RECEIVED` / `RUN_RESUMED` / `REALITY_REFRESH_*` (10.3D)
- NO `HANDOFF_CREATED` / `HANDOFF_PERSISTED` / `RUN_COMPLETED` terminal wiring (10.3E)
- NO labor/exception/handoff artifact observability
- NO `ConstructorManagedRuntimeLauncher`
- NO durable observability store (Increment 10.4)
- NO Query Port
- NO Control Room UI
- NO Supabase observability persistence
- Increment 10.3 overall is **NOT COMPLETE**
- Increment 10 overall is **NOT COMPLETE**

------------------------------------------------------------
TEST / RELEASE GATES
------------------------------------------------------------

Targeted 10.3C: **15 / 15 PASS**<br>
10.3B regression: **16 PASS**<br>
10.3A regression: **37 PASS**<br>
LangGraph runtime + handoff: **45 PASS**<br>
Lifecycle regression: **52 PASS**<br>
Constructor standard gate: **397 / 397 PASS**<br>
Observability + Run Control + EOS-SEC combined: **155 / 155 PASS**

**FULL POSTGRES DURABLE RESTART SUITE:** **ENVIRONMENT_BLOCKED**<br>
This is **NOT** classified as a 10.3C regression. Do **not** claim full postgres integration PASS.

------------------------------------------------------------
COMMITS
------------------------------------------------------------

CODE COMMIT:

- `719178c63434a8a822ecd65dd16e7f4824058be4`
- message: `feat(agents): instrument constructor tool and artifact runtime`

BRANCH: `wip/increment-10-agent-control-room`

PUSH: **SUCCESS**<br>
LOCAL == UPSTREAM: **YES**<br>
WORKTREE: **CLEAN**

------------------------------------------------------------
FILES
------------------------------------------------------------

Product:

- `agents/monthly_plan_constructor/lifecycle.py`
- `agents/monthly_plan_constructor/langgraph_runtime.py`

Tests:

- `tests/test_constructor_langgraph_stage_instrumentation.py` (compatibility fix)
- `tests/test_constructor_langgraph_tool_artifact_instrumentation.py`

FILE COUNT IN CODE COMMIT: **4**

NON-10.3C FILES IN COMMIT: **NO**

NEW DEPENDENCIES: **NONE**

**Not modified:** `runtime_instrumentation.py`, observability contracts/recorder, Run Control, domain modules, HITL/handoff modules.

------------------------------------------------------------
WHERE WE ARE IN THE AGENT ROADMAP
------------------------------------------------------------

Constructor Agent Runtime v0.1:

[1]–[9] — **DONE**<br>
[10] Agent Control Room / Observability — **IN PROGRESS**

Increment 10 decomposition:

- 10.0 — Architecture Discovery — **DONE**
- 10.A0 — WIP branch prep — **DONE**
- 10.A1 — Formal Architecture Spec — **DONE**
- 10.1 — Agent-Neutral Observability Foundation — **DONE**
- 10.2 — Run Control — **DONE**
- 10.3A — Runtime Instrumentation Foundation — **DONE**
- 10.3B — Core LangGraph Stage Wiring — **DONE**
- 10.3C — Tool / Artifact Runtime Instrumentation — **DONE** (this checkpoint)
- 10.3D — HITL / Resume / Reality Refresh Runtime Instrumentation — **NEXT / NOT STARTED**
- 10.3E — Handoff / Completion Runtime Instrumentation — **NOT STARTED**
- 10.4 — Durable Observability Store — **NOT STARTED**

Progress: **9 / 10** (Increment 10 overall not complete; do not claim 10 / 10)

------------------------------------------------------------
ONE-LINE SUMMARY
------------------------------------------------------------

На этом этапе Execution OS добавил к Constructor LangGraph runtime структурированную observability вокруг одного профессионального EOS-SEC инструмента (`load_constructor_scope`) и двух бизнес-артефактов (`ConstructorRealityRead`, `CandidatePackage`) — с single-source reality-read lifecycle extraction и без изобретения синтетических artifact identity.

------------------------------------------------------------
NEXT
------------------------------------------------------------

Increment 10.3D — HITL / Resume / Reality Refresh Runtime Instrumentation.

Expected scope (brief only — not designed here):

10.3D will instrument the runtime lifecycle around:

```
agent waits for human
→ human decision arrives
→ runtime resumes
→ current reality is refreshed/revalidated
→ professional work continues
```

Expected events (deferred): `HUMAN_WAIT_STARTED`, `HUMAN_DECISION_RECEIVED`, `RUN_RESUMED`, `REALITY_REFRESH_*`.

Increment 10.3D **не** реализован в этом checkpoint.

---

============================================================
CHECKPOINT — 2026-09-02 — CONSTRUCTOR AGENT — INCREMENT 10.3D
HITL / RESUME / REALITY REFRESH RUNTIME INSTRUMENTATION
============================================================

PROGRAM:
Monthly Planning Agentic Orchestration

CURRENT AGENT:
MONTHLY_PLAN_CONSTRUCTOR

CURRENT INCREMENT:
[10.3D] HITL / Resume / Reality Refresh Runtime Instrumentation

STATUS:
DONE

------------------------------------------------------------
WHAT WE BUILT
------------------------------------------------------------

Increment 10.3D made the existing durable HITL lifecycle observable without redesigning professional HITL logic.

Architecture law preserved: **Python function call ≠ tool call** · **Skill ≠ tool** · **Observability RECORDS execution truth; it does NOT become execution truth.**

**Observed lifecycle chain (10.3D):**

```
professional stage
→ WAITING_FOR_HUMAN
→ HUMAN_WAIT_STARTED
→ interrupt
→ HUMAN_DECISION_RECEIVED
→ apply human decision
→ RUN_RESUMED
→ REVALIDATING_REALITY
→ REALITY_REFRESH_STARTED
→ secure fresh read
→ REALITY_REFRESH_COMPLETED
→ fresh snapshot artifact
→ professional execution continues
```

10.3D did **NOT** change `hitl_resume.py`, `hitl_contracts.py`, `lifecycle.py`, observability contracts, or Run Control. Instrumentation lives in `langgraph_runtime.py` at the HITL boundary only.

When `recorder=None`, original professional paths are preserved unchanged.

------------------------------------------------------------
HUMAN WAIT
------------------------------------------------------------

**`WAITING_FOR_HUMAN` is NOT failure.**

The professional stage still completes correctly and routes to a human decision gate.

**`HUMAN_WAIT_STARTED` means:** the digital employee reached a real Human Decision Gate and intentionally paused execution.

Цифровой сотрудник достиг реальной точки решения человека и намеренно приостановил исполнение.

If `HUMAN_WAIT_STARTED` emission fails → `interrupt()` is not called (fail-closed).

------------------------------------------------------------
HUMAN DECISION VS RESUME
------------------------------------------------------------

**`HUMAN_DECISION_RECEIVED` ≠ `RUN_RESUMED`**

| Event | Meaning |
|-------|---------|
| `HUMAN_DECISION_RECEIVED` | A valid human resume/decision command was actually received and passed required validation |
| `RUN_RESUMED` | The decision was successfully applied and professional execution actually resumed |

For **ABORT_RUN:**

| Event | Emitted |
|-------|---------|
| `HUMAN_DECISION_RECEIVED` | **YES** |
| `RUN_RESUMED` | **NO** |
| `REALITY_REFRESH_*` | **NO** |

Professional `FAILED` remains authoritative. Observability does not rewrite lifecycle outcome.

If `HUMAN_DECISION_RECEIVED` emission fails → resume command is not applied (fail-closed).

------------------------------------------------------------
FRESH REALITY LAW
------------------------------------------------------------

**Runtime law:** After human resume, the digital employee must **NOT** continue from stale reality.

После решения человека цифровой сотрудник **НЕ** должен продолжать работу на устаревшей реальности.

Required chain:

```
resume
→ REVALIDATING_REALITY
→ fresh secure read
→ new reality snapshot
→ continued professional execution
```

This is a core distinction between a **durable digital employee** and a simple **automation script**.

`RUN_RESUMED` is emitted only when the applied decision yields `REVALIDATING_REALITY`.

------------------------------------------------------------
POST-HITL TOOL OBSERVABILITY
------------------------------------------------------------

10.3D owns post-HITL secure-read tool observability under **`REALITY_REVALIDATION`**.

Same professional EOS-SEC tool as initial read:

| Constant | Tool name | Node | Stage |
|----------|-----------|------|-------|
| `TOOL_LOAD_SCOPE` | `load_constructor_scope` | `revalidate_reality` | `REALITY_REVALIDATION` |

Events:

- `TOOL_CALL_STARTED`
- `TOOL_CALL_COMPLETED`
- `TOOL_CALL_DENIED`

Failure distinction within `TOOL_CALL_DENIED`:

| Failure class | Event | EventStatus |
|---------------|-------|-------------|
| Security denial | `TOOL_CALL_DENIED` | `DENIED` |
| Controlled read / tool failure | `TOOL_CALL_DENIED` | `FAILED` |

This is **distinct** from initial `REALITY_READ` in 10.3C.

If `REALITY_REFRESH_STARTED` or `TOOL_CALL_STARTED` emission fails → fresh read is not executed (fail-closed).

------------------------------------------------------------
REFRESH SNAPSHOT ARTIFACT
------------------------------------------------------------

A successful fresh reality read creates a new `ConstructorRealityRead`.

- `ARTIFACT_CREATED` is emitted only for a genuinely new stable `read_id`
- No synthetic artifact IDs
- Safe metadata only
- No raw rows · No DataFrames · No full business payload · No secrets

If `ARTIFACT_CREATED` emission fails after professional artifact creation → business artifact is not rewritten/removed (unchanged 10.3B/10.3C policy).

------------------------------------------------------------
MULTI-WAIT IDENTITY
------------------------------------------------------------

**Same-wait replay:**

| Property | Value |
|----------|-------|
| Semantic key | `wait-1` |
| Replay behavior | **IDEMPOTENT_REPLAY** |

**Multiple real waits in one run:**

| Wait episode | `wait_ordinal` | Semantic key |
|--------------|----------------|--------------|
| First real wait | 1 | `wait-1` |
| Second real wait | 2 | `wait-2` |

Distinct across episodes: `interrupt_id`, `event_id`, `resume_n`.

This proves checkpoint replay of the same wait is **NOT** confused with a genuinely new Human Gate episode.

**Proof tests:**

- `test_wait_replay_is_idempotent`
- `test_multiple_real_waits_get_distinct_wait_identity` — proved two real waits inside the same run

Production code change required for multi-wait proof: **NO**<br>
Runtime bug found: **NO**

------------------------------------------------------------
10.3B TEST COMPATIBILITY FIX
------------------------------------------------------------

`tests/test_constructor_langgraph_stage_instrumentation.py` received a justified compatibility correction.

Pre-resume assertion now filters `event.stage_id in CORE_STAGES`.

Reason: HITL uses `HUMAN_GATE`, which is not in core stages. HITL wait events belong to 10.3D, not 10.3B.

| Check | Result |
|-------|--------|
| Assertions removed | **NO** |
| Tests disabled | **NO** |
| Expected stage semantics weakened | **NO** |

------------------------------------------------------------
RECORDER FAILURE POLICY
------------------------------------------------------------

Existing fail-closed policy (unchanged from 10.3B/10.3C):

- Recorder failure **propagates**
- Does **NOT** silently swallow
- Does **NOT** rewrite professional lifecycle to `FAILED`
- Does **NOT** invent `RUN_FAILED`
- Does **NOT** remove already-created business artifacts

Specific 10.3D gates:

| Failure point | Consequence |
|---------------|-------------|
| `HUMAN_WAIT_STARTED` emission fails | `interrupt()` not called |
| `HUMAN_DECISION_RECEIVED` emission fails | Resume command not applied |
| `REALITY_REFRESH_STARTED` / `TOOL_CALL_STARTED` emission fails | Fresh read not executed |

------------------------------------------------------------
DATA MINIMIZATION
------------------------------------------------------------

Human decisions are sensitive. Allowed safe metadata includes:

- `decision_id`
- `decision_type`
- `actor_type`
- `actor_id`
- `interrupt_id`
- `checkpoint_id`
- `reason_code`
- `wait_ordinal`
- `route`
- `severity`
- `status` / error codes

Do **NOT** log:

- human free-text comment
- parameters mapping
- scope body
- full interrupt payload
- raw reality rows
- evidence bodies
- credentials
- tokens
- `AgentExecutionContext`

No secret leakage / Никаких утечек секретов.

------------------------------------------------------------
WHAT THIS GIVES THE SYSTEM
------------------------------------------------------------

После 10.3D цифровой сотрудник стал наблюдаемым не только во время обычного исполнения, но и в критическом цикле взаимодействия с человеком.

Теперь можно доказуемо увидеть:

```
агент столкнулся с исключением
→ остановился
→ запросил решение человека
→ получил решение
→ действительно возобновил работу
→ перечитал актуальную реальность
→ продолжил профессиональное исполнение
```

Это отличает **durable digital employee** / **долговечного цифрового сотрудника** от **one-time automation script** / **скрипта автоматизации**.

Conceptual chain now:

Run Control<br>
→ authorized runtime start boundary<br>
→ Runtime Instrumentation Foundation (10.3A)<br>
→ Core LangGraph Stage Wiring (10.3B)<br>
→ Tool / Artifact Runtime Instrumentation (10.3C)<br>
→ **HITL / Resume / Reality Refresh Runtime Instrumentation (10.3D)** ← this checkpoint<br>
→ Handoff / Completion Runtime Instrumentation (10.3E)

------------------------------------------------------------
PLACE IN OVERALL ARCHITECTURE
------------------------------------------------------------

Increment 10.3D sits between:

- **10.3C** Tool / Artifact Runtime Instrumentation (initial `REALITY_READ`, `CANDIDATE_ASSEMBLY`)
- **10.3E** Handoff / Completion Runtime Instrumentation

10.3D is thin runtime-boundary instrumentation only. No observability contract changes. No HITL professional logic changes.

------------------------------------------------------------
WHAT IS NOT DONE
------------------------------------------------------------

- NO `HANDOFF_CREATED` / `HANDOFF_PERSISTED` / `HANDOFF_PERSIST_FAILED` / `RUN_COMPLETED` (10.3E)
- NO labor/exception/handoff artifact observability
- NO `ConstructorManagedRuntimeLauncher`
- NO durable observability store (Increment 10.4)
- NO Query Port
- NO Control Room UI
- NO Supabase observability persistence
- Increment 10.3 overall is **NOT COMPLETE**
- Increment 10 overall is **NOT COMPLETE**

------------------------------------------------------------
TEST / RELEASE GATES
------------------------------------------------------------

Targeted 10.3D: **16 / 16 PASS**<br>
10.3B stage regression: **16 / 16 PASS**<br>
Constructor standard gate: **412 / 412 PASS**<br>
Observability + Run Control + EOS-SEC combined: **155 / 155 PASS**

**FULL POSTGRES DURABLE RESTART SUITE:** **ENVIRONMENT_BLOCKED**<br>
This is **NOT** classified as a 10.3D regression. Do **not** claim full postgres integration PASS.

------------------------------------------------------------
COMMITS
------------------------------------------------------------

CODE COMMIT:

- `0060e6509a036c77c8ff03d569a1727f82e4ded6`
- message: `feat(agents): instrument constructor hitl resume observability`

BRANCH: `wip/increment-10-agent-control-room`

PUSH: **SUCCESS**<br>
LOCAL == UPSTREAM: **YES**<br>
WORKTREE: **CLEAN**

------------------------------------------------------------
FILES
------------------------------------------------------------

Product:

- `agents/monthly_plan_constructor/langgraph_runtime.py`

Tests:

- `tests/test_constructor_langgraph_hitl_observability.py` (new)
- `tests/test_constructor_langgraph_stage_instrumentation.py` (compatibility fix)

FILE COUNT IN CODE COMMIT: **3**

NON-10.3D FILES IN COMMIT: **NO**

NEW DEPENDENCIES: **NONE**

**Not modified:** `hitl_resume.py`, `hitl_contracts.py`, `lifecycle.py`, observability contracts/recorder, Run Control, domain modules, handoff modules.

------------------------------------------------------------
WHERE WE ARE IN THE AGENT ROADMAP
------------------------------------------------------------

Constructor Agent Runtime v0.1:

[1]–[9] — **DONE**<br>
[10] Agent Control Room / Observability — **IN PROGRESS**

Increment 10 decomposition:

- 10.0 — Architecture Discovery — **DONE**
- 10.A0 — WIP branch prep — **DONE**
- 10.A1 — Formal Architecture Spec — **DONE**
- 10.1 — Agent-Neutral Observability Foundation — **DONE**
- 10.2 — Run Control — **DONE**
- 10.3A — Runtime Instrumentation Foundation — **DONE**
- 10.3B — Core LangGraph Stage Wiring — **DONE**
- 10.3C — Tool / Artifact Runtime Instrumentation — **DONE**
- 10.3D — HITL / Resume / Reality Refresh Runtime Instrumentation — **DONE** (this checkpoint)
- 10.3E — Handoff / Completion Runtime Instrumentation — **NEXT / NOT STARTED**
- 10.4 — Durable Observability Store — **NOT STARTED**

Progress: **9 / 10** (Increment 10 overall not complete; do not claim 10 / 10)

------------------------------------------------------------
ONE-LINE SUMMARY
------------------------------------------------------------

На этом этапе Execution OS добавил к Constructor LangGraph runtime структурированную observability вокруг durable HITL lifecycle — human wait, human decision, run resume, post-HITL reality refresh и fresh snapshot artifact — с доказанной multi-wait identity и без изменения профессиональной HITL-логики.

------------------------------------------------------------
NEXT
------------------------------------------------------------

Increment 10.3E — Handoff / Completion Runtime Instrumentation.

Expected scope (brief only — not designed here):

10.3E will instrument:

```
handoff artifact creation
→ handoff persistence
→ persistence failure if any
→ successful completion of Constructor run
```

Expected events (deferred): `HANDOFF_CREATED`, `HANDOFF_PERSISTED`, `HANDOFF_PERSIST_FAILED`, `RUN_COMPLETED`.

Increment 10.3E **не** реализован в этом checkpoint.

---

============================================================
CHECKPOINT — 2026-09-02 — CONSTRUCTOR AGENT — INCREMENT 10.3E
HANDOFF / COMPLETION RUNTIME INSTRUMENTATION
============================================================

PROGRAM: Monthly Planning Agentic Orchestration · CURRENT AGENT: MONTHLY_PLAN_CONSTRUCTOR · STATUS: **DONE**

Increment 10.3E completed the Constructor managed completion observability chain. **10.3A–E Runtime Instrumentation is DONE.** Increment 10 overall is **NOT COMPLETE**. Constructor progress remains **9 / 10** — do **not** claim 10 / 10.

------------------------------------------------------------
MANAGED COMPLETION CHAIN
------------------------------------------------------------

```
READY_FOR_HANDOFF
→ HANDOFF_CREATED
→ HANDOFF_PERSISTED
→ RUN_COMPLETED
```

**Law:** `READY_FOR_HANDOFF` ≠ `RUN_COMPLETED`.

| Status / Event | Meaning |
|----------------|---------|
| `READY_FOR_HANDOFF` | Professional result is ready for transfer — eligibility only |
| `HANDOFF_CREATED` | Valid `ConstructorHandoff` built with deterministic `handoff_id` — **not** persistence success |
| `HANDOFF_PERSISTED` | Persistence boundary accepted handoff as `CREATED` or `IDEMPOTENT_REPLAY` |
| `HANDOFF_PERSIST_FAILED` | Actual persistence/store operation failed |
| `RUN_COMPLETED` | Managed completion — only after `HANDOFF_PERSISTED` successfully recorded |

Legacy path (`handoff_store=None`): ends at `READY_FOR_HANDOFF` — **no** `RUN_COMPLETED`.

------------------------------------------------------------
HANDOFF RECIPIENT (unchanged contract)
------------------------------------------------------------

| Field | Value |
|-------|-------|
| `handoff_type` | `CONSTRUCTOR_TO_ADMISSION` |
| `source_agent` | `MONTHLY_PLAN_CONSTRUCTOR` |
| `target_role` | `MONTHLY_PLAN_ADMISSION_AGENT` |

Constructor transfers a structured professional result to the next digital role — not a local finish. Admission Agent consumption is **not** implemented yet.

------------------------------------------------------------
ARTIFACT OWNERSHIP
------------------------------------------------------------

**`ConstructorHandoff` does NOT emit `ARTIFACT_CREATED`.** Dedicated ownership: `HANDOFF_*` events only. Reason: avoid duplicate semantic representation of the same `handoff_id`.

------------------------------------------------------------
IDENTITY & REPLAY
------------------------------------------------------------

`handoff_id` is deterministic from `source_run_id` + `package_id` + `snapshot_id` + accepted contract coordinates. No synthetic observability UUID. Same semantic handoff replay → same `handoff_id` → **`IDEMPOTENT_REPLAY`**. Different package/snapshot → different handoff identity.

------------------------------------------------------------
BUSINESS TRUTH FIRST
------------------------------------------------------------

**Business truth > Telemetry.**

If persistence fails and recorder also fails while recording `HANDOFF_PERSIST_FAILED`: the **original persistence/store exception** remains the primary business failure; recorder failure stays chained/contextual. Business truth must **not** be erased by telemetry failure.

If persistence **already succeeded** but recorder fails on `HANDOFF_PERSISTED`: handoff remains persisted — do **not** rollback; do **not** emit `HANDOFF_PERSIST_FAILED`; do **not** emit `RUN_COMPLETED`; recorder failure propagates.

Recorder failure must **never** masquerade as persistence failure.

------------------------------------------------------------
FAILURE SEMANTICS (summary)
------------------------------------------------------------

| Case | Events |
|------|--------|
| Handoff build failure | No handoff events · no `RUN_COMPLETED` |
| Persistence failure | `HANDOFF_CREATED` · `HANDOFF_PERSIST_FAILED` · no `RUN_COMPLETED` |
| Recorder failure | Never `HANDOFF_PERSIST_FAILED` |
| ABORT / WAIT / FAILED | No `RUN_COMPLETED` |
| `handoff_store=None` | No `RUN_COMPLETED` |

------------------------------------------------------------
DATA MINIMIZATION
------------------------------------------------------------

Safe metadata only: `handoff_id`, `package_id`, `snapshot_id`, `schema_version`, `source_agent`, `target_role`, `persistence_status`, `payload_digest`, bounded summaries. No full handoff body · no candidate arrays · no scope body · no credentials · no tokens · no `AgentExecutionContext`. No secret leakage.

------------------------------------------------------------
FULL 10.3A–E RUNTIME TRACE
------------------------------------------------------------

Constructor now has an almost end-to-end observable runtime trace:

```
RUN → STAGE → TOOL → ARTIFACT
→ HUMAN WAIT → HUMAN DECISION → RUN RESUME → REALITY REFRESH
→ HANDOFF CREATED → HANDOFF PERSISTED → RUN COMPLETED
```

После завершения 10.3A–E цифровой сотрудник оставляет структурированный след практически по всему своему runtime-жизненному циклу: что делал, каким инструментом пользовался, какой результат создавал, когда остановился для решения человека, как возобновился, как перечитал актуальную реальность, как сформировал передачу следующей роли и когда действительно завершил свою ответственность.

Observability **RECORDS** execution truth. It does **NOT** become execution truth.

------------------------------------------------------------
TEST / RELEASE GATES
------------------------------------------------------------

Targeted 10.3E: **18 / 18 PASS** · 10.3A–D + handoff regression: **99 / 99 PASS** · Broader accepted gate: **566 PASS** · Failure-chain: **PASS** · Original persistence failure preserved: **YES** · Recorder failure chained: **YES**

Postgres durable restart: **ENVIRONMENT_BLOCKED** — not a 10.3E regression.

------------------------------------------------------------
COMMITS
------------------------------------------------------------

CODE: `1b7003ee067c94bbb6b75f9aa4fa16740d6f2f7f` · message: `feat(agents): instrument constructor handoff completion observability` · BRANCH: `wip/increment-10-agent-control-room` · PUSH: **SUCCESS** · LOCAL == UPSTREAM: **YES**

FILES (2): `langgraph_runtime.py` · `test_constructor_langgraph_handoff_observability.py` · NON-10.3E FILES: **NO**

**Not modified:** handoff contracts/store, lifecycle, observability contracts, Run Control, HITL modules.

------------------------------------------------------------
REMAINING INCREMENT 10 SCOPE
------------------------------------------------------------

| Item | Status |
|------|--------|
| 10.4 Durable Observability Store | **NOT STARTED** |
| Query Port | **NOT STARTED** |
| Control Room UI | **NOT STARTED** |
| `ConstructorManagedRuntimeLauncher` | **NOT STARTED** |
| Supabase observability persistence | **NOT STARTED** |
| Labor / exception artifact observability | Not yet formally completed — separate decision required |

Increment 10: **NOT COMPLETE** · Constructor: **9 / 10**

------------------------------------------------------------
NEXT
------------------------------------------------------------

**Architecture sequencing review** for remaining Increment 10 scope. Do **not** automatically set NEXT = Control Room UI. Decide correct dependency order between Durable Observability Store · Query Port · Managed Runtime Launcher · Supabase persistence · Control Room UI **before** implementation. Do **not** start 10.4 in this checkpoint.

------------------------------------------------------------
PROFESSIONAL PASSPORT REMINDER
------------------------------------------------------------

After Constructor reaches full completion, create **Constructor Professional Passport v1.0** / **Профессиональный паспорт Constructor v1.0**. **Not** part of this checkpoint. Do **not** create the passport now.

---

============================================================
CHECKPOINT — 2026-09-02
OPERATIONAL TRUTH FIX
/ ЗАКРЫТИЕ МОДЕЛИ ОПЕРАЦИОННОЙ ИСТИНЫ
============================================================

PROGRAM: Monthly Planning Agentic Orchestration · CURRENT AGENT: MONTHLY_PLAN_CONSTRUCTOR · STATUS: **DONE** (documentation + code)

**Purpose:** close AgentRun operational status truth gaps that blocked Increment 10.4 Durable Observability Store. **10.4 is NOT implemented in this checkpoint.**

------------------------------------------------------------
WHY THIS FIX WAS REQUIRED
------------------------------------------------------------

Before this fix, `AgentRun` operational truth was **not fully reconstructable** from immutable events:

- Run Control silently set `RUNNING` in memory after `launcher.launch()`
- no authoritative event represented `STARTING → RUNNING`
- `WAITING_FOR_HUMAN → RUNNING` had no explicit projection law
- terminal FAILED paths did not consistently emit `RUN_FAILED`
- human `ABORT_RUN` did not emit `RUN_ABORTED`

Therefore Durable Observability Store 10.4 was correctly **BLOCKED**.

------------------------------------------------------------
CORE ARCHITECTURE LAW
------------------------------------------------------------

**Projection must NEVER invent operational truth.**

- **Event log** = authoritative operational history
- **Projection** = materialized read/control state derived from accepted events
- No hidden process-local status may be treated as durable truth

------------------------------------------------------------
THREE PLANES / ТРИ ПЛОСКОСТИ
------------------------------------------------------------

| Plane | Scope |
|-------|-------|
| **Control plane** | request · authorization · mission binding · launch acceptance |
| **Runtime plane** | actual advancing · waiting · resume · runtime failure · abort · completion |
| **Professional plane** | Constructor lifecycle · candidate package · exceptions · labor norms · handoff readiness · professional failure/status |

These planes interact but must **not** be collapsed into one state model.

------------------------------------------------------------
RUNNING TRUTH LAW
------------------------------------------------------------

| Event / action | Operational meaning |
|----------------|---------------------|
| `RUN_STARTED` | Run Control initiating runtime handoff; `operational_status` remains **STARTING** |
| `launcher.launch()` success | accept/schedule only — **NOT RUNNING** |
| Run Control post-launch result | **STARTING** |
| `RUN_ADVANCING` | actual **RUNNING** — runtime-owned only |

------------------------------------------------------------
RUN_ADVANCING
------------------------------------------------------------

| Field | Value |
|-------|-------|
| **EventType** | `RUN_ADVANCING` (new) |
| **Owner** | Runtime / runtime instrumentation |
| **Meaning** | The authorized professional runtime has actually begun execution / Авторизованный профессиональный runtime фактически начал исполнение |
| **Emission seam** | actual entry into `bind_mission` graph node, **before** existing professional `_advance` logic |
| **NOT** | before `app.invoke` · launcher return · `STAGE_STARTED` inference |
| **Projection** | `RUN_ADVANCING → RUNNING` · `started_at` set on initial advancing event |
| **Identity** | `semantic_occurrence_key="start"`, `attempt_n=1`, `resume_n=0` · one per managed run · no second on HITL resume |

------------------------------------------------------------
LAUNCHER SEMANTICS
------------------------------------------------------------

`ManagedRuntimeLauncher.launch(...)` = accept/schedule authorized runtime execution in a decoupled execution context.

**NOT:** whole graph execution · proof of RUNNING · proof of completion.

`ConstructorManagedRuntimeLauncher` itself: **NOT IMPLEMENTED**.

------------------------------------------------------------
WAITING / RESUME TRUTH
------------------------------------------------------------

| Event | Projection |
|-------|------------|
| `HUMAN_WAIT_STARTED` | `WAITING_FOR_HUMAN` |
| `RUN_RESUMED` | `RUNNING` |

`RUN_RESUMED` is authoritative only after: human decision validated · resume command applied · `ABORT_RUN` excluded · runtime continues into reality revalidation.

No second `RUN_ADVANCING` on resume. `started_at` unchanged.

------------------------------------------------------------
ABORT TRUTH
------------------------------------------------------------

Human `ABORT_RUN`: `HUMAN_DECISION_RECEIVED` → abort validated/applied → `RUN_ABORTED`.

| Projection | |
|------------|--|
| `RUN_ABORTED` | `ABORTED` · `completed_at` set |

**Does NOT emit:** `RUN_RESUMED` · `RUN_FAILED`.

Professional lifecycle may still use `STATUS_FAILED` + `CODE_RUN_ABORTED_BY_HUMAN`. Operational **ABORTED** ≠ professional generic **FAILED**.

------------------------------------------------------------
FAILED TRUTH
------------------------------------------------------------

`RUN_FAILED` = Constructor professional/runtime responsibility ended in a **known terminal failure** that is **not** controlled human abort.

**Wired terminal paths:** (A) stage terminal lifecycle failure · (B) `bind_mission` terminal failure · (C) revalidation terminal failure · (D) handoff persistence terminal failure.

**Do NOT emit for:** observability failure · launcher outcome unknown · control-plane failure · `WAITING_FOR_HUMAN` · `ABORT_RUN` · generic `app.invoke` exception with unknown outcome.

**Plane separation:** `STAGE_FAILED` = stage fact · `RUN_FAILED` = terminal run fact. For terminal stage failure: `STAGE_FAILED → RUN_FAILED`. For non-terminal WAIT/recoverable route: `RUN_FAILED` only if lifecycle truly terminates `FAILED`.

------------------------------------------------------------
HANDOFF FAILURE CHAIN
------------------------------------------------------------

```
HANDOFF_CREATED → persistence attempt → HANDOFF_PERSIST_FAILED → RUN_FAILED → no RUN_COMPLETED → original persistence exception re-raised
```

**Business truth first / Бизнес-истина первична.** If recorder fails while recording `RUN_FAILED`: original persistence/store exception remains primary; recorder failure stays chained. Telemetry must not erase business failure.

------------------------------------------------------------
GENERIC EXCEPTION LAW
------------------------------------------------------------

Generic `app.invoke` exception does **NOT** automatically emit `RUN_FAILED`. Exception may represent observability failure · contract bug · infrastructure issue · unknown professional outcome.

------------------------------------------------------------
RETRYING · NON-PROJECTED OUTCOMES
------------------------------------------------------------

| Item | Status |
|------|--------|
| `OperationalStatus.RETRYING` | **DEFERRED** — executable retry path not wired; not blocking 10.4 |
| `LAUNCH_OUTCOME_UNKNOWN` · `CONTROL_PLANE_FAILURE` · `OBSERVABILITY_UNAVAILABLE` | **NOT** `AgentRun` operational statuses — control-plane/local failure outcomes; must **not** project to `FAILED` |

------------------------------------------------------------
FINAL OPERATIONAL TRUTH TABLE
------------------------------------------------------------

| Event | Operational status |
|-------|-------------------|
| `RUN_REQUESTED` | `REQUESTED` |
| `RUN_AUTHORIZATION_STARTED` / `RUN_AUTHORIZED` | `AUTHORIZING` |
| `RUN_DENIED` | `AUTHORIZATION_DENIED` |
| `MISSION_BOUND` / `RUN_STARTED` | `STARTING` |
| `RUN_ADVANCING` | `RUNNING` |
| `HUMAN_WAIT_STARTED` | `WAITING_FOR_HUMAN` |
| `RUN_RESUMED` | `RUNNING` |
| `RUN_FAILED` | `FAILED` |
| `RUN_ABORTED` | `ABORTED` |
| `RUN_COMPLETED` | `COMPLETED` |
| `RETRYING` | **DEFERRED** |

------------------------------------------------------------
TEST / RELEASE GATES
------------------------------------------------------------

Targeted operational truth: **19 / 19 PASS** · Constructor standard: **116 / 116 PASS** · Observability + Run Control + EOS-SEC: **315 / 315 PASS** · Architecture drift: **NO**

------------------------------------------------------------
COMMITS
------------------------------------------------------------

CODE: `edab8d9d80531b1ab58d13864042fe1506538163` · message: `fix(agents): close constructor operational status truth gaps` · BRANCH: `wip/increment-10-agent-control-room` · PUSH: **SUCCESS** · LOCAL == UPSTREAM: **YES** · WORKTREE: **CLEAN**

FILES (10): `agents/observability/contracts.py` · `agents/run_control/contracts.py` · `agents/run_control/service.py` · `agents/monthly_plan_constructor/runtime_instrumentation.py` · `agents/monthly_plan_constructor/langgraph_runtime.py` · `tests/test_run_control_service.py` · `tests/test_agent_observability_contracts.py` · `tests/test_constructor_langgraph_hitl_observability.py` · `tests/test_constructor_langgraph_handoff_observability.py` · `tests/test_constructor_langgraph_operational_truth.py`

------------------------------------------------------------
10.4 STATUS
------------------------------------------------------------

| Item | Status |
|------|--------|
| Increment 10.4 Durable Observability Store | **NOT IMPLEMENTED** |
| Architecture blocker | **RESOLVED** |

10.4 is architecturally **UNBLOCKED** because: `RUNNING` has authoritative runtime-owned event · WAITING exit has `RUN_RESUMED` mapping · terminal FAILED paths emit `RUN_FAILED` · human abort emits `RUN_ABORTED` · Run Control no longer silently creates `RUNNING` · projection engine no longer needs state inference.

------------------------------------------------------------
NEXT
------------------------------------------------------------

Return to **Increment 10.4 Durable Observability Store**. Before implementation: revalidate 10.4 preflight assumptions against this Operational Truth Fix. Update 10.4 design only where event/projection assumptions changed. Do **not** repeat the entire historical investigation.

Increment 10: **NOT COMPLETE** · Constructor: **9 / 10**

---

============================================================
CHECKPOINT — 2026-09-02
INCREMENT 10.4
DURABLE OBSERVABILITY STORE
============================================================

PROGRAM: Monthly Planning Agentic Orchestration · CURRENT AGENT: MONTHLY_PLAN_CONSTRUCTOR · STATUS: **DONE**

**Purpose:** agent-neutral durable observability infrastructure behind the accepted `ObservabilityRecorder` interface. **10.5 is NOT implemented in this checkpoint.**

------------------------------------------------------------
DELIVERABLES
------------------------------------------------------------

Agent-neutral infrastructure (reusable by future digital employees):

| Component | Role |
|-----------|------|
| `ObservabilityStore` | Agent-neutral durable port |
| `InMemoryObservabilityStore` | Contract test double with full store semantics |
| `SqliteObservabilityStore` | File-backed SQLite durable backend |
| `StoreObservabilityRecorder` | Durable adapter implementing existing `ObservabilityRecorder` |
| `AgentRunProjectionChange` | Constrained typed projection delta |
| `project_agent_run_event(...)` | Pure EventType-driven projection engine |

No Constructor-specific store.

------------------------------------------------------------
ATOMICITY LAW
------------------------------------------------------------

```
EVENT_ACCEPTED  ⇔  AGENT_RUN_PROJECTION_UPDATED_TO_MATCH
```

For **NEW** events: event append + projection update + `projection_version` increment = **one atomic durable operation**. Any failure: **neither** event nor projection commits. No standalone authoritative event append without matching projection update for projected Class A truth.

------------------------------------------------------------
REPLAY-BEFORE-CAS LAW
------------------------------------------------------------

Frozen durable ordering inside store transaction:

1. Validate event · 2. Compute fingerprint · 3. Look up `event_id` **first**

| Case | Result |
|------|--------|
| Same `event_id` + same fingerprint | `IDEMPOTENT_REPLAY` — no CAS · no projection mutation · no version increment (even if later events advanced version) |
| Same `event_id` + different fingerprint | Fail-closed conflict |
| **New** `event_id` only | CAS on `expected_projection_version` · append · project · `projection_version += 1` |

------------------------------------------------------------
PROJECTION VERSION LAW
------------------------------------------------------------

| Case | `projection_version` |
|------|---------------------|
| `create_run` | Initial accepted value (normally `0`) |
| NEW accepted event | `+1` exactly once |
| `IDEMPOTENT_REPLAY` | Unchanged |
| Fingerprint conflict | Unchanged |
| CAS conflict | No write |

No last-write-wins.

------------------------------------------------------------
OPERATIONAL TRUTH (IMPLEMENTED PROJECTION)
------------------------------------------------------------

| Event | `operational_status` | Notes |
|-------|---------------------|-------|
| `RUN_REQUESTED` | `REQUESTED` | |
| `RUN_AUTHORIZATION_STARTED` / `RUN_AUTHORIZED` | `AUTHORIZING` | Structured auth refs only |
| `RUN_DENIED` | `AUTHORIZATION_DENIED` | `completed_at` |
| `MISSION_BOUND` / `RUN_STARTED` | `STARTING` | Launcher return ≠ RUNNING |
| `RUN_ADVANCING` | `RUNNING` | Runtime-owned; sets `started_at` if unset |
| `HUMAN_WAIT_STARTED` | `WAITING_FOR_HUMAN` | |
| `RUN_RESUMED` | `RUNNING` | `started_at` preserved; no second `RUN_ADVANCING` |
| `RUN_FAILED` | `FAILED` | `completed_at`; no free-form `detail.error_code` promotion |
| `RUN_ABORTED` | `ABORTED` | `completed_at`; ≠ `RUN_FAILED` |
| `RUN_COMPLETED` | `COMPLETED` | `completed_at` |

Conservative: no inference from `STAGE_*`, `TOOL_*`, `ARTIFACT_*`, `HANDOFF_*`, `REALITY_REFRESH_*`, titles, node names, or free-form detail.

------------------------------------------------------------
UNKNOWN RUN · CREATE_RUN · ORDERING · READS · SECURITY
------------------------------------------------------------

- **Unknown run:** `StoreObservabilityRecorder` fail-closed for unknown `run_id` — no auto-create; bootstrap belongs to Run Control
- **create_run:** Immutable identity comparison only; same identity = idempotent ack; different identity = fail-closed
- **Ordering:** Internal `append_sequence` (not `occurred_at` alone); replay creates no new sequence
- **Bounded reads:** `list_events` / `list_runs` are storage-oriented bounded reads — **not** Control Room read models (10.6 Query Port)
- **EOS-SEC:** Typed contracts only; pre-write serialization + bounds + secret scan; no arbitrary SQL API
- **Business truth first:** Store failure does not create `RUN_FAILED`; store must not emit events about its own failure

------------------------------------------------------------
SQLITE DURABILITY SCOPE
------------------------------------------------------------

**Proved:** object-reopen durability (store A writes → closes → store B opens same file → identical projection + events/order).

**NOT proved:** separate-process durability — that is **Increment 10.5**.

Product Supabase: **NOT** part of 10.4. Future Supabase must be an adapter behind the same `ObservabilityStore` port.

------------------------------------------------------------
TEST / RELEASE GATES
------------------------------------------------------------

Targeted 10.4: **31 / 31 PASS** (+ 22 store subtests memory/sqlite) · Combined gate: **298 / 298 PASS** (+ 46 subtests) · Observability + Run Control + Operational Truth + 10.3A–E: **PASS** · Architecture drift: **NO**

------------------------------------------------------------
COMMITS
------------------------------------------------------------

CODE: `163d7bc9096dd9fe47d7275064ff60d4721b57ca` · message: `feat(agents): add durable observability store` · BRANCH: `wip/increment-10-agent-control-room` · PUSH: **SUCCESS** · LOCAL == UPSTREAM: **YES**

FILES (6): `store.py` · `projection.py` · `sqlite_store.py` · `durable_recorder.py` · `__init__.py` · `test_observability_durable_store.py`

Frozen unchanged: `recorder.py` · `contracts.py` · `run_control/**` · `monthly_plan_constructor/**`

------------------------------------------------------------
NEXT
------------------------------------------------------------

**Increment 10.5** — separate-process / restart durability proof. Do **not** start during this checkpoint.

Increment 10: **NOT COMPLETE** · Constructor: **9 / 10**

---

============================================================
CHECKPOINT — 2026-09-02
INCREMENT 10.5
SEPARATE-PROCESS DURABILITY PROOF
============================================================

PROGRAM: Monthly Planning Agentic Orchestration · CURRENT AGENT: MONTHLY_PLAN_CONSTRUCTOR · STATUS: **DONE**

**Purpose:** prove process-independent operational memory — durable `AgentRun` projection and immutable observability history survive Python process termination and are recoverable by another independent process. **ConstructorManagedRuntimeLauncher is NOT implemented in this checkpoint.**

------------------------------------------------------------
10.4 vs 10.5
------------------------------------------------------------

| Increment | Property proved |
|-----------|-----------------|
| **10.4** | SQLite **object-reopen** durability within one Python process |
| **10.5** | **Process-independent** operational memory — Process A may exit; Process B reconstructs identical durable truth |

------------------------------------------------------------
PROCESS A → PROCESS B PROOF
------------------------------------------------------------

**Process A** (independent OS-level Python subprocess · `sys.executable` · `shell=False`):

- Opens `SqliteObservabilityStore` on temp SQLite file
- Creates `AgentRun` · records 7 authoritative events · reaches `COMPLETED` · `projection_version = 7`
- Closes store · exits 0 · objects destroyed

**Process B** (NEW independent Python subprocess · **different PID**):

- Opens **same** SQLite file
- **Does NOT** call `create_run`
- Reconstructs existing `AgentRun` + immutable ordered event log · exits 0

Parent pytest orchestrates subprocesses only; no shared Python memory between A and B.

------------------------------------------------------------
DURABLE STATE PROVEN
------------------------------------------------------------

| Field | Value |
|-------|-------|
| `run_id` | `run-10-5-dur` |
| `operational_status` | `COMPLETED` |
| `projection_version` | **7** |
| `started_at` | `2026-09-02T14:00:03+00:00` |
| `completed_at` | `2026-09-02T14:00:06+00:00` |
| Event count | **7** |
| Event IDs | Same across processes |
| Event fingerprints | Same across processes (public `compute_observability_event_fingerprint`) |
| Event order | Same across processes (`list_events` public API) |

------------------------------------------------------------
REPLAY-AFTER-RESTART LAW
------------------------------------------------------------

Process B replays old `RUN_REQUESTED` written by Process A:

| Result | Value |
|--------|-------|
| Outcome | `IDEMPOTENT_REPLAY` |
| `projection_version` after replay | **7** (unchanged) |
| Event count after replay | **7** (unchanged) |

Replay-before-CAS law survives **full Python-process restart**, not only object reopen.

------------------------------------------------------------
PROCESS INDEPENDENCE LAW
------------------------------------------------------------

No Python object/state transferred between Process A and Process B. No shared: `AgentRun` object · `ObservabilityEvent` object · store instance · sqlite connection · in-memory cache.

Only durable filesystem artifacts: SQLite file (+ bounded verification JSON for comparison only — **not** used for `AgentRun` reconstruction).

------------------------------------------------------------
PARENT REOPEN
------------------------------------------------------------

After Process A and Process B both exited, parent pytest reopened same SQLite file. `AgentRun` and events remained readable and correct — final integrity confirmation.

------------------------------------------------------------
SECURITY / EOS-SEC
------------------------------------------------------------

No product credentials · no network · no Supabase · no `shell=True` · no business datasets · no prompt history · no `AgentExecutionContext` · no secret-bearing state. Synthetic bounded test metadata only.

------------------------------------------------------------
PRODUCTION SCOPE
------------------------------------------------------------

10.5 required **NO** production code changes.

| Item | Status |
|------|--------|
| File created | `tests/test_observability_process_durability.py` |
| SQLite schema | UNCHANGED |
| `ObservabilityStore` | UNCHANGED |
| Runtime | UNCHANGED |
| Run Control | UNCHANGED |

------------------------------------------------------------
TEST / RELEASE GATES
------------------------------------------------------------

Targeted 10.5: **1 / 1 PASS** · Combined observability gate: **203 / 203 PASS** (+ 43 subtests) · Operational Truth: **19 / 19 PASS** · 10.4 regression: **PASS** · Observability regression: **PASS** · Run Control regression: **PASS** · 10.3A–E regression: **PASS** · Architecture drift: **NO**

------------------------------------------------------------
PROGRAM MEANING
------------------------------------------------------------

**10.4** created durable operational memory. **10.5** proved this memory is independent of Python runtime process lifetime. Required before building a managed decoupled agent runtime.

------------------------------------------------------------
COMMITS
------------------------------------------------------------

CODE: `041cea0da21cc066ec42b0a6eea8fa4285f9bf00` · message: `test(agents): prove observability durability across processes` · BRANCH: `wip/increment-10-agent-control-room` · PUSH: **SUCCESS** · LOCAL == UPSTREAM: **YES**

------------------------------------------------------------
NEXT
------------------------------------------------------------

**ConstructorManagedRuntimeLauncher** — connect Run Control to real decoupled Constructor runtime execution. Contract: `launch(...)` = accept/schedule authorized runtime execution; **not** proof of `RUNNING`; **not** wait for whole graph completion. Actual `RUNNING` remains runtime-owned via `RUN_ADVANCING`.

Remaining accepted sequence: ConstructorManagedRuntimeLauncher → 10.6 AgentControlRoomQueryPort → 10.7 Control Room core → 10.8 HITL visualization → 10.9 Handoff/completion visualization → 10.10 full live-run proof

Increment 10: **NOT COMPLETE** · Constructor: **9 / 10**

---

============================================================
CHECKPOINT — 2026-09-02
CONSTRUCTOR MANAGED RUNTIME LAUNCHER
LOCAL MANAGED RUNTIME BACKEND v0.1
============================================================

PROGRAM: Monthly Planning Agentic Orchestration · CURRENT AGENT: MONTHLY_PLAN_CONSTRUCTOR · STATUS: **DONE**

**Purpose:** first real execution-orchestration bridge — Run Control → authorized launch acceptance → decoupled Constructor runtime → LangGraph → runtime-owned `RUN_ADVANCING` → durable operational projection. **10.6 is NOT implemented in this checkpoint.**

------------------------------------------------------------
BRIDGE CREATED
------------------------------------------------------------

```
Run Control
  → authorized launch acceptance
  → ConstructorManagedRuntimeLauncher (thread backend v0.1)
  → run_constructor_langgraph(...)
  → bind_mission → RUN_ADVANCING
  → durable projection RUNNING
```

Execution orchestration — **not** UI behavior.

------------------------------------------------------------
EXECUTION MODEL LAW
------------------------------------------------------------

| Item | Value |
|------|-------|
| **Model** | **THREAD** — Local Managed Runtime Backend v0.1 |
| **Worker thread** | Non-daemon background thread |
| **Replaceable by** | subprocess worker · external worker · queue-backed worker · container worker · on-prem worker |
| **Without changing** | Run Control semantics · Constructor professional lifecycle · Observability contracts · future Control Room contracts |

------------------------------------------------------------
IMPORTANT LIMITATION — MEMORY vs EXECUTION
------------------------------------------------------------

| Concept | Status |
|---------|--------|
| **Process-independent MEMORY** | **PROVEN** (Increment 10.5) |
| **Process-independent EXECUTION** | **NOT YET PROVEN** |

Worker thread lives inside the host Python process. If the host process dies: worker execution dies. Durable operational memory survives; runtime execution itself does not. **Do not blur these two concepts.**

------------------------------------------------------------
RUN CONTROL DURABLE BOOTSTRAP
------------------------------------------------------------

Run Control now optionally receives `durable_store: ObservabilityStore | None`.

When configured:

```
build AgentRun → create_run(agent_run) → first Class A event (RUN_REQUESTED …)
```

`StoreObservabilityRecorder` still does **not** auto-create runs. Bootstrap failure: fail-closed via existing control-plane failure semantics. Legacy in-memory recorder path: **UNCHANGED**.

------------------------------------------------------------
LAUNCH ACCEPTANCE · RUNNING TRUTH · AUTHORIZATION
------------------------------------------------------------

| Law | Detail |
|-----|--------|
| **Protocol** | `ManagedRuntimeLauncher.launch(...) -> None` — **UNCHANGED** |
| **Meaning** | Accepted/scheduled for decoupled execution — **not** RUNNING · **not** COMPLETED · **not** graph finished |
| **Run Control result** | `STARTING` after successful launcher acceptance |
| **Launcher** | Does **not** emit `RUN_ADVANCING`; does **not** mutate `AgentRun` to RUNNING |
| **Runtime owner** | `bind_mission` entry → `RUN_ADVANCING` → durable projection `RUNNING` |
| **Authorization** | Same Run-Control-issued `AgentExecutionContext` in worker thread — **no re-issue**; `authorization_id` **preserved** |

------------------------------------------------------------
WORKER OBSERVABILITY · STREAMLIT · FAILURE
------------------------------------------------------------

- Worker opens **own** `SqliteObservabilityStore` on **same** SQLite file; builds local `StoreObservabilityRecorder`; **no** shared live connection/store object; `close()` in `finally`
- **Streamlit independence:** no `streamlit` · no `pages/**` · no `st.session_state` · headless execution **PASS**
- **Scheduling failure:** propagates → `LAUNCH_OUTCOME_UNKNOWN` / control-plane semantics
- **Unknown worker exception after acceptance:** does **not** fabricate `RUN_FAILED`; last durable truth remains authoritative
- **Known terminal paths:** runtime instrumentation emits `RUN_FAILED` / `RUN_ABORTED` / `RUN_COMPLETED`
- **No kill/stop API** — professional human abort remains separate HITL `RUN_ABORTED` semantics

------------------------------------------------------------
TEST / RELEASE GATES
------------------------------------------------------------

Targeted launcher: **7 / 7 PASS** · Run Control: **30 / 30 PASS** · 10.4: **PASS** · 10.5: **PASS** · Operational Truth: **PASS** · 10.3A–E: **PASS** · Architecture drift: **NO** · Final runtime test state: **COMPLETED**

------------------------------------------------------------
COMMITS
------------------------------------------------------------

CODE: `4d3d683957c1d77cbdc27fab81904b83a98a360b` · message: `feat(agents): add constructor managed runtime launcher` · BRANCH: `wip/increment-10-agent-control-room` · PUSH: **SUCCESS** · LOCAL == UPSTREAM: **YES**

FILES (4): `managed_launcher.py` · `run_control/service.py` · `test_constructor_managed_launcher.py` · `test_run_control_service.py`

Frozen unchanged: Constructor lifecycle/professional logic · ObservabilityStore contracts · LangGraph nodes

------------------------------------------------------------
NEXT
------------------------------------------------------------

**Increment 10.6** AgentControlRoomQueryPort — do **not** start during this checkpoint.

Remaining: 10.6 Query Port → 10.7 Control Room core → 10.8 HITL visualization → 10.9 Handoff/completion visualization → 10.10 full live-run proof

Increment 10: **NOT COMPLETE** · Constructor: **9 / 10**

---

============================================================
CHECKPOINT — 2026-09-02
INCREMENT 10.6
AGENT CONTROL ROOM QUERY PORT
============================================================

PROGRAM: Monthly Planning Agentic Orchestration · CURRENT AGENT: MONTHLY_PLAN_CONSTRUCTOR · STATUS: **DONE**

**Purpose:** safe read-model boundary — Durable Observability → `AgentControlRoomQueryPort` → future Control Room. **Not UI. Not persistence.** Converts durable operational truth into bounded safe immutable operator-facing DTOs. **10.7 is NOT implemented in this checkpoint.**

------------------------------------------------------------
CORE ARCHITECTURE LAW
------------------------------------------------------------

```
Control Room → AgentControlRoomQueryPort → ObservabilityStore
```

**Forbidden:** Control Room → raw SQLite · raw Supabase · raw `ObservabilityEvent.detail`. Future UI **must not** bypass Query Port.

------------------------------------------------------------
QUERY PORT SCOPE · PUBLIC API · STORE DEPENDENCY
------------------------------------------------------------

| Item | Law |
|------|-----|
| **Scope** | **AGENT-NEUTRAL** — no Constructor lifecycle · CandidatePackage · LaborNormResolver · Exception Engine · LangGraph · Streamlit · LLM |
| **Stage IDs** | Opaque strings — future agents (Admission · Constraint · Resource Capacity · Economic Evaluation · Management Decision) reuse same port |
| **Public API** | `list_runs(...)` · `get_run(run_id)` · `get_run_snapshot(run_id, ...)` — **read-only** |
| **No writes** | No start · resume · approve · abort · kill · append_event · update_run |
| **Dependency** | `ObservabilityStore` only — InMemory · SQLite · future Supabase adapter without UI contract change |

------------------------------------------------------------
IMMUTABLE DTO · BOUNDED READ HONESTY
------------------------------------------------------------

Returns **frozen/immutable DTOs** — never raw `AgentRun` · `ObservabilityEvent` · `ObservabilityStore` · SQLite connection · DB rows · SQL.

| Flag / field | Meaning |
|--------------|---------|
| `AgentRunListView.runs_complete` | Store `list_runs` is bounded **oldest-first** window — do **not** claim global newest runs when `False` |
| `AgentRunSnapshot.events_complete` | Store `list_events` is bounded **oldest-first** window — do **not** claim global recent events when `False` |
| **Timeline field** | `timeline_events` — **NOT** `recent_events` |

------------------------------------------------------------
DIRECT TRUTH vs DERIVED VIEW · RAW DETAIL LAW
------------------------------------------------------------

**Direct truth:** `AgentRun` + structured top-level event fields.

**Derived (deterministic, read-only, no LLM, no free-form inference):** stage view · HITL view · handoff view · timeline composition · completeness flags · derivation state.

**`ObservabilityEvent.detail`:** **NOT EXPOSED · NOT AUTHORITATIVE · NOT USED FOR OPERATOR TRUTH.** No derivation of status · stage state · handoff target/source · decision meaning · error meaning from free-form detail. **EOS-SEC law.**

------------------------------------------------------------
STAGE · HITL · HANDOFF DERIVATION LAWS
------------------------------------------------------------

**Stage correlation key:** `(stage_id, node_name, attempt_n, resume_n, artifact_id or "")` · processing: durable append order · contradiction: `INCONSISTENT` · truncation: `INCOMPLETE` · `current_stage` asserted only when event history sufficiently complete (`events_complete=True`). **`AgentRun.current_stage_id` / `current_node` not authoritative** — projection does not maintain them.

**HITL:** headline `waiting_for_human` from `AgentRun.operational_status == WAITING_FOR_HUMAN` · supporting correlation from structured events only (`HUMAN_WAIT_STARTED` · `HUMAN_DECISION_RECEIVED` · `RUN_RESUMED` · `RUN_ABORTED`) · no raw decision payload · no detail interpretation.

**Handoff:** structured `handoff_id` + `HANDOFF_CREATED` / `HANDOFF_PERSISTED` / `HANDOFF_PERSIST_FAILED` only · **no** `source_agent` / `target_role` / `candidate_count` from detail · no handoff artifact body.

------------------------------------------------------------
SECURITY · AUTH · EVENTUAL CONSISTENCY
------------------------------------------------------------

**EOS-SEC allowlist — not exposed:** `AgentExecutionContext` · authorization secrets · tokens · credentials · DSN · service_role · scope blobs · checkpoint/snapshot/package contents · CandidatePackage · raw handoff artifact · event fingerprints · append_sequence · SQL internals · prompt/model data · chain-of-thought.

**Allowed:** `AgentRun.safe_summary` · `AgentRun.safe_counts` · bounded secret-scanned event `title`.

**Auth/RBAC:** **DEFERRED** — 10.6 does not invent fake authorization; product user auth remains future control above/around port.

**Eventual consistency:** atomic multi-read snapshot **NOT REQUIRED** in 10.6 — `get_run()` + `list_events()` may observe slightly different live moments; bounded eventually-consistent polling; expose `projection_version` · `read_at` · `events_complete`; no streaming/websocket.

------------------------------------------------------------
TECHNICAL CHAIN · TEST / RELEASE GATES
------------------------------------------------------------

```
Run Control → ConstructorManagedRuntimeLauncher → Constructor LangGraph Runtime
  → Durable Observability → AgentControlRoomQueryPort → future Control Room UI
```

10.6 closes the **read-model boundary** — does **not** create operator UI.

Targeted 10.6: **21 / 21 PASS** · 10.4: **PASS** · 10.5: **PASS** · Operational Truth: **PASS** · Run Control: **PASS** · ConstructorManagedRuntimeLauncher: **PASS** · 10.3A–E: **PASS** · py_compile: **PASS** · InMemory: **PASS** · SQLite: **PASS** · EOS-SEC: **PASS** · Architecture drift: **NO**

------------------------------------------------------------
COMMITS
------------------------------------------------------------

CODE: `3542f9dfaa03abcd21f3818977b415659f635614` · message: `feat(agents): add control room query port` · BRANCH: `wip/increment-10-agent-control-room` · PUSH: **SUCCESS** · LOCAL == UPSTREAM: **YES**

FILES (6): `control_room/__init__.py` · `dtos.py` · `errors.py` · `derivations.py` · `query_port.py` · `test_agent_control_room_query_port.py`

Existing production files modified: **NONE**

------------------------------------------------------------
NEXT
------------------------------------------------------------

**Increment 10.7** Control Room Core preflight — do **not** start during this checkpoint.

Remaining: 10.7 Control Room Core → 10.8 HITL visualization → 10.9 Handoff / Completion / Digital Organization visualization → 10.10 full live-run proof + regression + EOS-SEC

Increment 10: **NOT COMPLETE** · Constructor: **9 / 10**

---

============================================================
CHECKPOINT — 2026-09-02
INCREMENT 10.7
CONTROL ROOM CORE
============================================================

PROGRAM: Monthly Planning Agentic Orchestration · CURRENT AGENT: MONTHLY_PLAN_CONSTRUCTOR · STATUS: **DONE**

**Purpose:** first real operator-facing surface for the digital workforce — observation only, not execution engine, not control plane. **10.8 is NOT implemented in this checkpoint.**

------------------------------------------------------------
CORE ARCHITECTURE LAW
------------------------------------------------------------

```
Operator → Streamlit Control Room → AgentControlRoomQueryPort → ObservabilityStore
```

**Observe-only:** no start · resume · approve · reject · abort · kill · restart · delete · handoff control · database write · Run Control actions · HITL decision controls.

**Query Port law:** Control Room reads operational truth **ONLY** through `AgentControlRoomQueryPort` (`list_runs(...)` · `get_run_snapshot(...)`).

**Forbidden bypass:** Control Room → `SqliteObservabilityStore` directly · `sqlite3` · Supabase observability tables directly · raw `ObservabilityEvent`. Query Port bypass: **FORBIDDEN**.

------------------------------------------------------------
CORE PRODUCT MEANING
------------------------------------------------------------

For the first time an operator can observe:

- managed agent runs · operational status · project · month · mission · timestamps · projection version
- current stage when deterministically known · stage history · available event timeline
- completeness warnings · derivation warnings

**Without accessing:** runtime internals · raw SQLite · raw `ObservabilityEvent.detail` · Constructor professional logic.

------------------------------------------------------------
CONTROL ROOM FACTORY · OBSERVABILITY PATH LAW
------------------------------------------------------------

`agents/control_room/factory.py` — headless composition root.

| Does | Does NOT |
|------|----------|
| resolve observability configuration | import Streamlit |
| construct `SqliteObservabilityStore` | write runs / append events |
| construct `AgentControlRoomQueryPort` | start agents |
| return Query Port | know Constructor professional logic |
| | expose path to page |

**Production requires:** `AGENT_OBSERVABILITY_DB_PATH` · missing config: **FAIL CLOSED** · nonexistent configured file: **FAIL CLOSED** · ghost database auto-creation: **FORBIDDEN**.

**No false reality:** Control Room must never silently create an empty observability database and present it as operational reality. If durable truth is unavailable → UI reports observability unavailable/not configured. No synthetic empty truth.

**10.7 distinction:** establishes `AGENT_OBSERVABILITY_DB_PATH` as Control Room configuration convention. Does **NOT** yet prove Run Control + Launcher + Control Room all use the same production observability path — that full same-file end-to-end proof belongs to **10.10**.

------------------------------------------------------------
STREAMLIT RESOURCE LAW · PAGE SCOPE
------------------------------------------------------------

`st.cache_resource` — page-side composition wrapper only; caches Query Port/store resource for Streamlit process lifetime. Query data: **NOT cached** — every rerun reads current bounded durable truth through Query Port.

**Page:** `pages/53_AI_Центр_управления_агентами.py` · user-facing language: **Russian** · navigation: `▌ Контур агентной оркестрации` → **Центр управления агентами** · layout: wide · two-pane · operator-oriented.

**Core UX sections:** filters · available run list · selected run · operational status · project/month/mission · timestamps · current stage · stage history · available event window · completeness warnings · derivation warnings. No raw technical dump.

**Filters:** Агент · Проект · Месяц · Статус — values from bounded Query Port data and stable operational status codes only. No SQL-like filter · no raw DB lookup.

------------------------------------------------------------
BOUNDED-READ HONESTY · STAGE TRUTH
------------------------------------------------------------

| Flag | UI law |
|------|--------|
| `runs_complete=False` | explicit warning — only bounded sample visible; do **not** claim all agents / all runs / all active workers / complete fleet |
| `events_complete=False` | explicit warning — only part of event history visible; do **not** claim latest events globally |

**Timeline title:** **Доступное окно событий** — **NOT** «Последние события».

**Stage truth:** UI does **NOT** derive current stage — consumes `snapshot.stage` from Query Port. `INCOMPLETE` → warning only · `INCONSISTENT` → warning only · UI never guesses current stage · no reconstruction from timeline.

------------------------------------------------------------
HITL / HANDOFF BOUNDARIES
------------------------------------------------------------

**10.7 HITL:** when `operational_status == WAITING_FOR_HUMAN` — headline only: **Ожидает решения человека**. Does **NOT** display: decision form · approval/rejection · interrupt drilldown · resume action · decision payload. Dedicated HITL visualization: **10.8**.

**10.7 Handoff:** does **NOT** include handoff organization graph · recipient visualization · artifact drilldown · digital organization graph. Rich handoff/completion visualization: **10.9**.

------------------------------------------------------------
PRESENTATION MODULE · SAFE SUMMARY / COUNTS
------------------------------------------------------------

`agents/control_room/presentation.py` — presentation semantics only: Russian operational status mapping · stage state mapping · event labels · visual category · Moscow timestamp formatting · short run identifier formatting · safe fallback for unknown codes.

**No:** Streamlit · database · Query Port reads · Constructor logic · business truth mutation.

**NOT DISPLAYED in 10.7:** `AgentRun.safe_summary` · `AgentRun.safe_counts` — keep Control Room Core minimal; avoid turning generic dictionaries into uncontrolled presentation contract. DTO capability remains for future explicit design.

------------------------------------------------------------
TIME / IDENTIFIERS · ERROR HANDLING
------------------------------------------------------------

**Timestamps:** source UTC-aware · operator display Europe/Moscow · `DD.MM.YYYY HH:MM` · suffix **МСК**.

**Run identity:** full `run_id` = internal selection identity · list = short display form · full `run_id` in technical identifier area only. No authorization/security ids shown.

**Safe UI errors:** missing/unavailable observability · run not found · query blocker · unexpected error — all operator-safe. **No:** traceback · SQLite path · raw exception text · environment dump.

------------------------------------------------------------
SECURITY / EOS-SEC
------------------------------------------------------------

Control Room does **NOT** render: raw `event.detail` · `AgentExecutionContext` · `authorization_id` · tokens · credentials · DSN · service_role · scope blobs · CandidatePackage · package/snapshot blobs · handoff artifact · event fingerprints · append_sequence · raw DB rows · prompt/model content · chain-of-thought. No unrestricted DTO dump · no unsafe operational HTML.

------------------------------------------------------------
TECHNICAL CHAIN · PROCESS-INDEPENDENCE
------------------------------------------------------------

```
Run Control → ConstructorManagedRuntimeLauncher → Constructor LangGraph Runtime
  → Durable Observability → AgentControlRoomQueryPort → Control Room Core
```

First complete path from managed digital employee execution to safe operator visibility.

**Process-independent memory:** **PROVEN** · **Process-independent execution:** **NOT PROVEN** — Control Room does not change this. Current Constructor worker: **THREAD** inside host Python process.

------------------------------------------------------------
TEST / RELEASE GATES
------------------------------------------------------------

Targeted 10.7: **26 / 26 PASS** · 10.6 regression: **21 / 21 PASS** · Launcher: **PASS** · Run Control: **PASS** · 10.4: **PASS** · 10.5: **PASS** · Operational Truth: **PASS** · 10.3A–E: **PASS** · EOS-SEC: **PASS** · Architecture drift: **NO** · Factory SQLite smoke: **PASS**

------------------------------------------------------------
COMMITS
------------------------------------------------------------

CODE: `9a7eeed931a40dc6dd8fa615979c40675a057b6c` · message: `feat(agents): add control room core` · BRANCH: `wip/increment-10-agent-control-room` · PUSH: **SUCCESS** · LOCAL == UPSTREAM: **YES**

FILES (7): `app.py` · `pages/53_AI_Центр_управления_агентами.py` · `agents/control_room/factory.py` · `agents/control_room/presentation.py` · `tests/test_control_room_presentation.py` · `tests/test_control_room_factory.py` · `tests/test_control_room_page_guards.py`

Query Port / Observability / Run Control / Launcher / Constructor runtime: **unchanged in this commit**

------------------------------------------------------------
NEXT
------------------------------------------------------------

**Increment 10.8** State-of-the-Art HITL Architecture Gate — do **not** start before this checkpoint is committed.

10.8 gate must compare current leading agent/multi-agent HITL architecture patterns and define Execution OS Human Decision Surface:

```
Human Wait → wait identity → required professional decision → evidence/context
  → required authority → human decision → decision provenance
  → controlled resume → reality refresh → post-decision consequence
```

Remaining: 10.8 HITL Architecture Gate + HITL visualization → 10.9 Handoff / Completion / Digital Organization visualization → 10.10 full live-run proof + regression + EOS-SEC + final documentation

Increment 10: **NOT COMPLETE** · Constructor: **9 / 10**
