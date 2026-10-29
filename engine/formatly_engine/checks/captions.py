"""Tables and figures: captions, their position, numbering, and mentions in the text."""

from __future__ import annotations

import re

from ..docmodel import word_count
from ..issues import Issue
from docx.oxml.ns import qn

from ..docmodel import Block, iter_flow
from .base import CAPTION_RE, Caption, Context, text_problems

FIGURE_WORDS = ("figure", "fig", "fig.", "chart", "plate", "graph")


def _kind(word: str) -> str:
    return "table" if word.lower() == "table" else "figure"


def find_captions(ctx: Context) -> dict[int, Caption]:
    """Caption paragraphs, told apart from sentences that merely start with "Table 4.1 shows"."""
    out: dict[int, Caption] = {}
    outline = ctx.outline
    parsed = []
    for b in ctx.blocks:
        if b.kind != "p" or b.is_empty or b.in_toc or b.index in outline.listing_blocks:
            continue
        m = CAPTION_RE.match(b.text.strip())
        if not m or word_count(b.text) > 40:
            continue
        kind = _kind(m.group(1))
        number = re.sub(r"\s+", "", m.group(2)).replace("-", ".").replace("–", ".").rstrip(".")
        parts = tuple(int(x) for x in number.split(".") if x)
        if kind == "figure" and b.has_image:  # picture and caption in one paragraph
            out[b.index] = Caption(b.index, kind, number, parts, b.index,
                                   "below" if _image_first(b.el) else "above", inline=True)
        else:
            parsed.append((b, kind, number, parts))
    for b, kind, number, parts in parsed:
        def is_target(x, kind=kind):
            if kind == "table":
                return x.kind == "tbl"
            return x.has_image and x.index not in out  # not a picture that has its own caption
        above_target = next((x for x in ctx.nonempty_neighbours(b.index, +1, 1) if is_target(x)), None)
        below_target = next((x for x in ctx.nonempty_neighbours(b.index, -1, 2) if is_target(x)), None)
        pf = ctx.model.para_format(b)
        styled = "caption" in pf.style_name.lower()
        # A short centred or italic "Figure 4.5 …" line is a caption even if its
        # picture is misplaced; a sentence ("Table 4.1 shows …") is not.
        looks_like = (word_count(b.text) <= 25 and not b.text.strip().endswith(".")
                      and (pf.alignment == "center" or all(rf.italic for _, rf in ctx.model.run_formats(b))))
        if above_target is None and below_target is None and not (styled or looks_like):
            continue
        if above_target is not None:
            target, position = above_target.index, "above"
        elif below_target is not None:
            target, position = below_target.index, "below"
        else:
            target, position = None, None
        out[b.index] = Caption(b.index, kind, number, parts, target, position)
    return out


def _image_first(p_el) -> bool:
    """Does the picture come before the text in this paragraph?"""
    for node in iter_flow(p_el, (qn("w:t"), qn("w:drawing"), qn("w:pict"))):
        if node.tag == qn("w:t"):
            if (node.text or "").strip():
                return False
        else:
            return True
    return True


