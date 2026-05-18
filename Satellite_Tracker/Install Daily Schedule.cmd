@echo off
REM ATLAS — Register the daily HiRes EO forecast as a Windows scheduled task.
REM
REM Run this file ONCE.  After that, Windows will automatically run
REM `Run Daily Forecast.bat` every day at 06:00 local time.  Output goes to
REM `Satellite_Tracker\run_daily.log`.  The Tk dashboard will pick up the
REM refreshed forecast and "Changes since last run" banner automatically
REM the next time you open it.
REM
REM Re-running this script overwrites any prior schedule with the same name.
REM To remove the schedule:  schtasks /Delete /TN "ATLAS HiRes EO Forecast" /F

setlocal
set TASK_NAME=ATLAS HiRes EO Forecast
set BAT="%~dp0Run Daily Forecast.bat"

echo Registering scheduled task: %TASK_NAME%
echo Target:    %BAT%
echo Frequency: daily at 06:00 local time
echo.

schtasks /Create ^
  /SC DAILY ^
  /TN "%TASK_NAME%" ^
  /TR %BAT% ^
  /ST 06:00 ^
  /F

if errorlevel 1 (
    echo.
    echo Could not register. Try running this file as Administrator.
    pause
    exit /b 1
)

echo.
echo OK.  Run "schtasks /Query /TN ""%TASK_NAME%"" /V /FO LIST" to inspect.
echo.
pause
