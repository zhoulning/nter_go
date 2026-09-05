"""面试日历：轮次事件的查询（按日期范围）与增删改。"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.auth import get_current_user
from app.database import get_session
from app.models import (
    ROUND_FAILED,
    ROUND_NO_SHOW,
    ROUND_PENDING,
    ROUND_PASSED,
    ROUND_TYPES,
    InterviewRound,
    Opportunity,
    User,
)

router = APIRouter()

ROUND_RESULTS = [ROUND_PENDING, ROUND_PASSED, ROUND_FAILED, ROUND_NO_SHOW]


class RoundCreate(BaseModel):
    opportunity_id: int
    round_type: str = "first"
    scheduled_at: datetime
    result: str = ROUND_PENDING
    note: Optional[str] = None


class RoundUpdate(BaseModel):
    round_type: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    result: Optional[str] = None
    note: Optional[str] = None


def _event_dict(r: InterviewRound, opp: Opportunity) -> dict:
    return {
        "id": r.id,
        "opportunity_id": r.opportunity_id,
        "company": opp.company,
        "position": opp.position,
        "round_type": r.round_type,
        "scheduled_at": r.scheduled_at.isoformat() if r.scheduled_at else None,
        "result": r.result,
        "note": r.note,
    }


def _get_round_owned(session: Session, round_id: int, user: User) -> InterviewRound:
    """取当前用户的轮次；越权或不存在一律 404。"""
    r = session.get(InterviewRound, round_id)
    if r is None or r.user_id != user.id:
        raise HTTPException(status_code=404, detail="轮次不存在")
    return r


@router.get("/calendar/events")
def calendar_events(
    start: str,
    end: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """返回当前用户 [start, end] 区间内已排期的轮次事件。参数为 ISO 日期或日期时间。"""
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式不正确，应为 ISO 格式")
    if len(end) == 10:  # 纯日期，取当天结束
        end_dt = end_dt + timedelta(days=1, seconds=-1)

    rounds = session.exec(
        select(InterviewRound)
        .where(
            InterviewRound.user_id == user.id,
            col(InterviewRound.scheduled_at) >= start_dt,
            col(InterviewRound.scheduled_at) <= end_dt,
        )
        .order_by(col(InterviewRound.scheduled_at))
    ).all()
    opps = {
        o.id: o
        for o in session.exec(select(Opportunity).where(Opportunity.user_id == user.id)).all()
    }
    events = [_event_dict(r, opps[r.opportunity_id]) for r in rounds if r.opportunity_id in opps]
    return {"events": events, "total": len(events)}


@router.post("/rounds")
def create_round(
    body: RoundCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    opp = session.get(Opportunity, body.opportunity_id)
    if opp is None or opp.user_id != user.id:
        raise HTTPException(status_code=404, detail="岗位不存在")
    if body.round_type not in ROUND_TYPES:
        raise HTTPException(status_code=400, detail="非法轮次类型")
    if body.result not in ROUND_RESULTS:
        raise HTTPException(status_code=400, detail="非法轮次结果")

    r = InterviewRound(
        opportunity_id=body.opportunity_id,
        round_type=body.round_type,
        scheduled_at=body.scheduled_at,
        actual_at=datetime.now() if body.result in (ROUND_PASSED, ROUND_FAILED, ROUND_NO_SHOW) else None,
        result=body.result,
        note=body.note,
        user_id=user.id,
    )
    session.add(r)
    session.commit()
    session.refresh(r)
    return _event_dict(r, opp)


@router.patch("/rounds/{round_id}")
def update_round(
    round_id: int,
    body: RoundUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    r = _get_round_owned(session, round_id, user)
    changed = body.model_dump(exclude_unset=True)
    if "round_type" in changed and changed["round_type"] not in ROUND_TYPES:
        raise HTTPException(status_code=400, detail="非法轮次类型")
    if "result" in changed and changed["result"] not in ROUND_RESULTS:
        raise HTTPException(status_code=400, detail="非法轮次结果")

    for field, value in changed.items():
        setattr(r, field, value)
    session.add(r)
    session.commit()
    session.refresh(r)
    opp = session.get(Opportunity, r.opportunity_id)
    return _event_dict(r, opp)


@router.delete("/rounds/{round_id}")
def delete_round(
    round_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    r = _get_round_owned(session, round_id, user)
    session.delete(r)
    session.commit()
    return {"ok": True}
