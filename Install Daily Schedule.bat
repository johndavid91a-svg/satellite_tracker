@echo off
REM ============================================================
REM  Install / refresh the Windows Task Scheduler jobs for ATLAS
REM  HiRes EO surveillance:
REM
REM    1. ATLAS_HiRes_Daily_Forecast  - full pipeline once a day
REM       at 02:00 (forecast + Word doc + accuracy + LATEST.docx
REM       + Indian targeting summary + retention).
REM
REM    2. ATLAS_HiRes_Hourly_TLE      - lightweight TLE top-up
REM       every hour (fresh TLEs + forecast JSON + change history)
REM       so the dashboard never lags CelesTrak by > 1 hour.
REM
REM  Re-running this script just refreshes both task definitions.
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "SAT=%ROOT%\Satellite_Tracker"
set "DAILY=%SAT%\run_daily.py"
set "HOURLY=%SAT%\run_hourly.py"
set "DAILY_LOG=%SAT%\run_daily.log"
set "HOURLY_LOG=%SAT%\run_hourly.log"
set "TASK_DAILY=ATLAS_HiRes_Daily_Forecast"
set "TASK_HOURLY=ATLAS_HiRes_Hourly_TLE"

if not exist "%DAILY%" (
    echo [FATAL] Cannot find %DAILY%
    pause & exit /b 2
)
if not exist "%HOURLY%" (
    echo [FATAL] Cannot find %HOURLY%
    pause & exit /b 2
)

REM -- Locate a real Python install (same probe order as the launcher) ---
set "PY="
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%ProgramFiles%\Python314\python.exe"
    "%ProgramFiles%\Python313\python.exe"
    "%ProgramFiles%\Python312\python.exe"
    "%ProgramFiles%\Python311\python.exe"
    "%ProgramFiles%\Python310\python.exe"
    "%ROOT%\pakistan-orbit-tracker-main\pakistan-orbit-tracker-main\backend\.venv\Scripts\python.exe"
) do (
    if "!PY!"=="" if exist %%~P set "PY=%%~P"
)
if "!PY!"=="" (
    echo [FATAL] No Python interpreter found. Install Python 3.10+ from python.org.
    pause & exit /b 3
)
echo [OK] Using Python: !PY!

set "ACTION_DAILY=cmd /c \"cd /d %SAT% ^&^& \"!PY!\" \"%DAILY%\" >> \"%DAILY_LOG%\" 2^>^&1\""
set "ACTION_HOURLY=cmd /c \"cd /d %SAT% ^&^& \"!PY!\" \"%HOURLY%\" >> \"%HOURLY_LOG%\" 2^>^&1\""

REM -- Daily task: full pipeline at 02:00 -------------------------------
schtasks /Delete /TN "%TASK_DAILY%" /F >nul 2>&1
schtasks /Create /TN "%TASK_DAILY%" /TR "%ACTION_DAILY%" ^
    /SC DAILY /ST 02:00 /RL LIMITED /F
if errorlevel 1 (
    echo [FAIL] could not register %TASK_DAILY% - run as Administrator if "Access denied".
    pause & exit /b 4
)
echo [OK] Daily task registered: %TASK_DAILY% (every day 02:00)

REM -- Hourly task: lightweight TLE top-up every 60 minutes -------------
schtasks /Delete /TN "%TASK_HOURLY%" /F >nul 2>&1
schtasks /Create /TN "%TASK_HOURLY%" /TR "%ACTION_HOURLY%" ^
    /SC HOURLY /MO 1 /RL LIMITED /F
if errorlevel 1 (
    echo [FAIL] could not register %TASK_HOURLY% - run as Administrator if "Access denied".
    pause & exit /b 5
)
echo [OK] Hourly task registered: %TASK_HOURLY% (every 1 hour)

echo.
echo ============================================================
echo  [OK] Both scheduled tasks installed
echo ============================================================
echo   %TASK_DAILY%   every day at 02:00   -> %DAILY_LOG%
echo   %TASK_HOURLY%   every 1 hour         -> %HOURLY_LOG%
echo.
echo Run one now (does not wait for the schedule):
echo   schtasks /Run /TN "%TASK_HOURLY%"
echo   schtasks /Run /TN "%TASK_DAILY%"
echo.
echo Remove them later:
echo   schtasks /Delete /TN "%TASK_DAILY%" /F
echo   schtasks /Delete /TN "%TASK_HOURLY%" /F
echo ============================================================
pause
endlocal