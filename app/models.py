"""核心数据模型。

第一版先建「岗位 + 面试轮次」两张表，支撑看板链路；
其余表（题库、简历、录音、复盘报告等）按里程碑逐步增加。
"""
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

# 岗位状态（看板列）。社招笔试场景少，不设独立状态，如遇笔试按轮次记录。
STATUS_WISHLIST = "wishlist"          # 想投
STATUS_APPLIED = "applied"            # 已投递
STATUS_INTERVIEWING = "interviewing"  # 面试中
STATUS_OFFER = "offer"                # Offer
STATUS_ACCEPTED = "accepted"          # 接受
ACTIVE_STATUSES = [
    STATUS_WISHLIST,
    STATUS_APPLIED,
    STATUS_INTERVIEWING,
    STATUS_OFFER,
    STATUS_ACCEPTED,
]
# 终态（归档视图）
STATUS_REJECTED = "rejected"          # 挂了
STATUS_NO_RESPONSE = "no_response"    # 无响应
STATUS_GIVE_UP = "give_up"            # 主动放弃
ARCHIVED_STATUSES = [STATUS_REJECTED, STATUS_NO_RESPONSE, STATUS_GIVE_UP]

# 面试轮次类型
ROUND_TYPES = ["written", "first", "second", "third", "comprehensive", "hr", "other"]

# 调研笔记类型（每个岗位下每种类型各一条）
NOTE_TYPES = ["company", "team", "tech", "self_intro", "ask_back", "employee"]

# 轮次结果
ROUND_PENDING = "pending"
ROUND_PASSED = "passed"
ROUND_FAILED = "failed"
ROUND_NO_SHOW = "no_show"

# 用户角色 / 账号状态
ROLE_ADMIN = "admin"        # 超级管理员：用户管理、系统设置
ROLE_USER = "user"
USER_ACTIVE = "active"      # 正常（审核通过）
USER_PENDING = "pending"    # 注册待审核
USER_REJECTED = "rejected"  # 注册被拒绝
USER_DISABLED = "disabled"  # 已禁用（数据保留，不可登录）

# 通知类型
NOTIF_ACCOUNT = "account"    # 账号事件（注册待审核 / 审核结果 / 禁用等）


class User(SQLModel, table=True):
    """登录账号。admin 为超级管理员，现有数据全部归属 admin。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str                # pbkdf2_sha256$iterations$salt$hash
    display_name: Optional[str] = None
    role: str = Field(default=ROLE_USER, index=True)
    status: str = Field(default=USER_PENDING, index=True)
    avatar_path: Optional[str] = None  # 头像图片（data/uploads/avatars/ 内路径）
    reject_reason: Optional[str] = None  # 注册拒绝原因（可空）
    career_profile: Optional[str] = None  # 职业画像 JSON（每位用户一份；设默认简历时自动重生成）
    created_at: datetime = Field(default_factory=datetime.now)
    approved_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class UserSession(SQLModel, table=True):
    """登录会话（HttpOnly Cookie 中存原始 token，库里只存 sha256）。"""

    token_hash: str = Field(primary_key=True)
    user_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime = Field(index=True)


class Notification(SQLModel, table=True):
    """站内通知（账号事件）。面试日程提醒按日历数据实时计算，不入库。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    type: str = Field(default=NOTIF_ACCOUNT, index=True)
    title: str
    body: Optional[str] = None
    read: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.now)


