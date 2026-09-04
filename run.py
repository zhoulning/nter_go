"""进击の面试 启动入口：托管前端构建产物 + 自动打开浏览器。

首次使用：
    pip install -r requirements.txt
    cd frontend && npm install && npm run build && cd ..
    python run.py
"""
import sys
import threading
import time
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"


def _ensure_venv():
    """若存在项目 venv 且当前解释器不是它，则用 venv 解释器重启自己。"""
    if not VENV_PYTHON.exists() or Path(sys.executable).resolve() == VENV_PYTHON.resolve():
        return
    import os

    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), __file__])


def _open_browser():
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:8000/")


def main():
    import uvicorn

    if not (BASE_DIR / "frontend" / "dist" / "index.html").exists():
        print("[提示] 未找到 frontend/dist，请先执行：cd frontend && npm install && npm run build")

    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    _ensure_venv()
    main()
