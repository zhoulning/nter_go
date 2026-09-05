"""AI 题目预测：JD + 简历 + 匹配度报告 + 历史题库 → 按目标轮次生成分维度题单。

每个 (岗位, 目标轮次) 保留最新一份题单，重新生成即覆盖。
题目本身由 PREDICT_PROMPT 一次生成；完整答案不在出题时生成，
而是逐题走 ai.generate_reference_answer 统一答案引擎（简历 + JD + 知识库）。
"""
import json
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import engine, get_session
from app.models import MatchReport, Opportunity, Prediction, Question, Resume, User
from app.routers.ai import _call_llm, _parse_json_loose, generate_reference_answer
from app.routers.questions import DIMENSION_PRESETS
from app.routers.settings import get_ai_config

router = APIRouter()

ROUND_LABELS = {
    "written": "笔试",
    "first": "一面",
    "second": "二面",
    "third": "三面",
    "comprehensive": "综合面",
    "hr": "HR 面",
    # 以下为模拟面试专属专题，不是真实面试轮次
    "project": "项目经历面",
    "stress": "压力面",
    "other": "面试",
}

ROUND_EMPHASIS = {
    "written": "笔试侧重：算法手写题、语言基础、计算机基础选择题，给出题目时附上解题思路要点",
    "first": "一面侧重：语言特性、并发、数据库 / 缓存 / 消息队列等八股基础，以及简历项目的初步深挖",
    "second": "二面侧重：技术深度（原理、源码级理解、性能调优）、系统方案设计、复杂问题排查思路",
    "third": "三面侧重：大型系统设计、技术选型与权衡、架构演进、团队协作与技术视野、软素质",
    "comprehensive": "综合面侧重：不设固定侧重——八股基础、项目深挖、系统设计、场景开放题、职业规划与软素质都可能问到，考察整体素养与随机应变；提问自由度最大，按现场对话自然流动",
    "hr": "HR 面侧重：求职动机、离职原因、职业规划、稳定性、薪资沟通策略、软素质与价值观",
    "project": "项目经历面（专题）侧重：整场只围绕简历项目深挖——个人贡献与实际角色、架构与技术选型的取舍理由、难点攻关与故障排查过程、量化结果与业务价值、复盘与改进；不问与项目无关的八股 / 原理题",
    "stress": "压力面（专题）侧重：高压质询下的技术基础与项目——问题本身仍来自简历、项目与技术基础，但以质疑、否定、连环追问的施压方式提出，考察情绪稳定性、抗压能力与临场反应",
    "other": "一般技术面试：基础与项目并重",
}

GROUPS = ["八股基础", "项目深挖", "场景设计", "软素质", "反问建议"]

PREDICT_PROMPT = """你是一位资深的面试出题官，正在为候选人模拟出一份「{round_label}」预测题单。

【目标公司】{company} · {position}
【城市 / 薪资范围】{city} · {salary_range}
【JD】
{jd}

【我的简历摘要】
{resume}

【匹配度报告摘要】
{match_summary}

【历史题库参考】
{bank_summary}

本轮出题要求：{emphasis}

请输出 JSON（不要输出任何其他内容）：
{{
  "questions": [
    {{
      "group": "八股基础|项目深挖|场景设计|软素质|反问建议 之一",
      "dimension": "考察维度，必须严格从以下预设中选一个：{dimension_presets}，不要自创维度",
      "q": "问题题干（面试官的问法，具体不空泛）",
      "intent": "考察意图（这道题想验证什么）",
      "key_points": "参考答题要点（2-4 个核心点，简明）",
      "difficulty": "easy|medium|hard"
    }}
  ],
  "weak_focus": ["结合题库弱项，本轮重点加大了哪些维度的权重"],
  "overall_advice": "这一轮的整体备考建议（两三句）"
}}

要求：
- 共 {total} 道左右。八股基础最多；「项目深挖」必须基于简历中的真实项目设计追问链（如 QPS 怎么估的→出了问题怎么排查→为什么不用别的方案）；HR 面则软素质 + 反问为主。
- 「反问建议」给 2-3 条适合这一轮问面试官的反问题。
- 题库中「不会 / 模糊」的弱项维度优先覆盖；最近已被真实问过的题除非高价值否则避免原样重复。
- key_points 简明扼要，不要长篇大论。
- 难度校准：先判断目标公司在业界的面试难度层级（大厂 / 知名独角兽题更深更偏原理，中小厂偏基础与落地），再结合所在城市的竞争烈度、薪资水平与候选人年限校准整体难度——公司与城市标准越高，越多出原理、架构与线上实战难题；反之以基础为主，避免明显超纲。"""


