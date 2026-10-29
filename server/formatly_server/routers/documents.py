"""Documents, their versions, checks, downloads and auto-fix."""

from __future__ import annotations

import logging

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..checking import charge, load_report, run_check, run_fix
from ..config import Settings
from ..deps import current_user, get_session, get_settings, get_storage
from ..rulebooks import is_builtin, resolve
from ..storage import LocalStorage
from ..uploads import read_limited, require_docx, safe_filename

router = APIRouter(tags=["documents"])
log = logging.getLogger("formatly")
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class VersionOut(BaseModel):
    id: str
    number: int
    filename: str
    source: str
    status: str
    error: str
    score: int | None
    counts: dict
    rulebook_ref: str
    rulebook_name: str
    fix_summary: dict
    created_at: datetime


class DocumentOut(BaseModel):
    id: str
    title: str
    rulebook_ref: str
    created_at: datetime
    updated_at: datetime
    latest: VersionOut | None
    versions: list[VersionOut] = []


def version_out(v: models.Version) -> VersionOut:
    return VersionOut(id=v.id, number=v.number, filename=v.filename, source=v.source, status=v.status,
                      error=v.error, score=v.score, counts=v.counts or {}, rulebook_ref=v.rulebook_ref,
                      rulebook_name=v.rulebook_name, fix_summary=v.fix_summary or {}, created_at=v.created_at)


def document_out(d: models.Document, with_versions: bool = False) -> DocumentOut:
    latest = d.versions[-1] if d.versions else None
    return DocumentOut(id=d.id, title=d.title, rulebook_ref=d.rulebook_ref, created_at=d.created_at,
                       updated_at=d.updated_at, latest=version_out(latest) if latest else None,
                       versions=[version_out(v) for v in d.versions] if with_versions else [])


def _own_document(doc_id: str, user: models.User, session: Session) -> models.Document:
    d = session.get(models.Document, doc_id)
    if d is None or d.owner_id != user.id:
        raise HTTPException(404, "Document not found.")
    return d


def _own_version(version_id: str, user: models.User, session: Session) -> models.Version:
    v = session.get(models.Version, version_id)
    if v is None or v.document.owner_id != user.id:
        raise HTTPException(404, "Version not found.")
    return v


def _count_use(ref: str, session: Session) -> None:
    if not is_builtin(ref):
        rb = session.get(models.Rulebook, ref)
        if rb is not None:
            rb.uses += 1


def _add_version(doc: models.Document, file_data: bytes, filename: str, ref: str, user: models.User,
                 session: Session, storage: LocalStorage) -> models.Version:
    rules = resolve(ref, session, user)
    number = (doc.versions[-1].number + 1) if doc.versions else 1
    v = models.Version(document_id=doc.id, number=number, filename=filename,
                       original_key=storage.put("originals", file_data), rulebook_ref=ref)
    run_check(v, file_data, rules, storage)
    doc.versions.append(v)
    return v


@router.post("/documents", response_model=DocumentOut, status_code=201)
async def create_document(file: UploadFile = File(...), rulebook_ref: str = Form("builtin:default"),
                          title: str = Form(""), user: models.User = Depends(current_user),
                          session: Session = Depends(get_session), storage: LocalStorage = Depends(get_storage),
                          settings: Settings = Depends(get_settings)) -> DocumentOut:
    """Upload a document and check it straight away."""
    data = await read_limited(file, settings.max_upload_mb)
    require_docx(data)
    filename = safe_filename(file.filename)
    resolve(rulebook_ref, session, user)  # fail before storing anything
    default_title = filename[:-5] if filename.lower().endswith(".docx") else filename
    doc = models.Document(owner_id=user.id, title=(title.strip() or default_title)[:300], rulebook_ref=rulebook_ref)
    session.add(doc)
    session.flush()
    _add_version(doc, data, filename, rulebook_ref, user, session, storage)
    _count_use(rulebook_ref, session)
    session.commit()
    return document_out(doc, with_versions=True)


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(user: models.User = Depends(current_user),
                   session: Session = Depends(get_session)) -> list[DocumentOut]:
    docs = session.scalars(select(models.Document).where(models.Document.owner_id == user.id)
                           .order_by(models.Document.updated_at.desc()))
    return [document_out(d) for d in docs]


@router.get("/documents/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: str, user: models.User = Depends(current_user),
                 session: Session = Depends(get_session)) -> DocumentOut:
    return document_out(_own_document(doc_id, user, session), with_versions=True)


