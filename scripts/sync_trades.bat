@echo off
REM Congress Trades - Daily Sync Script
REM This script is run by Windows Task Scheduler

cd /d "%~dp0.."
py main.py sync --notify --days 7 --analyze

REM Keep window open briefly so you can see output (optional)
REM timeout /t 5
