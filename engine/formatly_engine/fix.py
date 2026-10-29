"""Auto-fix: correct formatting problems in place.

Only formatting, layout, numbering and reference order are changed. The
writer's words are never rewritten (the one exception is the chapter label,
e.g. "CHAPTER 1" to "CHAPTER ONE", which is a formatting convention).
The caller saves the result as a new file; the original is never modified.
"""

from __future__ import annotations

import copy
import re
from collections import Counter, defaultdict

from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Twips
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from lxml import etree

from .checks.base import Context, first_alignment
from .checks.page import PAPER
from .checks.references import parse_reference, reference_entries, sort_key
from .checks.structure import page_number_location
from .docmodel import Block, iter_flow, text_runs
from .issues import Issue
from .outline import CHAPTER_RE
from .rulebook import TextRules

ALIGN = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER,
         "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}
NUM_FMT = {"lower_roman": "lowerRoman", "upper_roman": "upperRoman", "decimal": "decimal"}


# --------------------------------------------------------------------------
# Low-level setters
# --------------------------------------------------------------------------

def set_run_font(r_el, name: str) -> None:
    rf = r_el.get_or_add_rPr().get_or_add_rFonts()
    for attr in ("asciiTheme", "hAnsiTheme", "cstheme"):
        rf.attrib.pop(qn(f"w:{attr}"), None)
    for attr in ("ascii", "hAnsi", "cs"):
        rf.set(qn(f"w:{attr}"), name)


def apply_text_rules(ctx: Context, b: Block, want: TextRules, aspects: set[str]) -> None:
    p = Paragraph(b.el, ctx.model.document._body)
    runs = [Run(r, p) for r in text_runs(b.el)]
    for run in runs:
        if "font" in aspects and want.font:
            set_run_font(run._r, want.font)
        if "size" in aspects and want.size:
            run.font.size = Pt(want.size)
        if "bold" in aspects and want.bold is not None:
            run.font.bold = want.bold
        if "italic" in aspects and want.italic is not None:
            run.font.italic = want.italic
        if "caps" in aspects and want.all_caps:
            run.font.all_caps = True
    pf = p.paragraph_format
    if "alignment" in aspects and want.alignment:
        pf.alignment = ALIGN[first_alignment(want.alignment)]
    if "line_spacing" in aspects and want.line_spacing:
        ls = want.line_spacing
        if ls.rule == "multiple":
            pf.line_spacing = ls.value
        else:
            pf.line_spacing = Pt(ls.value)
            pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY if ls.rule == "exact" else WD_LINE_SPACING.AT_LEAST
    if "space_before" in aspects and want.space_before is not None:
        pf.space_before = Twips(want.space_before)
    if "space_after" in aspects and want.space_after is not None:
        pf.space_after = Twips(want.space_after)
    if "first_line_indent" in aspects and want.first_line_indent is not None:
        pf.first_line_indent = Twips(want.first_line_indent)


def _set_pg_num(sect_pr, fmt: str | None = None, start: int | None | bool = False) -> None:
    """Set page number format and/or start. start=None removes a restart; False leaves it."""
    pg = sect_pr.find(qn("w:pgNumType"))
    if pg is None:
        pg = OxmlElement("w:pgNumType")
        # pgNumType goes after pgMar/paperSrc/pgBorders/lnNumType, before cols etc.
        anchor = None
        for tag in ("w:lnNumType", "w:pgBorders", "w:paperSrc", "w:pgMar", "w:pgSz"):
            anchor = sect_pr.find(qn(tag))
            if anchor is not None:
                break
        if anchor is not None:
            anchor.addnext(pg)
        else:
            sect_pr.append(pg)
    if fmt:
        pg.set(qn("w:fmt"), NUM_FMT.get(fmt, fmt))
    if start is None:
        pg.attrib.pop(qn("w:start"), None)
    elif start is not False:
        pg.set(qn("w:start"), str(start))


