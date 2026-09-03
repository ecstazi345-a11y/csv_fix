# Универсальный шаблон профессионального паспорта цифрового сотрудника

**Document:** PROFESSIONAL_PASSPORT_TEMPLATE_V1_0
**Version:** v1.0
**Status:** REUSABLE STANDARD
**Language:** Russian (English terms only where architecturally useful)

---

## Как пользоваться этим шаблоном

### Назначение

**Professional Passport / Профессиональный паспорт** — устойчивое определение цифрового сотрудника как **профессии** внутри организации Execution OS.

Это **не** в первую очередь:

- спецификация Python-модуля;
- prompt template;
- описание LangGraph-графа;
- system prompt чат-бота;
- UI-спецификация;
- API contract;
- checklist тестов.

Технология **реализует** профессию. Паспорт отвечает:

> **Какой профессиональный сотрудник существует** в организации?

### Рекомендуемый workflow

1. Определить **профессию** до кода.
2. Зафиксировать **границу ответственности**.
3. Разделить **CURRENT / PROVEN** и **TARGET / FUTURE**.
4. Определить **бизнес-артефакт** и **handoff**.
5. Определить **Human Decision Gates**.
6. Определить **permissions / security**.
7. Определить **skills / tools**.
8. Только затем выбрать **runtime**.
9. Реализовывать инкрементально.
10. Доказать полное профессиональное исполнение.
11. Финализировать Passport по **фактической** реализации.

| Вид паспорта | Смысл |
|--------------|--------|
| **Initial Passport** | design contract профессии |
| **Final Passport** | validated professional truth после proof |

### Ссылка на эталон (один раз)

Первая утверждённая реализация этого стандарта:

`MONTHLY_PLAN_CONSTRUCTOR_PROFESSIONAL_PASSPORT_V1_0.md`

Будущие агенты переиспользуют **стандарт**, а не Constructor-specific skills, states, decisions, artifacts или business rules.

### Концептуальный порядок

```
PROFESSION / ПРОФЕССИЯ
  → RESPONSIBILITY / ПРОФЕССИОНАЛЬНАЯ ОТВЕТСТВЕННОСТЬ
  → MISSION
  → SCOPE
  → SKILLS
  → TOOLS
  → PERMISSIONS
  → PROFESSIONAL STATE
  → LIFECYCLE
  → HUMAN DECISION GATES
  → BUSINESS ARTIFACTS
  → HANDOFF
  → RUNTIME
  → OBSERVABILITY
  → SECURITY
  → TESTS / PROOF
  → ECONOMIC KPI
```

### Карта обязательности разделов / Section Applicability Map

Цель: не заполнять нерелевантные разделы «для галочки».

#### A. MANDATORY CORE (каждый профессиональный цифровой сотрудник)

Professional Identity · Why / Business Problem · Responsibility · OWNED / SHARED / NOT OWNED · Organizational Position · Mission · Mission Scope · Input Reality · Skills · Tools · Permissions · Security / EOS-SEC · Professional State · Lifecycle · Business Result / Artifact or Formal Outcome · Completion Law · Observability · Traceability (по роли) · Human Role After Automation · Business Value classification · Current / Proven vs Target / Future vs Not In Scope · Failure Conditions · Professional Proof / Evidence · Versioning · Passport status.

Реализация не обязана быть одинаковой у всех ролей.

#### B. CONDITIONAL — заполнить, если применимо; иначе `NOT APPLICABLE / N/A` + одна строка причины

Human Decision Gates · Reality Refresh after decision · Handoff · Receiver Acceptance · Ownership Transfer · Write-Action Governance · Physical Actuation · LLM usage · Distributed Runtime · сложные restart/durability категории · финансовые KPI · сценарии Human Decision / Handoff Failure / Write Failure / Physical Safety · Downstream Acceptance KPI.

#### C. TECHNICAL APPENDIX / Technical Governance Evidence

Runtime backend · checkpoint backend · durability matrix · immutable-fact semantics · technical proof references · event/correlation details · test evidence · policy versions.

#### Закон N/A

| Статус | Значение |
|--------|----------|
| **CURRENT / PROVEN** | реализовано и есть evidence |
| **TARGET / FUTURE** | входит в целевую архитектуру, ещё не доказано |
| **NOT IN SCOPE** | явно исключено из роли/версии |
| **NOT APPLICABLE / N/A** | концепт **не применим** к этой профессии/версии |

`N/A` **не** означает «ещё не сделали».
Если capability относится к будущей архитектуре — пишите **TARGET / FUTURE**, не N/A.

#### Рекомендуемый порядок чтения

**Для руководства:** Profession → Business Problem → Responsibility → Boundaries → Business Result → Human Role → Business Value → Current vs Future.

