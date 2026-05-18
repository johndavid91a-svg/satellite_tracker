@echo off
REM ============================================================
REM  Space Tracker - background setup phase (no GUI).
REM  Called by Launch Space Tracker.vbs in hidden mode.
REM  Starts FastAPI backend (:8001) + Vite frontend (:8080).
REM  The .vbs launches pythonw GUI separately so its window is
REM  not affected by this process's hidden STARTUPINFO state.
REM ============================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "ORBIT_ROOT=%ROOT%\pakistan-orbit-tracker-main\pakistan-orbit-tracker-main"
set "BACKEND=%ORBIT_ROOT%\backend"
set "LAUNCH_LOG=%ROOT%\launcher.log"

echo. > "%LAUNCH_LOG%"
echo [%date% %time%] background setup start >> "%LAUNCH_LOG%"

if not exist "%BACKEND%\.venv\Scripts\python.exe" (
    echo [FATAL] backend venv missing >> "%LAUNCH_LOG%"
    exit /b 2
)
if not exist "%ORBIT_ROOT%\package.json" (
    echo [FATAL] frontend package.json missing >> "%LAUNCH_LOG%"
    exit /b 2
)
echo [OK] prereqs present >> "%LAUNCH_LOG%"

REM -- Release stale ports first ----------------------------------------
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8001 " 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8080 " 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo [OK] ports released >> "%LAUNCH_LOG%"

REM -- Start backend in its OWN cmd that cd's into the backend dir ------
REM    cd-then-run is the pattern uvicorn likes. --app-dir is fragile in
REM    a quoted start command, so we avoid it.
echo [start] backend >> "%LAUNCH_LOG%"
start "Orbit Backend" /min cmd /c "cd /d "%BACKEND%" && "%BACKEND%\.venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8001"

REM -- Start frontend ---------------------------------------------------
echo [start] frontend >> "%LAUNCH_LOG%"
start "Orbit Frontend" /min cmd /c "cd /d "%ORBIT_ROOT%" && npm run dev"

REM -- Brief wait then open the browser tab ----------------------------
timeout /t 6 /nobreak >nul
start "" "http://127.0.0.1:8080"
echo [OK] services launched, browser opened >> "%LAUNCH_LOG%"

endlocal
exit /b 0