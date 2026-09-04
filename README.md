# Go面试 · 面试跟踪管理

个人本地使用的社招面试跟踪工具。需求文档见 [docs/需求文档.md](docs/需求文档.md)。

## 当前状态

✅ **岗位跟踪 + AI 提取已可用**：

- SQLite 建表 + 种子数据（首次启动自动写入 10 个示例岗位）
- FastAPI REST API（岗位增删改查、统计）
- Vue 3 看板页面：新增 / 编辑 / 删除岗位、拖拽卡片流转状态、看板/列表双视图、多筛选
- **AI 快速填充**：粘贴 JD 文本（任意站点）或职位链接自动提取
  - 猎聘（liepin.com）链接：服务端直抓直解析，秒出结果、不耗 AI 额度
  - BOSS直聘（zhipin.com）链接：通过 CDP 直连你自己已登录的浏览器提取（见下方使用方法）
- **机会详情页**（`?page=opportunity-detail&id=N`）：概览 / 调研笔记 / 匹配度 / 题目预测 / 模拟面试 / 轮次与录音 / Offer 七 Tab；点击看板卡片或列表行直接跳转
- **AI 题目预测**：按目标轮次生成预测题单——结合 JD、关联简历、匹配度缺口与题库弱项（不会/模糊的维度加权、避免与近期真实被问题重复），分组输出（八股基础 / 项目深挖 / 场景设计 / 软素质 / 反问建议），附考察意图、答题要点与难度；自测模式一键隐藏要点逐题自测
- **AI 模拟面试**：对话式模拟——AI 面试官按题单提问，根据回答质量决定追问或下一题；点击结束对整场对话生成分析（总评分、逐题复盘三维度打分、薄弱维度、行动清单、题目入题库）；对话与分析全程入库可回看
- **调研笔记**：公司调研 / 团队与业务 / 技术栈 / 自我介绍稿 / 反问清单五大板块，Markdown 编辑渲染，一键 AI 生成调研提纲（占位待核实，不编造事实）
- **岗位匹配度评估**：JD × 简历 AI 生成匹配度报告——岗位画像、逐条匹配（✅/⚠️/❌ + 证据 + 建议）、总分 + 五维雷达图、准备重点、简历追问风险；支持换简历版本重新评估、导出 Markdown
- **URL 即状态**：每个页面都有 `?page=` 后缀（如 `?page=calendar`），切 tab、进详情、看板/列表切换、复盘详情均同步地址栏，刷新/收藏/发链接都能精确回到当前视图
- 后续里程碑：数据备份恢复 / 深色模式 / 全局搜索 / 简历导出打磨

### BOSS 直聘内容提取的使用方法

推荐工作流（最稳定，零自动化特征）：

1. 双击项目根目录 `start-boss-browser.bat` 启动专用浏览器（独立配置，不影响日常 Chrome），登录 BOSS 直聘一次，登录态长期有效
2. 之后在专用浏览器里像平常一样浏览职位（和 HR 沟通、看 JD）
3. 在应用里点「提取当前页面」，自动读取你当前打开的职位页并填表——应用不导航、不注入，只是读字

也可以直接粘贴 BOSS 职位链接点「解析」（自动打开提取，使用 Patchright 反检测内核；参数会被自动剥除）。


## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11 + FastAPI + SQLModel |
| 数据库 | SQLite（`data/app.db`，WAL 模式） |
| 前端 | Vue 3 + Vite + TypeScript + Naive UI + Tailwind CSS |
| 字体 | Inter + Noto Sans SC（本地打包，无外部依赖） |

## 快速开始（使用模式）

```bash
# 1. 安装后端依赖（已装过可跳过；国内网络建议加清华镜像）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. 构建前端（已构建过可跳过）
cd frontend
npm install --registry=https://registry.npmmirror.com
npm run build
cd ..

# 3. 启动（推荐：start.bat 会自动清理旧实例并绑定 0.0.0.0）
start.bat
# 或：python run.py
# 本机访问 http://127.0.0.1:8000 · 局域网访问 http://192.168.31.100:8000
```