class AuditLog(SQLModel, table=True):
    """操作日志：登录认证、用户管理、系统配置变更等关键操作留痕。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)  # 操作人（登录失败等场景可为空）
    username: str = Field(default="", index=True)  # 操作人用户名快照（用户删除后日志仍可读）
    action: str = Field(index=True)    # 如 auth.login / user.disable / settings.ai
    target: Optional[str] = None       # 操作对象（如被操作的用户名 / 配置名）
    detail: Optional[str] = None       # 补充说明（如拒绝原因）
    ip: Optional[str] = None           # 操作来源 IP
    created_at: datetime = Field(default_factory=datetime.now, index=True)


class Opportunity(SQLModel, table=True):
    """一个岗位 = 一家公司的一个岗位。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    company: str = Field(index=True)
    position: str
    department: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None  # 工作地址（详细地址）
    salary_range: Optional[str] = None
    channel: Optional[str] = None  # 内推 / BOSS直聘 / 猎聘 / 官网 / 脉脉 / 其他
    priority: str = Field(default="B", index=True)  # S / A / B
    status: str = Field(default=STATUS_WISHLIST, index=True)
    status_changed_at: datetime = Field(default_factory=datetime.now)
    applied_at: Optional[datetime] = None  # 投递时间：进入「已投递」时自动记录，可手动调整
    resume_id: Optional[int] = Field(default=None, foreign_key="resume.id")  # 投递所用简历
    jd_text: Optional[str] = None            # 工作描述：JD 完整内容（职责、要求及其他）
    note: Optional[str] = None
    user_id: Optional[int] = Field(default=None, index=True)  # 归属用户
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class InterviewRound(SQLModel, table=True):
    """岗位下的一场面试事件（笔试/一面/二面…）。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: int = Field(foreign_key="opportunity.id", index=True)
    user_id: Optional[int] = Field(default=None, index=True)  # 归属用户（冗余，随岗位）
    round_type: str = "first"
    scheduled_at: Optional[datetime] = None  # 计划时间
    actual_at: Optional[datetime] = None     # 实际时间
    result: str = Field(default=ROUND_PENDING, index=True)
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class Setting(SQLModel, table=True):
    """KV 配置表（AI Key 等本机配置，仅存本地）。"""

    key: str = Field(primary_key=True)
    value: str = ""


class Question(SQLModel, table=True):
    """题库 / 错题本中的题目。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    content: str = Field(index=True)                       # 题干
    dimension: str = Field(default="其他", index=True)      # 考察维度
    difficulty: str = Field(default="medium", index=True)  # easy / medium / hard
    source: str = Field(default="manual", index=True)      # manual / real / predicted
    opportunity_id: Optional[int] = Field(
        default=None, foreign_key="opportunity.id", index=True
    )
    resume_id: Optional[int] = Field(
        default=None, foreign_key="resume.id"
    )  # 关联简历：这道题因哪版简历被问到
    my_answer: Optional[str] = None   # 我的回答要点
    answer_key: Optional[str] = None  # 参考答案要点
    answer_spoken: Optional[str] = None  # AI 生成：口述版答案（面试现场怎么说）
    answer_brief: Optional[str] = None   # AI 生成：简答版答案（要点速览）
    self_rating: Optional[int] = None  # 自我评分 1-5
    mastery: str = Field(default="unknown", index=True)  # unknown / fuzzy / mastered
    review_done: bool = Field(default=False)  # 错题本：已复习标记
    user_id: Optional[int] = Field(default=None, index=True)  # 归属用户
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class QuestionSource(SQLModel, table=True):
    """题目来源：一道题可能被多家公司的多场面试问到（多对多）。

    round_id 可空 —— 只记得是哪家公司、记不清具体轮次时允许只挂公司。
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    question_id: int = Field(foreign_key="question.id", index=True)
    opportunity_id: int = Field(foreign_key="opportunity.id", index=True)
    round_id: Optional[int] = Field(default=None, foreign_key="interviewround.id")
    user_id: Optional[int] = Field(default=None, index=True)  # 归属用户（冗余，随题目）
    created_at: datetime = Field(default_factory=datetime.now)


class Resume(SQLModel, table=True):
    """简历版本库。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)  # 归属用户
    name: str = Field(index=True)  # 版本名，如「Java 后端-v3-强调高并发」
    filename: str                  # 原始文件名
    filepath: str                  # 本地存储路径
    ext: str                       # 扩展名（.pdf/.docx/...）
    size: int = 0                  # 字节数
    text: Optional[str] = None     # 抽取的纯文本（机器抽取原文，顺序可能错乱）
    structured: Optional[str] = None  # AI 整理后的结构化简历（5 大板块 Markdown）
    background: Optional[str] = None  # 求职者补充背景（目标方向/诉求/特殊情况），AI 体检与出题的重要依据
    score: Optional[int] = None    # AI 简历体检得分 0-100
    review_json: Optional[str] = None     # 优化建议 JSON：{"suggestions":[{title,detail,level}]}
    questions_json: Optional[str] = None  # 预测面试题 JSON：{"questions":[{tag,q,a}]}
    questions_direction: Optional[str] = None  # 最近一次生成预测题时指定的出题方向（空为综合出题）
    is_default: bool = Field(default=False, index=True)  # 默认简历（新投递自动选用）
    archived: bool = Field(default=False, index=True)  # 归档：不再出现在选择器中，但历史引用保留
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class Offer(SQLModel, table=True):
    """Offer 信息与主观评分（每个岗位最多一条）。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: int = Field(foreign_key="opportunity.id", unique=True, index=True)
    user_id: Optional[int] = Field(default=None, index=True)  # 归属用户（冗余，随岗位）
    # 薪资结构
    monthly_salary: Optional[float] = None  # 月薪（K）
    months: Optional[int] = None            # 薪资月数（如 15薪）
    signing_bonus: Optional[str] = None     # 签字费 / 奖金
    stock: Optional[str] = None             # 股票 / 期权
    welfare: Optional[str] = None           # 公积金 / 福利
    # 工作体验
    overtime: Optional[str] = None          # 加班情况（如 大小周 / 965）
    commute: Optional[str] = None           # 通勤情况
    # 主观评分 1-5
    score_salary: int = 3   # 薪资待遇
    score_platform: int = 3  # 平台规模
    score_growth: int = 3   # 成长空间
    score_worklife: int = 3  # 工作生活平衡
    score_commute: int = 3  # 通勤便利
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class Recording(SQLModel, table=True):
    """面试录音（关联岗位与轮次），含转写状态。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: int = Field(foreign_key="opportunity.id", index=True)
    round_id: Optional[int] = Field(default=None, foreign_key="interviewround.id", index=True)
    user_id: Optional[int] = Field(default=None, index=True)  # 归属用户
    kind: str = Field(default="recording", index=True)  # recording=录音复盘 / text=文字复盘
    filename: str                 # 原始文件名（文字复盘为标题）
    filepath: str                 # data/uploads/recordings/ 内路径
    ext: str                      # 扩展名
    size: int = 0
    duration_sec: Optional[float] = None
    transcript: Optional[str] = None           # 文字稿（带 [MM:SS] 时间戳）
    transcript_clean: Optional[str] = None     # AI 矫正稿（去口语化/修正技术名词/标注角色）
    polished_at: Optional[datetime] = None     # 矫正稿生成时间
    polish_status: str = Field(default="none", index=True)  # none/running/done/failed
    polish_error: Optional[str] = None
    transcript_engine: Optional[str] = None    # whisper-small / cloud:<model> / manual
    status: str = Field(default="uploaded", index=True)  # uploaded/transcribing/transcribed/failed
    progress: int = 0                          # 转写进度 0-100
    error: Optional[str] = None
    review_status: str = Field(default="none", index=True)  # none/running/done/failed
    review_error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)


