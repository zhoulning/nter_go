"""题库 / 错题本的 CRUD API。"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlmodel import Session, select

from app.database import get_session
from app.models import InterviewRound, Opportunity, Question, QuestionSource, Resume

router = APIRouter()

# 后端方向预置维度，用户也可在新增时自定义
DIMENSION_PRESETS = [
    "语言特性",
    "并发编程",
    "JVM",
    "MySQL",
    "Redis",
    "消息队列",
    "分布式",
    "微服务",
    "计算机网络",
    "系统设计",
    "项目深挖",
    "场景设计",
    "算法",
    "软素质",
    "其他",
]

DIFFICULTIES = ["easy", "medium", "hard"]
SOURCES = ["manual", "real", "predicted"]
MASTERY = ["unknown", "fuzzy", "mastered"]


class SourceIn(BaseModel):
    opportunity_id: int
    round_id: Optional[int] = None


class QuestionCreate(BaseModel):
    content: str
    dimension: str = "其他"
    difficulty: str = "medium"
    source: str = "manual"
    opportunity_id: Optional[int] = None
    resume_id: Optional[int] = None
    sources: Optional[list[SourceIn]] = None
    my_answer: Optional[str] = None
    answer_key: Optional[str] = None
    answer_spoken: Optional[str] = None
    answer_brief: Optional[str] = None
    self_rating: Optional[int] = None
    mastery: str = "unknown"


class QuestionUpdate(BaseModel):
    content: Optional[str] = None
    dimension: Optional[str] = None
    difficulty: Optional[str] = None
    source: Optional[str] = None
    opportunity_id: Optional[int] = None
    resume_id: Optional[int] = None
    sources: Optional[list[SourceIn]] = None
    my_answer: Optional[str] = None
    answer_key: Optional[str] = None
    answer_spoken: Optional[str] = None
    answer_brief: Optional[str] = None
    self_rating: Optional[int] = None
    mastery: Optional[str] = None
    review_done: Optional[bool] = None


def _validate_sources(session: Session, sources: list[SourceIn]) -> None:
    """校验来源里的岗位 / 轮次存在且从属关系正确。"""
    for src in sources:
        opp = session.get(Opportunity, src.opportunity_id)
        if opp is None:
            raise HTTPException(status_code=400, detail="题目来源的岗位不存在")
        if src.round_id is not None:
            rnd = session.get(InterviewRound, src.round_id)
            if rnd is None or rnd.opportunity_id != src.opportunity_id:
                raise HTTPException(status_code=400, detail="轮次与岗位不匹配")


def _replace_sources(session: Session, question_id: int, sources: list[SourceIn]) -> None:
    """整体替换某题的来源列表。"""
    for old in session.exec(
        select(QuestionSource).where(QuestionSource.question_id == question_id)
    ).all():
        session.delete(old)
    for src in sources:
        session.add(
            QuestionSource(
                question_id=question_id,
                opportunity_id=src.opportunity_id,
                round_id=src.round_id,
            )
        )


def _question_dict(
    q: Question,
    opps: dict[int, Opportunity],
    rounds: dict[int, InterviewRound],
    resumes: dict[int, Resume],
    sources_by_q: dict[int, list[QuestionSource]],
) -> dict:
    data = jsonable_encoder(q)
    o = opps.get(q.opportunity_id) if q.opportunity_id else None
    data["opportunity"] = (
        {"id": o.id, "company": o.company, "position": o.position} if o else None
    )
    data["resume_name"] = resumes[q.resume_id].name if q.resume_id and q.resume_id in resumes else None
    srcs = sources_by_q.get(q.id, [])
    data["sources"] = [
        {
            "opportunity_id": s.opportunity_id,
            "round_id": s.round_id,
            "company": opps[s.opportunity_id].company if s.opportunity_id in opps else None,
            "position": opps[s.opportunity_id].position if s.opportunity_id in opps else None,
            "round_type": rounds[s.round_id].round_type
            if s.round_id is not None and s.round_id in rounds
            else None,
        }
        for s in srcs
    ]
    return data


def _load_dicts(questions: list[Question], session: Session) -> list[dict]:
    opps = {o.id: o for o in session.exec(select(Opportunity)).all()}
    rounds = {r.id: r for r in session.exec(select(InterviewRound)).all()}
    resumes = {r.id: r for r in session.exec(select(Resume)).all()}
    sources_by_q: dict[int, list[QuestionSource]] = {}
    for s in session.exec(select(QuestionSource)).all():
        sources_by_q.setdefault(s.question_id, []).append(s)
    return [
        _question_dict(q, opps, rounds, resumes, sources_by_q) for q in questions
    ]


def backfill_question_sources(session: Session) -> None:
    """把存量题目上的单一 opportunity_id 迁移为来源表记录（幂等）。"""
    existing = {(s.question_id, s.opportunity_id) for s in session.exec(select(QuestionSource)).all()}
    added = False
    for q in session.exec(select(Question)).all():
        if q.opportunity_id and (q.id, q.opportunity_id) not in existing:
            session.add(QuestionSource(question_id=q.id, opportunity_id=q.opportunity_id))
            added = True
    if added:
        session.commit()


@router.get("/questions/meta")
def question_meta(session: Session = Depends(get_session)):
    dims = list(DIMENSION_PRESETS)
    for row in session.exec(select(Question.dimension).distinct()).all():
        if row and row not in dims:
            dims.append(row)
    return {"dimensions": dims}


@router.get("/questions")
def list_questions(session: Session = Depends(get_session)):
    """返回全部题目（个人数据量级，筛选在前端做）。"""
    questions = session.exec(
        select(Question).order_by(Question.updated_at.desc())
    ).all()
    return {
        "items": _load_dicts(list(questions), session),
        "total": len(questions),
    }


@router.post("/questions")
def create_question(body: QuestionCreate, session: Session = Depends(get_session)):
    if body.difficulty not in DIFFICULTIES:
        raise HTTPException(status_code=400, detail="非法难度")
    if body.source not in SOURCES:
        raise HTTPException(status_code=400, detail="非法来源")
    if body.mastery not in MASTERY:
        raise HTTPException(status_code=400, detail="非法掌握状态")
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="题干不能为空")
    if body.self_rating is not None and not (1 <= body.self_rating <= 5):
        raise HTTPException(status_code=400, detail="自评分需在 1-5 之间")
    if body.sources:
        _validate_sources(session, body.sources)

    data = body.model_dump()
    sources = data.pop("sources") or []
    if sources:
        data["opportunity_id"] = sources[0]["opportunity_id"]
    q = Question(**data)
    session.add(q)
    session.flush()
    if sources:
        _replace_sources(session, q.id, [SourceIn(**s) for s in sources])
    session.commit()
    session.refresh(q)
    return _load_dicts([q], session)[0]


@router.patch("/questions/{question_id}")
def update_question(
    question_id: int, body: QuestionUpdate, session: Session = Depends(get_session)
):
    q = session.get(Question, question_id)
    if q is None:
        raise HTTPException(status_code=404, detail="题目不存在")
    changed = body.model_dump(exclude_unset=True)
    if "difficulty" in changed and changed["difficulty"] not in DIFFICULTIES:
        raise HTTPException(status_code=400, detail="非法难度")
    if "mastery" in changed and changed["mastery"] not in MASTERY:
        raise HTTPException(status_code=400, detail="非法掌握状态")
    if "self_rating" in changed and changed["self_rating"] is not None:
        if not (1 <= changed["self_rating"] <= 5):
            raise HTTPException(status_code=400, detail="自评分需在 1-5 之间")

    new_sources = changed.pop("sources", None)
    if new_sources is not None:
        sources = [SourceIn(**s) for s in new_sources]
        _validate_sources(session, sources)
        _replace_sources(session, q.id, sources)
        # 同步主来源字段，兼容旧的筛选/展示逻辑
        q.opportunity_id = sources[0].opportunity_id if sources else None

    for field, value in changed.items():
        setattr(q, field, value)
    q.updated_at = datetime.now()
    session.add(q)
    session.commit()
    session.refresh(q)
    return _load_dicts([q], session)[0]


@router.delete("/questions/{question_id}")
def delete_question(question_id: int, session: Session = Depends(get_session)):
    q = session.get(Question, question_id)
    if q is None:
        raise HTTPException(status_code=404, detail="题目不存在")
    for s in session.exec(
        select(QuestionSource).where(QuestionSource.question_id == question_id)
    ).all():
        session.delete(s)
    session.flush()  # 先落来源删除，避免外键约束先删主表报错
    session.delete(q)
    session.commit()
    return {"ok": True}
