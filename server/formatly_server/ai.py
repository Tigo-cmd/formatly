"""Reading a guideline with Claude and turning it into a draft rulebook.

Claude fills in a flat "guideline extraction" form (below), not the full
rulebook: a small form with nullable fields is easier to fill accurately, and
the server, not the model, decides how it maps onto the rulebook. The result
is always validated by the engine before a user sees it.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Literal, Protocol

from pydantic import BaseModel, ValidationError

log = logging.getLogger("formatly")

Align = Literal["left", "center", "right", "justify"]
NumFmt = Literal["lower_roman", "upper_roman", "decimal", "none"]


# --------------------------------------------------------------------------
# The form Claude fills in. Every field is nullable: null means "the guideline
# does not say".
# --------------------------------------------------------------------------

class Margins(BaseModel):
    top: str | None
    bottom: str | None
    left: str | None
    right: str | None


class Page(BaseModel):
    size: Literal["A4", "Letter", "Legal", "A5"] | None
    orientation: Literal["portrait", "landscape"] | None
    margins: Margins | None


class Body(BaseModel):
    font: str | None
    size_pt: float | None
    line_spacing: str | None
    alignment: Align | None
    first_line_indent: str | None


class Heading(BaseModel):
    level: int
    font: str | None
    size_pt: float | None
    bold: bool | None
    italic: bool | None
    all_caps: bool | None
    alignment: Align | None
    new_page: bool | None


class Section(BaseModel):
    title: str
    required: bool
    line_spacing: str | None
    max_paragraphs: int | None
    max_words: int | None
    must_include: list[str]


class Subsection(BaseModel):
    number: str
    title: str


class Chapter(BaseModel):
    number: int
    title: str
    sections: list[Subsection]


class PageNumbering(BaseModel):
    preliminaries: NumFmt | None
    main: NumFmt | None
    position: Literal["bottom_center", "bottom_right", "bottom_left", "top_center", "top_right",
                      "top_left"] | None


class Captions(BaseModel):
    table_position: Literal["above", "below"] | None
    figure_position: Literal["above", "below"] | None
    numbering: Literal["by_chapter", "sequential"] | None


class References(BaseModel):
    style: Literal["apa7", "apa6", "harvard", "mla", "chicago", "ieee"] | None
    order: Literal["alphabetical", "numeric"] | None
    hanging_indent: str | None
    line_spacing: str | None
    max_age_years: int | None


class Question(BaseModel):
    field: str  # rulebook path the answer sets, e.g. "body.line_spacing"
    question: str
    options: list[str]
    suggested: str | None


class Quote(BaseModel):
    rule: str
    quote: str


class GuidelineExtraction(BaseModel):
    suggested_name: str
    institution: str | None
    department: str | None
    document_type: str | None
    page: Page
    body: Body
    headings: list[Heading]
    chapter_label: Literal["words", "digits", "roman"] | None
    preliminaries: list[Section]
    chapters: list[Chapter]
    back_matter: list[Section]
    page_numbering: PageNumbering
    captions: Captions
    references: References
    main_text_max_words: int | None
    questions: list[Question]
    not_checkable: list[str]
    quotes: list[Quote]


def _strict(schema: dict) -> dict:
    """Pydantic's JSON schema, made acceptable for structured outputs: every
    object closed and fully required, unsupported keywords removed."""
    drop = {"title", "default", "minimum", "maximum", "minLength", "maxLength", "exclusiveMinimum",
            "exclusiveMaximum", "multipleOf"}

    def walk(node, names: bool = False):
        # `names`: this mapping's keys are field names (under "properties" or "$defs"), not keywords.
        if isinstance(node, dict):
            node = {k: walk(v, names=k in ("properties", "$defs") and not names)
                    for k, v in node.items() if names or k not in drop}
            if not names and node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            return node
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)


EXTRACTION_SCHEMA = _strict(GuidelineExtraction.model_json_schema())

SYSTEM = """You read formatting guidelines for academic and professional documents \
(project reports, theses, seminar papers, journal articles) and record their rules in \
a structured form for Formatly, a tool that checks documents against those rules.

Record only what the guideline states or clearly shows. Use null for anything it does \
not cover; Formatly fills gaps from its own defaults, so a guess is worse than null. \
Convert lengths to strings with units ("1in", "2.54cm", "1.5in"). Write line spacing as \
"single", "1.5", "double", or "exactly 24pt".

When the guideline is vague or self-contradictory about something that matters for \
checking (for example "standard margins", "appropriate spacing", two different fonts), \
leave the field null and add a question. Each question's `field` is the rulebook path \
its answer sets: page.size, page.margins.left, body.font, body.size, body.line_spacing, \
body.alignment, body.first_line_indent, references.style, page_numbering.main, and so on. \
Give 2-4 short options and your suggested answer.

