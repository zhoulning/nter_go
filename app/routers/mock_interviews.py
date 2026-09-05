"""模拟面试：AI 面试官对话式提问（支持追问），结束后生成整体分析。

会话与对话记录、分析报告全部入库，可随时回看。
"""
import json
import random
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session
from app.models import MatchReport, MockInterview, Opportunity, Prediction, Resume, User
from app.routers.ai import (
    ANSWER_EXPERIENCE_RULES,
    ANSWER_STANDARD,
    _call_llm,
    _parse_json_loose,
)
from app.routers.predictions import ROUND_LABELS
from app.kb import search_knowledge_base
from app.routers.settings import get_ai_config
from app.tracks import build_profile_text, get_current_track

router = APIRouter()

TURN_PROMPT = """你正在扮演 {company} 的技术面试官（{round_label}），对候选人进行真实感很强的模拟面试。
你的提问风格：专业、口语化、有压迫感但不失礼貌，像真实面试一样逐步深挖。

【岗位】{position}
【城市 / 薪资范围】{city} · {salary_range}
【JD 要点】
{jd}

【候选人职业画像】（交叉技术背景，提问侧重参考它；为「（未设置）」则忽略本节）
{profile_block}

【候选人简历摘要】
{resume}

【知识库笔记】（候选人自己的复习笔记，按本场题目检索）
{kb}

【本轮面试侧重】
{round_emphasis}
{topic_block}
【本轮候选题库（顺序已打乱，仅供选题参考，禁止按列表顺序机械推进）】
{question_pool}

【目前对话记录】
{transcript}

目前状态：已向候选人提出 {asked} 个问题（追问不算新问题）。

请基于候选人上一条回答，决定你的下一个动作并输出 JSON（不要输出任何其他内容）：
{{
  "message": "面试官的口语化发言。对上一个回答简短点评一句（如「嗯，了解」/「这个说法有点问题」），然后：追问时提出追问问题；next 时自然过渡并抛出下一个新问题；finish 时做收尾致谢。",
  "action": "followup|next|finish",
  "dimension": "当前问题所属维度（如 {dim_examples}）"
}}

规则：
- 判断标准：上一条回答有明显含糊、矛盾或值得深挖的点 → followup 追问（每个问题最多追问 1 次，不要连环追问）；回答完整或无需深挖 → next 进入题库下一个问题。
- 量化结果的追问只适用于项目 / 场景 / 系统设计类回答：候选人主动提到数据可顺势问一句来由。纯八股 / 原理 / 对比类问题答到点上即算完整，不要追问「放到你的项目里效果如何 / 有没有量化指标」——不是每个知识点都能落到候选人的项目上，硬要数字既不真实也无必要；这类题值得深挖时优先问原理与机制本身（底层实现、边界条件、方案取舍）。
- 已提问数达到 {target} 题且当前无必须追问的点 → finish 收尾。
- 一次只问一个问题，禁止一次抛出多个问题；message 中不要出现 JSON 或括号标记。
- 候选人明确表示不知道 / 要求跳过 → 简单带过并 next；候选人要求结束面试 → finish。
- 选题规则：进入新问题时，从候选题库中挑一个尚未问过、且考察维度与上一题不同的题目；八股 / 项目深挖 / 场景设计等大类要穿插进行，不要连续多题同属一类，更不要按简历章节或题库列表的顺序推进。
- 项目深挖采用开放式提问：不必念题库原题，围绕简历中的任意项目自由切入（如个人贡献最大的点、最难的一次故障、如果重来会改哪个设计、两个方案的取舍对比），追问链根据候选人回答动态生成。
- 候选人的回答很可能来自语音转文字，会混入同音字 / 术语错写（如「瑞迪斯」=Redis、「米等」=幂等、「锁」/「落」不分）：按上下文推断其本意来理解即可，不要纠缠错别字，更不要因转写错误而降分或反复追问文字问题。
- 难度校准：先判断目标公司在业界的面试难度层级（大厂 / 知名独角兽标准更高，中小厂相对宽松），再结合所在城市的竞争烈度与薪资 / 年限对应的职级期望，决定提问与追问的深度——公司标准越高、城市竞争越激烈、薪资越高年限越长，越应追问原理与线上实战；反之以基础为主，避免超纲。"""