**Для архитекторов / разработчиков:** далее Skills → Tools → Permissions → State → Lifecycle → HITL (если применимо) → Handoff (если применимо) → Runtime → Observability → Security → Proof.

#### Design Passport vs Validated Passport

| Вид | Допустимо |
|-----|-----------|
| **DESIGN PASSPORT** | PLANNED / TARGET |
| **VALIDATED PASSPORT** | CURRENT только при evidence |

Намерение дизайна **не** становится CURRENT без proof.

---

# Профессиональный паспорт цифрового сотрудника

## Header / Шапка

| Поле | Значение |
|------|----------|
| **Профессия** | `<Название профессии>` |
| **System Code** | `<AGENT_CODE>` |
| **Passport Version** | `<например v1.0>` |
| **Agent Runtime Version** | `<например v0.1>` |
| **Business Contour** | `<бизнес-контур>` |
| **PRIMARY ORGANIZATIONAL LAYER** | `<Production / Design / Platform>` |
| **OPTIONAL SECONDARY INTERACTIONS** | `<другие слои / NONE — не «belongs everywhere»>` |
| **Action / Security Tier** | `<TIER_0…TIER_4 / repository equivalent>` |
| **Current Status** | `<DESIGN / IMPLEMENTING / TECHNICALLY PROVEN / FROZEN>` |
| **Technical Completion** | `<X / X или NOT APPLICABLE>` |
| **Primary Business Artifact / Formal Outcome** | `<... или N/A с причиной>` |
| **Upstream Role** | `<Upstream роль или NONE>` |
| **Target Downstream / Handoff Target** | `<роль / queue / human / platform / physical / NONE>` |
| **Current vs Target Chain** | `<явно классифицировать CURRENT / TARGET>` |

**Warning:** не заполняйте Target Downstream так, будто receiver уже доказан, если нет evidence.

**Security Tier** — только классификация риска (EOS-SEC baseline: `TIER_0_READ_ONLY_DETERMINISTIC` … `TIER_4_PHYSICAL_WORLD_ACTUATION`). Tier **не** выдаёт permissions и authority; они задаются явно.
---

## 1. Профессия в одном предложении

### Purpose

Дать одно сильное определение профессии.

### Required sentence form

`"<Role> — цифровой сотрудник, который <глагол> <объект работы> в пределах <scope>, чтобы получить <профессиональный результат>, и не владеет <граница полномочий>."`

### Questions

- Какой глагол профессиональной работы?
- Над чем именно работает сотрудник?
- В каких границах?
- Какой формальный результат?
- Где заканчивается власть роли?

### Reject

- «помогает управлять проектом»
- «анализирует данные»
- «использует ИИ для повышения эффективности»

### Fill

`<Одно предложение профессии>`

---

## 2. Зачем существует профессия

### Purpose

Объяснить **бизнес-проблему организации**, не мотивацию разработки ПО.

### Questions

- Какая реальная организационная проблема существует сегодня?
- Какая рутина / ручная работа порождает эту роль?
- Кто выполняет её сейчас (должность / функция)?
- Почему текущий процесс: медленный / дорогой / несогласованный / нетрассируемый / зависит от конкретных людей?
- Что происходит, если роли нет?

### Required fields

| Поле | Ответ |
|------|--------|
| Business problem | `<...>` |
| Current human owners | `<...>` |
| Pain / failure modes | `<...>` |
| Cost of absence | `<...>` |

### Warning

Не подменять бизнес-проблему «нужно внедрить агента / LLM / dashboard».

---

## 3. Профессиональная ответственность

### Purpose

Зафиксировать **ровно одну** primary responsibility и предотвратить супер-агента.

### Mandatory formulation

> This employee owns responsibility for / Этот сотрудник владеет ответственностью за:
> `<одна primary responsibility>`

### Required split

| Class | Content |
|-------|---------|
| **OWNED** | `<что роль владеет>` |
| **SHARED** | `<что разделяет с другими ролями / capability>` |
| **NOT OWNED** | `<что явно вне роли>` |

### Warning

Если «OWNED» разрастается на несколько независимых профессий — разделите агентов или вынесите capability.

---

## 4. Место в цифровой организации

### Purpose

Показать позицию роли в цепочке без ложного claim о receiver.

### Required

| Поле | Classification | Value |
|------|----------------|-------|
| Upstream role | CURRENT / TARGET / NONE | `<...>` |
| Current role | CURRENT / PROVEN | `<...>` |
| Downstream intended role | TARGET / PROVEN | `<...>` |
| Target organization chain | TARGET | `<...>` |

### Universal law

```
INTENDED TARGET ROLE  !=  OBSERVED RECEIVER
TARGET_ROLE_KNOWN     !=  TARGET_AGENT_OBSERVED
```

### Warning

Не рисуйте всю future-цепочку как уже доказанную.

---

## 5. Mission / Миссия

### Purpose