class DocumentPatch(BaseModel):
    title: str | None = None
    rulebook_ref: str | None = None


@router.patch("/documents/{doc_id}", response_model=DocumentOut)
def update_document(doc_id: str, body: DocumentPatch, user: models.User = Depends(current_user),
                    session: Session = Depends(get_session),
                    storage: LocalStorage = Depends(get_storage)) -> DocumentOut:
    """Rename, or switch rulebook (the latest version is checked again against it)."""
    doc = _own_document(doc_id, user, session)
    if body.title is not None and body.title.strip():
        doc.title = body.title.strip()[:300]
    if body.rulebook_ref and body.rulebook_ref != doc.rulebook_ref:
        resolve(body.rulebook_ref, session, user)
        doc.rulebook_ref = body.rulebook_ref
        latest = doc.versions[-1]
        _add_version(doc, storage.get(latest.original_key), latest.filename, body.rulebook_ref, user,
                     session, storage)
        _count_use(body.rulebook_ref, session)
    session.commit()
    return document_out(doc, with_versions=True)


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: str, user: models.User = Depends(current_user),
                    session: Session = Depends(get_session), storage: LocalStorage = Depends(get_storage)) -> None:
    """Delete a document and every stored file of it."""
    doc = _own_document(doc_id, user, session)
    for v in doc.versions:
        for key in (v.original_key, v.report_key, v.commented_key, v.fixed_key):
            storage.delete(key)
    session.delete(doc)
    session.commit()


@router.post("/documents/{doc_id}/versions", response_model=DocumentOut, status_code=201)
async def upload_version(doc_id: str, file: UploadFile = File(...), user: models.User = Depends(current_user),
                         session: Session = Depends(get_session), storage: LocalStorage = Depends(get_storage),
                         settings: Settings = Depends(get_settings)) -> DocumentOut:
    """Upload a corrected file: a new version, checked against the document's rulebook."""
    doc = _own_document(doc_id, user, session)
    data = await read_limited(file, settings.max_upload_mb)
    require_docx(data)
    _add_version(doc, data, safe_filename(file.filename), doc.rulebook_ref, user, session, storage)
    session.commit()
    return document_out(doc, with_versions=True)


@router.get("/versions/{version_id}/report")
def get_report(version_id: str, user: models.User = Depends(current_user),
               session: Session = Depends(get_session), storage: LocalStorage = Depends(get_storage)) -> dict:
    v = _own_version(version_id, user, session)
    return {"version": version_out(v).model_dump(mode="json"), "report": load_report(v, storage)}


@router.get("/versions/{version_id}/download")
def download(version_id: str, kind: Literal["original", "commented"] = "commented",
             user: models.User = Depends(current_user), session: Session = Depends(get_session),
             storage: LocalStorage = Depends(get_storage)) -> Response:
    v = _own_version(version_id, user, session)
    key = v.original_key if kind == "original" else v.commented_key
    if not key:
        raise HTTPException(404, "This file is not available.")
    stem = v.filename[:-5] if v.filename.lower().endswith(".docx") else v.filename
    name = v.filename if kind == "original" else f"{stem} (Formatly comments).docx"
    return Response(storage.get(key), media_type=DOCX,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/versions/{version_id}/fix", response_model=DocumentOut, status_code=201)
def autofix(version_id: str, user: models.User = Depends(current_user), session: Session = Depends(get_session),
            storage: LocalStorage = Depends(get_storage), settings: Settings = Depends(get_settings)) -> DocumentOut:
    """Auto-fix a version into a new version. Costs credits; refunded if it fails."""
    v = _own_version(version_id, user, session)
    if v.status != "done":
        raise HTTPException(409, "This version could not be checked, so it cannot be auto-fixed.")
    if not v.counts.get("fixable"):
        raise HTTPException(409, "Nothing in this version can be fixed automatically.")
    if not charge(session, user, settings.fix_cost, "Auto-fix", v.id):
        raise HTTPException(402, "You have no auto-fix credits left. Buy credits to continue.")
    session.flush()
    doc = v.document
    try:
        rules = resolve(v.rulebook_ref, session, user)
        new = run_fix(v, storage.get(v.original_key), rules, storage, doc.versions[-1].number + 1)
    except HTTPException:
        session.rollback()  # the charge is not saved
        raise
    except Exception:
        session.rollback()
        log.exception("auto-fix failed for version %s", version_id)
        raise HTTPException(500, "Auto-fix failed. You were not charged. Please try again or contact support.")
    doc.versions.append(new)
    session.commit()
    return document_out(doc, with_versions=True)
