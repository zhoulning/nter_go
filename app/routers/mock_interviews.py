"""模拟面试：AI 面试官对话式提问（支持追问），结束后生成整体分析。

会话与对话记录、分析报告全部入库，可随时回看。
"""
import json
import random
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.models import MatchReport, MockInterview, Opportunity, Prediction, Resume
from app.routers.ai import _call_llm, _parse_json_loose
from app.routers.predictions import ROUND_EMPHASIS, ROUND_LABELS
from app.routers.settings import get_ai_config

router = APIRouter()

TURN_PROMPT = """你正在扮演 {company} 的技术面试官（{round_label}），对候选人进行真实感很强的模拟面试。
你的提问风格：专业、口语化、有压迫感但不失礼貌，像真实面试一样逐步深挖。

【岗位】{position}
【城市 / 薪资范围】{city} · {salary_range}
【JD 要点】
{jd}

【候选人简历摘要】
{resume}

【本轮面试侧重】
{round_emphasis}

【本轮候选题库（顺序已打乱，仅供选题参考，禁止按列表顺序机械推进）】
{question_pool}

【目前对话记录】
{transcript}

目前状态：已向候选人提出 {asked} 个问题（追问不算新问题）。

请基于候选人上一条回答，决定你的下一个动作并输出 JSON（不要输出任何其他内容）：
{{
  "message": "面试官的口语化发言。对上一个回答简短点评一句（如「嗯，了解」/「这个说法有点问题」），然后：追问时提出追问问题；next 时自然过渡并抛出下一个新问题；finish 时做收尾致谢。",
  "action": "followup|next|finish",
  "dimension": "当前问题所属维度（如 MySQL / 项目深挖 / 系统设计）"
}}

规则：
- 判断标准：上一条回答有明显含糊、矛盾或值得深挖的点 → followup 追问（每个问题最多追问 1 次，不要连环追问）；回答完整或无需深挖 → next 进入题库下一个问题。
- 已提问数达到 {target} 题且当前无必须追问的点 → finish 收尾。
- 一次只问一个问题，禁止一次抛出多个问题；message 中不要出现 JSON 或括号标记。
- 候选人明确表示不知道 / 要求跳过 → 简单带过并 next；候选人要求结束面试 → finish。
- 选题规则：进入新问题时，从候选题库中挑一个尚未问过、且考察维度与上一题不同的题目；八股 / 项目深挖 / 场景设计等大类要穿插进行，不要连续多题同属一类，更不要按简历章节或题库列表的顺序推进。
- 项目深挖采用开放式提问：不必念题库原题，围绕简历中的任意项目自由切入（如个人贡献最大的点、最难的一次故障、如果重来会改哪个设计、两个方案的取舍对比），追问链根据候选人回答动态生成。
- 候选人的回答很可能来自语音转文字，会混入同音字 / 术语错写（如「瑞迪斯」=Redis、「米等」=幂等、「锁」/「落」不分）：按上下文推断其本意来理解即可，不要纠缠错别字，更不要因转写错误而降分或反复追问文字问题。
- 出题与追问深度要匹配薪资 / 年限对应的职级期望：目标薪资越高、年限越长，越应追问原理、线上实战与量化细节；初级岗则以基础为主，避免超纲。"""

OPENING_HINT = "这是面试的开场：先用一句话欢迎候选人并做简短自我介绍（不透露名字，只说角色），然后抛出题库中的第一个问题。action 用 next。"

ANALYSIS_PROMPT = """你是一位面试辅导专家。以下是一场模拟面试的完整对话记录（role: interviewer 是面试官，candidate 是候选人）。
请对候选人的表现做逐题复盘分析。

【评分背景校准】
- 目标公司 / 岗位：{company} · {position}
- 城市 / 薪资范围：{city} · {salary_range}
- 候选人工作年限：{years_hint}
- 评分基准必须与该薪资 / 职级的市场期望匹配：同样的回答，对标高薪资深岗应更严格（追问深度、量化意识、原理理解都要看），对标初级岗可适当放宽。

【候选人简历摘要】
{resume}

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
      "bad": ["回答中的问题（如没有量化结果、被追问时绕开）"],
      "reference": "该题的参考答题要点"
    }}
  ],
  "weak_dimensions": ["暴露薄弱的维度"],
  "action_items": ["下一场面试前要补的具体事项 3-5 条"],
  "questions_for_bank": [ {{ "content": "值得入题库的原题", "dimension": "维度", "difficulty": "easy|medium|hard" }} ]
}}

评分锚定：90+ 回答完整且有深度有量化；75-89 主体完整、深度一般；60-74 不少问题答不上或答偏；60 以下多数问题答不上。
questions 收录面试官提出的所有主要问题（追问合并进主问题即可）。

两类特殊情况必须正确处理：
1. 候选人消息带「（这题我不太熟，先跳过…）」或明确表示不会：该题记 "skipped": true，scores 置 null，my_answer 写「主动跳过」，good/bad 置空数组；
2. 对话结束时面试官已提问但候选人尚未作答：该题同样记 "skipped": true，scores 置 null，my_answer 写「未回答（面试在此结束）」，good/bad 置空数组。
skipped 的题不提供 good/bad，可以给 reference；overall 的总分只基于已回答的题目评定，跳过或未回答的题不扣分。"""


