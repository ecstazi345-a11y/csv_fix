# Профессиональный паспорт цифрового сотрудника

**Название:** Конструктор месячного плана
**System code:** `MONTHLY_PLAN_CONSTRUCTOR`
**Версия паспорта:** v1.0
**Соответствует технической версии агента:** v0.1
**Technical status:** 10 / 10
**Professional status:** TECHNICALLY PROVEN DIGITAL EMPLOYEE
**Организационный слой:** Проектировочная команда / Design Team of the AI-native organization
**Бизнес-контур:** Контур месячного планирования
**Позиция в цепочке (целевая):** Оркестратор месячного плана → **Конструктор месячного плана** → Агент допуска
**Текущая доказанная роль:** Конструктор месячного плана
**Core product:** Пакет кандидатов месячного плана / Candidate Package

---

## 1. Назначение этого документа

**Professional Passport / Профессиональный паспорт** — устойчивое определение цифрового сотрудника как **профессиональной роли**.

Это **не**:

- журнал прогресса разработки;
- документация исходного кода;
- отчёт о тестах;
- prompt;
- инструкция для чат-бота;
- описание UI.

Паспорт отвечает на вопросы:

1. **Кто** этот цифровой сотрудник?
2. **Какую профессиональную работу** он выполняет?
3. **Какую ответственность** он несёт?
4. **Где заканчиваются** его полномочия?
5. **Какой результат** он производит?

Читатель должен понять профессию **без чтения Python-кода**.

---

## 2. Профессия в одном предложении

**Конструктор месячного плана** — цифровой сотрудник, который из текущей производственной реальности формирует структурированный кандидатный состав работ месяца, проверяет профессиональную корректность исходных данных в пределах своей Mission Scope / области задания, разрешает нормы труда, выявляет исключения, останавливается перед решениями вне своих полномочий и формирует formal handoff пакета кандидатов для целевой профессиональной роли Агента допуска; факт запуска или принятия результата получателем этим не подтверждается.

Он **не** утверждает месячный план, **не** гарантирует исполнимость, **не** распределяет итоговые ресурсы, **не** принимает риски, **не** утверждает деньги и **не** фиксирует производственное обязательство компании. Эти решения принадлежат последующим ролям.

---

## 3. Зачем существует эта профессия

### 3.1. Классическая практика

Первый кандидатный состав месяца часто собирается через:

- Excel;
- совещания;
- телефонные согласования;
- субъективные заявки («давайте поставим 20 человек»);
- ручной просмотр BOQ;
- фрагментированную информацию;
- слабую связку ПТО / участок / МТО / планирование.

### 3.2. Профессиональная проблема

Первичная сборка кандидатного состава месяца:

- выполняется вручную;
- занимает много времени инженеров;
- получается несогласованной между итерациями;
- часто пересобирается заново после уточнения объёма.

### 3.3. Последствия

Это повышает:

- координационную нагрузку;
- потери времени ИТР;
- нестабильность базы планирования;
- риск ошибочных решений на этапе допуска;
- слабость последующего ресурсного планирования;
- ухудшение прогноза освоения / earned value.

Конструктор **не решает все** эти проблемы в одиночку. Он закрывает первую профессиональную роль: **корректно и трассируемо сформировать кандидатный состав** как вход для Агента допуска и дальнейшей цепочки.

---

## 4. Место в цифровой организации

**Целевая цепочка ролей:**

```
Оркестратор месячного плана
  → Конструктор месячного плана
  → Агент допуска
  → (далее, целевая архитектура)
       Ограничения → Ресурсная ёмкость → Экономическая оценка
       → Управленческое решение → Human Decision Gate
       → Паспорт месячного производственного обязательства
```

**Текущая доказанная роль этого паспорта:** Конструктор месячного плана.
Исполнение Оркестратора и Агента допуска как downstream runtime этим паспортом **не** доказывается.
**Конструктор** — один специализированный цифровой сотрудник / specialized digital employee.

