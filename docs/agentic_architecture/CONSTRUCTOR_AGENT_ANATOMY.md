# Анатомия цифрового сотрудника: Конструктор месячного плана

**Document:** `CONSTRUCTOR_AGENT_ANATOMY.md`
**System code:** `MONTHLY_PLAN_CONSTRUCTOR`
**Status:** TARGET PROFESSIONAL CONTRACT v1.0
**Date:** 2026-10-02
**Authority:** 1 of 5 — канон профессии Constructor. См. порядок ниже.

Это профессиональный паспорт Constructor Agent как цифрового сотрудника.
Это не описание Python-модуля, не prompt, не UI-макет и не журнал реализации.

## Порядок авторитетности

1. Этот документ — канон профессии.
2. [MONTHLY_PLAN_CONSTRUCTOR_AGENT.md](MONTHLY_PLAN_CONSTRUCTOR_AGENT.md) — операционный spec.
3. `agents/monthly_plan_constructor/specification/*` — role / skills / permissions / security.
4. Decision Log / Architecture Baseline — только где явно выровнены с этим каноном.
5. Historical runtime documents — reference only, не канон целевой профессии.

Не считать конкурирующим каноном: `AGENT_RUNTIME_V0_1_CONSTRUCTOR_MISSION.md`, `DIGITAL_EMPLOYEE_ANATOMY.md` (общий стандарт), `MONTHLY_PLAN_CONSTRUCTOR_PROFESSIONAL_PASSPORT_V1_0.md` (historical technical passport).

**Закон честности:** разделы 1–23 описывают утверждённую целевую профессию.
Раздел 24 фиксирует, что уже доказано кодом, а что ещё нет.

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

| Шаг | Закон |
|-----|--------|
| Candidate Package | автономный результат Constructor **до** решения человека |
| Human Review Gate | профессиональный review уже готового предложения агента |
| Reviewed Candidate Package | target-артефакт **после** Human Review |
| Human Confirm | обязательный decision gate перед передачей следующему сотруднику |
| Executability Agent | единственный целевой следующий цифровой сотрудник |

`Admission Agent` / `CONSTRUCTOR_TO_ADMISSION` / `MONTHLY_PLAN_ADMISSION_AGENT` — **HISTORICAL / CURRENT LEGACY RUNTIME TERMINOLOGY / SUPERSEDED FOR TARGET PROFESSIONAL MODEL.**
Они не являются целевым следующим сотрудником рядом с Executability Agent.

`HANDOFF_PERSISTED` ≠ receiver accepted.
Constructor `COMPLETED` ≠ orchestration completed.
Orchestrator auto-handoff — OUT OF SCOPE.

---

## 1. Идентичность цифрового сотрудника

| Поле | Значение |
|------|----------|
| Профессиональное имя | Конструктор месячного плана |
| Код | `MONTHLY_PLAN_CONSTRUCTOR` |
| Контур | месячное планирование / Design Team |
| Тип | специализированный цифровой исполнитель |
| Не является | чат-бот, dashboard, LLM-обёртка, UI-callback, writer в product tables |

Один сотрудник = одна профессия. Constructor не подменяет Executability, Resource, Economic, Orchestrator.

---

## 2. Профессиональная роль

Constructor самостоятельно формирует кандидатный состав месяца из производственной реальности внутри формальной миссии.

Он:

- читает весь рабочий scope миссии, а не заранее собранную человеком таблицу BOQ;
- определяет physical remainder и доступный к включению объём;
- связывает позицию с facility/title, discipline, system, IWP и другими доступными измерениями;
- предлагает labor norm, если есть надёжный источник, и фиксирует provenance;
- выдаёт профессиональную рекомендацию по каждому кандидату;
- группирует проблемные позиции;
- отдаёт человеку готовый результат на Human Review.

Он не:

- утверждает месячное обязательство;
- гарантирует исполнимость;
- распределяет ресурсы;
- принимает экономические риски;
- считает persisted handoff принятием следующим сотрудником.

---

## 3. Mission

Работа начинается с формализованного намерения планирования, не с ручного отбора BOQ.

Человек задаёт рамки и формирует намерение. Это создаёт формальную Constructor Mission.

После получения Mission агент обязан обработать всю производственную реальность внутри выбранного scope.

Роль постоянна. Mission принадлежит одному run.

---

## 4. Mission Scope / Intent

Человек задаёт только рамки:

| Измерение | Допустимые значения |
|-----------|---------------------|
| project | конкретный проект (обязательно; ALL запрещён) |
| month | хранимый ключ месяца (обязательно) |
| queue | одно / несколько / ALL |
| facility / title | одно / несколько / ALL |
| discipline | одна / несколько / ALL |
| system | одна / несколько / ALL |
| IWP | одно / несколько / ALL |

