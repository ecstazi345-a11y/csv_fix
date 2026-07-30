# Automatic Daily Sync

Каждый день в **23:00** автоматически запускается полный sync Airtable → Supabase.

## Задача Windows

| Параметр | Значение |
|----------|----------|
| Имя | `CSV_FIX_DAILY_SYNC` |
| Расписание | ежедневно в 23:00 |
| Планировщик | Windows Task Scheduler |
| Рабочая папка | `c:\csv_fix` |

## Скрипт запуска

Используется отдельный BAT для фона (без `pause`):

`ОБНОВИТЬ_ВСЕ_ДАННЫЕ_АВТО.bat`

Он активирует `.venv`, запускает `update_all_sync.py` (4 синка) и пишет лог.

Ручной BAT `ОБНОВИТЬ_ВСЕ_ДАННЫЕ.bat` не меняется и по-прежнему подходит для запуска двойным кликом.

## Лог

`c:\csv_fix\logs\daily_sync.log`

В логе должны быть маркеры `START`, `FINISH` и `EXIT_CODE=0`.

## Если проект переносится на другой компьютер

1. Установить Python.
2. Создать venv и установить зависимости (см. [SETUP_NEW_PC.md](../SETUP_NEW_PC.md)).
3. Настроить `.env` (Airtable / Supabase).
4. Создать задачу Windows Task Scheduler `CSV_FIX_DAILY_SYNC` на запуск `ОБНОВИТЬ_ВСЕ_ДАННЫЕ_АВТО.bat` ежедневно в 23:00.
5. Проверить задачу командами ниже.

## Команды проверки

```bat
schtasks /Query /TN "CSV_FIX_DAILY_SYNC"
schtasks /Query /TN "CSV_FIX_DAILY_SYNC" /V /FO LIST
schtasks /Run /TN "CSV_FIX_DAILY_SYNC"
```

После тестового запуска смотреть хвост лога:

```powershell
Get-Content "c:\csv_fix\logs\daily_sync.log" -Tail 50
```
