from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


def extract_text_pages(path: Path, max_pages: int | None = None) -> list[str]:
    reader = PdfReader(str(path))
    pages = reader.pages
    if max_pages is not None:
        pages = pages[:max_pages]

    texts: list[str] = []
    for page in pages:
        text = page.extract_text() or ""
        text = " ".join(text.split())
        if text:
            texts.append(text)

    return texts


def extract_text_from_pdf(path: Path, max_pages: int | None = None) -> str:
    return "\n".join(extract_text_pages(path, max_pages=max_pages))