Он **не** является:

- всем оркестратором;
- супер-агентом;
- системой календарного планирования;
- заменой всех планировщиков;
- базой данных;
- dashboard.

Закон декомпозиции Execution OS: **одна крупная профессиональная роль = один специализированный агент**. Общие capability (например, Labor Norm Resolver) — это не отдельные агенты.

---

## 5. Профессиональная ответственность

### 5.1. Что Конструктор владеет

**Сформировать корректный, структурированный и трассируемый кандидатный состав работ месяца из доступной производственной реальности в пределах утверждённой Mission Scope / области задания.**

В рамках ответственности:

- зафиксировать область задания;
- безопасно прочитать разрешённую реальность;
- рассчитать физическую доступность по утверждённой BOQ-логике;
- учесть уже включённые строки месяца и ручные исключения остатка;
- сформировать кандидатов (не утверждённые строки плана);
- разрешить статус нормы труда;
- выявить профессиональные исключения;
- при необходимости остановиться на Human Decision Gate;
- после релевантного решения перечитать реальность;
- подготовить и надёжно сохранить formal handoff для Агента допуска;
- завершить **свою** профессиональную ответственность.

Граница v0.1: **READ → ANALYZE → PROPOSE → TRACE**.

### 5.2. Что Конструктор не владеет

Конструктор **не владеет**:

- финальным допуском работ / Admission;
- закрытием ограничений / Constraint;
- финальной ресурсной ёмкостью;
- финальной экономической оценкой;
- управленческим commitment;
- утверждением паспорта месяца;
- приёмкой выполненных работ;
- коммерческим признанием;
- cash;
- командами роботам / дронам;
- всей оркестрацией месячного планирования.

`READY_FOR_HANDOFF` и даже `RUN_COMPLETED` Конструктора **не означают**, что месяц утверждён или что Агент допуска уже принял работу.

---

## 6. Входная реальность

### 6.1. Mission Scope vs бизнес-реальность

| Понятие | Смысл |
|---------|--------|
| **Mission / Миссия** | Конкретное профессиональное задание одного запуска |
| **Mission Scope / Область задания** | Формальная граница, где сотруднику **разрешено** работать |
| **Business reality / Производственная реальность** | Данные scope, корректировок, уже существующих строк плана и свидетельств по нормам труда, читаемые внутри scope |

### 6.2. Что читает сотрудник

В пределах утверждённых контрактов и allowlist:

- проект (`project_code`);
- месяц (`month_key`);
- facility / building;
- discipline;
- system;
- IWP;
- queue (где поддерживается контрактом);
- позиции BOQ / кандидаты работ;
- ручные исключения остатка (`not_required`);
- уже включённые строки месячного плана;
- свидетельства / входы для разрешения нормы труда.

Не входят в Agent Mission Scope: витринные статусы UI планирования, свободный поиск BOQ, presentation-фильтры интерфейса.

---

## 7. Миссия (Mission)

**Mission** — конкретное профессиональное задание на один agent run.

В типичном managed-запуске:

1. Запрос на старт проходит через Run Control (авторизация, governance запуска).
2. Выдаётся `run_id` и связанный контекст исполнения.
3. Фиксируются `mission_id`, проект и месяц.
4. Задаётся Mission Scope (обязательные и опциональные границы).
5. Managed Launcher планирует исполнение runtime.

Конструктор работает **в рамках одной миссии**, а не «в свободном режиме по всей базе».

---

## 8. Область задания (Mission Scope)

### 8.1. Состав

Обязательно:

- `project_code`
- `month_key` (с канонизацией ключа месяца)

Опционально (сужение):

- `facility_scope`
- `discipline_scope`
- `system_scope`
- `iwp_scope`
- `queue_scope`

Значения `None` / `ALL` означают «все» в данном измерении.

### 8.2. Ключевые законы

