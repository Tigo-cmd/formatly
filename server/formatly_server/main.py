"""The FastAPI app."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, settings as default_settings
from .db import Database
from .routers import auth, billing, documents, guidelines, rulebooks
from .storage import LocalStorage


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or default_settings
    app = FastAPI(title="Formatly API", version="0.1.0")
    app.state.settings = settings
    app.state.db = Database(settings.database_url)
    app.state.db.create_all()
    app.state.storage = LocalStorage(settings.storage_dir)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                       allow_methods=["*"], allow_headers=["*"])
    app.state.reader = _reader(settings)
    for r in (auth.router, rulebooks.router, documents.router, billing.router, guidelines.router):
        app.include_router(r, prefix="/api")

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    if (settings.web_dir / "index.html").exists():
        _serve_website(app, settings.web_dir)
    return app


def _serve_website(app: FastAPI, web_dir) -> None:
    """Deliver the built website. Unknown paths get index.html so the app's own
    pages (/documents/abc) work when opened directly or refreshed."""
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    root = web_dir.resolve()
    index = root / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def website(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found.")
        target = (root / path).resolve()
        if path and target.is_file() and target.is_relative_to(root):
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            return FileResponse(target, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


def _reader(settings: Settings):
    """Claude reads guidelines when an API key is configured."""
    if not settings.anthropic_api_key:
        return None
    from .ai import ClaudeGuidelineReader
    return ClaudeGuidelineReader(settings.anthropic_api_key, settings.ai_model)


def run() -> None:
    import uvicorn
    uvicorn.run("formatly_server.main:create_app", factory=True, host="0.0.0.0", port=8000)
