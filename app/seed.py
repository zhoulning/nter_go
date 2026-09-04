"""首次启动时写入一批贴近真实的种子数据，让看板开箱就有内容。"""
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.models import (
    InterviewRound,
    Opportunity,
    STATUS_ACCEPTED,
    STATUS_APPLIED,
    STATUS_INTERVIEWING,
    STATUS_OFFER,
    STATUS_WISHLIST,
)



def _at(days_offset: int, hour: int = 0, minute: int = 0) -> datetime:
    """相对今天 days_offset 天的指定时刻。"""
    day = datetime.now() + timedelta(days=days_offset)
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


SEED_OPPORTUNITIES = [
    # (公司, 岗位, 部门, 城市, 薪资, 渠道, 优先级, 状态, 状态变更距今天数, 轮次列表)
    (
        "字节跳动", "后端开发工程师-电商", "电商业务", "北京", "35-55K·16薪", "内推", "S",
        STATUS_INTERVIEWING, 12,
        [
            ("first", _at(-7, 14, 0), "passed", "节奏很快，项目和八股对半，聊了 55 分钟"),
            ("second", _at(1, 14, 0), "pending", None),
        ],
    ),
    (
        "小红书", "服务端开发-社区", "社区技术部", "上海", "35-60K·16薪", "内推", "S",
        STATUS_INTERVIEWING, 8,
        [
            ("first", _at(-3, 10, 30), "passed", "主要深挖了推荐链路的项目细节"),
            ("second", _at(2, 10, 30), "pending", None),
        ],
    ),
    (
        "拼多多", "服务端开发工程师", "基础电商", "上海", "40-70K·16薪", "猎聘", "S",
        STATUS_APPLIED, 5,
        [("written", _at(3, 19, 0), "pending", "线上笔试，算法 4 道，记得提前装好摄像头插件")],
    ),
    (
        "腾讯", "后端开发工程师-PCG", "PCG 技术线", "深圳", "30-50K·16薪", "BOSS直聘", "A",
        STATUS_APPLIED, 4,
        [("written", _at(1, 15, 0), "pending", None)],
    ),
    (
        "阿里巴巴", "Java 开发专家-淘天", "淘天集团", "杭州", "35-60K·16薪（P7）", "猎聘", "S",
        STATUS_APPLIED, 6, [],
    ),
    (
        "微软中国", "Software Engineer II", "Azure", "北京", "45-70K·14薪", "官网", "A",
        STATUS_APPLIED, 3, [],
    ),
    (
        "快手", "Java 后端开发-主站", "主站技术", "北京", "30-50K·15薪", "BOSS直聘", "A",
        STATUS_OFFER, 2,
        [
            ("first", _at(-10, 11, 0), "passed", None),
            ("second", _at(-6, 15, 0), "passed", "系统设计：短链服务"),
            ("hr", _at(-2, 16, 0), "passed", "谈薪环节，争取到了签字费"),
        ],
    ),
    (
        "理想汽车", "资深 Java 工程师", "智能驾驶", "北京", "35-55K·15薪", "猎聘", "A",
        STATUS_ACCEPTED, 1,
        [("hr", _at(-9, 14, 0), "passed", None)],
    ),
    (
        "美团", "后端开发工程师-到店", "到店事业群", "北京", "28-45K·15.5薪", "官网", "B",
        STATUS_WISHLIST, 0, [],
    ),
    (
        "Shopee", "后端开发工程师", "支付平台", "深圳", "30-55K·14薪", "脉脉", "B",
        STATUS_WISHLIST, 1, [],
    ),
]


def seed_if_empty(session: Session) -> bool:
    """数据库为空时写入种子数据；返回是否执行了写入。"""
    if session.exec(select(Opportunity)).first() is not None:
        return False

    for company, position, dept, city, salary, channel, priority, status, days_ago, rounds in SEED_OPPORTUNITIES:
        changed_at = datetime.now() - timedelta(days=days_ago)
        if status == STATUS_APPLIED:
            applied_at = changed_at
        elif status in (STATUS_INTERVIEWING, STATUS_OFFER, STATUS_ACCEPTED):
            applied_at = changed_at - timedelta(days=3)  # 投递早于最新状态变更几天
        else:
            applied_at = None
        opp = Opportunity(
            company=company,
            position=position,
            department=dept,
            city=city,
            salary_range=salary,
            channel=channel,
            priority=priority,
            status=status,
            status_changed_at=changed_at,
            applied_at=applied_at,
            created_at=changed_at - timedelta(days=2),
            updated_at=changed_at,
        )
        session.add(opp)
        session.flush()  # 拿到 opp.id
        for round_type, scheduled_at, result, note in rounds:
            session.add(
                InterviewRound(
                    opportunity_id=opp.id,
                    round_type=round_type,
                    scheduled_at=scheduled_at,
                    actual_at=None if result == "pending" else scheduled_at,
                    result=result,
                    note=note,
                )
            )
    session.commit()
    return True


# Offer 演示数据：公司名 -> Offer 信息
SEED_OFFERS = {
    "快手": dict(
        monthly_salary=40, months=15,
        signing_bonus="签字费 30K，分两年发放",
        stock="无",
        welfare="公积金 12%，额外商业保险",
        overtime="大小周",
        commute="地铁 45 分钟",
        score_salary=4, score_platform=4, score_growth=3, score_worklife=3, score_commute=3,
        note="HR 口头说一年内有机会晋升",
    ),
    "理想汽车": dict(
        monthly_salary=45, months=15,
        signing_bonus="无",
        stock="期权若干（4 年归属）",
        welfare="公积金 12% + 餐补",
        overtime="约 980，偶尔周末",
        commute="通勤 70 分钟（较远）",
        score_salary=4, score_platform=3, score_growth=4, score_worklife=3, score_commute=2,
        note="智驾业务扩张快，成长性看好",
    ),
}


def seed_offers_if_empty(session: Session) -> bool:
    """Offer 表为空时，为种子数据里已到 Offer 阶段的岗位补演示记录。"""
    from sqlmodel import select

    from app.models import Offer

    if session.exec(select(Offer)).first() is not None:
        return False

    opps = session.exec(select(Opportunity)).all()
    by_company = {o.company: o for o in opps}
    added = False
    for company, payload in SEED_OFFERS.items():
        opp = by_company.get(company)
        if opp is None or opp.status not in (STATUS_OFFER, STATUS_ACCEPTED):
            continue
        session.add(Offer(opportunity_id=opp.id, **payload))
        added = True
    if added:
        session.commit()
    return added
