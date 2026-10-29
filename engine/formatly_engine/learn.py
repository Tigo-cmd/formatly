"""Learning a rulebook from a correctly formatted model document.

A lecturer, department or journal often has a model document more readily than
a written guideline. This measures how that document is formatted and writes
the result as a rulebook that `extends` a base (usually the Formatly default),
so anything the model document cannot show (which sections are optional, word
limits) comes from the base. Every learned value is explained in `notes`, with
how consistent the document was about it.
"""

from __future__ import annotations

import io
from collections import Counter
from dataclasses import dataclass, field

import docx

from .checks.base import Context
from .checks.captions import find_captions
from .checks.references import reference_entries
from .checks.structure import page_number_location, section_number_format
from .docmodel import DocumentModel, word_count
from .outline import build_outline
from .rulebook import load_rulebook, _load_raw
from .units import TWIPS_PER_CM, TWIPS_PER_INCH, emu_to_twips

PAPER = {"A4": (11906, 16838), "Letter": (12240, 15840), "Legal": (12240, 20160), "A5": (8391, 11906)}
MIN_SHARE = 0.6  # a value must cover this share of the document to become a rule
ALIGN_WORDS = {"justify": "justified", "left": "left-aligned", "center": "centred", "right": "right-aligned"}
NUMBER_WORDS = {"lower_roman": "i, ii, iii", "upper_roman": "I, II, III", "decimal": "1, 2, 3"}


@dataclass
class Learned:
    data: dict
    notes: list[str] = field(default_factory=list)  # what was learned, and how consistently
    unsure: list[str] = field(default_factory=list)  # what the document was inconsistent about


def _length(twips: int) -> str:
    """Round to a value people write: quarter inches or half centimetres."""
    inches = round(twips / TWIPS_PER_INCH * 4) / 4
    if abs(inches * TWIPS_PER_INCH - twips) <= 40:
        return f"{inches:g}in"
    return f"{round(twips / TWIPS_PER_CM * 2) / 2:g}cm"


def _dominant(counter: Counter):
    if not counter:
        return None, 0.0
    value, n = counter.most_common(1)[0]
    return value, n / sum(counter.values())


def _spacing_value(rule: str, value: float):
    if rule == "multiple":
        for nice in (1.0, 1.15, 1.5, 2.0):
            if abs(value - nice) <= 0.05:
                return nice
        return round(value, 2)
    return f"{'exactly' if rule == 'exact' else 'at least'} {value:g}pt"


