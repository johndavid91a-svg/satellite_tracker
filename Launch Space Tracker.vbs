' ============================================================
'  Space Tracker - one-click launcher
'  1. Runs "Launch Space Tracker.bat" HIDDEN to start backend+frontend
'  2. Launches the Tkinter GUI in its OWN visible process so the
'     hidden-cmd STARTUPINFO is NOT inherited by Tk's window.
'  3. Waits for the GUI to close, then cleans up ports.
' ============================================================
Option Explicit

Dim sh, fso, scriptDir, batPath, gui, pyw, pyCandidates, i, exitCode
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = scriptDir
batPath = scriptDir & "\Launch Space Tracker.bat"
gui     = scriptDir & "\space_tracker_app.py"

If Not fso.FileExists(batPath) Then
    MsgBox "Missing: " & batPath, vbCritical, "Space Tracker"
    WScript.Quit 1
End If
If Not fso.FileExists(gui) Then
    MsgBox "Missing: " & gui, vbCritical, "Space Tracker"
    WScript.Quit 1
End If

' Resolve pythonw - prefer real installs, reject the WindowsApps stub.
pyCandidates = Array( _
    sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python314\pythonw.exe", _
    sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python313\pythonw.exe", _
    sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\pythonw.exe", _
    sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python311\pythonw.exe", _
    sh.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python310\pythonw.exe", _
    sh.ExpandEnvironmentStrings("%ProgramFiles%")  & "\Python314\pythonw.exe", _
    sh.ExpandEnvironmentStrings("%ProgramFiles%")  & "\Python313\pythonw.exe", _
    sh.ExpandEnvironmentStrings("%ProgramFiles%")  & "\Python312\pythonw.exe", _
    sh.ExpandEnvironmentStrings("%ProgramFiles%")  & "\Python311\pythonw.exe", _
    sh.ExpandEnvironmentStrings("%ProgramFiles%")  & "\Python310\pythonw.exe", _
    scriptDir & "\pakistan-orbit-tracker-main\pakistan-orbit-tracker-main\backend\.venv\Scripts\pythonw.exe" _
)
pyw = ""
For i = 0 To UBound(pyCandidates)
    If pyw = "" Then
        If fso.FileExists(pyCandidates(i)) Then pyw = pyCandidates(i)
    End If
Next

If pyw = "" Then
    MsgBox "No real Python interpreter found. Install Python 3.10+ from python.org.", _
           vbCritical, "Space Tracker"
    WScript.Quit 3
End If

' 1) Fire the headless setup .bat (hidden, do NOT wait so services and GUI
'    start in parallel - GUI is what the user actually sees first).
sh.Run "cmd /c """ & batPath & """", 0, False

' 2) Launch the GUI in a SEPARATE process with a NORMAL window style (1).
'    This prevents Tk's window from inheriting SW_HIDE from the .vbs.
'    bWaitOnReturn = True so we know when the user closes the GUI.
exitCode = sh.Run("""" & pyw & """ """ & gui & """", 1, True)

' 3) Cleanup: kill any backend/frontend the .bat started.
sh.Run "cmd /c " & _
       "for /f ""tokens=5"" %a in ('netstat -aon ^| findstr "":8001 ""') do taskkill /F /PID %a >nul 2>&1 & " & _
       "for /f ""tokens=5"" %a in ('netstat -aon ^| findstr "":8080 ""') do taskkill /F /PID %a >nul 2>&1 & " & _
       "taskkill /F /FI ""WINDOWTITLE eq Orbit Backend*"" >nul 2>&1 & " & _
       "taskkill /F /FI ""WINDOWTITLE eq Orbit Frontend*"" >nul 2>&1", _
       0, True