1. Агент может **сужать** scope, но **не вправе молча расширять** его.
2. Работа вне scope — **fail closed** / безопасный отказ.
3. Проект «все» / «all» запрещён.
4. Месяц не угадывается из системных часов.
5. Enforcement двойной: фильтрация при чтении + post-read assertion.

---

## 9. Профессиональные навыки (Skills)

Ниже — навыки, поддерживаемые спецификацией и доказанным runtime v0.1.

| # | Skill | Профессиональный смысл |
|---|--------|-------------------------|
| 1 | Binding Mission Scope / Фиксация области задания | Зафиксировать и проверить область полномочий миссии |
| 2 | Secure Reality Reading / Безопасное чтение реальности | Прочитать разрешённые источники через allowlist tools |
| 3 | Candidate Assembly / Формирование кандидатного состава | Собрать кандидатов: доступность, исключения, уже запланированное |
| 4 | Labor Norm Resolution / Разрешение нормы труда | Определить статус нормы труда без удаления физической позиции |
| 5 | Exception Analysis / Анализ исключений | Классифицировать blockers, wait-human и non-blocking исключения |
| 6 | Human Decision Preparation / Подготовка вопроса человеку | Сформировать формальный объект решения, а не «вопрос в чат» |
| 7 | Reality Revalidation / Повторная проверка реальности | После релевантного решения перечитать свежую реальность |
| 8 | Business Artifact Formation / Формирование пакета кандидатов | Создать структурированный Candidate Package |
| 9 | Professional Handoff / Формальная передача результата | Построить и durably сохранить передачу Агенту допуска |

Базовые skills спецификации v0.1 также включают: `get_working_scope`, `calculate_availability`, `apply_existing_month_plan`, `exclude_unavailable`, `detect_conflicts`, `build_candidates`, `build_human_exceptions`, `prepare_handoff`.

---

## 10. Инструменты (Tools)

Tools — **контролируемые способности**, а не неограниченный доступ к инфраструктуре.

### 10.1. Secure Read Tools

Разрешённые READ-инструменты (security manifest):

- `load_constructor_scope`
- `load_constructor_adjustments`
- `load_constructor_month_plan_lines`

`allowed_write_tools` в v0.1: **пусто**.

### 10.2. Capability внутри роли

**LaborNormResolver** — детерминированная capability / service внутри Конструктора.
Это **не** отдельный цифровой сотрудник и **не** отдельный professional agent.

### 10.3. Прочие границы

- handoff persistence — отдельный store boundary;
- observability recording — запись структурированных событий, не «логи как попало»;
- нет произвольного SQL / shell / HTTP.

---

## 11. Детерминированное ядро

Ключевой принцип: **ядро профессиональной логики Конструктора детерминировано**.

Жёсткая профессиональная истина (scope, расчёты доступности, статусы норм труда, правила исключений, identity событий, security checks, handoff contracts) **не должна зависеть от LLM**.

Это повышает:

- воспроизводимость;
- аудируемость;
- предсказуемость для ИТР и руководства.

---

## 12. Граница LLM

В каноническом доказанном исполнении:

**LLM не требуется** (`llm_enabled: false`).

Это **не** делает Конструктора «менее AI-native». Цифровой сотрудник определяется профессией, контрактами, lifecycle, Human Gate, артефактами и наблюдаемостью — а не наличием модели.

Будущее использование LLM допустимо только для ограниченных semantic / unstructured задач, где детерминированных правил недостаточно.

LLM **никогда** не должен становиться:

- security boundary;
- permission engine;
- авторитетом жёсткой арифметики;
- прямым writer в product DB;
- physical actuator.

Закон: **MODEL IS NOT A SECURITY BOUNDARY**.

---

## 13. Профессиональный жизненный цикл

### 13.1. Профессиональный поток

```
Получить миссию
  → зафиксировать область задания
  → прочитать реальность
  → сформировать кандидатов
  → разрешить нормы труда
  → выявить исключения
  → либо продолжить
  → либо остановиться на Human Decision Gate
  → после решения перечитать реальность
  → продолжить работу
  → сформировать бизнес-артефакт
  → подготовить передачу
  → надёжно сохранить handoff
  → завершить свою профессиональную ответственность
```

