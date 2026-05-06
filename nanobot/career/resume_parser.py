"""Resume input parsing helpers."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


SUPPORTED_TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}


@dataclass(slots=True)
class ParsedResume:
    """Normalized resume input."""

    content_text: str
    file_path: str | None = None
    file_type: str = "pasted"


def safe_resume_filename(name: str, suffix: str = ".txt") -> str:
    """Build a stable filesystem-safe resume filename."""
    cleaned = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", name).strip("._")
    if not cleaned:
        cleaned = "resume"
    if not cleaned.lower().endswith(suffix.lower()):
        cleaned += suffix
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{cleaned}"


def parse_resume_input(
    *,
    content: str | None = None,
    file_path: str | None = None,
    resume_dir: Path | None = None,
    name: str = "resume",
) -> ParsedResume:
    """Parse pasted text or a local text resume file.

    First version intentionally supports pasted text plus UTF-8 .txt/.md files.
    PDF/DOCX parsing should be added behind this function later.
    """
    text = (content or "").strip()
    if text:
        return ParsedResume(content_text=text, file_path=None, file_type="pasted")

    if not file_path:
        raise ValueError("Either content or file_path is required")

    source = Path(file_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Resume file not found: {file_path}")
    if not source.is_file():
        raise ValueError(f"Resume path is not a file: {file_path}")

    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_TEXT_EXTENSIONS:
        raise ValueError(
            "Unsupported resume file type. First version supports only .txt and .md files."
        )

    text = source.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("Resume file is empty")

    stored_path = str(source)
    if resume_dir:
        resume_dir.mkdir(parents=True, exist_ok=True)
        target = resume_dir / safe_resume_filename(source.stem, suffix)
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        stored_path = str(target)

    return ParsedResume(content_text=text, file_path=stored_path, file_type=suffix.lstrip("."))
