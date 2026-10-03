# Monthly Plan Constructor Agent

**Профессиональное название:** Цифровой сотрудник формирования кандидатного состава месячного плана
**Код:** `MONTHLY_PLAN_CONSTRUCTOR`
**Версия спецификации:** v1.0 target professional contract (2026-10-02)
**Канон:** [CONSTRUCTOR_AGENT_ANATOMY.md](CONSTRUCTOR_AGENT_ANATOMY.md)
**Authority:** 2 of 5 — операционный spec. Не конкурирует с Anatomy.

Код, runtime, UI и данные этим изменением не меняются.

---

## Закон честности

Разделы ниже описывают утверждённую целевую модель.
Что уже доказано кодом — в § Current implementation.
Не считать capability DONE только потому, что похожее поле существует.

---

## Единственная целевая цепочка

```
Human Intent
  → Constructor Mission
  → Constructor Agent
  → Candidate Package
  → Human Review Gate
  → Reviewed Candidate Package
  → Human Confirm
  → Executability Agent
```

- Candidate Package = автономный результат Constructor до решения человека.
- Human Review Gate = профессиональный review готового предложения.
- Reviewed Candidate Package = target-артефакт после Human Review.
- Human Confirm = обязательный decision gate перед передачей.
- Executability Agent = единственный целевой следующий сотрудник.

`Admission Agent` / Admission handoff — HISTORICAL / CURRENT LEGACY RUNTIME TERMINOLOGY / SUPERSEDED FOR TARGET PROFESSIONAL MODEL.

`PERSISTED` ≠ receiver accepted. Constructor `COMPLETED` ≠ orchestration completed.
Orchestrator auto-handoff — OUT OF SCOPE.

---

## 1. Mission

Constructor — цифровой сотрудник формирования кандидатного состава месяца.

Его работа начинается не с заранее подготовленной человеком таблицы BOQ, а с формализованного намерения планирования.

После получения Constructor Mission агент обязан самостоятельно обработать всю производственную реальность внутри выбранного scope.

Он:

1. Читает весь рабочий scope.
2. Определяет physical remainder.
3. Учитывает completed / no remainder / not required / overrun.
4. Учитывает уже включённые строки текущего месяца.
5. Находит доступный к новому включению объём.
6. Связывает BOQ с facility/title, discipline, system, IWP и другими доступными измерениями.
7. Получает labor norm, если существует надёжный источник.
8. Фиксирует provenance нормы.
9. Выявляет конфликты и аномалии.
10. Формирует рекомендацию: `RECOMMEND_ADD` / `RECOMMEND_REMOVE` / `HUMAN_REVIEW_REQUIRED` (target, не runtime enum).
11. Группирует проблемные позиции.
12. Формирует Candidate Package.
13. Представляет результат человеку через Human Review.

Constructor сам формирует кандидатный состав.
Человек не собирает BOQ-коды вручную до старта агента.

---

## 2. Human Intent → Constructor Mission

Человек задаёт только рамки миссии:

| Измерение | Допустимые значения |
|-----------|---------------------|
| project | конкретный проект (обязательно; ALL запрещён) |
| month | хранимый ключ месяца (обязательно) |
| queue | одно / несколько / ALL |
| facility / title | одно / несколько / ALL |
| discipline | одна / несколько / ALL |
| system | одна / несколько / ALL |
| IWP | одно / несколько / ALL |

Затем формирует намерение. Это создаёт формальную Constructor Mission.

Пустое optional поле = ALL внутри этого project+month.
Заданное поле = обязанность сузить работу. Scope не расширяется.

Не входят в Mission Scope: статус витрины, свободный поиск BOQ, заранее выбранный список кодов.

Durable Human Intent UX — target, не proven.

---

## 3. Target lifecycle

Та же цепочка, что в начале документа. Не перескакивать от Reviewed Candidate Package к Executability Agent без Human Confirm.

