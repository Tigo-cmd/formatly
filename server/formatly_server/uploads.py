"""Checking uploaded files before anything parses them."""

from __future__ import annotations

import io
import re
import zipfile

from fastapi import HTTPException, UploadFile

MAX_UNPACKED = 400 * 1024 * 1024  # a .docx that unpacks to more than this is refused (zip bomb)


async def read_limited(file: UploadFile, max_mb: int) -> bytes:
    data = await file.read(max_mb * 1024 * 1024 + 1)
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(413, f"The file is larger than {max_mb} MB.")
    if not data:
        raise HTTPException(400, "The file is empty.")
    return data


def require_docx(data: bytes) -> None:
    """A Word document (.docx). Old .doc files and PDFs are refused with a helpful message."""
    if data[:4] == b"%PDF":
        raise HTTPException(415, "This is a PDF. Please upload the Word file (.docx) of your work; "
                                 "a PDF does not keep the formatting details Formatly checks.")
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise HTTPException(415, "This is an old Word file (.doc). Open it in Word and use Save As > "
                                 "Word Document (.docx), then upload that.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = set(z.namelist())
            if "word/document.xml" not in names:
                raise HTTPException(415, "This is not a Word document (.docx).")
            if sum(i.file_size for i in z.infolist()) > MAX_UNPACKED:
                raise HTTPException(413, "This document is too large to process.")
    except zipfile.BadZipFile:
        raise HTTPException(415, "This is not a Word document (.docx).") from None


def safe_filename(name: str | None, default: str = "document.docx") -> str:
    name = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^\w .()\-]+", "_", name).strip(" .")[:150]
    return name or default
