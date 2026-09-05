"""职业方向档案（Track Profile）。

系统默认面向 Java 后端；每个方向档案自带一套「考察维度、题单分组、轮次侧重、
AI 人设与评分口径」配置。当前方向全局唯一（存 Setting.career_track），
切换后所有 AI 出题/答案/体检/复盘的 prompt 与题库维度预设置随之切换。
内置档案在代码中只读维护，不新增数据表；复用 Setting 键值存储。
"""
import json

from sqlmodel import Session

from app.models import Setting

TRACK_KEY = "career_track"      # 当前职业方向（Setting 键，值为档案 key）
PROFILE_KEY = "career_profile"  # 职业画像（Setting 键，值为 JSON 字符串）
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
        review_default="目标岗位默认为 Java 后端/服务端开发",
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
        review_default="目标岗位默认为 Go 后端/服务端开发",
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
        review_default="目标岗位默认为 Web 前端开发",
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
        review_default="目标岗位默认为测试开发 / 质量保障（QA）",
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
        review_default="目标岗位默认为算法工程师（机器学习/深度学习方向）",
        question_tags="论文与项目深挖/场景设计/系统设计/机器学习基础/深度学习/NLP/CV/推荐与搜广推/大模型/数学基础/代码与数据结构/软素质",
        dim_examples="深度学习 / 论文与项目深挖 / 大模型",
        typo_fixes="pytorch→PyTorch、tensorflow→TensorFlow、transformer→Transformer、过拟合→过拟合（无错则保持）、bb→Bleu（按上下文）",
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


def get_profile(session: Session) -> dict:
    """读取职业画像；缺失或损坏时返回空画像结构。"""
    row = session.get(Setting, PROFILE_KEY)
    if row is None or not row.value.strip():
        return dict(EMPTY_PROFILE)
    try:
        data = json.loads(row.value)
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


def set_profile(session: Session, profile: dict) -> None:
    value = json.dumps(profile, ensure_ascii=False)
    row = session.get(Setting, PROFILE_KEY)
    if row is None:
        session.add(Setting(key=PROFILE_KEY, value=value))
    else:
        row.value = value


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


def build_profile_text(session: Session) -> str:
    """把职业画像渲染成可注入 prompt 的文字块；空画像返回空串。

    画像是交叉背景（如 后端+AI、测试+交付）的唯一载体：主档案决定骨架，
    交叉的技能与侧重由画像补充，所有 AI 功能都应注入该文本。
    """
    p = get_profile(session)
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
