"""Issues: one problem found in a document."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

Severity = Literal["error", "warning", "suggestion"]

CATEGORIES = {
    "page": "Page setup",
    "body": "Body text",
    "headings": "Headings",
    "structure": "Structure",
    "numbering": "Page numbering",
    "toc": "Table of contents",
    "captions": "Tables and figures",
    "references": "References and citations",
    "limits": "Word limits",
    "hygiene": "Clean-up",
}


@dataclass
class Issue:
    rule: str  # e.g. "body.font"; the category is the part before the dot
    severity: Severity
    message: str  # what is wrong, in plain language
    hint: str = ""  # how to fix it
    block: int | None = None  # paragraph or table it is anchored to
    fixable: bool = False  # Formatly's auto-fix can correct it
    data: dict = field(default_factory=dict)

    @property
    def category(self) -> str:
        return self.rule.split(".", 1)[0]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category
        return d


class IssueLog:
    """Collects issues and remembers which rules were checked, for scoring."""

    def __init__(self) -> None:
        self.issues: list[Issue] = []
        self.checked: dict[str, int] = {}  # rule -> number of things checked
        self.severity: dict[str, Severity] = {}

    def checked_rule(self, rule: str, count: int = 1, severity: Severity = "error") -> None:
        self.checked[rule] = self.checked.get(rule, 0) + count
        self.severity.setdefault(rule, severity)

    def add(self, issue: Issue) -> Issue:
        self.issues.append(issue)
        self.checked.setdefault(issue.rule, 1)
        self.severity.setdefault(issue.rule, issue.severity)
        return issue

    def __iter__(self):
        return iter(self.issues)

    def __len__(self) -> int:
        return len(self.issues)
