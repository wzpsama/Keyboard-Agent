@echo off
chcp 65001 >nul
rem 前台运行宠物 agent（看日志，Ctrl+C 退出）
cd /d "%~dp0"
python win_agent.py
echo.
echo 宠物已停止。
pause