### 13.2. Основные состояния runtime (справочно)

| Код состояния | Смысл |
|---------------|--------|
| `CREATED` | Запуск создан |
| `MISSION_BOUND` | Область задания зафиксирована |
| `REALITY_LOADED` | Реальность прочитана |
| `PACKAGE_BUILT` | Пакет кандидатов собран |
| `LABOR_RESOLVED` | Нормы труда разрешены |
| `WAITING_FOR_HUMAN` | Требуется Human Decision |
| `APPLYING_HUMAN_DECISION` | Применение решения человека |
| `REVALIDATING_REALITY` | Reality Refresh |
| `READY_FOR_HANDOFF` | Готовность к профессиональной передаче |
| `FAILED` | Безопасный отказ / ошибка |

`READY_FOR_HANDOFF` — профессиональная готовность к передаче.
Операционное `RUN_COMPLETED` появляется только после успешной persistence handoff в managed-пути.

---

## 14. Human Decision Gate

Конструктор **не** «задаёт вопрос в чат».

Когда автономия должна остановиться, он создаёт **формальный управленческий объект**:

- причина / reason code;
- допустимые решения;
- evidence refs;
- interrupt identity;
- decision identity;
- actor provenance;
- controlled resume против активного wait / checkpoint.

Система фиксирует, кто представил решение (actor provenance), но сам факт наблюдения участника **не** является доказательством его полномочий.
**Observed actor ≠ Authorized actor.**
Enterprise authority / RBAC для Human Decision в текущем Constructor v1.0 **не** считается полностью смоделированным или доказанным.
### 14.1. Канонический пример

```
Неоднозначный scope (AMBIGUOUS_SCOPE)
  → STOP / WAITING_FOR_HUMAN
  → Human Decision: CLARIFY_SCOPE
  → Controlled Resume
  → Reality Refresh (свежее чтение)
  → продолжение профессиональной работы
```

Допустимые решения HITL v0.1: `CLARIFY_SCOPE`, `ABORT_RUN`.
Resumable reason для продолжения: `AMBIGUOUS_SCOPE`.

### 14.2. Формула HITL

```
Автономия останавливается
  → запрашивается структурированное решение
  → решение коррелируется
  → controlled resume
  → reality reread
  → профессиональное следствие
```

---

## 15. Когда сотрудник обязан остановиться

Поддерживаемые stop / fail условия:

| Условие | Поведение |
|---------|-----------|
| `AMBIGUOUS_SCOPE` | `WAIT_HUMAN` — формальный Human Decision Gate |
| `SECURITY_DENIED` (и родственные отказы контекста/tool) | `FAIL_RUN` — fail closed |
| `DATA_CONTRACT_BLOCKER` | `FAIL_RUN` |
| `READ_FAILED` | `FAIL_RUN` |
| `LABOR_NORM_UNRESOLVED` | **не** удаляет кандидата; non-blocking continue с корректным статусом |

**Fail Closed / Безопасный отказ:** при нарушении контракта, security или неоднозначности вне полномочий система предпочитает явную остановку / отказ, а не «догадку» и тихое продолжение.

---

## 16. Reality Refresh

Resume **не** означает: «продолжай со старыми допущениями».

После релевантного Human Decision:

```
Human Decision
  → Controlled Resume
  → Reality Refresh
  → Professional Continuation
```

Это защищает от планирования на устаревшей реальности и от передачи в Admission пакета, собранного на stale snapshot.

---

## 17. Бизнес-артефакт (Business Artifact)

### 17.1. Пакет кандидатов / Candidate Package

Это структурированный профессиональный артефакт — **вход для Агента допуска**.

Он **не** является:

- финальным месячным планом;
- утверждённым commitment;
- решением Admission.

### 17.2. Что содержит на профессиональном уровне

