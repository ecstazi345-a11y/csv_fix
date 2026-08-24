# Анатомия профессионального цифрового сотрудника

Базовая инженерная модель цифрового сотрудника и агентной организации Execution OS.

**Status:** LIVING DOCUMENT / учебный стандарт<br>
**Date:** 2026-08-24<br>
**Scope:** все будущие агенты Execution OS, не только Constructor.

Это **не** specification конкретного агента и **не** журнал commits.<br>
Progress — в [AGENT_RUNTIME_PROGRESS.md](AGENT_RUNTIME_PROGRESS.md).<br>
Законы стека — в [ARCHITECTURE_BASELINE.md](ARCHITECTURE_BASELINE.md).<br>
Решения — в [DECISION_LOG.md](DECISION_LOG.md).<br>
Безопасность — в `security/agent_security_baseline.md` (EOS-SEC).

Документ опирается на Architecture Baseline, EOS-SEC и общепринятые **production-grade agentic principles**. Он **не** описывает внутреннюю архитектуру закрытых продуктов (ChatGPT, Claude, Codex и т.п.).

---

## Зачем этот документ

Цифрового сотрудника часто путают с чатом: «есть LLM, есть tool call — значит есть агент».

Для Execution OS этого недостаточно. Профессиональный digital worker — это **система**: роль, регламент, поручение, зона работы, умения, разрешённые инструменты, договоры, артефакты, состояние, жизненный цикл, runtime, полномочия, безопасность, человек, передача работы, наблюдаемость и тесты.

Документ объясняет владельцу и архитектору:

- из каких частей состоит цифровой сотрудник;
- как части связаны;
- зачем каждая нужна;
- как это выглядит на примере Constructor Agent.

Писать будем простым русским языком, без требования уметь программировать.

---

## Инженерный закон

```
AGENT ≠ CHATBOT
AGENT ≠ PROMPT
AGENT ≠ DASHBOARD
AGENT ≠ DATAFRAME
AGENT ≠ STREAMLIT CALLBACK
LLM ≠ AGENT
```

**LLM** — одна **заменяемая** способность рассуждения внутри сотрудника. Не профессия, не полномочие, не граница безопасности.

Устаревшая модель, которую мы не принимаем как «агента»:

```
LLM → prompt → tool → текстовый ответ
```

Современный production-grade digital worker включает как минимум:

professional role · specification · mission · scope · skills · tools · contracts · schemas · business artifacts · state · lifecycle · runtime · permissions · security · guardrails · human-in-the-loop · durable pause/resume · structured handoff · shared external state · events/triggers · observability · audit/trace · evals/tests · versioning · failure/retry · kill switch · replaceable models · orchestration.

---

## Основная аналогия

У обычного профессионального сотрудника есть:

должность; зона ответственности; должностная инструкция; компетенции; инструменты; полномочия; рабочие операции; текущее поручение; рабочие документы; руководитель; точки согласования; передача результатов; журнал действий.

У цифрового сотрудника всё это тоже есть, но формализовано в **software contracts / runtime / security / state**.

---

## Шаблон каждого понятия

Для каждого слоя ниже:

1. Что это простыми словами.
2. Аналог у обычного сотрудника.
3. Пример у Constructor Agent.
4. Зачем это профессиональной системе.
5. Чем **не** является (частая путаница).

---

## 1. Professional role / Agent role

1. **Кто** этот сотрудник в организации. Одна крупная профессия.
2. Должность: «инженер ПТО по формированию месячного состава».
3. `MONTHLY_PLAN_CONSTRUCTOR` — Агент формирования кандидатного состава месячного плана.
4. Чтобы не плодить «зоопарк агентов» и строить цифровую организацию из понятных ролей.
5. Не набор кнопок UI. Не «микроагент на каждую формулу».

**Закон:** ONE MAJOR PROFESSIONAL ROLE = ONE SPECIALIZED AGENT.

---

## 2. Specification

1. Технический паспорт профессии: зачем, что делает, чего не делает, что принимает, что выдаёт, кому передаёт, как принимают работу.
2. Должностная инструкция + регламент + границы полномочий + требования к результату.
3. `MONTHLY_PLAN_CONSTRUCTOR_AGENT.md` и runtime spec `AGENT_RUNTIME_V0_1_CONSTRUCTOR_MISSION.md`.
4. Чтобы через месяцы можно было восстановить профессию без истории чата.
5. Не prompt. Не пользовательская справка Page52 (Page52 — «зачем и кто»; spec — «как строить»).

