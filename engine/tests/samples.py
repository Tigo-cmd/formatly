"""Builds sample project documents for tests and demos.

`build_project()` with no arguments produces a document that follows the
default rulebook. Each keyword argument introduces one typical mistake.
"""

from __future__ import annotations

import io
import struct
import zlib

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Mm, Pt, RGBColor

FILLER = ("This study examines how small and medium enterprises in Enugu State adopt digital payment "
          "systems and how this adoption affects their monthly revenue and customer retention.")
CITED = ("Earlier work found that access to mobile money increases sales for informal traders "
         "(Okafor & Bello, 2021; Eze et al., 2020), while Adeyemi (2019) reported mixed results in rural markets.")

REFERENCES = [
    "Adeyemi, T. (2019). Mobile money adoption in rural Nigeria. Journal of African Business, 20(3), 211–229.",
    "Eze, C., Nwosu, P., & Obi, L. (2020). Digital payments and small firms. Lagos: University Press.",
    "Okafor, C., & Bello, A. (2021). Fintech and informal traders in West Africa. "
    "https://doi.org/10.1000/xyz123",
]


def tiny_png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"\x00" + b"\x80\x80\x80" * 8
    data = zlib.compress(raw * 8)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", data) + chunk(b"IEND", b""))


def set_style_font(style, name: str) -> None:
    """Set a style's font, removing theme fonts (which would otherwise win)."""
    rpr = style.element.get_or_add_rPr()
    rf = rpr.get_or_add_rFonts()
    for a in ("asciiTheme", "hAnsiTheme", "cstheme", "eastAsiaTheme"):
        rf.attrib.pop(qn(f"w:{a}"), None)
    for a in ("ascii", "hAnsi", "cs"):
        rf.set(qn(f"w:{a}"), name)


def add_field(paragraph, instr: str, result: str = "1") -> None:
    p = paragraph._p
    for kind, payload in (("begin", None), ("instr", instr), ("separate", None), ("text", result), ("end", None)):
        r = OxmlElement("w:r")
        if kind in ("begin", "separate", "end"):
            fc = OxmlElement("w:fldChar")
            fc.set(qn("w:fldCharType"), kind)
            r.append(fc)
        elif kind == "instr":
            it = OxmlElement("w:instrText")
            it.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            it.text = f" {payload} "
            r.append(it)
        else:
            t = OxmlElement("w:t")
            t.text = payload
            r.append(t)
        p.append(r)


def _fld_run(paragraph, kind: str, instr: str | None = None) -> None:
    r = OxmlElement("w:r")
    if instr is None:
        fc = OxmlElement("w:fldChar")
        fc.set(qn("w:fldCharType"), kind)
        r.append(fc)
    else:
        it = OxmlElement("w:instrText")
        it.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        it.text = instr
        r.append(it)
    paragraph._p.append(r)


def set_page_numbering(section, fmt: str | None, start: int | None) -> None:
    pg = OxmlElement("w:pgNumType")
    if fmt:
        pg.set(qn("w:fmt"), fmt)
    if start is not None:
        pg.set(qn("w:start"), str(start))
    section._sectPr.find(qn("w:pgMar")).addnext(pg)


