"""职业方向档案（Track Profile）。

系统默认面向 Java 后端；每个方向档案自带一套「考察维度、题单分组、轮次侧重、
AI 人设与评分口径」配置。当前方向全局唯一（存 Setting.career_track），
切换后所有 AI 出题/答案/体检/复盘的 prompt 与题库维度预设置随之切换。
内置档案在代码中只读维护，不新增数据表；复用 Setting 键值存储。
"""
import json

from sqlmodel import Session

from app.models import Setting, User

TRACK_KEY = "career_track"  # 当前职业方向（Setting 键，值为档案 key，全局共享）
CUSTOM_DIMS_KEY = "career_custom_dimensions"  # 用户自定义考察维度（Setting 键，JSON 数组）

DEFAULT_TRACK = "java-backend"

# 轮次 key 与 predictions.ROUND_TYPES 对应；档案必须覆盖全部 9 个 key
_ROUND_KEYS = (
    "written", "first", "second", "third", "comprehensive", "hr",
    "project", "stress", "other",
)


def _track(
    *,
    key: str,
    name: str,
    tagline: str,
    dimensions: list[str],
    groups: list[str],
    round_emphasis: dict[str, str],
    coach_role: str,
    review_default: str,
    question_tags: str,
    dim_examples: str,
    typo_fixes: str,
) -> dict:
    missing = [k for k in _ROUND_KEYS if k not in round_emphasis]
    if missing:
        raise ValueError(f"track {key} 缺少轮次侧重: {missing}")
    return {
        "key": key,
        "name": name,
        "tagline": tagline,
        "dimensions": dimensions,
        "groups": groups,
        "round_emphasis": round_emphasis,
        "coach_role": coach_role,
        "review_default": review_default,
        "question_tags": question_tags,
        "dim_examples": dim_examples,
        "typo_fixes": typo_fixes,
    }