Mission = **одно конкретное профессиональное задание** одному цифровому сотруднику.

### Questions

- Что является mission identity?
- Какой business context?
- Какой scope?
- Какой ожидаемый professional result?
- Кто / что инициирует (человек / orchestrator / event)?
- Есть ли authorization context?

### Required conceptual fields

| Field | Value |
|-------|--------|
| Mission identity | `<...>` |
| Business context | `<...>` |
| Scope | `<...>` |
| Expected result | `<...>` |
| Initiator / orchestrator context | `<...>` |
| Authorization context | `<если применимо / NONE>` |

---

## 6. Mission Scope / Область задания

### Purpose

Формально определить, **где** сотруднику разрешено работать.

### Required dimensions (adapt per profession)

Objects · Locations · Time periods · Systems · Packages · Entities · другие профессиональные границы.

### Core laws

1. Scope **может сужаться**.
2. Scope **нельзя молча расширять**.
3. Outside Scope → **FAIL CLOSED**.

### Fill

| Scope dimension | Required? | Allowed values | Expansion forbidden? |
|-----------------|-----------|----------------|----------------------|
| `<...>` | YES/NO | `<...>` | YES |

---

## 7. Input Reality / Входная реальность

### Purpose

Описать, какую бизнес-реальность роль читает, и как классифицирует доверие.

### Required classes

| Class | Examples / Fill |
|-------|-----------------|
| **AUTHORITATIVE INPUTS** | `<...>` |
| **SUPPORTING INPUTS** | `<...>` |
| **HUMAN-PROVIDED INPUTS** | `<...>` |
| **DERIVED INPUTS** | `<...>` |
| **UNTRUSTED DATA** | `<...>` |

### Law

**DATA ≠ INSTRUCTION** — поля продукта / тексты / документы не становятся командами роли.

---

## 8. Professional Skills / Профессиональные навыки

### Purpose

Описать умения профессии. Skill **не** автоматически является Agent.

### Required table (one row per skill)

| Field | Value |
|-------|--------|
| Skill Name | `<...>` |
| Professional Purpose | `<...>` |
| Input | `<...>` |
| Action | `<...>` |
| Output | `<...>` |
| Stop Condition | `<...>` |
| Evidence | `<...>` |
| Deterministic / Semantic / Hybrid | `<...>` |
| Human Gate required? | YES / NO |

### Warning

Не создавайте «skill-агентов» без отдельной профессиональной ответственности.

---

## 9. Tools / Инструменты

### Purpose

Описать контролируемые способности, не неограниченный доступ.

### Required table (one row per tool)

| Field | Value |
|-------|--------|
| Tool Name | `<...>` |
| Purpose | `<...>` |
| Read / Write | READ / WRITE / BOTH |
| Allowed Scope | `<...>` |
| Required Permission | `<...>` |
| Possible Side Effect | `<...>` |
| Audit Requirement | `<...>` |
| Human Approval Requirement | YES / NO / CONDITIONAL |
| Failure Mode | FAIL CLOSED / RETRY / WAIT / OTHER |

### Warning

Запрещены unrestricted SQL / shell / HTTP / «полный доступ к БД» без явного allowlist и аудита.

---

## 10. Shared Capabilities / Services

### Purpose

Отделить reusable functions от профессиональных агентов.

### Typical classes (not agents by default)

resolver · validator · calculator · classifier · schema validator · security service

### Rule

Создавайте отдельный Agent **только** если есть:

- distinct professional responsibility;
- distinct lifecycle;
- meaningful handoff / artifact boundary;
- independent permissions.

### Fill

| Capability | Used by this role? | Separate Agent? | Why / Why not |
|------------|--------------------|-----------------|---------------|
| `<...>` | YES/NO | NO (default) | `<...>` |

---

## 11. Deterministic vs LLM Boundary

**Applicability:** LLM usage is CONDITIONAL. Fully deterministic role may mark **LLM: N/A** — это **не** архитектурная слабость. **AI-native ≠ LLM-required.**

### Purpose

Зафиксировать, где жёсткая истина, а где допускается LLM.
### Required table

| Professional Function | Deterministic? | LLM Allowed? | Reason | Hard Business Truth? | Human Validation Required? |
|-----------------------|----------------|--------------|--------|----------------------|----------------------------|
| `<...>` | YES/NO | YES/NO | `<...>` | YES/NO | YES/NO |

### Core laws

```
LLM != AGENT
LLM != SECURITY BOUNDARY
LLM != PERMISSION ENGINE
LLM != HARD ARITHMETIC AUTHORITY
LLM != DIRECT WRITE AUTHORITY
```

### Warning

Отсутствие LLM **не** означает «это не цифровой сотрудник».

---

## 12. Professional Lifecycle

### Purpose

Описать профессиональный поток работы роли (не копировать чужие state codes).

