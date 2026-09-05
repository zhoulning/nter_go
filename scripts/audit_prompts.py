"""改动前后 prompt 的逐字对比：以 admin 默认简历为输入，渲染新旧两版并 diff。

旧版 = 改造前工作区的模板（本次改造对 java-backend 档案的回退还原）：
  差异点仅四处 —— 教练人设(相同)、画像段(新增)、review_default 措辞(+或职业画像)、
  QUESTIONS_PROMPT 的 tag 举例(删「如 MySQL/Redis」)。
"""
import difflib
import sys

sys.path.insert(0, ".")

from sqlmodel import Session, select

from app.database import engine
from app.models import Resume, User
from app.routers.ai import ANSWER_STANDARD, ANSWER_EXPERIENCE_RULES, collect_answer_context, build_answer_prompt
from app.routers.resumes import QUESTIONS_PROMPT, REVIEW_PROMPT
from app.tracks import build_profile_text, get_current_track

with Session(engine) as s:
    admin = s.exec(select(User).where(User.username == "admin")).first()
    resume = s.exec(
        select(Resume)
        .where(Resume.user_id == admin.id)
        .order_by(Resume.is_default.desc(), Resume.created_at.desc())
    ).first()
    track = get_current_track(s)
    content = (resume.structured or resume.text or "")[:12000]
    background = resume.background or "（未提供）"
    profile_text = build_profile_text(s, admin) or "（未设置）"
    ctx = collect_answer_context(s, admin, kb_query="高并发")


def _strip(s: str) -> list[str]:
    return [ln for ln in s.splitlines() if ln.strip()]


def diff(name: str, old: str, new: str, show: bool = True) -> None:
    d = list(difflib.unified_diff(_strip(old), _strip(new), "改动前", "改动后", lineterm="", n=0))
    changed = [ln for ln in d if ln[:1] in "+-" and ln[:3] not in ("+++", "---")]
    print(f"\n===== {name}：{'无差异' if not changed else f'{len(changed)} 行差异'} =====")
    if show:
        for ln in d:
            if ln[:1] in "+-" and ln[:3] not in ("+++", "---"):
                print((ln[:150] + "…") if len(ln) > 150 else ln)


# ---------- 1. 答案生成 ----------
new_answer = build_answer_prompt(
    content="HashMap 在扩容时并发下会出现什么问题？",
    dimension="JUC",
    companies=["字节跳动"],
    ctx=ctx,
    coach_role=track["coach_role"],
)
old_answer = new_answer.replace(
    f"""我的职业画像（交叉技术背景与作答侧重参考它；为空则忽略本节）：
{ctx["profile_text"]}

""",
    "",
)
diff("答案生成 build_answer_prompt", old_answer, new_answer)

# ---------- 2. 简历体检 ----------
new_review = (
    REVIEW_PROMPT.replace("{content}", content)
    .replace("{background}", background)
    .replace("{review_default}", track["review_default"])
    .replace("{profile_block}", profile_text)
)
old_review = (
    new_review.replace("若求职者补充背景或职业画像中有说明", "若求职者补充背景中有说明")
    .replace(f"""求职者职业画像（评估口径的重要参考；为「（未设置）」则忽略本节）：
{profile_text}

""", "")
)
diff("简历体检 REVIEW_PROMPT", old_review, new_review)

# ---------- 3. 简历预测题 ----------
new_questions = (
    QUESTIONS_PROMPT.replace("{content}", content)
    .replace("{background}", background)
    .replace("{direction}", "（未指定，综合出题）")
    .replace("{question_tags}", track["question_tags"])
    .replace("{profile_block}", profile_text)
)
old_questions = (
    new_questions.replace(
        f"：{track['question_tags']}，纯技能八股优先用具体技术维度，匹配不上才用「其他」",
        f"：{track['question_tags']}，纯技能八股优先用具体技术维度（如 MySQL/Redis），匹配不上才用「其他」",
    )
    .replace(f"""求职者职业画像（交叉技术背景，出题与答案侧重参考它；为「（未设置）」则忽略本节）：
{profile_text}

""", "")
)
diff("简历预测题 QUESTIONS_PROMPT", old_questions, new_questions)

# ---------- 4. 模拟面试 TURN_PROMPT / 5. 复盘（模板层面差异） ----------
print("\n===== 模拟面试 / 复盘的模板层差异（与简历无关的部分）=====")
print("+ 新增画像段：【候选人职业画像】/【候选人职业画像】两处（同上，内容=画像文本）")
print("- TURN_PROMPT：追问规则删去举例「（如 Redis 持久化、索引为什么用 B+ 树）」")
print("- ANALYSIS_PROMPT：量化规则删去举例「（如 Redis 持久化、索引原理）」")
print("- 复盘 topic 示例：「如 项目深挖/MySQL/分布式/系统设计/软素质」→「尽量从这些里选：MySQL / 项目深挖 / 系统设计；都不合适可用其他具体维度」")
print("- 转写润色错别字示例：Java 档案逐字保留原 6 例（无变化）")
print("- JD 提取 / 简历结构化 / 转写切题 prompt：本次改造未触碰")