BUILTIN_TRACKS: list[dict] = [
    _track(
        key="java-backend",
        name="Java 后端",
        tagline="JVM、并发、分布式服务端",
        dimensions=[
            "语言特性", "JUC", "JVM", "MySQL", "Redis", "消息队列", "分布式",
            "微服务", "计算机网络", "系统设计", "项目深挖", "场景设计", "算法", "软素质", "其他",
        ],
        groups=["八股基础", "项目深挖", "场景设计", "软素质", "反问建议"],
        round_emphasis={
            "written": "笔试侧重：算法手写题、语言基础、计算机基础选择题，给出题目时附上解题思路要点",
            "first": "一面侧重：语言特性、并发、数据库 / 缓存 / 消息队列等八股基础，以及简历项目的初步深挖",
            "second": "二面侧重：技术深度（原理、源码级理解、性能调优）、系统方案设计、复杂问题排查思路",
            "third": "三面侧重：大型系统设计、技术选型与权衡、架构演进、团队协作与技术视野、软素质",
            "comprehensive": "综合面侧重：不设固定侧重——八股基础、项目深挖、系统设计、场景开放题、职业规划与软素质都可能问到，考察整体素养与随机应变；提问自由度最大，按现场对话自然流动",
            "hr": "HR 面侧重：求职动机、离职原因、职业规划、稳定性、薪资沟通策略、软素质与价值观",
            "project": "项目经历面（专题）侧重：整场只围绕简历项目深挖——个人贡献与实际角色、架构与技术选型的取舍理由、难点攻关与故障排查过程、量化结果与业务价值、复盘与改进；不问与项目无关的八股 / 原理 / 智力题",
            "stress": "压力面（专题）侧重：高压质询下的技术基础与项目——问题本身仍来自简历、项目与技术基础，但以质疑、否定、连环追问的施压方式提出，考察情绪稳定性、抗压能力与临场反应",
            "other": "一般技术面试：基础与项目并重",
        },
        coach_role="资深后端面试教练",
        review_default="Java 后端/服务端开发",
        question_tags="项目深挖/系统设计/场景设计/语言特性/JUC/JVM/MySQL/Redis/消息队列/分布式/微服务/计算机网络/算法/软素质",
        dim_examples="MySQL / 项目深挖 / 系统设计",
        typo_fixes="radis→Redis、麦ysql→MySQL、springboot→Spring Boot、dubble→Dubbo、卡夫卡→Kafka、布拉格→Pulsar",
    ),
    _track(
        key="go-backend",
        name="Go 后端",
        tagline="Goroutine、云原生、高并发服务",
        dimensions=[
            "语言特性", "Goroutine/GMP", "GC与内存", "MySQL", "Redis", "消息队列", "分布式",
            "微服务/K8s", "计算机网络", "系统设计", "项目深挖", "场景设计", "算法", "软素质", "其他",
        ],
        groups=["八股基础", "项目深挖", "场景设计", "软素质", "反问建议"],
        round_emphasis={
            "written": "笔试侧重：算法手写题、Go 语言基础（slice/map/chan 语义）、计算机基础选择题，给出题目时附上解题思路要点",
            "first": "一面侧重：Go 语言特性、Goroutine 与调度、数据库 / 缓存 / 消息队列等八股基础，以及简历项目的初步深挖",
            "second": "二面侧重：技术深度（runtime 原理、GC 调优、性能分析 pprof）、系统方案设计、复杂问题排查思路",
            "third": "三面侧重：大型系统设计、技术选型与权衡、架构演进、云原生与微服务治理、团队协作与技术视野、软素质",
            "comprehensive": "综合面侧重：不设固定侧重——八股基础、项目深挖、系统设计、场景开放题、职业规划与软素质都可能问到，考察整体素养与随机应变；提问自由度最大，按现场对话自然流动",
            "hr": "HR 面侧重：求职动机、离职原因、职业规划、稳定性、薪资沟通策略、软素质与价值观",
            "project": "项目经历面（专题）侧重：整场只围绕简历项目深挖——个人贡献与实际角色、架构与技术选型的取舍理由、难点攻关与故障排查过程、量化结果与业务价值、复盘与改进；不问与项目无关的八股 / 原理 / 智力题",
            "stress": "压力面（专题）侧重：高压质询下的技术基础与项目——问题本身仍来自简历、项目与技术基础，但以质疑、否定、连环追问的施压方式提出，考察情绪稳定性、抗压能力与临场反应",
            "other": "一般技术面试：基础与项目并重",
        },
        coach_role="资深 Go 后端面试教练",
        review_default="Go 后端/服务端开发",
        question_tags="项目深挖/系统设计/场景设计/语言特性/Goroutine与调度/GC与内存/MySQL/Redis/消息队列/分布式/微服务与K8s/计算机网络/算法/软素质",
        dim_examples="Goroutine/GMP / 项目深挖 / 系统设计",
        typo_fixes="golang→Go、goroutine→Goroutine、麦ysql→MySQL、radis→Redis、卡夫卡→Kafka、库伯内蒂斯→Kubernetes",
    ),
    _track(
        key="frontend",
        name="前端",
        tagline="浏览器、框架、工程化与体验",
        dimensions=[
            "JS/TS 语言特性", "CSS", "浏览器原理", "Vue", "React", "前端工程化", "性能优化",
            "跨端/小程序", "计算机网络", "系统设计", "项目深挖", "场景设计", "算法", "软素质", "其他",
        ],
        groups=["八股基础", "项目深挖", "场景设计", "软素质", "反问建议"],
        round_emphasis={
            "written": "笔试侧重：手写 JS 题（防抖节流、Promise 并发控制）、算法题、CSS 布局题，给出题目时附上解题思路要点",
            "first": "一面侧重：JS/TS 语言特性、CSS、浏览器原理（渲染、事件循环）、框架（Vue/React）高频机制题，以及简历项目的初步深挖",
            "second": "二面侧重：框架原理与源码级理解、性能优化实战、前端工程化（构建、微前端、监控）、复杂场景方案设计",
            "third": "三面侧重：大型前端架构设计、技术选型与权衡、跨团队协作与技术视野、软素质",
            "comprehensive": "综合面侧重：不设固定侧重——基础八股、项目深挖、方案设计、场景开放题、职业规划与软素质都可能问到，考察整体素养与随机应变；提问自由度最大，按现场对话自然流动",
            "hr": "HR 面侧重：求职动机、离职原因、职业规划、稳定性、薪资沟通策略、软素质与价值观",
            "project": "项目经历面（专题）侧重：整场只围绕简历项目深挖——个人贡献与实际角色、技术选型的取舍理由、难点攻关与性能优化过程、量化结果与业务价值、复盘与改进；不问与项目无关的八股 / 原理 / 智力题",
            "stress": "压力面（专题）侧重：高压质询下的技术基础与项目——问题本身仍来自简历、项目与技术基础，但以质疑、否定、连环追问的施压方式提出，考察情绪稳定性、抗压能力与临场反应",
            "other": "一般技术面试：基础与项目并重",
        },
        coach_role="资深前端面试教练",
        review_default="Web 前端开发",
        question_tags="项目深挖/系统设计/场景设计/JS与TS语言特性/CSS/浏览器原理/Vue/React/前端工程化/性能优化/跨端与小程序/计算机网络/算法/软素质",
        dim_examples="浏览器原理 / 项目深挖 / 系统设计",
        typo_fixes="javaScript→JavaScript、vus→Vue、react→React（指框架名时）、哭克→Cookie、websocket→WebSocket、首屏→首屏（无错则保持）",
    ),
    _track(
        key="qa",
        name="测试",
        tagline="测试理论、自动化与质量保障",
        dimensions=[
            "测试理论", "用例设计", "接口测试", "自动化测试", "性能测试", "测试开发", "CI/CD",
            "数据库", "计算机网络", "项目深挖", "场景设计", "编程基础", "软素质", "其他",
        ],
        groups=["测试基础", "项目深挖", "场景设计", "软素质", "反问建议"],
        round_emphasis={
            "written": "笔试侧重：测试用例设计题、逻辑题、基础编程题，给出题目时附上解题思路要点",
            "first": "一面侧重：测试理论、用例设计、接口测试工具、SQL 基础，以及简历项目的初步深挖",
            "second": "二面侧重：自动化框架原理与落地、性能测试方法、测试平台 / 工具开发能力、复杂业务的质量保障方案",
            "third": "三面侧重：质量体系建设、流程改进、跨团队协作与推动能力、技术视野、软素质",
            "comprehensive": "综合面侧重：不设固定侧重——测试基础、项目深挖、场景设计、职业规划与软素质都可能问到，考察整体素养与随机应变；提问自由度最大，按现场对话自然流动",
            "hr": "HR 面侧重：求职动机、离职原因、职业规划、稳定性、薪资沟通策略、软素质与价值观",
            "project": "项目经历面（专题）侧重：整场只围绕简历项目深挖——个人贡献与实际角色、测试策略与自动化方案的取舍理由、难点攻关（如 flaky 用例治理、环境稳定性）、量化结果与质量价值、复盘与改进；不问与项目无关的八股 / 原理 / 智力题",
            "stress": "压力面（专题）侧重：高压质询下的测试基础与项目——问题本身仍来自简历、项目与测试基础，但以质疑、否定、连环追问的施压方式提出（如「线上漏测了你怎么解释」），考察情绪稳定性、抗压能力与临场反应",
            "other": "一般测试面试：基础与项目并重",
        },
        coach_role="资深测试面试教练",
        review_default="测试开发 / 质量保障（QA）",
        question_tags="项目深挖/场景设计/测试理论/用例设计/接口测试/自动化测试/性能测试/测试开发/CI与CD/数据库/计算机网络/编程基础/软素质",
        dim_examples="用例设计 / 项目深挖 / 自动化测试",
        typo_fixes="postman→Postman、jmeter→JMeter、selinium→Selenium、接偶测试→接口测试、pytest→pytest（大小写保持）",
    ),
    _track(
        key="algorithm",
        name="算法",
        tagline="机器学习、深度学习与大模型",
        dimensions=[
            "机器学习基础", "深度学习", "NLP", "CV", "推荐/搜广推", "大模型", "数学基础",
            "代码与数据结构", "论文与项目深挖", "场景设计", "系统设计", "软素质", "其他",
        ],
        groups=["基础八股", "论文与项目深挖", "场景设计", "软素质", "反问建议"],
        round_emphasis={
            "written": "笔试侧重：算法与数据结构手写题（LeetCode 中硬题为主）、概率与数学题，给出题目时附上解题思路要点",
            "first": "一面侧重：机器学习 / 深度学习基础（模型原理、优化器、正则化、经典网络结构）、代码与数据结构，以及简历中论文 / 项目的初步深挖",
            "second": "二面侧重：技术深度——模型细节与调参经验、特征工程、线上部署与推理性能、论文创新点的批判性追问、复杂场景建模方案",
            "third": "三面侧重：算法方案的业务落地与权衡、研究方向与技术视野、跨团队协作、软素质",
            "comprehensive": "综合面侧重：不设固定侧重——基础八股、论文与项目深挖、场景建模、职业规划与软素质都可能问到，考察整体素养与随机应变；提问自由度最大，按现场对话自然流动",
            "hr": "HR 面侧重：求职动机、离职原因、职业规划、稳定性、薪资沟通策略、软素质与价值观",
            "project": "论文/项目经历面（专题）侧重：整场只围绕简历中的论文与项目深挖——个人贡献与实际角色、模型与方案选型的取舍理由、实验设计与指标提升归因、失败尝试与复盘；不问与项目无关的八股 / 原理 / 智力题",
            "stress": "压力面（专题）侧重：高压质询下的算法基础与项目——问题本身仍来自简历、论文与技术基础，但以质疑、否定、连环追问的施压方式提出（如「你的提升会不会只是随机波动」），考察情绪稳定性、抗压能力与临场反应",
            "other": "一般算法面试：基础与项目并重",
        },
        coach_role="资深算法面试教练",
        review_default="算法工程师（机器学习/深度学习方向）",
        question_tags="论文与项目深挖/场景设计/系统设计/机器学习基础/深度学习/NLP/CV/推荐与搜广推/大模型/数学基础/代码与数据结构/软素质",
        dim_examples="深度学习 / 论文与项目深挖 / 大模型",
        typo_fixes="pytorch→PyTorch、tensorflow→TensorFlow、transformer→Transformer、过拟合→过拟合（无错则保持）、bb→Bleu（按上下文）",
    ),
    _track(
        key="ai-app",
        name="AI 应用",
        tagline="大模型应用、RAG 与 Agent 工程",
        dimensions=[
            "LLM 基础", "Prompt 工程", "RAG 检索增强", "Agent 与工具调用", "向量数据库",
            "微调与部署", "AI 工程化", "评估与优化", "编程基础", "项目深挖", "场景设计", "软素质", "其他",
        ],
        groups=["基础八股", "项目深挖", "场景设计", "软素质", "反问建议"],
        round_emphasis={
            "written": "笔试侧重：编程基础题（Python 为主）、大模型基础概念题、算法题，给出题目时附上解题思路要点",
            "first": "一面侧重：LLM 基础（Token、上下文窗口、温度等采样参数）、Prompt 工程与 RAG 基本链路、Python 编程基础，以及简历项目的初步深挖",
            "second": "二面侧重：RAG 链路细节（切块策略、召回与重排、幻觉治理）、Agent 设计（工具调用、规划、多轮纠错）、效果评估体系与成本/延迟优化、复杂场景方案设计",
            "third": "三面侧重：AI 应用整体架构设计、技术选型与权衡（自研 / 开源模型 / API）、工程化与稳定性（缓存、限流降级、可观测）、业务落地价值与 ROI、软素质",
            "comprehensive": "综合面侧重：不设固定侧重——基础八股、项目深挖、方案设计、场景开放题、职业规划与软素质都可能问到，考察整体素养与随机应变；提问自由度最大，按现场对话自然流动",
            "hr": "HR 面侧重：求职动机、离职原因、职业规划、稳定性、薪资沟通策略、软素质与价值观",
            "project": "项目经历面（专题）侧重：整场只围绕简历项目深挖——个人贡献与实际角色、技术选型（模型 / 框架 / 向量库）的取舍理由、效果指标与评估方法、badcase 治理与迭代过程、量化结果与业务价值、复盘与改进；不问与项目无关的八股 / 原理 / 智力题",
            "stress": "压力面（专题）侧重：高压质询下的技术基础与项目——问题本身仍来自简历、项目与技术基础，但以质疑、否定、连环追问的施压方式提出（如「你这效果提升是不是靠标注数据堆出来的」），考察情绪稳定性、抗压能力与临场反应",
            "other": "一般 AI 应用面试：基础与项目并重",
        },
        coach_role="资深 AI 应用工程师面试教练",
        review_default="AI 应用工程师（大模型应用方向）",
        question_tags="项目深挖/场景设计/LLM基础/Prompt工程/RAG检索增强/Agent与工具调用/向量数据库/微调与部署/AI工程化/评估与优化/编程基础/软素质",
        dim_examples="RAG 检索增强 / Agent 与工具调用 / 项目深挖",
        typo_fixes="langchain→LangChain、llm→LLM、rag→RAG、faiss→FAISS、奥openai→OpenAI、智能体→Agent（指 LLM 智能体时）",
    ),
    _track(
        key="product-manager",
        name="产品经理",
        tagline="需求洞察、方案设计与产品落地",
        dimensions=[
            "产品方法论", "需求分析", "产品设计", "数据分析", "用户研究", "竞品分析",
            "商业思维", "技术理解力", "项目协作", "项目深挖", "场景设计", "软素质", "其他",
        ],
        groups=["产品基础", "项目深挖", "场景设计", "软素质", "反问建议"],
        round_emphasis={
            "written": "笔试侧重：产品分析题（需求优先级排序、功能方案设计）、逻辑与数据分析题，给出题目时附上解题思路要点",
            "first": "一面侧重：产品方法论、需求分析与优先级判断、基础数据分析（漏斗、留存、A/B 测试），以及简历项目 / 经历的初步深挖",
            "second": "二面侧重：产品方案设计（从需求洞察到上线验证的完整链路）、指标体系与数据驱动决策、竞品分析与差异化思考、复杂业务场景下的取舍",
            "third": "三面侧重：产品战略与规划、商业思维与商业模式、跨团队协作与资源推动、行业理解与视野、软素质",
            "comprehensive": "综合面侧重：不设固定侧重——产品基础、项目深挖、方案设计、场景开放题、职业规划与软素质都可能问到，考察整体素养与随机应变；提问自由度最大，按现场对话自然流动",
            "hr": "HR 面侧重：求职动机、离职原因、职业规划、稳定性、薪资沟通策略、软素质与价值观",
            "project": "项目经历面（专题）侧重：整场只围绕简历项目深挖——个人角色与实际贡献、需求背景与目标用户、方案取舍理由、数据表现与迭代过程、跨团队推动与上线结果、复盘与改进；不问与项目无关的方法论背诵 / 智力题",
            "stress": "压力面（专题）侧重：高压质询下的产品判断与项目——问题本身仍来自简历、项目与产品基础，但以质疑、否定、连环追问的施压方式提出（如「这功能上线后数据跌了你怎么解释」），考察情绪稳定性、抗压能力与临场反应",
            "other": "一般产品面试：基础与项目并重",
        },
        coach_role="资深产品经理面试教练",
        review_default="产品经理",
        question_tags="项目深挖/场景设计/产品方法论/需求分析/产品设计/数据分析/用户研究/竞品分析/商业思维/技术理解力/项目协作/软素质",
        dim_examples="需求分析 / 产品设计 / 项目深挖",
        typo_fixes="pm→PM（指产品经理时）、mrd→MRD、prd→PRD、ab测试→A/B 测试、b端→B 端、c端→C 端",
    ),
    _track(
        key="delivery",
        name="交付/实施",
        tagline="项目落地、部署实施与客户成功",
        dimensions=[
            "实施部署", "环境与运维基础", "数据库/SQL", "网络基础", "排障能力",
            "客户沟通", "项目管理", "文档与培训", "业务理解", "项目深挖", "场景设计", "软素质", "其他",
        ],
        groups=["交付基础", "项目深挖", "场景设计", "软素质", "反问建议"],
        round_emphasis={
            "written": "笔试侧重：SQL 与数据库基础、Linux 与网络基础、逻辑排查题，给出题目时附上解题思路要点",
            "first": "一面侧重：实施部署流程与环境配置、常见问题排查、SQL 与网络基础，以及简历项目的初步深挖",
            "second": "二面侧重：复杂环境交付方案（私有化部署、版本升级、数据迁移）、疑难故障定位思路、与研发 / 客户的协作机制、交付质量管理",
            "third": "三面侧重：大型项目交付管理（计划、风险、资源协调）、客户关系与期望管理、交付体系与流程建设、成本与效率、软素质",
            "comprehensive": "综合面侧重：不设固定侧重——交付基础、项目深挖、场景应对、职业规划与软素质都可能问到，考察整体素养与随机应变；提问自由度最大，按现场对话自然流动",
            "hr": "HR 面侧重：求职动机、离职原因、职业规划（含出差 / 驻场接受度）、稳定性、薪资沟通策略、软素质与价值观",
            "project": "项目经历面（专题）侧重：整场只围绕简历项目深挖——个人角色与实际贡献、交付方案与部署架构的取舍理由、难点攻关（疑难环境、数据迁移、故障处理）、客户协调与验收过程、量化结果与业务价值、复盘与改进；不问与项目无关的八股 / 原理 / 智力题",
            "stress": "压力面（专题）侧重：高压质询下的交付能力与项目——问题本身仍来自简历、项目与交付基础，但以质疑、否定、连环追问的施压方式提出（如「客户当场拒绝验收你怎么办」），考察情绪稳定性、抗压能力与临场反应",
            "other": "一般交付面试：基础与项目并重",
        },
        coach_role="资深交付项目经理面试教练",
        review_default="交付 / 实施工程师（项目经理方向）",
        question_tags="项目深挖/场景设计/实施部署/环境与运维基础/数据库与SQL/网络基础/排障能力/客户沟通/项目管理/文档与培训/业务理解/软素质",
        dim_examples="实施部署 / 排障能力 / 客户沟通",
        typo_fixes="mysql→MySQL、linux→Linux（指操作系统）、k8s→K8s、sql→SQL、uat→UAT、驻场→驻场（无错则保持）",
    ),
]

