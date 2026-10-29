"""Credits. Buying credits (Paystack) arrives in Phase 3."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import Settings
from ..deps import current_user, get_session, get_settings

router = APIRouter(prefix="/billing", tags=["billing"])


class Entry(BaseModel):
    delta: int
    reason: str
    created_at: datetime


class Balance(BaseModel):
    credits: int
    fix_cost: int
    history: list[Entry]


@router.get("", response_model=Balance)
def balance(user: models.User = Depends(current_user), session: Session = Depends(get_session),
            settings: Settings = Depends(get_settings)) -> Balance:
    rows = session.scalars(select(models.CreditEntry).where(models.CreditEntry.user_id == user.id)
                           .order_by(models.CreditEntry.created_at.desc()).limit(100))
    return Balance(credits=user.credits, fix_cost=settings.fix_cost,
                   history=[Entry(delta=r.delta, reason=r.reason, created_at=r.created_at) for r in rows])
