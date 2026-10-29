"""Rulebooks: built-in ones, a user's own, and the shared library."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models
from ..deps import current_user, get_session, optional_user
from ..rulebooks import BUILTIN, builtin_list, can_read, raw_data, resolve, validate_data

router = APIRouter(prefix="/rulebooks", tags=["rulebooks"])


class RulebookIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    institution: str = Field(default="", max_length=200)
    department: str = Field(default="", max_length=200)
    data: dict  # the rulebook; usually {"extends": "default", ...changes}
    visibility: Literal["private", "shared", "public"] = "private"


class RulebookSummary(BaseModel):
    ref: str
    name: str
    description: str = ""
    institution: str = ""
    department: str = ""
    builtin: bool = False
    verified: bool = False
    visibility: str = "public"
    mine: bool = False
    uses: int = 0


def summary(rb: models.Rulebook, user: models.User | None) -> RulebookSummary:
    return RulebookSummary(ref=rb.id, name=rb.name, description=rb.description, institution=rb.institution,
                           department=rb.department, verified=rb.verified, visibility=rb.visibility,
                           mine=user is not None and rb.owner_id == user.id, uses=rb.uses)


@router.get("", response_model=list[RulebookSummary])
def list_rulebooks(user: models.User | None = Depends(optional_user),
                   session: Session = Depends(get_session)) -> list[RulebookSummary]:
    """Built-in rulebooks, then the user's own."""
    out = [RulebookSummary(**b) for b in builtin_list()]
    if user is not None:
        mine = session.scalars(select(models.Rulebook).where(models.Rulebook.owner_id == user.id)
                               .order_by(models.Rulebook.updated_at.desc()))
        out += [summary(rb, user) for rb in mine]
    return out


@router.get("/library", response_model=list[RulebookSummary])
def library(q: str = "", user: models.User | None = Depends(optional_user),
            session: Session = Depends(get_session)) -> list[RulebookSummary]:
    """Public rulebooks other people made, e.g. "University X, Accounting, Project 2026"."""
    stmt = select(models.Rulebook).where(models.Rulebook.visibility == "public")
    for word in q.split()[:6]:
        like = f"%{word}%"
        stmt = stmt.where(or_(models.Rulebook.name.ilike(like), models.Rulebook.institution.ilike(like),
                              models.Rulebook.department.ilike(like)))
    stmt = stmt.order_by(models.Rulebook.verified.desc(), models.Rulebook.uses.desc()).limit(50)
    return [summary(rb, user) for rb in session.scalars(stmt)]


@router.get("/{ref}")
def get_rulebook(ref: str, user: models.User | None = Depends(optional_user),
                 session: Session = Depends(get_session)) -> dict:
    """The rulebook as written (`data`) and fully resolved (`rules`)."""
    rules = resolve(ref, session, user)
    if ref.startswith(BUILTIN):
        head = next(b for b in builtin_list() if b["ref"] == ref)
        written = raw_data(ref, session, user)
    else:
        rb = session.get(models.Rulebook, ref)
        head = summary(rb, user).model_dump()
        written = rb.data
    return {**head, "data": written, "rules": rules.model_dump(mode="json")}


@router.post("", response_model=RulebookSummary, status_code=201)
def create_rulebook(body: RulebookIn, user: models.User = Depends(current_user),
                    session: Session = Depends(get_session)) -> RulebookSummary:
    data = {**body.data, "name": body.data.get("name") or body.name}
    validate_data(data, session, user)
    rb = models.Rulebook(owner_id=user.id, name=body.name, description=body.description,
                         institution=body.institution, department=body.department, data=data,
                         visibility=body.visibility)
    session.add(rb)
    session.commit()
    return summary(rb, user)


def _own(ref: str, user: models.User, session: Session) -> models.Rulebook:
    rb = session.get(models.Rulebook, ref)
    if rb is None or rb.owner_id != user.id:
        raise HTTPException(404, "Rulebook not found.")
    return rb


@router.put("/{ref}", response_model=RulebookSummary)
def update_rulebook(ref: str, body: RulebookIn, user: models.User = Depends(current_user),
                    session: Session = Depends(get_session)) -> RulebookSummary:
    rb = _own(ref, user, session)
    data = {**body.data, "name": body.data.get("name") or body.name}
    if data.get("extends") == ref:
        raise HTTPException(400, "This rulebook extends itself.")
    validate_data(data, session, user)
    rb.name, rb.description, rb.data, rb.visibility = body.name, body.description, data, body.visibility
    rb.institution, rb.department = body.institution, body.department
    session.commit()
    return summary(rb, user)


@router.delete("/{ref}", status_code=204)
def delete_rulebook(ref: str, user: models.User = Depends(current_user),
                    session: Session = Depends(get_session)) -> None:
    rb = _own(ref, user, session)
    in_use = session.scalar(select(models.Document.id).where(models.Document.rulebook_ref == ref).limit(1))
    if in_use:
        raise HTTPException(409, "Documents still use this rulebook. Change their rulebook first.")
    session.delete(rb)
    session.commit()


@router.post("/{ref}/verify", response_model=RulebookSummary)
def verify_rulebook(ref: str, user: models.User = Depends(current_user),
                    session: Session = Depends(get_session)) -> RulebookSummary:
    """Mark a public rulebook as the official one (Formatly admins for now)."""
    if not user.is_admin:
        raise HTTPException(403, "Only Formatly admins can verify rulebooks.")
    rb = session.get(models.Rulebook, ref)
    if rb is None:
        raise HTTPException(404, "Rulebook not found.")
    rb.verified = True
    session.commit()
    return summary(rb, user)


__all__ = ["router", "can_read"]
