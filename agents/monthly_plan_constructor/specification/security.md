# Security Profile — MONTHLY_PLAN_CONSTRUCTOR (MPCA-001)

**Agent code:** `MONTHLY_PLAN_CONSTRUCTOR`
**Security tier:** `TIER_0_READ_ONLY_DETERMINISTIC`
**Security policy version:** `EOS-SEC-1.0`
**Manifest:** [security_manifest.json](security_manifest.json)
**Professional contract:** `docs/agentic_architecture/CONSTRUCTOR_AGENT_ANATOMY.md`

Этот файл — **CURRENT IMPLEMENTATION / CURRENT ADAPTER**, не канон профессии.
Имена таблиц, views, credentials и Python tools ниже описывают действующий store adapter.
Профессиональные источники и tool contracts — Anatomy §5–§6.
Новая профессия не расширяет tool allowlist и не открывает product writes.

---

## 1. Classification

| Attribute | Value |
|-----------|-------|
| LLM | No |
| Product writes | No |
| UI session_state as runtime | No |
| Tool surface | Narrow READ only |
| `select("*")` | Forbidden |
| Fail closed | Yes |
| Trace redaction | Enforced in runtime |
| Human Review of candidate package | Target professional gate; not a write grant |

Governance закона профессии:

- DATA ≠ INSTRUCTION (product free-text = Level 4 DATA);
- не скрывать `UNRESOLVED`;
- `HANDOFF_PERSISTED` ≠ receiver accepted;
- actor `LOCAL_APPLICATION` / `EXECUTION_OS_LOCAL_HOST` **не** verified human identity;
- Human Confirm перед handoff к Executability Agent — требуемый professional gate, не повышение полномочий.
- Admission terminology в текущем persist — CURRENT LEGACY RUNTIME / SUPERSEDED FOR TARGET.

---

## 2. Column allowlist (dependency)

Текущий proven READ surface. Не расширять без отдельного security increment.

### Scope — `monthly_scope_picker_view`

| COLUMN | WHY REQUIRED | CONSUMER |
|--------|--------------|----------|
| project_code | grain / filter | domain, normalize |
| facility_building | grain → facility | normalize, domain |
| construction_discipline | grain → discipline | normalize, domain |
| boq_code | BOQ identity | domain, normalize |
| boq_name | candidate label | Candidate |
| unit_of_measure | unit alias | Candidate (read-layer alias) |
| total_project_qty | total qty | normalize / metrics |
| executed_qty_all_time | executed | normalize / metrics |
| manual_executed_before_system | executed_total (no double apply) | metrics |
| manual_verified_remaining_qty | verified remaining | metrics |
| planning_remaining_qty | remaining / filter | normalize, filter_invalid |
| unit_price | zero-price physical keep | filter_invalid |
| total_project_value | value / filter | normalize |
| system_label | system alias / conflicts | domain enrich |
| iwp_id | iwp alias / conflicts | domain enrich |

### Adjustments — `monthly_scope_manual_adjustments`

| COLUMN | WHY REQUIRED | CONSUMER |
|--------|--------------|----------|
| project_code | grain | merge_not_required_once |
| facility_building | grain | merge_not_required_once |
| construction_discipline | grain | merge_not_required_once |
| boq_code | grain | merge_not_required_once |
| not_required_qty | effective requirement | merge + metrics |
| not_required_reason | audit text | merge |

### Plan lines — `monthly_plan_lines_v2`

| COLUMN | WHY REQUIRED | CONSUMER |
|--------|--------------|----------|
| plan_line_id | identity / candidate ids | aggregate |
| client_line_uid | conflict analysis | aggregate |
| project_code | filter / grain | aggregate |
| month_key | stored RU month filter | aggregate |
| facility | grain | aggregate |
| discipline | grain | aggregate |
| system | conflict detection | aggregate |
| iwp | conflict detection | aggregate |
| boq_code | grain | aggregate |
| planned_qty | already_planned sum | aggregate |
| crew | conflict evidence | aggregate |
| status | active line filter | aggregate |

---

## 3. Credential policy

| Source | Policy code | Env (infra only) | Notes |
|--------|-------------|------------------|-------|
| scope | `PUBLISHABLE_READ` | `SUPABASE_KEY` | via trusted executor |
| plan lines | `PUBLISHABLE_READ` | `SUPABASE_KEY` | via trusted executor |
| adjustments | `TRANSITIONAL_PRIVILEGED_READ` | `SUPABASE_SECRET_KEY` | **TRANSITIONAL_INFRASTRUCTURE_EXCEPTION** — explicit, not silent fallback |

Agent layer never sees credentials. Actor `LOCAL_APPLICATION` / `EXECUTION_OS_LOCAL_HOST` is **NOT verified human identity**.

### RLS requirement to clear transitional exception

Grant scoped SELECT (+ membership) so adjustments leave `TRANSITIONAL_PRIVILEGED_READ`.

---

## 4. Allowed tools (current adapter names)

Professional contracts: `get_working_scope`, `get_physical_remainder`, `get_existing_month_plan`, `get_adjustments`, `get_system_context`, `get_work_package_context`, `get_labor_norm`, `get_execution_state`.

Current Python READ allowlist:

| Tool | Mode |
|------|------|
| `load_scope` | READ |
| `load_adjustments` | READ |
| `load_existing_month_plan_lines` | READ |

**Allowed write tools:** none (`[]`).

`get_labor_norm` как отдельный Constructor product path — future contract gap, не текущий allowlist.

---

## 5. Trust & instruction handling

Product free-text fields remain Level 4 DATA, not instructions.

Target Human Review decisions (Добавить / Убрать / Требует уточнения) — human-authored control data. Они не дают агенту права invent quantity, менять BOQ master или считать handoff принятым получателем.
