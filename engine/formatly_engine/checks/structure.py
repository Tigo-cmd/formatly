"""Structure (sections present and in order), page numbering, table of contents."""

from __future__ import annotations

import re

from docx.oxml.ns import qn

from ..issues import Issue
from ..outline import NUMBER_WORDS, normalize, names_match
from .base import Context


def _expected(ctx: Context) -> list[tuple[str, str, bool]]:
    """(id, display name, required) in the expected order."""
    st = ctx.rules.structure
    out = [(s.id, s.title, s.required) for s in st.preliminaries]
    for ch in st.chapters:
        word = NUMBER_WORDS[ch.number].capitalize() if ch.number < len(NUMBER_WORDS) else str(ch.number)
        out.append((f"chapter_{ch.number}", f"Chapter {word} ({ch.title})", ch.required))
    out += [(s.id, s.title, s.required) for s in st.back_matter]
    return out


def _longest_increasing(seq: list[int]) -> set[int]:
    """Positions in `seq` forming a longest strictly increasing subsequence."""
    n = len(seq)
    if not n:
        return set()
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if seq[j] < seq[i] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    i = max(range(n), key=lambda k: best[k])
    keep = set()
    while i != -1:
        keep.add(i)
        i = prev[i]
    return keep


def check_structure(ctx: Context) -> None:
    st = ctx.rules.structure
    outline = ctx.outline
    expected = _expected(ctx)
    names = {sid: name for sid, name, _ in expected}
    order = {sid: i for i, (sid, _, _) in enumerate(expected)}
    found = {h.spec_id: h for h in outline.hits}

    if st.title_page_required:
        ctx.log.checked_rule("structure.title_page")
        has_title_page = any(not b.is_empty for b in ctx.blocks[:outline.title_page_end])
        if not has_title_page:
            ctx.log.add(Issue("structure.title_page", "error", "No title page found at the start of the document.",
                              "Add a title page before the first section.", 0 if ctx.blocks else None))

    # Missing sections, anchored where they should go.
    for i, (sid, name, required) in enumerate(expected):
        if not required:
            continue
        ctx.log.checked_rule("structure.missing")
        if sid in found:
            continue
        after = next((found[s] for s, _, _ in expected[i + 1:] if s in found), None)
        before = next((found[s] for s, _, _ in reversed(expected[:i]) if s in found), None)
        if after:
            where, anchor = f"It should come before {names[after.spec_id]}.", after.block
        elif before:
            where, anchor = f"It should come after {names[before.spec_id]}.", before.block
        else:
            where, anchor = "", (0 if ctx.blocks else None)
        is_chapter = sid.startswith("chapter_")
        ctx.log.add(Issue(
            "structure.missing", "error",
            f"{name} is missing{'' if is_chapter else ' (no heading found)'}. {where}".strip(),
            "Add it, or check its heading is spelled as expected and on its own line.",
            anchor, fixable=not is_chapter and (after or before) is not None,
            data={"section": sid, "title": name,
                  "before_block": after.block if after else None,
                  "after_end": before.end if (before and not after) else None}))

    # Order.
    if st.enforce_order and outline.hits:
        ctx.log.checked_rule("structure.order")
        seq = [order.get(h.spec_id, h.order) for h in outline.hits]
        keep = _longest_increasing(seq)
        kept = [outline.hits[i] for i in sorted(keep)]
        for i, h in enumerate(outline.hits):
            if i in keep:
                continue
            nxt = next((k for k in kept if order.get(k.spec_id, k.order) > seq[i]), None)
            where = f"It should come before {names.get(nxt.spec_id, nxt.heading)}." if nxt else "It should come later."
            ctx.log.add(Issue(
                "structure.order", "error",
                f"{names.get(h.spec_id, h.heading)} is out of order. {where}",
                "Move the whole section (heading and content) to its correct place.",
                h.block, fixable=nxt is not None,
                data={"section": h.spec_id, "start": h.block, "end": h.end,
                      "before_block": nxt.block if nxt else None}))

    for d in outline.duplicates:
        ctx.log.checked_rule("structure.duplicate", severity="warning")
        ctx.log.add(Issue("structure.duplicate", "warning",
                          f"{names.get(d.spec_id, d.heading)} appears more than once.",
                          "Remove or rename the duplicate heading.", d.block))

    # Chapter titles.
    specs = {f"chapter_{c.number}": c for c in st.chapters}
    for h in outline.chapters:
        spec = specs.get(h.spec_id)
        if not spec:
            continue
        ctx.log.checked_rule("structure.chapter_title", severity="error" if st.chapter_titles_strict else "suggestion")
        if not h.title:
            ctx.log.add(Issue("structure.chapter_title", "error",
                              f"{names[h.spec_id]} has no title after the chapter label.",
                              f"Add the title, e.g. “{spec.title.upper()}”.", h.block))
        elif not _title_ok(h.title, [spec.title, *spec.aliases]):
            sev = "error" if st.chapter_titles_strict else "suggestion"
            options = " / ".join([spec.title, *spec.aliases][:3])
            ctx.log.add(Issue("structure.chapter_title", sev,
                              f"Chapter title “{h.title[:60]}” differs from the expected title: {options}.",
                              "Use the title your guideline requires.",
                              h.title_block if h.title_block is not None else h.block))


