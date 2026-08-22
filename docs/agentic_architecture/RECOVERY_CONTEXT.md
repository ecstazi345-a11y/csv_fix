# Recovery Context — paste into a new ChatGPT / Cursor session

Продолжаем разработку Execution OS.<br>
**Не проектировать систему заново.**<br>
Ниже зафиксированный архитектурный baseline v0.1 (2026-08-22).

---

## Mission проекта

Execution OS — операционная система физического исполнения СМР: план → допуск → исполнение → приёмка → деньги.

Направление: **AI-native physical execution**, не чат по таблицам.

Контур месячного планирования готовит **месячное производственное обязательство**, а не отчётный dataframe.

Репозиторий продукта: `C:\csv_fix`. Работать только в нём, пока не сказано иное.

---

## Technical stack (TARGET)

```
Python
+ LangGraph runtime
+ Supabase shared state
+ EOS-SEC
+ replaceable LLM adapter
+ Streamlit Agent Control Room
```

Python: deterministic domain, skills, tools, validators, calculations, security adapters.<br>
LangGraph: lifecycle, state, pause/resume, HITL, handoff, retry. **Reuse** existing Python logic, do not rewrite it.<br>
Supabase: operational reality; agents re-read it; no hidden business dumps in prompts. Orchestration persistence schema OPEN.<br>
EOS-SEC: `security/*.md`. MODEL IS NOT A SECURITY BOUNDARY. MODEL IS NEVER CREDENTIAL HOLDER.<br>
LLM: only unstructured/semantic tasks; never arithmetic; never invented authoritative norms; never self-issued permissions.<br>
Streamlit: Control Room + Human Decision Surface + Evidence. **Not** agent runtime. Closing a page must not mean the digital employee dies.

---

## Core law

```
AGENT ≠ DASHBOARD ≠ DATAFRAME ≠ STREAMLIT CALLBACK ≠ CHATBOT
```

Принцип организации (Page52):

> Человек сообщает изменение реальности — агент выполняет работу вокруг этого изменения.

```
DETERMINISTIC WHERE POSSIBLE. AI WHERE USEFUL. HUMAN WHERE REQUIRED.
```

---

## Digital organization

```
ОРКЕСТРАТОР
  → Constructor (кандидатный состав)
  → Admission (допуск)
  → Constraints
  → Resource / capacity
  → Economic
  → Decision pack
  → HUMAN MANAGEMENT GATE
  → Паспорт месячного обязательства
  → Контур исполнения
```

Оркестратор запускает, координирует, пересчитывает, ставит на Human Gate, продолжает, фиксирует handoff. Он не super-agent и не dashboard.

Admission Agent **ещё не реализован**. Кнопка Page10B «В ДОПУСК» / `SENT_TO_ADMISSION` — существующий human product write, не старт Admission Agent.

---

## Constructor

Профессиональное имя: **Агент формирования кандидатного состава месячного плана**.

Не показывает человеку список BOQ как работу.<br>
Получает `ConstructorMission` / `MonthlyPlanningScope`, обрабатывает весь scope, исключает routine, формирует **package**, человеку — только exceptions, готовит handoff к Admission.

### MonthlyPlanningScope

Required: `project_code`, `month_key` (хранимый, пример `сентябрь-2026`; канон `2026-09` через `normalize_month_key`; не `date.today()`).

Optional (omit = ALL inside project/month; if set = MUST bind):

- `facility_scope` (титул/объект)
- `discipline_scope`
- `system_scope`
- `iwp_scope`
- `queue_scope`

NOT mission: витринный статус, свободный search BOQ.

```
UI FILTER ≠ AGENT BUSINESS SCOPE
```

### Lifecycle (target)

```
MISSION_RECEIVED → LOAD_REALITY → CLASSIFY_SCOPE → BUILD_CANDIDATE_PACKAGE
  → CHECK_EXCEPTIONS
      → WAITING_FOR_HUMAN → APPLY_HUMAN_DECISION → REVALIDATE → …
      → PREPARE_HANDOFF → HANDOFF_READY → COMPLETED
FAILED/BLOCKED if unsafe (fail-closed)
```

Grain KEEP: `constructor_candidate_id = PROJECT|MONTH|FACILITY|DISCIPLINE|BOQ`.

Available physical quantity ≠ final committed quantity. Constructor не Resource и не Economic.

Zero price ≠ нет работы.

---

## Handoff

NO HIDDEN AGENT-TO-AGENT CHAT.

Constructor → Admission (conceptual): `handoff_type`, `orchestration_run_id`, `source_agent`, `source_run_id`, `project_code`, `month_key`, `scope`, `candidate_ids`, package summary, labor_norm_status summary, `created_at`, `status`.

Agent B reads current reality itself.

Human Interrupt: pause with `question_id`, reason, object, evidence, allowed decisions; resume after answer. Human does not rerun the whole chain by hand.

---

## Human role

Задаёт mission/scope, сообщает факты, решает exceptions, управленческие решения, EOS-SEC authorization на критический write.

