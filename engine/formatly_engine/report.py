"""The report: score, summary by category, and every issue."""

from __future__ import annotations

from collections import Counter

from .checks.base import Context
from .docmodel import word_count
from .issues import CATEGORIES

WEIGHT = {"error": 3, "warning": 1, "suggestion": 0}


def score(ctx: Context) -> int:
    """100 means nothing wrong. Each rule loses weight in proportion to how much of
    the document breaks it, with a floor so that one wrong place still counts."""
    log = ctx.log
    by_rule = Counter(i.rule for i in log.issues if i.severity != "suggestion")
    total = lost = 0.0
    for rule, checked in log.checked.items():
        w = WEIGHT[log.severity.get(rule, "error")]
        if not w:
            continue
        total += w
        n = by_rule.get(rule, 0)
        if n:
            lost += w * min(1.0, 0.4 + 0.6 * n / max(checked, 1))
    value = 100 if total == 0 else max(0, round(100 * (1 - lost / total)))
    return min(value, 99) if by_rule else value  # 100 only when nothing needs attention


def build_report(ctx: Context) -> dict:
    issues = ctx.log.issues
    sev = Counter(i.severity for i in issues)
    categories = []
    for key, label in CATEGORIES.items():
        mine = [i for i in issues if i.category == key]
        checked = any(r.split(".", 1)[0] == key for r in ctx.log.checked)
        if not checked and not mine:
            continue
        c = Counter(i.severity for i in mine)
        categories.append({
            "id": key, "name": label,
            "status": "fail" if c["error"] else ("warn" if c["warning"] else "pass"),
            "errors": c["error"], "warnings": c["warning"], "suggestions": c["suggestion"],
        })
    outline = ctx.outline
    return {
        "rulebook": {"name": ctx.rules.name, "version": ctx.rules.version},
        "score": score(ctx),
        "counts": {"errors": sev["error"], "warnings": sev["warning"], "suggestions": sev["suggestion"],
                   "fixable": sum(1 for i in issues if i.fixable)},
        "categories": categories,
        "document": {
            "paragraphs": sum(1 for b in ctx.blocks if b.kind == "p" and not b.is_empty),
            "tables": sum(1 for b in ctx.blocks if b.kind == "tbl"),
            "words": sum(word_count(b.text) for b in ctx.blocks if b.kind == "p"),
            "sections_found": [{"id": h.spec_id, "heading": h.heading, "block": h.block} for h in outline.hits],
            "chapters": [{"number": h.number, "title": h.title} for h in outline.chapters],
            "headings": len(outline.headings),
            "captions": len(ctx.captions),
        },
        "issues": [i.to_dict() for i in issues],
    }
