# Agent Security & Confidentiality Baseline

**Policy version:** `EOS-SEC-1.0` / `EOS-SEC-1.1` / `EOS-SEC-1.2`
**Binding:** SECURITY LAW for Execution OS agents and orchestrators.

**Status labels used in this baseline:**

| Label | Meaning |
|-------|---------|
| CURRENTLY IMPLEMENTED | Enforced in code / config today |
| ARCHITECTURAL REQUIREMENT | Binding law; must be designed for |
| DEFERRED FUTURE ENFORCEMENT | Required later; not claimed as live |

---

## 1. Fundamental principles (EOS-SEC-1.2)

### 1.1 LLM / runtime / tool wrapper are not sole boundaries

**LLM IS NOT A SECURITY BOUNDARY.**

**AGENT RUNTIME IS NOT THE SOLE SECURITY BOUNDARY.**

**TOOL / MCP WRAPPER IS NOT THE SOLE SECURITY BOUNDARY.**

**MODEL IS NEVER CREDENTIAL HOLDER.**

Security design **assumes** that:

- the model may fail;
- the model may be prompt-injected;
- orchestration may contain defects;
- tool routing may contain defects;
- untrusted input may attempt to influence execution.

Security **cannot** depend on correct model behavior.

Enforcement lives in deterministic mechanisms **outside** the model:

permissions · tool allowlists · authentication · authorization · RLS · human gates · validators · schemas · rate limits · write policies · **execution isolation** · audit · kill switch · **trusted execution context** · **server-side tool / capability broker**

Even if the model receives a hostile instruction, it must **not** have technical capability to exceed granted powers.

### 1.2 Defense-in-depth — Execution Isolation does **not** replace EOS-SEC

**Execution Isolation Layer DOES NOT REPLACE EOS-SEC.**

EOS-SEC remains mandatory. Isolation is an **additional** lower layer. The following remain binding:

least privilege · narrow capabilities · read/write separation · HITL · structured outputs · validation · RLS · project/tenant isolation · secret management · audit · provenance · rate limits · transaction limits · controlled write · write → verify · prompt injection protection · kill switch · permission revocation · data minimization · log redaction · fail-closed · no universal SQL/exec · no execution of instructions from untrusted data

### 1.3 Effective permission (EOS-SEC-1.1)

```
EFFECTIVE PERMISSION
  = AUTHORITY SCOPE
  ∩ AGENT PERMISSION
  ∩ PROJECT SCOPE
  ∩ TOOL POLICY
  ∩ ACTION AUTHORIZATION
  ∩ EXECUTION ISOLATION (WHERE the process may act)
```

---

## 2. Canonical security chain (EOS-SEC-1.2)

```
HUMAN / POLICY AUTHORITY
        ↓
AGENT / LANGGRAPH RUNTIME
        ↓
CAPABILITY / TOOL BROKER
        ↓
EXECUTION ISOLATION LAYER
        ↓
EXTERNAL SYSTEMS / PHYSICAL WORLD
```

| Layer | Role | Sole boundary? |
|-------|------|----------------|
| Human / policy authority | What may be finalized | No |
| Agent / LangGraph runtime | Orchestration / reasoning | **No** |
| Capability / tool broker | What actions are callable | **No** |
| Execution Isolation Layer | Where / how the environment can act | **No** |
| External systems / physical world | Effects | — |

---

## 3. Three independent boundaries

### A. EXECUTION BOUNDARY — WHERE

Where the agent is **technically able** to act.

Examples: process · workspace · filesystem paths · network endpoints · database · project / tenant · namespace.

Enforced preferably by OS / runtime / network / identity isolation (see §4), not by prompt text.

### B. CAPABILITY BOUNDARY — WHAT

Which actions the agent may perform.

Prefer **narrow business capabilities**, e.g.:

- `read_project_context()`
- `create_candidate_package()`
- `persist_execution_event()`
- `request_executability_review()`
- `write_approved_plan()`

