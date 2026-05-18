@echo off
REM ============================================================
REM  Creates a "Space Tracker" shortcut on the user's Desktop.
REM  Double-click that shortcut to start the whole stack.
REM ============================================================
setlocal
cd /d "%~dp0"

set "TARGET=%~dp0Launch Space Tracker.vbs"
if not exist "%TARGET%" (
    echo [FATAL] Cannot find "Launch Space Tracker.vbs" next to this script.
    pause & exit /b 1
)

REM Write a one-shot PowerShell script and run it. Avoids cmd's
REM caret-continuation + quoting traps for inline PowerShell.
set "PSFILE=%TEMP%\create_space_tracker_shortcut.ps1"
(
    echo $target = $args[0]
    echo $desktop = [Environment]::GetFolderPath^('Desktop'^)
    echo $lnkPath = Join-Path $desktop 'Space Tracker.lnk'
    echo $wsh = New-Object -ComObject WScript.Shell
    echo $lnk = $wsh.CreateShortcut^($lnkPath^)
    echo $lnk.TargetPath = $target
    echo $lnk.WorkingDirectory = Split-Path $target
    echo $lnk.IconLocation = "$env:SystemRoot\System32\shell32.dll,14"
    echo $lnk.Description = 'Space Tracker - one-click launcher'
    echo $lnk.WindowStyle = 7
    echo $lnk.Save^(^)
    echo if ^(Test-Path $lnkPath^) { Write-Host "[OK] Created: $lnkPath" } else { Write-Host "[FAIL] Shortcut not created"; exit 1 }
) > "%PSFILE%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%PSFILE%" "%TARGET%"
set "PS_RC=%ERRORLEVEL%"
erase "%PSFILE%" >nul 2>&1

if not "%PS_RC%"=="0" (
    echo [FAIL] PowerShell exit code %PS_RC% - shortcut not created.
    echo Try right-click "Launch Space Tracker.vbs" -^> "Send to" -^> "Desktop (create shortcut)" instead.
    pause & exit /b 2
)

echo.
echo Done. Open your Desktop and double-click "Space Tracker" to start.
pause
endlocal
