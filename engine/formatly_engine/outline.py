"""Finding the document's outline: title page, sections, chapters, headings.

Students rarely use Word's heading styles consistently, so headings are
recognised from several signals: the style, the outline level, numbering such
as "2.1", the "CHAPTER ONE" pattern, and the names in the rulebook.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from .docmodel import Block, DocumentModel, word_count
from .rulebook import Rulebook

NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
                "seventeen", "eighteen", "nineteen", "twenty"]
_ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}

CHAPTER_RE = re.compile(r"^\s*chapter\s+([a-z]+|\d+)\b\s*[:.\-–—]?\s*(.*)$", re.I | re.S)
# "Abstract ........ v" or "Abstract<TAB>v": a line of a typed table of contents
LISTING_LINE_RE = re.compile(r"(\t|\.{3,}|…|_{3,})\s*[0-9ivxlcIVXLC]+\s*$")
NUMBERED_HEADING_RE = re.compile(r"^\s*(\d+(?:\.\d+){1,3})\.?\s+(\S.*)$", re.S)


def roman_to_int(s: str) -> int | None:
    s = s.lower()
    if not s or any(c not in _ROMAN for c in s):
        return None
    total = 0
    for i, c in enumerate(s):
        v = _ROMAN[c]
        total += -v if i + 1 < len(s) and _ROMAN[s[i + 1]] > v else v
    return total


def chapter_number(token: str) -> tuple[int | None, str]:
    """Parse "ONE" / "1" / "I" into (number, style)."""
    t = token.lower()
    if t.isdigit():
        return int(t), "digits"
    if t in NUMBER_WORDS:
        return NUMBER_WORDS.index(t), "words"
    r = roman_to_int(t)
    if r:
        return r, "roman"
    return None, "unknown"


def normalize(text: str) -> str:
    t = text.lower().replace("&", " and ")
    t = re.sub(r"^\s*(\d+(\.\d+)*|[ivx]+)[.)]?\s+", "", t)  # leading numbering
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def names_match(text: str, names: list[str]) -> bool:
    n = normalize(text)
    if not n:
        return False
    for name in names:
        m = normalize(name)
        if n == m or n.rstrip("s") == m.rstrip("s"):
            return True
        if len(m) >= 6 and difflib.SequenceMatcher(None, n, m).ratio() >= 0.88:
            return True
    return False


@dataclass
class SectionHit:
    spec_id: str  # "chapter_3" for chapters
    kind: str  # preliminary / chapter / back
    order: int  # position in the expected order
    block: int  # heading block
    heading: str
    number: int | None = None  # chapter number
    number_style: str | None = None
    title: str = ""  # chapter title text
    title_block: int | None = None
    end: int = 0  # first block after this section


@dataclass
class HeadingInfo:
    block: int
    level: int
    text: str
    source: str  # style / outline / numbering / chapter / section
    numbering: str | None = None  # "2.1" in "2.1 Conceptual Review"


@dataclass
class Outline:
    hits: list[SectionHit] = field(default_factory=list)
    duplicates: list[SectionHit] = field(default_factory=list)
    headings: dict[int, HeadingInfo] = field(default_factory=dict)
    title_page_end: int = 0  # blocks before this are the title page
    listing_blocks: set[int] = field(default_factory=set)  # typed TOC / list lines
    toc_field: bool = False
    n_blocks: int = 0

    def hit(self, spec_id: str) -> SectionHit | None:
        return next((h for h in self.hits if h.spec_id == spec_id), None)

    def section_at(self, index: int) -> SectionHit | None:
        found = None
        for h in self.hits:
            if h.block <= index:
                found = h
            else:
                break
        return found

    def chapter_at(self, index: int) -> int | None:
        s = self.section_at(index)
        return s.number if s and s.kind == "chapter" else None

    @property
    def chapters(self) -> list[SectionHit]:
        return [h for h in self.hits if h.kind == "chapter"]


def _is_candidate(model: DocumentModel, b: Block) -> bool:
    if b.kind != "p" or b.is_empty:
        return False
    if b.in_toc and model.para_format(b).style_name.lower() not in ("toc heading", "contents heading"):
        return False
    text = b.text.strip()
    if len(text) > 160 or word_count(text) > 22:
        return False
    return not LISTING_LINE_RE.search(text)


def style_level(model: DocumentModel, b: Block) -> tuple[int | None, str]:
    pf = model.para_format(b)
    name = pf.style_name.lower()
    m = re.match(r"heading\s*(\d)", name)
    if m:
        return int(m.group(1)), "style"
    if name == "title":
        return 1, "style"
    if pf.outline_level is not None and pf.outline_level < 9:
        return pf.outline_level + 1, "outline"
    return None, ""


def build_outline(model: DocumentModel, rules: Rulebook) -> Outline:
    out = Outline(n_blocks=len(model.blocks), toc_field=any(b.in_toc for b in model.blocks))
    st = rules.structure
    blocks = model.blocks
    candidates = [b for b in blocks if _is_candidate(model, b)]

    order: dict[str, int] = {}
    for spec in st.preliminaries:
        order[spec.id] = len(order)
    for ch in st.chapters:
        order[f"chapter_{ch.number}"] = len(order)
    for spec in st.back_matter:
        order[spec.id] = len(order)
    chapter_order_base = len(st.preliminaries)

    hits: list[SectionHit] = []
    title_blocks: set[int] = set()

    # 1. Chapters, from "CHAPTER ONE" style labels.
    for b in candidates:
        m = CHAPTER_RE.match(b.text.strip())
        if not m:
            continue
        num, style = chapter_number(m.group(1))
        if num is None:
            continue
        title = m.group(2).strip()
        # "Chapter one introduces the study." is a sentence, not a heading.
        if title and (title[0].islower() or b.text.strip().endswith((".", ",", ";"))):
            continue
        title_block = b.index if title else None
        if not title:
            nxt = next((x for x in blocks[b.index + 1:b.index + 4] if not x.is_empty), None)
            if nxt is not None and _is_candidate(model, nxt) and not CHAPTER_RE.match(nxt.text.strip()):
                title, title_block = nxt.text.strip(), nxt.index
                title_blocks.add(nxt.index)
        spec_id = f"chapter_{num}"
        hits.append(SectionHit(
            spec_id=spec_id, kind="chapter",
            order=order.get(spec_id, chapter_order_base + num - 1),
            block=b.index, heading=b.text.strip(), number=num, number_style=style,
            title=title, title_block=title_block,
        ))
    first_chapter = min((h.block for h in hits), default=None)

    # 2. Named sections (preliminaries before the first chapter, back matter after).
    for b in candidates:
        if b.index in title_blocks or any(h.block == b.index for h in hits) or word_count(b.text) > 8:
            continue
        before_chapters = first_chapter is None or b.index < first_chapter
        groups = [("preliminary", st.preliminaries)] if before_chapters else []
        if first_chapter is None or b.index > first_chapter:
            groups.append(("back", st.back_matter))
        for kind, specs in groups:
            spec = next((s for s in specs if names_match(b.text, [s.title, *s.aliases])), None)
            if spec:
                hits.append(SectionHit(spec_id=spec.id, kind=kind, order=order[spec.id],
                                       block=b.index, heading=b.text.strip()))
                break

    hits.sort(key=lambda h: h.block)
    seen: set[str] = set()
    for h in hits:
        if h.spec_id in seen:
            out.duplicates.append(h)
        else:
            seen.add(h.spec_id)
            out.hits.append(h)
    all_hits = sorted(out.hits + out.duplicates, key=lambda h: h.block)
    for i, h in enumerate(all_hits):
        h.end = all_hits[i + 1].block if i + 1 < len(all_hits) else len(blocks)

    out.title_page_end = all_hits[0].block if all_hits else 0

    # 3. Typed tables of contents and lists of tables / figures.
    for h in out.hits:
        if h.spec_id in ("table_of_contents", "list_of_tables", "list_of_figures", "list_of_abbreviations"):
            for b in blocks[h.block + 1:h.end]:
                if b.kind == "p" and not b.is_empty:
                    out.listing_blocks.add(b.index)

    # 4. Headings and their levels.
    for h in all_hits:
        out.headings[h.block] = HeadingInfo(h.block, 1, h.heading, "chapter" if h.kind == "chapter" else "section")
        if h.title_block is not None and h.title_block != h.block:
            out.headings[h.title_block] = HeadingInfo(h.title_block, 1, h.title, "chapter")
    for b in candidates:
        if b.index in out.headings or b.index in out.listing_blocks or b.index < out.title_page_end:
            continue
        text = b.text.strip()
        level, source = style_level(model, b)
        m = NUMBERED_HEADING_RE.match(text)
        numbering = m.group(1) if m else None
        if level is None and m and m.group(2)[:1].isupper() and not text.endswith((".", ",", ";")):
            level, source = numbering.count(".") + 1, "numbering"
        if level is not None:
            out.headings[b.index] = HeadingInfo(b.index, level, text, source, numbering)
    return out