def _page_field_runs(font: str | None, size: float | None) -> list:
    runs = []
    for kind, payload in (("begin", None), ("instr", " PAGE "), ("separate", None), ("text", "1"), ("end", None)):
        r = OxmlElement("w:r")
        if font or size:
            rpr = OxmlElement("w:rPr")
            if font:
                rf = OxmlElement("w:rFonts")
                for a in ("ascii", "hAnsi", "cs"):
                    rf.set(qn(f"w:{a}"), font)
                rpr.append(rf)
            if size:
                sz = OxmlElement("w:sz")
                sz.set(qn("w:val"), str(int(size * 2)))
                rpr.append(sz)
            r.append(rpr)
        if kind in ("begin", "separate", "end"):
            fc = OxmlElement("w:fldChar")
            fc.set(qn("w:fldCharType"), kind)
            r.append(fc)
        elif kind == "instr":
            it = OxmlElement("w:instrText")
            it.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            it.text = payload
            r.append(it)
        else:
            t = OxmlElement("w:t")
            t.text = payload
            r.append(t)
        runs.append(r)
    return runs


# --------------------------------------------------------------------------
# Fixers, one per rule family
# --------------------------------------------------------------------------

def _fix_page(ctx: Context, issues: list[Issue]) -> int:
    rules = ctx.rules.page
    sections = ctx.model.sections
    wrong = {i.rule for i in issues}
    for i, sec in enumerate(sections):
        landscape = sec.page_width and sec.page_height and sec.page_width > sec.page_height
        keep_landscape = landscape and rules.allow_landscape_sections and i > 0
        if rules.size and wrong & {"page.size", "page.orientation"}:
            if "page.size" in wrong:
                w, h = PAPER[rules.size[0] if isinstance(rules.size, list) else rules.size]
            else:  # orientation only: keep this paper, just turn it
                w, h = sorted((round(sec.page_width / 635), round(sec.page_height / 635)))
            if keep_landscape or (rules.orientation == "landscape"):
                w, h = h, w
            sec.page_width, sec.page_height = Twips(w), Twips(h)
            orient = qn("w:orient")
            pgsz = sec._sectPr.find(qn("w:pgSz"))
            if pgsz is not None:
                if w > h:
                    pgsz.set(orient, "landscape")
                else:
                    pgsz.attrib.pop(orient, None)
        if rules.margins and "page.margins" in wrong:
            m = rules.margins
            top, bottom, left, right = m.top, m.bottom, m.left, m.right
            if keep_landscape:
                top, bottom, left, right = m.right, m.left, m.top, m.bottom
            sec.top_margin, sec.bottom_margin = Twips(top), Twips(bottom)
            sec.left_margin, sec.right_margin = Twips(left), Twips(right)
            if m.gutter is not None:
                sec.gutter = Twips(m.gutter)
    return len(issues)


def _fix_text(ctx: Context, issues: list[Issue], want_for) -> int:
    aspects: dict[int, set[str]] = defaultdict(set)
    for i in issues:
        if i.block is None:
            continue
        aspects[i.block].add(i.data.get("aspect") or i.rule.split(".", 1)[1])
    for idx, asp in aspects.items():
        want = want_for(idx)
        if want is not None:
            apply_text_rules(ctx, ctx.blocks[idx], want, asp)
    return len(issues)


def _fix_new_page(ctx: Context, issues: list[Issue]) -> int:
    for i in issues:
        Paragraph(ctx.blocks[i.block].el, None).paragraph_format.page_break_before = True
        # Empty lines that were pushing the heading down would now leave a blank gap.
        if i.data.get("blank_lines", 0) >= 3:
            for prev in ctx.blocks[i.block - i.data["blank_lines"]:i.block]:
                if prev.is_empty and not prev.ends_section and prev.el.getparent() is not None:
                    prev.el.getparent().remove(prev.el)
    return len(issues)


def _fix_chapter_label(ctx: Context, issues: list[Issue]) -> int:
    fixed = 0
    for i in issues:
        b = ctx.blocks[i.block]
        m = CHAPTER_RE.match(b.text)
        if not m:
            continue
        expected_number = i.data["expected"].split(" ", 1)[1]
        start, end = m.span(1)
        pos = 0
        for t in b.el.iter(qn("w:t")):
            text = t.text or ""
            if pos <= start and end <= pos + len(text):
                a, z = start - pos, end - pos
                original = text[a:z]
                replacement = expected_number if original.isupper() or original.isdigit() else expected_number.capitalize()
                t.text = text[:a] + replacement + text[z:]
                fixed += 1
                break
            pos += len(text)
    return fixed