Fail-closed: невозможность доказать безопасное состояние критического действия → FAILED / BLOCKED (EOS-SEC).
Product writes по-прежнему запрещены в v0.1.

---

## 4. Два разных артефакта

### A. Candidate Package

Автономный результат Constructor до решения человека.

Может содержать `UNRESOLVED` labor. Такие позиции обязательны к показу.

Содержит: найденных кандидатов, physical remainder, `available_to_add`, labor norm status/source/provenance, recommendations (target), exceptions, provenance.

### B. Reviewed Candidate Package

Результат после Human Review. Target. NOT_IMPLEMENTED в текущем runtime.

Содержит: только подтверждённые человеком позиции, подтверждённый quantity, разрешённую labor norm, provenance, human decision trace, причины исключения/изменения, blocking validation result.

Included `UNRESOLVED` в Reviewed Candidate Package → HANDOFF BLOCKED.

Только Reviewed Candidate Package после Human Confirm передаётся Executability Agent.

Текущий runtime: Candidate Package struct есть без recommendation payload.

---

## 5. Human Review Gate

Constructor самостоятельно формирует полный Candidate Package.
Человек не формирует кандидатов вручную с нуля.
После работы Constructor человек получает готовый профессиональный результат и выполняет Human Review:

- Добавить
- Убрать
- Требует уточнения

Допустимы массовые действия и фильтры: добавить все допустимые; показать только проблемные; показать только без нормы; фильтровать по title / discipline / system / IWP / status; убрать выбранные.

Не описывать UX через checkbox.

Закон «человек видит только blocking exceptions» / «человек не просматривает routine candidates» снят как целевая профессия.
HITL runtime v0.1 (interrupt на blocking exceptions) — historical/current implementation only. Не заменяет Human Review Gate.

---

## 6. Labor Norm Gate — два разных закона

Используется существующая taxonomy Candidate Package:

```
VALIDATED | PROVISIONAL | UNRESOLVED | NOT_AVAILABLE
```

Не вводить P50/P80 как production-семантику Constructor.

### Закон 1 — Candidate discovery

`LABOR_NORM_UNRESOLVED` не удаляет физического кандидата.
Constructor обязан показать такого кандидата человеку.
Candidate Package может содержать unresolved.

### Закон 2 — Reviewed Candidate Package / final handoff

Ни одна включённая позиция не может иметь `UNRESOLVED`.

```
UNRESOLVED candidate          = allowed
UNRESOLVED included candidate → HANDOFF BLOCKED
```

Человек должен внести норму вручную, либо подтвердить допустимую предложенную, либо убрать позицию из итогового пакета.

Constructor не становится LaborNormResolver. Текущий Exception Engine NON_BLOCKING / CONTINUE — закон discovery, не final gate. Final gate — NOT_IMPLEMENTED.

Zero price ≠ нет физической работы.

---

## 7. Constructor and quantity

Constructor формирует PHYSICAL CANDIDATE PACKAGE.
Доказанный физический остаток может стать `available_to_add`. Это анализ, не выдумка.
Constructor не объявляет эту величину окончательным feasible commitment месяца.

| Понятие | Кто | Смысл |
|---------|-----|--------|
| AVAILABLE PHYSICAL QUANTITY | Constructor | Что физически ещё можно планировать в этом grain |
| REVIEWED QUANTITY | человек + Constructor gate | Что человек подтвердил к передаче |
| FINAL COMMITTED QUANTITY | Executability → Resource → Economic → Decision | Что организация обязуется выполнить |

Запрет: invent planned_qty / invent physical remainder.
Спорный остаток → `HUMAN_REVIEW_REQUIRED`, не тихая правка ведомости.
Crew Constructor не выдумывает.

---

## 8. Grain

KEEP из MPCA-001:

```
constructor_candidate_id = PROJECT|MONTH|FACILITY|DISCIPLINE|BOQ
```

