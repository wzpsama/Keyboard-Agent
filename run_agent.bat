@echo off
rem 常驻宠物 agent（后台静默，日志写到 agent.log）
rem 用 %~dp0 定位项目目录、用 PATH 里的 python，克隆到任意目录都能跑。
cd /d "%~dp0"
python win_agent.py > agent.log 2>&1
