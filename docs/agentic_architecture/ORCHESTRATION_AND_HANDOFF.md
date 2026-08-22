# Orchestration and Handoff

**Status:** TARGET LAW v0.1<br>
**Date:** 2026-08-22

---

## 1. Principle

**NO HIDDEN AGENT-TO-AGENT CHAT.**

Агенты не пересылают друг другу скрытые промпты с выгрузкой ведомости, остатков, цен и норм.

```
Agent A  →  structured result / state
Orchestrator  →  transition record
Agent B  →  identifiers + самостоятельное чтение current reality (Supabase)
```

Business data не дублировать в огромный prompt.<br>
Admission (и любой следующий агент) **сам** читает актуальную реальность.

---

## 2. Orchestrator role

Оркестратор месячного планирования:

- запускает специализированных агентов;
- держит последовательность контура;
- отслеживает зависимости;
- инициирует повторный расчёт при изменении реальности;
- ставит workflow на Human Gate;
- продолжает после решения;
- фиксирует handoff;
- контролирует завершённость.

Он **не**:

- не dashboard Page51 как замена runtime (Page51 — feasibility cockpit продукта, не Constructor);
- не super-agent, выполняющий навыки Constructor/Admission/Economic самостоятельно.

Page52 остаётся организационным описанием.<br>
Этот документ — технический контракт передачи работы.

---

## 3. Lifecycle outside the UI

Target runtime: LangGraph поверх existing Python skills/tools.

Закрытие Streamlit-страницы ≠ смерть run.

Нужны (schema OPEN):

- durable run state;
- pause / resume;
- retry policy;
- checkpoint.

Не выбирать backend в этом checkpoint.

---

## 4. Constructor → Admission conceptual handoff

Тип: `CONSTRUCTOR_TO_ADMISSION` (имя стабилизировать при первой реализации runtime).

Минимальный payload:

| Поле | Смысл |
|------|--------|
| `handoff_type` | вид передачи |
| `orchestration_run_id` | контур оркестратора |
| `source_agent` | `MONTHLY_PLAN_CONSTRUCTOR` |
| `source_run_id` | run Constructor |
| `project_code` | проект |
| `month_key` | хранимый месяц |
| `scope` | `MonthlyPlanningScope` целиком |
| `candidate_ids` | идентификаторы пакета |
| `candidate_package_summary` | counts, не все строки ведомости |
| `labor_norm_status_summary` | validated / provisional / unresolved counts |
| `created_at` | время фиксации |
| `status` | например `HANDOFF_READY` / `WAITING_FOR_HUMAN` / `BLOCKED` |

Admission Agent **не реализован**. Не подменять его:

- кнопкой Page10B «В ДОПУСК»;
- статусом `SENT_TO_ADMISSION` (это существующий человеческий product write);
- чатом.

Следующий инженерный шаг после доказательства Constructor runtime — пакет Admission Agent, не раньше.

---

## 5. Human Interrupt

LangGraph target должен поддерживать `WAITING_FOR_HUMAN`.

Агент формирует:

| Поле | Смысл |
|------|--------|
| `question_id` | стабильный id вопроса |
| `reason` | почему человек нужен |
| `business_object` | grain / candidate_id / constraint / … |
| `evidence` | доказуемые факты, не dump секретов |
| `allowed_decisions` | закрытый перечень решений |
| `current_state` | куда вернуться |

Workflow **pause**.<br>
Человек отвечает на Control Room / Decision Surface.<br>
Workflow **resume**.

Человек **не** запускает всю цепочку заново вручную и **не** копирует результат в следующий экран.

Persistent storage interrupt — OPEN.

---

## 6. Human Gate vs product write

Два разных контура:

1. **Workflow interrupt** — профессиональное исключение (спорный объём, неоднозначный grain). Не обязательно INSERT.
2. **EOS-SEC write gate** — HumanApproval + WriteAuthorization + trusted executor + kill switch (MPCA-002 KEEP).

Не смешивать.<br>
Не требовать write-approval, чтобы просто закончить READ/ANALYZE/PROPOSE.<br>
Не открывать generic write, чтобы «продолжить граф».

---

## 7. Agent Control Room (Streamlit)

Streamlit = наблюдаемость + решения человека + evidence.

Не runtime.

Пример поверхности — [ARCHITECTURE_BASELINE.md](ARCHITECTURE_BASELINE.md) § Observability.

Большие BOQ / candidate tables: только audit drill-down («Показать расчёт агента»).

Page10B manual constructor **сохраняется** как человеческий контур продукта.<br>
Он не должен быть единственным местом жизни агента.

---

## 8. Re-calculation

Изменение реальности (новый факт человека, снятие ограничения, изменение остатка) — оркестратор инициирует **необходимый** повторный расчёт зависимых агентов.

Не «пользователь помнит, кого дёрнуть».

Точные dependency rules — OPEN, но принцип зафиксирован Page52 и этим документом.

---

## 9. KPI across the contour

Главный KPI: routine removal с ИТР.

Constructor KPI — в спецификации Constructor.<br>
Не подменять его экономикой паспорта месяца.

Не утверждать финансовую экономию без доказательства.