uppercase, fail-closed при коллизии. Не скрывать дубли.

---

## 9. Professional sources and tools

```
Agent Core
  → Professional Tool Contracts
  → Replaceable Data Adapters
  → current storage implementation
```

Professional sources: Production Scope; Physical Remainder; Existing Month Plan; Adjustment; Labor Norm; System / Work Package Context.

Professional tool contracts: `get_working_scope`, `get_physical_remainder`, `get_existing_month_plan`, `get_adjustments`, `get_system_context`, `get_work_package_context`, `get_labor_norm`, `get_execution_state`.

Имена Python tools, таблиц, views и UI-страниц — только § Current implementation / current adapter. Они не часть профессии.

---

## 10. Autonomy Envelope

| Класс | Смысл |
|-------|--------|
| `AUTO` | делает сам |
| `AUTO_WITH_TRACE` | сам + обязательный audit |
| `HUMAN_REVIEW_REQUIRED` | подготовленный результат, человек должен увидеть |
| `HUMAN_DECISION_REQUIRED` | без человека шаг не завершается — целевой уровень на выходе |
| `FORBIDDEN` | никогда |

AUTO / AUTO_WITH_TRACE: читать professional sources; нормализовать; remainder; исключать очевидные completed / no remainder / invalid headers; `available_to_add`; предлагать labor norm; conflicts; recommendations; Candidate Package.

HUMAN_REVIEW_REQUIRED: спорные кандидаты; unresolved labor; data conflicts; нестандартные корректировки; аномальные quantities/norms.

HUMAN_DECISION_REQUIRED: итоговое включение/исключение; ручная labor norm; подтверждение Reviewed Candidate Package; Human Confirm handoff к Executability Agent.

FORBIDDEN: invent quantity; скрывать unresolved; менять BOQ master; менять договорные цены; утверждать месячное обязательство; фабриковать receiver acceptance; считать persisted = accepted; считать Constructor completed = orchestration completed; product writes; LLM как источник нормы или количества; передавать non-reviewed пакет; included UNRESOLVED в reviewed handoff.

---

## 11. Current implementation (честно)

### KEEP / DONE в смысле domain

Deterministic classify в `agents/monthly_plan_constructor/` (MPCA-001):

- read scope / adjustments / plan lines через trusted read executor;
- remainder / already planned в domain;
- exclusions completed / no remainder / already planned / invalid / overrun;
- HumanIssue;
- Candidate Package struct;
- no product write.

### PARTIAL

- mission dataclass + binder (ALL/multi) без Human Intent UX;
- existing month plan: domain умеет; Shadow Phase A передаёт пустой план;
- labor statuses на record; Shadow форсирует `UNRESOLVED`;
- current adapter tools привязаны к текущему store;
- legacy persist handoff без reviewed package.

### NOT_IMPLEMENTED относительно этого контракта

- durable Human Intent;
- recommendations `RECOMMEND_*`;
- Human Review surface;
- Reviewed Candidate Package;
- labor norm blocking gate на included;
- Human Confirm как package gate;
- Executability Agent;
- Django Human Surface;
- Orchestrator launch.

### Current adapter (не профессия)

Текущие Python names: `load_scope`, `load_adjustments`, `load_existing_month_plan_lines`.
Они реализуют professional contracts, но не являются именами профессии.

CURRENT LEGACY RUNTIME: persist с Admission terminology. SUPERSEDED FOR TARGET PROFESSIONAL MODEL.

Историческое отклонение ручной витрины BOQ после вызова агента — не target. Не развивать ручной сбор BOQ как основной ритуал.

Полная таблица Target vs Current: Anatomy §24.

---

## 12. KPI

Целевые: coverage assigned mission; человек ревьюит подготовленное, а не собирает BOQ с нуля; remainder honesty; already-planned honesty; labor honesty; handoff honesty.

Не KPI: «совпало с человеческим допуском прошлого месяца» без совпадения зерна миссии.