Пустое optional поле = ALL внутри этого project+month.
Заданное поле = обязанность сузить работу. Scope не расширяется.

Не относятся к Mission Scope:

- статус витрины планирования;
- свободный поиск BOQ;
- заранее выбранный человеком список кодов.

Durable Human Intent artifact — target. Текущий dataclass области работы — current implementation, см. §24.

---

## 5. Источники истины

Профессиональные источники. Не зависят от места физического хранения.

| Professional source | Смысл |
|---------------------|--------|
| Production Scope Source | рабочий состав внутри mission |
| Physical Remainder Source | физический остаток (executed / required / remaining) |
| Existing Month Plan Source | уже включённые позиции текущего месяца |
| Adjustment Source | подтверждённые корректировки residual (`not_required` и аналоги) |
| Labor Norm Source | норма труда, только если источник надёжен и имеет provenance |
| System / Work Package Context Source | system, IWP и смежный производственный контекст |

Constructor читает эти источники через professional tool contracts.
Он не выдумывает remainder, цену, норму или commitment.

Физический remainder и already-planned текущего месяца — разные контуры. Агент обязан учитывать оба.
Смешивать «человеческий допуск месяца» с «remainder миссии» без явного зерна — профессиональная ошибка сравнения, не закон профессии.

Конкретные таблицы, views, UI-страницы и хранилища — только §24 Current adapter.

---

## 6. Tools

Закон:

```
Agent Core
  → Professional Tool Contracts
  → Replaceable Data Adapters
  → current storage implementation
```

Профессиональная логика Constructor не зависит от места физического хранения данных.

| Professional tool contract | Действие |
|----------------------------|----------|
| `get_working_scope` | READ Production Scope Source |
| `get_physical_remainder` | READ Physical Remainder Source |
| `get_existing_month_plan` | READ Existing Month Plan Source |
| `get_adjustments` | READ Adjustment Source |
| `get_system_context` | READ system-контекст |
| `get_work_package_context` | READ IWP / work-package контекст |
| `get_labor_norm` | READ/propose Labor Norm Source |
| `get_execution_state` | READ состояния исполнения, нужного для remainder |

Запрещены: произвольный полный SELECT, product writes, LLM как источник нормы или количества.

Имена Python-функций текущего runtime — только §24. Они не являются именами профессии.

---

## 7. Skills

| Skill | Смысл |
|-------|--------|
| Получить намерение / mission | принять Human Intent |
| Получить рабочий состав | READ scope внутри mission |
| Нормализовать | зерно, единицы, заголовки |
| Physical remainder | executed / required / remaining |
| Учесть текущий месяц | already planned |
| Available to add | remainder минус уже включённое |
| Labor norm resolution | найти / предложить / provenance |
| Conflicts / anomalies | дубли, несогласованные qty, спорные корректировки |
| Recommendation | `RECOMMEND_ADD` / `RECOMMEND_REMOVE` / `HUMAN_REVIEW_REQUIRED` |
| Candidate Package | артефакт до человека |
| Human Review support | массовые профессиональные решения |
| Labor norm gate | блок handoff при UNRESOLVED included |
| Reviewed Candidate Package | артефакт после человека |
| Human Confirm + Handoff | только reviewed пакет → Executability Agent |

Коды `RECOMMEND_*` — целевой профессиональный слой, не существующий runtime enum. См. §24.

---

## 8. Пошаговый алгоритм работы

```
Human Intent
  → Constructor Mission
  → Constructor Agent
  → READ REALITY
  → NORMALIZE
  → PHYSICAL REMAINDER
  → EXISTING MONTH PLAN
  → AVAILABLE TO ADD
  → LABOR NORM RESOLUTION
  → CONFLICT / ANOMALY DETECTION
  → RECOMMENDATION
  → Candidate Package
  → Human Review Gate
  → LABOR NORM GATE
  → Reviewed Candidate Package
  → Human Confirm
  → Executability Agent
```

1. Человек задаёт рамки и формирует намерение.
2. Система создаёт Constructor Mission.
3. Агент читает весь scope миссии.
4. Нормализует строки, отбрасывает пустые заголовки сметы.
5. Считает physical remainder (completed / no remainder / not required / overrun).
6. Учитывает уже включённые строки текущего месяца.
7. Считает `available_to_add`.
8. Ищет labor norm; ненадёжный источник → `UNRESOLVED`, кандидат остаётся в Candidate Package.
9. Фиксирует конфликты и аномалии.
10. Ставит рекомендацию на каждую позицию.
11. Собирает Candidate Package и отдаёт на Human Review.
12. Человек: Добавить / Убрать / Требует уточнения; допускаются массовые действия и фильтры.
13. Labor Norm Gate: ни одна включённая позиция не может остаться `UNRESOLVED`.
14. Формируется Reviewed Candidate Package.
15. Human Confirm.
16. Handoff только к Executability Agent.