def _title_ok(title: str, names: list[str]) -> bool:
    if names_match(title, names):
        return True
    t = normalize(title)
    return any(normalize(n) in t for n in names if normalize(n))


# --------------------------------------------------------------------------
# Page numbering
# --------------------------------------------------------------------------

_FMT = {None: "decimal", "decimal": "decimal", "lowerRoman": "lower_roman", "upperRoman": "upper_roman",
        "lowerLetter": "lower_letter", "upperLetter": "upper_letter"}
_FMT_WORDS = {"decimal": "1, 2, 3", "lower_roman": "i, ii, iii", "upper_roman": "I, II, III",
              "lower_letter": "a, b, c", "upper_letter": "A, B, C", "none": "no numbers"}


def section_number_format(sect_pr) -> tuple[str, int | None]:
    pg = sect_pr.find(qn("w:pgNumType"))
    if pg is None:
        return "decimal", None
    start = pg.get(qn("w:start"))
    return _FMT.get(pg.get(qn("w:fmt")), pg.get(qn("w:fmt")) or "decimal"), (int(start) if start else None)


def _has_page_field(el) -> bool:
    for node in el.iter(qn("w:instrText"), qn("w:fldSimple")):
        instr = node.text if node.tag == qn("w:instrText") else node.get(qn("w:instr"))
        words = (instr or "").strip().split()
        if words and words[0].upper() == "PAGE":
            return True
    return False


def page_number_location(sections, section_index: int):
    """(paragraph element holding the PAGE field, "top"/"bottom") or None."""
    for i in range(section_index, -1, -1):
        sec = sections[i]
        for part, where in ((sec.footer, "bottom"), (sec.header, "top")):
            if part.is_linked_to_previous:
                continue
            for p in part._element.iter(qn("w:p")):
                if _has_page_field(p):
                    return p, where
    # Sections linked all the way back with no definition: nothing.
    return None


def check_numbering(ctx: Context) -> None:
    rules = ctx.rules.page_numbering
    sections = ctx.model.sections
    chapters = ctx.outline.chapters
    first_chapter = min(chapters, key=lambda h: h.block) if chapters else None
    has_prelims = ctx.outline.title_page_end > 0 or any(h.kind == "preliminary" for h in ctx.outline.hits)

    # Page numbers present.
    ctx.log.checked_rule("numbering.present")
    locations = [page_number_location(sections, i) for i in range(len(sections))]
    if not any(locations):
        ctx.log.add(Issue("numbering.present", "error", "The document has no page numbers.",
                          "Insert > Page Number > Bottom of Page > Plain Number 2.", 0 if ctx.blocks else None,
                          fixable=True))

    if rules.position and any(locations):
        ctx.log.checked_rule("numbering.position", severity="warning")
        seen = set()
        for loc in locations:
            if loc is None or id(loc[0]) in seen:
                continue
            seen.add(id(loc[0]))
            p_el, where = loc
            align = ctx.model.fmt.paragraph(p_el).alignment
            align = {"justify": "left"}.get(align, align)
            have = f"{where}_{align}"
            if have != rules.position:
                ctx.log.add(Issue("numbering.position", "warning",
                                  f"Page numbers are at the {where} {align}. Required: "
                                  f"{rules.position.replace('_', ' ')}.",
                                  "Double-click the header/footer and move the page number.",
                                  0 if ctx.blocks else None,
                                  fixable=rules.position.startswith(where)))

    if first_chapter is None:
        return
    first_block = ctx.blocks[first_chapter.block]
    ch_section = first_block.section

    if has_prelims and (rules.preliminaries or rules.main):
        ctx.log.checked_rule("numbering.section_break")
        shares = any(not b.is_empty for b in ctx.blocks if b.section == ch_section and b.index < first_chapter.block)
        if shares:
            ctx.log.add(Issue(
                "numbering.section_break", "error",
                "Chapter One is in the same section as the preliminary pages, so its page numbering cannot "
                "restart at 1.",
                "Put the cursor before CHAPTER ONE and insert Layout > Breaks > Section Break (Next Page). "
                "Then unlink the footer from the previous section.",
                first_chapter.block, fixable=True))
            return  # the format checks below would only repeat this

    if rules.preliminaries and rules.preliminaries != "none":
        for i in range(0, ch_section):
            ctx.log.checked_rule("numbering.preliminaries")
            fmt, _ = section_number_format(sections[i]._sectPr)
            if fmt != rules.preliminaries:
                anchor = next((b.index for b in ctx.blocks if b.section == i), 0)
                ctx.log.add(Issue(
                    "numbering.preliminaries", "error",
                    f"Preliminary pages are numbered {_FMT_WORDS.get(fmt, fmt)}. Required: "
                    f"{_FMT_WORDS[rules.preliminaries]}.",
                    "Insert > Page Number > Format Page Numbers > Number format.", anchor, fixable=True))
                break

    if rules.main and rules.main != "none":
        ctx.log.checked_rule("numbering.main")
        fmt, start = section_number_format(sections[ch_section]._sectPr)
        problems = []
        if fmt != rules.main:
            problems.append(f"numbered {_FMT_WORDS.get(fmt, fmt)} (required: {_FMT_WORDS[rules.main]})")
        if has_prelims and rules.main_starts_at is not None and start != rules.main_starts_at:
            problems.append(f"does not restart at page {rules.main_starts_at}")
        if problems:
            ctx.log.add(Issue(
                "numbering.main", "error", f"From Chapter One the pages are {' and '.join(problems)}.",
                "Insert > Page Number > Format Page Numbers: choose the format and Start at "
                f"{rules.main_starts_at or 1}.",
                first_chapter.block, fixable=True))
        for i in range(ch_section + 1, len(sections)):
            fmt_i, start_i = section_number_format(sections[i]._sectPr)
            if fmt_i != rules.main or start_i is not None:
                anchor = next((b.index for b in ctx.blocks if b.section == i), first_chapter.block)
                ctx.log.add(Issue(
                    "numbering.main", "error",
                    "Page numbering changes format or restarts after Chapter One.",
                    "Format Page Numbers: choose 'Continue from previous section'.", anchor, fixable=True,
                    data={"section": i}))