def learn_rulebook(source: bytes, base: str = "default", name: str = "Learned from a model document") -> Learned:
    rules = load_rulebook(base)
    d = docx.Document(io.BytesIO(source))
    model = DocumentModel.load(d)
    ctx = Context(model=model, rules=rules, outline=build_outline(model, rules))
    ctx.captions = find_captions(ctx)
    out = Learned(data={"name": name, "extends": base})
    data = out.data

    def decide(label: str, counter: Counter, setter, fmt=str) -> None:
        value, share = _dominant(counter)
        if value is None:
            return
        if share >= MIN_SHARE:
            setter(value)
            out.notes.append(f"{label}: {fmt(value)} ({share:.0%} of the document).")
        else:
            options = ", ".join(f"{fmt(v)} ({n / sum(counter.values()):.0%})" for v, n in counter.most_common(3))
            out.unsure.append(f"{label} varies: {options}. Kept the base rule.")

    # Page.
    sec = model.sections[0]
    w, h = emu_to_twips(sec.page_width), emu_to_twips(sec.page_height)
    short, long_ = sorted((w, h))
    paper = next((n for n, (pw, ph) in PAPER.items() if abs(short - pw) <= 60 and abs(long_ - ph) <= 60), None)
    if paper:
        data.setdefault("page", {})["size"] = paper
        out.notes.append(f"Paper: {paper}.")
    data.setdefault("page", {})["margins"] = {
        side: _length(emu_to_twips(getattr(sec, f"{side}_margin"))) for side in ("top", "bottom", "left", "right")}
    m = data["page"]["margins"]
    out.notes.append(f"Margins: top {m['top']}, bottom {m['bottom']}, left {m['left']}, right {m['right']}.")

    # Body text: measured on real paragraphs of the chapters, weighted by length.
    prose = [b for b in ctx.body_blocks if ctx.is_prose(b)]
    fonts, sizes, spacing, align, indent = Counter(), Counter(), Counter(), Counter(), Counter()
    for b in prose:
        weight = word_count(b.text)
        for r, rf in model.run_formats(b):
            n = len("".join(t.text or "" for t in r.iter("{*}t")))
            fonts[rf.font] += n
            sizes[rf.size] += n
        pf = model.para_format(b)
        spacing[_spacing_value(pf.line_rule, pf.line_value)] += weight
        align[pf.alignment] += weight
        indent[_length(max(pf.first_line, 0)) if pf.first_line > 36 else "0in"] += weight
    body = data.setdefault("body", {})
    decide("Body font", fonts, lambda v: body.__setitem__("font", v))
    decide("Body font size", sizes, lambda v: body.__setitem__("size", v), lambda v: f"{v:g} pt")
    decide("Body line spacing", spacing, lambda v: body.__setitem__("line_spacing", v),
           lambda v: {1.0: "single", 1.5: "1.5", 2.0: "double"}.get(v, str(v)))
    decide("Body alignment", align, lambda v: body.__setitem__("alignment", v), lambda v: ALIGN_WORDS.get(v, v))
    decide("First-line indent", indent, lambda v: body.__setitem__("first_line_indent", v))

    # Headings, per level.
    by_level: dict[int, list] = {}
    for idx, info in ctx.outline.headings.items():
        by_level.setdefault(info.level, []).append(ctx.blocks[idx])
    headings = []
    for level in sorted(by_level)[:3]:
        blocks = by_level[level]
        h: dict = {"level": level}
        bold, caps, al, size, font = Counter(), Counter(), Counter(), Counter(), Counter()
        for b in blocks:
            runs = model.run_formats(b)
            if not runs:
                continue
            bold[all(rf.bold for _, rf in runs)] += 1
            letters = [c for c in b.text if c.isalpha()]
            caps[bool(letters) and (all(rf.caps for _, rf in runs) or not any(c.islower() for c in letters))] += 1
            al[model.para_format(b).alignment] += 1
            size[runs[0][1].size] += 1
            font[runs[0][1].font] += 1
        decide(f"Level {level} headings font", font, lambda v: h.__setitem__("font", v))
        decide(f"Level {level} headings size", size, lambda v: h.__setitem__("size", v), lambda v: f"{v:g} pt")
        decide(f"Level {level} headings bold", bold, lambda v: h.__setitem__("bold", v), lambda v: "yes" if v else "no")
        value, share = _dominant(caps)
        if value and share >= MIN_SHARE:
            h["all_caps"] = True
            out.notes.append(f"Level {level} headings: capital letters ({share:.0%}).")
        value, share = _dominant(al)
        if value and share >= MIN_SHARE:
            # Left and justified look the same on a one-line heading: accept both.
            h["alignment"] = ["left", "justify"] if value in ("left", "justify") else value
            out.notes.append(f"Level {level} headings: {ALIGN_WORDS.get(value, value)} ({share:.0%}).")
        if level == 1:
            h["new_page"] = True
        headings.append(h)
    if headings:
        data["headings"] = headings

    # Structure: the sections this document has, in its order.
    st = rules.structure
    found = [hit.spec_id for hit in ctx.outline.hits]
    if found:
        base_raw = _load_raw(base).get("structure", {})
        pre = []
        for spec in base_raw.get("preliminaries", []):
            pre.append({**spec, "required": spec["id"] in found})
        order = {sid: i for i, sid in enumerate(found)}
        pre.sort(key=lambda s: order.get(s["id"], len(order) + 1))
        data.setdefault("structure", {})["preliminaries"] = pre
        present = [s["title"] for s in pre if s["required"]]
        out.notes.append("Preliminary pages, in order: " + ", ".join(present) + ".")
        n_chapters = len(ctx.outline.chapters)
        if n_chapters:
            out.notes.append(f"{n_chapters} chapters.")
            if st.chapters and n_chapters < len(st.chapters):
                out.unsure.append(f"The model document has {n_chapters} chapters; the base expects "
                                  f"{len(st.chapters)}. Kept the base chapter list.")
            labels = Counter(h.number_style for h in ctx.outline.chapters)
            decide("Chapter labels", labels, lambda v: data["structure"].__setitem__("chapter_label", v),
                   lambda v: {"words": "CHAPTER ONE", "digits": "CHAPTER 1", "roman": "CHAPTER I"}.get(v, v))

    # Page numbering.
    first = min(ctx.outline.chapters, key=lambda x: x.block) if ctx.outline.chapters else None
    if first is not None:
        ch_sec = ctx.blocks[first.block].section
        pn = data.setdefault("page_numbering", {})
        if ch_sec > 0:
            fmt, _ = section_number_format(model.sections[0]._sectPr)
            pn["preliminaries"] = fmt
            out.notes.append(f"Preliminary pages numbered {NUMBER_WORDS.get(fmt, fmt)}.")
        fmt, _ = section_number_format(model.sections[ch_sec]._sectPr)
        pn["main"] = fmt
        loc = page_number_location(model.sections, ch_sec)
        if loc:
            al = model.fmt.paragraph(loc[0]).alignment
            pn["position"] = f"{loc[1]}_{'center' if al == 'center' else ('right' if al == 'right' else 'left')}"
            out.notes.append(f"Page numbers at the {pn['position'].replace('_', ' ')}.")

    # Captions.
    pos = {"table": Counter(), "figure": Counter()}
    for cap in ctx.captions.values():
        if cap.position:
            pos[cap.kind][cap.position] += 1
    caps = data.setdefault("captions", {})
    decide("Table captions", pos["table"], lambda v: caps.__setitem__("table_position", v))
    decide("Figure captions", pos["figure"], lambda v: caps.__setitem__("figure_position", v))

    # References.
    entries = reference_entries(ctx)
    if entries:
        hang = Counter()
        ref_spacing = Counter()
        for e in entries:
            pf = model.para_format(e.first)
            hang[_length(-pf.first_line) if pf.first_line < -36 else "none"] += 1
            ref_spacing[_spacing_value(pf.line_rule, pf.line_value)] += 1
        refs = data.setdefault("references", {})
        value, share = _dominant(hang)
        if value == "none":
            # Usually lines pushed in with Tab instead of a real hanging indent: not a rule to copy.
            out.unsure.append("References in the model document have no hanging indent (often lines pushed "
                              "in with Tab). Kept the base rule.")
        else:
            decide("Reference hanging indent", hang, lambda v: refs.__setitem__("hanging_indent", v))
        decide("Reference line spacing", ref_spacing,
               lambda v: refs.__setitem__("text", {"line_spacing": v}))

    return out
