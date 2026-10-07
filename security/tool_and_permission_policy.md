# Tool & Permission Policy

**Policy version:** `EOS-SEC-1.0` / `EOS-SEC-1.2`

Complements [agent_security_baseline.md](agent_security_baseline.md).
Does **not** replace EOS-SEC or the Execution Isolation Layer — tools and permissions are the **capability** plane (WHAT), not the sole security boundary.

---

## 1. Capability vs infrastructure power

**Canonical law:**
**AGENT RECEIVES A CAPABILITY, NOT INFRASTRUCTURE POWER.**

Prefer narrow **business** capabilities, e.g.:

- `read_project_context()`
- `create_candidate_package()`
- `persist_execution_event()`
- `request_executability_review()`
- `write_approved_plan()`

Do **not** grant without proven necessity:

- arbitrary shell / terminal
- arbitrary SQL
- generic filesystem write
- generic HTTP / REST client
- unrestricted MCP / API surface
- generic database mutation
- infrastructure admin (e.g. GitHub admin, unrestricted cloud console)

---

## 2. Capability ≠ Authority

**Canonical law:**
**CAPABILITY ≠ AUTHORITY.**

A tool on the allowlist enables a **technical** action. It does **not** by itself authorize finalization of:

money · contract · procurement · schedule commitment · commercial recognition · physical actuation · safety-critical action

Authority requires the applicable Human / Policy gate (and, for Tier ≥ 2, controlled-write + verify path).

---

## 3. Least privilege

Each agent receives the **minimum** rights needed for its role.

No agent receives by default:

- full Supabase access
- universal SQL execution
- universal shell
- filesystem-wide access
- arbitrary HTTP client
- all product tables
- all write tools
- service-role / secret credentials in the agent / model layer

Example: Constructor Agent must not access payroll, contracts, banking, HR salary, delete ops, or acceptance approval merely because those tables exist.

---

## 4. Tool allowlist

Every agent declares an explicit allowlist in `security_manifest.json`:

- `allowed_tools` — callable tools (usually reads for Tier 0/1)
- `allowed_write_tools` — empty unless Tier ≥ 2 and Human Gate defined

A tool **not** on the allowlist **cannot** be invoked.

Forbidden in agent tool surface:

- `execute_sql(...)` / arbitrary query runners
- `execute_python(...)` / arbitrary code execution
- `run_shell(...)`
- `arbitrary_http(...)` / `call_any_api(...)`

---

## 5. Read / Write separation

READ tools and WRITE tools must be physically/logically separated.

**Forbidden:** polymorphic `database_tool(action=read|insert|update|delete)`.

Each write tool must be:

- narrow and typed
- object-checked
- field-allowlisted
- actor-checked
- Human Gate–checked (when required)
- limited in scope
- followed by **VERIFY** (read-back)

---

## 6. Controlled write pattern (Tier ≥ 2)

```
READ → ANALYZE → PROPOSE → HUMAN APPROVAL
  → AUTHORIZE TOOL → CONTROLLED WRITE
  → READ-BACK VERIFY → AUDIT → REVOKE / CLOSE ACTION
```

LLM never receives free-form write access.

---

## 7. Human gates (code-enforced)

Mandatory Human Gate for high-risk operations, including:

- physical / commercial quantity changes
- creating obligations
- send to admission
- override blocks
- economic parameter changes
- deletes / bulk ops
- external data exfiltration / sends
- physical system / robot / drone control
- security policy changes

Gate checks run in **code**, not via system-prompt wording.

Distinguish (when documenting gates):

| Kind | Meaning |
|------|---------|
| Review | Human inspects candidate / proposal |
| Approval | Human accepts a proposed action within policy |
| Authorization | Scoped grant to execute a controlled write / tool |
| Final authority | Right to finalize commitments (money, schedule, physical, etc.) |

---

## 8. Fail closed

If any of the following is true → **DENY / STOP** (never “try anyway”):

- permission undefined
- tool unknown
- instruction source unknown (for critical actions)
- Human Gate missing when required
- authorization expired
- schema invalid
- provenance missing
- security policy conflict
- **required** execution isolation cannot be applied (when that agent’s tier demands it)

---

## 9. Rate / operation limits (write-enabled)

Declare and enforce:

- max rows per action
- max writes per run
- max calls per minute
- max retries
- max external sends

Prevent accidental mass writes (e.g. 50 000 rows instead of 50).

---

## 10. Kill switch (write/action agents)

**Status:** ARCHITECTURAL REQUIREMENT for Tier ≥ 2.
**CURRENTLY IMPLEMENTED (Constructor Tier 0):** N/A / not required (`kill_switch_required: false`).

External (non-LLM) controls required for Tier ≥ 2:

- DISABLE AGENT
- REVOKE WRITE PERMISSION
- STOP CURRENT RUN
- BLOCK TOOL

---

## 11. Audit trail

Critical actions require:

`run_id` · `agent_code` · `agent_version` · `policy_version` · `tool` · `action` · `object` · `timestamp` · `human_approver` · `authorization_id` · before/after reference · `result` · verification result.

Denied capability attempts should be auditable when the durable security-event store exists.

---

## 12. Security events (architecture now, DB later)

Future Agent Cockpit should surface events such as:

`PROMPT_INJECTION_DETECTED` · `UNTRUSTED_INSTRUCTION_IGNORED` · `PERMISSION_DENIED` · `TOOL_BLOCKED` · `HUMAN_GATE_REQUIRED` · `WRITE_LIMIT_REACHED` · `INVALID_OUTPUT_BLOCKED` · `AGENT_DISABLED` · `KILL_SWITCH_TRIGGERED` · `ESCALATION_REQUESTED` · `PRIVILEGE_DROPPED`

Do **not** create DB logging tables in this foundation stage.
**Durable denied-action event store:** DEFERRED FUTURE ENFORCEMENT.

---

## 13. Escalation / privilege drop (future)

**Status:** DEFERRED for Tier 0. Required before broad write/privileged agents.

```
DENIED → STRUCTURED ESCALATION REQUEST → HUMAN/POLICY GATE
  → ONE-SHOT OR SHORT-LIVED AUTHORIZATION → EXECUTION → VERIFY
  → AUTOMATIC PRIVILEGE DROP
```

**ONE APPROVAL MUST NOT CREATE PERMANENT PRIVILEGE.**

Do not implement in the EOS-SEC-1.2 documentation checkpoint.

---

## 14. MCP / external tool servers

**MCP IS NOT AUTOMATICALLY A SECURITY BOUNDARY.**

Before use, each MCP / tool server must define: identity · permissions · read/write · resource scope · allowed operations · argument constraints · network · secrets · rate/transaction limits · audit · destructive actions · approval · verify-after-write.

Universal MCP surfaces are forbidden without proven necessity. See baseline §9.

---

## 15. Transitional privileged credentials

Service-role / secret keys must **never** be given to the model or agent business layer.

If a **transitional** privileged read exists inside the trusted executor (infrastructure exception):

- it must be **named** in the agent security profile and manifest;
- it must **not** expand silently to new tables / writes / agents;
- exit criteria must shrink the secret surface (narrower identity, RLS-compatible path, dedicated capability service, isolated secret boundary);
- security review is **mandatory** before privileged or write surface growth.

Detail and current Constructor state: per-agent `specification/security.md`.