### Required skeleton (adapt names)

```
mission received
  → work begins
  → professional stages
  → exceptions
  → optional Human Wait
  → resume
  → revalidation if needed
  → artifact
  → handoff
  → own completion
```

### Fill

| Stage | Meaning | Terminal? | Human Gate possible? |
|-------|---------|-----------|----------------------|
| `<...>` | `<...>` | YES/NO | YES/NO |

### Warning

Не форсируйте состояния другой профессии.

---

## 13. Professional State

### Purpose

Сделать состояние явным и внешним относительно prompt memory.

### Required answers

| Question | Answer |
|----------|--------|
| What state must survive between steps? | `<...>` |
| What is business state? | `<...>` |
| What is runtime state? | `<...>` |
| What is checkpoint state? | `<...>` |
| What is observability state? | `<...>` |
| What belongs in shared SoT? | `<...>` / TARGET |
| What must NOT depend on prompt memory? | `<...>` |

---

## 14. Human Decision Gates

**Applicability:** CONDITIONAL. Если у профессии нет Human Gate: `NOT APPLICABLE` + почему. Не выдумывайте fake approval workflow.

### Purpose

Описать формальные точки остановки автономии **там, где они требуются**.

Не каждый mission/run обязан содержать Human Wait.

### Required per gate (если применимо)

| Field | Value |
|-------|--------|
| Why autonomy stops | `<...>` |
| Reason codes | `<...>` |
| Allowed decisions | `<...>` |
| Evidence required | `<...>` |
| Actor observed | `<...>` |
| Authority required | `<modeled? YES/NO>` |
| Decision consequence | `<...>` |
| Reality refresh required? | YES / NO / CONDITIONAL |
| Resume conditions | `<...>` |
| Stale decision protection | `<...>` |
| Audit evidence | `<...>` |

### Universal law (если Human Gate существует)

```
OBSERVED ACTOR  !=  AUTHORIZED ACTOR
```

Authority / enterprise RBAC must be **explicitly modeled** before being claimed as proven.

### Reality Refresh (conditional)

Reality Refresh **REQUIRED**, когда decision/action может инвалидировать professional assumptions или authoritative reality, использованные до паузы.

Reality Refresh **не** обязателен после каждого Human Decision.

### Warning

Human Gate ≠ «кнопка в UI» ≠ «вопрос в чат».

---

## 15. Business Artifacts

### Purpose

Каждый профессиональный сотрудник обязан иметь формальный output.

### Required per artifact

| Field | Value |
|-------|--------|
| Artifact Name | `<Основной бизнес-артефакт>` |
| Business Meaning | `<...>` |
| Schema / Contract | `<...>` |
| Identity | `<...>` |
| Provenance | `<...>` |
| Version | `<...>` |
| Input References | `<...>` |
| Professional Status | `<...>` |
| Downstream Consumer | `<Целевая роль-получатель>` |
| What it DOES NOT mean | `<...>` |

### Warning

Primary output **не должен** быть «ответом на естественном языке», если профессия этого не требует.

---

## 16. Handoff / Передача результата

**Applicability:** CONDITIONAL. Не каждая профессия обязана иметь Handoff. Если нет — `NOT APPLICABLE` + причина. Если планируется позже — `TARGET / FUTURE`, не N/A.

### Purpose

Формализовать передачу результата получателю.

Получатель handoff **может** быть:

- другой professional digital employee;
- human role;
- management / organizational work queue;
- platform / service;
- external controlled system;
- physical executor / robot / drone / autonomous system — только если security architecture это разрешает.

### Required per handoff (если применимо)

| Field | Value |
|-------|--------|
| Source Role | `<AGENT_CODE>` |
| Artifact / Result | `<...>` |
| Handoff Type | `<...>` |
| Target (role / queue / human / platform / physical) | `<...>` |
| Persistence Requirement | REQUIRED / OPTIONAL |
| Receiver Acceptance Required? | YES / NO / FUTURE / N/A |
| Ownership Transfer Mode | NONE / FUTURE / MODELED / N/A |
| Authority Model | NONE / FUTURE / MODELED / N/A |
| Correlation Identity | `<...>` |
| Failure Handling | `<...>` |

### Default truth laws (где эти понятия применимы)

```
HANDOFF_CREATED      !=  HANDOFF_PERSISTED
HANDOFF_PERSISTED    !=  RECEIVER_ACCEPTED
TARGET_KNOWN         !=  RECEIVER_OBSERVED
SOURCE_COMPLETED     !=  ORCHESTRATION_COMPLETED
```

Не форсируйте конкретные имена событий одной реализации.

Do NOT imply every handoff has a receiver AI agent.

---

## 17. Completion Law / Закон завершения

### Purpose

Не допустить ложного заявления о завершении организации / оркестрации.

### Required answers

