"""Simple local file storage for captured / printed assets."""

from __future__ import annotations

import shutil
from pathlib import Path


class FileStorage:
    def __init__(self, uploads_dir: Path) -> None:
        self.uploads_dir = uploads_dir
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    def archive_photo(self, source: Path, photo_id: str) -> Path:
        dest = self.uploads_dir / f"{photo_id}.jpg"
        shutil.copy2(source, dest)
        return dest

    def get_photo(self, photo_id: str) -> Path | None:
        for ext in (".jpg", ".jpeg", ".png"):
            path = self.uploads_dir / f"{photo_id}{ext}"
            if path.exists():
                return path
        return None
