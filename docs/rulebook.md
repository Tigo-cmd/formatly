# Rulebook format

A rulebook is the set of rules a document is checked against. It is a YAML file
(JSON also works). Users will normally never see this file: the app builds it
from a form or from an uploaded guideline. It is documented here for the
Formatly team and for testing.

## Built-in rulebooks

| Name | For |
| --- | --- |
| `default` | **Formatly Standard (Project).** Final year projects. Built from the Formatly team's template documents and guidance. |
| `seminar` | Formatly Standard for seminar reports: Chapters One to Three required, "Background of the Study", seminar title page. |
| `postgraduate` | Formatly Standard for dissertations and theses: sources older than 4 years are errors. |
| `generic` | A common Nigerian layout (A4, 1.5 in binding margin, APA 7, first-line indents) for other institutions. |

Read [`default.yaml`](../engine/formatly_engine/rulebooks/default.yaml) alongside this page.

## Extending a rulebook

A rulebook usually starts from another one and changes only what differs:

```yaml
name: University X, Accounting, Project Work 2026
extends: default
body:
  line_spacing: 1.5
page:
  margins: {top: 1in, bottom: 1in, left: 1.25in, right: 1in}
```

Mappings merge; lists (such as `headings` or `structure.chapters`) replace the
parent's list entirely.

## Units

Lengths accept `in`, `cm`, `mm`, `pt`: `1in`, `2.54cm`, `25mm`, `72pt`. A bare
number is points. Font sizes are points.

Line spacing is a multiple (`1.0`, `1.5`, `2.0`, or `single` / `double`) or a
fixed height (`exactly 24pt`, `at least 12pt`).

Any rule left out or set to `null` is not checked.

Where a choice is acceptable, give a list: `alignment: [left, justify]`,
`size: [Letter, A4]`. Auto-fix uses the first.

## Sections

| Key | What it controls |
| --- | --- |
| `page` | `size` (A4, Letter, Legal, A5, or a list), `orientation`, `margins` (top, bottom, left, right, optional gutter), `allow_landscape_sections` (wide tables), `tolerance` |
| `body` | The running text: `font`, `size`, `line_spacing`, `space_before`, `space_after`, `alignment` (left, center, right, justify), `first_line_indent`. Alignment, spacing and indent are checked only on real paragraphs (12+ words, not list items). |
| `headings` | A list, one entry per level. Each takes the text keys above plus `bold`, `italic`, `all_caps` and `new_page`. Level 1 covers chapter labels and titles and named sections such as ABSTRACT. |
| `structure` | `preliminaries`, `chapters` and `back_matter` in the order they must appear. See *Sections and chapters* below. Also: `title_page_required`, `enforce_order`, `chapter_label` (`words` for CHAPTER ONE, `digits`, `roman`, `any`), `chapter_titles_strict`, `section_new_page`. |
| `title_page` | `text` (how its lines look) and `must_include`: a list of `{pattern, label}` where `pattern` is a regular expression (any case) and `label` says what is missing, e.g. "your registration number". |
| `page_numbering` | `preliminaries` and `main` formats (`lower_roman`, `upper_roman`, `decimal`, `none`), `main_starts_at`, `position` (e.g. `bottom_center`). |
| `captions` | `table_position` and `figure_position` (`above` / `below`), `numbering` (`by_chapter` for Table 4.1, `sequential`, `any`), `must_be_referenced`, and optional `text` / `table_text` rules (default: body font and size). |
| `references` | `style` (`apa7`, `apa6`, `harvard`, `mla`, `chicago`, `ieee`), `order` (`alphabetical`, `numeric`, `none`), `hanging_indent`, `text` (defaults to the body rules), `check_citations`, `max_age_years` (flag older sources) and `age_severity`. |
| `limits` | `abstract_max_words`, `abstract_min_words`, `main_text_max_words`. |
| `hygiene` | `no_highlight`, `no_coloured_text`, `no_double_spaces`. |
| `toc` | `automatic` (must be Word's automatic table of contents), `up_to_date` (headings, numbers and titles match the body; works for typed contents pages too), `lists_match_captions` (lists of figures and tables match the captions). |
| `report` | `comments_per_rule` (beyond this, the rest are listed in the report only), `comment_author`, `comment_initials`. |

## Sections and chapters

A named section (`preliminaries`, `back_matter`) takes:

| Key | Meaning |
| --- | --- |
| `id`, `title`, `aliases` | Its identity and the headings accepted for it. |
| `required` | `true`, `false`, or `if_figures` / `if_tables` / `if_figures_or_tables`. |
| `alternatives` | Other section ids that can stand in for it, e.g. a combined "List of Figures and Tables". |
| `body_text` | Hold its paragraphs to the body text rules. |
| `text` | Overrides for this section only, e.g. `{line_spacing: 1.0}` for the abstract. |
| `must_include`, `must_not_include` | Phrases (any case), e.g. the certification must say "External Examiner". |
| `max_paragraphs` | e.g. `1` for a one-paragraph abstract. |
| `free_format` | Pasted material such as code or questionnaires (appendices): only the heading is checked. |

A chapter takes `number`, `title`, `aliases`, `required` and `sections`: the
numbered headings it must contain, each with `number`, `title`, `aliases` and
`required`:

```yaml
chapters:
  - number: 1
    title: Introduction
    sections:
      - {number: "1.2", title: Statement of the Problem, aliases: [Problem Statement]}
```

## Severity

Each problem is one of:

- **error** ("Must fix"): breaks a rule for certain.
- **warning** ("Check"): very likely wrong, but needs a person to confirm (e.g.
  a citation that seems to be missing from the reference list).
- **suggestion**: advice, e.g. APA 7 style details or a chapter title that
  differs from the usual one.

## Rule IDs

Every issue carries a rule ID such as `body.font` or `structure.order`. The part
before the dot is the report category. The full list is in the code under
`engine/formatly_engine/checks/`.