1. **When may this digital employee truthfully claim that ITS OWN JOB is complete?**
   `<условия + predecessors>`

2. **What does its completion NOT mean?**
   `<список запрещённых интерпретаций>`

---

## 18. Permissions

### Purpose

Least privilege. Default: **DENY** unless explicitly allowed.

### Required matrix

| Capability | Read | Write | External Side Effect | Human Approval | Allowed Scope | Forbidden Scope |
|------------|------|-------|----------------------|----------------|---------------|-----------------|
| `<...>` | Y/N | Y/N | `<...>` | Y/N | `<...>` | `<...>` |

---

## 19. EOS-SEC

### Purpose

Привязать security law к конкретной профессии.

Also fill header field: **Action / Security Tier** (`TIER_0`…`TIER_4` per `security/agent_security_baseline.md`). Tier classifies risk; it does not grant permission.

### Mandatory laws (explain application)

| Law | How it applies to this profession |
|-----|-----------------------------------|
| MODEL IS NOT SECURITY BOUNDARY | `<...>` |
| DATA ≠ INSTRUCTION | `<...>` |
| LEAST PRIVILEGE | `<...>` |
| READ / WRITE SEPARATION | `<...>` |
| FAIL CLOSED | `<...>` |
| NO SECRET LEAKAGE | `<...>` |
| NO RAW LLM → WRITE | `<...>` |
| NO RAW LLM → PHYSICAL ACTUATION | `<...>` |
| HUMAN-GATED CRITICAL ACTIONS | `<...>` |

---

## 20. Write-Action Governance

**Applicability:** CONDITIONAL.

| Case | Action |
|------|--------|
| Role is read-only | state explicitly: **READ-ONLY**; section = `NOT APPLICABLE` |
| Role has writes | classify risk and apply the matching governance |

### Requirement vs current platform

Этот раздел задаёт **Passport requirement** для будущих write-capable профессий.
Он **не** утверждает, что Execution OS уже реализует все классы autonomous writes.

### Default mandatory flow — material / critical writes

Применяется по умолчанию к:

- material writes
- business-critical writes
- authority-changing writes
- financial writes
- safety-relevant writes
- irreversible or difficult-to-reverse writes
- privileged actions
- high-impact external side effects

```
READ
  → ANALYZE
  → PROPOSE
  → HUMAN APPROVAL
  → AUTHORIZE TOOL
  → CONTROLLED WRITE
  → READ-BACK VERIFY
  → AUDIT
  → REVOKE
```

### Low-risk deterministic write exception

Per-action Human Approval **может** не требоваться **только если одновременно**:

- явно разрешено Security Tier / Risk Class;
- явно разрешено authority policy;
- явно разрешено tool permission;
- bounded scope;
- deterministic validation;
- auditable;
- reversible или operationally safe (где применимо);
- fail-closed on uncertainty;
- no silent privilege escalation.

Human approval **нельзя** обходить ради удобства или latency.

### High-risk default

Если классификация риска **неясна** → **FAIL CLOSED**.
Для material / critical writes Human Approval остаётся обязательным, пока authoritative security policy явно не определит другую одобренную модель контроля.

### Security Tier (classification only)

| Tier (EOS-SEC baseline) | Meaning |
|-------------------------|---------|
| `TIER_0_READ_ONLY_DETERMINISTIC` | No LLM, no product writes |
| `TIER_1_READ_ONLY_AI` | LLM may analyze; no product state change |
| `TIER_2_HUMAN_GATED_WRITE` | Narrow writes only after Human Gate |
| `TIER_3_PRIVILEGED_CROSS_SYSTEM` | Multi-system operational authority |
| `TIER_4_PHYSICAL_WORLD_ACTUATION` | Robots, drones, equipment |

Tier **не** выдаёт permission сам по себе.

---

## 21. Physical Actuation

**Applicability:** CONDITIONAL. Default = **NO physical actuation** → `NOT APPLICABLE` (не изобретайте geofence / kill switch / telemetry без реальной actuation).

### If enabled — corresponding governance becomes mandatory

| Field | Value |
|-------|--------|
| Command authority | `<...>` |
| Geofence / operating envelope / scope | `<...>` |
| Allowed mission | `<...>` |
| Precondition validation | `<...>` |
| Human authorization (per risk tier) | `<...>` |
| Kill switch / safe stop | `<...>` |
| Telemetry | `<...>` |
| Read-back confirmation | `<...>` |
| Post-action evidence | `<...>` |

Template requirement ≠ claim that Physical AI already exists in current Execution OS.

---

## 22. Runtime

### Purpose

Технология подчинена профессии, не наоборот.

### Required fields

