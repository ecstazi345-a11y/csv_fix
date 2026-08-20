# Tool & Permission Policy

**Policy version:** `EOS-SEC-1.0`

---

## 1. Least privilege

Each agent receives the **minimum** rights needed for its role.

No agent receives by default:

- full Supabase access  
- universal SQL execution  
- universal shell  
- filesystem-wide access  
- arbitrary HTTP client  
- all product tables  
- all write tools  

Example: Constructor Agent must not access payroll, contracts, banking, HR salary, delete ops, or acceptance approval merely because those tables exist.

---

## 2. Tool allowlist

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

## 3. Read / Write separation

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

## 4. Controlled write pattern (Tier ≥ 2)

```
READ → ANALYZE → PROPOSE → HUMAN APPROVAL
  → AUTHORIZE TOOL → CONTROLLED WRITE
  → READ-BACK VERIFY → AUDIT → REVOKE / CLOSE ACTION
```

LLM never receives free-form write access.

---

## 5. Human gates (code-enforced)

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

---

## 6. Fail closed

If any of the following is true → **DENY / STOP** (never “try anyway”):

- permission undefined  
- tool unknown  
- instruction source unknown (for critical actions)  
- Human Gate missing when required  
- authorization expired  
- schema invalid  
- provenance missing  
- security policy conflict  

---

## 7. Rate / operation limits (write-enabled)

Declare and enforce:

- max rows per action  
- max writes per run  
- max calls per minute  
- max retries  
- max external sends  

Prevent accidental mass writes (e.g. 50 000 rows instead of 50).

---

## 8. Kill switch (write/action agents)

External (non-LLM) controls required for Tier ≥ 2:

- DISABLE AGENT  
- REVOKE WRITE PERMISSION  
- STOP CURRENT RUN  
- BLOCK TOOL  

---

## 9. Audit trail

Critical actions require:

`run_id` · `agent_code` · `agent_version` · `policy_version` · `tool` · `action` · `object` · `timestamp` · `human_approver` · `authorization_id` · before/after reference · `result` · verification result.

---

## 10. Security events (architecture now, DB later)

Future Agent Cockpit should surface events such as:

`PROMPT_INJECTION_DETECTED` · `UNTRUSTED_INSTRUCTION_IGNORED` · `PERMISSION_DENIED` · `TOOL_BLOCKED` · `HUMAN_GATE_REQUIRED` · `WRITE_LIMIT_REACHED` · `INVALID_OUTPUT_BLOCKED` · `AGENT_DISABLED` · `KILL_SWITCH_TRIGGERED`

Do **not** create DB logging tables in this foundation stage.