def _fix_hygiene(ctx: Context, issues: list[Issue]) -> int:
    for i in issues:
        b = ctx.blocks[i.block]
        if i.rule == "hygiene.highlight":
            for r in b.el.iter(qn("w:r")):
                rpr = r.find(qn("w:rPr"))
                if rpr is not None:
                    for tag in ("w:highlight", "w:shd"):
                        for el in rpr.findall(qn(tag)):
                            rpr.remove(el)
        elif i.rule == "hygiene.colour":
            for r in text_runs(b.el):
                rpr = r.get_or_add_rPr()
                rpr._remove_color()
                rpr._add_color().set(qn("w:val"), "auto")
        elif i.rule == "hygiene.double_space":
            prev_space = False  # the text before ended with a space (it may be in another run)
            for t in iter_flow(b.el, (qn("w:t"),)):
                text = re.sub(r"(?<=\S) {2,}(?=\S|$)", " ", t.text or "")
                if prev_space and text.startswith(" "):
                    text = text.lstrip(" ")
                elif text.startswith("  ") and not prev_space:
                    text = " " + text.lstrip(" ")
                if text != (t.text or ""):
                    t.text = text
                    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                if text:
                    prev_space = text.endswith(" ")
    return len(issues)


def _move_elements_sorted(els: list, keyfunc) -> None:
    sorted_els = sorted(els, key=keyfunc)
    holders = []
    for el in els:
        holder = etree.Element("placeholder")
        el.addprevious(holder)
        holders.append(holder)
    for el in els:
        el.getparent().remove(el)
    for holder, el in zip(holders, sorted_els):
        holder.addprevious(el)
        holder.getparent().remove(holder)


def _space_run(like) -> etree._Element:
    r = OxmlElement("w:r")
    if like is not None and like.find(qn("w:rPr")) is not None:
        r.append(copy.deepcopy(like.find(qn("w:rPr"))))
    t = OxmlElement("w:t")
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = " "
    r.append(t)
    return r


def _tabs_to_spaces(p_el) -> None:
    """Tabs and line breaks used to arrange lines become plain spaces."""
    for node in list(iter_flow(p_el, (qn("w:tab"), qn("w:br"), qn("w:cr")))):
        if node.tag == qn("w:br") and node.get(qn("w:type")) not in (None, "textWrapping"):
            continue  # page and column breaks stay
        if node.getparent().tag == qn("w:r"):
            t = OxmlElement("w:t")
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            t.text = " "
            node.addprevious(t)
            node.getparent().remove(node)


def collapse_spaces(p_el) -> None:
    """No spaces at the start, one space between words, also across runs."""
    prev_space = True  # the start of the paragraph counts as a space
    for t in iter_flow(p_el, (qn("w:t"),)):
        text = re.sub(r" {2,}", " ", t.text or "")
        if prev_space:
            text = text.lstrip(" ")
        if text != (t.text or ""):
            t.text = text
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        if text:
            prev_space = text.endswith(" ")


def _trim(p_el, leading: bool) -> None:
    texts = [t for t in iter_flow(p_el, (qn("w:t"),))]
    for t in (texts if leading else reversed(texts)):
        new = (t.text or "").lstrip() if leading else (t.text or "").rstrip()
        t.text = new
        if new:
            break


def merge_paragraphs(first_el, others: list) -> None:
    """Join paragraphs into the first, one space between them. Words are unchanged."""
    for el in others:
        _tabs_to_spaces(el)
        _trim(first_el, leading=False)
        _trim(el, leading=True)
        runs = first_el.findall(qn("w:r"))
        first_el.append(_space_run(runs[-1] if runs else None))
        for child in [c for c in el if c.tag != qn("w:pPr")]:
            first_el.append(child)
        el.getparent().remove(el)
    _trim(first_el, leading=False)


