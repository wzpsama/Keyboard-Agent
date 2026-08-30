@echo off
rem Background launcher: runs the Keyboard-Agent pet silently, logging to agent.log.
rem Uses %~dp0 so it works from any folder; prefers the local .venv if present.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
start "" /min cmd /c "%PY% win_agent.py > agent.log 2>&1"
