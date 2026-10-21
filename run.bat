@echo off
rem 启动 autocodex（无控制台窗口）
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo 首次使用请先执行: mise install ^&^& mise run install
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "main.py"
