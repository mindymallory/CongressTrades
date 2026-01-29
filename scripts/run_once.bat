@echo off
REM Congress Trades - Manual Sync
REM Double-click this to manually sync and check for new trades

cd /d "%~dp0.."
echo.
echo Congress Trades - Manual Sync
echo =============================
echo.

py main.py sync --notify --days 7 --analyze

echo.
echo Press any key to close...
pause >nul
