# Formatly server

The API behind the website and apps: accounts, uploads, rulebooks (built-in,
your own, the shared library), checks, version history, auto-fix with credits,
and making rulebooks from a guideline (read by AI) or a model document.

## Run it

```sh
pip install -e ../engine -e ".[dev]"
formatly-server                      # http://localhost:8000, API docs at /docs
pytest -q
```

## Settings (environment variables)

| Variable | Default | Meaning |
| --- | --- | --- |
| `FORMATLY_DATABASE_URL` | `sqlite:///./formatly.db` | Use PostgreSQL in production, e.g. `postgresql+psycopg://...` |
| `FORMATLY_STORAGE_DIR` | `./storage` | Where uploaded and generated files are kept |
| `FORMATLY_SECRET_KEY` | random | Signs login tokens. **Set it in production**, or everyone is signed out on restart |
| `FORMATLY_CORS_ORIGINS` | `http://localhost:5173` | Web app addresses allowed to call the API |
| `FORMATLY_MAX_UPLOAD_MB` | `25` | Largest upload |
| `FORMATLY_FREE_CREDITS` | `2` | Auto-fixes given on sign-up |
| `FORMATLY_FIX_COST` | `1` | Credits per auto-fix |
| `FORMATLY_ADMIN_EMAILS` | | Comma-separated; these accounts can verify library rulebooks |
| `ANTHROPIC_API_KEY` | | Enables reading guidelines with Claude |
| `FORMATLY_AI_MODEL` | `claude-opus-5-5` | Model used to read guidelines |

## API at a glance

| Endpoint | What it does |
| --- | --- |
| `POST /api/auth/register`, `/login`, `GET /me` | Accounts (email and password) |
| `GET /api/rulebooks`, `/library?q=`, `/{ref}` | Built-in and own rulebooks, public library, one rulebook in full |
| `POST/PUT/DELETE /api/rulebooks` | Own rulebooks; they `extend` a built-in or another readable rulebook |
| `POST /api/documents` | Upload a `.docx` and check it |
| `POST /api/documents/{id}/versions` | Upload a corrected version |
| `PATCH /api/documents/{id}` | Rename, or switch rulebook (re-checks) |
| `GET /api/versions/{id}/report`, `/download?kind=commented\|original` | Report and files |
| `POST /api/versions/{id}/fix` | Auto-fix into a new version (costs credits) |
| `POST /api/guidelines` | Guideline (PDF, Word, photos, text) to draft rulebook, read by AI in the background |
| `POST /api/guidelines/sample` | Model `.docx` to draft rulebook, measured |
| `POST /api/guidelines/{id}/answers` | Answer the draft's questions |
| `GET /api/billing` | Credits and history (buying credits: Phase 3) |

Checks run inside the request (a long project takes about a second). Guideline
reading runs in the background; the app polls for it.
