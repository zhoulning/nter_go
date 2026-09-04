# 技术调研：BOSS直聘 / 猎聘 工作描述的稳定获取方案

- 日期：2026-09-05
- 结论：**猎聘可服务端直抓（已实测通过）；BOSS直聘推荐 CDP 直连用户自己已登录的 Chrome（社区验证的主流稳定方案）**

---

## 1. 结论速览

| 场景 | 可行方案 | 实现成本 | 稳定性 | 备注 |
|---|---|---|---|---|
| 猎聘职位链接 | 服务端 HTTP 直抓 + HTML 解析 | 低（纯 httpx，已 PoC 验证） | 高（匿名可访问，页面 SSR） | 实测 200 + 完整 JD 在 HTML 中 |
| BOSS直聘职位链接 | **CDP 直连用户自己已登录的 Chrome** | 中（引入 Playwright） | 高（社区验证的主流做法） | 真实登录态 + 真实指纹，低频个人使用风险很小 |
| BOSS直聘（备选） | 浏览器扩展 / 油猴脚本回传 | 中高 | 极高（用户真实会话） | 需要写扩展，放二期 |
| 通用兜底 | 手动粘贴 JD 文本（已上线） | — | — | 任何站点都能用 |

---

## 2. 实测记录（2026-09-05，本机 Windows + Chrome UA）

### BOSS直聘（zhipin.com）

| 测试 | 结果 |
|---|---|
| `www.zhipin.com/job_detail/...` 服务端 GET | 200 但返回 41KB 反爬骨架页（loading-section + boss-loading），**无真实 JD** |
| `m.zhipin.com/job_detail/...`（iPhone UA） | 200 但含「安全验证」页 |
| 社区资料 | 未登录拿不到内容；登录后请求需 `__zp_stoken__` 等签名；同 IP 约 90 次访问触发滑块验证 |

**结论：服务端直抓不可行**，需要真实浏览器环境。

### 猎聘（liepin.com）

| 测试 | 结果 |
|---|---|
| 首页匿名 GET | 200，342KB，SSR 渲染，含 66 个真实职位链接 |
| 搜索页 `/zhaopin/?key=...` | 200 但是 29KB CSR 空壳（前端渲染），匿名抓不到列表 |
| **职位详情页 `/job/xxx.shtml` 匿名 GET** | **200，168KB，`job-intro-container` 内含完整岗位职责文本，纯 HTML 可解析** |
| 解析 PoC | title / JD 区块文本成功提取（518 字干净文本） |

**结论：职位详情页服务端直抓可行**（搜索列表页是 CSR，但我们的场景是"用户粘贴详情链接"，正好绕开列表页）。

---

## 3. 方案分析

### 3.1 BOSS直聘：CDP 直连用户自己的浏览器（推荐）

原理：不模拟浏览器、不伪造请求，而是**附加（attach）到用户自己正在用的、已登录 BOSS 的 Chrome/Edge**：

1. 一次性引导：以 `--remote-debugging-port=9222` 启动浏览器并登录 BOSS（用户平时怎么用就怎么用）。
2. 用户粘贴职位链接 → 后端 Playwright `connect_over_cdp("http://localhost:9222")`。
3. 在该浏览器里新开标签页打开链接 → 等 `.job-detail` 区域渲染 → 提取文本 → 关闭标签页。

为什么稳：
- 真实浏览器指纹 + 真实登录态 + 真实用户行为特征，风控视角与手动打开网页无异；
- 个人低频使用（一天几次），远低于约 90 次/IP 的频控线；
- 不注入 XHR、不碰签名算法，只是"打开页面读 DOM"。