- identity пакета;
- provenance миссии / агента;
- provenance scope;
- записи кандидатов;
- сводки / counts;
- статус / summary норм труда;
- summary исключений.

Важные законы количества:

- physical available qty ≠ resource-feasible ≠ approved commitment;
- out-of-scope кандидаты fail closed;
- отсутствие / unresolved нормы труда **не удаляет** физическую позицию молча.

Observability и Control Room показывают **безопасную identity** артефакта, а не тело пакета как observability truth.

---

## 18. Handoff / Передача результата

### 18.1. Формальная передача

```
Конструктор
  → Candidate Package
  → intended professional role: MONTHLY_PLAN_ADMISSION_AGENT
```

Ключевые поля:

- `handoff_type = CONSTRUCTOR_TO_ADMISSION`
- `handoff_id` (детерминированный)
- `target_role_code = MONTHLY_PLAN_ADMISSION_AGENT`
- artifact identity (тип/id пакета)

### 18.2. Закон persistence

| Событие | Смысл |
|---------|--------|
| `HANDOFF_CREATED` | Валидный handoff-контракт построен |
| `HANDOFF_PERSISTED` | Handoff durably сохранён |

`HANDOFF_PERSISTED` **не означает**:

- receiver accepted;
- receiver started;
- ownership transferred;
- Admission completed.

---

## 19. Завершение источника (Source Completion)

Причинный закон managed-пути:

```
HANDOFF_CREATED
  < HANDOFF_PERSISTED
  < RUN_COMPLETED
```

`RUN_COMPLETED` Конструктора означает: **сотрудник завершил свою профессиональную ответственность** после успешной persistence handoff.

Это **не** означает:

- Admission completed;
- весь месячный план готов;
- человек утвердил месяц;
- orchestration completed.

---

## 20. Полномочия (Permissions)

| CAN | CANNOT (v0.1) |
|-----|----------------|
| Читать утверждённые источники в Mission Scope | Расширять собственный Mission Scope |
| Выполнять детерминированные профессиональные расчёты | Произвольно опрашивать БД / arbitrary SQL |
| Формировать внутренние бизнес-артефакты | Arbitrary shell / arbitrary HTTP |
| Выявлять исключения | Утверждать финальный месяц |
| Запрашивать Human Decision | Менять product reality без controlled write architecture |
| Сохранять контрактно валидную формальную передачу результата в пределах разрешённого механизма persistence | Командовать роботами / дронами |
| Эмитить observability | Обходить Human Gate |
| Писать trace в объект run (не в product DB) | Product INSERT/UPDATE/DELETE/UPSERT, invent qty/crew, LLM-вызовы |

Security tier: `TIER_0_READ_ONLY_DETERMINISTIC`.

---

## 21. Security / EOS-SEC

Для этого сотрудника действуют законы Execution OS Security:

| Закон | Смысл для Конструктора |
|-------|-------------------------|
| **MODEL IS NOT SECURITY BOUNDARY** | Модель не выдаёт права и не обходит allowlist |
| **DATA ≠ INSTRUCTION** | Поля продукта — данные, не команды |
| **LEAST PRIVILEGE** | Только узкие READ tools |
| **READ / WRITE SEPARATION** | v0.1 без product writes |
| **FAIL CLOSED** | При сомнении — отказ / stop, не угадывание |
| **HUMAN-GATED CRITICAL ACTIONS** | Критические будущие writes требуют человека |
| **NO SECRET LEAKAGE** | Секреты не в observability / артефактах / UI |
| **NO RAW LLM → WRITE** | Нет прямого LLM-письма в продукт |
| **NO RAW LLM → PHYSICAL ACTUATION** | Нет физического исполнения |

Control Room / Query Port — **read-only / observe-only**.

---

## 22. Состояние и память

Цифровой сотрудник **не должен** зависеть от скрытой prompt-памяти.

Профессиональное состояние вынесено наружу:

- lifecycle / runtime state;
- checkpoint для HITL resume;
- business artifacts;
- durable observability.

