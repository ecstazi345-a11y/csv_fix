# Agent Security & Confidentiality — Execution OS

**Status:** MANDATORY SECURITY LAW / RELEASE REQUIREMENT  
**Policy version:** `EOS-SEC-1.0`  
**Applies to:** all specialized agents, orchestrators, future LLM agents, write-enabled agents, external-system agents, and (future) physical actuation agents.

## Two complementary standards

| Standard | Role | Location |
|----------|------|----------|
| Lessons_2 | Agent engineering methodology (roles, skills, tools, HITL, layered architecture) | External READ-ONLY: `C:\Users\Андрей\lesson_2` |
| Agent Security & Confidentiality Baseline | Security law for trust, tools, data, writes, audit | This directory (`security/`) |

Neither replaces the other. An agent is **not** production-ready until **all** gates pass:

1. Functional Tests  
2. Regression Tests  
3. Lessons_2 Methodology Gate  
4. **Agent Security & Confidentiality Gate**

## Core principle

> **MODEL IS NOT A SECURITY BOUNDARY.**

LLM / agent reasoning is not authorization. System prompts are not sufficient protection. Enforcement is deterministic and outside the model: permissions, tool allowlists, authn/authz, RLS, human gates, validators, schemas, rate limits, write policies, sandboxing, audit, kill switch.

## Documents in this package

| File | Purpose |
|------|---------|
| [agent_security_baseline.md](agent_security_baseline.md) | Master baseline: tiers, controls, patterns |
| [trust_and_instruction_policy.md](trust_and_instruction_policy.md) | Trust levels, DATA ≠ INSTRUCTION, provenance |
| [tool_and_permission_policy.md](tool_and_permission_policy.md) | Least privilege, allowlists, R/W separation, controlled write |
| [data_confidentiality_policy.md](data_confidentiality_policy.md) | Classification, minimization, secrets, trace redaction |
| [security_release_gate.md](security_release_gate.md) | SECURITY_GATE PASS/FAIL and release rule |

## Per-agent requirements

Every agent package under `agents/<agent>/` with `runtime` + `specification` **must** provide:

- `specification/security.md` — human-readable security profile  
- `specification/security_manifest.json` — machine-readable gate input  

Automated check: `tests/test_agent_security_governance.py`

## Non-goals of this foundation stage

- Do not create DB security event tables yet.  
- Do not implement kill-switch UI yet.  
- Do not change business logic of existing agents unless a **critical** vulnerability is found (then STOP and report).  
- Do not modify `lesson_2`.
