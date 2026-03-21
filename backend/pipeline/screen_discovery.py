"""Screen file discovery for prototype screen images."""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path

_SCREEN_EXTENSIONS = {".png", ".jpg", ".jpeg"}

_MIME_FALLBACK = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


@dataclass(frozen=True)
class ScreenFileInfo:
    """Metadata for one screen image file on disk."""

    filename: str
    full_path: Path
    mime_type: str


def discover_screen_files(screens_dir: Path) -> list[ScreenFileInfo]:
    """Scan *screens_dir* for PNG/JPG screen image files.

    Returns a sorted list of :class:`ScreenFileInfo`.  If *screens_dir* does
    not exist or is empty the function returns an empty list.
    """
    if not screens_dir.is_dir():
        return []

    results: list[ScreenFileInfo] = []
    for entry in sorted(screens_dir.iterdir()):
        if not entry.is_file():
            continue
        suffix = entry.suffix.lower()
        if suffix not in _SCREEN_EXTENSIONS:
            continue
        # Skip Unity .meta files that may share similar names
        if entry.name.endswith(".meta"):
            continue
        mime = mimetypes.guess_type(entry.name)[0] or _MIME_FALLBACK.get(suffix, "application/octet-stream")
        results.append(
            ScreenFileInfo(
                filename=entry.name,
                full_path=entry.resolve(),
                mime_type=mime,
            )
        )
    return results