---

## 3. Mission

1. Конкретное поручение **этому** запуску: что сделать сейчас. Роль постоянна, mission меняется.
2. Наряд / задание на смену: «по проекту X, сентябрь, объект Y, вентиляция».
3. Пример Constructor:
   - **Concept:** mission — поручение экземпляру/run агента.
   - **Implemented currently:** `ConstructorMissionScope` формализует рабочую область этой миссии (project + month + optional facility/discipline/system/IWP/queue).
   - **Designed / future contract:** отдельный тип `ConstructorMission` (если появится как самостоятельный schema) — пока **не** implemented asset. Сейчас миссия Constructor задаётся через scope-contract, а не через отдельный класс Mission.
4. Без mission агент не знает, какую работу выполнять. Scope отвечает **где**, mission — **какое поручение**.
5. Не фильтры экрана. Не search_text. Не visor status. Не session_state. Не путать implemented `ConstructorMissionScope` с ещё не существующим type `ConstructorMission`.

---

## 4. Scope

1. **Где** агент имеет право работать. Граница, а не удобный фильтр таблицы.
2. Участок, объект, дисциплина, очередь — зона ответственности.
3. Increment 1: `ConstructorMissionScope` + `bind_scope_to_mission`. Optional omitted = ALL **внутри** этого project+month, никогда все проекты.
4. Чтобы не повторить MPCA-003: UI выбрал объект, агент прочитал весь проект (447 строк).
5. Не UI filter utility. Scope не расширяется.

---

## 5. Skills

1. **Что** сотрудник профессионально умеет: классификация остатка, кандидаты, дубли, исключения.
2. Компетенции: «умеет читать ведомость и отделить выполнено от доступно».
3. Существующее deterministic ядро MPCA-001 (`classify_scope_rows`, remainder, already planned) предназначено к **reuse**. Increments 1–3 пока не подключают его как graph nodes.
4. Повторяемая профессиональная работа живёт в навыке, а не в промпте.
5. **SKILL ≠ AGENT.** Новый навык ≠ новый сотрудник.

---

## 6. Tools

1. **Чем** агенту разрешено трогать внешний мир (чтение БД, вызов сервиса).
2. Инструменты на объекте: только выданные, не любой ключ от склада.
3. Increment 3: `read_constructor_reality` → allowlisted `load_constructor_scope` через `AgentExecutionContext` + `validate_context_for_tool`. Economics tool **не** вызывается.
4. Формула: **SKILL = что умею. TOOL = чем мне разрешено это сделать.**
5. Не произвольный SQL. Не «раз сервис существует — агент может его вызвать». NO SERVICE BYPASS.

---

## 7. Contracts / schemas

1. Формальный язык между частями системы: поля, версии, обязательность.
2. Бланки и формы: заявка, акт, накладная — нельзя подменить свободным письмом.
3. `ConstructorMissionScope`, `CandidatePackage`, `ConstructorRealityRead`. В spec также будущие `HumanInterrupt`, `ConstructorHandoff`, `LaborNormResolution`.
4. Чтобы Admission не «догадывался» из текста, а читал договорённую структуру.
5. Не chat schema. Не «просто JSON как получится».

---

## 8. Business artifacts

1. **Что сотрудник реально произвёл** как рабочий документ.
2. Комплект документов по заданию, а не устный пересказ.
3. Increment 2: `CandidatePackage` — формальный кандидатный состав. Increment 3: `ConstructorRealityRead` — снимок прочитанной реальности (вход), не пакет кандидатов (выход).
4. Следующая роль и аудит понимают результат без чата.
5. **Output ≠ chat answer.** Artifact ≠ DataFrame ≠ таблица Streamlit ≠ запись в месячный план.

---

## 9. Nodes / operations

1. Внутренние шаги одной профессии: принять задание, прочитать, классифицировать, собрать пакет, проверить исключения, подготовить передачу.
2. Операции смены: получить наряд → осмотреть → заполнить форму → сдать мастеру.
3. В spec: `receive_mission` → `load_reality` → `classify_scope` → `build_candidate_package` → … LangGraph nodes **ещё не реализованы**.
4. Чтобы lifecycle был явным, а не «одна большая функция страницы».
5. **NODE ≠ AGENT.** Шаг работы ≠ новая должность.

