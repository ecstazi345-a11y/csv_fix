# DYNAMIS
## AI-native оркестрация физического исполнения инженерно-критической инфраструктуры

**Статус документа:** reference architecture  
**Назначение:** долговечный ориентир для проектирования Human Surface (Django), цифровых сотрудников, полевого исполнения, ПНР, приёмки, причинности и коммерческого признания.  
**Не является:** журналом прогресса, описанием Streamlit UI, спецификацией агентного runtime.

---

## 1. Идентичность продукта

**DYNAMIS** — AI-native оркестрация физического исполнения инженерно-критической инфраструктуры.

Дополнительная формулировка:

> Единая операционная среда людей, цифровых сотрудников и физических исполнителей.

На пользовательской поверхности **не** используются как идентичность продукта:

- dashboard
- control room
- workflow engine
- SaaS platform
- agent framework
- execution OS

Эти термины могут встречаться во внутренних технических контурах, но не определяют верхнеуровневый смысл DYNAMIS.

---

## 2. Фундаментальный принцип

DYNAMIS управляет не страницами, таблицами и отделами.

**Главный объект управления — физическая система.**

Пример: **П1** — система приточной вентиляции.

Каждая система проходит полный жизненный цикл:

ЗАМЫСЕЛ / КОНТРАКТ  
→ ИНЖЕНЕРНЫЙ КОНТЕКСТ  
→ РД / СПЕЦИФИКАЦИИ / СМЕТА  
→ АНАЛИЗ И ДЕКОМПОЗИЦИЯ  
→ ФИЗИЧЕСКИЕ ОБЪЕКТЫ  
→ МАТЕРИАЛЫ / ОБОРУДОВАНИЕ  
→ ЗАКУПКА  
→ ПОСТАВКА  
→ ВХОДНОЙ КОНТРОЛЬ  
→ СКЛАД / ВЫДАЧА  
→ ФРОНТ / ДОПУСК  
→ РАБОЧИЙ ПАКЕТ  
→ РЕСУРС  
→ ИСПОЛНЕНИЕ  
→ КОНТРОЛЬ КАЧЕСТВА  
→ ИНСПЕКЦИЯ  
→ ИСПОЛНИТЕЛЬНАЯ ДОКУМЕНТАЦИЯ  
→ ПРИЗНАНИЕ ОБЪЁМА  
→ КС-2 / КС-3  
→ СПИСАНИЕ МТР / М-29  
→ ГОТОВНОСТЬ К ПНР  
→ ПЕРЕДАЧА В ПНР  
→ ПНР  
→ ПРИЁМКА  
→ ЗАКРЫТО / АРХИВ

**Главное понятие:** операционный граф физического исполнения.

---

## 3. Физическая декомпозиция (пример П1)

```
П1
├── Вентиляционная установка
│   ├── корпус
│   ├── вентилятор
│   ├── фильтр
│   ├── калорифер
│   ├── клапаны
│   └── автоматика
├── Воздуховоды
│   ├── магистрали
│   ├── ответвления
│   ├── фасонные элементы
│   └── гибкие вставки
├── Изоляция
├── Клапаны
├── Решётки / диффузоры
├── Опоры / крепления
├── Электроснабжение
├── КИПиА
│   ├── датчики
│   ├── приводы
│   └── шкаф автоматики
└── BMS / верхний уровень
```

Пример состояния физического объекта (Клапан К1):

ТРЕБУЕТСЯ → СПЕЦИФИЦИРОВАН → ЗАКАЗАН → ПОСТАВЛЕН → ВХОДНОЙ КОНТРОЛЬ ПРОЙДЕН → ВЫДАН → СМОНТИРОВАН → ПРОИНСПЕКТИРОВАН → ПРИНЯТ → ПЕРЕДАН В ПНР → ПРОТЕСТИРОВАН → ЗАКРЫТО

---

## 4. Связанные операционные графы

Все графы описывают разные проекции одной физической реальности:

1. **Инженерный граф** — РД → анализ → физические объекты → требования → спецификации → TEQ/RFI → новая ревизия → актуальное инженерное решение  
2. **Материальный граф** — потребность → заявка → согласование → заказ → производство → отгрузка → доставка → входной контроль → склад → резервирование → выдача → монтаж → списание → М-29  
3. **Граф допуска** — физический объект → готовность РД / фронта / МТР / доступа / предшественников / QA-QC / разрешений / ресурса → ДОПУЩЕНО / ЗАБЛОКИРОВАНО / ТРЕБУЕТ УТОЧНЕНИЯ  
4. **Граф рабочего пакета** — система → зона → IWP → рабочий пакет → операция → звено → план начала → план окончания  
5. **Граф физического исполнения** — требуемая работа → операция → исполнитель → событие → объём → труд → доказательство → новое состояние  
6. **Граф качества** — работа выполнена → контроль → замечание? → исправление → инспекция → приёмка  
7. **Граф исполнительной документации** — событие → доказательство → исполнительная схема → акт → протокол → комплект → предъявление → утверждение  
8. **Коммерческий граф** — выполненный объём → принятый → признанный → КС-2 → КС-3 → счёт → оплата  
9. **Граф причинности** — событие → причина → источник → ответственный контур → последствие → затронутая работа → срок / труд / стоимость / деньги → основание для требования / claim  
10. **Граф ПНР** — инженерный контекст → требуемая работа → операция → измерение → доказательство → результат → проверка → новое состояние → функциональное / комплексное испытание → приёмка

