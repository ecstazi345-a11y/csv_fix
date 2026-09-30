# Automatic Daily Sync

Каждый день в **23:00** автоматически запускается полный sync Airtable → Supabase.

## Задача Windows

| Параметр | Значение |
|----------|----------|
| Имя | `CSV_FIX_DAILY_SYNC` |
| Расписание | ежедневно в 23:00 |
| Планировщик | Windows Task Scheduler |
| Рабочая папка | `c:\csv_fix` |
| Успех задачи | только если **4/4** sync завершились с exit 0 |

## Скрипт запуска

Используется отдельный BAT для фона (без `pause`):

`ОБНОВИТЬ_ВСЕ_ДАННЫЕ_АВТО.bat`

Он активирует `.venv`, запускает `update_all_sync.py` (4 синка) и пишет лог.
Exit code BAT = exit code orchestrator.

Ручной BAT `ОБНОВИТЬ_ВСЕ_ДАННЫЕ.bat` подходит для запуска двойным кликом и честно сообщает успех/ошибку.

## Orchestrator semantics (R1)

`update_all_sync.py`:

- fail-fast: при ошибке sync N остальные помечаются `SKIPPED`;
- exit **0** только при **4/4 SUCCESS**;
- иначе exit **1**.

## Airtable transport (R1)

Общий helper: `services/airtable_http.py`

- TLS verification **всегда включена** (`verify=False` запрещён);
- bounded retry (до 4 попыток) на SSL/Connection/Timeout и HTTP 429/5xx;
- **без retry** на 400/401/403/404/422;
- timeout `(connect=10s, read=60s)`.

Постоянный `CERTIFICATE_VERIFY_FAILED` / self-signed после исчерпания retry → **FAIL CLOSED**.

## Лог

`c:\csv_fix\logs\daily_sync.log`

Маркеры: `START`, `FINISH`, `EXIT_CODE=0|1`, сводка `COMPLETED: N/4`.

## Health artifact (operational only)

`c:\csv_fix\.runtime\sync\last_sync_status.json` (gitignored)

Не является business source of truth. Бизнес-данные — только Supabase.

## Если проект переносится на другой компьютер

1. Установить Python.
2. Создать venv и установить зависимости (см. [SETUP_NEW_PC.md](../SETUP_NEW_PC.md)).
3. Настроить `.env` (Airtable / Supabase).
4. Создать задачу Windows Task Scheduler `CSV_FIX_DAILY_SYNC` на запуск `ОБНОВИТЬ_ВСЕ_ДАННЫЕ_АВТО.bat` ежедневно в 23:00.
5. Убедиться, что путь к Airtable не ломается VPN/MITM proxy со self-signed сертификатом.
6. Проверить задачу командами ниже.

## Команды проверки

```bat
schtasks /Query /TN "CSV_FIX_DAILY_SYNC"
schtasks /Query /TN "CSV_FIX_DAILY_SYNC" /V /FO LIST
schtasks /Run /TN "CSV_FIX_DAILY_SYNC"
```

После тестового запуска смотреть хвост лога:

```powershell
Get-Content "c:\csv_fix\logs\daily_sync.log" -Tail 80
Get-Content "c:\csv_fix\.runtime\sync\last_sync_status.json"
```
