"""岗位调研笔记：五大板块 Markdown 笔记 + AI 调研提纲生成。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.models import NOTE_TYPES, Opportunity, ResearchNote, Resume
from app.routers.ai import _call_llm
from app.routers.settings import get_ai_config

router = APIRouter()

NOTE_TYPE_LABELS = {
    "company": "公司调研",
    "team": "团队与业务调研",
    "tech": "技术栈调研",
    "self_intro": "自我介绍稿",
    "ask_back": "反问清单",
}


class NoteUpdate(BaseModel):
    content: str = ""
    ai_generated: bool = False


class OutlineRequest(BaseModel):
    overwrite: bool = False


def _get_opportunity(session: Session, opportunity_id: int) -> Opportunity:
    opp = session.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return opp


def _note_dict(note: ResearchNote) -> dict:
    return {
        "id": note.id,
        "opportunity_id": note.opportunity_id,
        "note_type": note.note_type,
        "content": note.content,
        "ai_generated": note.ai_generated,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }


@router.get("/opportunities/{opportunity_id}/notes")
def list_notes(opportunity_id: int, session: Session = Depends(get_session)):
    _get_opportunity(session, opportunity_id)
    rows = session.exec(
        select(ResearchNote).where(ResearchNote.opportunity_id == opportunity_id)
    ).all()
    return {"items": [_note_dict(n) for n in rows]}


@router.put("/opportunities/{opportunity_id}/notes/{note_type}")
def save_note(
    opportunity_id: int,
    note_type: str,
    body: NoteUpdate,
    session: Session = Depends(get_session),
):
    if note_type not in NOTE_TYPES:
        raise HTTPException(status_code=404, detail="未知的笔记类型")
    _get_opportunity(session, opportunity_id)

    note = session.exec(
        select(ResearchNote).where(
            ResearchNote.opportunity_id == opportunity_id,
            ResearchNote.note_type == note_type,
        )
    ).first()
    if note is None:
        note = ResearchNote(opportunity_id=opportunity_id, note_type=note_type)
    note.content = body.content
    note.ai_generated = body.ai_generated
    note.updated_at = datetime.now()
    session.add(note)
    session.commit()
    session.refresh(note)
    return _note_dict(note)


@router.delete("/opportunities/{opportunity_id}/notes/{note_type}")
def delete_note(
    opportunity_id: int, note_type: str, session: Session = Depends(get_session)
):
    note = session.exec(
        select(ResearchNote).where(
            ResearchNote.opportunity_id == opportunity_id,
            ResearchNote.note_type == note_type,
        )
    ).first()
    if note is None:
        raise HTTPException(status_code=404, detail="该笔记尚不存在")
    session.delete(note)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------- AI 调研提纲

_OUTLINE_HINTS = {
    "company": """请输出「公司调研」提纲（Markdown）。围绕：
1. 主营业务与产品线；2. 商业模式与主要收入来源；3. 公司规模 / 融资 / 上市状态；
4. 行业地位与主要竞品对比；5. 近期动态（新产品、组织调整、财报要点）；
6. 技术团队规模与工程文化线索（技术博客、开源项目、招聘方向）；
7. 风险与口碑（加班情况、业务稳定性、裁员传闻等）。
每小节给出 2-4 条「该查什么、去哪查」的指引条目，用「（待补充）」标记需要用户自己填写的事实。""",
    "team": """请输出「团队与业务调研」提纲（Markdown）。围绕：
1. 该岗位所属部门 / 业务线的定位与价值；2. 团队规模与分工推测（从 JD 职责反推）；
3. 团队可能使用的技术栈与基建（从 JD 技能要求反推）；4. 该业务当前的核心指标与挑战；
5. 汇报关系与协作方；6. 面试中值得向面试官确认的问题（团队方向、技术演进、考核方式）。
每小节给出 2-4 条指引条目，用「（待补充）」标记需要核实的内容。""",
    "tech": """请输出「技术栈调研」提纲（Markdown）：从 JD 中提取全部技术关键词，逐项展开：
