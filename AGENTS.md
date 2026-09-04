# AI 会话工作约定（启动服务必读）

## 启动后端服务

- **唯一启动方式**：在项目根目录执行 `./start.bat`（内部等价于 `.venv/Scripts/python.exe run.py`）。
- 服务必须绑定 **`0.0.0.0:8000`**（run.py 已固定）。**严禁**用 `--host 127.0.0.1` 或任何只绑本机回环的命令启动 uvicorn——用户需要从局域网其他机器访问，地址是 `http://192.168.31.100:8000`。
- `start.bat` 启动前会自动清掉 8000 端口上的旧实例，不需要（也不要）手动 taskkill 后另起命令。
- 不要同时存在多个服务实例；发现 8000 端口被 `--host 127.0.0.1` 的旧实例占用时，杀掉并用 `start.bat` 重启。

## 改动后的生效方式

- 后端（`app/`、`run.py`）改动：需要重启服务（重新执行 `./start.bat`）。
- 前端（`frontend/`）改动：执行 `cd frontend && npm run build` 即可生效，**无需重启服务**（后端静态托管 dist）。

## 数据

- 数据库：`data/app.db`（SQLite / WAL），本地个人数据，勿删除、勿提交。
- 首次启动自动写入种子数据；`.venv/`、`frontend/node_modules/`、`frontend/dist/` 均为本地产物。