def _fix_references(ctx: Context, issues: list[Issue]) -> int:
    fixed = 0
    splits = [i for i in issues if i.rule == "references.split"]
    for i in [i for i in issues if i.rule == "references.layout"]:
        for k in i.data["blocks"]:
            _tabs_to_spaces(ctx.blocks[k].el)
        fixed += 1
    for i in splits:
        els = [ctx.blocks[k].el for k in i.data["blocks"]]
        merge_paragraphs(els[0], els[1:])
        fixed += 1
    for i in [i for i in issues if i.rule in ("references.layout", "references.split")]:
        el = ctx.blocks[i.data["blocks"][0]].el
        if el.getparent() is not None:
            collapse_spaces(el)
    want = ctx.rules.reference_text()
    text_issues = [i for i in issues if i.rule not in ("references.order", "references.hanging_indent",
                                                       "references.split", "references.layout")]
    fixed += _fix_text(ctx, text_issues, lambda _idx: want)
    hanging = ctx.rules.references.hanging_indent
    for i in issues:
        if i.rule == "references.hanging_indent" and hanging:
            pf = Paragraph(ctx.blocks[i.block].el, None).paragraph_format
            pf.left_indent = Twips(hanging)
            pf.first_line_indent = Twips(-hanging)
            fixed += 1
    # Sorting moves whole references; after joining split ones, the next pass sorts.
    if any(i.rule == "references.order" for i in issues) and not splits:
        entries = reference_entries(ctx)
        if entries and all(len(e.blocks) == 1 for e in entries) and not any(e.first.ends_section for e in entries):
            texts = {id(e.first.el): sort_key(parse_reference(e).text) for e in entries}
            _move_elements_sorted([e.first.el for e in entries], lambda el: texts[id(el)])
            fixed += sum(1 for i in issues if i.rule == "references.order")
    return fixed


def _fix_captions(ctx: Context, issues: list[Issue]) -> int:
    fixed = 0
    for i in issues:
        cap = ctx.blocks[i.block]
        target = ctx.blocks[i.data["target"]]
        if cap.ends_section:
            continue
        if i.data["want"] == "above":
            target.el.addprevious(cap.el)
        else:
            target.el.addnext(cap.el)
        fixed += 1
    return fixed


