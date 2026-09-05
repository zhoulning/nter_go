# AI 会话工作约定（启动服务必读）

## 启动后端服务

- **唯一启动方式**：在项目根目录执行 `./start.bat`（内部等价于 `.venv/Scripts/python.exe run.py`）。
- 服务必须绑定 **`0.0.0.0:8000`**（run.py 已固定）。**严禁**用 `--host 127.0.0.1` 或任何只绑本机回环的命令启动 uvicorn——用户需要从局域网其他机器访问，地址是 `http://192.168.31.100:8000`。
- `start.bat` 启动前会自动清掉 8000 端口上的旧实例，不需要（也不要）手动 taskkill 后另起命令。
- 不要同时存在多个服务实例；发现 8000 端口被 `--host 127.0.0.1` 的旧实例占用时，杀掉并用 `start.bat` 重启。

## 改动后的生效方式

- 后端（`app/`、`run.py`）改动：需要重启服务（重新执行 `./start.bat`）。
- 前端（`frontend/`）改动：执行 `cd frontend && npm run build` 即可生效，**无需重启服务**（后端静态托管 dist）。

## 硬性规定（不可违反）

- **知识库（用户 Obsidian vault）只读**：任何代码与 AI 操作对知识库文件夹只允许读取（检索、解析），严禁写入、修改、移动、重命名、删除其中的任何文件或目录。当前唯一入口是 `app/kb.py` 的 `search_knowledge_base`（纯只读实现）；未来新增知识库相关功能也必须遵守此规定。

## 前端移动端适配约定（新增页面必须遵守）

- 站点已同时适配 PC 与移动端浏览器。分界点是 Tailwind 的 `md`（768px）：`<768px` 走移动端布局，`≥768px` 是 PC 布局。
- **所有移动端样式一律用 `max-md:` 前缀做增量叠加**（如 `px-7 max-md:px-4`），禁止改动 PC 端已有类名；PC 端表现必须与适配前完全一致。
- 新增页面时必须同步做移动端适配，检查点：
  1. 页面内边距 `px-7`/`pt-6` 补上 `max-md:px-4`/`max-md:pt-4`；
  2. 固定宽度元素（`w-[xxx]`、`style="width:"`）在移动端改为 `max-md:w-full` 或允许换行/横向滚动；
  3. 多列布局给出移动端单列堆叠方案（`max-md:flex-col` 或基础类就是单列）；
  4. 仅 hover 触发的操作（`group-hover`、`opacity-0`）在移动端要有常显替代（`max-md:flex`/`max-md:opacity-100`）；
  5. 全屏高度用 `calc(100vh-…)` 的滚动容器，补 `max-md:max-h-[calc(100dvh-…)]`，避免手机地址栏遮挡。
- 导航接入：新页面在 `AppShell.vue` 的 `sections` 里注册后，侧边栏（PC）、底部标签栏/「更多」抽屉（移动端）、顶栏标题（`PAGE_TITLES`）会自动生效；若新增详情页且自带返回顶栏，记得加进 `hideMobileHeader` 与 `tabActive`/`moreActive` 的归类。
- 弹窗卡片沿用 `.modal-card` / `.edit-card` / `.detail-card` 类名（移动端全局样式已做收窄），或用 `n-modal preset="card"`；自建弹窗需自行保证 `max-width: calc(100vw - 16px)`。

## 数据

- 数据库：`data/app.db`（SQLite / WAL），本地个人数据，勿删除、勿提交。
- 首次启动自动写入种子数据；`.venv/`、`frontend/node_modules/`、`frontend/dist/` 均为本地产物。