OPENING_HINT = "这是面试的开场：先用一句话欢迎候选人并做简短自我介绍（不透露名字，只说角色），然后抛出题库中的第一个问题。action 用 next。"

# 模拟面试专属专题（不是真实面试轮次）：按轮次注入面试官的专题规则
TOPIC_RULES = {
    "project": (
        "【专题规则】本场是「项目经历面」专题：整场只围绕候选人简历上的项目经历展开，"
        "所有新问题都必须从项目切入（个人贡献与实际角色、为什么这么设计、技术选型与方案的取舍、"
        "难点攻关与故障排查、量化结果与业务价值、复盘与改进），禁止提问与项目无关的八股 / 原理 / 智力题；"
        "每题都要顺着候选人的回答继续往深处挖（追问上限放宽为每题 2 次）。"
    ),
    "stress": (
        "【专题规则】本场是「压力面」专题：面试官会刻意施压——频繁否定与质疑候选人的回答"
        "（如「我不认同」「这个方案线上根本扛不住」「你没答到点上」）、"
        "抓住回答中的漏洞与矛盾连续追问、用不耐烦的语气要求给出更好的答案；"
        "候选人答得对也不要立刻肯定，先质疑再勉强认可；施压只针对回答内容本身，保持职业底线，"
        "不嘲讽候选人个人、不进行人身攻击；本场目的在于观察候选人的情绪稳定性与临场反应。"
    ),
}


def _topic_block(round_type: str) -> str:
    rule = TOPIC_RULES.get(round_type)
    # 前后各留一个空行，与模板中的其他区块分隔；普通轮次返回空串
    return ("\n" + rule + "\n") if rule else ""