class PredictRequest(BaseModel):
    round_type: str = "first"


def _fill_answers(
    questions: list[dict],
    *,
    opportunity_id: int,
    resume_id: int | None,
    company: str,
    user: User,
) -> tuple[int, int]:
    """逐题调用统一答案引擎补全 answer 字段（与题库口述版答案同一路径）。

    每个工作线程用独立 Session（SQLModel Session 非线程安全）；
    单题失败不阻塞整张题单，返回 (成功数, 失败数)。反问建议不是问答，不出答案。
    """
    targets = [q for q in questions if q["group"] != "反问建议"]
    if not targets:
        return 0, 0

    def _job(q: dict) -> str:
        s = Session(engine)
        try:
            try:
                return generate_reference_answer(
                    s,
                    user,
                    content=q["q"],
                    dimension=q["dimension"],
                    companies=[company],
                    opportunity_id=opportunity_id,
                    resume_id=resume_id,
                )
            except Exception:
                return ""
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(_job, targets))
    for q, ans in zip(targets, results):
        q["answer"] = ans
    return sum(1 for a in results if a), sum(1 for a in results if not a)


def _get_opportunity(session: Session, opportunity_id: int, user: User) -> Opportunity:
    """取当前用户的岗位；不存在或越权一律 404。"""
    opp = session.get(Opportunity, opportunity_id)
    if opp is None or opp.user_id != user.id:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return opp