---

## 5. Общий связующий объект

Графы должны связываться **не только через BOQ**, а через **физический объект**.

Внутренний идентификатор: `physical_object_id`  
На пользовательской поверхности: **идентификатор физического объекта**  
Пример: `П1.КЛАПАН.0017`

К одному физическому объекту могут быть привязаны: РД, спецификация, BOQ, смета, МТР, заказ, поставка, входной контроль, рабочий пакет, операция, исполнитель, событие исполнения, фото, измерение, тест, акт, КС-2, причинность, ПНР.

---

## 6. Исполнитель

Исполнителем работы может быть:

- человек  
- цифровой сотрудник  
- робот  
- дрон  
- автономная машина  
- внешняя информационная система  

**Архитектурный закон DYNAMIS:**

СОСТОЯНИЕ → ДОПУСК → РАБОТА → ИСПОЛНИТЕЛЬ → ОПЕРАЦИЯ → СОБЫТИЕ → ДОКАЗАТЕЛЬСТВО → ПРОВЕРКА → НОВОЕ СОСТОЯНИЕ → СЛЕДУЮЩАЯ РАБОТА

---

## 7. Цифровые сотрудники месячного планирования

Старая target-цепочка Constructor → Admission → Constraint → Resource → Economics → Decision **больше не является** целевой организационной моделью Monthly Planning. Это HISTORICAL / SUPERSEDED AS TARGET. Admission и Constraint — профессиональные умения внутри Executability Agent, не отдельные целевые сотрудники. Resource / Economics / Decision pack — умения внутри Commitment Agent.

Целевая цепочка:

```
Human Intent
  → Constructor Agent
  → Candidate Package
  → Human Review Gate
  → Reviewed Candidate Package
  → Human Confirm
  → Executability Agent
  → Commitment Agent
  → Human Decision Gate
  → Monthly Commitment / Passport
```

Профессиональная ответственность:

| Digital Worker | Ответственность |
|----------------|-----------------|
| Constructor Agent | формирует кандидатный состав |
| Executability Agent | объединяет Admission + Constraints: можно ли реально выполнять выбранные позиции |
| Commitment Agent | объединяет Resource Capacity + Economics + Management Recommendation: какой объём реально принять как месячное обязательство |
| Human Decision Gate | финальная authority для утверждения месячного обязательства |

Не создавать agent zoo.

```
ONE LARGE PROFESSIONAL RESPONSIBILITY = ONE DIGITAL WORKER
```

Skills / tools / services / deterministic nodes остаются внутри агента, если не требуют отдельной профессиональной ответственности.

---

## 8. Месячное планирование — временной срез

Месячное планирование — **не вся DYNAMIS**. Это временной срез общего жизненного графа системы.

> Месячное планирование отвечает на вопрос: какую часть жизненного графа физической системы организация готова взять в производственное обязательство на конкретный период.

После утверждения:

ПАСПОРТ МЕСЯЦА → РАБОЧИЙ ПАКЕТ → ПОЛЕВОЕ ИСПОЛНЕНИЕ → СОБЫТИЕ → ДОКАЗАТЕЛЬСТВО → ПРОВЕРКА → НОВОЕ СОСТОЯНИЕ

---

## 9. Передача в ПНР

Система переходит в ПНР **не по ручной команде «передать»**, а по доказанному состоянию готовности.

Пример:

МЕХАНИЧЕСКАЯ ГОТОВНОСТЬ  
+ ЭЛЕКТРИЧЕСКАЯ ГОТОВНОСТЬ  
+ ГОТОВНОСТЬ АВТОМАТИКИ  
+ КАЧЕСТВО ПРИНЯТО  
+ ДОКУМЕНТАЦИЯ ГОТОВА  
+ НЕТ БЛОКИРУЮЩИХ ОГРАНИЧЕНИЙ  
→ **ГОТОВО К ПНР**

---

## 10. Межсистемные зависимости

Системы не изолированы. Пример:

П1 не может быть завершена → нет питания шкафа автоматики  
Шкаф автоматики не готов → не проложен кабель  
Кабель не проложен → не готова трасса  

Итог: блокировка П1 может находиться в другом графе / другой системе.

П1, П2, В1, ХС1, ЭОМ, АОВ и другие связаны через зависимости, ограничения, предшествующие работы, общие ресурсы, инфраструктуру и точки приёмки.

---

## 11. Практическое следствие для поверхностей

- Human Surface показывает жизненный цикл и решения человека.
- Цифровые сотрудники работают в пределах своей профессиональной роли.
- Источник истины о физическом состоянии — операционный граф и связанные доказательства, а не страница приложения.

---

## 12. Законы Digital Workforce

Сохраняются без ослабления:

- Agent = First-Class Digital Worker
- Professional Logic ≠ Runtime ≠ Model
- Durable runtime independent from UI
- Capability ≠ Permission ≠ Authority
- action-time authorization
- formal typed handoff
- governed shared state
- Human-by-Exception target (maturity, не current Constructor gate)
- independent control/kill layer
- professional/economic observability
- economics of digital worker
- do not rebuild horizontal infrastructure unnecessarily
- Physical Execution Semantics as DYNAMIS moat
- Physical AI readiness without premature implementation
- scale completed workflows, not number of agents
- Build minimum now → preserve architecture for later

---

## 13. Data-source independence

```
AGENT CORE MUST BE DATA-SOURCE INDEPENDENT.
```

Целевая архитектура:

```
Professional Agent Core
  → Professional Tool Contracts
  → Replaceable Data Adapters
  → PostgreSQL / Supabase / API / Document Store / future on-prem sources
```

Профессиональная роль, Mission, Skills, Decision Logic, Authority и Artifacts не зависят от Airtable, Streamlit, конкретного view, конкретной UI page, конкретного API provider.

Текущие tables/views — implementation adapters, не часть профессии.
Смена data foundation должна менять преимущественно adapters/tools, а не профессию агента.

---

## 14. Human Review и Human-by-Exception

Не смешивать current autonomy и target maturity.

CURRENT Constructor:

```
Constructor → autonomous candidate discovery → Human Review → Human Confirm → handoff
```

Human Review сейчас обязательный gate. Не считать Human-by-Exception уже реализованным.

TARGET maturity:

```
Machine by default
  → Human on exception
  → Human on authority
  → Human on ambiguity
  → Human on high-consequence decision
```

Human Review может позже сократиться до Human-by-Exception без смены профессии. CURRENT ≠ TARGET.

---

## 15. Сквозная physical data hierarchy

BOQ / Commercial Code не является верхней сущностью физической реальности. Это коммерческая проекция физической работы.

Будущая иерархия DYNAMIS:

```
Project
  → Stage / Queue
  → Facility / Title
  → Discipline
  → System
  → Work Package
  → Commercial Code / BOQ
  → Required Work
  → Physical Object
  → RD / drawings
  → axes / elevations / spatial bindings
  → Specification
  → Execution Event
  → Evidence
  → Proven State
```

Операционная истина должна постепенно строиться вокруг Physical System + Physical Object + Work Package + Required Work + Execution Event + Evidence + Proven State.

---

## 16. Formal handoff

```
Source Digital Worker
  → typed business artifact
  → durable persistence
  → authorized handoff
  → target role
  → receiver acknowledgement
  → next professional process
```

Законы:

```
HANDOFF_PERSISTED != RECEIVER_ACCEPTED
RECEIVER_ACCEPTED != BUSINESS_APPROVED
AGENT_COMPLETED != ORCHESTRATION_COMPLETED
```

---

## 17. Anatomy каждого Digital Worker

Архитектура должна поддерживать (не обязательно реализовать сразу; новые решения не закрывают путь):

worker_id / agent_id; professional role; version; owner / accountable role; Mission; Mission Scope; Skills; Tools; Professional Tool Contracts; permissions; authority; lifecycle; persistent state; typed artifacts; Human Gates; exceptions; handoff; observability; audit / trace; economics; suspend / revoke / retire.

---

## 18. Design gate для нового агента

1. Профессиональная логика отделена от data source?
2. Можно ли заменить adapter без переписывания профессии агента?
3. UI является Human Surface, а не runtime?
4. Какой typed business artifact создаёт агент?
5. Где заканчивается его authority?
6. Какие действия требуют Human Gate?
7. Формален ли handoff?
8. Есть ли provenance?
9. Есть ли fail-closed?
10. Разделены ли capability / permission / authority?
11. Есть ли durable state / restart?
12. Можно ли независимо suspend / revoke / terminate?
13. Видно ли professional outcome в observability?
14. Можно ли связать outcome с physical consequence?
15. Можно ли связать outcome с economic consequence?
16. Не строим ли горизонтальную capability, которую разумнее использовать готовой?
17. Не усложняем ли систему раньше реальной необходимости?
18. Можно ли позже сократить routine Human Review до Human-by-Exception без изменения профессии?
19. Совместим ли worker с HUMAN / DIGITAL WORKER / ROBOT / DRONE / AUTONOMOUS MACHINE execution model?

---

## 19. Current vs Target

CURRENT:

- Constructor = первый реально работающий Digital Worker
- Candidate Package существует
- Human Review target определён, runtime ещё не реализован
- Reviewed Candidate Package не реализован
- Executability Agent не реализован
- Commitment Agent не реализован
- Orchestrator не реализован
- новая сквозная physical data foundation не реализована

TARGET:

- governed Digital Workforce
- replaceable adapters
- persistent Digital Workers
- Human-by-Exception
- orchestrated workflows
- unified physical execution state
- HUMAN / DIGITAL WORKER / ROBOT / DRONE / AUTONOMOUS MACHINE as executor types

Не выдавать target за current implementation.

Конец reference-документа.