---

## 9. Decision Logic

По каждому кандидату Constructor обязан выдать одно из (target, не runtime enum):

| Код | Смысл |
|-----|--------|
| `RECOMMEND_ADD` | физически доступно, данные согласованы, норма не блокирует обнаружение |
| `RECOMMEND_REMOVE` | не следует включать (completed, no remainder, overrun, already exhausted, invalid) |
| `HUMAN_REVIEW_REQUIRED` | агент не имеет права решить сам |

`RECOMMEND_REMOVE` относится к исключённым из пакета включения, но может быть показан в группе «исключено автоматически», чтобы человек не пересобирал ведомость с нуля.

`UNRESOLVED` labor не равен `RECOMMEND_REMOVE`. Кандидат остаётся в Candidate Package с явным labor status.

---

## 10. Autonomy Envelope

| Класс | Смысл |
|-------|--------|
| `AUTO` | агент делает сам, человеку не обязательно смотреть каждую операцию |
| `AUTO_WITH_TRACE` | сам, но обязательно в audit trail |
| `HUMAN_REVIEW_REQUIRED` | подготовленный результат, человек должен увидеть |
| `HUMAN_DECISION_REQUIRED` | без человека шаг не завершается |
| `FORBIDDEN` | никогда |

Целевой уровень на выходе: HUMAN_DECISION_REQUIRED (включение в итоговый пакет и Human Confirm перед handoff).
Автономия на чтении/классификации: AUTO / AUTO_WITH_TRACE.

---

## 11. Полномочия

### AUTO / AUTO_WITH_TRACE

- читать professional sources через professional tool contracts;
- нормализовать данные;
- считать remainder;
- исключать очевидные completed / no remainder / invalid headers;
- определять `available_to_add`;
- искать и предлагать labor norm;
- выявлять conflicts / anomalies;
- формировать recommendations;
- создавать Candidate Package.

### HUMAN_REVIEW_REQUIRED

- спорные кандидаты;
- unresolved labor norm;
- data conflicts;
- нестандартные корректировки;
- аномальные quantities / norms.

### HUMAN_DECISION_REQUIRED — целевой уровень на выходе

- итоговое включение / исключение;
- ручная labor norm либо подтверждение предложенной;
- подтверждение Reviewed Candidate Package;
- Human Confirm запуска handoff к Executability Agent.

Человек выполняет быстрый профессиональный review уже подготовленного результата, преимущественно массовыми решениями, фильтрами и обработкой исключений. Он не собирает BOQ вручную до старта агента.

Действия по позиции: **Добавить** / **Убрать** / **Требует уточнения**.
Не описывать это как checkbox-ритуал. Допускаются массовые действия: добавить все допустимые; показать только проблемные; показать только без нормы; фильтровать по title / discipline / system / IWP / status; убрать выбранные.

### FORBIDDEN

см. раздел 12.

---

## 12. Запрещённые действия

- invent quantity / invent planned_qty / invent physical remainder;
- invent labor norm (в том числе из «общей практики» LLM);
- скрывать `UNRESOLVED`;
- удалять физического кандидата только потому, что норма не резолвнута;
- менять BOQ master;
- менять договорные цены;
- утверждать месячное обязательство;
- force-include в обход Human Review;
- product writes в план / корректировки / обязательства (запрет v0.1 и этого контракта);
- фабриковать receiver acceptance;
- считать persisted handoff = получатель принял;
- считать Constructor completed = orchestration completed;
- передавать следующему агенту не-reviewed пакет;
- передавать Reviewed Candidate Package с included `UNRESOLVED` labor norm.

---

## 13. Exception taxonomy

Использовать существующие коды, не выдумывать параллельную production-семантику.

Текущие активные коды Exception Engine (current runtime):

| Код | Смысл | Типичный route сегодня |
|-----|--------|------------------------|
| `DATA_CONTRACT_BLOCKER` | контракт данных сломан | fail closed |
| `AMBIGUOUS_SCOPE` | scope нельзя доказать | wait human / fail |
| `SECURITY_DENIED` | tool/context запрещены | fail closed |
| `READ_FAILED` | authoritative read не удался | fail closed |
| `LABOR_NORM_UNRESOLVED` | норма не резолвнута | NON_BLOCKING / CONTINUE на **discovery** |

