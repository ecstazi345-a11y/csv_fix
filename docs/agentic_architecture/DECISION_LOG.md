# Decision Log — Agentic Architecture

ADR-like. Новые решения добавлять сверху по дате.<br>
Не переписывать историю: rejected остаётся rejected, пока новый ADR явно не сменит закон.

---

## 2026-08-22 — Target runtime stack

**DECISION:** Target agent runtime = Python + LangGraph + Supabase + EOS-SEC + replaceable LLM adapter.<br>
Streamlit = Agent Control Room / Human Decision Surface / Evidence Drill-down, **не** runtime цифрового сотрудника.

**REASON:** Агентам нужен lifecycle вне UI: state, pause/resume, handoff, retry, observability. Закрытие страницы не должно убивать сотрудника. Deterministic ядро остаётся в Python.

**REJECTED:** Agent = Streamlit button callback + session_state как единственный runtime.

---

## 2026-08-22 — Candidate dataframe is evidence, not workflow

**DECISION:** Candidate dataframe = audit / evidence / drill-down, не primary human workflow.

**REASON:** Live MPCA-003 показал 175 строк как главную поверхность. Это уничтожает routine removal (447 обработано агентом → человек снова видит 175). Противоречит Page52 и закону AGENT ≠ DATAFRAME.

**REJECTED:** Развивать MPCA-003 как новые ручные таблицы кандидатов (MPCA-004 table).<br>
**REJECTED:** «Один агент = одна новая UI-таблица».

---

## 2026-08-22 — Constructor human interaction

**DECISION:** Человек задаёт mission/scope и решает exceptions. Не row-by-row routine approval, не 175 checkbox, не qty/crew на каждую обычную позицию.

**REASON:** Человек сообщает изменение реальности / область работы. Агент выполняет повторяемую классификацию. Human Gate = A (scope/task) + B (exceptions) + EOS-SEC authorization на критический write.

**REJECTED:** `human_required_fields = [crew, planned_qty]` как обязательный шаг на каждом candidate, без которого handoff к Admission невозможен.

**KEEP:** MPCA-002 security objects (issuer-only approval, WriteAuthorization, kill switch). Меняется **предмет** подтверждения, не контур полномочий. Код security в checkpoint документации не менялся.

---

## 2026-08-22 — No hidden agent-to-agent chat

**DECISION:** Handoff = identifiers + scope + run ids + summaries. Agent B сам читает Supabase.

**REASON:** Скрытый prompt с business data не является shared state, не аудируется как operational reality и ломает актуальность.

**REJECTED:** Передача ведомости/кандидатов следующим агентом через chat/LLM context.<br>
**REJECTED:** Человек как курьер между агентами.

---

## 2026-08-22 — Reuse deterministic MPCA in LangGraph

**DECISION:** Existing deterministic MPCA-001 logic (classify, remainder, exclusions, grain, validators) must be reused inside LangGraph. REUSE, not rewrite.

**REASON:** Ядро уже доказано тестами и live read. Перепись «на граф» создаст второй source of truth и регрессии.

**REJECTED:** Выбросить MPCA-001 и писать Constructor заново как LLM-agent.<br>
**REJECTED:** LLM для арифметики остатка / already planned.

---

## 2026-08-22 — Missing labor history does not kill physical candidates

**DECISION:** Missing internal labor history does **not** automatically block physical candidate formation.

**REASON:** Нет своего P50 ≠ нет работы. Иначе система планирует только то, что уже умеет считать, и теряет физический фронт.

**REJECTED:** «Нет P50 → выкинуть кандидата».<br>
**REJECTED:** Unknown norm silently = 0.

**RETAINED on write path:** MPCA-002 missing P50 → no plan-line write with invented labor. Physical package ≠ written plan line.

---

## 2026-08-22 — Labor norms require provenance

**DECISION:** Authoritative labor norm must have source, reference, version, confidence, conditions. LLM cannot silently invent production norms from general knowledge.

**REASON:** «Мировая практика ≈ N чел·ч» без источника неотличима от галлюцинации и загрязняет корпоративную базу норм.

**ALLOWED for LLM:** найти candidate source, сопоставить описания, объяснить различия, предложить выбор человеку.

---

## 2026-08-22 — Three labor values

**DECISION:** Separate NORMATIVE/BENCHMARK, OBSERVED PRODUCTIVITY (P50/P80/…), PLANNING NORM.

**REASON:** ГЭСН, факт бригады и принятая норма месяца — разные управленческие объекты. Смешение даёт ложную точность.

---

## 2026-08-22 — LaborNormResolver starts as shared capability

**DECISION:** Starts as shared service/capability/tool, not necessarily another agent. May become an agent later if autonomy/complexity warrants it.

**REASON:** Не размножать агентов, пока нет отдельной миссии, lifecycle и исключений, которые не покрывает сервис.

**REJECTED:** Немедленно создавать «Нормативного агента» как UI-таблицу.<br>
**REJECTED:** Загрузить Constructor функциями Economic / Resource / estimator.

---

## 2026-08-22 — MonthlyPlanningScope is the mission boundary

**DECISION:** UI FILTER ≠ AGENT BUSINESS SCOPE. Canonical `MonthlyPlanningScope`: required project+month; optional facility/discipline/system/iwp/queue = ALL if omitted, **must bind** if set. Status and free-text search are not mission scope.

**REASON:** Proven live bug: Page10B discipline/facility не входили в `run_monthly_plan_constructor_agent(project, month)`. Агент вернул весь проект (447/175) при выбранной вентиляции и титуле.

**REJECTED:** Надеяться, что человек «сначала отфильтрует витрину, и агент это поймёт».

---

## 2026-08-22 — Available physical qty ≠ final committed qty

**DECISION:** Constructor may attach proven available remainder as physical candidate quantity. Final month commitment is later in the contour.

**REASON:** Иначе Constructor либо парализуется без Resource, либо самовольно объявляет обязательство месяца.

**REJECTED:** Constructor invents crew and committed qty.<br>
**REJECTED:** Resource/Economic logic inside Constructor.

---

## 2026-08-22 — MPCA assets classification

**DECISION:**

| Asset | Status |
|-------|--------|
| Commit `4d7d21bb27c0ba7eea0bf40b77f8f3432d1c7de5` | safe committed baseline |
| MPCA-001 | KEEP deterministic core |
| MPCA-002 | KEEP security write architecture; not live write; not 175-row UX law |
| MPCA-003 | KEEP as technical experiment; do not extend as workbench tables |
| Uncommitted MPCA-002/003 worktree files | do not reset/restore because of this documentation checkpoint |

---

## 2026-08-22 — Next release name

**DECISION:** Next engineering release = **AGENT RUNTIME v0.1 — CONSTRUCTOR MISSION**. Not MPCA-004 table. Admission Agent after runtime proof.

**REJECTED:** Следующий шаг = ещё одна таблица / checkbox UI на Page10B.

---

## 2026-08-22 — Documentation checkpoint itself

**DECISION:** Canonical engineering source of truth lives in `docs/agentic_architecture/`. Page52 remains organizational description. EOS-SEC remains `security/*.md`.

**REASON:** Архитектура должна восстанавливаться без истории чатов.

This checkpoint: documentation only. No product code, no DB, no git add/commit/push.