def _fix_numbering(ctx: Context, issues: list[Issue]) -> int:
    rules = ctx.rules.page_numbering
    doc = ctx.model.document
    rules_found = {i.rule for i in issues}
    fixed = 0
    body_font, body_size = ctx.rules.body.font, ctx.rules.body.size

    if "numbering.present" in rules_found:
        where, align = (rules.position or "bottom_center").split("_")
        sec = ctx.model.sections[0]
        part = sec.footer if where == "bottom" else sec.header
        part.is_linked_to_previous = False
        p = part.paragraphs[0] if part.paragraphs else part.add_paragraph()
        p.paragraph_format.alignment = ALIGN[align]
        for r in _page_field_runs(body_font, body_size):
            p._p.append(r)
        sec.different_first_page_header_footer = True  # no number on the title page
        fixed += 1

    if "numbering.position" in rules_found and rules.position:
        where, align = rules.position.split("_")
        seen = set()
        for i in range(len(ctx.model.sections)):
            loc = page_number_location(ctx.model.sections, i)
            if loc and loc[1] == where and id(loc[0]) not in seen:
                seen.add(id(loc[0]))
                Paragraph(loc[0], None).paragraph_format.alignment = ALIGN[align]
        fixed += 1

    chapters = ctx.outline.chapters
    if not chapters:
        return fixed
    first = min(chapters, key=lambda h: h.block)
    ch_block = ctx.blocks[first.block]

    if "numbering.section_break" in rules_found:
        prev = ch_block.el.getprevious()
        if prev is None or prev.tag != qn("w:p"):
            prev = OxmlElement("w:p")
            ch_block.el.addprevious(prev)
        # The section that holds Chapter One is governed by the next sectPr after it.
        governing = None
        for b in ctx.blocks[first.block:]:
            if b.ends_section:
                governing = b.el.find(qn("w:pPr")).find(qn("w:sectPr"))
                break
        if governing is None:
            governing = doc.element.body.find(qn("w:sectPr"))
        new_sect = copy.deepcopy(governing)
        ppr = prev.find(qn("w:pPr"))
        if ppr is None:
            ppr = OxmlElement("w:pPr")
            prev.insert(0, ppr)
        old = ppr.find(qn("w:sectPr"))
        if old is not None:
            ppr.remove(old)
        ppr.append(new_sect)
        # Chapter One's section starts on a new page.
        t = governing.find(qn("w:type"))
        if t is not None:
            governing.remove(t)
        # A "different first page" setting belongs to the title page, not to Chapter One.
        title_pg = governing.find(qn("w:titlePg"))
        if title_pg is not None:
            governing.remove(title_pg)
        # Drop a manual page break that would now leave a blank page.
        for br in list(prev.iter(qn("w:br"))):
            if br.get(qn("w:type")) == "page":
                br.getparent().remove(br)
        Paragraph(ch_block.el, None).paragraph_format.page_break_before = None
        # Preliminary pages may show a title page: no number on it.
        _set_pg_num(new_sect, rules.preliminaries if rules.preliminaries not in (None, "none") else None,
                    start=None)
        _set_pg_num(governing, rules.main if rules.main not in (None, "none") else None,
                    start=rules.main_starts_at if rules.main_starts_at is not None else False)
        fixed += 1
        return fixed  # section layout changed; other numbering fixes would use stale indexes

    ch_section = ch_block.section
    sections = ctx.model.sections
    if "numbering.preliminaries" in rules_found and rules.preliminaries not in (None, "none"):
        for i in range(ch_section):
            _set_pg_num(sections[i]._sectPr, rules.preliminaries)
        fixed += 1
    if "numbering.main" in rules_found and rules.main not in (None, "none"):
        _set_pg_num(sections[ch_section]._sectPr, rules.main,
                    start=rules.main_starts_at if rules.main_starts_at is not None else False)
        for i in range(ch_section + 1, len(sections)):
            _set_pg_num(sections[i]._sectPr, rules.main, start=None)
        fixed += 1
    return fixed


def _section_elements(ctx: Context, start: int, end: int) -> list | None:
    """Elements of a section, without trailing blank lines; None if it holds a section break."""
    rng = ctx.blocks[start:end]
    while rng and rng[-1].is_empty:
        rng = rng[:-1]
    if any(b.ends_section for b in rng):
        return None
    return [b.el for b in rng]


def _fix_order(ctx: Context, issues: list[Issue]) -> int:
    fixed = 0
    for i in issues:
        d = i.data
        if d.get("before_block") is None:
            continue
        els = _section_elements(ctx, d["start"], d["end"])
        target = ctx.blocks[d["before_block"]].el
        if not els or target in els:
            continue
        for el in els:
            target.addprevious(el)
        fixed += 1
    return fixed


def _fix_missing(ctx: Context, issues: list[Issue]) -> int:
    fixed = 0
    template = next((ctx.blocks[h.block] for h in ctx.outline.hits if h.kind != "chapter"), None)
    want = ctx.rules.heading(1)
    for i in issues:
        d = i.data
        title = d["title"].upper() if (want and want.all_caps) else d["title"]
        heading = OxmlElement("w:p")
        if template is not None and template.el.find(qn("w:pPr")) is not None:
            ppr = copy.deepcopy(template.el.find(qn("w:pPr")))
            for sp in ppr.findall(qn("w:sectPr")):
                ppr.remove(sp)
            heading.append(ppr)
        run = OxmlElement("w:r")
        tmpl_runs = text_runs(template.el) if template is not None else []
        if tmpl_runs and tmpl_runs[0].find(qn("w:rPr")) is not None:
            run.append(copy.deepcopy(tmpl_runs[0].find(qn("w:rPr"))))
        t = OxmlElement("w:t")
        t.text = title
        run.append(t)
        heading.append(run)
        Paragraph(heading, None).paragraph_format.page_break_before = True
        placeholder = OxmlElement("w:p")
        prun = OxmlElement("w:r")
        pt = OxmlElement("w:t")
        pt.text = f"[Formatly: write your {d['title'].lower()} here.]"
        prun.append(pt)
        placeholder.append(prun)
        if d.get("before_block") is not None:
            target = ctx.blocks[d["before_block"]].el
            target.addprevious(heading)
            target.addprevious(placeholder)
        elif d.get("after_end") is not None:
            end = d["after_end"]
            if end < len(ctx.blocks):
                ctx.blocks[end].el.addprevious(heading)
                ctx.blocks[end].el.addprevious(placeholder)
            else:
                body = ctx.model.document.element.body
                last = body.find(qn("w:sectPr"))
                last.addprevious(heading)
                last.addprevious(placeholder)
        else:
            continue
        fixed += 1
    return fixed


