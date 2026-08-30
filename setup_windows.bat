@echo off
setlocal
cd /d "%~dp0"

echo ==============================================
echo   Keyboard-Agent - Windows Setup
echo ==============================================
echo.

rem ---- 1) Locate Python ----
set "PYTHON="
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
if not defined PYTHON where python >nul 2>nul && set "PYTHON=python"
if not defined PYTHON where py >nul 2>nul && set "PYTHON=py -3"
if not defined PYTHON (
    echo [1/3] Python not found, trying winget...
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    where python >nul 2>nul && set "PYTHON=python"
    if not defined PYTHON where py >nul 2>nul && set "PYTHON=py -3"
)
if not defined PYTHON (
    echo.
    echo Install failed. Get Python from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH", then run this again.
    pause
    exit /b 1
)
echo [1/3] Python: %PYTHON%

rem ---- 2) venv + dependencies ----
echo [2/3] Creating virtualenv and installing Pillow...
if not exist .venv %PYTHON% -m venv .venv
if errorlevel 1 (
    echo Failed to create the virtualenv.
    pause
    exit /b 1
)
.venv\Scripts\python -m pip install --upgrade pip >nul 2>nul
rem Offline mode needs only Pillow (the online brain wants anthropic, installed on demand).
.venv\Scripts\python -m pip install pillow
if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

rem ---- 3) Self-test: render one frame ----
echo [3/3] Rendering a test frame...
.venv\Scripts\python -c "from renderer.render import render_frame, save_frame; import os; os.makedirs('out', exist_ok=True); save_frame(render_frame({'mood':'idle','line':'Hi! I am Vega','sub':'Idle','t':0.0,'character':'vega'}), 'out/selftest')"
if errorlevel 1 (
    echo Self-test failed.
    pause
    exit /b 1
)

echo.
echo ==============================================
echo   Setup complete! Preview: out\selftest.png
echo   Next:
echo     1) Connect the AULA L99 keyboard via USB (COM3)
echo     2) Install the official driver (Image2Bin / SerialPortTool)
echo     3) Run start_agent.bat to launch the pet
echo     (If the COM port is not COM3, edit pusher\push_local.py)
echo ==============================================
pause
endlocal