Долгосрочное общее бизнес-состояние целевым образом относится к shared operational storage.
Полноценный production Supabase observability adapter **не** заявлен как уже завершённая часть 10/10.

---

## 23. Runtime v0.1

Стек:

- Python;
- LangGraph;
- managed launcher;
- externalized observability;
- Human-in-the-Loop.

**Authoritative managed start:**

`RunControlService.start` + `ConstructorManagedRuntimeLauncher`

Текущий backend исполнения: background **thread**.
Thread — это реализация backend, **не** профессиональная идентичность. Будущий process/external worker должен сохранять те же contracts.

Streamlit **не** является владельцем runtime.

Разделение:

| Слой | Владеет |
|------|---------|
| Run Control | request, authorization, launch governance, `STARTING` |
| Runtime | advancement, lifecycle, Human Wait, resume consequence, completion |

---

## 24. Наблюдаемость (Observability)

Пять уровней Control Room:

| Уровень | Вопрос |
|---------|--------|
| **1. Digital Organization** | Куда перешёл профессиональный результат? |
| **2. Professional Agent Execution** | Что делал цифровой сотрудник? |
| **3. Stage Detail** | Какие стадии / tools / artifacts наблюдались безопасно? |
| **4. Human Decision** | Где остановилась автономия и какое решение принято? |
| **5. Forensic Audit Trace** | Какой аудиторский след остался? |

Компании нужно видеть не только «агент online», а **какую профессиональную работу** он выполнил.

---

## 25. Control Room

Control Room — **observe-only**.

Показывает:

- run;
- professional execution path;
- Human Decision;
- Reality Refresh;
- handoff;
- Digital Organization;
- audit evidence.

Control Room **не исполняет** агента и не является runtime.

---

## 26. Трассируемость

Корреляция через identity-цепочку (где контракт их предоставляет):

- `run_id`
- `mission_id`
- `authorization_id`
- `interrupt_id`
- `decision_id`
- `artifact_id`
- `handoff_id`

Цель: доказать связку **причина → действие → результат → передача**.

---

## 27. Replay / Durability (техническое управление)

Доказано:

- durable SQLite observability;
- object reopen;
- independent Query Port reconstruction;
- process-independent observability (Increment 10.5);
- PostgreSQL HITL durable restart ранее доказан в Increment 8, когда среда была доступна.

Текущая известная классификация:

**DURABLE_RESTART = ACCEPTABLE_ENVIRONMENT_EXCEPTION**

Причина: недоступны Docker / disposable PostgreSQL / authoritative local start procedure в текущей среде. Это **не** PASS, **не** FAIL и **не** code regression.

Полная универсальная production durability **не** заявлена как решённая.

### 27.1. Clock / Immutable Fact Law

Для replay того же Human Wait:

- **CLOCK_OWNER:** `FIRST_OCCURRENCE`
- **REPLAY_SEMANTICS:** `SAME_IMMUTABLE_FACT`

Один и тот же immutable fact должен сохранять время исходного возникновения.
Recorder остаётся fail-closed: same `event_id` + different fingerprint → conflict.

---

## 28. Какую рутину снимает с инженеров

Конструктор снимает повторяемую рутину:

- ручной сбор кандидатных работ;
- ручную фильтрацию по проекту / месяцу / scope;
- повторный просмотр BOQ;
- ручное формирование первого кандидатного списка;
- ручную проверку наличия нормы труда;
- ручную классификацию стандартных исключений;
- ручную подготовку структурированной эскалации;
- ручную пересборку после уточнения scope;
- ручную подготовку handoff-пакета.

### Что остаётся за человеком

- неоднозначность;
- профессиональное суждение;
- решения authority;
- принятие риска;
- бизнес-приоритезация;
- нестандартные случаи.

Агент берёт: сбор, проверку, классификацию, расчёт, повторение, трассируемость, подготовку передачи.

---

## 29. Ценность для бизнеса

### 29.1. Proven technical value