| Field | Value |
|-------|--------|
| Runtime technology | `<...>` |
| Execution backend | `<thread / process / worker / other>` |
| Checkpointing | `<...>` |
| External state | `<...>` |
| Retry policy | `<...>` |
| Concurrency model | `<...>` |
| Pause / resume | `<...>` |
| Failure recovery | `<...>` |
| Idempotency | `<...>` |
| Durability classification | `<honest matrix, not "fully durable">` |

### Warning

Не выдавайте backend реализации за профессиональную идентичность.

---

## 23. Observability

### Reusable five-level model

| Level | Scope | What must be observable for this role? |
|-------|--------|----------------------------------------|
| **1** Digital Organization | transfer between roles | `<...>` |
| **2** Professional Agent Execution | what the employee did | `<...>` |
| **3** Professional Stage Detail | stages / tools / artifacts (safe) | `<...>` |
| **4** Human Decision | autonomy stop + decision | `<...>` |
| **5** Forensic Audit Trace | audit evidence | `<...>` |

---

## 24. Control Room

### Required classification

Choose one (or staged CURRENT → FUTURE):

| Mode | Meaning |
|------|---------|
| **Observe-only** | read surface only |
| **Human Decision Surface** | observe + submit decision through accepted contracts |
| **Authorized Control Surface** | requires explicit authority model |

### Law

UI **не** должен молча владеть runtime semantics.

---

## 25. Traceability

### Purpose

```
CAUSE → DECISION → ACTION → RESULT → HANDOFF
```

### Required correlation identities (as applicable)

run · mission · authorization · stage · tool call · interrupt · decision · artifact · handoff · physical mission (if any)

### Fill

| Identity | Required? | Owner |
|----------|-----------|--------|
| `<...>` | YES/NO | `<...>` |

---

## 26. Durability / Replay

### Required honest matrix

| Capability | Proven? | Backend | Evidence | Known Exception |
|------------|---------|---------|----------|-----------------|
| Observability durability | YES/NO/PARTIAL | `<...>` | `<...>` | `<...>` |
| Checkpoint durability | YES/NO/PARTIAL | `<...>` | `<...>` | `<...>` |
| Object restart | YES/NO/PARTIAL | `<...>` | `<...>` | `<...>` |
| Process restart | YES/NO/PARTIAL | `<...>` | `<...>` | `<...>` |
| Machine restart | YES/NO/PARTIAL | `<...>` | `<...>` | `<...>` |
| Worker restart | YES/NO/PARTIAL | `<...>` | `<...>` | `<...>` |
| Network interruption | YES/NO/PARTIAL | `<...>` | `<...>` | `<...>` |

### Warning

Запрещены generic claims: «fully durable», «полная отказоустойчивость доказана».

---

## 27. Immutable Facts

### Reusable law

Immutable professional fact must preserve **identity and semantics** across replay.

### Required

| Field | Value |
|-------|--------|
| Identity owner | `<...>` |
| Occurrence time owner | `<FIRST_OCCURRENCE / other>` |
| Replay semantics | `<SAME_IMMUTABLE_FACT / other>` |
| Conflict behavior | `<fail closed / other>` |

Optional reference pattern (not mandatory copy): first-occurrence clock ownership for wait/decision facts.

---

## 28. Routine removed from humans

### Required table

| Routine Today | Who Does It | Frequency | Agent Can Automate? | Human Still Required? | Expected Impact |
|---------------|-------------|-----------|---------------------|-----------------------|-----------------|
| `<...>` | `<...>` | `<...>` | YES/PARTIAL/NO | YES/NO | `<TARGET / PROVEN>` |

---

## 29. Human role after automation

### Purpose

Явно сохранить человеческую ответственность.

### Typical categories

authority · professional judgement · risk acceptance · exception handling · business priority · ethical/legal decision · physical safety

### Fill

| Human retains | Why |
|---------------|-----|
| `<...>` | `<...>` |

### Warning

Избегайте «человек удалён из процесса», если это не доказано и не оправдано.

---

## 30. Business Value

### Mandatory split

| Class | Content |
|-------|---------|
| **PROVEN VALUE** | `<только с evidence>` |
| **TARGET VALUE** | `<ожидаемый эффект, не измеренный>` |
| **UNPROVEN VALUE** | `<явно пометить как unproven / do not claim>` |

### Warning

Не вносите ROI / «ускорение в N раз» без измерений.

---

## 31. Economic Model

**Applicability:** Business Value classification (§30) is **mandatory**. Specific financial formulas are **CONDITIONAL**.

### Required future formulas when professionally meaningful (no invented numbers)

- Manual Hours Saved
- Cycle Time Reduction
- Error / Rework Reduction
- Human Escalation Rate
- Automation Coverage
- Cost per Mission
- Cost per Business Artifact — may be `N/A`
- Downstream Acceptance Rate — may be `N/A`
- Financial Value Protected — may be `N/A` if not meaningful

For each used formula: Definition · Formula · Source · Measured? YES/NO