ANALYSIS_PROMPT = """你是一位面试辅导专家。以下是一场模拟面试的完整对话记录（role: interviewer 是面试官，candidate 是候选人）。
请对候选人的表现做逐题复盘分析。

【评分背景校准】
- 目标公司 / 岗位：{company} · {position}
- 城市 / 薪资范围：{city} · {salary_range}
- 候选人工作年限：{years_hint}
- 本场面试类型：{round_label}{round_note}
- 评分基准必须与公司层级、城市与薪资 / 职级的市场期望匹配：先判断该公司在业界的面试难度（大厂 / 知名独角兽更严，中小厂相对宽松）与所在城市的竞争烈度——同样的回答，对标高难度公司或高薪资深岗应更严格（原理理解、实战深度都要看），对标初级岗或难度较低的团队可适当放宽。

【目标岗位 JD】（点评与示范答案需贴合岗位要求的技术栈与业务场景）
{jd}

【候选人职业画像】（交叉技术背景，点评与示范答案侧重参考它；为「（未设置）」则忽略本节）
{profile_block}

【候选人简历摘要】
{resume}

【知识库笔记】（候选人自己的复习笔记，按本场题目检索）
{kb}

【语音转写说明】候选人的回答很可能经语音转文字产生，会混入同音字 / 术语错写（如「瑞迪斯」=Redis、「米等」=幂等、「索印」=索引）。凡能从上下文推断出原意的错写，不算知识缺陷：按其想表达的实际内容评估，不扣「表达」分，也不在 bad 中提及错别字本身；仅当错误与转写无关、属于真实概念混淆或逻辑混乱时才扣分。

【对话记录】
{transcript}

请输出 JSON（不要输出任何其他内容）：
{{
  "overall": {{ "score": 0-100 整数, "summary": "整体表现两三句总评" }},
  "questions": [
    {{
      "question": "面试官问的问题",
      "my_answer": "候选人回答的要点摘述（一到两句）",
      "scores": {{ "structure": 1-5, "depth": 1-5, "clarity": 1-5 }},
      "good": ["回答中的亮点"],
      "bad": ["回答中的问题（如概念性错误、被追问时绕开、逻辑混乱）；「缺量化结果」只对项目 / 场景 / 案例类题目成立，纯八股 / 原理题不因没结合项目或没有数字而记 bad"],
      "reference": ["参考答题要点，逐条给出：数组每个元素是一个独立要点（一句话），不要把所有要点挤成一段"],
      "model_answer": "完整口述版示范答案（要求见下方 model_answer 规则）"
    }}
  ],
  "weak_dimensions": ["暴露薄弱的维度"],
  "action_items": ["下一场面试前要补的具体事项 3-5 条"],
  "questions_for_bank": [ {{ "content": "值得入题库的原题", "dimension": "维度", "difficulty": "easy|medium|hard" }} ]
}}

【单题评分细则】structure / depth / clarity 各 1-5 分，5 分指「优秀」而非「完美无瑕」：
- structure：5=有清晰框架（先分类再展开、有方法论）；4=大体有条理、局部松散；3=内容基本正确但想到哪说到哪；2=只有零散要点；1=答非所问或自相矛盾。
- depth：5=覆盖原理 / 机制 / 边界条件，有真实案例或参数级细节支撑；4=主体正确且至少一处有深入；3=表面正确、停在概念层；2=只有关键词级碎片；1=核心概念错误。
- clarity：5=表述精准、可直接当标准答案复述；4=偶有不严谨；3=意思能懂但含糊 / 绕；2=多处含糊或用词错误；1=混乱到难以理解。

【总分推导规则】先算后调，禁止凭整体印象直接给分：
1. 每道已回答的题折算百分制：(structure + depth + clarity - 3) ÷ 12 × 100；
2. 基础分 = 所有已回答题目折算分的平均（跳过 / 未回答的题不参与平均、不扣分）；
3. 在基础分上允许 ±5 内的整体微调（依据：被追问时的表现、整体流畅度、目标公司的难度校准），调整理由必须写进 summary；微调超过 ±5 视为违规。
量化结果只对项目 / 场景 / 系统设计类题目有要求：给出了量化数字是加分项。纯八股 / 原理题答到点上即为完整，不要因「没结合项目 / 没有量化指标」扣分或写进 bad——不是每个知识点都能落到候选人的项目里。

【分数含义：对标该公司的通过线】总分表示「以这个表现，该公司该轮面试能否通过」，不是答题质量的百分比：
- 95+ 远超该轮通过线，表现出色；85-94 稳过该轮——回答达到该公司该轮面试官的期望就应落在这个区间，不要舍不得给分；70-84 存疑过线，有明显短板；55-69 大概率挂，硬伤多处；55 以下明显不达标。
- 禁止分数聚堆：不得把所有正常发挥的场次都压进 70-89；对比对象是该公司该轮次的真实要求，与「还有进步空间」之类的自我要求无关。
questions 必须逐题收录面试官提出的所有主要问题（追问合并进主问题即可），任何情况下不允许返回空数组或漏题——这是逐题复盘的核心字段。
每道已回答的题都必须给出 good 与 bad：bad 至少 1 条具体、可改进的点（确实无懈可击时可例外），不要把所有问题只写进总评而不落到对应题目上。

两类特殊情况必须正确处理：
1. 候选人消息带「（这题我不太熟，先跳过…）」或明确表示不会：该题记 "skipped": true，scores 置 null，my_answer 写「主动跳过」，good/bad 置空数组；
2. 对话结束时面试官已提问但候选人尚未作答：该题同样记 "skipped": true，scores 置 null，my_answer 写「未回答（面试在此结束）」，good/bad 置空数组。
skipped 的题不提供 good/bad，可以给 reference；overall 的总分只基于已回答的题目评定，跳过或未回答的题不扣分。

model_answer 是给考后背诵用的**完整口述版示范答案**，每题都必须给出（跳过 / 未回答的题尤其要给，这是考后补课材料）。格式与经历边界遵守全站统一的题库答案标准：
【格式标准】
{answer_standard}
【经历边界】
{experience_rules}
复盘专属补充：
- **排版硬性要求：结论句单独一行；每个编号要点独占一行（编号前必须换行）——绝不允许把所有要点挤在一段里**；
- 项目 / 场景 / 案例类题目：对话中候选人提到的真实项目与数据直接沿用，写出比候选人当时回答更完整的版本；缺实际案例时构造一个贴合 JD 与简历的示例案例，并在案例处明确标注「（示例案例）」；要点本身含通用数值结论（如 InnoDB 页大小 16KB）可正常写出；
- 「知识库笔记」是候选人自己的复习笔记，可信度高：其中与某题直接相关的要点**必须优先融入**该题的 model_answer，并在该题 model_answer 末尾单独一行标注「参考：〈来源标题〉」（多篇用顿号分隔）；只有与题目明显无关时才不标注。"""


