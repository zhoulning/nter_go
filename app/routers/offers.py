"""Offer 信息的录入与查询（每个岗位最多一条 Offer 记录）。"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlmodel import Session, select

from app.database import get_session
from app.models import Offer, Opportunity

router = APIRouter()


class OfferUpsert(BaseModel):
    monthly_salary: Optional[float] = None  # 月薪（K）
    months: Optional[int] = None
    signing_bonus: Optional[str] = None
    stock: Optional[str] = None
    welfare: Optional[str] = None
    overtime: Optional[str] = None
    commute: Optional[str] = None
    score_salary: int = 3
    score_platform: int = 3
    score_growth: int = 3
    score_worklife: int = 3
    score_commute: int = 3
    note: Optional[str] = None

    @field_validator("score_salary", "score_platform", "score_growth", "score_worklife", "score_commute")
    @classmethod
    def _score_range(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError("评分范围为 1-5")
        return v


def _offer_dict(offer: Offer, opp: Opportunity | None) -> dict:
    data = {
        "id": offer.id,
        "opportunity_id": offer.opportunity_id,
        "monthly_salary": offer.monthly_salary,
        "months": offer.months,
        "signing_bonus": offer.signing_bonus,
        "stock": offer.stock,
        "welfare": offer.welfare,
        "overtime": offer.overtime,
        "commute": offer.commute,
        "score_salary": offer.score_salary,
        "score_platform": offer.score_platform,
        "score_growth": offer.score_growth,
        "score_worklife": offer.score_worklife,
        "score_commute": offer.score_commute,
        "note": offer.note,
        "company": opp.company if opp else None,
        "position": opp.position if opp else None,
        "city": opp.city if opp else None,
        "status": opp.status if opp else None,
        "salary_range": opp.salary_range if opp else None,
    }
    return data


@router.get("/offers")
def list_offers(session: Session = Depends(get_session)):
    """全部 Offer 记录，附带岗位的公司/岗位信息。"""
    rows = session.exec(select(Offer)).all()
    result = []
    for offer in rows:
        opp = session.get(Opportunity, offer.opportunity_id)
        result.append(_offer_dict(offer, opp))
    return {"items": result}


@router.put("/offers/{opportunity_id}")
def upsert_offer(opportunity_id: int, body: OfferUpsert, session: Session = Depends(get_session)):
    opp = session.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="岗位不存在")

    offer = session.exec(
        select(Offer).where(Offer.opportunity_id == opportunity_id)
    ).first()
    if offer is None:
        offer = Offer(opportunity_id=opportunity_id)
    for field, value in body.model_dump().items():
        setattr(offer, field, value)
    offer.updated_at = datetime.now()
    session.add(offer)
    session.commit()
    session.refresh(offer)
    return _offer_dict(offer, opp)


@router.delete("/offers/{opportunity_id}")
def delete_offer(opportunity_id: int, session: Session = Depends(get_session)):
    offer = session.exec(
        select(Offer).where(Offer.opportunity_id == opportunity_id)
    ).first()
    if offer is None:
        raise HTTPException(status_code=404, detail="该岗位还没有 Offer 记录")
    session.delete(offer)
    session.commit()
    return {"ok": True}