Не: 175 checkbox, qty/crew на каждую routine-строку, ручной перенос между агентами, держать workflow в голове.

Human Gate Constructor = **A scope/task + B exceptions**, не row-by-row.<br>
MPCA-002 security machinery KEEP; предмет gate будет пересмотрен. Security code не менять «заодно».

---

## EOS-SEC (must read)

`security/README.md`<br>
`security/agent_security_baseline.md` (EOS-SEC-1.0 / 1.1)

No generic SQL/write tools. No agent-minted permissions. Secrets never in prompts/traces. Fail closed.

---

## LaborNormResolver

Shared capability (not necessarily an agent). Used by Constructor/Resource/Economic/Tender later.

Source hierarchy: PROJECT_HISTORY → COMPANY_HISTORY → OFFICIAL_NORMATIVE (ГЭСН = benchmark, not automatic true crew productivity) → TECHNOLOGICAL/VENDOR/INDUSTRY → INDUSTRY_BENCHMARK (with provenance) → EXPERT_APPROVED.

LLM cannot invent authoritative norms.

Separate: **normative benchmark** vs **observed productivity (P50/P80)** vs **planning norm**.

```
HISTORY EXISTS ≠ HISTORY IS TRUSTWORTHY
```

Paid hours without executed quantity must not become production norms.

```
MISSING INTERNAL HISTORY ≠ STOP PLANNING
UNRESOLVED norm ≠ drop physical candidate
Unknown norm ≠ silent zero
```

Write path (MPCA-002) still: missing P50 → no invented labor_hours on INSERT.

Continuous learning:

```
benchmark → planning norm → execution → validated productive hours
  → observed P50/P80 → company history → better planning norm
```

---

## Current MPCA state

Safe committed hash:

```
4d7d21bb27c0ba7eea0bf40b77f8f3432d1c7de5
```

| Package | Status |
|---------|--------|
| **MPCA-001** | KEEP: read/analyze/propose, remainder, exclusions, security read. NOT target: project+month-only scope; crew/qty required on every row; table as workflow. |
| **MPCA-002** | KEEP: HumanApproval, WriteAuthorization, trusted write executor, allowlist, kill switch, verify, idempotency, fail closed. Live write NOT approved. Row-by-row approval NOT target UX. |
| **MPCA-003** | KEEP as experiment: Page10B invoke + live read + no write. 175-row dataframe NOT target UX. Do not grow new manual tables. |

Worktree may contain **uncommitted** MPCA-002/003 files. Do **not** git reset/restore/stash/delete them to “clean” a docs task.

Month storage law: `сентябрь-2026`. Labor Page10B: `labor_hours = qty × P50`, `labor_cost = hours × 3000` (page constant, not verified payroll), default `crew_size=1`.

---

## 2026-08-22 architectural deviation (proven)

Live Page10B:

- `PRJ_001_БХК` / `сентябрь-2026`
- scanned 447 / candidates 175 / completed 158 / no remainder 112 / human issues 0
- User selected discipline/facility in UI
- Agent received only project+month → returned **whole project**

Cause: UI filters applied to manual BOQ table after agent call; agent API is `(project_code, stored_month_key)` only.

Anti-pattern: returning 175 routine rows as the main human result after the agent already did the routine.

---

## Anti-patterns (do not revive)

Agent = dashboard / dataframe / Streamlit callback / chatbot.<br>
One agent = one new UI table.<br>
Human reviews every routine row.<br>
Human is courier between agents.<br>
Hidden agent-to-agent prompt chat.<br>
Orchestrator does every specialist job.<br>
LLM does deterministic arithmetic or invents norms.<br>
Unknown norm → 0.<br>
History automatically trusted.<br>
Generic SQL or write tool.<br>
Agent self-issues permissions.<br>
UI presentation filters silently redefine mission.<br>
Missing internal P50 kills physical candidate.

---

## Next step

**AGENT RUNTIME v0.1 — CONSTRUCTOR MISSION**<br>
(not MPCA-004 table)

Proof:

```
Mission: PRJ_001_БХК / сентябрь-2026 / specific facility / вентиляция
→ runtime independent of Streamlit callback
→ load ONLY mission scope
→ classify → candidate package
→ attach labor-norm provenance where available
→ unresolved norm does not erase physical candidate
→ WAITING_FOR_HUMAN if business exceptions else HANDOFF_READY
→ structured handoff prepared for Admission
without requiring candidate dataframe interaction
```

Admission Agent: after this runtime proof.<br>
Do not install LangGraph / change requirements / write SQL / scrape ГЭСН in a session that was only asked to read this file.

Open (do not invent now): checkpoint backend, agent_runs schema, interrupt/handoff persistence, licensed GESN access, BOQ→operation mapping, confidence formula, when resolver becomes an agent, Control Room frontend migration.

---

## Before continuing development

Прочитай:

```
docs/agentic_architecture/*.md
security/*.md
```

Не восстанавливай архитектуру по предположению.<br>
Не принимай текущую таблицу Page10B за утверждённый UX-закон.<br>
Не коммить и не пушь, пока пользователь явно не попросил.
