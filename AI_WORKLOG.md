# AI_WORKLOG — журнал работ по проекту csv_fix

> **Назначение:** хронология сессий и значимых изменений. Новые записи — **сверху**.  
> **Кто пишет:** владелец (кратко) и/или AI-агент после каждой содержательной сессии.

---

## Шаблон новой записи (копировать)

```markdown
### YYYY-MM-DD — [краткий заголовок]

**Участники:** Architect / AI Agent  
**Цель сессии:**  
**Сделано:**
- 
**Решения:**
- 
**Проблемы / блокеры:**
- 
**Следующий шаг:** см. NEXT_STEPS.md →
```

---

## 2026-05-15 — Data entry guide + page reorder (P1.3)

**Участники:** Architect / AI Agent (Cursor)  
**Сделано:**
- Перенумерация страниц: Приёмка → `07_`, Потери → `08_`, … AI → `11_` (убран дубль `06_`).
- `DATA_ENTRY_GUIDE.md` — инструкция мастерам по полям Daily Progress.
- Обновлены `README.md`, `NEXT_STEPS.md` (P1.3 ✅).

**Следующий шаг:** P1 EXECUTION — ТОП проблем на Главной (2.2) или KPI «за 60 секунд» (2.1).

---

## 2026-05-15 — Data quality page + sync regulation (P1.1, P1.2)

**Участники:** Architect / AI Agent (Cursor)  
**Сделано:**
- Страница `pages/06_Качество_данных.py` (KPI, фильтры, таблица из `smr_data_quality_issues`).
- `SYNC_REGULATION.md` — когда и как синкать Airtable → Supabase.
- `05_Исполнение.py` не менялся.
- Обновлены `README.md`, `NEXT_STEPS.md`.

**Следующий шаг:** P1.3 — инструкция мастерам по полям ввода.

---

## 2026-05-15 — P0 foundation block closed

**Участники:** Architect / AI Agent (Cursor)  
**Сделано:** блок P0 полностью закрыт — проектная память в git (`c8653bb`), чеклист нового ПК (`SETUP_NEW_PC.md`), удалён вложенный git-скелет.  
**Следующий шаг:** P1 DATA — Data Quality Dashboard или Sync Regulation.

---

## 2026-05-15 — New PC setup checklist (P0.2)

**Участники:** Architect / AI Agent (Cursor)  
**Цель сессии:** чеклист переноса проекта на другой компьютер.

**Сделано:**
- Создан `SETUP_NEW_PC.md`: Cursor, clone, `.env`, venv, зависимости, Streamlit, промпт для агента.
- Обновлён `NEXT_STEPS.md` (P0.2 ✅).

**Решения:**
- Отдельный файл вместо раздувания README; `PROJECT_CONTEXT.md` §6 остаётся справочником.

**Проблемы / блокеры:**
- нет

**Следующий шаг:** см. `NEXT_STEPS.md` → P1 DATA (качество данных / синк).

---

## 2026-05-15 — Cleanup nested git shell (P0.3)

**Участники:** Architect / AI Agent (Cursor)  
**Цель сессии:** разобрать и убрать вложенную папку `C:\csv_fix\csv_fix`.

**Сделано:**
- Проверена `csv_fix\csv_fix`: только сломанный `.git` (~26 KB), без кода и коммитов (`HEAD` → `.invalid`).
- Папка удалена по подтверждению владельца.
- Основной проект `C:\csv_fix` проверен: `app.py`, `pages/`, `services/`, `.venv`, `.env`, `.git` на месте.
- Обновлены `NEXT_STEPS.md` (P0.3 ✅), `AI_WORKLOG.md`.

**Решения:**
- Строка `csv_fix/` в `.gitignore` оставлена — защита от повторного случайного клона.

**Проблемы / блокеры:**
- нет

**Следующий шаг:** см. `NEXT_STEPS.md` → P0.2 (чеклист «новый компьютер») или P1 DATA.

---

## 2026-05-15 — Persistent memory layer + восстановление среды на ПК

**Участники:** Architect (владелец) / AI Agent (Cursor)  
**Цель сессии:** открыть проект на этом компьютере, запустить Streamlit, заложить память между сессиями.

**Сделано:**
- Найден проект: `C:\csv_fix` (ранее работа в VS Code на этом ПК).
- Проверены: `.venv` (Python 3.12.10), зависимости (`pip check` OK), `.env` (Supabase + Airtable ключи).
- Подключение к Supabase проверено (`supabase client: OK`).
- Запущен Streamlit: `http://localhost:8501` — витрина открывается.
- Создан persistent memory layer:
  - `PROJECT_CONTEXT.md`
  - `AI_WORKLOG.md`
  - `AGENT_MEMORY.md`
  - `NEXT_STEPS.md`

**Решения:**
- Зафиксирована формула: `DATA → EXECUTABILITY → EXECUTION → ACCEPTANCE → CASH`.
- Память проекта хранится в корне репозитория (переносимо между ПК через git).
- Роль владельца: Architect / Orchestrator; агент пишет код и объясняет простым языком.

**Проблемы / блокеры:**
- Вложенная папка `C:\csv_fix\csv_fix` (возможный дубликат) — не исследовалась; не мешает запуску.

**Следующий шаг:** см. `NEXT_STEPS.md` → приоритеты после memory layer.

---

## История до memory layer (из git, кратко)

| Дата (коммит) | Суть |
|---------------|------|
| f4cbb99 | Cache на `load_table` — ускорение дашборда |
| 32f149e | Execution dashboard: weekly KPI, форматирование, expanders |
| d718c3a | `update_all_sync.py` + bat-лаунчер |
| 08ffd46 | Monthly passport: Airtable вместо CSV |
| efc8a6d | PTO acceptance module + upsert + RLS |
| cba3726 | Live metrics на Главной |
| 7d35265 | Первый AI agent analysis |

*Детальная доменная логика — в `README_SMR_EXECUTION_LOGIC.md`.*

---

## Правила ведения журнала

1. Одна запись = одна сессия или один логичный блок работ (не чаще 1 раза в день без нужды).
2. Писать **простым языком**, что изменилось для бизнеса, не только имена файлов.
3. Блокеры переносить в `NEXT_STEPS.md`, если требуют действия.
4. Секреты и ключи **никогда** не записывать в worklog.