Do NOT force fake financial models.

---

## 32. Professional KPIs

### Organize by

QUALITY · SPEED · AUTONOMY · HUMAN LOAD · TRACEABILITY · SECURITY · BUSINESS EFFECT

### Required per KPI

| Field | Value |
|-------|--------|
| Definition | `<...>` |
| Formula | `<...>` |
| Source | `<...>` |
| Target | `<...>` |
| Currently measured? | YES / NO |

---

## 33. Success per Mission

### Require explicit law

Миссия успешна, если:

| Dimension | Required? | Criterion |
|-----------|-----------|-----------|
| Scope respected | YES | `<...>` |
| Required evidence present | YES | `<...>` |
| Correct artifact produced OR formal justified stop | YES | `<...>` |
| Required Human Gate used | CONDITIONAL | `<...>` |
| Handoff persisted (if completion requires it) | CONDITIONAL | `<...>` |
| Trace complete | YES | `<...>` |
| Security preserved | YES | `<...>` |

---

## 34. Failure Conditions

### Mandatory failures

- scope escape
- unauthorized action
- fabricated evidence
- untraceable decision
- silent ambiguity
- false completion
- secret leak
- unsafe write
- unsafe physical action

### Profession-specific failures

`<добавить>`

---

## 35. Professional Scenarios

### Mandatory minimum

1. Happy Path
2. Input / Professional Failure Path
3. Security / Denial Path
4. One profession-specific edge case

### Conditional scenarios (complete if applicable; else `N/A`)

- Human Decision Path
- Handoff Failure Path
- Write Failure Path
- Physical Actuation Safety Path

### Each scenario form

```
Input Reality
  → Professional Action
  → Gate
  → Artifact
  → Outcome
```

---

## 36. Difference from Chatbot

Digital employee has:

Role · Mission · Scope · Skills · Tools · Permissions · State · Lifecycle · Human Gates · Artifacts · Handoff · Security · Observability · Tests

Fill: `<1–2 предложения, почему роль не chatbot>`

---

## 37. Difference from Script

Mandatory criteria present? (YES / NO / N/A where concept does not apply)

| Criterion | Present? |
|-----------|----------|
| Conditional lifecycle | YES/NO |
| State | YES/NO |
| Exceptions | YES/NO |
| Human interruption | YES/NO/N/A |
| Resume | YES/NO/N/A |
| External truth | YES/NO |
| Handoff | YES/NO/N/A |
| Security | YES/NO |
| Observability | YES/NO |

---

## 38. Difference from Orchestrator

| Orchestrator | Specialized Professional Agent |
|--------------|--------------------------------|
| Coordinates roles / missions | Performs one specialized profession |
| Owns coordination responsibility | Owns professional responsibility |

### Law

Specialized professional role **≠** orchestrator-as-superuser.
Не схлопывайте несколько профессий в супер-агента.

### Orchestrator may have its own Passport

Если orchestration / coordination — **distinct professional responsibility** с:

- own mission
- own scope
- own authority
- own lifecycle
- own business / coordination result
- own observability

то Orchestrator **может** иметь собственный Professional Passport.

Это **не** разрешает Orchestrator становиться superuser или поглощать все профессии.

---

## 39. Difference from Human Profession

Digital employee:

- **не** обязан клонировать каждый человеческий ритуал;
- **обязан** сохранять: professional responsibility, decision boundaries, required evidence, business outcome;
- может реорганизовать рутину эффективнее существующего human workflow.

---

## 40. Organizational Layer

| Field | Value |
|-------|--------|
| **PRIMARY ORGANIZATIONAL LAYER** | Production / Design / Platform |
| **OPTIONAL SECONDARY INTERACTIONS** | `<другие слои / NONE>` |

| Layer | Meaning |
|-------|---------|
| **PRODUCTION TEAM / Производственная** | прямое влияние на производство / исполнение |
| **DESIGN TEAM / Проектировочная** | проектирование планов, допусков, решений до исполнения |
| **PLATFORM TEAM / Платформенная** | runtime, security, observability, shared platform |

У роли должна быть **одна primary** организационная идентичность.
Запрещено: «belongs everywhere». Secondary interactions — явно перечислить.

---

## 41. Current vs Future

### Mandatory status vocabulary (do not interchange)

| Status | Meaning |
|--------|---------|
| **CURRENT / PROVEN** | implemented and evidenced |
| **TARGET / FUTURE** | intended architecture, not yet proven |
| **NOT IN SCOPE** | explicitly excluded from this role/version |
| **NOT APPLICABLE / N/A** | concept does not apply to this profession/version |

### Mandatory capability table

| Capability | CURRENT / PROVEN | TARGET / FUTURE | NOT IN SCOPE | N/A |
|------------|------------------|-----------------|--------------|-----|
| `<...>` | ☐ | ☐ | ☐ | ☐ |

