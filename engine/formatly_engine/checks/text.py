"""Body text, headings and clean-up (highlight, colour, double spaces)."""

from __future__ import annotations

import re

from ..docmodel import in_hyperlink
from ..issues import Issue
from ..outline import NUMBER_WORDS
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from .base import Context, alignment_ok, spacing_matches, text_problems

FIXABLE_TEXT = {"font", "size", "bold", "italic", "caps", "alignment", "line_spacing",
                "space_before", "space_after", "first_line_indent"}


PLACEHOLDER_RE = re.compile(r"\[Formatly: [^\]]*\]")


def section_id(ctx: Context, index: int) -> str | None:
    sec = ctx.outline.section_at(index)
    return sec.spec_id if sec else None


def check_body(ctx: Context) -> None:
    style_hints: dict[tuple, set[str]] = {}
    for b in ctx.body_blocks:
        sid = section_id(ctx, b.index)
        want = ctx.rules.body_text_for(sid)
        prose = ctx.is_prose(b)
        for suffix in ("font", "size"):
            if getattr(want, suffix):
                ctx.log.checked_rule(f"body.{suffix}")
        if prose:
            for suffix in ("alignment", "line_spacing", "space_before", "space_after", "first_line_indent"):
                if getattr(want, suffix) is not None:
                    ctx.log.checked_rule(f"body.{suffix}")
        problems = text_problems(ctx, b, want, layout=prose)
        style_id = ctx.model.para_format(b).style_id
        if problems and (style_id, sid) not in style_hints:
            style_hints[(style_id, sid)] = style_problems(ctx, style_id, want)
        for suffix, msg, hint in problems:
            if suffix in style_hints.get((style_id, sid), ()):
                name = ctx.model.fmt.style_name(ctx.model.para_format(b).style_id)
                hint += (f" Fastest: Home > Styles > right-click “{name}” > Modify. That fixes every "
                         f"paragraph using the {name} style at once.")
            ctx.log.add(Issue(f"body.{suffix}", "error", msg, hint, b.index, fixable=suffix in FIXABLE_TEXT))


def check_headings(ctx: Context) -> None:
    rules = ctx.rules
    outline = ctx.outline
    section_blocks = {h.block for h in outline.hits + outline.duplicates if h.kind != "chapter"}
    chapter_blocks = {h.block for h in outline.chapters}

    for idx, info in sorted(outline.headings.items()):
        b = ctx.blocks[idx]
        want = rules.heading(info.level)
        if want:
            ctx.log.checked_rule("headings.format")
            for suffix, msg, hint in text_problems(ctx, b, want, check_first_line=False):
                ctx.log.add(Issue("headings.format", "error", f"Level {info.level} heading: {msg}", hint,
                                  idx, fixable=suffix in FIXABLE_TEXT,
                                  data={"level": info.level, "aspect": suffix}))

        # New page before chapters and named sections.
        needs_new_page = (
            (idx in chapter_blocks and want is not None and want.new_page)
            or (idx in section_blocks and rules.structure.section_new_page)
        )
        if needs_new_page:
            ctx.log.checked_rule("headings.new_page")
            if not ctx.model.starts_new_page(b):
                blanks = 0
                for prev in reversed(ctx.blocks[:idx]):
                    if not prev.is_empty:
                        break
                    blanks += 1
                msg = f"“{b.text.strip()[:60]}” should start on a new page."
                if blanks >= 3:
                    msg += (f" It is pushed down with {blanks} empty lines, which breaks as soon as anything "
                            "above it changes.")
                ctx.log.add(Issue(
                    "headings.new_page", "error", msg,
                    "Delete the empty lines, put the cursor before the heading and press Ctrl+Enter "
                    "(Insert > Page Break)." if blanks >= 3 else
                    "Put the cursor before it and press Ctrl+Enter (Insert > Page Break).",
                    idx, fixable=True, data={"blank_lines": blanks}))

    # "CHAPTER 1" vs "CHAPTER ONE".
    style = rules.structure.chapter_label
    if style != "any":
        for h in outline.chapters + [d for d in outline.duplicates if d.kind == "chapter"]:
            ctx.log.checked_rule("headings.chapter_label")
            if h.number_style != style:
                expected = _chapter_label(h.number, style)
                ctx.log.add(Issue(
                    "headings.chapter_label", "error",
                    f"Chapter label “{h.heading.splitlines()[0][:40]}” should be written as “{expected}”.",
                    f"Change it to {expected}.", h.block, fixable=True,
                    data={"expected": expected}))

    _check_heading_numbers(ctx)


def _chapter_label(n: int | None, style: str) -> str:
    if n is None:
        return "CHAPTER ..."
    if style == "words" and n < len(NUMBER_WORDS):
        return f"CHAPTER {NUMBER_WORDS[n].upper()}"
    if style == "roman":
        vals = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
        out, k = "", n
        for v, s in vals:
            while k >= v:
                out, k = out + s, k - v
        return f"CHAPTER {out}"
    return f"CHAPTER {n}"


