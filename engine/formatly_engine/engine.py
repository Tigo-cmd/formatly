"""Public entry points: check, annotate, fix."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import docx

from .annotate import annotate
from .checks import Context, run_checks
from .docmodel import DocumentModel
from .fix import apply_fixes
from .outline import build_outline
from .report import build_report
from .rulebook import Rulebook, load_rulebook

Source = str | Path | bytes | BinaryIO


def _open(source: Source):
    if isinstance(source, bytes):
        source = io.BytesIO(source)
    return docx.Document(source)


def _rules(rules: Rulebook | str | Path | None) -> Rulebook:
    if isinstance(rules, Rulebook):
        return rules
    return load_rulebook(rules or "default")


@dataclass
class CheckResult:
    context: Context
    report: dict

    @property
    def issues(self):
        return self.context.log.issues

    def annotated_bytes(self) -> bytes:
        """The checked document with every issue as a Word comment."""
        annotate(self.context, self.report)
        buf = io.BytesIO()
        self.context.model.document.save(buf)
        return buf.getvalue()


def analyse(document, rules: Rulebook) -> Context:
    model = DocumentModel.load(document)
    ctx = Context(model=model, rules=rules, outline=build_outline(model, rules))
    run_checks(ctx)
    return ctx


def check(source: Source, rules: Rulebook | str | Path | None = None) -> CheckResult:
    rb = _rules(rules)
    ctx = analyse(_open(source), rb)
    return CheckResult(ctx, build_report(ctx))


@dataclass
class FixResult:
    fixed: bytes  # the corrected document
    applied: dict[str, int]  # rule -> issues addressed
    before: dict  # report before fixing
    after: CheckResult  # check of the corrected document


def fix(source: Source, rules: Rulebook | str | Path | None = None, max_passes: int = 4) -> FixResult:
    """Fix what can be fixed, then re-check the result so the report is honest.

    Some fixes change the layout (moving a section, splitting page numbering),
    so the document is re-read between passes.
    """
    rb = _rules(rules)
    data = source if isinstance(source, bytes) else _open(source)
    if not isinstance(data, bytes):
        buf = io.BytesIO()
        data.save(buf)
        data = buf.getvalue()
    before: dict | None = None
    applied: dict[str, int] = {}
    for _ in range(max_passes):
        ctx = analyse(_open(data), rb)
        if before is None:
            before = build_report(ctx)
        if not any(i.fixable for i in ctx.log.issues):
            break
        done = apply_fixes(ctx)
        if not done:
            break
        for rule, n in done.items():
            applied[rule] = applied.get(rule, 0) + n
        buf = io.BytesIO()
        ctx.model.document.save(buf)
        data = buf.getvalue()
    return FixResult(fixed=data, applied=applied, before=before or {}, after=check(data, rb))
