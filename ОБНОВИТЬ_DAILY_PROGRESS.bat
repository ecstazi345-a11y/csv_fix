@echo off
cd /d C:\csv_fix
call .venv\Scripts\activate.bat
python daily_progress_sync_upsert.py
pause