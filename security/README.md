# Agent Security & Confidentiality — Execution OS

**Status:** MANDATORY SECURITY LAW / RELEASE REQUIREMENT
**Policy version:** `EOS-SEC-1.0` / `EOS-SEC-1.1` / `EOS-SEC-1.2`
**Applies to:** all specialized agents, orchestrators, future LLM agents, write-enabled agents, external-system agents, and (future) physical actuation agents.

## Two complementary standards

| Standard | Role | Location |
|----------|------|----------|
| Lessons_2 | Agent engineering methodology (roles, skills, tools, HITL, layered architecture) | External READ-ONLY: `C:\Users\Андрей\lesson_2` |
| Agent Security & Confidentiality Baseline | Security law for trust, tools, data, writes, audit, **execution isolation** | This directory (`security/`) |

Neither replaces the other. An agent is **not** production-ready until **all** gates pass:

1. Functional Tests
2. Regression Tests
3. Lessons_2 Methodology Gate
4. **Agent Security & Confidentiality Gate**

**LESSONS_2 LIVE SECURITY ISOLATION AUDIT:** `NOT_LIVE_VERIFIED`
Do not claim Execution Isolation Layer is live-proven by Lessons_2 unless that audit is recorded. Isolation law remains compatible with Lessons_2 principles (narrow tools, permissions, HITL, external state, structured outputs, safe writes, audit). Do **not** modify `lesson_2`.

## Core principles (EOS-SEC-1.2)

> **LLM IS NOT A SECURITY BOUNDARY.**
> **AGENT RUNTIME IS NOT THE SOLE SECURITY BOUNDARY.**
> **TOOL / MCP WRAPPER IS NOT THE SOLE SECURITY BOUNDARY.**
> **MODEL IS NEVER CREDENTIAL HOLDER.**

> **Execution Isolation Layer DOES NOT REPLACE EOS-SEC.**

LLM / agent reasoning is not authorization. System prompts are not sufficient protection. Enforcement is deterministic and outside the model: permissions, tool allowlists, authn/authz, RLS, human gates, validators, schemas, rate limits, write policies, **execution isolation**, audit, kill switch, trusted execution context, capability / tool broker.

Canonical chain:

```
HUMAN / POLICY AUTHORITY
  → AGENT / LANGGRAPH RUNTIME
  → CAPABILITY / TOOL BROKER
  → EXECUTION ISOLATION LAYER
  → EXTERNAL SYSTEMS / PHYSICAL WORLD
```

Three independent boundaries: **EXECUTION (WHERE)** · **CAPABILITY (WHAT)** · **AUTHORITY (MAY FINALIZE)**.
Laws: **CAPABILITY ≠ AUTHORITY** · **AGENT RECEIVES A CAPABILITY, NOT INFRASTRUCTURE POWER** · **DATA IS NOT INSTRUCTION**.

Isolation strength is **risk-tier appropriate**. microVM is **not** required for every agent. Tier 0 host-process isolation may be **explicitly DEFERRED** only while risk is low and documented. OS sandbox / container / microVM / kill switch / one-shot escalation / durable denied-event store are **not** claimed as implemented unless a specific agent profile proves them.

## Documents in this package

| File | Purpose |
|------|---------|
| [agent_security_baseline.md](agent_security_baseline.md) | Master baseline: tiers, isolation layer, three boundaries, compromised-model gate, physical safety-controller law, universal contract |
| [trust_and_instruction_policy.md](trust_and_instruction_policy.md) | Trust levels, DATA ≠ INSTRUCTION, provenance |
| [tool_and_permission_policy.md](tool_and_permission_policy.md) | Least privilege, allowlists, R/W separation, capability ≠ authority, controlled write, MCP law |
| [data_confidentiality_policy.md](data_confidentiality_policy.md) | Classification, minimization, secrets, trace redaction |
| [security_release_gate.md](security_release_gate.md) | SECURITY_GATE PASS/FAIL and release rule |

Do **not** create a parallel “security bible.” Extend these documents.

## Per-agent requirements

Every agent package under `agents/<agent>/` with `runtime` + `specification` **must** provide:

- `specification/security.md` — human-readable security profile (including Execution / Capability / Authority boundaries; N/A or DEFERRED where applicable)
- `specification/security_manifest.json` — machine-readable gate input

Automated check: `tests/test_agent_security_governance.py`

Universal pre-implementation contract fields: IDENTITY · MISSION · INPUT AUTHORITY · CAPABILITIES · FORBIDDEN CAPABILITIES · EXECUTION / NETWORK / DATA / WRITE / AUTHORITY BOUNDARIES · HUMAN GATES · ESCALATION · SECRETS MODEL · AUDIT · VERIFICATION · KILL SWITCH (see baseline §10).

## Non-goals of this foundation / docs checkpoint

- Do not create DB security event tables yet.
- Do not implement kill-switch UI yet.
- Do not implement OS sandbox / container / microVM in this docs-only checkpoint.
- Do not implement one-shot escalation yet.
- Do not change business logic of existing agents unless a **critical** vulnerability is found (then STOP and report).
- Do not modify `lesson_2`.