List preliminary pages, chapters (with the numbered sections the guideline requires \
inside each) and back matter in the order the guideline gives. Mark a section required \
only if the guideline requires it.

Put rules that cannot be checked by inspecting a Word file's formatting and structure \
(binding colour, number of printed copies, plagiarism limits, submission deadlines, \
content quality) in `not_checkable`, in plain words.

For each rule you record, add a short supporting quote from the guideline to `quotes`."""


class AIError(Exception):
    """Something the user should see, e.g. the guideline could not be read."""


class GuidelineReader(Protocol):
    def read(self, blocks: list[dict]) -> GuidelineExtraction: ...


class ClaudeGuidelineReader:
    def __init__(self, api_key: str, model: str):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key or None)
        self.model = model

    def read(self, blocks: list[dict]) -> GuidelineExtraction:
        anthropic = self._anthropic
        content = blocks + [{"type": "text", "text": "Record the formatting rules in this guideline."}]
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM,
                messages=[{"role": "user", "content": content}],
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": EXTRACTION_SCHEMA}},
                # If the model declines, Anthropic re-runs the request on a suitable model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.BadRequestError as e:
            log.warning("guideline request rejected: %s", e.message)
            raise AIError("This guideline could not be read. Try a clearer photo or a PDF.") from e
        except anthropic.RateLimitError as e:
            raise AIError("Formatly is busy. Please try again in a minute.") from e
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            log.exception("guideline request failed")
            raise AIError("Reading the guideline failed. Please try again.") from e
        if response.stop_reason == "refusal":
            raise AIError("This guideline could not be processed.")
        if response.stop_reason == "max_tokens":
            raise AIError("This guideline is too long to read in one go. Upload the formatting part only.")
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return GuidelineExtraction.model_validate_json(text)
        except ValidationError as e:
            log.warning("guideline output did not validate: %s", e)
            raise AIError("Reading the guideline failed. Please try again.") from e


# --------------------------------------------------------------------------
# Turning uploads into message content
# --------------------------------------------------------------------------

IMAGE_TYPES = {b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg", b"GIF8": "image/gif", b"RIFF": "image/webp"}


def content_blocks(files: list[tuple[str, bytes]], text: str) -> list[dict]:
    """PDFs as documents, photos as images, Word files and pasted text as text."""
    blocks: list[dict] = []
    for name, data in files:
        if data[:4] == b"%PDF":
            blocks.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                          "data": base64.b64encode(data).decode()}})
            continue
        media = next((m for sig, m in IMAGE_TYPES.items() if data.startswith(sig)), None)
        if media == "image/webp" and data[8:12] != b"WEBP":
            media = None
        if media:
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": media,
                                                       "data": base64.b64encode(data).decode()}})
            continue
        if data[:2] == b"PK":
            blocks.append({"type": "text", "text": f"Guideline document ({name}):\n\n{docx_text(data)}"})
            continue
        raise AIError(f"{name}: upload a PDF, a Word file, or photos (JPG/PNG) of the guideline.")
    if text.strip():
        blocks.append({"type": "text", "text": f"Guideline text:\n\n{text.strip()}"})
    if not blocks:
        raise AIError("Upload the guideline or paste its text.")
    return blocks


def docx_text(data: bytes) -> str:
    import io

    import docx

    from formatly_engine.docmodel import read_blocks

    d = docx.Document(io.BytesIO(data))
    lines = [b.text for b in read_blocks(d)]
    return "\n".join(t for t in lines if t.strip())


# --------------------------------------------------------------------------
# Extraction -> rulebook
# --------------------------------------------------------------------------

SMALL_WORDS = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"}


def _title(text: str) -> str:
    """'BACKGROUND OF THE STUDY' -> 'Background of the Study'; mixed case is kept as written."""
    text = text.strip()
    if not text.isupper() and not text.islower():
        return text
    words = text.lower().split()
    return " ".join(w if (i and w in SMALL_WORDS) else w.capitalize() for i, w in enumerate(words))


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:40] or "section"


def _spacing(v: str | None):
    if v is None:
        return None
    s = v.strip().lower()
    return {"single": 1.0, "1": 1.0, "1.0": 1.0, "1.5": 1.5, "one and a half": 1.5, "double": 2.0,
            "2": 2.0, "2.0": 2.0}.get(s, s)


def _set(d: dict, path: str, value) -> None:
    keys = path.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def _sections(found: list[Section], base_specs: list[dict], kind: str) -> list[dict]:
    """Guideline sections as rulebook specs, keeping Formatly's ids and aliases where they match."""
    from formatly_engine.outline import names_match

    out = []
    for s in found:
        spec = next((b for b in base_specs if names_match(s.title, [b["title"], *b.get("aliases", [])])), None)
        item = dict(spec) if spec else {"id": _slug(s.title), "title": _title(s.title)}
        item["required"] = s.required
        if s.line_spacing:
            item["text"] = {**item.get("text", {}), "line_spacing": _spacing(s.line_spacing)}
            item["body_text"] = True
        if s.max_paragraphs:
            item["max_paragraphs"] = s.max_paragraphs
        if s.must_include:
            item["must_include"] = s.must_include
        out.append(item)
    if kind == "back" and not any(x["id"] == "references" for x in out):
        out += [b for b in base_specs if b["id"] == "references"]
    return out