class ReviewReport(SQLModel, table=True):
    """AI 复盘报告（每个录音一份，重新生成即覆盖）。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    recording_id: int = Field(foreign_key="recording.id", unique=True, index=True)
    user_id: Optional[int] = Field(default=None, index=True)  # 归属用户（冗余，随录音）
    model: str                     # 生成使用的模型
    resume_id: Optional[int] = None
    report: str                    # 结构化报告 JSON
    overall_score: int = 0         # 总评 0-100
    question_count: int = 0
    created_at: datetime = Field(default_factory=datetime.now)


class ResearchNote(SQLModel, table=True):
    """岗位下的调研笔记（Markdown）。每个 (opportunity_id, note_type) 一条。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: int = Field(foreign_key="opportunity.id", index=True)
    user_id: Optional[int] = Field(default=None, index=True)  # 归属用户（冗余，随岗位）
    note_type: str = Field(default="company", index=True)  # 见 NOTE_TYPES
    content: str = ""                  # Markdown 正文
    ai_generated: bool = Field(default=False)  # 当前内容是否来自 AI 提纲（供界面标注）
    updated_at: datetime = Field(default_factory=datetime.now)


class MatchReport(SQLModel, table=True):
    """岗位匹配度报告（每个岗位一份，重新生成即覆盖）。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: int = Field(foreign_key="opportunity.id", unique=True, index=True)
    user_id: Optional[int] = Field(default=None, index=True)  # 归属用户（冗余，随岗位）
    resume_id: Optional[int] = Field(default=None, foreign_key="resume.id")  # 评估所用简历
    model: str                     # 生成使用的模型
    report: str                    # 结构化报告 JSON
    total_score: int = 0           # 匹配总分 0-100
    created_at: datetime = Field(default_factory=datetime.now)


class ResearchMaterial(SQLModel, table=True):
    """岗位情报的参考材料（抓取的网页 / 手动粘贴），AI 生成情报时作为事实来源。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: int = Field(foreign_key="opportunity.id", index=True)
    user_id: Optional[int] = Field(default=None, index=True)  # 归属用户（冗余，随岗位）
    source_type: str = "url"       # url: 直抓 / browser: CDP 浏览器抓取 / manual: 手动粘贴
    title: str = ""                # 页面标题或用户命名
    url: Optional[str] = None
    content: str = ""              # 正文文本（截断存储）
    created_at: datetime = Field(default_factory=datetime.now)


class Prediction(SQLModel, table=True):
    """AI 题目预测题单（每个岗位 × 每个目标轮次一份，重新生成即覆盖）。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: int = Field(foreign_key="opportunity.id", index=True)
    user_id: Optional[int] = Field(default=None, index=True)  # 归属用户（冗余，随岗位）
    round_type: str = Field(default="first", index=True)  # 目标轮次，见 ROUND_TYPES
    model: str                     # 生成使用的模型
    report: str                    # 结构化题单 JSON
    question_count: int = 0
    created_at: datetime = Field(default_factory=datetime.now)


class MockInterview(SQLModel, table=True):
    """模拟面试会话：AI 面试官与候选人的对话记录 + 结束后的分析报告。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    opportunity_id: int = Field(foreign_key="opportunity.id", index=True)
    user_id: Optional[int] = Field(default=None, index=True)  # 归属用户
    round_type: str = "first"
    model: str = ""
    status: str = Field(default="ongoing", index=True)  # ongoing / finished
    transcript: str = "[]"         # 对话记录 JSON：[{role, content, action, dimension}]
    analysis: Optional[str] = None  # 分析报告 JSON
    overall_score: int = 0
    created_at: datetime = Field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