## 开发模式

```bash
# 终端 1：后端（热重载）
.venv/Scripts/python -m uvicorn app.main:app --reload

# 终端 2：前端（Vite 热更新，已配置 /api 代理到 8000）
cd frontend && npm run dev
# 访问 http://localhost:5173
```

## 目录结构

```
inter_go/
├── app/                  # FastAPI 后端
│   ├── main.py           # 入口：API 路由 + 静态托管
│   ├── models.py         # 数据模型（Opportunity / InterviewRound）
│   ├── database.py       # SQLite 连接与初始化
│   ├── seed.py           # 首次启动种子数据
│   └── routers/          # 岗位 / 日历 / 题库 / 简历 / 录音 / AI / 设置等路由
├── frontend/             # Vue 3 前端
│   ├── src/views/        # 看板 / 日历 / 题库 / 简历库 / 复盘 / 统计 / Offer 等页面
│   ├── src/components/   # 侧边栏 / 卡片 / 弹窗
│   └── src/types.ts      # 状态、优先级等元数据
├── data/                 # 本地数据（app.db），已 gitignore
├── docs/                 # 需求文档 / 技术调研 / 规划
├── AGENTS.md             # AI 会话工作约定（启动方式等，AI 必读）
├── start.bat             # 统一启动入口（自动清端口、绑定 0.0.0.0）
├── start-boss-browser.bat# 以调试模式启动 BOSS 直聘专用浏览器
├── run.py                # 使用模式启动入口（start.bat 内部调用）
└── requirements.txt
```

## API 一览（当前）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/opportunities` | 岗位列表（含轮次与下一场面试） |
| POST | `/api/opportunities` | 新增岗位 |
| PATCH | `/api/opportunities/{id}` | 更新（改状态会刷新状态时间） |
| DELETE | `/api/opportunities/{id}` | 删除（连同轮次） |
| GET | `/api/stats` | 状态分布 + 未来 7 天面试数 |
| GET | `/api/stats/overview` | 漏斗 / 状态分布 / 渠道效果 / 周活跃 |
| GET PUT DELETE | `/api/offers/{opportunity_id}` | Offer 信息（PUT 为按岗位 upsert） |
| 其余 | `/api/calendar` `/api/rounds` `/api/questions` `/api/resumes` `/api/ai` `/api/settings` | 日历 / 轮次 / 题库 / 简历 / AI 提取 / 设置 |
| GET PUT DELETE | `/api/opportunities/{oid}/notes/{type}` | 调研笔记（type: company/team/tech/self_intro/ask_back，PUT 为按板块 upsert） |
| POST | `/api/opportunities/{oid}/notes/{type}/outline` | AI 生成调研提纲（已有内容需 overwrite=true） |
| GET POST DELETE | `/api/opportunities/{oid}/match-report` | 匹配度报告（POST 生成，body 可传 resume_id 换简历评估） |
| GET POST | `/api/opportunities/{oid}/predictions` | 题目预测题单（POST body 传 round_type，按轮次覆盖式生成） |
| GET POST | `/api/opportunities/{oid}/mock-interviews` | 模拟面试会话列表 / 新建（新建即生成面试官开场） |
| POST | `/api/mock-interviews/{id}/reply` | 提交回答，AI 面试官追问或下一题 |
| POST | `/api/mock-interviews/{id}/finish` | 结束模拟面试并生成分析报告 |
| POST | `/api/recordings` | 上传面试录音（关联岗位/轮次） |
| POST | `/api/recordings/{id}/transcribe` | 启动转写（local / cloud 双通道） |
| POST | `/api/recordings/{id}/review` | 生成 AI 复盘报告（JD + 简历 + 文字稿） |

交互式 API 文档：<http://127.0.0.1:8000/docs>