class MockCreateRequest(BaseModel):
    round_type: str = "first"


class MockReplyRequest(BaseModel):
    content: str = ""
    kind: str = "answer"  # answer: 正常回答 / skip: 主动跳过本题


def _get_opportunity(session: Session, opportunity_id: int, user: User) -> Opportunity:
    """取当前用户的岗位；不存在或越权一律 404。"""
    opp = session.get(Opportunity, opportunity_id)
    if opp is None or opp.user_id != user.id:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return opp


def _interview_dict(row: MockInterview) -> dict:
    try:
        transcript = json.loads(row.transcript) if row.transcript else []
    except ValueError:
        transcript = []
    analysis = None
    if row.analysis:
        try:
            analysis = json.loads(row.analysis)
        except ValueError:
            analysis = None
    return {
        "id": row.id,
        "opportunity_id": row.opportunity_id,
        "round_type": row.round_type,
        "model": row.model,
        "status": row.status,
        "transcript": transcript,
        "analysis": analysis,
        "overall_score": row.overall_score,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


def _question_pool(session: Session, opportunity_id: int, round_type: str) -> str:
    """优先使用题目预测的题单作为本轮候选题库（顺序打乱）；没有则提示 AI 自行根据 JD 出题。"""
    pred = session.exec(
        select(Prediction).where(
            Prediction.opportunity_id == opportunity_id,
            Prediction.round_type == round_type,
        )
    ).first()
    if pred is not None:
        try:
            data = json.loads(pred.report)
            lines = [
                f"- [{q.get('group', '')}·{q.get('dimension', '')}] {q.get('q', '')}"
                for q in data.get("questions", [])[:16]
                if q.get("group") != "反问建议"
            ]
            random.shuffle(lines)
            if lines:
                head = "（以下只是候选池，顺序随机，不代表提问顺序）"
                return head + chr(10) + chr(10).join(lines)
        except (ValueError, TypeError):
            pass
    return (
        "（未生成预测题单，请自行拟定 5-8 个候选问题：结合 JD 与简历自由设计，"
        "不要按简历章节顺序组织，项目题保持开放式切入）"
    )

def _interviewer_turn(
    session: Session,
    interview: MockInterview,
    opp: Opportunity,
    opening_hint: str | None,
) -> dict:
    cfg = get_ai_config(session)
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI，请先在「设置」中填写 API Key")
    resume = session.get(Resume, opp.resume_id) if opp.resume_id else None
    resume_text = (resume.structured or resume.text or "（未提供简历）")[:4000] if resume else "（未提供简历）"
    match = session.exec(
        select(MatchReport).where(MatchReport.opportunity_id == opp.id)
    ).first()

    try:
        transcript = json.loads(interview.transcript)
    except ValueError:
        transcript = []

    # 将匹配度缺口作为面试官重点关注方向
    focus_hint = ""
    if match is not None:
        try:
            md = json.loads(match.report)
            gaps = [i["requirement"] for i in md.get("items", []) if i.get("verdict") == "missing"]
            if gaps:
                focus_hint = f"\n候选人简历中的明显缺口（可在追问中适当试探）：{'；'.join(gaps[:4])}"
        except (ValueError, TypeError):
            pass

    asked = sum(1 for t in transcript if t.get("role") == "interviewer" and t.get("action") in (None, "next"))
    if interview.round_type == "hr":
        target = 4
    elif interview.round_type in ("project", "stress"):
        target = 5  # 专题场次题量少但每题挖得更深
    else:
        target = 6

    transcript_text = chr(10).join(
        (
            ("面试官[" + t["dimension"] + "]" if t.get("dimension") else "面试官")
            + "：" + t.get("content", "")[:1500]
            if t.get("role") == "interviewer"
            else "候选人：" + t.get("content", "")[:1500]
        )
        for t in transcript
    )[-16000:] or "（还没有对话）"

    # 知识库检索：按已问问题 + 岗位关键词检索，失败不阻塞
    try:
        kb_query = " ".join(
            t.get("content", "")[:80] for t in transcript if t.get("role") == "interviewer"
        )
        kb_hits = search_knowledge_base(session, f"{kb_query} {opp.company} {opp.position}")
    except Exception:
        kb_hits = []
    if kb_hits:
        kb_text = chr(10).join(f"[{i}] 来源 {h['source']}" + chr(10) + f"{h['text']}" for i, h in enumerate(kb_hits, 1))
        kb_text = kb_text[:3000]
    else:
        kb_text = "（未配置知识库或未检索到相关笔记，忽略本节，也不要标注「参考」）"

    track = get_current_track(session)
    owner = session.get(User, interview.user_id) if interview.user_id else None
    prompt = TURN_PROMPT.format(
        company=opp.company,
        round_label=ROUND_LABELS.get(interview.round_type, "面试"),
        round_emphasis=track["round_emphasis"].get(interview.round_type)
        or track["round_emphasis"]["other"],
        topic_block=_topic_block(interview.round_type),
        profile_block=(build_profile_text(session, owner) if owner else "") or "（未设置）",
        dim_examples=track["dim_examples"],
        position=opp.position,
        city=opp.city or "未填写",
        salary_range=opp.salary_range or "未填写",
        jd=(opp.jd_text or "（未提供 JD）")[:4000],
        resume=resume_text,
        kb=kb_text,
        question_pool=_question_pool(session, opp.id, interview.round_type) + focus_hint,
        transcript=transcript_text,
        asked=asked,
        target=target,
    )
    if opening_hint:
        prompt += f"\n\n当前状态：{opening_hint}"

    raw = _call_llm(cfg["base_url"], cfg["model"], cfg["api_key"], prompt, max_tokens=2048)
    try:
        turn = _parse_json_loose(raw)
    except ValueError:
        raise HTTPException(status_code=502, detail=f"AI 返回内容无法解析：{raw[:200]}")

    action = turn.get("action") if turn.get("action") in ("followup", "next", "finish") else "next"
    message = str(turn.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=502, detail="AI 未返回面试官发言，请重试")
    return {
        "role": "interviewer",
        "content": message,
        "action": action,
        "dimension": str(turn.get("dimension") or "")[:20] or None,
    }


@router.get("/opportunities/{opportunity_id}/mock-interviews")
def list_mock_interviews(
    opportunity_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _get_opportunity(session, opportunity_id, user)
    rows = session.exec(
        select(MockInterview)
        .where(MockInterview.opportunity_id == opportunity_id)
        .order_by(MockInterview.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    return {"items": [_interview_dict(r) for r in rows]}


@router.post("/opportunities/{opportunity_id}/mock-interviews")
def create_mock_interview(
    opportunity_id: int,
    body: MockCreateRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    opp = _get_opportunity(session, opportunity_id, user)
    if body.round_type not in ROUND_LABELS:
        raise HTTPException(status_code=400, detail="未知的目标轮次")

    cfg = get_ai_config(session)
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI，请先在「设置」中填写 API Key")

    interview = MockInterview(
        opportunity_id=opportunity_id,
        round_type=body.round_type,
        model=cfg["model"],
        transcript="[]",
        user_id=user.id,
    )
    session.add(interview)
    session.commit()
    session.refresh(interview)

    # 生成开场 + 第一个问题
    turn = _interviewer_turn(session, interview, opp, OPENING_HINT)
    interview.transcript = json.dumps([turn], ensure_ascii=False)
    session.add(interview)
    session.commit()
    session.refresh(interview)
    return _interview_dict(interview)


@router.post("/mock-interviews/{interview_id}/reply")
def reply_mock_interview(
    interview_id: int,
    body: MockReplyRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    interview = session.get(MockInterview, interview_id)
    if interview is None or interview.user_id != user.id:
        raise HTTPException(status_code=404, detail="模拟面试会话不存在")
    if interview.status != "ongoing":
        raise HTTPException(status_code=400, detail="该场模拟面试已结束")
    if body.kind not in ("answer", "skip"):
        raise HTTPException(status_code=400, detail="未知操作类型")
    content = body.content.strip()
    if body.kind == "answer" and not content:
        raise HTTPException(status_code=400, detail="回答内容不能为空")
    opp = _get_opportunity(session, interview.opportunity_id, user)

    try:
        transcript = json.loads(interview.transcript)
    except ValueError:
        transcript = []
    if body.kind == "skip":
        transcript.append({
            "role": "candidate",
            "content": SKIP_CANNED_REPLY,
            "action": "skip",
            "dimension": None,
        })
        interview.transcript = json.dumps(transcript, ensure_ascii=False)
        hint = "候选人刚才主动跳过了当前问题。请简单带过（不要批评），然后进入题库中的下一个新问题，action 用 next；题库已问完则 finish 收尾。"
    else:
        transcript.append({"role": "candidate", "content": content, "action": None, "dimension": None})
        interview.transcript = json.dumps(transcript, ensure_ascii=False)
        hint = None

    turn = _interviewer_turn(session, interview, opp, hint)
    transcript.append(turn)
    interview.transcript = json.dumps(transcript, ensure_ascii=False)
    if turn["action"] == "finish":
        interview.status = "finished"
        interview.finished_at = datetime.now()
    session.add(interview)
    session.commit()
    session.refresh(interview)
    return _interview_dict(interview)


def _normalize_reference(raw) -> list[str]:
    """参考要点统一为数组；兼容旧数据的字符串形式（按换行拆分）。"""
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        return [line.strip() for line in raw.split(chr(10)) if line.strip()]
    return []


def _clamp5(v):
    try:
        return max(1, min(5, int(v)))
    except (TypeError, ValueError):
        return 3


SKIP_CANNED_REPLY = "（这题我不太熟，先跳过，我们看下一个问题吧）"


def _group_candidate_answers(transcript: list) -> list[str]:
    """把对话中候选人的原始回答按题分组：next/首问开启新题，追问的补充回答并入同一题。

    返回的顺序与逐题复盘的题目顺序一致；跳过题的分组内容是固定的跳过话术。
    """
    groups: list[list[str]] = []
    current: list[str] | None = None
    for turn in transcript:
        if turn.get("role") == "interviewer":
            if turn.get("action") in (None, "next") or current is None:
                current = []
                groups.append(current)
        else:
            content = (turn.get("content") or "").strip()
            if not content:
                continue
            if current is None:
                current = []
                groups.append(current)
            current.append(content)
    return ["\n\n".join(g) for g in groups if g]


def _normalize_analysis(data: dict) -> dict:
    """把 AI 返回的分析 JSON 规范化为稳定结构。"""
    def _parse_scores(raw):
        # 跳过 / 未回答的题 AI 会置 scores 为 null，不参与评分
        if not isinstance(raw, dict):
            return None
        return {
            "structure": _clamp5(raw.get("structure")),
            "depth": _clamp5(raw.get("depth")),
            "clarity": _clamp5(raw.get("clarity")),
        }

    overall = data.get("overall") if isinstance(data.get("overall"), dict) else {}
    try:
        score = max(0, min(100, int(overall.get("score") or 0)))
    except (TypeError, ValueError):
        score = 0
    questions = [
        {
            "question": str(q.get("question") or ""),
            "my_answer": str(q.get("my_answer") or ""),
            "skipped": bool(q.get("skipped")) or q.get("scores") is None,
            "scores": _parse_scores(q.get("scores")),
            "good": [str(x) for x in (q.get("good") or [])],
            "bad": [str(x) for x in (q.get("bad") or [])],
            "reference": _normalize_reference(q.get("reference")),
            "model_answer": str(q.get("model_answer") or ""),
            "my_answer_full": "",
        }
        for q in (data.get("questions") or [])
        if isinstance(q, dict) and q.get("question")
    ]
    # 总分推导（Prompt「先算后调」规则的服务端强制版）：
    # 基础分 = 已回答题目 (三维和-3)/12 的平均；模型给的总分只允许在基础分 ±5 内微调
    answered = [q["scores"] for q in questions if not q["skipped"] and q["scores"]]
    base_score = None
    if answered:
        base_score = round(
            sum((s["structure"] + s["depth"] + s["clarity"] - 3) / 12 * 100 for s in answered)
            / len(answered)
        )
        score = max(0, min(100, round(max(base_score - 5, min(base_score + 5, score)))))
    return {
        "overall": {
            "score": score,
            "base_score": base_score,
            "summary": str(overall.get("summary") or ""),
        },
        "questions": questions,
        "weak_dimensions": [str(x) for x in (data.get("weak_dimensions") or [])],
        "action_items": [str(x) for x in (data.get("action_items") or [])],
        "questions_for_bank": [
            {
                "content": str(q.get("content") or "")[:200],
                "dimension": str(q.get("dimension") or "其他")[:20],
                "difficulty": q.get("difficulty") if q.get("difficulty") in ("easy", "medium", "hard") else "medium",
            }
            for q in (data.get("questions_for_bank") or [])
            if isinstance(q, dict) and q.get("content")
        ],
    }


def _analysis_round_note(round_type: str) -> str:
    """分析 Prompt 中的专题评分口径说明；普通轮次返回空串。"""
    if round_type == "stress":
        return (
            "（压力面专题）面试官的否定与质疑是压力设计的一部分，不代表回答真的很差；"
            "评分关注候选人在高压下的情绪稳定性与临场反应，被质疑后仍能冷静、有条理地阐述观点应视为亮点；"
            "仅因施压产生的紧张与表达波动不过度扣「表达」分。"
        )
    if round_type == "project":
        return (
            "（项目经历面专题）整场只考察项目深挖："
            "评分围绕项目理解深度、个人贡献真实性、技术决策与取舍、量化结果展开。"
        )
    return ""


def _generate_analysis(
    session: Session, opp: Opportunity, transcript_text: str, round_type: str = "other"
) -> dict:
    """按当前评价标准生成分析报告（finish 与 reanalyze 共用）。"""
    cfg = get_ai_config(session)
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI，请先在「设置」中填写 API Key")

    years_hint = "请从对话与简历表述中自行推断"
    resume_text = "（未关联简历）"
    if opp.resume_id:
        resume = session.get(Resume, opp.resume_id)
        if resume is not None:
            resume_text = resume.structured or resume.text or "（简历无可用文本）"
            years_hint = f"以简历为准（{resume.name}）；若简历未注明则从工作经历时间推断"

    # 知识库检索：按本场被问的问题 + 岗位关键词检索，失败不阻塞
    try:
        kb_query = " ".join(
            t.get("content", "")[:80] for t in json.loads(transcript_text) if t.get("role") == "interviewer"
        )
        kb_hits = search_knowledge_base(session, f"{kb_query} {opp.company} {opp.position}")
    except Exception:
        kb_hits = []
    if kb_hits:
        kb_text = chr(10).join(f"[{i}] 来源 {h['source']}" + chr(10) + f"{h['text']}" for i, h in enumerate(kb_hits, 1))
        kb_text = kb_text[:3000]
    else:
        kb_text = "（未配置知识库或未检索到相关笔记，忽略本节，也不要标注「参考」）"

    prompt = ANALYSIS_PROMPT.format(
        transcript=transcript_text[:30000],
        company=opp.company,
        position=opp.position,
        city=opp.city or "未填写",
        salary_range=opp.salary_range or "未填写",
        years_hint=years_hint,
        round_label=ROUND_LABELS.get(round_type, "面试"),
        round_note=_analysis_round_note(round_type),
        jd=(opp.jd_text or "（未填写）")[:3000],
        profile_block=(
            build_profile_text(session, owner)
            if (owner := session.get(User, opp.user_id) if opp.user_id else None) is not None
            else "（未设置）"
        ),
        resume=resume_text[:5000],
        kb=kb_text,
        answer_standard=ANSWER_STANDARD,
        experience_rules=ANSWER_EXPERIENCE_RULES,
    )
    raw = _call_llm(cfg["base_url"], cfg["model"], cfg["api_key"], prompt, max_tokens=16384)
    try:
        data = _parse_json_loose(raw)
    except ValueError:
        raise HTTPException(status_code=502, detail=f"AI 返回内容无法解析：{raw[:200]}")
    # 偶发：模型漏掉 questions 数组（逐题复盘为空）——带强调提示重试一次
    if not (data.get("questions") or []):
        retry_prompt = prompt + (
            "\n\n【重试强调】上一次输出遗漏了 questions 数组。questions 必须逐题收录面试官提出的"
            "所有主要问题（追问合并进主问题），绝不允许为空数组或省略——这是本次任务的核心输出。"
        )
        raw = _call_llm(cfg["base_url"], cfg["model"], cfg["api_key"], retry_prompt, max_tokens=16384)
        try:
            retried = _parse_json_loose(raw)
            if retried.get("questions"):
                data = retried
        except ValueError:
            pass
    analysis = _normalize_analysis(data)

    # 把对话中候选人的原始回答按题挂到分析上，供复盘时展开原话（摘述之外的原文）。
    # AI 标注的 followup/next 不总可靠：action 分组数与题数一致时用分组；
    # 否则退化为按顺序一一对齐（候选回答顺序 = 题目顺序）；再不行就留空。
    try:
        transcript = json.loads(transcript_text)
    except ValueError:
        transcript = []
    grouped = _group_candidate_answers(transcript)
    flat = [t.get("content", "").strip() for t in transcript if t.get("role") == "candidate" and t.get("content", "").strip()]
    n = len(analysis["questions"])
    if n and len(grouped) == n:
        answers = [[g] for g in grouped]      # 每题一组（组内可能含追问的多段回答）
    elif n and len(flat) == n:
        answers = [[t] for t in flat]
    else:
        answers = []
    for i, q in enumerate(analysis["questions"]):
        q["my_answer_full"] = (chr(10) * 2).join(answers[i]) if i < len(answers) else ""

    return analysis


@router.post("/mock-interviews/{interview_id}/reanalyze")
def reanalyze_mock_interview(
    interview_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """重新分析已结束的模拟面试：去掉末尾已提问但未回答的题，按当前评价标准重新打分。"""
    interview = session.get(MockInterview, interview_id)
    if interview is None or interview.user_id != user.id:
        raise HTTPException(status_code=404, detail="模拟面试会话不存在")
    if interview.status != "finished":
        raise HTTPException(status_code=400, detail="该场模拟面试尚未结束")
    opp = _get_opportunity(session, interview.opportunity_id, user)

    try:
        transcript = json.loads(interview.transcript)
    except ValueError:
        transcript = []
    # 去掉末尾「已提问但未回答」的题（最后一条候选人不作答则其后的面试官发言都不计分）
    trimmed = list(transcript)
    while trimmed and trimmed[-1].get("role") == "interviewer":
        trimmed.pop()
    if not any(t.get("role") == "candidate" for t in trimmed):
        raise HTTPException(status_code=400, detail="该场面试没有任何已回答的题目，无法评分")

    analysis = _generate_analysis(
        session, opp, json.dumps(trimmed, ensure_ascii=False), interview.round_type
    )
    analysis["removed_unanswered"] = len(transcript) - len(trimmed) > 0
    interview.analysis = json.dumps(analysis, ensure_ascii=False)
    interview.overall_score = analysis["overall"]["score"]
    session.add(interview)
    session.commit()
    session.refresh(interview)
    return _interview_dict(interview)


@router.post("/mock-interviews/{interview_id}/finish")
def finish_mock_interview(
    interview_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    interview = session.get(MockInterview, interview_id)
    if interview is None or interview.user_id != user.id:
        raise HTTPException(status_code=404, detail="模拟面试会话不存在")
    opp = _get_opportunity(session, interview.opportunity_id, user)
    cfg = get_ai_config(session)
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI，请先在「设置」中填写 API Key")

    # 候选人主动结束时，补一条面试官收尾语
    try:
        transcript = json.loads(interview.transcript)
    except ValueError:
        transcript = []
    if transcript and transcript[-1].get("role") == "candidate":
        turn = _interviewer_turn(session, interview, opp, "候选人主动提出了结束面试，请输出收尾致谢，action 用 finish。")
        transcript.append(turn)
        interview.transcript = json.dumps(transcript, ensure_ascii=False)

    analysis = _generate_analysis(session, opp, interview.transcript, interview.round_type)
    interview.analysis = json.dumps(analysis, ensure_ascii=False)
    interview.overall_score = analysis["overall"]["score"]
    if interview.status != "finished":
        interview.status = "finished"
        interview.finished_at = datetime.now()
    session.add(interview)
    session.commit()
    session.refresh(interview)
    return _interview_dict(interview)


@router.delete("/mock-interviews/{interview_id}")
def delete_mock_interview(
    interview_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    interview = session.get(MockInterview, interview_id)
    if interview is None or interview.user_id != user.id:
        raise HTTPException(status_code=404, detail="模拟面试会话不存在")
    session.delete(interview)
    session.commit()
    return {"ok": True}