参考实现 [eatmoreduck/boss-zhipin-scraper](https://github.com/eatmoreduck/boss-zhipin-scraper)（MIT）的要点值得借鉴：
- 用独立隔离的 Chrome profile 持久化登录态（登录一次长期有效，不影响主浏览器）；
- 识别风控信号（如 code 31/37「环境存在异常」）**立即停止**而非重试；
- 详情页检测到"登录查看完整内容"登录墙时明确报错，避免拿到截断内容。

不推荐的路线：
- **无头浏览器 + 伪造请求/签名逆向**：对抗激烈（字体反爬、行为指纹、滑块），维护成本高，社区项目大面积失效；
- **无头浏览器硬抓未登录页**：拿到的仍是安全验证页。

### 3.2 猎聘：服务端直抓（推荐，成本最低）

- 详情页是 SSR，匿名可访问；用 httpx + Chrome UA 请求后解析：
  - 标题：`<title>`（含岗位与公司名）
  - 薪资等字段：页面内嵌状态 JSON
  - 工作描述：`job-intro-container` 区块剥标签取文本
- 建议实现时注意：随机 2-5s 延迟、失败即停不重试轰炸、识别验证码页特征字样。
- 另有**官方通道**：[猎聘 CLI / MCP Server](https://www.liepin.com/mcp/server)（`liepin-cli`，提供职位搜索/投递等能力），是合规的接口化路线，可后续接入；社区已有基于它的封装（如 [liepin-jobs skill](https://lobehub.com/skills/terminalskills-skills-liepin-jobs)）。

### 3.3 通用兜底（已上线）

手动粘贴 JD 文本 → AI 提取。对任何站点都有效，作为两条自动通道失败时的兜底。

### 3.4 相关开源组件

| 项目 | 方式 | 状态 | 对本项目的价值 |
|---|---|---|---|
| [Playwright (Python)](https://github.com/microsoft/playwright-python) | 浏览器自动化 / CDP | 活跃 | BOSS 通道的底层依赖 |
| [eatmoreduck/boss-zhipin-scraper](https://github.com/eatmoreduck/boss-zhipin-scraper) | Chrome CDP 直连 + 被动旁听 API | 活跃（v2.2，MIT） | 风控信号识别、隔离 profile 等实践可直接借鉴 |
| [mergedao/mcp-jobs](https://github.com/mergedao/mcp-jobs) | 无头浏览器多平台抓取（猎聘/Boss/智联/51job，免登录搜索） | 125★，MIT | 站点适配（选择器/翻页）参考实现 |
| [猎聘官方 CLI / MCP Server](https://www.liepin.com/mcp/server) | 官方接口 | 官方 | 合规通道，后续可接职位搜索 |
| [ChoungJX/Liepin-spider](https://github.com/ChoungJX/Liepin-spider) 等老爬虫 | Scrapy HTTP | 多数已失效 | 仅作历史参考，验证了猎聘反爬相对宽松 |

---

## 4. 推荐落地计划

1. **第一期：猎聘直抓通道**
   - 后端识别 `liepin.com` 域名 → httpx 抓详情页 → 解析出标题/薪资/工作描述 → 交给现有 AI 提取链路填表；
   - 解析失败（验证码页/下架页）时给出明确提示。
2. **第二期：BOSS CDP 通道**
   - 设置页新增「连接我的浏览器」引导（一键命令启动带调试端口的浏览器）；
   - 检测到 `zhipin.com` 链接时走 CDP：打开 → 抽取 → 关闭；未连接时提示引导。
3. **第三期（可选）**：油猴脚本/浏览器扩展，用户在 JD 页面一键回传本地服务，彻底零风控暴露。

## 5. 风控与合规说明

- 本工具为**单机个人使用、低频访问**（每天个位数次），与批量爬取有本质区别；
- 所有抓取失败/风控信号（滑块、验证码页、异常 code）都应**立即停止并提示用户**，绝不自动重试轰炸；
- 各平台数据仅存本地 SQLite，仅供个人求职参考；
- 相关项目普遍附带声明：仅供学习研究，需遵守平台用户协议（BOSS 有 [BSSRC](https://security.zhipin.com/) 安全响应中心）。
