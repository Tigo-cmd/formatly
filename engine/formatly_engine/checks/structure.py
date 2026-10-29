"""Structure (sections present and in order), page numbering, table of contents."""

from __future__ import annotations

import difflib
import re

from docx.oxml.ns import qn

from ..issues import Issue
from ..outline import NUMBER_WORDS, normalize, names_match
from .base import Context, text_problems


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
    has_tables, has_figures = _has_tables_figures(ctx)
    alternatives = {s.id: s.alternatives for s in (*st.preliminaries, *st.back_matter)}
    for i, (sid, name, required) in enumerate(expected):
        if required == "if_figures":
            required = has_figures
        elif required == "if_tables":
            required = has_tables
        elif required == "if_figures_or_tables":
            required = has_figures or has_tables
        if not required:
            continue
        ctx.log.checked_rule("structure.missing")
        if sid in found or any(a in found for a in alternatives.get(sid, ())):
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


def _has_tables_figures(ctx: Context) -> tuple[bool, bool]:
    in_chapters = [b for b in ctx.blocks if ctx.outline.chapter_at(b.index) is not None]
    return (any(b.kind == "tbl" for b in in_chapters),
            any(b.kind == "p" and b.has_image for b in in_chapters))


def section_paragraphs(ctx: Context, hit) -> list:
    return [b for b in ctx.blocks[hit.block + 1:hit.end]
            if b.kind == "p" and not b.is_empty and b.index not in ctx.outline.headings]


def check_section_content(ctx: Context) -> None:
    """Required wording and paragraph limits inside named sections."""
    for h in ctx.outline.hits:
        spec = ctx.rules.section_spec(h.spec_id)
        if spec is None:
            continue
        paras = section_paragraphs(ctx, h)
        text = " ".join(b.text for b in paras)
        low = re.sub(r"\s+", " ", text.lower())
        for phrase in spec.must_include:
            ctx.log.checked_rule("structure.content")
            if phrase.lower() not in low:
                ctx.log.add(Issue("structure.content", "error",
                                  f"{spec.title} must include “{phrase}”.",
                                  f"Add “{phrase}” where your guideline requires it.", h.block,
                                  data={"section": h.spec_id, "missing": phrase}))
        for phrase in spec.must_not_include:
            ctx.log.checked_rule("structure.content")
            if phrase.lower() in low:
                where = next((b.index for b in paras if phrase.lower() in b.text.lower()), h.block)
                ctx.log.add(Issue("structure.content", "error",
                                  f"{spec.title} should not say “{phrase}”.",
                                  "Replace it with the wording your guideline requires.", where,
                                  data={"section": h.spec_id, "forbidden": phrase}))
        if spec.max_paragraphs:
            ctx.log.checked_rule("structure.content")
            n = sum(1 for b in paras if b.text.strip())
            if n > spec.max_paragraphs:
                ctx.log.add(Issue("structure.content", "error",
                                  f"{spec.title} has {n} paragraphs. It should be "
                                  f"{'one paragraph' if spec.max_paragraphs == 1 else f'at most {spec.max_paragraphs}'}.",
                                  "Merge the paragraphs.", h.block, data={"section": h.spec_id}))


def heading_title(text: str) -> str:
    """'1.2 STATEMENT OF THE PROBLEM' -> 'STATEMENT OF THE PROBLEM'."""
    return re.sub(r"^\s*\d+(\.\d+)*\.?\s*", "", text).strip()


def check_subsections(ctx: Context) -> None:
    """Headings each chapter must have, e.g. 1.2 Statement of the Problem."""
    specs = {f"chapter_{c.number}": c for c in ctx.rules.structure.chapters}
    for h in ctx.outline.chapters:
        spec = specs.get(h.spec_id)
        if not spec or not spec.sections:
            continue
        heads = [info for idx, info in sorted(ctx.outline.headings.items())
                 if h.block < idx < h.end and info.level >= 2]
        found_at: list[int] = []
        for sub in spec.sections:
            ctx.log.checked_rule("structure.subsections")
            names = [sub.title, *sub.aliases]
            match = next((x for x in heads if x.level == 2 and _title_ok(heading_title(x.text), names)), None)
            match = match or next((x for x in heads if _title_ok(heading_title(x.text), names)), None)
            if match is None:
                if sub.required:
                    prev = found_at[-1] if found_at else (h.title_block or h.block)
                    ctx.log.add(Issue("structure.subsections", "error",
                                      f"Chapter {h.number} needs the section “{sub.number} {sub.title}”.",
                                      "Add this section with its heading.", prev,
                                      data={"chapter": h.number, "section": sub.number}))
                continue
            if match.numbering and match.numbering != sub.number:
                ctx.log.add(Issue("structure.subsections", "warning",
                                  f"“{match.text[:60]}” should be numbered {sub.number}.",
                                  f"Renumber it {sub.number}.", match.block,
                                  data={"chapter": h.number, "section": sub.number}))
            if found_at and match.block < found_at[-1]:
                ctx.log.add(Issue("structure.subsections", "warning",
                                  f"“{match.text[:60]}” is out of order; it should come after the "
                                  f"previous required section.",
                                  "Move the section to its correct place.", match.block))
            found_at.append(match.block)


