"""岗位匹配度评估：JD × 简历 → AI 匹配度报告（每个岗位保留最新一份）。"""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session
from app.models import MatchReport, Opportunity, Resume, User
from app.routers.ai import _call_llm, _parse_json_loose
from app.routers.settings import get_ai_config

router = APIRouter()

# 五维固定键（前端雷达图按此渲染）
DIMENSIONS = ["stack", "experience", "projects", "soft", "fit"]
DIMENSION_LABELS = {
    "stack": "技术栈匹配",
    "experience": "经验匹配",
    "projects": "项目匹配",
    "soft": "软素质",
    "fit": "发展契合",
}

MATCH_PROMPT = """你是一位严格但建设性的技术面试辅导专家。请对照候选人的简历与目标岗位 JD，输出一份匹配度评估报告。

【JD】
{jd}

【我的简历】
{resume}

请严格按以下 JSON 结构输出（不要输出 JSON 以外的任何内容）：
{{
  "job_profile": {{
    "hard": ["硬性要求，如年限/学历/必备技能，逐条"],
    "stack": ["技术栈关键词，按 JD 出现的重要性排序"],
    "soft": ["软性要求，如沟通/协作/抗压"],
    "bonus": ["加分项"]
  }},
  "items": [
    {{
      "requirement": "JD 中的一条具体要求（合并同类后 6-10 条）",
      "weight": "high|mid|low",
      "verdict": "match|partial|missing",
      "evidence": "简历中对应的证据原文摘述；missing 时说明简历中为什么没有",
      "advice": "partial/missing 时给一句可执行的补齐建议；match 时给一句面试中如何放大这个优势"
    }}
  ],
  "total_score": 0 到 100 的整数，
  "dimensions": {{
    "stack": 0-100 整数, "experience": 0-100 整数, "projects": 0-100 整数,
    "soft": 0-100 整数, "fit": 0-100 整数
  }},
  "focus": ["面试前最该补的短板 3-5 条，每条具体可执行"],
  "resume_risks": ["简历上最容易被面试官追问的点 2-4 条，说明可能怎么问"]
}}

评分锚定：90+ 各维度均有直接对口的证据；75-89 主体匹配、少量缺口；60-74 方向正确但有明显缺口；60 以下建议慎重投入。
要求：evidence 必须引用简历中的真实内容，禁止编造；verdict 判定要严格，宁可 partial 不要放水。"""


class MatchGenerateRequest(BaseModel):
    resume_id: int | None = None  # 不传则用岗位已关联的简历


def _get_opportunity(session: Session, opportunity_id: int, user: User) -> Opportunity:
    """取当前用户的岗位；不存在或越权一律 404。"""
    opp = session.get(Opportunity, opportunity_id)
    if opp is None or opp.user_id != user.id:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return opp


def _report_dict(session: Session, row: MatchReport) -> dict:
    resume = session.get(Resume, row.resume_id) if row.resume_id else None
    opp = session.get(Opportunity, row.opportunity_id)
    try:
        report_data = json.loads(row.report) if row.report else None
    except ValueError:
        report_data = None
    return {
        "id": row.id,
        "opportunity_id": row.opportunity_id,
        "resume_id": row.resume_id,
        "resume_name": resume.name if resume else None,
        "model": row.model,
        "total_score": row.total_score,
        "report": report_data,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "company": opp.company if opp else None,
        "position": opp.position if opp else None,
    }


