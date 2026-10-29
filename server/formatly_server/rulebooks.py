"""Finding and resolving rulebooks: built-in ones from the engine, and users' own."""

from __future__ import annotations

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from formatly_engine.rulebook import Rulebook, builtin_names, deep_merge, load_rulebook
from formatly_engine.rulebook import _load_raw  # built-in YAML, already merged with its parents

from . import models

BUILTIN = "builtin:"


def is_builtin(ref: str) -> bool:
    return ref.startswith(BUILTIN) and ref[len(BUILTIN):] in builtin_names()


def can_read(rb: models.Rulebook, user: models.User | None) -> bool:
    return rb.visibility in ("shared", "public") or (user is not None and rb.owner_id == user.id)


def raw_data(ref: str, session: Session, user: models.User | None, _seen: tuple = ()) -> dict:
    """The rulebook behind `ref` as a plain mapping, with every `extends` merged in."""
    if ref in _seen:
        raise HTTPException(400, "This rulebook extends itself.")
    if ref.startswith(BUILTIN):
        name = ref[len(BUILTIN):]
        if name not in builtin_names():
            raise HTTPException(404, f"No built-in rulebook called {name!r}.")
        return _load_raw(name)
    rb = session.get(models.Rulebook, ref)
    if rb is None or not can_read(rb, user):
        raise HTTPException(404, "Rulebook not found.")
    data = dict(rb.data)
    parent = data.pop("extends", None)
    if parent:
        data = deep_merge(raw_data(normalise_ref(parent), session, user, _seen + (ref,)), data)
    return data


def normalise_ref(ref: str) -> str:
    """`extends: default` means the built-in; anything else must be a rulebook id."""
    if ref in builtin_names():
        return BUILTIN + ref
    return ref


def resolve(ref: str, session: Session, user: models.User | None) -> Rulebook:
    if is_builtin(ref):
        return load_rulebook(ref[len(BUILTIN):])
    data = raw_data(ref, session, user)
    data.pop("extends", None)
    try:
        return Rulebook.model_validate(data)
    except ValidationError as e:
        raise HTTPException(422, f"This rulebook is not valid: {e.errors()[0]['msg']}") from None


def validate_data(data: dict, session: Session, user: models.User) -> Rulebook:
    """Check a rulebook a user is saving. Its `extends` may only name a built-in
    rulebook or one this user can read."""
    data = dict(data)
    parent = data.get("extends")
    if parent is not None and not isinstance(parent, str):
        raise HTTPException(422, "`extends` must be the name of a rulebook.")
    merged = dict(data)
    if parent:
        merged = deep_merge(raw_data(normalise_ref(parent), session, user), data)
    merged.pop("extends", None)
    try:
        return Rulebook.model_validate(merged)
    except ValidationError as e:
        err = e.errors()[0]
        where = ".".join(str(x) for x in err["loc"])
        raise HTTPException(422, f"Rulebook problem at {where}: {err['msg']}") from None


def builtin_list() -> list[dict]:
    out = []
    for name in builtin_names():
        rb = load_rulebook(name)
        out.append({"ref": BUILTIN + name, "name": rb.name, "description": rb.description.strip(),
                    "builtin": True, "verified": True})
    # The default first.
    out.sort(key=lambda r: (r["ref"] != BUILTIN + "default", r["name"]))
    return out
