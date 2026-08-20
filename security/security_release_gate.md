# Security Release Gate

**Policy version:** `EOS-SEC-1.0`  
**Official status field:** `SECURITY_GATE`

---

## 1. Rule

```
SECURITY_GATE = PASS | FAIL
```

An agent **cannot** be marked RELEASE READY if `SECURITY_GATE != PASS`.

This holds even when:

- UNIT / FUNCTIONAL tests = PASS  
- REGRESSION = PASS  
- LESSONS_2 methodology gate = PASS  

---

## 2. Production-ready checklist (all required)

| # | Gate | Required |
|---|------|----------|
| 1 | Functional Tests | PASS |
| 2 | Regression Tests | PASS |
| 3 | Lessons_2 Methodology Gate | PASS |
| 4 | **Agent Security & Confidentiality Gate** | PASS |

---

## 3. Security Gate inputs

1. Global policies under `security/` present and versioned (`EOS-SEC-1.0`).  
2. Per-agent `specification/security.md` present.  
3. Per-agent `specification/security_manifest.json` present and valid.  
4. `tests/test_agent_security_governance.py` PASS.  
5. Tier-appropriate security tests PASS (subset for Tier 0).  
6. No unresolved **CRITICAL** vulnerabilities.  
7. HIGH risks either mitigated or explicitly accepted with documented residual risk (release owner decision).  

---

## 4. Manifest consistency rules (automated)

- `write_access=false` ⇒ `allowed_write_tools` empty  
- `llm_enabled=false` ⇒ runtime must not import LLM providers  
- `arbitrary_sql_allowed=false` ⇒ no universal SQL executor in tool surface  
- `arbitrary_shell_allowed=false` ⇒ no shell tool  
- `arbitrary_code_execution_allowed=false` ⇒ no arbitrary code tool  
- `secrets_allowed_in_context=false` ⇒ policy forbids secrets in context  
- `fail_closed=true` mandatory  
- `security_policy_version` present  

---

## 5. Critical finding procedure

If security review finds a **CRITICAL** vulnerability in an existing agent:

1. **STOP** business-logic auto-fix.  
2. Report CONTROL / EVIDENCE / RISK / ACTION REQUIRED.  
3. Wait for explicit remediation order.

Foundation stage focus: governance artifacts + automated gate — not silent refactors of domain/runtime unless ordered.
