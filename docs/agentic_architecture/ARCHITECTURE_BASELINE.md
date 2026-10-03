# Architecture Baseline — Execution OS Agentic Architecture v0.1

**Status:** TARGET LAW<br>
**Date:** 2026-08-22<br>
**Does not authorize implementation in this checkpoint.**

---

## 1. What we are building

Execution OS строит **агентную оркестрацию физического исполнения**, а не чат поверх таблиц.

Цифровой сотрудник — не экран и не кнопка. Он:

- получает производственную миссию;
- читает актуальную реальность;
- выполняет повторяемую работу;
- поднимает человеку подготовленный результат и решения, где требуется человек (review / confirm / unresolved), а не сырой массив для ручной сборки с нуля;
- передаёт структурированный результат следующему сотруднику через оркестратор и shared state.

Главный организационный принцип (канон Page52):

> **Человек сообщает изменение реальности — агент выполняет работу вокруг этого изменения.**

Второй принцип реализации:

> **DETERMINISTIC WHERE POSSIBLE. AI WHERE USEFUL. HUMAN WHERE REQUIRED.**

---

## 2. Target stack

Принятый target stack:

```
Python
+ LangGraph runtime
+ Supabase shared state
+ EOS-SEC
+ replaceable LLM adapter
+ Streamlit Agent Control Room
```

### Python

Среда исполнения цифровых сотрудников.

В Python живут:

- deterministic domain logic;
- skills;
- tools;
- validators;
- agent runtime;
- calculation services;
- security adapters;
- integration logic.

Существующее deterministic ядро MPCA **переиспользуется**, не переписывается «под граф».

### LangGraph

Целевой runtime долгоживущих agent workflows:

- state;
- graph lifecycle;
- conditional transitions;
- pause / resume;
- human-in-the-loop;
- handoff;
- retry;
- checkpoint / persistence architecture.

LangGraph **не** должен заставлять переписывать existing Python business logic.

Existing Python business logic: **REUSE, not rewrite.**

Exact checkpoint backend — OPEN (см. § Open design items).

### Supabase

Shared state / operational reality.

Агенты **не** передают друг другу большие hidden prompts с business data.

Business reality хранится и **перечитывается** из Supabase.

Supabase потенциально используется и для persistent orchestration state.<br>
Exact runtime schema (`agent_runs`, `agent_events`, handoff store) **пока не заморожена**.

### EOS-SEC

Обязательный внешний security law.

Канон: `security/README.md`, `security/agent_security_baseline.md`.

**MODEL IS NOT A SECURITY BOUNDARY.**<br>
**MODEL IS NEVER CREDENTIAL HOLDER.**

Security не живёт только в prompt. Enforcement — вне модели: permissions, tool allowlists, trusted context, trusted executor, HumanApproval, WriteAuthorization, kill switch, audit, fail-closed.

Effective permission (EOS-SEC-1.1):

```
EFFECTIVE PERMISSION
  = AUTHORITY SCOPE
  ∩ AGENT PERMISSION
  ∩ PROJECT SCOPE
  ∩ TOOL POLICY
  ∩ ACTION AUTHORIZATION
```

### Replaceable LLM adapter

LLM provider **не** несменяемый фундамент продукта.

- Deterministic logic работает **без** LLM.
- LLM — только там, где есть семантическая или неструктурированная задача (сопоставление описаний работ, поиск candidate source нормы, объяснение различий).
- LLM **не** выполняет детерминированную арифметику.
- LLM **не** выдумывает authoritative labor norms.
- LLM **не** выдаёт себе права и **не** держит credentials.

### Streamlit

Streamlit **не** является runtime цифрового сотрудника.

Streamlit =

- Agent Control Room;
- Human Decision Surface;
- Evidence Drill-down.

Закрытие страницы **не** означает смерть цифрового сотрудника.

Page10B остаётся human workbench существующего ручного конструктора.<br>
Она не должна стать скрытым LangGraph.

---

## 3. Core architectural law

```
AGENT ≠ DASHBOARD
AGENT ≠ DATAFRAME
AGENT ≠ STREAMLIT BUTTON CALLBACK
AGENT ≠ CHATBOT
```

Agent = независимый цифровой исполнитель (First-Class Digital Worker), имеющий:

- mission
- business scope
- state
- lifecycle
- skills
- tools
- permissions
- structured outputs
- exceptions
- human gates
- handoffs
- audit / trace

