"""Local JPEG archive — photos only (RAW discarded upstream)."""

from __future__ import annotations

import shutil
from pathlib import Path

JPEG_SUFFIXES = {".jpg", ".jpeg"}
RAW_SUFFIXES = {".arw", ".raw", ".nef", ".cr2", ".cr3", ".dng", ".raf", ".orf", ".rw2"}


class FileStorage:
    def __init__(self, photos_dir: Path) -> None:
        self.photos_dir = photos_dir
        self.photos_dir.mkdir(parents=True, exist_ok=True)
        # Back-compat alias used by older call sites
        self.uploads_dir = self.photos_dir

    def archive_photo(self, source: Path, photo_id: str) -> Path:
        if source.suffix.lower() not in JPEG_SUFFIXES:
            raise ValueError(f"Chỉ lưu JPEG, nhận được: {source.suffix}")
        dest = self.photos_dir / f"{photo_id}.jpg"
        shutil.copy2(source, dest)
        return dest

    def archive_frame(self, source: Path, session_id: str, frame_index: int) -> Path:
        """Save one burst frame as ``{session_id}_1.jpg`` … (1-based index)."""
        if source.suffix.lower() not in JPEG_SUFFIXES:
            raise ValueError(f"Chỉ lưu JPEG, nhận được: {source.suffix}")
        dest = self.photos_dir / f"{session_id}_{frame_index}.jpg"
        shutil.copy2(source, dest)
        return dest

    def get_session_frames(self, session_id: str) -> list[Path]:
        frames: list[Path] = []
        for i in range(1, 32):
            path = self.photos_dir / f"{session_id}_{i}.jpg"
            if path.exists():
                frames.append(path)
            elif frames:
                break
        return frames

    def get_photo(self, photo_id: str) -> Path | None:
        for ext in (".jpg", ".jpeg"):
            path = self.photos_dir / f"{photo_id}{ext}"
            if path.exists():
                return path
        return None

    def list_photos(self) -> list[Path]:
        return sorted(
            (p for p in self.photos_dir.iterdir() if p.suffix.lower() in JPEG_SUFFIXES),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )


def discard_raw_files(directory: Path) -> int:
    """Delete RAW sidecars in *directory*. Returns count removed."""
    removed = 0
    if not directory.exists():
        return 0
    for path in directory.iterdir():
        if path.is_file() and path.suffix.lower() in RAW_SUFFIXES:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def pick_jpeg(directory: Path) -> Path | None:
    """Newest JPEG in directory, if any."""
    jpegs = [
        p
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in JPEG_SUFFIXES
    ]
    if not jpegs:
        return None
    return max(jpegs, key=lambda p: p.stat().st_mtime)
