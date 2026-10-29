"""Things endpoints need: the database session, storage, settings, the signed-in user."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from . import models
from .config import Settings
from .security import read_token
from .storage import LocalStorage

_bearer = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_storage(request: Request) -> LocalStorage:
    return request.app.state.storage


def get_session(request: Request) -> Iterator[Session]:
    yield from request.app.state.db.session()


def optional_user(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                  session: Session = Depends(get_session)) -> models.User | None:
    if creds is None:
        return None
    user_id = read_token(creds.credentials, request.app.state.settings.secret_key)
    return session.get(models.User, user_id) if user_id else None


def current_user(user: models.User | None = Depends(optional_user)) -> models.User:
    if user is None:
        raise HTTPException(401, "Please sign in.")
    return user
