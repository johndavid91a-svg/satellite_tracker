@echo off
setlocal
set "ROOT=%~dp0"

echo ============================================================
echo  Pakistan Orbit Tracker - Startup
echo ============================================================

:: ── Kill anything already on port 8001 ───────────────────────
echo [Cleanup] Freeing port 8001...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8001 " 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)

:: ── Backend setup ─────────────────────────────────────────────
if not exist "%ROOT%backend\.venv\Scripts\python.exe" (
  echo [Backend] Creating Python virtual environment...
  cd /d "%ROOT%backend"
  python -m venv .venv
  if errorlevel 1 (
    echo ERROR: Failed to create venv. Make sure Python 3.10+ is installed.
    pause
    exit /b 1
  )
)

echo [Backend] Installing / updating Python dependencies...
"%ROOT%backend\.venv\Scripts\python.exe" -m pip install -r "%ROOT%backend\requirements.txt" --quiet
if errorlevel 1 (
  echo ERROR: pip install failed.
  pause
  exit /b 1
)

:: ── Frontend setup ────────────────────────────────────────────
if not exist "%ROOT%node_modules" (
  echo [Frontend] Installing npm dependencies...
  cd /d "%ROOT%"
  npm install
  if errorlevel 1 (
    echo ERROR: npm install failed. Make sure Node.js is installed.
    pause
    exit /b 1
  )
)

:: ── Launch ────────────────────────────────────────────────────
echo.
echo [Backend]  Starting FastAPI on http://127.0.0.1:8001
echo [Frontend] Starting Vite  on http://localhost:8080
echo.

start "Orbit Tracker - Backend" cmd /k "cd /d "%ROOT%backend" && call .venv\Scripts\activate && python -m uvicorn main:app --host 127.0.0.1 --port 8001"

echo [Startup]  Waiting for backend to be ready...
timeout /t 4 /nobreak >nul

start "Orbit Tracker - Frontend" cmd /k "cd /d "%ROOT%" && npm run dev"

echo [Startup]  Waiting for frontend to be ready...
timeout /t 4 /nobreak >nul

echo [Browser]  Opening http://localhost:8080 ...
start "" "http://localhost:8080"

echo.
echo ============================================================
echo  Both services are running.
echo  Backend  : http://127.0.0.1:8001
echo  Frontend : http://localhost:8080
echo  API Docs : http://127.0.0.1:8001/docs
echo ============================================================
echo  Close this window or press any key to exit.
pause >nul
endlocal
