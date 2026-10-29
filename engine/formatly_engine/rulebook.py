"""Rulebooks: the rules a document is checked against.

A rulebook is a YAML (or JSON) file. It can `extend` another rulebook, usually
the built-in `default`, and only state what differs. Lists replace, mappings
merge. See docs/rulebook.md for the format.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from .units import parse_length

BUILTIN_DIR = Path(__file__).parent / "rulebooks"

Length = Annotated[int, BeforeValidator(parse_length)]
Alignment = Literal["left", "center", "right", "justify"]
NumberFormat = Literal["lower_roman", "upper_roman", "decimal", "none"]
PaperSize = Literal["A4", "Letter", "Legal", "A5"]
Severity = Literal["error", "warning", "suggestion"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LineSpacing(_Model):
    """Either a multiple of single spacing (1.0, 1.5, 2.0) or an exact height."""

    rule: Literal["multiple", "exact", "at_least"] = "multiple"
    value: float  # multiple, or points for exact / at_least

    @classmethod
    def parse(cls, v: Any) -> Any:
        if v is None or isinstance(v, (dict, LineSpacing)):
            return v
        if isinstance(v, (int, float)):
            return {"rule": "multiple", "value": float(v)}
        s = str(v).strip().lower()
        named = {"single": 1.0, "one and half": 1.5, "1.5 lines": 1.5, "double": 2.0}
        if s in named:
            return {"rule": "multiple", "value": named[s]}
        m = re.match(r"^(exact|exactly|at_least|at least)\s+(\d+(?:\.\d+)?)\s*(pt)?$", s)
        if m:
            rule = "exact" if m.group(1).startswith("exact") else "at_least"
            return {"rule": rule, "value": float(m.group(2))}
        return {"rule": "multiple", "value": float(s)}


LineSpacingField = Annotated[LineSpacing | None, BeforeValidator(LineSpacing.parse)]


class TextRules(_Model):
    """How a kind of text must look. Unset (null) means "not checked"."""

    font: str | None = None
    size: float | None = None  # points
    bold: bool | None = None
    italic: bool | None = None
    all_caps: bool | None = None
    alignment: Alignment | list[Alignment] | None = None  # a list accepts any of them
    line_spacing: LineSpacingField = None
    space_before: Length | None = None
    space_after: Length | None = None
    first_line_indent: Length | None = None


class Margins(_Model):
    top: Length
    bottom: Length
    left: Length
    right: Length
    gutter: Length | None = None


class PageRules(_Model):
    size: PaperSize | list[PaperSize] | None = "A4"  # a list accepts any; auto-fix uses the first
    orientation: Literal["portrait", "landscape"] | None = "portrait"
    allow_landscape_sections: bool = True  # e.g. for a wide table
    margins: Margins | None = None
    tolerance: Length = parse_length("0.05in")


class HeadingRules(TextRules):
    level: int = Field(ge=1, le=6)
    new_page: bool | None = None


class SectionSpec(_Model):
    """A named section such as Dedication, Abstract or References."""

    id: str
    title: str
    aliases: list[str] = []
    # True, False, or required only when the document has figures / tables.
    required: bool | Literal["if_figures", "if_tables", "if_figures_or_tables"] = True
    alternatives: list[str] = []  # ids of sections that can stand in for this one
    body_text: bool = False  # check its paragraphs against the body text rules
    text: TextRules | None = None  # overrides the body text rules for this section
    must_include: list[str] = []  # phrases the section must contain (any case)
    must_not_include: list[str] = []  # phrases it must not contain
    max_paragraphs: int | None = None
    free_format: bool = False  # pasted material (code, questionnaires): only its heading is checked


class SubsectionSpec(_Model):
    """A numbered heading a chapter must have, e.g. 1.2 Statement of the Problem."""

    number: str
    title: str
    aliases: list[str] = []
    required: bool = True


class ChapterSpec(_Model):
    number: int
    title: str
    aliases: list[str] = []
    required: bool = True
    sections: list[SubsectionSpec] = []


class StructureRules(_Model):
    title_page_required: bool = True
    preliminaries: list[SectionSpec] = []
    chapters: list[ChapterSpec] = []
    back_matter: list[SectionSpec] = []
    enforce_order: bool = True
    chapter_label: Literal["words", "digits", "roman", "any"] = "words"  # CHAPTER ONE / 1 / I
    chapter_titles_strict: bool = False  # wrong chapter title: error (true) or suggestion
    section_new_page: bool = True  # each preliminary / back-matter section starts a new page


class PageNumberingRules(_Model):
    preliminaries: NumberFormat | None = "lower_roman"
    main: NumberFormat | None = "decimal"
    main_starts_at: int | None = 1
    position: Literal["bottom_center", "bottom_right", "bottom_left", "top_center", "top_right", "top_left"] | None = "bottom_center"


class CaptionRules(_Model):
    table_position: Literal["above", "below"] | None = "above"
    figure_position: Literal["above", "below"] | None = "below"
    numbering: Literal["by_chapter", "sequential", "any"] = "by_chapter"
    must_be_referenced: bool = True
    text: TextRules | None = None  # caption look; font and size default to the body text
    table_text: TextRules | None = None  # text inside tables; font defaults to the body font


class ReferenceRules(_Model):
    style: Literal["apa7", "apa6", "harvard", "mla", "chicago", "ieee"] | None = "apa7"
    order: Literal["alphabetical", "numeric", "none"] = "alphabetical"
    hanging_indent: Length | None = parse_length("0.5in")
    text: TextRules | None = None  # unset fields fall back to the body text rules
    check_citations: bool = True
    max_age_years: int | None = None  # sources older than this many years are flagged
    age_severity: Severity = "warning"


class LimitRules(_Model):
    abstract_max_words: int | None = None
    abstract_min_words: int | None = None
    main_text_max_words: int | None = None


class HygieneRules(_Model):
    no_highlight: bool = True
    no_coloured_text: bool = True
    no_double_spaces: bool = True


class TocRules(_Model):
    automatic: bool = True  # must be Word's automatic table of contents
    up_to_date: bool = True  # headings, their numbers and titles match the body
    lists_match_captions: bool = True  # lists of tables / figures match the captions


class Requirement(_Model):
    """Something a page must contain, as a regular expression (any case)."""

    pattern: str
    label: str  # what to tell the writer is missing, e.g. "your registration number"


class TitlePageRules(_Model):
    text: TextRules | None = None
    must_include: list[Requirement] = []


class ReportRules(_Model):
    comments_per_rule: int = 15  # beyond this, the report lists the rest
    comment_author: str = "Formatly"
    comment_initials: str = "FM"


class Rulebook(_Model):
    name: str
    version: int = 1
    description: str = ""
    extends: str | None = None
    page: PageRules = PageRules()
    body: TextRules = TextRules()
    headings: list[HeadingRules] = []
    structure: StructureRules = StructureRules()
    page_numbering: PageNumberingRules = PageNumberingRules()
    captions: CaptionRules = CaptionRules()
    references: ReferenceRules = ReferenceRules()
    limits: LimitRules = LimitRules()
    hygiene: HygieneRules = HygieneRules()
    toc: TocRules = TocRules()
    title_page: TitlePageRules = TitlePageRules()
    report: ReportRules = ReportRules()

    @field_validator("headings")
    @classmethod
    def _unique_levels(cls, v: list[HeadingRules]) -> list[HeadingRules]:
        levels = [h.level for h in v]
        if len(levels) != len(set(levels)):
            raise ValueError("each heading level may appear only once")
        return v

    def heading(self, level: int) -> HeadingRules | None:
        return next((h for h in self.headings if h.level == level), None)

    def reference_text(self) -> TextRules:
        """Reference list text rules, falling back to the body rules."""
        merged = merge_text(self.body, self.references.text)
        own = self.references.text or TextRules()
        # References use a hanging indent instead, and are often left-aligned.
        return merged.model_copy(update={"first_line_indent": None, "alignment": own.alignment})

    def caption_text(self) -> TextRules:
        own = self.captions.text or TextRules()
        return own.model_copy(update={"font": own.font or self.body.font, "size": own.size or self.body.size})

    def table_text(self) -> TextRules:
        own = self.captions.table_text or TextRules()
        return own.model_copy(update={"font": own.font or self.body.font})

    def section_spec(self, spec_id: str) -> "SectionSpec | None":
        return next((s for s in (*self.structure.preliminaries, *self.structure.back_matter) if s.id == spec_id),
                    None)

    def body_text_for(self, spec_id: str | None) -> TextRules:
        """Body text rules inside a section, with that section's overrides."""
        spec = self.section_spec(spec_id) if spec_id else None
        return merge_text(self.body, spec.text if spec else None)


