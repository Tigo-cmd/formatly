"""Making a rulebook from a guideline (read by AI) or from a model document (measured)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from formatly_engine.learn import learn_rulebook
from formatly_engine.rulebook import Rulebook, builtin_names, deep_merge, _load_raw

from .. import models
from ..ai import AIError, apply_answers, content_blocks, to_rulebook
from ..config import Settings
from ..deps import current_user, get_session, get_settings, get_storage
from ..storage import LocalStorage
from ..uploads import read_limited, require_docx, safe_filename

router = APIRouter(prefix="/guidelines", tags=["guidelines"])
log = logging.getLogger("formatly")
MAX_FILES = 10


class GuidelineOut(BaseModel):
    id: str
    kind: str
    filename: str
    status: str  # pending / done / failed
    error: str
    draft: dict
    questions: list
    notes: list


def out(g: models.Guideline) -> GuidelineOut:
    return GuidelineOut(id=g.id, kind=g.kind, filename=g.filename, status=g.status, error=g.error,
                        draft=g.draft or {}, questions=g.questions or [], notes=g.notes or [])


def _base_name(base_ref: str) -> str:
    name = base_ref.removeprefix("builtin:")
    if name not in builtin_names():
        raise HTTPException(422, "Start from one of the built-in rulebooks.")
    return name


def usable(data: dict, base_name: str) -> tuple[dict, list[dict]]:
    """Keep the parts of a draft that make a valid rulebook; explain any part dropped."""
    base = _load_raw(base_name)
    kept: dict = {}
    notes: list[dict] = []
    for key, value in data.items():
        trial = deep_merge(base, {**kept, key: value})
        trial.pop("extends", None)
        try:
            Rulebook.model_validate(trial)
            kept[key] = value
        except ValidationError as e:
            err = e.errors()[0]
            notes.append({"type": "dropped", "text": f"Could not use the {key.replace('_', ' ')} rules "
                                                     f"({'.'.join(map(str, err['loc']))}: {err['msg']}); "
                                                     "the base rule applies."})
    return kept, notes


def _read_guideline(app_state, guideline_id: str, blocks: list[dict], base_name: str) -> None:
    """Runs after the response: Claude reads the guideline, the draft is stored."""
    with app_state.db.sessions() as session:
        g = session.get(models.Guideline, guideline_id)
        try:
            extraction = app_state.reader.read(blocks)
            data, dropped = usable(to_rulebook(extraction, _load_raw(base_name), base_name), base_name)
            g.draft = data
            g.questions = [q.model_dump() for q in extraction.questions]
            g.notes = ([{"type": "not_checkable", "text": t} for t in extraction.not_checkable]
                       + [{"type": "quote", "rule": q.rule, "text": q.quote} for q in extraction.quotes]
                       + dropped)
            g.status = "done"
        except AIError as e:
            g.status, g.error = "failed", str(e)
        except Exception:
            log.exception("guideline %s failed", guideline_id)
            g.status, g.error = "failed", "Reading the guideline failed. Please try again."
        session.commit()


@router.post("", response_model=GuidelineOut, status_code=202)
async def read_guideline(request: Request, background: BackgroundTasks,
                         files: list[UploadFile] = File(default=[]), text: str = Form(""),
                         base_ref: str = Form("builtin:default"), user: models.User = Depends(current_user),
                         session: Session = Depends(get_session), storage: LocalStorage = Depends(get_storage),
                         settings: Settings = Depends(get_settings)) -> GuidelineOut:
    """Upload a guideline (PDF, Word, photos of a printed handout) or paste its text.
    Returns at once with status "pending"; poll GET /guidelines/{id}."""
    if request.app.state.reader is None:
        raise HTTPException(503, "Reading guidelines with AI is not set up on this server yet. You can still "
                                 "build a rulebook from a correctly formatted model document.")
    base_name = _base_name(base_ref)
    if len(files) > MAX_FILES:
        raise HTTPException(413, f"Upload at most {MAX_FILES} files (for example, one photo per page).")
    loaded = [(safe_filename(f.filename, "guideline"), await read_limited(f, settings.max_upload_mb)) for f in files]
    try:
        blocks = content_blocks(loaded, text)
    except AIError as e:
        raise HTTPException(415, str(e)) from None
    g = models.Guideline(owner_id=user.id, kind="guideline",
                         filename=", ".join(n for n, _ in loaded)[:300] or "pasted text")
    if loaded:
        g.file_key = storage.put("guidelines", loaded[0][1], "bin")
    session.add(g)
    session.commit()
    background.add_task(_read_guideline, request.app.state, g.id, blocks, base_name)
    return out(g)


@router.post("/sample", response_model=GuidelineOut, status_code=201)
async def learn_from_sample(file: UploadFile = File(...), base_ref: str = Form("builtin:default"),
                            user: models.User = Depends(current_user), session: Session = Depends(get_session),
                            settings: Settings = Depends(get_settings)) -> GuidelineOut:
    """Measure a correctly formatted model document (.docx) and draft a rulebook from it."""
    base_name = _base_name(base_ref)
    data = await read_limited(file, settings.max_upload_mb)
    require_docx(data)
    name = safe_filename(file.filename)
    try:
        learned = learn_rulebook(data, base_name, f"Learned from {name}")
    except Exception:
        log.exception("learning from %s failed", name)
        raise HTTPException(422, "Formatly could not read this document.") from None
    draft, dropped = usable(learned.data, base_name)
    g = models.Guideline(owner_id=user.id, kind="sample", filename=name, status="done", draft=draft,
                         notes=[{"type": "learned", "text": t} for t in learned.notes]
                         + [{"type": "unsure", "text": t} for t in learned.unsure] + dropped)
    session.add(g)
    session.commit()
    return out(g)


def _own(guideline_id: str, user: models.User, session: Session) -> models.Guideline:
    g = session.get(models.Guideline, guideline_id)
    if g is None or g.owner_id != user.id:
        raise HTTPException(404, "Not found.")
    return g


@router.get("/{guideline_id}", response_model=GuidelineOut)
def get_guideline(guideline_id: str, user: models.User = Depends(current_user),
                  session: Session = Depends(get_session)) -> GuidelineOut:
    return out(_own(guideline_id, user, session))


class Answers(BaseModel):
    answers: dict[str, str]


@router.post("/{guideline_id}/answers", response_model=GuidelineOut)
def answer_questions(guideline_id: str, body: Answers, user: models.User = Depends(current_user),
                     session: Session = Depends(get_session)) -> GuidelineOut:
    """Apply the user's answers to the draft. Answered questions are removed."""
    g = _own(guideline_id, user, session)
    if g.status != "done":
        raise HTTPException(409, "The guideline has not been read yet.")
    base_name = (g.draft or {}).get("extends", "default")
    draft, dropped = usable(apply_answers(g.draft, body.answers), base_name)
    g.draft = draft
    g.questions = [q for q in (g.questions or []) if q.get("field") not in body.answers]
    g.notes = [n for n in (g.notes or []) if n.get("type") != "dropped"] + dropped
    session.commit()
    return out(g)