def build_project(
    *,
    body_font: str = "Times New Roman",
    body_size: float = 12,
    spacing: float = 2.0,
    justify: bool = True,
    letter_paper: bool = False,
    even_margins: bool = False,
    chapter_digits: bool = False,
    headings_not_bold: bool = False,
    missing_dedication: bool = False,
    abstract_after_toc: bool = False,
    table_caption_below: bool = False,
    unsorted_references: bool = False,
    no_hanging_indent: bool = False,
    uncited_reference: bool = False,
    missing_reference: bool = False,
    highlight: bool = False,
    double_spaces: bool = False,
    no_page_numbers: bool = False,
    no_section_break: bool = False,
    chapter_same_page: bool = False,
    typed_toc: bool = False,
    long_abstract: bool = False,
    wrong_subheading_number: bool = False,
    theme_heading_font: bool = False,
) -> bytes:
    doc = Document()

    # Styles.
    normal = doc.styles["Normal"]
    set_style_font(normal, body_font)
    normal.font.size = Pt(body_size)
    pf = normal.paragraph_format
    pf.line_spacing = spacing
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY if justify else WD_ALIGN_PARAGRAPH.LEFT
    pf.first_line_indent = Inches(0.5)
    for name, align in (("Heading 1", WD_ALIGN_PARAGRAPH.CENTER), ("Heading 2", WD_ALIGN_PARAGRAPH.LEFT)):
        st = doc.styles[name]
        if not theme_heading_font:
            set_style_font(st, "Times New Roman")
        st.font.size = Pt(12)
        st.font.bold = not headings_not_bold
        st.font.color.rgb = RGBColor(0, 0, 0)
        st.paragraph_format.alignment = align
        st.paragraph_format.first_line_indent = Inches(0)
        st.paragraph_format.space_before = Pt(0)
        st.paragraph_format.space_after = Pt(0)
        st.paragraph_format.line_spacing = spacing

    sec = doc.sections[0]
    if letter_paper:
        sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    else:
        sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.top_margin = sec.bottom_margin = sec.right_margin = Inches(1)
    sec.left_margin = Inches(1 if even_margins else 1.5)

    def para(text: str, style: str | None = None, *, new_page: bool = False, center: bool = False):
        p = doc.add_paragraph(text, style=style)
        if new_page:
            p.paragraph_format.page_break_before = True
        if center:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.first_line_indent = Inches(0)
        return p

    def section_heading(text: str):
        return para(text, "Heading 1", new_page=True)

    # Title page.
    for line in ("DIGITAL PAYMENT ADOPTION AND THE PERFORMANCE OF SMALL BUSINESSES IN ENUGU STATE",
                 "BY", "ADA OKONKWO", "REG. NO: 2019/123456",
                 "A PROJECT SUBMITTED TO THE DEPARTMENT OF BUSINESS ADMINISTRATION", "OCTOBER 2026"):
        p = para(line, center=True)
        for r in p.runs:
            r.bold = True

    # Preliminaries.
    section_heading("CERTIFICATION")
    para("This is to certify that this project was carried out by Ada Okonkwo under supervision in the "
         "Department of Business Administration.")
    if not missing_dedication:
        section_heading("DEDICATION")
        para("This work is dedicated to my parents for their love and support throughout my studies.")
    section_heading("ACKNOWLEDGEMENTS")
    para("I thank everyone who supported this research, especially the business owners who took time to "
         "answer the questionnaire and share their experiences with digital payments.")

    def abstract():
        section_heading("ABSTRACT")
        n = 40 if long_abstract else 4
        para(" ".join([FILLER] * n))

    if not abstract_after_toc:
        abstract()

    toc_heading = section_heading("TABLE OF CONTENTS")
    del toc_heading
    toc_lines = ["CHAPTER ONE: INTRODUCTION\t1", "1.1 Background to the Study\t1",
                 "CHAPTER TWO: LITERATURE REVIEW\t3", "2.1 Conceptual Review\t3",
                 "CHAPTER THREE: RESEARCH METHODOLOGY\t5", "3.1 Research Design\t5",
                 "CHAPTER FOUR: DATA PRESENTATION, ANALYSIS AND INTERPRETATION\t7", "4.1 Data Presentation\t7",
                 "CHAPTER FIVE: SUMMARY, CONCLUSION AND RECOMMENDATIONS\t9", "5.1 Summary\t9",
                 "REFERENCES\t11"]
    if typed_toc:
        for line in toc_lines:
            para(line.replace("\t", " ........ "))
    else:
        first = para("")
        _fld_run(first, "begin")
        _fld_run(first, "instr", ' TOC \\o "1-3" \\h \\z \\u ')
        _fld_run(first, "separate")
        first.add_run(toc_lines[0])
        for line in toc_lines[1:]:
            para(line)
        last = doc.paragraphs[-1]
        _fld_run(last, "end")

    if abstract_after_toc:
        abstract()

    # Section break before Chapter One: roman numerals before, arabic from 1 after.
    if not no_section_break:
        doc.add_section(WD_SECTION.NEW_PAGE)

    chapters = [
        ("ONE", "INTRODUCTION", "Background to the Study"),
        ("TWO", "LITERATURE REVIEW", "Conceptual Review"),
        ("THREE", "RESEARCH METHODOLOGY", "Research Design"),
        ("FOUR", "DATA PRESENTATION, ANALYSIS AND INTERPRETATION", "Data Presentation"),
        ("FIVE", "SUMMARY, CONCLUSION AND RECOMMENDATIONS", "Summary"),
    ]
    for n, (word, title, sub) in enumerate(chapters, start=1):
        label = f"CHAPTER {n}" if chapter_digits else f"CHAPTER {word}"
        first_chapter = n == 1
        new_page = not (first_chapter and not no_section_break)
        if chapter_same_page and n == 2:
            new_page = False
        para(label, "Heading 1", new_page=new_page)
        para(title, "Heading 1")
        number = f"{n}.1"
        if wrong_subheading_number and n == 2:
            number = "3.1"
        para(f"{number} {sub}", "Heading 2")
        text = FILLER
        if highlight and n == 1:
            text = FILLER
        p = para(text)
        if highlight and n == 1:
            p.runs[0].font.highlight_color = WD_COLOR_INDEX.YELLOW
        cited = CITED
        if missing_reference and n == 2:
            cited += " Similar patterns were reported by Musa (2018)."
        if double_spaces and n == 3:
            cited = cited.replace("increases sales", "increases  sales")
        para(cited)
        if n == 4:
            para("As shown in Table 4.1 and Figure 4.1, most respondents are between 26 and 35 years old and "
                 "most of them use mobile transfers daily.")
            if not table_caption_below:
                para("Table 4.1: Distribution of respondents by age", center=True)
            t = doc.add_table(rows=3, cols=2)
            t.style = "Table Grid"
            for row, (a, b) in zip(t.rows, (("Age", "Frequency"), ("18–25", "40"), ("26–35", "62"))):
                row.cells[0].text, row.cells[1].text = a, b
            if table_caption_below:
                para("Table 4.1: Distribution of respondents by age", center=True)
            doc.add_picture(io.BytesIO(tiny_png()), width=Inches(2))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            para("Figure 4.1: Daily use of mobile transfers", center=True)

    # References.
    para("REFERENCES", "Heading 1", new_page=True)
    refs = list(REFERENCES)
    if uncited_reference:
        refs.append("Usman, K. (2017). Banking the unbanked. Abuja: Policy Press.")
    if unsorted_references:
        refs = list(reversed(refs))
    for r in refs:
        p = para(r)
        if not no_hanging_indent:
            p.paragraph_format.left_indent = Inches(0.5)
            p.paragraph_format.first_line_indent = Inches(-0.5)

    # Page numbering.
    sections = doc.sections
    for s in sections:
        s.page_width, s.page_height = sec.page_width, sec.page_height
        s.top_margin, s.bottom_margin = sec.top_margin, sec.bottom_margin
        s.left_margin, s.right_margin = sec.left_margin, sec.right_margin
    if not no_page_numbers:
        footer = sections[0].footer
        footer.is_linked_to_previous = False
        fp = footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        fp.paragraph_format.first_line_indent = Inches(0)
        add_field(fp, "PAGE")
        sections[0].different_first_page_header_footer = True
    if len(sections) > 1:
        set_page_numbering(sections[0], "lowerRoman", None)
        set_page_numbering(sections[1], "decimal", 1)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def build_messy_project() -> bytes:
    """Many typical mistakes at once, for demos."""
    return build_project(
        body_font="Calibri", body_size=11, spacing=1.15, justify=False, letter_paper=True,
        even_margins=True, chapter_digits=True, headings_not_bold=True, missing_dedication=True,
        abstract_after_toc=True, table_caption_below=True, unsorted_references=True,
        no_hanging_indent=True, uncited_reference=True, missing_reference=True, highlight=True,
        double_spaces=True, no_page_numbers=True, no_section_break=True, long_abstract=True,
    )