_TRACK_MAP = {t["key"]: t for t in BUILTIN_TRACKS}


def get_track(track_key: str | None) -> dict | None:
    if not track_key:
        return None
    return _TRACK_MAP.get(track_key)


def list_tracks() -> list[dict]:
    return BUILTIN_TRACKS


def get_current_track(session: Session) -> dict:
    """当前生效的方向档案；未设置或值失效时回退默认（Java 后端）。"""
    row = session.get(Setting, TRACK_KEY)
    current = row.value if row is not None else None
    return _TRACK_MAP.get(current) or _TRACK_MAP[DEFAULT_TRACK]


def set_current_track(session: Session, track_key: str) -> None:
    row = session.get(Setting, TRACK_KEY)
    if row is None:
        session.add(Setting(key=TRACK_KEY, value=track_key))
    else:
        row.value = track_key


EMPTY_PROFILE: dict = {
    "track_key": "",
    "years": None,
    "headline": "",
    "skills": [],
    "strengths": [],
    "gaps": [],
    "summary": "",
}


def get_profile(session: Session, user: User) -> dict:
    """读取某用户的职业画像；缺失或损坏时返回空画像结构。"""
    raw = (user.career_profile or "").strip()
    if not raw:
        return dict(EMPTY_PROFILE)
    try:
        data = json.loads(raw)
    except ValueError:
        return dict(EMPTY_PROFILE)
    if not isinstance(data, dict):
        return dict(EMPTY_PROFILE)
    profile = dict(EMPTY_PROFILE)
    profile.update(data)
    for k in ("skills", "strengths", "gaps"):
        if not isinstance(profile[k], list):
            profile[k] = []
    return profile