def figure_groups(ctx: Context) -> list[list[int]]:
    """Pictures inside chapters, with consecutive picture paragraphs (a figure in
    several parts, such as a flowchart) grouped together."""
    groups: list[list[int]] = []
    current: list[int] = []
    for b in ctx.blocks:
        in_chapter = ctx.outline.chapter_at(b.index) is not None
        if in_chapter and b.kind == "p" and b.has_image:
            current.append(b.index)
            if b.index in ctx.captions:  # a picture with its own caption is a complete figure
                groups.append(current)
                current = []
        elif b.is_empty and current:
            continue
        else:
            if current:
                groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def check_captions(ctx: Context) -> None:
    rules = ctx.rules.captions
    outline = ctx.outline
    captioned = {c.target: c for c in ctx.captions.values() if c.target is not None}

    # Every table and figure inside a chapter needs a caption, in the right place.
    targets = [("table", rules.table_position, [b.index])
               for b in ctx.blocks if b.kind == "tbl" and outline.chapter_at(b.index) is not None]
    targets += [("figure", rules.figure_position, g) for g in figure_groups(ctx)]
    for kind, want, members in sorted(targets, key=lambda t: t[2][0]):
        b = ctx.blocks[members[0]]
        ctx.log.checked_rule("captions.missing")
        cap = next((captioned[i] for i in members if i in captioned), None)
        if cap is None:
            ctx.log.add(Issue("captions.missing", "error", f"This {kind} has no caption.",
                              f"Add a caption {want or 'next to it'}, e.g. “{kind.capitalize()} "
                              f"{outline.chapter_at(b.index)}.1: Title”.", b.index))
            continue
        if want and not cap.inline:
            ctx.log.checked_rule("captions.position")
            if cap.position != want:
                ctx.log.add(Issue("captions.position", "error",
                                  f"{kind.capitalize()} caption should be {want} the {kind}, not {cap.position}.",
                                  f"Move “{kind.capitalize()} {cap.number}” {want} the {kind}.",
                                  cap.block, fixable=True,
                                  data={"target": (members[0] if want == "above" else members[-1]),
                                        "want": want}))

    # How captions and table text look.
    cap_want = ctx.rules.caption_text()
    for cap in ctx.captions.values():
        ctx.log.checked_rule("captions.format")
        b = ctx.blocks[cap.block]
        for suffix, msg, hint in text_problems(ctx, b, cap_want, check_first_line=False):
            ctx.log.add(Issue("captions.format", "error", f"Caption: {msg}", hint, cap.block, fixable=True,
                              data={"aspect": suffix}))
    table_want = ctx.rules.table_text()
    for b in ctx.blocks:
        if b.kind != "tbl" or outline.chapter_at(b.index) is None:
            continue
        ctx.log.checked_rule("captions.table_text")
        problems: dict[str, tuple[str, str]] = {}
        for p_el in b.el.iter(qn("w:p")):
            cell = Block(index=-1, kind="p", el=p_el, section=b.section, text="x")
            for suffix, msg, hint in text_problems(ctx, cell, table_want, layout=False):
                problems.setdefault(suffix, (msg, hint))
        for suffix, (msg, hint) in problems.items():
            ctx.log.add(Issue("captions.table_text", "error", f"Text in this table: {msg}", hint, b.index,
                              fixable=True, data={"aspect": suffix}))

    # Numbering.
    last: dict[tuple[str, int | None], int] = {}
    for cap in sorted(ctx.captions.values(), key=lambda c: c.block):
        chapter = outline.chapter_at(cap.block)
        label = f"{cap.kind.capitalize()} {cap.number}"
        if rules.numbering == "by_chapter" and chapter is not None:
            ctx.log.checked_rule("captions.numbering")
            if len(cap.parts) != 2 or cap.parts[0] != chapter:
                ctx.log.add(Issue("captions.numbering", "error",
                                  f"{label} is in Chapter {chapter}; number it {chapter}.x "
                                  f"(e.g. {cap.kind.capitalize()} {chapter}.1).",
                                  "Number tables and figures by chapter.", cap.block))
                continue
            key, n = (cap.kind, chapter), cap.parts[1]
        elif rules.numbering == "sequential":
            ctx.log.checked_rule("captions.numbering")
            key, n = (cap.kind, None), cap.parts[-1]
        else:
            continue
        expected = last.get(key, 0) + 1
        if n != expected:
            prefix = f"{chapter}." if rules.numbering == "by_chapter" else ""
            ctx.log.add(Issue("captions.numbering", "warning",
                              f"{label} is out of sequence; expected {cap.kind.capitalize()} {prefix}{expected}.",
                              "Check for missing or repeated numbers.", cap.block))
        last[key] = n

    # Mentioned in the text.
    if rules.must_be_referenced:
        text = "\n".join(b.text for b in ctx.text_blocks)
        for cap in ctx.captions.values():
            ctx.log.checked_rule("captions.referenced", severity="warning")
            words = r"(?:table|tab\.)" if cap.kind == "table" else r"(?:figure|fig\.?|chart|plate|graph)"
            pattern = rf"\b{words}\s*{re.escape(cap.number)}(?![\d.]\d)"
            if not re.search(pattern, text, re.I):
                ctx.log.add(Issue("captions.referenced", "warning",
                                  f"{cap.kind.capitalize()} {cap.number} is never mentioned in the text.",
                                  f"Refer to it in your discussion, e.g. “as shown in {cap.kind.capitalize()} "
                                  f"{cap.number}”.", cap.block))