# --------------------------------------------------------------------------
# Table of contents
# --------------------------------------------------------------------------

_TRAILING_PAGE = re.compile(r"[\t .…_]+(\d+|[ivxlc]+|[IVXLC]+)\s*$")


def check_toc(ctx: Context) -> None:
    rules = ctx.rules.toc
    outline = ctx.outline
    toc_hit = outline.hit("table_of_contents")
    if toc_hit is None and not outline.toc_field:
        return  # structure check reports the missing section
    if rules.automatic:
        ctx.log.checked_rule("toc.automatic", severity="warning")
        if not outline.toc_field:
            ctx.log.add(Issue(
                "toc.automatic", "warning",
                "The table of contents is typed by hand, so its page numbers will go out of date.",
                "Use Word's automatic table of contents: References > Table of Contents. It needs your "
                "headings to use Heading styles.", toc_hit.block if toc_hit else None))
            return
    if not rules.up_to_date or not outline.toc_field:
        return
    entries = []
    for b in ctx.blocks:
        if b.in_toc and not b.is_empty:
            if ctx.model.para_format(b).style_name.lower() in ("toc heading", "contents heading"):
                continue
            entries.append(normalize(_TRAILING_PAGE.sub("", b.text)))
    anchor = toc_hit.block if toc_hit else next(b.index for b in ctx.blocks if b.in_toc)
    ctx.log.checked_rule("toc.up_to_date", severity="warning")
    if not any(entries):
        ctx.log.add(Issue("toc.up_to_date", "warning", "The table of contents is empty.",
                          "Right-click the table of contents > Update Field > Update entire table.", anchor))
        return
    # Only headings after the table of contents: many guidelines leave the
    # pages before it out of the contents.
    toc_end = max(b.index for b in ctx.blocks if b.in_toc)
    if toc_hit:
        toc_end = max(toc_end, toc_hit.block)
    missing = []
    for idx, info in sorted(outline.headings.items()):
        sec = outline.section_at(idx)
        if info.level > 2 or idx <= toc_end or (sec and sec.spec_id == "table_of_contents"):
            continue
        n = normalize(info.text)
        if n and not any(n in e or (e and e in n) for e in entries):
            missing.append(info.text.strip())
    if missing:
        listed = "; ".join(f"“{m[:40]}”" for m in missing[:5])
        more = f" and {len(missing) - 5} more" if len(missing) > 5 else ""
        ctx.log.add(Issue(
            "toc.up_to_date", "warning",
            f"The table of contents is missing {len(missing)} heading{'s' if len(missing) > 1 else ''}: "
            f"{listed}{more}.",
            "Make sure each heading uses a Heading style, then right-click the table of contents > "
            "Update Field > Update entire table.", anchor, data={"missing": missing}))
