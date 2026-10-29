"""Reference list and in-text citations (author-date styles), and word limits.

These are rule-based first passes. The AI checks in a later phase handle the
long tail of reference formats; everything here is reported as a warning
unless it is certain.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from dataclasses import dataclass

from docx.oxml.ns import qn

from ..docmodel import Block, iter_flow, word_count
from ..issues import Issue
from ..units import fmt_length
from .base import INDENT_TOLERANCE, Context, text_problems

AUTHOR_DATE = {"apa7", "apa6", "harvard", "chicago"}
YEAR = r"(?:\d{4}[a-z]?|n\.\s?d\.?|in press|forthcoming)"
REF_YEAR_RE = re.compile(rf"\(\s*({YEAR})\s*(?:,[^)]*)?\)", re.I)
PAREN_RE = re.compile(rf"\(([^()]{{0,400}}?\b{YEAR}[^()]{{0,120}}?)\)", re.I)
PART_RE = re.compile(
    rf"^(?P<names>[^\d()]+?),?\s+(?P<years>{YEAR}(?:\s*,\s*{YEAR})*)\b", re.I)
NARRATIVE_RE = re.compile(
    rf"(?P<pre>\b\w+\s+)?(?P<name>[A-Z][\w'’\-]+)(?:\s+et\s+al\.?|\s+(?:and|&)\s+[A-Z][\w'’\-]+)?"
    rf"\s*\((?P<years>{YEAR}(?:\s*,\s*{YEAR})*)(?:[,;][^)]*)?\)")
NOT_AUTHOR_BEFORE = {"in", "at", "from", "the", "during", "since", "within", "until", "till"}
PREFIXES = re.compile(r"^(see also|see|e\.g\.,?|cf\.|i\.e\.,?|as cited in|for example,?)\s+", re.I)
SORT_STRIP = re.compile(r"^[^A-Za-zÀ-ɏ]+")


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def _surname_key(name: str) -> str:
    words = re.findall(r"[\w'’\-]+", name)
    return _fold(words[0]).strip("'’-") if words else ""


def _year_key(y: str) -> str:
    y = y.lower().replace(" ", "")
    return "n.d." if y.startswith("n.d") else y


@dataclass
class Citation:
    block: int
    surname: str
    year: str
    text: str
    names: tuple[str, ...] = ()  # every capitalised word of the author part, folded


def _name_words(names: str) -> tuple[str, ...]:
    return tuple(_fold(w).strip("'’-") for w in re.findall(r"[A-Z\u00C0-\u024F][\w'’\-]+", names)
                 if w.lower() not in ("et", "al", "and", "mr", "mrs", "dr", "prof", "engr"))


@dataclass
class Reference:
    block: int
    surname: str
    year: str | None
    text: str


def parse_citations(blocks: list[Block]) -> list[Citation]:
    out: list[Citation] = []
    for b in blocks:
        text = b.text
        spans = []
        for m in PAREN_RE.finditer(text):
            spans.append(m.span())
            for part in m.group(1).split(";"):
                part = PREFIXES.sub("", part.strip())
                pm = PART_RE.match(part)
                if not pm:
                    continue
                names = pm.group("names").strip()
                if not names[:1].isupper() or word_count(names) > 8:
                    continue
                for y in re.findall(YEAR, pm.group("years"), re.I):
                    out.append(Citation(b.index, _surname_key(names), _year_key(y), f"({part})",
                                        _name_words(names)))
        for m in NARRATIVE_RE.finditer(text):
            if any(s <= m.start("name") < e for s, e in spans):
                continue
            pre = (m.group("pre") or "").strip().lower()
            if pre in NOT_AUTHOR_BEFORE:
                continue
            for y in re.findall(YEAR, m.group("years"), re.I):
                surname = _surname_key(m.group("name"))
                out.append(Citation(b.index, surname, _year_key(y), m.group(0)[len(m.group("pre") or ""):],
                                    (surname,)))
    return out


@dataclass
class Entry:
    """One reference, which a writer may have broken over several paragraphs."""

    blocks: list[Block]

    @property
    def first(self) -> Block:
        return self.blocks[0]

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(b.text for b in self.blocks)).strip()


# "Okafor, C." or "Devivara Prasad, G." at the start of a line: a new reference.
ENTRY_START_RE = re.compile(r"^[A-Z\u00C0-\u024F][\w'’\-]+(?:\s[A-Z][\w'’\-]+){0,3},\s+[A-Z]")


def parse_reference(entry: Entry) -> Reference:
    text = entry.text
    ym = REF_YEAR_RE.search(text[:300])
    return Reference(entry.first.index, _surname_key(re.split(r"[,.(]", text, maxsplit=1)[0]),
                     _year_key(ym.group(1)) if ym else None, text)


def sort_key(text: str) -> str:
    return _fold(SORT_STRIP.sub("", text))


def reference_blocks(ctx: Context) -> list[Block]:
    hit = ctx.outline.hit("references")
    if hit is None:
        return []
    return [b for b in ctx.blocks[hit.block + 1:hit.end]
            if b.kind == "p" and not b.is_empty and b.index not in ctx.outline.headings
            and word_count(b.text) >= 1]


def _has_layout_marks(p_el) -> bool:
    for node in iter_flow(p_el, (qn("w:tab"), qn("w:br"), qn("w:cr"))):
        if node.tag != qn("w:br") or node.get(qn("w:type")) in (None, "textWrapping"):
            return True
    return False


def reference_entries(ctx: Context) -> list[Entry]:
    """Paragraphs of the reference list grouped into references: a line with no
    year in brackets that does not start "Surname, X." continues the one before."""
    entries: list[Entry] = []
    for b in reference_blocks(ctx):
        text = b.text.strip()
        # A reference never begins with a lowercase word: that is a wrapped line.
        starts = not text[:1].islower() and (bool(REF_YEAR_RE.search(text[:200]))
                                             or bool(ENTRY_START_RE.match(text)))
        if entries and not starts:
            entries[-1].blocks.append(b)
        else:
            entries.append(Entry([b]))
    return entries


def check_references(ctx: Context) -> None:
    rules = ctx.rules.references
    entries = reference_entries(ctx)
    if not entries:
        return

    # Look of each entry.
    want = ctx.rules.reference_text()
    for entry in entries:
        b = entry.first
        for suffix in ("font", "size", "line_spacing"):
            ctx.log.checked_rule(f"references.{suffix}")
        seen: set[str] = set()
        for part in entry.blocks:
            for suffix, msg, hint in text_problems(ctx, part, want, check_first_line=False):
                if suffix not in seen:
                    seen.add(suffix)
                    ctx.log.add(Issue(f"references.{suffix}", "error", f"Reference: {msg}", hint, b.index,
                                      fixable=True, data={"blocks": [x.index for x in entry.blocks]}))
        ctx.log.checked_rule("references.layout")
        if any(_has_layout_marks(x.el) for x in entry.blocks):
            ctx.log.add(Issue(
                "references.layout", "error",
                "This reference uses tabs or line breaks to arrange its lines.",
                "Remove them and let the hanging indent wrap the lines.", b.index,
                fixable=True, data={"blocks": [x.index for x in entry.blocks]}))
        ctx.log.checked_rule("references.split")
        if len(entry.blocks) > 1:
            ctx.log.add(Issue(
                "references.split", "error",
                f"This reference is broken over {len(entry.blocks)} paragraphs (Enter and Tab at the end of "
                "lines). Keep each reference in one paragraph; the hanging indent wraps it.",
                "Join the lines into one paragraph, then set a hanging indent.", b.index,
                fixable=not any(x.ends_section for x in entry.blocks),
                data={"blocks": [x.index for x in entry.blocks]}))
        if rules.hanging_indent:
            ctx.log.checked_rule("references.hanging_indent")
            pf = ctx.model.para_format(b)
            if abs(pf.first_line + rules.hanging_indent) > INDENT_TOLERANCE or \
                    abs(pf.ind_left - rules.hanging_indent) > INDENT_TOLERANCE:
                ctx.log.add(Issue(
                    "references.hanging_indent", "error",
                    f"Reference needs a hanging indent of {fmt_length(rules.hanging_indent)}.",
                    "Paragraph settings > Indentation > Special: Hanging, By: "
                    f"{fmt_length(rules.hanging_indent)}.", b.index, fixable=True))

    refs = [parse_reference(e) for e in entries]

    # Order.
    if rules.order == "alphabetical":
        ctx.log.checked_rule("references.order")
        keys = [sort_key(r.text) for r in refs]
        out_of_order = [i for i in range(1, len(refs)) if keys[i] < keys[i - 1]]
        for i in out_of_order:
            ctx.log.add(Issue(
                "references.order", "error",
                f"Not in alphabetical order: this should come before “{refs[i - 1].text[:40]}…”.",
                "Sort the reference list A to Z by the first author's surname.", refs[i].block, fixable=True))

    if rules.max_age_years:
        oldest = date.today().year - rules.max_age_years
        for r in refs:
            ctx.log.checked_rule("references.age", severity=rules.age_severity)
            if r.year and r.year[:4].isdigit() and int(r.year[:4]) < oldest:
                ctx.log.add(Issue("references.age", rules.age_severity,
                                  f"This source is from {r.year[:4]}. Sources should be from {oldest} or later "
                                  f"(the last {rules.max_age_years} years).",
                                  "Replace it with a recent source, unless it is a key or classic work.",
                                  r.block, data={"year": int(r.year[:4]), "oldest": oldest}))

    if rules.style not in AUTHOR_DATE:
        return

    # Entry format (APA).
    for r in refs:
        ctx.log.checked_rule("references.format", severity="warning")
        author_part = r.text[:REF_YEAR_RE.search(r.text).start()] if REF_YEAR_RE.search(r.text) else r.text[:120]
        if r.year is None:
            ctx.log.add(Issue("references.format", "warning",
                              "No year in brackets after the author(s).",
                              "APA format: Author, A. A. (Year). Title. Source.", r.block))
        if rules.style == "apa7" and re.search(r"\bet\.?\s+al\b", author_part, re.I):
            ctx.log.add(Issue("references.format", "suggestion",
                              "APA 7 does not use “et al.” in the reference list.",
                              "List all authors (up to 20).", r.block))
        if rules.style in ("apa7", "apa6") and r.year and re.search(r",.*\sand\s", author_part):
            ctx.log.add(Issue("references.format", "suggestion",
                              "Use “&” before the last author, not “and”.",
                              "e.g. Okafor, C., & Bello, A. (2021).", r.block))
        if rules.style == "apa7" and re.search(r"\bdoi:\s*10\.", r.text, re.I):
            ctx.log.add(Issue("references.format", "suggestion",
                              "Write the DOI as a link.",
                              "APA 7: https://doi.org/10.xxxx/xxxxx", r.block))

    # Citations against the list.
    if not rules.check_citations:
        return
    citing_blocks = [b for b in ctx.text_blocks
                     if not b.is_empty and b.index not in ctx.outline.headings
                     and ctx.outline.section_at(b.index) is not None
                     and ctx.outline.section_at(b.index).spec_id not in ("references", "appendices")]
    citations = parse_citations(citing_blocks)
    by_surname: dict[str, list[Reference]] = {}
    for r in refs:
        by_surname.setdefault(r.surname, []).append(r)
    cited: set[int] = set()  # reference blocks that some citation points to

    reported: set[tuple[int, str, str]] = set()
    for c in citations:
        ctx.log.checked_rule("references.citation_missing", severity="warning")
        same_name = by_surname.get(c.surname, [])
        exact = [r for r in same_name if (r.year or "")[:4] == c.year[:4]]
        if exact:
            cited.update(r.block for r in exact)
            continue
        key = (c.block, c.surname, c.year)
        if key in reported:
            continue
        reported.add(key)
        # The author is in the list under another word of the name (a first name was used).
        other = [r for w in c.names if w != c.surname for r in by_surname.get(w, [])]
        candidates = same_name or other
        if candidates:
            r = next((x for x in candidates if (x.year or "")[:4] == c.year[:4]), candidates[0])
            cited.add(r.block)
            problems = []
            if not same_name:
                problems.append("cite the author by surname only")
            if (r.year or "")[:4] != c.year[:4]:
                problems.append(f"the reference list has this author with year {r.year or 'no date'}")
            ctx.log.add(Issue("references.citation_mismatch", "warning",
                              f"Citation {c.text.strip()[:60]}: {'; '.join(problems)}.",
                              f"Make the citation match the reference “{r.text[:60]}…”.",
                              c.block, data={"surname": c.surname, "year": c.year, "reference": r.block}))
            continue
        ctx.log.add(Issue("references.citation_missing", "warning",
                          f"Citation {c.text.strip()[:60]} is not in the reference list.",
                          "Add the source to the reference list, or correct the author or year so they match.",
                          c.block, data={"surname": c.surname, "year": c.year}))
    if citations:
        for r in refs:
            ctx.log.checked_rule("references.uncited", severity="warning")
            if r.block not in cited:
                ctx.log.add(Issue("references.uncited", "warning",
                                  "This reference is never cited in the text.",
                                  "Cite it where you use it, or remove it from the list.", r.block))


def check_limits(ctx: Context) -> None:
    rules = ctx.rules.limits
    hit = ctx.outline.hit("abstract")
    if hit and (rules.abstract_max_words or rules.abstract_min_words):
        words = sum(word_count(b.text) for b in ctx.blocks[hit.block + 1:hit.end]
                    if b.kind == "p" and b.index not in ctx.outline.headings)
        ctx.log.checked_rule("limits.abstract")
        if rules.abstract_max_words and words > rules.abstract_max_words:
            ctx.log.add(Issue("limits.abstract", "error",
                              f"Abstract has {words} words. Maximum: {rules.abstract_max_words}.",
                              f"Shorten it by {words - rules.abstract_max_words} words.", hit.block,
                              data={"words": words}))
        if rules.abstract_min_words and words < rules.abstract_min_words:
            ctx.log.add(Issue("limits.abstract", "warning",
                              f"Abstract has {words} words. Minimum: {rules.abstract_min_words}.",
                              "Expand it to cover aim, method, findings and conclusion.", hit.block,
                              data={"words": words}))
    if rules.main_text_max_words:
        chapters = ctx.outline.chapters
        words = sum(word_count(b.text) for b in ctx.blocks
                    if b.kind == "p" and ctx.outline.chapter_at(b.index) is not None)
        ctx.log.checked_rule("limits.main_text")
        if chapters and words > rules.main_text_max_words:
            ctx.log.add(Issue("limits.main_text", "error",
                              f"The chapters have {words} words. Maximum: {rules.main_text_max_words}.",
                              "Shorten the main text.", chapters[0].block, data={"words": words}))
