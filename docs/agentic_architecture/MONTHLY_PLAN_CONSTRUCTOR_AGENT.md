# Monthly Plan Constructor Agent

**Профессиональное название:** Агент формирования кандидатного состава месячного плана<br>
**Код (текущая реализация):** `MONTHLY_PLAN_CONSTRUCTOR`<br>
**Версия спецификации:** v0.1 target (этот документ)<br>
**Реализация в коде:** MPCA-001 KEEP как deterministic ядро; MPCA-003 — эксперимент, не UX-закон.

---

## 1. Mission

Задача агента **не** показать человеку список BOQ.

Задача:

1. Получить производственную миссию месяца в заданном scope.
2. Самостоятельно обработать **весь** объём данных этого scope.
3. Исключить routine non-candidates.
4. Выявить exceptions.
5. Сформировать **candidate package**.
6. Поднять человеку только вопросы, где требуется профессиональное решение.
7. Подготовить structured handoff к Admission Agent.

Это соответствует Page52 и [ARCHITECTURE_BASELINE.md](ARCHITECTURE_BASELINE.md).

---

## 2. ConstructorMission

Цифровое **задание сотруднику**, не набор случайных UI filters.

Концепт: `ConstructorMission` (имя может стать dataclass / graph input; schema runtime OPEN).

Пример:

```
project:      PRJ_001_БХК
month:        сентябрь-2026          # хранимый ключ продукта, не date.today()
facility:     2041                   # титул / объект; или ALL
discipline:   вентиляция             # или ALL
system:       ALL
iwp:          ALL
queue:        <если задана человеком>
```

Человек сообщает область работы. Агент исполняет миссию внутри неё.

---

## 3. MonthlyPlanningScope — future canonical

UI и Agent используют **один** business scope contract.

### Обязательные

| Поле | Правило |
|------|---------|
| `project_code` | Конкретный проект. «Все» — не миссия. |
| `month_key` | Хранимый ключ месяца (`сентябрь-2026`). Канонический `2026-09` через существующий `normalize_month_key`. Агент **не** угадывает месяц из часов машины. |

### Опциональные explicit scope

| Поле | Если не задано | Если задано |
|------|----------------|-------------|
| `facility_scope` | ALL внутри project/month | агент работает **только** в этих титулах/объектах |
| `discipline_scope` | ALL | только эти дисциплины |
| `system_scope` | ALL | только эти системы |
| `iwp_scope` | ALL | только эти IWP |
| `queue_scope` | ALL | только эта очередь, если человек её задал |

Пустое optional поле = ALL.<br>
Заданное поле = **обязанность** сузить работу. Не игнорировать. Не «потом отфильтровать в UI».

### Не относятся к Agent Mission Scope

- статус витрины Page10B (`ДОСТУПНО` / `ВЫПОЛНЕНО` / …);
- свободный поиск BOQ;
- случайные presentation filters.

Агент **сам** классифицирует completed / no remainder / available.<br>
Человек не должен предварительно вырезать витрину, чтобы агент «правильно» посчитал.

---

## 4. Target lifecycle

```
MISSION_RECEIVED
  → LOAD_REALITY
  → CLASSIFY_SCOPE
  → BUILD_CANDIDATE_PACKAGE
  → CHECK_EXCEPTIONS
       ├─ exceptions > 0  → WAITING_FOR_HUMAN
       │                      → APPLY_HUMAN_DECISION
       │                      → REVALIDATE
       │                      → BUILD_CANDIDATE_PACKAGE
       └─ exceptions == 0 → PREPARE_HANDOFF
                              → HANDOFF_READY
                              → COMPLETED
```

Любая невозможность доказать безопасное состояние критического действия:

```
FAILED / BLOCKED
```

по fail-closed (EOS-SEC).

READ/ANALYZE/PROPOSE без записи плана не требует write-gate.<br>
Запись product state — только после отдельного Human Gate + WriteAuthorization (MPCA-002 KEEP; live write не разрешён).

---

## 5. What Constructor does automatically

Constructor сам:

- читает актуальный scope **миссии** (не весь проект, если scope ужежен);
- проверяет выполненный объём;
- определяет физический остаток;
- применяет подтверждённые корректировки (`not_required` и аналоги, уже существующие в продукте);
- исключает completed;
- исключает no remainder;
- учитывает already planned;
- проверяет duplicate / grain conflicts;
- формирует candidate identifiers (`constructor_candidate_id` = PROJECT\|MONTH\|FACILITY\|DISCIPLINE\|BOQ, uppercase; столкновения fail-closed / показать, не скрыть);
- классифицирует exceptions;
- формирует candidate package;
- пишет trace;
- готовит handoff;
- прикрепляет labor-norm metadata, **если** она доступна (не выдумывает).

Routine candidates **не** требуют ручного подтверждения каждой строки.

---

## 6. Human responsibility

Человек:

- задаёт mission / scope;
- сообщает новые факты;
- подтверждает спорные изменения реальности (например физический объём «по ведомости 120, факт требует 85»);
- решает exceptions;
- принимает управленческие решения контура (не подмена Admission/Economic).

Человек **не** должен:

- просматривать сотни routine BOQ как основной результат;
- ставить 175 checkbox;
- вручную переносить candidate rows;
- по каждой обычной позиции вводить qty/crew только потому, что агент не продолжает сам;
- вручную сообщать Admission, что сделал Constructor;
- держать state workflow в памяти.