def _check_heading_numbers(ctx: Context) -> None:
    """2.1, 2.2, 2.2.1 ... inside Chapter Two, with no gaps."""
    last: dict[tuple[int, ...], int] = {}
    for idx, info in sorted(ctx.outline.headings.items()):
        if not info.numbering:
            continue
        chapter = ctx.outline.chapter_at(idx)
        parts = tuple(int(p) for p in info.numbering.split("."))
        ctx.log.checked_rule("headings.numbering", severity="warning")
        if chapter is not None and parts[0] != chapter:
            ctx.log.add(Issue(
                "headings.numbering", "warning",
                f"Heading “{info.text[:50]}” is numbered {info.numbering} but it is in Chapter "
                f"{chapter}. It should start with {chapter}.",
                f"Renumber it {chapter}.{'.'.join(map(str, parts[1:]))}.", idx))
            continue
        parent, n = parts[:-1], parts[-1]
        prev = last.get(parent)
        expected = {0, 1} if prev is None else {prev + 1}
        if n not in expected:
            want = ".".join(map(str, parent + (min(expected),)))
            ctx.log.add(Issue(
                "headings.numbering", "warning",
                f"Heading number {info.numbering} is out of sequence; expected {want}.",
                "Check for a missing, repeated or misnumbered heading.", idx))
        last[parent] = n
        # A new parent number resets its children.
        for key in [k for k in last if len(k) > len(parts) - 1 and k[:len(parts)] == parts]:
            del last[key]


_DOUBLE_SPACE = re.compile(r"\S {2,}\S")
_BOX_DRAWING = re.compile("[\u2500-\u257f]")
URL_RE = re.compile(r"https?://|www\.", re.I)


def run_text(r) -> str:
    return "".join(t.text or "" for t in r.findall(qn("w:t")))


def style_problems(ctx: Context, style_id: str | None, want) -> set[str]:
    """Which body rules the paragraph style itself breaks (so fixing the style fixes all)."""
    p = OxmlElement("w:p")
    if style_id:
        ppr = OxmlElement("w:pPr")
        ps = OxmlElement("w:pStyle")
        ps.set(qn("w:val"), style_id)
        ppr.append(ps)
        p.append(ppr)
    r = OxmlElement("w:r")
    p.append(r)
    rf = ctx.model.fmt.run(p, r)
    pf = ctx.model.fmt.paragraph(p)
    out = set()
    if want.font and rf.font.lower() != want.font.lower():
        out.add("font")
    if want.size and abs(rf.size - want.size) > 0.25:
        out.add("size")
    if want.alignment and not alignment_ok(pf.alignment, want.alignment):
        out.add("alignment")
    if want.line_spacing and not spacing_matches(pf, want.line_spacing):
        out.add("line_spacing")
    if want.first_line_indent is not None and abs(pf.first_line - want.first_line_indent) > 72:
        out.add("first_line_indent")
    return out


def check_hygiene(ctx: Context) -> None:
    rules = ctx.rules.hygiene
    for b in ctx.text_blocks:
        if b.is_empty:
            continue
        runs = ctx.model.run_formats(b)
        if rules.no_highlight:
            ctx.log.checked_rule("hygiene.highlight", severity="warning")
            if any(rf.highlight and rf.highlight.lower() not in ("none", "auto") for _, rf in runs):
                ctx.log.add(Issue("hygiene.highlight", "warning", "Highlighted text.",
                                  "Remove the highlight (Home > Text Highlight Colour > No Colour).",
                                  b.index, fixable=True))
        if rules.no_coloured_text:
            ctx.log.checked_rule("hygiene.colour", severity="warning")
            coloured = [rf.color for r, rf in runs
                        if rf.color and rf.color.lower() not in ("auto", "000000")
                        and not in_hyperlink(r) and not URL_RE.search(run_text(r))
                        and "hyperlink" not in (ctx.model.fmt.style_name(rf.style_id) or "").lower()]
            if coloured:
                ctx.log.add(Issue("hygiene.colour", "warning", "Text is coloured; it should be black.",
                                  "Home > Font Colour > Automatic.", b.index, fixable=True))
        ctx.log.checked_rule("hygiene.placeholder")
        if PLACEHOLDER_RE.search(b.text):
            ctx.log.add(Issue("hygiene.placeholder", "error",
                              "Placeholder text added by Formatly: replace it with your own content.",
                              "Write this section, then delete the text in square brackets.", b.index))
        if rules.no_double_spaces:
            ctx.log.checked_rule("hygiene.double_space", severity="warning")
            # Tree diagrams and similar drawings use spaces on purpose.
            n = 0 if _BOX_DRAWING.search(b.text) else len(_DOUBLE_SPACE.findall(b.text))
            if n:
                ctx.log.add(Issue("hygiene.double_space", "warning",
                                  f"{n} place{'s' if n > 1 else ''} with two or more spaces between words.",
                                  "Replace double spaces with single spaces (Ctrl+H).", b.index,
                                  fixable=True))

