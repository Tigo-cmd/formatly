"""Shared pieces for checks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cached_property

from ..docmodel import Block, DocumentModel, ParaFormat, word_count
from ..issues import IssueLog
from ..outline import Outline
from ..rulebook import Rulebook, TextRules
from ..units import TWIPS_PER_PT, fmt_length, fmt_pt

SIZE_TOLERANCE = 0.25  # points
SPACING_TOLERANCE = 20  # twips (1 pt)
INDENT_TOLERANCE = 72  # twips (0.05 in)
MULTIPLE_TOLERANCE = 0.05

CAPTION_RE = re.compile(
    r"^\s*(table|figure|fig\.?|chart|plate|graph)\s+(\d+(?:\s*[.\-–]\s*\d+)*)\s*[:.\-–—]?\s*(.*)$",
    re.I | re.S,
)
ALIGN_WORDS = {"justify": "justified", "left": "left-aligned", "center": "centred", "right": "right-aligned"}


@dataclass
class Caption:
    block: int
    kind: str  # table / figure
    number: str  # "4.1"
    parts: tuple[int, ...]
    target: int | None  # the table or figure block it belongs to
    position: str | None  # above / below its target


@dataclass
class Context:
    model: DocumentModel
    rules: Rulebook
    outline: Outline
    log: IssueLog = field(default_factory=IssueLog)
    captions: dict[int, Caption] = field(default_factory=dict)

    @property
    def blocks(self) -> list[Block]:
        return self.model.blocks

    def nonempty_neighbours(self, index: int, direction: int, limit: int = 2) -> list[Block]:
        out = []
        i = index + direction
        while 0 <= i < len(self.blocks) and len(out) < limit:
            b = self.blocks[i]
            if not b.is_empty:
                out.append(b)
            i += direction
        return out

    def in_body_text_area(self, b: Block) -> bool:
        sec = self.outline.section_at(b.index)
        if sec is None or b.index < self.outline.title_page_end:
            return False
        if sec.kind == "chapter":
            return True
        specs = {s.id: s for s in (*self.rules.structure.preliminaries, *self.rules.structure.back_matter)}
        spec = specs.get(sec.spec_id)
        return bool(spec and spec.body_text)

    @cached_property
    def body_blocks(self) -> list[Block]:
        """Paragraphs held to the body text rules."""
        out = []
        for b in self.blocks:
            if (b.kind != "p" or b.is_empty or not b.text.strip() or b.in_toc
                    or b.index in self.outline.headings or b.index in self.outline.listing_blocks
                    or b.index in self.captions or not self.in_body_text_area(b)):
                continue
            out.append(b)
        return out

    def is_prose(self, b: Block) -> bool:
        """A real paragraph of writing, not a short line, list item or label."""
        return word_count(b.text) >= 12 and not self.model.para_format(b).numbered

    @cached_property
    def text_blocks(self) -> list[Block]:
        """Every paragraph of running text: body, excluding captions and listings."""
        return [b for b in self.blocks
                if b.kind == "p" and not b.in_toc and b.index not in self.outline.listing_blocks
                and b.index not in self.captions and b.index >= self.outline.title_page_end]


def spacing_matches(pf: ParaFormat, want) -> bool:
    if want.rule == "multiple":
        return pf.line_rule == "multiple" and abs(pf.line_value - want.value) <= MULTIPLE_TOLERANCE
    return pf.line_rule == want.rule and abs(pf.line_value - want.value) <= 0.5


def describe_spacing(rule: str, value: float) -> str:
    if rule == "multiple":
        return {1.0: "single", 1.5: "1.5 lines", 2.0: "double"}.get(round(value, 2), f"{value:g} lines")
    return f"{'exactly' if rule == 'exact' else 'at least'} {value:g} pt"


def text_problems(ctx: Context, b: Block, want: TextRules, *, layout: bool = True,
                  check_first_line: bool = True) -> list[tuple[str, str, str]]:
    """Compare a paragraph with text rules. Returns (rule suffix, message, hint)."""
    out: list[tuple[str, str, str]] = []
    runs = ctx.model.run_formats(b)
    if runs:
        if want.font:
            wrong = sorted({rf.font for _, rf in runs if rf.font.lower() != want.font.lower()})
            if wrong:
                out.append(("font", f"Font is {', '.join(wrong)}. Required: {want.font}.",
                            f"Select the text and set the font to {want.font}."))
        if want.size:
            wrong_sizes = sorted({rf.size for _, rf in runs if abs(rf.size - want.size) > SIZE_TOLERANCE})
            if wrong_sizes:
                sizes = ", ".join(f"{s:g}" for s in wrong_sizes)
                out.append(("size", f"Font size is {sizes} pt. Required: {want.size:g} pt.",
                            f"Set the font size to {want.size:g}."))
        if want.bold is not None:
            all_bold = all(rf.bold for _, rf in runs)
            if want.bold and not all_bold:
                out.append(("bold", "Should be bold.", "Make the whole line bold (Ctrl+B)."))
            elif not want.bold and all_bold:
                out.append(("bold", "Should not be bold.", "Remove the bold (Ctrl+B)."))
        if want.italic is not None:
            all_italic = all(rf.italic for _, rf in runs)
            if want.italic and not all_italic:
                out.append(("italic", "Should be italic.", "Make it italic (Ctrl+I)."))
            elif not want.italic and all_italic:
                out.append(("italic", "Should not be italic.", "Remove the italics (Ctrl+I)."))
        if want.all_caps:
            letters = [c for c in b.text if c.isalpha()]
            shown_caps = all(rf.caps for _, rf in runs)
            if letters and not shown_caps and any(c.islower() for c in letters):
                out.append(("caps", "Should be in CAPITAL LETTERS.",
                            "Type it in capitals, or select it and use Home > Change Case > UPPERCASE."))
    if not layout:
        return out
    pf = ctx.model.para_format(b)
    if want.alignment and pf.alignment != want.alignment:
        out.append(("alignment", f"Text is {ALIGN_WORDS[pf.alignment]}. Required: {ALIGN_WORDS[want.alignment]}.",
                    f"Set the paragraph alignment to {ALIGN_WORDS[want.alignment]}."))
    if want.line_spacing and not spacing_matches(pf, want.line_spacing):
        have = describe_spacing(pf.line_rule, pf.line_value)
        need = describe_spacing(want.line_spacing.rule, want.line_spacing.value)
        out.append(("line_spacing", f"Line spacing is {have}. Required: {need}.",
                    f"Home > Line and Paragraph Spacing: choose {need}."))
    for attr, label in (("space_before", "before"), ("space_after", "after")):
        need = getattr(want, attr)
        have = pf.before if attr == "space_before" else pf.after
        if need is not None and abs(have - need) > SPACING_TOLERANCE:
            out.append((attr, f"Spacing {label} the paragraph is {fmt_pt(have)}. Required: {fmt_pt(need)}.",
                        f"Paragraph settings > Spacing {label.capitalize()}: {need / TWIPS_PER_PT:g} pt."))
    if check_first_line and want.first_line_indent is not None and not pf.numbered:
        if abs(pf.first_line - want.first_line_indent) > INDENT_TOLERANCE:
            have = "none" if pf.first_line == 0 else fmt_length(abs(pf.first_line))
            if pf.first_line < 0:
                have = f"a hanging indent of {have}"
            out.append(("first_line_indent",
                        f"First-line indent is {have}. Required: {fmt_length(want.first_line_indent)}.",
                        "Paragraph settings > Indentation > Special: First line."))
    return out
