@echo off
REM Congress Trades - Daily Sync Script
REM This script is run by Windows Task Scheduler

cd /d "%~dp0.."
python main.py sync --notify --days 7

REM Keep window open briefly so you can see output (optional)
REM timeout /t 5
