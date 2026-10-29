"""All checks, in the order they run."""

from .base import Context
from .captions import check_captions, find_captions
from .page import check_page
from .references import check_limits, check_references
from .structure import (check_numbering, check_section_content, check_structure, check_subsections,
                        check_title_page, check_lists, check_toc)
from .text import check_body, check_headings, check_hygiene

ALL_CHECKS = [
    check_page,
    check_structure,
    check_title_page,
    check_section_content,
    check_subsections,
    check_headings,
    check_body,
    check_numbering,
    check_toc,
    check_lists,
    check_captions,
    check_references,
    check_limits,
    check_hygiene,
]


def run_checks(ctx: Context) -> None:
    ctx.captions = find_captions(ctx)
    for check in ALL_CHECKS:
        check(ctx)


__all__ = ["ALL_CHECKS", "Context", "run_checks"]