---

## 10. State

1. Состояние **этой** работы (run): на каком шаге, какой snapshot, какой interrupt.
2. Папка текущего дела: что уже сделано, что ждёт согласования.
3. Спроектировано в runtime spec (маленький graph state + ссылки). **Не реализовано** как persistent run.
4. Разделение: runtime state ≠ business truth в Supabase ≠ копия всей ведомости в памяти графа.
5. Не session_state браузера. Не prompt memory как единственный источник.

---

## 11. Lifecycle

1. Жизненный цикл одной mission от приёма до завершения или паузы.
2. Регламент дела: открыто → в работе → на согласовании → передано → закрыто.
3. Целевой: `MISSION_RECEIVED` → `LOAD_REALITY` → `BUILD_PACKAGE` → `CHECK_EXCEPTIONS` → `WAITING_FOR_HUMAN` → `REVALIDATE` → `HANDOFF_READY` → `COMPLETED`. Пока это **закон spec**, не код Increments 1–3.
4. Чтобы закрытие экрана не означало смерть работы.
5. Не «нажали кнопку — функция вернула dict».

---

## 12. Runtime

1. Среда, где исполняется lifecycle: процессы, граф, checkpoint.
2. Рабочая среда: офис, станок, смена — не сама профессия.
3. Target: Python (business execution) + LangGraph (orchestration). LangGraph **не установлен**.
4. Python считает и проверяет. LangGraph ведёт долгоживущий процесс. LangGraph не профессия и не замена deterministic logic.
5. Runtime ≠ Streamlit. Закрытие страницы ≠ остановка сотрудника (закон; HITL ещё не реализован).

---

## 13. Shared state / business reality

1. Общая операционная реальность организации: остатки, план, корректировки.
2. Корпоративная система учёта, а не записная книжка в кармане.
3. Supabase. Агенты **перечитывают** актуальное. Handoff не заменяет чтение.
4. Чтобы два сотрудника не работали с двумя разными «правдами».
5. Agent memory ≠ business truth. Prompt dump ≠ shared state.

---

## 14. Memory

Не складывать всё в слово «memory». Различать:

| Вид | Смысл |
|-----|--------|
| Runtime state | Где сейчас этот run |
| Conversation / context | Краткий служебный контекст рассуждения |
| Long-term knowledge | Нормы, справочники, выученные паттерны (с provenance) |
| Shared operational state | Supabase — общая реальность |
| Business database | Те же таблицы продукта; агент не владеет ими как «своей памятью» |

---

## 15. Permissions

1. Что разрешено: read / write / invoke / approve / escalate.
2. Допуск на объект, право подписи, право открыть склад.
3. Constructor v0.1: **READ ONLY**. `write_allowed=False`. Нет права INSERT в месячный план.
4. Полномочие должно быть технически узким, не «модель обещала, что не напишет».
5. Permission ≠ текст в system prompt.

---

## 16. Security / EOS-SEC

1. **MODEL IS NOT A SECURITY BOUNDARY.** Модель никогда не держатель секретов.
2. Пропуска, СКУД, сейф ключей, журнал охраны — не «сотрудник поклялся не воровать».
3. `AgentExecutionContext`, tool allowlist, trusted read executor, project boundary, fail closed, sanitized errors. Increment 3 это использует.
4. Нужны: least privilege, allowlists, read/write separation, scope, secret isolation, human gates, fail closed, audit, kill switch.
5. Не «хороший prompt = безопасность».

---

## 17. Guardrails / validation

1. Разница: модель **считает**, что нельзя — и система **не даёт** сделать.
2. «Не положено» в инструкции vs турникет, который не откроется.
3. Post-read assertion, mismatch project, tool not allowlisted — технический отказ, не совет модели.
4. Профессиональная система требует **второе**.
5. Guardrail в тексте промпта — не enforcement.

---

## 18. Human-in-the-loop

1. Когда агент обязан позвать человека: неоднозначность, спор о количестве, критическое полномочие, управленческое решение.
2. Обращение к руководителю / главному инженеру, не заполнение 175 галочек за агента.
3. Закон spec: grouped exceptions, не row-by-row. **Durable HITL не реализован** (Increment 8).
4. Человек сообщает изменение реальности; агент делает рутину вокруг него.
5. Не оператор 175 строк. Не скрытый массовый row editor.