class MockCreateRequest(BaseModel):
    round_type: str = "first"


class MockReplyRequest(BaseModel):
    content: str = ""
    kind: str = "answer"  # answer: 正常回答 / skip: 主动跳过本题


def _get_opportunity(session: Session, opportunity_id: int) -> Opportunity:
    opp = session.get(Opportunity, opportunity_id)
    if opp is None:
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
    target = 4 if interview.round_type == "hr" else 6

    transcript_text = chr(10).join(
        (
            ("面试官[" + t["dimension"] + "]" if t.get("dimension") else "面试官")
            + "：" + t.get("content", "")[:1500]
            if t.get("role") == "interviewer"
            else "候选人：" + t.get("content", "")[:1500]
        )
        for t in transcript
    )[-16000:] or "（还没有对话）"

    prompt = TURN_PROMPT.format(
        company=opp.company,
        round_label=ROUND_LABELS.get(interview.round_type, "面试"),
        round_emphasis=ROUND_EMPHASIS.get(interview.round_type, ROUND_EMPHASIS["other"]),
        position=opp.position,
        city=opp.city or "未填写",
        salary_range=opp.salary_range or "未填写",
        jd=(opp.jd_text or "（未提供 JD）")[:4000],
        resume=resume_text,
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
def list_mock_interviews(opportunity_id: int, session: Session = Depends(get_session)):
    _get_opportunity(session, opportunity_id)
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
    session: Session = Depends(get_session),
):
    opp = _get_opportunity(session, opportunity_id)
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
    session: Session = Depends(get_session),
):
    interview = session.get(MockInterview, interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="模拟面试会话不存在")
    if interview.status != "ongoing":
        raise HTTPException(status_code=400, detail="该场模拟面试已结束")
    if body.kind not in ("answer", "skip"):
        raise HTTPException(status_code=400, detail="未知操作类型")
    content = body.content.strip()
    if body.kind == "answer" and not content:
        raise HTTPException(status_code=400, detail="回答内容不能为空")
    opp = _get_opportunity(session, interview.opportunity_id)

    try:
        transcript = json.loads(interview.transcript)
    except ValueError:
        transcript = []
    if body.kind == "skip":
        transcript.append({
            "role": "candidate",
            "content": "（这题我不太熟，先跳过，我们看下一个问题吧）",
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


def _clamp5(v):
    try:
        return max(1, min(5, int(v)))
    except (TypeError, ValueError):
        return 3


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
    return {
        "overall": {
            "score": score,
            "summary": str(overall.get("summary") or ""),
        },
        "questions": [
            {
                "question": str(q.get("question") or ""),
                "my_answer": str(q.get("my_answer") or ""),
                "skipped": bool(q.get("skipped")) or q.get("scores") is None,
                "scores": _parse_scores(q.get("scores")),
                "good": [str(x) for x in (q.get("good") or [])],
                "bad": [str(x) for x in (q.get("bad") or [])],
                "reference": str(q.get("reference") or ""),
            }
            for q in (data.get("questions") or [])
            if isinstance(q, dict) and q.get("question")
        ],
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


def _generate_analysis(session: Session, opp: Opportunity, transcript_text: str) -> dict:
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

    prompt = ANALYSIS_PROMPT.format(
        transcript=transcript_text[:30000],
        company=opp.company,
        position=opp.position,
        city=opp.city or "未填写",
        salary_range=opp.salary_range or "未填写",
        years_hint=years_hint,
        resume=resume_text[:5000],
    )
    raw = _call_llm(cfg["base_url"], cfg["model"], cfg["api_key"], prompt, max_tokens=8192)
    try:
        data = _parse_json_loose(raw)
    except ValueError:
        raise HTTPException(status_code=502, detail=f"AI 返回内容无法解析：{raw[:200]}")
    return _normalize_analysis(data)


@router.post("/mock-interviews/{interview_id}/reanalyze")
def reanalyze_mock_interview(interview_id: int, session: Session = Depends(get_session)):
    """重新分析已结束的模拟面试：去掉末尾已提问但未回答的题，按当前评价标准重新打分。"""
    interview = session.get(MockInterview, interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="模拟面试会话不存在")
    if interview.status != "finished":
        raise HTTPException(status_code=400, detail="该场模拟面试尚未结束")
    opp = _get_opportunity(session, interview.opportunity_id)

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

    analysis = _generate_analysis(session, opp, json.dumps(trimmed, ensure_ascii=False))
    analysis["removed_unanswered"] = len(transcript) - len(trimmed) > 0
    interview.analysis = json.dumps(analysis, ensure_ascii=False)
    interview.overall_score = analysis["overall"]["score"]
    session.add(interview)
    session.commit()
    session.refresh(interview)
    return _interview_dict(interview)


@router.post("/mock-interviews/{interview_id}/finish")
def finish_mock_interview(interview_id: int, session: Session = Depends(get_session)):
    interview = session.get(MockInterview, interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="模拟面试会话不存在")
    opp = _get_opportunity(session, interview.opportunity_id)
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

    analysis = _generate_analysis(session, opp, interview.transcript)
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
def delete_mock_interview(interview_id: int, session: Session = Depends(get_session)):
    interview = session.get(MockInterview, interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="模拟面试会话不存在")
    session.delete(interview)
    session.commit()
    return {"ok": True}
