# PSAA Permissions (v0.1)

| Capability | Allowed |
|------------|---------|
| Trusted READ `daily_progress_active` (narrow filters) | YES |
| Product WRITE to `daily_progress_*` / Airtable | NO |
| Arbitrary SQL / shell / code execution | NO |
| LLM | NO |
| Cross-project read | NO (project_code from AgentExecutionContext only) |

Human gates for product writes: all write actions — required if ever introduced (none in v0.1).
