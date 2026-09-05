"""统计聚合。

- GET /stats/dashboard：首页全模块看板（指标卡、未来面试、待办、动态、漏斗速览）
- GET /stats/overview：转化分析（漏斗、轮次通过率、渠道效果、周趋势、周期指标、复盘得分趋势）
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session
from app.models import (
    ACTIVE_STATUSES,
    ROUND_FAILED,
    ROUND_NO_SHOW,
    ROUND_PENDING,
    ROUND_PASSED,
    ROUND_TYPES,
    STATUS_ACCEPTED,
    STATUS_APPLIED,
    STATUS_INTERVIEWING,
    STATUS_OFFER,
    STATUS_REJECTED,
    STATUS_WISHLIST,
    InterviewRound,
    MockInterview,
    Opportunity,
    Question,
    Recording,
    Resume,
    ReviewReport,
    User,
)

router = APIRouter()

# 走过「面试」环节：已进入面试中及之后，或存在任何正式面试轮次
_INTERVIEW_ROUND_TYPES = {"first", "second", "third", "comprehensive", "hr"}
# 到达「终面」环节：三面 / HR 面，或已到 Offer
_FINAL_ROUND_TYPES = {"third", "hr"}

_ROUND_LABELS = {
    "written": "笔试",
    "first": "一面",
    "second": "二面",
    "third": "三面",
    "comprehensive": "综合面",
    "hr": "HR 面",
    "other": "面试",
}


def _round_label(round_type: str) -> str:
    return _ROUND_LABELS.get(round_type, round_type)


def _start_of_today() -> datetime:
    now = datetime.now()
    return datetime(now.year, now.month, now.day)


def _funnel(opportunities: list[Opportunity], rounds: list[InterviewRound]) -> list[dict]:
    """投递 → 进入面试 → 到达终面 → Offer → 接受（含已挂掉 / 归档的岗位）。"""
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

    applied = [o for o in opportunities if o.status != STATUS_WISHLIST]
    interviewed = [o for o in applied if started_interview(o)]
    final = [o for o in applied if reached_final(o)]
    offers = [o for o in opportunities if o.status in (STATUS_OFFER, STATUS_ACCEPTED)]
    accepted = [o for o in opportunities if o.status == STATUS_ACCEPTED]
    return [
        {"key": "applied", "label": "投递", "count": len(applied)},
        {"key": "interviewed", "label": "进入面试", "count": len(interviewed)},
        {"key": "final", "label": "到达终面", "count": len(final)},
        {"key": "offer", "label": "Offer", "count": len(offers)},
        {"key": "accepted", "label": "接受", "count": len(accepted)},
    ]


def _is_wrong_question(q: Question) -> bool:
    """与题库「错题本」口径一致：掌握状态非已掌握，或自评分偏低。"""
    return q.mastery != "mastered" or (q.self_rating is not None and q.self_rating <= 3)


# ---------------------------------------------------------------- 首页看板


@router.get("/stats/dashboard")
def stats_dashboard(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    now = datetime.now()
    today_start = _start_of_today()
    week_end = today_start + timedelta(days=8)
    week_ago = now - timedelta(days=7)

    opportunities = session.exec(
        select(Opportunity).where(Opportunity.user_id == user.id)
    ).all()
    rounds = session.exec(
        select(InterviewRound).where(InterviewRound.user_id == user.id)
    ).all()
    questions = session.exec(
        select(Question).where(Question.user_id == user.id)
    ).all()
    resumes = session.exec(select(Resume).where(Resume.user_id == user.id)).all()
    recordings = session.exec(
        select(Recording).where(Recording.user_id == user.id)
    ).all()
    reviews = session.exec(
        select(ReviewReport).where(ReviewReport.user_id == user.id)
    ).all()
    mocks = session.exec(
        select(MockInterview).where(MockInterview.user_id == user.id)
    ).all()

    opp_by_id = {o.id: o for o in opportunities}
    active_opps = [o for o in opportunities if o.status in ACTIVE_STATUSES]
    rounds_by_opp: dict[int, list[InterviewRound]] = {}
    for r in rounds:
        rounds_by_opp.setdefault(r.opportunity_id, []).append(r)

    # ---- 指标卡 ----
    review_scores = [r.overall_score for r in reviews if r.overall_score]
    finished = [r for r in rounds if r.result in (ROUND_PASSED, ROUND_FAILED, ROUND_NO_SHOW)]
    passed = [r for r in finished if r.result == ROUND_PASSED]
    cards = {
        "active_opportunities": len(active_opps),
        "upcoming_interviews": 0,  # 与 upcoming 列表一起算
        "applied_week": sum(
            1 for o in opportunities if o.applied_at and o.applied_at >= week_ago
        ),
        "offers": sum(1 for o in opportunities if o.status in (STATUS_OFFER, STATUS_ACCEPTED)),
        "questions_total": len(questions),
        "questions_todo": sum(1 for q in questions if _is_wrong_question(q) and not q.review_done),
        "resumes": len(resumes),
        "resume_best_score": max((r.score for r in resumes if r.score is not None), default=None),
        "recordings": len(recordings),
        "recordings_todo": sum(
            1
            for rec in recordings
            if rec.status == "transcribed" and rec.review_status == "none"
        ),
        "review_avg_score": round(sum(review_scores) / len(review_scores)) if review_scores else None,
        "interviews_done": len(finished),
        "interview_pass_rate": (
            round(len(passed) / len(finished) * 100) if finished else None
        ),
    }

    # ---- 未来 7 天面试 ----
    upcoming = []
    for r in rounds:
        if r.result != ROUND_PENDING or not r.scheduled_at:
            continue
        if not (today_start <= r.scheduled_at < week_end):
            continue
        opp = opp_by_id.get(r.opportunity_id)
        if not opp:
            continue
        upcoming.append(
            {
                "round_id": r.id,
                "opportunity_id": opp.id,
                "company": opp.company,
                "position": opp.position,
                "round_type": r.round_type,
                "scheduled_at": r.scheduled_at.isoformat(),
            }
        )
    upcoming.sort(key=lambda x: x["scheduled_at"])
    cards["upcoming_interviews"] = len(upcoming)

    # ---- 待办 ----
    result_todo = []
    for r in rounds:
        if r.result != ROUND_PENDING or not r.scheduled_at:
            continue
        if r.scheduled_at >= today_start:
            continue
        opp = opp_by_id.get(r.opportunity_id)
        if not opp or opp.status not in ACTIVE_STATUSES:
            continue
        result_todo.append(
            {
                "opportunity_id": opp.id,
                "company": opp.company,
                "round_type": r.round_type,
                "scheduled_at": r.scheduled_at.isoformat(),
            }
        )
    result_todo.sort(key=lambda x: x["scheduled_at"])

    overdue = [
        {
            "opportunity_id": o.id,
            "company": o.company,
            "position": o.position,
            "days": (now - o.created_at).days,
        }
        for o in active_opps
        if o.status == STATUS_WISHLIST and now - o.created_at > timedelta(days=7)
    ]
    overdue.sort(key=lambda x: x["days"], reverse=True)

    missing_jd = [
        {"opportunity_id": o.id, "company": o.company, "position": o.position}
        for o in active_opps
        if o.status != STATUS_WISHLIST and not o.jd_text
    ]

    recordings_todo = [
        {
            "id": rec.id,
            "company": opp_by_id[rec.opportunity_id].company if rec.opportunity_id in opp_by_id else None,
            "title": rec.filename,
            "created_at": rec.created_at.isoformat(),
        }
        for rec in recordings
        if rec.status == "transcribed" and rec.review_status == "none"
    ]
    recordings_todo.sort(key=lambda x: x["created_at"], reverse=True)

    resumes_todo = [
        {"id": r.id, "name": r.name} for r in resumes if r.score is None
    ]

    todos = {
        "round_results": result_todo[:8],
        "round_results_total": len(result_todo),
        "overdue_wishlist": overdue[:8],
        "overdue_total": len(overdue),
        "missing_jd": missing_jd[:8],
        "missing_jd_total": len(missing_jd),
        "questions_todo": cards["questions_todo"],
        "recordings_review": recordings_todo[:8],
        "recordings_total": len(recordings_todo),
        "resumes_no_review": resumes_todo[:8],
        "resumes_total": len(resumes_todo),
    }

    # ---- 最近动态（跨模块时间线）----
    events: list[tuple[datetime, str, str, int | None]] = []
    for o in opportunities:
        events.append((o.created_at, "opp_created", f"新增岗位 {o.company} · {o.position}", o.id))
        if o.applied_at:
            events.append((o.applied_at, "applied", f"投递 {o.company} · {o.position}", o.id))
        if o.status == STATUS_OFFER:
            events.append((o.status_changed_at, "offer", f"{o.company} 拿下 Offer 🎉", o.id))
        elif o.status == STATUS_ACCEPTED:
            events.append((o.status_changed_at, "accepted", f"{o.company} 接受 Offer", o.id))
    for r in rounds:
        opp = opp_by_id.get(r.opportunity_id)
        if not opp:
            continue
        label = _round_label(r.round_type)
        if r.scheduled_at and r.result == ROUND_PENDING:
            events.append((r.created_at, "round_scheduled", f"约了 {opp.company} {label}", opp.id))
        if r.result == ROUND_PASSED:
            ts = r.actual_at or r.scheduled_at or r.created_at
            events.append((ts, "round_passed", f"{opp.company} {label}通过 ✅", opp.id))
        elif r.result == ROUND_FAILED:
            ts = r.actual_at or r.scheduled_at or r.created_at
            events.append((ts, "round_failed", f"{opp.company} {label}未通过", opp.id))
    for rec in recordings:
        opp = opp_by_id.get(rec.opportunity_id)
        company = opp.company if opp else "未知公司"
        kind_text = "文字复盘" if rec.kind == "text" else "面试录音"
        events.append((rec.created_at, "recording", f"上传 {company} {kind_text}", rec.opportunity_id))
    review_by_recording = {rv.recording_id: rv for rv in reviews}
    for rv in reviews:
        rec = next((x for x in recordings if x.id == rv.recording_id), None)
        if not rec:
            continue
        opp = opp_by_id.get(rec.opportunity_id)
        company = opp.company if opp else "未知公司"
        events.append(
            (rv.created_at, "review", f"{company} 复盘报告生成 · {rv.overall_score} 分", rec.opportunity_id)
        )
    for r in resumes:
        events.append((r.created_at, "resume", f"上传简历「{r.name}」", None))
    for m in mocks:
        if m.status != "finished" or not m.finished_at:
            continue
        opp = opp_by_id.get(m.opportunity_id)
        company = opp.company if opp else ""
        score = f" · {m.overall_score} 分" if m.overall_score else ""
        events.append((m.finished_at, "mock", f"{company} 完成模拟面试{score}", m.opportunity_id))

    events.sort(key=lambda e: e[0], reverse=True)
    activity = [
        {
            "ts": ts.isoformat(),
            "kind": kind,
            "text": text,
            "opportunity_id": opp_id,
        }
        for ts, kind, text, opp_id in events[:12]
    ]

    return {
        "generated_at": now.isoformat(),
        "cards": cards,
        "upcoming": upcoming,
        "todos": todos,
        "activity": activity,
        "funnel": _funnel(opportunities, rounds),
    }


# ---------------------------------------------------------------- 转化分析


@router.get("/stats/overview")
def stats_overview(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    now = datetime.now()
    opportunities = session.exec(
        select(Opportunity).where(Opportunity.user_id == user.id)
    ).all()
    rounds = session.exec(
        select(InterviewRound).where(InterviewRound.user_id == user.id)
    ).all()
    recordings = session.exec(
        select(Recording).where(Recording.user_id == user.id)
    ).all()
    reviews = session.exec(
        select(ReviewReport).where(ReviewReport.user_id == user.id)
    ).all()
    opp_by_id = {o.id: o for o in opportunities}

    funnel = _funnel(opportunities, rounds)

    # ---- 状态分布 ----
    by_status: dict[str, int] = {}
    for o in opportunities:
        by_status[o.status] = by_status.get(o.status, 0) + 1

    # ---- 面试轮次通过率（只算已出结果的场次）----
    round_stats: dict[str, dict] = {}
    for r in rounds:
        if r.result not in (ROUND_PASSED, ROUND_FAILED, ROUND_NO_SHOW):
            continue
        st = round_stats.setdefault(
            r.round_type, {"round_type": r.round_type, "total": 0, "passed": 0, "failed": 0, "no_show": 0}
        )
        st["total"] += 1
        st[r.result] += 1
    rounds_out = []
    for rt in ROUND_TYPES:
        if rt not in round_stats:
            continue
        st = round_stats.pop(rt)
        st["pass_rate"] = round(st["passed"] / st["total"] * 100) if st["total"] else None
        rounds_out.append(st)
    rounds_out.extend(round_stats.values())  # 兜底：未知类型也展示

    # ---- 周期与响应 ----
    apply_to_interview: list[float] = []
    for o in opportunities:
        if o.status == STATUS_WISHLIST or not o.applied_at:
            continue
        scheduled = [
            r.scheduled_at
            for r in rounds
            if r.opportunity_id == o.id and r.scheduled_at is not None
        ]
        if not scheduled:
            continue
        days = (min(scheduled) - o.applied_at).total_seconds() / 86400
        if days >= 0:
            apply_to_interview.append(days)
    apply_to_offer: list[float] = []
    for o in opportunities:
        if o.status not in (STATUS_OFFER, STATUS_ACCEPTED) or not o.applied_at:
            continue
        days = (o.status_changed_at - o.applied_at).total_seconds() / 86400
        if days >= 0:
            apply_to_offer.append(days)
    responded = sum(
        1
        for o in opportunities
        if o.status in (STATUS_INTERVIEWING, STATUS_OFFER, STATUS_ACCEPTED, STATUS_REJECTED)
    )
    no_response = sum(1 for o in opportunities if o.status == "no_response")
    waiting = sum(1 for o in opportunities if o.status == STATUS_APPLIED)
    cycles = {
        "apply_to_interview_days": (
            round(sum(apply_to_interview) / len(apply_to_interview), 1)
            if apply_to_interview
            else None
        ),
        "apply_to_offer_days": (
            round(sum(apply_to_offer) / len(apply_to_offer), 1) if apply_to_offer else None
        ),
        # 响应率 = 有明确回音（进面或被拒）占已出回音投递的比例，仍在等待的不计入
        "response_rate": (
            round(responded / (responded + no_response) * 100)
            if responded + no_response
            else None
        ),
        "responded": responded,
        "no_response": no_response,
        "waiting": waiting,
    }

    # ---- 渠道效果（仅统计已投出的岗位）----
    channels_map: dict[str, dict] = {}
    for o in (o for o in opportunities if o.status != STATUS_WISHLIST):
        key = o.channel or "未记录"
        stat = channels_map.setdefault(
            key, {"channel": key, "total": 0, "interviewed": 0, "offers": 0}
        )
        stat["total"] += 1
        if o.status in (STATUS_INTERVIEWING, STATUS_OFFER, STATUS_ACCEPTED) or any(
            r.round_type in _INTERVIEW_ROUND_TYPES
            for r in rounds
            if r.opportunity_id == o.id
        ):
            stat["interviewed"] += 1
        if o.status in (STATUS_OFFER, STATUS_ACCEPTED):
            stat["offers"] += 1
    channels = sorted(channels_map.values(), key=lambda x: x["total"], reverse=True)

    # ---- 近 12 周活跃（自然周，周一为起点）----
    today = now.date()
    monday = today - timedelta(days=today.weekday())
    weeks: list[dict] = []
    week_buckets: list[tuple[datetime, datetime]] = []
    for i in range(11, -1, -1):
        start = datetime.combine(monday - timedelta(weeks=i), datetime.min.time())
        end = start + timedelta(weeks=1)
        week_buckets.append((start, end))
        weeks.append({"week": f"{start.month}/{start.day}", "applied": 0, "interviews": 0})
    for o in (o for o in opportunities if o.status != STATUS_WISHLIST):
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

    # ---- 复盘得分趋势（面试表现是否在变好）----
    review_by_recording = {rv.recording_id: rv for rv in reviews}
    review_trend = []
    for rec in sorted(recordings, key=lambda x: x.created_at):
        rv = review_by_recording.get(rec.id)
        if not rv:
            continue
        opp = opp_by_id.get(rec.opportunity_id)
        review_trend.append(
            {
                "date": f"{rv.created_at.month}/{rv.created_at.day}",
                "score": rv.overall_score,
                "company": opp.company if opp else None,
            }
        )

    return {
        "funnel": funnel,
        "by_status": by_status,
        "channels": channels,
        "weekly": weeks,
        "rounds": rounds_out,
        "cycles": cycles,
        "review_trend": review_trend,
        "generated_at": now.isoformat(),
    }
