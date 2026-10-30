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
| [`engine/`](engine/): checking, comments, auto-fix, learning rules from a model document | Working |
| [`server/`](server/): accounts, uploads, rulebooks and library, versions, credits, AI guideline reading | Working (payments: Phase 3) |
| [`app/`](app/): the website | Working (Android and desktop: Phase 5) |

## Run it on your computer

**With Docker** (easiest): install Docker Desktop, then in this folder:

```sh
docker compose up --build
```

Open http://localhost:8000, create an account and upload a `.docx`. Accounts and
documents are kept between restarts. To let Formatly read guidelines with AI,
start it with your key: `ANTHROPIC_API_KEY=sk-ant-... docker compose up --build`.

**Without Docker** (Python 3.10+ and Node 22):

```sh
pip install -e engine -e server
cd app && npm install && npm run build && cd ..
formatly-server                     # website and API on http://localhost:8000
```

While working on the website, run `npm run dev` in `app/` as well and open
http://localhost:5173 (it reloads on every change).

**Preview with sample data** (no server): `npm run build:preview` in `app/`
writes `dist-preview/formatly-preview.html`, the whole website in one file with
results from the real engine on a sample project.

## Try the engine on its own

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
