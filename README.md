# csv_fix — AI Construction Control Center

Строительная витрина: **план → исполнение → приёмка → деньги** (Streamlit + Supabase + Airtable).

## Быстрый старт

**Новый компьютер:** [SETUP_NEW_PC.md](SETUP_NEW_PC.md)

**Уже настроенный ПК:**

```powershell
cd C:\csv_fix
.\.venv\Scripts\streamlit.exe run app.py
```

Браузер: http://localhost:8501

## Документация

| Файл | Назначение |
|------|------------|
| [SETUP_NEW_PC.md](SETUP_NEW_PC.md) | Чеклист переноса на другой ПК |
| [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) | Паспорт проекта |
| [AGENT_MEMORY.md](AGENT_MEMORY.md) | Краткая память для AI |
| [NEXT_STEPS.md](NEXT_STEPS.md) | Очередь задач |
| [README_SMR_EXECUTION_LOGIC.md](README_SMR_EXECUTION_LOGIC.md) | Логика план-факт СМР |

## Синхронизация данных

Двойной клик `ОБНОВИТЬ_ВСЕ_ДАННЫЕ.bat` или `python update_all_sync.py` (из `.venv`).