### Warning

Никакая future-capability не должна быть написана как current.
`N/A` ≠ `TARGET / FUTURE`.

---

## 42. Versioning

### Required versions (where relevant)

| Version | Value |
|---------|--------|
| Passport Version | `<...>` |
| Professional Role Version | `<...>` |
| Runtime Version | `<...>` |
| Artifact Contract Version | `<...>` |
| Security Policy Version | `<...>` |

### Passport version must change when

- responsibility changes
- authority changes
- new write capability
- new physical action
- new artifact
- new handoff semantics
- new professional skill that changes profession

Bug fixes without profession change may keep Passport professional version, but must preserve contracts/tests.

---

## 43. Technical Proof (appendix)

### Concise evidence only — no test dump

Proof must be **risk-based**: требуйте evidence, соответствующее responsibility и risk tier. Не требуйте нерелевантные категории.

| Role class | Typical additional proof |
|------------|--------------------------|
| Read-only | read / security / artifact / full-run (as applicable) |
| Write-capable | authorization · write · read-back · audit |
| Physical | safety · actuation · telemetry · safe-stop |
| Human Gate | interruption · resume · governance |

| Evidence class | Present? | Reference |
|----------------|----------|-----------|
| Unit / contract tests | YES/NO / N/A | `<...>` |
| Integration tests | YES/NO / N/A | `<...>` |
| Full managed live run | YES/NO / N/A | `<...>` |
| Durability test | YES/NO / EXCEPTION / N/A | `<...>` |
| Security gate | YES/NO | `<...>` |
| Architecture review | YES/NO | `<...>` |
| Human Gate proof | YES/NO / N/A | `<...>` |
| Handoff proof | YES/NO / N/A | `<...>` |
| Write / read-back proof | YES/NO / N/A | `<...>` |
| Physical safety proof | YES/NO / N/A | `<...>` |

---

## 44. Digital Employee Completion Checklist

- [ ] Role
- [ ] Professional Responsibility
- [ ] Mission
- [ ] Scope
- [ ] Skills
- [ ] Tools
- [ ] Shared Capabilities
- [ ] Permissions
- [ ] Security
- [ ] Contracts
- [ ] State
- [ ] Lifecycle
- [ ] Human Decision Gates
- [ ] Business Artifacts
- [ ] Handoff
- [ ] Completion Law
- [ ] Runtime
- [ ] Observability
- [ ] Durability
- [ ] Tests
- [ ] Full Professional Proof
- [ ] Business KPI Model
- [ ] Professional Passport

---

## 45. Completion Levels (maturity)

| Level | Meaning |
|------:|---------|
| **0** | Role Defined |
| **1** | Professional Contracts Defined |
| **2** | Deterministic Core Implemented |
| **3** | Tools + Security Implemented |
| **4** | Lifecycle Implemented |
| **5** | Human Gates Implemented *(or legitimate N/A)* |
| **6** | Business Artifact / Formal Outcome Implemented |
| **7** | Handoff Implemented *(or legitimate N/A)* |
| **8** | Durability / Resume Implemented *(as applicable)* |
| **9** | Observability / Control Room Implemented |
| **10** | Full Managed Professional Proof |

Levels = **maturity guidance**, not mandatory identical increment sequence.

Legitimate **N/A** conditional capabilities **do not** block Level 10.
Example: read-only agent does **not** need Physical Actuation to be Level 10.

**Level 10** = full managed professional proof **within approved scope** — not “perfect / fully autonomous / enterprise-complete / production-at-scale”.

---

## 46. Agent Creation Gate

Перед созданием нового агента ответьте:

| Question | YES / NO |
|----------|----------|
| Distinct professional responsibility? | |
| Distinct business artifact / formal outcome? | |
| Distinct lifecycle? | |
| Independent permissions / authority boundary? | |
| Meaningful handoff boundary (if applicable)? | |

Если в основном **NO** → создайте **Skill / Service / Capability**, не нового агента.

Capability **не** становится агентом только потому, что есть:

- separate code
- separate model call
- separate graph node
- separate API
- reusable logic

**Primary gate:** distinct professional responsibility.

Это защита от micro-agent sprawl.

---

## 47. Professional Change Gate

Перед добавлением capability в существующего агента:

| Question | YES / NO |
|----------|----------|
| Belongs to this profession? | |
| Changes authority? | |
| Changes artifact? | |
| Changes handoff? | |
| Creates another professional responsibility? | |

Если есть существенные **YES** → требуется architecture review.

---

## 48. Closing statement (fill)

`<Краткое профессиональное заключение: кем является роль, что доказано сейчас, что остаётся FUTURE, какой следующий шаг. Без маркетинга.>`

---

**End of PROFESSIONAL_PASSPORT_TEMPLATE_V1_0**
