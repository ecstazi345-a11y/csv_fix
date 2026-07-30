@echo off
chcp 65001 >nul
cd /d "%~dp0"

set PYTHONIOENCODING=utf-8

echo ================================================== >> logs\daily_sync.log
echo START %date% %time% >> logs\daily_sync.log
echo ================================================== >> logs\daily_sync.log

call .venv\Scripts\activate.bat >> logs\daily_sync.log 2>&1

python update_all_sync.py >> logs\daily_sync.log 2>&1
set SYNC_EXIT_CODE=%ERRORLEVEL%

echo. >> logs\daily_sync.log
echo EXIT_CODE=%SYNC_EXIT_CODE% >> logs\daily_sync.log
echo FINISH %date% %time% >> logs\daily_sync.log
echo ================================================== >> logs\daily_sync.log
echo. >> logs\daily_sync.log

exit /b %SYNC_EXIT_CODE%
