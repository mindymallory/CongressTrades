@echo off
REM Congress Trades - Manual Sync
REM Double-click this to manually sync and check for new trades

cd /d "%~dp0.."
echo.
echo Congress Trades - Manual Sync
echo =============================
echo.

python main.py sync --notify --days 7

echo.
echo Press any key to close...
pause >nul
