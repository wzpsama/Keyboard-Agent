@echo off
rem Foreground: run the Keyboard-Agent pet and watch its logs (Ctrl+C to stop).
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
%PY% win_agent.py
echo.
echo The pet has stopped.
pause
