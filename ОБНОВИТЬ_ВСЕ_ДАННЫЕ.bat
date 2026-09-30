@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Активирую виртуальное окружение...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo ОШИБКА: не удалось активировать .venv
    pause
    exit /b 1
)

set PYTHONIOENCODING=utf-8
echo Запускаю 4 синка: Daily Progress, BOQ, Monthly Passport, Crew_Register...
python update_all_sync.py
set SYNC_EXIT_CODE=%ERRORLEVEL%

echo.
if "%SYNC_EXIT_CODE%"=="0" (
    echo ОБНОВЛЕНИЕ УСПЕШНО ЗАВЕРШЕНО — 4/4
) else (
    echo ОШИБКА ОБНОВЛЕНИЯ
    echo Не все источники синхронизированы.
    echo См. сообщение выше.
)

pause
exit /b %SYNC_EXIT_CODE%
