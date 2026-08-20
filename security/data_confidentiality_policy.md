# Data Confidentiality Policy

**Policy version:** `EOS-SEC-1.0`

---

## 1. Data classification

| Class | Examples |
|-------|----------|
| `PUBLIC` | Intentionally public materials |
| `INTERNAL` | Internal operational production data |
| `CONFIDENTIAL` | Sensitive ops / commercial / financial |
| `RESTRICTED` | Personal data (PII), highly sensitive ops |
| `SECRET` | API keys, service-role keys, tokens, passwords, private credentials |

Each agent manifest must declare:

- `data_classes_allowed`  
- `data_classes_forbidden`  
- (and in narrative security.md) what may appear in output vs trace  

---

## 2. Data minimization

Agents receive **only required fields**.

Do **not** “give the whole table and let the agent figure it out.”

If Constructor does not need salary, passport, phone, or contract price details — those fields are not supplied.

---

## 3. Secrets policy

Secrets **never** appear in:

- system / user prompts  
- agent memory  
- `AgentRun` / structured output  
- `TraceEvent`  
- application logs  
- RAG documents  
- error messages  

Secrets live only in protected environment / secret storage.  
The model must not see secrets when technically avoidable.

`secrets_allowed_in_context: false` is the default and required unless an explicit Tier-3+ exception is approved (still never logging secrets).

---

## 4. Supabase access

Do **not** standardize on one omnipotent service-role credential for all agents.

As writes appear:

- separate scopes / roles  
- RLS  
- narrow server-side write endpoints  
- purpose-limited functions  

If service role is technically required for a server path, it **must not** be passed to the model / LLM context / agent prompts / traces.

---

## 5. Output security

Treat agent/model output as potentially unsafe.

**Forbidden direct paths:**

```
LLM OUTPUT → SQL
LLM OUTPUT → SHELL
LLM OUTPUT → WRITE API
LLM OUTPUT → ROBOT COMMAND
```

**Required path:**

```
structured schema → validation → permission check
  → policy check → optional Human Gate → deterministic executor
```

---

## 6. Trace / log confidentiality

Trace and audit are leakage channels.

**Never log:** API secrets, passwords, auth headers, service-role keys, full sensitive document bodies, unnecessary PII.

**Required:** REDACTION BEFORE LOGGING.

Trace should still preserve: what / when / which tool / which object / result / who authorized — without excess payload.