def set_profile(session: Session, user: User, profile: dict) -> None:
    user.career_profile = json.dumps(profile, ensure_ascii=False)
    session.add(user)


def get_custom_dimensions(session: Session) -> list[str]:
    """用户为交叉背景（如 后端+AI、测试+交付）自行追加的考察维度。"""
    row = session.get(Setting, CUSTOM_DIMS_KEY)
    if row is None or not row.value.strip():
        return []
    try:
        data = json.loads(row.value)
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    return [str(x).strip() for x in data if str(x).strip()][:50]


def set_custom_dimensions(session: Session, dims: list[str]) -> None:
    seen: list[str] = []
    for d in dims:
        d = str(d).strip()[:20]
        if d and d not in seen:
            seen.append(d)
    value = json.dumps(seen, ensure_ascii=False)
    row = session.get(Setting, CUSTOM_DIMS_KEY)
    if row is None:
        session.add(Setting(key=CUSTOM_DIMS_KEY, value=value))
    else:
        row.value = value


def dimension_presets(session: Session) -> list[str]:
    """当前方向的预设维度 + 用户自定义维度（自定义排后，不与预设重复）。"""
    base = get_current_track(session)["dimensions"]
    return base + [d for d in get_custom_dimensions(session) if d not in base]


def build_profile_text(session: Session, user: User) -> str:
    """把某用户的职业画像渲染成可注入 prompt 的文字块；空画像返回空串。

    画像是交叉背景（如 后端+AI、测试+交付）的唯一载体：主档案决定骨架，
    交叉的技能与侧重由画像补充，所有 AI 功能都应注入当前用户的画像。
    """
    p = get_profile(session, user)
    if not any((p.get("headline"), p.get("skills"), p.get("summary"), p.get("years"))):
        return ""
    lines = []
    if p.get("headline"):
        lines.append(f"一句话画像：{p['headline']}")
    if p.get("years"):
        lines.append(f"工作年限：{p['years']} 年")
    if p.get("skills"):
        lines.append(f"技能栈：{'、'.join(p['skills'])}")
    if p.get("strengths"):
        lines.append(f"优势：{'；'.join(p['strengths'])}")
    if p.get("gaps"):
        lines.append(f"短板：{'；'.join(p['gaps'])}")
    if p.get("summary"):
        lines.append(f"概述：{p['summary']}")
    return "\n".join(lines)