Доказано технически:

- повторяемое профессиональное исполнение;
- трассируемость;
- структурированный handoff;
- controlled Human Gate;
- Reality Refresh;
- снижение двусмысленности координации за счёт явных статусов и артефактов.

### 29.2. Target business value

Целевые эффекты (модель ценности, не измеренный ROI в этом паспорте):

- сокращение часов координации планировщика / ПТО;
- сокращение времени подготовки первого кандидатного состава;
- меньше пересборок кандидатного состава;
- меньше решений на устаревшей реальности;
- более быстрый и качественный вход в Admission.

**Не заявлены** достигнутые финансовые экономии.

---

## 30. Экономическая модель (будущие KPI)

Формулы — **будущая KPI-модель**, не достигнутые результаты:

**Routine Hours Saved**
= baseline manual coordination hours − human coordination hours with agent

**Candidate Preparation Lead Time Reduction**
= baseline preparation time − agent-assisted preparation time

**Rework Reduction %**
= 1 − (rebuilds_after_agent / rebuilds_baseline)

**Human Escalation Rate**
= runs requiring Human Decision / total runs

**Automation Coverage**
= deterministically completed professional operations / eligible professional operations

---

## 31. Профессиональные KPI

| Группа | KPI | Комментарий |
|--------|-----|-------------|
| Quality | Mission Scope violation rate | target = 0 |
| Quality | Untraceable handoff rate | target = 0 |
| Quality | False completion rate | target = 0 |
| Speed | Candidate package formation time | измерять после внедрения |
| Autonomy | Human Decision rate | не «чем меньше, тем лучше» всегда |
| Autonomy | Reality refresh completion rate | после релевантного resume |
| Quality | Labor norm unresolved rate | статус, не silent drop |
| Quality | Professional exception rate | по severity/route |
| Human load | Manual coordination hours saved | target business metric |
| Business effect | Package acceptance rate downstream | **FUTURE** — когда есть Admission |

Измеренные значения в паспорт v1.0 **не** внесены.

---

## 32. Критерии успеха одного запуска

Миссия Конструктора успешна, если:

1. Mission Scope соблюдён;
2. выполнено требуемое чтение реальности;
3. сформирован Candidate Package **или** формально остановлен с обоснованным исключением / Human Decision;
4. Human Decision использован, когда это требуется;
5. после релевантного resume выполнен Reality Refresh;
6. handoff persisted **до** source completion в managed-пути;
7. существует трассируемый audit trail;
8. нет security violations.

---

## 33. Критерии провала

Провалом считаются:

- выход за Mission Scope;
- unauthorized access;
- скрытая запись в product reality;
- fabricated evidence;
- completion без persistence handoff;
- silent ambiguity;
- untraceable decision;
- secret leakage;
- ложное заявление о завершении всей оркестрации.

---

## 34. Профессиональные сценарии

### Сценарий 1 — Чистый scope

Чёткий project/month/scope → автономное формирование Candidate Package → handoff → source completion.

### Сценарий 2 — Неоднозначный scope

`AMBIGUOUS_SCOPE` → Human Decision Gate → `CLARIFY_SCOPE` → Reality Refresh → продолжение → handoff.

### Сценарий 3 — Норма труда не разрешена

Кандидат **сохраняется** со статусом unresolved / корректным labor status; не удаляется молча.

### Сценарий 4 — Отказ безопасности / чтение

`SECURITY_DENIED` или `READ_FAILED` → fail closed / `FAILED`; нет «догадки» и скрытого продолжения.

### Сценарий 5 — Ошибка persistence handoff

Handoff не считается успешно переданным; source **не** заявляет успешный `RUN_COMPLETED` как будто persistence прошла.

### Сценарий 6 — Abort человеком

`ABORT_RUN` на открытом wait → run aborted by human; это не успешная передача в Admission.

---

## 35. Чем отличается от классического планировщика

Классический planner работает прежде всего с датами, последовательностями, календарями ресурсов и schedule-логикой.

