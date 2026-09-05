"""题库 / 错题本的 CRUD API。"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session
from app.models import InterviewRound, Opportunity, Question, QuestionSource, Resume, User
from app.tracks import dimension_presets

router = APIRouter()

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


def _validate_sources(session: Session, sources: list[SourceIn], user: User) -> None:
    """校验来源里的岗位 / 轮次属于当前用户且从属关系正确。"""
    for src in sources:
        opp = session.get(Opportunity, src.opportunity_id)
        if opp is None or opp.user_id != user.id:
            raise HTTPException(status_code=400, detail="题目来源的岗位不存在")
        if src.round_id is not None:
            rnd = session.get(InterviewRound, src.round_id)
            if rnd is None or rnd.user_id != user.id or rnd.opportunity_id != src.opportunity_id:
                raise HTTPException(status_code=400, detail="轮次与岗位不匹配")


def _replace_sources(session: Session, question_id: int, sources: list[SourceIn], user_id: int) -> None:
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
                user_id=user_id,
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
    # 同一批题目必属同一用户，用第一题的归属过滤关联数据
    owner_id = questions[0].user_id if questions else None
    opps = {
        o.id: o
        for o in session.exec(select(Opportunity).where(Opportunity.user_id == owner_id)).all()
    }
    rounds = {
        r.id: r
        for r in session.exec(select(InterviewRound).where(InterviewRound.user_id == owner_id)).all()
    }
    resumes = {
        r.id: r for r in session.exec(select(Resume).where(Resume.user_id == owner_id)).all()
    }
    sources_by_q: dict[int, list[QuestionSource]] = {}
    for s in session.exec(select(QuestionSource).where(QuestionSource.user_id == owner_id)).all():
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
            session.add(
                QuestionSource(
                    question_id=q.id,
                    opportunity_id=q.opportunity_id,
                    user_id=q.user_id,
                )
            )
            added = True
    if added:
        session.commit()


@router.get("/questions/meta")
def question_meta(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    dims = dimension_presets(session)
    rows = session.exec(
        select(Question.dimension).where(Question.user_id == user.id).distinct()
    ).all()
    for row in rows:
        if row and row not in dims:
            dims.append(row)
    return {"dimensions": dims}


@router.get("/questions/{question_id}/origins")
def question_origins(
    question_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """回溯题目在模拟面试 / 真实面试录音中的原问原答（用于答案详情悬浮窗）。"""
    from app.origins import find_origins

    q = session.get(Question, question_id)
    if q is None or q.user_id != user.id:
        raise HTTPException(status_code=404, detail="题目不存在")
    return find_origins(session, q.content, user.id)


@router.get("/questions")
def list_questions(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    """返回当前用户的全部题目（个人数据量级，筛选在前端做）。"""
    questions = session.exec(
        select(Question)
        .where(Question.user_id == user.id)
        .order_by(Question.updated_at.desc())
    ).all()
    return {
        "items": _load_dicts(list(questions), session),
        "total": len(questions),
    }


@router.post("/questions")
def create_question(
    body: QuestionCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
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
        _validate_sources(session, body.sources, user)

    data = body.model_dump()
    # AI 生成的题目（题单预测 / 模拟面试存题）维度必须落在预设内，避免自造近似维度
    if data["source"] == "predicted" and data["dimension"] not in dimension_presets(session):
        data["dimension"] = "其他"
    sources = data.pop("sources") or []
    if sources:
        data["opportunity_id"] = sources[0]["opportunity_id"]
    q = Question(**data, user_id=user.id)
    session.add(q)
    session.flush()
    if sources:
        _replace_sources(session, q.id, [SourceIn(**s) for s in sources], user.id)
    session.commit()
    session.refresh(q)
    return _load_dicts([q], session)[0]


@router.patch("/questions/{question_id}")
def update_question(
    question_id: int,
    body: QuestionUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    q = session.get(Question, question_id)
    if q is None or q.user_id != user.id:
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
        _validate_sources(session, sources, user)
        _replace_sources(session, q.id, sources, user.id)
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
def delete_question(
    question_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    q = session.get(Question, question_id)
    if q is None or q.user_id != user.id:
        raise HTTPException(status_code=404, detail="题目不存在")
    for s in session.exec(
        select(QuestionSource).where(QuestionSource.question_id == question_id)
    ).all():
        session.delete(s)
    session.flush()  # 先落来源删除，避免外键约束先删主表报错
    session.delete(q)
    session.commit()
    return {"ok": True}
