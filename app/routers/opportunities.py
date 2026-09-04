"""岗位与面试轮次的 REST API。"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.database import get_session
from app.models import (
    ACTIVE_STATUSES,
    ARCHIVED_STATUSES,
    ROUND_TYPES,
    STATUS_APPLIED,
    InterviewRound,
    Opportunity,
    Resume,
    ROUND_PENDING,
)

router = APIRouter()


class OpportunityCreate(BaseModel):
    company: str
    position: str
    department: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    salary_range: Optional[str] = None
    channel: Optional[str] = None
    priority: str = "B"
    status: str = "wishlist"
    applied_at: Optional[datetime] = None
    resume_id: Optional[int] = None
    jd_text: Optional[str] = None
    note: Optional[str] = None


class OpportunityUpdate(BaseModel):
    company: Optional[str] = None
    position: Optional[str] = None
    department: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    salary_range: Optional[str] = None
    channel: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    applied_at: Optional[datetime] = None
    resume_id: Optional[int] = None
    jd_text: Optional[str] = None
    note: Optional[str] = None


def _get_opportunity(session: Session, opportunity_id: int) -> Opportunity:
    opp = session.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return opp


def _round_dict(r: InterviewRound) -> dict:
    return {
        "id": r.id,
        "round_type": r.round_type,
        "scheduled_at": r.scheduled_at.isoformat() if r.scheduled_at else None,
        "actual_at": r.actual_at.isoformat() if r.actual_at else None,
        "result": r.result,
        "note": r.note,
    }


def _resume_brief(resume: Optional[Resume]) -> Optional[dict]:
    if resume is None:
        return None
    return {
        "id": resume.id,
        "name": resume.name,
        "filename": resume.filename,
        "ext": resume.ext,
        "is_default": resume.is_default,
    }


def _opp_dict(
    opp: Opportunity,
    rounds: list[InterviewRound],
    now: datetime,
    resume: Optional[Resume] = None,
) -> dict:
    data = jsonable_encoder(opp)
    data["rounds"] = [_round_dict(r) for r in rounds]
    data["next_event"] = next(
        (
            _round_dict(r)
            for r in rounds
            if r.scheduled_at and r.scheduled_at >= now and r.result == ROUND_PENDING
        ),
        None,
    )
    data["resume"] = _resume_brief(resume)
    return data


@router.get("/opportunities")
def list_opportunities(session: Session = Depends(get_session)):
    """返回全部未归档岗位，附带轮次与下一场面试。"""
    now = datetime.now()
    opportunities = session.exec(
        select(Opportunity).where(col(Opportunity.status).notin_(ARCHIVED_STATUSES))
    ).all()
    rounds = session.exec(select(InterviewRound).order_by(col(InterviewRound.scheduled_at))).all()
    rounds_by_opp: dict[int, list[InterviewRound]] = {}
    for r in rounds:
        rounds_by_opp.setdefault(r.opportunity_id, []).append(r)
    resumes = {r.id: r for r in session.exec(select(Resume)).all()}

    return {
        "items": [
            _opp_dict(
                opp,
                rounds_by_opp.get(opp.id, []),
                now,
                resume=resumes.get(opp.resume_id) if opp.resume_id else None,
            )
            for opp in opportunities
        ],
        "total": len(opportunities),
    }


@router.post("/opportunities")
def create_opportunity(body: OpportunityCreate, session: Session = Depends(get_session)):
    if body.status not in ACTIVE_STATUSES:
        raise HTTPException(status_code=400, detail="非法状态")
    data = body.model_dump()
    if data["status"] == STATUS_APPLIED and data.get("applied_at") is None:
        data["applied_at"] = datetime.now()  # 记录投递时间
    resume = session.get(Resume, data["resume_id"]) if data.get("resume_id") else None
    if data.get("resume_id") and resume is None:
        raise HTTPException(status_code=400, detail="关联的简历不存在")
    opp = Opportunity(**data)
    session.add(opp)
    session.commit()
    session.refresh(opp)
    return _opp_dict(opp, [], datetime.now(), resume=resume)


@router.patch("/opportunities/{opportunity_id}")
def update_opportunity(
    opportunity_id: int, body: OpportunityUpdate, session: Session = Depends(get_session)
):
    opp = _get_opportunity(session, opportunity_id)
    # 只更新请求里出现的字段；显式传 null 表示清空该字段
    changed = body.model_dump(exclude_unset=True)
    if not changed:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")

    if "status" in changed and changed["status"] not in ACTIVE_STATUSES + ARCHIVED_STATUSES:
        raise HTTPException(status_code=400, detail="非法状态")

    old_status = opp.status
    for field, value in changed.items():
        setattr(opp, field, value)
    if "status" in changed and changed["status"] != old_status:
        opp.status_changed_at = datetime.now()
        # 首次进入「已投递」且未手动指定时间时，自动记录投递时间
        if changed["status"] == STATUS_APPLIED and opp.applied_at is None and "applied_at" not in changed:
            opp.applied_at = datetime.now()
    if "resume_id" in changed and changed["resume_id"] is not None:
        if session.get(Resume, changed["resume_id"]) is None:
            raise HTTPException(status_code=400, detail="关联的简历不存在")

    opp.updated_at = datetime.now()
    session.add(opp)
    session.commit()
    session.refresh(opp)

    rounds = session.exec(
        select(InterviewRound)
        .where(col(InterviewRound.opportunity_id) == opp.id)
        .order_by(col(InterviewRound.scheduled_at))
    ).all()
    resume = session.get(Resume, opp.resume_id) if opp.resume_id else None
    return _opp_dict(opp, list(rounds), datetime.now(), resume=resume)


@router.delete("/opportunities/{opportunity_id}")
def delete_opportunity(opportunity_id: int, session: Session = Depends(get_session)):
    opp = _get_opportunity(session, opportunity_id)
    rounds = session.exec(
        select(InterviewRound).where(col(InterviewRound.opportunity_id) == opp.id)
    ).all()
    for r in rounds:
        session.delete(r)
    session.delete(opp)
    session.commit()
    return {"ok": True}


@router.get("/stats")
def stats(session: Session = Depends(get_session)):
    """首页/看板顶部用的汇总统计。"""
    now = datetime.now()
    opportunities = session.exec(select(Opportunity)).all()
    by_status = {s: 0 for s in ACTIVE_STATUSES + ARCHIVED_STATUSES}
    for opp in opportunities:
        by_status[opp.status] = by_status.get(opp.status, 0) + 1

    soon = now + timedelta(days=7)
    upcoming = session.exec(
        select(InterviewRound).where(
            col(InterviewRound.scheduled_at) >= now,
            col(InterviewRound.scheduled_at) <= soon,
            col(InterviewRound.result) == ROUND_PENDING,
        )
    ).all()
    return {"by_status": by_status, "upcoming_7d": len(upcoming), "total": len(opportunities)}
