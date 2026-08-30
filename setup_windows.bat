@echo off
setlocal
cd /d "%~dp0"

echo ==============================================
echo   Vega 键盘宠物 - Windows 一键安装
echo ==============================================
echo.

rem ---- 1) 找 Python ----
set "PYTHON="
where python >nul 2>nul && set "PYTHON=python"
if not defined PYTHON where py >nul 2>nul && set "PYTHON=py -3"
if not defined PYTHON (
    echo [1/3] 未找到 Python，尝试 winget 安装...
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    where python >nul 2>nul && set "PYTHON=python"
    if not defined PYTHON where py >nul 2>nul && set "PYTHON=py -3"
)
if not defined PYTHON (
    echo.
    echo 自动安装失败。请到 https://www.python.org/downloads/ 安装 Python，
    echo 勾选 "Add python.exe to PATH" 后重新运行本脚本。
    pause
    exit /b 1
)
echo [1/3] Python: %PYTHON%

rem ---- 2) venv + 依赖 ----
echo [2/3] 创建虚拟环境并安装依赖（约 1 分钟）...
if not exist .venv %PYTHON% -m venv .venv
if errorlevel 1 (
    echo 创建 venv 失败，请检查 Python 安装。
    pause
    exit /b 1
)
.venv\Scripts\python -m pip install --upgrade pip >nul 2>nul
rem 离线模式只依赖 Pillow（在线大脑才需要 anthropic，按需再装）
.venv\Scripts\python -m pip install pillow
if errorlevel 1 (
    echo 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)

rem ---- 3) 自检：渲染一帧预览 ----
echo [3/3] 自检：渲染一帧预览...
.venv\Scripts\python -c "from renderer.render import render_frame, save_frame; import os; os.makedirs('out', exist_ok=True); save_frame(render_frame({'mood':'idle','line':'你好，主人','sub':'住在你的键盘里','t':0.0}), 'out/selftest')"
if errorlevel 1 (
    echo 自检失败，请检查依赖是否装全。
    pause
    exit /b 1
)

echo.
echo ==============================================
echo   安装完成！预览图在 out\selftest.png
echo   下一步：
echo     1) AULA L99 键盘连 USB（串口默认 COM3）
echo     2) 已装官方驱动（Image2Bin / SerialPortTool 在
echo        "C:\Program Files (x86)\AULA L99\qt-tool"）
echo     3) 双击 start_agent.bat 启动宠物
echo     （串口不是 COM3 时：改 pusher\push_local.py 的 PORT）
echo ==============================================
pause
endlocal