---

## 19. Durable checkpoint / pause / resume

1. Работа остановилась, процесс умер, браузер закрыли, через часы человек ответил — run восстанавливается.
2. Дело лежит в канцелярии, а не в голове ушедшего со смены.
3. Закон spec: in-process interrupt ≠ durable HITL. Increment 8 — **NOT STARTED**.
4. Иначе «цифровой сотрудник» живёт только пока открыт Streamlit.
5. Не `st.session_state` как склад паузы.

---

## 20. Fresh reality

1. После долгой паузы нельзя продолжать по старому снимку. Решение человека **не** делает snapshot свежим.
2. Перед сдачей работы ещё раз сверяют факт на площадке.
3. В spec: `REFRESH_REALITY` + `FRESHNESS_GATE`. В коде Increments 1–3 **нет**.
4. Иначе в Admission уйдёт чужой remainder.
5. Не «тот же DataFrame, мы его уже читали утром».

---

## 21. Handoff

1. Формальная передача следующей **профессиональной роли**: идентификаторы, scope, ссылка на пакет, provenance.
2. Сдача смены / передача в другой отдел по акту, не устный рассказ в коридоре.
3. Constructor → Admission. `ConstructorHandoff` **не реализован**. CandidatePackage — заготовка содержимого.
4. NO HIDDEN AGENT CHAT. Agent B сам читает актуальную реальность.
5. Не prompt с выгрузкой ведомости. Не человек как курьер между агентами.

---

## 22. Orchestrator

1. Координатор порядка работ. Не выполняет чужую профессию.
2. Руководитель процесса / диспетчер, не совмещающий все должности.
3. Цепочка: Orchestrator → Constructor → Admission → Constraint → Resource Capacity → Economic Evaluation → Management Decision → Human Gate → Паспорт месячного производственного обязательства.
4. Page51 MPO cockpit — продукт feasibility, **не** Constructor Runtime.
5. Orchestrator ≠ super-agent, который сам считает remainder.

---

## 23. Shared capabilities / services

1. Общие службы: нормы, валидаторы, security, калькуляторы.
2. Бухгалтерия / ОТ / склад как сервисы для нескольких должностей.
3. `LaborNormResolver` — **shared capability**, не отдельный агент (Increment 4 — NEXT). EOS-SEC issuer — служба, не профессия планирования.
4. Чтобы не делать AGENT ZOO из каждой функции.
5. Сервис ≠ агент, пока это не самостоятельная профессиональная роль.

---

## 24. LLM / model boundary

1. LLM — там, где семантика, неструктурированный текст, неоднозначность, объяснение.
2. Экспертная оценка формулировки vs калькулятор и допуск.
3. Increments 1–3: **без LLM**. Remainder, scope, permissions — deterministic Python.
4. LLM не считает деньги, не выдумывает authoritative labor norm, не выдаёт себе права. Adapter **replaceable**.
5. LLM ≠ агент. Привязка бизнеса к одному провайдеру запрещена законом стека.

---

## 25. Events / triggers

1. Что запускает работу: новая mission, изменились данные, пришло решение человека, срок, пришёл handoff.
2. Наряд, авария, согласование вернулось, конец месяца.
3. Сейчас запуск — доверенный caller / будущий Control Room. Event bus **не реализован**; это concept.
4. Чтобы агент реагировал на реальность, а не только на клик.
5. Не «cron ради cron» без mission.

---

## 26. Observability

1. Что должно быть видно: run, status, node, duration, actions, tool calls, exceptions, ожидание человека, handoff, result, failure.
2. Диспетчерская доска, а не догадки.
3. Control Room — будущий Increment 10. Сейчас доказанные модули наблюдаемы тестами, не живым run UI.
4. Без этого нельзя управлять цифровым сотрудником.
5. Не таблица 175 строк как «мониторинг».

---

## 27. Trace / audit

1. Доказать: что сделано, когда, на каком основании, какие данные, кто подтвердил.
2. Журнал работ и подписи.
3. Provenance на `CandidatePackage` и `ConstructorRealityRead`. Полный append-only `agent_run_events` — **ещё нет**.
4. Разбор инцидента и compliance.
5. Не сырые секреты в логе. Не unredacted tool errors.

---

## 28. Failure / retry / fail-closed

