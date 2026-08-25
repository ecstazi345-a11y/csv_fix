# Agent Runtime Progress — Execution OS

**Purpose:** долговечная инженерная память агентной программы. Не история чата.

Checkpoints **append-only**. Не переписывать предыдущие записи.

**Program:** Monthly Planning Agentic Orchestration<br>
**Stack law:** Python + LangGraph + Supabase shared state + EOS-SEC + replaceable LLM adapter + Streamlit Control Room<br>
**Decomposition law:** one major professional role = one specialized agent. Shared capabilities are not agents.

## Current snapshot (not a checkpoint)

- **Program:** Monthly Planning Agentic Orchestration
- **Current agent:** MONTHLY_PLAN_CONSTRUCTOR
- **Progress:** **5 / 10**
- **DONE:** [1] Mission Scope · [2] Candidate Package · [3] Secure Read Tool Adapters · [4] Labor Norm Resolver · [5] Exception Engine
- **NEXT:** [6] Pure Python Lifecycle
- **Recovery HEAD:** `38cd42ff7fa256500a602614bf22e854ab763eff` (LOCAL == REMOTE)

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