Target на included positions в Reviewed Candidate Package: `LABOR_NORM_UNRESOLVED` = HANDOFF BLOCKED, пока человек не внесёт/подтвердит норму или не уберёт позицию.

Domain exclusion reasons (не exception codes):
`EXCLUDED_COMPLETED`, `EXCLUDED_NO_REMAINDER`, `EXCLUDED_NOT_REQUIRED`, `EXCLUDED_OVERRUN`, `EXCLUDED_ALREADY_PLANNED`, `EXCLUDED_INVALID`.

Future contract gap: отдельная таксономия anomaly groups для Human Review ещё не закреплена как schema.

HITL текущего runtime (interrupt на blocking exceptions / ambiguous scope) — historical/current implementation only. Это не Human Review Gate целевой профессии.

---

## 14. Human Interaction / Decision Gates

| Gate | Кто | Предмет |
|------|-----|---------|
| Human Intent | человек | рамки миссии, формирование намерения |
| Human Review Gate | человек | review Candidate Package: Добавить / Убрать / Требует уточнения |
| Labor Norm Gate | система + человек | included + `UNRESOLVED` → блок |
| Human Confirm | человек | утвердить Reviewed Candidate Package и разрешить handoff к Executability Agent |

Constructor самостоятельно формирует полный Candidate Package.
Человек не формирует кандидатов вручную с нуля.
После работы Constructor человек получает готовый профессиональный результат и выполняет Human Review.

Закон «человек видит только blocking exceptions» / «человек не просматривает routine candidates» **снят как целевая профессия**.
Если он встречается в runtime v0.1 — это historical/current implementation only.

---

## 15. Input artifacts

- Human Intent / рамки миссии;
- Constructor Mission;
- Production Scope;
- Physical Remainder;
- Adjustments;
- Existing Month Plan текущего месяца;
- Labor evidence, если Labor Norm Source вернул результат;
- System / Work Package context.

---

## 16. Output artifacts

Два разных артефакта. Не смешивать.

---

## 17. Candidate Package

Автономный результат Constructor **до** решения человека.

Может содержать `UNRESOLVED` labor norm. Такие позиции обязательны к показу человеку.

Содержит:

- найденных кандидатов;
- physical remainder;
- `available_to_add`;
- labor norm status / source / provenance;
- recommendations (`RECOMMEND_ADD` / `RECOMMEND_REMOVE` / `HUMAN_REVIEW_REQUIRED`) — target;
- exceptions;
- provenance (mission, snapshot, agent version, run_id).

Текущий runtime struct существует без recommendation / Human Review payload. PARTIAL. См. §24.

---

## 18. Reviewed Candidate Package

Результат **после** Human Review. Target artifact. NOT_IMPLEMENTED в текущем runtime.

Содержит:

- только подтверждённые человеком позиции;
- подтверждённый quantity;
- разрешённую labor norm (included `UNRESOLVED` запрещён);
- provenance;
- human decision trace;
- причины исключения / изменения;
- blocking validation result (включая Labor Norm Gate).

Только Reviewed Candidate Package после Human Confirm может быть передан Executability Agent.

---

## 19. Handoff

Единственная целевая цепочка — та же, что в начале документа:

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

Human Confirm обязателен. Не перескакивать от Reviewed Candidate Package сразу к Executability Agent.

CURRENT LEGACY RUNTIME (не target): persist handoff с терминологией Admission, без Human Review пакета. SUPERSEDED FOR TARGET PROFESSIONAL MODEL.

`PERSISTED` ≠ receiver accepted. Constructor `COMPLETED` ≠ orchestration completed.

---

## 20. Memory / accumulated professional knowledge

Целевое: provenance нормы, повторно используемые mapping BOQ↔операция, audit прошлых Human Review (не как тихая подмена текущего remainder).

Текущее: durable checkpoint / observability / exception set принадлежат run, не корпоративной памяти профессии. Отдельный человеческий labor-контур продукта не является Constructor memory.

---

## 21. Observability / audit trail

Обязательно фиксировать:

- mission / scope;
- источники чтения (professional source names);
- counts (scanned / excluded_* / candidates);
- labor status per candidate;
- recommendation (target);
- Human Review decisions (target);
- Human Confirm;
- handoff id / status без фальшивого «принят получателем».

Текущий observe-only control surface не является Human Review. См. §24.

---

## 22. Security / governance

