"""站内通知 REST API：账号事件通知（入库）+ 面试日程提醒（按日历数据实时计算）。"""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.auth import get_current_user
from app.database import get_session
from app.models import InterviewRound, Notification, Opportunity, ROUND_PENDING, User

router = APIRouter()


@router.get("/notifications/summary")
def notification_summary(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """铃铛面板一次拉全：未读数 + 最近通知 + 今日/明日面试提醒。"""
    notifications = session.exec(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(col(Notification.created_at).desc(), col(Notification.id).desc())
        .limit(30)
    ).all()
    unread = len(
        session.exec(
            select(Notification.id).where(
                Notification.user_id == user.id, Notification.read == False  # noqa: E712
            )
        ).all()
    )
    return {
        "unread_count": unread,
        "items": [
            {
                "id": n.id,
                "type": n.type,
                "title": n.title,
                "body": n.body,
                "read": n.read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifications
        ],
        "interview_reminders": _interview_reminders(session, user.id),
    }


def _interview_reminders(session: Session, user_id: int) -> List[dict]:
    """今日与明天的待面试轮次（含未过期的 pending）。"""
    now = datetime.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = day_start + timedelta(days=2)  # 今天 00:00 ~ 明天 24:00
    rows = session.exec(
        select(InterviewRound, Opportunity)
        .join(Opportunity, Opportunity.id == InterviewRound.opportunity_id)
        .where(
            Opportunity.user_id == user_id,
            col(InterviewRound.scheduled_at).is_not(None),
            InterviewRound.scheduled_at >= day_start,
            InterviewRound.scheduled_at < window_end,
        )
        .order_by(col(InterviewRound.scheduled_at).asc())
    ).all()
    reminders = []
    tomorrow = day_start + timedelta(days=1)
    for rnd, opp in rows:
        scheduled = rnd.scheduled_at
        if not scheduled:
            continue
        day_label = "今天" if scheduled < tomorrow else "明天"
        reminders.append(
            {
                "round_id": rnd.id,
                "opportunity_id": opp.id,
                "company": opp.company,
                "position": opp.position,
                "round_type": rnd.round_type,
                "scheduled_at": scheduled.isoformat(),
                "day_label": day_label,
                "time_text": scheduled.strftime("%H:%M"),
                "note": rnd.note,
                "is_past": scheduled < now,
                "pending": rnd.result == ROUND_PENDING,
            }
        )
    return reminders


class ReadPayload(BaseModel):
    ids: Optional[List[int]] = None  # 为空 = 全部已读


@router.post("/notifications/read")
def mark_read(
    body: ReadPayload,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    query = select(Notification).where(Notification.user_id == user.id, Notification.read == False)  # noqa: E712
    if body.ids:
        query = query.where(col(Notification.id).in_(body.ids))
    rows = session.exec(query).all()
    for n in rows:
        n.read = True
        session.add(n)
    session.commit()
    return {"updated": len(rows)}


@router.delete("/notifications/{notification_id}")
def delete_notification(
    notification_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    n = session.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise HTTPException(status_code=404, detail="通知不存在")
    session.delete(n)
    session.commit()
    return {"ok": True}
