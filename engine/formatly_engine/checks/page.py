"""Page setup: paper size, orientation, margins."""

from __future__ import annotations

from ..issues import Issue
from ..units import emu_to_twips, fmt_length
from .base import Context

PAPER = {  # twips, portrait
    "A4": (11906, 16838),
    "Letter": (12240, 15840),
    "Legal": (12240, 20160),
    "A5": (8391, 11906),
}
PAPER_TOLERANCE = 60  # twips


def _anchor(ctx: Context, section: int) -> int | None:
    return next((b.index for b in ctx.blocks if b.section == section and b.kind == "p"), None)


def _paper_name(w: int, h: int) -> str:
    short, long_ = sorted((w, h))
    for name, (pw, ph) in PAPER.items():
        if abs(short - pw) <= PAPER_TOLERANCE and abs(long_ - ph) <= PAPER_TOLERANCE:
            return name
    return f"{fmt_length(short)} × {fmt_length(long_)}"


def check_page(ctx: Context) -> None:
    rules = ctx.rules.page
    sections = ctx.model.sections
    for i, sec in enumerate(sections):
        w, h = emu_to_twips(sec.page_width), emu_to_twips(sec.page_height)
        where = "" if len(sections) == 1 else f" (section {i + 1} of {len(sections)})"
        anchor = _anchor(ctx, i)
        landscape = bool(w and h and w > h)

        if rules.size and w and h:
            ctx.log.checked_rule("page.size")
            allowed = rules.size if isinstance(rules.size, list) else [rules.size]
            short, long_ = sorted((w, h))
            if not any(abs(short - PAPER[s][0]) <= PAPER_TOLERANCE and abs(long_ - PAPER[s][1]) <= PAPER_TOLERANCE
                       for s in allowed):
                ctx.log.add(Issue(
                    "page.size", "error",
                    f"Paper size is {_paper_name(w, h)}{where}. Required: {' or '.join(allowed)}.",
                    f"Layout > Size > {allowed[0]}.", anchor, fixable=True))

        if rules.orientation and w and h:
            ctx.log.checked_rule("page.orientation")
            want_landscape = rules.orientation == "landscape"
            if landscape != want_landscape and not (landscape and rules.allow_landscape_sections and i > 0):
                ctx.log.add(Issue(
                    "page.orientation", "error",
                    f"Page orientation is {'landscape' if landscape else 'portrait'}{where}. "
                    f"Required: {rules.orientation}.",
                    f"Layout > Orientation > {rules.orientation.capitalize()}.", anchor, fixable=True))

        if rules.margins:
            ctx.log.checked_rule("page.margins")
            have = {
                "top": emu_to_twips(sec.top_margin), "bottom": emu_to_twips(sec.bottom_margin),
                "left": emu_to_twips(sec.left_margin), "right": emu_to_twips(sec.right_margin),
            }
            if landscape and rules.allow_landscape_sections and i > 0:
                # A rotated page keeps the binding edge: compare rotated margins.
                have = {"top": have["left"], "bottom": have["right"], "left": have["bottom"], "right": have["top"]}
            wrong = []
            for side in ("top", "bottom", "left", "right"):
                need = getattr(rules.margins, side)
                if have[side] is None or abs(have[side] - need) > rules.tolerance:
                    wrong.append(f"{side} {fmt_length(have[side])} (needs {fmt_length(need)})")
            if rules.margins.gutter is not None:
                g = emu_to_twips(sec.gutter) or 0
                if abs(g - rules.margins.gutter) > rules.tolerance:
                    wrong.append(f"gutter {fmt_length(g)} (needs {fmt_length(rules.margins.gutter)})")
            if wrong:
                ctx.log.add(Issue(
                    "page.margins", "error",
                    f"Margins are wrong{where}: {'; '.join(wrong)}.",
                    "Layout > Margins > Custom Margins.", anchor, fixable=True,
                    data={"section": i}))