Один агент **не** равен одной новой UI-таблице.

Большие BOQ/candidate tables — **audit / evidence / drill-down**, не основная поверхность человека.

```
AGENT CORE MUST BE DATA-SOURCE INDEPENDENT.
Professional Agent Core → Professional Tool Contracts → Replaceable Data Adapters
  → current store / API / future on-prem sources
```

Профессия не зависит от конкретного view, UI page или API provider. Текущий shared store — adapter, не часть роли.

Professional Logic ≠ Runtime ≠ Model. Durable runtime independent from UI. Capability ≠ Permission ≠ Authority.

---

## 4. Target digital organization

Канон организации Digital Workforce: [DYNAMIS_PHYSICAL_EXECUTION_ARCHITECTURE_RU.md](../architecture/DYNAMIS_PHYSICAL_EXECUTION_ARCHITECTURE_RU.md). Этот baseline не конкурирует с ним.

Целевая цепочка Monthly Planning:

```
Human Intent
  → Constructor Agent
  → Candidate Package
  → Human Review Gate
  → Reviewed Candidate Package
  → Human Confirm
  → Executability Agent
  → Commitment Agent
  → Human Decision Gate
  → Monthly Commitment / Passport
```

Constructor формирует кандидатный состав.
Executability объединяет Admission + Constraints.
Commitment объединяет Resource Capacity + Economics + Management Recommendation.
Human Decision Gate — финальная authority месячного обязательства.

```
ONE LARGE PROFESSIONAL RESPONSIBILITY = ONE DIGITAL WORKER
```

HISTORICAL / SUPERSEDED AS TARGET: Constructor → Admission → Constraint → Resource → Economics → Decision как отдельные целевые сотрудники.
Admission terminology в current persist — CURRENT LEGACY RUNTIME, не target org.

Оркестратор:

- не dashboard;
- не super-agent, который сам делает работу всех специалистов.

Он запускает, координирует, отслеживает зависимости, управляет повторными расчётами, останавливает workflow на Human Gate, продолжает после решения, создаёт handoff, контролирует завершённость контура.
Orchestrator launch — TARGET, CURRENT NOT_IMPLEMENTED.

Спецификации: Page52 (организационно) + DYNAMIS directive + этот baseline (технически).
Первый детальный сотрудник: [MONTHLY_PLAN_CONSTRUCTOR_AGENT.md](MONTHLY_PLAN_CONSTRUCTOR_AGENT.md), паспорт [CONSTRUCTOR_AGENT_ANATOMY.md](CONSTRUCTOR_AGENT_ANATOMY.md).

Не имитировать следующего сотрудника UI-кнопкой product write человека.

---

## 5. Shared state and handoff

**NO HIDDEN AGENT-TO-AGENT CHAT.**

```
Source Digital Worker → typed business artifact → durable persistence
  → authorized handoff → target role → receiver acknowledgement → next professional process
```

```
HANDOFF_PERSISTED != RECEIVER_ACCEPTED
RECEIVER_ACCEPTED != BUSINESS_APPROVED
AGENT_COMPLETED != ORCHESTRATION_COMPLETED
```

Agent A фиксирует structured result/state.
Orchestrator фиксирует transition.
Agent B получает identifiers и сам читает current reality через свои adapters.

Детали: [ORCHESTRATION_AND_HANDOFF.md](ORCHESTRATION_AND_HANDOFF.md).

---

## 6. Human place

Человек:

- задаёт mission / scope;
- сообщает новые факты реальности;
- решает exceptions;
- авторизует критические действия (EOS-SEC Human Gate);
- принимает управленческое обязательство месяца.

Человек **не**:

- не является runtime агента;
- не собирает заранее таблицу BOQ как вход Constructor;
- не переносит результаты между агентами вручную;
- не держит state workflow в памяти.

Human Gate constructor (2026-10-02): Human Intent → Human Review готового Candidate Package (Добавить / Убрать / Требует уточнения, массовые решения) → Reviewed Candidate Package → Human Confirm → Executability Agent.
Не закон целевой профессии: «человек видит только blocking exceptions».
Не закон: ручной ритуал как способ *собрать* состав с нуля.
Канон: [CONSTRUCTOR_AGENT_ANATOMY.md](CONSTRUCTOR_AGENT_ANATOMY.md). Architecture Baseline не конкурирует с Anatomy.

