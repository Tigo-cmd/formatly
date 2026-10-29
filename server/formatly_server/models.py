"""Tables."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    credits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Rulebook(Base):
    """A user's own rulebook. Built-in rulebooks live in the engine, not here."""

    __tablename__ = "rulebooks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    institution: Mapped[str] = mapped_column(String(200), default="")
    department: Mapped[str] = mapped_column(String(200), default="")
    data: Mapped[dict] = mapped_column(JSON)  # the rulebook as written (may `extends` another)
    visibility: Mapped[str] = mapped_column(String(16), default="private")  # private / shared / public
    verified: Mapped[bool] = mapped_column(Boolean, default=False)  # confirmed by a rule owner
    uses: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    rulebook_ref: Mapped[str] = mapped_column(String(64))  # "builtin:default" or a rulebook id
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    versions: Mapped[list["Version"]] = relationship(
        back_populates="document", order_by="Version.number", cascade="all, delete-orphan")


class Version(Base):
    """One uploaded file of a document, with its check and (optionally) its auto-fix."""

    __tablename__ = "versions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(16), default="upload")  # upload / autofix
    original_key: Mapped[str] = mapped_column(String(200))
    rulebook_ref: Mapped[str] = mapped_column(String(64))
    rulebook_name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending / done / failed
    error: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    report_key: Mapped[str] = mapped_column(String(200), default="")
    commented_key: Mapped[str] = mapped_column(String(200), default="")
    fixed_key: Mapped[str] = mapped_column(String(200), default="")
    fix_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    document: Mapped[Document] = relationship(back_populates="versions")


class CreditEntry(Base):
    """Every change to a user's credits, so the balance can always be explained."""

    __tablename__ = "credit_entries"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(200))
    reference: Mapped[str] = mapped_column(String(200), default="")  # e.g. version id, payment reference
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Guideline(Base):
    """A guideline a user uploaded to be turned into a rulebook."""

    __tablename__ = "guidelines"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(300), default="")
    kind: Mapped[str] = mapped_column(String(16))  # guideline (text, pdf, photo) / sample (a model .docx)
    file_key: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    error: Mapped[str] = mapped_column(Text, default="")
    draft: Mapped[dict] = mapped_column(JSON, default=dict)  # the proposed rulebook
    questions: Mapped[list] = mapped_column(JSON, default=list)  # what to ask the user
    notes: Mapped[list] = mapped_column(JSON, default=list)  # rules found that the engine cannot check yet
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