- 该技术在该公司业务中可能的用途（结合业务线推测）；
- 核心概念与原理要点（面试高频角度）；
- 结合我的简历，可能被追问的问题方向；
- 建议面试前重点复习的深度。
按「必须精通 / 重点熟悉 / 了解即可」分层排序。""",
    "self_intro": """请输出「自我介绍稿」（Markdown），包含两版：
1. **1 分钟版**（电话 / HR 初筛用）：开场 → 核心经历与量化结果 → 与该岗位的契合点 → 求职动机；
2. **3 分钟版**（技术面开场用）：在 1 分钟版基础上展开重点项目（背景-方案-结果）、技术亮点。
要求：只使用简历中真实存在的内容，禁止编造经历与数字；突出与该 JD 的匹配点；
在正文中用「【检查】」标注需要用户核对或替换成真实数字的位置。""",
    "ask_back": """请输出「反问清单」（Markdown），按场景分组：
1. 问业务（业务方向、目标与挑战）；2. 问团队（规模、分工、技术演进）；
3. 问成长（培养机制、技术氛围、晋升路径）；4. 问流程（后续轮次安排与反馈时间）。
每个反问附一句「为什么问 / 能获得什么信息」；要求体现对该公司做过功课（可引用 JD 内容），
避免薪资加班等敏感话题（留到 Offer 阶段）。共 8-12 条。""",
}


def _outline_prompt(opp: Opportunity, note_type: str, resume_text: str | None) -> str:
    jd = (opp.jd_text or "").strip() or "（未提供 JD）"
    department = f"，部门 / 业务线：{opp.department}" if opp.department else ""
    resume_block = ""
    if note_type in ("self_intro", "tech") and resume_text:
        resume_block = f"\n\n【我的简历摘要】\n{resume_text[:6000]}"
    hint = _OUTLINE_HINTS[note_type]
    return f"""你是一位资深求职辅导顾问。候选人正在准备 {opp.company} 的「{opp.position}」岗位面试（{department}），
以下是该岗位的 JD：

【JD】
{jd}{resume_block}

{hint}

输出要求：直接输出 Markdown 正文（以「# {NOTE_TYPE_LABELS[note_type]}：{opp.company} · {opp.position}」开头），
不要输出任何解释性文字。所有具体事实用「（待补充）」占位，禁止编造公司数据。"""


@router.post("/opportunities/{opportunity_id}/notes/{note_type}/outline")
def generate_outline(
    opportunity_id: int,
    note_type: str,
    body: OutlineRequest,
    session: Session = Depends(get_session),
):
    if note_type not in NOTE_TYPES:
        raise HTTPException(status_code=404, detail="未知的笔记类型")
    opp = _get_opportunity(session, opportunity_id)

    existing = session.exec(
        select(ResearchNote).where(
            ResearchNote.opportunity_id == opportunity_id,
            ResearchNote.note_type == note_type,
        )
    ).first()
    if existing is not None and existing.content.strip() and not body.overwrite:
        raise HTTPException(status_code=409, detail="该笔记已有内容，覆盖生成请携带 overwrite=true")

    resume_text = None
    if opp.resume_id:
        resume = session.get(Resume, opp.resume_id)
        if resume is not None:
            resume_text = resume.structured or resume.text

    cfg = get_ai_config(session)
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI，请先在「设置」中填写 API Key")

    raw = _call_llm(
        cfg["base_url"], cfg["model"], cfg["api_key"],
        _outline_prompt(opp, note_type, resume_text),
        max_tokens=8192,
    )
    content = raw.strip()
    if not content:
        raise HTTPException(status_code=502, detail="AI 未返回内容，请重试")

    if existing is None:
        existing = ResearchNote(opportunity_id=opportunity_id, note_type=note_type)
    existing.content = content
    existing.ai_generated = True
    existing.updated_at = datetime.now()
    session.add(existing)
    session.commit()
    session.refresh(existing)
    return _note_dict(existing)