def to_rulebook(x: GuidelineExtraction, base: dict, base_name: str) -> dict:
    """The rulebook data a user will review: `extends` the base, with what the guideline says."""
    data: dict = {"name": x.suggested_name[:200] or "My guideline", "extends": base_name}
    if x.page.size:
        _set(data, "page.size", x.page.size)
    if x.page.orientation:
        _set(data, "page.orientation", x.page.orientation)
    if x.page.margins and any(getattr(x.page.margins, s) for s in ("top", "bottom", "left", "right")):
        base_m = base.get("page", {}).get("margins") or {}
        _set(data, "page.margins", {s: getattr(x.page.margins, s) or base_m.get(s, "1in")
                                    for s in ("top", "bottom", "left", "right")})
    b = x.body
    for key, value in (("font", b.font), ("size", b.size_pt), ("line_spacing", _spacing(b.line_spacing)),
                       ("alignment", b.alignment), ("first_line_indent", b.first_line_indent)):
        if value is not None:
            _set(data, f"body.{key}", value)
    if x.headings:
        levels = {h["level"]: dict(h) for h in base.get("headings", [])}
        for h in x.headings:
            cur = levels.setdefault(h.level, {"level": h.level})
            for key, value in (("font", h.font), ("size", h.size_pt), ("bold", h.bold), ("italic", h.italic),
                               ("all_caps", h.all_caps), ("alignment", h.alignment), ("new_page", h.new_page)):
                if value is not None:
                    cur[key] = value
        data["headings"] = [levels[k] for k in sorted(levels)]
    st = base.get("structure", {})
    if x.chapter_label:
        _set(data, "structure.chapter_label", x.chapter_label)
    if x.preliminaries:
        _set(data, "structure.preliminaries", _sections(x.preliminaries, st.get("preliminaries", []), "pre"))
        abstract = next((s for s in x.preliminaries if "abstract" in s.title.lower() and s.max_words), None)
        if abstract:
            _set(data, "limits.abstract_max_words", abstract.max_words)
    if x.back_matter:
        _set(data, "structure.back_matter", _sections(x.back_matter, st.get("back_matter", []), "back"))
    if x.chapters:
        base_ch = {c["number"]: c for c in st.get("chapters", [])}
        chapters = []
        for c in x.chapters:
            item = {"number": c.number, "title": _title(c.title),
                    "aliases": base_ch.get(c.number, {}).get("aliases", [])}
            if c.sections:
                item["sections"] = [{"number": s.number, "title": _title(s.title)} for s in c.sections]
            chapters.append(item)
        _set(data, "structure.chapters", chapters)
    for key, value in (("preliminaries", x.page_numbering.preliminaries), ("main", x.page_numbering.main),
                       ("position", x.page_numbering.position)):
        if value is not None:
            _set(data, f"page_numbering.{key}", value)
    for key, value in (("table_position", x.captions.table_position),
                       ("figure_position", x.captions.figure_position), ("numbering", x.captions.numbering)):
        if value is not None:
            _set(data, f"captions.{key}", value)
    r = x.references
    for key, value in (("style", r.style), ("order", r.order), ("hanging_indent", r.hanging_indent),
                       ("max_age_years", r.max_age_years)):
        if value is not None:
            _set(data, f"references.{key}", value)
    if r.line_spacing:
        _set(data, "references.text", {"line_spacing": _spacing(r.line_spacing)})
    if x.main_text_max_words:
        _set(data, "limits.main_text_max_words", x.main_text_max_words)
    return data


def apply_answers(data: dict, answers: dict[str, str]) -> dict:
    """Set the fields a user answered (paths like "body.line_spacing")."""
    allowed = re.compile(r"^[a-z_]+(\.[a-z_]+){0,3}$")
    out = json.loads(json.dumps(data))
    for path, value in answers.items():
        if not allowed.match(path) or path.split(".")[0] in ("extends", "report"):
            continue
        v: object = value
        if path.endswith("line_spacing"):
            v = _spacing(value)
        elif path.endswith(".size") and not path.startswith("page."):
            try:
                v = float(value)
            except ValueError:
                pass
        _set(out, path, v)
    return out
