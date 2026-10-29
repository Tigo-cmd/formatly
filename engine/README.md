# Formatly engine

Checks a Word document (`.docx`) against a rulebook. It returns a report, writes
the problems into a copy of the document as Word comments, and auto-fixes the
formatting problems.

It is a plain Python library with a command-line tool. The server (Phase 2)
calls the same functions.

## Install

```sh
cd engine
pip install -e ".[dev]"
```

## Try it

```sh
python scripts/make_samples.py ../out          # sample documents to try
formatly check ../out/standard-with-mistakes.docx -o ../out/commented.docx
formatly fix   ../out/standard-with-mistakes.docx -o ../out/fixed.docx
formatly rules show default                    # the rulebook in use
formatly check my-project.docx -r my-rules.yaml --json report.json
```

`check` exits with status 1 when there are errors, so it can be used in scripts.

## Library

```python
from formatly_engine import check, fix, load_rulebook

result = check("project.docx", load_rulebook("default"))
result.report               # score, counts, categories, every issue (JSON-ready)
result.annotated_bytes()    # the document with comments

fixed = fix("project.docx")
fixed.fixed                 # corrected .docx bytes
fixed.applied               # {rule: issues fixed}
fixed.after.report          # honest re-check of the corrected file
```

## How it works

| Module | Job |
| --- | --- |
| `docmodel.py` | Reads the document in order and works out each paragraph's real formatting through Word's layers (defaults, theme fonts, style chains, character styles, direct formatting). |
| `outline.py` | Finds the title page, named sections, chapters ("CHAPTER ONE"), headings and their levels. |
| `checks/` | The checks: page setup, body text, headings, structure, page numbering, table of contents, captions, references and citations, word limits, clean-up. |
| `annotate.py` | Writes issues as Word comments, one per paragraph, capped per rule. |
| `fix.py` | Auto-fix. Changes formatting, numbering, order and layout; never the writer's words. Runs in passes and re-checks between them. |
| `report.py` | Score and summary. |
| `rulebook.py` | The rulebook model. Format: [`docs/rulebook.md`](../docs/rulebook.md). |

## Tests

```sh
pytest -q
```

The tests build sample documents in code (`tests/samples.py`), one per typical
mistake. Each mistake must be found, and each fixable one must be gone after
`fix`. One test round-trips the samples through LibreOffice, when it is
installed, to cover files written by programs other than Word.

## Built-in rulebooks

`default` (Formatly Standard, project), `seminar`, `postgraduate`, `generic`.
Choose one with `-r`, e.g. `formatly check seminar.docx -r seminar`.

## Not yet covered (later phases)

- AI checks: reading a guideline into a rulebook, recognising unusual headings,
  the long tail of reference formats, spelling, grammar, content suggestions.
- Regenerating the table of contents and lists of tables and figures.
- Checks that need page layout (e.g. "a table must not split across pages").
- Fonts set by table styles are not yet resolved.
