"""统计聚合：转化漏斗、状态分布、周活跃、渠道效果。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.database import get_session
from app.models import (
    ARCHIVED_STATUSES,
    STATUS_ACCEPTED,
    STATUS_APPLIED,
    STATUS_INTERVIEWING,
    STATUS_OFFER,
    STATUS_WISHLIST,
    InterviewRound,
    Opportunity,
)

router = APIRouter()

# 走过「面试」环节：已进入面试中及之后，或存在任何正式面试轮次
_INTERVIEW_ROUND_TYPES = {"first", "second", "third", "cross", "hr"}
# 到达「终面」环节：三面 / 交叉面 / HR 面，或已到 Offer
_FINAL_ROUND_TYPES = {"third", "cross", "hr"}


def _overview(session: Session) -> dict:
    now = datetime.now()
    opportunities = session.exec(select(Opportunity)).all()
    rounds = session.exec(select(InterviewRound)).all()
    rounds_by_opp: dict[int, list[InterviewRound]] = {}
    for r in rounds:
        rounds_by_opp.setdefault(r.opportunity_id, []).append(r)

    def started_interview(o: Opportunity) -> bool:
        if o.status in (STATUS_INTERVIEWING, STATUS_OFFER, STATUS_ACCEPTED):
            return True
        return any(r.round_type in _INTERVIEW_ROUND_TYPES for r in rounds_by_opp.get(o.id, []))

    def reached_final(o: Opportunity) -> bool:
        if o.status in (STATUS_OFFER, STATUS_ACCEPTED):
            return True
        return any(r.round_type in _FINAL_ROUND_TYPES for r in rounds_by_opp.get(o.id, []))

    # ---- 转化漏斗 ----
    applied = [o for o in opportunities if o.status != STATUS_WISHLIST]
    interviewed = [o for o in applied if started_interview(o)]
    final = [o for o in applied if reached_final(o)]
    offers = [o for o in opportunities if o.status in (STATUS_OFFER, STATUS_ACCEPTED)]
    accepted = [o for o in opportunities if o.status == STATUS_ACCEPTED]
    funnel = [
        {"key": "applied", "label": "投递", "count": len(applied)},
        {"key": "interviewed", "label": "进入面试", "count": len(interviewed)},
        {"key": "final", "label": "到达终面", "count": len(final)},
        {"key": "offer", "label": "Offer", "count": len(offers)},
        {"key": "accepted", "label": "接受", "count": len(accepted)},
    ]

    # ---- 状态分布 ----
    by_status: dict[str, int] = {}
    for o in opportunities:
        by_status[o.status] = by_status.get(o.status, 0) + 1

    # ---- 渠道效果（仅统计已投出的岗位）----
    channels_map: dict[str, dict] = {}
    for o in applied:
        key = o.channel or "未记录"
        stat = channels_map.setdefault(key, {"channel": key, "total": 0, "interviewed": 0, "offers": 0})
        stat["total"] += 1
        if started_interview(o):
            stat["interviewed"] += 1
        if o.status in (STATUS_OFFER, STATUS_ACCEPTED):
            stat["offers"] += 1
    channels = sorted(channels_map.values(), key=lambda x: x["total"], reverse=True)

    # ---- 近 8 周活跃（自然周，周一为起点）----
    today = now.date()
    monday = today - timedelta(days=today.weekday())
    weeks: list[dict] = []
    week_buckets: list[tuple[datetime, datetime]] = []
    for i in range(7, -1, -1):
        start = datetime.combine(monday - timedelta(weeks=i), datetime.min.time())
        end = start + timedelta(weeks=1)
        week_buckets.append((start, end))
        weeks.append({"week": f"{start.month}/{start.day}", "applied": 0, "interviews": 0})
    for o in applied:
        t = o.applied_at or o.created_at
        for idx, (start, end) in enumerate(week_buckets):
            if start <= t < end:
                weeks[idx]["applied"] += 1
                break
    for r in rounds:
        if r.scheduled_at is None:
            continue
        for idx, (start, end) in enumerate(week_buckets):
            if start <= r.scheduled_at < end:
                weeks[idx]["interviews"] += 1
                break

    return {
        "funnel": funnel,
        "by_status": by_status,
        "channels": channels,
        "weekly": weeks,
        "generated_at": now.isoformat(),
    }


@router.get("/stats/overview")
def stats_overview(session: Session = Depends(get_session)):
    return _overview(session)