Do **not** grant without proven necessity:

- arbitrary shell / SQL / filesystem write
- generic HTTP client
- unrestricted MCP
- generic database mutation
- infrastructure admin capabilities

**Canonical law:**
**AGENT RECEIVES A CAPABILITY, NOT INFRASTRUCTURE POWER.**

### C. AUTHORITY BOUNDARY — MAY FINALIZE

What the agent may lock as an **authoritative** decision.

**Canonical law:**
**CAPABILITY ≠ AUTHORITY.**

Technical ability to perform an operation does **not** mean the right to finalize:

money · contract · procurement · schedule commitment · commercial recognition · physical actuation · safety-critical action

---

## 4. Execution Isolation Layer (EOS-SEC-1.2)

**Status:** ARCHITECTURAL REQUIREMENT for all agents.
**CURRENTLY IMPLEMENTED as OS sandbox / container / microVM:** **NO** (ABSENT for current Tier 0 Constructor; see per-agent security profiles).
**DEFERRED FUTURE ENFORCEMENT:** risk-tier appropriate (see §5).

The Execution Isolation Layer provides **technically enforced** isolation of the execution environment. Possible mechanisms (select by risk; **not** all required for every agent):

- process isolation
- restricted OS identity
- filesystem isolation
- network isolation / controlled egress
- secrets isolation
- CPU / memory quotas
- execution timeout
- container / sandbox / microVM **where risk requires**
- no host access by default
- no inherited credentials by default
- fail-closed when **required** isolation cannot be applied

**Important:** microVM is **not** mandatory for every agent. Isolation strength must be **risk-tier appropriate**.

Do **not** claim OS sandbox, network firewall, restricted OS user, container, or microVM are implemented unless proven in that agent’s profile.

---

## 5. Risk tiers and tiered isolation

| Tier | Code | Meaning | Example |
|------|------|---------|---------|
| 0 | `TIER_0_READ_ONLY_DETERMINISTIC` | No LLM, no product writes | MPCA-001 |
| 1 | `TIER_1_READ_ONLY_AI` | LLM may analyze; no product state change | future analyzers |
| 2 | `TIER_2_HUMAN_GATED_WRITE` | Narrow writes only after Human Gate | future MPCA-002 |
| 3 | `TIER_3_PRIVILEGED_CROSS_SYSTEM` | Multi-system operational authority | future integrations |
| 4 | `TIER_4_PHYSICAL_WORLD_ACTUATION` | Robots, drones, equipment | future physical AI |

Higher tier ⇒ stricter Security Gate and stronger isolation expectations.

### Tiered isolation minimum (EOS-SEC-1.2)

**TIER 0 / READ-ORIENTED**

- narrow capabilities
- no product writes
- no arbitrary shell / SQL
- scoped data access
- fail-closed
- **host-process isolation gap may be explicitly DEFERRED** only while risk remains low **and** documented in the agent security profile

**WRITE / ACTION TIER (Tier ≥ 2) — before product writes**

Require:

- stronger execution isolation
- kill switch
- durable security audit
- scoped authorization
- controlled write
- verify-after-write
- revocation path

**PRIVILEGED / PHYSICAL TIER (Tier 3–4)**

May require:

- hardened sandbox / container / microVM
- strict egress
- dedicated identity
- stronger secrets isolation
- independent physical safety controller

---

## 6. Compromised-model acceptance test (mandatory)

For every **new** or **materially changed** agent, answer:

> If the model/runtime is fully compromised and attempts to abuse every capability available to it, what is the maximum damage it can technically cause?

**Unacceptable answers:** “the model must not do this” / policy-only assurances.

**Acceptable answers** cite **technical** enforcement, e.g.:

capability absent · OS denies · identity denies · RLS denies · network denies · scope restriction · human authorization · policy broker rejection · transaction limit · write verification · privilege expiration · safety controller

---

## 7. DATA IS NOT INSTRUCTION