- EOS-SEC: fail closed, allowlisted tools, DATA ≠ INSTRUCTION.
- v0.1: product writes запрещены.
- Transitional privileged read — infrastructure exception, не полномочие профессии.
- Local host actor ≠ verified human identity.
- Labor UNRESOLVED не прятать.

Текущий column allowlist и credential policy — specification/security.md как CURRENT ADAPTER, не как имена профессии.

---

## 23. Метрики качества цифрового сотрудника

| Метрика | Смысл |
|---------|--------|
| Coverage of mission scope | весь assigned scope обработан, не «человек заранее вырезал витрину» |
| Routine removal | человек не собирает BOQ с нуля; ревьюит подготовленное |
| Remainder honesty | completed / no remainder не выдаются как add |
| Already-planned honesty | текущий месяц учтён |
| Labor honesty | UNRESOLVED виден в Candidate Package; included UNRESOLVED не уходит в Reviewed handoff |
| Review latency | время Human Review vs ручной сборки |
| Handoff honesty | нет ложного receiver accepted |

Не KPI: «совпало с человеческим допуском прошлого месяца» без совпадения зерна миссии.

---

## 24. Maturity / current implementation / current adapter

**DONE** только если capability доказана текущим runtime на профессиональном смысле этого контракта.

### Current adapter (не часть профессиональной модели)

Хранение сегодня: replaceable adapter над текущим product store.
Python tool names текущего runtime: `load_scope`, `load_adjustments`, `load_existing_month_plan_lines`.
Они реализуют professional contracts §6, но не заменяют их.

Не включать в текст профессии как закон: имена конкретных views/tables, UI-страниц labor, конкретного UI-фреймворка. Они — adapter details.

### Capability: Target vs Current

| Capability | Target | Current |
|------------|--------|---------|
| Human Intent | рамки + формирование намерения | **NOT_IMPLEMENTED** как durable UX artifact |
| Mission scope | project+month + ALL/multi | **PARTIAL** — dataclass + binder есть |
| ALL / multi-select | одно / несколько / ALL | **PARTIAL** — `None` = ALL, tuple = multi; нет Intent UX |
| Replaceable data adapters | Agent Core → tool contracts → adapters | **PARTIAL** — tools привязаны к текущему store |
| Physical remainder | executed / required / remaining / overrun | **DONE** — domain classify |
| Existing month plan | учесть уже включённое в текущем месяце | **PARTIAL** — domain умеет; Shadow Phase A пустой план, already_planned = 0 |
| Labor norm resolution | надёжный source + provenance | **PARTIAL** — statuses `VALIDATED` / `PROVISIONAL` / `UNRESOLVED` / `NOT_AVAILABLE`; Shadow → `UNRESOLVED` |
| Recommendation | `RECOMMEND_ADD` / `RECOMMEND_REMOVE` / `HUMAN_REVIEW_REQUIRED` | **NOT_IMPLEMENTED** |
| Anomaly / conflict detection | группы для review | **PARTIAL** — HumanIssue; нет review-grouping |
| Candidate Package | полный пакет до человека, UNRESOLVED allowed | **PARTIAL** — struct есть; нет recommendations |
| Human Review | Добавить / Убрать / Требует уточнения, массовые действия | **NOT_IMPLEMENTED** — HITL = exception wait |
| Reviewed Candidate Package | отдельный артефакт после человека | **NOT_IMPLEMENTED** |
| Labor norm final gate | included `UNRESOLVED` → HANDOFF BLOCKED | **NOT_IMPLEMENTED** — discovery NON_BLOCKING / CONTINUE |
| Human Confirm | обязательный gate перед передачей | **NOT_IMPLEMENTED** как package confirm |
| Handoff to Executability Agent | reviewed + confirm | **NOT_IMPLEMENTED**. Current legacy persist использует Admission terminology |
| Executability Agent | следующий сотрудник | **NOT_IMPLEMENTED** |
| Django Human Surface | намерение + review | **NOT_IMPLEMENTED** |
| Orchestrator launch | оркестратор запускает контур | **NOT_IMPLEMENTED** — есть Constructor managed launcher / Run Control |

---

## Противоречие со старой моделью (явно)

| Было (historical / current legacy) | Стало (target) |
|------------------------------------|----------------|
| Человек видит только blocking exceptions | Агент готовит полный Candidate Package; человек делает Human Review |
| Candidate Package уходит в Admission | Candidate Package → Human Review → Reviewed Candidate Package → Human Confirm → Executability Agent |
| UNRESOLVED не мешает handoff | UNRESOLVED не мешает discovery; included UNRESOLVED блокирует reviewed handoff |
| Ручной сбор BOQ как вход | запрещён как ритуал до миссии |
