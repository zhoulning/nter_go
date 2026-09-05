"""A/B 实测：以 admin 默认简历为输入，改动前后的提示词各跑一次真实 LLM 调用，对比输出。

对比三组：简历体检（评分）、简历预测题（出题）、单题答案生成。
「旧版提示词」= 本次改造前工作区模板在 java-backend 档案下的渲染结果（逐字还原）。
"""
import sys

sys.path.insert(0, ".")

from sqlmodel import Session, select

from app.database import engine
from app.models import Resume, User
from app.routers.ai import _call_llm, _parse_json_loose, build_answer_prompt, collect_answer_context
from app.routers.resumes import QUESTIONS_PROMPT, REVIEW_PROMPT
from app.routers.settings import get_ai_config
from app.tracks import build_profile_text, get_current_track

Q = "HashMap 在扩容时并发下会出现什么问题？"
DIM = "JUC"

with Session(engine) as s:
    admin = s.exec(select(User).where(User.username == "admin")).first()
    resume = s.exec(
        select(Resume)
        .where(Resume.user_id == admin.id)
        .order_by(Resume.is_default.desc(), Resume.created_at.desc())
    ).first()
    track = get_current_track(s)
    cfg = get_ai_config(s)
    assert cfg["api_key"], "未配置 AI Key"
    content = (resume.structured or resume.text or "")[:12000]
    background = resume.background or "（未提供）"
    profile_text = build_profile_text(s, admin) or "（未设置）"
    ctx = collect_answer_context(s, admin, kb_query=f"{Q} {DIM}")

    # ---- 渲染新版 ----
    new_review = (
        REVIEW_PROMPT.replace("{content}", content)
        .replace("{background}", background)
        .replace("{review_default}", track["review_default"])
        .replace("{profile_block}", profile_text)
    )
    new_questions = (
        QUESTIONS_PROMPT.replace("{content}", content)
        .replace("{background}", background)
        .replace("{direction}", "（未指定，综合出题）")
        .replace("{question_tags}", track["question_tags"])
        .replace("{profile_block}", profile_text)
    )
    new_answer = build_answer_prompt(content=Q, dimension=DIM, companies=["字节跳动"], ctx=ctx, coach_role=track["coach_role"])

    # ---- 渲染旧版（删除画像段、还原原措辞） ----
    profile_block_review = f"""求职者职业画像（评估口径的重要参考；为「（未设置）」则忽略本节）：
{profile_text}

"""
    profile_block_questions = f"""求职者职业画像（交叉技术背景，出题与答案侧重参考它；为「（未设置）」则忽略本节）：
{profile_text}

"""
    profile_block_answer = f"""我的职业画像（交叉技术背景与作答侧重参考它；为空则忽略本节）：
{ctx["profile_text"]}

"""
    old_review = new_review.replace(profile_block_review, "").replace(
        "若求职者补充背景或职业画像中有说明", "若求职者补充背景中有说明"
    )
    old_questions = new_questions.replace(profile_block_questions, "").replace(
        "纯技能八股优先用具体技术维度，匹配不上才用「其他」",
        "纯技能八股优先用具体技术维度（如 MySQL/Redis），匹配不上才用「其他」",
    )
    old_answer = new_answer.replace(profile_block_answer, "")

    def ask(name: str, prompt: str):
        print(f"\n>>> 调用：{name}（prompt {len(prompt)} 字符）…", flush=True)
        raw = _call_llm(cfg["base_url"], cfg["model"], cfg["api_key"], prompt)
        return raw

    # 1) 体检 A/B
    for tag, p in (("旧", old_review), ("新", new_review)):
        raw = ask(f"简历体检-{tag}", p)
        try:
            d = _parse_json_loose(raw)
            dims = d.get("dimensions", {})
            print(f"[体检-{tag}] score={d.get('score')} dims={dims} 建议{len(d.get('suggestions') or [])}条")
            for sug in (d.get("suggestions") or [])[:3]:
                print(f"    - {sug.get('title')}")
        except Exception as e:
            print(f"[体检-{tag}] 解析失败: {e}")

    # 2) 预测题 A/B
    for tag, p in (("旧", old_questions), ("新", new_questions)):
        raw = ask(f"简历预测题-{tag}", p)
        try:
            d = _parse_json_loose(raw)
            qs = d.get("questions") or []
            from collections import Counter
            tags = Counter(q.get("tag", "?") for q in qs)
            print(f"[预测题-{tag}] 共{len(qs)}题 tag分布={dict(tags)}")
            for q in qs[:4]:
                print(f"    - [{q.get('tag')}] {str(q.get('q'))[:46]}")
        except Exception as e:
            print(f"[预测题-{tag}] 解析失败: {e}")

    # 3) 答案生成 A/B
    for tag, p in (("旧", old_answer), ("新", new_answer)):
        raw = ask(f"答案生成-{tag}", p)
        text = raw.strip()
        print(f"[答案-{tag}] 长度={len(text)}字")
        print(f"    开头: {text[:120]}")
        hit = [k for k in ("网络控制器", "云网", "设备纳管", "千台", "1000+", "SDN") if k in text]
        print(f"    引用本人领域背景的关键词: {hit or '无'}")