**Canonical law (reinforced):**
**DATA IS NOT INSTRUCTION.**

Untrusted data **cannot** grant: capability · authority · credentials · permissions · network access · tool access.

Instructions embedded in documents, emails, source data, project records, or external API responses remain **untrusted data** unless elevated by trusted policy / human authority.

Detail: [trust_and_instruction_policy.md](trust_and_instruction_policy.md).

---

## 8. Capability escalation model (future)

**Status:** ARCHITECTURAL REQUIREMENT for write/privileged agents.
**CURRENTLY IMPLEMENTED:** NO.
**For Tier 0 Constructor:** DEFERRED.

Normative flow:

```
DENIED
  → STRUCTURED ESCALATION REQUEST
  → REASON · REQUESTED CAPABILITY · SCOPE · EXPECTED EFFECT · RISK
  → HUMAN / POLICY GATE
  → ONE-SHOT OR SHORT-LIVED AUTHORIZATION
  → EXECUTION
  → VERIFY
  → AUTOMATIC PRIVILEGE DROP
```

**Canonical law:**
**ONE APPROVAL MUST NOT CREATE PERMANENT PRIVILEGE.**

Prefer: one-shot · operation-scoped · short-lived token · narrow resource scope · automatic expiry.

Do **not** implement this mechanism in the EOS-SEC-1.2 documentation checkpoint.

---

## 9. MCP / tool server security law

**MCP IS NOT AUTOMATICALLY A SECURITY BOUNDARY.**

Before any agent uses an MCP / tool server, define at least:

identity · permissions · read/write scope · resource scope · allowed operations · argument constraints · network scope · secrets exposure · rate limits · transaction limits · audit · destructive actions · human approval · verify-after-write

Universal / unrestricted MCP surfaces must not be used without proven necessity.

**Current Constructor / Agent Runtime:** MCP not in use (record per agent if that changes).

---

## 10. Universal Agent Security Contract (pre-implementation)

Before implementing a new agent, the security profile **must** explicitly define:

| Field | Required |
|-------|----------|
| IDENTITY | Yes |
| MISSION | Yes |
| INPUT AUTHORITY | Yes |
| CAPABILITIES | Yes |
| FORBIDDEN CAPABILITIES | Yes |
| EXECUTION BOUNDARY | Yes |
| NETWORK BOUNDARY | Yes |
| DATA BOUNDARY | Yes |
| WRITE BOUNDARY | Yes |
| AUTHORITY BOUNDARY | Yes |
| HUMAN GATES | Yes |
| ESCALATION | Yes (or N/A / DEFERRED) |
| SECRETS MODEL | Yes |
| AUDIT | Yes |
| VERIFICATION | Yes |
| KILL SWITCH | Yes (or N/A / DEFERRED for Tier 0) |

If a field is not applicable, it must be **explicit N/A / DEFERRED**, not silently omitted.

---

## 11. Release requirement

```
SECURITY_GATE: PASS | FAIL
```

If `SECURITY_GATE != PASS`, agent is **not** RELEASE READY — even when functional, regression, and Lessons_2 gates pass.

See [security_release_gate.md](security_release_gate.md).

---

## 12. Control catalog (summary)