Конструктор работает с **производственной реальностью**, чтобы сформировать кандидатный физический состав работ, который затем должен пройти Admission и другие профессиональные ворота.

Он **upstream** относительно финального commitment.
Он **не** позиционируется как замена Primavera / MS Project.

---

## 36. Чем отличается от чат-бота

Конструктор — не chatbot.

У него есть:

- formal mission;
- formal scope;
- skills;
- tools;
- permissions;
- state;
- lifecycle;
- Human Gates;
- business artifacts;
- handoff;
- durable observability;
- tests;
- security.

Главный выход — **бизнес-артефакт**, а не ответ на естественном языке.

---

## 37. Чем отличается от скрипта

Больше, чем script, потому что есть:

- lifecycle;
- условные решения;
- exceptions;
- human interruption;
- resume;
- revalidation;
- externalized state;
- handoff;
- observability;
- security boundaries.

При этом автономия **не** переоценивается: критические решения вне роли остаются за человеком и downstream-агентами.

---

## 38. Чем отличается от оркестратора

Конструктор владеет **одной** профессиональной ролью.

Оркестратор координирует роли.

Конструктор не должен поглощать:

- Admission;
- Constraint;
- Resource;
- Economic;
- Management Decision.

Это защищает архитектуру от супер-агента.

---

## 39. Будущая интеграция

Текущая доказанная передача:

```
Constructor → Candidate Package → intended Admission role
```

Целевая дальнейшая цепочка (архитектура, **не** текущее observed execution):

```
Admission
  → Constraint
  → Resource Capacity
  → Economic Evaluation
  → Management Decision
  → Human Decision Gate
  → Monthly Commitment Passport
```

Агент допуска / `MONTHLY_PLAN_ADMISSION_AGENT` — следующий специализированный цифровой сотрудник. В паспорте v1.0 он **не реализован**.

---

## 40. Версионирование

- Passport **v1.0** соответствует технически завершённому Constructor Agent **v0.1**.
- Изменение профессиональной capability требует обновления / инкремента паспорта.
- Bug fixes, не меняющие профессию, могут не требовать смены professional version, но обязаны сохранять tests/contracts.

---

## 41. Приложение A — Technical Completion Evidence

| Item | Value |
|------|--------|
| Technical completion | **10 / 10** |
| Final proof commit | `194bcfd27717f38b120a6651cf6794ce88a1d33a` |
| Final technical documentation commit | `ab839baea794c23809b9864d558b3ce01753dc68` |
| Full managed live run | **PASS** |
| Production-default clock/replay guard | **PASS** |
| EOS-SEC | **PASS** |
| Architecture drift (в 10.10) | **NO** |
| Durable restart | **ACCEPTABLE_ENVIRONMENT_EXCEPTION** |

Полный test journal в паспорт не копируется.

---

## 42. Приложение B — Digital Employee Completion Checklist

| Элемент | Статус |
|---------|--------|
| Role | DONE |
| Specification | DONE |
| Mission | DONE |
| Scope | DONE |
| Skills | DONE |
| Tools | DONE |
| Permissions | DONE |
| Security | DONE |
| Contracts | DONE |
| Lifecycle | DONE |
| State | DONE |
| Human-in-the-Loop | DONE |
| Business Artifact | DONE |
| Handoff | DONE |
| Runtime | DONE |
| Observability | DONE |
| Tests | DONE |
| Professional Passport | **v1.0 (этот документ)** |

---

## 43. Заключение

Constructor v1.0 — первый **завершённый** профессиональный цифровой сотрудник в контуре месячного планирования Execution OS.

Его архитектура становится **reference pattern** для следующих ролей.
Будущие агенты должны переиспользовать **принципы**, а не слепо копировать бизнес-логику Конструктора.

Следующий шаг программы: извлечь reusable Professional Passport Template, зафиксировать Constructor freeze, затем открыть architecture gate для **Агента допуска месячного плана**.