def check_title_page(ctx: Context) -> None:
    rules = ctx.rules.title_page
    blocks = [b for b in ctx.blocks[:ctx.outline.title_page_end] if b.kind == "p" and not b.is_empty]
    if not blocks:
        return
    if rules.text:
        ctx.log.checked_rule("structure.title_page_format")
        for b in blocks:
            for suffix, msg, hint in text_problems(ctx, b, rules.text, check_first_line=False):
                ctx.log.add(Issue("structure.title_page_format", "error", f"Title page: {msg}", hint,
                                  b.index, fixable=True, data={"aspect": suffix}))
    text = "\n".join(b.text for b in blocks)
    for req in rules.must_include:
        ctx.log.checked_rule("structure.title_page_content")
        if not re.search(req.pattern, text, re.I):
            ctx.log.add(Issue("structure.title_page_content", "error",
                              f"The title page should include {req.label}.",
                              "Add it to the title page.", blocks[0].index, data={"label": req.label}))


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


TOC_NUMBERED_RE = re.compile(r"^\s*(\d+(?:\.\d+)+)\.?\s+(.*)$")


def clean_listing(text: str) -> str:
    """A contents line without its dot leaders and page number."""
    t = _TRAILING_PAGE.sub("", text)
    t = re.sub(r"(\.{2,}|…+|_{2,})", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def same_title(a: str, b: str) -> bool:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    return difflib.SequenceMatcher(None, na, nb).ratio() >= 0.85


def _toc_entries(ctx: Context, toc_hit) -> list:
    """Lines of the table of contents: from Word's field, or typed by hand."""
    def keep(b) -> bool:
        return (b.kind == "p" and not b.is_empty
                and ctx.model.para_format(b).style_name.lower() not in ("toc heading", "contents heading"))
    if ctx.outline.toc_field:
        lines = [b for b in ctx.blocks if b.in_toc and keep(b)]
        if toc_hit is not None:  # Word's lists of figures are fields too; keep this section only
            lines = [b for b in lines if b.index < toc_hit.end]
        return lines
    if toc_hit is None:
        return []
    return [b for b in ctx.blocks[toc_hit.block + 1:toc_hit.end]
            if keep(b) and b.index in ctx.outline.listing_blocks]


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
    if not rules.up_to_date:
        return
    entries = _toc_entries(ctx, toc_hit)
    anchor = toc_hit.block if toc_hit else (entries[0].index if entries else None)
    ctx.log.checked_rule("toc.up_to_date", severity="warning")
    if not entries:
        ctx.log.add(Issue("toc.up_to_date", "warning", "The table of contents is empty.",
                          "Right-click the table of contents > Update Field > Update entire table.", anchor))
        return

    cleaned = [(b, clean_listing(b.text)) for b in entries]
    unnumbered = [(b, t) for b, t in cleaned if not TOC_NUMBERED_RE.match(t)]
    numbered: dict[str, tuple] = {}
    for b, t in cleaned:
        m = TOC_NUMBERED_RE.match(t)
        if m:
            numbered.setdefault(m.group(1), (b, m.group(2)))
    depth = max((n.count(".") + 1 for n in numbered), default=2)
    norm_entries = [normalize(t) for _, t in cleaned]
    # Only headings after the table of contents: many guidelines leave the
    # pages before it out of the contents.
    toc_end = max([b.index for b in entries] + ([toc_hit.block] if toc_hit else []))
    hint = ("Correct the table of contents so it matches the headings in your work. If it is automatic: "
            "right-click it > Update Field > Update entire table.")

    body_numbers: set[str] = set()
    for idx, info in sorted(outline.headings.items()):
        if idx <= toc_end or idx < outline.title_page_end:
            continue
        sec = outline.section_at(idx)
        if sec and sec.spec_id.startswith(("table_of_contents", "list_of")):
            continue
        if info.numbering:
            body_numbers.add(info.numbering)
            if info.level > depth:
                continue
            entry = numbered.get(info.numbering)
            if entry is None:
                by_title = next((b for b, t in unnumbered if same_title(heading_title(info.text), t)), None)
                if by_title is not None:
                    ctx.log.add(Issue("toc.up_to_date", "warning",
                                      f"The table of contents lists “{clean_listing(by_title.text)[:50]}” without "
                                      f"its number. Write it as “{info.numbering} …”, as in the work.",
                                      hint, by_title.index, data={"number": info.numbering}))
                else:
                    ctx.log.add(Issue("toc.up_to_date", "warning",
                                      f"“{info.text[:60]}” is not in the table of contents.", hint, idx,
                                      data={"number": info.numbering}))
            elif not same_title(heading_title(info.text), entry[1]):
                ctx.log.add(Issue("toc.up_to_date", "warning",
                                  f"The table of contents says “{info.numbering} {entry[1][:50]}”, but heading "
                                  f"{info.numbering} in the work is “{heading_title(info.text)[:50]}”.",
                                  hint, entry[0].index, data={"number": info.numbering}))
        elif info.level <= 2:
            n = normalize(info.text)
            if n and not any(n in e or (e and e in n) for e in norm_entries):
                close = _closest_entry(n, cleaned)
                if close is not None:
                    ctx.log.add(Issue("toc.up_to_date", "warning",
                                      f"The table of contents says “{clean_listing(close.text)[:60]}”, but the "
                                      f"heading in the work is “{info.text.strip()[:60]}”.", hint, close.index))
                else:
                    ctx.log.add(Issue("toc.up_to_date", "warning",
                                      f"“{info.text[:60]}” is not in the table of contents.", hint, idx))
    for number, (b, title) in numbered.items():
        if number not in body_numbers:
            ctx.log.add(Issue("toc.up_to_date", "warning",
                              f"The table of contents lists “{number} {title[:50]}”, but there is no heading "
                              f"{number} in the work.", hint, b.index, data={"number": number}))


_CHAPTER_PREFIX = re.compile(r"^chapter [a-z0-9]+ ?")


def _closest_entry(heading_norm: str, cleaned: list):
    """A contents line that is nearly this heading (a typo or a changed word)."""
    best, best_ratio = None, 0.0
    for b, t in cleaned:
        e = normalize(t)
        for candidate in {e, _CHAPTER_PREFIX.sub("", e)}:
            if not candidate:
                continue
            ratio = difflib.SequenceMatcher(None, heading_norm, candidate).ratio()
            if ratio > best_ratio:
                best, best_ratio = b, ratio
    return best if best_ratio >= 0.8 else None


def check_lists(ctx: Context) -> None:
    """Lists of figures and tables must match the captions in the work."""
    if not ctx.rules.toc.lists_match_captions:
        return
    from .base import CAPTION_RE  # local: avoids a cycle at import time
    for h in ctx.outline.hits:
        if not h.spec_id.startswith("list_of"):
            continue
        kinds = {k for k in ("figure", "table") if k in h.spec_id}
        if not kinds:
            continue
        name = ctx.rules.section_spec(h.spec_id).title if ctx.rules.section_spec(h.spec_id) else h.heading
        listed: dict[tuple[str, str], tuple] = {}
        for b in ctx.blocks[h.block + 1:h.end]:
            if b.kind != "p" or b.is_empty:
                continue
            m = CAPTION_RE.match(clean_listing(b.text))
            if m:
                kind = "table" if m.group(1).lower() == "table" else "figure"
                number = re.sub(r"\s+", "", m.group(2)).replace("-", ".").replace("–", ".").rstrip(".")
                listed.setdefault((kind, number), (b, m.group(3).strip()))
        ctx.log.checked_rule("toc.lists", severity="warning")
        hint = f"Make the {name} match the captions in your work (number and title)."
        in_body: dict[tuple[str, str], object] = {}
        for cap in sorted(ctx.captions.values(), key=lambda c: c.block):
            if cap.kind not in kinds:
                continue
            key = (cap.kind, cap.number.rstrip("."))
            in_body.setdefault(key, cap)
            label = f"{cap.kind.capitalize()} {cap.number}"
            if key not in listed:
                ctx.log.add(Issue("toc.lists", "warning", f"{label} is not in the {name}.", hint, cap.block))
                continue
            m = CAPTION_RE.match(ctx.blocks[cap.block].text.strip())
            body_title = m.group(3).strip() if m else ""
            entry_block, entry_title = listed[key]
            if body_title and entry_title and not same_title(body_title, entry_title):
                ctx.log.add(Issue("toc.lists", "warning",
                                  f"The {name} says “{label} {entry_title[:50]}”, but the caption in the work is "
                                  f"“{label} {body_title[:50]}”.", hint, entry_block.index))
        for (kind, number), (b, title) in listed.items():
            if (kind, number) not in in_body:
                ctx.log.add(Issue("toc.lists", "warning",
                                  f"The {name} lists “{kind.capitalize()} {number}”, but there is no "
                                  f"{kind} {number} in the work.", hint, b.index))