__all__ = ["build_project", "build_messy_project", "WD_BREAK"]


# --------------------------------------------------------------------------
# Formatly Standard (the default rulebook): built after the team's templates
# --------------------------------------------------------------------------

def build_standard_project(
    *,
    seminar: bool = False,
    certification_supervisor: bool = False,
    missing_scope: bool = False,
    old_reference: bool = False,
    abstract_two_paragraphs: bool = False,
    abstract_double: bool = False,
    toc_wrong_title: bool = False,
    toc_without_numbers: bool = False,
    list_title_mismatch: bool = False,
    no_list_of_tables: bool = False,
    blank_lines_before_chapter: bool = False,
    split_reference: bool = False,
    reference_tabs: bool = False,
    title_page_no_reg_number: bool = False,
    a4: bool = False,
    report_kind: str | None = None,  # e.g. "DISSERTATION"
) -> bytes:
    from datetime import date

    year = date.today().year
    doc = Document()
    normal = doc.styles["Normal"]
    set_style_font(normal, "Times New Roman")
    normal.font.size = Pt(12)
    pf = normal.paragraph_format
    pf.line_spacing = 2.0
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    pf.first_line_indent = Inches(0)

    sec = doc.sections[0]
    if a4:
        sec.page_width, sec.page_height = Mm(210), Mm(297)
    else:
        sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    for side in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(sec, side, Inches(1))

    def para(text, *, bold=False, center=False, new_page=False, spacing=None, italic=False):
        p = doc.add_paragraph()
        r = p.add_run(text)
        r.bold = bold
        r.italic = italic
        if center:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if new_page:
            p.paragraph_format.page_break_before = True
        if spacing is not None:
            p.paragraph_format.line_spacing = spacing
        return p

    def heading(text, *, new_page=False):  # level 1: centred, bold, capitals
        return para(text.upper(), bold=True, center=True, new_page=new_page)

    def sub(text):  # level 2 / 3: bold, capitals for level 2
        number, title = text.split(" ", 1)
        return para(f"{number} {title.upper() if number.count('.') == 1 else title}", bold=True)

    kind = report_kind or ("SEMINAR" if seminar else "PROJECT")
    title = "DESIGN OF A SMART IRRIGATION CONTROLLER"
    lines = [title, "BY", "ADA OKONKWO"]
    if not title_page_no_reg_number:
        lines.append("MOUAU/CME/19/123456")
    lines += [f"A {kind} REPORT SUBMITTED TO THE DEPARTMENT OF COMPUTER ENGINEERING",
              "MICHAEL OKPARA UNIVERSITY OF AGRICULTURE, UMUDIKE", f"AUGUST {year}"]
    for line in lines:
        para(line, bold=True, center=True)

    prose = ("This report describes the design and construction of a controller that waters crops "
             "automatically using soil moisture readings and a small solar powered pump.")
    heading("DECLARATION", new_page=True)
    para(f"I declare that this {kind.lower()} is my original work and has not been submitted elsewhere "
         "for the award of any degree.", spacing=1.5)
    heading("CERTIFICATION", new_page=True)
    para(f"This is to certify that this {kind.lower()} was carried out by Ada Okonkwo in the Department "
         "of Computer Engineering and meets the requirements of the department.", spacing=1.5)
    for signer in ("Project Supervisor", "Head of Department",
                   "External Supervisor" if certification_supervisor else "External Examiner"):
        para(signer, spacing=1.5)
    heading("DEDICATION", new_page=True)
    para("This work is dedicated to my parents for their love, patience and support throughout my studies "
         "at the university.", spacing=1.5)
    heading("ACKNOWLEDGEMENT", new_page=True)
    para("I thank my supervisor and every member of staff of the department for their guidance and "
         "encouragement during this work.", spacing=1.5)

    chapter_one = [("1.1", "Background of the Study" if seminar else "Background of the Project"),
                   ("1.2", "Statement of the Problem"), ("1.3", "Aim and Objectives"),
                   ("1.4", "Significance of the Study" if seminar else "Significance of the Project")]
    if not missing_scope:
        chapter_one.append(("1.5", "Scope of the Study" if seminar else "Scope of the Project"))
    chapters = [
        ("ONE", "INTRODUCTION", chapter_one),
        ("TWO", "LITERATURE REVIEW", [("2.1", "Review of Relevant Literature"), ("2.2", "Review of Related Works"),
                                      ("2.3", "Summary of Literature Review")]),
    ]
    if not seminar:
        chapters += [
            ("THREE", "MATERIALS AND METHODS", [("3.1", "Materials"), ("3.2", "Methods")]),
            ("FOUR", "RESULTS AND DISCUSSION", [("4.1", "Results")]),
            ("FIVE", "CONCLUSION AND RECOMMENDATION", [("5.1", "Conclusion"), ("5.2", "Recommendation")]),
        ]

    heading("TABLE OF CONTENTS", new_page=True)
    prelim_lines = ["Title Page\ti", "Declaration\tii", "Certification\tiii", "Dedication\tiv",
                    "Acknowledgement\tv", "Table of Contents\tvi", "List of Figures\tvii"]
    if not no_list_of_tables:
        prelim_lines.append("List of Tables\tviii")
    prelim_lines.append("Abstract\tix")
    for line in prelim_lines:
        para(line)
    for word, ch_title, subs in chapters:
        para(f"CHAPTER {word}: {ch_title}\t1")
        for number, sub_title in subs:
            shown = sub_title
            if toc_wrong_title and number == "2.2":
                shown = "Overview of Existing Systems"
            para(f"{'' if toc_without_numbers else number + ' '}{shown}\t1")
    para("REFERENCES\t9")

    table_chapter = 2 if seminar else 4
    figure_title = "Block diagram of the controller"
    heading("LIST OF FIGURES", new_page=True)
    para(f"Figure {table_chapter}.1 {'Circuit layout' if list_title_mismatch else figure_title}\tv")
    if not no_list_of_tables:
        heading("LIST OF TABLES", new_page=True)
        para(f"Table {table_chapter}.1 Cost of components\tvi")

    heading("ABSTRACT", new_page=True)
    abstract = " ".join([prose] * 4)
    para(abstract, spacing=2.0 if abstract_double else 1.0)
    if abstract_two_paragraphs:
        para(prose, spacing=1.0)

    doc.add_section(WD_SECTION.NEW_PAGE)
    for n, (word, ch_title, subs) in enumerate(chapters, start=1):
        if blank_lines_before_chapter and n == 2:
            for _ in range(8):
                doc.add_paragraph()
        heading(f"CHAPTER {word}", new_page=n > 1 and not (blank_lines_before_chapter and n == 2))
        heading(ch_title)
        for number, sub_title in subs:
            sub(f"{number} {sub_title}")
            cites = f"Prior systems watered on fixed timers (Okafor & Bello, {year - 2}), while Eze et al. ({year - 1}) used sensors."
            para(prose)
            para(cites)
        if n == table_chapter:
            para(f"As shown in Table {table_chapter}.1 and Figure {table_chapter}.1, the controller uses few parts.")
            para(f"Table {table_chapter}.1 Cost of components", center=True)
            t = doc.add_table(rows=2, cols=2)
            t.style = "Table Grid"
            t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Component", "Cost"
            t.rows[1].cells[0].text, t.rows[1].cells[1].text = "Sensor", "2,000"
            doc.add_picture(io.BytesIO(tiny_png()), width=Inches(2))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            para(f"Figure {table_chapter}.1 {figure_title}", center=True)

    heading("REFERENCES", new_page=True)
    refs = [f"Eze, C., Nwosu, P., & Obi, L. ({year - 1}). Sensor-based irrigation for small farms. "
            "Journal of Agricultural Engineering, 12(2), 40–52.",
            f"Okafor, C., & Bello, A. ({year - 2}). Automatic watering with solar pumps. Lagos: University Press."]
    if old_reference:
        refs.insert(1, "Musa, K. (2010). Irrigation in the savannah. Abuja: Policy Press.")
        doc.paragraphs[-1]  # keep the reference cited below
    for r in refs:
        if split_reference and r.startswith("Okafor"):
            first, rest = r.split(" Lagos:", 1)
            p1 = para(first, spacing=1.5)
            p2 = para("\tLagos:" + rest, spacing=1.5)
            for p in (p1, p2):
                p.paragraph_format.left_indent = Inches(0.5)
                p.paragraph_format.first_line_indent = Inches(-0.5)
            continue
        text = r.replace(" Journal", "\tJournal") if reference_tabs else r
        p = para(text, spacing=1.5)
        p.paragraph_format.left_indent = Inches(0.5)
        p.paragraph_format.first_line_indent = Inches(-0.5)
    if old_reference:
        # cite Musa in the last chapter so only its age is the problem
        target = [p for p in doc.paragraphs if p.text.startswith("Prior systems")][-1]
        target.add_run(" Earlier work agreed (Musa, 2010).")

    sections = doc.sections
    for s in sections:
        s.page_width, s.page_height = sec.page_width, sec.page_height
        for side in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
            setattr(s, side, getattr(sec, side))
    footer = sections[0].footer
    footer.is_linked_to_previous = False
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_field(fp, "PAGE")
    sections[0].different_first_page_header_footer = True
    set_page_numbering(sections[0], "lowerRoman", None)
    set_page_numbering(sections[1], "decimal", 1)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
