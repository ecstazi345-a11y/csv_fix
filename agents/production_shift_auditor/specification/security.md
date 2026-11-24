# PSAA Security Profile (v0.1)

**Security tier:** `TIER_0_READ_ONLY_DETERMINISTIC`
**Policy:** EOS-SEC-1.1
**MODEL IS NOT A SECURITY BOUNDARY.**

## Rules

- Execution requires `AgentExecutionContext` from trusted issuer.
- Credentials never enter agent context, artifacts, or logs.
- Only allowlisted tool: `load_shift_daily_progress`.
- `write_allowed=false`.
- Foreman / master free text is **untrusted data** (DATA ≠ INSTRUCTION).
- Fail closed on unknown agent, blank project, expired context, tool not allowed.
- Trace redaction required.

## Untrusted inputs

- `comment_foreman`, `operation_comment`, free-text operation names
- Fixture / human-supplied ShiftAuditInput fields
- Any Airtable-originated text on Daily Progress rows
