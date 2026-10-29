"""Sign up, sign in, the current user."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models
from ..checking import grant
from ..config import Settings
from ..deps import current_user, get_session, get_settings
from ..security import hash_password, make_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Register(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=8, max_length=200)
    name: str = Field(default="", max_length=200)


class Login(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    credits: int
    is_admin: bool


class TokenOut(BaseModel):
    token: str
    user: UserOut


def user_out(u: models.User) -> UserOut:
    return UserOut(id=u.id, email=u.email, name=u.name, credits=u.credits, is_admin=u.is_admin)


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: Register, session: Session = Depends(get_session),
             settings: Settings = Depends(get_settings)) -> TokenOut:
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Please enter a valid email address.")
    if session.scalar(select(models.User).where(func.lower(models.User.email) == email)):
        raise HTTPException(409, "An account with this email already exists. Please sign in.")
    user = models.User(email=email, name=body.name.strip(), password_hash=hash_password(body.password),
                       is_admin=email in settings.admin_emails)
    session.add(user)
    session.flush()
    if settings.free_credits:
        grant(session, user, settings.free_credits, "Welcome credits")
    session.commit()
    return TokenOut(token=make_token(user.id, settings.secret_key, settings.token_hours), user=user_out(user))


@router.post("/login", response_model=TokenOut)
def login(body: Login, session: Session = Depends(get_session),
          settings: Settings = Depends(get_settings)) -> TokenOut:
    user = session.scalar(select(models.User).where(models.User.email == body.email.strip().lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password.")
    return TokenOut(token=make_token(user.id, settings.secret_key, settings.token_hours), user=user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: models.User = Depends(current_user)) -> UserOut:
    return user_out(user)
