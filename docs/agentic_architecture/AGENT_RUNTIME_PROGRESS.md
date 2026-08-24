# Agent Runtime Progress — Execution OS

**Purpose:** долговечная инженерная память агентной программы. Не история чата.

Checkpoints **append-only**. Не переписывать предыдущие записи.

**Program:** Monthly Planning Agentic Orchestration<br>
**Stack law:** Python + LangGraph + Supabase shared state + EOS-SEC + replaceable LLM adapter + Streamlit Control Room<br>
**Decomposition law:** one major professional role = one specialized agent. Shared capabilities are not agents.

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
