# Agent Security & Confidentiality Baseline

**Policy version:** `EOS-SEC-1.0` / `EOS-SEC-1.1`  
**Binding:** SECURITY LAW for Execution OS agents and orchestrators.

---

## 1. Fundamental principle

**MODEL IS NOT A SECURITY BOUNDARY.**

**MODEL IS NEVER CREDENTIAL HOLDER.**

- LLM / agent reasoning ≠ authorization  
- System prompt ≠ sufficient protection  
- Enforcement lives in deterministic mechanisms **outside** the model:

permissions · tool allowlists · authentication · authorization · RLS · human gates · validators · schemas · rate limits · write policies · sandboxing · audit · kill switch · **trusted execution context** · **server-side tool executor**

Even if the model receives a hostile instruction, it must **not** have technical capability to exceed granted powers.

### Effective permission (EOS-SEC-1.1)

```
EFFECTIVE PERMISSION
  = AUTHORITY SCOPE
  ∩ AGENT PERMISSION
  ∩ PROJECT SCOPE
  ∩ TOOL POLICY
  ∩ ACTION AUTHORIZATION
```

---

## 2. Risk tiers (mandatory classification)

| Tier | Code | Meaning | Example |
|------|------|---------|---------|
| 0 | `TIER_0_READ_ONLY_DETERMINISTIC` | No LLM, no product writes | MPCA-001 |
| 1 | `TIER_1_READ_ONLY_AI` | LLM may analyze; no product state change | future analyzers |
| 2 | `TIER_2_HUMAN_GATED_WRITE` | Narrow writes only after Human Gate | future MPCA-002 |
| 3 | `TIER_3_PRIVILEGED_CROSS_SYSTEM` | Multi-system operational authority | future integrations |
| 4 | `TIER_4_PHYSICAL_WORLD_ACTUATION` | Robots, drones, equipment | future physical AI |

Higher tier ⇒ stricter Security Gate. Tier 4 requires command allowlists, safety envelopes, emergency stop, command signing, safe-state fallback (**specify now, implement later**).

---

## 3. Release requirement

```
SECURITY_GATE: PASS | FAIL
```

If `SECURITY_GATE != PASS`, agent is **not** RELEASE READY — even when functional, regression, and Lessons_2 gates pass.

See [security_release_gate.md](security_release_gate.md).

---

## 4. Control catalog (summary)

| Control | Requirement |
|---------|-------------|
| Trust model | Explicit levels 0–4; policy cannot be overridden by data or peer agents |
| Prompt injection | DATA ≠ INSTRUCTION; external text is untrusted data |
| Instruction provenance | Critical actions must answer who/what/source/trust/when/authorized/policy/tool/result |
| Least privilege | Minimal tools and tables; no universal SQL/shell/HTTP/filesystem |
| Tool allowlist | Only declared tools callable |
| Read/Write separation | No polymorphic `database_tool(action=...)` |
| Controlled write | READ→ANALYZE→PROPOSE→HUMAN→AUTHORIZE→WRITE→VERIFY→AUDIT→CLOSE |
| Human gates | High-risk ops gated in **code**, not prompt text |
| Secrets | Never in prompts, memory, runs, traces, logs, RAG, errors |
| Supabase | Prefer scoped roles/RLS; service role never given to the model |
| Data classification | PUBLIC / INTERNAL / CONFIDENTIAL / RESTRICTED (+ SECRET for credentials) |
| Data minimization | Only needed fields |
| Output security | Model output never direct→SQL/shell/write/robot; schema→validate→policy→gate→executor |
| Trace confidentiality | Redaction before logging |
| Fail closed | Undefined permission / unknown tool / missing gate / bad schema → DENY |
| Rate limits | Cap rows/writes/calls/retries/external sends (write-enabled) |
| Kill switch | External disable / revoke write / stop run / block tool (write/action agents) |
| Audit trail | Critical actions fully auditable |
| Security events | Architecture for cockpit events; DB logging later |
| Agent-to-agent | Handoff does not expand recipient permissions |
| Orchestrator | Coordinates; is **not** superuser / sum of all agent powers |

Detail documents:

- [trust_and_instruction_policy.md](trust_and_instruction_policy.md)  
- [tool_and_permission_policy.md](tool_and_permission_policy.md)  
- [data_confidentiality_policy.md](data_confidentiality_policy.md)

---

## 5. Security testing categories

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

Plus automated governance: `tests/test_agent_security_governance.py`.

---

## 6. Future physical AI (Tier 4) — mandatory standard, not implemented yet

Command allowlists · physical safety envelopes · speed/zone limits · emergency stop · human authorization · device identity · command signing · telemetry verification · safe-state fallback.

---

## 7. Relationship to Lessons_2

Lessons_2 = how to engineer agents.  
This baseline = how agents are allowed to act safely.  
Both are required.
