@echo off
rem Manual windowless launcher. Runtime output goes to agent_run.log.
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" /d "%CD%" "%CD%\.venv\Scripts\pythonw.exe" "%CD%\win_agent.py"
) else (
    where pythonw.exe >nul 2>nul
    if errorlevel 1 (
        echo pythonw.exe was not found. Run setup_windows.bat first.
        exit /b 1
    )
    start "" /d "%CD%" pythonw.exe "%CD%\win_agent.py"
)
