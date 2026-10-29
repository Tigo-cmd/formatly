# Formatly

**Format, cite and correct your work against any guideline.**

Upload the guideline you were given (by a lecturer, supervisor, department,
journal, employer or anyone else) and your document. Formatly checks the
document against those rules, returns it with comments wherever something is
wrong, and can correct the formatting automatically.

The full product plan is in [PLAN.md](PLAN.md).

## Status

| Part | Status |
| --- | --- |
| [`engine/`](engine/): checking, comments, auto-fix | Phase 1, working |
| `server/`: accounts, uploads, payments, AI | Phase 2 |
| `app/`: web, Android, desktop | Phase 2 onwards |

## Quick start

```sh
cd engine
pip install -e ".[dev]"
python scripts/make_samples.py ../out
formatly check ../out/standard-with-mistakes.docx -o ../out/commented.docx
formatly fix ../out/standard-with-mistakes.docx -o ../out/fixed.docx
```

## Rulebooks

Rules are written as a rulebook: see [docs/rulebook.md](docs/rulebook.md).
The default is the **Formatly Standard**, built from the team's template
documents, with variants for seminars and postgraduate work.
