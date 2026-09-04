@echo off
rem ============================================================
rem Interview Go unified launcher (the ONLY supported way)
rem - Binds 0.0.0.0:8000 so LAN machines can reach it:
rem   http://192.168.31.100:8000
rem - Kills stale instances on port 8000 before starting
rem ============================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [init] venv not found, creating and installing deps...
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
)

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo [restart] killing stale instance PID %%p
    taskkill /PID %%p /F >nul 2>&1
)

echo [start] Interview Go: http://127.0.0.1:8000  (LAN: http://192.168.31.100:8000)
.venv\Scripts\python.exe run.py