def _prediction_dict(row: Prediction) -> dict:
    try:
        data = json.loads(row.report) if row.report else None
    except ValueError:
        data = None
    return {
        "id": row.id,
        "opportunity_id": row.opportunity_id,
        "round_type": row.round_type,
        "model": row.model,
        "question_count": row.question_count,
        "report": data,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/opportunities/{opportunity_id}/predictions")
def list_predictions(
    opportunity_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _get_opportunity(session, opportunity_id, user)
    rows = session.exec(
        select(Prediction).where(Prediction.opportunity_id == opportunity_id)
    ).all()
    return {"items": [_prediction_dict(r) for r in rows]}


@router.post("/opportunities/{opportunity_id}/predictions")
def generate_prediction(
    opportunity_id: int,
    body: PredictRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    opp = _get_opportunity(session, opportunity_id, user)
    if body.round_type not in ROUND_LABELS:
        raise HTTPException(status_code=400, detail="未知的目标轮次")
    if not (opp.jd_text or "").strip():
        raise HTTPException(status_code=400, detail="该岗位还没有工作描述（JD），请先补充")
    resume_text = ""
    if opp.resume_id:
        resume = session.get(Resume, opp.resume_id)
        if resume is not None and resume.user_id == user.id:
            resume_text = resume.structured or resume.text or ""
    if not resume_text:
        resume_text = "（未关联简历，请仅依据 JD 出题）"

    match_summary = "（尚未生成匹配度报告）"
    match = session.exec(
        select(MatchReport).where(MatchReport.opportunity_id == opportunity_id)
    ).first()
    if match is not None:
        try:
            md = json.loads(match.report)
            gaps = [i["requirement"] for i in md.get("items", []) if i.get("verdict") != "match"]
            match_summary = (
                f"总分 {match.total_score}/100；主要缺口：{'；'.join(gaps[:6]) or '无'}"
            )
        except ValueError:
            pass

    # 题库：弱项优先 + 近期真实被问过的题（仅当前用户）
    all_questions = session.exec(select(Question).where(Question.user_id == user.id)).all()
    weak = [
        q for q in all_questions
        if q.mastery in ("unknown", "fuzzy") or (q.self_rating is not None and q.self_rating <= 3)
    ]
    real = [q for q in all_questions if q.source == "real"]
    bank_lines = []
    if weak:
        weak_dims = sorted({q.dimension for q in weak})
        bank_lines.append(
            f"- 弱项题（{len(weak)} 道，维度分布：{'、'.join(weak_dims)}），代表性题目："
        )
        for q in weak[:10]:
            bank_lines.append(f"  · [{q.dimension}] {q.content[:60]}")
    if real:
        bank_lines.append("- 近期真实面试被问过的题（避免原样重复）：")
        for q in real[:10]:
            bank_lines.append(f"  · [{q.dimension}] {q.content[:60]}")
    bank_summary = "\n".join(bank_lines) if bank_lines else "（题库为空）"

    cfg = get_ai_config(session)
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI，请先在「设置」中填写 API Key")

    prompt = PREDICT_PROMPT.format(
        round_label=ROUND_LABELS.get(body.round_type, "面试"),
        company=opp.company,
        position=opp.position,
        city=opp.city or "未填写",
        salary_range=opp.salary_range or "未填写",
        jd=opp.jd_text.strip()[:6000],
        resume=resume_text[:5000],
        match_summary=match_summary,
        bank_summary=bank_summary[:3000],
        emphasis=ROUND_EMPHASIS.get(body.round_type, ROUND_EMPHASIS["other"]),
        dimension_presets="/".join(DIMENSION_PRESETS),
        total=8 if body.round_type == "hr" else 14,
    )
    raw = _call_llm(cfg["base_url"], cfg["model"], cfg["api_key"], prompt)
    try:
        data = _parse_json_loose(raw)
    except ValueError:
        raise HTTPException(status_code=502, detail=f"AI 返回内容无法解析：{raw[:200]}")

    questions = []
    for item in data.get("questions") or []:
        if not isinstance(item, dict) or not item.get("q"):
            continue
        questions.append({
            "group": item.get("group") if item.get("group") in GROUPS else "八股基础",
            "dimension": item.get("dimension") if item.get("dimension") in DIMENSION_PRESETS else "其他",
            "q": str(item["q"]),
            "intent": str(item.get("intent") or ""),
            "key_points": str(item.get("key_points") or ""),
            "answer": "",
            "difficulty": item.get("difficulty") if item.get("difficulty") in ("easy", "medium", "hard") else "medium",
        })
    if not questions:
        raise HTTPException(status_code=502, detail="AI 未返回有效题目，请重试")

    # 完整答案逐题走统一答案引擎（简历 + JD + 知识库），与题库口述版答案同一条路径
    ok_count, failed_count = _fill_answers(
        questions,
        opportunity_id=opp.id,
        resume_id=opp.resume_id,
        company=opp.company,
        user=user,
    )

    report_json = {
        "questions": questions,
        "weak_focus": [str(x) for x in (data.get("weak_focus") or [])],
        "overall_advice": str(data.get("overall_advice") or ""),
    }
    if failed_count:
        report_json["answer_note"] = (
            f"有 {failed_count} 道题的参考答案生成失败（其余 {ok_count} 题正常），"
            "可重新生成题单，或在录入题库后单题重新生成"
        )

    row = session.exec(
        select(Prediction).where(
            Prediction.opportunity_id == opportunity_id,
            Prediction.round_type == body.round_type,
        )
    ).first()
    if row is None:
        row = Prediction(
            opportunity_id=opportunity_id, round_type=body.round_type, user_id=user.id
        )
    row.model = cfg["model"]
    row.report = json.dumps(report_json, ensure_ascii=False)
    row.question_count = len(questions)
    session.add(row)
    session.commit()
    session.refresh(row)
    return _prediction_dict(row)


@router.delete("/opportunities/{opportunity_id}/predictions/{prediction_id}")
def delete_prediction(
    opportunity_id: int,
    prediction_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _get_opportunity(session, opportunity_id, user)
    row = session.get(Prediction, prediction_id)
    if row is None or row.opportunity_id != opportunity_id:
        raise HTTPException(status_code=404, detail="预测题单不存在")
    session.delete(row)
    session.commit()
    return {"ok": True}
