# Skills — MONTHLY_PLAN_CONSTRUCTOR

**Версия контракта:** v1.0 target (2026-10-02)
**Канон:** `docs/agentic_architecture/CONSTRUCTOR_AGENT_ANATOMY.md`

## Professional tool contracts (target)

`get_working_scope` · `get_physical_remainder` · `get_existing_month_plan` · `get_adjustments` · `get_system_context` · `get_work_package_context` · `get_labor_norm` · `get_execution_state`

Имена ниже в секции v0.1 — CURRENT ADAPTER / Python runtime. Не имена профессии.

## Target professional skills

| # | Skill | Смысл | Current |
|---|--------|--------|---------|
| 1 | Получить намерение / mission | принять Human Intent, создать Constructor Mission | **PARTIAL** — dataclass области есть; Intent UX нет |
| 2 | Получить рабочий состав | READ Production Scope | **DONE** — current adapter `skill_get_working_scope` |
| 3 | Нормализовать | зерно, единицы, invalid headers | **DONE** |
| 4 | Physical remainder | executed / required / remaining / overrun | **DONE** |
| 5 | Учесть текущий месяц | Existing Month Plan | **PARTIAL** — domain есть; Shadow Phase A пустой план |
| 6 | Available to add | remainder минус уже включённое | **DONE** в domain; Shadow искажает из-за пустого плана |
| 7 | Labor norm resolution | найти / предложить / provenance | **PARTIAL** — statuses есть; Shadow → `UNRESOLVED` |
| 8 | Conflicts / anomalies | дубли, спорные qty | **PARTIAL** — HumanIssue; нет review-grouping |
| 9 | Recommendation | `RECOMMEND_ADD` / `RECOMMEND_REMOVE` / `HUMAN_REVIEW_REQUIRED` | **NOT_IMPLEMENTED** (не runtime enum) |
| 10 | Candidate Package | артефакт до человека; UNRESOLVED allowed | **PARTIAL** — struct без recommendation |
| 11 | Human Review support | Добавить / Убрать / Требует уточнения | **NOT_IMPLEMENTED** |
| 12 | Labor norm gate | included `UNRESOLVED` → HANDOFF BLOCKED | **NOT_IMPLEMENTED** |
| 13 | Reviewed Candidate Package | артефакт после человека | **NOT_IMPLEMENTED** |
| 14 | Human Confirm + Handoff | reviewed → Executability Agent | **PARTIAL** — legacy persist без review пакета; Executability **NOT_IMPLEMENTED** |

## Current named skills (v0.1 code — KEEP names)

Не переименовывать классы/файлы. CURRENT ADAPTER, не полный target.

| # | Skill (EN) | Label (RU) | Input | Action | Output |
|---|------------|------------|-------|--------|--------|
| 1 | `get_working_scope` | Получить рабочий состав | project_code | READ scope | scope rows |
| 2 | `calculate_availability` | Рассчитать доступность | scope + adjustments | merge not_required once + frozen BOQ metrics | availability df |
| 3 | `apply_existing_month_plan` | Учесть существующий месячный план | plan lines | aggregate already_planned | updated availability |
| 4 | `exclude_unavailable` | Исключить недоступное | classified rows | exclude completed / no remainder / fully planned / invalid | exclusions |
| 5 | `detect_conflicts` | Проверить конфликты | human_issues | filter blockers | conflicts |
| 6 | `build_candidates` | Сформировать кандидатный состав | open rows | build Candidate structs | candidates |
| 7 | `build_human_exceptions` | Сформировать исключения для человека | issues | package real exceptions | human_issues |
| 8 | `prepare_handoff` | Подготовить результат для следующего этапа | candidates + issues | build handoff contract | handoff |
