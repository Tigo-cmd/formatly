"""File storage. Local folder now; an S3-compatible bucket (e.g. Cloudflare R2) later,
behind the same three methods."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

_KEY = re.compile(r"^[a-z]+/[0-9a-f]{32}\.[a-z]{1,5}$")


class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not _KEY.match(key):  # keys are always generated here, never taken from a user
            raise ValueError(f"bad storage key: {key!r}")
        return self.root / key

    def put(self, kind: str, data: bytes, ext: str = "docx") -> str:
        key = f"{kind}/{uuid.uuid4().hex}.{ext}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        if key:
            self._path(key).unlink(missing_ok=True)