1. Если tool молчит, данные дырявые, scope нельзя доказать, security check упал — отказ, а не «почти».
2. Стоп-кран, а не «сделаем как получится на весь проект».
3. Increment 1–3: unknown facility → 0 rows или fail closed; extra-scope row → fail closed; tool not allowlisted → deny.
4. Retry только для явно transient ошибок (закон spec). Default — fail closed.
5. Не silent empty package при сбое чтения.

---

## 29. Kill switch

1. Быстро снять права: нельзя читать/писать/вызывать tools.
2. Изъять пропуск и ключи.
3. EOS-SEC и future write path (MPCA-002 kill switch — experiment, live write off). Для Constructor READ runtime — `write_allowed=False` уже сейчас.
4. Особенно важно для будущего physical AI (роботы, дроны): недостаточно «попросить модель остановиться».
5. Kill switch ≠ удалить prompt.

---

## 30. Tests / evals

1. Unit/regression проверяют контракты. Agent evals проверяют поведение сотрудника на сценариях.
2. Квалификация и разбор ошибок на площадке.
3. Реальный пример: **447 → 17** (scoped facility + Вентиляция). Ошибка MPCA-003 стала regression law.
4. Каждая найденная ошибка по возможности становится тестом/eval, чтобы не вернулась.
5. Не «ручной прогон страницы вместо контракта».

---

## 31. Versioning

1. Версии: агент, spec, contracts, schema артефакта (`CandidatePackage` `1.0`), skills, runtime.
2. Нельзя молча сменить должностную инструкцию в проде.
3. `schema_version` на пакете; agent_version в provenance. Breaking change — новый контракт, не тихая правка.
4. Admission должен понимать, какую версию пакета он читает.
5. Не «просто поправили поле вчера».

---

## 32. Single agent vs multi-agent

1. Новый агент — когда появляется **новая крупная профессиональная роль**.
2. Новый отдел vs новая операция внутри того же отдела.
3. Constructor остаётся одним агентом на 10 инкрементов. Admission — будущая **другая** роль. LaborNormResolver — capability.
4. Новая функция текущей роли → skill / tool / node / service, не агент.
5. Не «один агент = одна таблица UI».

---

## 33. Agent Control Room

1. Поверхность человека: мониторинг, exceptions, решения, evidence, audit.
2. Кабинет руководителя / диспетчерская. Сотрудник работает не «внутри монитора начальника».
3. Streamlit — целевой Control Room. **Не runtime.** Page10B — не место жизни Constructor Runtime.
4. Человек видит статус и исключения, не гоняет 175 строк как работу агента.
5. Control Room ≠ agent. Закрытие вкладки не должно убивать run (закон; реализация — Increment 8/10).

---

## 34. Digital employee completeness

Профессиональный агент **не** считается зрелым только потому, что есть prompt, LLM и tool call.

### A. General mature digital worker checklist

Минимальный набор слоёв, который рассматривается для **любого** будущего агента Execution OS (учебный стандарт, не отчёт о текущем Constructor):

role · specification · mission · scope · skills · tools · contracts · artifacts · state · lifecycle · runtime · permissions · security · HITL · handoff · observability · tests/evals

Пустой checkbox здесь **не** используется: этот список — модель полноты, а не статус реализации.

### B. Current Constructor status

Фактическое состояние **одного** Constructor Agent. Не выдавать будущие слои за сделанные.

| Слой | Статус |
|------|--------|
| Role / Specification | DESIGNED |
| Mission Scope | IMPLEMENTED + TESTED |
| Secure Read Tools | IMPLEMENTED + TESTED |
| Business Artifact / CandidatePackage | IMPLEMENTED + TESTED |
| Labor Norm Resolver | NEXT |
| Exception Engine | NOT IMPLEMENTED |
| Lifecycle | NOT IMPLEMENTED |
| LangGraph Runtime | NOT IMPLEMENTED |
| Durable HITL | NOT IMPLEMENTED |
| Structured Handoff | NOT IMPLEMENTED |
| Control Room | NOT IMPLEMENTED |

Подробнее — глава «Как эта анатомия выглядит на нашем Constructor Agent прямо сейчас».

---

## Сводная таблица: организация ↔ цифровой сотрудник ↔ Constructor