@router.get("/opportunities/{opportunity_id}/match-report")
def get_match_report(
    opportunity_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _get_opportunity(session, opportunity_id, user)
    row = session.exec(
        select(MatchReport).where(MatchReport.opportunity_id == opportunity_id)
    ).first()
    return {"report": _report_dict(session, row) if row else None}


@router.post("/opportunities/{opportunity_id}/match-report")
def generate_match_report(
    opportunity_id: int,
    body: MatchGenerateRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    opp = _get_opportunity(session, opportunity_id, user)
    if not (opp.jd_text or "").strip():
        raise HTTPException(
            status_code=400,
            detail="该岗位还没有工作描述（JD），请先在编辑弹窗中补充或用 AI 提取",
        )

    resume_id = body.resume_id or opp.resume_id
    if not resume_id:
        raise HTTPException(
            status_code=400, detail="请先为该岗位关联一份简历（编辑弹窗或详情页中选择）"
        )
    resume = session.get(Resume, resume_id)
    if resume is None or resume.user_id != user.id:
        raise HTTPException(status_code=404, detail="关联的简历不存在，请重新选择")
    resume_text = resume.structured or resume.text
    if not resume_text:
        raise HTTPException(
            status_code=400, detail="该简历没有可用的抽取文本，请先到「简历库」重新抽取"
        )

    cfg = get_ai_config(session)
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI，请先在「设置」中填写 API Key")

    prompt = MATCH_PROMPT.replace("{jd}", opp.jd_text.strip()[:8000]).replace(
        "{resume}", resume_text[:8000]
    )
    raw = _call_llm(cfg["base_url"], cfg["model"], cfg["api_key"], prompt, max_tokens=8192)
    try:
        data = _parse_json_loose(raw)
    except ValueError:
        raise HTTPException(status_code=502, detail=f"AI 返回内容无法解析：{raw[:200]}")

    def _clamp(v, default=0):
        try:
            return max(0, min(100, int(v)))
        except (TypeError, ValueError):
            return default

    dims = data.get("dimensions") or {}
    dimensions = {k: _clamp(dims.get(k)) for k in DIMENSIONS}
    total = _clamp(data.get("total_score"))
    if not total:
        valid = [v for v in dimensions.values() if v]
        total = round(sum(valid) / len(valid)) if valid else 0

    report_json = {
        "job_profile": {
            "hard": [str(x) for x in (data.get("job_profile") or {}).get("hard", [])],
            "stack": [str(x) for x in (data.get("job_profile") or {}).get("stack", [])],
            "soft": [str(x) for x in (data.get("job_profile") or {}).get("soft", [])],
            "bonus": [str(x) for x in (data.get("job_profile") or {}).get("bonus", [])],
        },
        "items": [
            {
                "requirement": str(item.get("requirement", "")),
                "weight": item.get("weight") if item.get("weight") in ("high", "mid", "low") else "mid",
                "verdict": item.get("verdict") if item.get("verdict") in ("match", "partial", "missing") else "partial",
                "evidence": str(item.get("evidence", "")),
                "advice": str(item.get("advice", "")),
            }
            for item in (data.get("items") or [])
            if isinstance(item, dict) and item.get("requirement")
        ],
        "total_score": total,
        "dimensions": dimensions,
        "dimension_labels": DIMENSION_LABELS,
        "focus": [str(x) for x in (data.get("focus") or [])],
        "resume_risks": [str(x) for x in (data.get("resume_risks") or [])],
    }
    if not report_json["items"]:
        raise HTTPException(status_code=502, detail="AI 未返回有效的逐条匹配结果，请重试")

    row = session.exec(
        select(MatchReport).where(MatchReport.opportunity_id == opportunity_id)
    ).first()
    if row is None:
        row = MatchReport(opportunity_id=opportunity_id, user_id=user.id)
    row.resume_id = resume_id
    row.model = cfg["model"]
    row.report = json.dumps(report_json, ensure_ascii=False)
    row.total_score = total
    session.add(row)
    session.commit()
    session.refresh(row)
    return _report_dict(session, row)


@router.delete("/opportunities/{opportunity_id}/match-report")
def delete_match_report(
    opportunity_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _get_opportunity(session, opportunity_id, user)
    row = session.exec(
        select(MatchReport).where(MatchReport.opportunity_id == opportunity_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="该岗位还没有匹配度报告")
    session.delete(row)
    session.commit()
    return {"ok": True}