def merge_text(base: TextRules, over: TextRules | None) -> TextRules:
    if over is None:
        return base
    return base.model_copy(update={k: v for k, v in over if v is not None})


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def builtin_names() -> list[str]:
    return sorted(p.stem for p in BUILTIN_DIR.glob("*.yaml"))


def _load_raw(source: str | Path, _seen: tuple[str, ...] = ()) -> dict:
    path = Path(source)
    if not path.exists():
        builtin = BUILTIN_DIR / f"{source}.yaml"
        if not builtin.exists():
            raise FileNotFoundError(
                f"rulebook {source!r} not found (built-in: {', '.join(builtin_names())})"
            )
        path = builtin
    key = str(path.resolve())
    if key in _seen:
        raise ValueError(f"rulebook extends itself: {' -> '.join(_seen + (key,))}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: a rulebook must be a mapping")
    parent = data.get("extends")
    if parent:
        parent_path = Path(parent)
        if not parent_path.is_absolute() and (path.parent / parent_path).exists():
            parent = str(path.parent / parent_path)
        data = deep_merge(_load_raw(parent, _seen + (key,)), data)
        data["extends"] = parent if isinstance(parent, str) else str(parent)
    return data


def load_rulebook(source: str | Path = "default") -> Rulebook:
    """Load a rulebook from a file path or a built-in name, resolving `extends`."""
    return Rulebook.model_validate(_load_raw(source))


def rulebook_from_dict(data: dict) -> Rulebook:
    """Build a rulebook from a mapping (e.g. from the API), resolving `extends`."""
    parent = data.get("extends")
    if parent:
        data = deep_merge(_load_raw(parent), data)
    return Rulebook.model_validate(data)
