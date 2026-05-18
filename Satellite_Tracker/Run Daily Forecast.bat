@echo off
REM ATLAS — daily HiRes EO Pakistan surveillance.
REM   Backs up state, refreshes TLEs from CelesTrak, regenerates 15-day forecast.
REM
REM Suitable for Windows Task Scheduler. Logs to run_daily.log next to this file.

setlocal
cd /d "%~dp0"
python "%~dp0run_daily.py" >> "%~dp0run_daily.log" 2>&1
endlocal
