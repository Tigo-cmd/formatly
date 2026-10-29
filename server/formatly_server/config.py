"""Settings, read from environment variables (prefix FORMATLY_)."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(f"FORMATLY_{name}", default)


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///./formatly.db"))
    storage_dir: Path = field(default_factory=lambda: Path(_env("STORAGE_DIR", "./storage")))
    # Signs login tokens. MUST be set in production; a random one logs everyone out on restart.
    secret_key: str = field(default_factory=lambda: _env("SECRET_KEY", "") or secrets.token_urlsafe(32))
    token_hours: int = field(default_factory=lambda: int(_env("TOKEN_HOURS", "168")))
    cors_origins: list[str] = field(default_factory=lambda: [
        o.strip() for o in _env("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()])
    max_upload_mb: int = field(default_factory=lambda: int(_env("MAX_UPLOAD_MB", "25")))
    free_credits: int = field(default_factory=lambda: int(_env("FREE_CREDITS", "2")))  # auto-fixes on sign-up
    fix_cost: int = field(default_factory=lambda: int(_env("FIX_COST", "1")))
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    ai_model: str = field(default_factory=lambda: _env("AI_MODEL", "claude-opus-5-5"))
    admin_emails: list[str] = field(default_factory=lambda: [
        e.strip().lower() for e in _env("ADMIN_EMAILS", "").split(",") if e.strip()])


settings = Settings()