### Human Gate — архитектурно (код security не менять сейчас)

Не 175 поэлементных подтверждений.

- **A.** Подтверждение самой mission/scope (задание).
- **B.** Подтверждение только исключений, где агент не имеет права решить.

Плюс EOS-SEC: критический write позже требует issuer-only approval / authorization.<br>
Предмет approval ≠ «каждая routine-строка».

---

## 7. Constructor and quantity

Открытый, но обязательный нюанс.

Constructor формирует **PHYSICAL CANDIDATE PACKAGE**.

Если физический доступный остаток однозначно доказан, он может использовать его как:

- `available_quantity` / candidate physical quantity.

Constructor **не** подменяет Resource Agent и **не** объявляет эту величину окончательным feasible commitment месяца, если для этого нужны:

- resource capacity;
- admission readiness;
- production limits;
- economic constraints.

Разделить всегда:

| Понятие | Кто | Смысл |
|---------|-----|--------|
| AVAILABLE PHYSICAL QUANTITY | Constructor (из scope/остатка) | Что физически ещё можно планировать в этом grain |
| FINAL COMMITTED QUANTITY | контур Admission → Resource → Economic → Decision → Паспорт | Что организация обязуется выполнить в месяце |

Запрет MPCA-001 «не invent planned_qty / physical quantity» сохраняется: нельзя выдумать объём.<br>
Использование доказанного остатка — анализ, не выдумка.<br>
Спорный остаток — exception человеку, не тихая правка ведомости.

Crew Constructor **не** выдумывает. Назначение звена — не routine constructor workflow. Resource / существующие product rules — отдельно.

Zero price ≠ нет физической работы. `unit_price = 0` не выкидывает кандидата из physical package.

---

## 8. Labor norm — Constructor behavior

Missing internal P50 **не** удаляет physical candidate.

Пример:

```
70 physical candidate works
  52 HIGH-CONFIDENCE internal norm
  11 provisional normative benchmark
   7 labor norm unresolved
```

Эти 7 **остаются** в physical package с metadata:

```
LABOR_NORM_STATUS: VALIDATED | PROVISIONAL | UNRESOLVED
```

Дальше:

- Admission проверяет физическую/организационную готовность;
- Resource не финализирует capacity по UNRESOLVED и инициирует resolution / exception;
- Economic показывает uncertainty;
- человек получает только реально необходимый вопрос.

Constructor не становится LaborNormResolver.<br>
Он **использует** shared capability, если результат есть.

Канон: [LABOR_NORM_RESOLUTION.md](LABOR_NORM_RESOLUTION.md).

На **write** path MPCA-002 по-прежнему: missing P50 → `LABOR_NORM_MISSING`, zero writes. Это закон записи plan line, не закон существования physical candidate.

---

## 9. Grain

Candidate grain (KEEP из MPCA-001):

```
constructor_candidate_id = PROJECT|MONTH|FACILITY|DISCIPLINE|BOQ
```

uppercase, fail-closed при коллизии. Не скрывать дубли.

---

## 10. Structured outputs

Минимальный смысл пакета (имена полей runtime OPEN):

- identity: agent_code, agent_version, run_id, mission, scope;
- counts: scanned, package_size, excluded_*, exceptions;
- candidate identifiers + physical quantities + labor_norm_status per item;
- exceptions list (только реальные);
- trace / audit (redacted, EOS-SEC);
- handoff block: см. [ORCHESTRATION_AND_HANDOFF.md](ORCHESTRATION_AND_HANDOFF.md).

Главная поверхность человека — **итог + exceptions**, не полный dataframe.

Полный расчёт — «Показать расчёт агента» (audit).

---

## 11. What current code actually does (2026-08-22)

### KEEP

Deterministic classify в `agents/monthly_plan_constructor/` (MPCA-001):

- read scope / adjustments / plan lines через trusted read executor;
- remainder / already planned;
- exclusions completed / no remainder / already planned;
- HumanIssue;
- no product write.

### Deviation (proven)

Page10B (`render_constructor_agent_workbench`) передаёт в агент только:

```
project_code, stored_month_key
```

Фильтры титул / дисциплина / очередь / система / IWP применяются **после** вызова агента и **только** к ручной таблице BOQ (`apply_scope_filters`).

Чтение: `load_constructor_scope(project_code)` — `eq("project_code")`.

Live: 447 scanned / 175 candidates на весь проект при выбранной вентиляции и титуле.

### Wrong human routine currently introduced

MPCA-003 показывает 175 кандидатов как main workbench.<br>
MPCA-002 моделирует `ApprovedPlanItem` с `approved_qty` + `approved_crew` на каждую строку.<br>
`skill_prepare_handoff` ставит `admission_handoff_ready=False`, пока человек не выберет crew/qty.

Это **не** target.

Не развивать новые UI-таблицы кандидатов.

---

## 12. KPI (Constructor)

См. [ARCHITECTURE_BASELINE.md](ARCHITECTURE_BASELINE.md) § Routine removal KPI.

Если агент обработал 447 и человек снова разбирает 175 — `routine_removal_percent` фактически уничтожен поверхностью, даже при `human_issues = 0`.

---

## 13. Next proof

Success = LangGraph (или эквивалентный workflow runtime) исполняет `ConstructorMission` в **заданном** scope и заканчивает `HANDOFF_READY` или `WAITING_FOR_HUMAN` **без** обязательной candidate table.

Не success = ещё одна таблица на Page10B.