| Control | Requirement |
|---------|-------------|
| Trust model | Explicit levels 0–4; policy cannot be overridden by data or peer agents |
| Prompt injection | DATA ≠ INSTRUCTION; external text is untrusted data |
| Instruction provenance | Critical actions must answer who/what/source/trust/when/authorized/policy/tool/result |
| Least privilege | Minimal tools and tables; no universal SQL/shell/HTTP/filesystem |
| Capability ≠ authority | Technical ability ≠ right to finalize |
| Capability ≠ infrastructure power | Narrow business tools, not admin primitives |
| Tool allowlist | Only declared tools callable |
| Read/Write separation | No polymorphic `database_tool(action=...)` |
| Controlled write | READ→ANALYZE→PROPOSE→HUMAN→AUTHORIZE→WRITE→VERIFY→AUDIT→CLOSE |
| Human gates | High-risk ops gated in **code**, not prompt text |
| Execution isolation | Risk-tier appropriate WHERE enforcement; Tier 0 gap may be DEFERRED if documented |
| Secrets | Never in prompts, memory, runs, traces, logs, RAG, errors |
| Supabase | Prefer scoped roles/RLS; service role never given to the model; transitional privileged reads must not expand silently |
| Data classification | PUBLIC / INTERNAL / CONFIDENTIAL / RESTRICTED (+ SECRET for credentials) |
| Data minimization | Only needed fields |
| Output security | Model output never direct→SQL/shell/write/robot; schema→validate→policy→gate→executor |
| Trace confidentiality | Redaction before logging |
| Fail closed | Undefined permission / unknown tool / missing gate / bad schema → DENY |
| Rate limits | Cap rows/writes/calls/retries/external sends (write-enabled) |
| Kill switch | External disable / revoke write / stop run / block tool (write/action agents) |
| Audit trail | Critical actions fully auditable |
| Security events | Architecture for cockpit events; durable DB logging later (DEFERRED) |
| Escalation | Structured one-shot / short-lived (DEFERRED until write agents) |
| Agent-to-agent | Handoff does not expand recipient permissions |
| Orchestrator | Coordinates; is **not** superuser / sum of all agent powers |
| Compromised-model test | Maximum technical damage must be stated with enforcement evidence |

Detail documents:

- [trust_and_instruction_policy.md](trust_and_instruction_policy.md)
- [tool_and_permission_policy.md](tool_and_permission_policy.md)
- [data_confidentiality_policy.md](data_confidentiality_policy.md)

---

## 13. Security testing categories

Every agent must pass relevant security tests (subset for Tier 0):

1. Direct prompt injection
2. Indirect prompt injection
3. Malicious document instruction
4. Tool escalation attempt
5. Unauthorized write attempt
6. Data exfiltration attempt
7. Secret leakage
8. Cross-agent privilege escalation
9. Malformed structured output
10. Replay / duplicate action
11. Excessive batch action
12. Fail-closed behavior
13. Log/trace leakage
14. Unauthorized table/data access
15. Compromised-model maximum-damage review (§6)

Plus automated governance: `tests/test_agent_security_governance.py`.

---

## 14. Future physical AI (Tier 4) — architecture law, not implemented

**Status:** ARCHITECTURAL REQUIREMENT. **CURRENTLY IMPLEMENTED:** NO.

Target chain:

```
LLM
  → AGENT RUNTIME
  → CAPABILITY BROKER
  → EXECUTION ISOLATION
  → INDEPENDENT SAFETY CONTROLLER
  → PLC / ROBOT / DRONE / MACHINE
  → PHYSICAL WORLD
```

**Canonical rule:**
**INDEPENDENT SAFETY CONTROLLER MAY REJECT A COMMAND REGARDLESS OF LLM / AGENT / ORCHESTRATOR DECISION.**

**LLM MUST NEVER BE THE FINAL SAFETY BARRIER BEFORE PHYSICAL ACTION.**

Also specify (implement later): command allowlists · physical safety envelopes · speed/zone limits · emergency stop · human authorization · device identity · command signing · telemetry verification · safe-state fallback.

---

## 15. Relationship to Lessons_2

Lessons_2 = how to engineer agents.
This baseline = how agents are allowed to act safely.
Both are required.

**LESSONS_2 LIVE SECURITY ISOLATION AUDIT:** `NOT_LIVE_VERIFIED`

Do not claim that Execution Isolation Layer law is proven by a live Lessons_2 isolation audit unless that audit is performed and recorded.

The isolation law is **compatible** with previously accepted Lessons_2 principles: narrow tools · permissions · HITL · external state · structured outputs · safe writes · audit.

Do **not** modify `lesson_2` / `LESSON_2` from Execution OS security work.
