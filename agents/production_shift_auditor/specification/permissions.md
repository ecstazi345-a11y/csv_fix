# PSAA Permissions (v0.1 + PSAA-02)

| Capability | Allowed |
|------------|---------|
| Trusted READ `daily_progress_active` (narrow filters) | YES |
| Controlled ARTIFACT PERSIST to `psaa_shift_audit_history` | YES (append-only, own artifact) |
| Trusted READ of own project audit history | YES |
| Product WRITE to `daily_progress_*` / Airtable | NO |
| WRITE norms / payroll / acceptance | NO |
| Arbitrary SQL / shell / code execution | NO |
| LLM | NO |
| Cross-project read/write | NO (`project_code` from AgentExecutionContext only) |
| Apply Supabase migration from agent | NO |

`write_allowed` on AgentExecutionContext remains **false** (no product write).
Artifact persist is a separate controlled tool path with read-back verify.
