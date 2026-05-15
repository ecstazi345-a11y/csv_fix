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
| [DATA_ENTRY_GUIDE.md](DATA_ENTRY_GUIDE.md) | Инструкция мастерам по полям Daily Progress |
| [SYNC_REGULATION.md](SYNC_REGULATION.md) | Регламент синхронизации Airtable → Supabase |

## Разделы Streamlit

| # | Страница | Файл |
|---|----------|------|
| 01 | Главная | `pages/01_Главная.py` |
| 02 | Допуск фронта | `pages/02_Допуск_фронта.py` |
| 03 | Допуск к оплате | `pages/03_Допуск_к_оплате.py` |
| 04 | Паспорт месяца | `pages/04_Паспорт_месяца.py` |
| 05 | Исполнение | `pages/05_Исполнение.py` |
| 06 | Качество данных | `pages/06_Качество_данных.py` |
| 07 | Приёмка и признание | `pages/07_Приемка_и_признание.py` |
| 08 | Контроль потерь | `pages/08_Контроль_потерь.py` |
| 09 | Экономика | `pages/09_Экономика.py` |
| 10 | Уведомления заказчику | `pages/10_Уведомления_заказчику.py` |
| 11 | AI-Агенты | `pages/11_AI_Агенты.py` |

## Синхронизация данных

Двойной клик `ОБНОВИТЬ_ВСЕ_ДАННЫЕ.bat` или `python update_all_sync.py` (из `.venv`).

Регламент синка: [SYNC_REGULATION.md](SYNC_REGULATION.md) · Ввод факта: [DATA_ENTRY_GUIDE.md](DATA_ENTRY_GUIDE.md)