| Обычная организация | Цифровой сотрудник | Пример Constructor |
|---------------------|--------------------|--------------------|
| Должность | Agent Role | `MONTHLY_PLAN_CONSTRUCTOR` |
| Должностная инструкция | Specification | MONTHLY_PLAN_CONSTRUCTOR_AGENT.md / runtime spec |
| Поручение | Mission | project + month + optional scope |
| Зона ответственности | Scope | Increment 1 `ConstructorMissionScope` |
| Компетенции | Skills | classify / remainder (reuse MPCA-001; graph не подключён) |
| Инструменты | Tools | Increment 3 secure read, allowlist |
| Формы документов | Contracts / schemas | MissionScope, CandidatePackage, RealityRead |
| Результат работы | Business artifact | CandidatePackage |
| Рабочие операции | Nodes | spec: receive / load / classify / package / … |
| Состояние дела | State | designed; not implemented as run store |
| Регламент | Lifecycle | designed in spec |
| Рабочая среда | Runtime | Python now; LangGraph target |
| Полномочия | Permissions | READ ONLY v0.1 |
| ИБ / допуски | EOS-SEC | context + allowlist + fail closed |
| Обращение к руководителю | HITL | spec only |
| Передача в другой отдел | Handoff | future Constructor → Admission |
| Корпоративная система | Shared state | Supabase |
| Руководитель процесса | Orchestrator | Monthly Planning chain |
| Журнал работы | Trace / audit / observability | provenance now; full events later |
| Проверка квалификации | Tests / evals | 447→17; 20+20+22 tests |

---

## Карта анатомии

```
PROFESSIONAL DIGITAL EMPLOYEE

ROLE
  ↓
SPECIFICATION
  ↓
MISSION + SCOPE
  ↓
SKILLS
  ↓
TOOLS
  ↓
CONTRACTS
  ↓
STATE + LIFECYCLE
  ↓
RUNTIME
  ↓
BUSINESS ARTIFACT
  ↓
HUMAN GATE (if required)
  ↓
HANDOFF

Вокруг всех слоёв:
  SECURITY / EOS-SEC
  SHARED STATE / SUPABASE
  OBSERVABILITY / AUDIT
  TESTS / EVALS

Над несколькими агентами:
  ORCHESTRATOR
```

---

## Как эта анатомия выглядит на нашем Constructor Agent прямо сейчас

Только факты. Будущее не выдаётся за сделанное.

| Слой | Статус |
|------|--------|
| ROLE | CONCEPT + SPEC |
| SPECIFICATION | DESIGNED + COMMITTED |
| MISSION / SCOPE | **IMPLEMENTED + TESTED** (`775993f`) |
| Candidate Package (artifact) | **IMPLEMENTED + TESTED** (`862279b`) |
| Secure Read Tools | **IMPLEMENTED + TESTED** (`af2e9af`) |
| Skills wired into increment runtime | NOT (MPCA-001 predecessor exists separately) |
| Labor Norm Resolver | **NEXT** (Increment 4) |
| Exception engine | NOT IMPLEMENTED |
| Lifecycle | NOT IMPLEMENTED |
| LangGraph Runtime | NOT IMPLEMENTED |
| Durable HITL | NOT IMPLEMENTED |
| Handoff | NOT IMPLEMENTED |
| Control Room as runtime surface | NOT IMPLEMENTED |

Constructor — **не** автономный digital worker runtime. Это доказанный contract core: где работать, какой артефакт производить, как безопасно читать.

---

## Текущий roadmap Constructor (один агент, не десять)

[1] Mission Scope Contract — **DONE**<br>
[2] Candidate Package Artifact — **DONE**<br>
[3] Secure Read Tool Adapters — **DONE**<br>
[4] Labor Norm Resolver integration — **NEXT**<br>
[5] Exception Engine<br>
[6] Pure Python Lifecycle<br>
[7] LangGraph Runtime<br>
[8] Durable HITL / Resume<br>
[9] Structured Handoff<br>
[10] Agent Control Room Integration

Это десять этапов строительства **одного** Constructor Agent. Не десять агентов.

---

## Living document law

`DIGITAL_EMPLOYEE_ANATOMY.md` можно дополнять, когда появляется **доказанный** архитектурный concept.

Не превращать этот файл в журнал commits.<br>
Progress — `AGENT_RUNTIME_PROGRESS.md`.<br>
Architecture decisions — `DECISION_LOG.md` / baseline.