Security-объекты MPCA-002 (issuer-only HumanApproval, WriteAuthorization, kill switch) **сохраняются**. Меняется предмет подтверждения, не контур полномочий. Код security в этом checkpoint не меняется.

---

## 7. Labor norms — core principle

**MISSING INTERNAL HISTORY ≠ STOP THE ENTIRE PLANNING FLOW.**

Отсутствие собственной истории не означает отсутствие физически существующей работы.

Два закона Constructor (канон Anatomy; taxonomy статусов — Candidate Package, не новые P50/P80 production semantics):

- Discovery: `UNRESOLVED` не удаляет physical candidate. Candidate Package может содержать unresolved и обязан показать их человеку.
- Reviewed / final handoff: included `UNRESOLVED` → HANDOFF BLOCKED. Семь unresolved в discovery-пакете нельзя передать Executability Agent как reviewed handoff.

Норма труда — отдельная атрибутированная оценка для:

- resource planning;
- economic analysis;
- capacity estimation;
- tender estimation;
- production forecasting.

Канон: [LABOR_NORM_RESOLUTION.md](LABOR_NORM_RESOLUTION.md).

Constructor **не** становится Resource / Economic / Normative Estimator.

---

## 8. Current implementation assets

Safe committed baseline (не трогать как «уже в main»):

```
4d7d21bb27c0ba7eea0bf40b77f8f3432d1c7de5
```

Worktree на 2026-08-22 также содержит **незакоммиченные** MPCA-002 / MPCA-003 файлы. Это не committed law. Не reset / restore / stash их из-за документации.

### MPCA-001 — KEEP

Ценность:

- deterministic READ → ANALYZE → PROPOSE;
- availability / remainder;
- completed / no remainder / already planned;
- candidate classification;
- security read layer (trusted context + trusted read executor).

**Не считать target law:**

- scope только `project + month`;
- `human_required_fields = crew + planned_qty` на каждой routine-строке;
- candidate table как human workflow;
- `admission_handoff_ready = False` только потому, что человек не проставил qty/crew.

### MPCA-002 — KEEP

Ценность:

- HumanApproval;
- WriteAuthorization;
- trusted write executor;
- field allowlist;
- kill switch (fail-closed);
- read-back verify;
- idempotency;
- audit;
- derived labor/price не от агента;
- missing P50 → zero writes на **write** path.

**Не считать target UX law:** row-by-row human approval как способ собрать состав с нуля.

Предмет Human Gate Constructor (2026-10-02) — Anatomy, не этот список MPCA-002:

- Human Review готового пакета;
- Human Confirm перед Executability Agent;
- critical action authorization.

Live product write **не** разрешён этим документом.

### MPCA-003 — KEEP AS TECHNICAL EXPERIMENT

Доказано:

- агент вызывается с Page10B;
- live Supabase read работает;
- candidate result можно отрисовать;
- product write не произошёл.

**Не считать target Agent UX:** 175-row candidate dataframe.

Не развивать MPCA-003 в сторону новых manual tables.

---

## 9. Architectural deviation — 2026-08-22

Live visual review Page10B:

| Поле | Факт |
|------|------|
| Project | `PRJ_001_БХК` |
| Month | `сентябрь-2026` |
| Scanned | 447 |
| Candidates | 175 |
| Completed excluded | 158 |
| No remainder excluded | 112 |
| Human issues | 0 |

Пользователь выбрал в Page10B discipline / facility (титул), но агент получил только project + month и вернул кандидатов **всего проекта**.

Причина: UI filters не являлись Agent Mission Scope. Агент вызывался как `run(project_code, stored_month_key)`.

Вывод:

```
UI FILTER ≠ AGENT BUSINESS SCOPE
```

Нужен explicit `MonthlyPlanningScope`.<br>
Возврат 175 строк человеку как основной результат — **anti-pattern**: routine removal, сделанный агентом, уничтожается поверхностью.

Доказательная цепочка зафиксирована в [MONTHLY_PLAN_CONSTRUCTOR_AGENT.md](MONTHLY_PLAN_CONSTRUCTOR_AGENT.md) и [DECISION_LOG.md](DECISION_LOG.md).

---

## 10. Anti-patterns

DO NOT:

- Agent = dashboard.
- Agent = dataframe generator.
- Agent = Streamlit callback only.
- One agent = one new UI table.
- Human manually reviews every routine row.
- Human transfers results between agents.
- Hidden agent-to-agent prompt chat.
- Orchestrator performs every specialist role.
- LLM performs deterministic arithmetic.
- LLM invents labor norms.
- Unknown norm silently becomes zero.
- Historical data automatically trusted.
- Generic SQL tool.
- Generic write tool.
- Agent self-issues permissions.
- UI presentation filters silently redefine mission.
- Missing internal P50 automatically kills a physical planning candidate.

---

## 11. Observability — Agent Control Room

Target Streamlit (пример, не макет к реализации в этом checkpoint):

```
ПОДГОТОВКА СЕНТЯБРЯ 2026

Constructor: COMPLETED
127 обработано
54 candidate package
2 exceptions

Norm coverage:
  41 validated
  9 provisional
  4 unresolved

Admission: RUNNING   # historical mock; not target org (Executability is target)
31 / 54 checked

Human attention: 2

[Открыть решения]
[Показать доказательства]
```

Большие таблицы — только drill-down.

---

## 12. Routine removal KPI

Главный KPI Execution OS (Page52):

> доля координационной, расчётной и административной рутины, снятая с ИТР.

Constructor измеряет **свою** рутину, не финансовую маржу месяца:

- `rows_processed`
- `routine_items_handled_by_agent`
- `human_exceptions`
- `manual_rows_before`
- `manual_decisions_after`
- `routine_removal_percent`
- `processing_duration`
- `estimated_engineering_time_saved` (оценка, не финансовый claim)
- `candidate_physical_scope_identified`
- `candidate_value_identified` (если цена доказана; иначе не выдумывать)
- `labor_norm_coverage_percent`
- `validated_norm_percent` / `provisional_norm_percent` / `unresolved_norm_percent`

Не утверждать финансовую экономию, если она не доказана.
Экономика месячного обязательства — ответственность Commitment Agent (target). HISTORICAL chain Admission → Resource → Economic → Decision как отдельные сотрудники — SUPERSEDED AS TARGET.

---

## 13. Next engineering release

**AGENT RUNTIME v0.1 — CONSTRUCTOR MISSION**

Не MPCA-004 table.

Цель: запустить Constructor как workflow, независимый от Streamlit callback.

Первый success scenario:

```
Mission:
  project:     PRJ_001_БХК
  month:       сентябрь-2026
  facility:    specific
  discipline:  вентиляция
  system:      ALL
  iwp:         ALL

→ LangGraph runtime starts
→ loads ONLY mission scope
→ classifies scope
→ builds candidate package
→ attaches labor norm provenance where available
→ unresolved labor norm does not erase physical candidate
→ Human Review / Reviewed Candidate Package / Human Confirm — TARGET, CURRENT NOT_IMPLEMENTED
→ structured handoff to Executability Agent — TARGET; current persist may still use Admission terminology (LEGACY)
```

Без обязательного interaction с candidate dataframe как способом *собрать* состав.

Executability Agent / Commitment Agent / Orchestrator: **NOT_IMPLEMENTED**. Не выдавать target за current.

Этот checkpoint **не** устанавливает LangGraph, **не** меняет requirements, **не** пишет runtime.

---

## 14. Open design items

Зафиксировано как OPEN — не выдумывать окончательное решение сейчас:

- LangGraph checkpoint backend;
- exact `agent_runs` / `agent_events` schema;
- persistent Human Interrupt storage;
- persistent handoff storage;
- exact ГЭСН / normative data connector;
- legal/licensed access to external normative databases;
- operation taxonomy;
- mapping BOQ → operation → norm source;
- confidence calculation;
- norm adjustment factors;
- when LaborNormResolver should become an independent agent;
- when to migrate Streamlit to another Control Room frontend.

---

## 15. Related documents

- [MONTHLY_PLAN_CONSTRUCTOR_AGENT.md](MONTHLY_PLAN_CONSTRUCTOR_AGENT.md)
- [ORCHESTRATION_AND_HANDOFF.md](ORCHESTRATION_AND_HANDOFF.md)
- [LABOR_NORM_RESOLUTION.md](LABOR_NORM_RESOLUTION.md)
- [DECISION_LOG.md](DECISION_LOG.md)
- [RECOVERY_CONTEXT.md](RECOVERY_CONTEXT.md)
- `security/*.md` — EOS-SEC
- Page52 — организационное описание
