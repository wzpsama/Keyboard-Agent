@echo off
rem Install or remove the per-user Startup shortcut. No admin access needed.
setlocal
cd /d "%~dp0"
if /i "%~1"=="--remove" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\autostart.ps1" -Action remove -ProjectRoot "%CD%"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\autostart.ps1" -Action install -ProjectRoot "%CD%"
)
if errorlevel 1 (
    echo Autostart setup failed.
    exit /b 1
)
echo The Startup entry will take effect at the next sign-in.
endlocal
