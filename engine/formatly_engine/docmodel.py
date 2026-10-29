"""Reading a .docx: blocks in reading order and their effective formatting.

Word decides how a piece of text looks by layering, lowest first:

1. document defaults (docDefaults), with theme fonts resolved;
2. the paragraph style and everything it is based on;
3. the run's character style and everything it is based on;
4. formatting applied directly to the paragraph or run.

python-docx only exposes each layer separately, so this module merges them.
Getting this right is what keeps Formatly from reporting false errors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator

from docx.document import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml.ns import qn
from docx.section import Section
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

DEFAULT_FONT = "Times New Roman"  # what Word uses when nothing sets a font
DEFAULT_HALF_POINTS = 20  # 10 pt


def _on(el) -> bool:
    """Toggle elements such as <w:b/>: present means on unless val is false."""
    if el is None:
        return False
    val = el.get(qn("w:val"))
    return val not in ("0", "false", "off", "none")


def _int(v: str | None) -> int | None:
    if v is None:
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Property extraction from a single layer
# --------------------------------------------------------------------------

def ppr_props(ppr) -> dict:
    """Paragraph properties set in one <w:pPr>."""
    out: dict = {}
    if ppr is None:
        return out
    jc = ppr.find(qn("w:jc"))
    if jc is not None:
        out["jc"] = jc.get(qn("w:val"))
    sp = ppr.find(qn("w:spacing"))
    if sp is not None:
        for attr, key in (("line", "line"), ("lineRule", "line_rule"), ("before", "before"),
                          ("after", "after"), ("beforeAutospacing", "before_auto"),
                          ("afterAutospacing", "after_auto")):
            v = sp.get(qn(f"w:{attr}"))
            if v is not None:
                out[key] = v
    ind = ppr.find(qn("w:ind"))
    if ind is not None:
        left = ind.get(qn("w:left")) or ind.get(qn("w:start"))
        right = ind.get(qn("w:right")) or ind.get(qn("w:end"))
        if left is not None:
            out["ind_left"] = _int(left)
        if right is not None:
            out["ind_right"] = _int(right)
        first, hanging = ind.get(qn("w:firstLine")), ind.get(qn("w:hanging"))
        if hanging is not None:
            out["first_line"] = -(_int(hanging) or 0)
        elif first is not None:
            out["first_line"] = _int(first)
    pbb = ppr.find(qn("w:pageBreakBefore"))
    if pbb is not None:
        out["page_break_before"] = _on(pbb)
    ol = ppr.find(qn("w:outlineLvl"))
    if ol is not None:
        out["outline_level"] = _int(ol.get(qn("w:val")))
    if ppr.find(qn("w:numPr")) is not None:
        num_id = ppr.find(qn("w:numPr")).find(qn("w:numId"))
        out["numbered"] = num_id is None or num_id.get(qn("w:val")) != "0"
    return out


_RFONT_ATTRS = ("ascii", "hAnsi", "asciiTheme", "hAnsiTheme")


def rpr_props(rpr) -> dict:
    """Run properties set in one <w:rPr>."""
    out: dict = {}
    if rpr is None:
        return out
    rf = rpr.find(qn("w:rFonts"))
    if rf is not None:
        # A theme attribute beats the plain one in the same element.
        theme = rf.get(qn("w:asciiTheme")) or rf.get(qn("w:hAnsiTheme"))
        plain = rf.get(qn("w:ascii")) or rf.get(qn("w:hAnsi"))
        if theme:
            out["font_theme"] = theme
            out["font"] = None
        elif plain:
            out["font"] = plain
            out["font_theme"] = None
    sz = rpr.find(qn("w:sz"))
    if sz is not None and _int(sz.get(qn("w:val"))):
        out["half_points"] = _int(sz.get(qn("w:val")))
    for tag, key in (("b", "bold"), ("i", "italic"), ("caps", "caps"), ("smallCaps", "small_caps"),
                     ("vanish", "hidden")):
        el = rpr.find(qn(f"w:{tag}"))
        if el is not None:
            out[key] = _on(el)
    color = rpr.find(qn("w:color"))
    if color is not None:
        out["color"] = color.get(qn("w:val"))
    hl = rpr.find(qn("w:highlight"))
    if hl is not None:
        out["highlight"] = hl.get(qn("w:val"))
    shd = rpr.find(qn("w:shd"))
    if shd is not None:
        fill = shd.get(qn("w:fill"))
        if fill and fill.lower() not in ("auto", "ffffff"):
            out["shading"] = fill
    rs = rpr.find(qn("w:rStyle"))
    if rs is not None:
        out["rstyle"] = rs.get(qn("w:val"))
    return out


# --------------------------------------------------------------------------
# Effective formatting
# --------------------------------------------------------------------------

@dataclass
class ParaFormat:
    alignment: str  # left / center / right / justify
    line_rule: str  # multiple / exact / at_least
    line_value: float  # multiple, or points
    before: int  # twips
    after: int
    ind_left: int
    first_line: int  # negative = hanging
    page_break_before: bool
    outline_level: int | None
    numbered: bool
    style_id: str | None
    style_name: str

    @property
    def is_justified(self) -> bool:
        return self.alignment == "justify"


@dataclass
class RunFormat:
    font: str
    size: float  # points
    bold: bool
    italic: bool
    caps: bool
    color: str | None
    highlight: str | None
    hidden: bool
    style_id: str | None


_JC = {"both": "justify", "distribute": "justify", "left": "left", "start": "left",
       "center": "center", "right": "right", "end": "right"}


class FormatResolver:
    def __init__(self, document: Document):
        self.document = document
        styles_el = document.styles.element
        self.styles: dict[str, etree._Element] = {}
        self.default_para_style: str | None = None
        self.style_names: dict[str, str] = {}
        for s in styles_el.findall(qn("w:style")):
            sid = s.get(qn("w:styleId"))
            if not sid:
                continue
            self.styles[sid] = s
            name_el = s.find(qn("w:name"))
            self.style_names[sid] = name_el.get(qn("w:val")) if name_el is not None else sid
            if s.get(qn("w:type")) == "paragraph" and _on_attr(s.get(qn("w:default"))):
                self.default_para_style = sid
        dd = styles_el.find(qn("w:docDefaults"))
        self.default_rpr = dd.find(qn("w:rPrDefault") + "/" + qn("w:rPr")) if dd is not None else None
        self.default_ppr = dd.find(qn("w:pPrDefault") + "/" + qn("w:pPr")) if dd is not None else None
        self.theme_fonts = _theme_fonts(document)
        self._ppr_cache: dict[str | None, dict] = {}
        self._rpr_cache: dict[tuple[str | None, str | None], dict] = {}

    def style_name(self, style_id: str | None) -> str:
        if style_id is None:
            return self.style_names.get(self.default_para_style or "", "Normal")
        return self.style_names.get(style_id, style_id)

    def chain(self, style_id: str | None) -> list[etree._Element]:
        """Styles from the root of the based-on chain down to `style_id`."""
        out: list[etree._Element] = []
        seen: set[str] = set()
        while style_id and style_id in self.styles and style_id not in seen:
            seen.add(style_id)
            s = self.styles[style_id]
            out.append(s)
            based = s.find(qn("w:basedOn"))
            style_id = based.get(qn("w:val")) if based is not None else None
        return list(reversed(out))

    @staticmethod
    def para_style_id(p_el) -> str | None:
        ppr = p_el.find(qn("w:pPr"))
        if ppr is None:
            return None
        ps = ppr.find(qn("w:pStyle"))
        return ps.get(qn("w:val")) if ps is not None else None

    def _style_ppr(self, style_id: str | None) -> dict:
        if style_id not in self._ppr_cache:
            props = ppr_props(self.default_ppr)
            for s in self.chain(style_id):
                props.update(ppr_props(s.find(qn("w:pPr"))))
            self._ppr_cache[style_id] = props
        return self._ppr_cache[style_id]

    def _style_rpr(self, para_style: str | None, run_style: str | None) -> dict:
        key = (para_style, run_style)
        if key not in self._rpr_cache:
            props = rpr_props(self.default_rpr)
            for s in self.chain(para_style):
                props.update(rpr_props(s.find(qn("w:rPr"))))
            for s in self.chain(run_style):
                props.update(rpr_props(s.find(qn("w:rPr"))))
            props.pop("rstyle", None)
            self._rpr_cache[key] = props
        return self._rpr_cache[key]

    def _effective_para_style(self, p_el) -> str | None:
        sid = self.para_style_id(p_el)
        if sid is None or sid not in self.styles:
            return self.default_para_style
        return sid

    def paragraph(self, p_el) -> ParaFormat:
        sid = self._effective_para_style(p_el)
        props = dict(self._style_ppr(sid))
        props.update(ppr_props(p_el.find(qn("w:pPr"))))
        line = _int(props.get("line"))
        rule = props.get("line_rule") or "auto"
        if line is None:
            line_rule, line_value = "multiple", 1.0
        elif rule == "auto":
            line_rule, line_value = "multiple", round(line / 240, 2)
        else:
            line_rule = "exact" if rule == "exact" else "at_least"
            line_value = line / 20
        return ParaFormat(
            alignment=_JC.get(props.get("jc") or "left", "left"),
            line_rule=line_rule,
            line_value=line_value,
            before=0 if _on_attr(props.get("before_auto")) else (_int(props.get("before")) or 0),
            after=0 if _on_attr(props.get("after_auto")) else (_int(props.get("after")) or 0),
            ind_left=props.get("ind_left") or 0,
            first_line=props.get("first_line") or 0,
            page_break_before=bool(props.get("page_break_before")),
            outline_level=props.get("outline_level"),
            numbered=bool(props.get("numbered")),
            style_id=sid,
            style_name=self.style_name(sid),
        )

    def run(self, p_el, r_el) -> RunFormat:
        direct = rpr_props(r_el.find(qn("w:rPr")))
        props = dict(self._style_rpr(self._effective_para_style(p_el), direct.get("rstyle")))
        props.update({k: v for k, v in direct.items() if k != "rstyle"})
        font = props.get("font")
        if props.get("font_theme"):
            font = self.theme_fonts.get(props["font_theme"]) or font
        return RunFormat(
            font=font or DEFAULT_FONT,
            size=(props.get("half_points") or DEFAULT_HALF_POINTS) / 2,
            bold=bool(props.get("bold")),
            italic=bool(props.get("italic")),
            caps=bool(props.get("caps")),
            color=props.get("color"),
            highlight=props.get("highlight") or props.get("shading"),
            hidden=bool(props.get("hidden")),
            style_id=direct.get("rstyle"),
        )


def _on_attr(v: str | None) -> bool:
    return v is not None and v not in ("0", "false", "off")


def _theme_fonts(document: Document) -> dict[str, str]:
    """Map theme font references (minorHAnsi, majorAscii, ...) to font names."""
    out: dict[str, str] = {}
    try:
        part = document.part.part_related_by(RT.THEME)
    except KeyError:
        return out
    root = etree.fromstring(part.blob)
    for kind in ("major", "minor"):
        latin = root.find(f".//{{{A_NS}}}{kind}Font/{{{A_NS}}}latin")
        if latin is not None and latin.get("typeface"):
            name = latin.get("typeface")
            for suffix in ("Ascii", "HAnsi", "Bidi", "EastAsia"):
                out[f"{kind}{suffix}"] = name
    return out


# --------------------------------------------------------------------------
# Blocks in reading order
# --------------------------------------------------------------------------

@dataclass
class Block:
    index: int
    kind: str  # "p" or "tbl"
    el: etree._Element
    section: int  # index into DocumentModel.sections
    in_toc: bool = False
    text: str = ""
    has_image: bool = False
    ends_section: bool = False
    page_break_after: bool = False  # ends with a manual page break
    starts_with_page_break: bool = False

    @property
    def is_paragraph(self) -> bool:
        return self.kind == "p"

    @property
    def is_empty(self) -> bool:
        return self.kind == "p" and not self.text.strip() and not self.has_image


_IMAGE_TAGS = (qn("w:drawing"), qn("w:pict"), qn("w:object"))


MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
# Content inside these is not part of the paragraph's own text: drawings and
# text boxes (a flowchart's labels), and paragraph / run property settings
# (whose <w:tab> elements are tab stops, not tab characters).
_SKIP = {qn("w:drawing"), qn("w:pict"), qn("w:object"), qn("w:txbxContent"), qn("w:pPr"), qn("w:rPr"),
         f"{{{MC_NS}}}AlternateContent", qn("w:del"), qn("w:moveFrom")}


def iter_flow(el, tags: tuple):
    """Elements with the given tags in reading order, skipping drawings, text
    boxes, property settings and deleted text."""
    for child in el:
        if child.tag in tags:
            yield child
        if len(child) and child.tag not in _SKIP:
            yield from iter_flow(child, tags)


def paragraph_text(p_el) -> str:
    """Visible text of a paragraph, including hyperlinks, excluding deleted text and drawings."""
    parts: list[str] = []
    for node in iter_flow(p_el, (qn("w:t"), qn("w:tab"), qn("w:br"))):
        if node.tag == qn("w:t"):
            parts.append(node.text or "")
        elif node.tag == qn("w:tab"):
            parts.append("\t")
        elif node.get(qn("w:type")) in (None, "textWrapping"):
            parts.append("\n")
    return "".join(parts)


def _has_image(p_el) -> bool:
    return any(True for _ in p_el.iter(*_IMAGE_TAGS))


def _page_break_positions(p_el) -> tuple[bool, bool]:
    """(starts with a page break, ends with a page break), ignoring empty text."""
    tokens: list[str] = []
    for node in iter_flow(p_el, (qn("w:t"), qn("w:br"), *_IMAGE_TAGS)):
        if node.tag == qn("w:br"):
            if node.get(qn("w:type")) == "page":
                tokens.append("B")
        elif node.tag != qn("w:t") or (node.text or "").strip():
            tokens.append("C")
    if "B" not in tokens:
        return False, False
    return tokens[0] == "B", tokens[-1] == "B"


class _FieldTracker:
    """Tracks complex fields across paragraphs to find TOC content."""

    def __init__(self) -> None:
        self.stack: list[str] = []

    def feed(self, p_el) -> bool:
        """Process a paragraph; True if any of it is inside a TOC field."""
        in_toc = self.inside_toc()
        for node in p_el.iter(qn("w:fldChar"), qn("w:instrText"), qn("w:fldSimple")):
            if node.tag == qn("w:fldChar"):
                kind = node.get(qn("w:fldCharType"))
                if kind == "begin":
                    self.stack.append("")
                elif kind == "end" and self.stack:
                    self.stack.pop()
            elif node.tag == qn("w:instrText") and self.stack:
                self.stack[-1] += node.text or ""
            elif node.tag == qn("w:fldSimple"):
                if _is_toc_instr(node.get(qn("w:instr")) or ""):
                    in_toc = True
            in_toc = in_toc or self.inside_toc()
        return in_toc

    def inside_toc(self) -> bool:
        return any(_is_toc_instr(s) for s in self.stack)


def _is_toc_instr(instr: str) -> bool:
    words = instr.strip().split()
    return bool(words) and words[0].upper() == "TOC"


def iter_body(document: Document) -> Iterator[tuple[etree._Element, bool]]:
    """Yield (w:p or w:tbl element, inside a TOC content control)."""

    def walk(parent, in_toc_sdt: bool):
        for child in parent:
            if child.tag in (qn("w:p"), qn("w:tbl")):
                yield child, in_toc_sdt
            elif child.tag == qn("w:sdt"):
                gallery = child.find(f"{qn('w:sdtPr')}/{qn('w:docPartObj')}/{qn('w:docPartGallery')}")
                is_toc = gallery is not None and "contents" in (gallery.get(qn("w:val")) or "").lower()
                content = child.find(qn("w:sdtContent"))
                if content is not None:
                    yield from walk(content, in_toc_sdt or is_toc)
            elif child.tag in (qn("w:customXml"), qn("w:smartTag")):
                yield from walk(child, in_toc_sdt)

    yield from walk(document.element.body, False)


def read_blocks(document: Document) -> list[Block]:
    blocks: list[Block] = []
    section = 0
    fields = _FieldTracker()
    for el, in_toc_sdt in iter_body(document):
        if el.tag == qn("w:p"):
            in_toc_field = fields.feed(el)
            starts_pb, ends_pb = _page_break_positions(el)
            ppr = el.find(qn("w:pPr"))
            ends_section = ppr is not None and ppr.find(qn("w:sectPr")) is not None
            b = Block(
                index=len(blocks), kind="p", el=el, section=section,
                in_toc=in_toc_sdt or in_toc_field,
                text=paragraph_text(el), has_image=_has_image(el),
                ends_section=ends_section,
                page_break_after=ends_pb, starts_with_page_break=starts_pb,
            )
            blocks.append(b)
            if ends_section:
                section += 1
        else:
            text = " ".join(paragraph_text(p) for p in el.iter(qn("w:p")))
            blocks.append(Block(index=len(blocks), kind="tbl", el=el, section=section,
                                in_toc=in_toc_sdt, text=text))
    return blocks


# --------------------------------------------------------------------------
# Convenience wrappers
# --------------------------------------------------------------------------

def as_paragraph(document: Document, block: Block) -> Paragraph:
    return Paragraph(block.el, document._body)


def as_table(document: Document, block: Block) -> Table:
    return Table(block.el, document._body)


def text_runs(p_el) -> list:
    """Runs that carry visible text (including those inside hyperlinks)."""
    out = []
    for r in iter_flow(p_el, (qn("w:r"),)):
        if any((t.text or "").strip() for t in r.findall(qn("w:t"))):
            out.append(r)
    return out


def in_hyperlink(r_el) -> bool:
    parent = r_el.getparent()
    while parent is not None and parent.tag != qn("w:p"):
        if parent.tag == qn("w:hyperlink"):
            return True
        parent = parent.getparent()
    return False


@dataclass
class DocumentModel:
    document: Document
    fmt: FormatResolver
    blocks: list[Block]
    _para_cache: dict[int, ParaFormat] = field(default_factory=dict)

    sections: list[Section] = field(default_factory=list)

    @classmethod
    def load(cls, document: Document) -> "DocumentModel":
        return cls(document=document, fmt=FormatResolver(document), blocks=read_blocks(document),
                   sections=document_sections(document))

    def para_format(self, block: Block) -> ParaFormat:
        if block.index not in self._para_cache:
            self._para_cache[block.index] = self.fmt.paragraph(block.el)
        return self._para_cache[block.index]

    def run_formats(self, block: Block) -> list[tuple[etree._Element, RunFormat]]:
        out = []
        for r in text_runs(block.el):
            rf = self.fmt.run(block.el, r)
            if not rf.hidden:
                out.append((r, rf))
        return out

    def starts_new_page(self, block: Block) -> bool:
        """Does this block begin on a fresh page?"""
        if block.kind == "p" and (self.para_format(block).page_break_before or block.starts_with_page_break):
            return True
        i = block.index - 1
        while i >= 0:
            prev = self.blocks[i]
            if prev.kind == "p":
                if prev.ends_section:
                    return _section_break_new_page(self.sections, prev.section)
                if prev.page_break_after:
                    return True
                if not prev.is_empty:
                    return False
            else:
                return False
            i -= 1
        return True  # first thing in the document


def document_sections(document: Document) -> list[Section]:
    """Sections in reading order, including breaks inside content controls.

    python-docx's `document.sections` misses section breaks that sit inside a
    content control (LibreOffice writes them inside the table of contents), so
    the engine uses this list everywhere instead.
    """
    sect_prs = []
    for el, _ in iter_body(document):
        if el.tag == qn("w:p"):
            ppr = el.find(qn("w:pPr"))
            sp = ppr.find(qn("w:sectPr")) if ppr is not None else None
            if sp is not None:
                sect_prs.append(sp)
    body_sp = document.element.body.find(qn("w:sectPr"))
    if body_sp is not None:
        sect_prs.append(body_sp)
    return [Section(sp, document.part) for sp in sect_prs]


def _section_break_new_page(sections: list[Section], section_index: int) -> bool:
    """A section break whose next section starts on a new page."""
    nxt = section_index + 1
    if nxt >= len(sections):
        return True
    t = sections[nxt]._sectPr.find(qn("w:type"))
    kind = t.get(qn("w:val")) if t is not None else "nextPage"
    return kind in ("nextPage", "oddPage", "evenPage")


WORD_RE = re.compile(r"[A-Za-z0-9À-ɏ]+(?:['’\-][A-Za-z0-9À-ɏ]+)*")


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text))