STRUCTURAL = ("structure.order", "structure.missing")


# --------------------------------------------------------------------------

def apply_fixes(ctx: Context) -> dict[str, int]:
    """Fix every fixable issue in ctx. Returns {rule: number of issues addressed}."""
    by_rule: dict[str, list[Issue]] = defaultdict(list)
    for i in ctx.log.issues:
        if i.fixable:
            by_rule[i.rule].append(i)

    def family(prefix: str) -> list[Issue]:
        return [i for r, lst in by_rule.items() if r.startswith(prefix) for i in lst]

    done: Counter = Counter()

    def record(issues: list[Issue]) -> None:
        for i in issues:
            done[i.rule] += 1

    # Moving or adding sections changes where everything is: do it alone, then
    # the caller re-reads the document before the formatting fixes.
    if any(by_rule.get(r) for r in STRUCTURAL):
        if by_rule.get("structure.order"):
            if _fix_order(ctx, by_rule["structure.order"]):
                record(by_rule["structure.order"])
        if by_rule.get("structure.missing"):
            if _fix_missing(ctx, by_rule["structure.missing"]):
                record(by_rule["structure.missing"])
        if done:
            return dict(done)

    # Order matters: text and style changes first, element moves next, section changes last.
    page = family("page.")
    if page:
        _fix_page(ctx, page)
        record(page)

    body = family("body.")
    if body:
        def body_want(idx: int):
            sec = ctx.outline.section_at(idx)
            return ctx.rules.body_text_for(sec.spec_id if sec else None)
        _fix_text(ctx, body, body_want)
        record(body)

    headings = by_rule.get("headings.format", [])
    if headings:
        _fix_text(ctx, headings, lambda idx: ctx.rules.heading(ctx.outline.headings[idx].level))
        record(headings)
    if by_rule.get("headings.new_page"):
        _fix_new_page(ctx, by_rule["headings.new_page"])
        record(by_rule["headings.new_page"])
    if by_rule.get("headings.chapter_label"):
        _fix_chapter_label(ctx, by_rule["headings.chapter_label"])
        record(by_rule["headings.chapter_label"])

    title_page = by_rule.get("structure.title_page_format", [])
    if title_page and ctx.rules.title_page.text:
        _fix_text(ctx, title_page, lambda _idx: ctx.rules.title_page.text)
        record(title_page)

    hygiene = family("hygiene.")
    if hygiene:
        _fix_hygiene(ctx, hygiene)
        record(hygiene)

    refs = family("references.")
    if refs:
        _fix_references(ctx, refs)
        record(refs)

    cap_format = by_rule.get("captions.format", [])
    if cap_format:
        _fix_text(ctx, cap_format, lambda _idx: ctx.rules.caption_text())
        record(cap_format)
    table_text = by_rule.get("captions.table_text", [])
    if table_text:
        want = ctx.rules.table_text()
        for i in table_text:
            for p_el in ctx.blocks[i.block].el.iter(qn("w:p")):
                cell = Block(index=-1, kind="p", el=p_el, section=0)
                apply_text_rules(ctx, cell, want, {i.data["aspect"]})
        record(table_text)

    caps = by_rule.get("captions.position", [])
    if caps:
        _fix_captions(ctx, caps)
        record(caps)

    numbering = family("numbering.")
    if numbering:
        _fix_numbering(ctx, numbering)
        record(numbering)

    return dict(done)
