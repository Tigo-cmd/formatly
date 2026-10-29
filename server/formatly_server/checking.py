"""Running the engine on stored documents."""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from formatly_engine import check, fix
from formatly_engine.rulebook import Rulebook

from . import models
from .storage import LocalStorage

log = logging.getLogger("formatly")


def run_check(version: models.Version, data: bytes, rules: Rulebook, storage: LocalStorage) -> None:
    """Check `data` and store the report and the commented copy on `version`."""
    try:
        result = check(data, rules)
        report = result.report
        version.report_key = storage.put("reports", json.dumps(report).encode(), "json")
        version.commented_key = storage.put("commented", result.annotated_bytes())
        version.score = report["score"]
        version.counts = report["counts"]
        version.rulebook_name = rules.name
        version.status = "done"
        version.error = ""
    except Exception as e:  # a document the engine cannot read must not break the request
        log.exception("check failed for version %s", version.id)
        version.status = "failed"
        version.error = ("Formatly could not read this document. If it opens in Word, please send it to "
                         f"support so we can fix this. ({type(e).__name__})")


def load_report(version: models.Version, storage: LocalStorage) -> dict:
    if not version.report_key:
        return {}
    return json.loads(storage.get(version.report_key))


def charge(session: Session, user: models.User, amount: int, reason: str, reference: str) -> bool:
    """Take credits if the user has enough. The caller commits."""
    if user.credits < amount:
        return False
    user.credits -= amount
    session.add(models.CreditEntry(user_id=user.id, delta=-amount, reason=reason, reference=reference))
    return True


def grant(session: Session, user: models.User, amount: int, reason: str, reference: str = "") -> None:
    user.credits += amount
    session.add(models.CreditEntry(user_id=user.id, delta=amount, reason=reason, reference=reference))


def run_fix(source: models.Version, data: bytes, rules: Rulebook, storage: LocalStorage,
            number: int) -> models.Version:
    """Auto-fix `data` into a new version of the same document."""
    result = fix(data, rules)
    new = models.Version(
        document_id=source.document_id, number=number, filename=_fixed_name(source.filename),
        source="autofix", original_key=storage.put("originals", result.fixed),
        rulebook_ref=source.rulebook_ref, rulebook_name=rules.name,
    )
    after = result.after
    new.report_key = storage.put("reports", json.dumps(after.report).encode(), "json")
    new.commented_key = storage.put("commented", after.annotated_bytes())
    new.score = after.report["score"]
    new.counts = after.report["counts"]
    new.status = "done"
    new.fix_summary = {"applied": result.applied, "before_score": result.before.get("score"),
                       "fixed_count": sum(result.applied.values()), "from_version": source.number}
    return new


def _fixed_name(name: str) -> str:
    stem = name[:-5] if name.lower().endswith(".docx") else name
    return f"{stem} (auto-fixed).docx"
